import os
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / 'app' / 'static'
TEMPLATES = ROOT / 'app' / 'templates'
RULE_VERSION = '2026.11.20-r1'
DATASETS = {'field': '河西四幅 · 外业原件', 'reference': '河西四幅 · 校准副本'}
FILES = ('catalog.json', 'pixels.csv', 'ground.csv', 'witness.csv')
MAX_INPUT_BYTES = 1_000_000
MAX_SHEET_POINTS = 32
LOCAL_RADIUS_M = 15_000
POSITION_EPSILON_PX = 0.05


class Settings:
    def __init__(self, sample_root=None, database=None):
        self.sample_root = Path(sample_root or os.getenv('REGISTER_SAMPLE_ROOT', ROOT / 'sample_data'))
        self.database = Path(database or os.getenv('REGISTER_DB_PATH', ROOT / 'data' / 'register.sqlite3'))


class RunOptions(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)

    dataset: Literal['field', 'reference'] = 'field'
    control_limit_m: Annotated[float, Field(ge=0.01, le=25)] = 0.75
    seam_limit_m: Annotated[float, Field(ge=0.01, le=25)] = 1.5
