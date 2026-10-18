"""Drive Claude Code (`claude -p`) through a scripted conversation in an isolated workspace.

This is the agent acceptance runner of plan WP0.7 (amendments A1 and A2). Results are
"Claude Code acceptance", never Copilot acceptance.

Isolation rules, all checked here:

* the study workspace is a fresh temporary directory **outside the repository**, and no
  ancestor directory holds an instruction file (CLAUDE.md, CLAUDE.local.md, AGENTS.md,
  .claude/CLAUDE.md, .claude/AGENTS.md) that Claude Code would load (A2);
* each run gets its own empty ``CLAUDE_CONFIG_DIR`` and a scrubbed environment, so no user
  skills, plugins, MCP servers, hooks, auto memory, or parent-session variables reach the
  agent under test;
* a scripted utterance is one ``claude -p`` process. Utterances of the same chat resume the
  chat's session (``--resume``); a new chat starts a new session without resume;
* hard caps: agent turns per utterance (``--max-turns``), dollars per chat
  (``--max-budget-usd``, which Claude Code applies to the session's cumulative cost, so it
  is a per-chat cap on resume), dollars per conversation, and a wall-clock timeout per
  utterance. ``total_cost_usd`` in a resumed turn's result is also cumulative for the
  session; the runner records the per-turn increment (``cost_usd``) and the session's
  cumulative value (``session_cost_usd``) separately;
* the runner never writes to the repository working tree. It snapshots ``git status`` of
  the repository before and after and reports any difference; the agent is denied the
  Read/Edit/Write tools on the repository and on the hidden grader directory, and the
  Bash audit (graders.audit_bash) flags any command that names them.

Usage (from the repository root)::

    uv run --project framework python framework/tests/acceptance/agent/e1.py run ...

The runner itself is a library; ``e1.py`` and ``test_scenarios.py`` drive it.
"""
from __future__ import annotations

import dataclasses
import datetime as _dt
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[3]
INSTRUCTION_FILES = ('CLAUDE.md', 'CLAUDE.local.md', 'AGENTS.md',
                     '.claude/CLAUDE.md', '.claude/AGENTS.md')
ENV_KEEP = ('PATH', 'LANG', 'LC_ALL', 'TERM', 'HTTPS_PROXY', 'https_proxy', 'HTTP_PROXY',
            'http_proxy', 'NO_PROXY', 'no_proxy', 'NODE_EXTRA_CA_CERTS', 'SSL_CERT_FILE',
            'REQUESTS_CA_BUNDLE', 'UV_CACHE_DIR')


class IsolationError(RuntimeError):
    """The workspace or environment would let repository instructions reach the agent."""


# --------------------------------------------------------------------------- arms

@dataclasses.dataclass
class Arm:
    id: str
    root: Path
    files: dict[str, str]
    python_version: str | None
    python_packages: list[str]
    model: str | None
    tools: list[str]
    allowed_tools: list[str]
    permission_mode: str
    bash_policy: str
    extra_args: list[str]
    setup: str = 'files'          # 'files' (copy arm files) or 'hypotrail_init' (arm B)

    @classmethod
    def load(cls, path: Path) -> 'Arm':
        path = Path(path)
        doc = yaml.safe_load((path / 'arm.yaml').read_text(encoding='utf-8'))
        py = doc.get('python') or {}
        cl = doc.get('claude') or {}
        return cls(id=doc['id'], root=path, files=dict(doc.get('files') or {}),
                   python_version=py.get('version'), python_packages=list(py.get('packages') or []),
                   model=cl.get('model'), tools=list(cl.get('tools') or []),
                   allowed_tools=list(cl.get('allowed_tools') or []),
                   permission_mode=cl.get('permission_mode', 'dontAsk'),
                   bash_policy=doc.get('bash_policy', 'hypotrail_cli_only'),
                   extra_args=list(cl.get('extra_args') or []),
                   setup=doc.get('setup', 'files'))

    def install(self, workspace: Path) -> list[str]:
        written = []
        for src, dst in self.files.items():
            target = workspace / dst
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(self.root / src, target)
            written.append(dst)
        return written


# --------------------------------------------------------------------------- isolation

def instruction_files_above(path: Path) -> list[Path]:
    """Instruction files Claude Code would load from ``path`` and its ancestors."""
    found = []
    for d in [path, *path.parents]:
        for name in INSTRUCTION_FILES:
            if (d / name).is_file():
                found.append(d / name)
    managed = Path('/etc/claude-code/CLAUDE.md')
    if managed.is_file():
        found.append(managed)
    return found


def check_isolation(workspace: Path, own_files: list[str] = ()) -> None:
    ws = workspace.resolve()
    if ws == REPO_ROOT or REPO_ROOT in ws.parents:
        raise IsolationError(f'workspace {ws} is inside the repository {REPO_ROOT}')
    own = {(ws / f).resolve() for f in own_files}
    leaked = [p for p in instruction_files_above(ws) if p.resolve() not in own]
    if leaked:
        raise IsolationError('instruction files would be loaded: ' + ', '.join(map(str, leaked)))


def scrubbed_env(config_dir: Path, extra: dict[str, str] | None = None) -> dict[str, str]:
    env = {k: os.environ[k] for k in ENV_KEEP if k in os.environ}
    env['HOME'] = os.environ.get('HOME', '/root')
    env['CLAUDE_CONFIG_DIR'] = str(config_dir)
    env['CLAUDE_CODE_DISABLE_AUTO_MEMORY'] = '1'
    env.update(extra or {})
    return env


class RepoGuard:
    """Snapshot of the repository working tree, to prove a run did not touch it."""

    def __init__(self, repo: Path = REPO_ROOT):
        self.repo = repo
        self.before = self.snapshot()

    def snapshot(self) -> dict:
        def git(*args):
            return subprocess.run(['git', '-C', str(self.repo), *args], capture_output=True,
                                  text=True, check=False).stdout
        status = git('status', '--porcelain=v1', '-uall')
        diff = git('diff', 'HEAD')
        return {'head': git('rev-parse', 'HEAD').strip(),
                'status': sorted(status.splitlines()),
                'diff_sha256': hashlib.sha256(diff.encode()).hexdigest()}

    def compare(self) -> dict:
        after = self.snapshot()
        added = sorted(set(after['status']) - set(self.before['status']))
        removed = sorted(set(self.before['status']) - set(after['status']))
        return {'unchanged': after == self.before, 'head_changed': after['head'] != self.before['head'],
                'status_added': added, 'status_removed': removed,
                'diff_changed': after['diff_sha256'] != self.before['diff_sha256']}


# --------------------------------------------------------------------------- environment

def cli_version() -> str:
    p = subprocess.run(['claude', '--version'], capture_output=True, text=True, check=False)
    return p.stdout.strip()


def create_python_env(workspace: Path, version: str | None, packages: list[str]) -> dict:
    if not packages:
        return {'created': False}
    venv = workspace / '.venv'
    t = time.time()
    subprocess.run(['uv', 'venv', str(venv), '--python', version or '3.13', '--quiet'],
                   check=True, capture_output=True)
    subprocess.run(['uv', 'pip', 'install', '--python', str(venv / 'bin/python'), '--quiet',
                    *packages], check=True, capture_output=True)
    freeze = subprocess.run(['uv', 'pip', 'freeze', '--python', str(venv / 'bin/python')],
                            check=True, capture_output=True, text=True).stdout.splitlines()
    return {'created': True, 'seconds': round(time.time() - t, 1), 'packages': freeze}


# --------------------------------------------------------------------------- conversation

@dataclasses.dataclass
class Caps:
    max_agent_turns: int = 80            # tool round trips inside one utterance
    max_budget_usd_per_chat: float = 15.0   # cumulative per session (Claude Code semantics)
    max_budget_usd_total: float = 40.0
    timeout_s_per_turn: int = 1800
    max_utterances: int = 30


def deny_rules(paths: list[Path]) -> list[str]:
    rules = []
    for p in paths:
        pattern = '/' + str(Path(p).resolve()) + '/**'      # '//abs/path/**' = absolute
        rules += [f'Read({pattern})', f'Edit({pattern})', f'Write({pattern})']
    return rules


class InterruptWatcher:
    """S9: kill the first ``hypotrail run`` that reaches the test pause hook.

    The agent's environment sets ``HYPOTRAIL_TEST_HOOKS=1`` and
    ``HYPOTRAIL_FAULT=run_pause_before_promote:<folder>``: every run then writes
    ``<folder>/ready`` (its pid) after computing and waits for ``<folder>/go`` before
    promoting. The watcher kills the first such process with SIGKILL, an abrupt end before
    the promotion, then writes ``go`` so that any later run proceeds normally.
    """

    def __init__(self, folder: str, after_seconds: float = 1.0, poll_s: float = 0.2):
        import threading
        self.folder = Path(folder)
        self.after = float(after_seconds)
        self.poll = poll_s
        self.events: list[dict] = []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)

    def start(self):
        self.folder.mkdir(parents=True, exist_ok=True)
        self._thread.start()

    def _loop(self):
        import signal
        ready = self.folder / 'ready'
        while not self._stop.is_set():
            if ready.is_file() and not (self.folder / 'go').exists():
                time.sleep(self.after)
                try:
                    pid = int(ready.read_text().strip())
                    os.kill(pid, signal.SIGKILL)
                    self.events.append({'killed_pid': pid, 'at': _dt.datetime.now(
                        _dt.timezone.utc).isoformat()})
                except (ValueError, ProcessLookupError, PermissionError) as exc:
                    self.events.append({'kill_failed': repr(exc)})
                (self.folder / 'go').write_text('go')
            self._stop.wait(self.poll)

    def stop(self) -> dict:
        self._stop.set()
        self._thread.join(timeout=5)
        return {'folder': str(self.folder), 'events': self.events}


class Conversation:
    """One scripted conversation (several chats) against one workspace."""

    def __init__(self, workspace: Path, run_dir: Path, arm: Arm, caps: Caps,
                 forbidden_paths: list[Path] = (), env_extra: dict[str, str] | None = None,
                 log=print):
        self.workspace = Path(workspace)
        self.run_dir = Path(run_dir)
        self.arm = arm
        self.caps = caps
        self.forbidden = [Path(p) for p in forbidden_paths]
        self.config_dir = self.run_dir / 'claude-config'
        self.config_dir.mkdir(parents=True, exist_ok=True)
        (self.run_dir / 'transcript').mkdir(parents=True, exist_ok=True)
        self.env = scrubbed_env(self.config_dir, env_extra)
        self.turns: list[dict] = []
        self.sessions: dict[int, str] = {}
        self.total_cost = 0.0
        self.session_costs: dict[str, float] = {}
        self.log = log
        self.stopped: str | None = None

    def _command(self, utterance: str, session_id: str | None) -> list[str]:
        a = self.arm
        cmd = ['claude', '-p', utterance, '--output-format', 'stream-json', '--verbose',
               '--max-turns', str(self.caps.max_agent_turns),
               '--max-budget-usd', str(self.caps.max_budget_usd_per_chat),
               '--permission-mode', a.permission_mode,
               '--settings', json.dumps({'autoMemoryEnabled': False})]
        if a.model:
            cmd += ['--model', a.model]
        if a.tools:
            cmd += ['--tools', ','.join(a.tools)]
        if a.allowed_tools:
            cmd += ['--allowedTools', *a.allowed_tools]
        denied = deny_rules([REPO_ROOT, *self.forbidden])
        if denied:
            cmd += ['--disallowedTools', *denied]
        cmd += a.extra_args
        if session_id:
            cmd += ['--resume', session_id]
        return cmd

    def say(self, chat: int, utterance: str, label: str | None = None,
            env_extra: dict[str, str] | None = None, interrupt: dict | None = None) -> dict:
        if self.stopped:
            raise RuntimeError(f'conversation stopped: {self.stopped}')
        if len(self.turns) >= self.caps.max_utterances:
            self.stopped = 'max_utterances'
            raise RuntimeError(self.stopped)
        index = len(self.turns) + 1
        session = self.sessions.get(chat)
        cmd = self._command(utterance, session)
        started = _dt.datetime.now(_dt.timezone.utc).isoformat()
        t = time.time()
        env = {**self.env, **(env_extra or {})}
        watcher = InterruptWatcher(**interrupt) if interrupt else None
        if watcher:
            watcher.start()
        try:
            p = subprocess.run(cmd, cwd=self.workspace, env=env, capture_output=True,
                               text=True, timeout=self.caps.timeout_s_per_turn)
            stdout, stderr, code, timed_out = p.stdout, p.stderr, p.returncode, False
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or '')
            stderr = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or '')
            code, timed_out = None, True
        finally_watch = watcher.stop() if watcher else None
        wall = round(time.time() - t, 1)
        path = self.run_dir / 'transcript' / f'turn-{index:02d}.jsonl'
        path.write_text(stdout, encoding='utf-8')
        events = parse_stream(stdout)
        init = next((e for e in events if e.get('type') == 'system' and e.get('subtype') == 'init'), {})
        result = next((e for e in reversed(events) if e.get('type') == 'result'), {})
        session_id = result.get('session_id') or init.get('session_id')
        if session_id and chat not in self.sessions:
            self.sessions[chat] = session_id
        cumulative = float(result.get('total_cost_usd') or 0.0)
        cost = turn_cost(cumulative, self.session_costs.get(session_id or '', 0.0) if session else 0.0)
        if session_id:
            self.session_costs[session_id] = cumulative
        self.total_cost += cost
        tool_calls = sum(1 for e in events if e.get('type') == 'assistant'
                         for c in e['message'].get('content', []) if c.get('type') == 'tool_use')
        record = {
            'index': index, 'chat': chat, 'label': label, 'utterance': utterance,
            'resumed_session': session, 'session_id': session_id, 'started_at': started,
            'wall_s': wall, 'exit_code': code, 'timed_out': timed_out,
            'result_subtype': result.get('subtype'), 'is_error': result.get('is_error'),
            'agent_turns': result.get('num_turns'), 'cost_usd': cost,
            'session_cost_usd': cumulative,
            'models': sorted((result.get('modelUsage') or {}).keys()) or [init.get('model')],
            'init_model': init.get('model'), 'cli_version': init.get('claude_code_version'),
            'init_tools': init.get('tools'), 'init_skills': init.get('skills'),
            'init_mcp_servers': [m.get('name') for m in init.get('mcp_servers', [])],
            'init_has_memory_paths': 'memory_paths' in init,
            'tool_calls': tool_calls, 'transcript': str(path.relative_to(self.run_dir)),
            'final_text': result.get('result'), 'stderr_tail': stderr[-2000:],
            'finished_at': _dt.datetime.now(_dt.timezone.utc).isoformat(),
            'env_extra': dict(env_extra or {}), 'interrupt': finally_watch,
        }
        self.turns.append(record)
        self.log(f'[turn {index:02d} chat {chat}] {label or ""} {wall}s ${cost:.2f} '
                 f'{record["result_subtype"]} tools={tool_calls} total=${self.total_cost:.2f}')
        if self.total_cost >= self.caps.max_budget_usd_total:
            self.stopped = 'max_budget_usd_total'
        return record


def turn_cost(session_cumulative: float, previous_cumulative: float) -> float:
    """Cost of one turn from the session's cumulative ``total_cost_usd`` values."""
    return round(max(0.0, session_cumulative - previous_cumulative), 6)


def recompute_turn_costs(turns: list[dict]) -> list[float]:
    """Per-turn costs for runs recorded before the runner separated them: in those runs
    ``cost_usd`` holds the session's cumulative value."""
    last: dict[str, float] = {}
    out = []
    for t in turns:
        cumulative = t.get('session_cost_usd', t['cost_usd'])
        sid = t.get('session_id') or ''
        out.append(turn_cost(cumulative, last.get(sid, 0.0)))
        last[sid] = cumulative
    return out


def parse_stream(text: str) -> list[dict]:
    events = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            events.append({'type': 'unparsed', 'text': line[:2000]})
    return events


def load_transcript(run_dir: Path) -> list[dict]:
    """All events of a run, each tagged with its turn index and chat."""
    run = json.loads((Path(run_dir) / 'run.json').read_text(encoding='utf-8'))
    events = []
    for t in run['turns']:
        for e in parse_stream((Path(run_dir) / t['transcript']).read_text(encoding='utf-8')):
            e['_turn'], e['_chat'], e['_label'] = t['index'], t['chat'], t.get('label')
            events.append(e)
    return events


def make_workspace(base: Path | None = None, prefix: str = 'hypotrail-ws-') -> Path:
    base = Path(base) if base else Path(tempfile.gettempdir())
    base.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix=prefix, dir=base)).resolve()


def archive_workspace(workspace: Path, dest: Path) -> None:
    ignore = shutil.ignore_patterns('.venv', '__pycache__', '__marimo__', '.ipynb_checkpoints')
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(workspace, dest, ignore=ignore, symlinks=True)


def run_conversation(*, arm: Arm, chats: list[list[dict]], run_dir: Path, prepare_workspace,
                     caps: Caps | None = None, workspace_base: Path | None = None,
                     forbidden_paths: list[Path] = (), env_extra: dict[str, str] | None = None,
                     meta: dict | None = None, log=print, after_turn=None,
                     before_first_turn=None, responder=None) -> dict:
    """Run a whole conversation and write ``run_dir/run.json``.

    ``chats`` is a list of chats; each chat is a list of ``{'say': str, 'label': str}``.
    ``prepare_workspace(ws)`` copies the case material and returns a description dict.
    ``after_turn(ws, turn, run_dir)`` returns a dict stored as ``turn['after']`` (arm B:
    study snapshot and number check). ``responder(ws, turn, step, next_step, answered)``
    may return an extra step ``{'say', 'label', 'simulated'}`` said right after the turn
    (a simulated junior answer); it is called again after that step, with ``answered``
    counting the answers already given after the scripted step.
    """
    caps = caps or Caps()
    run_dir = Path(run_dir).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    guard = RepoGuard()
    ws = make_workspace(workspace_base)
    case_info = prepare_workspace(ws)
    installed = arm.install(ws) + list(case_info.get('installed') or [])
    check_isolation(ws, installed)
    for p in forbidden_paths:
        if ws in Path(p).resolve().parents or Path(p).resolve() == ws:
            raise IsolationError(f'forbidden path {p} is inside the workspace')
    env_info = create_python_env(ws, arm.python_version, arm.python_packages)
    record = {
        'schema': 'hypotrail.agent-run/1', 'label': 'Claude Code acceptance',
        'arm': arm.id, 'meta': meta or {}, 'workspace': str(ws), 'case': case_info,
        'arm_files': installed, 'python_env': env_info, 'cli_version': cli_version(),
        'caps': dataclasses.asdict(caps), 'started_at': _dt.datetime.now(_dt.timezone.utc).isoformat(),
        'forbidden_paths': [str(p) for p in forbidden_paths], 'turns': [],
    }
    conv = Conversation(ws, run_dir, arm, caps, forbidden_paths, env_extra, log)
    if before_first_turn is not None:
        record['before'] = before_first_turn(ws)
    t = time.time()
    try:
        for chat_index, chat in enumerate(chats, start=1):
            for position, step in enumerate(chat):
                queue = [step]
                answered = 0
                while queue and not conv.stopped:
                    current = queue.pop(0)
                    turn = conv.say(int(current.get('chat', chat_index)), current['say'],
                                    current.get('label'), env_extra=current.get('env'),
                                    interrupt=current.get('interrupt'))
                    if current.get('simulated'):
                        turn['simulated'] = current['simulated']
                    if after_turn is not None:
                        turn['after'] = after_turn(ws, turn, run_dir)
                    record['turns'] = conv.turns
                    (run_dir / 'run.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
                    if responder is not None:
                        nxt = chat[position + 1] if position + 1 < len(chat) else None
                        extra = responder(ws, turn, step, nxt, answered)
                        if extra:
                            answered += 1
                            queue.append({**extra, 'chat': step.get('chat', chat_index)})
    finally:
        record.update({
            'turns': conv.turns, 'sessions': {str(k): v for k, v in conv.sessions.items()},
            'stopped': conv.stopped, 'total_cost_usd': round(conv.total_cost, 4),
            'wall_s': round(time.time() - t, 1),
            'finished_at': _dt.datetime.now(_dt.timezone.utc).isoformat(),
            'repo_guard': guard.compare(),
        })
        archive_workspace(ws, run_dir / 'workspace')
        (run_dir / 'run.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
    return record
