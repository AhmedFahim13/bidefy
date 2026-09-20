"""Render status.yaml, crawl checkpoints, model metrics and docs/product/*.md into site/."""
from __future__ import annotations

import html
import json
from pathlib import Path

import markdown
import yaml

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"

CSS = """
:root{--ink:#161925;--ink2:#4b5268;--ink3:#5b6178;--rule:#dce0ec;--bg:#f1f3f8;--card:#fff;--brand:#2a3a93;--ok:#15755b;--warn:#a5620b}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 -apple-system,Segoe UI,Roboto,sans-serif}
.wrap{max-width:1080px;margin:0 auto;padding:32px 24px}header{display:flex;justify-content:space-between;align-items:baseline;gap:16px;flex-wrap:wrap;border-bottom:2px solid var(--ink);padding-bottom:12px;margin-bottom:28px}
h1{font-size:28px;margin:0;letter-spacing:-.02em}h2{font-size:20px;margin:32px 0 12px}h3{font-size:16px;margin:0 0 6px}
.nav a{color:var(--brand);margin-left:16px;text-decoration:none;font-weight:600}
.grid{display:grid;gap:16px;grid-template-columns:repeat(auto-fit,minmax(240px,1fr))}
.card{background:var(--card);border:1px solid var(--rule);border-radius:6px;padding:16px 18px;box-shadow:0 1px 2px rgba(0,0,0,.04)}
.big{font-size:44px;font-weight:700;line-height:1;margin:6px 0}.muted{color:var(--ink3);font-size:13px;text-transform:uppercase;letter-spacing:.08em}
.bar{height:10px;background:var(--rule);border-radius:5px;overflow:hidden;margin:10px 0}.bar i{display:block;height:100%;background:var(--brand)}
ul{padding-left:18px;margin:8px 0}li{margin:4px 0}.tag{font-size:11px;padding:2px 7px;border-radius:3px;background:#e5e9fa;color:var(--brand);margin-left:6px;text-transform:uppercase}
.tag.fahim{background:#fbefd8;color:var(--warn)}.tag.done{background:#ddf0e8;color:var(--ok)}
table{border-collapse:collapse;width:100%;font-size:14px}th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--rule)}th{color:var(--ink3);font-size:12px;text-transform:uppercase}
.toc{columns:2;gap:24px;font-size:14px}.toc a{display:block;color:var(--ink2);text-decoration:none;padding:2px 0}
article{background:var(--card);border:1px solid var(--rule);border-radius:6px;padding:28px 32px;margin-top:20px}article h2{margin-top:0}
footer{margin-top:40px;color:var(--ink3);font-size:12px}
"""


def _weight(task: dict) -> int:
    """A task without an explicit weight counts as one unit."""
    return int(task.get("weight", 1))


def compute_progress(status: dict) -> dict:
    tasks = [dict(t, phase=ph["name"]) for ph in status["phases"] for t in ph.get("tasks", [])]
    total_w = sum(_weight(t) for t in tasks) or 1
    done_w = sum(_weight(t) for t in tasks if t["state"] == "done")
    phases = []
    for ph in status["phases"]:
        ph_tasks = ph.get("tasks", [])
        pw = sum(_weight(t) for t in ph_tasks) or 1
        pd = sum(_weight(t) for t in ph_tasks if t["state"] == "done")
        phases.append({"id": ph["id"], "name": ph["name"], "percent": round(100 * pd / pw), "tasks": ph_tasks})
    pending = [t for t in tasks if t["state"] != "done"]
    return {
        "percent": round(100 * done_w / total_w),
        "done_count": sum(1 for t in tasks if t["state"] == "done"),
        "total_count": len(tasks),
        "done": [t for t in tasks if t["state"] == "done"],
        "next_steps": pending[:3],
        "fahim_tasks": [t for t in pending if t["owner"] == "fahim"],
        "phases": phases,
    }


def _page(title: str, body: str, active: str) -> str:
    nav = "".join(
        f'<a href="{href}"{" aria-current=\"page\" style=\"text-decoration:underline\"" if key == active else ""}>{label}</a>'
        for key, href, label in (("dash", "index.html", "Dashboard"), ("doc", "doc.html", "Product document"), ("repo", "https://github.com/AhmedFahim13/bidefy", "Repo"))
    )
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title><style>{CSS}</style></head><body><div class="wrap">
<header><h1>{html.escape(title)}</h1><nav class="nav">{nav}</nav></header><main>{body}</main>
<footer>Built from status.yaml by tools/build_site.py. Zero production cost.</footer></div></body></html>"""


def _task_li(t: dict) -> str:
    owner = str(t.get("owner", ""))
    cls = "tag fahim" if owner == "fahim" else "tag"
    tag = f'<span class="{cls}">{html.escape(owner)}</span>'
    note = f' <span style="color:var(--ink3)">{html.escape(t["note"])}</span>' if t.get("note") else ""
    return f"<li>{html.escape(t['title'])}{tag}{note}</li>"


def _pct(v) -> str:
    return "n/a" if v is None else f"{v * 100:.1f}%"


def _x(v) -> str:
    return "n/a" if v is None else f"{v:.2f}x"


# The headline figures, in the order a reader should meet them. Everything else stays in
# models/metrics.json and on the accuracy page: a dashboard that prints every key prints none.
HEADLINE = (
    ("award_value_model", "Award, from the tender security", (
        ("security_mape", "median error", _pct),
        ("security_coverage_80", "inside the band", _pct),
        ("security_band_width_median", "typical band", _x),
        ("security_n", "awards scored", lambda v: f"{v:,}" if v is not None else "n/a"))),
    ("award_value_model", "Award, from entity history", (
        ("history_mape", "median error", _pct),
        ("history_coverage_80", "inside the band", _pct),
        ("history_band_width_median", "typical band", _x),
        ("deferral_rate", "declined overall", _pct))),
    ("category_classifier", "Category", (
        ("accuracy_acted", "accuracy on what it answers", _pct),
        ("deferral_rate", "declined", _pct),
        ("macro_f1", "macro F1", lambda v: "n/a" if v is None else f"{v:.3f}"),
        ("n_labels", "labels", lambda v: f"{v:,}" if v is not None else "n/a"),
        ("truth_coverage", "tenders with codes that identify a sector", _pct))),
)


def _metrics_table(metrics: dict | None) -> str:
    if not metrics:
        return "<p style='color:var(--ink3)'>No models trained yet.</p>"
    blocks = []
    for model, title, fields in HEADLINE:
        data = metrics.get(model) or {}
        if not data:
            continue
        rows = "".join(
            f"<tr><td>{html.escape(label)}</td><td>{html.escape(fmt(data.get(key)))}</td></tr>"
            for key, label, fmt in fields)
        trained = data.get("trained_at", "")
        blocks.append(f"<h3>{html.escape(title)}</h3><table>{rows}</table>"
                      f"<div class='muted' style='margin-top:6px'>trained {html.escape(str(trained))}</div>")
    return "<div class='grid'>" + "".join(f"<div class='card'>{b}</div>" for b in blocks) + "</div>"


def render_dashboard(status: dict, p: dict, crawl: dict, metrics: dict | None) -> str:
    crawl_rows = "".join(
        f"<tr><td>{html.escape(ep)}</td><td>{c.get('next_page', 1) - 1:,} / {c.get('total_pages', 0):,}</td>"
        f"<td>{html.escape(c.get('last_run_status', ''))}</td><td>{html.escape(c.get('updated_at', ''))}</td></tr>"
        for ep, c in crawl.items()
    ) or "<tr><td colspan=4>No crawl yet</td></tr>"
    metrics_html = _metrics_table(metrics)
    phases_html = "".join(
        f"<div class='card'><h3>{html.escape(ph['name'])}</h3><div class='bar'><i style='width:{ph['percent']}%'></i></div>"
        f"<div class='muted'>{ph['percent']}%</div><ul>{''.join(_task_li(t) for t in ph['tasks'])}</ul></div>"
        for ph in p["phases"]
    )
    body = f"""
<div class="grid">
  <div class="card"><div class="muted">Overall progress</div><div class="big">{p['percent']}%</div>
    <div class="bar"><i style="width:{p['percent']}%"></i></div><div class="muted">{p['done_count']} of {p['total_count']} tasks done. Launch target {html.escape(str(status.get('launch_target', '')))}</div></div>
  <div class="card"><div class="muted">Next three steps</div><ul>{''.join(_task_li(t) for t in p['next_steps'])}</ul></div>
  <div class="card"><div class="muted">Tasks only Fahim can do</div><ul>{''.join(_task_li(t) for t in p['fahim_tasks']) or '<li>None open</li>'}</ul></div>
  <div class="card"><div class="muted">Live</div><ul>
    <li><a href="https://bidefy.vercel.app">The site</a></li>
    <li><a href="https://bidefy.iba-jobs.workers.dev/api/v1/health">API health</a></li>
    <li><a href="doc.html">Product document, including what it gets right</a></li>
    <li><a href="https://github.com/AhmedFahim13/bidefy/actions">Nightly runs</a></li></ul></div>
</div>
<h2>Crawl</h2><div class="card"><table><tr><th>Endpoint</th><th>Pages</th><th>Last run</th><th>Updated</th></tr>{crawl_rows}</table></div>
<h2>Models</h2>{metrics_html}
<h2>Done</h2><div class="card"><ul>{''.join(_task_li(t) for t in p['done']) or '<li>Nothing yet</li>'}</ul></div>
<h2>Phases</h2><div class="grid">{phases_html}</div>"""
    return _page(f"{status['project']} command centre", body, "dash")


def render_doc(status: dict, sections: list[tuple[str, str]]) -> str:
    toc = "".join(f'<a href="#s{i}">{i}. {html.escape(t)}</a>' for i, (t, _) in enumerate(sections, 1))
    body = f'<div class="card"><div class="muted">Contents</div><div class="toc">{toc}</div></div>' + "".join(
        f'<article id="s{i}"><h2>{i}. {html.escape(t)}</h2>{b}</article>' for i, (t, b) in enumerate(sections, 1)
    )
    return _page(f"{status['project']} product document", body, "doc")


def load_sections(doc_dir: Path) -> list[tuple[str, str]]:
    out = []
    for path in sorted(doc_dir.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        first, _, rest = text.partition("\n")
        title = first.lstrip("# ").strip() if first.startswith("#") else path.stem
        rendered = markdown.markdown(rest if first.startswith("#") else text, extensions=["tables"])
        out.append((title, _demote_headings(rendered)))
    return out


def _demote_headings(rendered: str) -> str:
    """Shift h2/h3 in a section body to h3/h4 so each section's own h2 stays the top level."""
    for level in (3, 2):
        rendered = rendered.replace(f"<h{level}>", f"<h{level + 1}>").replace(f"</h{level}>", f"</h{level + 1}>")
    return rendered


def main() -> None:
    status = yaml.safe_load((ROOT / "status.yaml").read_text(encoding="utf-8"))
    crawl = {}
    for path in sorted((ROOT / "checkpoints").glob("*.json")) if (ROOT / "checkpoints").exists() else []:
        crawl[path.stem] = json.loads(path.read_text(encoding="utf-8"))
    metrics_path = ROOT / "models" / "metrics.json"
    metrics = json.loads(metrics_path.read_text(encoding="utf-8")) if metrics_path.exists() else None
    p = compute_progress(status)
    SITE.mkdir(exist_ok=True)
    (SITE / "index.html").write_text(render_dashboard(status, p, crawl, metrics), encoding="utf-8")
    (SITE / "doc.html").write_text(render_doc(status, load_sections(ROOT / "docs" / "product")), encoding="utf-8")
    print(f"site built: {p['percent']}% complete, {len(crawl)} checkpoints, {len(list((ROOT / 'docs' / 'product').glob('*.md')))} doc sections")


if __name__ == "__main__":
    main()
