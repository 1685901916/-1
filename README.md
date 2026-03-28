# MOBI Manga Enhancer

First-pass local pipeline for manga sources:

1. unpack or split a supported source file
2. normalize extracted page images
3. score page quality
4. apply a basic enhancement pipeline
5. export enhanced pages as a `.cbz`
6. optionally hand off to KCC for Kindle repack

This repository now supports `.mobi`, `.cbz`, `.zip`, `.pdf`, and image folders as import sources.

## Current scope

- Supports unprotected `.mobi` / `.azw3` inputs
- Supports `.cbz`, `.zip`, `.pdf`, and image-folder inputs
- Works even without AI models by shipping a basic image enhancement engine
- Detects external tools and integrates with them when available
- Keeps the pipeline outputs in a structured workspace for inspection
- Lets you choose whether final output keeps `pages` and `pages_ai`
- Supports merging multiple selected sources into one packaged output

## External tools

Recommended:

- `KindleUnpack` for MOBI unpacking
- `Kindle Comic Converter (KCC)` for final Kindle repack

You can point the app at custom commands with environment variables:

- `KINDLEUNPACK_CMD`
- `KCC_CMD`

If a variable points to a `.py` file, the app will invoke it through Python.

## Install

```bash
python -m pip install -e .
```

## Commands

Check environment:

```bash
python -m mobi_manga_app.cli doctor
```

Run the full pipeline:

```bash
python -m mobi_manga_app.cli process "F:\path\book.mobi" --workspace .work\book01
```

Skip repack and only get enhanced pages plus `.cbz`:

```bash
python -m mobi_manga_app.cli process "F:\path\book.mobi" --workspace .work\book01 --skip-kcc
```

Adjust enhancement strength:

```bash
python -m mobi_manga_app.cli process "F:\path\book.mobi" --workspace .work\book01 --mode strong --scale 2.0
```

## Workspace layout

`process` creates these folders:

- `unpacked/` raw unpacker output or rendered PDF pages
- `pages/` normalized sequential page files
- `enhanced/` enhanced page files
- `export/` generated `.cbz` and optional KCC output
- `analysis.json` page metrics and summary
- `manifest.json` run metadata

## Frontend

Visual dashboard lives in `frontend/`.

Run it with:

```bash
python -m mobi_manga_app.api

cd frontend
npm install
npm run dev
```

Build production assets with:

```bash
cd frontend
npm run build
```

The Vite dev server proxies `/api/*` to `http://127.0.0.1:8765`.

## Launcher build

Build the packaged launcher with:

```bash
powershell -ExecutionPolicy Bypass -File scripts/build-launcher.ps1
```

If the default `dist/MangaEnhancementLauncher` directory is locked by Explorer or an old process, build to a fresh location with:

```bash
pyinstaller packaging/launcher.spec --noconfirm --clean --distpath dist_rebuild --workpath build_rebuild
```

The latest verified rebuilt launcher output is:

```text
dist_rebuild/MangaEnhancementLauncher
```

## Current verified flows

- `mobi -> pages -> enhance -> package/export`
- `cbz/zip -> pages -> enhance -> package/export`
- `pdf -> pages -> enhance -> package/export`
- `folder + folder -> merged cbz/zip`

## Notes

- DRM-protected files are out of scope.
- The built-in enhancement engine is a baseline, not a replacement for Real-ESRGAN or waifu2x.
- If KCC is missing, the pipeline still completes and writes an enhanced `.cbz`.
