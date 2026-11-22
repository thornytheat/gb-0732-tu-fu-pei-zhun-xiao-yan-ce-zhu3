import math
from statistics import median

from app.config import POSITION_EPSILON_PX
from app.modules.affine.residuals import project
from app.modules.coordinates.numbers import failure

MIN_STATIONS = 3
MIN_COVERAGE = 0.60
EDGE_TOLERANCE_PX = 0.5
DISTANCE_EPSILON_M = 1e-9


def endpoints(sheet, side):
    width, height = sheet['width_px'], sheet['height_px']
    return {'N': ((0, 0), (width, 0)), 'E': ((width, 0), (width, height)),
            'S': ((0, height), (width, height)), 'W': ((0, 0), (0, height))}[side]


def edge_fraction(pixel, sheet, side):
    first, last = endpoints(sheet, side)
    axis = 0 if side in ('N', 'S') else 1
    if abs(pixel[1 - axis] - first[1 - axis]) > EDGE_TOLERANCE_PX:
        raise failure('OFF_EDGE')
    return pixel[axis] / last[axis]


def coverage(rows):
    if not rows:
        return [0.0, 0.0]
    return [max(row[key] for row in rows) - min(row[key] for row in rows) for key in ('at', 'bt')]


def duplicate_sources(rows, a, b, a_side, b_side):
    duplicates, by_name = set(), {}
    for row in rows:
        previous = by_name.setdefault(row['name'], row)
        if previous is not row:
            duplicates.update((previous['source']['id'], row['source']['id']))
    for key, sheet, side in (('at', a, a_side), ('bt', b, b_side)):
        length = sheet['width_px'] if side in ('N', 'S') else sheet['height_px']
        ordered = sorted(rows, key=lambda row: row[key])
        for left, right in zip(ordered, ordered[1:]):
            if (right[key] - left[key]) * length <= POSITION_EPSILON_PX:
                duplicates.update((left['source']['id'], right['source']['id']))
    return duplicates


def measure_gap(rows, a_model, b_model, a_edge, b_edge):
    a_line = [project(a_model, point) for point in a_edge]
    b_line = [project(b_model, point) for point in b_edge]
    (x1, y1), (x2, y2) = a_line
    length = math.dist(*a_line)
    tx, ty = (x2 - x1) / length, (y2 - y1) / length
    stations = []
    for row in rows:
        a_world, b_world = project(a_model, row['a_pixel']), project(b_model, row['b_pixel'])
        dx, dy = b_world[0] - a_world[0], b_world[1] - a_world[1]
        stations.append({**row, 'a_world': a_world, 'b_world': b_world, 'dx_m': dx, 'dy_m': dy,
                         'tangent_m': dx * tx + dy * ty, 'normal_m': -dx * ty + dy * tx,
                         'gap_m': math.hypot(dx, dy)})
    gaps = [station['gap_m'] for station in stations]
    return {'stations': stations, 'a_line': a_line, 'b_line': b_line,
            'max_m': max(gaps, default=None), 'median_m': median(gaps) if gaps else None}
