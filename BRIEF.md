# Voix du Niger: a voice collection platform for Niger's national languages

**Status:** imported 2026-10-09 from `voix-du-niger-national-platform.zip` (app version
0.6.0). Working MVP for a controlled pilot, not a production platform. Not yet specified
with Spec Kit.

**UI redesign, 2026-10-09:** the public page became a four-step flow (language, activity,
agreement, code) followed by a single recording screen, in plain French. The team space
shows one section at a time. The agreement text was rewritten in plain language, so the
consent version moved to `consent-v5-plain-language`; it needs the same validation as v4.

**Related:** `08-zarma-speech` builds the Zarma voice assistant. This project produces
the reviewed speech data such an assistant needs, for all national languages.

## Question

Can a small team collect speech in Niger's eleven national languages, review it, and
export clean, rights-checked datasets for speech recognition (ASR) and speech synthesis
(TTS), without inventing local-language content?

## What it is

- **Collection page** (`/`): pseudonymous code, pilot consent, language and task choice.
  Two tasks: read a prompt aloud (usable for ASR and TTS after review) or speak freely
  from a prompt (ASR only, after a verified transcript).
- **Admin** (`/admin`): named accounts with roles and language or region scopes,
  separate ASR and TTS review, audit log, participant deletion, national dashboard.
- **Exports**: per task, mono 16 bit WAV plus `metadata.csv`. Versioned dataset releases
  with independent rights validation.
- **Preparation script** `scripts/prepare_dataset.py`: audio checks, exact duplicates,
  grouped train, validation and test split.
- **Stack**: FastAPI, SQLite, plain HTML and JS. FFmpeg and ffprobe are required: the
  server rejects every audio upload without them.

## Blocking before a real pilot

1. Install FFmpeg (`sudo apt install ffmpeg`). Without it, uploads return 503 and 9 of
   40 tests fail.
2. No approved content ships with the app. The ten Zarma seed sentences in
   `examples/phrases_seed_DO_NOT_IMPORT_UNREVIEWED.csv` need a native speaker's review
   before import.
3. HTTPS is needed before any phone can record.
4. Consent text, end to end deletion, backups and brute force protection are listed as
   unfinished in `docs/PUBLIC_READINESS.md`.

## Run it

```bash
cd 11-voix-du-niger
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
export ZARMA_ADMIN_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(40))')"
export ZARMA_BOOTSTRAP_ADMIN_USERNAME=admin-local
export ZARMA_BOOTSTRAP_ADMIN_PASSWORD=change-me-14-chars-minimum
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## Open questions

- The code does not follow `_template/` (one 2,000 line `app/main.py`, French docs).
  Decide whether to restructure it or keep it as an imported project with its own layout.
- Package and environment names still say `zarma` although the scope is now national.
