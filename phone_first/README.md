# Phone-First Helmet Assistant

This subtree adds a parallel phone-first implementation without changing the
existing laptop-first worker or the original `companion/` app.

## What lives here

- `backend/`: issues LiveKit participant tokens and explicitly dispatches the assistant
- `assistant_service/`: the deployable LiveKit assistant worker registered for explicit dispatch
- `app/`: an Expo companion app variant that requests a session from the backend instead of asking the user for a token

## Quick start

1. Install Python dependencies for this subtree:

   ```powershell
   uv sync --project phone_first
   ```

2. Create local env files:

   ```powershell
   Copy-Item phone_first\backend\.env.example phone_first\backend\.env.local
   Copy-Item phone_first\assistant_service\.env.example phone_first\assistant_service\.env.local
   Copy-Item phone_first\app\.env.example phone_first\app\.env
   ```

3. Start the assistant service:

   ```powershell
   uv run --project phone_first phone-first-assistant-stable
   ```

4. Start the backend:

   ```powershell
   uv run --project phone_first phone-first-backend
   ```

5. Start the new mobile app from `phone_first\app`.

## Notes

- The backend creates a new LiveKit room per session and dispatches the assistant by `agent_name`.
- The assistant service must be running and registered before the app can receive replies.
- `phone-first-assistant-stable` uses LiveKit's `start` mode to avoid the Windows dev-reload watcher.
- The original code paths in the repo remain unchanged.

## Testing with LiveKit Cloud free tier

The easiest production-shaped test setup is:

- deploy only the assistant service to LiveKit Cloud
- keep the backend running locally on your laptop
- point both backend and app at your LiveKit Cloud project

That removes the flaky local assistant process from the loop while keeping the backend simple for testing.

### What runs where

- LiveKit Cloud: `assistant_service`
- Your laptop: `backend`
- Your phone: `app`

### Cloud test steps

1. Create a LiveKit Cloud project and note its:
   - `LIVEKIT_URL`
   - `LIVEKIT_API_KEY`
   - `LIVEKIT_API_SECRET`

2. Put those values in:
   - `backend/.env.local`
   - LiveKit Cloud agent secrets for the deployed assistant

3. Authenticate the CLI and create the cloud deployment from this directory:

   ```powershell
   cd D:\works\CODE\sarvam\phone_first
   lk cloud auth
   lk agent create
   ```

4. When prompted/configured, use the agent name:

   ```text
   helmet-phone-first-agent
   ```

   This must match `ASSISTANT_AGENT_NAME` in `backend/.env.local`.

5. Start the local backend:

   ```powershell
   uv run --project phone_first phone-first-backend
   ```

6. Point the mobile app at the local backend with `EXPO_PUBLIC_BACKEND_URL`.

7. Start the mobile app and test a session.

### Required secrets for the cloud assistant

Set these for the deployed assistant:

- `LIVEKIT_URL`
- `LIVEKIT_API_KEY`
- `LIVEKIT_API_SECRET`
- `SARVAM_API_KEY`
- `ASSISTANT_AGENT_NAME=helmet-phone-first-agent`

### Why this is the best free-tier test path

- You get the managed LiveKit Cloud agent runtime.
- You avoid running the assistant worker on Windows locally.
- You keep only one local service, the backend, which is easy to debug.
