"""The client's frozen key lists equal the engine's contract tests (scope U, WP-0).

``test/fixtures/contract-keys.json`` (read by ``fixtures.test.js``) and
``framework/tests/study/companion_contract.py`` (read by the engine contract tests) both
transcribe CLI-CONTRACT-COMPANION. This test fails when one of them drifts.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO / 'framework' / 'tests' / 'study'))

import companion_contract as cc  # noqa: E402
import test_contract_freeze as freeze  # noqa: E402  (WP-A7: the data card's frozen keys)

CONTRACT = json.loads((HERE / 'fixtures' / 'contract-keys.json').read_text(encoding='utf-8'))

EXPECTED = {
    'hypotrail.summary/1': {'': cc.SUMMARY_KEYS},
    'hypotrail.summary/1+digest': {'': cc.DIGEST_SUMMARY_KEYS, 'digest.items[]': cc.DIGEST_ITEM_KEYS,
                                   'digest.counts': cc.DIGEST_COUNT_KEYS, 'last_session': cc.LAST_SESSION_KEYS},
    'hypotrail.decisions/1': {'': cc.DECISIONS_KEYS, 'history[]': cc.DECISIONS_HISTORY_KEYS,
                              'proposals[]': cc.DECISIONS_PROPOSAL_KEYS},
    'hypotrail.preview_effects/1': {'': cc.PREVIEW_EFFECTS_KEYS},
    'hypotrail.proposal_draft/1': {'': cc.DRAFT_KEYS},
    'hypotrail.evidence/1': {'': cc.EVIDENCE_KEYS, 'results[]': cc.EVIDENCE_RESULT_KEYS,
                             'exposure.ledger[]': cc.LEDGER_KEYS, 'detail': cc.DETAIL_KEYS},
    'hypotrail.explain/1': {'': cc.EXPLAIN_KEYS, 'terms[]': cc.EXPLAIN_TERM_KEYS},
    'hypotrail.export/1': {'': cc.EXPORT_KEYS},
    'hypotrail.handoff/1': {'': cc.HANDOFF_KEYS},
    'hypotrail.check/1': {'findings[].location': cc.CHECK_LOCATION_KEYS},
    # WP-A7: the data card is a read of the Data & EDA tab (CLI-CONTRACT §11.1).
    'hypotrail.data/1': {'': freeze.DATA_PAYLOAD_KEYS, 'groups[].variables[]': freeze.DATA_VARIABLE_KEYS},
}


def test_client_key_lists_equal_the_engine_contract():
    for schema, rules in EXPECTED.items():
        for selector, keys in rules.items():
            assert CONTRACT['schemas'][schema][selector] == list(keys), (schema, selector)
    rules = CONTRACT['fixtures']['run.eda_distribution.']
    assert rules['values'] == list(cc.DISTRIBUTION_VALUE_KEYS)
    assert rules['values.numeric.bins[]'] == list(cc.DISTRIBUTION_BIN_KEYS)
    assert CONTRACT['not_implemented_reason'] == cc.NOT_IMPLEMENTED
    assert CONTRACT['error_codes_added'] == list(cc.NEW_ERROR_CODES)


def test_the_engine_stub_refusal_matches_the_fixture():
    from mlkit.study import errors
    refusal = errors.not_implemented('evidence').to_dict()
    payload = json.loads((HERE / 'fixtures' / 'error.not_implemented.json').read_text())['payload']
    assert payload['error'] == refusal
