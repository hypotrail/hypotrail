"""Guided confirmation (ADR 0005, owner remarks R1 and R3 of the first demo).

A confirmation is the junior's reply to one proposal, bound to it by ``decide confirm
PROPOSAL`` (or ``--proposal``). The ``training`` mode (v0.2b) adds concept matching
(:mod:`mlkit.study.concepts`) after the checks below; ``express`` keeps the guided rules.
In the ``guided`` mode, the default, the reply is
accepted when it is bound to the single open proposal of its decision at the current
revision, and it is not:

* empty (``missing_user_words``);
* a refusal, a hesitation or a disagreement (``negative_reply``, :func:`commands.is_negative`);
* a question (``question_reply``: the reply holds a question mark);
* conditional (``conditional_reply``: "oui mais je veux réfléchir", "d'accord sauf ...",
  "yes but", "unless", "sauf si": :func:`is_conditional`);
* a bare acknowledgement (``bare_acknowledgement``: "ok", "oui", "sure, sounds good"),
  unless it is an explicit first-person endorsement ("je confirme", "I agree",
  :data:`ENDORSEMENT`).

Then the reply must hold an explicit endorsement expression (:data:`ENDORSEMENT`) or
repeat content of the proposal (:func:`restates`); otherwise ``unrelated_reply``: a bare
agreement word followed by unrelated content ("yes, I like pizza") is never a decision. The recorded basis says which
kind of reply it was: ``restated`` when the reply repeats content of the proposal's value,
restatement or labels (:func:`restates`), else ``endorsed``.

The choice of the third pause (``policy``, or ``model_choice`` in a regression study) and the
``conclusion`` are business trade-offs: they need one reason (:func:`has_reason`), a clause
beyond the endorsement ("parce que", "because", "car", or any content word); otherwise
``reason_required``.

For ``feature_availability``, :func:`availability_warnings` compares the words with the value
mechanically: a variable named with exclusion words while the value keeps it, or with keep
words while the value excludes it, is a warning (``words_contradict_value``) in guided and
express, and a refusal of the same code in training (R3).

This module holds no state and performs no I/O; :mod:`mlkit.study.commands` calls it.
"""
from __future__ import annotations

import re
from typing import Any, Iterable, Mapping

from . import state as st

# --- reply classification ---------------------------------------------------------------

QUESTION_REPLY = 'question_reply'
CONDITIONAL_REPLY = 'conditional_reply'
REASON_REQUIRED = 'reason_required'
WORDS_CONTRADICT_VALUE = 'words_contradict_value'

# An explicit first-person endorsement: it makes an otherwise bare reply a decision
# ("oui je confirme cela", "I agree", "je suis d'accord", "je valide").
ENDORSEMENT = re.compile(r"""
    \b(?:i|we)\s+(?:do\s+|really\s+|fully\s+|hereby\s+)?
        (?:confirm|agree|approve|validate|accept|endorse|adopt)\b
  | \bje\s+(?:le\s+|la\s+|les\s+)?(?:confirme|valide|approuve|accepte|adopte)\b
  | \bj'?\s*(?:approuve|accepte|adopte)\b
  | \bje\s+suis\s+d'?\s*accord\b
  | \b(?:nous|on)\s+(?:le\s+|la\s+)?(?:confirm|valid)\w*\b
  | \bd'?\s*accord\s+pour\s+moi\b | \bca\s+me\s+va\b | \bc'?\s*est\s+bon\s+pour\s+moi\b
  | \bagreed\b | \bthat\s+works\s+for\s+me\b
""", re.IGNORECASE | re.VERBOSE)
# Words of an endorsement, and intensifiers: they are not a reason and do not restate.
ENDORSEMENT_TOKENS = frozenset("""
    confirm confirms confirmed confirme confirmes confirmons confirmez agree agreed agrees
    approve approved approuve approuvons validate validated valide valides validons accept
    accepted accepte acceptons adopt adopte adoptons endorse endorsed suis sommes cela ceci
    ca tout fait bien clairement totalement absolument completely fully absolutely
    definitely totally entierement vraiment really hereby yes oui ok okay agreement accord
""".split())
# A reply that sets a condition on its agreement. Anywhere: "unless", "sauf si", "only if",
# "à condition", "provided that", "pourvu que". After an endorsement (possibly with more
# endorsement or filler words): "but", "mais", "however", "cependant", "toutefois", "sauf",
# "except", "though". A hesitation anywhere ("je veux réfléchir", "let me think").
CONDITIONAL_ANYWHERE = re.compile(r"""
    \bunless\b | \bsauf\s+si\b | \bexcept\s+(?:if|when)\b | \bonly\s+if\b
  | \bseulement\s+si\b | \ba\s+condition\b | \bprovided\s+(?:that\b)? | \bpourvu\s+que\b
  | \breflechi\w* | \blet\s+me\s+think\b | \bthink\s+(?:about\s+)?(?:it|this|that)\s+over\b
  | \b(?:need|want|have)\s+to\s+think\b | \bthink\s+about\s+(?:it|this|that)\b
  | \bon\s+verra\b | \bje\s+vais\s+voir\b
""", re.IGNORECASE | re.VERBOSE)
RESERVATION_WORDS = frozenset('but mais however cependant toutefois neanmoins sauf except '
                              'though although'.split())
# A reason connector ("because", "parce que", "car", "since", "puisque", "given", "vu que").
REASON_CONNECTOR = re.compile(r"""
    \bbecause\b | \bsince\b | \bas\s+(?:the|it|we|our|this)\b | \bgiven\b | \bso\s+that\b
  | \bparce\s+qu | \bcar\b | \bpuisqu | \bvu\s+qu | \betant\s+donne | \bcomme\s+(?:le|la|les|on|nous)\b
  | \bafin\s+de\b | \bpour\s+que\b
""", re.IGNORECASE | re.VERBOSE)
# The decisions that need a reason, per task: the choice of the third pause and the
# conclusion (owner rule R1, "hybrid").
REASON_DECISIONS = {st.BINARY: ('policy', 'conclusion', st.FINAL_TEST),
                    st.REGRESSION: ('model_choice', 'conclusion', st.FINAL_TEST)}


def _cmd():
    from . import commands
    return commands


def is_question(words: str) -> bool:
    """A reply that asks rather than answers: it holds a question mark."""
    return '?' in words or '？' in words


def is_endorsement(words: str) -> bool:
    """An explicit first-person endorsement ("je confirme", "I agree", "je suis d'accord")."""
    cmd = _cmd()
    return bool(ENDORSEMENT.search(cmd._fold(words)))


def _tokens(folded: str) -> list[str]:
    return re.findall(r"[^\W_]+", folded)


def is_conditional(words: str) -> bool:
    """A reply that sets a condition on its agreement or hesitates (see the module doc)."""
    cmd = _cmd()
    folded = cmd._fold(cmd.IDENTIFIER.sub(' ', words))
    if CONDITIONAL_ANYWHERE.search(folded):
        return True
    lead = cmd.AGREEMENT_LEAD.match(folded)
    if not lead and not ENDORSEMENT.match(folded.strip()):
        return False
    rest = folded[lead.end():] if lead else folded
    skip = cmd._ACK | cmd._FILLER | ENDORSEMENT_TOKENS
    for tok in _tokens(rest):
        if tok in RESERVATION_WORDS:
            return True
        if tok not in skip:
            return False
    return False


def reply_problem(words: Any) -> str | None:
    """Why ``words`` cannot confirm in the guided mode, or None (the order of the module
    doc). The proposal-dependent checks (binding, reason, delegation) are the caller's."""
    cmd = _cmd()
    if not isinstance(words, str) or not words.strip():
        return 'missing_user_words'
    if cmd.is_negative(words):
        return 'negative_reply'
    if is_question(words):
        return QUESTION_REPLY
    if is_conditional(words):
        return CONDITIONAL_REPLY
    if cmd.is_bare_acknowledgement(words) and not is_endorsement(words):
        return 'bare_acknowledgement'
    return None


def _without_endorsement(words: str) -> str:
    """``words`` with endorsement words and intensifiers blanked."""
    cmd = _cmd()
    return re.sub(r'[^\W_]+', lambda m: ' ' if cmd._fold(m.group()) in ENDORSEMENT_TOKENS
                  else m.group(), words)


def content_beyond_endorsement(words: str) -> list[str]:
    """Content words of ``words`` that are not endorsement words or intensifiers."""
    cmd = _cmd()
    return [w for w in cmd.content_words(words) if w not in ENDORSEMENT_TOKENS]


def has_reason(words: str) -> bool:
    """A clause beyond the endorsement: a reason connector, or any content word that is not
    an endorsement word ("oui, parce que le centre d'appels a cette capacité", "yes, the desk
    handles twenty calls")."""
    cmd = _cmd()
    return bool(REASON_CONNECTOR.search(cmd._fold(words))) \
        or bool(content_beyond_endorsement(words))


def needs_reason(state: Mapping, decision_id: str) -> bool:
    return decision_id in REASON_DECISIONS[st.task_of(state)]


def restates(words: str, *, value: Any, texts: Iterable[str]) -> bool:
    """The reply repeats content of the proposal: a word or a number of its value,
    restatement or labels, endorsement words left out."""
    cmd = _cmd()
    return cmd.relates(_without_endorsement(words), value=value,
                       texts=tuple(t for t in texts if t))


def recorded_basis(words: str, proposal: Mapping) -> str:
    """``restated`` or ``endorsed`` for a confirmation in the junior's own words."""
    texts = (proposal['restatement'], *(proposal.get('labels') or {}).values())
    return st.RESTATED if restates(words, value=proposal['value'], texts=texts) \
        else st.ENDORSED


# --- the contradiction check of feature_availability (R3) ---------------------------------

EXCLUDE_STEMS = ('exclu', 'exclud', 'ecart', 'retir', 'enlev', 'supprim', 'drop', 'remov',
                 'without', 'sans', 'omit', 'jett')
EXCLUDE_WORDS = frozenset({'sans', 'without'})
KEEP_STEMS = ('gard', 'conserv', 'inclu', 'includ', 'keep', 'kept', 'retain', 'utilis',
              'using', 'retien', 'retenon')
KEEP_WORDS = frozenset({'use', 'used', 'uses', 'garde'})
NEGATORS = frozenset({'not', 'pas', 'never', 'jamais', 'ne', 'n', 'no', 'non', 'plus'})
EXCLUDED_STATUSES = ('not_available', 'uncertain_excluded')
KEPT_STATUSES = ('available_at_prediction', 'uncertain_included')
CLAUSES = re.compile(r"[,;:.!?…—–()]+|\s-\s")


def _direction(tokens: list[str]) -> str | None:
    """``exclude``, ``keep``, None (neither), or ``unclear`` (both kinds of words, or a
    negation before the first of them: "on ne garde pas x1")."""
    def excludes(t):
        return t in EXCLUDE_WORDS or t.startswith(EXCLUDE_STEMS)

    def keeps(t):
        return t in KEEP_WORDS or t.startswith(KEEP_STEMS)

    exclude = any(excludes(t) for t in tokens)
    keep = any(keeps(t) for t in tokens)
    if not exclude and not keep:
        return None
    first = next(i for i, t in enumerate(tokens) if excludes(t) or keeps(t))
    if (exclude and keep) or NEGATORS & set(tokens[:first]):
        return 'unclear'
    return 'exclude' if exclude else 'keep'


def availability_warnings(words: str, value: Mapping) -> list[dict]:
    """Variables the words name with exclusion or keep words against ``value`` (R3).

    The words are cut into clauses (punctuation). A clause that names a variable takes the
    direction of its exclusion words ("exclure", "écarter", "retirer", "sans", "exclude",
    "drop", "remove") or keep words ("garder", "inclure", "keep", "include", "use"); a clause
    with no such word continues the direction of the clause before it ("exclure x1,
    x2 et x3"). A clause with a negation, or with both kinds of words, says nothing.
    Each contradiction is ``{code: words_contradict_value, variable, said, value, message}``.
    """
    if not isinstance(words, str) or not isinstance(value, Mapping):
        return []
    cmd = _cmd()
    folded = cmd._fold(words)
    names = {cmd._fold(str(name)): name for name in value}
    warnings, seen = [], set()
    carried = None
    for clause in CLAUSES.split(folded):
        tokens = re.findall(r"[^\W]+(?:[._][^\W]+)*", clause)
        if not tokens:
            continue
        direction = _direction(re.findall(r'[^\W_]+', clause))
        named = [names[t] for t in tokens if t in names]
        if direction is None:
            direction = carried if named else None
        carried = direction if direction in ('exclude', 'keep') else None
        if direction not in ('exclude', 'keep'):
            continue
        for name in named:
            status = value[name]
            clash = (direction == 'exclude' and status in KEPT_STATUSES) \
                or (direction == 'keep' and status in EXCLUDED_STATUSES)
            if clash and name not in seen:
                seen.add(name)
                warnings.append({
                    'code': WORDS_CONTRADICT_VALUE, 'variable': name, 'said': direction,
                    'value': status,
                    'message': f'The words {"exclude" if direction == "exclude" else "keep"} '
                               f'{name}, but the confirmed value marks it {status}. Check with '
                               f'the junior; record a correction or propose again if the '
                               f'value is wrong.'})
    return warnings
