import pytest
from fastapi.testclient import TestClient

from app.config import ROOT, RunOptions, Settings
from app.main import create_app
from app.pipeline import Survey


@pytest.fixture
def settings(tmp_path):
    return Settings(sample_root=ROOT / 'sample_data', database=tmp_path / 'register.sqlite3')


@pytest.fixture
def field(settings):
    return Survey(settings, RunOptions())


@pytest.fixture
def reference(settings):
    return Survey(settings, RunOptions(dataset='reference'))


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as session:
        yield session


def by_key(records, value, key='code'):
    return next(record for record in records if record[key] == value)


def controls(points):
    return [{'id': str(index), 'name': f'P{index:02}', 'pixel': pixel, 'ground': ground}
            for index, (pixel, ground) in enumerate(points)]


def known_transform(pixel):
    u, v = pixel
    return 100 + .5 * u + .02 * v, 800 - .01 * u - .49 * v


def replace_witness_table(survey, raw):
    survey.bundle['witness.csv'] = raw.encode()
    return survey

