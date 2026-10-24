"""Live view for the projector: every task and every agent step, as it happens.

Callers never see this. It's for the demo and for debugging.
"""
import asyncio
import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse

from ..services import services

router = APIRouter()


@router.get("/api/tasks")
async def list_tasks(request: Request):
    s = services(request)
    return [{**t.to_dict(), "events": s.store.events(t.id)} for t in s.store.recent(20)]


@router.get("/api/tasks/{task_id}")
async def get_task(request: Request, task_id: str):
    s = services(request)
    t = s.store.get(task_id)
    if not t:
        raise HTTPException(404)
    return {**t.to_dict(), "events": s.store.events(t.id)}


@router.get("/live/stream")
async def stream(request: Request):
    s = services(request)
    queue = s.bus.subscribe()

    async def events():
        try:
            yield ": connected\n\n"
            while not await request.is_disconnected():
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=15)
                    yield f"data: {json.dumps(msg)}\n\n"
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            s.bus.unsubscribe(queue)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/live", response_class=HTMLResponse)
async def live_page():
    return LIVE_HTML


LIVE_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Dial-Up live</title>
<style>
:root{--bg:#0d1117;--card:#161b22;--line:#30363d;--text:#e6edf3;--dim:#8b949e;
--run:#d29922;--wait:#58a6ff;--ok:#3fb950;--bad:#f85149}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:16px/1.45 ui-monospace,SFMono-Regular,Menlo,monospace}
header{display:flex;justify-content:space-between;align-items:baseline;padding:20px 24px;border-bottom:1px solid var(--line)}
h1{margin:0;font-size:24px}
#conn{color:var(--dim);font-size:14px}
main{padding:20px 24px;display:grid;gap:16px}
.task{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px}
.top{display:flex;gap:12px;align-items:center;flex-wrap:wrap}
.id{color:var(--dim)}
.goal{font-size:20px;flex:1;min-width:200px}
.pill{padding:2px 10px;border-radius:999px;font-size:13px;border:1px solid currentColor}
.meta{color:var(--dim);font-size:13px;margin:6px 0 10px}
.ev{display:grid;grid-template-columns:84px 72px 1fr;gap:8px;padding:3px 0;font-size:14px;border-top:1px solid var(--line)}
.ev .t{color:var(--dim)} .ev .k{color:var(--dim)}
.k-guard{color:var(--run)!important} .k-error{color:var(--bad)!important}
.k-ask,.k-answer{color:var(--wait)!important} .k-result{color:var(--ok)!important}
.empty{color:var(--dim);text-align:center;padding:60px 0;font-size:18px}
</style></head>
<body>
<header><h1>Dial-Up live</h1><span id="conn">connecting...</span></header>
<main id="tasks"><div class="empty">Call the number to start a task.</div></main>
<script>
const tasks = new Map();
const colors = {running:'var(--run)',waiting_on_caller:'var(--wait)',done:'var(--ok)',
  gave_up:'var(--dim)',stopped:'var(--run)',failed:'var(--bad)',queued:'var(--dim)'};
const el = (tag, cls, text) => { const e = document.createElement(tag);
  if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
const clock = s => new Date(s * 1000).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false});

function render() {
  const root = document.getElementById('tasks');
  root.replaceChildren();
  const list = [...tasks.values()].sort((a, b) => b.created_at - a.created_at);
  if (!list.length) { root.append(el('div', 'empty', 'Call the number to start a task.')); return; }
  for (const t of list) {
    const card = el('section', 'task');
    const top = el('div', 'top');
    const pill = el('span', 'pill', t.status.replaceAll('_', ' '));
    pill.style.color = colors[t.status] || 'var(--dim)';
    top.append(el('span', 'id', '#' + t.id), el('span', 'goal', t.goal), pill);
    card.append(top, el('div', 'meta', `${t.channel} · ${t.language === 'zh' ? '中文' : 'English'} · ${t.steps} steps · ${t.tokens.toLocaleString()} tokens`));
    for (const e of t.events.slice(-14)) {
      const row = el('div', 'ev');
      row.append(el('span', 't', clock(e.at)), el('span', 'k k-' + e.kind, e.kind), el('span', '', e.text));
      card.append(row);
    }
    root.append(card);
  }
}

async function load() {
  const res = await fetch('/api/tasks');
  for (const t of await res.json()) tasks.set(t.id, t);
  render();
}

function connect() {
  const src = new EventSource('/live/stream');
  src.onopen = () => document.getElementById('conn').textContent = 'live';
  src.onerror = () => document.getElementById('conn').textContent = 'reconnecting...';
  src.onmessage = async ({data}) => {
    const msg = JSON.parse(data);
    if (msg.type === 'task') {
      const old = tasks.get(msg.task.id);
      tasks.set(msg.task.id, {...msg.task, events: old ? old.events : []});
    } else if (msg.type === 'event') {
      const t = tasks.get(msg.event.task_id);
      if (!t) { const r = await fetch('/api/tasks/' + msg.event.task_id); if (r.ok) tasks.set(msg.event.task_id, await r.json()); }
      else t.events.push(msg.event);
    }
    render();
  };
}

load().then(connect);
</script>
</body></html>"""
