# -*- coding: utf-8 -*-
"""内部导入汇总层。

UI 的每个模块都 from ..compat import *，省掉一长串重复 import；
这里只依赖 core / theme / config，不回头 import UI 模块，避免循环。
"""
from __future__ import annotations

import asyncio
import base64
import functools
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path

import flet as ft
from flet_video import PlaylistMode, Video, VideoMedia

from . import paths
from . import theme as th
from .config import *
from .constants import *
from .core import ffsetup
from .core import pkg as wparser
from .core import scan as ws
from .core import winutil
from .core.ffmpeg import *
from .core.ffsetup import *
from .core.pkg import *
from .core.scan import *
from .core.winutil import *
from .paths import *
from .theme import *
from .ui.window import fit_window_size

# 下划线开头的内部名字 star import 带不出来，单独引一下
from .core.ffmpeg import _FFMPEG_REJECTS
from .theme import _darken

# 让 from ..compat import * 也能拿到下划线开头的内部名字（_darken / _FFMPEG_REJECTS）
__all__ = [n for n in dir() if not n.startswith("__")]
