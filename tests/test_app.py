from __future__ import annotations

import csv
import io
import os
import tempfile
import wave
import math
import struct
import zipfile
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient

# Set the app paths before importing app.main so the tests never touch a user's data.
_TEST_ROOT = Path(tempfile.mkdtemp(prefix="zarma-mvp-tests-"))
os.environ["ZARMA_DATA_DIR"] = str(_TEST_ROOT)
os.environ["ZARMA_ADMIN_TOKEN"] = "pytest-zarma-token-that-is-long-enough"
os.environ["ZARMA_EXPORT_SAMPLE_RATE"] = "22050"

import app.main as main  # noqa: E402

client = TestClient(main.app)
ADMIN = {"X-Admin-Token": os.environ["ZARMA_ADMIN_TOKEN"]}


def wav_bytes(duration: float = 0.6, sample_rate: int = 16000, freq: float = 440.0) -> bytes:
    buffer = io.BytesIO()
    frames = bytearray()
    count = int(duration * sample_rate)
    for i in range(count):
        sample = int(7000 * math.sin(2 * math.pi * freq * i / sample_rate))
        frames.extend(struct.pack("<h", sample))
    with wave.open(buffer, "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(sample_rate)
        stream.writeframes(bytes(frames))
    return buffer.getvalue()


@pytest.fixture(autouse=True)
def clean_database_and_audio():
    main.DATA_DIR.mkdir(parents=True, exist_ok=True)
    main.AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    with main.db_conn() as conn:
        conn.execute("DELETE FROM review_events")
        conn.execute("DELETE FROM recordings")
        conn.execute("DELETE FROM deletion_events")
        conn.execute("DELETE FROM elicitation_prompts")
        conn.execute("DELETE FROM phrases")
        conn.execute("DELETE FROM participants")
    for path in main.AUDIO_DIR.iterdir():
        if path.is_file():
            path.unlink()
    yield


def import_one_phrase(text: str = "Mate ni kani?") -> str:
    payload = (
        "language_code,text_zarma,category,orthography_version,source,source_license,native_review_status,native_reviewed_by,native_reviewed_at\n"
        f'dje,"{text}",greetings,test-v1,test-fixture,TEST_ONLY,APPROVED,test-reviewer,2026-10-09\n'
    ).encode("utf-8")
    response = client.post(
        "/api/admin/import-phrases",
        headers=ADMIN,
        files={"file": ("phrases.csv", payload, "text/csv")},
    )
    assert response.status_code == 200, response.text
    assert response.json()["added"] == 1
    return client.get("/api/phrases").json()["phrases"][0]["phrase_id"]


def upload(phrase_id: str, tone: float = 440.0) -> str:
    response = client.post(
        "/api/recordings",
        data={
            "participant_code": "ZRM-001",
            "phrase_id": phrase_id,
            "consent": "true",
            "consent_version": main.CONSENT_VERSION,
            "consent_asr": "true",
            "consent_tts": "true",
            "duration_seconds": "0.6",
        },
        files={"file": ("recording.wav", wav_bytes(freq=tone), "audio/wav")},
    )
    assert response.status_code == 200, response.text
    return response.json()["recording_id"]


def import_one_elicitation_prompt(prompt_text: str = "Localized prompt for test only", language_code: str = "dje") -> str:
    payload = (
        "language_code,prompt_text,category,orthography_version,source,source_license,native_review_status,native_reviewed_by,native_reviewed_at\n"
        f'"{language_code}","{prompt_text}",general,test-v1,test-fixture,TEST_ONLY,APPROVED,test-reviewer,2026-10-09\n'
    ).encode("utf-8")
    response = client.post(
        "/api/admin/import-elicitation-prompts",
        headers=ADMIN,
        files={"file": ("elicitation.csv", payload, "text/csv")},
    )
    assert response.status_code == 200, response.text
    assert response.json()["added"] == 1
    prompts = client.get(f"/api/elicitation-prompts?language_code={language_code}").json()["prompts"]
    return prompts[0]["elicitation_prompt_id"]


def upload_spontaneous(prompt_text: str = "Localized prompt for test only", language_code: str = "dje") -> str:
    elicitation_prompt_id = import_one_elicitation_prompt(prompt_text, language_code)
    response = client.post(
        "/api/recordings",
        data={
            "participant_code": "ZRM-SPONT-01",
            "consent": "true",
            "consent_version": main.CONSENT_VERSION,
            "consent_asr": "true",
            "consent_tts": "false",
            "task_type": "spontaneous_speech",
            "language_code": language_code,
            "elicitation_prompt_id": elicitation_prompt_id,
            "duration_seconds": "12.0",
        },
        files={"file": ("recording.wav", wav_bytes(duration=0.6), "audio/wav")},
    )
    assert response.status_code == 200, response.text
    return response.json()["recording_id"]


def test_health_and_admin_token():
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/admin/stats").status_code == 401
    assert client.get("/api/admin/stats", headers=ADMIN).status_code == 200
    original = main.ADMIN_TOKEN
    try:
        main.ADMIN_TOKEN = ""
        assert client.get("/api/admin/stats", headers=ADMIN).status_code == 503
    finally:
        main.ADMIN_TOKEN = original


def test_pending_seed_phrases_are_not_imported():
    payload = (
        "text_zarma,category,orthography_version,source,source_license,native_review_status,native_reviewed_by,native_reviewed_at\n"
        '"Mate ni kani?",greetings,peacecorps_2006,peace-corps-reference,internal-pilot-only,PENDING_NATIVE_REVIEW,test-reviewer,2026-10-09\n'
    ).encode("utf-8")
    response = client.post(
        "/api/admin/import-phrases",
        headers=ADMIN,
        files={"file": ("seed.csv", payload, "text/csv")},
    )
    assert response.status_code == 200
    assert response.json()["added"] == 0
    assert response.json()["skipped"] == 1
    payload = payload.replace(b"PENDING_NATIVE_REVIEW", b"APPROVED")
    response = client.post(
        "/api/admin/import-phrases",
        headers=ADMIN,
        files={"file": ("seed.csv", payload, "text/csv")},
    )
    assert response.status_code == 200
    assert response.json()["added"] == 1


def test_redo_phrase_is_reoffered_after_reviewer_request():
    phrase_id = import_one_phrase()
    first_id = upload(phrase_id)
    response = client.post(
        f"/api/admin/recordings/{first_id}/review",
        headers=ADMIN,
        json={"decision": "redo", "note": "Refaire : le texte est coupé."},
    )
    assert response.status_code == 200
    phrases = client.get("/api/phrases?participant_code=ZRM-001").json()
    assert phrase_id in phrases["redo_phrase_ids"]
    second_id = upload(phrase_id, tone=550.0)
    assert second_id != first_id
    phrases = client.get("/api/phrases?participant_code=ZRM-001").json()
    assert phrase_id not in phrases["redo_phrase_ids"]




def test_legacy_phrase_table_migration_allows_same_text_in_different_languages():
    legacy_db = _TEST_ROOT / "legacy.sqlite3"
    conn = __import__("sqlite3").connect(legacy_db)
    conn.executescript("""
        CREATE TABLE phrases (
            phrase_id TEXT PRIMARY KEY,
            language_code TEXT NOT NULL DEFAULT 'dje',
            text_zarma TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT '',
            orthography_version TEXT NOT NULL DEFAULT 'v1',
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            UNIQUE(text_zarma, orthography_version)
        );
        INSERT INTO phrases VALUES ('p1','dje','Hello','greeting','v1',1,'2026-01-01');
    """)
    conn.commit(); conn.close()
    original_path = main.DB_PATH
    try:
        main.DB_PATH = legacy_db
        main.migrate_legacy_phrase_uniqueness()
        conn = __import__("sqlite3").connect(legacy_db)
        conn.execute("INSERT INTO phrases(phrase_id, language_code, text_zarma, category, orthography_version, is_active, created_at) VALUES ('p2','ha','Hello','greeting','v1',1,'2026-01-02')")
        conn.commit()
        rows = conn.execute("SELECT language_code, text_zarma FROM phrases ORDER BY phrase_id").fetchall()
        conn.close()
        assert rows == [("dje", "Hello"), ("ha", "Hello")]
    finally:
        main.DB_PATH = original_path


def test_language_selection_filters_phrases_and_export_metadata():
    payload = (
        "language_code,text_zarma,category,orthography_version,source,source_license,native_review_status,native_reviewed_by,native_reviewed_at\n"
        '"dje","Fofo",greetings,v1,test-fixture,TEST_ONLY,APPROVED,test-reviewer,2026-10-09\n'
        '"ha","Sannu",greetings,v1,test-fixture,TEST_ONLY,APPROVED,test-reviewer,2026-10-09\n'
        '"taq","Azul",greetings,v1,test-fixture,TEST_ONLY,APPROVED,test-reviewer,2026-10-09\n'
    ).encode("utf-8")
    response = client.post(
        "/api/admin/import-phrases",
        headers=ADMIN,
        files={"file": ("multi.csv", payload, "text/csv")},
    )
    assert response.status_code == 200, response.text
    assert response.json()["added"] == 3
    assert [p["text_zarma"] for p in client.get("/api/phrases?language_code=dje").json()["phrases"]] == ["Fofo"]
    assert [p["text_zarma"] for p in client.get("/api/phrases?language_code=ha").json()["phrases"]] == ["Sannu"]
    assert [p["text_zarma"] for p in client.get("/api/phrases?language_code=taq").json()["phrases"]] == ["Azul"]
    assert client.get("/api/phrases?language_code=xyz").status_code == 422


def test_export_contains_phrase_id_and_normalized_audio():
    if not main.shutil_which("ffmpeg"):
        pytest.skip("FFmpeg not installed")
    phrase_id = import_one_phrase()
    recording_id = upload(phrase_id)
    reviewed = client.post(
        f"/api/admin/recordings/{recording_id}/review",
        headers=ADMIN,
        json={"decision": "approved", "note": ""},
    )
    assert reviewed.status_code == 200
    response = client.get("/api/admin/export", headers=ADMIN)
    assert response.status_code == 200, response.text
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert "metadata.csv" in archive.namelist()
        with archive.open("metadata.csv") as stream:
            rows = list(csv.DictReader(io.TextIOWrapper(stream, encoding="utf-8-sig")))
        assert len(rows) == 1
        assert rows[0]["phrase_id"] == phrase_id
        assert "source" in rows[0] and "source_license" in rows[0]
        audio_name = rows[0]["audio_filename"]
        audio_content = archive.read(audio_name)
    with wave.open(io.BytesIO(audio_content), "rb") as output:
        assert output.getnchannels() == 1
        assert output.getsampwidth() == 2
        assert output.getframerate() == 22050


def test_phrase_import_requires_explicit_native_approval_column():
    payload = b"text_zarma,category,orthography_version\n\"Fofo\",greetings,v1\n"
    response = client.post(
        "/api/admin/import-phrases",
        headers=ADMIN,
        files={"file": ("phrases.csv", payload, "text/csv")},
    )
    assert response.status_code == 400
    assert "native_review_status" in response.json()["detail"]


def test_consent_timestamp_is_not_reset_for_same_consent_version():
    phrase_id = import_one_phrase()
    upload(phrase_id, tone=440.0)
    expected = "2026-01-01T00:00:00+00:00"
    with main.db_conn() as conn:
        conn.execute(
            "UPDATE participants SET consent_at=? WHERE participant_code=?",
            (expected, "ZRM-001"),
        )
    upload(phrase_id, tone=520.0)
    with main.db_conn() as conn:
        row = conn.execute(
            "SELECT consent_version, consent_at FROM participants WHERE participant_code=?",
            ("ZRM-001",),
        ).fetchone()
    assert row["consent_version"] == main.CONSENT_VERSION
    assert row["consent_at"] == expected


def test_participant_withdrawal_removes_active_audio_and_metadata_without_retaining_code_in_audit():
    phrase_id = import_one_phrase("Withdrawal test phrase")
    recording_id = upload(phrase_id)
    with main.db_conn() as conn:
        stored_name = conn.execute(
            "SELECT stored_filename FROM recordings WHERE recording_id=?", (recording_id,)
        ).fetchone()["stored_filename"]
    audio_path = main.AUDIO_DIR / stored_name
    assert audio_path.is_file()

    response = client.request(
        "DELETE", "/api/admin/participants/ZRM-001",
        headers=ADMIN,
        json={"reason": "participant_withdrawal", "handled_by": "DATA-STEWARD-01"},
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["recordings_deleted"] == 1
    assert result["audio_files_deleted"] == 1
    assert result["cleanup_pending"] == 0
    assert not audio_path.exists()
    with main.db_conn() as conn:
        assert conn.execute("SELECT 1 FROM participants WHERE participant_code='ZRM-001'").fetchone() is None
        assert conn.execute("SELECT 1 FROM recordings WHERE recording_id=?", (recording_id,)).fetchone() is None
        event = conn.execute("SELECT * FROM deletion_events WHERE request_ref=?", (result["request_ref"],)).fetchone()
    assert event is not None
    assert "participant_code" not in event.keys()
    assert "ZRM-001" not in str(dict(event))
    events_api = client.get("/api/admin/deletion-events", headers=ADMIN)
    assert events_api.status_code == 200
    assert events_api.json()["events"][0]["request_ref"] == result["request_ref"]


def test_importers_reject_unverified_rights_placeholders():
    phrase_payload = (
        "language_code,text_prompt,category,orthography_version,source,source_license,native_review_status,native_reviewed_by,native_reviewed_at\n"
        'dje,"Phrase sans licence confirmée",general,v1,source,TO_VERIFY,APPROVED,reviewer-01,2026-10-09\n'
    ).encode("utf-8")
    phrase_response = client.post(
        "/api/admin/import-phrases", headers=ADMIN,
        files={"file": ("phrases.csv", phrase_payload, "text/csv")},
    )
    assert phrase_response.status_code == 200
    assert phrase_response.json()["added"] == 0
    assert phrase_response.json()["skipped"] == 1

    prompt_payload = (
        "language_code,prompt_text,category,orthography_version,source,source_license,native_review_status,native_reviewed_by,native_reviewed_at\n"
        'dje,"Consigne sans droits confirmés",general,v1,source,PENDING_RIGHTS_REVIEW,APPROVED,reviewer-01,2026-10-09\n'
    ).encode("utf-8")
    prompt_response = client.post(
        "/api/admin/import-elicitation-prompts", headers=ADMIN,
        files={"file": ("prompts.csv", prompt_payload, "text/csv")},
    )
    assert prompt_response.status_code == 200
    assert prompt_response.json()["added"] == 0
    assert prompt_response.json()["skipped"] == 1


def test_text_prompt_and_source_provenance_survive_import_review_and_export():
    if not main.shutil_which("ffmpeg"):
        pytest.skip("FFmpeg not installed")
    payload = (
        "language_code,text_prompt,category,orthography_version,gloss_fr,source,source_license,native_review_status,native_reviewed_by,native_reviewed_at\n"
        'dje,"Phrase de test validée",greetings,orthography-v2,"Traduction de test","Source institutionnelle - exemple","TEST_ONLY",APPROVED,"reviewer-01","2026-10-09"\n'
    ).encode("utf-8")
    response = client.post(
        "/api/admin/import-phrases",
        headers=ADMIN,
        files={"file": ("phrases.csv", payload, "text/csv")},
    )
    assert response.status_code == 200, response.text
    assert response.json()["added"] == 1
    phrase_id = client.get("/api/phrases?language_code=dje").json()["phrases"][0]["phrase_id"]
    with main.db_conn() as conn:
        phrase = conn.execute(
            "SELECT source, source_license, gloss_fr, native_reviewed_by, native_reviewed_at FROM phrases WHERE phrase_id=?",
            (phrase_id,),
        ).fetchone()
    assert phrase["source"] == "Source institutionnelle - exemple"
    assert phrase["source_license"] == "TEST_ONLY"
    assert phrase["native_reviewed_by"] == "reviewer-01"

    recording_id = upload(phrase_id)
    assert client.post(
        f"/api/admin/recordings/{recording_id}/review",
        headers=ADMIN,
        json={"decision": "approved", "note": ""},
    ).status_code == 200
    export = client.get("/api/admin/export", headers=ADMIN)
    assert export.status_code == 200, export.text
    with zipfile.ZipFile(io.BytesIO(export.content)) as archive:
        with archive.open("metadata.csv") as stream:
            exported = list(csv.DictReader(io.TextIOWrapper(stream, encoding="utf-8-sig")))
    assert exported[0]["source"] == "Source institutionnelle - exemple"
    assert exported[0]["source_license"] == "TEST_ONLY"
    assert exported[0]["gloss_fr"] == "Traduction de test"
    assert exported[0]["native_reviewed_by"] == "reviewer-01"


def test_elicitation_prompt_import_requires_approval_provenance_and_exposes_only_approved_prompts():
    pending_payload = (
        "language_code,prompt_text,category,orthography_version,source,source_license,native_review_status,native_reviewed_by,native_reviewed_at\n"
        'dje,"Pending test prompt",general,v1,source,original,PENDING_NATIVE_REVIEW,,\n'
        'ha,"Missing reviewer fields",general,v1,source,original,APPROVED,,\n'
    ).encode("utf-8")
    pending = client.post(
        "/api/admin/import-elicitation-prompts", headers=ADMIN,
        files={"file": ("prompts.csv", pending_payload, "text/csv")},
    )
    assert pending.status_code == 200, pending.text
    assert pending.json()["added"] == 0
    assert pending.json()["skipped"] == 2
    assert client.get("/api/elicitation-prompts?language_code=dje").json()["prompts"] == []

    prompt_id = import_one_elicitation_prompt(language_code="taq")
    visible = client.get("/api/elicitation-prompts?language_code=taq").json()["prompts"]
    assert len(visible) == 1
    assert visible[0]["elicitation_prompt_id"] == prompt_id
    assert client.get("/api/elicitation-prompts?language_code=dje").json()["prompts"] == []


def test_spontaneous_prompt_must_match_selected_language():
    prompt_id = import_one_elicitation_prompt(language_code="ha")
    response = client.post(
        "/api/recordings",
        data={
            "participant_code": "ZRM-SPONT-02", "consent": "true",
            "consent_version": main.CONSENT_VERSION, "task_type": "spontaneous_speech",
            "language_code": "dje", "elicitation_prompt_id": prompt_id,
            "consent_asr": "true", "consent_tts": "false",
        },
        files={"file": ("recording.wav", wav_bytes(), "audio/wav")},
    )
    assert response.status_code == 422


def test_spontaneous_recording_is_stored_without_phrase_and_not_tts_eligible():
    recording_id = upload_spontaneous(language_code="ha")
    with main.db_conn() as conn:
        row = conn.execute(
            "SELECT task_type, phrase_id, language_code, prompt_text, transcription_text, asr_approved, tts_approved, duration_seconds "
            "FROM recordings WHERE recording_id=?", (recording_id,)
        ).fetchone()
    assert row["task_type"] == "spontaneous_speech"
    assert row["phrase_id"] is None
    assert row["language_code"] == "ha"
    assert row["prompt_text"] == "Localized prompt for test only"
    assert row["transcription_text"] == ""
    assert row["duration_seconds"] == pytest.approx(0.6)  # decoded WAV, not the 12s browser claim
    assert row["asr_approved"] == 0 and row["tts_approved"] == 0
    listed = client.get("/api/admin/recordings?task_type=spontaneous_speech", headers=ADMIN).json()["recordings"]
    assert listed[0]["recording_id"] == recording_id


def test_spontaneous_recording_requires_verified_transcript_for_asr_and_blocks_tts():
    recording_id = upload_spontaneous()
    missing = client.post(
        f"/api/admin/recordings/{recording_id}/review", headers=ADMIN,
        json={"decision": "approve_asr", "transcription_text": ""},
    )
    assert missing.status_code == 400
    transcript = "Wande no ga koyra ra" 
    approved = client.post(
        f"/api/admin/recordings/{recording_id}/review", headers=ADMIN,
        json={"decision": "approve_asr", "transcription_text": transcript, "reviewer_label": "REV-01"},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["asr_approved"] is True
    assert approved.json()["tts_approved"] is False
    forbidden = client.post(
        f"/api/admin/recordings/{recording_id}/review", headers=ADMIN,
        json={"decision": "approve_tts", "transcription_text": transcript},
    )
    assert forbidden.status_code == 403
    history = client.get(f"/api/admin/recordings/{recording_id}/history", headers=ADMIN)
    assert history.status_code == 200
    assert history.json()["events"][0]["reviewer_label"] == "REV-01"
    if main.shutil_which("ffmpeg"):
        asr_export = client.get("/api/admin/export?task=asr", headers=ADMIN)
        assert asr_export.status_code == 200, asr_export.text
        with zipfile.ZipFile(io.BytesIO(asr_export.content)) as archive:
            with archive.open("metadata.csv") as stream:
                exported = list(csv.DictReader(io.TextIOWrapper(stream, encoding="utf-8-sig")))
        assert len(exported) == 1
        assert exported[0]["task_type"] == "spontaneous_speech"
        assert exported[0]["text"] == transcript
        assert exported[0]["source"] == "test-fixture"
        assert exported[0]["native_reviewed_by"] == "test-reviewer"
        assert "consent_at" not in exported[0]
        assert client.get("/api/admin/export?task=tts", headers=ADMIN).status_code == 400


def test_read_speech_tts_requires_exact_prompt_text_and_exports_filter_by_task():
    phrase_id = import_one_phrase("Hello test phrase")
    recording_id = upload(phrase_id)
    wrong_tts = client.post(
        f"/api/admin/recordings/{recording_id}/review", headers=ADMIN,
        json={"decision": "approve_tts", "transcription_text": "A different sentence"},
    )
    assert wrong_tts.status_code == 422
    approve_both = client.post(
        f"/api/admin/recordings/{recording_id}/review", headers=ADMIN,
        json={"decision": "approve_both", "transcription_text": "Hello test phrase"},
    )
    assert approve_both.status_code == 200
    if main.shutil_which("ffmpeg"):
        for task in ("asr", "tts"):
            response = client.get(f"/api/admin/export?task={task}", headers=ADMIN)
            assert response.status_code == 200, response.text
            with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
                with archive.open("metadata.csv") as stream:
                    rows = list(csv.DictReader(io.TextIOWrapper(stream, encoding="utf-8-sig")))
            assert len(rows) == 1
            assert rows[0]["text"] == "Hello test phrase"


def test_non_audio_payload_with_audio_mime_is_rejected():
    phrase_id = import_one_phrase()
    response = client.post(
        "/api/recordings",
        data={"participant_code":"ZRM-FAKE-01", "phrase_id":phrase_id,
              "consent":"true", "consent_version":main.CONSENT_VERSION,
              "consent_asr":"true", "consent_tts":"true"},
        files={"file":("not-really.wav", b"this is not audio content", "audio/wav")},
    )
    assert response.status_code == 415


def test_audio_with_wav_signature_but_invalid_payload_is_rejected():
    phrase_id = import_one_phrase()
    fake_wav = b"RIFF" + (100).to_bytes(4, "little") + b"WAVE" + b"not-a-valid-wave-payload"
    response = client.post(
        "/api/recordings",
        data={"participant_code": "ZRM-CORRUPT-01", "phrase_id": phrase_id,
              "consent": "true", "consent_version": main.CONSENT_VERSION,
              "consent_asr": "true", "consent_tts": "true"},
        files={"file": ("corrupt.wav", fake_wav, "audio/wav")},
    )
    assert response.status_code == 415


def test_read_recording_requires_explicit_task_consent():
    phrase_id = import_one_phrase()
    response = client.post(
        "/api/recordings",
        data={"participant_code": "ZRM-NOCONSENT-01", "phrase_id": phrase_id,
              "consent": "true", "consent_version": main.CONSENT_VERSION,
              "consent_asr": "false", "consent_tts": "false"},
        files={"file": ("recording.wav", wav_bytes(), "audio/wav")},
    )
    assert response.status_code == 400


def test_legacy_recording_table_migration_preserves_rows_and_requires_tts_re_review(tmp_path):
    legacy_db = tmp_path / "legacy_recordings.sqlite3"
    import sqlite3
    conn = sqlite3.connect(legacy_db)
    conn.executescript("""
        PRAGMA foreign_keys=OFF;
        CREATE TABLE participants (
            participant_code TEXT PRIMARY KEY, consent_version TEXT NOT NULL,
            consent_at TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE phrases (
            phrase_id TEXT PRIMARY KEY, language_code TEXT NOT NULL DEFAULT 'dje',
            text_zarma TEXT NOT NULL, category TEXT NOT NULL DEFAULT '',
            orthography_version TEXT NOT NULL DEFAULT 'v1', source TEXT NOT NULL DEFAULT '',
            source_license TEXT NOT NULL DEFAULT '', gloss_fr TEXT NOT NULL DEFAULT '',
            native_reviewed_by TEXT NOT NULL DEFAULT '', native_reviewed_at TEXT NOT NULL DEFAULT '',
            is_active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL,
            UNIQUE(language_code, text_zarma, orthography_version)
        );
        CREATE TABLE recordings (
            recording_id TEXT PRIMARY KEY, participant_code TEXT NOT NULL,
            phrase_id TEXT NOT NULL, stored_filename TEXT NOT NULL,
            original_filename TEXT NOT NULL, mime_type TEXT NOT NULL,
            duration_seconds REAL, file_size_bytes INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending_review', created_at TEXT NOT NULL,
            reviewed_at TEXT, reviewer_note TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE review_events (
            event_id TEXT PRIMARY KEY, recording_id TEXT NOT NULL REFERENCES recordings(recording_id),
            decision TEXT NOT NULL, reviewer_label TEXT NOT NULL DEFAULT '',
            transcription_snapshot TEXT NOT NULL DEFAULT '', note TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
        );
        INSERT INTO participants VALUES ('ZRM-LEG-01','consent-v2','2026-01-01T00:00:00+00:00','2026-01-01T00:00:00+00:00');
        INSERT INTO phrases VALUES ('phrase-legacy','dje','Fofo','greeting','v1','','','','','',1,'2026-01-01T00:00:00+00:00');
        INSERT INTO recordings VALUES ('rec-legacy','ZRM-LEG-01','phrase-legacy','rec.wav','rec.wav','audio/wav',1.0,100,'approved','2026-01-01T00:00:00+00:00','2026-01-01T01:00:00+00:00','legacy review');
    """)
    conn.commit(); conn.close()
    original_path = main.DB_PATH
    try:
        main.DB_PATH = legacy_db
        main.init_db()
        main.migrate_legacy_phrase_uniqueness()
        main.migrate_recordings_v2()
        with main.db_conn() as migrated:
            row = migrated.execute("SELECT task_type, language_code, phrase_id, prompt_text, transcription_text, asr_approved, tts_approved, consent_version, consent_asr, consent_tts FROM recordings WHERE recording_id='rec-legacy'").fetchone()
        assert row["task_type"] == "read_speech"
        assert row["language_code"] == "dje"
        assert row["phrase_id"] == "phrase-legacy"
        assert row["prompt_text"] == "Fofo" and row["transcription_text"] == "Fofo"
        assert row["asr_approved"] == 1 and row["tts_approved"] == 0
        assert row["consent_version"] == "legacy_unverified"
        assert row["consent_asr"] == 0 and row["consent_tts"] == 0
    finally:
        main.DB_PATH = original_path


def test_editing_transcript_invalidates_previous_task_approvals():
    phrase_id = import_one_phrase("Phrase inchangée")
    recording_id = upload(phrase_id)
    approved = client.post(
        f"/api/admin/recordings/{recording_id}/review", headers=ADMIN,
        json={"decision":"approve_both", "transcription_text":"Phrase inchangée"},
    )
    assert approved.status_code == 200
    saved = client.post(
        f"/api/admin/recordings/{recording_id}/review", headers=ADMIN,
        json={"decision":"save_transcript", "transcription_text":"Phrase corrigée"},
    )
    assert saved.status_code == 200
    assert saved.json()["status"] == "pending_review"
    assert saved.json()["asr_approved"] is False and saved.json()["tts_approved"] is False


def test_national_language_catalog_and_reviewer_rbac():
    catalog = client.get("/api/languages")
    assert catalog.status_code == 200
    languages = catalog.json()["languages"]
    spoken = {row["code"] for row in languages if row["scope"] == "spoken"}
    charter_codes = {"ara", "bdm", "ful", "gux", "ha", "kau", "taq", "tda", "twq", "tuq", "dje"}
    assert charter_codes <= spoken
    # Dazaga is a distinct technical subcorpus within the broader Tubu/Toubou category.
    assert "dzg" in spoken
    assert next(row for row in languages if row["code"] == "tuq")["name_fr"].startswith("Teda / Tedaga")
    assert "Dazaga" in next(row for row in languages if row["code"] == "dzg")["name_fr"]
    assert {row["code"] for row in languages if row["scope"] == "work"} == {"en", "fr"}

    username = "reviewer_" + __import__("uuid").uuid4().hex[:10]
    password = "Test-Password-2026!" + __import__("uuid").uuid4().hex[:6]
    created = client.post("/api/admin/users", headers=ADMIN, json={
        "username": username, "display_name": "Test reviewer", "role": "reviewer", "password": password,
        "allowed_languages": ["dje"], "assigned_regions": ["NIA"],
    })
    assert created.status_code == 200, created.text
    login = client.post("/api/auth/login", json={"username": username, "password": password})
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    me = client.get("/api/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["allowed_languages"] == ["dje"]
    assert me.json()["assigned_regions"] == ["NIA"]
    dash = client.get("/api/admin/dashboard", headers=headers)
    assert dash.status_code == 200, dash.text
    assert {r["code"] for r in dash.json()["languages"]} == {"dje"}
    assert client.get("/api/admin/users", headers=headers).status_code == 403
    assert client.get("/api/admin/volunteers", headers=headers).status_code == 200
    assert client.post("/api/admin/import-phrases", headers=headers, files={"file": ("x.csv", b"native_review_status\n", "text/csv")}).status_code == 403
    with main.db_conn() as conn:
        conn.execute("DELETE FROM auth_sessions WHERE user_id=?", (created.json()["user_id"],))
        conn.execute("DELETE FROM users WHERE user_id=?", (created.json()["user_id"],))


def test_non_admin_accounts_require_explicit_scope_and_training_requires_approved_regional_release():
    no_scope = client.post("/api/admin/users", headers=ADMIN, json={
        "username": "noscope_" + __import__("uuid").uuid4().hex[:8], "role": "reviewer",
        "password": "Test-Password-2026!", "allowed_languages": [], "assigned_regions": [],
    })
    assert no_scope.status_code == 422

    username = "trainer_" + __import__("uuid").uuid4().hex[:10]
    password = "Trainer-Password-2026!" + __import__("uuid").uuid4().hex[:5]
    created = client.post("/api/admin/users", headers=ADMIN, json={
        "username": username, "role": "training_operator", "password": password,
        "allowed_languages": ["dje"], "assigned_regions": ["NIA"],
    })
    assert created.status_code == 200, created.text
    token = client.post("/api/auth/login", json={"username": username, "password": password}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    import uuid
    stamp = main.now_iso()
    release_id = str(uuid.uuid4())
    with main.db_conn() as conn:
        conn.execute("INSERT INTO dataset_releases(release_id,label,task,language_code,region_code,status,approved_recordings,estimated_audio_hours,manifest_summary_json,license_status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (release_id, "unapproved fixture", "asr", "dje", "NIA", "awaiting_preparation", 1, 0.1, "{}", "pending", stamp, stamp))
    blocked = client.post("/api/admin/training/jobs", headers=headers, json={"release_id": release_id, "model_name": "test-asr"})
    assert blocked.status_code == 409, blocked.text

    national_id = str(uuid.uuid4())
    with main.db_conn() as conn:
        conn.execute("INSERT INTO dataset_releases(release_id,label,task,language_code,region_code,status,approved_recordings,estimated_audio_hours,relative_path,manifest_sha256,manifest_summary_json,license_status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (national_id, "national fixture", "asr", "dje", "ALL", "approved", 1, 0.1, "fixture", "abc123", '{"eligible_recordings":1}', "verified", stamp, stamp))
    denied = client.post("/api/admin/training/jobs", headers=headers, json={"release_id": national_id, "model_name": "test-asr"})
    assert denied.status_code == 403, denied.text
    with main.db_conn() as conn:
        conn.execute("DELETE FROM training_jobs WHERE release_id IN (?,?)", (release_id,national_id))
        conn.execute("DELETE FROM dataset_releases WHERE release_id IN (?,?)", (release_id,national_id))
        conn.execute("DELETE FROM auth_sessions WHERE user_id=?", (created.json()["user_id"],))
        conn.execute("DELETE FROM users WHERE user_id=?", (created.json()["user_id"],))


def test_language_lead_cannot_import_out_of_scope_language_in_either_catalog():
    import uuid
    username = "lead_" + uuid.uuid4().hex[:10]
    password = "Language-Lead-Password!" + uuid.uuid4().hex[:4]
    created = client.post("/api/admin/users", headers=ADMIN, json={
        "username": username, "role": "language_lead", "password": password,
        "allowed_languages": ["dje"], "assigned_regions": ["NIA"],
    })
    assert created.status_code == 200, created.text
    token = client.post("/api/auth/login", json={"username": username, "password": password}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    phrase_csv = (
        "language_code,text_prompt,native_review_status,category,orthography_version,source,source_license,native_reviewed_by,native_reviewed_at\n"
        "ha,Frase test hors périmètre,APPROVED,general,v1,community-review,CC-BY-4.0,reviewer-natif,2026-10-09\n"
    ).encode("utf-8")
    phrase_response = client.post("/api/admin/import-phrases", headers=headers, files={"file": ("phrases.csv", phrase_csv, "text/csv")})
    assert phrase_response.status_code == 403, phrase_response.text

    prompt_csv = (
        "language_code,prompt_text,category,orthography_version,native_review_status,source,source_license,native_reviewed_by,native_reviewed_at\n"
        "ha,Consigne de test hors périmètre,general,v1,APPROVED,community-review,CC-BY-4.0,reviewer-natif,2026-10-09\n"
    ).encode("utf-8")
    prompt_response = client.post("/api/admin/import-elicitation-prompts", headers=headers, files={"file": ("prompts.csv", prompt_csv, "text/csv")})
    assert prompt_response.status_code == 403, prompt_response.text

    with main.db_conn() as conn:
        assert conn.execute("SELECT 1 FROM phrases WHERE text_zarma='Frase test hors périmètre'").fetchone() is None
        assert conn.execute("SELECT 1 FROM elicitation_prompts WHERE prompt_text='Consigne de test hors périmètre'").fetchone() is None
        conn.execute("DELETE FROM auth_sessions WHERE user_id=?", (created.json()["user_id"],))
        conn.execute("DELETE FROM users WHERE user_id=?", (created.json()["user_id"],))



def test_spontaneous_prompt_endpoint_supports_all_enabled_spoken_languages():
    # National rollout must not be limited to the original three pilot languages.
    prompt_id = import_one_elicitation_prompt("Kanuri prompt fixture", language_code="kau")
    response = client.get("/api/elicitation-prompts?language_code=kau")
    assert response.status_code == 200, response.text
    assert response.json()["language_code"] == "kau"
    assert any(row["elicitation_prompt_id"] == prompt_id for row in response.json()["prompts"])
    assert client.get("/api/elicitation-prompts?language_code=xyz").status_code == 422


def test_generic_legacy_approval_cannot_bypass_tts_validator_role():
    phrase_id = import_one_phrase("Permission regression fixture")
    recording_id = upload(phrase_id)
    username = "reviewer_legacy_" + __import__("uuid").uuid4().hex[:8]
    password = "Legacy-Review-Password!" + __import__("uuid").uuid4().hex[:5]
    created = client.post("/api/admin/users", headers=ADMIN, json={
        "username": username, "display_name": "Review only", "role": "reviewer", "password": password,
        "allowed_languages": ["dje"], "assigned_regions": ["UNK"],
    })
    assert created.status_code == 200, created.text
    token = client.post("/api/auth/login", json={"username": username, "password": password}).json()["access_token"]
    response = client.post(
        f"/api/admin/recordings/{recording_id}/review",
        headers={"Authorization": f"Bearer {token}"},
        json={"decision": "approved"},
    )
    assert response.status_code == 403, response.text
    with main.db_conn() as conn:
        row = conn.execute("SELECT asr_approved,tts_approved FROM recordings WHERE recording_id=?", (recording_id,)).fetchone()
        conn.execute("DELETE FROM auth_sessions WHERE user_id=?", (created.json()["user_id"],))
        conn.execute("DELETE FROM users WHERE user_id=?", (created.json()["user_id"],))
    assert row["asr_approved"] == 0 and row["tts_approved"] == 0


def test_training_job_update_enforces_region_scope():
    import uuid
    username = "regional_trainer_" + uuid.uuid4().hex[:8]
    password = "Regional-Trainer-Password!" + uuid.uuid4().hex[:4]
    created = client.post("/api/admin/users", headers=ADMIN, json={
        "username": username, "display_name": "Regional trainer", "role": "training_operator", "password": password,
        "allowed_languages": ["dje"], "assigned_regions": ["NIA"],
    })
    assert created.status_code == 200, created.text
    token = client.post("/api/auth/login", json={"username": username, "password": password}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    stamp = main.now_iso()
    release_id, job_id = str(uuid.uuid4()), str(uuid.uuid4())
    with main.db_conn() as conn:
        conn.execute("INSERT INTO dataset_releases(release_id,label,task,language_code,region_code,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                     (release_id,"Tillsbéri-only fixture","asr","dje","TIL","approved",stamp,stamp))
        conn.execute("INSERT INTO training_jobs(job_id,release_id,task,language_code,model_name,training_method,status,started_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                     (job_id,release_id,"asr","dje","fixture-model","full_finetuning","queued",username,stamp,stamp))
    response = client.patch(f"/api/admin/training/jobs/{job_id}", headers=headers, json={"status":"running"})
    assert response.status_code == 403, response.text
    with main.db_conn() as conn:
        row = conn.execute("SELECT status FROM training_jobs WHERE job_id=?", (job_id,)).fetchone()
        conn.execute("DELETE FROM training_jobs WHERE job_id=?", (job_id,))
        conn.execute("DELETE FROM dataset_releases WHERE release_id=?", (release_id,))
        conn.execute("DELETE FROM auth_sessions WHERE user_id=?", (created.json()["user_id"],))
        conn.execute("DELETE FROM users WHERE user_id=?", (created.json()["user_id"],))
    assert row["status"] == "queued"


def test_dataset_registration_enforces_region_scope(tmp_path):
    import json
    import uuid
    username = "regional_dataset_" + uuid.uuid4().hex[:8]
    password = "Regional-Dataset-Password!" + uuid.uuid4().hex[:4]
    created = client.post("/api/admin/users", headers=ADMIN, json={
        "username": username, "display_name": "Regional dataset manager", "role": "dataset_manager", "password": password,
        "allowed_languages": ["dje"], "assigned_regions": ["NIA"],
    })
    assert created.status_code == 200, created.text
    token = client.post("/api/auth/login", json={"username": username, "password": password}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    release_id = str(uuid.uuid4())
    stamp = main.now_iso()
    with main.db_conn() as conn:
        conn.execute("INSERT INTO dataset_releases(release_id,label,task,language_code,region_code,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                     (release_id, "Tillsbéri release fixture", "asr", "dje", "TIL", "awaiting_preparation", stamp, stamp))

    folder = main.PREPARED_DIR / ("scope-test-" + uuid.uuid4().hex)
    folder.mkdir(parents=True)
    (folder / "dataset_summary.json").write_text(json.dumps({"task": "asr", "language_code": "dje", "eligible_recordings": 1}), encoding="utf-8")
    for name in ("train.csv", "validation.csv", "test.csv", "quality_report.csv"):
        (folder / name).write_text("recording_id\nfixture\n", encoding="utf-8")
    response = client.post(f"/api/admin/datasets/releases/{release_id}/register", headers=headers,
                           json={"relative_path": folder.name, "license_status": "pending"})
    assert response.status_code == 403, response.text
    with main.db_conn() as conn:
        row = conn.execute("SELECT status FROM dataset_releases WHERE release_id=?", (release_id,)).fetchone()
        conn.execute("DELETE FROM dataset_releases WHERE release_id=?", (release_id,))
        conn.execute("DELETE FROM auth_sessions WHERE user_id=?", (created.json()["user_id"],))
        conn.execute("DELETE FROM users WHERE user_id=?", (created.json()["user_id"],))
    import shutil
    shutil.rmtree(folder, ignore_errors=True)
    assert row["status"] == "awaiting_preparation"


def test_user_update_rejects_malformed_scope_types():
    import uuid
    username = "scope_type_" + uuid.uuid4().hex[:8]
    password = "Scope-Type-Password!" + uuid.uuid4().hex[:4]
    created = client.post("/api/admin/users", headers=ADMIN, json={
        "username": username, "display_name": "Scope type test", "role": "reviewer", "password": password,
        "allowed_languages": ["dje"], "assigned_regions": ["NIA"],
    })
    assert created.status_code == 200, created.text
    response = client.patch(f"/api/admin/users/{created.json()['user_id']}", headers=ADMIN,
                            json={"allowed_languages": "dje"})
    assert response.status_code == 422, response.text
    with main.db_conn() as conn:
        conn.execute("DELETE FROM auth_sessions WHERE user_id=?", (created.json()["user_id"],))
        conn.execute("DELETE FROM users WHERE user_id=?", (created.json()["user_id"],))


def test_prepared_release_detects_manifest_changes_before_review_or_approval(tmp_path):
    import json
    import uuid
    folder = main.PREPARED_DIR / ("manifest-test-" + uuid.uuid4().hex)
    folder.mkdir(parents=True)
    (folder / "dataset_summary.json").write_text(json.dumps({"task": "asr", "language_code": "dje", "eligible_recordings": 3}), encoding="utf-8")
    for name in ("train.csv", "validation.csv", "test.csv", "quality_report.csv"):
        (folder / name).write_text("recording_id,text\nr001,fixture\n", encoding="utf-8")
    stamp = main.now_iso()
    release_id = str(uuid.uuid4())
    with main.db_conn() as conn:
        conn.execute("INSERT INTO dataset_releases(release_id,label,task,language_code,region_code,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                     (release_id, "Manifest integrity fixture", "asr", "dje", "ALL", "awaiting_preparation", stamp, stamp))
    registered = client.post(f"/api/admin/datasets/releases/{release_id}/register", headers=ADMIN,
                             json={"relative_path": folder.name, "license_status": "pending"})
    assert registered.status_code == 200, registered.text
    assert registered.json()["manifest_sha256"].startswith("v2:")
    preview = client.get(f"/api/admin/datasets/releases/{release_id}/preview", headers=ADMIN)
    assert preview.status_code == 200, preview.text
    assert preview.json()["manifest_verified"] is True

    (folder / "train.csv").write_text("recording_id,text\nr001,TAMPERED\n", encoding="utf-8")
    tampered_preview = client.get(f"/api/admin/datasets/releases/{release_id}/preview", headers=ADMIN)
    assert tampered_preview.status_code == 409, tampered_preview.text
    approval = client.patch(f"/api/admin/datasets/releases/{release_id}", headers=ADMIN,
                            json={"status": "approved", "license_status": "verified"})
    assert approval.status_code == 409, approval.text
    with main.db_conn() as conn:
        row = conn.execute("SELECT status FROM dataset_releases WHERE release_id=?", (release_id,)).fetchone()
        conn.execute("DELETE FROM dataset_releases WHERE release_id=?", (release_id,))
    import shutil
    shutil.rmtree(folder, ignore_errors=True)
    assert row["status"] == "prepared"


def test_provider_endpoint_rejects_lookalike_localhost_hosts():
    base = {
        "name": "provider-test",
        "provider_type": "cloud_gpu",
        "endpoint_url": "http://localhost.evil.example/api",
        "region": "test",
        "credential_env_var": "TEST_PROVIDER_KEY",
        "notes": "test-only",
    }
    response = client.post("/api/admin/providers", headers=ADMIN, json=base)
    assert response.status_code == 422, response.text

    accepted = {**base, "name": "provider-local-test", "endpoint_url": "http://localhost:9000/api"}
    response = client.post("/api/admin/providers", headers=ADMIN, json=accepted)
    assert response.status_code == 200, response.text

    bad_port = {**base, "name": "provider-bad-port", "endpoint_url": "https://example.org:not-a-port/api"}
    response = client.post("/api/admin/providers", headers=ADMIN, json=bad_port)
    assert response.status_code == 422, response.text
