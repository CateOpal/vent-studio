# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions
adhere to [Semantic Versioning](https://semver.org/).

| Version | Date | Highlights |
| :--- | :--- | :--- |
| [1.0.0](#100--2026-11-03) | 2026-11-03 | First public release as **Vent Studio** |
| Unreleased | — | Chinese-only UI, repo cleanup, status-bar save dialog fix |

## Unreleased

### Changed

- The interface is Simplified Chinese only. The runtime language switch and the
  translation tables were removed, along with the `lang` config key — the app no
  longer ships a translation layer.
- Repository trimmed to a standard Flet project layout: the `vent` package, `main.py`,
  `requirements.txt`, `assets/` and Markdown docs. Build scripts, the installer sources and
  the icon generator were removed; the icon is kept as an asset and packaging now uses
  plain `flet pack`.

### Fixed

- **Status-bar save location did nothing** and left an invisible full-screen layer on
  top of the window, which made the whole UI look frozen. The dialog now returns its
  card again, and the "choose folder" action exists and closes the dialog.
- The brand mark in the title bar is now a **V** (it was still an "O").
- The application / task bar icon is the V mark in every size; small sizes use a thicker
  stroke without the glow so they no longer read as a circle. The window icon is also
  set at runtime, so it does not depend on the Explorer icon cache.

## [1.0.0] — 2026-11-03

First public release as **Vent Studio** (renamed from ORE Studio).

### Added

- Library scanner for the Steam workshop folder (`431960`) and local `projects` on any
  drive, plus a manual folder picker.
- Thumbnail preview with an on-disk cache, video playback and on-the-fly H.264
  transcoding for codecs the player cannot open.
- `scene.pkg` unpacker ("media only" / "media + audio").
- Scene / web wallpaper recording through Wallpaper Engine (capturekit, gdigrab
  fallback).
- Set-as-background with a liquid-glass blur, and a portable `data\` directory next to
  the executable.

### Changed

- Renamed the project, package (`vent`), executable and data paths.
- Restructured the code base into `core/` (scan, PKG parser, ffmpeg, downloader, Windows
  helpers) and `ui/` mixins composed by a thin `App`.
- FFmpeg downloader tries a mirror first, measures throughput and falls back to the
  official build automatically; the fastest source is remembered.
- New application icon drawn in code, kept as `assets/icon.ico` and `assets/icon.png`.
