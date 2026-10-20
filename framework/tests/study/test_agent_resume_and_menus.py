"""Agent instructions after v0.1: the five-line resume (T8) and one menu per pause (F5),
plus numbers in words (F3, rule 2). The phrases tested are where the agent reads them and
name the engine's real fields."""
from __future__ import annotations

from mlkit.study import agent_files as af, view

CLAUDE = (af.SOURCE / 'CLAUDE.md.in').read_text()
SKILL = (af.SOURCE / 'dot-claude/skills/hypotrail-study/SKILL.md').read_text()
RESUME = (af.SOURCE / 'dot-claude/commands/hypotrail-resume.md').read_text()


class Flat(str):
    """Template text whose ``in`` ignores line wrapping (WP-A8)."""

    def __contains__(self, phrase) -> bool:
        return ' '.join(str(phrase).split()) in ' '.join(self.split())


def _rule(text: str, n: int) -> Flat:
    return Flat(text.split(f'\n{n}. **', 1)[1].split(f'\n{n + 1}. **', 1)[0])


def _items(text: str) -> list[str]:
    """The bold headings of a numbered five-line list, in order."""
    import re
    return re.findall(r'^\s*\d\. \*\*([^*]+)\*\*', text, re.MULTILINE)


def test_the_resume_answer_is_goal_decisions_position_next_limit():
    """The resume command lists the five lines; the skill's "where are we?" quotes the same
    engine recap (v0.3, WP-D: stated once, the skill points to the command)."""
    assert view.RECAP_LABELS == ('Goal', 'Decided', 'Now', 'Next', 'Limit')
    expected = ['The goal first', 'Decisions made', 'Where we are', 'The next decision',
                'One limitation']
    resume = Flat(RESUME)
    assert _items(RESUME) == expected, _items(RESUME)
    for phrase in ('`recap_junior`', 'quote it', 'excluded features by name', 'illustrative',
                   'revision numbers', 'in at most five lines'):
        assert phrase in resume, phrase
    resuming = Flat(SKILL.split('## Resuming', 1)[1].split('\n## ', 1)[0])
    for phrase in ('the same answer as the resume command', '`recap_junior`',
                   'five flat lines, goal first, quoted', 'no revision number'):
        assert phrase in resuming, phrase
    assert 'recap_junior' in view.SUMMARY_KEYS


def test_one_menu_then_one_question():
    rule4 = _rule(CLAUDE, 4)
    for phrase in ('Do not repeat the same option menu on consecutive turns',
                   'ask a single question'):
        assert phrase in rule4, phrase
    assert 'do not repeat the menu: ask one question' in SKILL


def test_numbers_in_words_are_numbers():
    rule2 = _rule(CLAUDE, 2)
    for phrase in ('Numbers in words are numbers', '"one in nine"',
                   'Name a withdrawn\n   or superseded proposal without its figure'):
        assert phrase in rule2, phrase


def test_both_task_renderings_carry_f3_f5_t8():
    """M3 task blocks: F3, F5, and T8 reach the regression rendering too (no stale
    regression copy of a rule), and the regression F3 example names the target unit."""
    for task in ('binary', 'regression'):
        claude = af.select_task(CLAUDE, task)
        skill = af.select_task(SKILL, task)
        resume = af.select_task(RESUME, task)
        rule2 = _rule(claude, 2)
        assert 'Numbers in words are numbers' in rule2, task
        assert 'superseded proposal without its figure' in ' '.join(rule2.split()), task
        assert 'ask a single question' in _rule(claude, 4), task
        assert 'do not repeat the menu: ask one question' in skill, task
        expected = ['The goal first', 'Decisions made', 'Where we are', 'The next decision',
                    'One limitation']
        assert _items(resume) == expected, (task, _items(resume))
        assert '`recap_junior`' in resume and '`recap_junior`' in skill, task
        assert 'hypotrail:task' not in claude + skill + resume
    regression_rule2 = ' '.join(_rule(af.select_task(CLAUDE, 'regression'), 2).split())
    assert '"about six <unit>"' in regression_rule2 and 'the target unit included' in \
        regression_rule2
    assert '"one in nine"' not in regression_rule2
