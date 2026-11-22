from app.config import DATASETS, FILES, MAX_INPUT_BYTES
from app.errors import RegisterError
from app.modules.intake.catalog import read_catalog
from app.modules.intake.decode import decode_table
from app.modules.intake.reader import read_rows


def acquire_bundle(root, dataset):
    if dataset not in DATASETS:
        raise RegisterError('UNKNOWN_DATASET', '请选择已登记的图册', 404)
    bundle = {}
    for name in FILES:
        try:
            with (root / dataset / name).open('rb') as stream:
                bundle[name] = stream.read(MAX_INPUT_BYTES + 1)
        except OSError as error:
            raise RegisterError('SOURCE_UNAVAILABLE', '图册档件无法读取', 503, name) from error
        if len(bundle[name]) > MAX_INPUT_BYTES:
            raise RegisterError('SOURCE_TOO_LARGE', '档件超过单表上限', 413, name)
    return bundle


def intake(bundle):
    catalog = read_catalog(bundle['catalog.json'])
    tables = {}
    for filename in ('pixels.csv', 'ground.csv', 'witness.csv'):
        text, encoding = decode_table(bundle[filename], filename)
        tables[filename] = read_rows(text, filename, encoding)
    return {'catalog': catalog.model_dump(), 'tables': tables}
