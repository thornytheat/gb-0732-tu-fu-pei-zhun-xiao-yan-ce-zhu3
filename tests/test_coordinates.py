import pytest

from app.errors import RegisterError
from app.modules.coordinates.numbers import measure
from app.modules.coordinates.projection import ground_position, pixel_position, to_enu


def point(rows, sheet, name):
    return next(row for row in rows if row['sheet'] == sheet and row['name'] == name)


def test_fullwidth_thousands_and_pixel_suffix(field):  # TRAP-06
    row = point(field.coordinates['pixels'], '0421', '河堤四号')
    assert row['xy'] == (1040, 118)
    assert row['source']['raw'][2] == '１，０４０ px'


def test_missing_token_is_not_a_zero_coordinate(field):  # TRAP-07
    blanks = [row for row in field.coordinates['quarantine'] if row['reason'] == 'EMPTY_COORDINATE']
    assert [row['source']['raw'][3] for row in blanks] == ['N/A']
    assert not any(row['name'] == '缺测' for row in field.coordinates['pixels'])
    assert measure('0 px', 'px') == 0


def test_centimeters_and_geographic_degrees_match_reference(field, reference):  # TRAP-15
    historic = field.coordinates['ground']
    baseline = reference.coordinates['ground']
    for name in ('P02', 'P04'):
        incoming = point(historic, '0421', name)
        expected = point(baseline, '0421', name)
        assert incoming['xy'] == pytest.approx(expected['xy'], abs=0.000003)
    assert point(historic, '0421', 'P04')['xy'] == pytest.approx((621.73, 801.44), abs=1e-9)


def test_degree_meter_conflicts_and_mismatched_suffix_are_isolated(field):
    invalid = {row['name']: row for row in field.coordinates['quarantine'] if row['reason'] == 'UNIT_MISMATCH'}
    assert set(invalid) == {'度米混填', '坏单位后缀'}
    assert invalid['坏单位后缀']['source']['raw'][4] == '113度'


def test_wgs84_enu_axes_and_short_equatorial_arcs():
    assert to_enu(0, 0, (0, 0)) == (0, 0)
    assert to_enu(.01, 0, (0, 0)) == pytest.approx((1113.194902, 0), abs=1e-6)
    assert to_enu(0, .01, (0, 0)) == pytest.approx((0, 1105.742753), abs=1e-6)


def test_distant_antipode_and_unknown_crs_are_rejected():
    with pytest.raises(RegisterError) as far:
        to_enu(180, 0, (0, 0))
    with pytest.raises(RegisterError) as unknown:
        ground_position({'crs': 'EPSG:3857', 'unit': 'm', 'x': '0', 'y': '0'}, (0, 0))
    assert (far.value.code, unknown.value.code) == ('COORDINATE_RANGE', 'INVALID_CRS')


def test_corner_allowed_but_bad_grouping_and_pixels_outside_excluded(field):
    sheet = field.catalog['sheets'][0]
    assert pixel_position('1200', '900', sheet) == (1200, 900)
    with pytest.raises(RegisterError) as outside:
        pixel_position('1200.01', '900', sheet)
    with pytest.raises(RegisterError) as grouping:
        measure('12,00', 'px')
    assert (outside.value.code, grouping.value.code) == ('COORDINATE_RANGE', 'BAD_NUMBER')
