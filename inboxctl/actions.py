"""Actions on a sender: unsubscribe, sweep existing mail, block future mail.

Every action is appended to data/actions.jsonl so you always have an audit trail.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from urllib.parse import parse_qs, unquote, urlparse

import requests

from .config import ensure_data_dir
from .graph import Graph, GraphError

LOG_NAME = "actions.jsonl"
KEEP_NAME = "keep.json"
RULE_PREFIX = "inboxctl block: "

UA = "inboxctl/0.1 (+local mailbox cleanup; RFC 8058 one-click)"


def _log(entry: dict) -> None:
    entry["at"] = datetime.now(timezone.utc).isoformat()
    with (ensure_data_dir() / LOG_NAME).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def read_log() -> list[dict]:
    path = ensure_data_dir() / LOG_NAME
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


# ------------------------------------------------------------------ keep list
def load_keep() -> set[str]:
    path = ensure_data_dir() / KEEP_NAME
    if not path.exists():
        return set()
    return set(json.loads(path.read_text(encoding="utf-8")))


def save_keep(keep: set[str]) -> None:
    (ensure_data_dir() / KEEP_NAME).write_text(json.dumps(sorted(keep), indent=1), encoding="utf-8")


# ---------------------------------------------------------------- unsubscribe
def unsubscribe_one_click(url: str) -> dict:
    """RFC 8058: POST with body List-Unsubscribe=One-Click. No redirects followed (spec says 2xx)."""
    try:
        resp = requests.post(
            url,
            data="List-Unsubscribe=One-Click",
            headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": UA},
            timeout=20,
            allow_redirects=True,
        )
        ok = 200 <= resp.status_code < 300
        return {"ok": ok, "status": resp.status_code, "detail": "" if ok else resp.text[:200]}
    except requests.RequestException as exc:
        return {"ok": False, "status": 0, "detail": str(exc)[:200]}


def unsubscribe_mailto(graph: Graph, mailto_uri: str) -> dict:
    """Send the unsubscribe e-mail through the user's own mailbox (Graph sendMail)."""
    parsed = urlparse(mailto_uri)
    to_addr = unquote(parsed.path).strip()
    qs = parse_qs(parsed.query)
    subject = unquote(qs.get("subject", ["unsubscribe"])[0])
    body = unquote(qs.get("body", ["unsubscribe"])[0])
    if not to_addr:
        return {"ok": False, "status": 0, "detail": "mailto without address"}
    payload = {
        "message": {
            "subject": subject,
            "body": {"contentType": "Text", "content": body},
            "toRecipients": [{"emailAddress": {"address": to_addr}}],
        },
        "saveToSentItems": False,
    }
    try:
        graph.post("/me/sendMail", payload)
        return {"ok": True, "status": 202, "detail": f"sent to {to_addr}"}
    except GraphError as exc:
        return {"ok": False, "status": 0, "detail": str(exc)[:200]}


def unsubscribe(graph: Graph, sender: dict) -> dict:
    """Pick the best available method. Returns {method, ok, status, detail, manual_url}."""
    method = sender.get("unsub_method", "none")
    result: dict = {"email": sender["email"], "method": method, "ok": False, "status": 0, "detail": "", "manual_url": ""}

    if method == "one-click":
        r = unsubscribe_one_click(sender["unsub_http"])
        result.update(r)
        # fall back to mailto if the POST failed and mailto exists
        if not r["ok"] and sender.get("unsub_mailto"):
            r2 = unsubscribe_mailto(graph, sender["unsub_mailto"])
            result.update(r2)
            result["method"] = "mailto (fallback)"
    elif method == "mailto":
        result.update(unsubscribe_mailto(graph, sender["unsub_mailto"]))
    elif method == "link":
        # A plain link usually needs a human click (confirmation page). We do not GET it blindly.
        result.update({"ok": False, "status": 0, "detail": "needs manual click", "manual_url": sender["unsub_http"]})
    else:
        result["detail"] = "no unsubscribe header; use block + sweep"

    _log({"action": "unsubscribe", **result})
    return result


# ---------------------------------------------------------------------- sweep
def sweep(graph: Graph, sender: dict, destination: str = "deleteditems") -> dict:
    """Move all scanned messages from this sender to Deleted Items (or another folder)."""
    ids = sender.get("message_ids") or []
    reqs = [
        {"id": str(i), "method": "POST", "url": f"/me/messages/{mid}/move",
         "body": {"destinationId": destination}}
        for i, mid in enumerate(ids)
    ]
    moved, failed = 0, 0
    if reqs:
        try:
            for r in graph.batch(reqs):
                if 200 <= int(r.get("status", 0)) < 300:
                    moved += 1
                else:
                    failed += 1
        except GraphError as exc:
            _log({"action": "sweep", "email": sender["email"], "ok": False, "detail": str(exc)[:200]})
            return {"ok": False, "moved": moved, "failed": len(ids) - moved, "detail": str(exc)[:200]}
    out = {"ok": failed == 0, "moved": moved, "failed": failed, "detail": ""}
    _log({"action": "sweep", "email": sender["email"], **out})
    return out


# ---------------------------------------------------------------------- rules
def list_rules(graph: Graph) -> list[dict]:
    return list(graph.paged("/me/mailFolders/inbox/messageRules"))


def block_sender(graph: Graph, email: str) -> dict:
    """Create an inbox rule: from <email> -> delete, stop processing. Idempotent by display name."""
    name = RULE_PREFIX + email
    try:
        for rule in list_rules(graph):
            if rule.get("displayName") == name:
                out = {"ok": True, "rule_id": rule["id"], "detail": "already exists"}
                _log({"action": "block", "email": email, **out})
                return out
        payload = {
            "displayName": name,
            "sequence": 1,
            "isEnabled": True,
            "conditions": {"fromAddresses": [{"emailAddress": {"address": email}}]},
            "actions": {"delete": True, "stopProcessingRules": True},
        }
        resp = graph.post("/me/mailFolders/inbox/messageRules", payload)
        out = {"ok": True, "rule_id": resp.json().get("id", ""), "detail": "created"}
    except GraphError as exc:
        out = {"ok": False, "rule_id": "", "detail": str(exc)[:200]}
    _log({"action": "block", "email": email, **out})
    return out


def unblock_sender(graph: Graph, email: str) -> dict:
    name = RULE_PREFIX + email
    removed = 0
    try:
        for rule in list_rules(graph):
            if rule.get("displayName") == name:
                graph.request("DELETE", f"/me/mailFolders/inbox/messageRules/{rule['id']}")
                removed += 1
        out = {"ok": True, "removed": removed}
    except GraphError as exc:
        out = {"ok": False, "removed": removed, "detail": str(exc)[:200]}
    _log({"action": "unblock", "email": email, **out})
    return out
