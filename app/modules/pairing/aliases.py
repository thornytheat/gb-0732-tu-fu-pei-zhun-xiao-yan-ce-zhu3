from app.errors import RegisterError
from app.modules.coordinates.numbers import point_name


def resolve_aliases(aliases):
    links, resolved = {}, {}
    for raw_alias, raw_target in aliases.items():
        alias, target = point_name(raw_alias), point_name(raw_target)
        if not alias or not target or (alias in links and links[alias] != target):
            raise RegisterError('ALIAS_AMBIGUOUS', '点名别名登记冲突', evidence=raw_alias)
        links[alias] = target
    links = {alias: target for alias, target in links.items() if alias != target}
    for alias in links:
        path, seen, current = [], set(), alias
        while current in links and current not in resolved:
            if current in seen:
                raise RegisterError('ALIAS_CYCLE', '点名别名出现循环', evidence=path + [current])
            seen.add(current)
            path.append(current)
            current = links[current]
        target = resolved.get(current, current)
        resolved.update(dict.fromkeys(path, target))
    return resolved
