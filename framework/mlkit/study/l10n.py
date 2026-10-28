"""One language per study (owner session 2026-10-26, L3, remark R4; decisions D4 A, D4b).

English is the source language. This module gives the junior-facing texts that were English
only a French form, without touching a fingerprinted engine module (plan §2.3) and without
changing a byte of a committed case file (plan §2.2 rule 3):

1. **The case's translations** (D4 option A): a sidecar ``case.l10n.yaml`` next to
   ``case.yaml`` (``hypotrail.case_l10n/1``, CASE-CONTRACT "Translations") gives the French
   form of the case's statements the junior reads: the facts (``facts.<id>.fr``), the row
   unit (``structure.row_unit.fr``), the meaning of each special value
   (``special_values[{column, value}].meaning.fr``), the group of each variable and the
   source of its availability (``variables.<name>.group.fr``,
   ``variables.<name>.availability.source.fr``). ``init`` records its path and sha256 in the
   state (``case_l10n``, :func:`record`); a study reads it only while its bytes match
   (:func:`translations`), so a study never shows a translation it did not record, and a
   study without one (every study created before L3) shows the case's English, unchanged.
   The sidecar is not a source of any result: a changed sidecar makes nothing
   ``sources_changed``.
2. **The engine's EDA sentences** (T7): the question, the note, the warnings and the binning
   of an ``eda.*`` result are stored in English in its registered values
   (``eda.QUESTIONS``, ``eda.question``, ``eda.development_words``). They are translated at
   read time by their English form (:func:`eda_text`), so results computed before L3
   translate too, and ``eda.py`` is not edited.
3. **Both languages for the panel** (D4b): :func:`pair` gives ``{"en", "fr"}``.

Pure: no pandas, numpy or scikit-learn. Not fingerprinted (not in ``activities.MODULES``).
"""
from __future__ import annotations

import copy
import hashlib
import re
from pathlib import Path
from typing import Any, Mapping

import yaml

EN, FR = 'en', 'fr'
LANGUAGES = (EN, FR)
SCHEMA = 'hypotrail.case_l10n/1'
FILE = 'case.l10n.yaml'
STATE_KEY = 'case_l10n'
STATE_KEYS = ('path', 'sha256')
# The languages a sidecar may translate into (English is the case's own language).
TARGET_LANGUAGES = (FR,)
TOP_KEYS = ('schema', 'case')
# ``glossary_examples`` (wave W2 integration): true when the engine glossary's "For example"
# sentences describe this case; the case says so, the engine names no dataset.
TOP_OPTIONAL = ('facts', 'structure', 'special_values', 'variables', 'glossary_examples')
CASE_KEYS = ('id', 'sha256')
STRUCTURE_KEYS = ('row_unit',)
VARIABLE_KEYS = ('group', 'availability')
AVAILABILITY_KEYS = ('source',)
SPECIAL_KEYS = ('column', 'value', 'meaning')


class L10nError(ValueError):
    """An invalid translation sidecar (``invalid_case`` with ``problems``)."""

    def __init__(self, message: str, problems: list[dict]):
        super().__init__(message)
        self.problems = problems


def pair(en: str | None, fr: str | None) -> dict:
    """``{"en": en, "fr": fr}``: one junior text in both languages (D4b)."""
    return {EN: en, FR: fr}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# --- the sidecar --------------------------------------------------------------------------

def sidecar_path(case_path) -> Path:
    """The sidecar next to a case file (or in a case directory)."""
    path = Path(case_path)
    return (path if path.is_dir() else path.parent) / FILE


def _translated(node: Any, path: str, problems: list) -> bool:
    """``{fr: text}``: a mapping of target languages to non-empty texts."""
    if not isinstance(node, dict) or not node:
        problems.append({'path': path, 'problem': 'must map a language to a text'})
        return False
    ok = True
    for lang, text in node.items():
        if lang not in TARGET_LANGUAGES:
            problems.append({'path': f'{path}.{lang}',
                             'problem': f'must be one of {", ".join(TARGET_LANGUAGES)}'})
            ok = False
        elif not isinstance(text, str) or not text.strip():
            problems.append({'path': f'{path}.{lang}', 'problem': 'must be a non-empty string'})
            ok = False
    return ok


def _keys(node: Any, path: str, required, optional, problems: list) -> bool:
    if not isinstance(node, dict):
        problems.append({'path': path, 'problem': 'must be a mapping'})
        return False
    for k in required:
        if k not in node:
            problems.append({'path': f'{path}.{k}' if path else k, 'problem': 'is required'})
    for k in node:
        if k not in tuple(required) + tuple(optional):
            problems.append({'path': f'{path}.{k}' if path else str(k),
                             'problem': 'is not part of the schema'})
    return all(k in node for k in required)


def validate(document: Any, case_document: Mapping, case_sha256: str) -> list[dict]:
    """Every problem of a sidecar ``document`` for the case ``case_document`` whose file has
    ``case_sha256`` (empty when it is valid). Every key names something the case states, and
    the sidecar names the case's id and the sha256 of the exact case file it translates."""
    problems: list[dict] = []
    if not _keys(document, '', TOP_KEYS, TOP_OPTIONAL, problems):
        return problems
    if document['schema'] != SCHEMA:
        problems.append({'path': 'schema', 'problem': f'must be "{SCHEMA}"'})
    if 'glossary_examples' in document and not isinstance(document['glossary_examples'], bool):
        problems.append({'path': 'glossary_examples', 'problem': 'must be true or false'})
    if _keys(document['case'], 'case', CASE_KEYS, (), problems):
        if document['case']['id'] != case_document.get('id'):
            problems.append({'path': 'case.id', 'problem': 'must be the id of the case'})
        if document['case']['sha256'] != case_sha256:
            problems.append({'path': 'case.sha256',
                             'problem': 'must be the sha256 of the case file it translates'})
    facts = {f['id'] for f in case_document.get('facts') or []}
    for fid, node in (document.get('facts') or {}).items():
        if fid not in facts:
            problems.append({'path': f'facts.{fid}', 'problem': 'is not a fact of the case'})
        _translated(node, f'facts.{fid}', problems)
    structure = document.get('structure')
    if structure is not None and _keys(structure, 'structure', (), STRUCTURE_KEYS, problems):
        for k, node in structure.items():
            _translated(node, f'structure.{k}', problems)
    variables = {v['name']: v for v in case_document.get('variables') or []}
    groups: dict[tuple, str] = {}
    for name, node in (document.get('variables') or {}).items():
        path = f'variables.{name}'
        if name not in variables:
            problems.append({'path': path, 'problem': 'is not a variable of the case'})
            continue
        if not _keys(node, path, (), VARIABLE_KEYS, problems):
            continue
        if 'group' in node:
            english = variables[name].get('group')
            if not english:
                problems.append({'path': f'{path}.group', 'problem': 'the case gives no group'})
            elif _translated(node['group'], f'{path}.group', problems):
                for lang, text in node['group'].items():
                    seen = groups.setdefault((english, lang), text)
                    if seen != text:
                        problems.append({'path': f'{path}.group.{lang}',
                                         'problem': f'translates the group "{english}" '
                                                    f'differently from another variable'})
        if 'availability' in node and _keys(node['availability'], f'{path}.availability', (),
                                            AVAILABILITY_KEYS, problems):
            for k, text in node['availability'].items():
                _translated(text, f'{path}.availability.{k}', problems)
    specials = {(str(s['column']), str(s['value'])) for s in case_document.get('special_values')
                or []}
    for v in case_document.get('variables') or []:
        specials |= {(v['name'], str(s['value'])) for s in v.get('special_values') or []}
    seen_specials = set()
    for i, node in enumerate(document.get('special_values') or []):
        path = f'special_values[{i}]'
        if not _keys(node, path, SPECIAL_KEYS, (), problems):
            continue
        key = (str(node['column']), str(node['value']))
        if key not in specials:
            problems.append({'path': path, 'problem': 'is not a special value of the case'})
        if key in seen_specials:
            problems.append({'path': path, 'problem': 'translates a special value twice'})
        seen_specials.add(key)
        _translated(node['meaning'], f'{path}.meaning', problems)
    return problems


def load(case, *, required: bool = False) -> dict | None:
    """The validated sidecar of ``case`` (a :class:`mlkit.study.case.Case`) as
    ``{"path", "sha256", "document"}``, or None when the case has none. A sidecar written
    for other bytes of the case file (its ``case.sha256`` differs: the case was edited and
    the translation not regenerated) is not used, so the study shows the case's own words;
    with ``required`` it is refused. Any other invalid sidecar is refused
    (:class:`L10nError`): a translation never silently drifts from its case."""
    from .case import sha256_file
    path = sidecar_path(case.path)
    if not path.is_file():
        if required:
            raise L10nError(f'No {FILE} next to the case.', [{'path': str(path),
                                                               'problem': 'is missing'}])
        return None
    data = path.read_bytes()
    try:
        document = yaml.safe_load(data.decode('utf-8'))
    except (UnicodeDecodeError, yaml.YAMLError) as exc:
        raise L10nError(f'{FILE} is not valid YAML: {exc}', [{'path': str(path),
                                                              'problem': str(exc)}]) from exc
    case_sha = sha256_file(case.path)
    written_for = (document.get('case') or {}).get('sha256') \
        if isinstance(document, dict) and isinstance(document.get('case'), dict) else None
    if not required and isinstance(written_for, str) and written_for != case_sha:
        return None
    problems = validate(document, case.document, case_sha)
    if problems:
        raise L10nError(f'{FILE} does not follow {SCHEMA}', problems)
    return {'path': str(path.resolve()), 'sha256': sha256_bytes(data), 'document': document}


def record(state: dict, case) -> dict | None:
    """``init``: the sidecar of ``case`` recorded in a new study's ``state`` (its path and
    sha256 under ``case_l10n``), or None when the case has none (the key is then absent)."""
    loaded = load(case)
    if loaded is None:
        return None
    state[STATE_KEY] = {'path': loaded['path'], 'sha256': loaded['sha256']}
    return state[STATE_KEY]


def state_problems(state: Mapping) -> list[dict]:
    """Schema problems of ``state['case_l10n']`` (validate_state)."""
    node = state.get(STATE_KEY)
    problems: list[dict] = []
    if _keys(node, STATE_KEY, STATE_KEYS, (), problems):
        for k in STATE_KEYS:
            if not isinstance(node[k], str) or not node[k]:
                problems.append({'path': f'{STATE_KEY}.{k}', 'problem': 'must be a string'})
    return problems


class Translations:
    """The recorded sidecar of a study, read while its bytes match (or nothing)."""

    def __init__(self, document: Mapping | None, case_document=None):
        doc = document or {}
        # The case document (or a function that reads it), read only to name the groups.
        self._case_document = case_document
        self.facts = {k: dict(v) for k, v in (doc.get('facts') or {}).items()}
        self.glossary_examples = doc.get('glossary_examples') is True
        self.structure = {k: dict(v) for k, v in (doc.get('structure') or {}).items()}
        self.variables = copy.deepcopy(doc.get('variables') or {})
        self.specials = {(str(s['column']), str(s['value'])): dict(s['meaning'])
                         for s in doc.get('special_values') or []}
        self.groups: dict[str, dict] = {}
        self._group_names: dict[str, str] = {}

    def __bool__(self) -> bool:
        return bool(self.facts or self.structure or self.variables or self.specials)

    def bind_groups(self, case_document: Mapping) -> 'Translations':
        """Index the group translations by the case's English group name."""
        for v in case_document.get('variables') or []:
            group = (self.variables.get(v['name']) or {}).get('group')
            if v.get('group') and group:
                self.groups.setdefault(v['group'], dict(group))
        return self

    def fact(self, fact_id: str, lang: str) -> str | None:
        return (self.facts.get(fact_id) or {}).get(lang)

    def row_unit(self, lang: str) -> str | None:
        return (self.structure.get('row_unit') or {}).get(lang)

    def group(self, english: str | None, lang: str) -> str | None:
        if not english or not self.variables:
            return None
        if not self.groups and self._case_document is not None:
            document = self._case_document
            self._case_document = None
            self.bind_groups(document() if callable(document) else document)
        return (self.groups.get(english) or {}).get(lang)

    def availability_source(self, name: str, lang: str) -> str | None:
        node = ((self.variables.get(name) or {}).get('availability') or {}).get('source')
        return (node or {}).get(lang)

    def meaning(self, column: str, value: Any, lang: str) -> str | None:
        return (self.specials.get((str(column), str(value))) or {}).get(lang)


EMPTY = Translations(None)


_PARSED: dict[str, dict] = {}


def _parsed(path: str, sha: str) -> dict | None:
    """The sidecar at ``path`` when its bytes have the recorded ``sha`` (read every time: a
    small file; parsed once per content)."""
    try:
        data = Path(path).read_bytes()
    except OSError:
        return None
    if sha256_bytes(data) != sha:
        return None
    if sha not in _PARSED:
        _PARSED[sha] = yaml.safe_load(data.decode('utf-8'))
    return _PARSED[sha]


def translations(state: Mapping | None, case_document: Mapping | None = None) -> Translations:
    """The translations ``init`` recorded for this study, while the sidecar's bytes match
    its recorded sha256; :data:`EMPTY` otherwise (a study created before L3, a case without
    a sidecar, or a sidecar changed or removed since ``init``)."""
    node = (state or {}).get(STATE_KEY) if isinstance(state, Mapping) else None
    if not isinstance(node, Mapping) or not node.get('path') or not node.get('sha256'):
        return EMPTY
    document = _parsed(str(node['path']), str(node['sha256']))
    if not document:
        return EMPTY
    if case_document is None:
        def case_document():
            from . import case as c
            try:
                return c.case_of(state).document
            except Exception:                          # noqa: BLE001 - groups shown in English
                return {}
    return Translations(document, case_document)


def case_texts(state: Mapping | None, case_document: Mapping | None = None) -> dict | None:
    """``view.case_texts`` (L3, D4 A, D4b): the case's statements a surface shows the junior,
    each in both languages (``{en, fr}``), by where they are: ``facts`` (by fact id),
    ``special_values`` (``"column=value"``), ``groups`` (by the case's English group name),
    ``availability`` (the availability source, by variable) and ``row_unit``; only the
    statements the recorded sidecar translates; and ``glossary_examples``, whether the
    glossary's own examples describe this case. None when the study has no current sidecar."""
    tr = translations(state, case_document)
    if not tr:
        return None
    if case_document is None:
        from . import case as c
        try:
            case_document = c.case_of(state).document
        except Exception:                              # noqa: BLE001
            return None
    out: dict[str, Any] = {'facts': {}, 'special_values': {}, 'groups': {}, 'availability': {},
                           'row_unit': None, 'glossary_examples': tr.glossary_examples}
    for f in case_document.get('facts') or []:
        french = tr.fact(f['id'], FR)
        if french:
            out['facts'][f['id']] = pair(f['value'], french)
    for v in case_document.get('variables') or []:
        group = tr.group(v.get('group'), FR)
        if group:
            out['groups'][v['group']] = pair(v['group'], group)
        source = tr.availability_source(v['name'], FR)
        if source:
            out['availability'][v['name']] = pair((v.get('availability') or {}).get('source'),
                                                  source)
        for sv in v.get('special_values') or []:
            meaning = tr.meaning(v['name'], sv['value'], FR)
            if meaning:
                out['special_values'][f'{v["name"]}={sv["value"]}'] = pair(sv['meaning'], meaning)
    unit = tr.row_unit(FR)
    if unit:
        out['row_unit'] = pair(((case_document.get('structure') or {}).get('row_unit') or {})
                               .get('value'), unit)
    return out


def status(state: Mapping | None) -> str:
    """``none`` (no sidecar recorded), ``current`` (its bytes match), or ``changed`` (changed
    or removed since ``init``: the study shows the case's English)."""
    node = (state or {}).get(STATE_KEY) if isinstance(state, Mapping) else None
    if not isinstance(node, Mapping):
        return 'none'
    return 'current' if _parsed(str(node.get('path')), str(node.get('sha256'))) else 'changed'


# --- the engine's EDA sentences in French (T7) -------------------------------------------

# How the stored sentences name their rows (``eda.development_words`` turns "training rows"
# into "development rows" under cross-validation).
_ROWS = r'(?P<rows>training|development)'
_ROWS_FR = {'training': "lignes d'entraînement",
            'development': "lignes de l'échantillon de développement"}
_THE_ROWS_FR = {'training': "les lignes d'entraînement",
                'development': "les lignes de l'échantillon de développement"}
_OF_ROWS_FR = {'training': "des lignes d'entraînement",
               'development': "des lignes de l'échantillon de développement"}
_OTHER_GROUP = "'(other values)'"


def _num(text: str) -> str:
    """A number of an engine sentence in French notation (decimal comma)."""
    return text.replace('.', ',')


# ``(regex, french)``: the regex matches a whole English sentence of ``eda`` or
# ``correlation``; ``french`` is a format string over its named groups (``R``, ``theR``,
# ``ofR``: the rows in French), or a function of the match.
_EDA_FR: list[tuple[re.Pattern, Any]] = [(re.compile(p), f) for p, f in [
    # questions (eda.QUESTIONS, eda.REGRESSION_QUESTIONS, eda.question, correlation.QUESTION)
    (rf'How often is the outcome positive among the {_ROWS} rows\?',
     'À quelle fréquence le résultat est-il positif parmi {theR} ?'),
    (rf'How is the target distributed among the {_ROWS} rows\?',
     'Comment la cible se répartit-elle parmi {theR} ?'),
    (rf'How many {_ROWS} rows carry each special value, and how does the outcome look among '
     rf'them\?',
     'Combien {ofR} portent chaque valeur spéciale, et à quoi ressemble le résultat parmi '
     'elles ?'),
    (rf'How many {_ROWS} rows carry each special value, and how does the target look among '
     rf'them\?',
     'Combien {ofR} portent chaque valeur spéciale, et à quoi ressemble la cible parmi '
     'elles ?'),
    (r'Are there missing cells, repeated rows, rare categories, or values outside their '
     r'possible range in the development rows\?',
     "Y a-t-il des cellules manquantes, des lignes répétées, des catégories rares ou des "
     "valeurs hors de leur plage possible dans les lignes de l'échantillon de "
     "développement ?"),
    (r'Does any single feature, on its own, predict the outcome so well that its availability '
     r'at the prediction moment should be questioned\?',
     'Une variable, à elle seule, prédit-elle le résultat si bien que sa disponibilité au '
     'moment de la prédiction doit être mise en question ?'),
    (r'Does any single feature, on its own, predict the target so well that its availability '
     r'at the prediction moment should be questioned\?',
     'Une variable, à elle seule, prédit-elle la cible si bien que sa disponibilité au '
     'moment de la prédiction doit être mise en question ?'),
    (r'Does the positive rate differ across the groups of (?P<column>.+) by more than chance '
     r'alone draws\?',
     'Le taux de résultat diffère-t-il entre les groupes de {column} plus que le hasard seul '
     'ne le produit ?'),
    (r'Does the mean target differ across the groups of (?P<column>.+) by more than chance '
     r'alone draws\?',
     'La moyenne de la cible diffère-t-elle entre les groupes de {column} plus que le hasard '
     'seul ne le produit ?'),
    (rf'How are the values of (?P<column>.+) distributed among the {_ROWS} rows\?',
     'Comment les valeurs de {column} se répartissent-elles parmi {theR} ?'),
    (r'Do any two predictors carry nearly the same information in the development rows, so '
     r'that a model would split its weight between them\?',
     "Deux prédicteurs portent-ils presque la même information dans les lignes de "
     "l'échantillon de développement, au point qu'un modèle partagerait son poids entre "
     "eux ?"),
    # the questions of the model diagnostics (``diagnostics.QUESTIONS``)
    (r'Where does the model err at the rule, and can its score be read as a probability\?',
     'Où le modèle se trompe-t-il avec la règle, et son score peut-il être lu comme une '
     'probabilité ?'),
    (r'Where are the predictions off, by how much, and does the error grow with the '
     r'prediction or differ across groups\?',
     "Où les prédictions s'écartent-elles, de combien, et l'erreur grandit-elle avec la "
     "prédiction ou diffère-t-elle selon les groupes ?"),
    (r'On rows nothing had seen, where does the chosen model err at the rule, and do its '
     r'scores match the observed rates\?',
     "Sur des lignes que rien n'avait vues, où le modèle choisi se trompe-t-il avec la règle, "
     "et ses scores correspondent-ils aux taux observés ?"),
    (r"On rows nothing had seen, where are the chosen model's predictions off, and does the "
     r"error grow with the prediction\?",
     "Sur des lignes que rien n'avait vues, où les prédictions du modèle choisi "
     "s'écartent-elles, et l'erreur grandit-elle avec la prédiction ?"),
    # notes
    (rf'Counts of {_ROWS} rows only\. A distribution describes this sample; it is not a rate '
     rf'of the outcome and says nothing about causes\.',
     'Effectifs {ofR} seulement. Une distribution décrit cet échantillon ; ce n\'est pas un '
     'taux du résultat et elle ne dit rien des causes.'),
    (rf'Distribution of the target on {_ROWS} rows, in its unit\. The mean is what the '
     rf'baseline predicts for every row\.',
     'Distribution de la cible sur {theR}, dans son unité. La moyenne est ce que le modèle '
     'de référence prédit pour chaque ligne.'),
    (rf'Counts on {_ROWS} rows\. Special values that always occur together describe one fact '
     rf'twice\.',
     'Effectifs sur {theR}. Des valeurs spéciales toujours présentes ensemble décrivent deux '
     'fois le même fait.'),
    (rf'Counts on {_ROWS} rows\. A missing-value marker is imputed by the model, with an '
     rf'indicator column for a numeric variable\.',
     'Effectifs sur {theR}. Un marqueur de valeur manquante est imputé par le modèle, avec '
     'une colonne indicatrice pour une variable numérique.'),
    (rf'Rates by group on {_ROWS} rows are associations, not effects of the variable\.',
     'Les taux par groupe sur {theR} sont des associations, pas des effets de la variable.'),
    (rf'Mean target by group on {_ROWS} rows: associations, not effects of the variable\.',
     'Moyenne de la cible par groupe sur {theR} : des associations, pas des effets de la '
     'variable.'),
    (rf'The band is the range of the same figure after shuffling the target among the {_ROWS} '
     rf'rows (?P<n>\d+) times \(fixed seed\): what chance alone draws\. A pattern inside it is '
     rf'not distinguishable from chance; one above every shuffle happens by chance about once '
     rf'in (?P<m>\d+) looks\.',
     'La bande est l\'étendue du même chiffre après avoir mélangé la cible entre {theR} '
     '{n} fois (graine fixe) : ce que le hasard seul produit. Un motif à l\'intérieur ne se '
     'distingue pas du hasard ; un motif au-dessus de chaque mélange arrive par hasard environ '
     'une fois sur {m} regards.'),
    (r'Structural reading of the development rows: the target is not read, and nothing here '
     r'is a rate or an association\. A range is checked only against a range the case '
     r'declares\.',
     "Lecture structurelle des lignes de l'échantillon de développement : la cible n'est pas "
     "lue, et rien ici n'est un taux ni une association. Une plage n'est vérifiée que par "
     "rapport à une plage que le cas déclare."),
    (rf'Each feature alone, scored out of fold on the {_ROWS} rows\. A high value only raises '
     rf'a question about when the value is known; it never keeps or drops a feature, and a '
     rf'legitimate feature may score high\.',
     'Chaque variable seule, notée hors pli sur {theR}. Une valeur élevée pose seulement une '
     'question sur le moment où la valeur est connue ; elle ne garde ni n\'écarte jamais une '
     'variable, et une variable légitime peut obtenir une valeur élevée.'),
    (r'Structural reading of the development rows: the target is not read, so this is not a '
     r'look at the outcome\. An association between two predictors is not an effect on the '
     r'outcome; a flagged pair only asks whether both are needed\.',
     "Lecture structurelle des lignes de l'échantillon de développement : la cible n'est pas "
     "lue, ce n'est donc pas un regard sur le résultat. Une association entre deux "
     "prédicteurs n'est pas un effet sur le résultat ; une paire signalée demande seulement "
     "si les deux sont nécessaires."),
    (r'unrestricted label shuffling is unsupported for the declared dependence structure',
     'le mélange libre des étiquettes n\'est pas valable pour la structure de dépendance '
     'déclarée'),
    # warnings
    (rf'(?P<column>.+) = (?P<label>.+): only (?P<n>\d+) {_ROWS} rows; its rate is too noisy to '
     rf'read on its own\.',
     '{column} = {label} : seulement {n} {R} ; son taux est trop bruité pour être lu seul.'),
    (rf'(?P<column>.+) = (?P<label>.+): only (?P<n>\d+) {_ROWS} rows; its mean is too noisy to '
     rf'read on its own\.',
     '{column} = {label} : seulement {n} {R} ; sa moyenne est trop bruitée pour être lue '
     'seule.'),
    (rf'(?P<column>.+) has (?P<k>\d+) values: the (?P<m>\d+) largest groups are shown and the '
     rf'other (?P<j>\d+) values are grouped as {re.escape(_OTHER_GROUP)} \((?P<n>\d+) {_ROWS} '
     rf'rows\)\.',
     '{column} a {k} valeurs : les {m} plus grands groupes sont montrés et les {j} autres '
     'valeurs sont regroupées sous \'(other values)\' ({n} {R}).'),
    # binning (eda.binning_words; "training" or "development")
    (rf'(?P<n>\d+) {_ROWS} quantile bins \((?P<q>\d+) asked; tied values merged the others\)',
     '{n} classes de quantiles {binR} ({q} demandées ; des valeurs égales ont fusionné les '
     'autres)'),
    (rf'(?P<n>\d+) {_ROWS} quantile bins',
     '{n} classes de quantiles {binR}'),
]]
_BIN_FR = {'training': "du jeu d'entraînement",
           'development': "de l'échantillon de développement"}

# The single-feature signal's question about one feature (``eda.single_feature_signal``).
_SIGNAL = re.compile(
    rf'(?P<feature>\S+) (?:ranks the {_ROWS} rows with an out-of-fold AUC of (?P<auc>[\d.]+)'
    r'|explains (?P<r2>[\d.]+) of the variance of the target out of fold \(R²\))'
    r' on its own(?:, far above the other features \(median (?P<median>[\d.]+)\))?\. '
    r'Is its value really known at the prediction moment, or is it recorded at or after the '
    r'(?P<what>outcome|target)\? \(availability decided: (?P<status>[^)]+)\)')
_STATUS_FR = {'available_at_prediction': 'disponible au moment de la prédiction',
              'not_available': 'non disponible', 'uncertain_excluded': 'incertaine, exclue',
              'uncertain_included': 'incertaine, incluse',
              'no availability decision': 'aucune décision de disponibilité'}


def _signal_fr(m: re.Match) -> str:
    rows = m.group('rows')
    if m.group('auc'):
        what = (f"classe {_THE_ROWS_FR[rows or 'training']} avec une AUC hors pli de "
                f"{_num(m.group('auc'))}")
    else:
        what = f"explique {_num(m.group('r2'))} de la variance de la cible hors pli (R²)"
    far = (f", bien au-dessus des autres variables (médiane {_num(m.group('median'))})"
           if m.group('median') else '')
    after = 'le résultat' if m.group('what') == 'outcome' else 'la cible'
    status = _STATUS_FR.get(m.group('status'), m.group('status'))
    return (f"{m.group('feature')} {what} à elle seule{far}. Sa valeur est-elle vraiment "
            f"connue au moment de la prédiction, ou est-elle enregistrée au moment de "
            f"{after} ou après ? (disponibilité décidée : {status})")


def eda_text(text: Any, lang: str) -> str | None:
    """The French form of one stored EDA sentence (a question, a note, a warning, a binning,
    a signal question), its English when ``lang`` is English, or None when the sentence has
    no French form (a surface then shows the English, labelled)."""
    if not isinstance(text, str):
        return None
    if lang != FR:
        return text
    m = _SIGNAL.fullmatch(text)
    if m:
        return _signal_fr(m)
    for pattern, french in _EDA_FR:
        m = pattern.fullmatch(text)
        if m is None:
            continue
        fields = dict(m.groupdict())
        rows = fields.get('rows') or 'training'
        fields.update(R=_ROWS_FR[rows], theR=_THE_ROWS_FR[rows], ofR=_OF_ROWS_FR[rows],
                      binR=_BIN_FR[rows])
        return french(m) if callable(french) else french.format(**fields)
    return None


def eda_texts(values: Mapping | None, lang: str, translations: Translations = EMPTY,
              ) -> dict:
    """The junior texts of an ``eda.*`` (or ``eda.correlation``) result's ``values`` in
    ``lang``: ``question``, ``note``, ``warnings`` (list), ``binning``, ``signal_questions``
    (``{feature: text}``), ``null_band`` (the band's note), and ``meanings``
    (``{"column=value": meaning}``, the case's special values through the sidecar). A text
    without a form in ``lang`` is None."""
    v = values if isinstance(values, Mapping) else {}
    out: dict[str, Any] = {'question': eda_text(v.get('question'), lang),
                           'note': eda_text(v.get('note'), lang),
                           'warnings': [eda_text(w, lang) for w in v.get('warnings') or []],
                           'binning': eda_text(v.get('binning'), lang)}
    out['signal_questions'] = {str(q.get('feature')): eda_text(q.get('text'), lang)
                               for q in v.get('questions') or [] if isinstance(q, Mapping)}
    band = v.get('null_band') if isinstance(v.get('null_band'), Mapping) else {}
    out['null_band'] = eda_text(band.get('note') or band.get('reason'), lang)
    meanings = {}
    for s in v.get('special_values') or []:
        if isinstance(s, Mapping) and 'meaning' in s:
            key = f'{s.get("column")}={s.get("value")}'
            meanings[key] = (s['meaning'] if lang == EN else
                             translations.meaning(s.get('column'), s.get('value'), lang))
    out['meanings'] = meanings
    return out


def eda_texts_pair(values: Mapping | None, translations: Translations = EMPTY) -> dict:
    """:func:`eda_texts` in both languages, ``{"en": ..., "fr": ...}`` (D4b)."""
    return {lang: eda_texts(values, lang, translations) for lang in LANGUAGES}


def question_junior(values: Mapping | None, lang: str) -> str | None:
    """The question an EDA result answers, in the study language (its stored English when
    no French form exists)."""
    q = (values or {}).get('question') if isinstance(values, Mapping) else None
    if not isinstance(q, str):
        return None
    return eda_text(q, lang) or q


__all__ = ['SCHEMA', 'FILE', 'STATE_KEY', 'L10nError', 'pair', 'validate', 'load', 'record',
           'state_problems', 'Translations', 'translations', 'status', 'eda_text',
           'eda_texts', 'eda_texts_pair', 'question_junior', 'sidecar_path', 'EMPTY',
           'case_texts']
