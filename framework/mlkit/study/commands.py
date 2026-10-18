"""Commands of the ``hypotrail`` CLI (plan §4; contract in ``docs/specs/CLI-CONTRACT.md``).

Every command returns an :class:`Outcome`: a JSON payload with a versioned ``schema``
and an exit code. Mutations go through :func:`mlkit.reliability.apply_command` as
``{request_id, expected_revision, action, params}`` under the writer lock
(:meth:`mlkit.study.store.StudyStore.execute`).

Actions (``ACTIONS``) are registered by name with a factory that receives the
:class:`Context` of the request and returns a :class:`mlkit.reliability.Handler`.
Phase 2 activities add their own actions with :func:`register_action` (for example
``run.reserve`` and ``run.promote``) and call the precondition checks in
:mod:`mlkit.study.preconditions`.

Decision actions:

* ``decide.propose``: records a first-class proposal with its restatement. Proposing
  never changes a confirmed decision; it supersedes an older open proposal for the
  same decision.
* ``decide.confirm``: needs the user's verbatim words in reply to the restatement,
  and an open proposal created by an earlier request whose basis (the confirmed
  decisions it rests on) is unchanged. Otherwise it refuses with
  ``ambiguous_confirmation``. It checks the three-pause preconditions, applies the
  §3.7 dependency table, and records the invalidation. Its ``basis`` says how the
  user decided: ``explicit`` (their own reply to the restatement, the default) or
  ``delegated_default`` (they explicitly delegated to the assistant's recommended
  default, which the restatement must state; the decision is then listed in
  ``not_yet_defensible``). A delegation's ``delegation_scope`` is ``this_decision`` (given
  at this pause) or ``standing`` (an earlier "for questions I can't answer, use your
  recommended default"); a standing delegation covers only the prediction moment, the
  feature availability and the split, so the policy and the conclusion are delegated only
  with ``this_decision`` (R1).
* ``decide.withdraw``: closes an open proposal.

pandas is never imported here, so ``status`` and ``plan`` stay fast.
"""
from __future__ import annotations

import copy
import importlib
import importlib.util
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from mlkit.reliability import CommandRefused, Handler

from . import case as c
from . import data as dt
from . import dependencies as dep
from . import exposure, guard, lock, preconditions, read, view
from . import state as st
from .errors import StudyError
from .store import StudyStore

# --- contract constants (frozen by tests/study/test_contract_freeze.py) -----------------

SCHEMAS = {'init': 'hypotrail.init/1', 'status': 'hypotrail.status/1',
           'plan': 'hypotrail.plan/1', 'decide': 'hypotrail.decide/1',
           'error': 'hypotrail.error/1'}
# ``status --summary`` (D3): a compact digest for chat agents; ``status --json`` is unchanged.
SUMMARY_SCHEMA = view.SUMMARY_SCHEMA
EXIT_OK = 0
EXIT_INTERNAL = 1
EXIT_REFUSED = 2
EXIT_ARTIFACT_STALE = 3
EXIT_UNKNOWN_OUTCOME = 4

ACTION_PROPOSE = 'decide.propose'
ACTION_CONFIRM = 'decide.confirm'
ACTION_WITHDRAW = 'decide.withdraw'
PROPOSE_PARAMS = frozenset({'decision_id', 'value', 'restatement', 'rationale'})
CONFIRM_PARAMS = frozenset({'proposal_id', 'user_words', 'channel', 'actor', 'basis',
                            'delegation_scope'})
WITHDRAW_PARAMS = frozenset({'proposal_id', 'reason'})
DEFAULT_CHANNEL = 'chat'
DEFAULT_ACTOR = 'user'
DEFAULT_BASIS = st.DEFAULT_BASIS

SPLIT_METHODS = ('stratified_random',)
SPLIT_KEYS = ('method', 'validation_fraction', 'seed')
CONCLUSION_KEYS = ('verdict', 'text')
# Companion files that may sit next to a case. They are never read by init: their
# statuses are tutorial choices, not human decisions (AGENTS.md).
IGNORED_CASE_SOURCES = ('project.json', 'results.json', 'tutorial-results.json',
                        'answers.yaml', 'project.yaml', 'frame.yaml')

# Words that alone never confirm anything (plan §5): a reply made only of these, filler
# words, and identifiers is a bare acknowledgement, not the user's own restatement.
ACKNOWLEDGEMENT_WORDS = frozenset("""
    ok okay okey k kk yes y yep yeah yup ya sure fine go ahead do it agreed agree approve
    approved confirm confirmed correct right exactly perfect good great sounds sound looks lgtm
    keep that this one it is s let lets please thanks thank you so alright all done nice cool
    oui ouais d accord daccord garde ça ca vas parfait c est cest bon très tres bien super
    merci valide validé go entendu compris understood noted
""".split())
# Grammatical words that carry no content of their own (English and French).
FILLER_WORDS = frozenset("""
    i me my mine we us our ours you your yours he she they them their to with by for of from
    the a an and or but as then now also on in at be been being am are was were will would
    can could should shall may might must just really very quite too well oh ah hmm uh um
    use using want wanted think mean meant like same way thing what which who
    there here have has had get got take taken pick picked choose chosen those these
    je j moi m nous tu te t toi vous il ils elle elles on le la les l un une des de du et ou
    mais pour avec à au aux en sur par ce cet cette ces se y donc alors cela comme
""".split())
# Identifiers a reply may quote (proposal and execution ids, request ids, digests): they
# say which proposal, not what is decided.
IDENTIFIER = re.compile(r'\b(?:[a-z]+_(?=[0-9a-z]*\d)[0-9a-z]+|r-[0-9a-z]+'
                        r'|(?=[0-9a-f]*[a-f])(?=[0-9a-f]*\d)[0-9a-f]{8,})\b', re.IGNORECASE)
# A reply that refuses, hesitates or disagrees: a clause opening with one of these words,
# or one of the phrases anywhere.
NEGATIVE_LEADS = frozenset("""
    no non nope nah nan wait stop attends attendez cancel annule annuler never jamais hold
""".split())
NEGATIVE_PHRASE = re.compile(r"""
    \b(?:disagree[sd]?|incorrect|wrong|reject|refuse|wait|stop|attends|attendez|faux|
        desaccord|hold\s+on|not\s+so\s+fast|no\s+way)\b
  | \bpas\s+d\W?\s*accord\b
""", re.IGNORECASE | re.VERBOSE)
# A negator ("not", "don't", "pas", "never") refuses unless one of the next words
# describes availability or a restart: "this feature is not available", "we don't know it
# before the call", "elle n'est pas connue", "don't restart it" are statements. So is an
# inability to answer ("for questions I can't answer, use your recommended default", R1).
NEGATORS = frozenset("not n't cannot pas never".split())
NEGATOR_SKIP = frozenset('be been yet encore really actually it them we nous that is are '
                         'was were'.split())
DESCRIPTIVE_AFTER_NEGATOR = (
    'availab', 'known', 'know', 'usable', 'used', 'use', 'included', 'include', 'recorded',
    'collected', 'observed', 'exist', 'have', 'has', 'restart', 'rerun', 'retry', 'relaunch',
    'run', 'disponib', 'connu', 'utilis', 'inclu', 'relanc', 'refai', 'sait', 'savons',
    'collect', 'enregistr', 'observ', 'redo', 'recompute', 'refit', 'answer', 'repond')
# Words that tie an acknowledgement to the interruption it acknowledges (L5).
ACKNOWLEDGEMENT_TOPIC = ('interrupt', 'unknown', 'outcome', 'killed', 'crash', 'died', 'dead',
                         'stopped', 'lost', 'failed', 'restart', 'rerun', 'run', 'result',
                         'execution', 'interromp', 'inconnu', 'relanc', 'arret', 'plant',
                         'resultat', 'execut')
STEM = 5   # two words relate when equal, or when both are long and share this prefix


@dataclass(frozen=True)
class Outcome:
    """A command result: the JSON payload printed and the process exit code."""

    payload: dict
    exit_code: int = EXIT_OK


@dataclass(frozen=True)
class Context:
    """What an action factory knows about the request it serves."""

    store: StudyStore
    request_id: str


ActionFactory = Callable[[Context], Handler]
ACTIONS: dict[str, ActionFactory] = {}


def register_action(name: str, factory: ActionFactory) -> None:
    """Register an ``apply_command`` action (Phase 2 extension point).

    ``factory(ctx)`` returns a :class:`mlkit.reliability.Handler` whose ``run(state,
    params)`` mutates state in memory and returns a JSON-serialisable result. Names are
    dotted (``run.promote``); registering a name twice is an error.
    """
    if name in ACTIONS:
        raise ValueError(f'action {name} is already registered')
    ACTIONS[name] = factory


def handlers(ctx: Context) -> dict[str, Handler]:
    return {name: factory(ctx) for name, factory in ACTIONS.items()}


def error_payload(command: str, exc: Exception) -> dict:
    if hasattr(exc, 'to_dict'):
        error = exc.to_dict()
    else:
        error = {'code': 'internal_error', 'message': f'{type(exc).__name__}: {exc}'}
    return {'schema': SCHEMAS['error'], 'ok': False, 'command': command, 'error': error}


def refused(command: str, exc: Exception) -> Outcome:
    return Outcome(error_payload(command, exc), EXIT_REFUSED)


# --- value checks -----------------------------------------------------------------------

# A number in free text: digits glued to letters count ("top100", review fix L4); digits
# inside an identifier (``p_5``, ``r_1a2b``, a digest prefix) are masked first.
NUMBER = re.compile(r'(?<![\d.])\d+(?:[.,]\d+)?')
PERCENT_AFTER = re.compile(r'\s?(?:%|percent\b|per\s?cent\b|pour\s?cent\b)', re.IGNORECASE)


def mask_identifiers(text: str) -> str:
    """``text`` with identifiers blanked (same length), so their digits are not numbers."""
    return IDENTIFIER.sub(lambda m: ' ' * len(m.group(0)), text)


def _numbers(text: str) -> set[float]:
    return {float(m.replace(',', '.')) for m in NUMBER.findall(mask_identifiers(text))}


def _value_numbers(value: Any, *, percents_only: bool = False) -> set[float]:
    """Numbers of a proposed value. A fraction may also be written as a percentage (of
    itself or of its complement). ``percents_only``: only those percentage forms."""
    found: set[float] = set()

    def walk(node):
        if isinstance(node, bool):
            return
        if isinstance(node, (int, float)):
            if not percents_only:
                found.add(float(node))
            if 0 < node < 1:   # a fraction may be written as a percentage
                found.update({round(100 * node, 6), round(100 * (1 - node), 6)})
        elif isinstance(node, str):
            if not percents_only:
                found.update(_numbers(node))
        elif isinstance(node, Mapping):
            for k, v in node.items():
                walk(k)
                walk(v)
        elif isinstance(node, (list, tuple)):
            for v in node:
                walk(v)
    walk(value)
    return found


def literal_numbers(text: str, value: Any, pool=None) -> list[str]:
    """Numbers written in ``text`` that come neither from ``value`` nor from ``pool``.

    A proposal's restatement and rationale may repeat the numbers of the proposed
    value, and the figures of current registry results it rests on ("115 selected"),
    traced with the matcher of ``hypotrail check`` (``pool`` is a
    :class:`mlkit.study.cmd_check.Pool` of the current results). A percentage ("100%",
    "30 percent") comes from a result, or from a fraction of the value ("30%" for a
    validation fraction of 0.3), never from another number of the value: "capacity:100"
    does not allow "100% precision" (review fix L3). Any other number is free text and
    is refused; it is reported as written, with ``%`` for a percentage.
    """
    from . import cite

    masked = mask_identifiers(text)
    plain = {round(n, 6) for n in _value_numbers(value)}
    percents = {round(n, 6) for n in _value_numbers(value, percents_only=True)}
    tokens = cite.parse_numbers(masked) if pool is not None else []
    out = set()
    for m in NUMBER.finditer(masked):
        number = round(float(m.group().replace(',', '.')), 6)
        percent = bool(PERCENT_AFTER.match(masked, m.end()))
        if number in (percents if percent else plain):
            continue
        if any(t.start <= m.start() < t.end and pool.trace(t)[0] == 'current' for t in tokens):
            continue
        out.add(m.group() + ('%' if percent else ''))
    return sorted(out)


def current_results_pool(store: StudyStore, state: Mapping, *, literals: bool = False):
    """A number pool of the current, verified registry results: what a proposal's text may
    cite besides its own value (D5). Current means current by state, lineage and code
    (:meth:`mlkit.study.read.Study.currency`).

    ``literals`` (the conclusion text, review fix M1) also admits the recorded values a
    report may repeat: the confirmed decisions other than the conclusion, the junior's
    recorded words, and the rules of the current policy evaluation; never the proposed
    conclusion itself.
    """
    from . import cmd_check

    study = read.open(store.study_dir)
    results = {}
    for slot, rid in sorted(state['current'].items()):
        if not st.is_current(state, slot) or not study.currency(rid)['current']:
            continue
        try:
            entry = study.result(rid)
        except StudyError:
            continue
        results[slot] = {'result_id': rid, 'values': entry['output']['values'],
                         'n_rows': entry['n_rows'], 'current': True, 'integrity': 'ok',
                         'activity': entry['activity'], 'params': entry['params']}
    decisions = {}
    if literals:
        decisions = {d: {'decision_id': d, 'value': dec['value'],
                         'confirmation': dec['confirmation']}
                     for d, dec in state['decisions'].items()
                     if d != 'conclusion' and dec['status'] == 'confirmed'}
    return cmd_check.Pool({'results': results, 'decisions': decisions, 'open_proposals': [],
                           'settings': {}, 'dataset': {}, 'facts': {'by_status': {}}})


def check_conclusion(store: StudyStore, state: Mapping, value: Mapping, restatement: str,
                     rationale: str) -> None:
    """Review fix M1: the conclusion text is traced when it is proposed.

    Every number of ``value.text`` must match a current result (or a recorded literal,
    :func:`current_results_pool`); the proposed value is no whitelist for itself
    (``literal_number_in_text``, ``details.field`` ``value.text``). Causal or forecast
    wording in the text, the restatement, or the rationale is refused
    (``causal_or_forecast_wording``, ``details.findings`` as ``hypotrail check`` reports
    them).
    """
    from . import cmd_check

    findings, _ = cmd_check.trace_text(current_results_pool(store, state, literals=True),
                                       mask_identifiers(value['text']), 'value.text')
    numbers = [f['details']['number'] for f in findings
               if f['code'] in ('untraceable_number', 'stale_number')]
    if numbers:
        raise CommandRefused('literal_number_in_text',
                             'The conclusion text contains numbers that are not figures of a '
                             'current result. Cite registered figures only.',
                             details={'field': 'value.text', 'numbers': sorted(set(numbers)),
                                      'findings': findings})
    wording = (cmd_check.wording(value['text'], 'value.text')
               + cmd_check.wording(restatement, 'restatement')
               + cmd_check.wording(rationale, 'rationale'))
    if wording:
        raise CommandRefused('causal_or_forecast_wording',
                             'The conclusion uses causal or forecast wording. The study shows '
                             'associations and rankings on past validation rows, not effects '
                             'of acting or forecasts; rephrase it.',
                             details={'findings': wording})


def _invalid(message: str, **details) -> CommandRefused:
    return CommandRefused('invalid_value', message, details=details)


case_of = c.case_of


def candidate_features(case: c.Case) -> list[str]:
    return [v['name'] for v in case.document['variables'] if v['role'] == 'feature']


def validate_value(state: Mapping, decision_id: str, value: Any) -> None:
    """Refuse a value that does not fit ``decision_id`` (``invalid_value``)."""
    if decision_id == 'prediction_time':
        if not isinstance(value, str) or not value.strip():
            raise _invalid('prediction_time is a non-empty description of the prediction moment.')
    elif decision_id == 'feature_availability':
        features = candidate_features(case_of(state))
        if not isinstance(value, Mapping):
            raise _invalid('feature_availability maps every candidate feature to a status.',
                           features=features, statuses=list(st.AVAILABILITY_DECISIONS))
        missing = sorted(set(features) - set(value))
        unknown = sorted(set(value) - set(features))
        bad = sorted(k for k, v in value.items() if v not in st.AVAILABILITY_DECISIONS)
        if missing or unknown or bad:
            raise _invalid('Every candidate feature needs exactly one availability status.',
                           missing=missing, not_features=unknown, invalid_status=bad,
                           statuses=list(st.AVAILABILITY_DECISIONS))
    elif decision_id == 'split':
        if not isinstance(value, Mapping) or set(value) != set(SPLIT_KEYS):
            raise _invalid('split is {"method", "validation_fraction", "seed"}.',
                           keys=list(SPLIT_KEYS))
        if value['method'] not in SPLIT_METHODS:
            raise CommandRefused('unsupported_capability',
                                 f'Split method {value["method"]!r} is not available.',
                                 details={'methods': list(SPLIT_METHODS)})
        fraction = value['validation_fraction']
        if isinstance(fraction, bool) or not isinstance(fraction, (int, float)) \
                or not 0 < fraction < 1:
            raise _invalid('validation_fraction is strictly between 0 and 1.')
        if type(value['seed']) is not int:
            raise _invalid('seed is an integer.')
    elif decision_id == 'policy':
        if dep.parse_policy(value) is None:
            raise _invalid('policy is "threshold:<t in [0, 1]>" or "capacity:<k >= 1>".')
    elif decision_id == 'conclusion':
        if not isinstance(value, Mapping) or set(value) != set(CONCLUSION_KEYS) \
                or value['verdict'] not in preconditions.CONCLUSION_VERDICTS \
                or not isinstance(value['text'], str) or not value['text'].strip():
            raise _invalid('conclusion is {"verdict", "text"}.',
                           verdicts=list(preconditions.CONCLUSION_VERDICTS))


def _fold(text: str) -> str:
    """Lower case without accents, with typographic apostrophes made plain."""
    import unicodedata
    text = text.lower().replace('’', "'").replace('`', "'")
    return ''.join(ch for ch in unicodedata.normalize('NFKD', text)
                   if not unicodedata.combining(ch))


def _words(text: str) -> list[str]:
    """Word tokens of ``text`` (identifiers removed, underscores split, accents folded)."""
    return re.findall(r'[^\W_]+', _fold(IDENTIFIER.sub(' ', text)))


def _folded(words) -> frozenset:
    return frozenset(_fold(w) for w in words)


_ACK, _FILLER = _folded(ACKNOWLEDGEMENT_WORDS), _folded(FILLER_WORDS)


def content_words(text: str) -> list[str]:
    """Tokens of ``text`` that are neither acknowledgements, filler, nor identifiers."""
    return [t for t in _words(text) if t not in _ACK and t not in _FILLER]


def is_bare_acknowledgement(words: str) -> bool:
    """True when a reply has no content beyond acknowledgement words, filler words and
    identifiers ("ok", "garde ça", "sure, sounds good to me", "ok p_5")."""
    return not content_words(words)


def is_negative(words: str) -> bool:
    """True when a reply refuses, hesitates or disagrees ("no", "wait", "I do not agree",
    "pas d'accord", "yes, but not before the call"). A negated availability or restart
    ("this feature is not available", "don't restart it") is a statement, not a refusal."""
    folded = _fold(IDENTIFIER.sub(' ', words))
    if NEGATIVE_PHRASE.search(folded):
        return True
    for clause in re.split(r"[,.;:!?…—-]+|\bbut\b|\bmais\b", folded):
        tokens = re.findall(r"[^\W_]+", clause)
        if tokens and tokens[0] in NEGATIVE_LEADS:
            return True
    tokens = re.findall(r"n't|[^\W_]+", folded.replace("n't", " n't "))
    for i, t in enumerate(tokens):
        if t in NEGATORS:
            after = [w for w in tokens[i + 1:i + 4] if w not in NEGATOR_SKIP]
            if not after or not after[0].startswith(DESCRIPTIVE_AFTER_NEGATOR):
                return True
    return False


def _related(a: str, b: str) -> bool:
    return a == b or (len(a) >= STEM and len(b) >= STEM and a[:STEM] == b[:STEM])


def _value_words(value: Any) -> list[str]:
    out: list[str] = []

    def walk(node):
        if isinstance(node, str):
            out.extend(_words(node))
        elif isinstance(node, Mapping):
            for k, v in node.items():
                walk(k)
                walk(v)
        elif isinstance(node, (list, tuple)):
            for v in node:
                walk(v)
    walk(value)
    return out


def relates(words: str, *, value: Any = None, texts: tuple[str, ...] = (),
            topic: tuple[str, ...] = ()) -> bool:
    """True when ``words`` share a content word or a number with ``value`` or ``texts``,
    or contain a word that starts with one of ``topic``."""
    mine = [w for w in content_words(words) if not w.isdigit()]
    theirs = [w for w in _value_words(value) + [w for t in texts for w in _words(t)]
              if w not in _FILLER and w not in _ACK and not w.isdigit()]
    if any(_related(a, b) for a in mine for b in theirs):
        return True
    if topic and any(a.startswith(topic) for a in mine):
        return True
    numbers = _value_numbers(value)
    for t in texts:
        numbers |= _numbers(IDENTIFIER.sub(' ', t))
    said = _numbers(IDENTIFIER.sub(' ', words)) | {float(NUMBER_WORDS[w]) for w in _words(words)
                                                   if w in NUMBER_WORDS}
    return bool({round(n, 6) for n in said} & {round(n, 6) for n in numbers})


# Number words a reply may use for a figure of the proposal ("twenty calls", "seventy
# thirty"): each word alone, no compound arithmetic.
NUMBER_WORDS = {w: n for n, names in enumerate((
    'zero', 'one un une', 'two deux', 'three trois', 'four quatre', 'five cinq', 'six',
    'seven sept', 'eight huit', 'nine neuf', 'ten dix', 'eleven onze', 'twelve douze',
    'thirteen treize', 'fourteen quatorze', 'fifteen quinze', 'sixteen seize', 'seventeen',
    'eighteen', 'nineteen')) for w in names.split()}
NUMBER_WORDS.update({w: n for n, names in (
    (20, 'twenty vingt'), (30, 'thirty trente'), (40, 'forty quarante'), (50, 'fifty cinquante'),
    (60, 'sixty soixante'), (70, 'seventy septante'), (80, 'eighty'), (90, 'ninety nonante'),
    (100, 'hundred cent'), (1000, 'thousand mille')) for w in names.split()})


def reply_problem(words: Any, *, value: Any = None, restatement: str | None = None,
                  topic: tuple[str, ...] = (), delegated: bool = False) -> str | None:
    """Why ``words`` cannot confirm (an ``ambiguous_confirmation`` reason), or None.

    In order: ``missing_user_words`` (empty), ``negative_reply`` (a refusal, a
    hesitation, a disagreement), ``bare_acknowledgement`` (nothing beyond
    acknowledgements, filler and identifiers), and, when a ``value``, ``restatement`` or
    ``topic`` is given, ``unrelated_reply`` (no word or number shared with them). A
    delegation (D1) relates by delegating, so ``delegated`` skips the last check.
    """
    if not isinstance(words, str) or not words.strip():
        return 'missing_user_words'
    if is_negative(words):
        return 'negative_reply'
    if is_bare_acknowledgement(words):
        return 'bare_acknowledgement'
    if delegated or (value is None and restatement is None and not topic):
        return None
    texts = (restatement,) if restatement else ()
    return None if relates(words, value=value, texts=texts, topic=topic) else 'unrelated_reply'


REPLY_MESSAGES = {
    'missing_user_words': "A confirmation needs the user's own words in reply to the restatement.",
    'negative_reply': 'These words refuse, hesitate, or disagree: nothing is confirmed. Ask what '
                      'the user wants instead and propose again.',
    'bare_acknowledgement': 'A bare acknowledgement is not a decision. Restate the proposal and '
                            'ask the user to answer it in their own words.',
    'unrelated_reply': 'These words share nothing with the proposal (no word or number of its '
                       'value or restatement). Restate the proposal and ask the user to answer '
                       'it in their own words.',
}


# A reply that hands the choice to the assistant's recommendation (D1). It must name the
# assistant's default or recommendation, or the act of leaving the choice to it: "go with
# it", "ok", or "garde ça" never delegate.
DELEGATION = re.compile(r"""
    \b(?:use|go\s+with|take|follow|pick|stick\s+with|keep|accept|choose|apply)\s+
        (?:your|the\s+assistant'?s?)\s+(?:own\s+)?(?:recommended\s+)?
        (?:defaults?|recommendations?|suggestions?|choice|pick|proposal)\b
  | \b(?:your|the\s+assistant'?s?)\s+(?:recommended\s+)?defaults?\b
  | \b(?:use|take|keep|go\s+with|stick\s+with|accept)\s+the\s+(?:recommended\s+)?defaults?\b
  | \bwhat(?:ever)?\s+you\s+(?:recommend|suggest|propose|think\s+is\s+best)\b
  | \b(?:it'?s|that'?s|is)\s+up\s+to\s+you\b | \byour\s+call\b
  | \bi(?:'ll|\s+will)?\s+leave\s+(?:it|that|this|the\s+choice)\s+(?:up\s+)?to\s+you\b
  | \b(?:let\s+you|you\s+can|you\s+may)\s+(?:decide|choose|pick)\b
  | \byou\s+(?:decide|choose|pick)\s+for\s+me\b
  | \bje\s+(?:te|vous)\s+laisse\s+(?:choisir|d[ée]cider|faire)\b
  | \b(?:prends|prenez|garde|gardez|utilise|utilisez|suis|suivez|retiens|retenez|applique|appliquez)\s+
        (?:ta|votre|ton|tes|vos)\s+(?:recommandations?|propositions?|choix|d[ée]fauts?|
        valeurs?\s+par\s+d[ée]faut)\b
  | \b(?:valeur|choix|option)\s+par\s+d[ée]faut\b
  | \bcomme\s+(?:tu\s+(?:veux|recommandes|proposes)|vous\s+(?:voulez|recommandez|proposez))\b
  | \b[àa]\s+(?:toi|vous)\s+de\s+(?:voir|choisir|d[ée]cider)\b
""", re.IGNORECASE | re.VERBOSE)
# A restatement that says it is the assistant's recommended default, the only kind a
# delegation can confirm: the junior must know what they delegated (D1).
STATES_DEFAULT = re.compile(r"""
    \brecommended\s+default\b
  | \bdefault\s+(?:that\s+)?(?:i|we|the\s+assistant)\s+recommends?\b
  | \bassistant'?s\s+(?:recommended\s+)?default\b
  | \bd[ée]faut\s+recommand[ée]e?\b
  | \brecommandation\s+par\s+d[ée]faut\b
""", re.IGNORECASE | re.VERBOSE)


def is_delegation(words: str) -> bool:
    """True when ``words`` explicitly delegate the choice to the assistant's recommended
    default ("use your recommended default", "je te laisse choisir"); a bare
    acknowledgement never does."""
    return isinstance(words, str) and not is_bare_acknowledgement(words) \
        and bool(DELEGATION.search(words))


def states_default(restatement: str) -> bool:
    """True when a restatement says it is the assistant's recommended default."""
    return isinstance(restatement, str) and bool(STATES_DEFAULT.search(restatement))


def basis(state: Mapping, decision_id: str) -> dict:
    """Confirmed values a proposal rests on (its ``depends_on`` decisions)."""
    out = {}
    for d in st.DEPENDS_ON[decision_id]:
        dec = state['decisions'][d]
        out[d] = dec['value'] if dec['status'] == 'confirmed' else None
    return out


def _ambiguous(reason: str, message: str, **details) -> CommandRefused:
    return CommandRefused('ambiguous_confirmation', message, details={'reason': reason, **details})


def _verify_sources(state: Mapping) -> None:
    """Plan §3.7 row 12: a changed case or dataset is refused, never absorbed."""
    changes = c.source_changes(state)
    if changes:
        raise c.changed_sources_error(changes)


# --- decision actions -------------------------------------------------------------------

def _propose(ctx: Context) -> Handler:
    def check(params):
        if params['decision_id'] not in st.DECISION_IDS:
            raise CommandRefused('unknown_decision', f'Unknown decision {params["decision_id"]!r}.',
                                 details={'decisions': list(st.DECISION_IDS)})
        for key in ('restatement', 'rationale'):
            if not isinstance(params[key], str) or not params[key].strip():
                raise _invalid(f'{key} is a non-empty string.', field=key)

    def run(state, params):
        decision_id, value = params['decision_id'], params['value']
        _verify_sources(state)                     # L1: never propose on changed bytes
        validate_value(state, decision_id, value)
        if decision_id == 'policy':
            value = dep.canonical_rule(value)        # L2: one spelling per rule
        if decision_id == 'conclusion':
            check_conclusion(ctx.store, state, value, params['restatement'],
                             params['rationale'])
        pool = None
        for key in ('restatement', 'rationale'):
            if not literal_numbers(params[key], value):
                continue
            pool = pool or current_results_pool(ctx.store, state)
            found = literal_numbers(params[key], value, pool)
            if found:
                raise CommandRefused('literal_number_in_text',
                                     f'The {key} contains numbers that are neither part of the '
                                     f'proposed value nor a figure of a current result. Repeat '
                                     f'only registered figures, or cite results by their '
                                     f'result_id.', details={'field': key, 'numbers': found})
        revision = state['revision'] + 1
        superseded = []
        for p in st.open_proposals(state):
            if p['decision_id'] == decision_id:
                p.update(status='superseded', closed_revision=revision,
                         closed_reason='a newer proposal replaced it')
                superseded.append(p['proposal_id'])
        pid = f'p_{len(state["proposals"]) + 1}'
        state['proposals'][pid] = {
            'proposal_id': pid, 'decision_id': decision_id, 'value': copy.deepcopy(value),
            'restatement': params['restatement'], 'rationale': params['rationale'],
            'revision': revision, 'status': 'open', 'created': st.now(),
            'request_id': ctx.request_id, 'basis': basis(state, decision_id)}
        decision = state['decisions'][decision_id]
        if decision['status'] in ('open', 'proposed'):
            decision.update(status='proposed', value=copy.deepcopy(value), proposal_id=pid,
                            revision=revision)
        return {'proposal_id': pid, 'decision_id': decision_id, 'status': 'open',
                'decision_status': decision['status'], 'superseded': superseded,
                'restatement': params['restatement']}
    return Handler(PROPOSE_PARAMS, run, check)


def _confirm(ctx: Context) -> Handler:
    def check(params):
        words = params['user_words']
        reason = reply_problem(words)
        if reason == 'missing_user_words':
            raise _ambiguous('missing_user_words', REPLY_MESSAGES[reason])
        if reason == 'negative_reply':
            raise _ambiguous('negative_reply', REPLY_MESSAGES[reason], user_words=words)
        if reason == 'bare_acknowledgement':
            raise _ambiguous('bare_acknowledgement', REPLY_MESSAGES[reason], user_words=words)
        if params['basis'] not in st.CONFIRMATION_BASES:
            raise _invalid(f'basis is one of {", ".join(st.CONFIRMATION_BASES)}.')
        scope = params['delegation_scope']
        if scope is not None and scope not in st.DELEGATION_SCOPES:
            raise _invalid(f'delegation_scope is one of {", ".join(st.DELEGATION_SCOPES)}.',
                           field='delegation_scope')
        if scope is not None and params['basis'] != st.DELEGATED_DEFAULT:
            raise _invalid('delegation_scope goes with basis delegated_default only.',
                           field='delegation_scope')
        if params['basis'] == st.DELEGATED_DEFAULT and not is_delegation(words):
            raise _ambiguous('not_a_delegation',
                             'These words do not delegate the choice to your recommended default. '
                             'Only an explicit delegation ("use your recommended default") can be '
                             'confirmed with basis delegated_default.', user_words=words)
        if params['basis'] == st.EXPLICIT and is_delegation(words):
            raise _ambiguous('delegation_needs_basis',
                             'These words delegate the choice to the assistant. Restate the '
                             'proposal as your recommended default and confirm it with --basis '
                             'delegated_default, so the study shows it was delegated.',
                             user_words=words)
        if params['channel'] not in st.CHANNELS:
            raise _invalid(f'channel is one of {", ".join(st.CHANNELS)}.')
        if not isinstance(params['actor'], str) or not params['actor'].strip():
            raise _invalid('actor is a non-empty string.')

    def run(state, params):
        pid = params['proposal_id']
        proposal = state['proposals'].get(pid)
        if proposal is None:
            raise _ambiguous('proposal_not_found', f'There is no proposal {pid}; propose first.',
                             proposal_id=pid, open_proposals=[p['proposal_id'] for p in
                                                              st.open_proposals(state)])
        if proposal['status'] != 'open':
            raise _ambiguous(f'proposal_{proposal["status"]}',
                             f'Proposal {pid} is {proposal["status"]}; only an open proposal '
                             f'can be confirmed.', proposal_id=pid,
                             open_proposals=[p['proposal_id'] for p in st.open_proposals(state)])
        if proposal.get('request_id') == ctx.request_id or proposal['revision'] > state['revision']:
            raise _ambiguous('same_request', 'A proposal is confirmed by a later request than the '
                                             'one that created it.', proposal_id=pid)
        if params['basis'] == st.DELEGATED_DEFAULT and not states_default(proposal['restatement']):
            raise _ambiguous('restatement_not_default',
                             f'Proposal {pid} does not say it is the assistant\'s recommended '
                             f'default, so a delegation cannot confirm it. Propose again with a '
                             f'restatement that states the recommended default.',
                             proposal_id=pid, restatement=proposal['restatement'])
        decision_id, value = proposal['decision_id'], proposal['value']
        if params['basis'] == st.DELEGATED_DEFAULT \
                and decision_id not in st.STANDING_DELEGATION_DECISIONS \
                and params['delegation_scope'] != st.THIS_DECISION:
            raise _ambiguous('delegation_not_given_at_this_pause',
                             f'The {decision_id} is decided only with the junior\'s own words, '
                             f'or with a delegation they give at this pause: a standing '
                             f'delegation covers the prediction moment, the feature '
                             f'availability and the split only. Ask the junior to choose, '
                             f'stating your recommended default; if they delegate now, confirm '
                             f'with --delegation-scope this_decision.',
                             proposal_id=pid, decision_id=decision_id,
                             delegation_scope=params['delegation_scope'],
                             standing_covers=list(st.STANDING_DELEGATION_DECISIONS))
        current_basis = basis(state, decision_id)
        if proposal.get('basis', current_basis) != current_basis:
            raise _ambiguous('proposal_stale', f'Proposal {pid} rests on decisions that changed '
                                               f'since it was made; propose again.',
                             proposal_id=pid, basis=proposal.get('basis'),
                             current_basis=current_basis)
        if reply_problem(params['user_words'], value=value, restatement=proposal['restatement'],
                         delegated=params['basis'] == st.DELEGATED_DEFAULT) == 'unrelated_reply':
            raise _ambiguous('unrelated_reply', REPLY_MESSAGES['unrelated_reply'],
                             proposal_id=pid, user_words=params['user_words'],
                             restatement=proposal['restatement'])
        _verify_sources(state)
        validate_value(state, decision_id, value)
        preconditions.require_decision(state, decision_id, value, store=ctx.store)
        decision = state['decisions'][decision_id]
        revision = state['revision'] + 1
        had = decision['status'] in ('confirmed', 'reconfirm_required') \
            and decision['confirmation'] is not None
        old = copy.deepcopy(decision['value']) if had else None
        previous = ({'value': old, 'confirmation': copy.deepcopy(decision['confirmation']),
                     'proposal_id': decision['proposal_id']} if had else None)
        eff = dep.effects(copy.deepcopy(state), decision_id, old, value)
        if had and decision['proposal_id'] in state['proposals'] \
                and decision['proposal_id'] != pid:
            state['proposals'][decision['proposal_id']].update(
                status='superseded', closed_revision=revision,
                closed_reason=f'replaced by {pid}')
        confirmation = st.confirmation(user_words=params['user_words'], proposal=proposal,
                                       channel=params['channel'], actor=params['actor'],
                                       revision=revision, basis=params['basis'],
                                       delegation_scope=params['delegation_scope'])
        proposal.update(status='confirmed', closed_revision=revision, closed_reason='confirmed')
        decision.update(status='confirmed', value=copy.deepcopy(value), proposal_id=pid,
                        confirmation=confirmation, revision=revision, reason=None)
        record = dep.apply_effects(state, eff, revision=revision, decision_id=decision_id,
                                   store=ctx.store, previous=previous)
        return {'decision_id': decision_id, 'proposal_id': pid, 'status': 'confirmed',
                'value': copy.deepcopy(value), 'user_words': params['user_words'],
                'channel': params['channel'], 'actor': params['actor'],
                'invalidation': {k: record[k] for k in ('mutation', 'row', 'reason',
                                                         'stale_results', 'stale_slots',
                                                         'reconfirm_required')},
                'basis': params['basis'], 'delegation_scope': params['delegation_scope']}
    return Handler(CONFIRM_PARAMS, run, check)


def _withdraw(ctx: Context) -> Handler:
    def check(params):
        if params['reason'] is not None and not isinstance(params['reason'], str):
            raise _invalid('reason is a string.')

    def run(state, params):
        pid = params['proposal_id']
        proposal = state['proposals'].get(pid)
        if proposal is None:
            raise CommandRefused('unknown_proposal', f'There is no proposal {pid}.',
                                 details={'proposal_id': pid})
        if proposal['status'] != 'open':
            raise CommandRefused('proposal_not_open', f'Proposal {pid} is {proposal["status"]}.',
                                 details={'proposal_id': pid, 'status': proposal['status']})
        revision = state['revision'] + 1
        proposal.update(status='withdrawn', closed_revision=revision,
                        closed_reason=params['reason'] or 'withdrawn')
        decision = state['decisions'][proposal['decision_id']]
        if decision['status'] == 'proposed' and decision['proposal_id'] == pid:
            decision.update(status='open', value=None, proposal_id=None, revision=revision)
        return {'proposal_id': pid, 'decision_id': proposal['decision_id'], 'status': 'withdrawn',
                'decision_status': decision['status']}
    return Handler(WITHDRAW_PARAMS, run, check)


register_action(ACTION_PROPOSE, _propose)
register_action(ACTION_CONFIRM, _confirm)
register_action(ACTION_WITHDRAW, _withdraw)


# --- commands ---------------------------------------------------------------------------

def _case_file(path) -> Path:
    path = Path(path).resolve()
    return path / c.CASE_FILE if path.is_dir() else path


def _copy_agent_templates(study_dir: Path) -> dict:
    """Install the study agent instructions (plan §5, :mod:`mlkit.study.agent_files`)."""
    from . import agent_files

    return agent_files.install(study_dir)


def init(case_path, study_dir) -> Outcome:
    """Create a study on a case (revision 1). Never overwrites an existing study."""
    guard.assert_writable()
    lock.require_posix()
    study_dir = Path(study_dir).resolve()
    store = StudyStore(study_dir)
    if store.exists():
        raise StudyError('state_exists', 'A study already exists here; it is never overwritten.',
                         details={'study': str(study_dir)})
    case = c.require_supported(c.load_case(_case_file(case_path)))
    index = dt.row_index(case)
    state = st.initial_state(case)
    study_dir.mkdir(parents=True, exist_ok=True)
    store.create(state)
    with lock.writer_lock(study_dir):
        record = exposure.record(store, exposure_id=exposure.new_exposure_id(),
                                 revision=state['revision'], activity='init.structure',
                                 result_id=None, purpose='structural_inspection', partition='all',
                                 row_keys=index.keys, dataset_sha256=index.dataset_sha256,
                                 columns=case.column_names)
    agent = _copy_agent_templates(study_dir)
    ignored = sorted(n for n in IGNORED_CASE_SOURCES if (case.root / n).exists())
    snapshot = read.open(study_dir).state
    return Outcome({'schema': SCHEMAS['init'], 'ok': True, 'study': str(study_dir),
                    'revision': snapshot['revision'], 'case': snapshot['case'],
                    'dataset': snapshot['dataset'],
                    'structural_exposure': {'exposure_id': record['exposure_id'],
                                            'n_rows': record['n_rows']},
                    'plan': st.derive_plan(snapshot), 'next_action': st.next_action(snapshot),
                    'agent_instructions': agent,
                    'ignored_sources': ignored,
                    'note': 'Companion files next to the case are not read: their statuses are '
                            'tutorial choices, not decisions. Every decision starts open.'})


def status(study_dir, since: int | None = None, summary: bool = False) -> Outcome:
    study = read.open(study_dir)
    built = view.build(study)
    if summary:
        return Outcome({'schema': SUMMARY_SCHEMA, 'ok': True, 'study': str(study.study_dir),
                        'revision': study.revision, 'since': since,
                        'changed': None if since is None else study.revision > since,
                        **view.summary(built)})
    payload = {'schema': SCHEMAS['status'], 'ok': True, 'study': str(study.study_dir),
               'revision': study.revision, 'since': since,
               'changed': None if since is None else study.revision > since,
               'changes_since': None if since is None else study.revisions(since),
               'view': built}
    return Outcome(payload)


def plan(study_dir) -> Outcome:
    study = read.open(study_dir)
    state = study.state
    steps = st.derive_plan(state)
    return Outcome({'schema': SCHEMAS['plan'], 'ok': True, 'study': str(study.study_dir),
                    'revision': study.revision, 'steps': steps,
                    'current_step': next((s['id'] for s in steps if s['current']), None),
                    'next_action': st.next_action(state)})


def apply(study_dir, *, action: str, params: dict, request_id: str, expected_revision: int,
          command: str = 'decide') -> Outcome:
    """Apply one registered action through ``apply_command`` and describe the receipt."""
    guard.assert_writable()
    store = StudyStore(study_dir)
    if not store.exists():
        raise StudyError('study_missing', f'No study here: {store.state_path} does not exist.',
                         details={'study': str(store.study_dir)})
    request = {'request_id': request_id, 'expected_revision': expected_revision,
               'action': action, 'params': params}
    receipt = store.execute(request, handlers(Context(store, request_id)))
    payload = {'schema': SCHEMAS['decide'], 'ok': True, 'study': str(store.study_dir),
               'action': action, 'request_id': request_id,
               'replayed': bool(receipt.get('replayed')), 'revision': receipt['revision'],
               'result': receipt['result'], 'artifacts': None}
    code = EXIT_OK
    if not payload['replayed']:
        artifacts = after_commit(store.study_dir, payload)
        if artifacts is not None:
            payload['artifacts'] = artifacts
            if any(a.get('status') in ('stale', 'failed') for a in artifacts.values()):
                code = EXIT_ARTIFACT_STALE
    return Outcome(payload, code)


# Phase 3 extension point: a module that renders artefacts after every committed
# mutation (WP3.4). It defines ``after_commit(study_dir: Path, payload: dict) ->
# {artifact name: {"status": "ok" | "stale" | "failed", ...}}``. A render failure never
# undoes the commit; it makes the command exit with code 3.
AFTER_COMMIT_MODULE = 'mlkit.study.cmd_render'


def after_commit(study_dir: Path, payload: dict) -> dict | None:
    if importlib.util.find_spec(AFTER_COMMIT_MODULE) is None:
        return None
    module = importlib.import_module(AFTER_COMMIT_MODULE)
    hook = getattr(module, 'after_commit', None)
    return hook(Path(study_dir), payload) if hook else None

