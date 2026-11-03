# Contributing

Thanks for taking a look! This is a small, Windows-only desktop app; keeping it that way
is a feature, not a limitation.

## Development setup

~~~bat
git clone https://github.com/CateOpal/vent-studio.git
cd vent-studio
python -m pip install -r requirements.txt
python main.py
~~~

Requires Python 3.10+ on Windows. The first run creates `data\` next to `main.py`
(config, log and thumbnail cache).

## Project conventions

- `vent/core` must not import `flet`; all UI code lives in `vent/ui`.
- Long-running work (scanning, thumbnails, unpacking) goes through `asyncio.to_thread`
  so the UI thread never blocks.
- Dialogs are transparent full-screen containers holding one card; give them a `content=`
  and an `on_click` that closes the dialog or swallows the click.
- User-visible strings are written in Simplified Chinese and go through `txt()`,
  `text_button()` and `toast()`.

## Before you open a PR

- Run the app once and check `data\vent.log` for tracebacks.
- Do not commit `data/`, `dist/` or `build/` — they are generated at run / package time.
- Keep the diff focused; unrelated formatting changes make review harder.
