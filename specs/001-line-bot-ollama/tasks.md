# Tasks: LINE Bot with Local Ollama VLM Integration

**Input**: Design documents from `/specs/001-line-bot-ollama/`
**Prerequisites**: plan.md, spec.md, data-model.md, contracts/, quickstart.md

**Tests**: Tests are NOT explicitly requested in the specification, so test tasks are NOT included in this breakdown.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3, US4)
- Include exact file paths in descriptions

## Path Conventions

Single project structure at `/home/user/Desktop/Tom/AI-linebot/`:
- Source code: `src/`
- No tests directory (tests not requested)
- Specs: `specs/001-line-bot-ollama/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure

- [ ] T001 Create project directory structure (`src/`, `src/models/`, `src/services/`, `src/handlers/`, `src/utils/`)
- [ ] T002 Initialize Python project with requirements.txt (FastAPI, uvicorn, line-bot-sdk, ollama, google-api-python-client, Pillow, pydantic)
- [ ] T003 [P] Create .env.example file with required environment variables (LINE_CHANNEL_SECRET, LINE_CHANNEL_ACCESS_TOKEN, OLLAMA_BASE_URL, DRIVE_FOLDER_ID, ADMIN_USER_IDS)
- [ ] T004 [P] Setup logging configuration in src/utils/logger.py with structured logging format

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [ ] T005 Create configuration loader in src/config.py (load env vars, validate required settings)
- [ ] T006 [P] Create data models in src/models/llm_request.py (LLMRequest dataclass/Pydantic model per data-model.md)
- [ ] T007 [P] Create data models in src/models/prompt_config.py (PromptConfig entity)
- [ ] T008 [P] Create data models in src/models/rate_limit.py (RateLimitTracker entity)
- [ ] T009 Implement LINE webhook signature validation in src/utils/validators.py (FR-039, constant-time comparison)
- [ ] T010 Create rate limiting service in src/services/rate_limit_service.py (30 req/min per user, sliding window, FR-049, FR-050)
- [ ] T011 Setup FastAPI app structure in src/main.py (app initialization, health check endpoint, startup event handlers)
- [ ] T012 Create async queue service in src/services/queue_service.py (asyncio.Queue with max size 10, Semaphore(1) for concurrency control, FR-031 to FR-037)
- [ ] T013 Implement constant-running queue worker in src/main.py startup event (background worker: while True → queue.get() → process → reply, per plan.md ADR #4)

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - Text-Based AI Conversation (Priority: P1) 🎯 MVP

**Goal**: Users can ask the bot questions using `!hej [question]` and receive AI-generated responses from the local Ollama VLM.

**Independent Test**: Send `!hej What is the capital of France?` in a LINE group and receive an AI response. Verify multiple concurrent requests are queued properly.

### Implementation for User Story 1

- [ ] T014 [P] [US1] Implement Ollama service in src/services/ollama_service.py (API integration, text-only prompts, FR-006, FR-007, FR-011, FR-012)
- [ ] T015 [P] [US1] Implement LINE service in src/services/line_service.py (webhook event parsing, message sending via reply API, FR-038, FR-040, FR-041)
- [ ] T016 [US1] Create command parser in src/handlers/command_handler.py (detect `!hej` prefix, extract question text, route to handlers, FR-001 to FR-004)
- [ ] T017 [US1] Implement `!hej` command handler in src/handlers/hej_handler.py (create LLMRequest, check rate limit, enqueue, send "queued" feedback, FR-034, FR-035)
- [ ] T018 [US1] Integrate Ollama service with queue worker (dequeue LLMRequest, call Ollama API, handle response, FR-006, FR-007, FR-011)
- [ ] T019 [US1] Add error handling for LLM failures (Ollama offline/unresponsive, friendly error messages, logging, FR-043, FR-044)
- [ ] T020 [US1] Implement webhook endpoint in src/main.py (POST /webhook, signature validation, parse events, call command_handler, return 200 immediately)
- [ ] T021 [US1] Add input validation and sanitization (prevent prompt injection, validate prompt length max 4000 chars, FR-048, data-model.md validation rules)

**Checkpoint**: At this point, User Story 1 should be fully functional - basic text-based chatbot working end-to-end

---

## Phase 4: User Story 2 - Multimodal Conversation via Reply (Priority: P1)

**Goal**: Users can reply to existing messages (with images or text) using `!hej [question]` to analyze the referenced content.

**Independent Test**: Post an image in the group, reply to it with `!hej What's in this image?`, and receive analysis. Test with text message reply as well.

### Implementation for User Story 2

- [ ] T022 [P] [US2] Create image service in src/services/image_service.py (download from LINE Content API, in-memory BytesIO processing, resize to max 1920px, base64 encoding, FR-008, FR-009, FR-010, FR-042)
- [ ] T023 [US2] Extend command parser to detect reply-based interactions (check for quoted_message in webhook event, FR-013)
- [ ] T024 [US2] Implement quoted message content extraction in command_handler.py (extract text from referenced message, extract image message ID, FR-014, FR-015)
- [ ] T025 [US2] Extend LLMRequest creation for multimodal requests (populate context_text and/or context_image_base64 fields, FR-016)
- [ ] T026 [US2] Update Ollama service to support multimodal requests (send base64 image + text prompt to Ollama API, FR-010, FR-016)
- [ ] T027 [US2] Add validation for image size and format (pre-flight checks, handle oversized images, error messages, FR-008)
- [ ] T028 [US2] Implement error handling for missing/invalid quoted content (no text or image in referenced message, FR-013 to FR-015)

**Checkpoint**: At this point, User Stories 1 AND 2 should both work independently - text and multimodal AI chatbot fully operational

---

## Phase 5: User Story 3 - Collaborative Prompt Engineering (Priority: P2)

**Goal**: Non-technical users can edit `system_prompt.md` in Google Drive, and the bot automatically detects and applies changes within 30-60 seconds.

**Independent Test**: Edit `system_prompt.md` in Google Drive, wait up to 60 seconds, send `!hej` command, verify response reflects new prompt. Test `!reload` command for manual sync.

### Implementation for User Story 3

- [ ] T029 [P] [US3] Create data models in src/models/cached_asset.py (CachedAsset entity per data-model.md)
- [ ] T030 [US3] Implement Google Drive service in src/services/drive_service.py (authenticate via service account, download files, MD5 checksum tracking, FR-017, FR-018)
- [ ] T031 [US3] Implement prompt loading from Google Drive (download `system_prompt.md`, cache locally with timestamp, FR-019)
- [ ] T032 [US3] Create background polling worker for auto-sync (launch via startup event, check Drive every 30-60s, compare checksums, reload on changes, FR-022, FR-023, FR-024)
- [ ] T033 [US3] Implement `!reload` command handler in src/handlers/reload_handler.py (manually trigger Drive sync, FR-005, FR-025)
- [ ] T034 [US3] Add validation for prompt file format (markdown syntax check, handle invalid files gracefully, log warnings, FR-026)
- [ ] T035 [US3] Implement error handling for Drive sync failures (continue with cached data, log failures, don't crash bot, FR-045, FR-067)
- [ ] T036 [US3] Add admin notifications for Drive failures (send LINE push message to admin user IDs on critical failures, FR-046, FR-047)
- [ ] T037 [US3] Update hej_handler to use dynamic system_prompt from PromptConfig (replace hardcoded prompt with Drive-loaded version)

**Checkpoint**: User Story 3 complete - collaborative prompt editing functional with auto-sync and manual reload

---

## Phase 6: User Story 4 - Image Asset Retrieval (Priority: P3)

**Goal**: Users can request predefined images using `!img [keyword]`, with keyword mappings managed via Google Drive.

**Independent Test**: Configure `image_map.json` in Google Drive with a test mapping (e.g., "test" → "test_image.png"), send `!img test`, receive the image. Test error handling for unknown keywords.

### Implementation for User Story 4

- [ ] T038 [P] [US4] Create data models in src/models/image_mapping.py (ImageMapping entity per data-model.md)
- [ ] T039 [US4] Extend Drive service to load `image_map.json` (download, parse JSON, validate schema, FR-020, FR-026)
- [ ] T040 [US4] Implement image_map.json polling in background worker (check for updates every 30-60s alongside prompt sync, FR-022, FR-023)
- [ ] T041 [US4] Implement image download and caching in drive_service.py (download from `images/` folder, cache with MD5, LRU eviction, FR-021, FR-029)
- [ ] T042 [US4] Create `!img` command handler in src/handlers/img_handler.py (parse keyword, lookup in ImageMapping, retrieve from cache or download, FR-004, FR-027)
- [ ] T043 [US4] Implement LINE image sending in line_service.py (send binary image data via LINE API, FR-028)
- [ ] T044 [US4] Add error handling for unknown keywords (respond with available keyword list, FR-027)
- [ ] T045 [US4] Add error handling for missing image files (file referenced in JSON but not in Drive, notify admins, FR-046)
- [ ] T046 [US4] Update command_handler.py to route `!img` commands to img_handler

**Checkpoint**: All user stories complete - full feature set operational

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories and final deployment preparation

- [ ] T047 [P] Add comprehensive error logging across all services (structured logs with context, request IDs, user IDs for debugging)
- [ ] T048 Implement graceful shutdown handling (cleanup queue, close connections, finish in-flight requests)
- [ ] T049 [P] Add performance optimizations (minimize memory copying, efficient async/await, optimize queue throughput, FR-052, FR-053, FR-054)
- [ ] T050 [P] Create deployment documentation (systemd service file, Cloudflare Tunnel setup, environment setup per quickstart.md)
- [ ] T051 Validate all functional requirements are met (FR-001 through FR-054 checklist)
- [ ] T052 Add monitoring and health checks (Ollama connectivity, Drive API status, queue depth metrics)
- [ ] T053 Security hardening review (input sanitization, secrets management, webhook validation, FR-048, FR-066 to FR-070)
- [ ] T054 Run full end-to-end validation per quickstart.md (all commands, error scenarios, multi-user concurrent testing)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3-6)**: All depend on Foundational phase completion
  - US1 (P1): Can start after Foundational - No dependencies on other stories
  - US2 (P1): Can start after Foundational - Extends US1 but can be parallel
  - US3 (P2): Can start after Foundational - Independent of US1/US2
  - US4 (P3): Can start after Foundational - Independent of other stories
- **Polish (Phase 7)**: Depends on all desired user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Foundation required. Delivers: basic text chatbot
- **User Story 2 (P1)**: Foundation + extends US1 command handler and Ollama service. Delivers: multimodal capabilities
- **User Story 3 (P2)**: Foundation only. Independent implementation. Delivers: collaborative prompt editing
- **User Story 4 (P3)**: Foundation + may reuse Drive service from US3. Delivers: image library

### Within Each User Story

- **US1**: LINE service + Ollama service (parallel) → command_handler → hej_handler → webhook endpoint → validation
- **US2**: Image service (builds on US1's foundation) → extend command parsing → multimodal support
- **US3**: Drive service + cached_asset model (parallel) → polling worker → reload handler → admin alerts
- **US4**: ImageMapping model + extend Drive service → img_handler → error handling

### Parallel Opportunities

- **Setup (Phase 1)**: T003 and T004 can run in parallel
- **Foundational (Phase 2)**: T006, T007, T008 can run in parallel (all data models)
- **US1**: T014 and T015 can run in parallel (Ollama service + LINE service)
- **US2**: T022 can run in parallel with T023
- **US3**: T029 and T030 can run in parallel
- **US4**: T038 and T039 can run in parallel
- **Polish**: T047, T049, T050 can run in parallel
- **User stories can be worked on in parallel by different developers** after Foundational phase completes

---

## Implementation Strategy

### MVP First (User Stories 1 + 2 Only - Both P1)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL - blocks all stories)
3. Complete Phase 3: User Story 1 (Text-based chatbot)
4. Complete Phase 4: User Story 2 (Multimodal via reply)
5. **STOP and VALIDATE**: Test both P1 stories independently and together
6. Deploy and use - this is a fully functional AI chatbot with image analysis

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add User Story 1 → Test independently → **MVP v1: Text chatbot** ✅
3. Add User Story 2 → Test independently → **MVP v2: Multimodal chatbot** ✅
4. Add User Story 3 → Test independently → **v3: Collaborative prompts** ✅
5. Add User Story 4 → Test independently → **v4: Full feature set** ✅
6. Each story adds value without breaking previous stories

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together
2. Once Foundational is done:
   - **Developer A**: User Story 1 + 2 (P1 features, core chatbot)
   - **Developer B**: User Story 3 (P2, Drive integration)
   - **Developer C**: User Story 4 (P3, image library)
3. Stories complete and integrate independently
4. Final integration testing and polish

---

## Notes

- [P] tasks = different files, no dependencies, can run in parallel
- [Story] label maps task to specific user story for traceability (US1, US2, US3, US4)
- Each user story should be independently completable and testable
- Tests are NOT included (not requested in spec.md)
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- **Performance priority**: All implementations must optimize for speed, efficiency, minimal memory usage (FR-051 to FR-054)
- **Privacy requirement**: User images NEVER stored to disk, only in-memory processing (FR-009, FR-011, FR-052)
- **Deployment model**: Constantly-running service with startup workers, not per-request background tasks (plan.md ADR #4)
- Follow data-model.md for entity definitions and validation rules
- Follow contracts/ for API integration specifications
- Follow quickstart.md for deployment and validation procedures
