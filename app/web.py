from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.config import DATASETS, RULE_VERSION, TEMPLATES
from app.reasons import REASONS

router = APIRouter()
templates = Jinja2Templates(directory=TEMPLATES)
SECTIONS = [('intake', '点表收件'), ('coordinates', '坐标换算'), ('pairing', '控制点配对'),
            ('affine', '仿射拟合'), ('refit', '离群重估'), ('seams', '接缝验核'), ('review', '图幅签审')]


@router.get('/', response_class=HTMLResponse, include_in_schema=False)
def index(request: Request):
    return templates.TemplateResponse(request=request, name='index.html', context={
        'datasets': DATASETS, 'rule_version': RULE_VERSION, 'sections': SECTIONS, 'reasons': REASONS,
    })
