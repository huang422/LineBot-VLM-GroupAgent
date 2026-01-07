# Implementation Plan: LINE Bot with Local Ollama VLM Integration

**Branch**: `001-line-bot-ollama` | **Date**: 2026-01-07 | **Spec**: [spec.md](./spec.md)

## Summary

Build a headless LINE group chatbot backend with keyword-triggered responses (`!hej`, `!img`, `!reload`) that integrates with locally-deployed Ollama gemma3 4B VLM on RTX 4080 GPU. The system uses Google Drive for collaborative prompt/image management with 30-60 second auto-sync polling, processes requests through an async queue (max 10, concurrency=1) to prevent GPU overload, and streams images directly to the LLM in-memory without local storage for privacy protection. Runs as a constantly-running FastAPI service, deployed via Cloudflare Tunnel for public webhook access, with no frontend interface required - all operations controlled via LINE messages.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: FastAPI, uvicorn, line-bot-sdk, ollama, google-api-python-client, Pillow, asyncio
**Storage**: Google Drive (prompts, images, config), local cache (Drive assets only, no user images)
**Testing**: pytest, pytest-asyncio
**Target Platform**: Linux server (local machine with RTX 4080 GPU)
**Project Type**: Headless backend service (no frontend, no web interface, LINE-only interaction)
**Deployment Model**: Constantly-running daemon service (systemd), startup triggers background workers
**Performance Goals**: <30s LLM response time, <60s auto-sync latency, minimal memory footprint
**Constraints**: Sequential LLM processing (concurrency=1), no local image persistence, 30 req/min per user
**Scale/Scope**: Private LINE group usage, ~10-20 concurrent users, 4B parameter VLM model

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

**Status**: No constitution defined yet - template placeholders only. This plan proceeds without constitutional constraints. Future iterations should establish principles for:
- Code simplicity standards
- Testing requirements (contract, integration, unit)
- Privacy-first data handling policies
- Performance benchmarking gates

## Project Structure

### Documentation (this feature)

```text
specs/001-line-bot-ollama/
├── plan.md              # This file
├── research.md          # Phase 0 research on key technologies
├── data-model.md        # Phase 1 data structures and entities
├── quickstart.md        # Phase 1 setup and deployment guide
├── contracts/           # Phase 1 API contracts
│   ├── line_webhook.yaml
│   ├── ollama_api.md
│   └── drive_sync.md
└── tasks.md             # Phase 2 (created by /speckit.tasks, not this command)
```

### Source Code (repository root)

```text
/home/user/Desktop/Tom/AI-linebot/
├── src/
│   ├── main.py                 # FastAPI app + startup event handlers
│   ├── config.py               # Environment config and constants
│   ├── models/
│   │   ├── __init__.py
│   │   ├── llm_request.py      # LLMRequest queue item
│   │   ├── prompt_config.py    # PromptConfig entity
│   │   ├── image_mapping.py    # ImageMapping entity
│   │   ├── cached_asset.py     # CachedAsset entity
│   │   └── rate_limit.py       # RateLimitTracker entity
│   ├── services/
│   │   ├── __init__.py
│   │   ├── line_service.py     # LINE webhook handling, message sending
│   │   ├── ollama_service.py   # Ollama API integration
│   │   ├── drive_service.py    # Google Drive sync and caching
│   │   ├── queue_service.py    # Async queue + constant worker
│   │   ├── image_service.py    # In-memory image processing
│   │   └── rate_limit_service.py  # Per-user rate limiting
│   ├── handlers/
│   │   ├── __init__.py
│   │   ├── command_handler.py  # Parse and route commands
│   │   ├── hej_handler.py      # !hej command logic
│   │   ├── img_handler.py      # !img command logic
│   │   └── reload_handler.py   # !reload command logic
│   └── utils/
│       ├── __init__.py
│       ├── validators.py       # Input validation, signature check
│       └── logger.py           # Structured logging
│
├── tests/
│   ├── contract/               # API contract tests
│   │   ├── test_line_webhook.py
│   │   ├── test_ollama_integration.py
│   │   └── test_drive_sync.py
│   ├── integration/            # End-to-end integration tests
│   │   ├── test_command_flow.py
│   │   └── test_queue_processing.py
│   └── unit/                   # Unit tests for services
│       ├── test_line_service.py
│       ├── test_ollama_service.py
│       ├── test_drive_service.py
│       ├── test_queue_service.py
│       ├── test_image_service.py
│       └── test_rate_limit_service.py
│
├── .env.example                # Environment variable template
├── requirements.txt            # Python dependencies
├── README.md                   # Project overview
└── Dockerfile                  # Optional containerization

Note: No frontend, no static file server, no web UI - purely webhook-driven backend
```

**Structure Decision**: Headless backend service with no frontend/UI components. System runs as a constantly-running daemon (via systemd) that launches background workers on startup. All user interaction happens exclusively through LINE messages - no web interface, no static file serving, no HTTP endpoints except webhook and health check. The modular service-based architecture allows clean separation of concerns while maintaining simplicity.

## Key Architectural Decisions

### 1. Sequential LLM Processing
**Decision**: Use asyncio.Semaphore(1) to enforce single concurrent LLM request
**Rationale**: RTX 4080 12GB VRAM prevents concurrent gemma3 4B VLM inference
**Trade-off**: Higher latency under load vs GPU stability

### 2. In-Memory Image Processing
**Decision**: Stream images from LINE → Pillow BytesIO → base64 → Ollama without disk writes
**Rationale**: Privacy requirement (FR-009) prohibits local image persistence
**Trade-off**: Slightly higher memory usage vs compliance with privacy constraints

### 3. Google Drive Polling vs Webhooks
**Decision**: Implement 30-60s polling loop with page token tracking
**Rationale**: Simpler setup than Drive webhooks (no domain verification, push notifications)
**Trade-off**: 60s max latency for prompt updates vs real-time webhook complexity

### 4. FastAPI Startup Workers + Background Tasks
**Decision**:
  - Launch persistent worker via `@app.on_event("startup")` for constant queue processing
  - Webhook handlers enqueue tasks and return HTTP 200 immediately
  - Worker runs continuously: `while True: await queue.get() → process → reply`
**Rationale**:
  - LINE webhook requires <15s response
  - Constant worker eliminates startup overhead per request
  - Single long-running task more efficient than per-request BackgroundTasks
**Trade-off**: Cannot use reply_token if processing exceeds 60s (fallback to push messages)

### 5. Local Cache for Drive Assets
**Decision**: Cache prompts, image_map.json, and static images locally with checksums
**Rationale**: Reduce Google Drive API quota consumption, improve response times
**Trade-off**: Eventual consistency (up to 60s stale data) vs API efficiency

## Risk Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| Ollama service crash | High - bot non-functional | Health check endpoint, auto-restart, admin alerts |
| Google Drive auth expiration | Medium - stale prompts | Cached fallback, auth refresh logic, monitoring |
| LINE webhook signature failure | High - security breach | Constant-time comparison, log all failures, alert admins |
| Queue overflow (>10 requests) | Medium - user frustration | Clear rejection message with retry guidance, queue metrics |
| Image too large for memory | Medium - OOM crash | Pre-flight size check, 1920px resize, graceful error response |
| Rate limit bypass | Low - resource exhaustion | Persistent tracking (Redis optional), IP fallback if user_id missing |

## Success Metrics

- **Functional**: All 54 functional requirements met (FR-001 to FR-054)
- **Performance**: <30s LLM response time, <60s auto-sync, <10s image retrieval
- **Reliability**: 99% uptime, zero GPU OOM errors, zero privacy violations (no disk writes)
- **Security**: 100% webhook signature validation, 30 req/min rate limit enforcement
- **Usability**: Non-technical users can edit prompts/images in Google Drive without developer help

## Next Steps

1. ✅ **Phase 0**: Research complete (see [research.md](./research.md))
2. ✅ **Phase 1**: Design complete (see [data-model.md](./data-model.md), [quickstart.md](./quickstart.md), [contracts/](./contracts/))
3. ⏭️ **Phase 2**: Run `/speckit.tasks` to generate actionable task breakdown
