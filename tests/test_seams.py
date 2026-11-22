from math import hypot

import pytest

from app.modules.seams.geometry import measure_gap
from conftest import by_key, replace_witness_table

HEADER = '拼缝,证点,甲列,甲行,乙列,乙行,备注\n'


def test_independent_edge_fails_even_when_both_training_residuals_are_small(field):  # TRAP-29
    edge = by_key(field.seams['edges'], 'HX-QS')
    assert all(field.refit['sheets'][key]['rms_m'] < .08 for key in ('0421', '0422'))
    assert (edge['status'], edge['reason'], edge['count']) == ('FAIL', 'GAP_OVER_LIMIT', 6)
    assert edge['max_m'] == pytest.approx(2.521602, abs=1e-5)
    assert edge['stations'][0]['source']['id'] == 'witness.csv:2'
    assert all(row['source']['file'] == 'witness.csv' for row in edge['stations'])


def test_low_gap_and_missing_model_are_distinct(field):
    passed, blocked = (by_key(field.seams['edges'], code) for code in ('HX-LW', 'QS-SJ'))
    assert passed['max_m'] == pytest.approx(.433304, abs=1e-5)
    assert passed['status'] == 'PASS'
    assert (blocked['status'], blocked['reason'], blocked['max_m'], blocked['count']) == ('BLOCKED', 'MODEL_UNAVAILABLE', None, 6)
    assert blocked['stations'][0]['a_pixel'] == (93, 900)


def test_signed_components_preserve_direction_and_total_distance(reference):
    edge = by_key(reference.seams['edges'], 'HX-LW')
    assert edge['status'] == 'PASS'
    for station in edge['stations']:
        assert hypot(station['tangent_m'], station['normal_m']) == pytest.approx(station['gap_m'], abs=1e-9)
        assert station['normal_m'] < 0


def test_unknown_witness_edge_keeps_source_without_polluting_known_edges(field):
    row, = field.seams['quarantine']
    assert (row['reason'], row['edge'], row['source']['line']) == ('UNKNOWN_EDGE', 'QX-99', 20)
    assert sum(edge['count'] for edge in field.seams['edges']) == 18


def test_pseudo_witness_reusing_a_control_alias_is_excluded(field):  # TRAP-30
    altered = field.bundle['witness.csv'].decode().replace('HX-QS-01', '河西旧一', 1)
    replace_witness_table(field, altered)
    row = by_key(field.seams['quarantine'], 'TRAINING_REUSE', key='reason')
    edge = by_key(field.seams['edges'], 'HX-QS')
    assert row['source']['id'] == 'witness.csv:2'
    assert edge['count'] == 5
    assert 'EDGE_DIRTY' in edge['reasons']


def test_duplicate_positions_and_off_edge_records_cannot_supply_coverage(reference):
    raw = HEADER + 'HX-QS,ONE,1200,100,0,100,x\nHX-QS,TWO,1200,100.04,0,104,y\nHX-QS,THREE,1199,800,0,800,z\n'
    replace_witness_table(reference, raw)
    result = reference.seams
    assert [row['reason'] for row in result['quarantine']] == ['EDGE_DUPLICATE', 'EDGE_DUPLICATE', 'OFF_EDGE']
    edge = by_key(result['edges'], 'HX-QS')
    assert (edge['count'], edge['coverage'], edge['reason']) == (0, [0, 0], 'EDGE_COVERAGE')


def test_crossing_correspondence_blocks_computation(reference):
    raw = HEADER + 'HX-QS,ONE,1200,100,0,100,x\nHX-QS,TWO,1200,450,0,800,y\nHX-QS,THREE,1200,800,0,450,z\n'
    replace_witness_table(reference, raw)
    edge = by_key(reference.seams['edges'], 'HX-QS')
    assert (edge['status'], edge['reason'], edge['max_m']) == ('BLOCKED', 'EDGE_ORDER', None)
    assert edge['coverage'] == pytest.approx([700 / 900, 700 / 900])


def test_gap_calculation_uses_both_affine_models_on_corresponding_positions():
    identity = {'east': [1, 0, 0], 'north': [0, 1, 0]}
    translated = {'east': [1, 0, 3], 'north': [0, 1, 4]}
    rows = [{'a_pixel': (0, 0), 'b_pixel': (0, 0)}, {'a_pixel': (0, 10), 'b_pixel': (0, 11)}]
    result = measure_gap(rows, identity, translated, [(0, 0), (0, 10)], [(0, 0), (0, 10)])
    assert result['max_m'] == pytest.approx(hypot(3, 5), abs=1e-12)
    assert result['stations'][0]['gap_m'] == 5
    assert result['stations'][0]['normal_m'] == -3


def test_exact_minimum_coverage_and_inclusive_gap_are_accepted(reference):
    raw = HEADER + 'HX-QS,ONE,1200,180,0,180,x\nHX-QS,TWO,1200,450,0,450,y\nHX-QS,THREE,1200,720,0,720,z\n'
    replace_witness_table(reference, raw)
    edge = by_key(reference.seams['edges'], 'HX-QS')
    assert edge['status'] == 'PASS'
    assert edge['coverage'] == pytest.approx([.6, .6])
