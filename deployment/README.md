# Urban Insight Microservices

## Service split

- `frontend/`: React + Vite web app, now talking to `/api` instead of hard-coded local ports.
- `microservices/auth_service`: login and user management.
- `microservices/media_service`: file upload, file list, upload asset hosting.
- `microservices/analysis_service`: async analysis tasks, history, thumbnail hosting.
- `microservices/search_service`: structured search, natural-language search, image search.
- `microservices/insight_service`: stats, LLM insights, system settings.
- `microservices/agent_control_plane`: agent session/run/scheduled-task/approval control APIs.
- `microservices/agent_connector_email`: inbound email bridge, ACK/result delivery, approval email loop.
- `microservices/agent_executor`: internal execution service for agent tools, ready to evolve into a sandbox executor.
- `microservices/agent_runtime_manager`: background worker for claim/lease, heartbeat, and minimal API-only execution.
- `microservices/agent_scheduler`: scheduled-task dispatcher for 24x7 patrols and periodic jobs.

## Deployment

1. Build and start:

   ```bash
   docker compose up --build
   ```

2. Open:

   - Web UI: `http://localhost`
   - Monolith fallback: `uvicorn backend.main:app --reload`

## Runtime notes

- The default server deployment uses PostgreSQL via `DATABASE_URL`.
- Uploaded media and thumbnails are persisted in Docker volumes.
- `analysis-service` and `search-service` load the recognition model independently, so deploy them on machines with enough CPU/GPU and memory.
