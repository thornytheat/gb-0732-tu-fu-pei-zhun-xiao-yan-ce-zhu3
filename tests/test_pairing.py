import pytest

from app.errors import RegisterError
from app.modules.pairing.aliases import resolve_aliases
from app.modules.pairing.duplicates import resolve_observations
from app.modules.pairing.service import pair_controls


def test_sheet_codes_keep_their_leading_zero(field):  # TRAP-08
    assert {row['sheet'] for row in field.pairing['pairs']} == {'0421', '0422', '0431', '0432'}
    assert any(row['sheet'] == '0999' and row['reason'] == 'UNKNOWN_SHEET' for row in field.pairing['quarantine'])


def test_alias_chains_resolve_independent_of_row_and_alias_order(field):  # TRAP-22
    expected = field.pairing
    catalog = {**field.catalog, 'aliases': dict(reversed(list(field.catalog['aliases'].items())))}
    converted = {**field.coordinates, 'pixels': list(reversed(field.coordinates['pixels'])),
                 'ground': list(reversed(field.coordinates['ground']))}
    assert pair_controls(converted, catalog) == expected
    p01 = next(row for row in expected['pairs'] if (row['sheet'], row['name']) == ('0421', 'P01'))
    assert p01['pixel_source']['raw'][1] == ' 河西旧一 '
    assert p01['ground_source']['raw'][1] == 'Ｐ０１'
    assert expected['aliases']['河西旧一'] == 'P01'


def test_ground_and_pixel_conflicts_do_not_use_last_write(field):  # TRAP-14
    issues = field.pairing['quarantine']
    ground = [row for row in issues if row['reason'] == 'GROUND_CONFLICT']
    pixel = [row for row in issues if row['reason'] == 'PIXEL_CONFLICT']
    assert ([row['source']['id'] for row in ground], len(pixel)) == (
        ['ground.csv:14', 'ground.csv:15', 'pixels.csv:18'], 2)
    assert ground[-1]['observations'] == ['ground.csv:14', 'ground.csv:15']
    assert not {'冲突地面', '冲突像素'} & {row['name'] for row in field.pairing['pairs']}


def test_nonconflicting_duplicates_keep_first_physical_row(field):
    duplicates = {row['reason']: row for row in field.pairing['quarantine'] if row['reason'].endswith('REPEAT')}
    assert {key: row['kept'] for key, row in duplicates.items()} == {'GROUND_REPEAT': 'ground.csv:2', 'PIXEL_REPEAT': 'pixels.csv:2'}


def test_same_point_name_on_separate_sheets_never_merges(field):
    p01 = [row for row in field.pairing['pairs'] if row['name'] == 'P01']
    assert len(p01) == 4
    assert p01[0]['ground'] != p01[1]['ground']


def test_alias_loop_and_normalized_collision_are_explicit():  # TRAP-20
    with pytest.raises(RegisterError) as loop:
        resolve_aliases({'桥一': '桥二', '桥二': '桥一'})
    with pytest.raises(RegisterError) as collision:
        resolve_aliases({'Ｐ１': 'P2', 'p1': 'P3'})
    assert (loop.value.code, loop.value.evidence) == ('ALIAS_CYCLE', ['桥一', '桥二', '桥一'])
    assert collision.value.code == 'ALIAS_AMBIGUOUS'


def test_close_chain_does_not_hide_spread_between_endpoints():
    observations = [{'sheet': '0421', 'name': 'P1', 'xy': (x, 0), 'source': {'line': i, 'id': str(i)}}
                    for i, x in enumerate((0, .00075, .0015), 1)]
    chosen, conflicts, rejected = resolve_observations(observations, {}, 'GROUND')
    assert chosen == {}
    assert conflicts == {('0421', 'P1'): ['1', '2', '3']}
    assert [row['reason'] for row in rejected] == ['GROUND_CONFLICT'] * 3


def test_self_alias_cannot_hide_normalized_collision():
    for aliases in ({'P1': 'P1', 'Ｐ１': 'P2'}, {'Ｐ１': 'P2', 'P1': 'P1'}):
        with pytest.raises(RegisterError) as caught:
            resolve_aliases(aliases)
        assert caught.value.code == 'ALIAS_AMBIGUOUS'
