from typing import Annotated

from fastapi import APIRouter, Query, Request

from app.config import RunOptions
from app.pipeline import Survey

router = APIRouter(prefix='/api/seams')


@router.get('')
def inspect(request: Request, options: Annotated[RunOptions, Query()]):
    survey = Survey(request.app.state.settings, options)
    return survey.seams
