from datetime import datetime, timezone
from hashlib import sha256
import json

from app.config import RULE_VERSION


def canonical_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def run_manifest(survey, processing_ms):
    inputs = {name: sha256(raw).hexdigest() for name, raw in survey.bundle.items()}
    fingerprint = {'inputs': inputs, 'parameters': survey.options.model_dump(), 'rule_version': RULE_VERSION}
    run_id = sha256(canonical_json(fingerprint).encode()).hexdigest()
    return {'run_id': run_id, **fingerprint, 'data_version': survey.catalog['version'],
            'created_at': datetime.now(timezone.utc).isoformat(timespec='milliseconds'),
            'processing_ms': processing_ms}


def archive_key(manifest):
    """Identity of the archive item itself, independent of rerun parameters."""
    identity = {'inputs': manifest['inputs'], 'rule_version': manifest['rule_version']}
    return sha256(canonical_json(identity).encode()).hexdigest()
