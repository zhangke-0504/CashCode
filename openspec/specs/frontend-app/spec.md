## ADDED Requirements

### Requirement: Frontend app bootstraps with Vite
The system SHALL use Vite + React 19 + TypeScript + Tailwind v4 as the client-side stack, located in `client/`.

#### Scenario: Development server starts
- **WHEN** developer runs `npm run dev` in `client/`
- **THEN** Vite dev server starts on port 5173 and hot-reload is active

#### Scenario: Production build succeeds
- **WHEN** developer runs `npm run build` in `client/`
- **THEN** `client/dist/` contains optimized static files ready for deployment

### Requirement: App connects to backend on startup
The system SHALL auto-connect to the WebSocket on `ws://127.0.0.1:8765/` and poll the REST API at `http://127.0.0.1:8000/`.

#### Scenario: Backend is running
- **WHEN** user opens the app and backend is up
- **THEN** app establishes WebSocket connection within 2 seconds and loads session list

#### Scenario: Backend is offline
- **WHEN** user opens the app and backend is down
- **THEN** app displays a connection error message and retries every 3 seconds

### Requirement: CashCode branding assets are used
The system SHALL display `CashLogo.png` as the application logo and use `CashMe.png` as the empty-state illustration.

#### Scenario: Logo in title bar
- **WHEN** app renders the title bar
- **THEN** CashLogo.png is displayed at 24×24px beside the text "CashCode"

#### Scenario: Empty state illustration
- **WHEN** no messages exist in the current session
- **THEN** CashMe.png is displayed centered in the chat area with welcome text
