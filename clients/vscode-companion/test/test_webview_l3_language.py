"""L3 (owner session 2026-10-26, R4; decision D4b; simulated browser): one language per panel.

The engine gives each junior text the panel shows in both languages (`status --summary
--digest` `texts`, `evidence` `texts` and `question_junior`, the data card's `texts`), and the
panel shows the one of its EN | FR switch. On the captured payloads of a French Auto MPG study
(`captured/*.regression.fr.json`, `capture.py`):

* the French panel shows no English sentence that is not marked as such (`lang="en"`, the
  "(en)" marker of a text the engine has in English only, or the agent's restatement);
* the English panel, on the same French study, shows the engine's English texts, and no
  French sentence that is not marked `lang="fr"`.

Identifiers, column names, quoted case or junior words and code are not prose and are left
out. This is not a VS Code session.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from panel_cases import expand_eda, goto, open_case, set_language

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / 'framework' / 'tests' / 'acceptance' / 'agent'))
import graders_v03 as g  # noqa: E402

CAPTURED = Path(__file__).resolve().parent / 'fixtures' / 'captured'
pytestmark = pytest.mark.skipif(not (CAPTURED / 'summary.regression.fr.json').is_file(),
                                reason='the French captures are not present (capture.py)')

# The visible prose of one tab, with the texts marked in another language left out (the
# marker itself says which), and what is not prose: code, quotations, identifiers.
PROSE = """(lang) => {
  const out = [];
  const walker = document.createTreeWalker(document.getElementById('app'), NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    const n = walker.currentNode, p = n.parentElement;
    if (!p || !n.textContent.trim()) continue;
    if (p.closest('[hidden], .sr-only, code, pre, option, q, [data-quoted], [data-en-marker], .ht-src')) continue;
    const marked = p.closest('[lang]');
    if (marked && marked !== document.documentElement && marked.getAttribute('lang') !== lang) continue;
    const d = p.closest('details');
    if (d && !d.open && !p.closest('summary')) continue;
    const r = p.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) continue;
    out.push(n.textContent);
  }
  return out;
}"""


@pytest.fixture(scope='module')
def french_views(model):
    out = {}
    for view, name in [('summary', 'summary'), ('evidence', 'evidence'), ('eda', 'evidence'),
                       ('whatif', 'evidence'), ('decisions', 'decisions'), ('data', 'data'),
                       ('explain', 'explain'), ('trials', 'status')]:
        out[f'{view}.french'] = model(view, f'captured/{name}.regression.fr')
    return out


def _foreign(panel, lang: str) -> list[tuple[str, str]]:
    """The whole page, every fold and drawer open (the former tabs, ADR 0004 d13)."""
    page = panel.page
    goto(panel)
    expand_eda(page)
    found = []
    for text in page.evaluate(PROSE, lang):
        found += [('page', s) for s in g.foreign_sentences(' '.join(text.split()), lang, 5)]
    return found


def test_the_french_capture_is_a_french_study(french_views):
    summary = french_views['summary.french']
    assert summary['language'] == 'fr'
    texts = summary['texts']
    assert set(texts) == {'en', 'fr'}
    assert texts['fr']['plan'] != texts['en']['plan']


def test_a_french_panel_on_a_french_study_shows_no_unmarked_english(open_panel, french_views):
    panel = open_case(open_panel, french_views, case='french', lang='fr')
    found = _foreign(panel, 'fr')
    assert found == [], found
    assert panel.page.evaluate('document.documentElement.lang') == 'fr'


def test_an_english_panel_on_a_french_study_shows_the_engine_texts_in_english(open_panel,
                                                                              french_views):
    panel = open_case(open_panel, french_views, case='french', lang='en')
    page = panel.page
    found = _foreign(panel, 'en')
    assert found == [], found
    # The switch changes the engine's texts too: a limit the page shows (the ledger fold) is the
    # English table's, and back in French the French table's, without a new read.
    limits = french_views['summary.french']['texts']
    english = limits['en']['limits']['validation_is_not_independent']
    french = limits['fr']['limits']['validation_is_not_independent']
    assert english != french
    goto(panel)
    shown = ' '.join(page.locator('#main').inner_text().split())
    assert english in shown and french not in shown
    set_language(page, 'fr')
    goto(panel)
    shown = ' '.join(page.locator('#main').inner_text().split()).replace('\u202f', ' ')
    assert french in shown and english not in shown
