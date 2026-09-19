from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import StreamingResponse

app = FastAPI()

sessions: list[dict[str, Any]] = [
    {
        "id": "session-demo",
        "title": "Hermes Companion Demo",
        "preview": "A durable session shared with Desktop",
        "last_active": int(time.time()),
    }
]
messages: dict[str, list[dict[str, Any]]] = {
    "session-demo": [
        {"role": "user", "content": "Explain the companion architecture.", "created_at": int(time.time()) - 30},
        {"role": "assistant", "content": "The bridge keeps Hermes keys server-side while the PWA uses short-lived Companion tokens.", "created_at": int(time.time()) - 25},
    ]
}
runs: dict[str, dict[str, Any]] = {}
jobs: list[dict[str, Any]] = [
    {
        "id": "job-demo",
        "name": "Daily Hermes release study",
        "prompt": "Study official Hermes releases and record material changes.",
        "schedule": "0 9 * * *",
        "enabled": True,
        "next_run_at": int(time.time()) + 3600,
    }
]


def _auth(authorization: str | None) -> None:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "missing bearer")


@app.get("/health")
@app.get("/health/detailed")
@app.get("/p/{profile}/health")
@app.get("/p/{profile}/health/detailed")
def health(profile: str | None = None, authorization: str | None = Header(default=None)):
    _auth(authorization)
    return {"status": "ok", "service": "mock-hermes", "profile": profile or "default"}


@app.get("/api/sessions")
@app.get("/p/{profile}/api/sessions")
def list_sessions(authorization: str | None = Header(default=None)):
    _auth(authorization)
    return {"sessions": sessions}


@app.post("/api/sessions")
@app.post("/p/{profile}/api/sessions")
async def create_session(request: Request, authorization: str | None = Header(default=None)):
    _auth(authorization)
    body = await request.json()
    item = {
        "id": f"session-{uuid.uuid4().hex[:8]}",
        "title": body.get("title") or "Untitled session",
        "preview": "New durable session",
        "last_active": int(time.time()),
    }
    sessions.insert(0, item)
    messages[item["id"]] = []
    return item


@app.get("/api/sessions/{session_id}/messages")
@app.get("/p/{profile}/api/sessions/{session_id}/messages")
def session_messages(session_id: str, authorization: str | None = Header(default=None)):
    _auth(authorization)
    return {"messages": messages.get(session_id, [])}


@app.patch("/api/sessions/{session_id}")
@app.patch("/p/{profile}/api/sessions/{session_id}")
async def update_session(session_id: str, request: Request, authorization: str | None = Header(default=None)):
    _auth(authorization)
    body = await request.json()
    for item in sessions:
        if item["id"] == session_id:
            item.update({key: body[key] for key in ("title", "end_reason") if key in body})
            return item
    raise HTTPException(404, "session not found")


@app.delete("/api/sessions/{session_id}")
@app.delete("/p/{profile}/api/sessions/{session_id}")
def delete_session(session_id: str, authorization: str | None = Header(default=None)):
    _auth(authorization)
    sessions[:] = [item for item in sessions if item["id"] != session_id]
    messages.pop(session_id, None)
    return {"ok": True}


@app.post("/api/sessions/{session_id}/fork")
@app.post("/p/{profile}/api/sessions/{session_id}/fork")
def fork_session(session_id: str, authorization: str | None = Header(default=None)):
    _auth(authorization)
    source = next((item for item in sessions if item["id"] == session_id), None)
    if not source:
        raise HTTPException(404, "session not found")
    item = {**source, "id": f"session-{uuid.uuid4().hex[:8]}", "title": f"{source['title']} · branch"}
    sessions.insert(0, item)
    messages[item["id"]] = list(messages.get(session_id, []))
    return item


@app.get("/api/model/options")
@app.get("/p/{profile}/api/model/options")
def model_options(authorization: str | None = Header(default=None)):
    _auth(authorization)
    return {
        "providers": [
            {"provider": "openrouter", "models": [
                {"id": "nousresearch/hermes-4-405b", "name": "Hermes 4 405B"},
                {"id": "deepseek/deepseek-chat", "name": "DeepSeek Chat"},
            ]}
        ]
    }


@app.get("/v1/capabilities")
@app.get("/p/{profile}/v1/capabilities")
def capabilities(authorization: str | None = Header(default=None)):
    _auth(authorization)
    return {"runs": True, "run_approval": True, "run_steer": True}


@app.post("/v1/runs")
@app.post("/p/{profile}/v1/runs")
async def create_run(request: Request, authorization: str | None = Header(default=None)):
    _auth(authorization)
    body = await request.json()
    run_id = f"run-{uuid.uuid4().hex[:8]}"
    session_id = body.get("session_id") or "session-demo"
    prompt = body.get("input") or ""
    messages.setdefault(session_id, []).append({"role": "user", "content": prompt, "created_at": int(time.time())})
    runs[run_id] = {"run_id": run_id, "status": "running", "session_id": session_id, "prompt": prompt}
    return runs[run_id]


@app.get("/v1/runs/{run_id}")
@app.get("/p/{profile}/v1/runs/{run_id}")
def get_run(run_id: str, authorization: str | None = Header(default=None)):
    _auth(authorization)
    if run_id not in runs:
        raise HTTPException(404, "run not found")
    return runs[run_id]


@app.get("/v1/runs/{run_id}/events")
@app.get("/p/{profile}/v1/runs/{run_id}/events")
def run_events(run_id: str, authorization: str | None = Header(default=None)):
    _auth(authorization)
    if run_id not in runs:
        raise HTTPException(404, "run not found")

    async def stream():
        yield f'data: {{"event":"tool.started","run_id":"{run_id}","tool":"memory","preview":"Reading project context"}}\n\n'
        await asyncio.sleep(0.08)
        yield f'data: {{"event":"tool.completed","run_id":"{run_id}","tool":"memory","duration":0.08}}\n\n'
        for delta in ("Hermes ", "Companion ", "is connected successfully."):
            await asyncio.sleep(0.08)
            yield f'data: {{"event":"assistant.delta","run_id":"{run_id}","delta":"{delta}"}}\n\n'
        await asyncio.sleep(0.05)
        runs[run_id]["status"] = "completed"
        output = "Hermes Companion is connected successfully."
        messages[runs[run_id]["session_id"]].append({"role": "assistant", "content": output, "created_at": int(time.time())})
        yield f'data: {{"event":"run.completed","run_id":"{run_id}","completed":true,"output":"{output}"}}\n\n'

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.post("/v1/runs/{run_id}/stop")
@app.post("/p/{profile}/v1/runs/{run_id}/stop")
def stop_run(run_id: str, authorization: str | None = Header(default=None)):
    _auth(authorization)
    if run_id in runs:
        runs[run_id]["status"] = "cancelled"
    return {"ok": True}


@app.post("/v1/runs/{run_id}/steer")
@app.post("/p/{profile}/v1/runs/{run_id}/steer")
async def steer_run(run_id: str, request: Request, authorization: str | None = Header(default=None)):
    _auth(authorization)
    body = await request.json()
    return {"ok": True, "queued": body.get("prompt")}


@app.post("/v1/runs/{run_id}/approval")
@app.post("/p/{profile}/v1/runs/{run_id}/approval")
async def approve_run(run_id: str, request: Request, authorization: str | None = Header(default=None)):
    _auth(authorization)
    body = await request.json()
    return {"ok": True, "choice": body.get("choice")}


@app.get("/api/jobs")
@app.get("/p/{profile}/api/jobs")
def list_jobs(authorization: str | None = Header(default=None)):
    _auth(authorization)
    return {"jobs": jobs}


@app.post("/api/jobs")
@app.post("/p/{profile}/api/jobs")
async def create_job(request: Request, authorization: str | None = Header(default=None)):
    _auth(authorization)
    body = await request.json()
    item = {"id": f"job-{uuid.uuid4().hex[:8]}", **body}
    jobs.insert(0, item)
    return item


@app.get("/api/jobs/{job_id}")
@app.get("/p/{profile}/api/jobs/{job_id}")
def get_job(job_id: str, authorization: str | None = Header(default=None)):
    _auth(authorization)
    return next((item for item in jobs if item["id"] == job_id), {})


@app.patch("/api/jobs/{job_id}")
@app.patch("/p/{profile}/api/jobs/{job_id}")
async def update_job(job_id: str, request: Request, authorization: str | None = Header(default=None)):
    _auth(authorization)
    body = await request.json()
    item = next((item for item in jobs if item["id"] == job_id), None)
    if not item:
        raise HTTPException(404, "job not found")
    item.update(body)
    return item


@app.delete("/api/jobs/{job_id}")
@app.delete("/p/{profile}/api/jobs/{job_id}")
def delete_job(job_id: str, authorization: str | None = Header(default=None)):
    _auth(authorization)
    jobs[:] = [item for item in jobs if item["id"] != job_id]
    return {"ok": True}


@app.post("/api/jobs/{job_id}/{action}")
@app.post("/p/{profile}/api/jobs/{job_id}/{action}")
async def job_action(job_id: str, action: str, request: Request, authorization: str | None = Header(default=None)):
    _auth(authorization)
    item = next((item for item in jobs if item["id"] == job_id), None)
    if not item:
        raise HTTPException(404, "job not found")
    if action == "pause": item["enabled"] = False
    if action == "resume": item["enabled"] = True
    return {"ok": True, "action": action}
