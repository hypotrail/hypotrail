"""One immutable presentation snapshot shared by every surface (J6)."""
from __future__ import annotations

from typing import Mapping

SCHEMA = 'hypotrail.presentation/1'


def build(view: Mapping) -> dict:
    results = view.get('results') or {}
    current = {slot: item['result_id'] for slot, item in sorted(results.items())
               if item.get('current') and item.get('integrity') == 'ok'}
    uncertainty = {
        slot: values['uncertainty']
        for slot, item in sorted(results.items())
        for values in [item.get('values') or {}]
        if item.get('current') and isinstance(values, Mapping)
        and isinstance(values.get('uncertainty'), Mapping)
    }
    final = view.get('final_test') or {}
    historical = {
        'stale_result_ids': sorted((view.get('stale') or {}).keys()),
        'final_test_opened': final.get('status') == 'opened',
        'changed_after_opening': bool(final.get('post_final_test') or final.get('changed_after')),
    }
    return {
        'schema': SCHEMA, 'revision': view['revision'], 'result_ids': current,
        'eligibility': view.get('claim_eligibility'), 'uncertainty': uncertainty,
        'assurance': view.get('assurance'),
        'pending_action': (view.get('next_action') or {}).get('pause'),
        'historical': historical,
    }
