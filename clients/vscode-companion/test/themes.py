"""VS Code theme variable sets for the webview browser tests (WP-A5).

A real VS Code webview sets ``--vscode-*`` custom properties on ``<html>`` and a theme class
on ``<body>`` (``vscode-light``, ``vscode-dark``, ``vscode-high-contrast``). The offline
Playwright page has none, so the panel falls back to the mockup colours. These sets are the
values of the built-in themes Light+, Dark+, and Dark High Contrast (VS Code 1.9x defaults)
for the variables the panel reads, so a test can check the theming under the variables the
real host gives. An unset variable (``None``) is one the theme leaves undefined: Light+ and
Dark+ define no ``contrastBorder`` and no ``button.border``; High Contrast draws buttons as
black on black and relies on them, which is the failure the UI review found.

``apply(page, name)`` sets them through CSSOM (``style.setProperty``), which the webview's
CSP allows, and reports the theme kind as ``data-vscode-theme-kind`` like VS Code does.
"""
from __future__ import annotations

COMMON = {
    '--vscode-font-family': 'system-ui, -apple-system, "Segoe UI", sans-serif',
    '--vscode-font-size': '13px',
    '--vscode-editor-font-family': 'ui-monospace, Menlo, Consolas, monospace',
}

LIGHT_PLUS = {
    '--vscode-editor-background': '#ffffff',
    '--vscode-sideBar-background': '#f3f3f3',
    '--vscode-panel-border': 'rgba(128, 128, 128, 0.35)',
    '--vscode-foreground': '#616161',
    '--vscode-descriptionForeground': '#717171',
    '--vscode-textLink-foreground': '#006ab1',
    '--vscode-focusBorder': '#0090f1',
    '--vscode-button-background': '#007acc',
    '--vscode-button-foreground': '#ffffff',
    '--vscode-button-secondaryBackground': '#5f6a79',
    '--vscode-button-secondaryForeground': '#ffffff',
    '--vscode-input-background': '#ffffff',
    '--vscode-input-foreground': '#616161',
    '--vscode-input-border': '#cecece',
    '--vscode-inputValidation-warningBackground': '#f6f5d2',
    '--vscode-inputValidation-warningBorder': '#b89500',
    '--vscode-inputValidation-errorBackground': '#f2dede',
    '--vscode-inputValidation-errorBorder': '#be1100',
    '--vscode-errorForeground': '#a1260d',
    '--vscode-textBlockQuote-background': 'rgba(127, 127, 127, 0.1)',
    '--vscode-textBlockQuote-border': 'rgba(0, 122, 204, 0.5)',
    '--vscode-charts-foreground': '#616161',
    '--vscode-charts-lines': 'rgba(97, 97, 97, 0.5)',
    '--vscode-charts-red': '#e51400',
    '--vscode-charts-blue': '#1a85ff',
    '--vscode-charts-yellow': '#bf8803',
    '--vscode-charts-orange': '#d18616',
    '--vscode-charts-green': '#388a34',
    '--vscode-charts-purple': '#652d90',
    '--vscode-contrastBorder': None,
    '--vscode-button-border': None,
}

DARK_PLUS = {
    '--vscode-editor-background': '#1e1e1e',
    '--vscode-sideBar-background': '#252526',
    '--vscode-panel-border': 'rgba(128, 128, 128, 0.35)',
    '--vscode-foreground': '#cccccc',
    '--vscode-descriptionForeground': 'rgba(204, 204, 204, 0.7)',
    '--vscode-textLink-foreground': '#3794ff',
    '--vscode-focusBorder': '#007fd4',
    '--vscode-button-background': '#0e639c',
    '--vscode-button-foreground': '#ffffff',
    '--vscode-button-secondaryBackground': '#3a3d41',
    '--vscode-button-secondaryForeground': '#ffffff',
    '--vscode-input-background': '#3c3c3c',
    '--vscode-input-foreground': '#cccccc',
    '--vscode-input-border': None,
    '--vscode-inputValidation-warningBackground': '#352a05',
    '--vscode-inputValidation-warningBorder': '#b89500',
    '--vscode-inputValidation-errorBackground': '#5a1d1d',
    '--vscode-inputValidation-errorBorder': '#be1100',
    '--vscode-errorForeground': '#f48771',
    '--vscode-textBlockQuote-background': 'rgba(127, 127, 127, 0.1)',
    '--vscode-textBlockQuote-border': 'rgba(0, 122, 204, 0.5)',
    '--vscode-charts-foreground': '#cccccc',
    '--vscode-charts-lines': 'rgba(204, 204, 204, 0.5)',
    '--vscode-charts-red': '#f14c4c',
    '--vscode-charts-blue': '#3794ff',
    '--vscode-charts-yellow': '#cca700',
    '--vscode-charts-orange': '#d18616',
    '--vscode-charts-green': '#89d185',
    '--vscode-charts-purple': '#b180d7',
    '--vscode-contrastBorder': None,
    '--vscode-button-border': None,
}

# Dark High Contrast: black surfaces, cyan borders, orange focus; buttons are black on
# black, so only `button.border` (= contrastBorder) shows where a button is.
HIGH_CONTRAST = {
    '--vscode-editor-background': '#000000',
    '--vscode-sideBar-background': '#000000',
    '--vscode-panel-border': '#6fc3df',
    '--vscode-foreground': '#ffffff',
    '--vscode-descriptionForeground': '#ffffff',
    '--vscode-textLink-foreground': '#21a6ff',
    '--vscode-focusBorder': '#f38518',
    '--vscode-contrastBorder': '#6fc3df',
    '--vscode-contrastActiveBorder': '#f38518',
    '--vscode-button-background': '#000000',
    '--vscode-button-foreground': '#ffffff',
    '--vscode-button-border': '#6fc3df',
    '--vscode-button-secondaryBackground': '#000000',
    '--vscode-button-secondaryForeground': '#ffffff',
    '--vscode-input-background': '#000000',
    '--vscode-input-foreground': '#ffffff',
    '--vscode-input-border': '#6fc3df',
    '--vscode-inputValidation-warningBackground': '#000000',
    '--vscode-inputValidation-warningBorder': '#6fc3df',
    '--vscode-inputValidation-errorBackground': '#000000',
    '--vscode-inputValidation-errorBorder': '#6fc3df',
    '--vscode-errorForeground': '#f48771',
    '--vscode-textBlockQuote-background': '#000000',
    '--vscode-textBlockQuote-border': '#ffffff',
    '--vscode-charts-foreground': '#ffffff',
    '--vscode-charts-lines': 'rgba(255, 255, 255, 0.5)',
    '--vscode-charts-red': '#f48771',
    '--vscode-charts-blue': '#3794ff',
    '--vscode-charts-yellow': '#cca700',
    '--vscode-charts-orange': '#d18616',
    '--vscode-charts-green': '#89d185',
    '--vscode-charts-purple': '#b180d7',
}

# v0.3 (WP-E2): the current defaults, Light Modern and Dark Modern (VS Code 1.9x), which the
# design system was drawn against (docs/design/companion-v0.3-mockups/ds.css).
LIGHT_MODERN = {**LIGHT_PLUS,
    '--vscode-editor-background': '#ffffff', '--vscode-editor-foreground': '#3b3b3b',
    '--vscode-sideBar-background': '#f8f8f8', '--vscode-panel-border': '#e5e5e5',
    '--vscode-foreground': '#3b3b3b', '--vscode-descriptionForeground': '#6b6b6b',
    '--vscode-textLink-foreground': '#005fb8', '--vscode-focusBorder': '#005fb8',
    '--vscode-button-background': '#005fb8', '--vscode-button-foreground': '#ffffff',
    '--vscode-button-secondaryBackground': '#e5e5e5', '--vscode-button-secondaryForeground': '#3b3b3b',
    '--vscode-input-border': '#cecece', '--vscode-widget-border': '#e5e5e5'}
DARK_MODERN = {**DARK_PLUS,
    '--vscode-editor-background': '#1f1f1f', '--vscode-editor-foreground': '#cccccc',
    '--vscode-sideBar-background': '#181818', '--vscode-panel-border': '#2b2b2b',
    '--vscode-foreground': '#cccccc', '--vscode-descriptionForeground': '#9d9d9d',
    '--vscode-textLink-foreground': '#4daafc', '--vscode-focusBorder': '#0078d4',
    '--vscode-button-background': '#0078d4', '--vscode-button-foreground': '#ffffff',
    '--vscode-button-secondaryBackground': '#313131', '--vscode-button-secondaryForeground': '#cccccc',
    '--vscode-input-background': '#313131', '--vscode-input-border': '#3c3c3c', '--vscode-widget-border': '#313131'}

THEMES = {
    'light-modern': ('vscode-light', 'light', LIGHT_MODERN),
    'dark-modern': ('vscode-dark', 'dark', DARK_MODERN),
    'light': ('vscode-light', 'light', LIGHT_PLUS),
    'dark': ('vscode-dark', 'dark', DARK_PLUS),
    'hc': ('vscode-high-contrast', 'dark', HIGH_CONTRAST),
}


def scheme(name: str) -> str:
    """The ``prefers-color-scheme`` a theme runs under (High Contrast dark is dark)."""
    return THEMES[name][1]


def apply(page, name: str) -> None:
    """Set the theme's variables on ``<html>`` and its class on ``<body>``, as VS Code does."""
    body_class, _scheme, variables = THEMES[name]
    values = {**COMMON, **variables}
    page.evaluate(
        """([cls, vars]) => {
          const root = document.documentElement;
          for (const [k, v] of Object.entries(vars)) {
            if (v === null) root.style.removeProperty(k); else root.style.setProperty(k, v);
          }
          document.body.classList.remove('vscode-light', 'vscode-dark', 'vscode-high-contrast');
          document.body.classList.add(cls);
          document.body.setAttribute('data-vscode-theme-kind', cls);
        }""", [body_class, values])
