# <img src="assets/icon.png" width="36" align="top" alt=""> Vent Studio

**Browse, preview, unpack and record your Wallpaper Engine library.**

[![Platform](https://img.shields.io/badge/platform-Windows%2010%20%7C%2011-0a7ea4?style=flat-square)](#-requirements)
[![Python](https://img.shields.io/badge/python-3.10%2B-3776ab?style=flat-square)](#-run-from-source)
[![Version](https://img.shields.io/badge/version-1.0.0-8b5cf6?style=flat-square)](CHANGELOG.md)
[![License](https://img.shields.io/badge/license-MIT-22c55e?style=flat-square)](LICENSE.md)
[![UI](https://img.shields.io/badge/UI-%E7%AE%80%E4%BD%93%E4%B8%AD%E6%96%87-ef4444?style=flat-square)](#-faq)

[简体中文](README.zh-CN.md) · **English**

---

Vent Studio is a small desktop app for people who collect
[Wallpaper Engine](https://store.steampowered.com/app/431960/Wallpaper_Engine/) wallpapers.
It reads the library straight from disk — no Steam login, no network — shows real
thumbnails, plays video wallpapers, unpacks `scene.pkg` archives, and records scene / web
wallpapers into ordinary video files.

The interface is a hand-drawn liquid-glass UI built with [Flet](https://flet.dev) 1.0.4
and is Simplified Chinese. Everything the app writes lives in a portable `data\` folder
next to the executable.

## ✨ Features

| | |
| :--- | :--- |
| **Library** | Scans the Steam workshop folder (`431960`) and local `projects` on any drive, with a one-click manual folder picker when auto-detection fails. |
| **Preview** | Cached thumbnails, video playback, and on-the-fly H.264 transcoding for codecs the player cannot open. |
| **Unpack** | Extracts images, videos and audio from `scene.pkg` — "media only" or "media + audio". |
| **Record** | Captures scene / web wallpapers through Wallpaper Engine itself (capturekit, gdigrab fallback). 15 s by default, up to 2 minutes. |
| **Set as background** | Uses any wallpaper as the app's own background, including the liquid-glass blur behind the UI. |
| **Offline-first** | No network calls except the optional one-time FFmpeg download, which tries a fast mirror first and falls back to the official build. |

## 📋 Requirements

- Windows 10 (1809+) or Windows 11, 64-bit
- [Wallpaper Engine](https://store.steampowered.com/app/431960/Wallpaper_Engine/) — for the
  wallpapers themselves; the app only reads files
- **FFmpeg (optional)** — needed to mux video + audio and to record; if missing, the app
  offers a one-time download (~30 MB) or reuses a system install

## 🚀 Run from source

```bat
git clone https://github.com/neverlove1129/vent-studio.git
cd vent-studio
python -m pip install -r requirements.txt
python main.py
```

## 📦 Package

Plain Flet packaging — `flet pack` wraps PyInstaller and writes the result to `dist\`:

```bat
flet pack main.py --name "Vent Studio" --icon assets\icon.ico --onedir --add-data "assets;assets"
```

The `data\` folder (config, log, thumbnail cache, extracted Flet client) is created next
to the executable at runtime, so the packaged folder can be zipped and carried around as
a portable build.

## 🗂 Project layout

```
main.py               entry point: prepares the Flet client, then ft.run(vent.app.main)
requirements.txt      runtime dependencies
assets/               icon.ico, icon.png — window icon and packaged exe icon
vent/                 application package
  app.py              App class: composes the UI mixins
  compat.py           shared import surface for the UI layer
  config.py           config load/save (data\config.json)
  constants.py        window sizes, grid metrics, type icons
  paths.py            runtime dirs (portable data\, %APPDATA% fallback)
  theme.py            liquid-glass design tokens + widget factories
  core/               scan.py (library), pkg.py (PKG parser), ffmpeg.py,
                      ffsetup.py (download), winutil.py, client.py
  ui/                 shell / library / detail / settings / export / record mixins
```

## ❓ FAQ

<details>
<summary><b>No wallpapers found</b></summary>

The library is read from `steamapps/workshop/content/431960`. If Steam sits on another
drive, Vent Studio probes every Steam library folder automatically; if that still fails,
open **设置 → 组件 → 引擎目录** and point it at the folder once.
</details>

<details>
<summary><b>Recording produces a black video</b></summary>

Recording needs a normal-integrity process. Starting the exe from a script or a sandboxed
terminal (Low IL) blocks screen capture — double-click `Vent Studio.exe` instead.
</details>

<details>
<summary><b>Where do settings live?</b></summary>

`data\config.json` next to the executable, with the log in `data\vent.log`. Delete the
`data\` folder to reset everything.
</details>

<details>
<summary><b>Why is the interface Chinese only?</b></summary>

The UI is written and designed in Simplified Chinese; there is no translation layer to
switch. See [CHANGELOG.md](CHANGELOG.md).
</details>

## 📄 License

[MIT](LICENSE.md) — do whatever you like, no warranty.
