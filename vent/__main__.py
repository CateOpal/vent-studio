# -*- coding: utf-8 -*-
"""python -m vent：从包内启动（等价于 main.py）。"""
from __future__ import annotations

import sys


def main() -> int:
    from .app import main as app_main
    from .core.client import prepare_flet_client
    from .paths import APP_NAME, force_client_home, prepare_client_home
    import flet as ft

    client_dir = prepare_flet_client()
    if not client_dir:
        prepare_client_home()
    try:
        ft.run(app_main, name=APP_NAME)
    except PermissionError:
        if not force_client_home():
            raise
        ft.run(app_main, name=APP_NAME)
    return 0


if __name__ == "__main__":
    sys.exit(main())
