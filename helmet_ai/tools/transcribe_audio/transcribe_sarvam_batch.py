from __future__ import annotations

import argparse
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from sarvamai import SarvamAI


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_AUDIO_PATH = PROJECT_ROOT / "data" / "raw" / "dhoni_interview_01.mp3"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "transcripts"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Transcribe long audio with Sarvam Batch STT and download the results."
    )
    parser.add_argument(
        "audio_path",
        nargs="?",
        default=str(DEFAULT_AUDIO_PATH),
        help=f"Audio file to transcribe. Defaults to {DEFAULT_AUDIO_PATH}.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help=f"Directory for downloaded transcript output. Defaults to {DEFAULT_OUTPUT_DIR}.",
    )
    parser.add_argument(
        "--model",
        default=os.getenv("SARVAM_STT_MODEL", "saaras:v3"),
        help="Sarvam STT model name.",
    )
    parser.add_argument(
        "--mode",
        default=os.getenv("SARVAM_STT_MODE", "codemix"),
        choices=("transcribe", "translate", "verbatim", "translit", "codemix"),
        help=(
            "Sarvam STT mode. codemix is the default because it handles Hindi-English "
            "speech more naturally than plain transcribe."
        ),
    )
    parser.add_argument(
        "--language-code",
        default=os.getenv("SARVAM_STT_LANGUAGE", "hi-IN"),
        help="Source language code. hi-IN is a good default for Hindi-English code-mixed audio.",
    )
    parser.add_argument(
        "--diarization",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable speaker diarization. Defaults to enabled.",
    )
    parser.add_argument(
        "--num-speakers",
        type=int,
        default=int(os.getenv("SARVAM_STT_NUM_SPEAKERS", "2")),
        help="Expected speaker count for diarization.",
    )
    return parser.parse_args()


def load_environment() -> None:
    load_dotenv(PROJECT_ROOT / ".env.local")
    load_dotenv(PROJECT_ROOT / ".env")


def write_job_manifest(
    *,
    output_dir: Path,
    audio_path: Path,
    model: str,
    mode: str,
    language_code: str,
    diarization: bool,
    num_speakers: int,
    file_results: Any,
) -> Path:
    manifest_path = output_dir / "job_manifest.json"
    manifest = {
        "source_audio": str(audio_path),
        "model": model,
        "mode": mode,
        "language_code": language_code,
        "with_diarization": diarization,
        "num_speakers": num_speakers,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "file_results": file_results,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest_path


def main() -> None:
    load_environment()
    args = parse_args()

    api_key = (os.getenv("SARVAM_STT_TOKEN") or "").strip().strip('"').strip("'")
    if not api_key:
        raise RuntimeError("Missing SARVAM_STT_TOKEN in helmet_ai/.env.local")

    audio_path = Path(args.audio_path).resolve()
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = Path(args.output_dir).resolve() / f"{audio_path.stem}.{timestamp}.sarvam-batch"
    output_dir.mkdir(parents=True, exist_ok=False)

    client = SarvamAI(api_subscription_key=api_key)
    job = client.speech_to_text_job.create_job(
        model=args.model,
        mode=args.mode,
        language_code=args.language_code,
        with_diarization=args.diarization,
        num_speakers=args.num_speakers,
    )

    print(f"Created Sarvam batch job for {audio_path.name}")
    print(f"Uploading: {audio_path}")
    job.upload_files(file_paths=[str(audio_path)])

    print("Starting job. This can take several minutes for long audio.")
    job.start()
    job.wait_until_complete()

    file_results = job.get_file_results()
    manifest_path = write_job_manifest(
        output_dir=output_dir,
        audio_path=audio_path,
        model=args.model,
        mode=args.mode,
        language_code=args.language_code,
        diarization=args.diarization,
        num_speakers=args.num_speakers,
        file_results=file_results,
    )

    successful = file_results.get("successful", []) if isinstance(file_results, dict) else []
    failed = file_results.get("failed", []) if isinstance(file_results, dict) else []

    if failed:
        print(f"Failed files: {len(failed)}")
        print(json.dumps(failed, ensure_ascii=False, indent=2))

    if not successful:
        raise RuntimeError(f"No successful transcript files. Wrote manifest: {manifest_path}")

    print(f"Downloading {len(successful)} transcript output file(s) to: {output_dir}")
    job.download_outputs(output_dir=str(output_dir))

    latest_dir = Path(args.output_dir).resolve() / "latest_sarvam_batch"
    if latest_dir.exists():
        shutil.rmtree(latest_dir)
    shutil.copytree(output_dir, latest_dir)

    print(f"Wrote manifest: {manifest_path}")
    print(f"Wrote latest copy: {latest_dir}")


if __name__ == "__main__":
    main()
