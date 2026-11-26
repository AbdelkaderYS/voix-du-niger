#!/usr/bin/env python3
"""Prepare a dataset release from the Voix du Niger server and register its manifest.

Run this on the same trusted server/container as the FastAPI application. It never
puts a secret in the command line: set ZARMA_ADMIN_TOKEN in the environment.
"""
from __future__ import annotations
import argparse, json, os, re, subprocess, sys, tempfile, urllib.error, urllib.parse, urllib.request, zipfile
from pathlib import Path

CODES = {"ara", "bdm", "ful", "gux", "ha", "kau", "taq", "tda", "twq", "tuq", "dzg", "dje"}

def request_json(url: str, token: str, data: dict | None = None):
    body = None if data is None else json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="GET" if data is None else "POST", headers={
        "X-Admin-Token": token, "Accept": "application/json", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=180) as response:
            payload = response.read()
            return response.headers, json.loads(payload) if "json" in response.headers.get("Content-Type", "") else payload
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:1200]
        raise RuntimeError(f"API HTTP {exc.code}: {detail}") from exc

def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-id", required=True, help="ID de la release créée dans l’interface admin")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--data-dir", default=os.getenv("ZARMA_DATA_DIR", "./data"))
    parser.add_argument("--target-sample-rate", type=int, default=None, help="Ex. 16000 ou 22050; selon la recette modèle")
    parser.add_argument("--output-suffix", default="", help="Suffixe court pour une nouvelle révision de préparation, ex. rev2")
    parser.add_argument("--min-duration", type=float, default=None)
    parser.add_argument("--max-duration", type=float, default=None)
    args=parser.parse_args()
    token=os.getenv("ZARMA_ADMIN_TOKEN", "").strip()
    if not token or token == "replace-with-a-long-random-secret":
        parser.error("Définis ZARMA_ADMIN_TOKEN dans l’environnement du serveur; ne passe pas le secret comme argument CLI.")
    if not re.fullmatch(r"[a-f0-9-]{36}", args.release_id): parser.error("release-id invalide")
    base=args.base_url.rstrip("/")
    headers, result=request_json(base+"/api/admin/datasets/releases", token)
    releases=result.get("releases", [])
    release=next((item for item in releases if item.get("release_id")==args.release_id), None)
    if not release: raise RuntimeError("Release introuvable ou non visible avec cette clé.")
    if release.get("status") not in {"awaiting_preparation", "prepared", "rejected"}: raise RuntimeError(f"Statut incompatible : {release.get('status')}")
    if args.output_suffix and not re.fullmatch(r"[a-zA-Z0-9_-]{1,40}", args.output_suffix): parser.error("output-suffix : utilise 1 à 40 caractères alphanumériques, tiret ou underscore")
    task=release["task"]; lang=release["language_code"]; region=release.get("region_code", "ALL")
    if lang not in CODES: raise RuntimeError(f"Code langue non pris en charge dans ce script : {lang}")
    data_dir=Path(args.data_dir).expanduser().resolve()
    prepared=(data_dir/"prepared_datasets").resolve(); prepared.mkdir(parents=True, exist_ok=True)
    folder_name = args.release_id + (f"-{args.output_suffix}" if args.output_suffix else "")
    out_dir=(prepared/folder_name).resolve()
    if not out_dir.is_relative_to(prepared): raise RuntimeError("Chemin de sortie hors du dossier prepared_datasets")
    if out_dir.exists(): raise RuntimeError(f"Le dossier de sortie existe déjà : {out_dir}; déplace-le ou supprime-le explicitement avant une nouvelle préparation.")
    query=urllib.parse.urlencode({"task":task,"language_code":lang,"region_code":region})
    req=urllib.request.Request(base+"/api/admin/export?"+query,headers={"X-Admin-Token":token})
    with tempfile.TemporaryDirectory(prefix="voix-release-") as tmp:
        src=Path(tmp)/"approved-export.zip"
        try:
            with urllib.request.urlopen(req,timeout=300) as response: src.write_bytes(response.read())
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"Export HTTP {exc.code}: {exc.read().decode('utf-8','replace')[:1200]}") from exc
        with zipfile.ZipFile(src) as zf: bad=zf.testzip()
        if bad: raise RuntimeError(f"Archive d’export corrompue: {bad}")
        cmd=[sys.executable,str(Path(__file__).with_name("prepare_dataset.py")),"--input",str(src),"--out-dir",str(out_dir),"--task",task,"--language-code",lang]
        if args.target_sample_rate: cmd.extend(["--target-sample-rate",str(args.target_sample_rate)])
        if args.min_duration is not None: cmd.extend(["--min-duration",str(args.min_duration)])
        if args.max_duration is not None: cmd.extend(["--max-duration",str(args.max_duration)])
        print("Execution:", " ".join(cmd[1:]), flush=True)
        run=subprocess.run(cmd,check=False)
        if run.returncode: return run.returncode
    _, registered=request_json(base+f"/api/admin/datasets/releases/{args.release_id}/register",token,{
        "relative_path":folder_name,"license_status":"pending",
        "review_note":"Pipeline automatisé exécuté côté serveur. Contrôler le rapport qualité, la transcription, la licence et les partitions avant approbation."})
    print(json.dumps(registered,ensure_ascii=False,indent=2))
    print(f"Release préparée et inscrite. Langue: {lang}; région: {region}; dossier: {out_dir}")
    print("Étape suivante: dans le dashboard, vérifier les droits et le rapport, puis un validator habilité peut approuver la release.")
    return 0

if __name__ == "__main__":
    try: raise SystemExit(main())
    except (RuntimeError, OSError, zipfile.BadZipFile, json.JSONDecodeError) as exc:
        print(f"ERREUR: {exc}",file=sys.stderr); raise SystemExit(2)
