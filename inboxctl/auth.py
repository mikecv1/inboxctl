"""Authentication against the Microsoft identity platform using MSAL (public client, no secret).

Two entry points:
  - Auth.get_token(): silent token from the local cache (raises NotSignedIn if none).
  - AuthManager: drives an interactive sign-in from the web UI, either through the system
    browser (redirect to http://localhost) or through a device code the user types in.

The token cache is persisted in the data dir so the user signs in once.
"""

from __future__ import annotations

import atexit
import threading
import time

import msal

from .config import SCOPES, Config, ensure_data_dir


class NotSignedIn(RuntimeError):
    pass


class Auth:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._cache_path = ensure_data_dir() / "token_cache.json"
        self._cache = msal.SerializableTokenCache()
        if self._cache_path.exists():
            try:
                self._cache.deserialize(self._cache_path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001  corrupt cache: start fresh
                pass
        atexit.register(self.persist)
        self.app = msal.PublicClientApplication(
            cfg.client_id, authority=cfg.authority, token_cache=self._cache
        )

    def persist(self) -> None:
        if self._cache.has_state_changed:
            self._cache_path.write_text(self._cache.serialize(), encoding="utf-8")

    def account(self) -> dict | None:
        accounts = self.app.get_accounts()
        return accounts[0] if accounts else None

    def get_token(self) -> str:
        acc = self.account()
        result = self.app.acquire_token_silent(SCOPES, account=acc) if acc else None
        if not result or "access_token" not in result:
            raise NotSignedIn("not signed in")
        self.persist()
        return result["access_token"]

    def is_signed_in(self) -> bool:
        try:
            self.get_token()
            return True
        except NotSignedIn:
            return False

    def sign_out(self) -> None:
        for acc in self.app.get_accounts():
            self.app.remove_account(acc)
        self.persist()
        if self._cache_path.exists():
            self._cache_path.unlink()

    # ---------------------------------------------------------- interactive
    def interactive_browser(self, timeout: int = 300) -> dict:
        """Open the system browser; MSAL listens on http://localhost:<random port> for the redirect."""
        return self.app.acquire_token_interactive(SCOPES, prompt="select_account", timeout=timeout)

    def device_flow_start(self) -> dict:
        flow = self.app.initiate_device_flow(scopes=SCOPES)
        if "user_code" not in flow:
            raise RuntimeError(f"Could not start device flow: {flow.get('error_description', flow)}")
        return flow

    def device_flow_finish(self, flow: dict) -> dict:
        return self.app.acquire_token_by_device_flow(flow)


class AuthManager:
    """State machine used by the web UI. Thread-safe enough for a single local user."""

    def __init__(self, auth: Auth):
        self.auth = auth
        self._lock = threading.Lock()
        self.state: dict = {"status": "signed_out", "mode": None, "user_code": None,
                            "verification_uri": None, "error": None, "started_at": None}
        self._refresh_status()

    def _refresh_status(self) -> None:
        if self.auth.is_signed_in():
            self.state.update(status="signed_in", error=None, user_code=None, verification_uri=None)
        elif self.state["status"] == "signed_in":
            self.state["status"] = "signed_out"

    def snapshot(self) -> dict:
        self._refresh_status()
        acc = self.auth.account()
        return {**self.state, "account": (acc or {}).get("username")}

    def start(self, mode: str = "browser") -> dict:
        with self._lock:
            if self.state["status"] == "pending":
                return self.snapshot()
            self.state.update(status="pending", mode=mode, error=None, user_code=None,
                              verification_uri=None, started_at=time.time())
            threading.Thread(target=self._run, args=(mode,), daemon=True).start()
        return self.snapshot()

    def _run(self, mode: str) -> None:
        try:
            if mode == "browser":
                result = self.auth.interactive_browser()
            else:
                flow = self.auth.device_flow_start()
                self.state.update(user_code=flow["user_code"], verification_uri=flow["verification_uri"])
                result = self.auth.device_flow_finish(flow)
            if "access_token" in result:
                self.auth.persist()
                self.state.update(status="signed_in", error=None, user_code=None, verification_uri=None)
            else:
                self.state.update(status="error", error=result.get("error_description") or result.get("error") or "sign-in failed")
        except Exception as exc:  # noqa: BLE001
            self.state.update(status="error", error=str(exc)[:300])

    def sign_out(self) -> None:
        self.auth.sign_out()
        self.state.update(status="signed_out", mode=None, user_code=None, verification_uri=None, error=None)
