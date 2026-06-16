# Helmet AI

Clean working folder for the phone-first helmet assistant product.

This folder is the new home for active development. The older `src`, `companion`, and `phone_first` folders are left untouched for reference.

## Layout

```text
helmet_ai/
  backend/             LiveKit session backend, GPS context, directions tools
  assistant_service/   LiveKit/Sarvam voice assistant worker
  mobile_app/          Expo companion app
  data/
    raw/               Put original Dhoni MP3/audio files here
    transcripts/       Raw STT transcript outputs
    processed/         Cleaned passages and metadata
    knowledge_base/    Searchable/indexed Dhoni corpus artifacts
  tools/
    transcribe_audio/  Audio-to-transcript pipeline scripts
    ingest_dhoni_corpus/
  docs/
```

## Secrets

Create a local env file:

```powershell
Copy-Item helmet_ai\.env.example helmet_ai\.env.local
```

Fill in at least:

- `LIVEKIT_URL`
- `LIVEKIT_API_KEY`
- `LIVEKIT_API_SECRET`
- `SARVAM_API_KEY`
- `SARVAM_STT_TOKEN`
- `ASSISTANT_BACKEND_TOKEN`

`MAPPLS_ACCESS_TOKEN` is optional for now because Mappls directions are parked until the production cleanup.

For the mobile app, Expo reads env from the app folder. Create:

```powershell
Copy-Item helmet_ai\mobile_app\.env.example helmet_ai\mobile_app\.env
```

Set `EXPO_PUBLIC_BACKEND_URL` to the backend URL reachable by the phone.

## Dhoni Audio

Place the 1-hour MP3 here:

```text
helmet_ai/data/raw/dhoni_interview_01.mp3
```

The transcription pipeline should write raw Sarvam STT output to:

```text
helmet_ai/data/transcripts/
```

Run the first-pass transcription script with:

```powershell
.venv\Scripts\python.exe helmet_ai\tools\transcribe_audio\transcribe_sarvam.py helmet_ai\data\raw\dhoni_interview_01.mp3
```

That script uses Sarvam's short REST STT endpoint, which is only for clips up to 30 seconds.
For the full Dhoni interview, use the Batch STT script:

```powershell
python helmet_ai\tools\transcribe_audio\transcribe_sarvam_batch.py helmet_ai\data\raw\dhoni_interview_01.mp3
```

The batch script defaults to `mode=codemix` and `language_code=hi-IN` so Hindi-English speech is preserved more naturally.

The script reads the STT key from:

```env
SARVAM_STT_TOKEN=...
```

Cleaned chunks and metadata should go to:

```text
helmet_ai/data/processed/
```

Search/index artifacts should go to:

```text
helmet_ai/data/knowledge_base/
```

## Run Order

Install Python dependencies from this folder:

```powershell
uv sync --project helmet_ai
```

Start the assistant service:

```powershell
uv run --project helmet_ai phone-first-assistant-stable
```

Start the backend:

```powershell
uv run --project helmet_ai phone-first-backend
```

Start the mobile app:

```powershell
Set-Location helmet_ai\mobile_app
npm install
npx expo start
```

## Current Capabilities

- LiveKit room/session creation
- Explicit assistant dispatch
- Sarvam STT/TTS voice loop
- Phone GPS context upload
- Mappls route summary tool

## Next Work

- Add `tools/transcribe_audio` for the Dhoni MP3.
- Add `tools/ingest_dhoni_corpus` to clean, chunk, tag, and index transcripts.
- Add assistant retrieval tools for Dhoni-first information flow.
