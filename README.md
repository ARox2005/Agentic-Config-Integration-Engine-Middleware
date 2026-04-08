---
title: Agentic Config Integration Engine Middleware
emoji: 💻
colorFrom: gray
colorTo: purple
sdk: docker
pinned: false
---
# Agentic Config Integration Engine Middleware (Integration Gateway)

The runtime API gateway for FinSpark. It dynamically loads AI-generated JSON configuration blueprints and routes incoming requests to external APIs (like KYC and GST). It successfully enforces tenant isolation and API version coexistence.

## Architecture Context

```
┌──────────────┐        ┌──────────────────┐        ┌──────────────┐
│   Main App   │──────▶ │    Middleware     │──────▶ │   Mock APIs  │
│  (React UI)  │  HTTP  │ (FastAPI Gateway) │  HTTP  │  (FastAPI)   │
└──────────────┘        └──────────────────┘        └──────────────┘
                                ▲
                                │ reads configs from
                                │ /middleware/configs/{tenant_id}/
                                │
                        ┌───────────────────────────┐
                        │      AI Orchestrator      │
                        │ Backend: 8003             │
                        └───────────────────────────┘
```
**Role**: Runtime gateway — reads JSON configs, transforms data, forwards to APIs
**Tech**: FastAPI

## Prerequisites
- **Python 3.10+**

## Setup & Quick Start

1. Create a `.env` file in the project root if it doesn't exist (used for mock credential resolving):
```env
# Mock credentials (resolved by middleware at runtime)
KYC_PROVIDER_KEY=dummy-kyc-key-12345
GST_SERVICE_KEY=dummy-gst-key-67890
```
2. Create virtual env: `python -m venv venv`
3. Activate the virtual environment (`venv\Scripts\activate`)
4. Install dependencies: `pip install -r requirements.txt`
5. Run the server: `uvicorn src.main:app --reload --port 8002`
6. Verify: `curl http://localhost:8002/health`

## API Reference (Port 8002)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| POST | `/api/gateway/execute/{service_name}?tenant_id=` | Execute integration via deployed config (tenant-aware) |
| POST | `/api/gateway/simulate` | Simulate integration with inline config |

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Middleware returns 404 | Config file missing in `middleware/configs/{tenant_id}/`. Deploy from orchestrator first, and ensure the same tenant is selected in both UIs |
| `Credential not found` | Check `.env` file exists with the right keys |
| CORS errors in browser | Make sure backends have `allow_origins=["*"]` |

## Deployment
This FastAPI server requires a persistent file system to store Tenant configurations deployed by the Orchestrator. Docker deployment (e.g., Hugging Face Spaces, Render) mapping a volume to `/configs` is highly recommended.

## License
Built for the FinSpark Hackathon.
