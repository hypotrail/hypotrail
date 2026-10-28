"""Static checks of the Azure ML YAML of a project: references, expressions and graph.

A YAML file that passes the Azure ML JSON schema can still be wrong: a ``${{...}}``
expression can name an input that does not exist, a job can bind an output of a job that
does not produce it, an asset can be referenced as ``@latest``. :func:`check` reads the job,
the pipeline component and the command components of ``aml/`` and returns every such
problem. It never contacts Azure: a passing check says nothing about the existence of the
resources, the permissions or a future run (spec §14, AC28).

The Azure expressions are read as text and never resolved (OmegaConf never sees them).
Standalone (standard library and PyYAML): copied byte for byte into the generated project
(``src/pipeline/utils/hypotrail/azure_yaml.py``).
"""
from __future__ import annotations

import posixpath
import re
from pathlib import Path

EXPRESSION = re.compile(r'\$\{\{\s*([^}]*?)\s*\}\}')
FORMS = {
    'component': re.compile(r'(inputs|outputs)\.([A-Za-z_][A-Za-z0-9_]*)'),
    'pipeline': re.compile(r'parent\.(?:(inputs|outputs)\.([A-Za-z_][A-Za-z0-9_]*)|jobs\.'
                           r'([A-Za-z_][A-Za-z0-9_]*)\.outputs\.([A-Za-z_][A-Za-z0-9_]*))'),
}
ASSET_REF = re.compile(r'azureml:[A-Za-z0-9][A-Za-z0-9_.-]*:[A-Za-z0-9][A-Za-z0-9_.-]*')
LATEST = re.compile(r'(@latest\b|:latest\b)')
JOB = 'aml/pipelines/training/pipeline-job.yml'
PIPELINE = 'aml/pipelines/training/pipeline.yml'
ENVIRONMENT = 'aml/pipelines/training/aml-environment.yml'
DATA = 'aml/pipelines/training/data.yml'


def _load(path: Path):
    import yaml
    return yaml.safe_load(path.read_text(encoding='utf-8'))


def expressions(text: str) -> list[str]:
    return [m.group(1) for m in EXPRESSION.finditer(text)]


def _latest(root: Path, rel: str, problems: list) -> None:
    for number, line in enumerate((root / rel).read_text(encoding='utf-8').splitlines(), 1):
        if line.lstrip().startswith('$schema:'):
            continue
        if LATEST.search(line):
            problems.append(f'{rel}:{number}: a reference uses latest instead of a version')


def check_component(root: Path, rel: str, problems: list) -> dict:
    """The inputs and outputs of a command component, after checking its expressions."""
    doc = _load(root / rel) or {}
    inputs, outputs = set(doc.get('inputs') or {}), set(doc.get('outputs') or {})
    command = str(doc.get('command') or '')
    used = set()
    for expr in expressions(command):
        match = FORMS['component'].fullmatch(expr)
        if not match:
            problems.append(f'{rel}: expression ${{{{{expr}}}}} is not inputs.X or outputs.X')
            continue
        kind, name = match.groups()
        if name not in (inputs if kind == 'inputs' else outputs):
            problems.append(f'{rel}: ${{{{{expr}}}}} names an undeclared {kind[:-1]}')
        used.add((kind, name))
    for name in sorted(inputs):
        if ('inputs', name) not in used:
            problems.append(f'{rel}: input {name} is declared but not passed to the command')
    for name in sorted(outputs):
        if ('outputs', name) not in used:
            problems.append(f'{rel}: output {name} is declared but not written by the command')
    environment = str(doc.get('environment') or '')
    if not ASSET_REF.fullmatch(environment):
        problems.append(f'{rel}: environment {environment!r} is not azureml:<name>:<version>')
    if doc.get('code') != './../../':
        problems.append(f'{rel}: code must be ./../../ (the project root, filtered by .amlignore)')
    _latest(root, rel, problems)
    return {'inputs': inputs, 'outputs': outputs}


def check(root) -> tuple[list[str], dict]:
    """``(problems, graph)``; ``graph`` lists the job -> job edges of the pipeline."""
    root = Path(root)
    problems: list[str] = []
    pipeline = _load(root / PIPELINE) or {}
    p_inputs, p_outputs = set(pipeline.get('inputs') or {}), set(pipeline.get('outputs') or {})
    jobs = pipeline.get('jobs') or {}
    components = {}
    for name, job in jobs.items():
        rel_component = posixpath.normpath(posixpath.join(posixpath.dirname(PIPELINE),
                                                          str(job.get('component'))))
        if not (root / rel_component).is_file():
            problems.append(f'{PIPELINE}: job {name} uses a missing component {rel_component}')
            continue
        components[name] = check_component(root, rel_component, problems)
    edges, bound_outputs = [], []
    for name, job in jobs.items():
        if name not in components:
            continue
        spec = components[name]
        job_inputs = set((job.get('inputs') or {}))
        if job_inputs != spec['inputs']:
            problems.append(f'{PIPELINE}: job {name} inputs {sorted(job_inputs)} differ from its '
                            f'component inputs {sorted(spec["inputs"])}')
        for port in ('inputs', 'outputs'):
            for key, value in (job.get(port) or {}).items():
                if port == 'outputs' and key not in spec['outputs']:
                    problems.append(f'{PIPELINE}: job {name} binds an unknown output {key}')
                if not isinstance(value, str):
                    continue
                for expr in expressions(value):
                    match = FORMS['pipeline'].fullmatch(expr)
                    if not match:
                        problems.append(f'{PIPELINE}: job {name}: ${{{{{expr}}}}} is not a '
                                        'parent.inputs, parent.outputs or parent.jobs reference')
                        continue
                    kind, port_name, source, source_output = match.groups()
                    if kind == 'inputs' and port_name not in p_inputs:
                        problems.append(f'{PIPELINE}: job {name}: unknown pipeline input '
                                        f'{port_name}')
                    elif kind == 'outputs':
                        if port_name not in p_outputs:
                            problems.append(f'{PIPELINE}: job {name}: unknown pipeline output '
                                            f'{port_name}')
                        bound_outputs.append(port_name)
                    elif source is not None:
                        if source == name or source not in components:
                            problems.append(f'{PIPELINE}: job {name}: unknown source job '
                                            f'{source}')
                        elif source_output not in components[source]['outputs']:
                            problems.append(f'{PIPELINE}: job {name}: job {source} has no '
                                            f'output {source_output}')
                        else:
                            edges.append((source, source_output, name, key))
    for output in sorted(p_outputs):
        if bound_outputs.count(output) != 1:
            problems.append(f'{PIPELINE}: pipeline output {output} is bound '
                            f'{bound_outputs.count(output)} times')
    _latest(root, PIPELINE, problems)
    job = _load(root / JOB) or {}
    if job.get('component') != 'pipeline.yml':
        problems.append(f'{JOB}: component must be pipeline.yml')
    j_inputs = job.get('inputs') or {}
    if set(j_inputs) != p_inputs:
        problems.append(f'{JOB}: inputs {sorted(j_inputs)} differ from the pipeline inputs '
                        f'{sorted(p_inputs)}')
    for key, value in j_inputs.items():
        path = str((value or {}).get('path') or '')
        if not ASSET_REF.fullmatch(path):
            problems.append(f'{JOB}: input {key} path {path!r} is not azureml:<name>:<version>')
    compute = str(job.get('compute') or '')
    if not compute.startswith('azureml:') or len(compute) <= len('azureml:'):
        problems.append(f'{JOB}: compute {compute!r} is not azureml:<name>')
    _latest(root, JOB, problems)
    for rel in (ENVIRONMENT, DATA):
        doc = _load(root / rel) or {}
        if not doc.get('name') or doc.get('version') in (None, ''):
            problems.append(f'{rel}: name and an explicit version are required')
        _latest(root, rel, problems)
    environment = _load(root / ENVIRONMENT) or {}
    build = environment.get('build') or {}
    if 'image' in environment and build:
        problems.append(f'{ENVIRONMENT}: image and build are exclusive')
    if build and not (root / Path(ENVIRONMENT).parent / str(build.get('path')) /
                      str(build.get('dockerfile_path', 'Dockerfile'))).is_file():
        problems.append(f'{ENVIRONMENT}: the build context has no Dockerfile')
    return problems, {'jobs': sorted(components), 'edges': sorted(edges)}
