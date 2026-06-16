# Architecture

`helmet_ai` keeps the product split into three runtime pieces.

## Backend

The backend owns service-to-service work:

- creates LiveKit rooms
- issues participant tokens
- dispatches the assistant agent
- stores ride-session context such as GPS
- exposes assistant-only tool endpoints such as directions

The assistant calls backend endpoints with `X-Assistant-Token`.

## Assistant Service

The assistant service owns real-time conversation:

- joins LiveKit rooms as the configured agent
- uses Sarvam STT and TTS
- uses short rider-safe responses
- calls backend tools instead of performing external API work directly

This same pattern should be used for Dhoni information flow: the assistant asks the backend/retrieval layer for relevant passages or current info, then speaks a concise answer.

## Mobile App

The Expo app owns phone-side permissions and context:

- microphone permission
- LiveKit audio connection
- push-to-talk controls
- location permission
- session context upload to backend

For the true phone-free target, this app should eventually support a BluArmor button trigger and background-ready session behavior, especially on Android.

## Data Pipeline

Dhoni source material should move through these stages:

1. `data/raw`: original MP3/audio and source files
2. `data/transcripts`: raw STT output with timestamps
3. `data/processed`: cleaned passages with metadata and topic tags
4. `data/knowledge_base`: retrieval/index artifacts used by assistant tools
