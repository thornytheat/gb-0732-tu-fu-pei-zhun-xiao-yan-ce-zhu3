import pytest

from app.errors import RegisterError
from app.modules.affine.service import fit
from app.modules.refit.consensus import consensus_fit, inliers
from conftest import controls, known_transform


def test_refit_recovers_good_points_that_initial_fit_would_drop(field):  # TRAP-28
    result = field.refit
    outlier, = result['outliers']
    assert (outlier['name'], outlier['reason'], outlier['sheet']) == ('P08', 'CONTROL_OUTLIER', '0421')
    assert outlier['after']['distance_m'] == pytest.approx(15.88445, abs=1e-5)
    assert outlier['pixel_source']['raw'][1] == 'P08'
    assert outlier['ground_source']['raw'][1] == 'P08'
    recovered = [row for row in result['accepted'] if row['before']['distance_m'] > .75]
    assert len(recovered) >= 4
    assert all(row['after']['distance_m'] < .15 for row in recovered)


def test_refit_exports_a_world_footprint_from_the_final_model(field):
    first = field.refit['sheets']['0421']['footprint']
    assert len(first) == 4
    assert first[0] == pytest.approx((100, 850), abs=.15)
    assert first[2] == pytest.approx((713.5, 412.0), abs=.15)


def test_consensus_rejects_insufficient_evidence_for_a_fourth_outlier():
    pixels = [(0, 0), (0, 700), (600, 0)]
    points = controls([*((pixel, known_transform(pixel)) for pixel in pixels), ((600, 700), (990, 995))])
    with pytest.raises(RegisterError) as caught:
        consensus_fit(points, {'status': 'FIT', **fit(points)}, .75)
    assert caught.value.code == 'NO_CONSENSUS'


def test_same_size_alternate_models_return_ambiguity_instead_of_arbitrary_choice():  # TRAP-19
    # The two correctable hypotheses share four controls along v=0 and take different off-line pairs.
    pairs = [((u, 0), (u, 0)) for u in (0, 10, 20, 30)]
    pairs += [((0, 25), (0, 25)), ((25, 25), (25, 25)), ((0, 40), (0, 80)), ((25, 40), (25, 80))]
    for points in (controls(pairs), controls(reversed(pairs))):
        with pytest.raises(RegisterError) as caught:
            consensus_fit(points, {'status': 'FIT', **fit(points)}, .1)
        assert caught.value.code == 'AMBIGUOUS_CONTROLS'


def test_threshold_is_inclusive_but_does_not_round_away_overage():
    records = [{'id': 'a', 'distance_m': .75}, {'id': 'b', 'distance_m': .750004}]
    assert inliers(records, .75) == {'a'}


def test_refit_does_not_convert_degenerate_points_to_outliers(field):
    result = field.refit
    assert result['sheets']['0432']['reason'] == 'COLLINEAR_PIXELS'
    assert len([row for row in result['quarantine'] if row['sheet'] == '0432']) == 7
    assert not any(row['sheet'] == '0432' for row in result['outliers'])


def test_all_calibrated_controls_remain_accepted_and_unchanged(reference):
    assert len(reference.refit['accepted']) == 48
    assert reference.refit['outliers'] == []
    assert all(row['before'] == row['after'] for row in reference.refit['accepted'])
