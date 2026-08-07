"""Markdown and HTML renderers (M8) — two stylings of the shared report blocks.

Both read AnalysisResult only (via build_report) and perform no recomputation.
The HTML renderer is a styling pass over the same block structure; it emits a
self-contained document (inline CSS, no external references).
"""

from __future__ import annotations

import html as _html

from ..domain.models import AnalysisResult
from .ai import AiSummary
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


# --- HTML (a styling pass over the same blocks) -----------------------------
# This branch owns HTML structure + CSS only. It reads the same blocks the
# Markdown renderer does; it inspects a couple of Table header tuples (from
# report.py) purely to style them (chips, before->after arrow, signed deltas).
# If those header labels ever change, tables fall back to a plain rendering.

_STRUCTURAL_HEADERS = ("Change", "Columns")
_CHANGES_HEADERS = ("Record", "Column", "Before", "After", "Delta", "% change")

_AI_PLACEHOLDER = (
    '<section class="card ai-summary" aria-label="AI summary">'
    "<h2>AI Summary</h2>"
    '<p class="placeholder">Not generated. Enable the optional AI provider to include a '
    "plain-language narrative of these findings here.</p>"
    "</section>"
)


def render_html(result: AnalysisResult, ai: AiSummary = AiSummary(False, ())) -> str:
    blocks = build_report(result)
    split = next(
        (i for i, b in enumerate(blocks) if isinstance(b, Heading) and b.level == 2),
        len(blocks),
    )
    cards = _cards(blocks[split:])
    cards.insert(1, _ai_card(ai, result))  # AI summary sits just below Key findings
    body = '<div class="report">' + _header(blocks[:split]) + "".join(cards) + "</div>"
    return _TEMPLATE.replace("{{BODY}}", body)


def _ai_card(ai: AiSummary, result: AnalysisResult) -> str:
    if not ai.requested:
        return _AI_PLACEHOLDER
    if ai.bullets:
        items = "".join(f"<li>{_esc(b)}</li>" for b in ai.bullets)
        return (
            '<section class="card ai-summary ready" aria-label="AI summary"><h2>AI Summary</h2>'
            '<p class="ai-note">AI-generated from the findings above; the verified findings '
            "remain the source of truth.</p>"
            f"<ul>{items}</ul></section>"
        )
    items = "".join(f"<li>{_esc(i.message)}</li>" for i in result.insights)
    return (
        '<section class="card ai-summary" aria-label="AI summary"><h2>AI Summary</h2>'
        '<p class="placeholder">AI summary unavailable - showing the verified findings.</p>'
        f"<ul>{items}</ul></section>"
    )


def _header(blocks: list) -> str:
    parts = []
    for b in blocks:
        if isinstance(b, Heading):
            parts.append(f"<h1>{_esc(b.text)}</h1>")
        elif isinstance(b, Text):
            parts.append(f'<p class="subtitle">{_esc(b.text)}</p>')
        else:  # a callout (positional / not-comparable alignment) stays prominent
            parts.append(_html_block(b))
    return f'<header class="report-header">{"".join(parts)}</header>'


def _cards(blocks: list) -> list[str]:
    out: list[str] = []
    current: list = []
    for b in blocks:
        if isinstance(b, Heading) and b.level == 2 and current:
            out.append(_card(current))
            current = [b]
        else:
            current.append(b)
    if current:
        out.append(_card(current))
    return out


def _card(blocks: list) -> str:
    return '<section class="card">' + "".join(_html_block(b) for b in blocks) + "</section>"


def _html_block(b: Block) -> str:
    if isinstance(b, Heading):
        return f"<h{b.level}>{_esc(b.text)}</h{b.level}>"
    if isinstance(b, Text):
        return f"<p>{_esc(b.text)}</p>"
    if isinstance(b, Bullets):
        return "<ul>" + "".join(f"<li>{_esc(i)}</li>" for i in b.items) + "</ul>"
    if isinstance(b, Callout):
        return (
            f'<div class="callout {b.kind}">'
            f'<span class="callout-tag">{_CALLOUT_LABEL[b.kind]}</span>'
            f'<span class="callout-body">{_esc(b.text)}</span></div>'
        )
    if isinstance(b, Table):
        return _table(b)
    return ""


def _table(t: Table) -> str:
    if t.headers == _STRUCTURAL_HEADERS:
        return _structural_table(t)
    if t.headers == _CHANGES_HEADERS:
        return _changes_table(t)
    head = "<tr>" + "".join(f"<th>{_esc(h)}</th>" for h in t.headers) + "</tr>"
    rows = "".join(
        "<tr>" + "".join(f"<td>{_esc(c)}</td>" for c in row) + "</tr>" for row in t.rows
    )
    return f'<div class="table-wrap"><table class="data-table"><thead>{head}</thead><tbody>{rows}</tbody></table></div>'


def _structural_table(t: Table) -> str:
    rows = []
    for change, columns in t.rows:
        chips = "".join(f'<span class="chip">{_esc(c)}</span>' for c in columns.split(", "))
        rows.append(
            f'<tr><th scope="row">{_esc(change)}</th>'
            f'<td><div class="chips">{chips}</div></td></tr>'
        )
    return f'<div class="table-wrap"><table class="data-table structural"><tbody>{"".join(rows)}</tbody></table></div>'


def _changes_table(t: Table) -> str:
    head = "<tr>" + "".join(f"<th>{_esc(h)}</th>" for h in t.headers) + "</tr>"
    body = []
    for record, column, before, after, delta, pct in t.rows:
        body.append(
            "<tr>"
            f"<td>{_esc(record)}</td>"
            f"<td>{_esc(column)}</td>"
            f'<td class="before">{_esc(before)}</td>'
            f'<td class="after"><span class="arrow">&rarr;</span>{_esc(after)}</td>'
            f'<td class="num {_sign(delta)}">{_esc(delta)}</td>'
            f'<td class="num {_sign(pct)}">{_esc(pct)}</td>'
            "</tr>"
        )
    return f'<div class="table-wrap"><table class="data-table changes"><thead>{head}</thead><tbody>{"".join(body)}</tbody></table></div>'


def _sign(value: str) -> str:
    if value.startswith("+"):
        return "up"
    if value.startswith("-"):
        return "down"
    return ""


def _esc(s: str) -> str:
    return _html.escape(str(s))


_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Comparison Report</title>
<style>
:root {
  --ink:#1a1f2b; --muted:#5b6472; --faint:#8a92a0; --line:#e4e7ee; --bg:#f5f6f8;
  --card:#ffffff; --accent:#1f3a5f; --up:#15803d; --down:#b42318;
  --int-border:#b42318; --int-bg:#fdf3f2; --warn-border:#b7791f; --warn-bg:#fdf6ec;
  --info-border:#8a92a0; --info-bg:#f6f8fa; --chip-bg:#eef1f6;
}
* { box-sizing:border-box; }
body {
  margin:0; padding:2rem 1rem; background:var(--bg); color:var(--ink);
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  font-variant-numeric:tabular-nums; line-height:1.6; -webkit-font-smoothing:antialiased;
}
.report { max-width:900px; margin:0 auto; }
.report-header {
  background:var(--card); border:1px solid var(--line); border-top:3px solid var(--accent);
  border-radius:8px; padding:1.4rem 1.6rem; margin-bottom:1.25rem;
}
h1 { margin:0 0 .3rem; font-size:1.55rem; font-weight:650; letter-spacing:-.01em; }
.subtitle { margin:0; color:var(--muted); font-size:.95rem; }
.card {
  background:var(--card); border:1px solid var(--line); border-radius:8px;
  padding:1.25rem 1.6rem; margin-bottom:1.25rem;
}
.card h2 {
  margin:0 0 .9rem; padding-bottom:.55rem; border-bottom:1px solid var(--line);
  color:var(--accent); font-size:.82rem; font-weight:650; text-transform:uppercase;
  letter-spacing:.06em;
}
p { margin:.55rem 0; }
ul { margin:.5rem 0; padding-left:1.2rem; }
li { margin:.3rem 0; }
.ai-summary { border-style:dashed; background:transparent; }
.ai-summary h2 { color:var(--muted); border-bottom-color:transparent; margin-bottom:.3rem; }
.ai-summary .placeholder { color:var(--faint); font-style:italic; margin:0; }
.ai-summary.ready { border-style:solid; }
.ai-summary.ready h2 { color:var(--accent); border-bottom-color:var(--line); }
.ai-note { color:var(--muted); font-style:italic; font-size:.85rem; margin:0 0 .4rem; }
.callout {
  display:flex; gap:.75rem; align-items:baseline; margin:.65rem 0;
  padding:.8rem 1rem; border:1px solid var(--line); border-left-width:4px; border-radius:6px;
}
.callout-tag {
  flex:none; font-size:.68rem; font-weight:700; letter-spacing:.06em; text-transform:uppercase;
  color:#fff; padding:.15rem .5rem; border-radius:4px;
}
.callout-body { color:var(--ink); }
.callout.integrity { border-left-color:var(--int-border); background:var(--int-bg); }
.callout.integrity .callout-tag { background:var(--int-border); }
.callout.warning { border-left-color:var(--warn-border); background:var(--warn-bg); }
.callout.warning .callout-tag { background:var(--warn-border); }
.callout.info { border-left-color:var(--info-border); background:var(--info-bg); }
.callout.info .callout-tag { background:var(--info-border); }
.table-wrap { overflow-x:auto; }
.data-table { width:100%; border-collapse:collapse; font-size:.9rem; }
.data-table th, .data-table td {
  padding:.5rem .7rem; text-align:left; border-bottom:1px solid var(--line); vertical-align:top;
}
.data-table thead th {
  color:var(--muted); font-size:.72rem; font-weight:650; text-transform:uppercase;
  letter-spacing:.04em; border-bottom:2px solid var(--line);
}
.data-table tbody tr:last-child td, .data-table tbody tr:last-child th { border-bottom:none; }
.data-table td.num { text-align:right; white-space:nowrap; }
.data-table td.num.up { color:var(--up); }
.data-table td.num.down { color:var(--down); }
.changes td.before { color:var(--muted); }
.changes td.after .arrow { color:var(--faint); margin-right:.35rem; }
.structural th[scope="row"] { color:var(--muted); font-weight:650; white-space:nowrap; width:8.5rem; }
.chips { display:flex; flex-wrap:wrap; gap:.35rem; }
.chip {
  background:var(--chip-bg); border:1px solid var(--line); border-radius:999px;
  padding:.12rem .6rem; font-size:.8rem; white-space:nowrap;
}
@media (max-width:640px) {
  body { padding:1rem .5rem; }
  .report-header, .card { padding:1rem 1.1rem; }
}
@media (prefers-reduced-motion:reduce) {
  * { transition:none !important; animation:none !important; }
}
@media print {
  body { background:#fff; padding:0; }
  .card, .report-header { box-shadow:none; }
}
</style>
</head>
<body>
{{BODY}}
</body>
</html>
"""
