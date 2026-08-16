"""Run the local GUI when the package is started as a module."""

from .gui.launcher import main

if __name__ == "__main__":
    raise SystemExit(main())
