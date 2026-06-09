# Proton Tools

Browser automation tools for Proton services.

## Files

- `signup.py` — Automated Proton Mail signup using CloakBridge Playwright browser
- `cloakbridge_server.py` — CloakBridge server (Camofox-compatible REST API via CloakBrowser/Playwright)

## Quick Start

```bash
# Start CloakBridge
python cloakbridge_server.py --port 9377

# Run signup
python signup.py
```

## CloakBridge Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/tabs` | POST | Create new tab |
| `/tabs/{id}/navigate` | POST | Navigate to URL |
| `/tabs/{id}/snapshot` | GET | Accessibility snapshot with refs |
| `/tabs/{id}/click` | POST | Click element by ref |
| `/tabs/{id}/type` | POST | Type text by ref |
| `/tabs/{id}/type-in-frame` | POST | Type text in iframe |
| `/tabs/{id}/evaluate` | POST | Execute JS in page |
| `/tabs/{id}/evaluate-in-frame` | POST | Execute JS in iframe |
| `/tabs/{id}/press` | POST | Press keyboard key |
| `/tabs/{id}/solve-turnstile` | POST | Solve Cloudflare Turnstile |
| `/sessions/{user}` | DELETE | Close all tabs |

## Requirements

- Python 3.11+
- Playwright or CloakBrowser
- uvicorn, fastapi
