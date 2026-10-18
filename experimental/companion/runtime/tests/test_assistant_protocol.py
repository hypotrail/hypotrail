"""Panel conversation: migration, references, idempotence, and separation from business state."""
from contextlib import closing
import importlib.util
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import threading
import urllib.error
import urllib.request

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location('osml_protocol_ai', ROOT / 'protocol.py')
protocol = importlib.util.module_from_spec(spec)
spec.loader.exec_module(protocol)
RESULTS = json.loads((ROOT / 'projects/bank-marketing/results.json').read_text())


@pytest.fixture(autouse=True)
def bank():
    protocol.use_project('uci-bank-marketing-v1')


def submit(db, answers, step=5, key='choice'):
    s = protocol.status(db)
    event = {'protocol_version': 1, 'event_id': key, 'session_id': s['session_id'], 'expected_revision': s['revision'],
             'context_hash': s['context_hash'], 'type': 'submit_state', 'payload': {'state': {'step': step, 'answers': answers}}}
    return protocol.submit(db, event)


def apply_threshold(db, value, key):
    s = submit(db, {'threshold': value}, key=key)
    return protocol.apply(db, key, s['revision'], s['context_hash'])


def begin(db, **request):
    s = protocol.status(db)
    request.setdefault('context_hash', s['context_hash'])
    return protocol.assistant_begin(db, request)


def initial(db, event_id):
    return begin(db, exchange_id=f'initial-{event_id}-threshold', kind='initial', activity='selection', subject='applied',
                 expected_application_event_id=event_id)


def question(db, exchange_id, text, **extra):
    return begin(db, exchange_id=exchange_id, kind='question', activity='selection', subject='applied', question=text, **extra)


def selected(value):
    return next(r for r in RESULTS['results'] if r['id'] == f'selection-{value:.2f}')['metrics']


def legacy_db(path, payload='{"answers":{"goal":0},"step":2}', exchanges=False):
    with closing(sqlite3.connect(path)) as old:
        # Exact 0.2.0 schema, without user_version.
        old.execute('CREATE TABLE session (id INTEGER PRIMARY KEY, revision INTEGER, payload TEXT, message TEXT)')
        old.execute('CREATE TABLE companion_meta (id INTEGER PRIMARY KEY, session_id TEXT, applied TEXT)')
        old.execute('CREATE TABLE companion_events (seq INTEGER PRIMARY KEY AUTOINCREMENT,event_id TEXT UNIQUE,request_hash TEXT,type TEXT,status TEXT,revision INTEGER,payload TEXT,created TEXT)')
        old.execute('INSERT INTO session VALUES(1,4,?,?)', (payload, 'Ancien message'))
        old.execute('INSERT INTO companion_meta VALUES(1,?,?)', ('legacy-session', json.dumps({'event_id': 'old', 'revision': 3, 'context_hash': 'ancien', 'answers': {'goal': 0}, 'result': None})))
        old.execute("INSERT INTO companion_events(event_id,request_hash,type,status,revision,payload,created) VALUES('e1','h','choice_registered','pending',4,'{}','t')")
        old.commit()


def test_migration_keeps_existing_v1_session(tmp_path):
    db = tmp_path / 'old.sqlite'
    legacy_db(db)
    s = protocol.status(db)
    assert s['schema_version'] == 3 and s['session_id'] == 'legacy-session' and s['revision'] == 4
    assert s['project_id'] == 'uci-bank-marketing-v1'
    # Legacy page 2 maps to baseline (compatibility.legacy_steps).
    assert s['state'] == {'activity': 'baseline', 'answers': {'goal': 0}, 'step': 2} and s['pilot_message'] == 'Ancien message'
    assert s['pending_event_id'] == 'e1' and s['conversation'] == []
    # A legacy application cannot be attached to current results: inspectable, never current.
    assert s['application']['event_id'] == 'old' and s['application']['current'] is False and 'review' in s
    with closing(sqlite3.connect(db)) as check:
        assert check.execute('SELECT version,previous FROM schema_history ORDER BY version').fetchall() == [(2, 0), (3, 0)]
        assert check.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    assert protocol.status(db)['revision'] == 4


def test_migration_from_v2_maps_exchange_steps(tmp_path):
    db = tmp_path / 'v2.sqlite'
    legacy_db(db, '{"answers":{"threshold":0.2},"step":5}')
    with closing(sqlite3.connect(db)) as v2:
        v2.execute(protocol.EXCHANGES_V2)
        v2.execute("INSERT INTO assistant_exchanges(exchange_id,request_hash,kind,source,status,session_id,context_hash,revision,step,subject,answer,created,updated) VALUES('x1','h','question','panel','completed','legacy-session','old',4,5,'step','Previous answer','t','t')")
        v2.execute('PRAGMA user_version=2'); v2.commit()
    s = protocol.status(db)
    row = s['conversation'][0]
    assert row['activity'] == 'selection' and row['project_id'] == 'uci-bank-marketing-v1' and row['answer'] == 'Previous answer'
    assert row['current'] is False and s['state']['activity'] == 'selection'


def test_session_of_other_project_refused(tmp_path):
    db = tmp_path / 'bank.sqlite'
    protocol.status(db)
    protocol.use_project('uci-auto-mpg-v1')
    with pytest.raises(protocol.ProtocolError) as error:
        protocol.status(db)
    assert error.value.code == 'project_mismatch'
    legacy = tmp_path / 'legacy.sqlite'
    legacy_db(legacy)
    with pytest.raises(protocol.ProtocolError):
        protocol.status(legacy)


def test_initial_exchange_references_attested_application(tmp_path):
    db = tmp_path / 's.sqlite'
    applied = apply_threshold(db, .2, 'c1')
    out = initial(db, 'c1')
    ex, ctx = out['exchange'], out['context']
    assert not out['replayed'] and ex['status'] == 'pending' and ex['application_event_id'] == 'c1' and ex['activity'] == 'selection'
    assert ex['session_id'] == applied['session_id'] and ex['context_hash'] == applied['context_hash']
    assert ex['choice'] == {'key': 'threshold', 'value': .2, 'label': 'threshold 0.20', 'applied': True}
    assert {k: v['value'] for k, v in ctx['result']['metrics'].items()} == selected(.2) and ctx['result']['new_fits'] == 0
    assert ctx['result']['metrics']['selected_contacts']['unit'] == 'contacts'
    assert ctx['dataset']['id'] == 'uci-bank-marketing' and ctx['dataset']['rows'] == 4521 and ctx['project']['problem_type'] == 'binary_classification'
    assert RESULTS['limitations'][2] in ctx['limitations'] and 'duration' in [v['name'] for v in ctx['variables']]
    assert any('lost sale' in g for g in ctx['guidance'])
    text = json.dumps(ctx, ensure_ascii=False)
    assert 'state.json' not in text and 'project.yaml' not in text and len(text) < 20000
    after = protocol.status(db)
    assert after['revision'] == applied['revision'] and after['application'] == applied['application']


def test_initial_replay_is_idempotent(tmp_path):
    db = tmp_path / 's.sqlite'
    apply_threshold(db, .2, 'c1')
    assert not initial(db, 'c1')['replayed']
    again = initial(db, 'c1')
    assert again['replayed'] and again['context'] is None
    assert len(protocol.status(db)['conversation']) == 1


def test_stale_application_rejected_before_any_generation(tmp_path):
    db = tmp_path / 's.sqlite'
    apply_threshold(db, .2, 'c1')
    apply_threshold(db, .35, 'c2')
    with pytest.raises(protocol.ProtocolError) as error:
        initial(db, 'c1')
    assert error.value.code == 'stale_context'
    assert protocol.status(db)['conversation'] == []


def test_navigation_does_not_invalidate_explanation(tmp_path):
    db = tmp_path / 's.sqlite'
    apply_threshold(db, .2, 'c1')
    ex = initial(db, 'c1')['exchange']
    protocol.assistant_update(db, ex['exchange_id'], 'streaming', model={'id': 'm', 'name': 'Model'})
    done = protocol.assistant_update(db, ex['exchange_id'], 'completed', answer='Texte')
    assert done['current']
    submit(db, {'threshold': .2}, step=2, key='nav')
    s = protocol.status(db)
    assert s['revision'] > done['exchange']['revision'] and s['conversation'][0]['current']


def test_preview_question_does_not_apply(tmp_path):
    db = tmp_path / 's.sqlite'
    apply_threshold(db, .2, 'c1')
    submit(db, {'threshold': .35}, key='draft')
    before = protocol.status(db)
    out = begin(db, exchange_id='q-preview', kind='question', activity='selection', subject='preview', preview_value=.35,
                question='What about this threshold?', expected_application_event_id='c1')
    assert out['exchange']['choice']['applied'] is False and out['context']['result']['origin'].startswith('precomputed preview')
    assert out['context']['applied_choice']['label'] == 'threshold 0.20'
    after = protocol.status(db)
    assert after['application'] == before['application'] and after['pending_event_id'] == 'draft'
    assert after['revision'] == before['revision']


def test_new_application_makes_old_answer_historical(tmp_path):
    db = tmp_path / 's.sqlite'
    apply_threshold(db, .2, 'c1')
    old = initial(db, 'c1')['exchange']['exchange_id']
    apply_threshold(db, .35, 'c2')
    late = protocol.assistant_update(db, old, 'completed', answer='Late response')
    assert late['current'] is False
    new = initial(db, 'c2')['exchange']['exchange_id']
    conv = {x['exchange_id']: x for x in protocol.status(db)['conversation']}
    assert conv[new]['current'] and not conv[old]['current'] and conv[old]['choice']['label'] == 'threshold 0.20'


def test_compare_previous_and_history_limit(tmp_path):
    db = tmp_path / 's.sqlite'
    apply_threshold(db, .2, 'c1')
    apply_threshold(db, .35, 'c2')
    for i in range(12):
        ex = question(db, f'q{i}', f'Q{i}', expected_application_event_id='c2')['exchange']
        protocol.assistant_update(db, ex['exchange_id'], 'completed', answer=f'A{i}')
    ctx = question(db, 'qc', 'Compare', expected_application_event_id='c2', compare_previous=True)['context']
    assert ctx['previous_choice']['label'] == 'threshold 0.20' and ctx['previous_choice']['result']['result_id'] == 'selection-0.20'
    assert len(ctx['history']) == 10 and ctx['history'][-1]['question'] == 'Q11' and 'history_note' in ctx
    plain = question(db, 'qp', 'No comparison', expected_application_event_id='c2')['context']
    assert 'previous_choice' not in plain


def test_question_limits_and_reused_id(tmp_path):
    db = tmp_path / 's.sqlite'
    ask = lambda text, i='q1': begin(db, exchange_id=i, kind='question', activity='start', subject='step', question=text)
    with pytest.raises(protocol.ProtocolError) as error:
        ask('x' * 4001)
    assert error.value.code == 'question_too_long' and '4000' in str(error.value)
    ask('Bonjour')
    assert ask('Bonjour')['replayed']
    with pytest.raises(protocol.ProtocolError, match='reused'):
        ask('Other')
    with pytest.raises(protocol.ProtocolError):
        ask('x', '../etc')
    with pytest.raises(protocol.ProtocolError):
        begin(db, exchange_id='q9', kind='question', activity='unknown', subject='step', question='x')


def test_error_retry_and_terminal_states(tmp_path):
    db = tmp_path / 's.sqlite'
    apply_threshold(db, .2, 'c1')
    ex = initial(db, 'c1')['exchange']['exchange_id']
    protocol.assistant_update(db, ex, 'error', error_code='quota', error_message='Quota reached')
    assert protocol.status(db)['application']['event_id'] == 'c1'
    retried = protocol.assistant_begin(db, {'exchange_id': ex, 'retry': True})
    assert not retried['replayed'] and retried['exchange']['attempts'] == 2 and retried['context']
    protocol.assistant_update(db, ex, 'completed', answer='Good answer')
    assert protocol.assistant_update(db, ex, 'error', error_code='x')['replayed']
    assert protocol.assistant_begin(db, {'exchange_id': ex, 'retry': True})['replayed']


def test_recover_marks_interrupted_without_new_request(tmp_path):
    db = tmp_path / 's.sqlite'
    apply_threshold(db, .2, 'c1')
    ex = initial(db, 'c1')['exchange']['exchange_id']
    protocol.assistant_update(db, ex, 'streaming')
    assert protocol.assistant_recover(db) == {'recovered': 1}
    row = protocol.status(db)['conversation'][0]
    assert row['status'] == 'interrupted' and row['error_code'] == 'restart'
    assert protocol.assistant_recover(db) == {'recovered': 0}


def test_chat_explanations_attached_or_unattached(tmp_path):
    db = tmp_path / 's.sqlite'
    s = apply_threshold(db, .2, 'c1')
    panel = initial(db, 'c1')['exchange']['exchange_id']
    protocol.assistant_update(db, panel, 'streaming')
    protocol.explain(db, 'Message free')
    protocol.explain(db, 'Attached', 'c1', s['context_hash'], 'chat_tool')
    with pytest.raises(protocol.ProtocolError) as error:
        protocol.explain(db, 'Stale', 'other', s['context_hash'], 'chat_tool')
    assert error.value.code == 'stale_context'
    conv = protocol.status(db)['conversation']
    assert [x['subject'] for x in conv] == ['applied', 'unattached', 'applied']
    assert conv[0]['status'] == 'streaming'
    assert conv[2]['current'] and conv[2]['source'] == 'chat_tool' and not conv[1]['current']


def test_export_links_choices_applications_results_and_answers(tmp_path):
    db = tmp_path / 's.sqlite'
    apply_threshold(db, .2, 'c1')
    ex = initial(db, 'c1')['exchange']['exchange_id']
    protocol.assistant_update(db, ex, 'completed', answer='Explanation', model={'id': 'm1', 'name': 'Model'})
    out = protocol.dispatch(db, {'action': 'export'})['export']
    assert out['project']['id'] == 'uci-bank-marketing-v1' and out['project']['journey']['id'] == 'binary-selection'
    assert out['applications'][0]['event_id'] == 'c1' and out['applications'][0]['result']['metrics']['selected_contacts'] == selected(.2)['selected_contacts']
    link = out['links'][0]
    assert link['choice_event_id'] == 'c1' and link['result_event_id'] == out['applications'][0]['result_event_id'] and link['activity'] == 'selection'
    assert out['conversation'][0]['answer'] == 'Explanation' and out['conversation'][0]['model']['id'] == 'm1'


def test_clear_conversation_keeps_choices(tmp_path):
    db = tmp_path / 's.sqlite'
    apply_threshold(db, .2, 'c1')
    initial(db, 'c1')
    with pytest.raises(protocol.ProtocolError):
        protocol.dispatch(db, {'action': 'assistant_clear', 'confirm': False})
    s = protocol.dispatch(db, {'action': 'assistant_clear', 'confirm': True})
    assert s['conversation'] == [] and s['application']['event_id'] == 'c1'


def test_http_fallback_refuses_assistant_actions(tmp_path):
    out = subprocess.run([sys.executable, str(ROOT / 'bridge.py'), 'rpc', '--db', str(tmp_path / 's.sqlite')],
                         input=json.dumps({'action': 'assistant_recover'}), capture_output=True, text=True, timeout=30)
    assert json.loads(out.stdout) == {'recovered': 0}
    spec_b = importlib.util.spec_from_file_location('bridge_ai', ROOT / 'bridge.py')
    bridge = importlib.util.module_from_spec(spec_b)
    spec_b.loader.exec_module(bridge)
    server = bridge.make_server(tmp_path / 'h.sqlite', 'tok', 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        host = f'127.0.0.1:{server.server_port}'
        request = urllib.request.Request(f'http://{host}/rpc', data=json.dumps({'action': 'assistant_clear', 'confirm': True}).encode(),
                                         headers={'X-Pilot-Token': 'tok', 'Content-Type': 'application/json'}, method='POST')
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(request, timeout=5)
        assert error.value.code == 400
    finally:
        server.shutdown()
        server.server_close()
