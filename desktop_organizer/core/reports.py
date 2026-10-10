"""Save a record of a preview or a past run as a spreadsheet (CSV) or a web page (HTML)."""

from __future__ import annotations

import csv
import html
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from desktop_organizer import APP_NAME, __version__
from desktop_organizer.core.config import describe_pattern
from desktop_organizer.core.history import History
from desktop_organizer.core.rules import PlannedMove

FORMATS = {".csv": "Spreadsheet (*.csv)", ".html": "Web page (*.html)"}


@dataclass(frozen=True)
class ReportRow:
    source: Path
    destination: Path
    note: str = ""  # the rule that decided the move, or "Undone"

    @property
    def name(self) -> str:
        return self.source.name

    @property
    def renamed(self) -> bool:
        return self.source.name != self.destination.name


@dataclass
class Report:
    title: str
    details: list[tuple[str, str]]  # label, value: shown above the table
    rows: list[ReportRow]
    note_heading: str = "Rule"


def preview_report(folder: Path, pattern: str, moves: Iterable[PlannedMove]) -> Report:
    rows = [ReportRow(m.source, m.target_dir / m.target_name, m.rule or "") for m in moves]
    return Report(
        title=f"Preview for {folder.name or folder}",
        details=[("Folder", str(folder)), ("Structure", describe_pattern(pattern)),
                 ("Files", str(len(rows))), ("Status", "Preview only. Nothing has been moved.")],
        rows=rows,
    )


def run_report(history: History, run_id: int) -> Report:
    run = history.get_run(run_id)
    if run is None:
        raise ValueError(f"There is no run #{run_id} in the history.")
    rows = [ReportRow(source, destination, "Undone" if undone else "")
            for source, destination, undone in history.moves_for_run(run_id)]
    status = f"Undone on {run.undone_at:%Y-%m-%d %H:%M}" if run.undone_at else "Files moved"
    return Report(
        title=f"Run #{run.id} in {run.folder.name or run.folder}",
        details=[("Folder", str(run.folder)), ("When", f"{run.started_at:%Y-%m-%d %H:%M}"),
                 ("Structure", describe_pattern(run.structure)), ("Files", str(len(rows))),
                 ("Status", status)],
        rows=rows,
        note_heading="Status",
    )


def save(report: Report, path: Path) -> Path:
    """Write ``report`` as CSV or HTML, chosen by the file extension (HTML if unknown)."""
    if path.suffix.lower() not in FORMATS:
        path = path.with_suffix(".html")
    if path.suffix.lower() == ".csv":
        _write_csv(report, path)
    else:
        path.write_text(to_html(report), encoding="utf-8")
    return path


def _write_csv(report: Report, path: Path) -> None:
    # utf-8-sig so Excel shows accented file names correctly.
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)
        writer.writerow(["File", "From", "To", "New name", report.note_heading])
        for row in report.rows:
            writer.writerow([row.name, str(row.source.parent), str(row.destination.parent),
                             row.destination.name if row.renamed else "", row.note])


def to_html(report: Report) -> str:
    e = html.escape
    details = "".join(f"<dt>{e(label)}</dt><dd>{e(value)}</dd>" for label, value in report.details)
    body = "".join(
        "<tr>"
        f"<td>{e(row.name)}</td>"
        f"<td>{e(str(row.source.parent))}</td>"
        f"<td>{e(str(row.destination.parent))}</td>"
        f"<td>{e(row.destination.name) if row.renamed else ''}</td>"
        f"<td>{e(row.note)}</td>"
        "</tr>"
        for row in report.rows
    ) or '<tr><td colspan="5" class="empty">No files.</td></tr>'
    created = datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(report.title)}</title>
<style>
  :root {{ --bg: #ffffff; --fg: #1f2328; --muted: #656d76; --line: #d0d7de; --head: #f6f8fa; --accent: #2f6feb; }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --bg: #0d1117; --fg: #e6edf3; --muted: #8d96a0; --line: #30363d; --head: #161b22; --accent: #4493f8; }}
  }}
  body {{ margin: 0; padding: 24px 16px; background: var(--bg); color: var(--fg);
         font: 14px/1.5 "Segoe UI", system-ui, sans-serif; }}
  main {{ max-width: 1100px; margin: 0 auto; }}
  h1 {{ font-size: 22px; margin: 0 0 4px; }}
  .by {{ color: var(--muted); margin: 0 0 16px; }}
  dl {{ display: grid; grid-template-columns: max-content 1fr; gap: 4px 16px; margin: 0 0 20px; }}
  dt {{ color: var(--muted); }}
  dd {{ margin: 0; overflow-wrap: anywhere; }}
  .scroll {{ overflow-x: auto; border: 1px solid var(--line); border-radius: 8px; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ text-align: left; padding: 6px 10px; border-bottom: 1px solid var(--line); vertical-align: top;
           overflow-wrap: anywhere; }}
  th {{ background: var(--head); font-weight: 600; }}
  tr:last-child td {{ border-bottom: 0; }}
  .empty {{ color: var(--muted); text-align: center; }}
</style>
</head>
<body>
<main>
<h1>{e(report.title)}</h1>
<p class="by">{e(APP_NAME)} {e(__version__)} · saved {created}</p>
<dl>{details}</dl>
<div class="scroll">
<table>
<thead><tr><th>File</th><th>From</th><th>To</th><th>New name</th><th>{e(report.note_heading)}</th></tr></thead>
<tbody>{body}</tbody>
</table>
</div>
</main>
</body>
</html>
"""
