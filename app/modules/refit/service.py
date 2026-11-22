from collections import defaultdict

from app.errors import RegisterError
from app.modules.affine.residuals import project, residuals
from app.modules.coordinates.numbers import failure
from app.modules.refit.consensus import consensus_fit
from app.reasons import finding


def refit_sheets(pairing, initial, catalog, control_limit_m):
    grouped = defaultdict(list)
    for point in pairing['pairs']:
        grouped[point['sheet']].append(point)
    sheets, accepted, outliers = {}, [], []
    quarantine = list(pairing['quarantine'])
    for specification in catalog['sheets']:
        sheet = specification['code']
        first = initial[sheet]
        points = grouped[sheet]
        try:
            if first['status'] == 'BLOCKED' and first['reason'] != 'SINGULAR_TRANSFORM':
                raise failure(first['reason'])
            selected, final = consensus_fit(points, first, control_limit_m)
        except RegisterError as error:
            sheets[sheet] = {'status': 'BLOCKED', 'reason': error.code, 'count': len(points)}
            quarantine.extend(finding(point['pixel_source'], error.code, sheet=sheet, name=point['name'],
                                      ground_source=point['ground_source']) for point in points)
            continue
        before = {row['id']: row for row in first.get('residuals', [])}
        final_rows = {row['id']: row for row in residuals(final['model'], points)}
        for point in points:
            identity = point['id']
            record = {**point, 'before': before.get(identity), 'after': final_rows[identity]}
            if identity in selected:
                accepted.append(record)
            else:
                outliers.append({**record, **finding(point['pixel_source'], 'CONTROL_OUTLIER')})
        width, height = specification['width_px'], specification['height_px']
        corners = ((0, 0), (width, 0), (width, height), (0, height))
        footprint = [project(final['model'], pixel) for pixel in corners]
        sheets[sheet] = {'footprint': footprint, 'status': 'FIT', 'count': len(selected), 'removed': len(points) - len(selected),
                         'model': final['model'], 'rms_m': final['rms_m'], 'max_m': final['max_m']}
    return {'sheets': sheets, 'accepted': accepted, 'outliers': outliers, 'quarantine': quarantine}
