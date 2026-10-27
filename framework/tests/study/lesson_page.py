"""Helpers for the tests of the lesson-style report (``render_html.TEMPLATE_VERSION`` 4):
the page holds one edition per language (R27), the study language's first."""
from __future__ import annotations

import re

_EDITION = re.compile(r'<div class="ed" data-ed="(en|fr)" lang="(?:en|fr)"[^>]*>')


def editions(page: str) -> dict[str, str]:
    """``{language: the HTML of its edition}``, in page order."""
    starts = [(m.group(1), m.start()) for m in _EDITION.finditer(page)]
    out = {}
    for i, (lang, start) in enumerate(starts):
        end = starts[i + 1][1] if i + 1 < len(starts) else page.index('<script', start)
        out[lang] = page[start:end]
    return out


def primary(page: str) -> str:
    """The edition in the study language (shown alone without script)."""
    return next(iter(editions(page).values()))


def study_language(page: str) -> str:
    return re.search(r'data-study-lang="(en|fr)"', page).group(1)


def other(lang: str) -> str:
    return 'fr' if lang == 'en' else 'en'


def chapter_html(fragment: str, cid: str) -> str:
    """One chapter of an edition (``<section class="notion chapter" id="chN">``)."""
    start = fragment.index(f'<section class="notion chapter" id="{cid}"')
    end = fragment.find('<section class="notion chapter"', start + 10)
    if end < 0:
        end = fragment.find('</div></section>', start)
    return fragment[start:end if end > 0 else len(fragment)]
