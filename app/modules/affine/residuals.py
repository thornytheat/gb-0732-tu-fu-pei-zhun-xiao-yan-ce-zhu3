import math


def project(model, pixel):
    u, v = pixel
    return tuple(a * u + b * v + c for a, b, c in (model['east'], model['north']))


def residuals(model, points):
    result = []
    for point in points:
        east, north = project(model, point['pixel'])
        dx, dy = east - point['ground'][0], north - point['ground'][1]
        result.append({'id': point['id'], 'name': point['name'], 'projected': (east, north),
                       'dx_m': dx, 'dy_m': dy, 'distance_m': math.hypot(dx, dy)})
    return result


def summarize(rows):
    if not rows:
        return None
    return {'rms_m': math.sqrt(math.fsum(row['distance_m'] ** 2 for row in rows) / len(rows)),
            'max_m': max(row['distance_m'] for row in rows)}
