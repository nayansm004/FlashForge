# FlashForge

AI-powered flashcard software. Paste text, upload a document, or drop in a URL — FlashForge turns it into a studyable deck in seconds, using free-tier AI models. No account, no cloud, no subscription.

![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![PyQt6](https://img.shields.io/badge/UI-PyQt6-41cd52)
![License](https://img.shields.io/badge/license-MIT-lightgrey)

## What it does

- **Generate** — paste notes, upload a PDF/DOCX/TXT, or fetch a URL, pick a difficulty and card count, and let AI write the Q&A pairs.
- **Study** — flip-card study mode with keyboard shortcuts (`Space` flip, `↑` knew it, `↓` missed, `→` skip), live scoring, and an end-of-session summary with confetti when you crush it.
- **Spaced repetition** — cards you get right are pushed further out; right-click a deck and choose **Study Due Cards Only** to review just what's actually due today.
- **Manage decks** — rename, delete, export to JSON, and import decks back in (including from a friend, or a backup).
- **Runs entirely locally** — your notes and your OpenRouter API key never leave your machine except to call the model you chose.

## Use it online

No install: **[Open the web app](https://nayansm004.github.io/flashforge/)** — same generation and spaced-repetition logic, running entirely in your browser. Decks are stored in browser local storage (this device only — export to JSON if you want a backup or want to move them). Paste your own OpenRouter key in its Settings tab; nothing is sent anywhere except directly to OpenRouter.

The web version only accepts pasted text or `.txt` uploads for now (no PDF/DOCX parsing yet — that's desktop-only). To enable Pages yourself on a fork: **Settings → Pages → Source: GitHub Actions** (the included workflow deploys `docs/` automatically).

## Download the desktop app

Grab a build for your OS from the [Releases page](../../releases) — no install required, just unzip and run.

| OS | File |
|---|---|
| Windows | `FlashForge-windows.zip` |
| macOS | `FlashForge-macos.zip` |
| Linux | `FlashForge-linux.zip` |

## Running from source

```bash
git clone https://github.com/nayansm004/flashforge.git
cd flashforge
pip install -r requirements.txt
python main.py
```

## AI setup (free)

1. Get a free API key at [openrouter.ai](https://openrouter.ai/) — no credit card needed.
2. In FlashForge, go to **Settings → AI Configuration** and paste the key.
3. Leave the model on `openrouter/free` — it auto-picks whatever free model is currently live on OpenRouter, so you're never stuck on a model that's been retired. Pinned `:free` models are offered too, but OpenRouter rotates its free lineup without much notice, so treat those as fallbacks, not guarantees.

Without a key, FlashForge just tells you it needs one — no silent mock data.

## Data

Everything is stored locally in a SQLite database in your OS's standard app-data folder. There's no server, no account, no telemetry. Export/import uses a portable JSON format if you want to move decks between machines or share a deck with someone.

## Building it yourself

```bash
pip install pyinstaller
pyinstaller flashforge.spec
```

Output lands in `dist/FlashForge/`. Pushing a tag like `v1.0.0` also triggers CI to build all three platforms automatically and attach them to a GitHub Release — see `.github/workflows/build.yml`.

## Tech

Single-file PyQt6 desktop app, SQLite for storage, OpenRouter for generation (with automatic retry/fallback across models), PyMuPDF for PDF text extraction, python-docx for `.docx`.

## License

MIT — do whatever you want with it.
