# Contributing to Samovar Lite

Thanks for wanting to help. Bug reports, fixes, and reports of "this is not how PotPlayer behaves" are
all welcome.

## Reporting a problem

Open an [issue](https://github.com/AliMilani/samovar-lite/issues/new/choose) and include what the form asks
for. The text from **Ctrl+F1** (Playback/System Info, "Copy All") answers most of the questions about
your system and the file at once.

For security problems, see [SECURITY.md](SECURITY.md) instead of opening a public issue.

## Setting up

```sh
git clone https://github.com/AliMilani/samovar-lite.git
cd samovar-lite
./install.sh --no-desktop
.venv/bin/python -m pip install pytest ruff
```

Run from the checkout with `.venv/bin/samovar-lite`. It reads your normal settings; point
`XDG_CONFIG_HOME` somewhere else if you want a clean slate.

## Before you open a pull request

```sh
ruff check . && ruff format .        # style; CI fails on either
.venv/bin/python -m pytest           # unit tests, no display needed
.venv/bin/python tests/smoke.py      # drives the real window; needs ffmpeg and a display
```

Without a display, the smoke test runs under a virtual one, exactly as CI does:

```sh
QT_QPA_PLATFORM=xcb LIBGL_ALWAYS_SOFTWARE=1 xvfb-run -a -s "-screen 0 1920x1080x24" \
    .venv/bin/python tests/smoke.py
```

## What makes a change easy to merge

- **One topic per pull request**, with a description of what changes for the user.
- **Behaviour first.** When PotPlayer has an established behaviour for something, Samovar Lite follows it
  unless Linux makes that impossible. Say so in the description if you deviate.
- **No third-party artwork.** Every glyph is drawn in `samovar_lite/skin.py` from primitives. Do not add
  icons, skins or other assets taken from PotPlayer or anywhere else.
- **Tests** for logic that can be tested without a window (`tests/unit`), and a line in the smoke test
  when you fix something a user could see.
- **A changelog entry** under "Unreleased" in [CHANGELOG.md](CHANGELOG.md).
- Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/)
  (`feat: ...`, `fix: ...`, `docs: ...`).

## Where things are

| File | What lives there |
|------|------------------|
| `samovar_lite/app.py` | Main window, keyboard and mouse handling, every user action, entry point |
| `samovar_lite/engine.py` | libmpv wrapper and the OpenGL video widget |
| `samovar_lite/widgets.py` | Title bar, seek bar, volume bar, control row, on-screen display |
| `samovar_lite/skin.py` | Colours, metrics and glyph drawing |
| `samovar_lite/menus.py` | The right-click menu, rebuilt from live state each time it opens |
| `samovar_lite/playlist.py` | Playlist panel |
| `samovar_lite/dialogs.py` | Control panel, preferences and the small dialogs |
| `samovar_lite/settings.py`, `samovar_lite/util.py` | Settings file and helpers without Qt dependencies |

By contributing you agree that your work is licensed under the project's license,
[GPL-3.0-or-later](LICENSE).
