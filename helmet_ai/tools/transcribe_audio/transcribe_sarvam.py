from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from sarvamai import SarvamAI


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_AUDIO_PATH = PROJECT_ROOT / "data" / "raw" / "dhoni_interview_01.mp3"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "transcripts"


@dataclass(frozen=True)
class TranscriptArtifact:
    source_audio: str
    model: str
    mode: str
    created_at: str
    response: Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Transcribe an audio file with Sarvam STT and save the raw response as JSON."
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
        help=f"Directory for transcript JSON output. Defaults to {DEFAULT_OUTPUT_DIR}.",
    )
    parser.add_argument(
        "--model",
        default=os.getenv("SARVAM_STT_MODEL", "saaras:v3"),
        help="Sarvam STT model name.",
    )
    parser.add_argument(
        "--mode",
        default=os.getenv("SARVAM_STT_MODE", "transcribe"),
        help="Sarvam STT mode.",
    )
    return parser.parse_args()


def load_environment() -> None:
    load_dotenv(PROJECT_ROOT / ".env.local")
    load_dotenv(PROJECT_ROOT / ".env")


def to_jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        return [to_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    return repr(value)


def build_output_path(audio_path: Path, output_dir: Path) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filename = f"{audio_path.stem}.{timestamp}.sarvam-transcript.json"
    return output_dir / filename


def main() -> None:
    load_environment()
    args = parse_args()

    api_key = (os.getenv("SARVAM_STT_TOKEN") or "").strip().strip('"').strip("'")
    if not api_key:
        raise RuntimeError("Missing SARVAM_STT_TOKEN in helmet_ai/.env.local")

    audio_path = Path(args.audio_path).resolve()
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")
    audio_size_mb = audio_path.stat().st_size / (1024 * 1024)
    if audio_size_mb > 25:
        batch_script = PROJECT_ROOT / "tools" / "transcribe_audio" / "transcribe_sarvam_batch.py"
        raise RuntimeError(
            f"{audio_path.name} is {audio_size_mb:.1f} MB. This script uses Sarvam's "
            "short REST STT endpoint, which is only for clips up to 30 seconds. "
            "Use the Batch STT script instead:\n\n"
            f'python "{batch_script}" "{audio_path}"'
        )

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    client = SarvamAI(api_subscription_key=api_key)
    with audio_path.open("rb") as audio_file:
        try:
            response = client.speech_to_text.transcribe(
                file=audio_file,
                model=args.model,
                mode=args.mode,
            )
        except Exception as error:
            status_code = getattr(error, "status_code", None)
            body = getattr(error, "body", "")
            if status_code == 403:
                raise RuntimeError(
                    "Sarvam rejected the transcription request with 403 Forbidden. "
                    "Check that SARVAM_STT_TOKEN is the correct active API subscription key "
                    "and that the key has access to speech_to_text.transcribe. "
                    f"The audio file is {audio_size_mb:.1f} MB; if the key is correct, "
                    "try a much smaller audio clip to rule out upload-size rejection."
                ) from error
            if status_code:
                raise RuntimeError(
                    f"Sarvam transcription failed with HTTP {status_code}: {body}"
                ) from error
            raise

    artifact = TranscriptArtifact(
        source_audio=str(audio_path),
        model=args.model,
        mode=args.mode,
        created_at=datetime.now(timezone.utc).isoformat(),
        response=to_jsonable(response),
    )

    output_path = build_output_path(audio_path, output_dir)
    output_path.write_text(
        json.dumps(asdict(artifact), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Wrote transcript: {output_path}")


if __name__ == "__main__":
    main()
