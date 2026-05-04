# Helmet Voice Assistant Starter

This repo is the first working slice of the smart-helmet assistant:

- LiveKit handles realtime audio transport and session orchestration.
- Sarvam handles STT and TTS.
- A LiveKit LLM model handles reply generation.
- The agent is tuned for short, rider-safe spoken responses.

## What this starter does

It gives you a Python LiveKit worker that can:

- accept microphone audio from a LiveKit client
- transcribe with Sarvam STT
- generate concise spoken replies
- synthesize with Sarvam TTS
- return audio back to the client

This is the right first milestone before adding GPS, restaurant lookup, navigation, or the custom Dhoni voice.

## Project layout

```text
agent.py
src/helmet_assistant/config.py
src/helmet_assistant/agent.py
.env.example
```

## Prerequisites

Install these before trying to run the agent:

1. Python 3.10 or newer
2. `uv` package manager
3. LiveKit CLI

Recommended on Windows:

- Install Python from [python.org](https://www.python.org/downloads/windows/) instead of the Microsoft Store.
- Install `uv` from [Astral's installer docs](https://docs.astral.sh/uv/getting-started/installation/).
- Install LiveKit CLI from [LiveKit's Windows instructions](https://docs.livekit.io/home/cli/).

## Setup

1. Create a local env file:

```powershell
Copy-Item .env.example .env.local
```

2. Fill in:

- `LIVEKIT_URL`
- `LIVEKIT_API_KEY`
- `LIVEKIT_API_SECRET`
- `SARVAM_API_KEY`

3. Install dependencies:

```powershell
uv sync
```

4. Download model files required by the VAD and turn detector plugins:

```powershell
uv run agent.py download-files
```

## Run modes

Run locally in console mode:

```powershell
uv run agent.py console
```

Run in development mode and connect from the LiveKit playground or your mobile client:

```powershell
uv run agent.py dev
```

## Configuration

The starter uses these defaults:

- STT model: `saaras:v3`
- STT language: `en-IN`
- TTS model: `bulbul:v3`
- TTS speaker: `anushka`
- LLM model: `openai/gpt-4.1-mini`

You can override them in `.env.local`.

The LLM setting uses a LiveKit model descriptor. That keeps the starter simple and lets you switch later if you want a different provider.

## Suggested next steps

After this voice loop is running, build in this order:

1. Add a mobile companion client with push-to-talk.
2. Add latency and transcript logging.
3. Add one deterministic tool, such as `nearest_restaurant`.
4. Add GPS from the phone client.
5. Swap in the custom Sarvam voice once it is ready.

## Known limitations in this repo right now

- No mobile client yet
- No tool calling yet
- No analytics pipeline wiring yet
- No production deployment config yet

That is intentional. This repo is focused on getting the first end-to-end audio loop working.
