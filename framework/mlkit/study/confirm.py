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
  | \bpas\s+pour\b | \bnot\s+for\b | \bbut\s+not\b | \bmais\s+pas\b
""", re.IGNORECASE | re.VERBOSE)
# A partial refusal (WP-A9, B1): a negator followed by a part of the proposal ("oui pour le
# plafonnement, pas de log", "keep everything except contact" while the value keeps
# contact). "pas pour" / "not for" are conditional anywhere (above); these negators are
# checked against the value by :func:`partial_refusal`.
PARTIAL_NEGATORS = frozenset('pas not sans except sauf no non without'.split())
PARTIAL_SKIP = frozenset("""
    le la les l de du des d un une the a an for pour of to au aux en with avec on sur in dans
    any aucun aucune
""".split())
# The decisions whose value has several parts a reply could accept separately.
PARTIAL_DECISIONS = ('feature_availability', 'preprocessing', 'split', 'model_variant',
                     'final_test')
# The parts of a preprocessing value and the concept terms that name them
# (``content/concepts.yaml``): a negated part is consistent when the value leaves it out.
PREPROCESSING_PARTS = {'caps': 'caps', 'log_transform': 'log_transform',
                       'missing': 'missing_indicator',
                       'rare_category_min_rows': 'rare_categories'}
# A word the reply points at ("that split", "this rule", "cette règle"): a proposal word
# pointed at relates the reply on its own (WP-A9, H1).
DEICTIC = re.compile(r"\b(?:that|this|these|those|ce|cet|cette|ces|same|meme)\s+([^\W_]+)")
# A reply that opens with a choosing verb in the imperative states a choice (WP-A9, H1).
CHOOSING_LEAD = re.compile(r"""^\s*(?:
    use|take|keep|go\s+with|adopt|choose|pick|apply|fix|call|drop|exclude|leave|remove
  | utilise[sz]?|prends|prenez|garde[sz]?|adopte[sz]?|choisis|choisissez|applique[sz]?
  | fixe[sz]?|appelle[sz]?|exclu[se]|excluez|ecarte[sz]?|retire[sz]?|on\s+(?:prend|utilise|fixe)
  | (?:i|we)\s+(?:conclude|keep|use|take|call|exclude|drop|pick|choose|go\s+with)
  | je\s+(?:conclus|garde|prends|retiens|choisis|exclus|appelle)
  | (?:on|nous)\s+(?:conclut|concluons|garde|gardons|retient|retenons|choisit|choisissons)
)\b""", re.IGNORECASE | re.VERBOSE)
# Keys of a preprocessing value that the engine sets: not part of what a reply relates to.
ENGINE_SET_KEYS = frozenset({'motivated_by', 'data_contingent', 'target_looks_before'})
# Words of decision ids too common to relate a reply on their own.
GENERIC_DECISION_WORDS = frozenset({'time', 'model', 'choice'})
# Words of an agreement (WP-A9, H1): an overlap with the proposal counts only in a reply that
# agrees ("oui, avant le premier appel"), never in a remark that merely shares a word.
AGREEMENT_TOKENS = frozenset("""
    yes yeah yep yup ya oui ouais ok okay okey sure accord daccord agreed agree correct right
    exactly exactement exact parfait perfect entendu valide fine absolutely definitely indeed
    go va
""".split())
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


def _match(a: str, b: str) -> bool:
    """Two folded words relate: equal, a final "s" aside, or a shared five-letter stem."""
    if a == b or (a.endswith('s') and a[:-1] == b) or (b.endswith('s') and b[:-1] == a):
        return True
    return len(a) >= 5 and len(b) >= 5 and a[:5] == b[:5]


# Clause cuts of a reply: punctuation, but never the point or comma inside a number ("0.2").
REPLY_CLAUSES = re.compile(r"(?:[;:!?…—–()]|(?<!\d)[.,]|[.,](?!\d))+|\s-\s")


def _clauses(words: str) -> list[str]:
    """``words`` cut on punctuation (a decimal point is not a cut), identifiers removed."""
    cmd = _cmd()
    return [c for c in REPLY_CLAUSES.split(cmd.IDENTIFIER.sub(' ', words)) if c.strip()]


class Topic:
    """What a reply may relate to (WP-A9, H1): the words and numbers of the proposal's value,
    restatement and labels, and the concept terms of its value (``content/concepts.yaml``),
    which a reply repeats when it restates; and the ``reason_domain`` words of its decision,
    which say something about the decision beyond its value."""

    def __init__(self, value: Any, texts: Iterable[str], terms: Iterable[str] = (),
                 domain: Iterable[str] = ()):
        cmd = _cmd()
        texts = tuple(t for t in texts if t)
        skip = cmd._FILLER | cmd._ACK | ENDORSEMENT_TOKENS
        self.words = {w for w in cmd._value_words(value) + [w for t in texts
                                                            for w in cmd._words(t)]
                      if w not in skip and not w.isdigit()}
        self.numbers = {round(n, 6) for n in cmd._value_numbers(value)}
        for t in texts:
            self.numbers |= {round(n, 6) for n in cmd._numbers(cmd.IDENTIFIER.sub(' ', t))}
        self.terms = [str(t) for t in terms if t]
        self.domain_terms = [str(t) for t in domain if t]
        self.names = {cmd._fold(str(k)) for k in _names(value)}
        # Words of the structured value (keys, identifiers such as a verdict, a rule, a
        # model; never a free-text sentence): naming one relates a reply on its own.
        self.specific = {w for name in _names(value) | _identifiers(value)
                         for w in cmd._words(str(name))
                         if len(w) >= 4 and not w.isdigit() and w not in skip}

    def restates(self, word: str) -> bool:
        """``word`` repeats a word of the value, restatement or labels, or names a concept
        of the value ("plafonnement" for caps, "meilleurs" for a capacity)."""
        from . import concepts
        return any(_match(word, w) for w in self.words) \
            or any(concepts.term_said(t, [word]) for t in self.terms)

    def says_concept(self, clause: str) -> bool:
        """``clause`` names a concept of the value ("leave out", "exclude", "before",
        "plafonner"): it states the decision rather than only mentioning its words."""
        from . import concepts
        tokens = [t for t in concepts.fold_tokens(clause) if t not in ENDORSEMENT_TOKENS]
        return concepts.any_said(self.terms, tokens)

    def domain(self, word: str) -> bool:
        """``word`` belongs to the decision's domain (``reason_domain``)."""
        from . import concepts
        return any(concepts.term_said(t, [word]) for t in self.domain_terms)

    def number(self, word: str) -> bool:
        cmd = _cmd()
        if word in cmd.NUMBER_WORDS:
            return float(cmd.NUMBER_WORDS[word]) in self.numbers
        try:
            return round(float(word.replace(',', '.')), 6) in self.numbers
        except ValueError:
            return False


def _identifiers(value: Any) -> set[str]:
    """String leaves of ``value`` without a space (a verdict, a rule, a model slot)."""
    if isinstance(value, str):
        return {value} if value.strip() and ' ' not in value.strip() else set()
    if isinstance(value, Mapping):
        return set().union(*(_identifiers(v) for v in value.values())) if value else set()
    if isinstance(value, (list, tuple)):
        return set().union(*(_identifiers(v) for v in value)) if value else set()
    return set()


def _names(value: Any) -> set[str]:
    """Mapping keys of ``value`` at any depth (variable and column names)."""
    out: set[str] = set()
    if isinstance(value, Mapping):
        for k, v in value.items():
            out.add(str(k))
            out |= _names(v)
    elif isinstance(value, (list, tuple)):
        for v in value:
            if isinstance(v, str):
                out.add(v)
            out |= _names(v)
    return out


def _content(clause: str) -> list[str]:
    cmd = _cmd()
    numbers = [n.group().replace(',', '.') for n in cmd.NUMBER.finditer(clause)]
    words = [w for w in content_beyond_endorsement(clause) if not w.isdigit()]
    return words + numbers


def _related(word: str, topic: Topic) -> bool:
    return topic.number(word) or word in topic.names or topic.restates(word) \
        or topic.domain(word)


def clause_relates(clause: str, topic: Topic) -> bool | None:
    """Whether a clause (or a whole reply) is about the proposal: it states a number or
    names a key of the value, or two of its content words (all of them, when there is only
    one) repeat the proposal or belong to the decision's domain. One shared common noun in
    otherwise unrelated words is not enough. None without content."""
    content = _content(clause)
    if not content:
        return None
    if any(topic.number(w) or w in topic.names
           or any(_match(w, x) for x in topic.specific) for w in content):
        return True
    cmd = _cmd()
    pointed = [m.group(1) for m in DEICTIC.finditer(cmd._fold(clause))]
    if any(_related(w, topic) for w in pointed):
        return True                      # "use that split", "cette règle"
    related = sum(_related(w, topic) for w in content)
    return related >= 2 or related == len(content)


def states_decision(words: str, topic: Topic) -> bool:
    """A clause of the reply is a restatement of the proposal and nothing else: every
    content word repeats it or belongs to its domain, and there are at least two ("We
    predict before the first call.", "seventy thirty stratified split with that seed",
    "appeler les 20 meilleurs"). Stating the decision is an agreement signal."""
    for clause in _clauses(words):
        content = _content(clause)
        if len(content) >= 2 and all(_related(w, topic) for w in content):
            return True
    return False


def agrees(words: str) -> bool:
    """An agreement signal: an endorsement, an agreement opening ("yes", "je garde", "let's
    go with"), a clause that opens with a choosing verb ("use that split", "leave x1 out",
    "keep the default", "prends cette règle"), or an agreement word anywhere ("d'accord",
    "ok")."""
    cmd = _cmd()
    folded = cmd._fold(words)
    return bool(ENDORSEMENT.search(folded) or cmd.AGREEMENT_LEAD.match(folded)
                or any(CHOOSING_LEAD.match(c) for c in _clauses(folded))
                or AGREEMENT_TOKENS & set(_tokens(folded)))


def relates_to(words: str, topic: Topic) -> bool:
    """WP-A9 (H1): a reply relates to the proposal when its words are about the proposal
    (:func:`clause_relates` applied to the whole reply, identifiers removed) and it agrees:
    an agreement word or opening (:func:`agrees`), a clause that is a restatement only
    (:func:`states_decision`), or a concept of the value named ("Leave out the desk
    follow-ups", "on plafonne ce montant"). One shared common noun in an off-topic remark ("oui,
    la pizza du client est bonne") is not enough."""
    # The decision part of the reply: before a reason connector, when it holds content
    # ("Yes, adopt the model because it ranks better": the reason is not the answer).
    folded = _cmd()._fold(words)
    cut = REASON_CONNECTOR.search(folded)
    head = folded[:cut.start()] if cut and _content(folded[:cut.start()]) else folded
    if not clause_relates(' '.join(_clauses(head)), topic):
        return False
    return agrees(words) or states_decision(words, topic) or topic.says_concept(words)


def has_reason(words: str, topic: Topic | None = None) -> bool:
    """A reason (WP-A9, H1): a reason connector ("parce que", "car", "because", "since",
    "puisque", "vu que", "étant donné", "given", "as the ..."), or a clause that is neither a
    restatement of the value nor unrelated: it says something beyond the value's own words
    and numbers, and it is about the proposal or its domain ("yes, the desk handles twenty
    calls"). "ok, 10 %" restates; "je confirme, j'aime la pizza" is unrelated. Without a
    ``topic``, only a connector counts."""
    cmd = _cmd()
    if REASON_CONNECTOR.search(cmd._fold(words)):
        return True
    if topic is None:
        return False
    for clause in _clauses(words):
        content = _content(clause)
        extra = [w for w in content if not topic.number(w) and not topic.restates(w)]
        if extra and clause_relates(clause, topic):
            return True
    return False


def _negated_in(texts: Iterable[str], word: str) -> bool:
    """A text of the proposal negates ``word`` itself ("no log transform", "sans
    plafonnement"): a reply that repeats that negation restates."""
    cmd = _cmd()
    for text in texts:
        tokens = _tokens(cmd._fold(cmd.IDENTIFIER.sub(' ', text or '')))
        for i, t in enumerate(tokens):
            if t in PARTIAL_NEGATORS:
                j = i + 1
                while j < len(tokens) and tokens[j] in PARTIAL_SKIP:
                    j += 1
                if j < len(tokens) and _match(tokens[j], word):
                    return True
    return False


def partial_refusal(words: str, proposal: Mapping) -> dict | None:
    """WP-A9 (B1): a reply that accepts one part of a multi-part proposal and refuses
    another. A negator ("pas", "not", "sans", "except", "sauf", "no", "non", "without")
    followed by a part of the value is a refusal of that part unless the value itself leaves
    it out:

    * ``feature_availability``: the part is a variable; "except x1", "sans x1"
      agree with a value that excludes it, and refuse a value that keeps it;
    * ``preprocessing``: the part is a step (caps, log, missing indicator, rare grouping, by
      its concept terms) or a column of a step; "pas de log" agrees with a value without a
      log transform;
    * ``split``: a word of the value or restatement, unless the restatement negates it too.

    A negated description ("pas connu avant l'appel", "not available") is a statement, not a
    refusal. A part followed by "non" or "no" ("le log non merci") is negated too. Returns
    ``{negator, part}`` or None. "pas pour" and "not for" are conditional anywhere
    (:data:`CONDITIONAL_ANYWHERE`)."""
    decision_id, value = proposal.get('decision_id'), proposal.get('value')
    if decision_id not in PARTIAL_DECISIONS or not isinstance(value, Mapping):
        return None
    cmd = _cmd()
    texts = (proposal.get('restatement') or '', *(proposal.get('labels') or {}).values())
    folded = cmd._fold(cmd.IDENTIFIER.sub(' ', words))
    tokens = re.findall(r"[^\W]+(?:\.[^\W]+)*", folded)
    names = {cmd._fold(str(k)): k for k in value}
    for i, t in enumerate(tokens):
        if t not in PARTIAL_NEGATORS:
            continue
        j = i + 1
        while j < len(tokens) and tokens[j] in PARTIAL_SKIP:
            j += 1
        if j >= len(tokens):
            continue
        part = tokens[j]
        if part.startswith(cmd.DESCRIPTIVE_AFTER_NEGATOR) or part in PARTIAL_NEGATORS:
            continue
        found = _partial_part(decision_id, value, texts, names, t, part)
        if found is not None:
            return found
    # A part followed by "non" / "no" ("le log non merci", "the log, no").
    for i, t in enumerate(tokens):
        if t in ('non', 'no') and i > 0 and tokens[i - 1] not in PARTIAL_SKIP:
            found = _partial_part(decision_id, value, texts, names, t, tokens[i - 1])
            if found is not None:
                return found
    return None


def _partial_part(decision_id: str, value: Mapping, texts, names: Mapping, t: str,
                  part: str) -> dict | None:
    """``{negator, part}`` when negating ``part`` refuses a part the value holds."""
    from . import concepts
    cmd = _cmd()
    found = {'negator': t, 'part': part}
    if decision_id == 'feature_availability':
        name = names.get(part)
        if name is not None and value[name] not in EXCLUDED_STATUSES:
            return found
        return None
    if decision_id == 'preprocessing':
        step = next((k for k, concept in PREPROCESSING_PARTS.items()
                     if concepts.any_said(concepts.concept_terms(concept), [part])), None)
        if step is None:
            columns = {cmd._fold(str(c)) for c in list(value.get('caps') or {})
                       + list(value.get('log_transform') or [])}
            return found if part in columns else None
        active = value.get(step)
        if step == 'missing':
            active = active == 'indicator' or (isinstance(active, Mapping)
                                               and 'indicator' in active.values())
        return found if active and not _negated_in(texts, part) else None
    topic = Topic(value, texts)
    if topic.restates(part) and not _negated_in(texts, part):
        return found
    return None


def topic_of(state: Mapping, proposal: Mapping) -> Topic:
    """The :class:`Topic` of an open proposal: its value, restatement and labels, the concept
    terms of its value, and the ``reason_domain`` words of its decision
    (``content/concepts.yaml``)."""
    from . import concepts
    terms = [t for item in concepts.concept_map(state, proposal) for t in item.get('terms') or []]
    domain = (concepts.data().get('reason_domain') or {}).get(proposal['decision_id']) or []
    texts = (proposal['restatement'], *(proposal.get('labels') or {}).values())
    value = proposal['value']
    if isinstance(value, Mapping):   # keys the engine sets are not what the junior decides
        value = {k: v for k, v in value.items() if k not in ENGINE_SET_KEYS}
    topic = Topic(value, texts, terms, domain)
    # The decision's own name ("split", "policy", "preprocessing") relates a reply too.
    topic.specific |= {w for w in str(proposal['decision_id']).split('_')
                       if w not in GENERIC_DECISION_WORDS}
    return topic


def guided_problem(state: Mapping, proposal: Mapping, words: str) -> str | None:
    """The guided rule that depends on the proposal (ADR 0005, WP-A9): ``unrelated_reply``
    unless the reply holds an explicit endorsement or agrees and is about the proposal
    (:func:`relates_to`); then, for the trade-offs, ``reason_required`` unless it gives a
    reason (:func:`has_reason`). None when the words confirm."""
    topic = topic_of(state, proposal)
    if not is_endorsement(words) and not relates_to(words, topic):
        return 'unrelated_reply'
    if needs_reason(state, proposal['decision_id']) and not has_reason(words, topic):
        return REASON_REQUIRED
    return None


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
