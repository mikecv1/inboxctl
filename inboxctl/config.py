"""Configuration. Works with zero setup: built-in defaults, optional config.json overrides.

State lives in a per-user data folder:
  Windows: %LOCALAPPDATA%\\inboxctl
  macOS:   ~/Library/Application Support/inboxctl
  Linux:   ~/.local/share/inboxctl
Override with INBOXCTL_DATA.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

APP_NAME = "inboxctl"

# Public client id of "Microsoft Graph Command Line Tools" (the app behind Connect-MgGraph).
# It supports personal Microsoft accounts and needs no app registration. Replace with your own
# registration when you have an Entra tenant (see README).
DEFAULT_CLIENT_ID = "14d82eec-204b-4c2f-b7e8-296a70dab67e"

GRAPH_BASE = "https://graph.microsoft.com/v1.0"

# Delegated scopes. Keep this list minimal; every scope shows on the consent screen.
SCOPES = [
    "User.Read",
    "Mail.ReadWrite",            # list messages, read headers, move to Deleted Items
    "Mail.Send",                 # send mailto: unsubscribe requests
    "MailboxSettings.ReadWrite",  # create inbox rules that block future mail
]


def _frozen() -> bool:
    return getattr(sys, "frozen", False)


def bundle_root() -> Path:
    """Folder that holds bundled resources (static/). Differs under PyInstaller."""
    if _frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / "inboxctl"
    return Path(__file__).resolve().parent


def static_dir() -> Path:
    return bundle_root() / "static"


def default_data_dir() -> Path:
    env = os.environ.get("INBOXCTL_DATA")
    if env:
        return Path(env)
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / APP_NAME


DATA_DIR = default_data_dir()


def config_candidates() -> list[Path]:
    """config.json next to the executable/project, then in the data dir."""
    exe_dir = Path(sys.executable).parent if _frozen() else Path(__file__).resolve().parent.parent
    return [exe_dir / "config.json", DATA_DIR / "config.json"]


@dataclass
class Config:
    client_id: str = DEFAULT_CLIENT_ID
    # "consumers" = personal Microsoft accounts only (outlook.com, hotmail, live).
    # "common" also allows work/school accounts.
    authority_tenant: str = "consumers"
    folders: list[str] = field(default_factory=lambda: ["inbox"])
    max_messages_per_folder: int = 0
    host: str = "127.0.0.1"
    port: int = 8765

    @property
    def authority(self) -> str:
        return f"https://login.microsoftonline.com/{self.authority_tenant}"


def load_config() -> Config:
    for path in config_candidates():
        if path.exists():
            raw = json.loads(path.read_text(encoding="utf-8"))
            raw = {k: v for k, v in raw.items() if k in Config.__dataclass_fields__}
            if str(raw.get("client_id", "")).startswith("PASTE"):
                raw.pop("client_id")
            return Config(**raw)
    return Config()


def ensure_data_dir() -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR
