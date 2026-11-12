"""Local web UI (FastAPI). Binds to 127.0.0.1 only; nothing is exposed to the network."""

from __future__ import annotations

import os
import threading
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from . import actions
from .auth import Auth, AuthManager, NotSignedIn
from .config import Config, static_dir
from .graph import Graph
from .scanner import Scanner, load_senders


class Jobs:
    """Very small in-memory job registry so long operations don't block HTTP requests."""

    def __init__(self):
        self._jobs: dict[str, dict] = {}
        self._lock = threading.Lock()

    def start(self, kind: str, target, *args) -> str:
        job_id = uuid.uuid4().hex[:8]
        job = {"id": job_id, "kind": kind, "status": "running", "log": [], "result": None, "error": None}
        with self._lock:
            self._jobs[job_id] = job

        def runner():
            try:
                job["result"] = target(job, *args)
                job["status"] = "done"
            except Exception as exc:  # noqa: BLE001
                job["error"] = str(exc)
                job["status"] = "failed"

        threading.Thread(target=runner, daemon=True).start()
        return job_id

    def get(self, job_id: str) -> dict | None:
        return self._jobs.get(job_id)

    def running(self, kind: str) -> dict | None:
        for j in self._jobs.values():
            if j["kind"] == kind and j["status"] == "running":
                return j
        return None


class ApplyRequest(BaseModel):
    emails: list[str]
    unsubscribe: bool = True
    sweep: bool = False
    block: bool = False


class KeepRequest(BaseModel):
    emails: list[str]
    keep: bool = True


class AuthStart(BaseModel):
    mode: str = "browser"  # browser | device


def create_app(cfg: Config) -> FastAPI:
    auth = Auth(cfg)
    authm = AuthManager(auth)
    graph = Graph(auth.get_token)
    jobs = Jobs()
    app = FastAPI(title="inboxctl", docs_url=None, redoc_url=None)

    @app.exception_handler(NotSignedIn)
    async def _not_signed_in(request: Request, exc: NotSignedIn):
        return JSONResponse({"error": "not_signed_in"}, status_code=401)

    @app.get("/")
    def index():
        return FileResponse(static_dir() / "index.html")

    # ------------------------------------------------------------- auth
    def _start_scan_job() -> str:
        running = jobs.running("scan")
        if running:
            return running["id"]

        def run(job):
            scanner = Scanner(graph, cfg)
            scanner.scan(progress=lambda m: job["log"].append(m))
            path = scanner.save()
            return {"path": path, "senders": len(scanner.senders)}
        return jobs.start("scan", run)

    @app.get("/api/auth")
    def auth_status():
        snap = authm.snapshot()
        # First sign-in on this machine: kick off the scan without waiting for a click.
        if snap["status"] == "signed_in" and not load_senders().get("scanned_at") and not jobs.running("scan"):
            _start_scan_job()
        return snap

    @app.post("/api/auth/start")
    def auth_start(req: AuthStart):
        return authm.start("device" if req.mode == "device" else "browser")

    @app.post("/api/auth/signout")
    def auth_signout():
        authm.sign_out()
        return authm.snapshot()

    # ----------------------------------------------------------- status
    @app.get("/api/status")
    def status():
        data = load_senders()
        me = {}
        try:
            me = graph.me()
        except NotSignedIn:
            me = {"error": "not_signed_in"}
        except Exception as exc:  # noqa: BLE001
            me = {"error": str(exc)[:200]}
        running = jobs.running("scan")
        return {
            "me": me,
            "scanned_at": data.get("scanned_at"),
            "folders": cfg.folders,
            "sender_count": len(data.get("senders", [])),
            "message_count": sum(s["count"] for s in data.get("senders", [])),
            "scan_job": running["id"] if running else None,
        }

    @app.post("/api/scan")
    def scan():
        auth.get_token()  # raise 401 early instead of inside the thread
        return {"job": _start_scan_job()}

    @app.get("/api/jobs/{job_id}")
    def job(job_id: str):
        j = jobs.get(job_id)
        if not j:
            raise HTTPException(404, "unknown job")
        return j

    @app.get("/api/senders")
    def senders():
        data = load_senders()
        keep = actions.load_keep()
        history: dict[str, dict] = {}
        for entry in actions.read_log():
            email = entry.get("email")
            if email:
                history.setdefault(email, {})[entry["action"]] = {"ok": entry.get("ok"), "at": entry.get("at"),
                                                                   "detail": entry.get("detail", "")}
        out = []
        for s in data.get("senders", []):
            s = dict(s)
            s.pop("message_ids", None)  # not needed in the UI, keeps payload small
            s["keep"] = s["email"] in keep
            s["history"] = history.get(s["email"], {})
            out.append(s)
        return {"scanned_at": data.get("scanned_at"), "senders": out}

    @app.post("/api/keep")
    def keep(req: KeepRequest):
        keep = actions.load_keep()
        for e in req.emails:
            (keep.add if req.keep else keep.discard)(e)
        actions.save_keep(keep)
        return {"ok": True, "keep_count": len(keep)}

    @app.post("/api/apply")
    def apply(req: ApplyRequest):
        auth.get_token()
        data = load_senders()
        by_email = {s["email"]: s for s in data.get("senders", [])}
        targets = [by_email[e] for e in req.emails if e in by_email]
        if not targets:
            raise HTTPException(400, "no known senders selected")

        def run(job):
            results = []
            for i, s in enumerate(targets, 1):
                job["log"].append(f"[{i}/{len(targets)}] {s['email']}")
                r = {"email": s["email"]}
                if req.unsubscribe:
                    r["unsubscribe"] = actions.unsubscribe(graph, s)
                if req.block:
                    r["block"] = actions.block_sender(graph, s["email"])
                if req.sweep:
                    r["sweep"] = actions.sweep(graph, s)
                results.append(r)
            manual = [r["unsubscribe"]["manual_url"] for r in results
                      if r.get("unsubscribe", {}).get("manual_url")]
            return {"results": results, "manual_urls": manual}
        return {"job": jobs.start("apply", run)}

    @app.post("/api/unblock")
    def unblock(req: KeepRequest):
        return {"results": [actions.unblock_sender(graph, e) for e in req.emails]}

    @app.get("/api/log")
    def log():
        return JSONResponse(actions.read_log()[-500:])

    @app.get("/api/rules")
    def rules():
        return [r for r in actions.list_rules(graph) if (r.get("displayName") or "").startswith(actions.RULE_PREFIX)]

    @app.post("/api/quit")
    def quit_app():
        # Give the response time to flush, then exit the process (the packaged app has no console).
        threading.Timer(0.5, lambda: os._exit(0)).start()
        return {"ok": True}

    return app
