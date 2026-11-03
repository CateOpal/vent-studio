# <img src="assets/icon.png" width="36" align="top" alt=""> Vent Studio

**浏览、预览、解包、录制你的 Wallpaper Engine 壁纸库。**

[![平台](https://img.shields.io/badge/platform-Windows%2010%20%7C%2011-0a7ea4?style=flat-square)](#-环境要求)
[![Python](https://img.shields.io/badge/python-3.10%2B-3776ab?style=flat-square)](#-源码运行)
[![版本](https://img.shields.io/badge/version-1.0.0-8b5cf6?style=flat-square)](CHANGELOG.md)
[![许可](https://img.shields.io/badge/license-MIT-22c55e?style=flat-square)](LICENSE.md)
[![界面](https://img.shields.io/badge/UI-%E7%AE%80%E4%BD%93%E4%B8%AD%E6%96%87-ef4444?style=flat-square)](#-常见问题)

**简体中文** · [English](README.md)

---

Vent Studio 是一个面向 [Wallpaper Engine](https://store.steampowered.com/app/431960/Wallpaper_Engine/)
用户的小工具：直接读本地壁纸库（不登录 Steam、不联网），显示真实缩略图、播放视频壁纸、
解包 `scene.pkg`，还能把场景 / 网页壁纸录成普通视频文件。

界面是用 [Flet](https://flet.dev) 1.0.4 手写的液态玻璃风格，全中文。运行期写的东西都在
exe 旁边的便携目录 `data\` 里，删掉即干净。

## ✨ 功能

| | |
| :--- | :--- |
| **壁纸库** | 自动扫描 Steam 创意工坊（`431960`）和本地 `projects`，D 盘 E 盘都能找到；找不到时可一键手动指定目录。 |
| **预览** | 真实缩略图（带缓存）、视频播放；播放器打不开的编码自动转成 H.264。 |
| **解包** | 从 `scene.pkg` 里抽出图片 / 视频 / 音频，可选「只导画面」或「画面 + 音频」。 |
| **录制** | 通过 Wallpaper Engine 本体录制场景 / 网页壁纸（capturekit，失败回退 gdigrab）。默认 15 秒，最长 2 分钟。 |
| **设为背景** | 任意壁纸都能当软件自己的背景，界面后面那层模糊就是它。 |
| **离线优先** | 除了可选的 FFmpeg 一次性下载，不联网；下载先测国内镜像速度，太慢自动换官方源。 |

## 📋 环境要求

- Windows 10（1809+）/ Windows 11 64 位
- [Wallpaper Engine](https://store.steampowered.com/app/431960/Wallpaper_Engine/)（本程序只读文件）
- **FFmpeg 可选**：合成音视频、录制时需要；没有会提示一次性下载（约 30 MB），也可以用系统里已有的

## 🚀 源码运行

```bat
git clone https://github.com/CateOpal/vent-studio.git
cd vent-studio
python -m pip install -r requirements.txt
python main.py
```

## 📦 打包

标准 Flet 打包方式：`flet pack` 内部调用 PyInstaller，产物落在 `dist\`：

```bat
flet pack main.py --name "Vent Studio" --icon assets\icon.ico --onedir --add-data "assets;assets"
```

运行期写的东西（配置、日志、缩略图缓存、解压出来的 Flet 客户端）都在 exe 旁边的
`data\`，所以整个目录可以直接压成绿色版压缩包带走。

## 🗂 目录结构

```
main.py              入口：先准备 Flet 客户端，再 ft.run(vent.app.main)
requirements.txt     运行依赖
assets/              icon.ico、icon.png（窗口图标与打包后的 exe 图标）
vent/                应用包
  app.py             App 组合各 mixin
  compat.py          UI 层统一的导入面
  config.py          配置读写（data\config.json）
  constants.py       窗口 / 卡片尺寸、字号、类型图标
  paths.py           运行目录（便携 data\，兜底 %APPDATA%）
  theme.py           液态玻璃设计令牌 + 控件工厂
  core/              scan（扫描）、pkg（PKG 解析）、ffmpeg、ffsetup（下载）、winutil、client
  ui/                shell / library / detail / settings / export / record
```

## ❓ 常见问题

<details>
<summary><b>找不到壁纸库</b></summary>

壁纸库来自 `steamapps/workshop/content/431960`。Steam 装在别的盘时程序会自动遍历所有
Steam 库目录；仍然找不到就打开 **设置 → 组件 → 引擎目录** 手动指一次。
</details>

<details>
<summary><b>录出来是黑屏</b></summary>

录制要求正常完整性级别运行。从脚本或沙箱终端（Low IL）启动会挡住截屏接口，
直接双击 `Vent Studio.exe` 即可。
</details>

<details>
<summary><b>配置存在哪？</b></summary>

exe 旁边的 `data\config.json`，日志是同目录的 `vent.log`。想恢复出厂设置，
把 `data\` 整个删掉即可。
</details>

<details>
<summary><b>为什么只有中文界面？</b></summary>

界面就是按简体中文设计和书写的，没有切换语言的翻译层。详见 [CHANGELOG.md](CHANGELOG.md)。
</details>

## 📄 许可

[MIT](LICENSE.md)
