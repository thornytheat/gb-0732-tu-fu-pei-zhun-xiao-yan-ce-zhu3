from collections import defaultdict


def decisions(catalog, refit, seams):
    incident = defaultdict(list)
    for edge in seams['edges']:
        incident[edge['a']].append(edge)
        incident[edge['b']].append(edge)
    reviews = []
    for sheet in catalog['sheets']:
        code = sheet['code']
        model, edges = refit['sheets'][code], incident[code]
        failed = [edge['code'] for edge in edges if edge['status'] == 'FAIL']
        blocked = [edge['code'] for edge in edges if edge['status'] == 'BLOCKED']
        if model['status'] != 'FIT':
            status, reason = 'HOLD', model['reason']
        elif failed:
            status, reason = 'RETURN', 'GAP_OVER_LIMIT'
        elif blocked:
            status, reason = 'HOLD', next(edge['reason'] for edge in edges if edge['status'] == 'BLOCKED')
        elif not edges:
            status, reason = 'HOLD', 'NO_EDGE_REGISTERED'
        else:
            status, reason = 'READY', None
        reviews.append({**sheet, 'status': status, 'reason': reason, 'fit_rms_m': model.get('rms_m'),
                        'edges': [edge['code'] for edge in edges], 'failed_edges': failed, 'blocked_edges': blocked})
    return reviews
