from concurrent.futures import ThreadPoolExecutor
import shutil
import sqlite3

import pytest

from app.config import RunOptions
from app.errors import RegisterError
from app.manifest import archive_key
from app.modules.review.issuance import build_issuance, fingerprint
from app.modules.review.service import run_review
from app.store import Store


def issue(client, run_id, **form):
    return client.post(f'/api/review/runs/{run_id}/issuance', json=form)


def sign(client, run_id, sheet, reviewer='周测绘'):
    return client.post(f'/api/review/runs/{run_id}/signatures', json={'sheet': sheet, 'reviewer': reviewer})


def test_issuance_separates_released_from_withheld_with_stage(client):
    run = client.post('/api/review/runs', json={}).json()
    response = issue(client, run['manifest']['run_id'])
    assert response.status_code == 200
    register = response.json()
    released = {row['code'] for row in register['released']}
    withheld = {row['code']: row for row in register['withheld']}
    # 柳湾 fits and its only seam passes but it has not been signed yet.
    assert released == set()
    assert set(withheld) == {'0421', '0422', '0431', '0432'}
    assert withheld['0421']['stage'] == 'SEAM'
    assert withheld['0421']['reason'] == 'GAP_OVER_LIMIT'
    assert '2.522' in withheld['0421']['detail']
    assert withheld['0422']['stage'] == 'SEAM'
    assert withheld['0431']['stage'] == 'SIGNATURE'
    assert withheld['0431']['reason'] == 'SIGNATURE_PENDING'
    assert withheld['0432']['stage'] == 'FIT'
    assert withheld['0432']['reason'] == 'COLLINEAR_PIXELS'
    assert register['summary'] == {'sheets': 4, 'released': 0, 'withheld': 4,
                                   'by_stage': {'FIT': 1, 'SEAM': 2, 'SIGNATURE': 1}}


def test_signed_sheets_are_released_and_prior_register_is_recoverable(client):
    run = client.post('/api/review/runs', json={'dataset': 'reference'}).json()
    run_id = run['manifest']['run_id']
    sign(client, run_id, '0431')
    first = issue(client, run_id, recipient='分所值班室').json()
    assert {row['code'] for row in first['released']} == {'0431'}
    assert first['revision'] == 1 and first['recipient'] == '分所值班室'

    # A later signature revises the one register; the issued revision stays intact.
    sign(client, run_id, '0421')
    second = issue(client, run_id).json()
    assert second['reused'] is False and second['revision'] == 2
    assert {row['code'] for row in second['released']} == {'0431', '0421'}
    assert second['run_id'] == run_id
    assert second['recipient'] == '分所值班室'  # carried forward from the prior revision

    # Same content again is not a new revision.
    again = issue(client, run_id).json()
    assert again['reused'] is True and again['revision'] == 2
    assert again['issuance_id'] == second['issuance_id']

    first_again = client.get(f'/api/review/runs/{run_id}/issuance?revision=1').json()
    assert first_again['issuance_id'] == first['issuance_id']
    assert {row['code'] for row in first_again['released']} == {'0431'}
    history = client.get(f'/api/review/runs/{run_id}/issuance/history').json()['revisions']
    assert [row['revision'] for row in history] == [1, 2]
    assert client.get(f'/api/review/runs/{run_id}/issuance').json()['revision'] == 2


def test_rerun_of_same_archive_never_creates_a_second_register(client):
    first = client.post('/api/review/runs', json={'dataset': 'reference'}).json()
    sign(client, first['manifest']['run_id'], '0431')
    register = issue(client, first['manifest']['run_id']).json()

    # A different parameter set is a new batch but the same archive item.
    rerun = client.post('/api/review/runs', json={'dataset': 'reference', 'seam_limit_m': 3}).json()
    assert rerun['manifest']['run_id'] != first['manifest']['run_id']
    again = issue(client, rerun['manifest']['run_id']).json()
    assert again['reused'] is True
    assert again['issuance_id'] == register['issuance_id']
    assert again['run_id'] == first['manifest']['run_id']
    assert again['revision'] == 1
    history = client.get(f"/api/review/runs/{rerun['manifest']['run_id']}/issuance/history").json()
    assert len(history['revisions']) == 1


def test_later_signature_on_a_rerun_revises_the_same_register(client):
    first = client.post('/api/review/runs', json={'dataset': 'reference'}).json()
    issue(client, first['manifest']['run_id'])
    rerun = client.post('/api/review/runs', json={'dataset': 'reference', 'seam_limit_m': 3}).json()
    sign(client, rerun['manifest']['run_id'], '0421')
    revised = issue(client, rerun['manifest']['run_id']).json()
    assert revised['revision'] == 2 and revised['reused'] is False
    registry = client.get(f"/api/review/runs/{rerun['manifest']['run_id']}/issuance/history").json()
    assert [row['revision'] for row in registry['revisions']] == [1, 2]
    assert registry['revisions'][1]['run_id'] == rerun['manifest']['run_id']


def test_failed_issuance_rolls_back_without_orphans(settings):
    store = Store(settings.database)
    store.initialize()
    snapshot, _ = run_review(settings, store, RunOptions())
    run_id = snapshot['manifest']['run_id']

    def explode(current, revision, previous):
        raise RuntimeError('发放中途失败')

    with pytest.raises(RuntimeError):
        store.create_issuance(run_id, explode)
    with sqlite3.connect(settings.database) as connection:
        assert connection.execute('SELECT COUNT(*) FROM issuances').fetchone() == (0,)
    with pytest.raises(RegisterError) as missing:
        store.get_issuance(run_id)
    assert missing.value.code == 'ISSUANCE_NOT_FOUND'

    original, reused = store.create_issuance(run_id, lambda current, revision, previous: build_issuance(
        current, '分所', revision=revision, previous=previous))
    assert reused is False
    assert store.get_issuance(run_id)['issuance_id'] == original['issuance_id']


def test_failed_write_leaves_no_partial_register_and_retry_recovers(settings, monkeypatch):
    store = Store(settings.database)
    store.initialize()
    snapshot, _ = run_review(settings, store, RunOptions())
    run_id = snapshot['manifest']['run_id']

    import app.store as store_module

    def broken(*args, **kwargs):
        raise sqlite3.OperationalError('disk full')

    candidate = lambda current, revision, previous: build_issuance(current, "分所", revision=revision, previous=previous)
    monkeypatch.setattr(store_module, 'canonical_json', broken)
    with pytest.raises(sqlite3.OperationalError):
        store.create_issuance(run_id, candidate)
    monkeypatch.undo()
    with sqlite3.connect(settings.database) as connection:
        assert connection.execute('SELECT COUNT(*) FROM issuances').fetchone() == (0,)

    recovered, reused = store.create_issuance(run_id, candidate)
    assert reused is False
    assert store.get_issuance(run_id)['issuance_id'] == recovered['issuance_id']


def test_failed_revision_does_not_disturb_the_earlier_revision(settings):
    store = Store(settings.database)
    store.initialize()
    first, _ = run_review(settings, store, RunOptions())
    run_id = first['manifest']['run_id']
    original, _ = store.create_issuance(run_id, lambda current, revision, previous: build_issuance(
        current, '分所', revision=revision, previous=previous))

    def explode(current, revision, previous):
        raise RuntimeError('改版中途失败')

    with pytest.raises(RuntimeError):
        store.create_issuance(run_id, explode)
    assert store.get_issuance(run_id, revision=1)['issuance_id'] == original['issuance_id']
    assert store.get_issuance(run_id)['issuance_id'] == original['issuance_id']
    with sqlite3.connect(settings.database) as connection:
        assert connection.execute('SELECT COUNT(*) FROM issuances').fetchone() == (1,)


def test_concurrent_issuance_creates_exactly_one_revision(settings):
    store = Store(settings.database)
    store.initialize()
    snapshot, _ = run_review(settings, store, RunOptions())
    run_id = snapshot['manifest']['run_id']
    same = lambda previous, candidate: fingerprint(previous) == fingerprint(candidate)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: store.create_issuance(
            run_id,
            lambda current, revision, previous: build_issuance(
                current, '分所', revision=revision, previous=previous),
            same_content=same), range(4)))
    assert sum(not reused for _, reused in results) == 1
    assert len({register['issuance_id'] for register, _ in results}) == 1
    with sqlite3.connect(settings.database) as connection:
        assert connection.execute('SELECT COUNT(*) FROM issuances').fetchone() == (1,)


def test_changed_source_bytes_form_a_new_archive_and_its_own_register(settings, tmp_path):
    copies = tmp_path / 'copies'
    shutil.copytree(settings.sample_root, copies)
    settings.sample_root = copies
    store = Store(settings.database)
    store.initialize()
    build = lambda current, revision, previous: build_issuance(current, "分所", revision=revision, previous=previous)
    first, _ = run_review(settings, store, RunOptions())
    original, _ = store.create_issuance(first['manifest']['run_id'], build)
    with (copies / 'field' / 'witness.csv').open('ab') as file:
        file.write(b'\n')
    second, _ = run_review(settings, store, RunOptions())
    assert archive_key(second['manifest']) != archive_key(first['manifest'])
    fresh, reused = store.create_issuance(second['manifest']['run_id'], build)
    assert reused is False and fresh['revision'] == 1
    assert fresh['issuance_id'] != original['issuance_id']
    assert store.get_issuance(first['manifest']['run_id'])['issuance_id'] == original['issuance_id']


def test_preview_tracks_signatures_without_being_persisted(client):
    run = client.post('/api/review/runs', json={}).json()
    run_id = run['manifest']['run_id']
    preview = client.get(f'/api/review/runs/{run_id}/issuance/preview').json()
    assert preview['draft'] is True
    assert preview['summary'] == {'sheets': 4, 'released': 0, 'withheld': 4,
                                  'by_stage': {'FIT': 1, 'SEAM': 2, 'SIGNATURE': 1}}
    assert client.get(f'/api/review/runs/{run_id}/issuance').status_code == 404
    sign(client, run_id, '0431')
    updated = client.get(f'/api/review/runs/{run_id}/issuance/preview').json()
    assert updated['draft'] is True and updated['summary']['released'] == 1
    frozen = issue(client, run_id).json()
    assert frozen['draft'] is False and frozen['summary']['released'] == 1
    assert issue(client, run_id).json()['issuance_id'] == frozen['issuance_id']


def test_issuance_export_is_the_frozen_register(client):
    run = client.post('/api/review/runs', json={'dataset': 'reference'}).json()
    run_id = run['manifest']['run_id']
    register = issue(client, run_id).json()
    export = client.get(f'/api/review/runs/{run_id}/issuance/export')
    assert export.status_code == 200
    assert export.headers['content-disposition'] == \
        f'attachment; filename="map-issuance-{register["issuance_id"][:12]}.json"'
    assert export.json() == {key: value for key, value in register.items() if key != 'reused'}


def test_issuance_unknown_run_is_a_clean_404(client):
    response = client.get('/api/review/runs/' + '0' * 64 + '/issuance')
    assert (response.status_code, response.json()['detail']['code']) == (404, 'RUN_NOT_FOUND')
    missing = client.get('/api/review/runs/' + '0' * 64 + '/issuance/export')
    assert (missing.status_code, missing.json()['detail']['code']) == (404, 'RUN_NOT_FOUND')


def test_archive_key_ignores_parameters_but_not_inputs(client, field):
    first = client.post('/api/review/runs', json={}).json()
    widened = client.post('/api/review/runs', json={'seam_limit_m': 3}).json()
    assert archive_key(first['manifest']) == archive_key(widened['manifest'])
    assert first['manifest']['run_id'] != widened['manifest']['run_id']


def test_reference_dataset_withholds_every_sheet_until_signed(client):
    run = client.post('/api/review/runs', json={'dataset': 'reference'}).json()
    register = issue(client, run['manifest']['run_id']).json()
    assert register['summary'] == {'sheets': 4, 'released': 0, 'withheld': 4,
                                   'by_stage': {'SIGNATURE': 4}}
    assert all(row['stage_label'] == '签审' for row in register['withheld'])
