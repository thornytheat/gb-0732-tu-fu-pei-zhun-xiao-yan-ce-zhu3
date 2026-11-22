from collections import defaultdict
from math import dist, floor

from app.config import POSITION_EPSILON_PX
from app.errors import RegisterError
from app.modules.coordinates.numbers import clean, failure, point_name
from app.modules.coordinates.projection import pixel_position
from app.modules.seams.geometry import duplicate_sources, edge_fraction
from app.reasons import finding


class TrainingIndex:
    def __init__(self, pixels, aliases):
        self.aliases = aliases
        self.names, self.cells = defaultdict(set), defaultdict(list)
        for row in pixels:
            sheet = row['sheet']
            self.names[sheet].add(aliases.get(row['name'], row['name']))
            self.cells[(sheet, *self.cell(row['xy']))].append(row['xy'])

    @staticmethod
    def cell(pixel):
        return tuple(floor(value / POSITION_EPSILON_PX) for value in pixel)

    def reused(self, sheet, name, pixel):
        if self.aliases.get(name, name) in self.names[sheet]:
            return True
        x, y = self.cell(pixel)
        return any(dist(pixel, prior) <= POSITION_EPSILON_PX
                   for u in range(x - 1, x + 2) for v in range(y - 1, y + 2)
                   for prior in self.cells.get((sheet, u, v), ()))


def read_witnesses(rows, edge, a, b, training):
    valid, quarantine = [], []
    for row in rows:
        name = point_name(row['name'])
        try:
            if not name:
                raise failure('EMPTY_NAME')
            a_pixel = pixel_position(row['au'], row['av'], a)
            b_pixel = pixel_position(row['bu'], row['bv'], b)
            at = edge_fraction(a_pixel, a, edge['a_side'])
            bt = edge_fraction(b_pixel, b, edge['b_side'])
            if training.reused(a['code'], name, a_pixel) or training.reused(b['code'], name, b_pixel):
                raise failure('TRAINING_REUSE')
            valid.append({'source': row['source'], 'name': name, 'a_pixel': a_pixel, 'b_pixel': b_pixel,
                          'at': at, 'bt': bt})
        except RegisterError as error:
            quarantine.append(finding(row['source'], error.code, edge=edge['code'], name=name))
    duplicates = duplicate_sources(valid, a, b, edge['a_side'], edge['b_side'])
    retained = []
    for row in valid:
        if row['source']['id'] in duplicates:
            quarantine.append(finding(row['source'], 'EDGE_DUPLICATE', edge=edge['code'], name=row['name']))
        else:
            retained.append(row)
    return sorted(retained, key=lambda row: row['at']), quarantine


def split_by_edge(table, catalog):
    known = {edge['code'] for edge in catalog['edges']}
    by_edge, issues = defaultdict(list), defaultdict(list)
    for error in table['quarantine']:
        edge = clean(error.get('edge', '')).upper()
        issues[edge if edge in known else None].append(error)
    for row in table['rows']:
        edge = clean(row['edge']).upper()
        if edge in known:
            by_edge[edge].append(row)
        else:
            issues[None].append(finding(row['source'], 'UNKNOWN_EDGE', edge=edge))
    return by_edge, issues
