from fastapi.testclient import TestClient

from app.main import create_app


def test_home_and_each_independent_endpoint(client):
    home = client.get('/')
    assert home.status_code == 200
    assert all(mark in home.text for mark in ('运行校验', '导出证据', 'atlas-plot', 'edge-plot', '图幅签审'))
    for stage, field in [('intake', 'catalog'), ('coordinates', 'ground'), ('pairing', 'pairs'),
                         ('affine', 'sheets'), ('refit', 'outliers'), ('seams', 'edges')]:
        result = client.get(f'/api/{stage}?dataset=field')
        assert result.status_code == 200 and field in result.json()
    assert client.post('/api/review/runs', json={}).status_code == 200


def test_contract_errors_have_expected_http_status_and_reason(client):
    invalid = client.post('/api/review/runs', json={'control_limit_m': 0})
    assert (invalid.status_code, invalid.json()['detail']['code']) == (422, 'INVALID_INPUT')
    missing = client.get('/api/review/runs/' + '0' * 64)
    assert (missing.status_code, missing.json()['detail']['code']) == (404, 'RUN_NOT_FOUND')
    assert client.get('/api/intake?dataset=../field').status_code == 422


def test_run_and_signature_survive_application_restart(settings):
    with TestClient(create_app(settings)) as first:
        data = first.post('/api/review/runs', json={'dataset': 'reference'}).json()
        path = f"/api/review/runs/{data['manifest']['run_id']}"
        response = first.post(path + '/signatures', json={'sheet': '0432', 'reviewer': '丁复核'})
        assert response.status_code == 200
    with TestClient(create_app(settings)) as second:
        persisted = second.get(path + '/export').json()
        assert persisted['ledger']['controls']['accepted'] == 48
        assert persisted['signatures'][0]['reviewer'] == '丁复核'
