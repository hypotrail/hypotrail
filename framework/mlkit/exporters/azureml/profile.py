"""The destination profile ``hypotrail.azure_target/1`` (export spec §08, §12).

A trainer writes one profile for every participant of a workshop (``--profile FILE``, YAML
or JSON). It names the Azure resources that already exist; the export never invents one.
A missing field makes the export ``draft`` and is listed in ``missing_fields``; a field
present but malformed, an unknown key, or a key that looks like a credential is refused
(``contract_invalid``) before anything is rendered. The profile never holds a secret: the
identity is described by its mechanism, never by a value.

Normalised form (written to ``src/conf/azure/target.yaml`` of the project)::

    schema_version: hypotrail.azure_target/1
    subscription_id: <GUID>
    resource_group: <name>
    workspace: <name>
    compute: <compute cluster name>
    experiment_name: <name>            # optional: derived from the project name
    data_asset: {name: <name>, version: <explicit version>}
    environment: {name: <name>, version: <explicit version>, base_image: <image:tag|@digest>}
    identity: {mode: user_identity | managed_identity | compute_default}
    devops: {service_connection: <name>}   # optional, by name only
    ci: {cloud_enabled: false}             # cloud CI stays manual unless true
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping

from .errors import ExportError

SCHEMA = 'hypotrail.azure_target/1'
REQUIRED = ('subscription_id', 'resource_group', 'workspace', 'compute',
            'data_asset.name', 'data_asset.version', 'environment.name',
            'environment.version', 'environment.base_image', 'identity.mode')
SHAPE = {'schema_version': None, 'subscription_id': None, 'resource_group': None,
         'workspace': None, 'compute': None, 'experiment_name': None,
         'data_asset': {'name': None, 'version': None},
         'environment': {'name': None, 'version': None, 'base_image': None},
         'identity': {'mode': None}, 'devops': {'service_connection': None},
         'ci': {'cloud_enabled': None}}
IDENTITY_MODES = ('user_identity', 'managed_identity', 'compute_default')
GUID = re.compile(r'^[0-9a-fA-F]{8}-([0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$')
# Azure ML resource and asset names: letters, digits, '-', '_' (and '.' for assets).
NAME = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]{0,254}$')
ASSET_NAME = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,254}$')
VERSION = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,29}$')
IMAGE = re.compile(r'^[a-z0-9.-]+(:[0-9]+)?/[a-z0-9._/-]+(:[A-Za-z0-9._-]+|@sha256:[0-9a-f]{64})$')
SECRET_WORDS = ('password', 'passwd', 'secret', 'token', 'credential', 'account_key',
                'accountkey', 'sas', 'connection_string', 'connectionstring', 'private_key',
                'client_secret', 'api_key', 'apikey')
SECRET_VALUES = re.compile(r'(AccountKey=|SharedAccessSignature=|sig=|-----BEGIN |'
                           r'DefaultEndpointsProtocol=)', re.IGNORECASE)


def _get(document: Mapping, dotted: str):
    node: Any = document
    for part in dotted.split('.'):
        if not isinstance(node, Mapping) or part not in node:
            return None
        node = node[part]
    return node


def _walk(document: Mapping, shape: Mapping, path: str = '') -> None:
    for key, value in document.items():
        where = f'{path}.{key}' if path else str(key)
        lowered = str(key).lower()
        if any(word in lowered for word in SECRET_WORDS):
            raise ExportError('contract_invalid', 'The profile may not hold a credential.',
                              path=where, remediation='Remove the key: name the identity '
                              'mechanism in identity.mode, never a secret value.')
        if isinstance(value, str) and SECRET_VALUES.search(value):
            raise ExportError('contract_invalid', 'A profile value looks like a credential.',
                              path=where, remediation='Remove the value from the profile.')
        if key not in shape:
            raise ExportError('contract_invalid', 'Unknown profile key.', path=where,
                              remediation=f'Allowed keys: {", ".join(sorted(shape))}.')
        child = shape[key]
        if isinstance(child, Mapping):
            if value is None:
                continue
            if not isinstance(value, Mapping):
                raise ExportError('contract_invalid', 'Expected a mapping.', path=where,
                                  remediation='Write this field as a mapping.')
            _walk(value, child, where)


def _check(dotted: str, value, pattern: re.Pattern, words: str) -> None:
    if value is None:
        return
    if not isinstance(value, str) or not pattern.match(value):
        raise ExportError('contract_invalid', f'{dotted} is not {words}.', path=dotted,
                          remediation=f'Write {dotted} as {words}.')


def load(path) -> dict:
    """The profile file as a mapping (YAML or JSON); ``contract_invalid`` if unreadable."""
    source = Path(path)
    try:
        text = source.read_text(encoding='utf-8')
    except OSError as error:
        raise ExportError('invalid_arguments', 'The profile file cannot be read.',
                          path='profile', remediation='Pass an existing --profile file.',
                          details={'error': error.strerror}) from error
    try:
        if source.suffix.lower() == '.json':
            document = json.loads(text)
        else:
            import yaml
            document = yaml.safe_load(text)
    except Exception as error:   # a YAML or JSON syntax error, reported without traceback
        raise ExportError('contract_invalid', 'The profile is not valid YAML or JSON.',
                          path='profile', remediation='Fix the profile syntax.',
                          details={'error': str(error)[:200]}) from error
    if not isinstance(document, Mapping):
        raise ExportError('contract_invalid', 'The profile is not a mapping.', path='profile',
                          remediation='Write the profile as a YAML mapping.')
    return dict(document)


def validate(document: Mapping | None) -> tuple[dict, list[str]]:
    """``(normalised profile, missing_fields)``. ``None`` (no ``--profile``) gives an empty
    draft profile with every required field missing."""
    document = dict(document or {'schema_version': SCHEMA})
    if document.get('schema_version') != SCHEMA:
        code = 'schema_version_unsupported' if 'schema_version' in document \
            else 'contract_invalid'
        raise ExportError(code, f'The profile must declare schema_version {SCHEMA}.',
                          path='schema_version',
                          remediation=f'Set schema_version: {SCHEMA}.')
    _walk(document, SHAPE)
    _check('subscription_id', document.get('subscription_id'), GUID, 'a subscription GUID')
    for name in ('resource_group', 'workspace', 'compute', 'experiment_name'):
        _check(name, document.get(name), NAME, 'an Azure resource name')
    _check('data_asset.name', _get(document, 'data_asset.name'), ASSET_NAME, 'an asset name')
    _check('environment.name', _get(document, 'environment.name'), ASSET_NAME,
           'an asset name')
    for dotted in ('data_asset.version', 'environment.version'):
        value = _get(document, dotted)
        if isinstance(value, int) and not isinstance(value, bool):
            value = str(value)
        if value is not None and str(value).lower() == 'latest':
            raise ExportError('contract_invalid', f'{dotted} may not be "latest".', path=dotted,
                              remediation='Name an explicit, immutable asset version.')
        _check(dotted, value, VERSION, 'an explicit version')
    image = _get(document, 'environment.base_image')
    if isinstance(image, str) and image.endswith(':latest'):
        raise ExportError('contract_invalid', 'environment.base_image may not use :latest.',
                          path='environment.base_image',
                          remediation='Pin the image by tag or, better, by digest.')
    _check('environment.base_image', image, IMAGE, 'an image reference with a tag or digest')
    mode = _get(document, 'identity.mode')
    if mode is not None and mode not in IDENTITY_MODES:
        raise ExportError('contract_invalid', 'identity.mode is not a known mechanism.',
                          path='identity.mode',
                          remediation=f'Use one of {", ".join(IDENTITY_MODES)}.')
    cloud = _get(document, 'ci.cloud_enabled')
    if cloud is not None and not isinstance(cloud, bool):
        raise ExportError('contract_invalid', 'ci.cloud_enabled must be true or false.',
                          path='ci.cloud_enabled', remediation='Write true or false.')
    connection = _get(document, 'devops.service_connection')
    _check('devops.service_connection', connection, NAME, 'a service connection name')
    normal = {
        'schema_version': SCHEMA,
        'subscription_id': document.get('subscription_id'),
        'resource_group': document.get('resource_group'),
        'workspace': document.get('workspace'),
        'compute': document.get('compute'),
        'experiment_name': document.get('experiment_name'),
        'data_asset': {'name': _get(document, 'data_asset.name'),
                       'version': _str(_get(document, 'data_asset.version'))},
        'environment': {'name': _get(document, 'environment.name'),
                        'version': _str(_get(document, 'environment.version')),
                        'base_image': image},
        'identity': {'mode': mode},
        'devops': {'service_connection': connection},
        'ci': {'cloud_enabled': bool(cloud) if cloud is not None else False},
    }
    missing = [field for field in REQUIRED if _get(normal, field) is None]
    return normal, missing


def _str(value):
    return None if value is None else str(value)


def operational_identity(normal: Mapping) -> dict:
    """The non-secret destination fields that enter ``export_id`` (spec §08)."""
    return {k: normal[k] for k in ('subscription_id', 'resource_group', 'workspace',
                                   'compute', 'experiment_name', 'data_asset',
                                   'environment', 'identity', 'ci')}
