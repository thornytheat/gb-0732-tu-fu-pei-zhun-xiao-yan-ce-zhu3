from collections import defaultdict
from math import dist

from app.reasons import finding

EPSILON = {'PIXEL': 0.001, 'GROUND': 0.001}


def resolve_observations(rows, aliases, kind):
    grouped = defaultdict(list)
    for row in rows:
        name = aliases.get(row['name'], row['name'])
        grouped[row['sheet'], name].append(row)
    selected, conflicts, quarantine = {}, {}, []
    for key, group in sorted(grouped.items()):
        group.sort(key=lambda row: row['source']['line'])
        sheet, name = key
        # Compare the full spread, including cases where nearby readings form a chain.
        positions = list(dict.fromkeys(row['xy'] for row in group))
        x_values, y_values = zip(*positions)
        extremes = ((min(x_values), min(y_values)), (max(x_values), max(y_values)))
        # The bounding rectangle is a quick acceptance test. Compare pairs only when needed.
        epsilon = EPSILON[kind]
        conflict = dist(*extremes) > epsilon and any(
            dist(point, other) > epsilon
            for index, point in enumerate(positions) for other in positions[index + 1:]
        )
        if conflict:
            sources = [row['source']['id'] for row in group]
            conflicts[key] = sources
            quarantine.extend(finding(row['source'], f'{kind}_CONFLICT', sheet=sheet, name=name,
                                      observations=sources) for row in group)
            continue
        # Highest available source precision is unspecified, so prefer the first physical row.
        keep, *duplicates = group
        selected[key] = keep
        quarantine.extend(finding(row['source'], f'{kind}_REPEAT', sheet=sheet, name=name,
                                  kept=keep['source']['id']) for row in duplicates)
    return selected, conflicts, quarantine
