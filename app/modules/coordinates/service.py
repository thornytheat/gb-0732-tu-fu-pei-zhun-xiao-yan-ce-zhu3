from app.errors import RegisterError
from app.modules.coordinates.numbers import clean, failure, point_name
from app.modules.coordinates.projection import ground_position, pixel_position
from app.reasons import finding


def convert(intake):
    catalog = intake['catalog']
    sheets = {sheet['code']: sheet for sheet in catalog['sheets']}
    origin = (catalog['longitude_deg'], catalog['latitude_deg'])
    values = {'pixels': [], 'ground': [], 'quarantine': [], 'counts': {}}
    for kind in ('pixels', 'ground'):
        filename = f'{kind}.csv'
        table = intake['tables'][filename]
        values['quarantine'].extend(table['quarantine'])
        for row in table['rows']:
            sheet, name = clean(row['sheet']).upper(), point_name(row['name'])
            try:
                if sheet not in sheets:
                    raise failure('UNKNOWN_SHEET')
                if not name:
                    raise failure('EMPTY_NAME')
                point = (pixel_position(row['u'], row['v'], sheets[sheet]) if kind == 'pixels'
                         else ground_position(row, origin))
                values[kind].append({'source': row['source'], 'sheet': sheet, 'name': name, 'xy': point})
            except RegisterError as error:
                values['quarantine'].append(finding(row['source'], error.code, sheet=sheet, name=name))
        values['counts'][kind] = table['records']
    return values
