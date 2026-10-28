"""The workshop's Copilot hook (scripts/workshop/hooks/pretool.py): plain engine commands are
allowed, a raw read of the data file is denied, anything else gets no decision."""
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
HOOK = REPO / 'scripts' / 'workshop' / 'hooks' / 'pretool.py'
ENGINE = f'uv run --project {REPO}/framework hypotrail'


def _decide(event, tmp_path):
    out = subprocess.run([sys.executable, str(HOOK), '--repo', str(REPO), '--data-file',
                          'auto-mpg.data', '--log', str(tmp_path / 'hook.log')],
                         input=json.dumps(event), capture_output=True, text=True, check=True)
    return json.loads(out.stdout).get('hookSpecificOutput', {}).get('permissionDecision')


def test_the_hook_allows_engine_commands_and_refuses_raw_data(tmp_path):
    run = lambda c: {'tool_name': 'run_in_terminal', 'tool_input': {'command': c}}
    assert _decide(run(f'{ENGINE} status --study s'), tmp_path) == 'allow'
    assert _decide({'toolName': 'bash', 'toolArgs': json.dumps(
        {'command': f'uv run --quiet --project {REPO}/framework hypotrail run split'})},
        tmp_path) == 'allow'
    assert _decide(run(f'{ENGINE} status | python -c x'), tmp_path) is None
    assert _decide(run(f'{ENGINE} status; rm -rf x'), tmp_path) is None
    assert _decide(run('uv run --project /elsewhere/framework hypotrail status'), tmp_path) is None
    assert _decide(run('rm -rf /'), tmp_path) is None
    assert _decide({'tool_name': 'read_file', 'tool_input': {'filePath': '/s/data/auto-mpg.data'}},
                   tmp_path) == 'deny'
    assert _decide(run('head use-cases/auto-mpg/data/auto-mpg.data'), tmp_path) == 'deny'
    assert len((tmp_path / 'hook.log').read_text().splitlines()) == 8
