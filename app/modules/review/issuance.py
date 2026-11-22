from datetime import datetime, timezone
from hashlib import sha256

from app.manifest import canonical_json
from app.reasons import REASONS

FORMAT = 'map-register/issuance-1'
STAGES = {'FIT': '拟合与重估', 'SEAM': '接缝复核', 'SIGNATURE': '签审'}
STATEMENT = ('本册为受控发放记录。分所仅可按“可调阅图幅”栏取件；未放行图幅不得出库。'
             '同一档件只有一册，重发时在原册上改版，旧版留存可查。')


def _now():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds')


def _edge_view(edge):
    return {'code': edge['code'], 'status': edge['status'], 'reason': edge['reason'],
            'reason_label': REASONS.get(edge['reason'], edge['reason']) if edge['reason'] else None,
            'reasons': list(edge.get('reasons') or []), 'max_m': edge.get('max_m'),
            'limit_m': edge.get('limit_m'), 'a': edge['a'], 'b': edge['b'],
            'a_side': edge['a_side'], 'b_side': edge['b_side']}


def _signature_view(signature):
    if signature is None:
        return None
    return {'reviewer': signature['reviewer'], 'signed_at': signature['signed_at'],
            'version': signature['version']}


def _gap_text(edge):
    if edge.get('max_m') is None:
        return f"{edge['code']} 无法实测（{REASONS.get(edge['reason'], edge['reason'])}）"
    return f"{edge['code']} 实测 {edge['max_m']:.3f} m / 限 {edge['limit_m']:.3f} m"


def _blockage(review, model, edges, signature):
    """Return (stage, reason, detail) for a withheld sheet, or None when releasable.

    The stage follows the order evidence is actually consumed: the fit must exist
    before a seam can be measured, and every registered seam must pass before a
    signature counts. A sheet is released only when all three are satisfied.
    """
    if model['status'] != 'FIT':
        reason = model.get('reason') or 'MODEL_UNAVAILABLE'
        blocked = [edge for edge in edges if edge['status'] == 'BLOCKED']
        detail = f"模型拟合未通过：{REASONS.get(reason, reason)}。"
        if blocked:
            detail += '关联拼缝 ' + '、'.join(edge['code'] for edge in blocked) + ' 因此无法实测。'
        return 'FIT', reason, detail
    failed = [edge for edge in edges if edge['status'] == 'FAIL']
    blocked = [edge for edge in edges if edge['status'] == 'BLOCKED']
    if failed:
        detail = '；'.join(_gap_text(edge) for edge in failed) + '。'
        if blocked:
            detail += '另有 ' + '、'.join(f"{edge['code']}（{REASONS.get(edge['reason'], edge['reason'])}）"
                                          for edge in blocked) + ' 未完成验核。'
        return 'SEAM', 'GAP_OVER_LIMIT', detail
    if blocked:
        reason = blocked[0]['reason'] or 'EDGE_COVERAGE'
        detail = '；'.join(f"{edge['code']} 未完成验核：{REASONS.get(edge['reason'], edge['reason'])}"
                          for edge in blocked) + '。'
        return 'SEAM', reason, detail
    if not edges:
        return 'SEAM', 'NO_EDGE_REGISTERED', '该幅未登记独立拼缝，无法完成接边复核。'
    if review['status'] == 'READY' and signature is None:
        return 'SIGNATURE', 'SIGNATURE_PENDING', '拟合与登记拼缝均已通过，尚缺签审员入册。'
    if signature is not None:
        return None
    reason = review.get('reason') or 'SIGNATURE_BLOCKED'
    return 'SIGNATURE', reason, '图幅当前状态不允许发放。'


def build_issuance(snapshot, recipient=None, note=None, issued_at=None, revision=1, draft=False, previous=None):
    signatures = {signature['sheet']: signature for signature in snapshot.get('signatures', [])}
    # A register belongs to the archive item, not to one parameter batch. A rerun
    # of the same archive has no signature rows of its own, so carry forward what
    # the prior revision already recorded; otherwise reissuing would regress a
    # sheet that 分所 already holds.
    carried = set()
    if previous is not None:
        for entry in previous.get('released', []) + previous.get('withheld', []):
            if entry['code'] not in signatures and entry.get('signature'):
                signatures[entry['code']] = entry['signature']
                carried.add(entry['code'])
    models = snapshot['refit']['sheets']
    edges = snapshot['seams']['edges']
    by_sheet = {}
    for edge in edges:
        by_sheet.setdefault(edge['a'], []).append(edge)
        by_sheet.setdefault(edge['b'], []).append(edge)

    entries = []
    for review in snapshot['reviews']:
        code = review['code']
        model, signature = models[code], signatures.get(code)
        incident = by_sheet.get(code, [])
        blockage = _blockage(review, model, incident, signature)
        entry = {'code': code, 'title': review['title'],
                 'review_status': review['status'], 'review_reason': review.get('reason'),
                 'fit': {'status': model['status'], 'reason': model.get('reason'), 'rms_m': model.get('rms_m')},
                 'edge_refs': [edge['code'] for edge in incident],
                 'edges': [_edge_view(edge) for edge in incident],
                 'signature': _signature_view(signature),
                 'signature_carried': code in carried}
        if blockage is None:
            entry.update(outcome='RELEASED', stage=None, stage_label=None, reason=None, reason_label=None,
                         detail='拟合与登记拼缝均通过，签审已入册。')
        else:
            stage, reason, detail = blockage
            entry.update(outcome='WITHHELD', stage=stage, stage_label=STAGES.get(stage),
                         reason=reason, reason_label=REASONS.get(reason, reason), detail=detail)
        entries.append(entry)

    released = [entry for entry in entries if entry['outcome'] == 'RELEASED']
    withheld = [entry for entry in entries if entry['outcome'] == 'WITHHELD']
    by_stage = {}
    for entry in withheld:
        by_stage[entry['stage']] = by_stage.get(entry['stage'], 0) + 1
    if not (recipient or '').strip() and previous is not None:
        recipient = previous.get('recipient')
    if not (note or '').strip() and previous is not None:
        note = previous.get('note')
    body = {'format': FORMAT, 'revision': revision,
            'run_id': snapshot['manifest']['run_id'],
            'issued_at': issued_at or _now(),
            'recipient': (recipient or '').strip() or '分所', 'note': (note or '').strip(),
            'manifest': snapshot['manifest'], 'ledger': snapshot['ledger'],
            'entries': entries,
            'released': released, 'withheld': withheld,
            'summary': {'sheets': len(entries), 'released': len(released), 'withheld': len(withheld),
                        'by_stage': by_stage},
            'statement': STATEMENT}
    issuance_id = sha256(canonical_json(body).encode()).hexdigest()
    return {**body, 'issuance_id': issuance_id, 'draft': draft}


def fingerprint(register):
    """What 分所 actually reads: released sheets, their signatures, which sheets
    are withheld and at which stage/reason, and who is collecting. Detail prose
    and threshold metadata do not by themselves warrant a new revision."""
    return sha256(canonical_json({
        'released': sorted((row['code'], (row['signature'] or {}).get('reviewer'),
                            (row['signature'] or {}).get('signed_at')) for row in register['released']),
        'withheld': sorted((row['code'], row['stage'], row['reason']) for row in register['withheld']),
        'recipient': register['recipient'], 'note': register['note'],
    }).encode()).hexdigest()


def issue(store, run_id, recipient=None, note=None):
    return store.create_issuance(
        run_id,
        lambda snapshot, revision, previous: build_issuance(
            snapshot, recipient, note, revision=revision, previous=previous),
        same_content=lambda previous, candidate: fingerprint(previous) == fingerprint(candidate))

