"""Markdown and HTML renderers (M8) — two stylings of the shared report blocks.

Both read AnalysisResult only (via build_report) and perform no recomputation.
The HTML renderer is a styling pass over the same block structure; it emits a
self-contained document (inline CSS, no external references).
"""

from __future__ import annotations

import html as _html

from ..domain.models import AnalysisResult
from .report import Block, Bullets, Callout, Heading, Table, Text, build_report

_CALLOUT_LABEL = {"integrity": "Integrity", "warning": "Warning", "info": "Note"}


# --- Markdown ---------------------------------------------------------------


def render_markdown(result: AnalysisResult) -> str:
    return "\n\n".join(_md_block(b) for b in build_report(result)) + "\n"


def _md_block(b: Block) -> str:
    if isinstance(b, Heading):
        return "#" * b.level + " " + b.text
    if isinstance(b, Text):
        return b.text
    if isinstance(b, Bullets):
        return "\n".join("- " + _oneline(i) for i in b.items)
    if isinstance(b, Callout):
        return f"> **{_CALLOUT_LABEL[b.kind]}** - {_oneline(b.text)}"
    if isinstance(b, Table):
        head = "| " + " | ".join(b.headers) + " |"
        sep = "| " + " | ".join("---" for _ in b.headers) + " |"
        rows = ["| " + " | ".join(_md_cell(c) for c in row) + " |" for row in b.rows]
        return "\n".join([head, sep, *rows])
    return ""


def _oneline(s: str) -> str:
    return s.replace("\n", " ")


def _md_cell(s: str) -> str:
    return s.replace("|", "\\|").replace("\n", " ")


# --- HTML (styling pass over the same blocks) -------------------------------


def render_html(result: AnalysisResult) -> str:
    body = "\n".join(_html_block(b) for b in build_report(result))
    return _TEMPLATE.replace("{{BODY}}", body)


def _html_block(b: Block) -> str:
    if isinstance(b, Heading):
        return f"<h{b.level}>{_esc(b.text)}</h{b.level}>"
    if isinstance(b, Text):
        return f"<p>{_esc(b.text)}</p>"
    if isinstance(b, Bullets):
        return "<ul>" + "".join(f"<li>{_esc(i)}</li>" for i in b.items) + "</ul>"
    if isinstance(b, Callout):
        return (
            f'<div class="callout {b.kind}"><strong>{_CALLOUT_LABEL[b.kind]}</strong> '
            f"&mdash; {_esc(b.text)}</div>"
        )
    if isinstance(b, Table):
        head = "<tr>" + "".join(f"<th>{_esc(h)}</th>" for h in b.headers) + "</tr>"
        rows = "".join(
            "<tr>" + "".join(f"<td>{_esc(c)}</td>" for c in row) + "</tr>" for row in b.rows
        )
        return f"<table>{head}{rows}</table>"
    return ""


def _esc(s: str) -> str:
    return _html.escape(str(s))


_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Comparison Report</title>
<style>
body { font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
       max-width: 60rem; margin: 2rem auto; padding: 0 1rem; color: #1b1b1b; line-height: 1.5; }
h1 { border-bottom: 2px solid #eee; padding-bottom: .3rem; }
h2 { margin-top: 1.8rem; }
table { border-collapse: collapse; width: 100%; margin: .5rem 0; font-size: .95rem; }
th, td { border: 1px solid #ddd; padding: .3rem .6rem; text-align: left; }
th { background: #f5f5f5; }
ul { padding-left: 1.2rem; }
.callout { padding: .5rem .8rem; border-left: 4px solid; margin: .6rem 0; border-radius: 2px; }
.callout.integrity { border-color: #c0392b; background: #fdecea; }
.callout.warning   { border-color: #d68910; background: #fef5e7; }
.callout.info      { border-color: #7f8c8d; background: #f4f6f6; }
</style>
</head>
<body>
{{BODY}}
</body>
</html>
"""
