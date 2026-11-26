from __future__ import annotations

import csv
import hashlib
from contextlib import contextmanager
import io
import json
import os
import re
import secrets
import sqlite3
import subprocess
import tempfile
import uuid
import urllib.parse
import zipfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Annotated, Iterator

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, UploadFile, Request
from fastapi.responses import FileResponse, HTMLResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

PROJECT_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = PROJECT_DIR / "app" / "static"
DATA_DIR = Path(os.getenv("ZARMA_DATA_DIR", str(PROJECT_DIR / "data"))).expanduser().resolve()
AUDIO_DIR = DATA_DIR / "audio"
DB_PATH = DATA_DIR / "collection.sqlite3"
ADMIN_TOKEN = os.getenv("ZARMA_ADMIN_TOKEN", "").strip()
EXPORT_SAMPLE_RATE = int(os.getenv("ZARMA_EXPORT_SAMPLE_RATE", "22050"))
MAX_UPLOAD_BYTES = 30 * 1024 * 1024
MAX_CSV_BYTES = 2 * 1024 * 1024
CONSENT_VERSION = "consent-v5-plain-language"
SESSION_HOURS = int(os.getenv("ZARMA_SESSION_HOURS", "12"))
PASSWORD_ITERATIONS = 310_000
PREPARED_DIR = (DATA_DIR / "prepared_datasets").resolve()
PREPARED_DIR.mkdir(parents=True, exist_ok=True)
LANGUAGE_SEED = [
    ("ara", "Arabe", "ara", "spoken", "setup", "Préciser la variété locale et la graphie avant collecte."),
    ("bdm", "Buduma", "bdm", "spoken", "setup", "Consigne, orthographe et variantes à valider avec des locuteurs."),
    ("ful", "Fulfuldé", "ful", "spoken", "setup", "Préciser la variété de Fulfuldé et sa zone de collecte."),
    ("gux", "Gourmanchéma (Gulmancema)", "gux", "spoken", "setup", "Vérifier la norme orthographique utilisée au Niger."),
    ("ha", "Hausa", "hau", "spoken", "pilot", "Le code applicatif ha est conservé pour compatibilité; ISO 639-3: hau."),
    ("kau", "Kanuri", "kau", "spoken", "setup", "Préciser la variété locale et les conventions d’écriture."),
    ("taq", "Tamajaq / Tamasheq", "taq", "spoken", "pilot", "Définir la variété locale (p. ex. région) et la norme de transcription."),
    ("tda", "Tagdal", "tda", "spoken", "setup", "Langue à ressources limitées : validation native nécessaire."),
    ("twq", "Tassawaq", "twq", "spoken", "setup", "Langue à ressources limitées : validation native nécessaire."),
    ("tuq", "Teda / Tedaga (catégorie Tubu/Toubou)", "tuq", "spoken", "setup", "Le code ISO tuq désigne Teda/Tedaga. Ne pas agréger avec Dazaga ; voir le sous-corpus dzg."),
    ("dzg", "Dazaga (sous-corpus Tubu/Toubou)", "dzg", "spoken", "setup", "Sous-corpus technique distinct de Teda/Tedaga ; valider les variétés et l’orthographe avec des locuteurs."),
    ("dje", "Zarma-Sonraï", "dje", "spoken", "pilot", "Le projet conserve dje pour le corpus Zarma actuel; préciser les variétés Songhay."),
    ("en", "Anglais", "eng", "work", "work_language", "Langue de travail selon la Charte de la Refondation 2025."),
    ("fr", "Français", "fra", "work", "work_language", "Langue de travail selon la Charte de la Refondation 2025."),
]
VALID_LANGUAGE_CODES = {row[0] for row in LANGUAGE_SEED}
REGION_CODES = {"AGD", "DIF", "DOS", "MAR", "TAH", "TIL", "ZIN", "NIA", "UNK"}
ROLE_PERMISSIONS = {
    "transcriber": {"transcribe"},
    "reviewer": {"transcribe", "review_asr"},
    "validator": {"transcribe", "review_asr", "validate_tts", "validate_dataset"},
    "language_lead": {"transcribe", "review_asr", "language_content"},
    "dataset_manager": {"read_dashboard", "language_content", "prepare_dataset", "validate_dataset", "export_dataset"},
    "training_operator": {"read_dashboard", "prepare_dataset", "export_dataset", "manage_training"},
    "provider_manager": {"read_dashboard", "manage_providers"},
    "privacy_officer": {"read_dashboard", "delete_participant"},
    "admin": {"*"},
    "superadmin": {"*"},
}
ALLOWED_MIME_PREFIX = "audio/"

DATA_DIR.mkdir(parents=True, exist_ok=True)
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Voix du Niger : collecte vocale multilingue", version="0.6.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def db_conn() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with db_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS participants (
                participant_code TEXT PRIMARY KEY,
                consent_version TEXT NOT NULL,
                consent_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS phrases (
                phrase_id TEXT PRIMARY KEY,
                language_code TEXT NOT NULL DEFAULT 'dje',
                text_zarma TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT '',
                orthography_version TEXT NOT NULL DEFAULT 'v1',
                source TEXT NOT NULL DEFAULT '',
                source_license TEXT NOT NULL DEFAULT '',
                gloss_fr TEXT NOT NULL DEFAULT '',
                native_reviewed_by TEXT NOT NULL DEFAULT '',
                native_reviewed_at TEXT NOT NULL DEFAULT '',
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                UNIQUE(language_code, text_zarma, orthography_version)
            );

            CREATE TABLE IF NOT EXISTS elicitation_prompts (
                elicitation_prompt_id TEXT PRIMARY KEY,
                language_code TEXT NOT NULL DEFAULT 'dje',
                prompt_text TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'general',
                orthography_version TEXT NOT NULL DEFAULT 'v1',
                source TEXT NOT NULL DEFAULT '',
                source_license TEXT NOT NULL DEFAULT '',
                native_reviewed_by TEXT NOT NULL DEFAULT '',
                native_reviewed_at TEXT NOT NULL DEFAULT '',
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                UNIQUE(language_code, prompt_text, orthography_version)
            );

            CREATE TABLE IF NOT EXISTS recordings (
                recording_id TEXT PRIMARY KEY,
                participant_code TEXT NOT NULL REFERENCES participants(participant_code),
                phrase_id TEXT REFERENCES phrases(phrase_id),
                elicitation_prompt_id TEXT REFERENCES elicitation_prompts(elicitation_prompt_id),
                task_type TEXT NOT NULL DEFAULT 'read_speech'
                    CHECK(task_type IN ('read_speech', 'spontaneous_speech')),
                language_code TEXT NOT NULL DEFAULT 'dje',
                consent_version TEXT NOT NULL DEFAULT '',
                consent_at TEXT NOT NULL DEFAULT '',
                consent_asr INTEGER NOT NULL DEFAULT 0 CHECK(consent_asr IN (0, 1)),
                consent_tts INTEGER NOT NULL DEFAULT 0 CHECK(consent_tts IN (0, 1)),
                prompt_text TEXT NOT NULL DEFAULT '', 
                transcription_text TEXT NOT NULL DEFAULT '',
                stored_filename TEXT NOT NULL,
                original_filename TEXT NOT NULL,
                mime_type TEXT NOT NULL,
                duration_seconds REAL,
                file_size_bytes INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending_review'
                    CHECK(status IN ('pending_review', 'approved', 'redo', 'rejected')),
                asr_approved INTEGER NOT NULL DEFAULT 0 CHECK(asr_approved IN (0, 1)),
                tts_approved INTEGER NOT NULL DEFAULT 0 CHECK(tts_approved IN (0, 1)),
                created_at TEXT NOT NULL,
                reviewed_at TEXT,
                reviewer_note TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS review_events (
                event_id TEXT PRIMARY KEY,
                recording_id TEXT NOT NULL REFERENCES recordings(recording_id),
                decision TEXT NOT NULL,
                reviewer_label TEXT NOT NULL DEFAULT '',
                transcription_snapshot TEXT NOT NULL DEFAULT '',
                note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS deletion_events (
                event_id TEXT PRIMARY KEY,
                request_ref TEXT NOT NULL,
                reason TEXT NOT NULL,
                handled_by TEXT NOT NULL,
                recordings_deleted INTEGER NOT NULL DEFAULT 0,
                audio_files_deleted INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS language_catalog (
                code TEXT PRIMARY KEY, name_fr TEXT NOT NULL, iso_639_3 TEXT NOT NULL DEFAULT '',
                scope TEXT NOT NULL CHECK(scope IN ('spoken','work','other')),
                collection_status TEXT NOT NULL DEFAULT 'setup', content_note TEXT NOT NULL DEFAULT '',
                source_url TEXT NOT NULL DEFAULT '', is_enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE, display_name TEXT NOT NULL,
                email TEXT NOT NULL DEFAULT '', password_hash TEXT NOT NULL, role TEXT NOT NULL,
                allowed_languages_json TEXT NOT NULL DEFAULT '[]', assigned_regions_json TEXT NOT NULL DEFAULT '[]',
                active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, last_login_at TEXT
            );
            CREATE TABLE IF NOT EXISTS auth_sessions (
                token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                created_at TEXT NOT NULL, expires_at TEXT NOT NULL, revoked_at TEXT
            );
            CREATE TABLE IF NOT EXISTS dataset_releases (
                release_id TEXT PRIMARY KEY, label TEXT NOT NULL, task TEXT NOT NULL CHECK(task IN ('asr','tts')),
                language_code TEXT NOT NULL, region_code TEXT NOT NULL DEFAULT 'ALL', status TEXT NOT NULL DEFAULT 'awaiting_preparation',
                approved_recordings INTEGER NOT NULL DEFAULT 0, estimated_audio_hours REAL NOT NULL DEFAULT 0,
                relative_path TEXT NOT NULL DEFAULT '', manifest_sha256 TEXT NOT NULL DEFAULT '',
                manifest_summary_json TEXT NOT NULL DEFAULT '{}', license_status TEXT NOT NULL DEFAULT 'pending',
                prepared_by TEXT NOT NULL DEFAULT '', reviewed_by TEXT NOT NULL DEFAULT '',
                review_note TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS providers (
                provider_id TEXT PRIMARY KEY, name TEXT NOT NULL, provider_type TEXT NOT NULL,
                endpoint_url TEXT NOT NULL DEFAULT '', region TEXT NOT NULL DEFAULT '',
                credential_env_var TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'configured',
                notes TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS training_jobs (
                job_id TEXT PRIMARY KEY, release_id TEXT NOT NULL REFERENCES dataset_releases(release_id),
                provider_id TEXT REFERENCES providers(provider_id), task TEXT NOT NULL, language_code TEXT NOT NULL,
                model_name TEXT NOT NULL, training_method TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'queued',
                remote_job_id TEXT NOT NULL DEFAULT '', started_by TEXT NOT NULL, metrics_json TEXT NOT NULL DEFAULT '{}',
                log_summary TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, started_at TEXT, finished_at TEXT, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS audit_events (
                event_id TEXT PRIMARY KEY, actor_user_id TEXT NOT NULL DEFAULT '', actor_role TEXT NOT NULL DEFAULT '',
                action TEXT NOT NULL, resource_type TEXT NOT NULL DEFAULT '', resource_id TEXT NOT NULL DEFAULT '',
                details_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_sessions_user ON auth_sessions(user_id, expires_at);
            CREATE INDEX IF NOT EXISTS idx_users_role ON users(role, active);
            CREATE INDEX IF NOT EXISTS idx_dataset_status ON dataset_releases(status, task, language_code);
            CREATE INDEX IF NOT EXISTS idx_training_status ON training_jobs(status, provider_id);
            CREATE INDEX IF NOT EXISTS idx_recordings_status ON recordings(status);
            CREATE INDEX IF NOT EXISTS idx_recordings_participant ON recordings(participant_code);
            CREATE INDEX IF NOT EXISTS idx_recordings_phrase ON recordings(phrase_id);
            """
        )
        # Safe migration for databases created by the earlier Zarma-only MVP.
        phrase_columns = {row[1] for row in conn.execute("PRAGMA table_info(phrases)").fetchall()}
        if "language_code" not in phrase_columns:
            conn.execute("ALTER TABLE phrases ADD COLUMN language_code TEXT NOT NULL DEFAULT 'dje'")
        optional_phrase_columns = {
            "source": "TEXT NOT NULL DEFAULT ''",
            "source_license": "TEXT NOT NULL DEFAULT ''",
            "gloss_fr": "TEXT NOT NULL DEFAULT ''",
            "native_reviewed_by": "TEXT NOT NULL DEFAULT ''",
            "native_reviewed_at": "TEXT NOT NULL DEFAULT ''",
        }
        for column, declaration in optional_phrase_columns.items():
            if column not in phrase_columns:
                conn.execute(f"ALTER TABLE phrases ADD COLUMN {column} {declaration}")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_phrases_language ON phrases(language_code, is_active)")
        deletion_columns = {row[1] for row in conn.execute("PRAGMA table_info(deletion_events)").fetchall()}
        if "cleanup_pending" not in deletion_columns:
            conn.execute("ALTER TABLE deletion_events ADD COLUMN cleanup_pending INTEGER NOT NULL DEFAULT 0")


def migrate_recordings_v2() -> None:
    """Add dual ASR/TTS eligibility and nullable phrase links, preserving legacy recordings."""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys = OFF")
        cols = {row[1]: row for row in conn.execute("PRAGMA table_info(recordings)").fetchall()}
        if not cols:
            return
        phrase_not_null = bool(cols.get("phrase_id") and cols["phrase_id"][3])
        required_columns = {"elicitation_prompt_id", "task_type", "language_code", "consent_version", "consent_at", "consent_asr", "consent_tts", "prompt_text", "transcription_text", "asr_approved", "tts_approved"}
        missing_columns = required_columns - set(cols)
        if phrase_not_null:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("""
                CREATE TABLE recordings_v2 (
                    recording_id TEXT PRIMARY KEY,
                    participant_code TEXT NOT NULL REFERENCES participants(participant_code),
                    phrase_id TEXT REFERENCES phrases(phrase_id),
                    elicitation_prompt_id TEXT REFERENCES elicitation_prompts(elicitation_prompt_id),
                    task_type TEXT NOT NULL DEFAULT 'read_speech' CHECK(task_type IN ('read_speech','spontaneous_speech')),
                    language_code TEXT NOT NULL DEFAULT 'dje',
                    consent_version TEXT NOT NULL DEFAULT '',
                    consent_at TEXT NOT NULL DEFAULT '',
                    consent_asr INTEGER NOT NULL DEFAULT 0 CHECK(consent_asr IN (0,1)),
                    consent_tts INTEGER NOT NULL DEFAULT 0 CHECK(consent_tts IN (0,1)),
                    prompt_text TEXT NOT NULL DEFAULT '',
                    transcription_text TEXT NOT NULL DEFAULT '',
                    stored_filename TEXT NOT NULL,
                    original_filename TEXT NOT NULL,
                    mime_type TEXT NOT NULL,
                    duration_seconds REAL,
                    file_size_bytes INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending_review' CHECK(status IN ('pending_review','approved','redo','rejected')),
                    asr_approved INTEGER NOT NULL DEFAULT 0 CHECK(asr_approved IN (0,1)),
                    tts_approved INTEGER NOT NULL DEFAULT 0 CHECK(tts_approved IN (0,1)),
                    created_at TEXT NOT NULL,
                    reviewed_at TEXT,
                    reviewer_note TEXT NOT NULL DEFAULT ''
                )
            """)
            phrase_expr = "r.phrase_id" if "phrase_id" in cols else "NULL"
            # Legacy approved clips have an old general review, not a task-specific TTS review.
            conn.execute(f"""
                INSERT INTO recordings_v2(
                    recording_id, participant_code, phrase_id, elicitation_prompt_id, task_type, language_code, consent_version, consent_at, consent_asr, consent_tts, prompt_text, transcription_text,
                    stored_filename, original_filename, mime_type, duration_seconds, file_size_bytes, status,
                    asr_approved, tts_approved, created_at, reviewed_at, reviewer_note
                )
                SELECT r.recording_id, r.participant_code, {phrase_expr}, NULL, 'read_speech',
                       COALESCE(p.language_code, 'dje'), 'legacy_unverified', '', 0, 0,
                       COALESCE(p.text_zarma, ''), COALESCE(p.text_zarma, ''),
                       r.stored_filename, r.original_filename, r.mime_type, r.duration_seconds, r.file_size_bytes,
                       r.status, CASE WHEN r.status='approved' THEN 1 ELSE 0 END, 0,
                       r.created_at, r.reviewed_at, r.reviewer_note
                FROM recordings r LEFT JOIN phrases p ON p.phrase_id=r.phrase_id
                LEFT JOIN participants part ON part.participant_code=r.participant_code
            """)
            conn.execute("DROP TABLE recordings")
            conn.execute("ALTER TABLE recordings_v2 RENAME TO recordings")
            conn.commit()
        else:
            # Columns can be added in place when phrase_id is already nullable.
            for column, declaration in {
                "elicitation_prompt_id": "TEXT REFERENCES elicitation_prompts(elicitation_prompt_id)",
                "task_type": "TEXT NOT NULL DEFAULT 'read_speech'",
                "language_code": "TEXT NOT NULL DEFAULT 'dje'",
                "consent_version": "TEXT NOT NULL DEFAULT ''",
                "consent_at": "TEXT NOT NULL DEFAULT ''",
                "consent_asr": "INTEGER NOT NULL DEFAULT 0",
                "consent_tts": "INTEGER NOT NULL DEFAULT 0",
                "prompt_text": "TEXT NOT NULL DEFAULT ''",
                "transcription_text": "TEXT NOT NULL DEFAULT ''",
                "asr_approved": "INTEGER NOT NULL DEFAULT 0",
                "tts_approved": "INTEGER NOT NULL DEFAULT 0",
            }.items():
                if column not in cols:
                    conn.execute(f"ALTER TABLE recordings ADD COLUMN {column} {declaration}")
            conn.execute("UPDATE recordings SET prompt_text=COALESCE((SELECT text_zarma FROM phrases WHERE phrases.phrase_id=recordings.phrase_id), '') WHERE prompt_text=''")
            conn.execute("UPDATE recordings SET language_code=COALESCE((SELECT language_code FROM phrases WHERE phrases.phrase_id=recordings.phrase_id), 'dje') WHERE task_type='read_speech'")
            conn.execute("UPDATE recordings SET consent_version=COALESCE((SELECT consent_version FROM participants WHERE participants.participant_code=recordings.participant_code), '') WHERE consent_version=''")
            conn.execute("UPDATE recordings SET consent_at=COALESCE((SELECT consent_at FROM participants WHERE participants.participant_code=recordings.participant_code), '') WHERE consent_at=''")
            conn.execute("UPDATE recordings SET transcription_text=prompt_text WHERE transcription_text=''")
            conn.execute("UPDATE recordings SET asr_approved=1 WHERE status='approved' AND asr_approved=0")
            conn.commit()
        conn.execute("CREATE INDEX IF NOT EXISTS idx_recordings_status ON recordings(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_recordings_participant ON recordings(participant_code)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_recordings_phrase ON recordings(phrase_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_recordings_task_status ON recordings(task_type, status, asr_approved, tts_approved)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_recordings_elicitation_prompt ON recordings(elicitation_prompt_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_elicitation_prompts_language ON elicitation_prompts(language_code, is_active)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_review_events_recording ON review_events(recording_id, created_at)")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def migrate_legacy_phrase_uniqueness() -> None:
    """Rebuild an older Zarma-only phrase table so identical text can exist in different languages."""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    try:
        conn.execute("PRAGMA foreign_keys = OFF")
        table = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='phrases'").fetchone()
        if not table or not table[0]:
            return
        compact_sql = re.sub(r"\s+", "", table[0].lower())
        if "unique(text_zarma,orthography_version)" not in compact_sql:
            return
        conn.execute("BEGIN IMMEDIATE")
        existing_columns = {row[1] for row in conn.execute("PRAGMA table_info(phrases)").fetchall()}
        def old_column_or_empty(name: str) -> str:
            return name if name in existing_columns else "''"
        conn.execute("""
            CREATE TABLE phrases_multilang_new (
                phrase_id TEXT PRIMARY KEY,
                language_code TEXT NOT NULL DEFAULT 'dje',
                text_zarma TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT '',
                orthography_version TEXT NOT NULL DEFAULT 'v1',
                source TEXT NOT NULL DEFAULT '',
                source_license TEXT NOT NULL DEFAULT '',
                gloss_fr TEXT NOT NULL DEFAULT '',
                native_reviewed_by TEXT NOT NULL DEFAULT '',
                native_reviewed_at TEXT NOT NULL DEFAULT '',
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                UNIQUE(language_code, text_zarma, orthography_version)
            )
        """)
        conn.execute(f"""
            INSERT INTO phrases_multilang_new
                (phrase_id, language_code, text_zarma, category, orthography_version,
                 source, source_license, gloss_fr, native_reviewed_by, native_reviewed_at,
                 is_active, created_at)
            SELECT phrase_id, COALESCE(language_code, 'dje'), text_zarma, category, orthography_version,
                   {old_column_or_empty('source')}, {old_column_or_empty('source_license')},
                   {old_column_or_empty('gloss_fr')}, {old_column_or_empty('native_reviewed_by')},
                   {old_column_or_empty('native_reviewed_at')}, is_active, created_at
            FROM phrases
        """)
        conn.execute("DROP TABLE phrases")
        conn.execute("ALTER TABLE phrases_multilang_new RENAME TO phrases")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_phrases_language ON phrases(language_code, is_active)")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


init_db()
migrate_legacy_phrase_uniqueness()
migrate_recordings_v2()

def migrate_platform_extensions() -> None:
    with db_conn() as conn:
        participant_cols = {r[1] for r in conn.execute("PRAGMA table_info(participants)").fetchall()}
        for col, decl in {"region_code": "TEXT NOT NULL DEFAULT 'UNK'", "dialect_code": "TEXT NOT NULL DEFAULT ''", "participant_type": "TEXT NOT NULL DEFAULT 'volunteer'"}.items():
            if col not in participant_cols:
                conn.execute(f"ALTER TABLE participants ADD COLUMN {col} {decl}")
        recording_cols = {r[1] for r in conn.execute("PRAGMA table_info(recordings)").fetchall()}
        for col, decl in {"region_code": "TEXT NOT NULL DEFAULT 'UNK'", "dialect_code": "TEXT NOT NULL DEFAULT ''"}.items():
            if col not in recording_cols:
                conn.execute(f"ALTER TABLE recordings ADD COLUMN {col} {decl}")
        release_cols = {r[1] for r in conn.execute("PRAGMA table_info(dataset_releases)").fetchall()}
        if "region_code" not in release_cols:
            conn.execute("ALTER TABLE dataset_releases ADD COLUMN region_code TEXT NOT NULL DEFAULT 'ALL'")
        for code, name, iso, scope, state, note in LANGUAGE_SEED:
            conn.execute(
                "INSERT OR IGNORE INTO language_catalog(code,name_fr,iso_639_3,scope,collection_status,content_note,source_url,is_enabled,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (code, name, iso, scope, state, note, "https://www.presidence.ne/pages/refondation", 1, now_iso()),
            )
            # Refresh catalogue labels/notes on existing installs without overwriting
            # an administrator's collection_status or enabled/disabled decision.
            conn.execute("UPDATE language_catalog SET name_fr=?,iso_639_3=?,scope=?,content_note=? WHERE code=?",
                (name, iso, scope, note, code))
        # Bootstrap account is created only when an explicit strong password is provided.
        username = os.getenv("ZARMA_BOOTSTRAP_ADMIN_USERNAME", "").strip()
        password = os.getenv("ZARMA_BOOTSTRAP_ADMIN_PASSWORD", "")
        if username and password:
            exists = conn.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone()
            if not exists:
                conn.execute(
                    "INSERT INTO users(user_id,username,display_name,password_hash,role,created_at) VALUES(?,?,?,?,?,?)",
                    (str(uuid.uuid4()), username, username, hash_password(password), "admin", now_iso()),
                )

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS)
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${salt.hex()}${digest.hex()}"

def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, iterations, salt_hex, digest_hex = stored.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations))
        return secrets.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError):
        return False

migrate_platform_extensions()

def record_audit(actor: dict, action: str, resource_type: str = "", resource_id: str = "", details: dict | None = None) -> None:
    with db_conn() as conn:
        conn.execute(
            "INSERT INTO audit_events(event_id,actor_user_id,actor_role,action,resource_type,resource_id,details_json,created_at) VALUES(?,?,?,?,?,?,?,?)",
            (str(uuid.uuid4()), str(actor.get("user_id", "")), str(actor.get("role", "")), action, resource_type, resource_id, json.dumps(details or {}, ensure_ascii=False), now_iso()),
        )

def language_is_allowed(actor: dict, code: str) -> bool:
    if actor.get("role") in {"admin", "superadmin"}:
        return True
    allowed = actor.get("allowed_languages") or []
    return bool(allowed) and code in allowed

def region_is_allowed(actor: dict, code: str) -> bool:
    if actor.get("role") in {"admin", "superadmin"}:
        return True
    allowed = actor.get("assigned_regions") or []
    return bool(allowed) and code in allowed

def get_current_actor(
    request: Request,
    x_admin_token: Annotated[str | None, Header()] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> dict:
    expected = ADMIN_TOKEN
    if x_admin_token and (not expected or expected == "replace-with-a-long-random-secret"):
        raise HTTPException(status_code=503, detail="Administration désactivée : configurez ZARMA_ADMIN_TOKEN ou créez un compte bootstrap.")
    if expected and expected != "replace-with-a-long-random-secret" and secrets.compare_digest(x_admin_token or "", expected):
        actor = {"user_id": "legacy-admin-token", "username": "legacy-admin-token", "display_name": "Admin (clé historique)", "role": "admin", "allowed_languages": [], "assigned_regions": [], "auth_type": "legacy_token"}
        request.state.actor = actor
        return actor
    token = ""
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Authentification requise. Connectez-vous avec un compte ou une clé serveur autorisée.")
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    with db_conn() as conn:
        row = conn.execute(
            "SELECT s.expires_at,s.revoked_at,u.user_id,u.username,u.display_name,u.role,u.allowed_languages_json,u.assigned_regions_json,u.active "
            "FROM auth_sessions s JOIN users u ON u.user_id=s.user_id WHERE s.token_hash=?", (token_hash,)
        ).fetchone()
        if not row or row["revoked_at"] or not row["active"] or row["expires_at"] <= now_iso():
            raise HTTPException(status_code=401, detail="Session invalide ou expirée. Reconnectez-vous.")
    actor = {"user_id": row["user_id"], "username": row["username"], "display_name": row["display_name"], "role": row["role"],
             "allowed_languages": json.loads(row["allowed_languages_json"] or "[]"), "assigned_regions": json.loads(row["assigned_regions_json"] or "[]"), "auth_type": "session"}
    request.state.actor = actor
    return actor

def require_admin(actor: dict = Depends(get_current_actor)) -> dict:
    if actor["role"] not in {"admin", "superadmin"}:
        raise HTTPException(status_code=403, detail="Permission réservée à l’administration système.")
    return actor

def require_roles(*roles: str):
    def dependency(actor: dict = Depends(get_current_actor)) -> dict:
        if actor["role"] in {"admin", "superadmin"}:
            return actor
        if actor["role"] not in roles:
            raise HTTPException(status_code=403, detail=f"Rôle insuffisant. Rôles autorisés : {', '.join(roles)}.")
        return actor
    return dependency

def require_permission(permission: str):
    def dependency(actor: dict = Depends(get_current_actor)) -> dict:
        perms = ROLE_PERMISSIONS.get(actor["role"], set())
        if "*" not in perms and permission not in perms:
            raise HTTPException(status_code=403, detail=f"Permission requise : {permission}.")
        return actor
    return dependency

def has_recognized_audio_signature(payload: bytes) -> bool:
    """Reject obvious non-audio uploads; this is a signature check, not a full decode."""
    if len(payload) < 12:
        return False
    if payload[:4] == b"RIFF" and payload[8:12] == b"WAVE":
        return True
    if payload[:4] == b"OggS":
        return True
    if payload[:4] == b"\x1aE\xdf\xa3":  # WebM / Matroska EBML header
        return True
    if payload[4:8] == b"ftyp":  # ISO BMFF (MP4 / M4A)
        return True
    if payload[:3] == b"ID3":  # MP3 with ID3 metadata
        return True
    # MPEG audio frame sync (with reserved sync bits excluded).
    if payload[0] == 0xFF and (payload[1] & 0xE0) == 0xE0:
        return True
    return False


def validate_audio_payload(payload: bytes, original_filename: str | None) -> float:
    """Decode uploaded audio with bounded, local-only FFmpeg tools and return actual duration."""
    ffmpeg = shutil_which("ffmpeg")
    ffprobe = shutil_which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise HTTPException(status_code=503, detail="Le serveur doit disposer de FFmpeg et ffprobe pour valider les fichiers audio.")

    suffix = Path(original_filename or "").suffix.lower()
    if suffix not in {".wav", ".wave", ".webm", ".ogg", ".oga", ".mp4", ".m4a", ".mp3", ".aac", ".flac"}:
        suffix = ".audio"
    try:
        with tempfile.TemporaryDirectory(prefix="voix-upload-") as tmp_dir:
            path = Path(tmp_dir) / f"input{suffix}"
            path.write_bytes(payload)
            probe = subprocess.run(
                [ffprobe, "-protocol_whitelist", "file,crypto,data", "-v", "error",
                 "-select_streams", "a:0", "-show_entries", "stream=codec_type,duration:format=duration",
                 "-of", "json", str(path)],
                capture_output=True, text=True, timeout=10,
            )
            if probe.returncode != 0:
                raise ValueError("conteneur audio illisible")
            metadata = json.loads(probe.stdout or "{}")
            if not metadata.get("streams"):
                raise ValueError("aucun flux audio détecté")
            duration_value = (metadata.get("format") or {}).get("duration")
            if duration_value in (None, "N/A"):
                duration_value = (metadata["streams"][0] or {}).get("duration")
            duration = float(duration_value)
            if not (0.05 <= duration <= 600):
                raise ValueError("durée audio hors limites (0,05–600 secondes)")
            decoded = subprocess.run(
                [ffmpeg, "-nostdin", "-protocol_whitelist", "file,crypto,data", "-v", "error", "-xerror",
                 "-threads", "1", "-i", str(path), "-map", "0:a:0", "-vn", "-sn", "-dn", "-f", "null", "-"],
                capture_output=True, text=True, timeout=30,
            )
            if decoded.returncode != 0:
                raise ValueError("décodage complet impossible")
            return duration
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=422, detail="La vérification audio a dépassé le délai autorisé.")
    except (ValueError, TypeError, KeyError, json.JSONDecodeError, OSError) as exc:
        raise HTTPException(status_code=415, detail="Le fichier ne contient pas un enregistrement audio complet et lisible.") from exc


def is_unverified_rights_label(value: str) -> bool:
    """Common rights placeholders must never be mistaken for verified terms."""
    normalized = " ".join((value or "").strip().casefold().split())
    return normalized in {"", "to_verify", "to verify", "tbd", "unknown", "unverified", "pending", "pending_rights_review", "rights_pending"}


def normalize_text_for_comparison(value: str) -> str:
    import unicodedata
    return " ".join(unicodedata.normalize("NFC", value).split())


def safe_extension(mime_type: str, filename: str | None) -> str:
    suffix = Path(filename or "").suffix.lower()
    known = {".wav", ".wave", ".webm", ".ogg", ".oga", ".mp4", ".m4a", ".mp3", ".aac", ".flac"}
    if suffix in known:
        return ".wav" if suffix == ".wave" else suffix
    if "webm" in mime_type:
        return ".webm"
    if "ogg" in mime_type:
        return ".ogg"
    if "mp4" in mime_type:
        return ".m4a"
    if "wav" in mime_type or "wave" in mime_type:
        return ".wav"
    if "mpeg" in mime_type or "mp3" in mime_type:
        return ".mp3"
    return ".audio"


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    return response


@app.get("/", response_class=HTMLResponse)
def home() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/admin", response_class=HTMLResponse)
def admin_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "admin.html")


@app.post("/api/auth/login")
def login(payload: dict, request: Request) -> dict:
    username = str(payload.get("username", "")).strip()[:120]
    password = str(payload.get("password", ""))
    if not username or not password:
        raise HTTPException(status_code=400, detail="Nom d’utilisateur et mot de passe obligatoires.")
    with db_conn() as conn:
        conn.execute("DELETE FROM auth_sessions WHERE expires_at < ? OR revoked_at IS NOT NULL", (now_iso(),))
        row = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        if not row or not row["active"] or not verify_password(password, row["password_hash"]):
            raise HTTPException(status_code=401, detail="Identifiants incorrects ou compte désactivé.")
        token = secrets.token_urlsafe(40)
        stamp = now_iso()
        expires = (datetime.now(timezone.utc) + timedelta(hours=max(1, min(SESSION_HOURS, 48)))).isoformat(timespec="seconds")
        conn.execute("INSERT INTO auth_sessions(token_hash,user_id,created_at,expires_at) VALUES(?,?,?,?)",
                     (hashlib.sha256(token.encode()).hexdigest(), row["user_id"], stamp, expires))
        conn.execute("UPDATE users SET last_login_at=? WHERE user_id=?", (stamp, row["user_id"]))
    actor = {"user_id": row["user_id"], "username": row["username"], "display_name": row["display_name"], "role": row["role"],
             "allowed_languages": json.loads(row["allowed_languages_json"] or "[]"), "assigned_regions": json.loads(row["assigned_regions_json"] or "[]"), "expires_at": expires}
    record_audit(actor, "login", "session", actor["user_id"])
    return {"ok": True, "access_token": token, "token_type": "bearer", "expires_at": expires, "user": actor, "permissions": sorted(ROLE_PERMISSIONS.get(actor["role"], set()))}

@app.post("/api/auth/logout")
def logout(actor: dict = Depends(get_current_actor), authorization: Annotated[str | None, Header()] = None) -> dict:
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
        with db_conn() as conn:
            conn.execute("UPDATE auth_sessions SET revoked_at=? WHERE token_hash=?", (now_iso(), hashlib.sha256(token.encode()).hexdigest()))
    record_audit(actor, "logout", "session", actor["user_id"])
    return {"ok": True}

@app.get("/api/auth/me")
def auth_me(actor: dict = Depends(get_current_actor)) -> dict:
    return {k: actor[k] for k in ("user_id", "username", "display_name", "role", "allowed_languages", "assigned_regions")}

@app.get("/api/languages")
def public_languages() -> dict:
    with db_conn() as conn:
        rows = conn.execute(
            "SELECT l.code,l.name_fr,l.iso_639_3,l.scope,l.collection_status,l.content_note,l.is_enabled, "
            "(SELECT COUNT(*) FROM phrases p WHERE p.language_code=l.code AND p.is_active=1) AS approved_phrase_count, "
            "(SELECT COUNT(*) FROM elicitation_prompts e WHERE e.language_code=l.code AND e.is_active=1) AS approved_prompt_count "
            "FROM language_catalog l WHERE l.is_enabled=1 ORDER BY CASE l.scope WHEN 'spoken' THEN 0 ELSE 1 END,l.name_fr"
        ).fetchall()
    return {"languages": [dict(r) for r in rows], "consent_version": CONSENT_VERSION, "note": "La présence au catalogue n’implique pas qu’un corpus validé soit déjà disponible. Les dialectes et règles d’orthographe doivent être documentés par langue."}

@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "service": "voix-du-niger-collection-platform", "version": "0.6.0"}


@app.get("/api/phrases")
def get_phrases(
    participant_code: str | None = Query(default=None, max_length=40),
    language_code: str = Query(default="dje", min_length=2, max_length=12),
) -> dict:
    """Return active phrases for one selected language and any requested retakes."""
    language_code = language_code.strip().lower()
    with db_conn() as conn:
        language_exists = conn.execute("SELECT 1 FROM language_catalog WHERE code=? AND is_enabled=1", (language_code,)).fetchone()
    if not language_exists:
        raise HTTPException(status_code=422, detail="Code langue inconnu ou désactivé.")
    code = (participant_code or "").strip().upper()
    redo_phrase_ids: list[str] = []
    if code and re.fullmatch(r"[A-Za-z0-9_-]{3,40}", code):
        with db_conn() as conn:
            rows = conn.execute(
                "SELECT phrase_id FROM recordings r "
                "WHERE r.participant_code=? AND r.status='redo' "
                "AND r.rowid=(SELECT MAX(r2.rowid) FROM recordings r2 "
                "WHERE r2.participant_code=r.participant_code AND r2.phrase_id=r.phrase_id)",
                (code,),
            ).fetchall()
            redo_phrase_ids = [row["phrase_id"] for row in rows]
    with db_conn() as conn:
        rows = conn.execute(
            "SELECT phrase_id, language_code, text_zarma, text_zarma AS text_prompt, category, orthography_version FROM phrases WHERE is_active=1 AND language_code=? ORDER BY created_at, phrase_id",
            (language_code,),
        ).fetchall()
    with db_conn() as conn:
        language_row = conn.execute("SELECT name_fr, collection_status FROM language_catalog WHERE code=?", (language_code,)).fetchone()
    selected_ids = {row["phrase_id"] for row in rows}
    return {
        "phrases": [dict(row) for row in rows],
        "redo_phrase_ids": [phrase_id for phrase_id in redo_phrase_ids if phrase_id in selected_ids],
        "consent_version": CONSENT_VERSION,
        "language_code": language_code,
        "language_name": language_row["name_fr"],
        "collection_status": language_row["collection_status"],
    }


@app.get("/api/elicitation-prompts")
def get_elicitation_prompts(language_code: str = Query(default="dje", min_length=2, max_length=12)) -> dict:
    """Expose active, human-reviewed prompts for any enabled spoken language in the national catalog."""
    language_code = language_code.strip().lower()
    with db_conn() as conn:
        language_exists = conn.execute(
            "SELECT 1 FROM language_catalog WHERE code=? AND is_enabled=1 AND scope='spoken'",
            (language_code,),
        ).fetchone()
        if not language_exists:
            raise HTTPException(status_code=422, detail="Code langue parlée inconnu ou désactivé.")
        rows = conn.execute(
            "SELECT elicitation_prompt_id, language_code, prompt_text, category, orthography_version "
            "FROM elicitation_prompts WHERE is_active=1 AND language_code=? ORDER BY category, created_at",
            (language_code,),
        ).fetchall()
    return {"prompts": [dict(row) for row in rows], "language_code": language_code}


@app.post("/api/recordings")
async def create_recording(
    participant_code: Annotated[str, Form()],
    consent: Annotated[str, Form()],
    consent_version: Annotated[str, Form()],
    file: UploadFile = File(...),
    phrase_id: Annotated[str | None, Form()] = None,
    elicitation_prompt_id: Annotated[str | None, Form()] = None,
    task_type: Annotated[str, Form()] = "read_speech",
    consent_asr: Annotated[str, Form()] = "false",
    consent_tts: Annotated[str, Form()] = "false",
    prompt_text: Annotated[str, Form()] = "",
    language_code: Annotated[str, Form()] = "dje",
    region_code: Annotated[str, Form()] = "UNK",
    dialect_code: Annotated[str, Form()] = "",
    duration_seconds: Annotated[str, Form()] = "",
) -> dict:
    code = participant_code.strip().upper()
    if not re.fullmatch(r"[A-Za-z0-9_-]{3,40}", code):
        raise HTTPException(status_code=422, detail="Le code participant doit faire 3 à 40 caractères (lettres, chiffres, - ou _).")
    if consent.lower() not in {"true", "1", "yes", "on"}:
        raise HTTPException(status_code=400, detail="Le consentement doit être confirmé avant l'envoi.")
    if consent_version != CONSENT_VERSION:
        raise HTTPException(status_code=400, detail="La version du consentement a changé. Rechargez la page et relisez le texte.")
    if task_type not in {"read_speech", "spontaneous_speech"}:
        raise HTTPException(status_code=422, detail="Type de collecte inconnu.")
    consent_asr_value = int(consent_asr.lower() in {"true", "1", "yes", "on"})
    consent_tts_value = int(consent_tts.lower() in {"true", "1", "yes", "on"})
    if task_type == "spontaneous_speech" and not consent_asr_value:
        raise HTTPException(status_code=400, detail="La parole spontanée nécessite une autorisation explicite pour l'usage ASR.")
    if task_type == "read_speech" and not (consent_asr_value or consent_tts_value):
        raise HTTPException(status_code=400, detail="Choisis explicitement au moins un usage autorisé : ASR et/ou TTS.")

    prompt_text = prompt_text.strip()[:1000]
    language_code = language_code.strip().lower()
    with db_conn() as conn:
        language_exists = conn.execute("SELECT 1 FROM language_catalog WHERE code=? AND is_enabled=1 AND scope='spoken'", (language_code,)).fetchone()
    if not language_exists:
        raise HTTPException(status_code=422, detail="Langue parlée inconnue, désactivée ou non collectable dans le catalogue.")
    region_code = region_code.strip().upper() or "UNK"
    if region_code not in REGION_CODES:
        raise HTTPException(status_code=422, detail="Code de région invalide.")
    dialect_code = dialect_code.strip()[:80]
    transcription_text = ""
    phrase = None
    if task_type == "read_speech":
        if not phrase_id:
            raise HTTPException(status_code=422, detail="Une phrase validée est obligatoire pour la lecture guidée.")
        with db_conn() as conn:
            phrase = conn.execute(
                "SELECT phrase_id, text_zarma FROM phrases WHERE phrase_id=? AND is_active=1",
                (phrase_id,),
            ).fetchone()
        if not phrase:
            raise HTTPException(status_code=404, detail="Phrase inconnue ou inactive.")
        prompt_text = phrase["text_zarma"]
        transcription_text = prompt_text
        with db_conn() as conn:
            language_row = conn.execute("SELECT language_code FROM phrases WHERE phrase_id=?", (phrase_id,)).fetchone()
        language_code = language_row["language_code"]
    else:
        if phrase_id:
            raise HTTPException(status_code=422, detail="La parole spontanée ne doit pas être liée à une phrase à lire.")
        if not elicitation_prompt_id:
            raise HTTPException(status_code=422, detail="Une consigne spontanée approuvée est obligatoire.")
        with db_conn() as conn:
            elicitation = conn.execute(
                "SELECT elicitation_prompt_id, language_code, prompt_text FROM elicitation_prompts "
                "WHERE elicitation_prompt_id=? AND is_active=1",
                (elicitation_prompt_id,),
            ).fetchone()
        if not elicitation:
            raise HTTPException(status_code=404, detail="Consigne spontanée inconnue ou inactive.")
        if elicitation["language_code"] != language_code:
            raise HTTPException(status_code=422, detail="La consigne ne correspond pas à la langue sélectionnée.")
        prompt_text = elicitation["prompt_text"]

    mime_type = (file.content_type or "application/octet-stream").lower()
    if not mime_type.startswith(ALLOWED_MIME_PREFIX):
        raise HTTPException(status_code=415, detail=f"Format audio non accepté : {mime_type}")

    payload = await file.read(MAX_UPLOAD_BYTES + 1)
    if not payload:
        raise HTTPException(status_code=400, detail="Le fichier audio est vide.")
    if len(payload) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Fichier trop volumineux (maximum 30 Mo).")
    if not has_recognized_audio_signature(payload):
        raise HTTPException(status_code=415, detail="Le contenu du fichier ne correspond pas à un format audio pris en charge.")

    # Never trust the browser-supplied duration; inspect and fully decode the actual payload.
    duration = validate_audio_payload(payload, file.filename)

    with db_conn() as conn:
        stamp = now_iso()
        conn.execute(
            "INSERT INTO participants(participant_code, consent_version, consent_at, created_at, region_code, dialect_code, participant_type) VALUES (?, ?, ?, ?, ?, ?, 'volunteer') "
            "ON CONFLICT(participant_code) DO UPDATE SET consent_version=excluded.consent_version, "
            "consent_at=CASE WHEN participants.consent_version != excluded.consent_version THEN excluded.consent_at ELSE participants.consent_at END, "
            "region_code=CASE WHEN excluded.region_code!='UNK' THEN excluded.region_code ELSE participants.region_code END, "
            "dialect_code=CASE WHEN excluded.dialect_code!='' THEN excluded.dialect_code ELSE participants.dialect_code END",
            (code, consent_version, stamp, stamp, region_code, dialect_code),
        )
        recording_id = str(uuid.uuid4())
        ext = safe_extension(mime_type, file.filename)
        stored_filename = f"{recording_id}{ext}"
        dest = AUDIO_DIR / stored_filename
        dest.write_bytes(payload)
        try:
            conn.execute(
                "INSERT INTO recordings(recording_id, participant_code, phrase_id, elicitation_prompt_id, task_type, language_code, consent_version, consent_at, consent_asr, consent_tts, prompt_text, transcription_text, "
                "stored_filename, original_filename, mime_type, duration_seconds, file_size_bytes, status, created_at, region_code, dialect_code) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending_review', ?, ?, ?)",
                (recording_id, code, phrase_id if task_type == "read_speech" else None,
                 elicitation_prompt_id if task_type == "spontaneous_speech" else None, task_type, language_code,
                 consent_version, stamp, consent_asr_value, consent_tts_value, prompt_text, transcription_text, stored_filename, (file.filename or "recording")[:255], mime_type, duration,
                 len(payload), stamp, region_code, dialect_code),
            )
        except Exception:
            dest.unlink(missing_ok=True)
            raise

    return {
        "ok": True,
        "recording_id": recording_id,
        "task_type": task_type,
        "status": "pending_review",
        "message": "Enregistrement reçu. Il sera vérifié avant d'être ajouté au corpus.",
    }


@app.post("/api/admin/import-phrases", dependencies=[Depends(require_roles("language_lead", "dataset_manager"))])
async def import_phrases(file: UploadFile = File(...), actor: dict = Depends(require_roles("language_lead", "dataset_manager"))) -> dict:
    raw = await file.read(MAX_CSV_BYTES + 1)
    if len(raw) > MAX_CSV_BYTES:
        raise HTTPException(status_code=413, detail="CSV trop volumineux (maximum 2 Mo).")
    try:
        decoded = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="Le CSV doit être encodé en UTF-8.")
    reader = csv.DictReader(io.StringIO(decoded))
    fieldnames = set(reader.fieldnames or [])
    text_column = "text_prompt" if "text_prompt" in fieldnames else "text_zarma" if "text_zarma" in fieldnames else None
    required_phrase_columns = {"native_review_status"}
    missing_columns = required_phrase_columns - fieldnames
    if text_column is None:
        missing_columns.add("text_prompt (or legacy text_zarma)")
    if missing_columns:
        raise HTTPException(
            status_code=400,
            detail="Colonnes requises absentes : " + ", ".join(sorted(missing_columns)) + ". "
                   "Chaque phrase doit porter native_review_status=APPROVED après vérification par un locuteur compétent.",
        )
    requires_native_approval = True

    added = 0
    skipped = 0
    problems = []
    with db_conn() as conn:
        for line_number, row in enumerate(reader, start=2):
            text_zarma = (row.get(text_column) or "").strip()
            if requires_native_approval and (row.get("native_review_status") or "").strip().upper() != "APPROVED":
                skipped += 1
                if len(problems) < 10:
                    problems.append(f"Ligne {line_number} : phrase ignorée ; native_review_status doit être APPROVED après validation humaine.")
                continue
            if not text_zarma:
                skipped += 1
                if len(problems) < 10:
                    problems.append(f"Ligne {line_number} : texte vide, ignoré.")
                continue
            if len(text_zarma) > 2000:
                skipped += 1
                if len(problems) < 10:
                    problems.append(f"Ligne {line_number} : texte de plus de 2 000 caractères, ignoré.")
                continue
            language_code = (row.get("language_code") or "dje").strip().lower()
            with db_conn() as lang_conn:
                language_exists = lang_conn.execute("SELECT 1 FROM language_catalog WHERE code=? AND is_enabled=1 AND scope='spoken'", (language_code,)).fetchone()
            if not language_exists:
                skipped += 1
                if len(problems) < 10:
                    problems.append(f"Ligne {line_number} : code langue non reconnu/non activé pour une langue parlée : {language_code}.")
                continue
            if not language_is_allowed(actor, language_code):
                raise HTTPException(status_code=403, detail=f"Import refusé : la langue {language_code} est hors du périmètre autorisé du compte. Aucun changement du fichier ne sera conservé.")
            category = (row.get("category") or "general").strip()[:100]
            orthography = (row.get("orthography_version") or "v1").strip()[:100] or "v1"
            source = (row.get("source") or "").strip()[:1000]
            source_license = (row.get("source_license") or row.get("license") or "").strip()[:500]
            gloss_fr = (row.get("gloss_fr") or "").strip()[:2000]
            native_reviewed_by = (row.get("native_reviewed_by") or "").strip()[:200]
            native_reviewed_at = (row.get("native_reviewed_at") or "").strip()[:100]
            if not source or is_unverified_rights_label(source_license) or not native_reviewed_by or not native_reviewed_at:
                skipped += 1
                if len(problems) < 10:
                    problems.append(f"Ligne {line_number} : source, licence/conditions vérifiées, réviseur natif et date de validation sont requis ; les marqueurs temporaires comme TO_VERIFY sont refusés.")
                continue
            try:
                conn.execute(
                    "INSERT INTO phrases(phrase_id, language_code, text_zarma, category, orthography_version, source, source_license, gloss_fr, native_reviewed_by, native_reviewed_at, is_active, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)",
                    (str(uuid.uuid4()), language_code, text_zarma, category, orthography, source, source_license,
                     gloss_fr, native_reviewed_by, native_reviewed_at, now_iso()),
                )
                added += 1
            except sqlite3.IntegrityError:
                skipped += 1
                if len(problems) < 10:
                    problems.append(f"Ligne {line_number} : doublon (même texte et version d'orthographe), ignoré.")
    record_audit(actor, "import_phrases", "phrase_catalog", "", {"added": added, "skipped": skipped})
    return {"ok": True, "added": added, "skipped": skipped, "problems": problems}


@app.post("/api/admin/import-elicitation-prompts", dependencies=[Depends(require_roles("language_lead", "dataset_manager"))])
async def import_elicitation_prompts(file: UploadFile = File(...), actor: dict = Depends(require_roles("language_lead", "dataset_manager"))) -> dict:
    raw = await file.read(MAX_CSV_BYTES + 1)
    if len(raw) > MAX_CSV_BYTES:
        raise HTTPException(status_code=413, detail="CSV trop volumineux (maximum 2 Mo).")
    try:
        decoded = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="Le CSV doit être encodé en UTF-8.")
    reader = csv.DictReader(io.StringIO(decoded))
    fields = set(reader.fieldnames or [])
    required = {"language_code", "prompt_text", "category", "orthography_version", "native_review_status"}
    missing = required - fields
    if missing:
        raise HTTPException(status_code=400, detail="Colonnes requises absentes : " + ", ".join(sorted(missing)))
    added = skipped = 0
    problems: list[str] = []
    with db_conn() as conn:
        for line_number, row in enumerate(reader, start=2):
            language_code = (row.get("language_code") or "").strip().lower()
            prompt_text = (row.get("prompt_text") or "").strip()
            status = (row.get("native_review_status") or "").strip().upper()
            if status != "APPROVED":
                skipped += 1
                if len(problems) < 10:
                    problems.append(f"Ligne {line_number} ignorée : la consigne doit être validée par un locuteur compétent.")
                continue
            with db_conn() as lang_conn:
                language_exists = lang_conn.execute("SELECT 1 FROM language_catalog WHERE code=? AND is_enabled=1 AND scope='spoken'", (language_code,)).fetchone()
            if not language_exists or not prompt_text or len(prompt_text) > 1000:
                skipped += 1
                if len(problems) < 10:
                    problems.append(f"Ligne {line_number} ignorée : langue ou texte invalide.")
                continue
            if not language_is_allowed(actor, language_code):
                raise HTTPException(status_code=403, detail=f"Import refusé : la langue {language_code} est hors du périmètre autorisé du compte. Aucun changement du fichier ne sera conservé.")
            category = (row.get("category") or "general").strip()[:100]
            orthography = (row.get("orthography_version") or "v1").strip()[:100] or "v1"
            source = (row.get("source") or "").strip()[:1000]
            source_license = (row.get("source_license") or row.get("license") or "").strip()[:500]
            reviewer = (row.get("native_reviewed_by") or "").strip()[:200]
            reviewed_at = (row.get("native_reviewed_at") or "").strip()[:100]
            if not source or is_unverified_rights_label(source_license) or not reviewer or not reviewed_at:
                skipped += 1
                if len(problems) < 10:
                    problems.append(f"Ligne {line_number} ignorée : source, licence/conditions vérifiées, réviseur natif et date de validation sont requis ; les marqueurs temporaires comme TO_VERIFY sont refusés.")
                continue
            try:
                conn.execute(
                    "INSERT INTO elicitation_prompts(elicitation_prompt_id, language_code, prompt_text, category, orthography_version, source, source_license, native_reviewed_by, native_reviewed_at, is_active, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)",
                    (str(uuid.uuid4()), language_code, prompt_text, category, orthography, source, source_license, reviewer, reviewed_at, now_iso()),
                )
                added += 1
            except sqlite3.IntegrityError:
                skipped += 1
                if len(problems) < 10:
                    problems.append(f"Ligne {line_number} ignorée : doublon de consigne dans cette langue et version d'orthographe.")
    record_audit(actor, "import_elicitation_prompts", "elicitation_catalog", "", {"added": added, "skipped": skipped})
    return {"ok": True, "added": added, "skipped": skipped, "problems": problems}


@app.get("/api/admin/stats", dependencies=[Depends(require_roles("transcriber", "reviewer", "validator", "language_lead", "dataset_manager", "training_operator", "provider_manager", "privacy_officer"))])
def admin_stats(actor: dict = Depends(require_roles("transcriber", "reviewer", "validator", "language_lead", "dataset_manager", "training_operator", "provider_manager", "privacy_officer"))) -> dict:
    """Return counters limited to the authenticated team member's assignment scope."""
    is_admin = actor.get("role") in {"admin", "superadmin"}
    allowed_languages = actor.get("allowed_languages") or []
    allowed_regions = actor.get("assigned_regions") or []
    with db_conn() as conn:
        phrase_count = conn.execute("SELECT COUNT(*) AS n FROM phrases WHERE is_active=1").fetchone()["n"]
        elicitation_count = conn.execute("SELECT COUNT(*) AS n FROM elicitation_prompts WHERE is_active=1").fetchone()["n"]
        if not is_admin:
            if allowed_languages:
                marks = ",".join("?" for _ in allowed_languages)
                phrase_count = conn.execute(f"SELECT COUNT(*) n FROM phrases WHERE is_active=1 AND language_code IN ({marks})", allowed_languages).fetchone()["n"]
                elicitation_count = conn.execute(f"SELECT COUNT(*) n FROM elicitation_prompts WHERE is_active=1 AND language_code IN ({marks})", allowed_languages).fetchone()["n"]
            else:
                phrase_count = elicitation_count = 0

        filters: list[str] = []
        params: list[str] = []
        if not is_admin and (not allowed_languages or not allowed_regions):
            filters.append("1=0")
        elif not is_admin:
            filters.append("language_code IN (" + ",".join("?" for _ in allowed_languages) + ")")
            params.extend(allowed_languages)
            filters.append("region_code IN (" + ",".join("?" for _ in allowed_regions) + ")")
            params.extend(allowed_regions)
        where = (" WHERE " + " AND ".join(filters)) if filters else ""
        participant_count = conn.execute("SELECT COUNT(DISTINCT participant_code) n FROM recordings" + where, params).fetchone()["n"]
        rows = conn.execute("SELECT status, COUNT(*) AS n FROM recordings" + where + " GROUP BY status", params).fetchall()
        task_rows = conn.execute(
            "SELECT task_type, COUNT(*) AS n, "
            "SUM(CASE WHEN status='approved' AND consent_asr=1 AND asr_approved=1 THEN 1 ELSE 0 END) AS asr_n, "
            "SUM(CASE WHEN status='approved' AND consent_tts=1 AND tts_approved=1 THEN 1 ELSE 0 END) AS tts_n "
            "FROM recordings" + where + " GROUP BY task_type", params
        ).fetchall()
    counts = {row["status"]: row["n"] for row in rows}
    for state in ("pending_review", "approved", "redo", "rejected"):
        counts.setdefault(state, 0)
    by_task = {row["task_type"]: {"recordings": row["n"], "approved_for_asr": row["asr_n"] or 0, "approved_for_tts": row["tts_n"] or 0} for row in task_rows}
    return {"phrases": phrase_count, "elicitation_prompts": elicitation_count, "participants": participant_count,
            "recordings": sum(counts.values()), "statuses": counts, "by_task": by_task}


@app.get("/api/admin/recordings", dependencies=[Depends(require_roles("transcriber", "reviewer", "validator", "language_lead", "dataset_manager"))])
def admin_recordings(
    status: str = Query(default="pending_review"),
    task_type: str = Query(default="all"),
    limit: int = Query(default=100, ge=1, le=250),
    actor: dict = Depends(require_roles("transcriber", "reviewer", "validator", "language_lead", "dataset_manager")),
) -> dict:
    valid_statuses = {"pending_review", "approved", "redo", "rejected", "all"}
    valid_tasks = {"read_speech", "spontaneous_speech", "all"}
    if status not in valid_statuses:
        raise HTTPException(status_code=422, detail="Statut invalide.")
    if task_type not in valid_tasks:
        raise HTTPException(status_code=422, detail="Type de collecte invalide.")
    with db_conn() as conn:
        sql = (
            "SELECT r.recording_id, r.participant_code, r.phrase_id, r.elicitation_prompt_id, r.task_type, r.language_code, "
            "r.prompt_text, r.transcription_text, r.consent_asr, r.consent_tts, r.asr_approved, r.tts_approved, "
            "COALESCE(p.text_zarma, '') AS text_zarma, COALESCE(p.category, ep.category, '') AS category, "
            "COALESCE(p.orthography_version, ep.orthography_version, '') AS orthography_version, "
            "COALESCE(p.source, ep.source, '') AS source, COALESCE(p.source_license, ep.source_license, '') AS source_license, "
            "COALESCE(p.gloss_fr, '') AS gloss_fr, "
            "COALESCE(p.native_reviewed_by, ep.native_reviewed_by, '') AS native_reviewed_by, "
            "COALESCE(p.native_reviewed_at, ep.native_reviewed_at, '') AS native_reviewed_at, "
            "r.mime_type, r.duration_seconds, r.file_size_bytes, r.status, r.created_at, r.reviewed_at, r.reviewer_note, r.region_code, r.dialect_code "
            "FROM recordings r LEFT JOIN phrases p ON p.phrase_id=r.phrase_id "
            "LEFT JOIN elicitation_prompts ep ON ep.elicitation_prompt_id=r.elicitation_prompt_id WHERE 1=1 "
        )
        params: list = []
        if status != "all":
            sql += "AND r.status=? "
            params.append(status)
        if task_type != "all":
            sql += "AND r.task_type=? "
            params.append(task_type)
        allowed_languages = actor.get("allowed_languages") or []
        allowed_regions = actor.get("assigned_regions") or []
        if actor.get("role") not in {"admin", "superadmin"}:
            if not allowed_languages or not allowed_regions:
                sql += "AND 1=0 "
            else:
                sql += "AND r.language_code IN (" + ",".join("?" for _ in allowed_languages) + ") "
                params.extend(allowed_languages)
                sql += "AND r.region_code IN (" + ",".join("?" for _ in allowed_regions) + ") "
                params.extend(allowed_regions)
        sql += "ORDER BY r.created_at DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
    return {"recordings": [dict(row) for row in rows]}


@app.get("/api/admin/recordings/{recording_id}/audio", dependencies=[Depends(require_roles("transcriber", "reviewer", "validator", "language_lead"))])
def admin_recording_audio(recording_id: str, actor: dict = Depends(require_roles("transcriber", "reviewer", "validator", "language_lead"))) -> FileResponse:
    with db_conn() as conn:
        row = conn.execute("SELECT stored_filename, mime_type, language_code, region_code FROM recordings WHERE recording_id=?", (recording_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Enregistrement introuvable.")
    if not language_is_allowed(actor, row["language_code"]) or not region_is_allowed(actor, row["region_code"]):
        raise HTTPException(status_code=403, detail="Cette contribution est hors de votre périmètre de revue.")
    path = AUDIO_DIR / row["stored_filename"]
    if not path.is_file():
        raise HTTPException(status_code=410, detail="Fichier audio manquant sur le serveur.")
    return FileResponse(path, media_type=row["mime_type"], filename=row["stored_filename"])


@app.post("/api/admin/recordings/{recording_id}/review", dependencies=[Depends(require_roles("transcriber", "reviewer", "validator", "language_lead"))])
def review_recording(recording_id: str, payload: dict, actor: dict = Depends(require_roles("transcriber", "reviewer", "validator", "language_lead"))) -> dict:
    decision = str(payload.get("decision", ""))
    note = str(payload.get("note", "")).strip()[:2000]
    reviewer_label = str(payload.get("reviewer_label", "")).strip()[:120]
    submitted_transcript = str(payload.get("transcription_text", "")).strip()[:10000]
    allowed_decisions = {"approved", "approve_asr", "approve_tts", "approve_both", "save_transcript", "redo", "rejected"}
    if decision not in allowed_decisions:
        raise HTTPException(status_code=422, detail="Décision invalide.")
    if decision in {"redo", "rejected"} and not note:
        raise HTTPException(status_code=400, detail="Ajoutez un commentaire pour demander une reprise ou rejeter le fichier.")

    with db_conn() as conn:
        row = conn.execute(
            "SELECT recording_id, task_type, language_code, region_code, prompt_text, transcription_text, status, consent_asr, consent_tts, asr_approved, tts_approved "
            "FROM recordings WHERE recording_id=?", (recording_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Enregistrement introuvable.")

        if not language_is_allowed(actor, row["language_code"]) or not region_is_allowed(actor, row["region_code"]):
            raise HTTPException(status_code=403, detail="Cette contribution est hors du périmètre de langues/régions attribué à votre compte.")
        role = actor.get("role", "")
        transcript = submitted_transcript if "transcription_text" in payload else row["transcription_text"]
        # Resolve the legacy generic decision BEFORE permission checks. Otherwise a reviewer
        # could submit "approved" and be silently upgraded to TTS/both approval.
        if decision == "approved":
            if row["consent_asr"] and row["consent_tts"] and row["task_type"] == "read_speech":
                decision = "approve_both"
            elif row["consent_asr"]:
                decision = "approve_asr"
            elif row["consent_tts"] and row["task_type"] == "read_speech":
                decision = "approve_tts"
            else:
                raise HTTPException(status_code=403, detail="Aucun usage d'entraînement applicable n'a été autorisé.")

        if role == "transcriber" and decision != "save_transcript":
            raise HTTPException(status_code=403, detail="Le rôle transcriber peut uniquement enregistrer une transcription à faire vérifier.")
        if decision in {"approve_asr", "approve_both"} and role not in {"reviewer", "validator", "language_lead", "admin", "superadmin"}:
            raise HTTPException(status_code=403, detail="Validation ASR réservée aux reviewers/validators habilités.")
        if decision in {"approve_tts", "approve_both"} and role not in {"validator", "admin", "superadmin"}:
            raise HTTPException(status_code=403, detail="Validation TTS réservée au rôle validator ou admin.")
        if decision in {"approve_asr", "approve_both", "save_transcript"} and not transcript:
            raise HTTPException(status_code=400, detail="Une transcription vérifiée est obligatoire pour cette décision.")
        if decision in {"approve_asr", "approve_both"} and not row["consent_asr"]:
            raise HTTPException(status_code=403, detail="Aucune autorisation ASR n'a été enregistrée pour cette contribution.")
        if decision in {"approve_tts", "approve_both"} and not row["consent_tts"]:
            raise HTTPException(status_code=403, detail="Aucune autorisation TTS n'a été enregistrée pour cette contribution.")
        if decision in {"approve_tts", "approve_both"}:
            if row["task_type"] != "read_speech":
                if decision in {"approve_tts", "approve_both"}:
                    raise HTTPException(status_code=422, detail="La parole spontanée n'est pas éligible au TTS dans ce protocole.")
                decision = "approve_asr"
            else:
                if normalize_text_for_comparison(transcript) != normalize_text_for_comparison(row["prompt_text"]):
                    raise HTTPException(status_code=422, detail="Pour le TTS, la transcription doit correspondre exactement au texte de la phrase validée. Corrige le texte ou valide uniquement pour l'ASR.")

        stamp = now_iso()
        asr_approved = int(row["asr_approved"] or 0)
        tts_approved = int(row["tts_approved"] or 0)
        transcript_changed = transcript != row["transcription_text"]
        if transcript_changed:
            # Any changed annotation invalidates previous task approvals. The current decision below may re-approve it.
            asr_approved = 0
            tts_approved = 0
        new_status = row["status"]
        if decision == "save_transcript":
            new_status = "pending_review" if transcript_changed or row["status"] not in {"redo", "rejected"} else row["status"]
        elif decision == "approve_asr":
            asr_approved = 1
            new_status = "approved"
        elif decision == "approve_tts":
            tts_approved = 1
            new_status = "approved"
        elif decision == "approve_both":
            asr_approved = 1
            tts_approved = 1
            new_status = "approved"
        elif decision == "redo":
            asr_approved = 0
            tts_approved = 0
            new_status = "redo"
        elif decision == "rejected":
            asr_approved = 0
            tts_approved = 0
            new_status = "rejected"

        conn.execute(
            "UPDATE recordings SET status=?, transcription_text=?, asr_approved=?, tts_approved=?, reviewed_at=?, reviewer_note=? WHERE recording_id=?",
            (new_status, transcript, asr_approved, tts_approved, stamp, note, recording_id),
        )
        conn.execute(
            "INSERT INTO review_events(event_id, recording_id, decision, reviewer_label, transcription_snapshot, note, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), recording_id, decision, reviewer_label, transcript, note, stamp),
        )
    return {
        "ok": True,
        "recording_id": recording_id,
        "status": new_status,
        "asr_approved": bool(asr_approved),
        "tts_approved": bool(tts_approved),
        "decision": decision,
    }


@app.get("/api/admin/recordings/{recording_id}/history", dependencies=[Depends(require_roles("transcriber", "reviewer", "validator", "language_lead"))])
def recording_review_history(recording_id: str, actor: dict = Depends(require_roles("transcriber", "reviewer", "validator", "language_lead"))) -> dict:
    with db_conn() as conn:
        exists = conn.execute("SELECT language_code,region_code FROM recordings WHERE recording_id=?", (recording_id,)).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail="Enregistrement introuvable.")
        if not language_is_allowed(actor, exists["language_code"]) or not region_is_allowed(actor, exists["region_code"]):
            raise HTTPException(status_code=403, detail="Cette contribution est hors de votre périmètre de revue.")
        rows = conn.execute(
            "SELECT decision, reviewer_label, transcription_snapshot, note, created_at FROM review_events "
            "WHERE recording_id=? ORDER BY created_at", (recording_id,)
        ).fetchall()
    return {"events": [dict(row) for row in rows]}


@app.delete("/api/admin/participants/{participant_code}", dependencies=[Depends(require_roles("privacy_officer"))])
def delete_participant_data(participant_code: str, payload: dict, actor: dict = Depends(require_roles("privacy_officer"))) -> dict:
    """Erase one participant's active data; keep only a non-identifying audit record."""
    code = participant_code.strip().upper()
    if not re.fullmatch(r"[A-Za-z0-9_-]{3,40}", code):
        raise HTTPException(status_code=422, detail="Code participant invalide.")
    handled_by = str(payload.get("handled_by", "")).strip()[:120]
    reason = str(payload.get("reason", "")).strip()
    allowed_reasons = {"participant_withdrawal", "duplicate_or_wrong_code", "data_subject_request"}
    if not handled_by:
        raise HTTPException(status_code=400, detail="Indique le code pseudonyme du responsable ayant traité la demande.")
    if reason not in allowed_reasons:
        raise HTTPException(status_code=422, detail="Motif invalide. Utilise participant_withdrawal, duplicate_or_wrong_code ou data_subject_request.")

    request_ref = str(uuid.uuid4())
    staged: list[tuple[Path, Path]] = []
    recording_count = 0
    try:
        with db_conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            participant = conn.execute("SELECT participant_code,region_code FROM participants WHERE participant_code=?", (code,)).fetchone()
            rows = conn.execute(
                "SELECT recording_id, stored_filename, language_code, region_code FROM recordings WHERE participant_code=?", (code,)
            ).fetchall()
            if not participant and not rows:
                raise HTTPException(status_code=404, detail="Code participant introuvable.")
            if actor.get("role") not in {"admin", "superadmin"}:
                participant_region = participant["region_code"] if participant else (rows[0]["region_code"] if rows else "UNK")
                if not region_is_allowed(actor, participant_region):
                    raise HTTPException(status_code=403, detail="Ce participant est hors du périmètre régional de ce privacy officer.")
                if any(not language_is_allowed(actor, r["language_code"]) or not region_is_allowed(actor, r["region_code"]) for r in rows):
                    raise HTTPException(status_code=403, detail="Le participant possède des données hors du périmètre autorisé ; demande une intervention nationale.")
            recording_count = len(rows)
            originals: list[Path] = []
            for row in rows:
                original = (AUDIO_DIR / row["stored_filename"]).resolve()
                if original.parent != AUDIO_DIR.resolve():
                    raise HTTPException(status_code=500, detail="Un chemin audio inattendu bloque la suppression ; contacte la personne responsable technique.")
                if original.exists() and not original.is_file():
                    raise HTTPException(status_code=500, detail="Un chemin audio inattendu bloque la suppression.")
                if original.is_file():
                    originals.append(original)
            # Stage files before changing database rows. If this transaction or commit fails,
            # the outer exception handler attempts to restore every staged file.
            for original in originals:
                quarantine = AUDIO_DIR / f".withdraw-{uuid.uuid4().hex}{original.suffix}"
                original.replace(quarantine)
                staged.append((quarantine, original))
            recording_ids = [row["recording_id"] for row in rows]
            for recording_id in recording_ids:
                conn.execute("DELETE FROM review_events WHERE recording_id=?", (recording_id,))
            conn.execute("DELETE FROM recordings WHERE participant_code=?", (code,))
            conn.execute("DELETE FROM participants WHERE participant_code=?", (code,))
            conn.execute(
                "INSERT INTO deletion_events(event_id, request_ref, reason, handled_by, recordings_deleted, audio_files_deleted, cleanup_pending, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), request_ref, reason, handled_by, recording_count, 0, len(staged), now_iso()),
            )
    except Exception:
        for quarantine, original in reversed(staged):
            if quarantine.exists() and not original.exists():
                try:
                    quarantine.replace(original)
                except OSError:
                    # If storage prevents restoration, keep the unindexed quarantine file inaccessible
                    # through normal recording routes and let operations staff investigate the disk.
                    pass
        raise

    # Database commit succeeded; now permanently remove quarantined audio files and update the audit.
    deleted = 0
    pending = 0
    for quarantine, _original in staged:
        try:
            quarantine.unlink(missing_ok=True)
            deleted += 1
        except OSError:
            pending += 1
    with db_conn() as conn:
        conn.execute(
            "UPDATE deletion_events SET audio_files_deleted=?, cleanup_pending=? WHERE request_ref=?",
            (deleted, pending, request_ref),
        )
    return {
        "ok": True,
        "request_ref": request_ref,
        "recordings_deleted": recording_count,
        "audio_files_deleted": deleted,
        "cleanup_pending": pending,
        "message": "Données retirées du stockage actif. Vérifie aussi les sauvegardes, archives exportées et copies déjà partagées.",
    }


@app.get("/api/admin/deletion-events", dependencies=[Depends(require_roles("privacy_officer"))])
def get_deletion_events(limit: int = Query(default=50, ge=1, le=200)) -> dict:
    """Audit deletion operations without retaining participant codes."""
    with db_conn() as conn:
        rows = conn.execute(
            "SELECT request_ref, reason, handled_by, recordings_deleted, audio_files_deleted, cleanup_pending, created_at "
            "FROM deletion_events ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return {"events": [dict(row) for row in rows]}


@app.get("/api/admin/export", dependencies=[Depends(require_roles("dataset_manager", "training_operator"))])
def export_approved(task: str = Query(default="all", pattern="^(all|asr|tts)$"), language_code: str | None = Query(default=None, min_length=2, max_length=12), region_code: str = Query(default="ALL", min_length=2, max_length=12), actor: dict = Depends(require_roles("dataset_manager", "training_operator"))) -> Response:
    """Export task-specific reviewed data; task=all is retained for compatibility."""
    is_admin = actor.get("role") in {"admin", "superadmin"}
    if region_code != "ALL" and region_code not in REGION_CODES:
        raise HTTPException(status_code=422, detail="Code région inconnu.")
    if not is_admin and (not actor.get("allowed_languages") or not actor.get("assigned_regions")):
        raise HTTPException(status_code=403, detail="Export refusé : le compte doit avoir un périmètre langue et région explicite.")
    if not is_admin and (region_code == "ALL" or not region_is_allowed(actor, region_code)):
        raise HTTPException(status_code=403, detail="Export national interdit pour ce rôle ; sélectionne une région attribuée.")
    if language_code and not language_is_allowed(actor, language_code):
        raise HTTPException(status_code=403, detail="Cette langue est hors du périmètre attribué à votre compte.")
    if not is_admin and region_code == "ALL":
        raise HTTPException(status_code=403, detail="Un export national est réservé à l’administration.")
    if not shutil_which("ffmpeg"):
        raise HTTPException(status_code=500, detail="FFmpeg n'est pas installé sur le serveur. Installez FFmpeg puis relancez l'export.")
    task_filter = {
        "asr": "r.status='approved' AND r.consent_asr=1 AND r.asr_approved=1 AND TRIM(r.transcription_text) != ''",
        "tts": "r.status='approved' AND r.consent_tts=1 AND r.tts_approved=1 AND r.task_type='read_speech'",
        "all": "r.status='approved' AND (r.consent_asr=1 OR r.consent_tts=1)",
    }[task]
    with db_conn() as conn:
        rows = conn.execute(
            "SELECT r.recording_id, r.participant_code, r.phrase_id, r.elicitation_prompt_id, r.task_type, r.language_code, r.prompt_text, "
            "r.transcription_text, r.asr_approved, r.tts_approved, r.consent_asr, r.consent_tts, r.consent_version, r.stored_filename, r.duration_seconds, r.created_at, "
            "COALESCE(p.text_zarma, '') AS phrase_text, COALESCE(p.category, ep.category, 'spontaneous') AS category, "
            "COALESCE(p.orthography_version, ep.orthography_version, '') AS orthography_version, "
            "COALESCE(p.source, ep.source, '') AS source, COALESCE(p.source_license, ep.source_license, '') AS source_license, "
            "COALESCE(p.gloss_fr, '') AS gloss_fr, "
            "COALESCE(p.native_reviewed_by, ep.native_reviewed_by, '') AS native_reviewed_by, "
            "COALESCE(p.native_reviewed_at, ep.native_reviewed_at, '') AS native_reviewed_at, r.mime_type "
            f"FROM recordings r LEFT JOIN phrases p ON p.phrase_id=r.phrase_id "
            f"LEFT JOIN elicitation_prompts ep ON ep.elicitation_prompt_id=r.elicitation_prompt_id "
            f"WHERE {task_filter} " + ("AND r.language_code=? " if language_code else "") +
            ("AND r.language_code IN (" + ",".join("?" for _ in (actor.get("allowed_languages") or [])) + ") " if not is_admin and not language_code else "") +
            ("AND r.region_code=? " if region_code != "ALL" else "") +
            ("AND r.region_code IN (" + ",".join("?" for _ in (actor.get("assigned_regions") or [])) + ") " if not is_admin else "") + "ORDER BY r.created_at",
            (([language_code] if language_code else []) + ((actor.get("allowed_languages") or []) if not is_admin and not language_code else []) + ([region_code] if region_code != "ALL" else []) + ((actor.get("assigned_regions") or []) if not is_admin else [])),
        ).fetchall()
    if not rows:
        raise HTTPException(status_code=400, detail=f"Aucun enregistrement approuvé pour l'export {task.upper()}.")

    buffer = io.BytesIO()
    with tempfile.TemporaryDirectory(prefix="voix-export-") as tmp_dir:
        tmp = Path(tmp_dir)
        out_rows = []
        wav_items = []
        for row in rows:
            src = AUDIO_DIR / row["stored_filename"]
            if not src.is_file():
                raise HTTPException(status_code=500, detail=f"Fichier source manquant pour {row['recording_id']}.")
            relative = f"audio/{row['recording_id']}.wav"
            dest = tmp / f"{row['recording_id']}.wav"
            cmd = [
                "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-i", str(src),
                "-vn", "-ac", "1", "-ar", str(EXPORT_SAMPLE_RATE), "-sample_fmt", "s16", str(dest),
            ]
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            except subprocess.TimeoutExpired:
                raise HTTPException(status_code=422, detail=f"La conversion audio a dépassé le délai pour {row['recording_id']}.")
            if result.returncode != 0 or not dest.exists() or dest.stat().st_size == 0:
                msg = (result.stderr or "Conversion audio impossible.").strip()[-500:]
                raise HTTPException(status_code=422, detail=f"Conversion impossible pour {row['recording_id']} : {msg}")
            out_rows.append({
                "recording_id": row["recording_id"],
                "task_type": row["task_type"],
                "phrase_id": row["phrase_id"] or "",
                "elicitation_prompt_id": row["elicitation_prompt_id"] or "",
                "audio_filename": relative,
                "text": row["transcription_text"],
                "prompt_text": row["prompt_text"],
                "language_code": row["language_code"],
                "participant_code": row["participant_code"],
                "category": row["category"],
                "orthography_version": row["orthography_version"],
                "source": row["source"],
                "source_license": row["source_license"],
                "gloss_fr": row["gloss_fr"],
                "native_reviewed_by": row["native_reviewed_by"],
                "native_reviewed_at": row["native_reviewed_at"],
                "asr_approved": row["asr_approved"],
                "tts_approved": row["tts_approved"],
                "consent_asr": row["consent_asr"],
                "consent_tts": row["consent_tts"],
                "consent_version": row["consent_version"],
                "duration_seconds_reported_by_browser": row["duration_seconds"],
                "recorded_at": row["created_at"],
            })
            wav_items.append((relative, dest))

        metadata = io.StringIO(newline="")
        writer = csv.DictWriter(metadata, fieldnames=list(out_rows[0].keys()))
        writer.writeheader()
        writer.writerows(out_rows)
        readme = (
            "Voix du Niger: versioned review-based speech corpus export\n"
            f"Task: {task.upper()}\nRecordings: {len(out_rows)}\n"
            f"Audio: WAV, mono, PCM signed 16-bit, {EXPORT_SAMPLE_RATE} Hz\n"
            "This package contains only recordings approved for the selected task, except task=all which is a compatibility export.\n"
            "Verify consent, licensing, transcript quality, speaker-disjoint splits and dataset documentation before training or redistribution.\n"
        )
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("metadata.csv", metadata.getvalue().encode("utf-8-sig"))
            zf.writestr("README-export.txt", readme)
            for relative, wav_path in wav_items:
                zf.write(wav_path, relative)

    buffer.seek(0)
    language_suffix = f"-{language_code}" if language_code else "-multilingual"
    filename = f"voix-du-niger-{task}{language_suffix}-approved-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.zip"
    return StreamingResponse(buffer, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


def shutil_which(program: str) -> str | None:
    # Keep imports lean while using the standard library.
    import shutil
    return shutil.which(program)


@app.get("/api/admin/dashboard")
def admin_dashboard(actor: dict = Depends(require_roles("transcriber", "reviewer", "validator", "language_lead", "dataset_manager", "training_operator", "provider_manager", "privacy_officer"))) -> dict:
    """National overview for admins; team accounts only see assigned language/region scope."""
    is_admin = actor.get("role") in {"admin", "superadmin"}
    languages = actor.get("allowed_languages") or []
    regions = actor.get("assigned_regions") or []
    join_conditions = ["r.language_code=l.code"]
    join_params: list[str] = []
    if not is_admin and (not languages or not regions):
        join_conditions.append("1=0")
    elif not is_admin:
        join_conditions.append("r.language_code IN (" + ",".join("?" for _ in languages) + ")")
        join_params.extend(languages)
        join_conditions.append("r.region_code IN (" + ",".join("?" for _ in regions) + ")")
        join_params.extend(regions)
    language_filter = ""
    language_params: list[str] = []
    if not is_admin and (not languages or not regions):
        language_filter = " AND 1=0"
    elif not is_admin:
        language_filter = " AND l.code IN (" + ",".join("?" for _ in languages) + ")"
        language_params.extend(languages)
    rec_conditions: list[str] = []
    rec_params: list[str] = []
    if not is_admin and (not languages or not regions):
        rec_conditions.append("1=0")
    elif not is_admin:
        rec_conditions.append("language_code IN (" + ",".join("?" for _ in languages) + ")")
        rec_params.extend(languages)
        rec_conditions.append("region_code IN (" + ",".join("?" for _ in regions) + ")")
        rec_params.extend(regions)
    rec_where = (" WHERE " + " AND ".join(rec_conditions)) if rec_conditions else ""
    release_conditions: list[str] = []
    release_params: list[str] = []
    if not is_admin and (not languages or not regions):
        release_conditions.append("1=0")
    elif not is_admin:
        release_conditions.append("language_code IN (" + ",".join("?" for _ in languages) + ")")
        release_params.extend(languages)
        release_conditions.append("region_code IN (" + ",".join("?" for _ in regions) + ")")
        release_params.extend(regions)
    release_where = (" WHERE " + " AND ".join(release_conditions)) if release_conditions else ""
    with db_conn() as conn:
        lang_rows = conn.execute(f"""
          SELECT l.code,l.name_fr,l.scope,l.collection_status,
            COUNT(DISTINCT r.recording_id) recordings,
            SUM(CASE WHEN r.status='pending_review' THEN 1 ELSE 0 END) pending_review,
            SUM(CASE WHEN r.status='approved' AND r.consent_asr=1 AND r.asr_approved=1 THEN 1 ELSE 0 END) approved_asr,
            SUM(CASE WHEN r.status='approved' AND r.consent_tts=1 AND r.tts_approved=1 THEN 1 ELSE 0 END) approved_tts,
            COALESCE(SUM(CASE WHEN r.status='approved' AND r.consent_asr=1 AND r.asr_approved=1 THEN COALESCE(r.duration_seconds,0) ELSE 0 END),0) as asr_seconds,
            COUNT(DISTINCT r.participant_code) speakers
          FROM language_catalog l LEFT JOIN recordings r ON {' AND '.join(join_conditions)}
          WHERE l.scope='spoken' AND l.is_enabled=1{language_filter}
          GROUP BY l.code,l.name_fr,l.scope,l.collection_status
          ORDER BY recordings DESC,l.name_fr
        """, join_params + language_params).fetchall()
        region_rows = conn.execute("""
          SELECT COALESCE(region_code,'UNK') region_code, COUNT(*) recordings, COUNT(DISTINCT participant_code) speakers,
          SUM(CASE WHEN status='pending_review' THEN 1 ELSE 0 END) pending_review
          FROM recordings""" + rec_where + " GROUP BY region_code ORDER BY recordings DESC", rec_params).fetchall()
        status_rows = conn.execute("SELECT status,COUNT(*) n FROM recordings" + rec_where + " GROUP BY status", rec_params).fetchall()
        release_rows = conn.execute("SELECT status,COUNT(*) n FROM dataset_releases" + release_where + " GROUP BY status", release_params).fetchall()
        if is_admin:
            job_rows = conn.execute("SELECT status,COUNT(*) n FROM training_jobs GROUP BY status").fetchall()
        elif not languages or not regions:
            job_rows = []
        else:
            job_rows = conn.execute("SELECT j.status,COUNT(*) n FROM training_jobs j JOIN dataset_releases d ON d.release_id=j.release_id WHERE d.language_code IN (" + ",".join("?" for _ in languages) + ") AND d.region_code IN (" + ",".join("?" for _ in regions) + ") GROUP BY j.status", languages + regions).fetchall()
        if is_admin:
            user_rows = conn.execute("SELECT role,COUNT(*) n FROM users WHERE active=1 GROUP BY role").fetchall()
            provider_rows = conn.execute("SELECT status,COUNT(*) n FROM providers GROUP BY status").fetchall()
        else:
            user_rows = []
            provider_rows = []
    langs=[]
    for row in lang_rows:
        item=dict(row)
        item["asr_hours"] = round((item.pop("asr_seconds") or 0)/3600,3)
        for key in ("recordings","pending_review","approved_asr","approved_tts","speakers"):
            item[key]=item[key] or 0
        langs.append(item)
    regions_out=[dict(r) for r in region_rows]
    return {"languages":langs,"regions":regions_out,"recording_statuses":{r["status"]:r["n"] for r in status_rows},
            "releases":{r["status"]:r["n"] for r in release_rows},"training_jobs":{r["status"]:r["n"] for r in job_rows},
            "active_users_by_role":{r["role"]:r["n"] for r in user_rows},"providers":{r["status"]:r["n"] for r in provider_rows},
            "permissions": sorted(ROLE_PERMISSIONS.get(actor["role"],set())), "actor": {k:actor.get(k) for k in ("username","display_name","role")}}


@app.get("/api/admin/volunteers")
def volunteer_summary(actor: dict = Depends(require_roles("reviewer", "validator", "language_lead", "dataset_manager"))) -> dict:
    is_admin = actor.get("role") in {"admin", "superadmin"}
    languages = actor.get("allowed_languages") or []
    regions = actor.get("assigned_regions") or []
    join_parts = ["r.participant_code=p.participant_code"]
    join_params: list[str] = []
    where_parts: list[str] = []
    where_params: list[str] = []
    if not is_admin and (not languages or not regions):
        join_parts.append("1=0")
        where_parts.append("1=0")
    if not is_admin and languages and regions:
        placeholders = ",".join("?" for _ in languages)
        join_parts.append(f"r.language_code IN ({placeholders})")
        join_params.extend(languages)
        where_parts.append(f"EXISTS (SELECT 1 FROM recordings rx WHERE rx.participant_code=p.participant_code AND rx.language_code IN ({placeholders})")
        where_params.extend(languages)
        if regions:
            region_marks = ",".join("?" for _ in regions)
            where_parts[-1] += f" AND rx.region_code IN ({region_marks})"
            where_params.extend(regions)
        where_parts[-1] += ")"
    if not is_admin and regions:
        marks = ",".join("?" for _ in regions)
        join_parts.append(f"r.region_code IN ({marks})")
        join_params.extend(regions)
        where_parts.append(f"p.region_code IN ({marks})")
        where_params.extend(regions)
    where = (" WHERE " + " AND ".join(where_parts)) if where_parts else ""
    with db_conn() as conn:
        rows=conn.execute("""SELECT p.participant_code,p.region_code,p.dialect_code,p.participant_type,p.created_at,
          COUNT(r.recording_id) recordings,COUNT(DISTINCT r.language_code) languages,
          SUM(CASE WHEN r.status='approved' THEN 1 ELSE 0 END) approved_recordings
          FROM participants p LEFT JOIN recordings r ON """ + " AND ".join(join_parts) + where +
          " GROUP BY p.participant_code ORDER BY p.created_at DESC LIMIT 500", join_params + where_params).fetchall()
    return {"volunteers":[dict(row) for row in rows],"note":"Codes pseudonymes uniquement ; aucune donnée nominative ni contact personnel n’est collecté dans cette vue."}


@app.get("/api/admin/users")
def list_users(actor: dict = Depends(require_admin)) -> dict:
    with db_conn() as conn:
        rows=conn.execute("SELECT user_id,username,display_name,email,role,allowed_languages_json,assigned_regions_json,active,created_at,last_login_at FROM users ORDER BY created_at DESC").fetchall()
    values=[]
    for r in rows:
        d=dict(r); d["allowed_languages"]=json.loads(d.pop("allowed_languages_json") or "[]"); d["assigned_regions"]=json.loads(d.pop("assigned_regions_json") or "[]"); values.append(d)
    return {"users":values,"roles":[{"role":r,"permissions":sorted(p)} for r,p in ROLE_PERMISSIONS.items()]}

@app.post("/api/admin/users")
def create_user(payload: dict, actor: dict = Depends(require_admin)) -> dict:
    username=str(payload.get("username","")).strip().lower()
    display=str(payload.get("display_name",username)).strip()[:160]
    email=str(payload.get("email","")).strip()[:240]
    role=str(payload.get("role","reviewer"))
    password=str(payload.get("password", ""))
    langs=payload.get("allowed_languages",[]) or []
    regions=payload.get("assigned_regions",[]) or []
    if not re.fullmatch(r"[a-z0-9._-]{3,64}",username): raise HTTPException(422,"Nom d’utilisateur invalide (3–64 caractères, a-z, chiffres, point, tiret, underscore).")
    if role not in ROLE_PERMISSIONS or role in {"superadmin"}: raise HTTPException(422,"Rôle inconnu ou non attribuable.")
    if len(password)<14: raise HTTPException(422,"Le mot de passe doit contenir au moins 14 caractères.")
    if not isinstance(langs,list) or any(code not in VALID_LANGUAGE_CODES for code in langs): raise HTTPException(422,"Liste de langues invalide.")
    if not isinstance(regions,list) or any(code not in REGION_CODES for code in regions): raise HTTPException(422,"Liste de régions invalide.")
    if role != "admin" and (not langs or not regions):
        raise HTTPException(422,"Pour respecter le moindre privilège, chaque compte non-admin doit recevoir au moins une langue et une région explicites.")
    user_id=str(uuid.uuid4()); stamp=now_iso()
    try:
        with db_conn() as conn:
            conn.execute("INSERT INTO users(user_id,username,display_name,email,password_hash,role,allowed_languages_json,assigned_regions_json,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (user_id,username,display,email,hash_password(password),role,json.dumps(langs),json.dumps(regions),stamp))
    except sqlite3.IntegrityError:
        raise HTTPException(409,"Ce nom d’utilisateur existe déjà.")
    record_audit(actor,"create_user","user",user_id,{"role":role})
    return {"ok":True,"user_id":user_id,"username":username,"role":role}

@app.patch("/api/admin/users/{user_id}")
def update_user(user_id: str, payload: dict, actor: dict = Depends(require_admin)) -> dict:
    with db_conn() as conn:
        row=conn.execute("SELECT * FROM users WHERE user_id=?",(user_id,)).fetchone()
        if not row: raise HTTPException(404,"Compte introuvable.")
        role=str(payload.get("role",row["role"]))
        if "active" in payload and not isinstance(payload["active"], bool): raise HTTPException(422,"Le champ active doit être booléen.")
        active=int(payload.get("active", bool(row["active"])))
        langs=payload.get("allowed_languages",json.loads(row["allowed_languages_json"] or "[]"))
        regions=payload.get("assigned_regions",json.loads(row["assigned_regions_json"] or "[]"))
        display=str(payload.get("display_name",row["display_name"])).strip()[:160]
        if role not in ROLE_PERMISSIONS or role=="superadmin": raise HTTPException(422,"Rôle non attribuable.")
        if user_id==actor.get("user_id") and (not active or role!="admin"): raise HTTPException(400,"Évitez de désactiver ou rétrograder votre propre compte administrateur.")
        if not isinstance(langs, list) or not isinstance(regions, list): raise HTTPException(422,"Les langues et régions doivent être transmises sous forme de listes.")
        if any(c not in VALID_LANGUAGE_CODES for c in langs) or any(c not in REGION_CODES for c in regions): raise HTTPException(422,"Périmètre langue/région invalide.")
        if role != "admin" and (not langs or not regions): raise HTTPException(422,"Chaque compte non-admin doit avoir au moins une langue et une région assignées.")
        password=str(payload.get("password", ""))
        if password and len(password)<14: raise HTTPException(422,"Le nouveau mot de passe doit contenir au moins 14 caractères.")
        if password:
            conn.execute("UPDATE users SET role=?,active=?,allowed_languages_json=?,assigned_regions_json=?,display_name=?,password_hash=? WHERE user_id=?",(role,active,json.dumps(langs),json.dumps(regions),display,hash_password(password),user_id))
        else:
            conn.execute("UPDATE users SET role=?,active=?,allowed_languages_json=?,assigned_regions_json=?,display_name=? WHERE user_id=?",(role,active,json.dumps(langs),json.dumps(regions),display,user_id))
        if not active or password:
            conn.execute("UPDATE auth_sessions SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL",(now_iso(),user_id))
    record_audit(actor,"update_user","user",user_id,{"role":role,"active":active})
    return {"ok":True,"user_id":user_id,"role":role,"active":bool(active)}

@app.get("/api/admin/audit-events")
def audit_events(limit: int=Query(default=100,ge=1,le=500), actor: dict=Depends(require_admin)) -> dict:
    with db_conn() as conn:
        rows=conn.execute("SELECT actor_user_id,action,resource_type,resource_id,details_json,actor_role,created_at FROM audit_events ORDER BY created_at DESC LIMIT ?",(limit,)).fetchall()
    return {"events":[{**dict(r),"details":json.loads(r["details_json"] or "{}" )} for r in rows]}

def prepared_manifest_digest(directory: Path) -> str:
    """Hash the release summary and every manifest/report file registered for review."""
    root = directory.resolve()
    required = ("train.csv", "validation.csv", "test.csv", "quality_report.csv", "dataset_summary.json")
    optional = ("excluded_errors.csv",)
    digest = hashlib.sha256()
    for name in (*required, *optional):
        path = root / name
        if not path.exists() and name in optional:
            continue
        resolved = path.resolve()
        if not resolved.is_relative_to(root) or not resolved.is_file():
            raise ValueError(f"Fichier de release absent ou hors dossier : {name}")
        content_hash = hashlib.sha256(resolved.read_bytes()).digest()
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(content_hash)
    return "v2:" + digest.hexdigest()


@app.get("/api/admin/datasets/releases")
def list_dataset_releases(actor: dict=Depends(require_roles("dataset_manager","training_operator","validator"))) -> dict:
    with db_conn() as conn:
        rows=conn.execute("SELECT * FROM dataset_releases ORDER BY created_at DESC LIMIT 200").fetchall()
    result=[dict(r) for r in rows if language_is_allowed(actor,r["language_code"]) and (actor.get("role") in {"admin","superadmin"} or (r["region_code"] != "ALL" and region_is_allowed(actor,r["region_code"]))) ]
    for item in result: item["manifest_summary"]=json.loads(item.pop("manifest_summary_json") or "{}")
    return {"releases":result}

@app.get("/api/admin/datasets/releases/{release_id}/preview")
def preview_prepared_dataset(release_id: str, actor: dict = Depends(require_roles("dataset_manager", "training_operator", "validator"))) -> dict:
    """Preview a registered, server-local prepared corpus without exposing arbitrary file paths."""
    with db_conn() as conn:
        row = conn.execute("SELECT * FROM dataset_releases WHERE release_id=?", (release_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Release introuvable.")
    if not language_is_allowed(actor, row["language_code"]) or (actor.get("role") not in {"admin","superadmin"} and (row["region_code"] == "ALL" or not region_is_allowed(actor,row["region_code"]))):
        raise HTTPException(status_code=403, detail="Langue ou région hors périmètre.")
    relative = str(row["relative_path"] or "").strip()
    if not relative:
        raise HTTPException(status_code=409, detail="Le dataset n’a pas encore été préparé/enregistré sur le serveur.")
    candidate = (PREPARED_DIR / relative).resolve()
    if not candidate.is_relative_to(PREPARED_DIR) or not candidate.is_dir():
        raise HTTPException(status_code=409, detail="Le dossier préparé est absent ou hors du répertoire autorisé.")
    manifest_verified = False
    if str(row["manifest_sha256"] or "").startswith("v2:"):
        try:
            manifest_verified = prepared_manifest_digest(candidate) == row["manifest_sha256"]
        except (OSError, ValueError):
            manifest_verified = False
        if not manifest_verified:
            raise HTTPException(status_code=409, detail="Le contenu de la release a changé depuis son enregistrement ; prépare une nouvelle révision avant validation.")
    summary_path = candidate / "dataset_summary.json"
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise HTTPException(status_code=409, detail="Résumé de dataset absent ou illisible.")
    files = []
    for name in ("train.csv", "validation.csv", "test.csv", "quality_report.csv", "excluded_errors.csv", "dataset_summary.json"):
        file_path = candidate / name
        if file_path.is_file():
            files.append({"name": name, "size_bytes": file_path.stat().st_size})
    quality_preview = []
    quality_path = candidate / "quality_report.csv"
    if quality_path.is_file():
        try:
            with quality_path.open("r", encoding="utf-8-sig", newline="") as stream:
                for index, record in enumerate(csv.DictReader(stream)):
                    if index >= 50:
                        break
                    quality_preview.append(record)
        except (OSError, csv.Error):
            raise HTTPException(status_code=422, detail="quality_report.csv est illisible.")
    return {"release_id": release_id, "label": row["label"], "task": row["task"], "language_code": row["language_code"], "region_code": row["region_code"],
            "status": row["status"], "license_status": row["license_status"], "manifest_sha256": row["manifest_sha256"],
            "manifest_verified": manifest_verified,
            "summary": summary, "files": files, "quality_preview": quality_preview,
            "quality_preview_limit": 50,
            "note": "Aperçu limité. L’approbation finale exige une revue humaine des textes, droits et splits ; ce rapport technique n’est pas une validation linguistique."}


@app.post("/api/admin/datasets/releases")
def create_dataset_release(payload: dict, actor: dict=Depends(require_roles("dataset_manager"))) -> dict:
    task=str(payload.get("task", "")).lower(); lang=str(payload.get("language_code", "")).lower()
    region=str(payload.get("region_code", "ALL")).upper()
    label=str(payload.get("label",f"{task}-{lang}-{region}-{datetime.now(timezone.utc).strftime('%Y%m%d')}")).strip()[:200]
    if task not in {"asr","tts"}: raise HTTPException(422,"Tâche attendue : asr ou tts.")
    if lang not in VALID_LANGUAGE_CODES or not language_is_allowed(actor,lang): raise HTTPException(403,"Code langue invalide ou hors du périmètre du compte.")
    is_admin=actor.get("role") in {"admin","superadmin"}
    if region != "ALL" and region not in REGION_CODES: raise HTTPException(422,"Code région inconnu.")
    if not is_admin and (region == "ALL" or not region_is_allowed(actor,region)):
        raise HTTPException(403,"Un compte non-admin doit créer une release pour une région qui lui est attribuée ; les releases nationales sont réservées à l’administration.")
    where="status='approved' AND consent_asr=1 AND asr_approved=1 AND TRIM(transcription_text)!=''" if task=="asr" else "status='approved' AND consent_tts=1 AND tts_approved=1 AND task_type='read_speech'"
    query=f"SELECT COUNT(*) n, COALESCE(SUM(duration_seconds),0) seconds FROM recordings WHERE language_code=? AND {where}"
    params: list[str] = [lang]
    if region != "ALL":
        query += " AND region_code=?"; params.append(region)
    with db_conn() as conn:
        count=conn.execute(query,params).fetchone()
        if not count["n"]: raise HTTPException(400,"Aucun enregistrement approuvé et autorisé pour cette langue/tâche/région.")
        rid=str(uuid.uuid4()); stamp=now_iso()
        conn.execute("INSERT INTO dataset_releases(release_id,label,task,language_code,region_code,status,approved_recordings,estimated_audio_hours,prepared_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (rid,label,task,lang,region,"awaiting_preparation",count["n"],round((count["seconds"] or 0)/3600,4),actor.get("username",""),stamp,stamp))
    record_audit(actor,"create_dataset_release","dataset_release",rid,{"task":task,"language":lang,"region":region,"recordings":count["n"]})
    return {"ok":True,"release_id":rid,"status":"awaiting_preparation","region_code":region,"approved_recordings":count["n"],"estimated_audio_hours":round((count["seconds"] or 0)/3600,4)}

@app.post("/api/admin/datasets/releases/{release_id}/register")
def register_prepared_dataset(release_id: str, payload: dict, actor: dict=Depends(require_roles("dataset_manager"))) -> dict:
    relative=str(payload.get("relative_path","")).strip()
    license_status=str(payload.get("license_status","pending")).lower()
    note=str(payload.get("review_note","")).strip()[:2000]
    if license_status not in {"pending","restricted","rejected"}: raise HTTPException(422,"À l’enregistrement, le statut des droits doit rester pending/restricted/rejected. Seul un validator peut confirmer verified.")
    candidate=(PREPARED_DIR/relative).resolve()
    if not relative or not candidate.is_relative_to(PREPARED_DIR) or not candidate.is_dir(): raise HTTPException(422,"Le chemin doit désigner un dossier existant dans le dossier prepared_datasets du serveur.")
    summary_path=candidate/"dataset_summary.json"
    if not summary_path.is_file(): raise HTTPException(422,"dataset_summary.json manquant : le pipeline de préparation n’a pas abouti.")
    try:
        summary=json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError,json.JSONDecodeError): raise HTTPException(422,"Résumé du dataset illisible.")
    manifest_files=[candidate/name for name in ("train.csv","validation.csv","test.csv","quality_report.csv")]
    if not all(p.is_file() for p in manifest_files): raise HTTPException(422,"Les manifests train/validation/test et quality_report.csv sont obligatoires.")
    try:
        digest=prepared_manifest_digest(candidate)
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"Manifest incomplet ou non sûr : {exc}") from exc
    with db_conn() as conn:
        row=conn.execute("SELECT * FROM dataset_releases WHERE release_id=?",(release_id,)).fetchone()
        if not row: raise HTTPException(404,"Release introuvable.")
        if row["status"] in {"approved","training","trained","archived"}: raise HTTPException(409,"Cette release est figée; crée une nouvelle release pour changer le dataset approuvé.")
        if not language_is_allowed(actor,row["language_code"]): raise HTTPException(403,"Langue hors périmètre.")
        if actor.get("role") not in {"admin", "superadmin"} and (
            row["region_code"] == "ALL" or not region_is_allowed(actor,row["region_code"])
        ):
            raise HTTPException(status_code=403, detail="Région hors périmètre : vous ne pouvez pas enregistrer cette release.")
        if summary.get("task")!=row["task"] or summary.get("language_code")!=row["language_code"]: raise HTTPException(422,"Le task/language du manifest ne correspond pas à la release.")
        new_status="prepared"
        conn.execute("UPDATE dataset_releases SET status=?,relative_path=?,manifest_sha256=?,manifest_summary_json=?,license_status=?,review_note=?,prepared_by=?,updated_at=? WHERE release_id=?",
            (new_status,relative,digest,json.dumps(summary,ensure_ascii=False),license_status,note,actor.get("username",""),now_iso(),release_id))
    record_audit(actor,"register_prepared_dataset","dataset_release",release_id,{"relative_path":relative,"manifest_sha256":digest,"license_status":license_status,"review_note":note})
    return {"ok":True,"release_id":release_id,"status":"prepared","manifest_sha256":digest,"summary":summary}

@app.patch("/api/admin/datasets/releases/{release_id}")
def update_dataset_release(release_id: str,payload: dict,actor: dict=Depends(require_roles("validator","dataset_manager"))) -> dict:
    status=str(payload.get("status", "")); note=str(payload.get("review_note","")).strip()[:2000]
    requested_license = payload.get("license_status")
    if requested_license is not None:
        if actor.get("role") not in {"validator", "admin", "superadmin"}:
            raise HTTPException(403,"Seul un validator peut confirmer les droits de réutilisation.")
        if requested_license not in {"pending", "verified", "restricted", "rejected"}:
            raise HTTPException(422,"Statut de droits invalide.")
    permitted={"under_review","approved","rejected","archived"}
    if status not in permitted: raise HTTPException(422,"Statut autorisé : under_review, approved, rejected, archived.")
    if status in {"approved", "rejected", "archived"} and actor.get("role") not in {"validator", "admin", "superadmin"}:
        raise HTTPException(403,"Les décisions finales de validation, rejet ou archivage sont réservées au validator/admin.")
    with db_conn() as conn:
        row=conn.execute("SELECT * FROM dataset_releases WHERE release_id=?",(release_id,)).fetchone()
        if not row: raise HTTPException(404,"Release introuvable.")
        if not language_is_allowed(actor,row["language_code"]) or (actor.get("role") not in {"admin","superadmin"} and (row["region_code"] == "ALL" or not region_is_allowed(actor,row["region_code"]))): raise HTTPException(403,"Langue ou région hors périmètre.")
        effective_license = requested_license if requested_license is not None else row["license_status"]
        if status=="approved":
            if actor.get("role") not in {"validator","admin","superadmin"}: raise HTTPException(403,"Approbation finale réservée au validator/admin.")
            if row["status"] not in {"prepared","under_review"}: raise HTTPException(409,"Un dataset doit être préparé et enregistré avant validation.")
            if effective_license!="verified": raise HTTPException(409,"Les licences/droits doivent être explicitement vérifiés par le validator avant l’approbation.")
            summary=json.loads(row["manifest_summary_json"] or "{}")
            if not summary.get("eligible_recordings") or not row["manifest_sha256"]: raise HTTPException(409,"Le manifest ne contient pas de données préparées vérifiables.")
            if str(row["manifest_sha256"]).startswith("v2:"):
                relative = str(row["relative_path"] or "").strip()
                candidate = (PREPARED_DIR / relative).resolve() if relative else PREPARED_DIR
                if not relative or not candidate.is_relative_to(PREPARED_DIR) or not candidate.is_dir():
                    raise HTTPException(409,"Le dossier préparé a disparu ou est hors du répertoire autorisé.")
                try:
                    current_digest = prepared_manifest_digest(candidate)
                except (OSError, ValueError):
                    current_digest = ""
                if current_digest != row["manifest_sha256"]:
                    raise HTTPException(409,"Le manifest ou les CSV ont changé depuis leur enregistrement ; re-prépare et soumets une nouvelle révision.")
        if status=="under_review" and row["status"]!="prepared": raise HTTPException(409,"Seuls les datasets préparés peuvent passer en revue.")
        conn.execute("UPDATE dataset_releases SET status=?,license_status=?,reviewed_by=?,review_note=?,updated_at=? WHERE release_id=?",(status,effective_license,actor.get("username",""),note,now_iso(),release_id))
    record_audit(actor,"update_dataset_release","dataset_release",release_id,{"status":status,"license_status":effective_license,"review_note":note})
    return {"ok":True,"release_id":release_id,"status":status,"license_status":effective_license}

@app.get("/api/admin/providers")
def list_providers(actor: dict=Depends(require_roles("provider_manager","training_operator"))) -> dict:
    with db_conn() as conn:
        rows=conn.execute("SELECT provider_id,name,provider_type,endpoint_url,region,credential_env_var,status,notes,created_at,updated_at FROM providers ORDER BY created_at DESC").fetchall()
    return {"providers":[dict(r) for r in rows]}

@app.post("/api/admin/providers")
def create_provider(payload: dict,actor: dict=Depends(require_roles("provider_manager"))) -> dict:
    name=str(payload.get("name","")).strip()[:160]; kind=str(payload.get("provider_type","")).lower()
    endpoint=str(payload.get("endpoint_url","")).strip()[:1000]; region=str(payload.get("region","")).strip()[:120]
    envvar=str(payload.get("credential_env_var","")).strip()[:120]; notes=str(payload.get("notes","")).strip()[:2000]
    if not name or kind not in {"local_gpu","ssh_server","notebook","cloud_gpu","managed_api","slurm","other"}: raise HTTPException(422,"Nom et type de provider requis.")
    if endpoint:
        try:
            parsed_endpoint = urllib.parse.urlsplit(endpoint)
            hostname = (parsed_endpoint.hostname or "").lower().rstrip(".")
            # HTTP is limited to exact loopback hostnames; prefix checks would accept
            # attacker-controlled names such as localhost.example.org.
            is_loopback_http = parsed_endpoint.scheme == "http" and hostname in {"localhost", "127.0.0.1", "::1"}
            is_https = parsed_endpoint.scheme == "https" and bool(hostname)
            # Force validation of malformed port numbers before persisting the URL.
            _ = parsed_endpoint.port
        except ValueError:
            raise HTTPException(422, "URL de provider invalide.")
        if not (is_https or is_loopback_http):
            raise HTTPException(422, "Endpoint HTTPS requis (HTTP permis uniquement sur localhost/loopback exact).")
        if parsed_endpoint.username or parsed_endpoint.password or parsed_endpoint.query or parsed_endpoint.fragment:
            raise HTTPException(422,"N’inscris aucun secret ou paramètre d’authentification dans l’URL. Utilise une variable d’environnement référencée séparément.")
    if envvar and not re.fullmatch(r"[A-Z][A-Z0-9_]{2,119}",envvar): raise HTTPException(422,"credential_env_var doit être un nom de variable d’environnement, jamais une clé secrète.")
    pid=str(uuid.uuid4()); stamp=now_iso()
    with db_conn() as conn:
        conn.execute("INSERT INTO providers(provider_id,name,provider_type,endpoint_url,region,credential_env_var,status,notes,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (pid,name,kind,endpoint,region,envvar,"configured",notes,stamp,stamp))
    record_audit(actor,"create_provider","provider",pid,{"provider_type":kind})
    return {"ok":True,"provider_id":pid,"status":"configured","note":"Le connecteur doit encore être testé côté serveur avant d’être marqué active."}

@app.patch("/api/admin/providers/{provider_id}")
def update_provider(provider_id: str,payload: dict,actor: dict=Depends(require_roles("provider_manager"))) -> dict:
    allowed={"configured","active","offline","disabled"}; status=str(payload.get("status","configured"))
    if status not in allowed: raise HTTPException(422,"Statut provider invalide.")
    with db_conn() as conn:
        row=conn.execute("SELECT provider_id FROM providers WHERE provider_id=?",(provider_id,)).fetchone()
        if not row: raise HTTPException(404,"Provider introuvable.")
        conn.execute("UPDATE providers SET status=?,updated_at=? WHERE provider_id=?",(status,now_iso(),provider_id))
    record_audit(actor,"update_provider","provider",provider_id,{"status":status})
    return {"ok":True,"provider_id":provider_id,"status":status}

@app.get("/api/admin/training/jobs")
def list_training_jobs(actor: dict=Depends(require_roles("training_operator"))) -> dict:
    with db_conn() as conn:
        rows=conn.execute("""SELECT j.*,d.label dataset_label,d.region_code dataset_region_code,p.name provider_name FROM training_jobs j
            JOIN dataset_releases d ON d.release_id=j.release_id LEFT JOIN providers p ON p.provider_id=j.provider_id
            ORDER BY j.created_at DESC LIMIT 200""").fetchall()
    result=[]
    for r in rows:
        d=dict(r); d["metrics"]=json.loads(d.pop("metrics_json") or "{}");
        if language_is_allowed(actor,d["language_code"]) and (actor.get("role") in {"admin","superadmin"} or (d.get("dataset_region_code") != "ALL" and region_is_allowed(actor,d.get("dataset_region_code", "")))): result.append(d)
    return {"jobs":result}

@app.post("/api/admin/training/jobs")
def create_training_job(payload: dict,actor: dict=Depends(require_roles("training_operator"))) -> dict:
    release_id=str(payload.get("release_id","")); provider_id=str(payload.get("provider_id", "")) or None
    model=str(payload.get("model_name","")).strip()[:200]; method=str(payload.get("training_method","full_finetuning")).lower()
    if method not in {"full_finetuning","lora","qlora","adapter","continued_pretraining"}: raise HTTPException(422,"Méthode de training inconnue.")
    if not model: raise HTTPException(422,"Nom du modèle requis.")
    with db_conn() as conn:
        release=conn.execute("SELECT * FROM dataset_releases WHERE release_id=?",(release_id,)).fetchone()
        if not release: raise HTTPException(404,"Dataset/release introuvable.")
        if release["status"]!="approved": raise HTTPException(409,"La release doit être approuvée avant de créer un entraînement.")
        if not language_is_allowed(actor,release["language_code"]) or (actor.get("role") not in {"admin","superadmin"} and (release["region_code"] == "ALL" or not region_is_allowed(actor,release["region_code"]))): raise HTTPException(403,"Langue ou région hors périmètre.")
        if provider_id:
            provider=conn.execute("SELECT * FROM providers WHERE provider_id=?",(provider_id,)).fetchone()
            if not provider or provider["status"]!="active": raise HTTPException(409,"Provider absent ou pas marqué active par son responsable.")
        jid=str(uuid.uuid4()); stamp=now_iso()
        conn.execute("INSERT INTO training_jobs(job_id,release_id,provider_id,task,language_code,model_name,training_method,status,started_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,'queued',?,?,?)",
          (jid,release_id,provider_id,release["task"],release["language_code"],model,method,actor.get("username",""),stamp,stamp))
    record_audit(actor,"create_training_job","training_job",jid,{"release_id":release_id,"provider_id":provider_id,"method":method})
    return {"ok":True,"job_id":jid,"status":"queued","message":"Le suivi est créé; cette opération ne lance pas elle-même une commande distante. L’opérateur doit lancer le job via le connecteur/serveur choisi puis reporter son identifiant et ses métriques."}

@app.patch("/api/admin/training/jobs/{job_id}")
def update_training_job(job_id: str,payload: dict,actor: dict=Depends(require_roles("training_operator"))) -> dict:
    status=str(payload.get("status","")); allowed={"queued","submitted","running","succeeded","failed","cancelled"}
    if status not in allowed: raise HTTPException(422,"Statut de job invalide.")
    remote=str(payload.get("remote_job_id","")).strip()[:240]; log=str(payload.get("log_summary","")).strip()[:4000]
    metrics=payload.get("metrics",{})
    if not isinstance(metrics,dict): raise HTTPException(422,"metrics doit être un objet JSON.")
    with db_conn() as conn:
        row=conn.execute("""SELECT j.*,d.region_code AS dataset_region_code
            FROM training_jobs j JOIN dataset_releases d ON d.release_id=j.release_id
            WHERE j.job_id=?""",(job_id,)).fetchone()
        if not row: raise HTTPException(404,"Job introuvable.")
        if not language_is_allowed(actor,row["language_code"]):
            raise HTTPException(403,"Langue hors périmètre.")
        if actor.get("role") not in {"admin", "superadmin"} and (
            row["dataset_region_code"] == "ALL" or not region_is_allowed(actor,row["dataset_region_code"])
        ):
            raise HTTPException(403,"Région hors périmètre : vous ne pouvez pas modifier ce job.")
        started=row["started_at"] or (now_iso() if status in {"submitted","running"} else None)
        finished=now_iso() if status in {"succeeded","failed","cancelled"} else None
        conn.execute("UPDATE training_jobs SET status=?,remote_job_id=?,metrics_json=?,log_summary=?,started_at=?,finished_at=?,updated_at=? WHERE job_id=?",
          (status,remote,json.dumps(metrics,ensure_ascii=False),log,started,finished,now_iso(),job_id))
    record_audit(actor,"update_training_job","training_job",job_id,{"status":status,"remote_job_id":remote})
    return {"ok":True,"job_id":job_id,"status":status}

@app.get("/api/admin/phrases", dependencies=[Depends(require_roles("language_lead", "dataset_manager"))])
def admin_phrases(actor: dict = Depends(require_roles("language_lead", "dataset_manager"))) -> dict:
    sql = "SELECT phrase_id, language_code, text_zarma, category, orthography_version, source, source_license, gloss_fr, native_reviewed_by, native_reviewed_at, created_at FROM phrases WHERE is_active=1"
    params: list[str] = []
    if actor.get("role") not in {"admin", "superadmin"}:
        languages = actor.get("allowed_languages") or []
        if not languages:
            return {"phrases": []}
        sql += " AND language_code IN (" + ",".join("?" for _ in languages) + ")"
        params.extend(languages)
    sql += " ORDER BY created_at DESC LIMIT 500"
    with db_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return {"phrases": [dict(row) for row in rows]}
