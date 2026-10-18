"""Revisioned local commands and durable log; requires the pilot lock.
This mechanism confines no agent and manages no remote jobs.
"""
import copy
import hashlib
import json
import os
import platform
import sys
import uuid
from pathlib import Path
from importlib.metadata import version, PackageNotFoundError


def provenance(root):
    root = Path(root)
    hashes = {}
    for folder in ['mlkit', 'model', 'scripts']:
        for path in sorted((root / folder).glob('*.py')):
            hashes[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    for path in sorted(Path(__file__).parent.glob('*.py')):
        hashes['kit/' + path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    packages = {}
    for name in ['numpy', 'pandas', 'scikit-learn', 'marimo']:
        try:
            packages[name] = version(name)
        except PackageNotFoundError:
            packages[name] = None
    environment = {'python': sys.version, 'platform': platform.platform(), 'packages': packages}
    return {'code': hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest(),
            'environment': hashlib.sha256(json.dumps(environment, sort_keys=True).encode()).hexdigest(),
            'versions': environment}


def recover(pilot, state):
    """Under the acquired lock, no previous local process owns it.
Never repeat an action with an unknown outcome automatically.
"""
    changed = False
    transaction = pilot.home() / 'transaction.json'
    if transaction.exists():
        row = json.loads(transaction.read_text())
        if row['request_id'] not in state.get('receipts', {}):
            # Saving state.json is the commit point.
            for name, content in row['before_files'].items():
                path = pilot.config.ROOT / name
                if content is None:
                    path.unlink(missing_ok=True)
                else:
                    temp = path.with_suffix(path.suffix + '.recovery')
                    temp.write_text(content); os.replace(temp, path)
            pilot.event('transaction_rolled_back', request_id=row['request_id'])
        transaction.unlink()
    active = state.pop('active_execution', None)
    if active:
        active.update(status='interrupted_unknown', finished=pilot.now())
        pilot.write(pilot.home() / 'executions' / (active['id'] + '.json'), active)
        state['interrupted_execution'] = active
        pilot.event('interrupted_execution', execution=active['id'])
        changed = True
    if changed:
        pilot.save(state)
    return state


def apply(pilot, state, request):
    """Recommended single entry point for multi-client decisions.
The retained historical CLI does not provide this guarantee.
"""
    if set(request) != {'request_id', 'expected_revision', 'action', 'params'}:
        raise ValueError('Commande : request_id, expected_revision, action, params required')
    key = request['request_id']
    if not isinstance(key, str) or not key.strip() or len(key) > 200:
        raise ValueError('Invalid idempotency key')
    signature = hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()
    receipt = state.get('receipts', {}).get(key)
    if receipt:
        if receipt['signature'] != signature:
            raise ValueError('Idempotency key already used for a different command')
        return {**receipt, 'replayed': True}
    if type(request['expected_revision']) is not int or request['expected_revision'] != state.get('revision', 0):
        raise ValueError('Revision is stale: reread pilot next before deciding')
    action, params = request['action'], request['params']
    allowed = {'answer': {'question', 'value', 'rationale', 'confirmed'},
               'revise': {'changes', 'expected_context'},
               'iterate': {'reason', 'steps', 'seconds'},
               'mode': {'mode'}}
    if action not in allowed or not isinstance(params, dict) or set(params) != allowed[action]:
        raise ValueError('Invalid action or command parameters')
    if action == 'answer' and type(params['confirmed']) is not bool:
        raise ValueError('Explicit boolean confirmation required')
    if action == 'mode' and params['mode'] not in {'junior', 'senior', 'auto'}:
        raise ValueError('Unknown mode')
    before = copy.deepcopy(state)
    names = ['project.yaml', 'frame.yaml', 'answers.yaml']
    files = {n: (pilot.config.ROOT / n).read_text() if (pilot.config.ROOT / n).exists() else None for n in names}
    transaction = pilot.home() / 'transaction.json'
    pilot.write(transaction, {'request_id': key, 'before_files': files})
    # Suboperations call save; their state remains in memory until commit.
    real_save = pilot.save
    pilot.save = lambda value: None
    committed = False
    try:
        if action == 'answer':
            pilot.propose(state, params['question'], params['value'], params['rationale'],
                          status='confirmed' if params['confirmed'] else 'assumed')
            result = {'question': params['question'], 'status': state['answers'][params['question']]['status']}
        elif action == 'revise':
            path = pilot.home() / 'requested-revision.json'
            pilot.write(path, params['changes'])
            result = pilot.revise(state, path, params['expected_context'])
        elif action == 'iterate':
            result = pilot.iterate(state, params['reason'], params['steps'], params['seconds'])
        else:
            state['mode'] = params['mode']; result = {'mode': params['mode']}
        receipt = {'signature': signature, 'result': result, 'revision': before.get('revision', 0) + 1}
        state.setdefault('receipts', {})[key] = receipt
        pilot.save = real_save
        real_save(state)
        committed = True
        transaction.unlink()
        pilot.event('command_committed', request_id=key, action=action, revision=state['revision'])
        return receipt
    except BaseException:
        if committed:
            raise
        pilot.save = real_save
        state.clear(); state.update(before)
        recover(pilot, state)
        raise
    finally:
        pilot.save = real_save


def start(pilot, state, key, argv):
    row = {'id': uuid.uuid4().hex, 'step': key, 'command': argv,
           'context': state['context'], 'revision': state.get('revision', 0),
           'iteration': state.get('iteration', 1), 'started': pilot.now(),
           'status': 'running', 'provenance': provenance(pilot.config.ROOT)}
    state['active_execution'] = row
    # Durable reservation before execution; interruption does not create a free budget.
    state['executions'] = state.get('executions', 0) + 1
    pilot.save(state)
    pilot.write(pilot.home() / 'executions' / (row['id'] + '.json'), row)
    return row


def finish(pilot, state, row, code, seconds):
    row = {**row, 'returncode': code, 'seconds': seconds, 'finished': pilot.now(),
           'status': 'succeeded' if code == 0 else 'failed'}
    current = provenance(pilot.config.ROOT)
    if row['context'] != pilot.context_hash() or row['provenance'] != current:
        row['status'] = 'stale'
    pilot.write(pilot.home() / 'executions' / (row['id'] + '.json'), row)
    state.pop('active_execution', None)
    return row


def summary(pilot, state):
    blockers = []
    if any('provenance' not in value for key, value in state['steps'].items() if key != 'quality'):
        blockers.append('Previous results retained: this new log does not attest their complete provenance.')
    if state.get('interrupted_execution'):
        blockers.append('Execution interrupted with unknown outcome; inspect before resuming.')
    failures = [k for k, v in state['steps'].items() if v.get('returncode') != 0]
    if failures:
        blockers.append('Failed calculations: ' + ', '.join(failures))
    if state.get('revision_pending'):
        blockers.append('Contract revised: an explicit new cycle is required.')
    unresolved = [q['id'] for q in pilot.pending(state)]
    if unresolved:
        blockers.append('Unconfirmed decisions: ' + ', '.join(unresolved))
    todo = pilot.remaining(state)
    if state.get('executions', 0) >= state['max_steps'] or state['seconds_used'] >= state['max_seconds']:
        status = 'budget_exhausted'; next_action = 'Review the summary and decide the next budget.'
    elif blockers:
        status = 'attention_required'; next_action = blockers[0]
    elif todo:
        labels = {'discovery':'Discover the data', 'classical-plan':'Prepare the comparison and evidence', 'classical-profile':'Check data quality and splitting', 'classical-run':'Run the exploratory comparison', 'quality':'Check tests for the change', 'notebooks':'Prepare explanatory notebooks'}
        status = 'ready'; next_action = labels.get(todo[0][0], 'Run the next workflow check')
    else:
        status = 'plan_finished'; next_action = 'Compare evidence and reach an exploratory conclusion.'
    return {'revision': state.get('revision', 0), 'context': state['context'],
            'status': status, 'blockers': blockers, 'next_action': next_action,
            'proof_scope': 'exploratory_only', 'generalization': 'not_established',
            'moments': ['Frame the change', 'Prepare evidence', 'Work and compare', 'Conclude and hand over'],
            'guidance': 'detailed' if state['mode'] == 'junior' else 'concise',
            'execution': 'bounded' if state['mode'] == 'auto' else 'interactive'}


def sync_provenance(pilot, state):
    """Invalidate a tracked result when code or environment changes.
Historical evidence without fingerprints is never retroactively certified.
"""
    current = provenance(pilot.config.ROOT)
    changed = [key for key, value in state['steps'].items()
               if value.get('provenance') and value['provenance'] != current]
    if changed:
        pilot.snapshot(state, suffix='-provenance-' + uuid.uuid4().hex[:12])
        previous = state['steps']; state['steps'] = {}
        for task in state['tasks']:
            if task['status'] == 'queued': task['status'] = 'stale'
        pilot.event('provenance_changed', affected=changed, invalidated=previous)
        pilot.save(state)
