# Tasks: LINE Bot with Local Ollama VLM Integration

**Input**: Design documents from `/home/user/Desktop/Tom/AI-linebot/specs/001-line-bot-ollama/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Tests are NOT explicitly requested in the spec, so test tasks are excluded per the template guidance.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `- [ ] [ID] [P?] [Story?] Description with file path`

- **Checkbox**: ALWAYS starts with `- [ ]` (markdown checkbox)
- **Task ID**: Sequential number (T001, T002, etc.) in execution order
- **[P]**: OPTIONAL marker - included only if task is parallelizable (different files, no dependencies)
- **[Story]**: REQUIRED for user story phase tasks (e.g., [US1], [US2], [US3], [US4])
- **Description**: Clear action with exact file path

## Path Conventions

Single project structure at `/home/user/Desktop/Tom/AI-linebot/`:
- Source code: `src/`
- Specs: `specs/001-line-bot-ollama/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure

- [x] T001 Create project directory structure at /home/user/Desktop/Tom/AI-linebot/src/ with subdirectories: models/, services/, handlers/, utils/
- [x] T002 Initialize Python project with requirements.txt dependencies: FastAPI, uvicorn, line-bot-sdk, google-api-python-client, Pillow, aiohttp, pytest
- [x] T003 [P] Create .env.example file at /home/user/Desktop/Tom/AI-linebot/.env.example with environment variable template (LINE_CHANNEL_SECRET, LINE_CHANNEL_ACCESS_TOKEN, OLLAMA_BASE_URL, GOOGLE_DRIVE_FOLDER_ID, ADMIN_USER_IDS)
- [x] T004 [P] Create README.md at /home/user/Desktop/Tom/AI-linebot/README.md with project overview
- [x] T005 [P] Update .gitignore at /home/user/Desktop/Tom/AI-linebot/.gitignore to exclude .env, service_account_key.json, and cache directories

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T006 Create configuration module in src/config.py to load environment variables (LINE credentials, Ollama URL, Drive folder ID, queue settings, rate limits)
- [x] T007 [P] Create structured logger utility in src/utils/logger.py with support for log levels (INFO, WARNING, ERROR, CRITICAL)
- [x] T008 [P] Create validator utilities in src/utils/validators.py for LINE signature validation using HMAC-SHA256 constant-time comparison per line_webhook.yaml contract
- [x] T009 Create LLMRequest dataclass in src/models/llm_request.py per data-model.md with fields: request_id, user_id, group_id, prompt, system_prompt, context_text, context_image_base64, reply_token, timestamp, priority, max_retries
- [x] T010 [P] Create PromptConfig dataclass in src/models/prompt_config.py per data-model.md with fields: content, file_id, modified_time, md5_checksum, cached_at, version
- [x] T011 [P] Create ImageMapping dataclass in src/models/image_mapping.py per data-model.md with fields: keyword, filename, file_id, cached_path, md5_checksum
- [x] T012 [P] Create CachedAsset dataclass in src/models/cached_asset.py per data-model.md with fields: file_id, filename, local_path, md5_checksum, size_bytes, cached_at, last_accessed, content_type
- [x] T013 [P] Create RateLimitTracker dataclass in src/models/rate_limit.py per data-model.md with fields: user_id, request_timestamps, window_seconds, max_requests and methods: is_allowed(), record_request()
- [x] T014 Create FastAPI application skeleton in src/main.py with startup event handler and /health endpoint
- [x] T015 Implement Google Drive service initialization in src/services/drive_service.py with service account authentication per drive_sync.md contract

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - Text-Based AI Conversation (Priority: P1) 🎯 MVP

**Goal**: Users in a LINE group can ask the bot questions using `!hej` command and receive AI-generated responses from local Ollama VLM

**Independent Test**: Send `!hej What is the capital of France?` in a LINE group and receive an AI-generated response. Verify multiple concurrent requests are queued properly.

### Implementation for User Story 1

- [x] T016 [P] [US1] Implement Ollama service text-only generation in src/services/ollama_service.py with generate_text_response() method per ollama_api.md contract
- [x] T017 [P] [US1] Implement rate limiting service in src/services/rate_limit_service.py to enforce 30 requests per minute per user using RateLimitTracker
- [x] T018 [P] [US1] Implement async queue service in src/services/queue_service.py with asyncio.Queue(maxsize=10) and asyncio.Semaphore(1) for sequential LLM processing
- [x] T019 [US1] Implement LINE webhook signature validation in src/services/line_service.py per line_webhook.yaml contract
- [x] T020 [US1] Implement LINE reply functionality in src/services/line_service.py using reply_token API
- [x] T021 [US1] Implement command parser in src/handlers/command_handler.py to detect !hej prefix and extract question text
- [x] T022 [US1] Implement !hej handler in src/handlers/hej_handler.py to create LLMRequest and enqueue to queue_service
- [x] T023 [US1] Create constantly-running LLM worker in src/main.py using @app.on_event("startup") to launch background task that processes queue with while True loop
- [x] T024 [US1] Implement /webhook endpoint in src/main.py to receive LINE events, validate signature, parse commands, enqueue tasks, and return HTTP 200 within 1 second
- [x] T025 [US1] Add error handling in !hej handler at src/handlers/hej_handler.py to send admin alerts when Ollama service is unreachable and user-friendly error messages
- [x] T026 [US1] Add rate limit enforcement in src/handlers/command_handler.py to reject requests exceeding 30/minute with error message showing time until reset
- [x] T027 [US1] Add queue overflow handling in src/handlers/hej_handler.py to reject requests when queue is full with "系統忙碌中，請稍後再試" message
- [x] T028 [US1] Add input validation in src/handlers/hej_handler.py to sanitize user input and enforce 4000 character prompt limit

**Checkpoint**: At this point, User Story 1 should be fully functional - bot responds to `!hej` commands with AI-generated text responses

---

## Phase 4: User Story 2 - Multimodal Conversation via Reply (Priority: P1)

**Goal**: Users can ask the bot to analyze images or quoted text by replying to existing messages with the `!hej` command

**Independent Test**: Post an image in the group, reply to it with `!hej What's in this image?`, and receive an AI-generated image analysis. Test with text message reply as well.

### Implementation for User Story 2

- [x] T029 [P] [US2] Implement in-memory image processing service in src/services/image_service.py with download_and_process_image() method to stream LINE images to BytesIO, resize to max 1920px, and encode to base64 without disk writes
- [x] T030 [US2] Extend Ollama service in src/services/ollama_service.py to add generate_multimodal_response() method that sends text + base64 image per ollama_api.md contract
- [x] T031 [US2] Implement quoted message detection in src/handlers/command_handler.py to extract quotedMessageId from LINE webhook events
- [x] T032 [US2] Extend !hej handler in src/handlers/hej_handler.py to fetch quoted message content via LINE Content API when quotedMessageId is present
- [x] T033 [US2] Add text extraction logic in src/handlers/hej_handler.py to handle quoted text messages and populate context_text in LLMRequest
- [x] T034 [US2] Add image extraction logic in src/handlers/hej_handler.py to download quoted images via image_service and populate context_image_base64 in LLMRequest
- [x] T035 [US2] Update LLM worker in src/main.py to detect context_image_base64 and route to multimodal generation instead of text-only
- [x] T036 [US2] Add error handling in src/services/image_service.py for invalid image formats, unsupported content types, and images exceeding size limits with user-friendly error messages
- [x] T037 [US2] Add validation in src/handlers/hej_handler.py to return error when quotedMessageId references a message with neither text nor image

**Checkpoint**: At this point, User Stories 1 AND 2 should both work - bot handles text-only questions and multimodal image analysis via reply

---

## Phase 5: User Story 3 - Collaborative Prompt Engineering (Priority: P2)

**Goal**: Non-technical team members can edit the bot's system prompts by updating Markdown files in Google Drive, with changes automatically detected and applied within 60 seconds

**Independent Test**: Edit `system_prompt.md` in Google Drive, wait up to 60 seconds, and observe different bot behavior in subsequent `!hej` responses. Test manual `!reload` command.

### Implementation for User Story 3

- [x] T038 [P] [US3] Implement Google Drive polling worker in src/services/drive_service.py with check_for_changes() method using Changes API and page tokens per drive_sync.md contract
- [x] T039 [P] [US3] Implement file download functionality in src/services/drive_service.py with download_file_content() method per drive_sync.md contract
- [x] T040 [P] [US3] Implement local caching in src/services/drive_service.py to store downloaded files with MD5 checksums at /tmp/linebot_cache/
- [x] T041 [US3] Implement cache invalidation logic in src/services/drive_service.py to compare MD5 checksums and re-download when files change
- [x] T042 [US3] Create constantly-running Drive sync worker in src/main.py using @app.on_event("startup") to launch background task that polls every 30 seconds
- [x] T043 [US3] Load initial system_prompt.md from Google Drive on startup in src/services/drive_service.py and store in PromptConfig instance
- [x] T044 [US3] Implement automatic prompt update logic in src/services/drive_service.py to reload PromptConfig when system_prompt.md changes detected
- [x] T045 [US3] Update !hej handler in src/handlers/hej_handler.py to use current PromptConfig.content when creating LLMRequest
- [x] T046 [US3] Add error handling in src/services/drive_service.py to continue with cached data when Google Drive API is unavailable
- [x] T047 [US3] Add admin alerts in src/services/drive_service.py when Drive sync fails for more than 5 minutes
- [x] T048 [US3] Implement !reload command handler in src/handlers/reload_handler.py to force immediate re-download of all config files bypassing cache
- [x] T049 [US3] Add !reload command routing in src/handlers/command_handler.py to detect !reload prefix

**Checkpoint**: At this point, User Stories 1, 2, AND 3 should work - bot auto-syncs prompts from Google Drive and supports manual !reload

---

## Phase 6: User Story 4 - Image Asset Retrieval (Priority: P3)

**Goal**: Users can request predefined images using keyword commands like `!img 架構圖`, with mappings managed via Google Drive

**Independent Test**: Configure `image_map.json` in Google Drive with a keyword mapping, send `!img [keyword]` in LINE, and receive the corresponding image. Test error handling for unknown keywords.

### Implementation for User Story 4

- [x] T050 [P] [US4] Load image_map.json from Google Drive in src/services/drive_service.py and parse into list of ImageMapping objects
- [x] T051 [P] [US4] Implement JSON schema validation for image_map.json in src/services/drive_service.py per drive_sync.md contract
- [x] T052 [US4] Extend Drive sync worker in src/main.py to detect changes to image_map.json and reload mappings automatically
- [x] T053 [US4] Implement on-demand image download in src/services/drive_service.py to cache images from images/ folder when first requested
- [x] T054 [US4] Implement !img command handler in src/handlers/img_handler.py to parse keyword and lookup in ImageMapping list
- [x] T055 [US4] Add !img command routing in src/handlers/command_handler.py to detect !img prefix
- [x] T056 [US4] Implement LINE image sending in src/services/line_service.py to upload binary image data using push message API
- [x] T057 [US4] Add error handling in src/handlers/img_handler.py to return available keywords list when requested keyword not found
- [x] T058 [US4] Add error handling in src/handlers/img_handler.py to notify admins when referenced image file is missing from Google Drive
- [x] T059 [US4] Validate image file existence during initial image_map.json load in src/services/drive_service.py and log warnings for missing files

**Checkpoint**: All user stories should now be independently functional - bot supports text AI, multimodal analysis, auto-synced prompts, and keyword image retrieval

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [x] T060 [P] Add comprehensive logging throughout all services in src/services/ with appropriate log levels (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- [x] T061 [P] Implement admin notification utility in src/utils/admin_notifier.py to send LINE push messages to configured admin user IDs
- [x] T062 [P] Add performance metrics logging in src/main.py to track LLM response times, queue sizes, and Drive sync latency
- [x] T063 Add health check endpoint implementation in src/main.py to verify Ollama availability and Google Drive connectivity
- [x] T064 Create Dockerfile at /home/user/Desktop/Tom/AI-linebot/Dockerfile for optional containerization per plan.md structure
- [ ] T065 Validate all quickstart.md steps work end-to-end (Ollama setup, Google Drive folder structure, LINE channel configuration, Cloudflare Tunnel)
- [x] T066 Add input sanitization in src/handlers/command_handler.py to prevent prompt injection attacks
- [ ] T067 Implement LRU cache eviction in src/services/drive_service.py when cache exceeds 100MB per drive_sync.md contract
- [x] T068 Add timeout configurations in src/services/ollama_service.py for Ollama API calls (10s for text, 30s for multimodal) per ollama_api.md contract
- [x] T069 Optimize memory usage in src/services/image_service.py to ensure BytesIO objects are garbage collected after processing
- [x] T070 Add graceful shutdown handling in src/main.py to drain queue and complete in-flight requests before exit

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3-6)**: All depend on Foundational phase completion
  - User stories can then proceed in parallel (if staffed)
  - Or sequentially in priority order (US1 → US2 → US3 → US4)
- **Polish (Phase 7)**: Depends on all desired user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2) - No dependencies on other stories
- **User Story 2 (P1)**: Can start after Foundational (Phase 2) - Extends US1 but independently testable
- **User Story 3 (P2)**: Can start after Foundational (Phase 2) - Integrates with US1/US2 via PromptConfig but independently testable
- **User Story 4 (P3)**: Can start after Foundational (Phase 2) - Completely independent of other stories

### Within Each User Story

- Services before handlers (e.g., ollama_service before hej_handler)
- Core implementation before integration (e.g., queue_service before webhook endpoint)
- Error handling after happy path implementation
- Story complete before moving to next priority

### Parallel Opportunities

- All Setup tasks marked [P] can run in parallel (T003, T004, T005)
- All Foundational model creation tasks marked [P] can run in parallel (T007, T008, T010-T013)
- Once Foundational phase completes, different user stories can be worked on in parallel by different team members
- Within US1: T016, T017, T018 can run in parallel (different services)
- Within US2: T029, T030 can run in parallel after US1 completes
- Within US3: T038, T039, T040 can run in parallel (different Drive service methods)
- Within US4: T050, T051 can run in parallel (different Drive parsing logic)
- All Polish tasks marked [P] can run in parallel (T060, T061, T062)

---

## Parallel Example: User Story 1

```bash
# Launch core services for User Story 1 together:
Task T016: "Implement Ollama service text-only generation in src/services/ollama_service.py"
Task T017: "Implement rate limiting service in src/services/rate_limit_service.py"
Task T018: "Implement async queue service in src/services/queue_service.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 + User Story 2 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL - blocks all stories)
3. Complete Phase 3: User Story 1 (Text-based AI conversation)
4. Complete Phase 4: User Story 2 (Multimodal conversation via reply)
5. **STOP and VALIDATE**: Test US1 and US2 independently
6. Deploy/demo if ready - this delivers core AI chatbot functionality

**Rationale**: Both US1 and US2 are marked P1 (highest priority) and together provide the core value proposition - an AI-powered chatbot with vision capabilities. US3 (prompt management) and US4 (image retrieval) add convenience but aren't essential for initial deployment.

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add User Story 1 → Test independently → Basic text AI chatbot working
3. Add User Story 2 → Test independently → Multimodal vision capabilities added
4. **Deploy/Demo (MVP!)** - Core functionality complete
5. Add User Story 3 → Test independently → Collaborative prompt editing added
6. Add User Story 4 → Test independently → Keyword image retrieval added
7. Each story adds value without breaking previous stories

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together
2. Once Foundational is done:
   - Developer A: User Story 1 (T016-T028)
   - Developer B: User Story 2 (T029-T037, depends on some US1 components)
   - Developer C: User Story 3 (T038-T049)
   - Developer D: User Story 4 (T050-T059)
3. Stories complete and integrate independently
4. Team collaborates on Phase 7: Polish

---

## Summary

**Total Task Count**: 70 tasks across 7 phases

**Task Count per User Story**:
- Setup: 5 tasks
- Foundational: 10 tasks (BLOCKING)
- User Story 1 (P1): 13 tasks
- User Story 2 (P1): 9 tasks
- User Story 3 (P2): 12 tasks
- User Story 4 (P3): 10 tasks
- Polish: 11 tasks

**Parallel Opportunities Identified**: 15 tasks marked with [P] can run in parallel within their phases

**Independent Test Criteria**:
- US1: Send `!hej` command and receive AI response, verify queue handling
- US2: Reply to image/text with `!hej` and receive contextual analysis
- US3: Edit Drive prompt, wait 60s, verify behavior change, test `!reload`
- US4: Configure image mapping, request via `!img`, receive image

**Suggested MVP Scope**: User Story 1 + User Story 2 (both P1) = 22 implementation tasks after foundational setup

**Format Validation**: ✅ ALL tasks follow the strict checklist format: `- [ ] [TaskID] [P?] [Story?] Description with file path`

---

## Notes

- [P] tasks = different files, no dependencies, can run in parallel
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- **Tests are NOT included** - the spec does not explicitly request TDD or test generation
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- **Privacy compliance**: All image processing happens in-memory only (no disk writes for user images, FR-009, FR-015, SC-011)
- **Performance priority**: All implementation decisions prioritize efficiency, speed, and minimal memory usage (FR-051, FR-052, FR-053, FR-054)
- **Constantly-running daemon model**: Background workers start once at app startup and run forever in while True loops (LLM queue processor, Drive sync poller)
- Avoid: vague tasks, same file conflicts, cross-story dependencies that break independence
