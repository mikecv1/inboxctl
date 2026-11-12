"""Scan mail folders and aggregate messages per sender, detecting unsubscribe capability.

Unsubscribe detection follows RFC 2369 (List-Unsubscribe) and RFC 8058 (List-Unsubscribe-Post).
"""

from __future__ import annotations

import json
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from .config import Config, ensure_data_dir
from .graph import Graph

SENDERS_PATH_NAME = "senders.json"

_ANGLE_RE = re.compile(r"<([^>]+)>")


@dataclass
class Sender:
    email: str
    name: str = ""
    domain: str = ""
    count: int = 0
    unread: int = 0
    first_seen: str = ""
    last_seen: str = ""
    subjects: list[str] = field(default_factory=list)   # a few samples
    message_ids: list[str] = field(default_factory=list)
    # unsubscribe capability
    unsub_method: str = "none"          # one-click | mailto | link | none
    unsub_http: str = ""                # https URL from List-Unsubscribe
    unsub_mailto: str = ""              # mailto: URI from List-Unsubscribe
    one_click: bool = False             # List-Unsubscribe-Post present
    has_unsubscribe_word: bool = False  # body/subject mentions "unsubscribe" (heuristic, headers missing)
    folders: list[str] = field(default_factory=list)


def parse_list_unsubscribe(value: str) -> tuple[str, str]:
    """Return (https_url, mailto_uri) from a List-Unsubscribe header value."""
    http, mailto = "", ""
    for uri in _ANGLE_RE.findall(value or ""):
        uri = uri.strip()
        low = uri.lower()
        if low.startswith("mailto:") and not mailto:
            mailto = uri
        elif low.startswith(("https://", "http://")) and not http:
            http = uri
    return http, mailto


def classify(http: str, mailto: str, one_click: bool) -> str:
    if one_click and http:
        return "one-click"
    if mailto:
        return "mailto"
    if http:
        return "link"
    return "none"


def _headers_map(msg: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    for h in msg.get("internetMessageHeaders") or []:
        name = (h.get("name") or "").lower()
        # keep the first occurrence
        out.setdefault(name, h.get("value") or "")
    return out


class Scanner:
    SELECT = ",".join([
        "id", "subject", "from", "sender", "receivedDateTime", "isRead",
        "internetMessageHeaders", "bodyPreview",
    ])

    def __init__(self, graph: Graph, cfg: Config):
        self.graph = graph
        self.cfg = cfg
        self.senders: dict[str, Sender] = {}

    def scan(self, progress=None) -> dict[str, Sender]:
        started = time.time()
        for folder_name in self.cfg.folders:
            folder = self.graph.resolve_folder(folder_name)
            url = f"/me/mailFolders/{folder}/messages"
            params = {"$select": self.SELECT, "$top": 50, "$orderby": "receivedDateTime desc"}
            n = 0
            for msg in self.graph.paged(url, params=params, limit=self.cfg.max_messages_per_folder):
                self._ingest(msg, folder_name)
                n += 1
                if progress and n % 200 == 0:
                    progress(f"{folder_name}: {n} messages, {len(self.senders)} senders")
            if progress:
                progress(f"{folder_name}: done, {n} messages")
        for s in self.senders.values():
            s.unsub_method = classify(s.unsub_http, s.unsub_mailto, s.one_click)
        if progress:
            progress(f"scan finished in {time.time() - started:.0f}s: {len(self.senders)} senders")
        return self.senders

    def _ingest(self, msg: dict, folder_name: str) -> None:
        frm = (msg.get("from") or msg.get("sender") or {}).get("emailAddress") or {}
        email = (frm.get("address") or "").strip().lower()
        if not email:
            return
        s = self.senders.get(email)
        if s is None:
            s = Sender(email=email, name=frm.get("name") or "", domain=email.split("@")[-1])
            self.senders[email] = s
        s.count += 1
        if not msg.get("isRead", True):
            s.unread += 1
        ts = msg.get("receivedDateTime") or ""
        if ts:
            s.last_seen = max(s.last_seen, ts) if s.last_seen else ts
            s.first_seen = min(s.first_seen, ts) if s.first_seen else ts
        if len(s.subjects) < 3 and msg.get("subject"):
            s.subjects.append(msg["subject"][:120])
        s.message_ids.append(msg["id"])
        if folder_name not in s.folders:
            s.folders.append(folder_name)

        hdrs = _headers_map(msg)
        lu = hdrs.get("list-unsubscribe")
        if lu:
            http, mailto = parse_list_unsubscribe(lu)
            # prefer the most recent message's URLs (we iterate newest first, so only fill if empty)
            if http and not s.unsub_http:
                s.unsub_http = http
            if mailto and not s.unsub_mailto:
                s.unsub_mailto = mailto
            post = hdrs.get("list-unsubscribe-post", "")
            if "one-click" in post.lower() and http:
                s.one_click = True
        preview = (msg.get("bodyPreview") or "").lower()
        if "unsubscribe" in preview or "abmelden" in preview or "descadastr" in preview:
            s.has_unsubscribe_word = True

    # -------------------------------------------------------------- persist
    def save(self) -> str:
        path = ensure_data_dir() / SENDERS_PATH_NAME
        payload = {
            "scanned_at": datetime.now(timezone.utc).isoformat(),
            "folders": self.cfg.folders,
            "senders": [asdict(s) for s in self.senders.values()],
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        return str(path)


def load_senders() -> dict:
    path = ensure_data_dir() / SENDERS_PATH_NAME
    if not path.exists():
        return {"scanned_at": None, "folders": [], "senders": []}
    return json.loads(path.read_text(encoding="utf-8"))


def print_progress(msg: str) -> None:
    print(f"[scan] {msg}", file=sys.stderr, flush=True)
