import unicodedata
from typing import Annotated

from fastapi import APIRouter, Path, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.config import RunOptions
from app.manifest import canonical_json
from app.modules.review.service import evidence, run_review

router = APIRouter(prefix='/api/review')
RunId = Annotated[str, Path(pattern=r'^[0-9a-f]{64}$')]


class SignatureInput(BaseModel):
    model_config = ConfigDict(extra='forbid')

    sheet: Annotated[str, Field(pattern=r'^[A-Z0-9][A-Z0-9-]{0,23}$')]
    reviewer: Annotated[str, Field(min_length=1, max_length=30)]
    expected_version: Annotated[int, Field(ge=0)] = 0

    @field_validator('reviewer', mode='before')
    @classmethod
    def reviewer_name(cls, name):
        if not isinstance(name, str):
            return name
        if any(unicodedata.category(char).startswith('C') for char in name):
            raise ValueError('签审员姓名包含控制字符')
        return name.strip()


@router.post('/runs')
def run(request: Request, options: RunOptions):
    snapshot, reused = run_review(request.app.state.settings, request.app.state.store, options)
    return {'reused': reused, **snapshot}


@router.get('/runs/{run_id}')
def get_run(request: Request, run_id: RunId):
    return request.app.state.store.get(run_id)


@router.post('/runs/{run_id}/signatures')
def signatures(request: Request, run_id: RunId, form: SignatureInput):
    return request.app.state.store.sign(run_id, form.sheet, form.reviewer, form.expected_version)


@router.get('/runs/{run_id}/export')
def export(request: Request, run_id: RunId):
    snapshot = request.app.state.store.get(run_id)
    return Response(canonical_json(evidence(snapshot)) + '\n', media_type='application/json',
                    headers={'Content-Disposition': f'attachment; filename="map-register-{run_id[:12]}.json"'})
