import unicodedata
from typing import Annotated

from fastapi import APIRouter, Path, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.config import RunOptions
from app.manifest import canonical_json
from app.modules.review.issuance import build_issuance, issue
from app.modules.review.service import evidence, run_review

router = APIRouter(prefix='/api/review')
RunId = Annotated[str, Path(pattern=r'^[0-9a-f]{64}$')]


class IssuanceInput(BaseModel):
    model_config = ConfigDict(extra='forbid')

    recipient: Annotated[str | None, Field(max_length=40)] = None
    note: Annotated[str | None, Field(max_length=200)] = None

    @field_validator('recipient', 'note', mode='before')
    @classmethod
    def clean_text(cls, value):
        if not isinstance(value, str):
            return value
        if any(unicodedata.category(char).startswith('C') for char in value):
            raise ValueError('发放栏位包含控制字符')
        return value.strip()


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


@router.get('/runs/{run_id}/issuance')
def get_issuance(request: Request, run_id: RunId, revision: int | None = None):
    return request.app.state.store.get_issuance(run_id, revision=revision)


@router.get('/runs/{run_id}/issuance/history')
def issuance_history(request: Request, run_id: RunId):
    return {'run_id': run_id, 'revisions': request.app.state.store.issuance_history(run_id)}


@router.get('/runs/{run_id}/issuance/preview')
def preview_issuance(request: Request, run_id: RunId):
    return build_issuance(request.app.state.store.get(run_id), draft=True)


@router.post('/runs/{run_id}/issuance')
def post_issuance(request: Request, run_id: RunId, form: IssuanceInput):
    issuance, reused = issue(request.app.state.store, run_id, form.recipient, form.note)
    return {'reused': reused, **issuance}


@router.get('/runs/{run_id}/issuance/export')
def export_issuance(request: Request, run_id: RunId, revision: int | None = None):
    register = request.app.state.store.get_issuance(run_id, revision=revision)
    return Response(canonical_json(register) + '\n', media_type='application/json',
                    headers={'Content-Disposition':
                             f'attachment; filename="map-issuance-{register["issuance_id"][:12]}.json"'})
