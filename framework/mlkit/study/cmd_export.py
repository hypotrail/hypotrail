"""``hypotrail export handoff``: a reviewer's pack written under ``--out`` only.

    hypotrail export handoff --study DIR [--out DIR] [--expected-revision REV] [--json]
    hypotrail export azureml --study DIR --expected-revision REV [--profile FILE]
                     [--template team-azureml-v1] [--require-configured] (--out DIR | --plan)

CLI-CONTRACT-COMPANION §7 (C7), payloads ``hypotrail.export/1`` (stdout) and
``hypotrail.handoff/1`` (``handoff.json``).

It **never changes the study**: no state, revision, registry entry, exposure record,
artefact, manifest, event, or lock; it does not render; it reads the view the way
``status`` does. It writes files only under ``--out`` (default
``<study>/handoff/revision-<n>/``), which must be a new or empty folder outside
``.hypotrail/``, ``reports/``, and ``notebooks/``, and never overwrites a file. It reads no
clock: one study content and one ``--out`` give the same bytes. The default folder is named
after the revision the engine read, which the payload reports as ``revision``; with
``--expected-revision`` (review fix), a study at another revision is refused with
``stale_revision`` and nothing is written, so a client exports the revision it showed.

Files: ``handoff.md`` (a human summary; ``hypotrail check --text handoff.md`` reports it
clean, and the export refuses with ``untraceable_number``, writing nothing, when it would
not be), ``handoff.json``, ``study.html`` (a byte copy of the report, only when it is
current), and ``SHA256SUMS``. Exit code 3 when the report is not current; the pack is
written all the same.

Third session of 2026-10-26 (R22): ``handoff.md`` is written in the study language, with
that language's number forms (a French study: thousands grouped by a narrow no-break space,
a decimal comma, French labels), and checked in the language it is written in, so a count
of 1,000 rows or more no longer reads as a decimal in a French study. An English study's
pack is unchanged byte for byte. ``handoff.json`` keeps its keys; its ``results_cited``
``shown`` is the text ``handoff.md`` shows.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Mapping

from . import audience, cite, read, texts
from . import cmd_check
from . import cmd_evidence as ev
from . import commands as cmd
from . import guard
from . import manifest as mf
from . import state as st
from . import view as view_model
from .cmd_explain import placeholders
from .errors import StudyError

SCHEMA = 'hypotrail.export/1'
HANDOFF_SCHEMA = 'hypotrail.handoff/1'
PAYLOAD_KEYS = ('schema', 'ok', 'study', 'revision', 'kind', 'out', 'files', 'included_report',
                'warnings')
HANDOFF_KEYS = ('schema', 'study', 'revision', 'task', 'case', 'dataset', 'goal', 'decisions',
                'results_cited', 'exposure', 'not_yet_defensible', 'open_items', 'deliverables',
                'reproduce', 'environment', 'history')
CITED_KEYS = ('result_id', 'activity', 'path', 'value', 'shown')
FILE_KEYS = ('path', 'sha256', 'bytes')
KINDS = ('handoff', 'azureml')
FILES = ('handoff.md', 'handoff.json', 'study.html', 'SHA256SUMS')
WARNINGS = ('report_not_current', 'open_proposals', 'open_holds', 'interrupted_executions',
            'sources_changed', 'unconfirmed_decisions')
DEFAULT_PARENT = 'handoff'
# ``--out`` may not be inside these study folders (the engine's own files and deliverables).
FORBIDDEN = ('.hypotrail', 'reports', 'notebooks')
STUDY = '<study>'
# handoff.json anchors of a path outside the study folder (review fix: no absolute path).
CASE = '<case>'
EXTERNAL = '<external>'
RID = 8
PURPOSE_LABELS = {'structural_inspection': 'Structural inspection',
                  'train_eda': 'Exploration of training rows', 'train_fit': 'Model fitting',
                  'validation_model_evaluation': 'Model evaluation',
                  'validation_policy_selection': 'Rule selection',
                  'policy_exploration': 'Recorded policy exploration',
                  'labelled_preview_available': 'Labelled preview made available',
                  # Contract P1.9 (CLI-CONTRACT §17.3).
                  'development_target_sample': 'Development target sample shown at step 1',
                  'sealed': 'Final test set aside, sealed (schema check only)'}
BASIS_WORDS = {st.EXPLICIT: "the junior's own decision",
               # ADR 0005: the two kinds of own words of the guided mode.
               st.ENDORSED: "the junior's own decision (an explicit endorsement)",
               st.RESTATED: "the junior's own decision (restated in their words)",
               st.DELEGATED_DEFAULT: "delegated by the junior to the assistant's recommended "
                                     'default',
               # L9 (R20): neither the junior's words nor a delegation.
               st.AUTOMATIC: 'recorded by the automatic mode chosen at launch, not yet '
                             "reviewed by the junior"}
NOT_AUTHENTICATED = 'Recorded words, not an authenticated signature.'
CLOSING = ('This pack records a study made for learning and review. It does not authorise '
           'production use: the validation rows were used to choose, the decisions are '
           'recorded words rather than signatures, and the limits listed above still apply.')
EN, FR = 'en', 'fr'
# R22 (third session of 2026-10-26): the words of a French study's handoff.md. The English
# words stay in the code paths above and below, unchanged.
PURPOSE_LABELS_FR = {'structural_inspection': 'Inspection de la structure',
                     'train_eda': "Exploration des lignes d'entraînement",
                     'train_fit': 'Ajustement des modèles',
                     'validation_model_evaluation': 'Évaluation des modèles',
                     'validation_policy_selection': 'Choix de la règle',
                     'policy_exploration': 'Exploration enregistrée des règles',
                     'labelled_preview_available': 'Aperçu étiqueté mis à disposition',
                     'development_target_sample': 'Échantillon de développement montré à '
                                                  "l'étape 1, cible comprise",
                     'sealed': 'Test final mis de côté, scellé (contrôle du schéma seulement)',
                     'cross_validated_fit': 'Ajustement en validation croisée',
                     'out_of_fold_evaluation': 'Évaluation hors pli',
                     'out_of_fold_policy_selection': 'Choix de la règle sur les prédictions '
                                                     'hors pli',
                     'final_evaluation': 'Évaluation du test final',
                     'development_diagnostics': 'Diagnostics de développement'}
BASIS_WORDS_FR = {st.EXPLICIT: "la décision de l'analyste",
                  st.ENDORSED: "la décision de l'analyste (une approbation explicite)",
                  st.RESTATED: "la décision de l'analyste (reformulée avec ses mots)",
                  st.DELEGATED_DEFAULT: "déléguée par l'analyste à la valeur par défaut "
                                        "recommandée par l'assistant",
                  # L9 (R20): neither the junior's words nor a delegation.
                  st.AUTOMATIC: 'enregistrée par le mode automatique choisi au lancement, '
                                "pas encore relue par l'analyste"}
STATUS_WORDS_FR = {'open': 'ouverte', 'proposed': 'proposée', 'confirmed': 'confirmée',
                   'reconfirm_required': 'à confirmer de nouveau', 'superseded': 'remplacée'}
AVAILABILITY_WORDS_FR = {'available_at_prediction': 'Disponible au moment de la prédiction',
                         'not_available': 'Non disponible',
                         'uncertain_excluded': 'Incertaine, exclue',
                         'uncertain_included': 'Incertaine, incluse'}
PARTITION_WORDS_FR = {'all': 'toutes les lignes du jeu de données',
                      'train': "tout l'échantillon d'entraînement",
                      'validation': "tout l'échantillon de validation",
                      'development': "toutes les lignes de l'échantillon de développement (le "
                                     'test final reste scellé)'}
NOT_AUTHENTICATED_FR = 'Des mots enregistrés, pas une signature authentifiée.'
CLOSING_FR = ("Ce dossier rend compte d'une étude faite pour apprendre et pour être relue. Il "
              "n'autorise pas un usage en production : les lignes de validation ont servi à "
              'choisir, les décisions sont des mots enregistrés et non des signatures, et les '
              'limites ci-dessus restent valables.')


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument('kind', choices=KINDS)
    parser.add_argument('--out', default=None, metavar='DIR',
                        help='a new or empty folder (default <study>/handoff/revision-<n>/)')
    parser.add_argument('--expected-revision', default=None, type=int, metavar='REV',
                        help='refuse with stale_revision unless the study is at REV')
    # v0.3 (WP-J, R35): the study panel passes webview; recorded as an event.
    parser.add_argument('--channel', default=None,
                        help='chat (the default), cli, or webview: where the export came from')
    # export azureml (chantier B): mlkit.exporters.azureml.
    parser.add_argument('--profile', default=None, metavar='FILE',
                        help='azureml: the destination profile (hypotrail.azure_target/1)')
    parser.add_argument('--template', default='team-azureml-v1',
                        help='azureml: the project template (team-azureml-v1)')
    parser.add_argument('--plan', action='store_true',
                        help='azureml: list files, statuses and missing fields; write nothing')
    parser.add_argument('--require-configured', action='store_true',
                        help='azureml: refuse a draft (incomplete profile)')


# --- the target folder -----------------------------------------------------------------

def _target(study_dir: Path, out, revision: int) -> Path:
    """The ``--out`` folder, refused when it is inside the study's own folders
    (``invalid_arguments``) or exists and is not an empty folder (``export_target_exists``)."""
    target = Path(out) if out is not None else study_dir / DEFAULT_PARENT / f'revision-{revision}'
    if not target.is_absolute():
        target = Path.cwd() / target
    real = Path(os.path.realpath(target))
    for name in FORBIDDEN:
        folder = Path(os.path.realpath(study_dir / name))
        if real == folder or folder in real.parents:
            raise StudyError('invalid_arguments',
                             f'--out may not be inside the study folder {name}/: choose a '
                             'folder outside the engine files and the deliverables.',
                             details={'field': 'out', 'out': str(target)})
    if target.exists() or target.is_symlink():
        if not target.is_dir() or any(target.iterdir()):
            raise StudyError('export_target_exists',
                             'The export folder exists and is not empty; nothing was written.',
                             details={'path': str(target)})
    return target


# --- content ---------------------------------------------------------------------------

def _label(decision_id: str, lang: str = EN) -> str:
    if lang == FR:
        words = audience.decision_words(decision_id, FR)
        for article in ('le ', 'la ', "l'"):
            if words.startswith(article):
                words = words[len(article):]
                break
        return words[:1].upper() + words[1:]
    return view_model.DECISION_LABELS.get(decision_id, decision_id).capitalize()


def _value_lines_fr(decision_id: str, value, task: str) -> list[str]:
    if value is None:
        return []
    if decision_id == 'feature_availability' and isinstance(value, Mapping):
        grouped: dict[str, list[str]] = {}
        for feature, status in sorted(value.items()):
            grouped.setdefault(str(status), []).append(str(feature))
        return [f'- {AVAILABILITY_WORDS_FR.get(status, " ".join(status.split("_")))} : '
                f'{", ".join(names)}' for status, names in sorted(grouped.items())]
    if decision_id == 'model_choice' and isinstance(value, str):
        from . import render_html
        with texts.report_language_context(FR):
            words = render_html.value_words('model_choice', value, task)
        return [f'- Valeur : {words} (`{value}`)']
    if decision_id == 'conclusion' and isinstance(value, Mapping):
        from . import junior
        verdict = str(value.get('verdict', ''))
        pair = junior.VERDICT_LABELS.get(verdict)
        out = [f'- Verdict : {pair[1] if pair else " ".join(verdict.split("_"))}']
        if isinstance(value.get('text'), str):
            out.append(f'- Texte : « {value["text"]} »')
        return out
    if isinstance(value, (Mapping, list)):
        return [f'- Valeur : `{json.dumps(value, sort_keys=True, ensure_ascii=False)}`']
    return [f'- Valeur : {value}']


def _value_lines(decision_id: str, value) -> list[str]:
    if value is None:
        return []
    if decision_id == 'feature_availability' and isinstance(value, Mapping):
        grouped: dict[str, list[str]] = {}
        for feature, status in sorted(value.items()):
            grouped.setdefault(str(status), []).append(str(feature))
        return [f'- {" ".join(status.split("_")).capitalize()}: {", ".join(names)}'
                for status, names in sorted(grouped.items())]
    if decision_id == 'model_choice' and isinstance(value, str):
        return [f'- Value: {view_model.MODEL_CHOICE_WORDS.get(value, value)} (`{value}`)']
    if decision_id == 'conclusion' and isinstance(value, Mapping):
        out = [f'- Verdict: {" ".join(str(value.get("verdict", "")).split("_"))}']
        if isinstance(value.get('text'), str):
            out.append(f'- Text: "{value["text"]}"')
        return out
    if isinstance(value, (Mapping, list)):
        return [f'- Value: `{json.dumps(value, sort_keys=True, ensure_ascii=False)}`']
    return [f'- Value: {value}']


def _decisions(view: Mapping, lang: str = EN) -> tuple[list[dict], list[str]]:
    items, lines = [], []
    for d, dec in view['decisions'].items():
        conf = dec['confirmation'] or None
        items.append({'decision_id': d, 'status': dec['status'], 'value': dec['value'],
                      'user_words': conf['user_words'] if conf else None,
                      'basis': conf['basis'] if conf else None,
                      'delegation_scope': conf['delegation_scope'] if conf else None,
                      'channel': conf['channel'] if conf else None,
                      'actor': conf['actor'] if conf else None,
                      'authenticated': bool(conf['authenticated']) if conf else False,
                      'proposal_id': dec['proposal_id']})
        if lang == FR:
            lines += _decision_lines_fr(d, dec, conf, view['task'])
            continue
        lines.append(f'### {_label(d)} (`{d}`)')
        lines.append('')
        lines.append(f'- Status: {" ".join(dec["status"].split("_"))}')
        if dec['status'] in ('confirmed', 'reconfirm_required'):
            lines += _value_lines(d, dec['value'])
        if conf:
            if conf.get('user_words') is not None:
                lines.append(f'- The junior\'s words: "{conf["user_words"]}"')
            if conf.get('reason_given') is False:    # v0.3 (WP-B, R27)
                lines.append('- No reason given')
            basis = BASIS_WORDS.get(conf['basis'], conf['basis'])
            if conf.get('delegation_scope'):
                basis += f' (scope: {" ".join(conf["delegation_scope"].split("_"))})'
            lines.append(f'- Basis: {basis}')
            if conf.get('agent_concern'):          # R3 (ADR 0005)
                lines.append(f'- Point raised by the agent, kept by the junior: '
                             f'"{conf["agent_concern"]}"')
            lines.append(f'- Channel: {conf["channel"]}')
            lines.append(f'- {NOT_AUTHENTICATED}')
        if dec['status'] == 'reconfirm_required' and dec.get('reason'):
            lines.append('- To confirm again before it is relied on.')
        lines.append('')
    return items, lines


def _decision_lines_fr(d: str, dec: Mapping, conf: Mapping | None, task: str) -> list[str]:
    """R22: the lines of one decision in a French study's handoff.md."""
    status = STATUS_WORDS_FR.get(dec['status'], ' '.join(dec['status'].split('_')))
    lines = [f'### {_label(d, FR)} (`{d}`)', '', f'- Statut : {status}']
    if dec['status'] in ('confirmed', 'reconfirm_required'):
        lines += _value_lines_fr(d, dec['value'], task)
    if conf:
        if conf.get('user_words') is not None:
            lines.append(f"- Les mots de l'analyste : « {conf['user_words']} »")
        if conf.get('reason_given') is False:
            lines.append('- Sans raison donnée')
        basis = BASIS_WORDS_FR.get(conf['basis'], conf['basis'])
        if conf.get('delegation_scope'):
            basis += f' (portée : {" ".join(conf["delegation_scope"].split("_"))})'
        lines.append(f'- Fondement : {basis}')
        if conf.get('agent_concern'):
            lines.append("- Point soulevé par l'agent, maintenu par l'analyste : "
                         f"« {conf['agent_concern']} »")
        lines.append(f'- Canal : {conf["channel"]}')
        lines.append(f'- {NOT_AUTHENTICATED_FR}')
    if dec['status'] == 'reconfirm_required' and dec.get('reason'):
        lines.append("- À confirmer de nouveau avant de s'appuyer dessus.")
    lines.append('')
    return lines


def _cited(view: Mapping, study: read.Study, citer: cite.Citer,
           lang: str = EN) -> tuple[list[dict], list[str]]:
    """One line per current, verified result: its headline, cited (``results_cited``).
    R22: a French study reads the French headline (out of fold where the result is) and
    writes each cited number in French (:func:`mlkit.study.cite.format_value`)."""
    values = placeholders(view)
    order = ev._slot_order(study.state)
    items, lines = [], []
    for slot in sorted(view['results'], key=order):
        item = view['results'][slot]
        if not (item['current'] and item['integrity'] == 'ok'):
            continue
        rid = item['result_id']
        before = len(citer.cited)
        if lang == FR:
            headline = ev._headline(view['task'], item['activity'], rid, citer, values,
                                    ev._cross_validated(study, study.result(rid)), FR)
            cited = [s for s in (headline or {}).get('segments') or [] if 'result_id' in s]
            for segment, c in zip(cited, citer.cited[before:]):
                segment['text'] = c['text'] = cite.format_value(segment['value'],
                                                                segment['format'], FR)
        else:
            headline = ev._headline(view['task'], item['activity'], rid, citer, values)
        for c in citer.cited[before:]:
            items.append({'result_id': c['result_id'], 'activity': item['activity'],
                          'path': c['path'], 'value': c['value'], 'shown': c['text']})
        if lang == FR:
            text = ''.join(s['text'] for s in headline['segments']) if headline else 'à jour'
            lines.append(f'- `{slot}` : {text} (résultat {rid[:RID]})')
            continue
        text = ''.join(s['text'] for s in headline['segments']) if headline else 'current'
        lines.append(f'- `{slot}`: {text} (result {rid[:RID]})')
    if lang == FR:
        return items, lines or ['- Aucun résultat à jour pour le moment.']
    return items, lines or ['- No current result yet.']


# The value of the current split that counts the rows of each partition.
PARTITION_PATHS = {'all': 'n_rows', 'train': 'partitions.train.n_rows',
                   'validation': 'partitions.validation.n_rows',
                   # ADR 0006: the split counts the development rows it divided.
                   'development': 'n_rows'}
PARTITION_WORDS = {'all': 'every row of the dataset', 'train': 'the whole training partition',
                   'validation': 'the whole validation partition',
                   'development': 'every development row (the final test stays sealed)'}


def _ledger_lines(ledger: list[dict], citer: cite.Citer,
                  lang: str = EN) -> tuple[list[dict], list[str]]:
    """One line per ledger row. A row count is written when it equals the size of its
    partition in the current split, cited from it; otherwise (rows read under an earlier
    split too) it is in ``handoff.json`` only, since no registry value states it."""
    lines, cited = [], []
    split = citer.slot_rid('split')
    for row in ledger:
        if lang == FR:
            label = PURPOSE_LABELS_FR.get(row['purpose'], row['purpose'])
        else:
            label = PURPOSE_LABELS.get(row['purpose'], row['purpose'])
        path = PARTITION_PATHS.get(row['partition'])
        try:
            size = citer.lookup(split, path) if split and path else None
        except StudyError:
            size = None
        if size is not None and size == row['rows']:
            # R22: the count in the language handoff.md is written in (a French study:
            # "32 049", never "32,049", which a French reader reads as a decimal).
            shown = cite.format_value(size, 'int', FR) if lang == FR \
                else cite.fmt_number(size, 'int')
            cited.append({'result_id': split, 'activity': 'split', 'path': path,
                          'value': size, 'shown': shown})
            if lang == FR:
                count = (f'{shown} lignes, {PARTITION_WORDS_FR[row["partition"]]} '
                         f'(résultat {split[:RID]})')
            else:
                count = (f'{shown} rows, {PARTITION_WORDS[row["partition"]]} '
                         f'(result {split[:RID]})')
        else:
            count = ('le nombre de lignes distinctes est dans handoff.json' if lang == FR
                     else 'the count of distinct rows is in handoff.json')
        names = ', '.join(f'`{a}`' for a in row['activities'])
        if lang == FR:
            lines.append(f'- {label}, échantillon `{row["partition"]}` : {count} ; enregistré '
                         f'par {names}.')
        else:
            lines.append(f'- {label}, `{row["partition"]}` partition: {count}; recorded by '
                         + names + '.')
    if lang == FR:
        return cited, lines or ["- Aucune ligne n'a encore été lue."]
    return cited, lines or ['- No rows were read yet.']


def _open_items(view: Mapping, lang: str = EN) -> tuple[dict, list[str]]:
    ex = view['executions']
    proposals = [p['proposal_id'] for p in view['open_proposals']]
    holds = [n['note_id'] for n in view['notes'] if n['status'] == 'open']
    executions = sorted(set(ex['interrupted']) | set(ex['suspected_interrupted'])
                        | set(ex['late']))
    stale = sorted(name for name, item in view['artifacts']['items'].items()
                   if name in ev.LINEAGE_ARTIFACTS and item.get('status') != 'ok')
    stale += [name for name in ev.LINEAGE_ARTIFACTS
              if name not in view['artifacts']['items']]
    if lang == FR:
        return ({'proposals': proposals, 'holds': holds, 'executions': executions,
                 'stale_deliverables': stale}, _open_lines_fr(view, stale))
    lines = []
    for p in view['open_proposals']:
        lines.append(f'- Open proposal {p["proposal_id"]} on the '
                     f'{view_model.DECISION_LABELS.get(p["decision_id"], p["decision_id"])}: '
                     'not a decision until the junior confirms it.')
    for n in view['notes']:
        if n['status'] == 'open':
            lines.append(f'- Hold {n["note_id"]} on the '
                         f'{view_model.DECISION_LABELS.get(n["decision_id"], n["decision_id"])}'
                         f', in the junior\'s words: "{n["user_words"]}"')
    for bucket, words in (('interrupted', 'interrupted, outcome unknown'),
                          ('suspected_interrupted', 'stopped, outcome unknown'),
                          ('late', 'finished after the study moved on, not promoted')):
        for eid, record in sorted(ex[bucket].items()):
            lines.append(f'- Execution {eid} (`{record.get("activity")}`): {words}.')
    for name in stale:
        item = view['artifacts']['items'].get(name)
        message = item.get('message') if item else f'The {name} has not been rendered yet.'
        lines.append(f'- {message}')
    return ({'proposals': proposals, 'holds': holds, 'executions': executions,
             'stale_deliverables': stale}, lines or ['- Nothing is open.'])


def _open_lines_fr(view: Mapping, stale: list[str]) -> list[str]:
    """R22: the open items of a French study's handoff.md."""
    ex, lines = view['executions'], []
    for p in view['open_proposals']:
        lines.append(f'- Proposition ouverte {p["proposal_id"]} sur '
                     f'{audience.decision_words(p["decision_id"], FR)} : ce n\'est pas une '
                     "décision tant que l'analyste ne l'a pas confirmée.")
    for n in view['notes']:
        if n['status'] == 'open':
            lines.append(f'- Condition {n["note_id"]} sur '
                         f'{audience.decision_words(n["decision_id"], FR)}, avec les mots de '
                         f"l'analyste : « {n['user_words']} »")
    for bucket, words in (('interrupted', 'interrompue, résultat inconnu'),
                          ('suspected_interrupted', 'arrêtée, résultat inconnu'),
                          ('late', "terminée après que l'étude a avancé, non promue")):
        for eid, record in sorted(ex[bucket].items()):
            lines.append(f'- Exécution {eid} (`{record.get("activity")}`) : {words}.')
    for name in stale:
        item = view['artifacts']['items'].get(name)
        message = (item.get('junior_message') or item.get('message')) if item \
            else f"Le livrable {name} n'a pas encore été produit."
        lines.append(f'- {message}')
    return lines or ["- Rien n'est ouvert."]


def _reproduce(view: Mapping, order) -> list[str]:
    commands = [f'hypotrail status --study {STUDY} --summary',
                f'hypotrail evidence --study {STUDY}']
    for slot in sorted(view['results'], key=order):
        item = view['results'][slot]
        if not (item['current'] and item['integrity'] == 'ok') or not item['activity']:
            continue
        activity = item['activity']
        options = ''
        params = item['params'] if isinstance(item.get('params'), Mapping) else {}
        if isinstance(params.get('column'), str):
            options = f' --column {params["column"]}'
        if activity == 'policy.evaluation':
            activity = 'policy.evaluate'
            options = ''.join(f' --rule {r}' for r in params.get('rules') or [])
        commands.append(f'hypotrail run {activity}{options} --request-id <new id> '
                        f'--expected-revision <revision> --study {STUDY}')
    commands += [f'hypotrail render --study {STUDY}', f'hypotrail check --study {STUDY}']
    return commands


def _environment(view: Mapping) -> dict | None:
    """The environment recorded with the newest current result (display only)."""
    current = [r for r in view['results'].values()
               if r['current'] and r['integrity'] == 'ok' and isinstance(r.get('environment'),
                                                                          Mapping)]
    if not current:
        return None
    newest = max(current, key=lambda r: (r.get('started_revision') or -1, r['result_id']))
    return dict(newest['environment'])


def _goal(summary: Mapping) -> str:
    line = summary['recap'][0]
    return line[len('Goal: '):] if line.startswith('Goal: ') else line


def _goal_fr(summary: Mapping) -> str:
    """R22: the goal as the French recap words it (``recap_junior``)."""
    lines = summary.get('recap_junior') or []
    line = lines[0] if lines else _goal(summary)
    return line[len('Objectif : '):] if line.startswith('Objectif : ') else line


def _warnings(view: Mapping, included: bool) -> list[str]:
    ex = view['executions']
    found = {
        'report_not_current': not included,
        'open_proposals': bool(view['open_proposals']),
        'open_holds': any(n['status'] == 'open' for n in view['notes']),
        'interrupted_executions': bool(ex['interrupted'] or ex['suspected_interrupted']),
        'sources_changed': any(x['id'] == 'sources_changed'
                               for x in view['not_yet_defensible']),
        'unconfirmed_decisions': any(d['status'] != 'confirmed'
                                     for d in view['decisions'].values()),
    }
    return [w for w in WARNINGS if found[w]]


def _report(study: read.Study, view: Mapping) -> tuple[bytes | None, str]:
    """The report bytes when it is current (effective status ``ok`` and its bytes match the
    manifest), else None; and its effective status."""
    item = view['artifacts']['items'].get('report')
    status = item.get('status') if item else 'not_rendered'
    path = study.study_dir / mf.ARTIFACTS['report']
    if status != 'ok' or not path.is_file():
        return None, status if status != 'ok' else 'not_rendered'
    data = path.read_bytes()
    if item.get('sha256') and hashlib.sha256(data).hexdigest() != item['sha256']:
        return None, 'stale'
    return data, status


def _markdown(view, summary, decisions_md, cited_md, ledger_md, open_md, included, status,
              reproduce, environment) -> str:
    rows = []
    rows += [f'# Handoff pack: {view["case"].get("id", "study")}', '',
             f'Study at revision {view["revision"]}, a {view["task"]} task. Every figure below is '
             'cited from a current, verified registry result, with its result id; '
             'handoff.json holds the same content as data.', '',
             '## Goal', '', _goal(summary), '',
             '## Decisions', '', *decisions_md,
             '## Cited results', '', *cited_md, '',
             '## Exposure ledger', '',
             'Rows read by the study, by purpose. Changing the split does not make explored '
             'rows unseen.', '', *ledger_md, '',
             '## Not yet defensible', '',
             *[f'- {x["text"]}' for x in view['not_yet_defensible']], '',
             '## Open items', '', *open_md, '',
             '## Report', '']
    if included:
        rows.append(f'The report ({mf.ARTIFACTS["report"]}) is up to date; this pack holds a '
                    'byte copy, study.html.')
    else:
        rows.append(f'The report ({mf.ARTIFACTS["report"]}) is not current ({status}), so it '
                    'is not in this pack. Render it again and export again to include it.')
    rows += ['', '## How to reproduce', '',
             f'Run these commands with the study folder in place of {STUDY}; a run needs a new '
             'request id and the revision read with status.', '',
             *[f'- `{c}`' for c in reproduce], '']
    if environment:
        packages = ', '.join(sorted((environment.get('packages') or {}).keys()))
        rows.append(f'Environment recorded with the results: Python '
                    f'({environment.get("implementation", "python")}) with {packages}; the '
                    'versions are in handoff.json (`environment`).')
        rows.append('')
    rows += ['## Not for production use', '', CLOSING, '']
    return '\n'.join(rows)


def _markdown_fr(view, summary, decisions_md, cited_md, ledger_md, open_md, included, status,
                 reproduce, environment) -> str:
    """R22: :func:`_markdown` in French, for a French study."""
    task = 'binaire' if st.task_of(view['task']) == st.BINARY else 'de régression'
    rows = [f'# Dossier de passation : {view["case"].get("id", "étude")}', '',
            f'Étude à la révision {view["revision"]}, une tâche {task}. Chaque chiffre '
            "ci-dessous est cité d'un résultat du registre à jour et vérifié, avec son "
            'identifiant ; handoff.json contient le même contenu sous forme de données.', '',
            '## Objectif', '', _goal_fr(summary), '',
            '## Décisions', '', *decisions_md,
            '## Résultats cités', '', *cited_md, '',
            '## Registre des lignes lues', '',
            "Lignes lues par l'étude, par usage. Changer le découpage ne rend pas invisibles "
            'les lignes déjà explorées.', '', *ledger_md, '',
            '## Pas encore défendable', '',
            *[f'- {x.get("junior_text") or x["text"]}' for x in view['not_yet_defensible']], '',
            '## Points ouverts', '', *open_md, '',
            '## Rapport', '']
    if included:
        rows.append(f'Le rapport ({mf.ARTIFACTS["report"]}) est à jour ; ce dossier en contient '
                    'une copie octet pour octet, study.html.')
    else:
        rows.append(f"Le rapport ({mf.ARTIFACTS['report']}) n'est pas à jour ({status}) : il "
                    "n'est donc pas dans ce dossier. Produisez-le de nouveau puis exportez de "
                    "nouveau pour l'inclure.")
    rows += ['', '## Reproduire', '',
             f"Lancez ces commandes en remplaçant {STUDY} par le dossier de l'étude ; une "
             'exécution demande un nouvel identifiant de requête et la révision lue avec status.',
             '', *[f'- `{c}`' for c in reproduce], '']
    if environment:
        packages = ', '.join(sorted((environment.get('packages') or {}).keys()))
        rows.append('Environnement enregistré avec les résultats : Python '
                    f'({environment.get("implementation", "python")}) avec {packages} ; les '
                    'versions sont dans handoff.json (`environment`).')
        rows.append('')
    rows += ['## Pas pour un usage en production', '', CLOSING_FR, '']
    return '\n'.join(rows)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _under(path: str, folder) -> str | None:
    """The POSIX path of ``path`` relative to ``folder`` when it is inside it, else None."""
    real, base = Path(os.path.realpath(path)), Path(os.path.realpath(folder))
    if real == base:
        return ''
    return real.relative_to(base).as_posix() if base in real.parents else None


def study_path(study_dir: Path, path, case_dir=None) -> str | None:
    """``path`` as the pack writes it (review fix): never an absolute path, and nothing of
    the folders around the study. Inside the study folder, ``<study>/<relative path>``;
    else inside the case's folder ``case_dir``, ``<case>/<relative path>``; else
    ``<external>/<file name>``. A relative path is kept as it is."""
    if not isinstance(path, str):
        return path
    if not os.path.isabs(path):
        return Path(path).as_posix()
    for anchor, folder in ((STUDY, study_dir), (CASE, case_dir)):
        rel = _under(path, folder) if folder is not None else None
        if rel is not None:
            return f'{anchor}/{rel}' if rel else anchor
    return f'{EXTERNAL}/{Path(path).name}'


def _relative(study_dir: Path, record: Mapping, case_dir) -> dict:
    """A copy of a ``case`` or ``dataset`` record whose ``path`` is :func:`study_path`."""
    out = dict(record)
    if 'path' in out:
        out['path'] = study_path(study_dir, out['path'], case_dir)
    return out


def build(study_dir) -> tuple[read.Study, dict, dict[str, bytes], bool]:
    """``(study, view, {file: bytes}, included_report)`` of the pack, built in memory.

    Refuses with ``untraceable_number`` when ``handoff.md`` would not pass
    ``hypotrail check --text``."""
    study = read.open(study_dir)
    view = view_model.build(study)
    summary = view_model.summary(view)
    task = st.task_of(view['task'])
    # R22: handoff.md is written in the study language, the one check_text reads it in.
    lang = FR if view.get('language') == FR else EN
    with texts.study_context(view):
        citer = cite.Citer.from_view(view)
        decisions, decisions_md = _decisions(view, lang)
        results_cited, cited_md = _cited(view, study, citer, lang)
        exposure = ev._exposure(study)
        ledger_cited, ledger_md = _ledger_lines(exposure['ledger'], citer, lang)
        results_cited += ledger_cited
        open_items, open_md = _open_items(view, lang)
        report, status = _report(study, view)
        included = report is not None
        reproduce = _reproduce(view, ev._slot_order(study.state))
        environment = _environment(view)
        md = (_markdown_fr if lang == FR else _markdown)(
            view, summary, decisions_md, cited_md, ledger_md, open_md, included, status,
            reproduce, environment)
    findings, _ = cmd_check.check_text(view, md, 'handoff.md',
                                       result_ids=cmd_check.registry_ids(study))
    errors = [f for f in findings if f['severity'] == 'error']
    if errors:
        raise StudyError('untraceable_number',
                         'The handoff summary would hold a number that cannot be traced to a '
                         'current result; nothing was written.',
                         details={'findings': errors})
    case_path = view['case'].get('path')
    case_dir = os.path.dirname(case_path) if isinstance(case_path, str) \
        and os.path.isabs(case_path) else None
    handoff = {
        'schema': HANDOFF_SCHEMA, 'study': STUDY, 'revision': view['revision'],
        'task': task, 'case': _relative(study.study_dir, view['case'], case_dir),
        'dataset': _relative(study.study_dir, view['dataset'], case_dir),
        'goal': _goal(summary), 'decisions': decisions,
        'results_cited': [{k: c[k] for k in CITED_KEYS} for c in results_cited],
        'exposure': {'summary': exposure['summary'], 'ledger': exposure['ledger']},
        'not_yet_defensible': [{'id': x['id'], 'text': x['text']}
                               for x in view['not_yet_defensible']],
        'open_items': open_items,
        'deliverables': {name: (view['artifacts']['items'].get(name) or {}).get(
            'status', 'not_rendered') for name in ev.LINEAGE_ARTIFACTS},
        'reproduce': reproduce, 'environment': environment,
        'history': {
            'dataset_sha256': view['dataset']['sha256'],
            'exploration_events': list((study.state.get('exploration') or {})
                                       .get('events', {}).values()),
            'exploration_coverage': 'instrumented_operations_only',
            'unrecorded_surfaces': ['preview', 'workbench', 'external_files'],
            'cross_study_history': 'not_enforced',
        }}
    files = {'handoff.md': md.encode('utf-8'),
             'handoff.json': (json.dumps({k: handoff[k] for k in HANDOFF_KEYS}, indent=2,
                                         ensure_ascii=False) + '\n').encode('utf-8')}
    if included:
        files['study.html'] = report
    files['SHA256SUMS'] = ''.join(f'{_sha(data)}  {name}\n'
                                  for name, data in files.items()).encode('utf-8')
    return study, view, files, included


def _expected(study: read.Study, view: Mapping, expected_revision) -> None:
    """``stale_revision`` (CLI-CONTRACT §7 details) unless the pack's revision is
    ``expected_revision``; nothing is written."""
    if expected_revision is None or expected_revision == view['revision']:
        return
    raise StudyError('stale_revision',
                     f'The study is at revision {view["revision"]}, not '
                     f'{expected_revision}: read the study again before exporting; nothing '
                     'was written.',
                     details={'expected_revision': expected_revision,
                              'current_revision': view['revision'],
                              'changes_since': study.revisions(expected_revision)
                              if expected_revision < view['revision'] else []})


def export_handoff(study_dir, *, out=None, expected_revision=None) -> tuple[dict, int]:
    """``(hypotrail.export/1 payload, exit code)``: 0, or 3 when the report is not
    current (the pack is written without it)."""
    if guard.read_only():
        raise StudyError('read_only', f'{guard.ENV}=1: a read-only process writes no file, so '
                                      'it cannot export a handoff pack.',
                         details={'variable': guard.ENV})
    if expected_revision is not None and (type(expected_revision) is not int
                                          or expected_revision < 0):
        raise StudyError('invalid_arguments', '--expected-revision must be a revision number.',
                         details={'field': 'expected_revision'})
    from .understanding import milestone
    if milestone.required(study_dir, 'handoff'):
        return milestone.export_handoff_gated(study_dir, out=out,
                                              expected_revision=expected_revision)
    study, view, files, included = build(study_dir)
    _expected(study, view, expected_revision)
    target = _target(study.study_dir, out, view['revision'])
    target.mkdir(parents=True, exist_ok=True)
    listed = []
    for name in FILES:
        if name not in files:
            continue
        with open(target / name, 'xb') as handle:     # never overwrite a file
            handle.write(files[name])
        listed.append({'path': name, 'sha256': _sha(files[name]), 'bytes': len(files[name])})
    payload = {'schema': SCHEMA, 'ok': True, 'study': str(study.study_dir),
               'revision': view['revision'], 'kind': 'handoff', 'out': str(target),
               'files': listed, 'included_report': included,
               'warnings': _warnings(view, included)}
    return ({k: payload[k] for k in PAYLOAD_KEYS},
            cmd.EXIT_OK if included else cmd.EXIT_ARTIFACT_STALE)


def main(args: argparse.Namespace) -> cmd.Outcome:
    if args.kind == 'azureml':
        from mlkit.exporters.azureml import export_azureml
        payload, code = export_azureml(args.study, expected_revision=args.expected_revision,
                                       out=args.out, profile_path=args.profile,
                                       template_id=args.template, plan=args.plan,
                                       require_configured=args.require_configured)
        return cmd.Outcome(payload, code)
    if args.plan or args.profile or args.require_configured:
        raise StudyError('invalid_arguments', '--plan, --profile and --require-configured are '
                         'options of export azureml.', details={'field': 'kind'})
    from .cmd_render import record_channel
    from .executions import channel_param
    channel = getattr(args, 'channel', None)
    channel_param(channel)                       # refused before anything is written
    payload, code = export_handoff(args.study, out=args.out,
                                   expected_revision=args.expected_revision)
    record_channel(args.study, 'export', channel, payload.get('revision'))
    return cmd.Outcome(payload, code)
