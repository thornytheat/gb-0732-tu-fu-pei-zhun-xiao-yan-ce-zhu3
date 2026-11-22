import csv
import io

from app.errors import RegisterError
from app.reasons import finding

HEADERS = {
    'pixels.csv': dict(zip(('图幅', '点名', '像素列', '像素行', '备注'),
                           ('sheet', 'name', 'u', 'v', 'note'))),
    'ground.csv': dict(zip(('图幅', '点名', '坐标系', '单位', '横坐标', '纵坐标', '备注'),
                           ('sheet', 'name', 'crs', 'unit', 'x', 'y', 'note'))),
    'witness.csv': dict(zip(('拼缝', '证点', '甲列', '甲行', '乙列', '乙行', '备注'),
                            ('edge', 'name', 'au', 'av', 'bu', 'bv', 'note'))),
}


def header_keys(fields, filename):
    mapping = HEADERS[filename]
    return tuple(mapping.get(value.strip(), value.strip()) for value in fields)


def read_rows(text, filename, encoding):
    header = None
    rows, quarantine = [], []
    blank = repeated = end = 0
    reader = csv.reader(io.StringIO(text, newline=''), strict=True)
    try:
        for fields in reader:
            start = end + 1
            end = reader.line_num
            if not any(value.strip() for value in fields):
                blank += 1
                continue
            possible_header = header_keys(fields, filename)
            if header is None:
                expected = set(HEADERS[filename].values())
                if len(fields) != len(expected) or set(possible_header) != expected:
                    raise RegisterError('BAD_HEADER', '点表字段与登记格式不符',
                                        evidence={'file': filename, 'line': start})
                header = possible_header
                continue
            if possible_header == header:
                repeated += 1
                continue
            source = {'id': f'{filename}:{start}', 'file': filename, 'line': start,
                      'end_line': end, 'raw': fields}
            if len(fields) != len(header):
                hints = {key: fields[header.index(key)].strip() for key in ('sheet', 'edge', 'name')
                         if key in header and header.index(key) < len(fields)}
                quarantine.append(finding(source, 'COLUMN_COUNT', **hints))
                continue
            rows.append({'source': source, **dict(zip(header, fields))})
    except csv.Error as error:
        raise RegisterError('MALFORMED_CSV', '引号未闭合或字段格式损坏',
                            evidence={'file': filename, 'line': reader.line_num}) from error

    if header is None:
        state = 'BLANK_FILE' if blank else 'EMPTY_FILE'
    elif not rows and not quarantine:
        state = 'HEADER_ONLY'
    else:
        state = 'RECEIVED'
    return {'file': filename, 'encoding': encoding, 'state': state, 'blank': blank, 'headers': repeated,
            'records': len(rows) + len(quarantine), 'rows': rows, 'quarantine': quarantine}
