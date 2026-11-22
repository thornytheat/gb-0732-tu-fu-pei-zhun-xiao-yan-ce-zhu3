import pytest

from app.errors import RegisterError
from app.modules.affine.residuals import project
from app.modules.affine.service import fit
from conftest import controls, known_transform


def test_three_noncollinear_points_determine_full_affine():
    pixels = [(9, 20), (125, 29), (45, 550)]
    result = fit(controls((pixel, known_transform(pixel)) for pixel in pixels))
    assert result['model']['east'] == pytest.approx([.5, .02, 100], abs=1e-10)
    assert result['model']['north'] == pytest.approx([-.01, -.49, 800], abs=1e-10)
    assert project(result['model'], (87, 99)) == pytest.approx(known_transform((87, 99)), abs=1e-10)


def test_collinear_scans_are_blocked_even_with_seven_controls(field):  # TRAP-27
    assert field.affine['0432'] == {'status': 'BLOCKED', 'count': 7, 'reason': 'COLLINEAR_PIXELS'}


def test_too_few_and_nearly_collinear_control_designs_fail():
    with pytest.raises(RegisterError) as small:
        fit(controls([((0, 0), (0, 0))] * 2))
    pixels = [(0, 0), (30_000, 30_000), (60_000, 60_000.000001)]
    with pytest.raises(RegisterError) as skinny:
        fit(controls((pixel, known_transform(pixel)) for pixel in pixels))
    assert (small.value.code, skinny.value.code) == ('TOO_FEW_CONTROLS', 'COLLINEAR_PIXELS')


def test_independent_design_with_rank_deficient_ground_is_blocked():
    with pytest.raises(RegisterError) as caught:
        fit(controls([((0, 0), (0, 0)), ((300, 0), (10, 0)), ((0, 300), (30, 0))]))
    assert caught.value.code == 'SINGULAR_TRANSFORM'


def test_centering_keeps_large_pixel_origins_stable():
    pixels = [(98_000, 97_000), (98_100, 97_000), (98_000, 97_400), (98_250, 97_240)]
    result = fit(controls((pixel, known_transform(pixel)) for pixel in pixels))
    assert project(result['model'], (98_220, 97_100)) == pytest.approx(known_transform((98_220, 97_100)), abs=1e-9)
    assert result['model']['condition'] < 4


def test_full_sample_initial_fit_distributes_large_error(field):
    result = field.affine['0421']
    p08 = next(row for row in result['residuals'] if row['name'] == 'P08')
    assert result['count'] == 12
    assert result['rms_m'] == pytest.approx(3.634053, abs=1e-6)
    assert p08['distance_m'] == pytest.approx(9.973543, abs=1e-6)
    assert sum(row['distance_m'] > .75 for row in result['residuals']) >= 5


def test_calibrated_sample_retains_orientation_and_small_residual(reference):
    result = reference.affine['0422']
    assert result['model']['determinant'] == pytest.approx(-.25015, abs=.0001)
    assert result['rms_m'] == pytest.approx(.0709123, abs=1e-6)
    assert result['count'] == 12


def test_bound_prevents_unbounded_candidate_search():
    with pytest.raises(RegisterError) as caught:
        fit(controls([((1, 2), (3, 4))] * 33))
    assert caught.value.code == 'TOO_MANY_CONTROLS'
