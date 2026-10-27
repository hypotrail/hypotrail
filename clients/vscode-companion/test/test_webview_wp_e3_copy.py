"""v0.3 WP-E3 (scope S, simulated browser): the copy says to answer in the chat (R23).

Since R23 every decision is answered in the chat, and in the guided and express modes an
endorsement is enough (ADR 0005, decision 8 as amended): the panel no longer asks the junior
for "your own words" outside the training mode. On the one page (ADR 0004 d13) the proposal is
Now's card: it says to answer in the chat, in the mode's words, and its one action copies the
question (the former "See the proposal" button went with the tabs). The French copy addresses
the junior as "vous" throughout (WP-E2's choice, kept). Captured payloads of the real engine,
in English and in French. This is not a VS Code session.
"""
from __future__ import annotations

import copy
import re
from pathlib import Path

import pytest

from panel_cases import goto, load_views, open_case

CLIENT = Path(__file__).resolve().parent.parent

LEADS = {
    ('en', 'guided'): 'Answer in the chat: adopt it, or say what you change. This panel records no decision.',
    ('en', 'training'): 'Answer in the chat, in your own words: say what it decides, or what you change. This panel records no decision.',
    ('fr', 'guided'): "Répondez dans le chat : adoptez-la, ou dites ce que vous changez. Ce panneau n'enregistre aucune décision.",
    ('fr', 'training'): "Répondez dans le chat, avec vos mots : dites ce qu'elle décide, ou ce que vous changez. Ce panneau n'enregistre aucune décision.",
}
# Asking for the junior's own words, or sending the junior to answer in the panel (a record of
# past words, "avec vos mots :" before the quote, is not a request).
ASKS_WORDS = re.compile(r'in your own words|avec vos mots(?!\s*:)|Answer in Decisions|Répondre dans Décisions|answer here|répondez ici|'
                        r'Nothing changes until you answer|Rien ne change tant que', re.IGNORECASE)

# Prose a junior reads, without the quoted record of past answers ("Recorded in your words",
# the digest of what happened since the last visit, the basis of a recorded decision)
# and the acknowledgement of an interrupted run (it always takes the junior's words; since R31
# it is made in the chat, and `.ov-ack` explains it).
PROSE = """() => {
  const out = [];
  const w = document.createTreeWalker(document.getElementById('app'), NodeFilter.SHOW_TEXT);
  while (w.nextNode()) {
    const n = w.currentNode, p = n.parentElement;
    if (!p || !n.textContent.trim() || p.closest('[hidden], .sr-only, [data-hero-details], .ov-ack, [data-quoted], [data-digest-text], [data-basis]')) continue;
    const d = p.closest('details');
    if (d && !d.open && !p.closest('summary')) continue;
    out.push(n.textContent);
  }
  return out.join(' | ');
}"""


@pytest.fixture(scope='module')
def views(model, payload):
    return load_views(model, payload)


def with_mode(views, mode):
    out = dict(views)
    for case in ('binary', 'cv', 'regression'):
        out[f'summary.{case}'] = {**copy.deepcopy(views[f'summary.{case}']), 'mode': mode}
        out[f'decisions.{case}'] = {**copy.deepcopy(views[f'decisions.{case}']), 'mode': mode}
    return out


@pytest.mark.parametrize('lang', ['en', 'fr'])
@pytest.mark.parametrize('mode', ['guided', 'express', 'training'])
def test_now_says_to_answer_the_proposal_in_the_chat_in_the_modes_words(open_panel, views, mode, lang):
    panel = open_case(open_panel, with_mode(views, mode), lang=lang)
    page = panel.page
    now = page.locator('[data-block="now"]')
    assert now.get_attribute('data-now') == 'proposal'
    lead = now.locator('[data-answer-in-chat]').inner_text().replace('\u202f', ' ')
    assert lead == LEADS[(lang, 'training' if mode == 'training' else 'guided')]
    # Nothing is written (W4, W5, W7) and nothing is asked by itself.
    assert not [m for m in panel.posted() if m['type'] in ('run_eda', 'render', 'acknowledge', 'export_handoff', 'ask_agent')]


@pytest.mark.parametrize('lang', ['en', 'fr'])
def test_outside_training_the_page_never_asks_for_own_words(open_panel, views, lang):
    for case in ('binary', 'cv'):
        for mode in ('guided', 'express'):
            panel = open_case(open_panel, with_mode(views, mode), case=case, lang=lang)
            goto(panel)
            prose = panel.page.evaluate(PROSE).replace('\u202f', ' ')
            hit = ASKS_WORDS.search(prose)
            assert not hit, (case, mode, prose[max(0, hit.start() - 80):hit.end() + 40])


@pytest.mark.parametrize('lang', ['en', 'fr'])
def test_the_sealed_final_test_asks_for_words_and_a_reason_in_training_only(open_panel, views, model, lang):
    """At the opening (Now, NOW-7), the final test's card says how to answer, by mode."""
    words = {'en': 'in your own words and with your reason', 'fr': 'avec vos mots et votre raison'}[lang]
    opening = model('summary', 'captured/summary.binary.cv.opening')
    for mode, expected in (('guided', False), ('training', True)):
        v = with_mode(views, mode)
        v['summary.cv'] = {**copy.deepcopy(opening), 'mode': mode}
        v['evidence.cv'] = model('evidence', 'captured/evidence.binary.cv.sealed')
        panel = open_case(open_panel, v, case='cv', lang=lang)
        goto(panel)
        text = panel.page.locator('[data-block="now"] [data-open-in-chat]').inner_text().replace('\u202f', ' ')
        assert (words in text) is expected, (mode, text)


def test_the_french_copy_says_vous_throughout():
    tu = re.compile(r"(?<![\w'’])(tu|toi|ton|tes|ta|te)(?![\w'’])|(?<![\w])t['’](?=\w)", re.IGNORECASE)
    for path in sorted((CLIENT / 'media' / 'copy-fr').glob('*.js')):
        for i, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
            if line.strip().startswith('//'):
                continue
            for literal in re.findall(r"'((?:[^'\\]|\\.)*)'|\"((?:[^\"\\]|\\.)*)\"|`((?:[^`\\]|\\.)*)`", line):
                text = ''.join(literal)
                hit = tu.search(text)
                assert not hit, f'{path.name}:{i}: "{hit.group(0)}" in {text!r}'
