"""A synthetic packager reserved for tests (``HYPOTRAIL_TEST_HOOKS=1`` only).

It exercises the packaging hook of :func:`hypotrail_runtime.capture_predictor` without
MLflow: it copies the native payload, describes it as a ``hypotrail.package_descriptor/1``
and verifies it on the bundle's parity rows. It is never a production packager; the
workshop format ``mlflow_pyfunc`` is workstream B's.
"""
from __future__ import annotations

import json
import pickle
import shutil
from pathlib import Path
from typing import Mapping

FORMAT = 'synthetic_test'


class SyntheticPackager:
    format = FORMAT

    def __init__(self, *, fail: bool = False):
        self.fail = fail
        self.calls: list[str] = []

    def package(self, native_bundle_dir: Path, output_dir: Path, parity_spec: Mapping):
        from hypotrail_runtime import canonical, verify_bundle
        self.calls.append('package')
        native = verify_bundle(native_bundle_dir)
        payload = native.manifest.payload_files[0].relative_path
        shutil.copyfile(Path(native_bundle_dir) / payload, Path(output_dir) / 'model.pkl')
        result = self.verify(native_bundle_dir, output_dir, parity_spec)
        files = [{'relative_path': 'model.pkl',
                  'size_bytes': (Path(output_dir) / 'model.pkl').stat().st_size,
                  'sha256': canonical.file_sha256(Path(output_dir) / 'model.pkl')}]
        doc = {'schema_version': 'hypotrail.package_descriptor/1', 'format': FORMAT,
               'artifact_id': '0' * 64, 'predictor_id': native.predictor_id, 'files': files,
               'signature': {'inputs': list(native.recipe.features),
                             'output': native.recipe.output_contract.kind},
               'environment': {'note': 'synthetic test packager'},
               'parity_result': result.model_dump(mode='json'), 'extensions': {}}
        doc['artifact_id'] = canonical.artifact_id(doc, exclude=('artifact_id',))
        return doc

    def verify(self, native_bundle_dir: Path, package_dir: Path, parity_spec: Mapping):
        from hypotrail_runtime.predictor import compare, frame_from_document
        self.calls.append('verify')
        root = Path(native_bundle_dir)
        with open(Path(package_dir) / 'model.pkl', 'rb') as fh:
            pipeline = pickle.load(fh)
        features = frame_from_document(json.loads((root / parity_spec['features_path'])
                                                  .read_bytes()))
        expected = json.loads((root / parity_spec['expected_outputs_path']).read_bytes())
        if self.fail:
            values = [v + 1.0 for v in expected['values']]
        elif expected['kind'] == 'binary_score':
            values = pipeline.predict_proba(features)[:, list(pipeline.classes_).index(1)]
        else:
            values = pipeline.predict(features)
        return compare(expected['values'], values, parity_spec['tolerance'])


def packager() -> SyntheticPackager:
    return SyntheticPackager()
