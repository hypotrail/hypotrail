"""Module versions declared equivalent for the results they computed (v0.3, WP-F1).

A result is current only while the source of every module of its code fingerprint is the
one it was computed with (CLI-CONTRACT §6 row 11). An engine change that leaves the values of
earlier results unchanged would still make every one of them "code changed", including the
one evaluation of an opened final test, which can never be run again.

This table lists, per fingerprinted module, source digests (sha256 of the file bytes) of an
earlier version whose results the current code would compute identically. A result whose
module digest is listed here is not "code changed" for that module
(:meth:`mlkit.study.read.Study.code_changed`). An entry is a claim made by the change that
introduced it, with its reason and the tests that back it; it never covers a change of what
an earlier configuration computes.

WP-F1 (ADR 0007): ``activities``, ``fit``, ``governance`` and ``diagnostics`` gained the
variants 2 and 3, nested tuning, the model families, the stored selection and the linear
checks. For every configuration a study could hold before (the baseline, the candidate, a
regularisation or drop-group variant, their evaluations, the opening of the final test, the
diagnostics), the values are those the earlier code computed; results computed before only
lack the new additive keys (``selection`` of an evaluation, ``linear_checks`` of the
development diagnostics), which the view reads as absent.

Pure: no I/O.
"""
from __future__ import annotations

# The integrator tip before WP-F1 (9fa1b2a): the digests of the modules WP-F1 changed.
WP_F1_BASE = 'v0.3 before WP-F1 (integrator tip 9fa1b2a)'
EQUIVALENT: dict[str, dict[str, str]] = {
    'mlkit.study.activities': {
        '312bf5b3e72f130bfdb7a0d5216486a739c4fa57e4fac10be7fb249a96d96ecd': WP_F1_BASE},
    'mlkit.study.fit': {
        '8ca21144b689113a6390e185ee74042c32581509e9766a82c0b591f5589820a6': WP_F1_BASE},
    'mlkit.study.governance': {
        '38d02a4e1a2bb7a0a8805cb485f25484c3b973965aff604d18aa2c394cb4e447': WP_F1_BASE},
    'mlkit.study.diagnostics': {
        'ca4a6a3b886c9e35cb07a1c7823c34c14de70d8866b6476c3932508f4a674d9b': WP_F1_BASE},
}


def equivalent(module: str, sha: str | None) -> bool:
    """Whether a result computed with ``module`` at digest ``sha`` holds under the current
    source of that module (an earlier version declared equivalent)."""
    return sha is not None and sha in EQUIVALENT.get(module, {})
