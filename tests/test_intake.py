import pytest

from app.errors import RegisterError
from app.modules.intake.catalog import read_catalog
from app.modules.intake.decode import decode_table
from app.modules.intake.reader import read_rows


def test_gb18030_archive(field):  # TRAP-01
    ground = field.intake['tables']['ground.csv']
    assert ground['encoding'] == 'gb18030'
    assert ground['rows'][0]['name'] == 'Ｐ０１'
    assert ground['rows'][1]['note'] == '坐标抄自经纬簿'


def test_bom_stripped_from_first_header(field):  # TRAP-02
    pixels = field.intake['tables']['pixels.csv']
    assert pixels['encoding'] == 'utf-8-sig'
    assert pixels['rows'][0]['sheet'] == '0421'


def test_multiline_records_preserve_physical_lines(field):  # TRAP-03
    rows = field.intake['tables']['pixels.csv']['rows']
    assert rows[0]['note'] == '复核点\n旧簿名'
    assert (rows[0]['source']['line'], rows[0]['source']['end_line']) == (2, 3)
    assert rows[1]['source']['id'] == 'pixels.csv:4'


def test_repeated_section_header_is_counted_separately(field):  # TRAP-04
    pixels = field.intake['tables']['pixels.csv']
    assert (pixels['headers'], pixels['blank'], pixels['records']) == (1, 1, 53)
    assert not any(row['sheet'] == '图幅' for row in pixels['rows'])


def test_extra_delimiter_preserves_unshifted_raw_row(field):  # TRAP-05
    row, = field.intake['tables']['pixels.csv']['quarantine']
    assert (row['reason'], row['name'], row['source']['line']) == ('COLUMN_COUNT', '短行', 19)
    assert row['source']['raw'] == ['0421', '短行', '590', '650', '多余分隔符', '']


def test_empty_blank_and_header_only_are_distinct(field):  # TRAP-18
    filename = 'pixels.csv'
    header = field.bundle[filename].decode('utf-8-sig').splitlines()[0]
    states = [read_rows(text, filename, 'utf-8')['state'] for text in ('', '\n, ,\r\n', header)]
    assert states == ['EMPTY_FILE', 'BLANK_FILE', 'HEADER_ONLY']


def test_open_quote_after_valid_records_rejects_whole_table(field):  # TRAP-16
    text = field.bundle['witness.csv'].decode()
    with pytest.raises(RegisterError) as caught:
        read_rows(text + 'HX-QS,"unfinished', 'witness.csv', 'utf-8')
    assert caught.value.code == 'MALFORMED_CSV'
    assert caught.value.evidence == {'file': 'witness.csv', 'line': 21}


def test_english_columns_may_be_reordered(field):  # TRAP-17
    text = 'name,note,v,u,sheet\nP01,边桩,129,115,0421\n'
    row, = read_rows(text, 'pixels.csv', 'utf-8')['rows']
    assert {k: row[k] for k in ('sheet', 'u', 'v')} == {'sheet': '0421', 'u': '115', 'v': '129'}
    assert field.intake['tables']['pixels.csv']['rows'][0]['u'] == row['u']


def test_catalog_rejects_a_sheet_joined_to_itself(field):
    raw = field.bundle['catalog.json'].replace(b'"b": "0422"', b'"b": "0421"', 1)
    with pytest.raises(RegisterError, match='图幅登记册无效') as caught:
        read_catalog(raw)
    assert caught.value.code == 'BAD_CATALOG'


def test_invalid_bom_payload_is_not_reinterpreted():
    with pytest.raises(RegisterError) as caught:
        decode_table(b'\xef\xbb\xbf\xff', 'pixels.csv')
    assert caught.value.evidence == {'file': 'pixels.csv', 'byte': 0}
