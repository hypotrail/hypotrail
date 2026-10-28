"""``hypotrail data``: the data card of a study (v0.2a, WP-A4; remarks R2 and R5).

Read-only and never session-logged. It shows the junior what the data are before any
decision: what one row describes (a case fact), how many development rows and columns
there are, the target and its labels, whether a final test is sealed, a dictionary of the
columns grouped as the case groups them (type, unit, description and its French label,
availability as the case states it, special values with their counts, missing cells,
distinct values, three example values), the seeded step-1 sample (eight development rows
drawn at random, target first; contract P1.9), and the development rows holding a declared
special value, without the target (contract P1.10).

It shows no target rate and no distribution: reading the outcome across rows is
exploration, done on training rows after the split. The rows shown are development rows
only (ADR 0006), whose structure ``init`` already recorded as exposure
(``structural_inspection``). The sample's target values are a counted look, recorded once per
seed by ``init`` or by the first committed write of an older study still before its split
(``development_target_sample``, :func:`mlkit.study.exposure.ensure_sample`); this read records
nothing, so until that record exists the sample is shown without its target (``target_shown:
false``), for good when the split came first (``exposure.withheld``).

Payload ``hypotrail.data/1``, keys in order: :data:`PAYLOAD_KEYS`. ``--format text``
prints a readable card (not a contract).
"""
from __future__ import annotations

import argparse
import math
from typing import Any, Mapping

from . import assurance

SCHEMA = 'hypotrail.data/1'
PAYLOAD_KEYS = ('schema', 'ok', 'study', 'revision', 'observation_unit', 'development',
                'target', 'final_test', 'groups', 'rows', 'note',
                # Contract P1.10 (CLI-CONTRACT §17.4): the development rows holding a declared
                # special value, without the target.
                'special_rows')
# Contract P1.9 (CLI-CONTRACT §17.3): ``rows`` is the seeded step-1 sample; ``seed``,
# ``target_shown`` and ``exposure`` come after its earlier keys.
ROWS_KEYS = ('columns', 'n_rows', 'order', 'items', 'seed', 'target_shown', 'exposure')
ROWS_ORDER = 'seeded sample'
ROWS_EXPOSURE_KEYS = ('exposure_id', 'purpose', 'recorded')
SPECIAL_ROW_KEYS = ('columns', 'n_rows', 'items', 'truncated')
SPECIAL_ROWS_MAX = 50
VARIABLE_KEYS = ('name', 'role', 'type', 'unit', 'description', 'description_fr',
                 'availability', 'decided', 'special_values', 'n_missing', 'n_distinct',
                 'examples')
N_EXAMPLES = 3
UNGROUPED = 'Other columns'
NOTE = ('These are development rows only; the final test stays sealed. The card shows what '
        'the columns mean and a few rows, never how often the outcome occurs: that is '
        'explored after the split, on the rows it leaves for exploration. '
        + assurance.protection_notice())


def configure(parser: argparse.ArgumentParser) -> None:
    parser.description = ('Read-only data card: row unit, sizes, target labels, grouped column '
                          'dictionary, eight development rows drawn at random, and the rows '
                          'holding a special value (never logged).')


def _plain(value: Any) -> Any:
    """A cell as JSON: missing as None, numpy scalars as Python ones, whole floats as ints."""
    if hasattr(value, 'item'):
        value = value.item()
    if isinstance(value, float):
        if math.isnan(value):
            return None
        if value.is_integer():
            return int(value)
    return value


def _fact(state: Mapping, fact_id: str) -> dict | None:
    fact = state['facts'].get(fact_id)
    return {'value': fact['value'], 'status': fact['status'], 'source': fact['source']} \
        if fact else None


def _observation_unit(state: Mapping, tr) -> dict:
    """What one row describes: the case's ``observation_unit`` fact, else its row unit,
    with ``texts`` ({en, fr}; L3) from the case's translation sidecar."""
    from . import l10n
    fact = _fact(state, 'observation_unit')
    if fact:
        return {**fact, 'texts': l10n.pair(fact['value'], tr.fact('observation_unit', l10n.FR))}
    unit = dict(state['structure']['row_unit'])
    return {**unit, 'texts': l10n.pair(unit.get('value'), tr.row_unit(l10n.FR))}


def _final_test_line(final: Mapping, lang: str = 'en') -> dict:
    from . import junior
    if final['status'] == 'absent':
        text = ('This study has no final test: it was created before the final test existed, '
                'so every row is a development row.')
    else:
        text = (f'{final["rows"]} rows are set aside as the final test and stay sealed: '
                f'nothing here reads them.')
    # v0.3 (WP-C): ``junior_text`` is the line in the study language.
    return {**final, 'line': text, 'audience': 'junior',
            'junior_text': junior.final_test_line(final, lang)}


def _duplicates(case, dataset, lang: str = 'en') -> dict:
    """``{policy, n_groups, n_rows, n_extra_rows, definition, line}`` of the identical
    records among the development rows (structural: content hashes, no value)."""
    from . import data as dt
    out = dt.duplicate_summary(case, dataset.index)
    if not out['n_groups']:
        line = 'No two development rows are identical.'
    elif out['policy'] == dt.DUPLICATES_GROUP:
        line = (f'{out["n_rows"]} development rows form {out["n_groups"]} groups of identical '
                f'rows. Each group is treated as one entity: its rows always stay together on '
                f'one side of every split.')
    else:
        line = f'{out["n_rows"]} development rows form {out["n_groups"]} groups of identical rows.'
    from . import junior
    return {**out, 'line': line, 'audience': 'junior',
            'junior_text': junior.duplicates_line(out, out['policy'] == dt.DUPLICATES_GROUP,
                                                  lang)}


def sample_rows(study, frame, case) -> dict:
    """``rows`` (:data:`ROWS_KEYS`): the seeded step-1 sample (contract P1.9), target first,
    in row-key order. The target is shown only once the look is recorded
    (``development_target_sample`` of this seed); a read never records it, so until then
    every item omits the target column (``target_shown: false``)."""
    from . import partition
    state = study.state
    entries = study.exposure_records()
    drawn = partition.study_sample(state, study.blob, entries)
    keys = [k for k in (drawn or {}).get('row_keys', []) if k in frame.index]
    recorded = partition.sample_records(entries, drawn['seed']) if drawn else []
    shown = bool(recorded)
    from . import exposure
    withheld = exposure.sample_withheld(state, entries, drawn['seed'] if drawn else None)
    target = case.target_column
    columns = ([target] if shown else []) + [n for n in case.column_names if n != target]
    return {'columns': columns, 'n_rows': len(keys), 'order': ROWS_ORDER,
            'items': [{'row_key': k,
                       'values': {col: _plain(frame.at[k, col]) for col in columns}}
                      for k in keys],
            'seed': drawn['seed'] if drawn else None, 'target_shown': shown,
            'exposure': {'exposure_id': recorded[0]['exposure_id'] if shown else None,
                         'purpose': partition.SAMPLE_PURPOSE, 'recorded': shown,
                         # Why the target stays hidden for good (the split was confirmed
                         # before the study recorded the look), or null.
                         'withheld': withheld}}


def _special_rows(case, frame, special_masks: Mapping[str, list]) -> dict:
    """``special_rows`` (:data:`SPECIAL_ROW_KEYS`, contract P1.10): every development row
    holding at least one declared special value of a column other than the target (matched
    as the dictionary counts them), in row-key order, at most :data:`SPECIAL_ROWS_MAX`, each
    without the target. A structural anomaly, not what is predicted: no exposure beyond
    ``init``'s structural inspection."""
    target = case.target_column
    columns = [n for n in case.column_names if n != target]
    found: dict[str, list[dict]] = {}
    for name in columns:
        for value, mask in special_masks.get(name, []):
            for key in mask[mask].index:
                found.setdefault(key, []).append({'column': name, 'value': value})
    keys = sorted(found, key=lambda k: int(str(k)[1:]))
    return {'columns': columns, 'n_rows': len(keys),
            'items': [{'row_key': k,
                       'values': {col: _plain(frame.at[k, col]) for col in columns},
                       'specials': found[k]} for k in keys[:SPECIAL_ROWS_MAX]],
            'truncated': len(keys) > SPECIAL_ROWS_MAX}


def card(study_dir) -> dict:
    """The ``hypotrail.data/1`` payload of the study at ``study_dir``."""
    from . import case as c
    from . import data as dt
    from . import partition, read
    from .activities import matches

    from . import junior, assurance, l10n
    from . import state as st
    study = read.open(study_dir)
    state = study.state
    language = st.language_of(state)
    case = c.case_of(state, verify_data=True)
    # L3 (R4, T4-T6; D4b): every case statement the card shows carries ``texts`` ({en, fr}):
    # the case's words and their French form from the case's translation sidecar (null when
    # the study recorded none).
    tr = l10n.translations(state, case.document)
    keys = partition.development_keys(study.blob, partition.inputs(state))
    dataset = dt.load_development(case, keys)
    frame = dataset.frame
    target = case.target_column
    na_values = case.dataset.get('na_values', ())
    availability = state['decisions']['feature_availability']
    decided = availability['value'] if isinstance(availability['value'], dict) else {}
    groups: dict[str, list[dict]] = {}
    special_masks: dict[str, list] = {}
    for v in case.document['variables']:
        name = v['name']
        values = frame[name]
        specials, special_mask = [], values.isna() & False
        for s in v['special_values']:
            mask = matches(values, s['value'], na_values) & ~special_mask
            special_mask |= mask
            special_masks.setdefault(name, []).append((s['value'], mask))
            specials.append({'value': s['value'], 'meaning': s['meaning'], 'status': s['status'],
                             'n_rows': int(mask.sum()),
                             'texts': l10n.pair(s['meaning'],
                                                tr.meaning(name, s['value'], l10n.FR))})
        ordinary = values[~special_mask & values.notna()]
        examples = []
        for x in ordinary.tolist():
            x = _plain(x)
            if x not in examples:
                examples.append(x)
            if len(examples) == N_EXAMPLES:
                break
        a = v['availability']
        item = {'name': name, 'role': v['role'], 'type': v['type'], 'unit': v.get('unit'),
                'description': v['description'],
                'description_fr': (v.get('labels') or {}).get('fr'),
                'availability': {'value': a['value'], 'status': a['status'],
                                 'source': a['source'],
                                 'texts': l10n.pair(a['source'],
                                                    tr.availability_source(name, l10n.FR))},
                'decided': ({'status': availability['status'], 'value': decided.get(name)}
                            if name in decided else None),
                'special_values': specials, 'n_missing': int(values.isna().sum()),
                # WP-A9 (M4): distinct ordinary values, special values and missing cells
                # apart, as ``eda.quality`` counts them (``cardinality.n_distinct``).
                'n_distinct': int(ordinary.nunique(dropna=True)), 'examples': examples}
        groups.setdefault(v.get('group') or UNGROUPED, []).append(item)
    rows = sample_rows(study, frame, case)
    special_rows = _special_rows(case, frame, special_masks)
    final = partition.final_test_status(state)
    target_doc = case.document['target']
    variable = case.variables[target]
    payload = {
        'schema': SCHEMA, 'ok': True, 'study': str(study.study_dir), 'revision': study.revision,
        'observation_unit': _observation_unit(state, tr),
        'development': {'rows': int(len(frame)), 'columns': len(case.column_names),
                        'partition': 'development' if keys is not None else 'all',
                        # v0.2b (WP-B3): groups of identical records and the case's policy.
                        'duplicates': _duplicates(case, dataset, language)},
        'target': {'column': target, 'task': case.task,
                   'positive_label': target_doc.get('positive_label'),
                   'negative_label': target_doc.get('negative_label'),
                   'unit': variable.get('unit'), 'description': variable['description'],
                   'description_fr': (variable.get('labels') or {}).get('fr')},
        'final_test': _final_test_line(final, language),
        'groups': [{'group': g, 'variables': items,
                    'texts': l10n.pair(g, tr.group(g, l10n.FR)
                                       or (junior.UNGROUPED_FR if g == UNGROUPED else None))}
                   for g, items in groups.items()],
        'rows': rows,
        'note': {'text': NOTE, 'audience': 'junior',
                 'junior_text': junior.DATA_NOTE_FR if language == 'fr' else NOTE},
        'special_rows': special_rows,
    }
    payload['note']['text'] = ' '.join(filter(None, (
        NOTE, assurance.scope_notice(case))))
    payload['note']['junior_text'] = ' '.join(filter(None, (
        junior.DATA_NOTE_FR if language == 'fr' else NOTE,
        assurance.scope_notice(case, language))))
    assert tuple(payload) == PAYLOAD_KEYS
    return payload


def main(args: argparse.Namespace):
    from . import commands as cmd
    return cmd.Outcome(card(args.study))


# L3 (owner session 2026-10-26, R4): the labels of the text card of a French study.
TEXT_WORDS = {
    'en': {'one_row': 'One row', 'not_stated': 'not stated by the case',
           'development': 'Development rows: {rows}, columns: {columns}', 'target': 'Target',
           'in': 'in', 'availability': 'availability (case)', 'special': 'special value',
           'rows': 'rows', 'missing': 'missing {missing}, distinct {distinct}, examples ',
           'first': '{n} development rows drawn at random, target included (a counted look '
                    'at the target), seed {seed}:',
           'hidden': '{n} development rows drawn at random, seed {seed}; their target is shown '
                     'once a write records the look:',
           'withheld': '{n} development rows drawn at random, seed {seed}, without their '
                       'target: the split was confirmed before this study recorded a look at '
                       'them, so they are not shown with their target:', 'row': 'row'},
    'fr': {'one_row': 'Une ligne', 'not_stated': 'non indiqué par le cas',
           'development': "Lignes de l'échantillon de développement : {rows}, colonnes : "
                          "{columns}", 'target': 'Cible', 'in': 'en',
           'availability': 'disponibilité (selon le cas)', 'special': 'valeur spéciale',
           'rows': 'lignes', 'missing': 'manquants {missing}, distincts {distinct}, exemples ',
           'first': '{n} lignes de développement tirées au hasard, cible comprise (un regard '
                    'compté sur la cible), graine {seed} :',
           'hidden': '{n} lignes de développement tirées au hasard, graine {seed} ; leur cible '
                     "s'affiche quand une écriture enregistre ce regard :",
           'withheld': '{n} lignes de développement tirées au hasard, graine {seed}, sans leur '
                       "cible : le découpage a été confirmé avant que l'étude n'enregistre un "
                       "regard sur elles, elles ne sont donc pas montrées avec leur cible :",
           'row': 'ligne'},
}


def _language_of(payload: Mapping) -> str:
    """The study language of a card: French when its note is given in another text than the
    English source (``junior_text``, WP-C)."""
    note = payload.get('note') or {}
    return 'fr' if note.get('junior_text') and note['junior_text'] != note.get('text') else 'en'


def text(payload: Mapping) -> str:
    """The data card as readable text (``--format text``; not a contract), in the study
    language (L3): a French study reads the case's statements in French where the case's
    translation sidecar gives them (``texts.fr``) and the descriptions' ``description_fr``."""
    lang = _language_of(payload)
    w = TEXT_WORDS[lang]

    def say(node, english):
        return ((node or {}).get('texts') or {}).get(lang) or english
    unit = payload['observation_unit'] or {}
    dev = payload['development']
    t = payload['target']
    junior = lang != 'en'
    colon = ' : ' if junior else ': '
    lines = [f'{w["one_row"]}{colon}{say(unit, unit.get("value")) or w["not_stated"]}',
             w['development'].format(rows=dev['rows'], columns=dev['columns']),
             dev['duplicates']['junior_text'] if junior else dev['duplicates']['line']]
    description = (t.get('description_fr') if junior else None) or t['description']
    if t['task'] == 'binary':
        labels = ' / '.join(str(x) for x in (t['positive_label'], t['negative_label'])
                            if x is not None)
        lines.append(f'{w["target"]}{colon}{t["column"]} ({labels}){colon}{description}')
    else:
        lines.append(f'{w["target"]}{colon}{t["column"]} ({w["in"]} {t["unit"]}){colon}'
                     f'{description}')
    final = payload['final_test']
    lines.append(final['junior_text'] if junior else final['line'])
    for g in payload['groups']:
        lines.append('')
        lines.append(f'## {say(g, g["group"])}')
        for v in g['variables']:
            unit_text = f', {v["unit"]}' if v['unit'] else ''
            shown = (v['description_fr'] if junior else None) or v['description']
            lines.append(f'- {v["name"]} ({v["type"]}{unit_text}, {v["role"]}){colon}{shown}')
            if v['description_fr'] and not junior:
                lines.append(f'    fr: {v["description_fr"]}')
            if v['role'] == 'feature':
                a = v['availability']
                lines.append(f'    {w["availability"]}{colon}{a["value"]} [{a["status"]}] - '
                             f'{say(a, a["source"])}')
            for s in v['special_values']:
                lines.append(f'    {w["special"]} {s["value"]!r}{colon}{say(s, s["meaning"])} '
                             f'({s["n_rows"]} {w["rows"]})')
            lines.append(w['missing'].format(missing=v['n_missing'], distinct=v['n_distinct'])
                         .join(['    ', '']) + ', '.join(repr(x) for x in v['examples']))
    lines.append('')
    rows = payload['rows']
    lines.append(w['first' if rows.get('target_shown') else
                   'withheld' if (rows.get('exposure') or {}).get('withheld') else 'hidden'].format(
        n=rows['n_rows'], seed=rows.get('seed')))
    lines.append(' | '.join([w['row']] + rows['columns']))
    for r in rows['items']:
        lines.append(' | '.join([r['row_key']] + [str(r['values'][c]) for c in rows['columns']]))
    lines.append('')
    lines.append(payload['note']['junior_text'] if junior else payload['note']['text'])
    return '\n'.join(lines)
