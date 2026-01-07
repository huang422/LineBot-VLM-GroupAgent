# Ollama API Integration Contract

**Feature**: [spec.md](../spec.md) | **Phase**: 1 (Design) | **Date**: 2026-01-07

## Purpose

This contract defines the integration between our LINE Bot and the locally deployed Ollama service running gemma3:4b VLM. It specifies request/response formats, error handling, and performance expectations.

## Service Configuration

### Endpoint
- **Base URL**: `http://localhost:11434`
- **API Version**: v1 (implicit, no version in URL)
- **Authentication**: None (local deployment, no auth required)
- **Network**: Localhost only (no external exposure)

### Model
- **Model Name**: `gemma3:4b`
- **Type**: Vision-Language Model (VLM)
- **Context Window**: 8192 tokens (typical for gemma3)
- **VRAM Usage**: ~4-5GB when loaded
- **Concurrent Limit**: 1 request at a time (enforced by our queue)

## API Endpoints

### 1. Generate Response (Text-Only)

**Endpoint**: `POST /api/generate`

**Request**:
```json
{
  "model": "gemma3:4b",
  "prompt": "What is the capital of France?",
  "system": "You are a helpful assistant in a LINE group chat. Respond concisely in Traditional Chinese or English based on the user's language.",
  "stream": false,
  "options": {
    "temperature": 0.7,
    "top_p": 0.9,
    "top_k": 40
  }
}
```

**Request Schema**:
- `model` (string, required): Model identifier (`gemma3:4b`)
- `prompt` (string, required): User question text
- `system` (string, optional): System prompt from Google Drive
- `stream` (boolean, optional): Enable streaming responses (default: false)
- `options` (object, optional): Generation parameters
  - `temperature` (float, 0.0-2.0): Randomness (default: 0.7)
  - `top_p` (float, 0.0-1.0): Nucleus sampling (default: 0.9)
  - `top_k` (int, 1-100): Top-K sampling (default: 40)
  - `num_predict` (int, optional): Max tokens to generate (default: -1, unlimited)

**Response** (Success):
```json
{
  "model": "gemma3:4b",
  "created_at": "2026-01-07T12:34:56.789012345Z",
  "response": "Paris is the capital of France.",
  "done": true,
  "context": [128, 256, 512, ...],
  "total_duration": 2500000000,
  "load_duration": 500000000,
  "prompt_eval_count": 20,
  "prompt_eval_duration": 1200000000,
  "eval_count": 12,
  "eval_duration": 800000000
}
```

**Response Schema**:
- `model` (string): Model used for generation
- `created_at` (string, ISO 8601): Response timestamp
- `response` (string): Generated text response
- `done` (boolean): Whether generation is complete
- `context` (array of int, optional): Context tokens (for conversation continuity)
- `total_duration` (int): Total time in nanoseconds
- `load_duration` (int): Model load time in nanoseconds
- `prompt_eval_count` (int): Number of tokens in prompt
- `prompt_eval_duration` (int): Prompt processing time in nanoseconds
- `eval_count` (int): Number of tokens generated
- `eval_duration` (int): Generation time in nanoseconds

**Performance Expectations**:
- Typical response time: 1-3 seconds for 20-50 token responses
- Model loading (first request): 0.5-1 second
- Subsequent requests: Model remains loaded in VRAM

---

### 2. Generate Response (Multimodal: Text + Image)

**Endpoint**: `POST /api/generate`

**Request**:
```json
{
  "model": "gemma3:4b",
  "prompt": "What's in this image? Describe it in detail.",
  "system": "You are a helpful assistant analyzing images in a LINE group chat. Respond concisely.",
  "images": ["iVBORw0KGgoAAAANSUhEUgAAAAUA..."],
  "stream": false,
  "options": {
    "temperature": 0.7
  }
}
```

**Additional Fields**:
- `images` (array of string, required for VLM): Base64-encoded image data
  - Format: Raw base64 string (no `data:image/png;base64,` prefix)
  - Supported formats: JPEG, PNG, WebP
  - Recommended max dimension: 1920px (resized before encoding)
  - Multiple images supported (array), but we use single image per request

**Response**: Same schema as text-only, but with image processing metrics:
```json
{
  "model": "gemma3:4b",
  "created_at": "2026-01-07T12:35:00.123456789Z",
  "response": "The image shows a cat sitting on a windowsill. The cat appears to be orange and white, looking outside. There's natural daylight coming through the window.",
  "done": true,
  "total_duration": 12000000000,
  "load_duration": 500000000,
  "prompt_eval_count": 850,
  "prompt_eval_duration": 5000000000,
  "eval_count": 45,
  "eval_duration": 6500000000
}
```

**Performance Expectations**:
- Typical response time: 5-15 seconds depending on image size
- Image encoding increases prompt token count (~800-1000 tokens per image)
- Higher VRAM usage during inference (~6-7GB peak)

---

### 3. Check Model Status (Health Check)

**Endpoint**: `GET /api/tags`

**Request**: No body required

**Response**:
```json
{
  "models": [
    {
      "name": "gemma3:4b",
      "modified_at": "2026-01-05T10:00:00.123456789Z",
      "size": 4200000000,
      "digest": "sha256:1234567890abcdef...",
      "details": {
        "format": "gguf",
        "family": "gemma",
        "parameter_size": "4B",
        "quantization_level": "Q4_K_M"
      }
    }
  ]
}
```

**Use Case**: Verify `gemma3:4b` model is available before processing requests

---

## Error Handling

### Error Response Format

All error responses follow this schema:
```json
{
  "error": "model 'gemma3:4b' not found"
}
```

### Common Error Scenarios

#### 1. Model Not Found (404)
**Trigger**: Requested model not installed
**Response**:
```json
{
  "error": "model 'gemma3:4b' not found"
}
```
**Bot Action**:
- Send error message to admin contacts: "Ollama model not found - please run `ollama pull gemma3:4b`"
- Reply to user: "⚠️ 系統維護中，請稍後再試 (System maintenance, please try later)"
- FR-043, FR-044, FR-046

#### 2. Service Unavailable (Connection Error)
**Trigger**: Ollama service not running or unreachable
**Response**: Connection timeout or refused
**Bot Action**:
- Log error with full stack trace
- Send admin alert: "Ollama service unreachable - check if service is running"
- Reply to user: "⚠️ AI 功能暫時無法使用 (AI service temporarily unavailable)"
- FR-043, FR-046

#### 3. Out of Memory (500)
**Trigger**: GPU OOM (should not happen with sequential processing)
**Response**:
```json
{
  "error": "out of memory"
}
```
**Bot Action**:
- CRITICAL alert to admins: "GPU OOM error detected - review queue implementation"
- Reply to user: "⚠️ 系統負載過高，請稍後再試 (System overloaded, retry later)"
- Remove request from queue
- FR-033, FR-046

#### 4. Context Length Exceeded (400)
**Trigger**: Prompt + image tokens exceed model context window
**Response**:
```json
{
  "error": "context length exceeded"
}
```
**Bot Action**:
- Reply to user: "⚠️ 提問太長，請簡化問題 (Question too long, please simplify)"
- Log warning with prompt length
- FR-044, FR-048

#### 5. Invalid Image Format (400)
**Trigger**: Malformed base64 or unsupported image format
**Response**:
```json
{
  "error": "invalid image format"
}
```
**Bot Action**:
- Reply to user: "⚠️ 圖片格式不支援 (Image format not supported)"
- Log error with image metadata
- FR-044

---

## Integration Code Examples

### Text-Only Request

```python
import aiohttp
import asyncio

async def generate_text_response(prompt: str, system_prompt: str) -> str:
    """Send text-only request to Ollama API"""
    payload = {
        "model": "gemma3:4b",
        "prompt": prompt,
        "system": system_prompt,
        "stream": False,
        "options": {
            "temperature": 0.7,
            "top_p": 0.9
        }
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(
            "http://localhost:11434/api/generate",
            json=payload,
            timeout=aiohttp.ClientTimeout(total=30)
        ) as resp:
            if resp.status != 200:
                error_data = await resp.json()
                raise OllamaError(f"Ollama API error: {error_data.get('error')}")

            data = await resp.json()
            return data['response']
```

### Multimodal Request

```python
async def generate_multimodal_response(
    prompt: str,
    system_prompt: str,
    image_base64: str
) -> str:
    """Send text + image request to Ollama API"""
    payload = {
        "model": "gemma3:4b",
        "prompt": prompt,
        "system": system_prompt,
        "images": [image_base64],  # Single image as array
        "stream": False,
        "options": {
            "temperature": 0.7
        }
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(
            "http://localhost:11434/api/generate",
            json=payload,
            timeout=aiohttp.ClientTimeout(total=30)  # 30s timeout
        ) as resp:
            if resp.status != 200:
                error_data = await resp.json()
                raise OllamaError(f"Ollama API error: {error_data.get('error')}")

            data = await resp.json()
            return data['response']
```

### Health Check

```python
async def check_ollama_health() -> bool:
    """Verify Ollama service and model availability"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "http://localhost:11434/api/tags",
                timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                if resp.status != 200:
                    return False

                data = await resp.json()
                models = data.get('models', [])
                return any(m['name'] == 'gemma3:4b' for m in models)
    except (aiohttp.ClientError, asyncio.TimeoutError):
        return False
```

---

## Performance Metrics

### Expected Response Times

| Scenario | Tokens | Expected Time | Max Acceptable |
|----------|--------|---------------|----------------|
| Simple text (20 tokens) | 20 | 1-2s | 5s |
| Complex text (100 tokens) | 100 | 3-5s | 10s |
| Image + short question | 850 + 20 | 8-12s | 20s |
| Image + detailed question | 850 + 50 | 12-18s | 30s |

**Success Criteria**: SC-001 requires <30s LLM response time

### Timeout Configuration

```python
# Recommended timeout values
OLLAMA_TIMEOUT_TEXT = 10  # seconds
OLLAMA_TIMEOUT_MULTIMODAL = 30  # seconds
OLLAMA_HEALTH_CHECK_TIMEOUT = 5  # seconds
```

---

## Contract Compliance

### Functional Requirements Coverage

- ✅ FR-006: Integrate with locally deployed Ollama service
- ✅ FR-007: Send text prompts in correct payload format
- ✅ FR-010: Encode images to base64 and send to Ollama API
- ✅ FR-011: Combine system prompts with user input
- ✅ FR-012: Handle LLM response streaming or blocking responses

### Testing Requirements

**Contract Tests** (to be implemented in `tests/contract/test_ollama_integration.py`):
1. Test text-only generation with valid prompt
2. Test multimodal generation with base64 image
3. Test error handling for model not found
4. Test error handling for service unreachable
5. Test health check endpoint
6. Test timeout handling (30s limit)
7. Test response parsing and validation

**Example Test Case**:
```python
@pytest.mark.asyncio
async def test_ollama_text_generation():
    """Verify text-only generation works"""
    response = await generate_text_response(
        prompt="What is 2+2?",
        system_prompt="You are a helpful assistant."
    )
    assert isinstance(response, str)
    assert len(response) > 0
    assert "4" in response.lower()
```

---

## Next Steps

✅ **Ollama API Contract Complete** → Proceed to Drive Sync Contract
