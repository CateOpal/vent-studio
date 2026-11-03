# -*- coding: utf-8 -*-
"""Vent Studio —— Wallpaper Engine 壁纸库浏览 / 解包 / 录制工具。

这个模块只负责把各层拼起来：界面逻辑在 ui/，核心逻辑在 core/。
"""
from __future__ import annotations

from .compat import *  # noqa: F401,F403
from .ui.detail import DetailMixin
from .ui.export import ExportMixin
from .ui.library import LibraryMixin
from .ui.record import RecordMixin
from .ui.settings import SettingsMixin
from .ui.shell import ShellMixin


class App(ShellMixin, LibraryMixin, DetailMixin, SettingsMixin, ExportMixin, RecordMixin):
    def __init__(self, page: ft.Page):
        self.page = page
        self.cfg = load_cfg()
        self.wps: list[ws.Wallpaper] = []
        self.thumbs: dict[str, Path | None] = {}
        self.roots: dict = {}
        self.q = ""
        self.type_filter = "all"
        self.sort = "title"
        self.sel: ws.Wallpaper | None = None
        self.detail_video: Video | None = None
        self._pkg_cache: dict = {}
        self._thumb_running = False
        # 运行日志：状态 / 警告 / 错误都进这里，底栏状态胶囊点开就能看
        self.logs: list[dict] = []
        self.error_count = 0
        self._last_status: str | None = None
        self._last_status_shape: str | None = None

        self.picker = ft.FilePicker()
        page.services.append(self.picker)

        self.bg_layer = ft.Stack(expand=True, fit=ft.StackFit.EXPAND)
        self.body = ft.Container(expand=True)
        self.card_holders: dict = {}
        self.title_holder = ft.Container()
        self.overlay = ft.Stack(expand=True, fit=ft.StackFit.EXPAND)
        self.dialog_host = ft.Stack(expand=True, fit=ft.StackFit.EXPAND)
        self.toast_host = ft.Stack(expand=True, fit=ft.StackFit.EXPAND)
        self.status_text = txt("就绪", S_SMALL, T.FAINT)
        # 宽度由胶囊固定（250），超出的部分由 Text 自己变成省略号
        self.engine_text = txt("引擎目录  扫描中…", S_SMALL, a(0.55), max_lines=1,
                               ellipsis=True)
        self.engine_dir = ""
        self.grid_host = ft.Column(spacing=0, scroll=ft.ScrollMode.AUTO, expand=True)
        self.count_text = txt("", S_SMALL, T.FAINT)
        # 底栏「保存位置」胶囊 / 设置里的路径文字，供 sync 更新
        self.save_text: ft.Text | None = None
        self.export_text: ft.Text | None = None
        # 本次解包要用的目录（解包弹窗里可临时改）
        self._unpack_dest: str = ""

        self._install_error_hooks()
        self.build()
        page.run_task(self.boot)


def main(page: ft.Page) -> None:
    """Flet 入口：由 main.py 负责 ft.run()，这里只装配界面。"""
    App(page)
