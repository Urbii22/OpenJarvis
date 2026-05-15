# Voice-First Desktop Shell

The new Tauri desktop shell is feature-flagged so the legacy UI remains the rollback path while the compact/expanded shell is validated.

## Enable

Use either toggle:

- Environment: `VITE_VOICE_SHELL_ENABLED=true`
- Browser/local Tauri storage: `localStorage.setItem('openjarvis-desktop-voice-shell-enabled', 'true')`

Disable with:

- `VITE_VOICE_SHELL_ENABLED=false`
- `localStorage.setItem('openjarvis-desktop-voice-shell-enabled', 'false')`

The shell opens in compact mode by default. The current mode is persisted in `openjarvis-desktop-voice-shell-mode`.

## Runtime Contract

The frontend normalizes voice/runtime events into:

- `READY`
- `LISTENING`
- `THINKING`
- `SPEAKING`
- `INTERRUPTED`
- `ERROR`

Supported payload fields include `voice_provider`, `voice_profile`, `ttfs_ms`, `total_synthesis_ms`, `mic_energy`, `mic_rms`, and `mic_peak`.

## Rollback

Set the feature flag to `false` or use the legacy UI button in the shell. The legacy routes and layout remain intact.
