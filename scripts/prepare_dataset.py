#!/usr/bin/env python3
"""Prepare an approved Voix du Niger export ZIP for language-specific ASR or TTS experiments.

This script validates the export, optionally resamples WAVs, flags technical audio
issues, avoids exact duplicate audio, and creates train/validation/test CSV manifests.
Choose --task asr or tts for task-specific filtering and sensible duration/split defaults.
Multilingual exports must be filtered to one language. It does not validate transcript
correctness or replace native-speaker review.
"""
from __future__ import annotations

import argparse
import array
import csv
import hashlib
import json
import random
import re
import shutil
import subprocess
import tempfile
import unicodedata
import wave
import zipfile
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath
from typing import Any

REQUIRED_COLUMNS = {"recording_id", "audio_filename", "text", "participant_code"}
OUTPUT_COLUMNS = [
    "recording_id", "phrase_id", "task_type", "language_code", "category", "orthography_version",
    "source", "source_license", "gloss_fr", "native_reviewed_by", "native_reviewed_at",
    "consent_version", "consent_asr", "consent_tts", "recorded_at",
    "audio_path", "text", "speaker_id", "sample_rate", "duration_seconds",
    "audio_sha256", "quality_flags",
]


def normalized_text(text: str) -> str:
    # Split hygiene only: NFC + case-folding + whitespace/punctuation normalization.
    # This prevents identical text from leaking across splits when it was imported
    # more than once under different phrase IDs or punctuation conventions.
    text = unicodedata.normalize("NFC", text).casefold()
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    return " ".join(text.split())


SUPPORTED_LANGUAGE_CODES = {"ara", "bdm", "ful", "gux", "ha", "kau", "taq", "tda", "twq", "tuq", "dzg", "dje"}

UNVERIFIED_RIGHTS_LABELS = {
    "", "to_verify", "to verify", "tbd", "unknown", "unverified", "pending",
    "pending_rights_review", "rights_pending",
}


def rights_are_unverified(value: str) -> bool:
    normalized = " ".join((value or "").strip().casefold().split())
    return normalized in UNVERIFIED_RIGHTS_LABELS


def safe_member_name(name: str) -> str:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or not name.startswith("audio/"):
        raise ValueError(f"Chemin audio non sûr dans metadata.csv : {name!r}")
    if path.suffix.lower() != ".wav":
        raise ValueError(f"Le fichier exporté n'est pas un WAV : {name!r}")
    return path.as_posix()


def inspect_wav(path: Path, min_duration: float, max_duration: float) -> dict[str, Any]:
    with wave.open(str(path), "rb") as wav:
        channels = wav.getnchannels()
        sample_width = wav.getsampwidth()
        sample_rate = wav.getframerate()
        frame_count = wav.getnframes()
        comp_type = wav.getcomptype()
        if comp_type != "NONE":
            raise ValueError(f"WAV compressé non pris en charge : {comp_type}")
        if channels != 1:
            raise ValueError(f"Audio attendu en mono, reçu : {channels} canaux")
        if sample_width != 2:
            raise ValueError(f"PCM 16 bits attendu, largeur reçue : {sample_width * 8} bits")
        if sample_rate <= 0 or frame_count <= 0:
            raise ValueError("WAV vide ou fréquence d'échantillonnage invalide")
        duration = frame_count / sample_rate
        sample_count = 0
        square_sum = 0.0
        peak = 0
        clipped = 0
        # Read in chunks so that long files don't all need to be in memory.
        while True:
            raw = wav.readframes(65536)
            if not raw:
                break
            samples = array.array("h")
            samples.frombytes(raw)
            if samples.itemsize != 2:
                raise ValueError("La plateforme ne permet pas de lire ce PCM 16 bits")
            if __import__("sys").byteorder != "little":
                samples.byteswap()
            sample_count += len(samples)
            for sample in samples:
                value = int(sample)
                abs_value = abs(value)
                peak = max(peak, abs_value)
                clipped += abs_value >= 32760
                square_sum += float(value * value)
        rms = ((square_sum / max(sample_count, 1)) ** 0.5) / 32768.0
        clipping_ratio = clipped / max(sample_count, 1)

    flags: list[str] = []
    if duration < min_duration:
        flags.append("too_short")
    if duration > max_duration:
        flags.append("too_long")
    if rms < 0.003:
        flags.append("very_quiet_or_silent")
    if clipping_ratio > 0.01:
        flags.append("possible_clipping")
    return {
        "sample_rate": sample_rate,
        "duration_seconds": round(duration, 4),
        "rms": round(rms, 6),
        "peak_abs": peak,
        "clipping_ratio": round(clipping_ratio, 6),
        "quality_flags": flags,
    }


def maybe_resample(source: Path, destination: Path, target_rate: int | None) -> Path:
    if target_rate is None:
        shutil.copy2(source, destination)
        return destination
    with wave.open(str(source), "rb") as wav:
        same_format = wav.getframerate() == target_rate and wav.getnchannels() == 1 and wav.getsampwidth() == 2
    if same_format:
        shutil.copy2(source, destination)
        return destination
    if not shutil.which("ffmpeg"):
        raise RuntimeError("FFmpeg est nécessaire pour convertir la fréquence audio. Installez-le ou retirez --target-sample-rate.")
    result = subprocess.run(
        ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-i", str(source),
         "-vn", "-ac", "1", "-ar", str(target_rate), "-c:a", "pcm_s16le", str(destination)],
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0 or not destination.is_file() or destination.stat().st_size == 0:
        raise RuntimeError(f"Échec de conversion FFmpeg : {(result.stderr or '')[-500:]}")
    return destination


def allocate_splits(rows: list[dict[str, Any]], group_by: str, seed: int) -> dict[str, str]:
    groups: set[str] = set()
    for row in rows:
        if group_by == "speaker":
            key = row["speaker_id"]
        else:
            # Group by canonicalized transcript rather than phrase_id alone:
            # the same text may have been imported twice with another orthography version.
            language = row.get("language_code", "dje") or "dje"
            key = f"{language}::{normalized_text(row['text'])}"
        row["_split_group"] = key
        groups.add(key)
    group_list = sorted(groups)
    if len(group_list) < 3:
        raise ValueError(
            f"Il faut au moins 3 groupes distincts pour créer train/validation/test ; reçu {len(group_list)}. "
            "Collectez plus de phrases ou choisissez --group-by adapté."
        )
    random.Random(seed).shuffle(group_list)
    n_test = max(1, round(len(group_list) * 0.10))
    n_val = max(1, round(len(group_list) * 0.10))
    while n_test + n_val >= len(group_list):
        if n_val > 1:
            n_val -= 1
        elif n_test > 1:
            n_test -= 1
        else:
            break
    assignment: dict[str, str] = {}
    for key in group_list[:n_test]:
        assignment[key] = "test"
    for key in group_list[n_test:n_test + n_val]:
        assignment[key] = "validation"
    for key in group_list[n_test + n_val:]:
        assignment[key] = "train"
    return assignment


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="ZIP généré par l'administration du MVP")
    parser.add_argument("--out-dir", required=True, type=Path, help="Dossier de préparation, qui doit être vide ou absent")
    parser.add_argument("--task", choices=("asr", "tts"), default=None,
                        help="Filtrer selon les indicateurs d'approbation de l'export ; avec ASR, split speaker-disjoint par défaut")
    parser.add_argument("--target-sample-rate", type=int, default=None, help="Ex. 16000 ou 22050 ; uniquement selon le modèle retenu")
    parser.add_argument("--language-code", choices=tuple(sorted(SUPPORTED_LANGUAGE_CODES)), default=None,
                        help="Préparer une seule langue depuis un export multilingue ; requis si plusieurs langues sont présentes")
    parser.add_argument("--group-by", choices=("phrase", "speaker"), default=None,
                        help="Groupe par transcription (défaut TTS) ou par locuteur (défaut ASR ; évite les fuites entre splits)")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--min-duration", type=float, default=None)
    parser.add_argument("--max-duration", type=float, default=None)
    parser.add_argument("--include-flagged", action="store_true",
                        help="Inclure aux splits les WAV techniquement suspects ; à utiliser seulement après écoute manuelle")
    parser.add_argument("--keep-exact-duplicates", action="store_true",
                        help="Garder les fichiers audio dont le hash est identique à un autre fichier")
    args = parser.parse_args()

    if args.target_sample_rate is not None and args.target_sample_rate <= 0:
        parser.error("--target-sample-rate doit être un entier positif")
    if args.group_by is None:
        args.group_by = "speaker" if args.task == "asr" else "phrase"
    if args.min_duration is None:
        args.min_duration = 0.5 if args.task == "asr" else 0.35
    if args.max_duration is None:
        args.max_duration = 60.0 if args.task == "asr" else 20.0
    if args.min_duration <= 0 or args.max_duration <= args.min_duration:
        parser.error("Les bornes de durée sont invalides")
    if not args.input.is_file():
        parser.error(f"Archive introuvable : {args.input}")
    if args.out_dir.exists() and any(args.out_dir.iterdir()):
        parser.error(f"Le dossier de sortie n'est pas vide : {args.out_dir}. Choisissez un autre dossier ou videz-le.")
    audio_out = args.out_dir / "audio"

    errors: list[dict[str, str]] = []
    report: list[dict[str, Any]] = []
    eligible: list[dict[str, Any]] = []
    seen_hash: dict[str, str] = {}

    try:
        archive = zipfile.ZipFile(args.input)
    except zipfile.BadZipFile:
        parser.error("Le fichier d'entrée n'est pas un ZIP valide")

    with archive as zf, tempfile.TemporaryDirectory(prefix="zarma-prep-") as tmp_name:
        names = set(zf.namelist())
        if "metadata.csv" not in names:
            parser.error("metadata.csv est absent de l'export ZIP")
        with zf.open("metadata.csv") as meta_stream:
            import io
            text_stream = io.TextIOWrapper(meta_stream, encoding="utf-8-sig", newline="")
            reader = csv.DictReader(text_stream)
            if not reader.fieldnames or not REQUIRED_COLUMNS.issubset(set(reader.fieldnames)):
                parser.error(f"metadata.csv doit contenir les colonnes : {', '.join(sorted(REQUIRED_COLUMNS))}")
            raw_rows = list(reader)
        if not raw_rows:
            parser.error("metadata.csv ne contient aucun enregistrement.")
        if args.task == "asr":
            required_task_fields = {"asr_approved", "consent_asr"}
            if not required_task_fields.issubset(set(reader.fieldnames or [])):
                parser.error("Pour --task asr, metadata.csv doit contenir asr_approved et consent_asr. Utilisez un export Voix du Niger à consentements par tâche.")
            raw_rows = [row for row in raw_rows if
                        (row.get("asr_approved") or "").strip().lower() in {"1", "true", "yes"}
                        and (row.get("consent_asr") or "").strip().lower() in {"1", "true", "yes"}
                        and (row.get("text") or "").strip()]
        elif args.task == "tts":
            required_task_fields = {"tts_approved", "consent_tts"}
            if not required_task_fields.issubset(set(reader.fieldnames or [])):
                parser.error("Pour --task tts, metadata.csv doit contenir tts_approved et consent_tts. Utilisez un export Voix du Niger à consentements par tâche.")
            raw_rows = [row for row in raw_rows if
                        (row.get("tts_approved") or "").strip().lower() in {"1", "true", "yes"}
                        and (row.get("consent_tts") or "").strip().lower() in {"1", "true", "yes"}
                        and (row.get("task_type") or "read_speech") == "read_speech"]
        if not raw_rows:
            parser.error(f"Aucun enregistrement n'est approuvé pour la tâche {args.task or 'sélectionnée'}.")
        if args.task:
            missing_rights = [row.get("recording_id", "(ID absent)") for row in raw_rows
                              if rights_are_unverified(row.get("source_license") or "")]
            if missing_rights:
                parser.error(
                    f"{len(missing_rights)} enregistrement(s) approuvé(s) ont une licence/condition de réutilisation absente ou non vérifiée. "
                    "Ne prépare pas de corpus d'entraînement avant d'avoir vérifié les droits; exemples d'IDs : "
                    + ", ".join(missing_rights[:5])
                )
        source_languages = {
            (row.get("language_code") or "dje").strip().lower() or "dje"
            for row in raw_rows
        }
        supported_languages = SUPPORTED_LANGUAGE_CODES
        invalid_languages = source_languages - supported_languages
        if invalid_languages:
            parser.error(f"Codes langue non pris en charge dans metadata.csv : {', '.join(sorted(invalid_languages))}")
        if args.language_code is None and len(source_languages) > 1:
            parser.error(
                "L'export contient plusieurs langues (" + ", ".join(sorted(source_languages)) + "). "
                "Prépare un modèle par langue et relance avec --language-code <code> (voir /api/languages)."
            )
        selected_language = args.language_code or next(iter(source_languages))
        raw_rows = [
            row for row in raw_rows
            if ((row.get("language_code") or "dje").strip().lower() or "dje") == selected_language
        ]
        if not raw_rows:
            parser.error(f"Aucun enregistrement trouvé pour la langue {selected_language}.")
        # Create output only after input, language selection and ambiguity checks pass.
        # Otherwise a failed multi-language invocation would leave an empty output tree
        # that blocks a corrected retry using the same --out-dir.
        args.out_dir.mkdir(parents=True, exist_ok=True)
        audio_out.mkdir()
        temp_root = Path(tmp_name)
        for row_num, meta in enumerate(raw_rows, start=2):
            rec_id = (meta.get("recording_id") or "").strip()
            text = (meta.get("text") or "").strip()
            speaker = (meta.get("participant_code") or "").strip()
            task_type = (meta.get("task_type") or ("read_speech" if args.task == "tts" else "unknown")).strip()
            phrase_id = (meta.get("phrase_id") or "").strip()
            language_code = (meta.get("language_code") or "dje").strip().lower() or "dje"
            category = (meta.get("category") or "").strip()
            orthography_version = (meta.get("orthography_version") or "v1").strip()
            source_citation = (meta.get("source") or "").strip()
            source_license = (meta.get("source_license") or "").strip()
            gloss_fr = (meta.get("gloss_fr") or "").strip()
            native_reviewed_by = (meta.get("native_reviewed_by") or "").strip()
            native_reviewed_at = (meta.get("native_reviewed_at") or "").strip()
            member = (meta.get("audio_filename") or "").strip()
            try:
                if not rec_id or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", rec_id):
                    raise ValueError("recording_id absent ou invalide")
                if not text:
                    raise ValueError("transcription vide")
                if language_code not in SUPPORTED_LANGUAGE_CODES:
                    raise ValueError(f"code langue non pris en charge par le catalogue actuel : {language_code}")
                if not speaker:
                    raise ValueError("participant_code vide")
                member = safe_member_name(member)
                if member not in names:
                    raise ValueError(f"Audio absent du ZIP : {member}")
                source_wav = temp_root / f"source_{row_num}.wav"
                with zf.open(member) as source_stream, source_wav.open("wb") as target_stream:
                    shutil.copyfileobj(source_stream, target_stream)
                output_path = audio_out / f"{rec_id}.wav"
                maybe_resample(source_wav, output_path, args.target_sample_rate)
                stats = inspect_wav(output_path, args.min_duration, args.max_duration)
                sha = hashlib.sha256(output_path.read_bytes()).hexdigest()
                flags = list(stats["quality_flags"])
                is_duplicate = sha in seen_hash and not args.keep_exact_duplicates
                if is_duplicate:
                    flags.append("exact_duplicate_audio")
                else:
                    seen_hash.setdefault(sha, rec_id)
                included = (args.include_flagged or not stats["quality_flags"]) and not is_duplicate
                output = {
                    "recording_id": rec_id,
                    "phrase_id": phrase_id,
                    "task_type": task_type,
                    "language_code": language_code,
                    "category": category,
                    "orthography_version": orthography_version,
                    "source": source_citation,
                    "source_license": source_license,
                    "gloss_fr": gloss_fr,
                    "native_reviewed_by": native_reviewed_by,
                    "native_reviewed_at": native_reviewed_at,
                    "consent_version": (meta.get("consent_version") or "").strip(),
                    "consent_asr": (meta.get("consent_asr") or "").strip(),
                    "consent_tts": (meta.get("consent_tts") or "").strip(),
                    "recorded_at": (meta.get("recorded_at") or "").strip(),
                    "audio_path": f"audio/{rec_id}.wav",
                    "text": text,
                    "speaker_id": speaker,
                    "sample_rate": stats["sample_rate"],
                    "duration_seconds": stats["duration_seconds"],
                    "audio_sha256": sha,
                    "quality_flags": ";".join(flags),
                    "rms": stats["rms"],
                    "peak_abs": stats["peak_abs"],
                    "clipping_ratio": stats["clipping_ratio"],
                    "included_in_splits": str(included).lower(),
                    "source_row": row_num,
                }
                report.append(output)
                if included:
                    eligible.append(output)
            except Exception as exc:
                errors.append({"source_row": str(row_num), "recording_id": rec_id, "audio_filename": member,
                               "error": str(exc)})
                report.append({"source_row": row_num, "recording_id": rec_id, "audio_filename": member,
                               "text": text, "speaker_id": speaker, "quality_flags": f"invalid:{exc}",
                               "included_in_splits": "false"})

    if errors:
        write_csv(args.out_dir / "excluded_errors.csv", errors, ["source_row", "recording_id", "audio_filename", "error"])

    quality_fields = ["source_row", "recording_id", "phrase_id", "language_code", "category", "orthography_version", "source", "source_license", "gloss_fr", "native_reviewed_by", "native_reviewed_at", "audio_path", "text", "speaker_id", "sample_rate",
                      "duration_seconds", "rms", "peak_abs", "clipping_ratio", "audio_sha256", "quality_flags", "included_in_splits"]
    write_csv(args.out_dir / "quality_report.csv", report, quality_fields)
    if not eligible:
        print("Aucun enregistrement éligible. Consultez quality_report.csv et excluded_errors.csv.")
        return 2

    assignments = allocate_splits(eligible, args.group_by, args.seed)
    split_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in eligible:
        row["split"] = assignments[row["_split_group"]]
        split_rows[row["split"]].append(row)
    manifest_fields = OUTPUT_COLUMNS
    for split_name in ("train", "validation", "test"):
        rows = split_rows.get(split_name, [])
        write_csv(args.out_dir / f"{split_name}.csv", rows, manifest_fields)

    unique_phrase_groups = len({row["_split_group"] for row in eligible})
    summary = {
        "source_archive": args.input.name,
        "language_code": selected_language,
        "task": args.task or "unspecified_legacy_export",
        "group_by": args.group_by,
        "seed": args.seed,
        "target_sample_rate": args.target_sample_rate,
        "eligible_recordings": len(eligible),
        "excluded_or_flagged_recordings": len(report) - len(eligible),
        "technical_errors": len(errors),
        "unique_split_groups": unique_phrase_groups,
        "split_recordings": {name: len(split_rows.get(name, [])) for name in ("train", "validation", "test")},
        "warning": "Quality flags do not verify that the spoken audio matches its transcript. Listen to flagged files and validate language-specific text with fluent speakers. For ASR, verify speaker-disjoint splits and inspect transcript-normalization rules before interpreting WER/CER.",
    }
    (args.out_dir / "dataset_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"\nManifests et rapports écrits dans : {args.out_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
