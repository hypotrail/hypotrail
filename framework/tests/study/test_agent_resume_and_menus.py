"""Agent instructions after v0.1: the five-line resume (T8) and one menu per pause (F5),
plus numbers in words (F3, rule 2). The phrases tested are where the agent reads them and
name the engine's real fields."""
from __future__ import annotations

from mlkit.study import agent_files as af, view

CLAUDE = (af.SOURCE / 'CLAUDE.md.in').read_text()
SKILL = (af.SOURCE / 'dot-claude/skills/hypotrail-study/SKILL.md').read_text()
RESUME = (af.SOURCE / 'dot-claude/commands/hypotrail-resume.md').read_text()


def _rule(text: str, n: int) -> str:
    return text.split(f'\n{n}. **', 1)[1].split(f'\n{n + 1}. **', 1)[0]


def _items(text: str) -> list[str]:
    """The bold headings of a numbered five-line list, in order."""
    import re
    return re.findall(r'^\s*\d\. \*\*([^*]+)\*\*', text, re.MULTILINE)


def test_the_resume_answer_is_goal_decisions_position_next_limit():
    assert view.RECAP_LABELS == ('Goal', 'Decided', 'Now', 'Next', 'Limit')
    expected = ['The goal first', 'Decisions made', 'Where we are', 'The next decision',
                'One limitation']
    resuming = SKILL.split('## Resuming', 1)[1].split('\n## ', 1)[0]
    for doc in (RESUME, resuming):
        assert _items(doc) == expected, _items(doc)
        assert '`recap`' in doc and 'quote it' in doc
        assert 'excluded features by name' in doc
        assert 'illustrative' in doc
    assert 'revision numbers' in RESUME and 'No revision numbers' in resuming
    assert 'in at most five lines' in RESUME


def test_one_menu_then_one_question():
    rule4 = _rule(CLAUDE, 4)
    for phrase in ('do not repeat the same option\n   menu on consecutive turns',
                   'ask a single question'):
        assert phrase in rule4, phrase
    assert 'do not repeat the menu: ask one question' in SKILL


def test_numbers_in_words_are_numbers():
    rule2 = _rule(CLAUDE, 2)
    for phrase in ('Numbers in words are numbers', '"one in nine"',
                   'Name a withdrawn\n   or superseded proposal without its figure'):
        assert phrase in rule2, phrase
