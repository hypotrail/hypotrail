"""The "Variants and model families" section of the HTML report (v0.3, WP-F1, ADR 0007).

Fed by the view only. Every number is cited from the registry (:class:`mlkit.study.cite.Citer`):
the selection among the configurations from the ``selection`` the current evaluation stored
(``policy.evaluation`` or ``evaluate.regression``), the tuning and each family's own
diagnostics from the variants' fit results, the flags of the linear fit from the current
development diagnostics. Counts that describe the study rather than a result (the variant
budget) are recorded literals. Headings and sentences follow the study language (English or
French).

Pure: no pandas, numpy, or scikit-learn.
"""
from __future__ import annotations

import html
from typing import Any, Mapping

from . import audience, cite, trials

e = html.escape
MAX_TERMS = 8

LABELS = {
    'en': {
        'heading': 'Variants and model families',
        'intro': 'The candidate model and the variants you named, compared on the same folds. '
                 'Each variant is one trial of the budget; the final test is not affected by '
                 'this choice.',
        'budget': 'Variant budget',
        'budget_text': 'variants confirmed out of',
        'legacy': 'This study named its variant before v0.3: it counts as one variant of the '
                  'budget.',
        'shortlist': 'Which model families are worth a trial?',
        'flags': 'What the diagnostics of the linear model flagged',
        'no_flags': 'Nothing was flagged.',
        'excluded': 'Excluded',
        'selection': 'The configurations compared fold by fold',
        'metric': {'roc_auc': 'Out-of-fold AUC by fold (mean, standard error)',
                   'mae': 'Out-of-fold MAE by fold (mean, standard error)'},
        'cols': ['Configuration', 'Question', 'Mean', 'Standard error',
                 'Difference with the candidate (± one standard error)',
                 'Within one standard error of the best'],
        'one_se': 'One-standard-error rule',
        'pick': 'pick',
        'best': 'best mean',
        'optimism': 'Approximate selection optimism',
        'advice': 'Advice',
        'tuning': 'Hyperparameter chosen in each outer fold (nested cross-validation)',
        'tuning_cols': ['Configuration', 'Parameter', 'Fold', 'Value chosen'],
        'ebm': 'Shape functions of the Explainable Boosting Machine',
        'ebm_cols': ['Term', 'Kind', 'Importance'],
        'hgb': 'Permutation importance of the gradient boosting model (out of fold)',
        'hgb_cols': ['Input column', 'Importance'],
        'pending': 'No evaluation compares the variants yet: the comparison appears once the '
                   'variants are fitted and evaluated.',
        'candidate': 'the candidate', 'yes': 'yes', 'no': 'no',
        'main': 'feature', 'interaction': 'interaction',
    },
    'fr': {
        'heading': 'Variantes et familles de modèles',
        'intro': 'Le modèle candidat et les variantes que vous avez nommées, comparés sur les '
                 'mêmes plis. Chaque variante est un essai du budget ; le test final ne dépend '
                 'pas de ce choix.',
        'budget': 'Budget de variantes',
        'budget_text': 'variantes confirmées sur',
        'legacy': "Cette étude a nommé sa variante avant la v0.3 : elle compte pour une "
                  'variante du budget.',
        'shortlist': 'Quelles familles de modèles méritent un essai ?',
        'flags': 'Ce que les diagnostics du modèle linéaire ont signalé',
        'no_flags': "Rien n'a été signalé.",
        'excluded': 'Exclue',
        'selection': 'Les configurations comparées pli par pli',
        'metric': {'roc_auc': 'AUC hors pli par pli (moyenne, erreur type)',
                   'mae': 'MAE hors pli par pli (moyenne, erreur type)'},
        'cols': ['Configuration', 'Question', 'Moyenne', 'Erreur type',
                 'Écart avec le candidat (± une erreur type)',
                 "À moins d'une erreur type de la meilleure"],
        'one_se': "Règle d'une erreur type",
        'pick': 'retenue',
        'best': 'meilleure moyenne',
        'optimism': 'Optimisme approximatif de la sélection',
        'advice': 'Conseil',
        'tuning': 'Hyperparamètre choisi dans chaque pli externe (validation croisée imbriquée)',
        'tuning_cols': ['Configuration', 'Paramètre', 'Pli', 'Valeur choisie'],
        'ebm': "Fonctions de forme de l'Explainable Boosting Machine",
        'ebm_cols': ['Terme', 'Type', 'Importance'],
        'hgb': 'Importance par permutation du gradient boosting (hors pli)',
        'hgb_cols': ['Colonne', 'Importance'],
        'pending': "Aucune évaluation ne compare encore les variantes : la comparaison apparaît "
                   'une fois les variantes ajustées et évaluées.',
        'candidate': 'le candidat', 'yes': 'oui', 'no': 'non',
        'main': 'variable', 'interaction': 'interaction',
    },
}
CHECK_WORDS = {'en': {'nonlinearity': 'a shape the linear model does not follow',
                      'interaction': 'a score whose effect differs by group (an interaction)',
                      'calibration_slope': 'scores too extreme or too flat (calibration slope)'},
               'fr': {'nonlinearity': 'une forme que le modèle linéaire ne suit pas',
                      'interaction': 'un score dont l\'effet change selon le groupe (une '
                                     'interaction)',
                      'calibration_slope': 'des scores trop extrêmes ou trop plats (pente de '
                                           'calibration)'}}


def _lit(kind: str, text: Any, tag: str = 'span') -> str:
    return f'<{tag} data-literal="{kind}">{e(str(text))}</{tag}>'


def _num(citer: cite.Citer, rid: str, path: list, fmt: str = 'auto') -> str:
    p = cite.format_path(path)
    return citer.num(rid, p, fmt) if citer.has(rid, p) else ''


def _table(head: list[str], rows: list[str], cls: str = '') -> str:
    th = ''.join(f'<th>{e(h)}</th>' for h in head)
    klass = f' class="{cls}"' if cls else ''
    return (f'<div class="scroll"><table{klass}><thead><tr>{th}</tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div>')


def _name(slot: str, words: str | None, lab: Mapping) -> str:
    if words:
        return words
    if slot in ('fit.logistic', 'fit.linear'):
        return lab['candidate']
    return audience.model_words(slot)


def _shortlist(view: Mapping, citer: cite.Citer, lab: Mapping, lang: str) -> str:
    fam = view.get('model_families') or {}
    if not fam:
        return ''
    parts = [f'<h3>{e(lab["shortlist"])}</h3>',
             f'<p data-shortlist="{e(str(fam.get("recommendation")))}">'
             f'{e((fam.get("texts") or {}).get(lang) or fam.get("text") or "")}</p>']
    items = []
    for f in fam.get('families') or []:
        mark = '' if f.get('allowed') else f' ({e(lab["excluded"])}: {e(f.get("excluded_reason") or "")})'
        listed = f.get('family') in (fam.get('shortlist') or [])
        items.append(f'<li data-family="{e(str(f.get("family")))}" '
                     f'data-listed="{"yes" if listed else "no"}">{e(f.get("words") or "")}'
                     f'{mark}</li>')
    parts.append(f'<ul>{"".join(items)}</ul>')
    evidence = fam.get('evidence') or {}
    rid = evidence.get('source')
    checks = evidence.get('checks') or {}
    if evidence.get('checked') and citer.citable(rid):
        rows = []
        for key in ('nonlinearity', 'interaction'):
            for i, c in enumerate(checks.get(key) or []):
                if not c.get('flagged'):
                    continue
                rows.append(f'<li data-check="{e(key)}">{e(CHECK_WORDS[lang][key])}: '
                            f'{_lit("identifier", c.get("feature", ""), "code")} (p '
                            f'{_num(citer, rid, ["linear_checks", key, str(i), "p_value"], "f4")})'
                            f'</li>')
        cal = checks.get('calibration_slope') or {}
        if cal.get('flagged'):
            rows.append(f'<li data-check="calibration_slope">{e(CHECK_WORDS[lang]["calibration_slope"])}: '
                        f'{_num(citer, rid, ["linear_checks", "calibration_slope", "slope"], "f2")}</li>')
        parts.append(f'<h4>{e(lab["flags"])}</h4>'
                     + (f'<ul>{"".join(rows)}</ul>' if rows
                        else f'<p class="muted">{e(lab["no_flags"])}</p>'))
    return ''.join(parts)


def _selection(view: Mapping, citer: cite.Citer, lab: Mapping, lang: str) -> str:
    slot = 'evaluate.regression' if view.get('task') == 'regression' else 'policy.evaluation'
    rid = citer.slot_rid(slot)
    values = citer.results[rid].values if rid else None
    sel = values.get('selection') if isinstance(values, Mapping) else None
    if not isinstance(sel, Mapping) or not sel.get('available'):
        return f'<p class="muted" data-selection="pending">{e(lab["pending"])}</p>'
    fmt = 'f3' if sel.get('metric') == 'roc_auc' else 'f2'
    rows = []
    for i, c in enumerate(sel.get('configurations') or []):
        p = ['selection', 'configurations', str(i)]
        diff = ''
        if c.get('difference'):
            d = p + ['difference']
            diff = (f'{_num(citer, rid, d + ["mean"], fmt)} '
                    f'<span class="small">[{_num(citer, rid, d + ["low"], fmt)}, '
                    f'{_num(citer, rid, d + ["high"], fmt)}]</span>')
        within = lab['yes'] if c.get('within_one_se') else lab['no']
        rows.append(f'<tr data-model="{e(str(c.get("slot")))}">'
                    f'<td>{e(_name(c.get("slot"), c.get("words"), lab))}</td>'
                    f'<td>{_lit("user_words", c.get("question") or "")}</td>'
                    f'<td>{_num(citer, rid, p + ["mean"], fmt)}</td>'
                    f'<td>{_num(citer, rid, p + ["se"], fmt)}</td>'
                    f'<td>{diff}</td><td>{_lit("category", within)}</td></tr>')
    one = sel.get('one_se') or {}
    configs = {c.get('slot'): c for c in sel.get('configurations') or []}
    pick = configs.get(one.get('pick')) or {}
    best = configs.get(one.get('best')) or {}
    opt = sel.get('optimism') or {}
    advice = sel.get('advice') or {}
    parts = [f'<h3>{e(lab["selection"])}</h3><p class="small">{e(lab["metric"][sel["metric"]])}</p>',
             _table(lab['cols'], rows, 'selection'),
             f'<p data-one-se="{e(str(one.get("pick")))}"><strong>{e(lab["one_se"])}:</strong> '
             f'{e(lab["pick"])} {e(_name(pick.get("slot"), pick.get("words"), lab))}, '
             f'{e(lab["best"])} {e(_name(best.get("slot"), best.get("words"), lab))}. '
             f'{e((one.get("texts") or {}).get(lang) or "")} '
             f'<span class="small">{_lit("message", one.get("source") or "")}</span></p>',
             f'<p data-optimism="estimate"><strong>{e(lab["optimism"])}:</strong> '
             f'{_num(citer, rid, ["selection", "optimism", "estimate"], fmt)}. '
             f'{e((opt.get("texts") or {}).get(lang) or "")} '
             f'<span class="small">{_lit("message", opt.get("source") or "")}</span></p>',
             f'<p class="notice" data-advice="{e(str(advice.get("code")))}"><strong>'
             f'{e(lab["advice"])}:</strong> {e((advice.get("texts") or {}).get(lang) or "")}</p>']
    return ''.join(parts)


def _tuning(view: Mapping, citer: cite.Citer, lab: Mapping) -> str:
    rows = []
    for slot in trials.VARIANT_SLOTS:
        rid = citer.slot_rid(slot)
        if rid is None:
            continue
        tuning = (citer.results[rid].values or {}).get('tuning')
        if not isinstance(tuning, Mapping):
            continue
        words = audience.model_words(slot)
        for i, f in enumerate(tuning.get('per_fold') or []):
            rows.append(f'<tr data-model="{e(slot)}"><td>{e(words)}</td>'
                        f'<td>{_lit("parameter", tuning.get("parameter", ""), "code")}</td>'
                        f'<td>{_lit("ordinal", f.get("fold"))}</td>'
                        f'<td>{_num(citer, rid, ["tuning", "per_fold", str(i), "value"])}</td>'
                        f'</tr>')
    if not rows:
        return ''
    return (f'<details class="diag-more"><summary><strong>{e(lab["tuning"])}</strong></summary>'
            + _table(lab['tuning_cols'], rows, 'tuning') + '</details>')


def _families(view: Mapping, citer: cite.Citer, lab: Mapping) -> str:
    parts = []
    for slot in trials.VARIANT_SLOTS:
        rid = citer.slot_rid(slot)
        if rid is None:
            continue
        fd = (citer.results[rid].values or {}).get('family_diagnostics')
        if not isinstance(fd, Mapping):
            continue
        words = audience.model_words(slot)
        if fd.get('kind') == 'ebm_terms':
            rows = []
            for i, t in enumerate((fd.get('terms') or [])[:MAX_TERMS]):
                kind = lab['interaction'] if t.get('kind') == 'interaction' else lab['main']
                rows.append(f'<tr><td>{_lit("identifier", t.get("term", ""), "code")}</td>'
                            f'<td>{_lit("category", kind)}</td>'
                            f'<td>{_num(citer, rid, ["family_diagnostics", "terms", str(i), "importance"], "f3")}</td></tr>')
            parts.append(f'<h4 data-model="{e(slot)}">{e(lab["ebm"])} ({e(words)})</h4>'
                         f'<p class="small">{_lit("message", fd.get("note") or "")}</p>'
                         + _table(lab['ebm_cols'], rows, 'ebm-terms'))
        elif fd.get('kind') == 'permutation_importance':
            rows = []
            for i, c in enumerate((fd.get('columns') or [])[:MAX_TERMS]):
                rows.append(f'<tr><td>{_lit("identifier", c.get("column", ""), "code")}</td>'
                            f'<td>{_num(citer, rid, ["family_diagnostics", "columns", str(i), "importance"], "f3")}</td></tr>')
            parts.append(f'<h4 data-model="{e(slot)}">{e(lab["hgb"])} ({e(words)})</h4>'
                         f'<p class="small">{_lit("message", fd.get("note") or "")}</p>'
                         + _table(lab['hgb_cols'], rows, 'permutation-importance'))
    return ''.join(parts)


def section(view: Mapping, citer: cite.Citer) -> str:
    """The section, or '' in a study without the variant decision."""
    if view.get('selection') is None and view.get('model_families') is None:
        return ''
    lang = view.get('language') if view.get('language') in LABELS else 'en'
    lab = LABELS[lang]
    budget = (view.get('selection') or {}).get('budget') or {}
    parts = [f'<section class="card" id="variants" lang="{lang}"><h2>{e(lab["heading"])}</h2>'
             f'<p>{e(lab["intro"])}</p>']
    if budget:
        parts.append(f'<p data-budget="{e(str(budget.get("used")))}"><strong>{e(lab["budget"])}:'
                     f'</strong> {_lit("structure", budget.get("used"))} {e(lab["budget_text"])} '
                     f'{_lit("structure", budget.get("max"))}.'
                     + (f' {e(lab["legacy"])}' if budget.get('legacy') else '') + '</p>')
    parts.append(_shortlist(view, citer, lab, lang))
    parts.append(_selection(view, citer, lab, lang))
    parts.append(_tuning(view, citer, lab))
    parts.append(_families(view, citer, lab))
    parts.append('</section>')
    return ''.join(p for p in parts if p)
