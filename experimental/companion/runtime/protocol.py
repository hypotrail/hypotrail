"""Companion engine: recorded choices, applied choices, and results stay distinct per project.

The current project comes from the registry (contracts.py). No historical project, network,
or training launcher is accessed; results come from the preparation adapters.
"""
from contextlib import closing
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import uuid

import contracts

ROOT = Path(__file__).resolve().parent
SCHEMA_VERSION = 3
# Legacy format: only Bank Marketing sessions existed before schema 3.
LEGACY_PROJECT_ID = 'uci-bank-marketing-v1'
# Limits are documented in the companion README.
LIMITS = {'question_chars': 4000, 'answer_chars': 20000, 'history_exchanges': 10, 'history_answer_chars': 1500, 'snapshot_exchanges': 50, 'chat_message_chars': 6000}
_bundle = None


class ProtocolError(ValueError):
    def __init__(self, code, message, status=400):
        super().__init__(message); self.code = code; self.status = status


def timestamp(): return dt.datetime.now(dt.timezone.utc).isoformat()
def canonical(obj): return json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def use_project(project_id=None, projects_root=None):
    global _bundle
    _bundle = contracts.load_bundle(project_id, projects_root)
    return _bundle


def bundle():
    return _bundle or use_project()


def context_hash(): return bundle()['context_hash']


def activities(): return [a['id'] for a in bundle()['journey']['activities']]


def activity_spec(activity_id): return next(a for a in bundle()['journey']['activities'] if a['id'] == activity_id)


def legacy_order():
    return (bundle()['project'].get('compatibility') or {}).get('legacy_steps') or activities()


def normalize(state):
    """Exercise state validated against the declared domain; convert the legacy {step} format."""
    if not isinstance(state, dict) or not isinstance(state.get('answers'), dict): return None
    if set(state) == {'activity', 'answers'}:
        if state['activity'] not in activities(): return None
        activity = state['activity']
    elif set(state) == {'step', 'answers'}:
        order = legacy_order()
        if type(state['step']) is not int or not 0 <= state['step'] < len(order): return None
        activity = order[state['step']]
    else:
        return None
    choices = bundle()['choices']
    for key, value in state['answers'].items():
        spec = choices.get(key)
        if spec is None: return None
        if spec['kind'] == 'choice_question':
            if type(value) is not int or not 0 <= value < len(spec['options']): return None
        elif spec['kind'] == 'numeric_selection':
            if type(value) not in (int, float) or value not in [o['value'] for o in spec['domain']]: return None
        elif type(value) is not str or value not in [o['value'] for o in spec['domain']]: return None
    return {'activity': activity, 'answers': state['answers']}


def valid(state): return normalize(state) is not None


def choice_label(key, value):
    return contracts.format_choice(value, bundle()['choices'][key])


EXCHANGES_V2 = '''CREATE TABLE IF NOT EXISTS assistant_exchanges (
    seq INTEGER PRIMARY KEY AUTOINCREMENT, exchange_id TEXT UNIQUE NOT NULL, request_hash TEXT NOT NULL,
    kind TEXT NOT NULL, source TEXT NOT NULL, status TEXT NOT NULL, session_id TEXT NOT NULL,
    context_hash TEXT NOT NULL, application_event_id TEXT, revision INTEGER NOT NULL, step INTEGER,
    subject TEXT NOT NULL, choice TEXT, question TEXT, answer TEXT NOT NULL DEFAULT '', model TEXT,
    error_code TEXT, error_message TEXT, attempts INTEGER NOT NULL DEFAULT 1, options TEXT,
    created TEXT NOT NULL, updated TEXT NOT NULL)'''
CONFIRMATIONS = '''CREATE TABLE IF NOT EXISTS fact_confirmations (seq INTEGER PRIMARY KEY AUTOINCREMENT, fact_id TEXT NOT NULL,
    decision TEXT NOT NULL, value TEXT, fingerprint TEXT NOT NULL, source TEXT NOT NULL, created TEXT NOT NULL)'''


def migrate(db, version):
    db.execute('BEGIN IMMEDIATE')
    version = db.execute('PRAGMA user_version').fetchone()[0]
    db.execute('CREATE TABLE IF NOT EXISTS schema_history (version INTEGER PRIMARY KEY, previous INTEGER, applied TEXT)')
    if version < 2:
        db.execute(EXCHANGES_V2)
        db.execute('INSERT OR IGNORE INTO schema_history VALUES(?,?,?)', (2, version, timestamp()))
    if version < 3:
        # v3: project, named activities, and confirmations. Map old pages through Bank Marketing legacy_steps.
        _, folder = contracts.project_dir(LEGACY_PROJECT_ID)
        order = contracts.read_json(folder / 'project.json', 'project')['compatibility']['legacy_steps']
        db.execute('ALTER TABLE companion_meta ADD COLUMN project_id TEXT')
        db.execute('UPDATE companion_meta SET project_id=? WHERE id=1', (LEGACY_PROJECT_ID,))
        db.execute('ALTER TABLE assistant_exchanges ADD COLUMN project_id TEXT')
        db.execute('ALTER TABLE assistant_exchanges ADD COLUMN activity TEXT')
        for seq, step in db.execute('SELECT seq,step FROM assistant_exchanges').fetchall():
            db.execute('UPDATE assistant_exchanges SET project_id=?,activity=? WHERE seq=?', (LEGACY_PROJECT_ID, order[step] if isinstance(step, int) and 0 <= step < len(order) else None, seq))
        payload = json.loads(db.execute('SELECT payload FROM session WHERE id=1').fetchone()[0])
        if 'step' in payload:
            step = payload['step'] if isinstance(payload['step'], int) and 0 <= payload['step'] < len(order) else 0
            db.execute('UPDATE session SET payload=? WHERE id=1', (canonical({'activity': order[step], 'answers': payload.get('answers', {})}),))
        db.execute(CONFIRMATIONS)
        db.execute('INSERT OR IGNORE INTO schema_history VALUES(?,?,?)', (3, version, timestamp()))
    db.execute(f'PRAGMA user_version={SCHEMA_VERSION}')
    db.commit()


def connect(path):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=5)
    existed = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='session'").fetchone() is not None
    if not existed:
        db.execute('BEGIN IMMEDIATE')
        db.execute('CREATE TABLE IF NOT EXISTS session (id INTEGER PRIMARY KEY, revision INTEGER, payload TEXT, message TEXT)')
        db.execute('INSERT OR IGNORE INTO session VALUES(1,0,?,?)', (canonical({'activity': activities()[0], 'answers': {}}), ''))
        db.execute('CREATE TABLE IF NOT EXISTS companion_meta (id INTEGER PRIMARY KEY, session_id TEXT, applied TEXT, project_id TEXT)')
        db.execute('INSERT OR IGNORE INTO companion_meta VALUES(1,?,NULL,?)', (uuid.uuid4().hex, bundle()['project']['id']))
        db.execute('CREATE TABLE IF NOT EXISTS companion_events (seq INTEGER PRIMARY KEY AUTOINCREMENT,event_id TEXT UNIQUE,request_hash TEXT,type TEXT,status TEXT,revision INTEGER,payload TEXT,created TEXT)')
        db.execute(EXCHANGES_V2)
        db.execute('ALTER TABLE assistant_exchanges ADD COLUMN project_id TEXT')
        db.execute('ALTER TABLE assistant_exchanges ADD COLUMN activity TEXT')
        db.execute(CONFIRMATIONS)
        db.execute('CREATE TABLE IF NOT EXISTS schema_history (version INTEGER PRIMARY KEY, previous INTEGER, applied TEXT)')
        db.execute('INSERT OR IGNORE INTO schema_history VALUES(?,?,?)', (SCHEMA_VERSION, 0, timestamp()))
        db.execute(f'PRAGMA user_version={SCHEMA_VERSION}')
        db.commit()
    else:
        db.execute('CREATE TABLE IF NOT EXISTS companion_meta (id INTEGER PRIMARY KEY, session_id TEXT, applied TEXT)')
        db.execute('INSERT OR IGNORE INTO companion_meta(id,session_id,applied) VALUES(1,?,NULL)', (uuid.uuid4().hex,))
        db.execute('CREATE TABLE IF NOT EXISTS companion_events (seq INTEGER PRIMARY KEY AUTOINCREMENT,event_id TEXT UNIQUE,request_hash TEXT,type TEXT,status TEXT,revision INTEGER,payload TEXT,created TEXT)')
        db.commit()
        version = db.execute('PRAGMA user_version').fetchone()[0]
        if version < SCHEMA_VERSION: migrate(db, version)
    owner = db.execute('SELECT project_id FROM companion_meta WHERE id=1').fetchone()[0]
    if owner != bundle()['project']['id']:
        db.close()
        raise ProtocolError('project_mismatch', f'This session belongs to project {owner}: open the session for project {bundle()["project"]["id"]}.', 409)
    return db


# Business facts are declared by the project and confirmed only by a person.
def dependency_print(fact):
    prints = bundle()['fingerprints']
    return canonical({dep: prints[dep] for dep in fact.get('depends_on', [])} | {'value': fact.get('value')})


def facts(db):
    rows = {}
    for fact_id, decision, value, fingerprint, source, created in db.execute('SELECT fact_id,decision,value,fingerprint,source,created FROM fact_confirmations ORDER BY seq'):
        rows[fact_id] = {'decision': decision, 'value': value, 'fingerprint': fingerprint, 'source': source, 'time': created}
    out = []
    for fact in bundle()['project']['facts']:
        item = {k: fact.get(k) for k in ('id', 'label', 'value', 'status', 'source', 'depends_on')} | {'declared_status': fact['status'], 'confirmation': None, 'needs_review': False}
        confirmation = rows.get(fact['id'])
        if confirmation:
            still_valid = confirmation['fingerprint'] == dependency_print(fact)
            item['confirmation'] = confirmation | {'valid': still_valid}
            if still_valid and confirmation['decision'] == 'confirm':
                item['status'] = 'confirmed'; item['source'] = 'Confirmed by you in the companion'
            elif still_valid:
                item['status'] = 'unknown'; item['source'] = 'Proposal rejected by you; clarification still needed'
            else:
                item['needs_review'] = True
        out.append(item)
    return out


def blocked(fact_list):
    status = {f['id']: f for f in fact_list}
    return {a['id']: [status[r]['label'] for r in a.get('requires', []) if status[r]['status'] != 'confirmed'] for a in bundle()['journey']['activities'] if any(status[r]['status'] != 'confirmed' for r in a.get('requires', []))}


def snapshot(db):
    revision, payload, message = db.execute('SELECT revision,payload,message FROM session WHERE id=1').fetchone()
    session_id, applied, project_id = db.execute('SELECT session_id,applied,project_id FROM companion_meta WHERE id=1').fetchone()
    stored = json.loads(payload); application = json.loads(applied) if applied else None
    order = activities()
    state = {'activity': stored['activity'], 'answers': stored['answers'], 'step': order.index(stored['activity']) if stored['activity'] in order else 0}
    pending = db.execute("SELECT event_id FROM companion_events WHERE type='choice_registered' AND status='pending' ORDER BY seq DESC LIMIT 1").fetchone()
    rows = db.execute('SELECT seq,event_id,type,status,revision,payload,created FROM companion_events ORDER BY seq DESC LIMIT 30').fetchall()
    events = [{'seq': x[0], 'event_id': x[1], 'type': x[2], 'status': x[3], 'revision': x[4], 'payload': json.loads(x[5]), 'created': x[6]} for x in reversed(rows)]
    if application:
        application['current'] = application['answers'] == state['answers'] and application['context_hash'] == context_hash()
        application['context_current'] = application['context_hash'] == context_hash()
    fact_list = facts(db)
    result = {'protocol_version': 1, 'schema_version': db.execute('PRAGMA user_version').fetchone()[0], 'purpose': 'tutorial_only',
              'project_id': project_id, 'project_title': bundle()['project']['title'], 'journey': {k: bundle()['journey'][k] for k in ('id', 'version')},
              'ticket_id': 'discovery-exercise', 'cycle_id': 'exercise-v1',
              'session_id': session_id, 'revision': revision, 'context_hash': context_hash(), 'state': state, 'pilot_message': message, 'project_approval': False,
              'pending_event_id': pending[0] if pending else None, 'application': application, 'events': events,
              'facts': fact_list, 'blocked': blocked(fact_list), 'dataset_changed': bundle()['dataset_changed'],
              'limits': ['The panel does not open Copilot chat; explanations use the VS Code language model API.', 'Choices belong to the tutorial only.', 'Displayed results are precomputed; no new model is trained.'],
              'assistant_limits': LIMITS}
    if application and not application['context_current']:
        result['review'] = 'Results or data changed after application: review the choice before reuse.'
    rows = db.execute(f'SELECT {EXCHANGE_COLUMNS} FROM assistant_exchanges ORDER BY seq DESC LIMIT ?', (LIMITS['snapshot_exchanges'],)).fetchall()
    result['conversation'] = [{**x, 'current': is_current(x, result)} for x in map(exchange_dict, reversed(rows))]
    return result


def status(path):
    with closing(connect(path)) as db:
        db.execute('BEGIN')
        result = snapshot(db)
        db.rollback()
        return result


def add(db, event_id, kind, status_, revision, payload, request_hash=''):
    db.execute('INSERT INTO companion_events(event_id,request_hash,type,status,revision,payload,created) VALUES(?,?,?,?,?,?,?)',
               (event_id, request_hash, kind, status_, revision, canonical(payload), timestamp()))


def submit(path, event):
    required = {'protocol_version', 'event_id', 'session_id', 'expected_revision', 'context_hash', 'type', 'payload'}
    if not isinstance(event, dict) or set(event) != required: raise ProtocolError('schema', 'Incomplete event or unknown fields.')
    if type(event['protocol_version']) is not int or event['protocol_version'] != 1 or event['type'] != 'submit_state': raise ProtocolError('version', 'Version ou type non pris en charge.')
    if not isinstance(event['event_id'], str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,128}', event['event_id']): raise ProtocolError('id', 'Identifiant invalid.')
    if not isinstance(event['payload'], dict) or set(event['payload']) != {'state'}: raise ProtocolError('choice', 'Invalid exercise choice.')
    state = normalize(event['payload']['state'])
    if state is None: raise ProtocolError('choice', 'Invalid exercise choice.')
    if type(event['expected_revision']) is not int: raise ProtocolError('revision', 'Integer revision required.')
    signature = hashlib.sha256(canonical(event).encode()).hexdigest()
    with closing(connect(path)) as db:
        db.execute('BEGIN IMMEDIATE'); current = snapshot(db)
        prior = db.execute('SELECT request_hash,revision FROM companion_events WHERE event_id=?', (event['event_id'],)).fetchone()
        if prior:
            if prior[0] != signature: raise ProtocolError('id_reused', 'Identifier reused for a different choice.', 409)
            return {**current, 'receipt': {'event_id': event['event_id'], 'registered_revision': prior[1], 'replayed': True}}
        if event['session_id'] != current['session_id']: raise ProtocolError('session', 'Other session de tutoriel.', 409)
        if event['context_hash'] != current['context_hash']: raise ProtocolError('context', 'Tutorial results changed: reread context.', 409)
        if event['expected_revision'] != current['revision']: raise ProtocolError('stale_revision', 'Another tab changed the answers. Reread state before continuing.', 409)
        changed = state['answers'] != current['state']['answers']; revision = current['revision'] + 1
        kind = 'choice_registered' if changed else 'reading_visited'
        if changed: db.execute("UPDATE companion_events SET status='superseded' WHERE type='choice_registered' AND status='pending'")
        db.execute('UPDATE session SET revision=?,payload=? WHERE id=1', (revision, canonical(state)))
        add(db, event['event_id'], kind, 'pending' if changed else 'recorded', revision, {'state': state, 'context_hash': event['context_hash']}, signature)
        db.commit(); result = snapshot(db)
        return {**result, 'receipt': {'event_id': event['event_id'], 'registered_revision': revision, 'replayed': False}}


def result_by_id(result_id): return next((r for r in bundle()['results']['results'] if r['id'] == result_id), None)


def bound_results(answers):
    """Attach an existing result to each calculation-linked choice; missing calculations are explicit, never invented."""
    aliases = (bundle()['project'].get('compatibility') or {}).get('legacy_metric_aliases') or {}
    out = []
    for key, value in answers.items():
        spec = bundle()['choices'].get(key)
        if not spec or spec['kind'] == 'choice_question': continue
        option = next(o for o in spec['domain'] if o['value'] == value)
        found = result_by_id(option.get('result')) if spec['compute'] == 'precomputed' else None
        if not found:
            out.append({'key': key, 'kind': 'not_available', 'status': 'absent', 'message': 'Calculation unavailable in this version: no associated result.', 'new_fits': 0})
            continue
        metrics = dict(found['metrics'])
        metrics.update({alias: metrics[target] for alias, target in aliases.items() if target in metrics})
        out.append({'key': key, 'kind': 'precomputed_selection', 'result_id': found['id'], 'label': found['label'], 'status': found['status'],
                    'source': found['provenance'], 'source_hash': context_hash(), 'protocol': found['protocol'], 'scope': found['scope'],
                    'observations': found['observations'], 'metrics': metrics, 'display': found['display'], 'new_fits': 0})
    return out


def apply(path, event_id, expected_revision, context):
    with closing(connect(path)) as db:
        db.execute('BEGIN IMMEDIATE'); current = snapshot(db)
        event = db.execute('SELECT type,status,payload FROM companion_events WHERE event_id=?', (event_id,)).fetchone()
        if not event or event[0] != 'choice_registered': raise ProtocolError('event', 'Recorded choice not found.')
        if event[1] == 'applied': return {**current, 'receipt': {'event_id': event_id, 'replayed': True}}
        if expected_revision != current['revision'] or type(expected_revision) is not int: raise ProtocolError('stale_revision', 'Revision is stale: reread choices.', 409)
        if context != current['context_hash']: raise ProtocolError('context', 'Context is stale: reread results.', 409)
        original = json.loads(event[2])
        if original.get('context_hash') != current['context_hash']: raise ProtocolError('context', 'This choice belongs to another result version.', 409)
        answers = original['state']['answers']
        if event[1] != 'pending' or answers != current['state']['answers']: raise ProtocolError('superseded', 'This choice was replaced.', 409)
        for key in answers:
            missing = current['blocked'].get(bundle()['choices'][key]['activity'])
            if missing: raise ProtocolError('blocked', 'Activity blocked: first confirm ' + ', '.join(f'« {m} »' for m in missing) + '.', 409)
        results = bound_results(answers)
        revision = current['revision'] + 1
        application = {'event_id': event_id, 'revision': revision, 'context_hash': context, 'answers': answers,
                       'result': results[0] if results else None, 'results': results, 'time': timestamp()}
        db.execute('UPDATE companion_meta SET applied=? WHERE id=1', (canonical(application),))
        db.execute('UPDATE session SET revision=? WHERE id=1', (revision,))
        db.execute("UPDATE companion_events SET status='applied' WHERE event_id=?", (event_id,))
        add(db, uuid.uuid4().hex, 'choice_applied', 'applied', revision, {'source_event_id': event_id})
        for item in results:
            if item['kind'] == 'precomputed_selection': add(db, uuid.uuid4().hex, 'result_selected', 'available', revision, item)
        db.commit(); return snapshot(db)


def confirm_fact(path, fact_id, decision):
    """Only an explicit human action confirms or rejects a proposal; the model never does."""
    fact = next((f for f in bundle()['project']['facts'] if f['id'] == fact_id), None)
    if fact is None or decision not in {'confirm', 'reject'}: raise ProtocolError('schema', 'Unknown fact or decision.')
    with closing(connect(path)) as db:
        db.execute('BEGIN IMMEDIATE'); revision = snapshot(db)['revision']
        db.execute('INSERT INTO fact_confirmations(fact_id,decision,value,fingerprint,source,created) VALUES(?,?,?,?,?,?)',
                   (fact_id, decision, fact.get('value'), dependency_print(fact), 'user', timestamp()))
        add(db, uuid.uuid4().hex, 'fact_' + decision + 'ed', 'recorded', revision, {'fact_id': fact_id, 'value': fact.get('value')})
        db.commit(); return snapshot(db)


def explain(path, message, application_event_id=None, context=None, source='cli'):
    """Message from chat or CLI: attach to the current application only when references match."""
    if not isinstance(message, str) or not message.strip() or len(message) > LIMITS['chat_message_chars']: raise ProtocolError('message', 'An explanation is required, up to 6,000 characters.')
    if source not in {'cli', 'chat_tool'}: raise ProtocolError('schema', 'Source unknown.')
    with closing(connect(path)) as db:
        db.execute('BEGIN IMMEDIATE'); current = snapshot(db); revision = current['revision']
        subject, app_id, choice = 'unattached', None, None
        if application_event_id is not None or context is not None:
            if not isinstance(application_event_id, str) or not isinstance(context, str): raise ProtocolError('schema', 'applicationEventId et contextHash vont ensemble.')
            if context != current['context_hash']: raise ProtocolError('context', 'Context is stale: reread status before publishing.', 409)
            app = current['application']
            if not app or app['event_id'] != application_event_id: raise ProtocolError('stale_context', 'This is no longer the applied choice: reread status.', 409)
            subject, app_id = 'applied', app['event_id']
            choice = {'answers': app['answers'], 'label': answers_label(app['answers'])}
        db.execute('UPDATE session SET message=? WHERE id=1', (message,))
        add(db, uuid.uuid4().hex, 'explanation_published', 'available', revision, {'message': message, 'application_event_id': app_id})
        now = timestamp(); exchange_id = 'chat-' + uuid.uuid4().hex
        db.execute('INSERT INTO assistant_exchanges(exchange_id,request_hash,kind,source,status,session_id,context_hash,application_event_id,revision,step,subject,choice,question,answer,model,options,created,updated,project_id,activity) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                   (exchange_id, exchange_id, 'chat', source, 'published', current['session_id'], current['context_hash'], app_id, revision, None, subject, canonical(choice) if choice else None, None, message, None, canonical({}), now, now, current['project_id'], None))
        db.commit(); return snapshot(db)


# AI guidance: the engine persists exchanges and their references; it generates no text.
EXCHANGE_COLUMNS = 'seq,exchange_id,kind,source,status,session_id,context_hash,application_event_id,revision,step,subject,choice,question,answer,model,error_code,error_message,attempts,options,created,updated,project_id,activity'
EXCHANGE_ID = re.compile(r'[A-Za-z0-9_-]{1,200}')
TERMINAL = {'completed', 'interrupted', 'cancelled', 'error', 'published'}
RETRYABLE = {'error', 'interrupted', 'cancelled'}


def exchange_dict(row):
    item = dict(zip(EXCHANGE_COLUMNS.split(','), row))
    for key in ('choice', 'model', 'options'): item[key] = json.loads(item[key]) if item[key] else None
    return item


def fetch_exchange(db, exchange_id):
    row = db.execute(f'SELECT {EXCHANGE_COLUMNS} FROM assistant_exchanges WHERE exchange_id=?', (exchange_id,)).fetchone()
    return exchange_dict(row) if row else None


def is_current(exchange, snap):
    """An explanation stays current while its referenced application and results are unchanged; navigation has no effect."""
    if exchange['context_hash'] != snap['context_hash'] or exchange.get('project_id') != snap['project_id']: return False
    if exchange['subject'] == 'unattached': return False
    app = snap.get('application')
    return (app['event_id'] if app else None) == exchange['application_event_id']


def answers_label(answers):
    labels = [choice_label(k, v) for k, v in answers.items() if k in bundle()['choices'] and bundle()['choices'][k]['kind'] != 'choice_question']
    return ', '.join(labels) or 'applied exercise choices'


def applications(db):
    """Application history reconstructed from versioned events."""
    out = []
    for revision, payload, created in db.execute("SELECT revision,payload,created FROM companion_events WHERE type='choice_applied' ORDER BY seq").fetchall():
        source = json.loads(payload)['source_event_id']
        registered = db.execute('SELECT payload FROM companion_events WHERE event_id=?', (source,)).fetchone()
        selected = db.execute("SELECT event_id,payload FROM companion_events WHERE type='result_selected' AND revision=?", (revision,)).fetchall()
        out.append({'event_id': source, 'revision': revision, 'answers': json.loads(registered[0])['state']['answers'] if registered else None,
                    'result_event_id': selected[0][0] if selected else None, 'result': json.loads(selected[0][1]) if selected else None,
                    'results': [{'event_id': e, **json.loads(p)} for e, p in selected], 'time': created})
    return out


def previous_choice(db, key, current_event_id, current_value):
    for item in reversed(applications(db)):
        if item['event_id'] == current_event_id or not item['answers'] or key not in item['answers']: continue
        if item['answers'][key] != current_value:
            value = item['answers'][key]
            found = {'value': value, 'label': choice_label(key, value), 'application_event_id': item['event_id']}
            bound = next((r for r in item['results'] if r.get('key') == key), None) or (item['result'] if item['result'] and item['result'].get('key', key) == key else None)
            if bound: found['result'] = {'result_id': bound.get('result_id'), 'display': bound.get('display') or bound.get('metrics')}
            return found
    return None


def result_view(result):
    definitions = bundle()['results']['metric_definitions']
    return {'id': result['id'], 'label': result['label'], 'status': result['status'], 'scope': result['scope'], 'protocol': result['protocol'],
            'observations': result['observations'], 'method': result['method'],
            'metrics': {k: {'value': v, 'display': result['display'][k], 'label': definitions[k]['label'], 'unit': definitions[k]['unit'],
                            'direction': definitions[k].get('direction'), 'meaning': definitions[k].get('description')} for k, v in result['metrics'].items()},
            'limitations': result.get('limitations', [])}


def build_context(db, snap, exchange):
    """Model context reread from database and contracts: only information relevant to this activity."""
    b = bundle(); project, results = b['project'], b['results']
    activity = activity_spec(exchange['activity'])
    content = project['activities'][activity['id']]
    choice, options, app = exchange['choice'], exchange['options'] or {}, snap['application']
    moment = next(m['label'] for m in b['journey']['moments'] if m['id'] == activity['moment'])
    context = {
        'project': {k: project[k] for k in ('id', 'title', 'description', 'problem_type', 'language')},
        'dataset': {'id': project['dataset']['id'], 'name': project['dataset']['name'], 'rows': project['dataset']['rows'], 'version': project['dataset']['sha256'][:12],
                    'results_version': snap['context_hash'][:12], 'provenance': {k: project['dataset']['provenance'][k] for k in ('authors', 'doi', 'license')},
                    'transformations': project['dataset'].get('transformations', [])},
        'facts': [{'label': f['label'], 'value': f['value'], 'status': f['status']} for f in snap['facts']],
        'variables': [{k: v.get(k) for k in ('name', 'label', 'unit', 'role', 'available_at_prediction', 'status', 'special_values')} for v in project['variables']],
        'activity': {'id': activity['id'], 'title': content['title'], 'objective': content['objective'], 'moment': moment, 'instructions': activity.get('instructions')},
        'guidance': b['journey'].get('ai_guidance', []) + project.get('ai_guidance', []),
        'subject': exchange['subject'], 'choice': choice,
        'request': {'kind': exchange['kind'], 'question': exchange['question'], 'junior': options.get('junior', True), 'compare_previous': options.get('compare_previous', False)},
        'limitations': project.get('limitations', []) + results.get('limitations', []),
        'references': {'project_id': snap['project_id'], 'session_id': exchange['session_id'], 'exchange_id': exchange['exchange_id'],
                       'application_event_id': exchange['application_event_id'], 'context_hash': exchange['context_hash']}}
    blocked_by = snap['blocked'].get(activity['id'])
    if blocked_by: context['blocked_until_confirmed'] = blocked_by
    shown = []
    for block in content['blocks']:
        if block['component'] == 'model_comparison': shown += [item['id'] for item in block['results']]
        if block['component'] == 'choice_question' and choice and choice.get('key') == block['key']:
            context['question_options'] = [o['label'] for o in block['options']]
            context['static_feedback'] = block['options'][choice['value']].get('feedback')
        if block['component'] == 'error_view':
            context['error_breakdown'] = results['display'].get(block['source'])
    if shown:
        context['activity_results'] = [result_view(result_by_id(rid)) for rid in dict.fromkeys(shown)]
        context['protocols'] = [p for p in results['protocols'] if p['id'] in {result_by_id(r)['protocol'] for r in shown}]
    spec = b['choices'].get(choice['key']) if choice else None
    if spec and spec['kind'] != 'choice_question':
        if choice.get('applied') and app:
            bound = next((r for r in app.get('results') or [] if r.get('key') == choice['key']), None)
        else:
            bound = next((r for r in bound_results({choice['key']: choice['value']})), None)
        if bound and bound['kind'] == 'precomputed_selection':
            context['result'] = {**result_view(result_by_id(bound['result_id'])), 'origin': 'engine-attested result for the applied choice' if choice.get('applied') else 'precomputed preview, NOT applied', 'new_fits': 0}
            context.setdefault('protocols', [p for p in results['protocols'] if p['id'] == bound['protocol']])
        elif bound:
            context['result'] = {'status': 'absent', 'message': bound['message']}
    if exchange['subject'] == 'preview' and app and choice and choice['key'] in app['answers']:
        context['applied_choice'] = {'value': app['answers'][choice['key']], 'label': choice_label(choice['key'], app['answers'][choice['key']])}
    key = choice['key'] if choice else next((s['key'] for s in b['choices'].values() if s['activity'] == activity['id']), None)
    if context['request']['compare_previous'] and key:
        current_value = choice['value'] if choice else (app['answers'].get(key) if app else None)
        context['previous_choice'] = previous_choice(db, key, exchange['application_event_id'], current_value) if current_value is not None else None
        if context['previous_choice'] is None: context['previous_choice_note'] = 'No different previous choice has been applied for this activity.'
    rows = db.execute(f"SELECT {EXCHANGE_COLUMNS} FROM assistant_exchanges WHERE seq<? AND status IN ('completed','published') AND (activity=? OR activity IS NULL) ORDER BY seq DESC", (exchange['seq'], exchange['activity'])).fetchall()
    limit = LIMITS['history_exchanges']; history = [exchange_dict(r) for r in rows[:limit]]
    context['history'] = [{'kind': h['kind'], 'question': h['question'], 'answer': h['answer'][:LIMITS['history_answer_chars']],
                           'about': (h['choice'] or {}).get('label'), 'still_current': is_current(h, snap)} for h in reversed(history)]
    if len(rows) > limit: context['history_note'] = f'Only the {limit} recent exchanges for this activity are sent; {len(rows) - limit} earlier exchanges remain in local history.'
    return context


BEGIN_FIELDS = {'exchange_id', 'kind', 'activity', 'subject', 'context_hash', 'expected_application_event_id', 'preview_value', 'question', 'junior', 'compare_previous', 'retry'}


def assistant_begin(path, request):
    """Reserve an idempotent exchange, validate its references, and return attested context."""
    if not isinstance(request, dict) or not set(request) <= BEGIN_FIELDS: raise ProtocolError('schema', 'Demande d’explication invalid.')
    exchange_id = request.get('exchange_id')
    if not isinstance(exchange_id, str) or not EXCHANGE_ID.fullmatch(exchange_id): raise ProtocolError('id', 'Invalid exchange identifier.')
    with closing(connect(path)) as db:
        db.execute('BEGIN IMMEDIATE'); snap = snapshot(db); row = fetch_exchange(db, exchange_id)
        if request.get('retry') is True:
            if set(request) != {'exchange_id', 'retry'}: raise ProtocolError('schema', 'Resumption does not change the request.')
            if not row: raise ProtocolError('exchange', 'Exchange not found.', 404)
            if row['status'] not in RETRYABLE: return {'exchange': row, 'replayed': True, 'context': None}
            if not is_current(row, snap) or row['activity'] not in activities(): raise ProtocolError('stale_context', 'This choice was replaced: ask again about the current choice.', 409)
            db.execute("UPDATE assistant_exchanges SET status='pending',answer='',error_code=NULL,error_message=NULL,attempts=attempts+1,updated=? WHERE exchange_id=?", (timestamp(), exchange_id))
            db.commit(); row = fetch_exchange(db, exchange_id)
            return {'exchange': row, 'replayed': False, 'context': build_context(db, snapshot(db), row)}
        kind, activity, subject = request.get('kind'), request.get('activity'), request.get('subject')
        if kind not in {'initial', 'question'} or activity not in activities() or subject not in {'applied', 'preview', 'step'}: raise ProtocolError('schema', 'Invalid kind, activity, or subject.')
        junior, compare = request.get('junior', True), request.get('compare_previous', False)
        if type(junior) is not bool or type(compare) is not bool: raise ProtocolError('schema', 'Options invalides.')
        question = request.get('question')
        if kind == 'question':
            if not isinstance(question, str) or not question.strip(): raise ProtocolError('question', 'Question empty.')
            if len(question) > LIMITS['question_chars']: raise ProtocolError('question_too_long', f'Questions are limited to {LIMITS["question_chars"]} characters to keep context focused; shorten the question.')
        elif question is not None: raise ProtocolError('schema', 'The initial explanation contains no question.')
        if request.get('context_hash') != snap['context_hash']: raise ProtocolError('context', 'Tutorial results changed: reread context.', 409)
        app, expected = snap['application'], request.get('expected_application_event_id')
        if expected is not None and (not app or app['event_id'] != expected): raise ProtocolError('stale_context', 'The applied choice changed: reread state before requesting an explanation.', 409)
        if kind == 'initial' and (subject != 'applied' or expected is None): raise ProtocolError('schema', 'The initial explanation concerns an attested applied choice.')
        key = next((s['key'] for s in bundle()['choices'].values() if s['activity'] == activity), None); choice = None
        if subject == 'applied':
            if not key or not app or key not in app['answers'] or expected is None: raise ProtocolError('choice', 'No applied choice for this activity.', 409)
            choice = {'key': key, 'value': app['answers'][key], 'label': choice_label(key, app['answers'][key]), 'applied': True}
        elif subject == 'preview':
            value = request.get('preview_value')
            if not key or not valid({'activity': activity, 'answers': {key: value}}): raise ProtocolError('choice', 'Invalid preview for this activity.')
            choice = {'key': key, 'value': value, 'label': choice_label(key, value), 'applied': False}
        elif 'preview_value' in request: raise ProtocolError('schema', 'Unexpected preview.')
        app_id = app['event_id'] if app else None
        identity = {'kind': kind, 'activity': activity, 'subject': subject, 'choice': choice, 'application_event_id': app_id, 'question': question, 'context_hash': snap['context_hash']}
        request_hash = hashlib.sha256(canonical(identity).encode()).hexdigest()
        if row:
            prior = db.execute('SELECT request_hash FROM assistant_exchanges WHERE exchange_id=?', (exchange_id,)).fetchone()[0]
            if prior != request_hash: raise ProtocolError('id_reused', 'Exchange identifier reused for a different request.', 409)
            return {'exchange': row, 'replayed': True, 'context': None}
        now = timestamp()
        db.execute('INSERT INTO assistant_exchanges(exchange_id,request_hash,kind,source,status,session_id,context_hash,application_event_id,revision,step,subject,choice,question,options,created,updated,project_id,activity) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                   (exchange_id, request_hash, kind, 'panel', 'pending', snap['session_id'], snap['context_hash'], app_id, snap['revision'], None, subject,
                    canonical(choice) if choice else None, question, canonical({'junior': junior, 'compare_previous': compare}), now, now, snap['project_id'], activity))
        db.commit(); row = fetch_exchange(db, exchange_id)
        return {'exchange': row, 'replayed': False, 'context': build_context(db, snap, row)}


MODEL_FIELDS = {'id', 'name', 'vendor', 'family', 'version'}


def assistant_update(path, exchange_id, status_, answer=None, model=None, error_code=None, error_message=None):
    if not isinstance(exchange_id, str) or not EXCHANGE_ID.fullmatch(exchange_id): raise ProtocolError('id', 'Invalid exchange identifier.')
    if status_ not in {'streaming', 'completed', 'interrupted', 'cancelled', 'error'}: raise ProtocolError('schema', 'Status invalid.')
    if answer is not None and (not isinstance(answer, str) or len(answer) > LIMITS['answer_chars']): raise ProtocolError('answer', 'Response too long.')
    if model is not None and (not isinstance(model, dict) or not set(model) <= MODEL_FIELDS or any(not isinstance(v, str) or len(v) > 200 for v in model.values() if v is not None)): raise ProtocolError('schema', 'Invalid model.')
    if error_code is not None and (not isinstance(error_code, str) or not re.fullmatch(r'[a-z_]{1,40}', error_code)): raise ProtocolError('schema', 'Invalid error code.')
    if error_message is not None and (not isinstance(error_message, str) or len(error_message) > 500): raise ProtocolError('schema', 'Invalid error message.')
    with closing(connect(path)) as db:
        db.execute('BEGIN IMMEDIATE'); row = fetch_exchange(db, exchange_id)
        if not row: raise ProtocolError('exchange', 'Exchange not found.', 404)
        if row['status'] in TERMINAL: return {'exchange': row, 'current': is_current(row, snapshot(db)), 'replayed': True}
        if status_ == 'streaming' and row['status'] != 'pending': raise ProtocolError('state', 'Exchange already started.', 409)
        db.execute('UPDATE assistant_exchanges SET status=?,answer=COALESCE(?,answer),model=COALESCE(?,model),error_code=?,error_message=?,updated=? WHERE exchange_id=?',
                   (status_, answer, canonical(model) if model else None, error_code, error_message, timestamp(), exchange_id))
        db.commit(); row = fetch_exchange(db, exchange_id)
        # Recheck context on publication: a completed answer is current only while its choice is current.
        return {'exchange': row, 'current': is_current(row, snapshot(db)), 'replayed': False}


def assistant_recover(path):
    """After restart, mark unfinished generations interrupted; never resume automatically."""
    with closing(connect(path)) as db:
        db.execute('BEGIN IMMEDIATE')
        count = db.execute("UPDATE assistant_exchanges SET status='interrupted',error_code='restart',error_message=?,updated=? WHERE status IN ('pending','streaming')",
                           ('Response interrupted by closure or restart. No new request was sent.', timestamp())).rowcount
        db.commit(); return {'recovered': count}


def assistant_clear(path):
    """Clear panel conversation only: retain choices, applications, confirmations, and results."""
    with closing(connect(path)) as db:
        db.execute('BEGIN IMMEDIATE'); revision = snapshot(db)['revision']
        count = db.execute('DELETE FROM assistant_exchanges').rowcount
        db.execute("UPDATE session SET message='' WHERE id=1")
        add(db, uuid.uuid4().hex, 'conversation_cleared', 'recorded', revision, {'exchanges': count})
        db.commit(); return snapshot(db)


def project_view():
    """Validated project, journey, and results: the sole source of displayed text, options, and units."""
    b = bundle()
    return {'project': {k: v for k, v in b['project'].items() if k != 'compatibility'}, 'journey': b['journey'], 'choices': b['choices'],
            'results': {k: b['results'][k] for k in ('protocols', 'metric_definitions', 'results', 'display', 'limitations', 'generated_by')},
            'context_hash': b['context_hash'], 'dataset_changed': b['dataset_changed'], 'components': sorted(contracts.COMPONENTS)}


def export(path):
    with closing(connect(path)) as db:
        db.execute('BEGIN'); snap = snapshot(db)
        conversation = [{**x, 'current': is_current(x, snap)} for x in map(exchange_dict, db.execute(f'SELECT {EXCHANGE_COLUMNS} FROM assistant_exchanges ORDER BY seq').fetchall())]
        apps = applications(db); by_app = {a['event_id']: a for a in apps}
        links = [{'exchange_id': x['exchange_id'], 'kind': x['kind'], 'status': x['status'], 'subject': x['subject'], 'activity': x['activity'], 'choice': (x['choice'] or {}).get('label'),
                  'choice_event_id': x['application_event_id'], 'application_revision': by_app.get(x['application_event_id'], {}).get('revision'),
                  'result_event_id': by_app.get(x['application_event_id'], {}).get('result_event_id'), 'context_hash': x['context_hash'], 'current': x['current']} for x in conversation]
        confirmations = [dict(zip(('fact_id', 'decision', 'value', 'source', 'time'), r)) for r in db.execute('SELECT fact_id,decision,value,source,created FROM fact_confirmations ORDER BY seq')]
        db.rollback()
        return {**snap, 'export': {'format': 'hypotrail-tutorial-session', 'schema_version': SCHEMA_VERSION, 'exported': timestamp(),
                                   'project': {'id': snap['project_id'], 'journey': snap['journey'], 'dataset_sha256': bundle()['fingerprints']['dataset.content']},
                                   'applications': apps, 'confirmations': confirmations, 'conversation': conversation, 'links': links}}


def projects():
    """Registry projects: surface invalid configuration instead of hiding it."""
    out = []
    for entry in contracts.registry():
        try:
            b = contracts.load_bundle(entry['id'])
            out.append({'id': entry['id'], 'title': b['project']['title'], 'problem_type': b['project']['problem_type'], 'session_name': b['project']['session_name'], 'default': bool(entry.get('default'))})
        except contracts.ContractError as e:
            out.append({'id': entry['id'], 'title': entry['id'], 'error': f'{e.code} : {e}'})
    return {'projects': out}


def dispatch(path, request):
    if not isinstance(request, dict) or not isinstance(request.get('action'), str): raise ProtocolError('schema', 'Invalid request.')
    action = request['action']
    fields = {'status': ({'action'}, set()), 'project': ({'action'}, set()), 'projects': ({'action'}, set()), 'submit': ({'action', 'event'}, set()), 'apply': ({'action', 'event_id', 'expected_revision', 'context_hash'}, set()),
              'export': ({'action'}, set()), 'confirm_fact': ({'action', 'fact_id', 'decision'}, set()),
              'explain': ({'action', 'message'}, {'application_event_id', 'context_hash', 'source'}), 'assistant_begin': ({'action', 'request'}, set()),
              'assistant_update': ({'action', 'exchange_id', 'status'}, {'answer', 'model', 'error_code', 'error_message'}), 'assistant_recover': ({'action'}, set()), 'assistant_clear': ({'action', 'confirm'}, set())}
    if action not in fields or not fields[action][0] <= set(request) <= fields[action][0] | fields[action][1]: raise ProtocolError('action', 'Action or parameters are not allowed.')
    if action == 'status': return status(path)
    if action == 'project': return project_view()
    if action == 'projects': return projects()
    if action == 'export': return export(path)
    if action == 'submit': return submit(path, request['event'])
    if action == 'apply': return apply(path, request['event_id'], request['expected_revision'], request['context_hash'])
    if action == 'confirm_fact': return confirm_fact(path, request['fact_id'], request['decision'])
    if action == 'assistant_begin': return assistant_begin(path, request['request'])
    if action == 'assistant_update': return assistant_update(path, request['exchange_id'], request['status'], request.get('answer'), request.get('model'), request.get('error_code'), request.get('error_message'))
    if action == 'assistant_recover': return assistant_recover(path)
    if action == 'assistant_clear':
        if request['confirm'] is not True: raise ProtocolError('confirm', 'Confirmation required.')
        return assistant_clear(path)
    return explain(path, request['message'], request.get('application_event_id'), request.get('context_hash'), request.get('source', 'cli'))
