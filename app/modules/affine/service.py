from collections import defaultdict

from app.errors import RegisterError
from app.modules.affine.residuals import residuals, summarize
from app.modules.affine.solve import solve_affine


def fit(points):
    model = solve_affine(points)
    rows = residuals(model, points)
    return {'model': model, 'residuals': rows, **summarize(rows)}


def fit_sheets(pairing, catalog):
    grouped = defaultdict(list)
    for pair in pairing['pairs']:
        grouped[pair['sheet']].append(pair)
    result = {}
    for sheet in catalog['sheets']:
        code = sheet['code']
        points = grouped[code]
        try:
            result[code] = {'status': 'FIT', 'count': len(points), **fit(points)}
        except RegisterError as error:
            result[code] = {'status': 'BLOCKED', 'count': len(points), 'reason': error.code}
    return result
