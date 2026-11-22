import numpy as np

from app.config import MAX_SHEET_POINTS
from app.modules.coordinates.numbers import failure

RANK_TOLERANCE = 1e-8
MIN_SCALE_M_PER_PX = 1e-9


def solve_affine(points):
    if len(points) < 3:
        raise failure('TOO_FEW_CONTROLS')
    if len(points) > MAX_SHEET_POINTS:
        raise failure('TOO_MANY_CONTROLS')
    pixels = np.array([point['pixel'] for point in points], dtype=float)
    ground = np.array([point['ground'] for point in points], dtype=float)
    center, target_center = pixels.mean(axis=0), ground.mean(axis=0)
    centered = pixels - center
    scale = float(np.linalg.norm(centered, axis=1).max())
    if scale == 0:
        raise failure('COLLINEAR_PIXELS')
    design = np.column_stack((centered / scale, np.ones(len(points))))
    coeff, _, rank, spectrum = np.linalg.lstsq(design, ground - target_center, rcond=RANK_TOLERANCE)
    if rank != 3:
        raise failure('COLLINEAR_PIXELS')
    linear = coeff[:2] / scale
    singular_values = np.linalg.svd(linear, compute_uv=False)
    if singular_values[1] <= max(MIN_SCALE_M_PER_PX, singular_values[0] * RANK_TOLERANCE):
        raise failure('SINGULAR_TRANSFORM')
    shift = target_center + coeff[2] - center @ linear
    return {'east': [float(linear[0, 0]), float(linear[1, 0]), float(shift[0])],
            'north': [float(linear[0, 1]), float(linear[1, 1]), float(shift[1])],
            'condition': float(spectrum[0] / spectrum[-1]),
            'determinant': float(np.linalg.det(linear))}
