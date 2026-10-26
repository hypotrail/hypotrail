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
  ``ambiguous_confirmation``. The words follow the rules of the study's confirmation mode
  (ADR 0005, :mod:`mlkit.study.confirm`: ``guided``, the default; ``training``, a paraphrase
  on the proposal's concepts, :mod:`mlkit.study.concepts`, ``paraphrase_required``; and
  ``express``, a wider standing delegation), and the policy, the model choice and the
  conclusion need a reason (``reason_required``). It checks the three-pause
  preconditions, applies the §3.7 dependency table, and records the invalidation. Its
  request ``basis`` says how the user decided: ``explicit`` (their own reply to the
  restatement, the default; recorded as ``endorsed`` or ``restated``) or
  ``delegated_default`` (they explicitly delegated to the assistant's recommended
  default, which the restatement must state; the decision is then listed in
  ``not_yet_defensible``). ``agent_concern`` records a point the agent raised before the
  junior confirmed (R3); ``feature_availability`` words that contradict the value are
  returned as ``warnings``. A delegation's ``delegation_scope`` is ``this_decision`` (given
  at this pause) or ``standing`` (an earlier "for questions I can't answer, use your
  recommended default"); a standing delegation covers only the prediction moment, the
  feature availability and the split, so the policy and the conclusion are delegated only
  with ``this_decision`` (R1).
* ``decide.withdraw``: closes an open proposal.
* ``decide.note``, ``decide.resolve_note``, ``decide.withdraw_note``: a condition or hold
  the junior states on a decision, verbatim, and its resolution or withdrawal in their
  words (post-v0.1, P2 and D5). A hold on a confirmed decision asks for it again (D1). A
  note of kind ``correction`` (R3) corrects a confirmed decision's reasoning later, without
  asking for it again.
* ``study.set_mode``: the confirmation mode, in the user's words (ADR 0005).

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
from . import companion_env, concepts
from . import confirm as cf
from . import data as dt
from . import dependencies as dep
from . import exposure, governance, guard, lock, partition, preconditions, read, view
from . import records as rec
from . import state as st
from . import trials
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
# Post-v0.1 (P2): a condition or hold the junior states at a pause, and its resolution.
ACTION_NOTE = 'decide.note'
ACTION_RESOLVE_NOTE = 'decide.resolve_note'
# Post-v0.1 fixes (D5): the junior withdraws a hold that no longer applies, in their words.
ACTION_WITHDRAW_NOTE = 'decide.withdraw_note'
# ADR 0005: the confirmation mode of the study, set in the user's words.
ACTION_SET_MODE = 'study.set_mode'
SET_MODE_PARAMS = frozenset({'mode', 'user_words'})
PROPOSE_PARAMS = frozenset({'decision_id', 'value', 'restatement', 'rationale'})
# Parameters an action accepts when present (CLI-CONTRACT-COMPANION §9, C9): a propose
# request carries ``channel`` only when it is not ``chat``, so every request recorded
# before C9 keeps its signature and a replay stays a replay. :func:`apply` widens the
# handler's exact parameter set with the optional ones the request carries.
# ADR 0005 adds ``labels`` (a restatement per language) to a proposal, ``agent_concern`` to a
# confirmation, and ``kind`` (``correction``) to a note, on the same terms.
OPTIONAL_PARAMS = {'decide.propose': frozenset({'channel', 'labels'}),
                   # v0.3 (WP-B): ``adoption_question`` only when true.
                   'decide.confirm': frozenset({'agent_concern', 'adoption_question'}),
                   'decide.note': frozenset({'kind'})}
CONFIRM_PARAMS = frozenset({'proposal_id', 'user_words', 'channel', 'actor', 'basis',
                            'delegation_scope'})
WITHDRAW_PARAMS = frozenset({'proposal_id', 'reason'})
NOTE_PARAMS = frozenset({'decision_id', 'user_words'})
NOTE_KIND_PARAM = 'kind'
RESOLVE_NOTE_PARAMS = frozenset({'note_id', 'user_words'})
WITHDRAW_NOTE_PARAMS = frozenset({'note_id', 'user_words'})
DEFAULT_CHANNEL = 'chat'
DEFAULT_ACTOR = 'user'
DEFAULT_BASIS = st.DEFAULT_BASIS

# Split methods (plan WP2.2; regression, M3). A random split keeps rows apart at random
# (``stratified_random`` keeps the outcome share for a binary target; ``random`` for a
# numeric target); ``ordinal_cutoff`` puts the rows whose integer time column is at least
# ``cutoff`` in validation (later years validated on a model fitted on earlier years).
SPLIT_METHODS = ('stratified_random',)
RANDOM_SPLIT_METHODS = {st.BINARY: 'stratified_random', st.REGRESSION: 'random'}
ORDINAL_CUTOFF = 'ordinal_cutoff'
ALL_SPLIT_METHODS = ('stratified_random', 'random', ORDINAL_CUTOFF)
SPLIT_KEYS = ('method', 'validation_fraction', 'seed')
ORDINAL_SPLIT_KEYS = ('method', 'column', 'cutoff')
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
    merci valide validé go entendu compris understood noted allons allez
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
# A reply that refuses, hesitates or disagrees (review fix H1, narrowed after the
# post-v0.1 acceptance, P1). A negation is a refusal only when it targets the agreement
# itself or the proposal, never when it sits in a caveat after an agreement ("Yes, and it's
# not a forecast", "agreed, never an input"). A reply is negative when:
#
# 1. it refuses the agreement anywhere (``REFUSES_AGREEMENT``: "I don't agree", "pas
#    d'accord", "disagree", "hold on", "don't adopt anything until ...");
# 2. it opens with a refusal (its first word is in ``NEGATIVE_LEADS``, or it opens with
#    "not yet", "pas encore", "not so fast": ``REFUSAL_OPENINGS``), also right after an
#    agreement word ("ok, not yet", "yes no");
# 3. its first clause negates the proposal: without an agreement lead
#    (``AGREEMENT_LEAD``), a negator whose next word does not describe availability, a
#    restart, or an inability to answer ("not before the call", "I'm not sure"), or a
#    word of ``FIRST_CLAUSE_REFUSALS`` ("that's wrong");
# 4. a later clause is a refusal on its own ("ok... no", "yes. No, wait.") or a
#    reservation that opens with "but" or "mais" followed by a negation ("Yes, but not
#    before the first call", "d'accord, mais je ne veux pas de seuil").
#
# After an agreement lead ("yes", "I confirm", "I adopt", "go with your recommendation",
# "je confirme"), a negated description in a later clause is a statement of a limit.
NEGATIVE_LEADS = frozenset("""
    no non nope nah nan wait stop attends attendez cancel annule annuler never jamais hold
""".split())
REFUSAL_OPENINGS = (('not', 'yet'), ('pas', 'encore'), ('not', 'now'), ('pas', 'maintenant'),
                    ('not', 'so', 'fast'), ('not', 'that'), ('pas', 'ca'))
FIRST_CLAUSE_REFUSALS = frozenset('incorrect wrong reject rejected refuse refused faux '
                                  'disagree'.split())
_AGREEMENT_VERBS = r'(?:agree|confirm|accept|adopt|approve|validate|go\s+(?:with|ahead))'
REFUSES_AGREEMENT = re.compile(rf"""
    \bdisagree[sd]?\b | \bdesaccord\b | \bpas\s+d\W?\s*accord\b
  | \bnot\s+so\s+fast\b | \bno\s+way\b | \bhold\s+on\b | \bhang\s+on\b
  | (?:\b(?:i|we)\s+(?:(?:do|does|did|ca|can|could|wo|will|would|really|still)\s+)?
        (?:not|n't|never|cannot)
     | (?:^|[,.;:!?—–-]\s*|\b(?:so|and|but|please|then)\s+)
        (?:do\s+n't|do\s+not|never))
    \s+(?:really\s+|quite\s+|fully\s+|yet\s+)?{_AGREEMENT_VERBS}\b(?!\s+more)
  | \b(?:je|nous|on)\s+n(?:e\s+|')(?:(?:le|la|les)\s+|l')?
        (?:confirm|valid|accept|adopt|approuv|sui[st]\s+pas\s+d)\w*\s+(?:pas|rien|encore)\b
  | \bn(?:e\s+|')(?:confirm|valid|accept|adopt|approuv)\w*\s+(?:rien|pas)\b
  | \b(?:i'?m|i\s+am)\s+(?:not|n't)\s+(?:so\s+|really\s+|quite\s+|entirely\s+)?sure\b
  | \bi'?m\s+unsure\b | \bje\s+ne\s+suis\s+pas\s+(?:tres\s+|vraiment\s+)?sur\b
""", re.IGNORECASE | re.VERBOSE)
# An opening that agrees with the restatement (rule 3 does not apply after it).
AGREEMENT_LEAD = re.compile(r"""
    ^\s*(?:(?:well|so|alors|bon|oh)\W+)?(?:
        yes|yeah|yep|yup|ya|ok|okay|sure|agreed|agree|right|correct|exactly|absolutely
      | definitely|indeed|perfect|fine|great|good|understood|noted|confirmed|approved
      | sounds\s+(?:good|right|fine)|looks\s+(?:good|right|fine)|lgtm
      | oui|ouais|d\W?\s*accord|parfait|exact|exactement|entendu|compris|valide
      | tout\s+a\s+fait|c'?est\s+(?:bon|ca|correct|juste)|ca\s+me\s+va
      | that'?s\s+(?:right|correct|it|fine|good)|that\s+is\s+(?:right|correct)
      | that\s+(?:matches|works)
      | (?:i|we)\s+(?:'ll\s+|will\s+|do\s+|can\s+|also\s+)?
            (?:confirm|agree|adopt|choose|accept|approve|validate|keep|go\s+with|pick|take)
      | (?:i'?m|i\s+am|we'?re|we\s+are)\s+
            (?:agreeing|confirming|adopting|choosing|accepting|fine|ok|okay|good|happy)
      | let'?s\s+(?:go|do|keep|use|adopt|take)|go\s+(?:with|ahead)
      | je\s+(?:confirme|valide|choisis|garde|retiens|suis\s+d\W?\s*accord)
      | j'?(?:adopte|accepte|approuve)|on\s+(?:part|garde|valide|retient|adopte)|va\s+pour
    )\b""", re.IGNORECASE | re.VERBOSE)
CLAUSE_BREAK = re.compile(r"[,.;:!?…—–()]+|\s-\s|\b(but|mais|however|cependant)\b")
RESERVATION_CONJUNCTIONS = frozenset('but mais however cependant'.split())
# Words a reservation may hold before its negation ("but I don't", "mais je ne").
RESERVATION_SKIP = frozenset('i we you je nous on tu vous do does did ne n please'.split())
# Words a clause made only of a refusal may also hold ("no, not yet", "wait a second").
STANDALONE_REFUSAL = frozenset("""
    not n't yet pas encore now maintenant please so fast a minute second sec moment that ca
    actually merci thanks thank you on just
""".split()) | NEGATIVE_LEADS
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
    'run', 'disponib', 'connu', 'conna', 'utilis', 'inclu', 'relanc', 'refai', 'sait', 'savons',
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


def literal_numbers(text: str, value: Any) -> list[str]:
    """Numbers written in ``text`` that do not come from ``value`` (digits glued to letters
    count, review fix L4; identifiers do not). A percentage ("100%", "30 percent") comes
    from a fraction of the value ("30%" for a validation fraction of 0.3), never from
    another number of the value (review fix L3). Reported as written, with ``%`` for a
    percentage. ``decide propose`` traces its texts with :func:`check_proposal_texts`."""
    masked = mask_identifiers(text)
    plain = {round(n, 6) for n in _value_numbers(value)}
    percents = {round(n, 6) for n in _value_numbers(value, percents_only=True)}
    out = set()
    for m in NUMBER.finditer(masked):
        number = round(float(m.group().replace(',', '.')), 6)
        percent = bool(PERCENT_AFTER.match(masked, m.end()))
        if number in (percents if percent else plain):
            continue
        out.add(m.group() + ('%' if percent else ''))
    return sorted(out)


def check_proposal_texts(store: StudyStore, texts, value: Any) -> None:
    """Refuse a proposal whose texts hold a number ``hypotrail check`` would not trace
    (``literal_number_in_text``, ``details.field``, ``details.numbers`` as written,
    ``details.findings``).

    v0.3 (WP-A): one tracer for both commands (:mod:`mlkit.study.numtrace`): the pool of
    ``check --text`` plus the proposed value, so a text ``check`` accepts is accepted here
    (a proposal's texts may repeat its own value, D5, and cite current results, rounded to
    the decimals they show). ``texts`` is ``[(field, text)]``.
    """
    from . import numtrace

    pool = None
    texts = list(texts)
    labels = {key.split('.', 1)[1]: text for key, text in texts if key.startswith('labels.')}
    for key, text in texts:
        if not literal_numbers(text, value) and not _has_number(text):
            continue
        pool = pool or numtrace.study_pool(store.study_dir, proposed=value)
        # Review round 4 (E4-6): a label is read in its language, the restatement in the
        # language a label gives it (``--lang``), any other text in the study language.
        language = (key.split('.', 1)[1] if key.startswith('labels.') else
                    next((lang for lang, label in sorted(labels.items()) if label == text),
                         None))
        findings = numtrace.number_findings(pool, text, key, language=language)
        if findings:
            numbers = sorted({f['details']['number'] for f in findings})
            raise CommandRefused('literal_number_in_text',
                                 f'The {key} contains numbers that are neither part of the '
                                 f'proposed value nor a figure of a current result. Repeat '
                                 f'only registered figures, or cite results by their '
                                 f'result_id.', details={'field': key, 'numbers': numbers,
                                                         'findings': findings})


def _has_number(text: str) -> bool:
    """A number in digits or in words (``check`` traces both), a number in words with a scale
    word included (review round 9, R9E-2: ``check`` reports it)."""
    from . import cite, wordnum
    return bool(cite.parse_numbers(text) or wordnum.parse(text) or wordnum.unread(text))


def check_conclusion(store: StudyStore, state: Mapping, value: Mapping, restatement: str,
                     rationale: str) -> None:
    """Review fix M1: the conclusion text is traced when it is proposed.

    Every number of ``value.text`` must match a current result (or a recorded literal,
    :func:`mlkit.study.numtrace.study_pool`); the proposed value is no whitelist for itself
    (``literal_number_in_text``, ``details.field`` ``value.text``). Causal or forecast
    wording in the text, the restatement, or the rationale is refused
    (``causal_or_forecast_wording``, ``details.findings`` as ``hypotrail check`` reports
    them).
    """
    from . import cmd_check, numtrace

    # v0.3 (WP-A): the pool of ``hypotrail check`` (the conclusion is never a literal of
    # itself), so a text ``check`` accepts is accepted here.
    findings = numtrace.number_findings(numtrace.study_pool(store.study_dir), value['text'],
                                        'value.text')
    numbers = [f['details']['number'] for f in findings]
    if numbers:
        raise CommandRefused('literal_number_in_text',
                             'The conclusion text contains numbers that are not figures of a '
                             'current result. Cite registered figures only.',
                             details={'field': 'value.text', 'numbers': sorted(set(numbers)),
                                      'findings': findings})
    wording = (cmd_check.wording(value['text'], 'value.text')
               + cmd_check.wording(restatement, 'restatement')
               + cmd_check.wording(rationale, 'rationale'))
    credit = (cmd_check.attribution(value['text'], 'value.text')
              + cmd_check.attribution(restatement, 'restatement')
              + cmd_check.attribution(rationale, 'rationale'))
    if credit:
        # P7: a delegated decision is the assistant's recommended default, delegated by the
        # analyst; the conclusion never credits it to the analyst.
        raise CommandRefused('misattributed_delegation',
                             'The conclusion credits a recommended default to the analyst. A '
                             'delegated decision is the assistant\'s recommended default, '
                             'delegated by the analyst; say so.',
                             details={'findings': credit,
                                      'delegated': st.delegated_decisions(state)})
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
        from . import assurance
        assurance.require_prediction_statement(state, value)
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
        from . import assurance, validity
        if assurance.profile(state) == 'review-v1':
            validity.require_availability(case_of(state), value)
    elif decision_id == 'split':
        validate_split(state, value)
    elif decision_id == 'policy':
        if dep.parse_policy(value) is None:
            raise _invalid('policy is "threshold:<t in [0, 1]>", "capacity:<k >= 1>", or '
                           '"share:<p in (0, 1]>"'
                           + (', optionally followed by "@fit.variant" (or "@fit.variant:2", '
                              '"@fit.variant:3") to apply it to a variant'
                              if st.has_wp_b1_decisions(state) else '') + '.')
        if rec.policy_model(value) != rec.POLICY_CANDIDATE \
                and not st.has_wp_b1_decisions(state):
            raise _invalid('This study has no variant: its policy applies to the logistic '
                           'model.', models=[rec.POLICY_CANDIDATE])
        named = trials.declared_slots(state)
        if rec.policy_model(value) in trials.VARIANT_SLOTS[1:] \
                and rec.policy_model(value) not in named:
            # v0.3 (WP-F1): a rule applies to a variant the decision names.
            raise _invalid('The policy names a variant the variant decision does not declare.',
                           models=[rec.POLICY_CANDIDATE] + named)
        if st.has_explicit_binary_model_choice(state):
            selected = state['decisions']['model_choice']
            if selected.get('status') != 'confirmed':
                raise _invalid('Choose the model explicitly before proposing its decision rule.',
                               decision='model_choice')
            if rec.policy_model(value) != selected.get('value'):
                raise _invalid('The decision rule must name the explicitly selected model.',
                               selected_model=selected.get('value'),
                               policy_model=rec.policy_model(value))
        from . import assurance
        if assurance.profile(state) == 'review-v1':
            criterion_value = (state['decisions'].get(st.SUCCESS_CRITERION) or {}).get('value')
            fixed = ((criterion_value or {}).get('selection') or {}).get('rule')
            proposed = rec.policy_rule(value)
            if fixed is not None and rec.canonical_rule(fixed) != proposed:
                raise _invalid('The policy must adopt the rule fixed by the success criterion; '
                               'change that criterion and rerun selection first.',
                               reason='selection_rule_mismatch', expected=fixed,
                               actual=proposed)
    elif decision_id == 'model_choice':
        choices = model_choices(state)
        if value not in choices:
            raise _invalid('model_choice names the model slot you adopt: '
                           + ' or '.join(f'"{m}"' for m in choices) + '.',
                           choices=list(choices))
    elif decision_id == st.MODEL_VARIANT:
        validate_variant(state, value)
    elif decision_id == st.FINAL_TEST:
        if not isinstance(value, Mapping) or set(value) != set(FINAL_TEST_KEYS):
            raise _invalid('final_test is {"model", "rule"}: the configuration the study chose '
                           '(the rule is null in a regression study).',
                           keys=list(FINAL_TEST_KEYS), chosen=st.choice_config(state))
        # B6c (Low): a value that is not the chosen configuration is refused when proposed,
        # not only when confirmed.
        chosen = st.choice_config(state)
        rule = value.get('rule')
        said = {'model': value.get('model'),
                'rule': (rec.canonical_rule(rule) or rule) if isinstance(rule, str) else rule}
        if chosen is not None and said != chosen:
            raise _invalid('The final test opens the configuration the study chose; propose it '
                           'as chosen.', field='final_test', chosen=chosen, value=dict(value))
    elif decision_id == st.SUCCESS_CRITERION:
        try:
            # v0.3 (WP-C, R18): a metric of ``criterion.METRICS_BY_TASK`` and a minimum.
            from . import criterion
            from . import assurance
            if assurance.profile(state) == 'review-v1':
                from . import objective
                objective.validate_criterion(value, st.task_of(state))
                batch = value['selection'].get('batch_column')
                if batch is not None:
                    variable = case_of(state).variables.get(batch)
                    if variable is None or variable.get('role') == 'target':
                        raise ValueError('batch_column must name a non-target case variable')
            else:
                criterion.check(value, st.task_of(state))
        except (governance.ValueProblem, ValueError) as exc:
            if isinstance(exc, ValueError) and not isinstance(exc, governance.ValueProblem):
                raise _invalid(str(exc)) from None
            raise _invalid(exc.message, **exc.details) from None
    elif decision_id == st.PREPROCESSING:
        try:
            governance.check_preprocessing(value, case_of(state))
        except governance.ValueProblem as exc:
            raise _invalid(exc.message, **exc.details) from None
        # B6c (Low): a cap or a transform of a variable the model does not use would be
        # silently ignored; it is refused instead, naming the variables.
        availability = (state['decisions'].get('feature_availability') or {}).get('value')
        if isinstance(availability, Mapping):
            excluded = {f for f, s in availability.items() if s in cf.EXCLUDED_STATUSES}
            for field in ('caps', 'log_transform'):
                named = sorted(set(value.get(field) or []) & excluded)
                if named:
                    raise _invalid(f'{field} names variables the model does not use (excluded '
                                   f'by the availability decision): {", ".join(named)}.',
                                   field=field, excluded=named)
    elif decision_id == 'conclusion':
        verdicts = preconditions.conclusion_verdicts(state)
        if not isinstance(value, Mapping) or set(value) != set(CONCLUSION_KEYS) \
                or value['verdict'] not in verdicts \
                or not isinstance(value['text'], str) or not value['text'].strip():
            raise _invalid('conclusion is {"verdict", "text"}.', verdicts=list(verdicts))


# WP-B1: the opening of the final test names the chosen configuration.
FINAL_TEST_KEYS = ('model', 'rule')
VARIANT_KEYS = {'regularisation': ('kind', 'strength'), 'drop_group': ('kind', 'group')}


def model_choices(state: Mapping) -> tuple[str, ...]:
    """The model slots a regression study may choose: the candidate and the baseline, and
    (WP-B1) the variant (v0.3, WP-F1: every variant the decision names)."""
    if st.has_wp_b1_decisions(state):
        named = tuple(trials.declared_slots(state)) or ('fit.variant',)
        if st.task_of(state) == st.BINARY:
            return (rec.POLICY_CANDIDATE,) + named
        return preconditions.MODEL_CHOICES[:1] + named + preconditions.MODEL_CHOICES[1:]
    return preconditions.MODEL_CHOICES


def variant_groups(case: c.Case) -> dict[str, list[str]]:
    """``{group: [candidate features]}`` of the case's variable groups (WP-B1)."""
    out: dict[str, list[str]] = {}
    for v in case.document['variables']:
        if v['role'] == 'feature' and v.get('group'):
            out.setdefault(v['group'], []).append(v['name'])
    return out


def validate_variant(state: Mapping, value: Any) -> None:
    """Refuse a ``model_variant`` value that does not fit the study (``invalid_value``).

    v0.3 (WP-F1, ADR 0007): ``{"variants": [...]}``, one to three variants each declared with
    its ``question``, of the kinds ``regularisation`` (``strength``), ``drop_group``
    (``group``), ``tuned`` (the penalty by nested cross-validation) and ``family``
    (``family``: ``ebm`` or ``hgb``); a v0.2b value (one variant of the first two kinds, no
    question) is still accepted. The budget counts every distinct variant the study ever
    confirmed: a value that would bring it above three is refused (``budget`` in the
    details), whatever the list holds."""
    groups = variant_groups(case_of(state))
    problem = trials.check_value(value, groups, st.task_of(state))
    if problem is None and not trials.is_list_value(value) \
            and trials.variants_of(value)[0]['kind'] not in VARIANT_KEYS:
        problem = 'A variant of kind tuned or family is declared in a list, with its question.'
    if problem is not None:
        raise _invalid(problem + ' model_variant is {"variants": [{"kind": ..., "question": '
                       '...}, ...]} (at most three).', kinds=list(st.VARIANT_KINDS),
                       strengths=list(st.VARIANT_STRENGTHS), groups=sorted(groups),
                       families=list(trials.VARIANT_FAMILIES), max=trials.MAX_VARIANTS)
    from . import assurance
    if assurance.profile(state) == 'review-v1':
        items = trials.variants_of(value)
        missing_origin = [i + 1 for i, item in enumerate(items)
                          if item.get(trials.ORIGIN_KEY) not in trials.ORIGINS]
        if missing_origin:
            raise _invalid('Every review-v1 variant records origin as planned or '
                           'diagnostic_informed.', variants=missing_origin,
                           origins=list(trials.ORIGINS))
        current_diag = (state.get('current') or {}).get(st.DIAG_SLOT[st.task_of(state)])
        bad_diagnostics = [i + 1 for i, item in enumerate(items)
                           if item.get(trials.ORIGIN_KEY) == 'diagnostic_informed'
                           and (item.get(trials.DIAGNOSTIC_RESULT_KEY) != current_diag
                                or not st.is_current(state, st.DIAG_SLOT[st.task_of(state)]))]
        if bad_diagnostics:
            raise _invalid('A diagnostic-informed variant must cite the current development '
                           'diagnostic.', reason='diagnostic_not_current',
                           variants=bad_diagnostics, current_diagnostic=current_diag)
        required = (((case_of(state).document.get('constraints') or {})
                     .get('interpretability') or {}).get('value') == 'required')
        forbidden = [i + 1 for i, item in enumerate(items)
                     if item.get('kind') == 'family' and item.get('family') == 'hgb']
        if required and forbidden:
            raise _invalid('Histogram gradient boosting is incompatible with the case\'s '
                           'required interpretability constraint.',
                           reason='interpretability_required', variants=forbidden,
                           source=((case_of(state).document.get('constraints') or {})
                                   .get('interpretability') or {}).get('source'))
    used = trials.used_specs(state, value)
    if len(used) > trials.MAX_VARIANTS:
        raise _invalid(f'The trial budget is {trials.MAX_VARIANTS} variants: this value would '
                       f'bring the variants confirmed in this study to {len(used)}. Choose among '
                       f'the variants already compared.',
                       budget={'max': trials.MAX_VARIANTS, 'used': len(trials.used_specs(state)),
                               'would_use': len(used)})


def split_methods(state: Mapping) -> list[str]:
    """The split methods of a study: its random method, and ``ordinal_cutoff`` when the
    case declares an integer time column. A declared time column allows ``ordinal_cutoff``
    only: a random split would mix earlier and later rows (no silent fallback)."""
    from . import assurance
    if assurance.profile(state) == 'review-v1':
        return [st.cv_method(state)]
    time_column = state['structure']['time_column']['value']
    if time_column is not None:
        methods = [ORDINAL_CUTOFF]
    else:
        methods = [RANDOM_SPLIT_METHODS[st.task_of(state)]]
    if st.has_wp_b1_decisions(state):
        # WP-B1: cross-validation on the development rows, the recommended scheme; the
        # single validation split stays available.
        methods = [st.cv_method(state)] + methods
    return methods


def validate_split(state: Mapping, value: Any) -> None:
    """Refuse a split value that does not fit the study (``invalid_value``,
    ``unsupported_capability`` for an unknown method)."""
    allowed = split_methods(state)
    time_column = state['structure']['time_column']['value']
    if not isinstance(value, Mapping) or 'method' not in value:
        raise _invalid('split is {"method", "validation_fraction", "seed"} or '
                       '{"method": "ordinal_cutoff", "column", "cutoff"}.',
                       keys=list(SPLIT_KEYS), ordinal_keys=list(ORDINAL_SPLIT_KEYS),
                       methods=allowed)
    method = value['method']
    if method not in ALL_SPLIT_METHODS + st.CV_METHODS or (
            method in st.CV_METHODS and not st.has_wp_b1_decisions(state)):
        raise CommandRefused('unsupported_capability',
                             f'Split method {method!r} is not available.',
                             details={'methods': allowed})
    if method not in allowed:
        if time_column is not None:
            why = (f'The case declares the time column {time_column!r}: a random split would '
                   f'mix earlier and later rows across partitions. Split by an ordinal cutoff on '
                   f'{time_column!r}.')
        elif method == ORDINAL_CUTOFF:
            why = 'The case declares no time column to cut on.'
        elif method in st.CV_METHODS:
            why = f'The cross-validation of this study is {st.cv_method(state)!r}.'
        elif st.task_of(state) == st.REGRESSION:
            why = 'A numeric target is not stratified: use "random".'
        else:
            why = 'A binary target keeps its outcome share: use "stratified_random".'
        raise _invalid(f'Split method {method!r} does not fit this study. {why}', methods=allowed)
    if method in st.CV_METHODS:
        temporal = method in ('forward_chaining', 'ordered_retrospective')
        keys = st.TEMPORAL_CV_KEYS if temporal else st.CV_KEYS
        if set(value) != set(keys):
            shape = '{"method", "folds", "gap"}' if temporal else \
                '{"method", "folds", "seed"}'
            raise _invalid(f'A cross-validation scheme is {shape}.', keys=list(keys))
        folds = value['folds']
        minimum = 2 if temporal else st.MIN_FOLDS
        if type(folds) is not int or not minimum <= folds <= st.MAX_FOLDS:
            raise _invalid(f'folds is a whole number from {minimum} to {st.MAX_FOLDS}.',
                           field='folds')
        if temporal and (type(value['gap']) not in (int, float) or value['gap'] < 0):
            raise _invalid('gap is a nonnegative number on the ordinal clock.', field='gap')
        if not temporal and type(value['seed']) is not int:
            raise _invalid('seed is an integer.', field='seed')
        return
    if method == ORDINAL_CUTOFF:
        if set(value) != set(ORDINAL_SPLIT_KEYS):
            raise _invalid('An ordinal cutoff split is {"method", "column", "cutoff"}.',
                           keys=list(ORDINAL_SPLIT_KEYS))
        if value['column'] != time_column:
            raise _invalid(f'An ordinal cutoff cuts on the declared time column {time_column!r}.',
                           column=value['column'], time_column=time_column)
        if type(value['cutoff']) is not int:
            raise _invalid('cutoff is an integer value of the time column (rows at or above it '
                           'go to validation).')
        return
    if set(value) != set(SPLIT_KEYS):
        raise _invalid('split is {"method", "validation_fraction", "seed"}.',
                       keys=list(SPLIT_KEYS))
    fraction = value['validation_fraction']
    if isinstance(fraction, bool) or not isinstance(fraction, (int, float)) \
            or not 0 < fraction < 1:
        raise _invalid('validation_fraction is strictly between 0 and 1.')
    if type(value['seed']) is not int:
        raise _invalid('seed is an integer.')


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


def _tokens(text: str) -> list[str]:
    return re.findall(r"n't|[^\W_]+", text)


def _descriptive(after: list[str]) -> bool:
    """The words after a negator describe availability, a restart, or an inability to
    answer ("not available", "don't know", "can't answer")."""
    after = [w for w in after[:3] if w not in NEGATOR_SKIP]
    return bool(after) and after[0].startswith(DESCRIPTIVE_AFTER_NEGATOR)


def _negates(tokens: list[str]) -> bool:
    """A negator in ``tokens`` that is not followed by a descriptive word."""
    return any(t in NEGATORS and not _descriptive(tokens[i + 1:]) for i, t in enumerate(tokens))


def _opens_with_refusal(tokens: list[str]) -> bool:
    return bool(tokens) and (tokens[0] in NEGATIVE_LEADS or any(
        tuple(tokens[:len(o)]) == o for o in REFUSAL_OPENINGS))


def _reservation(tokens: list[str]) -> bool:
    """A clause after "but" / "mais" that negates: "but not before the call", "but no",
    "but I don't want that", "mais je ne veux pas de seuil" (a negated description such as
    "but we don't know it before the call" is a statement)."""
    i = 0
    while i < len(tokens) and tokens[i] in RESERVATION_SKIP and tokens[i] not in ('ne', 'n'):
        i += 1
    if i >= len(tokens):
        return False
    if tokens[i] in NEGATIVE_LEADS:
        return True
    if tokens[i] in NEGATORS:
        return not _descriptive(tokens[i + 1:])
    if tokens[i] in ('ne', 'n'):
        for j in range(i + 2, min(i + 5, len(tokens))):
            if tokens[j] in ('pas', 'jamais', 'plus', 'rien'):
                return not tokens[i + 1].startswith(DESCRIPTIVE_AFTER_NEGATOR)
    return False


def _standalone_refusal(tokens: list[str]) -> bool:
    """A clause made only of a refusal ("no", "not yet", "wait a second")."""
    return bool(tokens) and set(tokens) <= STANDALONE_REFUSAL \
        and any(t in NEGATIVE_LEADS or t in ('not', 'pas') for t in tokens)


def is_negative(words: str) -> bool:
    """True when a reply refuses, hesitates or disagrees ("no", "wait", "I do not agree",
    "pas d'accord", "not yet", "yes, but not before the call").

    A negation is a refusal only when it targets the agreement or the proposal (the rules
    above :data:`NEGATIVE_LEADS`): after an agreement lead, a negated clause states a limit
    ("Yes, and it's not a forecast", "agreed, never an input", "I confirm: its validation
    errors aren't evidence of future error"). A negated availability, restart, or
    inability to answer ("this feature is not available", "don't restart it", "for
    questions I can't answer") is a statement wherever it is.
    """
    folded = _fold(IDENTIFIER.sub(' ', words)).strip()
    spaced = folded.replace("n't", " n't")
    if REFUSES_AGREEMENT.search(spaced):
        return True
    parts = CLAUSE_BREAK.split(spaced)
    clauses: list[tuple[str | None, list[str]]] = []
    first_text = ''
    conjunction = None
    for part in parts:
        if part is None:
            continue
        if part.strip() in RESERVATION_CONJUNCTIONS:
            conjunction = part.strip()
            continue
        tokens = _tokens(part)
        if tokens:
            first_text = first_text or part
            clauses.append((conjunction, tokens))
            conjunction = None
    if not clauses:
        return False
    first = clauses[0][1]
    if _opens_with_refusal(first) or FIRST_CLAUSE_REFUSALS & set(first):
        return True
    lead = AGREEMENT_LEAD.match(spaced)
    if lead:
        # "ok not yet", "yes no wait": a refusal right after the agreement words.
        if _opens_with_refusal(first[len(_tokens(lead.group(0))):]):
            return True
    elif not DELEGATION.search(first_text) and _negates(first):
        return True
    for conj, tokens in clauses[1:]:
        if _standalone_refusal(tokens):
            return True
        if conj is not None and _reservation(tokens):
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


# v0.3 (WP-B, R14/R16): a bare "oui" to a proposal is refused unless it answers the closed
# adoption question; the refusal says how to ask it.
CONFIRM_BARE_MESSAGE = ('A bare acknowledgement is not a decision on its own. Show the '
                        'restatement and ask the one closed question "Do you adopt this '
                        'decision?": in the guided and express modes a short yes to that '
                        'question confirms, sent with --adoption-question (or --channel choice '
                        'for the adoption option of an interactive choice). In the training '
                        'mode the junior says what the proposal decides.')
REPLY_MESSAGES = {
    'missing_user_words': "A confirmation needs the user's own words in reply to the restatement.",
    'negative_reply': 'These words refuse, hesitate, or disagree: nothing is confirmed. Ask what '
                      'the user wants instead and propose again.',
    'bare_acknowledgement': 'A bare acknowledgement is not a decision. Restate the proposal and '
                            'ask the user to answer it in their own words.',
    'unrelated_reply': 'These words share nothing with the proposal (no word or number of its '
                       'value or restatement). Restate the proposal and ask the closed question '
                       '"Do you adopt this decision?" (in the training mode, ask what it '
                       'decides).',
    # ADR 0005 (guided mode).
    'question_reply': 'These words ask a question: nothing is confirmed. Answer it, restate the '
                      'proposal, and ask again.',
    'conditional_reply': 'These words set a condition or hesitate ("yes but", "unless", "oui '
                         'mais"): nothing is confirmed. Ask what the condition is; record it as '
                         'a hold, or propose again.',
    # WP-A9 (B1): a partial refusal is reported as ``conditional_reply``.
    'partial_reply': 'These words accept one part of the proposal and refuse another ("oui pour '
                     'le plafonnement, pas pour le log"): nothing is confirmed. Ask which parts '
                     'the junior wants and propose again with that value.',
}


def standing_covers_default_preprocessing(state: Mapping, decision_id: str, value) -> bool:
    """B6c (integrator decision, ADR 0005): in the guided mode a standing delegation also
    covers the ``preprocessing`` when the proposal is the engine's default (the variables
    kept as they are: no change chosen from the data), so a junior who delegated is not
    paused for it. A preparation that changes anything still needs their words."""
    return decision_id == 'preprocessing' and st.mode_of(state) == st.GUIDED \
        and isinstance(value, Mapping) and governance.is_default(value)


# B6c (M2): the example of a partial refusal is one of the decision refused, never the
# preprocessing example on another decision.
PARTIAL_EXAMPLES = {
    'preprocessing': '"oui pour le plafonnement, pas pour le log"',
    'feature_availability': '"yes, keep them all except contact"',
    'split': '"yes for the folds, not that seed"',
    'model_variant': '"yes for the variant, not the strong regularisation"',
    'final_test': '"yes for the model, not that rule"',
}


def partial_reply_message(decision_id: str, partial: Mapping | None = None) -> str:
    """The refusal message of a partial acceptance of ``decision_id``, naming the refused
    part when known."""
    example = PARTIAL_EXAMPLES.get(decision_id)
    partial = partial or {}
    said = (f' (here "{partial["negator"]} {partial["part"]}")'
            if partial.get('part') and partial.get('negator') else '')
    return ('These words accept one part of the proposal and refuse another'
            + (f', as in {example}' if example else '') + f'{said}: nothing is confirmed. '
            'Ask which parts the junior wants and propose again with that value.')


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
    for d in st.depends_on(state, decision_id):
        dec = state['decisions'][d]
        out[d] = dec['value'] if dec['status'] == 'confirmed' else None
    return out


def check_channel(channel: Any) -> None:
    """C9: a proposal's channel is one of :data:`state.CHANNELS` (``invalid_value``)."""
    if channel not in st.CHANNELS:
        raise _invalid(f'channel is one of {", ".join(st.CHANNELS)}.', field='channel',
                       channels=list(st.CHANNELS))


def check_labels(labels: Any) -> None:
    """ADR 0005: ``labels`` maps a language of :data:`state.LANGUAGES` to a non-empty
    restatement in that language (``invalid_value``, ``details.field`` ``labels``)."""
    if not isinstance(labels, Mapping) or not labels or any(
            k not in st.LANGUAGES or not isinstance(v, str) or not v.strip()
            for k, v in labels.items()):
        raise _invalid(f'labels maps a language ({", ".join(st.LANGUAGES)}) to a non-empty '
                       f'restatement in that language.', field='labels',
                       languages=list(st.LANGUAGES))


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
        if params['decision_id'] not in st.ALL_DECISION_IDS:
            raise CommandRefused('unknown_decision', f'Unknown decision {params["decision_id"]!r}.',
                                 details={'decisions': list(st.FULL_DECISION_IDS)})
        for key in ('restatement', 'rationale'):
            if not isinstance(params[key], str) or not params[key].strip():
                raise _invalid(f'{key} is a non-empty string.', field=key)
        check_channel(params.get('channel', DEFAULT_CHANNEL))
        if 'labels' in params:
            check_labels(params['labels'])

    def run(state, params):
        decision_id, value = params['decision_id'], params['value']
        channel = params.get('channel', DEFAULT_CHANNEL)
        if decision_id not in st.decision_ids(state):
            raise CommandRefused('unknown_decision',
                                 f'Decision {decision_id!r} is not part of a {st.task_of(state)} '
                                 f'study.', details={'decisions': list(st.decision_ids(state)),
                                                     'task': st.task_of(state)})
        _verify_sources(state)                     # L1: never propose on changed bytes

        if decision_id == st.FINAL_TEST and st.final_test_opened(state):
            raise final_test_opened_refusal(state)
        if decision_id == st.MODEL_VARIANT:
            value = normalize_variant_provenance(state, value)
        validate_value(state, decision_id, value)
        if decision_id == 'policy':
            value = rec.canonical_policy(value)      # L2: one spelling per rule
        if decision_id == st.PREPROCESSING:
            # WP-A4: the motivating results are checked, and the engine stamps the value
            # data-contingent when any of them read the target.
            value = _normalized_preprocessing(ctx.store, state, value)
        if decision_id == 'conclusion':
            check_conclusion(ctx.store, state, value, params['restatement'],
                             params['rationale'])
        labels = dict(params.get('labels') or {})
        texts = [('restatement', params['restatement']), ('rationale', params['rationale'])]
        texts += [(f'labels.{lang}', text) for lang, text in sorted(labels.items())]
        check_proposal_texts(ctx.store, texts, value)
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
            'request_id': ctx.request_id, 'basis': basis(state, decision_id),
            # C9: where the proposal came from. The channel changes no rule.
            'origin': {'channel': channel}}
        if labels:
            state['proposals'][pid]['labels'] = labels
        decision = state['decisions'][decision_id]
        if decision['status'] in ('open', 'proposed'):
            decision.update(status='proposed', value=copy.deepcopy(value), proposal_id=pid,
                            revision=revision)
        contingent, why = data_contingency(ctx.store, state, decision_id, value)
        response = {'proposal_id': pid, 'decision_id': decision_id, 'status': 'open',
                'decision_status': decision['status'], 'superseded': superseded,
                'restatement': params['restatement'],
                # v0.3 (WP-A, R32): said before the proposal is presented.
                'data_contingent': contingent, 'data_contingent_reason': why}
        if decision_id == st.MODEL_VARIANT:
            missing = preconditions.missing_for_decision(state, decision_id, value,
                                                          store=ctx.store)
            response.update(adoptable=not missing, missing_prerequisites=missing)
        return response
    return Handler(PROPOSE_PARAMS, run, check)


def normalize_variant_provenance(state: Mapping, value: Any) -> Any:
    """A planned challenger declared after scores is never retroactively predeclared."""
    from . import assurance
    if assurance.profile(state) != 'review-v1' or not trials.is_list_value(value):
        return value
    value = copy.deepcopy(value)
    scored = any(slot.startswith(('fit.', 'policy.', 'evaluate.'))
                 for slot in (state.get('current') or {}))
    if not scored:
        return value
    diag_id = (state.get('current') or {}).get(st.DIAG_SLOT[st.task_of(state)])
    for variant in value[trials.LIST_KEY]:
        if variant.get(trials.ORIGIN_KEY) == 'planned':
            variant[trials.ORIGIN_KEY] = 'diagnostic_informed'
            variant[trials.DIAGNOSTIC_RESULT_KEY] = diag_id
    return value


def final_test_opened_refusal(state: Mapping) -> CommandRefused:
    """WP-B1: the final test is opened once; a second opening is refused."""
    opening = (state.get('partition') or {}).get('opening') or {}
    return CommandRefused('final_test_already_opened',
                          'The final test was already opened; it is opened once. A later '
                          'change is shown as made after the final test, never measured on it '
                          'again.',
                          details={'opening': {k: opening.get(k) for k in
                                               ('revision', 'model', 'rule', 'result_id')}})


def _normalized_preprocessing(store, state: Mapping, value: Mapping) -> dict:
    from . import registry

    def lookup(rid):
        try:
            return registry.get(store, rid)
        except StudyError:
            return None
    target = case_of(state).target_column
    # WP-A9 (M1): every target-involving look before the proposal makes it data-contingent.
    looks = governance.ledger(read.open(store.study_dir).exposure_records(),
                              target)['target_looks']
    try:
        return governance.normalize_preprocessing(value, lookup, target, looks_before=looks)
    except governance.ValueProblem as exc:
        raise _invalid(exc.message, **exc.details) from None


def data_contingency(store, state: Mapping, decision_id: str,
                     value: Any) -> tuple[bool | None, dict | None]:
    """v0.3 (WP-A, R32): ``(data_contingent, data_contingent_reason)`` of a proposal.

    The engine assesses it for the preprocessing (WP-A4, WP-A9 M1): the value it recorded
    says whether a motivating result read the target, or any look at the target came before
    the proposal. The reason names them: ``{target_looks_before, looks_by_activity,
    look_results, motivating_results_reading_target, text}``; None when the value is not
    data-contingent. Any other decision: ``(None, None)`` (not assessed).
    """
    if decision_id == st.MODEL_VARIANT and isinstance(value, Mapping):
        # v0.3 (WP-F1): a model family proposed after the diagnostics of the linear fit
        # flagged a pattern is data-contingent; the other variants are not assessed further.
        from . import registry
        slot = st.DIAG_SLOT[st.task_of(state)]
        rid = state['current'].get(slot)
        diag = None
        if rid is not None:
            try:
                diag = registry.get(store, rid)['output']['values']
            except StudyError:
                diag = None
        return trials.data_contingency(value, diag, rid)
    if decision_id != st.PREPROCESSING or not isinstance(value, Mapping):
        return None, None
    contingent = bool(value.get('data_contingent'))
    if not contingent:
        return False, None
    from . import registry
    target = case_of(state).target_column
    looks = governance.ledger(read.open(store.study_dir).exposure_records(), target)
    motivating = []
    for rid in value.get('motivated_by') or []:
        try:
            if governance.uses_target(registry.get(store, rid), target):
                motivating.append(rid)
        except StudyError:
            continue
    parts = []
    if looks['target_looks']:
        named = ', '.join(f'{a} ({n})' if n > 1 else a
                          for a, n in looks['by_activity'].items())
        parts.append(f'{looks["target_looks"]} look(s) at the target came before this proposal '
                     f'({named})')
    if motivating:
        parts.append(f'{len(motivating)} motivating result(s) read the target')
    text = ('This preprocessing is data-contingent: ' + '; '.join(parts) + '. Say so to the '
            'junior before presenting it: a choice made after looking at the outcome makes '
            'the development figures more optimistic.')
    return True, {'target_looks_before': looks['target_looks'],
                  'looks_by_activity': looks['by_activity'], 'look_results': looks['results'],
                  'motivating_results_reading_target': motivating, 'text': text}


def _confirm(ctx: Context) -> Handler:
    def check(params):
        words = params['user_words']
        # ADR 0005: the reply rules of every mode (the training rules follow in ``run``).
        reason = cf.reply_problem(words)
        # v0.3 (WP-B, R14/R16): a short affirmative that answers the closed adoption
        # question (``--adoption-question``, or the adoption option of ``--channel choice``)
        # is not a bare acknowledgement; ``run`` checks it is a short affirmative.
        if reason == 'bare_acknowledgement' and answers_adoption_question(params):
            reason = None
        if reason == 'missing_user_words':
            raise _ambiguous('missing_user_words', REPLY_MESSAGES[reason])
        if reason == 'negative_reply':
            raise _ambiguous('negative_reply', REPLY_MESSAGES[reason], user_words=words)
        if reason == 'question_reply':
            raise _ambiguous('question_reply', REPLY_MESSAGES[reason], user_words=words)
        if reason == 'conditional_reply':
            raise _ambiguous('conditional_reply', REPLY_MESSAGES[reason], user_words=words)
        if reason == 'bare_acknowledgement':
            raise _ambiguous('bare_acknowledgement', CONFIRM_BARE_MESSAGE, user_words=words)
        concern = params.get('agent_concern')
        if concern is not None and (not isinstance(concern, str) or not concern.strip()):
            raise _invalid('agent_concern is a non-empty string: the point you raised with the '
                           'junior before they confirmed.', field='agent_concern')
        if params['basis'] not in st.REQUEST_BASES:
            raise _invalid(f'basis is one of {", ".join(st.REQUEST_BASES)}.')
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
        if params['channel'] not in st.CONFIRMATION_CHANNELS:
            raise _invalid(f'channel is one of {", ".join(st.CONFIRMATION_CHANNELS)}.')
        if params.get('adoption_question') not in (None, True):
            raise _invalid('adoption_question is true when given.', field='adoption_question')
        if params['channel'] == st.CHOICE_CHANNEL and params['basis'] == st.DELEGATED_DEFAULT:
            raise _invalid('The choice channel records the adoption option the junior picked; '
                           'it is never a delegation.', field='channel')
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
        if proposal['decision_id'] == st.FINAL_TEST:
            decision_id = proposal['decision_id']
            if decision_id == st.FINAL_TEST and st.final_test_opened(state):
                raise final_test_opened_refusal(state)
            if decision_id == st.FINAL_TEST and params['basis'] == st.DELEGATED_DEFAULT:
                # WP-B1: the opening is the junior's own act, never delegated. v0.3 (WP-B,
                # R27): a reason is optional, so the refusal is no longer reason_required.
                raise _ambiguous('delegation_not_allowed',
                                 'The final test is opened only in the junior\'s own words; it '
                                 'cannot be delegated. Ask them whether they adopt the opening.',
                                 decision_id=decision_id, proposal_id=pid,
                                 user_words=params['user_words'], mode=st.mode_of(state))
        if params['basis'] == st.DELEGATED_DEFAULT and not states_default(proposal['restatement']):
            raise _ambiguous('restatement_not_default',
                             f'Proposal {pid} does not say it is the assistant\'s recommended '
                             f'default, so a delegation cannot confirm it. Propose again with a '
                             f'restatement that states the recommended default.',
                             proposal_id=pid, restatement=proposal['restatement'])
        decision_id, value = proposal['decision_id'], proposal['value']
        hold = _hold_refusal(state, decision_id, pid)
        if hold is not None:
            raise hold
        mode = st.mode_of(state)
        standing = st.standing_delegation_decisions(state)
        if params['basis'] == st.DELEGATED_DEFAULT and decision_id not in standing \
                and params['delegation_scope'] != st.THIS_DECISION \
                and not standing_covers_default_preprocessing(state, decision_id, value):
            covers = ('the prediction moment, the feature availability, the split, the success '
                      'criterion and the preprocessing' if mode == st.EXPRESS else
                      'the prediction moment, the feature availability, the split, and the '
                      'preprocessing when it is the engine\'s default'
                      if mode == st.GUIDED else
                      'the prediction moment, the feature availability and the split')
            raise _ambiguous('delegation_not_given_at_this_pause',
                             f'The {decision_id} is decided only with the junior\'s own words, '
                             f'or with a delegation they give at this pause: in the {mode} mode '
                             f'a standing delegation covers {covers} only. Ask the junior to '
                             f'choose, stating your recommended default; if they delegate now, '
                             f'confirm with --delegation-scope this_decision.',
                             proposal_id=pid, decision_id=decision_id,
                             delegation_scope=params['delegation_scope'],
                             standing_covers=list(standing), mode=mode)
        stale = _stale_refusal(state, proposal)
        if stale is not None:
            raise stale
        words = params['user_words']
        others = [p['proposal_id'] for p in st.open_proposals(state)
                  if p['decision_id'] == decision_id and p['proposal_id'] != pid]
        if others:   # never reached while proposing supersedes; kept as the guided invariant
            raise _ambiguous('proposal_superseded', f'Proposal {pid} is not the single open '
                                                    f'proposal of {decision_id}.',
                             proposal_id=pid, open_proposals=others)
        delegated = params['basis'] == st.DELEGATED_DEFAULT
        # WP-A9 (B1): accepting one part of the proposal and refusing another is no
        # confirmation, in every mode ("oui pour le plafonnement, pas de log").
        partial = cf.partial_refusal(words, proposal)
        if partial is not None:
            raise _ambiguous('conditional_reply', partial_reply_message(decision_id, partial),
                             proposal_id=pid, user_words=words, partial=partial)
        warnings = cf.availability_warnings(words, value) \
            if decision_id == 'feature_availability' and not delegated else []
        concern = params.get('agent_concern')
        closed = answers_adoption_question(params)
        reason_given = None
        if delegated:
            basis_recorded = st.DELEGATED_DEFAULT
        elif mode == st.TRAINING:
            # v0.2b (WP-B2): the training rules, concept matching and a stop on a contradiction.
            _check_training(state, proposal, words)
            basis_recorded = st.RESTATED
            reason_given = cf.reason_given(state, proposal, words)
        else:
            # Guided rule (ADR 0005, WP-A9; v0.3 WP-B): an explicit endorsement expression,
            # a reply that agrees and is about the proposal, or a short affirmative to the
            # closed adoption question; "yes, I like pizza" and "oui, la pizza du client est
            # bonne" are never decisions. No decision needs a reason (R27).
            problem = cf.guided_problem(state, proposal, words, closed=closed)
            if problem == 'unrelated_reply':
                raise _ambiguous('unrelated_reply', REPLY_MESSAGES['unrelated_reply'],
                                 proposal_id=pid, user_words=words,
                                 restatement=proposal['restatement'],
                                 channel=params['channel'])
            if warnings and mode == st.GUIDED and concern is None:
                # WP-A9 (H3): in the guided mode the contradiction is the one stop of R3; the
                # agent raises it, and the junior's kept words are recorded with the concern.
                raise _contradiction_refusal(decision_id, pid, words, mode, warnings)
            # R16: an option label is the agent's wording, never a restatement by the junior.
            basis_recorded = st.ENDORSED if params['channel'] == st.CHOICE_CHANNEL \
                else cf.recorded_basis(words, proposal)
            reason_given = cf.reason_given(state, proposal, words)
        # C3: the part of a confirmation that does not depend on the words is one function,
        # shared with ``preview effects``: the refusals left (changed sources, value,
        # preconditions, in that order) and the effects to apply.
        plan = confirmation_plan(state, ctx.store, pid, basis=basis_recorded)
        if plan['refusals']:
            raise plan['refusals'][0]
        # R3 by mode: a recorded warning in express, and in guided once the agent raised it
        # (``--agent-concern``); a contradiction stops a training confirmation before this
        # point. WP-A9 (H3): the warnings are kept on the confirmation record.
        record = _apply_confirmation(state, plan, pid, store=ctx.store,
                                     user_words=words, channel=params['channel'],
                                     actor=params['actor'], basis=basis_recorded,
                                     delegation_scope=params['delegation_scope'],
                                     agent_concern=concern, mode=mode, warnings=warnings,
                                     reason_given=reason_given,
                                     adoption_question=closed and not delegated)
        return {'decision_id': decision_id, 'proposal_id': pid, 'status': 'confirmed',
                'value': copy.deepcopy(value), 'user_words': words,
                'channel': params['channel'], 'actor': params['actor'],
                'invalidation': {k: record[k] for k in INVALIDATION_RESULT_KEYS},
                'basis': basis_recorded, 'delegation_scope': params['delegation_scope'],
                'agent_concern': concern, 'warnings': warnings, 'mode': mode,
                'reason_given': reason_given, 'adoption_question': closed and not delegated}
    return Handler(CONFIRM_PARAMS, run, check)


def answers_adoption_question(params: Mapping) -> bool:
    """v0.3 (WP-B, R14/R16): the words answer the closed adoption question asked right
    after the restatement: ``--adoption-question``, or the adoption option picked through
    ``--channel choice``."""
    return params.get('adoption_question') is True \
        or params.get('channel') == st.CHOICE_CHANNEL


def _check_training(state: Mapping, proposal: Mapping, words: str) -> None:
    """The training rules (ADR 0005, v0.2b): refuse the junior's words unless they restate
    the proposal on its concepts (:mod:`mlkit.study.concepts`).

    In order: a ``feature_availability`` reply whose words contradict the value
    (``words_contradict_value``, a refusal in this mode); a reply with no endorsement, no
    word or number of the proposal and no concept of it (``ambiguous_confirmation``,
    ``unrelated_reply``); a concept left unsaid (``paraphrase_required``, ``details.missing``
    names each one, with a hint for the junior); for the trade-offs, no reason connector
    (``reason_required``)."""
    pid, decision_id, value = proposal['proposal_id'], proposal['decision_id'], proposal['value']
    mode = st.TRAINING
    if decision_id == 'feature_availability':
        found = cf.availability_warnings(words, value)
        if found:
            raise _contradiction_refusal(decision_id, pid, words, mode, found)
    texts = (proposal['restatement'], *(proposal.get('labels') or {}).values())
    result = concepts.check(state, proposal, words)
    if not result['said'] and not cf.is_endorsement(words) \
            and not cf.restates(words, value=value, texts=texts):
        raise _ambiguous('unrelated_reply', REPLY_MESSAGES['unrelated_reply'],
                         proposal_id=pid, user_words=words,
                         restatement=proposal['restatement'])
    if result['missing']:
        hints = '; '.join(m['hint'] for m in result['missing'])
        raise CommandRefused(
            'paraphrase_required',
            f'In the training mode the junior confirms by saying, in their own words, what the '
            f'proposal decides; an endorsement is not enough. Their reply does not say: {hints}. '
            f'Ask them to restate the decision in their own words; do not suggest the words.',
            details={'decision_id': decision_id, 'proposal_id': pid, 'user_words': words,
                     'mode': mode, 'missing': result['missing'], 'said': result['said'],
                     'junior_message': 'In the training mode, your confirmation says in your own '
                                       'words what you decide, not only that you agree. Your '
                                       f'reply does not say yet: {hints}.'})
    if cf.needs_reason(state, decision_id) and not concepts.has_reason_connector(words):
        raise CommandRefused(
            'reason_required',
            f'The {decision_id} is a trade-off: in the training mode the junior also says why, '
            f'with a reason clause ("because ...", "parce que ..."). Ask the junior why it fits '
            f'their situation and confirm with that reply.',
            details={'decision_id': decision_id, 'proposal_id': pid, 'user_words': words,
                     'mode': mode})


def _contradiction_refusal(decision_id: str, pid: str, words: str, mode: str,
                           found: list[dict]) -> CommandRefused:
    """``words_contradict_value`` (R3): a refusal in the training mode, and in the guided
    mode while the agent has not raised the point (``--agent-concern``, WP-A9)."""
    named = ', '.join(w['variable'] for w in found)
    if mode == st.TRAINING:
        lead = ('In the training mode, words that contradict the value stop the confirmation: '
                f'the junior\'s words say the opposite of the proposal for {named}. Tell them '
                'what the value says; they confirm with words that match it, or you propose '
                'again with the value they mean.')
    else:
        lead = (f'The junior\'s words say the opposite of the proposal for {named}. In the '
                f'guided mode this is the one stop: tell them what the value says. They '
                f'reformulate, confirm with new words, or keep their words; to keep them, '
                f'confirm again with --agent-concern stating the point you raised. If the '
                f'value is wrong, propose again with the value they mean.')
    return CommandRefused(
        'words_contradict_value', lead,
        details={'decision_id': decision_id, 'proposal_id': pid, 'user_words': words,
                 'mode': mode, 'warnings': found,
                 'junior_message': f'Your words and the proposal disagree about {named}: '
                                   f'say which one you mean.'})


# The part of an invalidation record a confirmation reports in ``result.invalidation``,
# and that ``preview effects`` predicts (CLI-CONTRACT-COMPANION §3).
INVALIDATION_RESULT_KEYS = ('mutation', 'row', 'reason', 'stale_results', 'stale_slots',
                            'reconfirm_required')


def _hold_refusal(state: Mapping, decision_id: str, pid: str) -> CommandRefused | None:
    holds = st.open_holds(state, decision_id)
    if not holds:
        return None
    return CommandRefused(
        'decision_on_hold',
        f'The junior put the {decision_id} on hold in their own words; it cannot be '
        f'confirmed until their words resolve the hold (decide note --resolve). Tell '
        f'them what is still pending and ask whether the condition is met.',
        details={'decision_id': decision_id, 'proposal_id': pid,
                 'notes': [{'note_id': n['note_id'], 'user_words': n['user_words']}
                           for n in holds]})


def _stale_refusal(state: Mapping, proposal: Mapping) -> CommandRefused | None:
    pid = proposal['proposal_id']
    current_basis = basis(state, proposal['decision_id'])
    if proposal.get('basis', current_basis) == current_basis:
        return None
    return _ambiguous('proposal_stale', f'Proposal {pid} rests on decisions that changed '
                                        f'since it was made; propose again.',
                      proposal_id=pid, basis=proposal.get('basis'), current_basis=current_basis)


def refusal_dict(exc: Exception) -> dict:
    """``{code, reason, message, details}`` of a refusal (``reason`` is ``details.reason``)."""
    details = dict(getattr(exc, 'details', None) or {})
    return {'code': exc.code, 'reason': details.get('reason'), 'message': exc.message,
            'details': details}


def _diagnostic_rule(store, state: Mapping) -> str | None:
    """v0.3 (WP-A, R34): the rule the current binary diagnostics were computed at (their
    registry entry's ``params.rule``), or None when there are none or it cannot be read."""
    from . import registry
    rid = state.get('current', {}).get(dep.DIAG_BINARY_SLOT)
    if rid is None or store is None:
        return None
    try:
        return (registry.get(store, rid).get('params') or {}).get('rule')
    except (StudyError, OSError, ValueError, AttributeError):
        return None


def decision_refusals(state: Mapping, store, decision_id: str, value: Any, *,
                      validate: bool = True) -> tuple[list[Exception], bool]:
    """The refusals of confirming ``decision_id`` with ``value`` that depend on the state
    only and not on any open proposal or words, in the order ``decide confirm`` raises
    them: the final test already opened, an ``invalid_value`` (when ``validate``), then the
    preconditions (``precondition_missing``). Returns ``(refusals, valid)``.

    Review round 6 (area E, R6E-1, R6E-2): ``next_action`` checks a ``propose`` with this
    same function before naming it (:mod:`mlkit.study.feasibility`)."""
    refusals: list[Exception] = []
    if decision_id == st.FINAL_TEST and st.final_test_opened(state):
        refusals.append(final_test_opened_refusal(state))
    valid = True
    if validate:
        try:
            validate_value(state, decision_id, value)
        except (CommandRefused, StudyError) as exc:
            refusals.append(exc)
            valid = False
    if valid:
        try:
            if decision_id == st.FINAL_TEST:
                from . import assurance
                assurance.require_activity(state, 'final_test.evaluation')
            preconditions.require_decision(state, decision_id, value, store=store)
        except (CommandRefused, StudyError) as exc:
            refusals.append(exc)
    return refusals, valid


def confirmation_refusals(state: Mapping, store, proposal_id: str, *,
                          sources: bool = True) -> tuple[list[Exception], bool]:
    """The refusals of ``decide confirm`` on the open proposal ``proposal_id`` that depend on
    the state only, whatever the words, in this order: ``dataset_changed`` (when
    ``sources``), ``final_test_already_opened``, ``decision_on_hold``, ``proposal_stale``,
    ``invalid_value``, ``precondition_missing``. Returns ``(refusals, valid)``, ``valid``
    False when the value is invalid. :func:`confirmation_plan` (so ``decide confirm`` and
    ``preview effects``) and ``next_action`` (review round 6, R6E-1, R6E-2,
    :mod:`mlkit.study.feasibility`) use it, so they cannot drift."""
    proposal = state['proposals'][proposal_id]
    decision_id, value = proposal['decision_id'], proposal['value']
    refusals: list[Exception] = []
    if sources:
        changes = c.source_changes(state)
        if changes:
            refusals.append(c.changed_sources_error(changes))
    rest, valid = decision_refusals(state, store, decision_id, value)
    opened = [e for e in rest if getattr(e, 'code', None) == 'final_test_already_opened']
    refusals += opened
    for found in (_hold_refusal(state, decision_id, proposal_id), _stale_refusal(state, proposal)):
        if found is not None:
            refusals.append(found)
    refusals += [e for e in rest if e not in opened]
    return refusals, valid


def confirmation_plan(state: Mapping, store, proposal_id: str, *,
                      basis: str = DEFAULT_BASIS) -> dict:
    """What confirming the open proposal ``proposal_id`` would do, whatever the words.

    This is the part of ``decide confirm`` that does not depend on the user's words
    (CLI-CONTRACT-COMPANION §3, C3). ``decide confirm`` calls it under the writer lock and
    applies its effects; ``preview effects`` calls it on a state read without the lock
    and discards the result. ``state`` is never mutated: the invalidation is computed by
    applying the effects to a deep copy, with ``store`` used for lineage reads only.
    ``basis`` is the confirmation basis (an explicit confirmation by default): a change of
    basis can outdate a confirmed conclusion.

    The caller has checked that the proposal exists and is open. Returns::

        {'blocked': [refusal dicts], 'refusals': [the refusals, raisable],
         'decision_id', 'value', 'previous', 'effects', 'invalidation',
         'supersedes_proposal'}

    ``blocked`` lists, in this order, the refusals of ``decide confirm`` that depend on
    the state only: ``dataset_changed``, ``decision_on_hold``, ``proposal_stale``,
    ``invalid_value``, ``precondition_missing``. ``previous`` is ``{value, confirmation,
    proposal_id}`` of the confirmation that would be replaced, or None. ``effects`` are
    the dependency-table effects (:func:`dependencies.effects`, with the conclusion rule
    D2), and ``invalidation`` the record :func:`dependencies.apply_effects` returns. Both
    are None when the effects cannot be computed (the value is invalid).
    """
    proposal = state['proposals'][proposal_id]
    decision_id, value = proposal['decision_id'], proposal['value']
    refusals, valid = confirmation_refusals(state, store, proposal_id)
    plan = {'blocked': [refusal_dict(e) for e in refusals], 'refusals': refusals,
            'decision_id': decision_id, 'value': copy.deepcopy(value), 'previous': None,
            'effects': None, 'invalidation': None, 'supersedes_proposal': None}
    decision = state['decisions'][decision_id]
    had = decision['status'] in ('confirmed', 'reconfirm_required') \
        and decision['confirmation'] is not None
    old = copy.deepcopy(decision['value']) if had else None
    if had:
        plan['previous'] = {'value': old, 'confirmation': copy.deepcopy(decision['confirmation']),
                            'proposal_id': decision['proposal_id']}
        if decision['proposal_id'] in state['proposals'] and decision['proposal_id'] != proposal_id:
            plan['supersedes_proposal'] = decision['proposal_id']
    if not valid:
        return plan
    eff = dep.effects_at(copy.deepcopy(state), decision_id, old, value,
                         _diagnostic_rule(store, state) if decision_id == 'policy' else None)
    outdated = dep.outdates_conclusion(
        state, decision_id, was_confirmed=decision['status'] == 'confirmed', old=old,
        new=value, old_basis=st.confirmation_basis(decision['confirmation']) if had else None,
        new_basis=basis)
    if outdated and dep.CONCLUSION not in eff['reconfirm']:
        # D2: the conclusion no longer describes the decisions it summarizes.
        eff['reconfirm'] = list(eff['reconfirm']) + [dep.CONCLUSION]
        eff['re_explain'] = list(dict.fromkeys(list(eff['re_explain']) + [dep.CONCLUSION]))
        if eff['mutation'] in dep.QUIET_MUTATIONS:
            eff['reason'] = outdated
    plan['effects'] = eff
    dry = copy.deepcopy(dict(state))
    plan['invalidation'] = _apply_confirmation(
        dry, plan, proposal_id, store=store, user_words='(preview)', channel=DEFAULT_CHANNEL,
        actor=DEFAULT_ACTOR, basis=basis, delegation_scope=None, time=state['updated'])
    return plan


def _apply_confirmation(state: dict, plan: Mapping, proposal_id: str, *, store, user_words: str,
                        channel: str, actor: str, basis: str, delegation_scope: str | None,
                        time: str | None = None, agent_concern: str | None = None,
                        mode: str | None = None, warnings: list | None = None,
                        reason_given: bool | None = None,
                        adoption_question: bool = False) -> dict:
    """Apply a :func:`confirmation_plan` to ``state`` in memory; the invalidation record."""
    decision_id, value = plan['decision_id'], plan['value']
    proposal = state['proposals'][proposal_id]
    decision = state['decisions'][decision_id]
    revision = state['revision'] + 1
    if plan['supersedes_proposal'] is not None:
        state['proposals'][plan['supersedes_proposal']].update(
            status='superseded', closed_revision=revision,
            closed_reason=f'replaced by {proposal_id}')
    confirmation = st.confirmation(user_words=user_words, proposal=proposal, channel=channel,
                                   actor=actor, revision=revision, time=time, basis=basis,
                                   delegation_scope=delegation_scope,
                                   agent_concern=agent_concern,
                                   mode=mode if mode is not None else st.mode_of(state),
                                   warnings=warnings, reason_given=reason_given,
                                   adoption_question=adoption_question)
    proposal.update(status='confirmed', closed_revision=revision, closed_reason='confirmed')
    decision.update(status='confirmed', value=copy.deepcopy(value), proposal_id=proposal_id,
                    confirmation=confirmation, revision=revision, reason=None)
    return dep.apply_effects(state, copy.deepcopy(plan['effects']), revision=revision,
                             decision_id=decision_id, store=store,
                             previous=copy.deepcopy(plan['previous']))


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


def _note(ctx: Context) -> Handler:
    """``decide.note`` (P2): record a condition or hold the junior stated, verbatim.

    The words are the junior's, about one decision of the study ("don't adopt anything until
    I bring my manager's figure"). A bare acknowledgement says nothing to hold on. The note
    stays open until :func:`_resolve_note` or :func:`_withdraw_note`; while it is open the
    decision cannot be confirmed (``decision_on_hold``). A hold on a decision that is
    already confirmed withdraws that agreement (D1): the decision and every confirmed
    decision resting on it become ``reconfirm_required`` (:func:`dependencies.apply_hold`),
    so the study never shows a decision as both confirmed and on hold."""
    def check(params):
        words = params['user_words']
        kind = params.get(NOTE_KIND_PARAM, st.HOLD)
        if kind not in st.NOTE_KINDS:
            raise _invalid(f'kind is one of {", ".join(st.NOTE_KINDS)}.', field='kind',
                           kinds=list(st.NOTE_KINDS))
        if not isinstance(words, str) or not words.strip():
            raise _invalid("A note holds the junior's own words.", field='user_words')
        if is_bare_acknowledgement(words):
            raise _invalid('These words state no condition: record what the junior asked to '
                           'wait for, verbatim.' if kind == st.HOLD else
                           'These words correct nothing: record the junior\'s corrected '
                           'reasoning, verbatim.', field='user_words', user_words=words)

    def run(state, params):
        decision_id = params['decision_id']
        kind = params.get(NOTE_KIND_PARAM, st.HOLD)
        if decision_id not in st.decision_ids(state):
            raise CommandRefused('unknown_decision',
                                 f'Decision {decision_id!r} is not part of a {st.task_of(state)} '
                                 f'study.', details={'decisions': list(st.decision_ids(state))})
        decision = state['decisions'][decision_id]
        if kind == st.CORRECTION and decision['confirmation'] is None:
            raise _invalid(f'A correction is about a decision already confirmed; the '
                           f'{decision_id} is {decision["status"]}. Before a confirmation, the '
                           f'junior answers the proposal in the words they mean.',
                           field='kind', decision_id=decision_id, status=decision['status'])
        revision = state['revision'] + 1
        notes = state.setdefault('notes', {})
        nid = f'n_{len(notes) + 1}'
        status = 'recorded' if kind == st.CORRECTION else 'open'
        notes[nid] = {'note_id': nid, 'decision_id': decision_id, 'kind': kind,
                      'user_words': params['user_words'], 'status': status, 'created': st.now(),
                      'revision': revision, 'request_id': ctx.request_id, 'resolution': None}
        # R3: a correction changes the recorded reasoning only; it asks for nothing again.
        record = dep.apply_hold(state, decision_id, nid, revision=revision) \
            if kind == st.HOLD else None
        return {'note_id': nid, 'decision_id': decision_id, 'status': status,
                'user_words': params['user_words'],
                'open_holds': [n['note_id'] for n in st.open_holds(state, decision_id)],
                'reconfirm_required': list(record['reconfirm_required']) if record else [],
                'kind': kind}
    return Handler(NOTE_PARAMS, run, check)


def _open_note(state, nid: str, request_id: str) -> dict:
    """The open note ``nid``, or the refusal (``unknown_note``, ``note_not_open``,
    ``same_request``)."""
    note = (state.get('notes') or {}).get(nid)
    if note is None:
        raise CommandRefused('unknown_note', f'There is no note {nid}.',
                             details={'note_id': nid,
                                      'open_holds': [n['note_id'] for n in st.open_holds(state)]})
    if note['status'] != 'open':
        raise CommandRefused('note_not_open', f'Note {nid} is {note["status"]}.',
                             details={'note_id': nid, 'status': note['status']})
    if note.get('request_id') == request_id:
        raise _ambiguous('same_request', 'A hold is resolved or withdrawn by a later request than '
                                         'the one that recorded it.', note_id=nid)
    return note


def _resolve_note(ctx: Context) -> Handler:
    """``decide.resolve_note`` (P2): the junior's own words resolve an open hold.

    Refused like a confirmation (``ambiguous_confirmation``): empty words, a refusal ("not
    yet"), a bare acknowledgement, or words that share nothing with the note, the decision,
    or its open proposal (``unrelated_reply``)."""
    def check(params):
        words = params['user_words']
        reason = reply_problem(words)
        if reason is not None:
            raise _ambiguous(reason, REPLY_MESSAGES[reason], user_words=words)

    def run(state, params):
        nid = params['note_id']
        note = _open_note(state, nid, ctx.request_id)
        proposals = [p for p in st.open_proposals(state) if p['decision_id'] == note['decision_id']]
        texts = (note['user_words'], *(p['restatement'] for p in proposals))
        value = [p['value'] for p in proposals] or None
        if not relates(params['user_words'], value=value, texts=texts,
                       topic=(note['decision_id'],)):
            raise _ambiguous('unrelated_reply', REPLY_MESSAGES['unrelated_reply'],
                             note_id=nid, user_words=params['user_words'],
                             note_words=note['user_words'])
        revision = state['revision'] + 1
        note.update(status='resolved', resolution={'user_words': params['user_words'],
                                                   'revision': revision, 'time': st.now(),
                                                   'request_id': ctx.request_id})
        return {'note_id': nid, 'decision_id': note['decision_id'], 'status': 'resolved',
                'user_words': params['user_words'],
                'open_holds': [n['note_id'] for n in st.open_holds(state, note['decision_id'])]}
    return Handler(RESOLVE_NOTE_PARAMS, run, check)


def _withdraw_note(ctx: Context) -> Handler:
    """``decide.withdraw_note`` (D5): the junior withdraws a hold that no longer applies
    (a restatement of a hold already recorded, a condition they dropped), in their words.

    Unlike a resolution, the words may hold a negation ("no need to wait for that any
    more"): they must be non-blank and say more than an acknowledgement. A withdrawn note
    stops blocking its decision; a decision a hold made ``reconfirm_required`` (D1) still
    needs the junior's words again."""
    def check(params):
        words = params['user_words']
        if not isinstance(words, str) or not words.strip():
            raise _ambiguous('missing_user_words', "A hold is withdrawn with the junior's own "
                                                   'words.')
        if is_bare_acknowledgement(words):
            raise _ambiguous('bare_acknowledgement', 'A bare acknowledgement does not withdraw '
                                                     "a hold: record the junior's words that "
                                                     'drop it.', user_words=words)

    def run(state, params):
        nid = params['note_id']
        note = _open_note(state, nid, ctx.request_id)
        revision = state['revision'] + 1
        note.update(status='withdrawn', resolution={'user_words': params['user_words'],
                                                    'revision': revision, 'time': st.now(),
                                                    'request_id': ctx.request_id})
        return {'note_id': nid, 'decision_id': note['decision_id'], 'status': 'withdrawn',
                'user_words': params['user_words'],
                'open_holds': [n['note_id'] for n in st.open_holds(state, note['decision_id'])]}
    return Handler(WITHDRAW_NOTE_PARAMS, run, check)


def _set_mode(ctx: Context) -> Handler:
    """``study.set_mode`` (ADR 0005): the confirmation mode, in the user's own words.

    ``guided`` (the default), ``training`` and ``express`` (v0.2b). Lowering the strictness
    (training to guided, guided to express, :func:`state.lowers_strictness`) needs the user's
    words, and they must name the mode asked for (``unrelated_reply`` otherwise,
    ``concepts.mode_named``); raising it (express to guided, guided to training) needs no
    words. Words, when given, are never empty, a refusal, a question, a condition, or a bare
    acknowledgement (``ambiguous_confirmation``, as for a confirmation). Keeping the same mode
    needs words too. A change never touches a decision: past confirmations stay valid, each
    with the mode it was recorded in. The change is recorded in ``mode_history``."""
    def check(params):
        mode = params['mode']
        if mode not in st.MODES:
            raise _invalid(f'mode is one of {", ".join(st.MODES)}.', field='mode',
                           modes=list(st.MODES))
        if mode not in st.SUPPORTED_MODES:
            raise CommandRefused('unsupported_capability',
                                 f'The {mode} mode is planned for '
                                 f'{st.MODES_AVAILABLE_IN.get(mode, "a later version")}; this '
                                 f'version supports {", ".join(st.SUPPORTED_MODES)} only.',
                                 details={'mode': mode,
                                          'available_in': st.MODES_AVAILABLE_IN.get(mode),
                                          'supported': list(st.SUPPORTED_MODES)})
        words = params['user_words']
        if words is not None and not isinstance(words, str):
            raise _invalid('user_words is a string.', field='user_words')
        if words is not None and words.strip():
            reason = cf.reply_problem(words)
            if reason is not None:
                raise _ambiguous(reason, REPLY_MESSAGES[reason], user_words=words)

    def run(state, params):
        previous = st.mode_of(state)
        mode, words = params['mode'], params['user_words']
        given = isinstance(words, str) and bool(words.strip())
        if not given and not st.raises_strictness(previous, mode):
            raise _ambiguous('missing_user_words',
                             f'Changing the mode from {previous} to {mode} needs the user\'s '
                             f'own words asking for it: only a change to a stricter mode '
                             f'(express to guided, guided to training) is made without them.',
                             previous=previous, mode=mode)
        if given and st.lowers_strictness(previous, mode) \
                and not concepts.mode_named(mode, words):
            raise _ambiguous('unrelated_reply',
                             f'These words do not ask for the {mode} mode: a less strict mode is '
                             f'set only on the user\'s words that name it. Ask the user which '
                             f'mode they want.', user_words=words, previous=previous, mode=mode)
        revision = state['revision'] + 1
        state['mode'] = mode
        recorded = words if given else None
        state.setdefault('mode_history', []).append(
            {'mode': mode, 'previous': previous, 'user_words': recorded,
             'revision': revision, 'time': st.now(), 'request_id': ctx.request_id})
        return {'mode': mode, 'previous': previous, 'user_words': recorded,
                'changed': previous != mode}
    return Handler(SET_MODE_PARAMS, run, check)


register_action(ACTION_PROPOSE, _propose)
register_action(ACTION_CONFIRM, _confirm)
register_action(ACTION_WITHDRAW, _withdraw)
register_action(ACTION_NOTE, _note)
register_action(ACTION_RESOLVE_NOTE, _resolve_note)
register_action(ACTION_WITHDRAW_NOTE, _withdraw_note)
register_action(ACTION_SET_MODE, _set_mode)


# --- commands ---------------------------------------------------------------------------

def _case_file(path) -> Path:
    path = Path(path).resolve()
    return path / c.CASE_FILE if path.is_dir() else path


def _copy_agent_templates(study_dir: Path, task: str = st.DEFAULT_TASK) -> dict:
    """Install the study agent instructions (plan §5, :mod:`mlkit.study.agent_files`)."""
    from . import agent_files

    return agent_files.install(study_dir, task=task)


def init(case_path, study_dir, language: str = st.DEFAULT_LANGUAGE,
         reliability_profile: str | None = None) -> Outcome:
    """Create a study on a case (revision 1). Never overwrites an existing study.
    ``language`` is the study language (ADR 0005, ``init --lang``)."""
    guard.assert_writable()
    lock.require_posix()
    study_dir = Path(study_dir).resolve()
    store = StudyStore(study_dir)
    if store.exists():
        raise StudyError('state_exists', 'A study already exists here; it is never overwritten.',
                         details={'study': str(study_dir)})
    from . import assurance
    if reliability_profile is not None and reliability_profile not in assurance.PROFILES:
        raise StudyError('invalid_arguments', 'reliability_profile must be legacy or review-v1.')
    # Validate the static contract before reading dataset bytes. A review-v1 scenario whose
    # partition planner is not implemented must be refused without inspecting the source data.
    case = c.require_supported(c.load_case(_case_file(case_path), verify_data=False))
    assurance.require_initialization(case, reliability_profile)
    # L3 (D4 A): the case's translation sidecar is validated before any data byte is read; a
    # committed translation that drifted from its case is refused like an invalid case.
    from . import l10n
    try:
        sidecar = l10n.load(case)
    except l10n.L10nError as exc:
        raise c.CaseError('invalid_case', str(exc), problems=exc.problems) from exc
    c.verify_dataset(case)
    c.prior_exposed_keys(case)
    # ADR 0006: the final test is assigned and sealed before any look. Row keys and
    # duplicates are read on every record (keys only); the stratification reads the
    # target (or the declared order); values that would silently change meaning
    # (``data.check_values``) are then inspected on the development rows only, and the
    # final test gets a counts-only schema check (``partition.schema_check``).
    if language not in st.LANGUAGES:
        raise StudyError('invalid_arguments', f'language is one of {", ".join(st.LANGUAGES)}.')
    index = dt.row_index(case)
    frame = dt.read_frame(case, index)
    assigned = partition.assign(case, index, frame,
                                reliability_profile=reliability_profile or 'legacy')
    check = partition.schema_check(case, frame.loc[assigned['final_test']],
                                   frame.loc[assigned['development']])
    del frame
    try:
        development = dt.load_dataset(case, rows=assigned['development'])
    except c.CaseError as exc:
        raise partition.with_final_test_counts(exc, check)
    partition.refuse_failed_check(case, check)
    state = st.initial_state(case, language=language, reliability_profile=reliability_profile)
    if sidecar is not None:
        state[l10n.STATE_KEY] = {'path': sidecar['path'], 'sha256': sidecar['sha256']}
    study_dir.mkdir(parents=True, exist_ok=True)
    dev_sha = store.put_blob(rec.row_keys_bytes(assigned['development']))
    final_sha = store.put_blob(rec.row_keys_bytes(assigned['final_test']))
    if 'training_excluded' in assigned:
        excluded_sha = store.put_blob(rec.row_keys_bytes(assigned['training_excluded']))
        assigned['record']['training_exclusions']['row_keys'] = excluded_sha
    state[partition.STATE_KEY] = partition.seal(
        assigned['record'], development_sha=dev_sha,
        n_development=len(assigned['development']), final_sha=final_sha,
        n_final=len(assigned['final_test']), check=check, created=state['created'])
    store.create(state)
    with lock.writer_lock(study_dir):
        record = exposure.record(store, exposure_id=exposure.new_exposure_id(),
                                 revision=state['revision'], activity='init.structure',
                                 result_id=None, purpose='structural_inspection',
                                 partition=partition.DEVELOPMENT,
                                 row_keys=development.index.keys,
                                 dataset_sha256=index.dataset_sha256,
                                 columns=case.column_names)
        # J4: the data card deterministically shows these labelled development rows. Record
        # their availability at init; previews remain byte-level read-only afterwards.
        preview_keys = sorted(development.index.keys,
                              key=lambda key: int(str(key)[1:]))[:5]
        exposure.record(store, exposure_id=exposure.new_exposure_id(),
                        revision=state['revision'], activity='init.labelled_preview',
                        result_id=None, purpose='labelled_preview_available',
                        partition=partition.DEVELOPMENT, row_keys=preview_keys,
                        dataset_sha256=index.dataset_sha256, columns=case.column_names)
        exposure.record(store, exposure_id=exposure.new_exposure_id(),
                        revision=state['revision'], activity=partition.ACTIVITY,
                        result_id=None, purpose=partition.EXPOSURE_PURPOSE,
                        partition=partition.FINAL_TEST, row_keys=assigned['final_test'],
                        dataset_sha256=index.dataset_sha256, columns=case.column_names)
    agent = _copy_agent_templates(study_dir, case.task)
    # R7 (v0.2a, WP-A1): the editor's Python for the notebooks, and Marimo's cache ignored.
    from . import audience, launch

    notices = [n for n in (launch.install_settings(study_dir),) if n is not None]
    notices.extend(assurance.initial_notices(case, language))
    launch.install_gitignore(study_dir)
    ignored = sorted(n for n in IGNORED_CASE_SOURCES if (case.root / n).exists())
    snapshot = read.open(study_dir).state
    return Outcome({'schema': SCHEMAS['init'], 'ok': True, 'study': str(study_dir),
                    'revision': snapshot['revision'], 'case': snapshot['case'],
                    'dataset': snapshot['dataset'],
                    'structural_exposure': {'exposure_id': record['exposure_id'],
                                            'n_rows': record['n_rows']},
                    'final_test': partition.final_test_status(snapshot),
                    # L3 (R4, T2): the plan in the study language, as ``status`` gives it.
                    'plan': _localized_plan(snapshot),
                    'next_action': companion_env.annotate(
                        audience.next_action(st.next_action(snapshot), st.language_of(snapshot)),
                        study_dir, st.language_of(snapshot), produced={'command': 'init'}),
                    'agent_instructions': agent,
                    'ignored_sources': ignored,
                    'note': 'Companion files next to the case are not read: their statuses are '
                            'tutorial choices, not decisions. Every decision starts open.',
                    'notices': notices,
                    'deliverables': launch.deliverables(study_dir)})


def _localized_plan(state: Mapping) -> list[dict]:
    """The derived plan with each step's title and question in the study language
    (:func:`mlkit.study.junior.step_text`, the path ``view.build`` takes for ``status``)."""
    from . import junior
    language = st.language_of(state)
    return [{**step, 'title': junior.step_text(step['title'], language),
             'question': junior.step_text(step['question'], language)}
            for step in st.derive_plan(state)]


SUMMARY_FIXED_KEYS = ('schema', 'ok', 'study', 'revision')
# WP-H3: keys of the full view that ``status --summary --fields`` also gives.
FIELDS_FROM_VIEW = ('model_selection', 'model_families', 'assurance', 'requirements',
                    'completion', 'claim_eligibility')


def status(study_dir, since: int | None = None, summary: bool = False,
           digest: bool = False, fields: list[str] | None = None) -> Outcome:
    """``status`` (``hypotrail.status/1``), ``--summary`` (``hypotrail.summary/1``), and
    ``--summary --digest`` (CLI-CONTRACT-COMPANION §1, C1): the summary with ``moments``,
    ``pauses``, ``last_session``, ``digest``, and ``task`` appended, and ``origin`` as the
    last key of each open proposal. Without ``--digest`` the summary is unchanged."""
    # F1: probe execution leases (read-only, no writer lock) *before* reading the state,
    # so a dead execution is reported as ``outcome_unknown``, never as running.
    leases = lock.probe_leases(study_dir)
    study = read.open(study_dir)
    built = view.build(study, leases=leases)
    # R1 (2026-10-26): where the study panel shows this step, only when the panel is on;
    # R1b: a read shows nothing new (``panel.shown``), except the data card at step 0.
    companion_env.annotate(built['next_action'], study.study_dir, built.get('language'),
                           produced={'command': 'status'})
    if summary:
        out = view.summary(built)
        if digest:
            out = view.with_digest(study, built, out, since=since, leases=leases)
        payload = {'schema': SUMMARY_SCHEMA, 'ok': True, 'study': str(study.study_dir),
                   'revision': study.revision, 'since': since,
                   'changed': None if since is None else study.revision > since, **out}
        if fields is not None:
            # v0.3 (WP-J): ``--fields``: only the keys asked for, so an agent reads a short
            # document instead of piping the summary into a script. WP-H3: the full view's
            # ``model_selection`` and ``model_families`` (not in the summary) may be asked
            # for too; round-3 full studies asked for them this way and were refused.
            for key in FIELDS_FROM_VIEW:
                if key in fields and key not in payload:
                    payload[key] = built.get(key)
            unknown = [f for f in fields if f not in payload]
            if unknown or not fields:
                keys = list(payload) + [k for k in FIELDS_FROM_VIEW if k not in payload]
                raise StudyError('invalid_arguments',
                                 f'--fields names keys of the summary: {", ".join(keys)}.',
                                 details={'unknown': unknown, 'keys': keys})
            payload = {**{k: payload[k] for k in SUMMARY_FIXED_KEYS},
                       **{k: payload[k] for k in fields if k not in SUMMARY_FIXED_KEYS}}
        return Outcome(payload)
    payload = {'schema': SCHEMAS['status'], 'ok': True, 'study': str(study.study_dir),
               'revision': study.revision, 'since': since,
               'changed': None if since is None else study.revision > since,
               'changes_since': None if since is None else study.revisions(since),
               'view': built}
    return Outcome(payload)


def plan(study_dir) -> Outcome:
    from . import view

    study = read.open(study_dir)
    state = study.state
    # L3 (R4, T2): the step titles and questions in the study language, as ``status``.
    steps = _localized_plan(state)
    # v0.3 (WP-C): the view's next action, with its junior-ready keys (the same as status).
    return Outcome({'schema': SCHEMAS['plan'], 'ok': True, 'study': str(study.study_dir),
                    'revision': study.revision, 'steps': steps,
                    'current_step': next((s['id'] for s in steps if s['current']), None),
                    'next_action': _with_panel(view.build(study), study.study_dir,
                                               {'command': 'plan'})})


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
    available = handlers(Context(store, request_id))
    optional = OPTIONAL_PARAMS.get(action, frozenset()) & set(params)
    if optional and action in available:
        handler = available[action]
        available[action] = Handler(handler.params | optional, handler.run, handler.check)
    receipt = store.execute(request, available)
    payload = {'schema': SCHEMAS['decide'], 'ok': True, 'study': str(store.study_dir),
               'action': action, 'request_id': request_id,
               'replayed': bool(receipt.get('replayed')), 'revision': receipt['revision'],
               'result': receipt['result'], 'artifacts': None}
    if action == ACTION_CONFIRM:
        opening = _opening(store, payload, request_id)
        result = dict(payload['result'])
        # v0.3 (WP-B): the two new keys come last (additive, after ``opening``); a receipt
        # recorded before v0.3 reads as no reason flag and no adoption question.
        late = {'reason_given': result.pop('reason_given', None),
                'adoption_question': bool(result.pop('adoption_question', False))}
        payload['result'] = {**result, 'opening': opening, **late}
        if opening is not None and not payload['replayed']:
            # v0.3 (WP-A): the opening runs the final evaluation after the confirmation
            # commits; the payload's revision is the study's revision after both, so the
            # next command's --expected-revision is the one this output gives.
            payload['revision'] = max(payload['revision'],
                                      read.open(store.study_dir).state['revision'])
    code = EXIT_OK
    if not payload['replayed']:
        artifacts = after_commit(store.study_dir, payload)
        if artifacts is not None:
            payload['artifacts'] = artifacts
            if any(a.get('status') in ('stale', 'failed') for a in artifacts.values()):
                code = EXIT_ARTIFACT_STALE
    # R1b (2026-10-26): what this write produced, for ``next_action.panel.shown``.
    produced = {'command': 'decide', 'action': action,
                'opening': payload['result'].get('opening')
                if isinstance(payload['result'], dict) else None,
                'kind': params.get(NOTE_KIND_PARAM, st.HOLD)}
    payload['next_action'] = refreshed_next_action(store.study_dir, produced)
    return Outcome(payload, code)


def refreshed_next_action(study_dir, produced: Mapping | None = None) -> dict | None:
    """v0.3 (WP-J): the study's ``next_action`` after a write, as ``status`` gives it (its
    junior-ready keys included), so the agent needs no ``status`` call between a write and
    the next pause. None when the view cannot be built (the write itself stands).
    ``produced`` describes the write (R1b, ``companion_env.shown_section``)."""
    from . import view
    try:
        leases = lock.probe_leases(study_dir)
        return _with_panel(view.build(read.open(study_dir), leases=leases), study_dir,
                           produced)
    except Exception:                     # noqa: BLE001 - a read never undoes a write
        return None


def _with_panel(built: dict, study_dir, produced: Mapping | None = None) -> dict | None:
    """R1 (2026-10-26): the view's ``next_action`` with ``panel`` (where the study panel
    shows this step and, R1b, what the command ``produced``) when the panel is on
    (:mod:`mlkit.study.companion_env`); unchanged otherwise. Added by the command surfaces
    only, never by the view the deliverables are rendered from, so they do not depend on
    the environment."""
    return companion_env.annotate(built['next_action'], study_dir, built.get('language'),
                                  produced=produced)


OPENING_KEYS = ('status', 'execution_id', 'result_id', 'revision', 'error')


def _opening(store: StudyStore, payload: dict, request_id: str) -> dict | None:
    """WP-B1: confirming ``final_test`` opens the final test: the engine runs
    ``final_test.evaluation`` once, right after the confirmation commits (its reservation
    marks the final test opened). ``{status, execution_id, result_id, revision, error}`` of
    that run, None for any other confirmation. A replayed confirmation reports the recorded
    opening and runs nothing."""
    result = payload['result']
    if result.get('decision_id') != st.FINAL_TEST:
        return None
    from . import executions
    if payload['replayed']:
        state = read.open(store.study_dir).state
        opening = (state.get('partition') or {}).get('opening') or {}
        return {'status': 'opened' if opening else 'not_opened',
                'execution_id': opening.get('execution_id'),
                'result_id': opening.get('result_id'), 'revision': state['revision'],
                'error': None}
    # Review round 9 (R9E-5): the opening's own request id is derived at a fixed length (it
    # was ``<request_id>:final_test.evaluation``, over the 200-character limit for a long
    # request id, so the confirmation committed and the opening was refused). Only this first
    # run uses it: a replayed confirmation reads the recorded opening from the state (above),
    # whatever key an earlier engine reserved it under.
    try:
        outcome = executions.run(store.study_dir, 'final_test.evaluation', {},
                                 request_id=executions.derived_request_id(
                                     'final_test.evaluation', request_id),
                                 expected_revision=payload['revision'], render=False)
    except Exception as exc:
        # Refused before its reservation (nothing opened), or failed after it (the final test
        # is opened and consumed: run.fail recorded the failure and the rows it may have read).
        # Review round 2 (A F1): a failure before any final-test row was read (the captured
        # predictor refused when loaded) withdraws the opening, so it reads as refused.
        state = read.open(store.study_dir).state
        opening = (state.get('partition') or {}).get('opening') or {}
        error = (refusal_dict(exc) if isinstance(exc, (CommandRefused, StudyError)) else
                 {'code': 'internal_error', 'reason': None,
                  'message': f'{type(exc).__name__}: {exc}', 'details': {}})
        return {'status': 'failed' if opening else 'refused',
                'execution_id': opening.get('execution_id'), 'result_id': None,
                'revision': state['revision'], 'error': error}
    run = outcome.payload
    return {'status': run['status'], 'execution_id': run['execution_id'],
            'result_id': run['result_id'], 'revision': run['revision'], 'error': None}


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
