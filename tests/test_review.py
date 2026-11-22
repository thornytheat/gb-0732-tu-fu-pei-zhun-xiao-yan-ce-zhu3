from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from hashlib import sha256
import shutil
import sqlite3

import pytest

from app.config import RunOptions
from app.errors import RegisterError
from app.modules.review.reconcile import reconcile
from app.modules.review.service import run_review
from app.pipeline import Survey
from app.store import Store
from conftest import by_key


def test_conservation_covers_every_control_ground_and_witness_row(field):
    result = reconcile(field.intake, field.pairing, field.refit, field.seams)
    assert result['controls'] == {'input': 53, 'accepted': 35, 'outlier': 1, 'isolated': 17,
                                  'blank': 1, 'repeated_headers': 1, 'balanced': True}
    assert (result['ground']['paired'], result['ground']['isolated']) == (43, 6)
    assert (result['witnesses']['eligible'], result['witnesses']['isolated']) == (18, 1)
    assert sum(result['reason_counts'].values()) == 24


def test_equal_counts_with_substituted_source_break_reconciliation(field):
    refit = deepcopy(field.refit)
    refit['accepted'][0] = refit['accepted'][1]
    with pytest.raises(RegisterError) as caught:
        reconcile(field.intake, field.pairing, refit, field.seams)
    assert (caught.value.code, caught.value.evidence) == ('LEDGER_MISMATCH', 'pixels.csv')


def test_run_reuse_is_stable_and_thresholds_create_a_new_batch(client):
    first = client.post('/api/review/runs', json={}).json()
    again = client.post('/api/review/runs', json={}).json()
    widened = client.post('/api/review/runs', json={'seam_limit_m': 3}).json()
    assert first.pop('reused') is False
    assert again.pop('reused') is True
    assert first == again
    assert first['manifest']['run_id'] != widened['manifest']['run_id']
    assert by_key(widened['seams']['edges'], 'HX-QS')['status'] == 'PASS'


def test_concurrent_runs_store_exactly_one_complete_snapshot(settings):
    store = Store(settings.database)
    store.initialize()
    options = RunOptions()
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: run_review(settings, store, options), range(4)))
    assert sum(not reused for _, reused in results) == 1
    assert len({value['manifest']['run_id'] for value, _ in results}) == 1
    assert all(value['ledger']['controls']['accepted'] == 35 for value, _ in results)
    with sqlite3.connect(settings.database) as connection:
        assert connection.execute('SELECT COUNT(*) FROM runs').fetchone() == (1,)


def test_source_error_leaves_no_partial_batch_and_retry_succeeds(settings, tmp_path):
    test_sources = tmp_path / 'inputs'
    shutil.copytree(settings.sample_root, test_sources)
    settings.sample_root = test_sources
    file = test_sources / 'field' / 'witness.csv'
    good = file.read_bytes()
    file.write_bytes(good + b'"unterminated')
    store = Store(settings.database)
    store.initialize()
    with pytest.raises(RegisterError, match='引号未闭合'):
        run_review(settings, store, RunOptions())
    with sqlite3.connect(settings.database) as connection:
        assert connection.execute('SELECT COUNT(*) FROM runs').fetchone() == (0,)
    file.write_bytes(good)
    result, reused = run_review(settings, store, RunOptions())
    assert reused is False and result['ledger']['witnesses']['input'] == 19


def test_review_readiness_uses_edges_and_blocks_invalid_signature(client):
    response = client.post('/api/review/runs', json={})
    payload = response.json()
    assert [row['status'] for row in payload['reviews']] == ['RETURN', 'RETURN', 'READY', 'HOLD']
    url = f"/api/review/runs/{payload['manifest']['run_id']}/signatures"
    blocked = client.post(url, json={'sheet': '0421', 'reviewer': '周测绘'})
    assert blocked.status_code == 409
    assert blocked.json()['detail']['evidence'] == 'GAP_OVER_LIMIT'
    signed = client.post(url, json={'sheet': '0431', 'reviewer': ' 周测绘 '})
    assert signed.status_code == 200
    assert signed.json()['reviewer'] == '周测绘'


def test_stale_signature_cannot_replace_first_reviewer(client):  # TRAP-26
    first = client.post('/api/review/runs', json={}).json()
    run = f"/api/review/runs/{first['manifest']['run_id']}"
    form = {'sheet': '0431', 'reviewer': '周测绘', 'expected_version': 0}
    signed = client.post(run + '/signatures', json=form).json()
    assert client.post(run + '/signatures', json=form).json() == signed
    stale = client.post(run + '/signatures', json={**form, 'reviewer': '陈测绘'})
    assert (stale.status_code, stale.json()['detail']['code']) == (409, 'SIGNATURE_VERSION_CONFLICT')
    assert client.get(run).json()['signatures'] == [signed]
    assert client.post('/api/review/runs', json={}).json()['signatures'] == [signed]


def test_export_preserves_input_hashes_and_original_evidence(client, field):
    result = client.post('/api/review/runs', json={}).json()
    run_id = result['manifest']['run_id']
    response = client.get(f'/api/review/runs/{run_id}/export')
    bundle = response.json()
    assert response.headers['content-disposition'] == f'attachment; filename="map-register-{run_id[:12]}.json"'
    assert bundle['manifest']['inputs'] == {name: sha256(raw).hexdigest() for name, raw in field.bundle.items()}
    assert bundle['refit']['outliers'][0]['ground_source']['file'] == 'ground.csv'
    assert bundle['intake']['pixels.csv']['rows'][0]['source']['raw'][4] == '复核点\n旧簿名'
    assert 'CONTROL_OUTLIER' in bundle['reason_dictionary']


def test_any_input_byte_change_creates_a_new_snapshot(settings, tmp_path):
    new_root = tmp_path / 'copies'
    shutil.copytree(settings.sample_root, new_root)
    settings.sample_root = new_root
    store = Store(settings.database)
    store.initialize()
    first, _ = run_review(settings, store, RunOptions())
    raw_data = new_root / 'field' / 'pixels.csv'
    with raw_data.open('ab') as file:
        file.write(b'\n')
    second, reused = run_review(settings, store, RunOptions())
    assert not reused and first['manifest']['run_id'] != second['manifest']['run_id']
    assert second['ledger']['controls']['blank'] == 2
    assert Survey(settings, RunOptions()).intake['tables']['pixels.csv']['records'] == 53
