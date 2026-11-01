# PyPI placeholders

Empty releases (version 0.0.0, no code) that reserve the names `hypotrail` and
`hypotrail-runtime` on PyPI until the engine is published for real. Built wheels contain
only their metadata. Publish them once, from the repository root, with a PyPI API token:

```sh
uv build --out-dir dist packaging/pypi-placeholder/hypotrail
uv build --out-dir dist packaging/pypi-placeholder/hypotrail-runtime
uv publish --token pypi-XXXX dist/*
```

A later real release (0.1.0 or above) of the engine supersedes 0.0.0.
