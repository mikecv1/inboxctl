"""Thin Microsoft Graph client: paging, retries, JSON batch."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from typing import Any

import requests

from .config import GRAPH_BASE


class GraphError(RuntimeError):
    pass


class Graph:
    def __init__(self, token_provider: Callable[[], str]):
        self._token_provider = token_provider
        self.session = requests.Session()

    # ------------------------------------------------------------------ core
    def _headers(self, extra: dict | None = None) -> dict:
        h = {
            "Authorization": f"Bearer {self._token_provider()}",
            "Accept": "application/json",
        }
        if extra:
            h.update(extra)
        return h

    def request(self, method: str, url: str, *, json: Any = None, headers: dict | None = None,
                params: dict | None = None, retries: int = 5) -> requests.Response:
        if url.startswith("/"):
            url = GRAPH_BASE + url
        attempt = 0
        while True:
            resp = self.session.request(
                method, url, json=json, headers=self._headers(headers), params=params, timeout=60
            )
            if resp.status_code in (429, 503, 504) and attempt < retries:
                wait = float(resp.headers.get("Retry-After", 2 ** attempt))
                time.sleep(min(wait, 60))
                attempt += 1
                continue
            if resp.status_code >= 400:
                raise GraphError(f"{method} {url} -> {resp.status_code}: {resp.text[:500]}")
            return resp

    def get(self, url: str, **kw) -> dict:
        return self.request("GET", url, **kw).json()

    def post(self, url: str, json: Any, **kw) -> requests.Response:
        return self.request("POST", url, json=json, **kw)

    def paged(self, url: str, params: dict | None = None, headers: dict | None = None,
              limit: int = 0) -> Iterator[dict]:
        """Iterate over a collection following @odata.nextLink."""
        count = 0
        data = self.get(url, params=params, headers=headers)
        while True:
            for item in data.get("value", []):
                yield item
                count += 1
                if limit and count >= limit:
                    return
            nxt = data.get("@odata.nextLink")
            if not nxt:
                return
            data = self.get(nxt, headers=headers)

    # ----------------------------------------------------------------- batch
    def batch(self, requests_: list[dict]) -> list[dict]:
        """Execute up to 20 requests per $batch call. Each item: {id, method, url, body?}."""
        results: list[dict] = []
        for i in range(0, len(requests_), 20):
            chunk = requests_[i:i + 20]
            for r in chunk:
                if "body" in r:
                    r.setdefault("headers", {})["Content-Type"] = "application/json"
            resp = self.post("/$batch", {"requests": chunk})
            results.extend(resp.json().get("responses", []))
        return results

    # -------------------------------------------------------------- helpers
    def me(self) -> dict:
        return self.get("/me", params={"$select": "displayName,mail,userPrincipalName"})

    def mail_folders(self) -> list[dict]:
        return list(self.paged("/me/mailFolders", params={"$top": 100, "$select": "id,displayName,totalItemCount"}))

    def resolve_folder(self, name: str) -> str:
        """Accept well-known names (inbox, archive, ...) or display names; return a folder id/name usable in URLs."""
        well_known = {"inbox", "archive", "drafts", "sentitems", "deleteditems", "junkemail", "clutter"}
        if name.lower() in well_known:
            return name.lower()
        for f in self.mail_folders():
            if f["displayName"].lower() == name.lower():
                return f["id"]
        raise GraphError(f"Folder not found: {name}")
