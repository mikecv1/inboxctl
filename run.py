"""PyInstaller entry point (python -m is not supported by PyInstaller)."""

import sys

from inboxctl.__main__ import main

if __name__ == "__main__":
    sys.exit(main(sys.argv))
