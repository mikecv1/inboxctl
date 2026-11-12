"""Entry point.

  inboxctl (double-click / no args)   start the local UI and open the browser
  python -m inboxctl scan             scan folders from the terminal (must be signed in)
  python -m inboxctl logout           remove cached tokens
"""

from __future__ import annotations

import socket
import sys
import threading
import webbrowser

from .config import Config, ensure_data_dir, load_config


def _setup_logging() -> None:
    """In a windowed (no console) build stdout/stderr are None; send them to a log file."""
    if sys.stdout is None or sys.stderr is None or getattr(sys, "frozen", False):
        log = open(ensure_data_dir() / "inboxctl.log", "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = log


def _free_port(host: str, preferred: int) -> int:
    for port in (preferred, 0):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((host, port))
                return s.getsockname()[1]
            except OSError:
                continue
    return preferred


def serve(cfg: Config) -> int:
    import uvicorn

    from .server import create_app

    port = _free_port(cfg.host, cfg.port)
    url = f"http://{cfg.host}:{port}"
    print(f"inboxctl UI: {url}", flush=True)
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    uvicorn.run(create_app(cfg), host=cfg.host, port=port, log_level="warning")
    return 0


def main(argv: list[str]) -> int:
    _setup_logging()
    cmd = argv[1] if len(argv) > 1 else "serve"
    cfg = load_config()

    if cmd == "serve":
        return serve(cfg)

    if cmd == "logout":
        from .auth import Auth
        Auth(cfg).sign_out()
        print("Token cache removed.")
        return 0

    if cmd == "scan":
        from .auth import Auth, NotSignedIn
        from .graph import Graph
        from .scanner import Scanner, print_progress
        auth = Auth(cfg)
        try:
            auth.get_token()
        except NotSignedIn:
            print("Not signed in. Start the UI and connect your mailbox first.")
            return 2
        scanner = Scanner(Graph(auth.get_token), cfg)
        scanner.scan(progress=print_progress)
        print(f"Saved {len(scanner.senders)} senders to {scanner.save()}")
        return 0

    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
