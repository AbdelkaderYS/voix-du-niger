from __future__ import annotations

import csv
import io
import math
import struct
import subprocess
import sys
import wave
import zipfile
from pathlib import Path


def make_wav(freq: float) -> bytes:
    buffer = io.BytesIO()
    sample_rate = 22050
    frames = bytearray()
    for i in range(sample_rate):
        value = int(6000 * math.sin(2 * math.pi * freq * i / sample_rate))
        frames.extend(struct.pack("<h", value))
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(bytes(frames))
    return buffer.getvalue()


def test_prepare_export_creates_grouped_train_validation_test(tmp_path: Path):
    root = Path(__file__).resolve().parents[1]
    archive_path = tmp_path / "export.zip"
    output = tmp_path / "prepared"
    rows = []
    wavs = []
    for index in range(4):
        record_id = f"r{index+1:03d}"
        filename = f"audio/{record_id}.wav"
        rows.append({
            "recording_id": record_id,
            "phrase_id": f"p{index+1:03d}",
            "audio_filename": filename,
            "text": f"phrase de test {index+1}",
            "participant_code": "ZRM-001",
            "language_code": "dje",
            "source": "Source de test",
            "source_license": "TEST_LICENSE_CONFIRMED",
            "gloss_fr": "Traduction de test",
        })
        wavs.append((filename, make_wav(300 + 50 * index)))
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
        meta = io.StringIO(newline="")
        writer = csv.DictWriter(meta, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
        archive.writestr("metadata.csv", meta.getvalue())
        for filename, wav in wavs:
            archive.writestr(filename, wav)

    result = subprocess.run(
        [sys.executable, "scripts/prepare_dataset.py", "--input", str(archive_path),
         "--out-dir", str(output), "--group-by", "phrase"],
        cwd=root, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    for name in ("train.csv", "validation.csv", "test.csv", "quality_report.csv", "dataset_summary.json"):
        assert (output / name).is_file(), name
    split_counts = {}
    for split in ("train", "validation", "test"):
        with (output / f"{split}.csv").open(encoding="utf-8", newline="") as stream:
            split_counts[split] = len(list(csv.DictReader(stream)))
    assert split_counts == {"train": 2, "validation": 1, "test": 1}
    with (output / "train.csv").open(encoding="utf-8", newline="") as stream:
        train_rows = list(csv.DictReader(stream))
    assert train_rows
    assert train_rows[0]["source"] == "Source de test"
    assert train_rows[0]["source_license"] == "TEST_LICENSE_CONFIRMED"


def test_asr_task_filters_approval_and_splits_by_speaker(tmp_path: Path):
    root = Path(__file__).resolve().parents[1]
    archive_path = tmp_path / "asr_export.zip"
    output = tmp_path / "asr_prepared"
    rows = []
    audio_files = []
    # Four approved, distinct speakers give the speaker-disjoint split enough groups.
    for index in range(4):
        record_id = f"asr{index:03d}"
        filename = f"audio/{record_id}.wav"
        rows.append({
            "recording_id": record_id,
            "phrase_id": "",
            "task_type": "spontaneous_speech",
            "language_code": "dje",
            "source_license": "TEST_LICENSE_CONFIRMED",
            "audio_filename": filename,
            "text": f"transcription test {index}",
            "participant_code": f"SPK-{index:03d}",
            "asr_approved": "1",
            "consent_asr": "1",
            "tts_approved": "0",
            "consent_tts": "0",
        })
        audio_files.append((filename, make_wav(320 + 30 * index)))
    rows.append({
        "recording_id": "asr_unapproved", "phrase_id": "", "task_type": "spontaneous_speech",
        "language_code": "dje", "source_license": "TEST_LICENSE_CONFIRMED", "audio_filename": "audio/asr_unapproved.wav",
        "text": "should be filtered", "participant_code": "SPK-UNAPPROVED",
        "asr_approved": "0", "consent_asr": "1", "tts_approved": "0", "consent_tts": "0",
    })
    audio_files.append(("audio/asr_unapproved.wav", make_wav(520)))
    rows.append({
        "recording_id": "asr_no_consent", "phrase_id": "", "task_type": "spontaneous_speech",
        "language_code": "dje", "source_license": "TEST_LICENSE_CONFIRMED", "audio_filename": "audio/asr_no_consent.wav",
        "text": "must not leak without task consent", "participant_code": "SPK-NO-CONSENT",
        "asr_approved": "1", "consent_asr": "0", "tts_approved": "0", "consent_tts": "0",
    })
    audio_files.append(("audio/asr_no_consent.wav", make_wav(570)))
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
        meta = io.StringIO(newline="")
        writer = csv.DictWriter(meta, fieldnames=list(rows[0].keys()))
        writer.writeheader(); writer.writerows(rows)
        archive.writestr("metadata.csv", meta.getvalue())
        for filename, wav in audio_files:
            archive.writestr(filename, wav)

    result = subprocess.run(
        [sys.executable, "scripts/prepare_dataset.py", "--input", str(archive_path),
         "--out-dir", str(output), "--task", "asr", "--language-code", "dje", "--seed", "17"],
        cwd=root, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    manifest = []
    groups_by_split = {}
    for split in ("train", "validation", "test"):
        with (output / f"{split}.csv").open(encoding="utf-8", newline="") as stream:
            split_rows = list(csv.DictReader(stream))
        manifest.extend(split_rows)
        groups_by_split[split] = {row["speaker_id"] for row in split_rows}
    assert len(manifest) == 4
    assert "should be filtered" not in {row["text"] for row in manifest}
    assert "must not leak without task consent" not in {row["text"] for row in manifest}
    assert all(row["task_type"] == "spontaneous_speech" for row in manifest)
    assert not (groups_by_split["train"] & groups_by_split["validation"])
    assert not (groups_by_split["train"] & groups_by_split["test"])
    assert not (groups_by_split["validation"] & groups_by_split["test"])


def test_tts_task_filters_missing_consent_and_spontaneous_speech(tmp_path: Path):
    root = Path(__file__).resolve().parents[1]
    archive_path = tmp_path / "tts_export.zip"
    output = tmp_path / "tts_prepared"
    rows = []
    audio_files = []
    for index in range(4):
        name = f"audio/tts{index:03d}.wav"
        rows.append({
            "recording_id": f"tts{index:03d}", "phrase_id": f"p{index:03d}",
            "task_type": "read_speech", "language_code": "dje", "source_license": "TEST_LICENSE_CONFIRMED",
            "audio_filename": name, "text": f"TTS phrase {index}", "participant_code": f"SPK-{index:03d}",
            "tts_approved": "1", "consent_tts": "1", "asr_approved": "1", "consent_asr": "1",
        })
        audio_files.append((name, make_wav(300 + 40 * index)))
    rows.extend([
        {"recording_id": "tts_no_consent", "phrase_id": "p-no", "task_type": "read_speech", "language_code": "dje",
         "source_license": "TEST_LICENSE_CONFIRMED", "audio_filename": "audio/no_consent.wav", "text": "no consent",
         "participant_code": "SPK-NO", "tts_approved": "1", "consent_tts": "0", "asr_approved": "0", "consent_asr": "1"},
        {"recording_id": "tts_spontaneous", "phrase_id": "", "task_type": "spontaneous_speech", "language_code": "dje",
         "source_license": "TEST_LICENSE_CONFIRMED", "audio_filename": "audio/spontaneous.wav", "text": "spontaneous",
         "participant_code": "SPK-SPONT", "tts_approved": "1", "consent_tts": "1", "asr_approved": "1", "consent_asr": "1"},
    ])
    audio_files.extend([("audio/no_consent.wav", make_wav(510)), ("audio/spontaneous.wav", make_wav(550))])
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
        meta = io.StringIO(newline="")
        writer = csv.DictWriter(meta, fieldnames=list(rows[0].keys()))
        writer.writeheader(); writer.writerows(rows)
        archive.writestr("metadata.csv", meta.getvalue())
        for filename, wav in audio_files:
            archive.writestr(filename, wav)
    result = subprocess.run(
        [sys.executable, "scripts/prepare_dataset.py", "--input", str(archive_path), "--out-dir", str(output),
         "--task", "tts", "--language-code", "dje", "--seed", "13"],
        cwd=root, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    manifest = []
    for split in ("train", "validation", "test"):
        with (output / f"{split}.csv").open(encoding="utf-8", newline="") as stream:
            manifest.extend(csv.DictReader(stream))
    assert len(manifest) == 4
    assert all(row["task_type"] == "read_speech" for row in manifest)
    assert all(row["consent_tts"] == "1" for row in manifest)
    assert "no consent" not in {row["text"] for row in manifest}
    assert "spontaneous" not in {row["text"] for row in manifest}


def test_task_dataset_prep_rejects_unverified_license_terms(tmp_path: Path):
    root = Path(__file__).resolve().parents[1]
    archive_path = tmp_path / "unverified_license.zip"
    row = {
        "recording_id": "r001", "phrase_id": "p001", "task_type": "read_speech", "language_code": "dje",
        "audio_filename": "audio/r001.wav", "text": "Phrase", "participant_code": "SPK-001",
        "source_license": "TO_VERIFY", "asr_approved": "1", "consent_asr": "1", "tts_approved": "0", "consent_tts": "0",
    }
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
        meta = io.StringIO(newline="")
        writer = csv.DictWriter(meta, fieldnames=list(row.keys())); writer.writeheader(); writer.writerow(row)
        archive.writestr("metadata.csv", meta.getvalue())
        archive.writestr("audio/r001.wav", make_wav(340))
    output = tmp_path / "must_not_prepare"
    result = subprocess.run(
        [sys.executable, "scripts/prepare_dataset.py", "--input", str(archive_path), "--out-dir", str(output),
         "--task", "asr", "--language-code", "dje"],
        cwd=root, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode != 0
    assert "licence/condition de réutilisation" in (result.stdout + result.stderr)
    assert not output.exists()


def test_phrase_split_groups_same_text_even_with_different_ids_and_punctuation():
    from scripts.prepare_dataset import allocate_splits

    rows = [
        {"phrase_id": "p001", "text": "Mate ni kani?", "speaker_id": "spk1"},
        {"phrase_id": "p099", "text": "mate ni kani", "speaker_id": "spk2"},
        {"phrase_id": "p002", "text": "Bani samay walla", "speaker_id": "spk1"},
        {"phrase_id": "p003", "text": "Fofo", "speaker_id": "spk2"},
    ]
    assignment = allocate_splits(rows, "phrase", seed=42)
    assert rows[0]["_split_group"] == rows[1]["_split_group"]
    assert assignment[rows[0]["_split_group"]] == assignment[rows[1]["_split_group"]]


def test_wav_rms_is_not_overcounted(tmp_path: Path):
    from scripts.prepare_dataset import inspect_wav

    path = tmp_path / "tone.wav"
    path.write_bytes(make_wav(440.0))
    info = inspect_wav(path, min_duration=0.35, max_duration=20.0)
    # A 6000-amplitude full-scale 16-bit sine wave has RMS near 0.129.
    # This guards against accidentally accumulating sample energy twice.
    assert 0.127 < info["rms"] < 0.132


def test_multilingual_export_requires_language_and_filters_selected_language(tmp_path: Path):
    root = Path(__file__).resolve().parents[1]
    archive_path = tmp_path / "multilingual_export.zip"
    rows = [
        {"recording_id": "dje001", "phrase_id": "pdje1", "language_code": "dje", "audio_filename": "audio/dje001.wav", "text": "Fofo", "participant_code": "ZRM-001"},
        {"recording_id": "ha001", "phrase_id": "pha1", "language_code": "ha", "audio_filename": "audio/ha001.wav", "text": "Sannu", "participant_code": "HA-001"},
        {"recording_id": "ha002", "phrase_id": "pha2", "language_code": "ha", "audio_filename": "audio/ha002.wav", "text": "Ina kwana", "participant_code": "HA-001"},
        {"recording_id": "ha003", "phrase_id": "pha3", "language_code": "ha", "audio_filename": "audio/ha003.wav", "text": "Na gode", "participant_code": "HA-002"},
        {"recording_id": "taq001", "phrase_id": "ptaq1", "language_code": "taq", "audio_filename": "audio/taq001.wav", "text": "Phrase Tamasheq", "participant_code": "TAQ-001"},
    ]
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
        meta = io.StringIO(newline="")
        writer = csv.DictWriter(meta, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
        archive.writestr("metadata.csv", meta.getvalue())
        for index, row in enumerate(rows):
            archive.writestr(row["audio_filename"], make_wav(300 + index * 60))

    no_language = subprocess.run(
        [sys.executable, "scripts/prepare_dataset.py", "--input", str(archive_path),
         "--out-dir", str(tmp_path / "no_language"), "--group-by", "phrase"],
        cwd=root, capture_output=True, text=True, timeout=60,
    )
    assert no_language.returncode != 0
    assert "plusieurs langues" in (no_language.stdout + no_language.stderr)

    selected = tmp_path / "hausa_prepared"
    result = subprocess.run(
        [sys.executable, "scripts/prepare_dataset.py", "--input", str(archive_path),
         "--out-dir", str(selected), "--language-code", "ha", "--group-by", "phrase"],
        cwd=root, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    manifest_rows = []
    for split in ("train", "validation", "test"):
        with (selected / f"{split}.csv").open(encoding="utf-8", newline="") as stream:
            manifest_rows.extend(csv.DictReader(stream))
    assert len(manifest_rows) == 3
    assert {row["language_code"] for row in manifest_rows} == {"ha"}
    assert {row["text"] for row in manifest_rows} == {"Sannu", "Ina kwana", "Na gode"}


def test_language_error_does_not_leave_blocking_output_directory(tmp_path: Path):
    root = Path(__file__).resolve().parents[1]
    archive_path = tmp_path / "multilingual_export.zip"
    rows = [
        {"recording_id": "r001", "phrase_id": "p1", "language_code": "dje", "audio_filename": "audio/r001.wav", "text": "Fofo", "participant_code": "spk1"},
        {"recording_id": "r002", "phrase_id": "p2", "language_code": "ha", "audio_filename": "audio/r002.wav", "text": "Sannu", "participant_code": "spk2"},
    ]
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
        meta = io.StringIO(newline="")
        writer = csv.DictWriter(meta, fieldnames=list(rows[0].keys()))
        writer.writeheader(); writer.writerows(rows)
        archive.writestr("metadata.csv", meta.getvalue())
        for index, row in enumerate(rows):
            archive.writestr(row["audio_filename"], make_wav(350 + index * 100))
    output = tmp_path / "corrected_retry"
    failed = subprocess.run(
        [sys.executable, "scripts/prepare_dataset.py", "--input", str(archive_path), "--out-dir", str(output)],
        cwd=root, capture_output=True, text=True, timeout=60,
    )
    assert failed.returncode != 0
    assert not output.exists()


def test_national_language_outside_original_pilot_can_be_prepared(tmp_path: Path):
    root = Path(__file__).resolve().parents[1]
    archive_path = tmp_path / "kanuri_asr_export.zip"
    output = tmp_path / "kanuri_prepared"
    rows = []
    audio = []
    for index in range(4):
        rec_id = f"kau{index:03d}"
        name = f"audio/{rec_id}.wav"
        rows.append({
            "recording_id": rec_id, "phrase_id": "", "task_type": "spontaneous_speech",
            "language_code": "kau", "audio_filename": name, "text": f"Kanuri transcription fixture {index}",
            "participant_code": f"KAU-SPK-{index}", "source_license": "TEST_LICENSE_CONFIRMED",
            "asr_approved": "1", "consent_asr": "1", "tts_approved": "0", "consent_tts": "0",
        })
        audio.append((name, make_wav(320 + 30 * index)))
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
        meta = io.StringIO(newline="")
        writer = csv.DictWriter(meta, fieldnames=list(rows[0].keys()))
        writer.writeheader(); writer.writerows(rows)
        archive.writestr("metadata.csv", meta.getvalue())
        for name, data in audio:
            archive.writestr(name, data)
    result = subprocess.run(
        [sys.executable, "scripts/prepare_dataset.py", "--input", str(archive_path),
         "--out-dir", str(output), "--task", "asr", "--language-code", "kau"],
        cwd=root, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    import json
    summary = json.loads((output / "dataset_summary.json").read_text(encoding="utf-8"))
    assert summary["language_code"] == "kau"
    assert summary["eligible_recordings"] == 4
