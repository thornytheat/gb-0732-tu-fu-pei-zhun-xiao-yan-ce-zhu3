from itertools import combinations

from app.errors import RegisterError
from app.modules.affine.residuals import residuals
from app.modules.affine.service import fit
from app.modules.coordinates.numbers import failure

LIMIT_EPSILON_M = 1e-9


def inliers(rows, limit):
    return frozenset(row['id'] for row in rows if row['distance_m'] <= limit + LIMIT_EPSILON_M)


def classify(model, points, limit):
    return inliers(residuals(model, points), limit)


def consensus_fit(points, initial, limit):
    if initial['status'] == 'FIT' and len(inliers(initial['residuals'], limit)) == len(points):
        return frozenset(point['id'] for point in points), initial
    # A triple can determine a map but cannot by itself rule a fourth observation out.
    minimum = max(4, len(points) // 2 + 1)
    if minimum >= len(points):
        raise failure('NO_CONSENSUS')
    seeds = set()
    for trial in combinations(points, 3):
        try:
            candidate = classify(fit(trial)['model'], points, limit)
        except RegisterError:
            continue
        if len(candidate) >= minimum:
            seeds.add(candidate)

    visited, stable = {}, {}
    for seed in sorted(seeds, key=lambda key: (-len(key), sorted(key))):
        mask = seed
        # Each refit is deterministic for its point set. Memoizing the successor also breaks cycles.
        while len(mask) >= minimum and mask not in visited:
            selected = [point for point in points if point['id'] in mask]
            try:
                fitted = fit(selected)
            except RegisterError:
                visited[mask] = None
                break
            next_mask = classify(fitted['model'], points, limit)
            visited[mask] = next_mask
            if next_mask == mask:
                stable[mask] = fitted
                break
            mask = next_mask
    if not stable:
        raise failure('NO_CONSENSUS')
    size = max(map(len, stable))
    leaders = [mask for mask in stable if len(mask) == size]
    if len(leaders) != 1:
        raise failure('AMBIGUOUS_CONTROLS')
    mask = leaders[0]
    return mask, stable[mask]
