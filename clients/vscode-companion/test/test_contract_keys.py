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

from mlkit.study import after_study as aft, cmd_data, companion_env as ce, panel_digest as pd  # noqa: E402

CONTRACT = json.loads((HERE / 'fixtures' / 'contract-keys.json').read_text(encoding='utf-8'))

# Owner session 2026-10-26, wave W1 (CLI-CONTRACT §3.1, §3.2; CLI-CONTRACT-COMPANION): the
# objects of the summary's ``next_action`` the panel reads or receives, frozen with the wave's
# contract commit: the pause (L1 ``option_labels``), a free choice's options (L1, the R16
# choice card), what comes after the study (L7), and the panel line (R1, R1b; absent when the
# panel is off). Each list is absent from a payload where it does not apply.
NEXT_ACTION = {'next_action.pause': freeze.PAUSE_KEYS,
               'next_action.choice_options[]': freeze.CHOICE_OPTION_KEYS,
               'next_action.after_study': aft.AFTER_STUDY_KEYS,
               'next_action.after_study.azureml': aft.AZUREML_KEYS,
               'next_action.panel': ce.PANEL_KEYS,
               'next_action.panel.where': ce.WHERE_KEYS,
               'next_action.panel.shown': ce.SHOWN_KEYS}
# Contract P1 (CLI-CONTRACT §17.2): the digest's objects for the one page.
P1_DIGEST = {'automation': pd.SUMMARY_AUTOMATION_KEYS, 'review_queue': pd.SUMMARY_REVIEW_KEYS,
             'defensibility': pd.SUMMARY_DEFENSIBILITY_KEYS, 'ledger': pd.SUMMARY_LEDGER_KEYS,
             'sample': pd.SUMMARY_SAMPLE_KEYS, 'criterion_configurations': pd.SUMMARY_CRITERION_CONFIG_KEYS}

EXPECTED = {
    'hypotrail.summary/1': {'': cc.SUMMARY_KEYS, **NEXT_ACTION},
    'hypotrail.summary/1+digest': {'': cc.DIGEST_SUMMARY_KEYS, 'digest.items[]': cc.DIGEST_ITEM_KEYS,
                                   'digest.counts': cc.DIGEST_COUNT_KEYS, 'last_session': cc.LAST_SESSION_KEYS,
                                   **NEXT_ACTION, **P1_DIGEST},
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
    'hypotrail.data/1': {'': freeze.DATA_PAYLOAD_KEYS, 'groups[].variables[]': freeze.DATA_VARIABLE_KEYS,
                         # Contract P1.9, P1.10 (§17.3, §17.4): the seeded sample, the special rows.
                         'rows': cmd_data.ROWS_KEYS, 'special_rows': cmd_data.SPECIAL_ROW_KEYS},
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


def test_the_panel_contract_version_is_the_engines():
    """CLI-CONTRACT §17.1.5: the panel's constant (``lib/flag.js``) is the engine's version."""
    flag = (HERE.parent / 'lib' / 'flag.js').read_text(encoding='utf-8')
    assert f'const PANEL_CONTRACT = {ce.PANEL_CONTRACT};' in flag


def test_one_anchor_grammar_for_the_engine_and_the_panel():
    """CLI-CONTRACT §17.1.1: the panel's grammar (``lib/protocol.js`` ``ANCHOR``, which
    ``lib/models/page.js`` repeats) is the engine's ``companion_env.ANCHOR_RE``: the same
    anchors pass and fail, a column with accents, spaces or parentheses included."""
    import re
    text = (HERE.parent / 'lib' / 'protocol.js').read_text(encoding='utf-8')
    raw = re.search(r"const ANCHOR = '([^']+)';", text).group(1).replace('\\\\', '\\')
    panel = re.compile(raw.replace('\\u0000', '\\x00').replace('\\u001f', '\\x1f')
                       .replace('\\u007f', '\\x7f'))
    page = (HERE.parent / 'lib' / 'models' / 'page.js').read_text(encoding='utf-8')
    assert re.search(r"const ANCHOR_RE = new RegExp\('([^']+)'\);", page).group(1) == \
        re.search(r"const ANCHOR = '([^']+)';", text).group(1)
    good = ['now', 'todo:sources', 'path', 'path:split', 'path:train_eda/eda.rate_by:job',
            'path:structural_eda/eda.distribution:Durée (min)', 'path:train_eda/eda.mean_by:Visitor Type',
            'tools:deliverables', 'tools:how']
    bad = ['', 'Now', 'path:', 'path:Split', 'path:split/', 'path:split/a\nb', 'tools:learn',
           'todo:other']
    for anchor in good:
        assert ce.ANCHOR_RE.fullmatch(anchor) and panel.fullmatch(anchor), anchor
    for anchor in bad:
        assert not ce.ANCHOR_RE.fullmatch(anchor) and not panel.fullmatch(anchor), anchor


def test_the_engine_stub_refusal_matches_the_fixture():
    from mlkit.study import errors
    refusal = errors.not_implemented('evidence').to_dict()
    payload = json.loads((HERE / 'fixtures' / 'error.not_implemented.json').read_text())['payload']
    assert payload['error'] == refusal
