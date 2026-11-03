# -*- coding: utf-8 -*-
"""Vent Studio 启动入口。

打包（flet pack / PyInstaller）时指向这个文件即可。
"""
from __future__ import annotations

import flet as ft

from vent.app import main
from vent.core.client import prepare_flet_client
from vent.paths import APP_NAME, force_client_home, prepare_client_home


def run() -> None:
    # 先把本地现成的 Flet 客户端指给 flet：既不写 ~/.flet，也不会去联网下载
    client_dir = prepare_flet_client()
    # 兜底：真找不到现成客户端时，至少把缓存目录挪到可写的地方
    if not client_dir:
        prepare_client_home()
    try:
        ft.run(main, name=APP_NAME)
    except PermissionError:
        # 探测通过但真实解压仍被拒：强制换到数据目录再来一次
        if not force_client_home():
            raise
        ft.run(main, name=APP_NAME)


if __name__ == "__main__":
    run()
