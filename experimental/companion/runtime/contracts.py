"""Versioned companion contracts: registry, project, journey, results.

All validation happens in the engine. Configuration is JSON data and is never executed.
"""
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent
PROJECTS_ROOT = ROOT / 'projects'
JOURNEYS_ROOT = ROOT / 'journeys'
SHARED_DATA = ROOT / 'data'

SCHEMAS = {'registry': 'hypotrail.registry/1', 'project': 'hypotrail.project/1', 'journey': 'hypotrail.journey/1', 'results': 'hypotrail.results/1'}
COMPONENTS = {'objective', 'examples_table', 'variable_dictionary', 'distribution', 'choice_question', 'numeric_selection', 'model_comparison',
              'metrics', 'error_view', 'limits', 'choice_summary', 'clarifications', 'text', 'details', 'data_explorer'}
CHOICE_KINDS = {'choice_question', 'numeric_selection', 'result_choice'}
FACT_STATUS = {'unknown', 'proposed', 'confirmed'}
ROLES = {'identifier', 'feature', 'target', 'time', 'group', 'excluded'}
AVAILABILITY = {'yes', 'no', 'unknown'}
REQUIRED_FACTS = ('target', 'observation_unit', 'intended_use', 'decision', 'prediction_time')
DEPENDENCIES = {'dataset.content', 'dataset.schema'}
FORBIDDEN_KEYS = {'command', 'exec', 'shell', 'run', 'eval', 'script_inline'}
SLUG = re.compile(r'[a-z0-9][a-z0-9-]{0,63}')
KEY = re.compile(r'[a-z][a-z0-9_]{0,39}')
PLACEHOLDER = re.compile(r'\{\{([a-z]):([A-Za-z0-9_.\-]+)\}\}')


class ContractError(ValueError):
    def __init__(self, code, message, status=422):
        super().__init__(message); self.code = code; self.status = status


def fail(code, message): raise ContractError(code, message)
def need(condition, code, message):
    if not condition: fail(code, message)
def sha256_file(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def digest(obj): return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


def read_json(path, kind):
    try: data = json.loads(Path(path).read_text())
    except (OSError, ValueError) as e: fail('config', f'{kind} illisible : {Path(path).name} ({e.__class__.__name__}).')
    need(isinstance(data, dict), 'config', f'{kind} : objet JSON expected.')
    need(data.get('schema') == SCHEMAS[kind], 'schema_version', f'{kind}: unknown schema version ({data.get("schema")!r}), expected {SCHEMAS[kind]}.')
    reject_code(data, kind)
    return data


def reject_code(node, kind, where='racine'):
    if isinstance(node, dict):
        for key, value in node.items():
            need(key not in FORBIDDEN_KEYS, 'config', f'{kind}: forbidden key « {key} » forbidden ({where}); configuration cannot contain commands.')
            reject_code(value, kind, key)
    elif isinstance(node, list):
        for value in node: reject_code(value, kind, where)


def inside(path, roots):
    resolved = path.resolve()
    return any(resolved == r.resolve() or r.resolve() in resolved.parents for r in roots)


def registry(projects_root=None):
    root = Path(projects_root or PROJECTS_ROOT)
    data = read_json(root / 'registry.json', 'registry')
    entries = data.get('projects')
    need(isinstance(entries, list) and entries, 'config', 'Registry empty.')
    seen = set()
    for entry in entries:
        need(isinstance(entry, dict) and set(entry) <= {'id', 'dir', 'default'}, 'config', 'Invalid registry entry.')
        need(isinstance(entry.get('dir'), str) and SLUG.fullmatch(entry['dir']), 'path_forbidden', f'Project directory not allowed: {entry.get("dir")!r}.')
        need(isinstance(entry.get('id'), str) and entry['id'] not in seen, 'config', 'Missing or duplicate project identifier.')
        seen.add(entry['id'])
    return entries


def project_dir(project_id=None, projects_root=None):
    root = Path(projects_root or PROJECTS_ROOT)
    entries = registry(root)
    entry = next((e for e in entries if e['id'] == project_id), None) if project_id else next((e for e in entries if e.get('default')), entries[0])
    need(entry is not None, 'project', f'Unknown project: {project_id!r}.')
    folder = root / entry['dir']
    need(inside(folder, [root]), 'path_forbidden', 'Project directory is outside the allowed scope.')
    return entry, folder


# Formatting shared with narrative text.
def fmt_number(value, digits): return f'{value:.{digits}f}'

def format_metric(value, definition):
    kind = definition.get('format', 'number:2')
    if value is None: return 'unavailable'
    if kind == 'percent': return fmt_number(100 * value, 1) + ' %'
    if kind == 'count': return str(int(value))
    digits = int(kind.split(':')[1]) if kind.startswith('number:') else 2
    unit = definition.get('unit') or ''
    return fmt_number(value, digits) + ('' if unit.startswith('unitless') or not unit else ' ' + unit)


def format_choice(value, spec):
    if spec.get('kind') == 'numeric_selection':
        kind = spec.get('format', 'number:2')
        digits = int(kind.split(':')[1]) if kind.startswith('number:') else 2
        return f"{spec.get('short_label') or spec['label'].lower()} {fmt_number(value, digits)}"
    if spec.get('kind') == 'result_choice': return next(o['label'] for o in spec['domain'] if o['value'] == value)
    return spec['options'][value]['label']


def resolve(text, ctx, where):
    def lookup(match):
        kind, ref = match.groups()
        try:
            if kind == 'd': value = ctx['project']['dataset'][ref]
            elif kind == 'g': value = ctx['results']['generated_by'][ref]
            elif kind == 'p':
                pid, field = ref.rsplit('.', 1); value = next(p for p in ctx['results']['protocols'] if p['id'] == pid)['partition'][field]
            elif kind == 'r':
                rid, metric = ref.rsplit('.', 1); result = next(r for r in ctx['results']['results'] if r['id'] == rid)
                return format_metric(result['metrics'][metric], ctx['results']['metric_definitions'][metric])
            elif kind == 'x':
                value = ctx['results']['display']
                for part in ref.split('.'): value = value[part]
            else: raise KeyError(kind)
        except (KeyError, StopIteration, ValueError, TypeError):
            fail('placeholder', f'Unknown reference {match.group(0)} in {where}.')
        return str(value)
    return PLACEHOLDER.sub(lookup, text)


def resolve_all(node, ctx, where='project'):
    if isinstance(node, str): return resolve(node, ctx, where)
    if isinstance(node, list): return [resolve_all(v, ctx, where) for v in node]
    if isinstance(node, dict): return {k: resolve_all(v, ctx, f'{where}.{k}') for k, v in node.items()}
    return node


# ---- validation ----
def validate_results(results, project):
    need(results.get('project_id') == project['id'], 'results_other_project', f'Results belong to another project ({results.get("project_id")!r}).')
    need(isinstance(results.get('dataset'), dict) and results['dataset'].get('id') == project['dataset']['id'], 'results_other_dataset',
         f'Results reference another dataset ({(results.get("dataset") or {}).get("id")!r}).')
    definitions = results.get('metric_definitions')
    need(isinstance(definitions, dict), 'metric_missing', 'Missing metric definitions.')
    for name, d in definitions.items():
        need(isinstance(d, dict) and d.get('label') and 'unit' in d and d.get('unit'), 'unit_missing', f'Metric {name}: missing label or unit.')
    protocols = {p.get('id'): p for p in results.get('protocols', []) if isinstance(p, dict)}
    need(protocols, 'config', 'No declared protocol.')
    for p in protocols.values():
        need(p.get('scope') in {'exploratory', 'confirmatory', 'counterexample'} and p.get('scope_justification'), 'config', f'Protocol {p.get("id")}: missing scope or justification.')
    ids = set()
    for r in results.get('results', []):
        need(isinstance(r, dict) and isinstance(r.get('id'), str) and r['id'] not in ids, 'config', 'Result has no unique identifier.')
        ids.add(r['id'])
        need(r.get('protocol') in protocols, 'config', f'Result {r["id"]} : unknown protocol.')
        need(r.get('status') in {'available', 'stale', 'absent', 'error'}, 'config', f'Result {r["id"]} : invalid status.')
        need(r.get('scope') in {'exploratory', 'confirmatory', 'counterexample'}, 'config', f'Result {r["id"]}: invalid scope.')
        need(isinstance(r.get('observations'), int) and r.get('method') and r.get('provenance'), 'config', f'Result {r["id"]}: missing method, provenance, or sample size.')
        for metric in r.get('metrics', {}):
            need(metric in definitions, 'metric_missing', f'Result {r["id"]}: metric {metric} has no definition.')
    return ids


def validate(project, journey, results, folder):
    need(isinstance(project.get('id'), str) and project['id'], 'config', 'Project has no identifier.')
    need(isinstance(project.get('session_name'), str) and SLUG.fullmatch(project['session_name']), 'config', 'session_name invalid.')
    for field in ('title', 'description', 'language', 'problem_type'):
        need(isinstance(project.get(field), str) and project[field], 'config', f'Missing project field: {field}.')
    need(project['problem_type'] in journey.get('problem_types', []), 'journey_incompatible', f'Journey {journey.get("id")} does not support type {project["problem_type"]}.')
    ref = project.get('journey') or {}
    need(ref.get('id') == journey.get('id') and ref.get('version') == journey.get('version'), 'journey_incompatible', 'Journey version differs from the project version.')
    dataset = project.get('dataset') or {}
    for field in ('id', 'name', 'path', 'sha256', 'rows', 'provenance'):
        need(field in dataset, 'config', f'Dataset : champ missing {field}.')
    for field in ('license', 'source_url', 'authors'):
        need(dataset['provenance'].get(field), 'config', f'Provenance : champ missing {field}.')
    path = Path(dataset['path'])
    need(not path.is_absolute() and inside(folder / path, [folder, SHARED_DATA]), 'path_forbidden', f'Data path not allowed: {dataset["path"]}.')
    facts = {f.get('id'): f for f in project.get('facts', []) if isinstance(f, dict)}
    for fact in facts.values():
        need(fact.get('status') in FACT_STATUS and fact.get('label') and fact.get('source') is not None, 'config', f'Information {fact.get("id")}: invalid status, label, or source.')
        need(set(fact.get('depends_on', [])) <= DEPENDENCIES, 'config', f'Information {fact.get("id")}: unknown dependency.')
    need('target' in facts and facts['target'].get('value'), 'target_missing', 'Target missing from the project definition.')
    for required in REQUIRED_FACTS:
        need(required in facts, 'config', f'Information required missing : {required} (unknown is allowed; omission is not).')
    variables = project.get('variables', [])
    names = set()
    for v in variables:
        need(isinstance(v, dict) and v.get('name') and v.get('label') and v.get('type'), 'config', 'Incomplete variable definition.')
        need(v.get('role') in ROLES and v.get('available_at_prediction') in AVAILABILITY and v.get('status') in FACT_STATUS, 'config', f'Variable {v.get("name")}: invalid role, availability, or status.')
        names.add(v['name'])
    need(any(v['role'] == 'target' for v in variables), 'target_missing', 'No variable has the target role.')
    result_ids = validate_results(results, project)
    definitions = results['metric_definitions']
    contents = project.get('activities') or {}
    choices = {}
    for activity in journey.get('activities', []):
        aid = activity.get('id')
        need(isinstance(aid, str) and SLUG.fullmatch(aid), 'config', 'Activity has no stable identifier.')
        unsupported = set(activity.get('components', [])) - COMPONENTS
        need(not unsupported, 'component_unknown', f'Activity {aid} : unsupported component {sorted(unsupported)}.')
        need(set(activity.get('requires', [])) <= set(facts), 'config', f'Activity {aid}: unknown prerequisite.')
        content = contents.get(aid)
        need(isinstance(content, dict) and content.get('title') and content.get('objective'), 'config', f'Activity {aid}: project content missing.')
        blocks = content.get('blocks', [])
        kinds = {b.get('component') for b in blocks if isinstance(b, dict)}
        unknown = kinds - COMPONENTS
        need(not unknown, 'component_unknown', f'Activity {aid} : unknown component {sorted(unknown)}.')
        missing = set(activity.get('components', [])) - kinds - {'objective'}
        need(not missing, 'component_missing', f'Activity {aid} : missing required component {sorted(missing)}.')
        expected = activity.get('choice')
        found = []
        for b in blocks:
            if b['component'] == 'data_explorer':
                eda = results.get('display', {}).get(b.get('source'))
                need(isinstance(eda, dict) and eda.get('scope') == 'train_only' and eda.get('rows', 0) > 0, 'config', 'Exploration requires training scope.')
                need(eda.get('dataset_sha256') == project['dataset']['sha256'], 'config', 'Exploration dataset fingerprint mismatch.')
                for chart in eda.get('charts', []):
                    need(chart.get('kind') in {'bars', 'scatter'} and chart.get('title') and chart.get('unit'), 'config', 'Graphique invalid.')
            elif b['component'] == 'choice_question':
                need(KEY.fullmatch(b.get('key', '')) and isinstance(b.get('options'), list) and len(b['options']) >= 2, 'config', f'Activity {aid} : invalid question.')
                found.append({'kind': 'choice_question', 'key': b['key'], 'activity': aid, 'options': b['options'], 'label': b.get('question', '')})
            elif b['component'] == 'numeric_selection':
                found.append({'kind': 'numeric_selection', 'activity': aid, **{k: b[k] for k in ('key', 'label', 'short_label', 'domain', 'compute') if k in b}, 'format': b.get('format', 'number:2'), 'unit': b.get('unit')})
            elif b['component'] == 'model_comparison':
                for item in b.get('results', []): need(item.get('id') in result_ids, 'result_missing', f'Activity {aid}: unknown result {item.get("id")}.')
                for metric in b.get('metrics', []): need(metric in definitions, 'metric_missing', f'Activity {aid}: required metric has no definition: {metric}.')
                if b.get('choice'):
                    found.append({'kind': 'result_choice', 'activity': aid, **b['choice'],
                                  'domain': [{**o, 'label': next((i['label'] for i in b['results'] if i['id'] == o['value']), o['value'])} for o in b['choice'].get('domain', [])]})
            elif b['component'] in ('metrics', 'error_view'):
                for metric in b.get('metrics', []) + b.get('summary', []) + ([b['metric']] if b.get('metric') else []):
                    need(metric in definitions, 'metric_missing', f'Activity {aid}: required metric has no definition: {metric}.')
        need(len(found) == (1 if expected else 0) and (not found or found[0]['kind'] == expected), 'config', f'Activity {aid} : choice expected {expected}, found {[f["kind"] for f in found]}.')
        for spec in found:
            need(KEY.fullmatch(spec.get('key', '')) and spec['key'] not in choices, 'config', f'Invalid or duplicate choice key: {spec.get("key")}.')
            if spec['kind'] in ('numeric_selection', 'result_choice'):
                need(spec.get('compute') in {'precomputed', 'not_available'} and isinstance(spec.get('domain'), list) and spec['domain'], 'config', f'Choice {spec["key"]} : invalid domain or calculation mode.')
                for option in spec['domain']:
                    if spec['compute'] == 'precomputed':
                        need(option.get('result') in result_ids, 'result_missing', f'Choice {spec["key"]}: missing result {option.get("result")}.')
                if spec['kind'] == 'numeric_selection':
                    need(all(type(o.get('value')) in (int, float) for o in spec['domain']), 'config', f'Choice {spec["key"]}: numeric values expected.')
            choices[spec['key']] = spec
    extra = set(contents) - {a['id'] for a in journey['activities']}
    need(not extra, 'config', f'Unknown journey activities: {sorted(extra)}.')
    legacy = (project.get('compatibility') or {}).get('legacy_steps')
    if legacy is not None:
        need(set(legacy) <= {a['id'] for a in journey['activities']}, 'config', 'Invalid historical page mapping.')
    return choices


def fingerprints(project, folder, results):
    dataset = project['dataset']
    path = folder / dataset['path']
    # When data is absent from an installed bundle, use the declared fingerprint.
    actual = sha256_file(path) if path.is_file() else dataset['sha256']
    schema = digest([[v['name'], v['type'], v['role']] for v in project['variables']])
    return {'dataset.content': actual, 'dataset.schema': schema, 'declared_content': dataset['sha256'], 'results_dataset': results['dataset'].get('sha256')}


def load_bundle(project_id=None, projects_root=None):
    entry, folder = project_dir(project_id, projects_root)
    project = read_json(folder / 'project.json', 'project')
    need(project.get('id') == entry['id'], 'config', 'Project identifier differs from the registry entry.')
    ref = project.get('journey') or {}
    need(isinstance(ref.get('id'), str) and SLUG.fullmatch(ref['id']), 'path_forbidden', 'Journey is not allowed.')
    journey = read_json(JOURNEYS_ROOT / f'{ref["id"]}.json', 'journey')
    results = read_json(folder / 'results.json', 'results')
    choices = validate(project, journey, results, folder)
    prints = fingerprints(project, folder, results)
    changed = prints['dataset.content'] != prints['declared_content'] or prints['results_dataset'] != prints['declared_content']
    for r in results['results']:
        if changed and r['status'] == 'available':
            r['status'] = 'stale'
            r['status_reason'] = 'Data changed since calculation: recomputation required.'
        r['display'] = {k: format_metric(v, results['metric_definitions'][k]) for k, v in r['metrics'].items()}
    ctx = {'project': project, 'results': results}
    project = resolve_all({k: v for k, v in project.items() if k != 'activities'}, ctx) | {'activities': resolve_all(project['activities'], ctx, 'activities')}
    for spec in choices.values():
        spec['label'] = resolve(spec.get('label', ''), ctx, spec['key'])
        if spec['kind'] == 'numeric_selection':
            for option in spec['domain']: option['label'] = format_choice(option['value'], spec)
    # Result dependencies are hashed; editing a title or explanation does not change the hash.
    context = digest({'dataset': prints['dataset.content'], 'protocols': results['protocols'],
                      'results': [[r['id'], r['configuration'], r['metrics'], r['status']] for r in results['results']]})
    return {'entry': entry, 'folder': folder, 'project': project, 'journey': journey, 'results': results, 'choices': choices,
            'fingerprints': prints, 'dataset_changed': changed, 'context_hash': context}
