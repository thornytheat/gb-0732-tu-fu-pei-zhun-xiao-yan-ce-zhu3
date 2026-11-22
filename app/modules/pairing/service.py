from app.modules.pairing.aliases import resolve_aliases
from app.modules.pairing.duplicates import resolve_observations
from app.reasons import finding


def pair_controls(converted, catalog):
    aliases = resolve_aliases(catalog['aliases'])
    pixels, _, pixel_issues = resolve_observations(converted['pixels'], aliases, 'PIXEL')
    ground, conflicts, ground_issues = resolve_observations(converted['ground'], aliases, 'GROUND')
    quarantine = converted['quarantine'] + pixel_issues + ground_issues
    pairs, used_ground = [], set()
    for (sheet, name), pixel in pixels.items():
        key = sheet, name
        if key in conflicts:
            quarantine.append(finding(pixel['source'], 'GROUND_CONFLICT', sheet=sheet, name=name,
                                      observations=conflicts[key]))
        elif key not in ground:
            quarantine.append(finding(pixel['source'], 'MISSING_GROUND', sheet=sheet, name=name))
        else:
            record = ground[key]
            used_ground.add(key)
            pairs.append({'id': pixel['source']['id'], 'sheet': sheet, 'name': name, 'pixel': pixel['xy'],
                          'ground': record['xy'], 'pixel_source': pixel['source'],
                          'ground_source': record['source']})
    for key in sorted(ground.keys() - used_ground):
        sheet, name = key
        quarantine.append(finding(ground[key]['source'], 'UNUSED_GROUND', sheet=sheet, name=name))
    quarantine.sort(key=lambda mark: (mark['source']['file'], mark['source']['line']))
    return {'pairs': pairs, 'quarantine': quarantine, 'aliases': aliases, 'counts': converted['counts']}
