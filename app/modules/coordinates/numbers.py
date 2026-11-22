import math
import re
import unicodedata

from app.errors import RegisterError
from app.reasons import REASONS

MISSING = {'', '-', '—', 'n/a', 'null', '未知'}
NUMBER = re.compile(r'^[+-]?(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.[0-9]+)?$')
SUFFIXES = (('厘米', 'cm'), ('cm', 'cm'), ('米', 'm'), ('m', 'm'), ('°', 'deg'), ('度', 'deg'), ('px', 'px'))
UNIT_LABELS = {'米': 'm', '厘米': 'cm', '度': 'deg', '°': 'deg'}


def clean(value):
    return unicodedata.normalize('NFKC', value).strip()


def point_name(value):
    return clean(value).casefold().upper()


def normalized_unit(value):
    value = clean(value).lower()
    return UNIT_LABELS.get(value, value)


def failure(code):
    return RegisterError(code, REASONS[code])


def measure(value, expected_unit):
    value = clean(value).lower()
    if value in MISSING:
        raise failure('EMPTY_COORDINATE')
    for suffix, unit in SUFFIXES:
        if value.endswith(suffix):
            if unit != expected_unit:
                raise failure('UNIT_MISMATCH')
            value = value[:-len(suffix)].strip()
            break
    if not NUMBER.fullmatch(value):
        raise failure('BAD_NUMBER')
    number = float(value.replace(',', ''))
    if not math.isfinite(number):
        raise failure('BAD_NUMBER')
    return number
