from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import RULE_VERSION, STATIC, Settings
from app.errors import RegisterError
from app.modules.affine.handler import router as affine
from app.modules.coordinates.handler import router as coordinates
from app.modules.intake.handler import router as intake
from app.modules.pairing.handler import router as pairing
from app.modules.refit.handler import router as refit
from app.modules.review.handler import router as review
from app.modules.seams.handler import router as seams
from app.store import Store
from app.web import router as web


def create_app(settings=None):
    @asynccontextmanager
    async def lifespan(application):
        application.state.store.initialize()
        yield

    app = FastAPI(title='图幅配准校验册', version=RULE_VERSION, lifespan=lifespan, redoc_url=None)
    app.state.settings = settings or Settings()
    app.state.store = Store(app.state.settings.database)
    app.mount('/static', StaticFiles(directory=STATIC), name='static')
    for router in (web, intake, coordinates, pairing, affine, refit, seams, review):
        app.include_router(router)

    @app.exception_handler(RegisterError)
    def business_error(request: Request, error: RegisterError):
        return JSONResponse(error.payload(), status_code=error.status)

    @app.exception_handler(RequestValidationError)
    def invalid_input(request: Request, error: RequestValidationError):
        fields = ['.'.join(map(str, issue['loc'])) for issue in error.errors()]
        return JSONResponse({'detail': {'code': 'INVALID_INPUT', 'message': '参数无效，请核对输入',
                                        'evidence': fields}}, status_code=422)

    @app.get('/health')
    def health():
        return {'status': 'ok', 'rules': RULE_VERSION}

    return app


app = create_app()
