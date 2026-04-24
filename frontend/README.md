# Frontend

This Flutter app is now wired for local inspection against the backend.

## Current flow
- Enter the backend base URL, defaulting to `http://127.0.0.1:8080`
- Click `Run Wikipedia Fixture Job`
- The app creates a backend job from the 30 bundled Wikipedia Markdown fixtures
- It then fetches the extracted graph and displays entities and relations
- Clicking a relation loads evidence and highlights the supporting source span

## Local run
1. Start the Go backend from `backend/`
2. Run the Flutter app from `frontend/`
3. Use either:
   - `/opt/homebrew/share/flutter/bin/flutter run -d macos`
   - `/opt/homebrew/share/flutter/bin/flutter run -d chrome`

## Current UI scope
- Local backend URL configuration
- Fixture-backed job creation
- Entity list and relation list
- Evidence detail panel with highlighted chunk text

File upload and richer graph visualization are the next frontend steps.
