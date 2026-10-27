# Safe API error responses

## Changes

- FastAPI HTTP debug pages are always disabled, even if a local `.env` retains
  `DEBUG=true`. The setting default/example are now false. Uvicorn reload is
  independent and remains usable for development.
- Unexpected endpoint/dependency/response-serialization errors return JSON 500
  with a generic message, stable error code and generated request ID. Explicit
  5xx HTTP exceptions are sanitized too; original exception details are never
  sent to the browser. Payment messages advise checking the existing order
  before retrying, not blindly submitting another charge.
- The ASGI error boundary sits inside CORS. Failures retain allowed-origin
  headers and expose X-Request-ID. Error responses are no-store.
- Expected 4xx status codes and short public business messages are preserved.
  Structured errors retain only code/message; internal fields are removed.
  Diagnostic-looking text is replaced. Authentication, Allow and Retry-After
  headers remain supported. Developers must still never place secrets in public
  business messages: heuristic text detection is defense-in-depth, not a license
  to return arbitrary exception strings.
- Validation errors preserve declared field locations with controlled messages;
  submitted input, exception context, custom messages, unknown field names and
  raw request bodies are not echoed. This prevents password/token leaks from
  Pydantic's normal error objects.
- `/health/db` no longer returns str(exception). Database unavailable/not
  configured returns safe HTTP 503 with healthy=false; healthy still returns 200.
- Check-in operational 5xx failures use the central handler rather than being
  converted into an HTTP 200 QR rejection containing server detail.
- SQLAlchemy engine hides bound parameters in its exception formatting.

## Server diagnostics

Logger `fitigo.errors` records the generated request ID, exception class and
source frame locations (basename, line, function). It deliberately does NOT log
exception messages, source-code lines, locals, SQL/parameters, request bodies,
headers, tokens, query strings or full local paths. Search private server logs
using the response request_id. No public diagnostic endpoint was added.

Already-started streaming responses cannot be replaced with a new JSON response;
the middleware logs safely without appending diagnostics. Background failures
likewise do not append details to the original successful response. Startup
failures remain server-side and may prevent the server starting at all.

This protects application-generated errors, not arbitrary failures emitted by
an upstream proxy, hosting service or a future route that returns sensitive data
as a successful response. API documentation remains unchanged. Browser-visible
frontend JavaScript is public by design; server exception/source disclosure is
what this change addresses.

## Validation

- 151 tests passed (exit 0): safe failures, health, wallet/history, profile edits,
  password recovery, Razorpay/Cashfree, QR/scanner and analytics.
- Tests force debug=true in settings and exercise JSON/HTML Accept headers,
  database exceptions, response validation, dependencies, backgrounds, 4xx/5xx,
  CORS, request IDs, and validation secrets. Actual wallet/history route DB
  dependencies are replaced with failures in tests; no production schema was
  deliberately damaged.
- Two duplicate local FitiGo Uvicorn process trees on port 8000 were restarted as
  one instance so current code is active. Live requests through localhost:5173
  confirmed safe 404 and 422 JSON with request IDs and no echoed invalid email.
  Database health remained healthy. No schema/data changes for this task.

Run:

```powershell
Set-Location 'C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend'
& ./.venv/Scripts/python.exe -m pytest tests/test_safe_errors.py tests/test_health.py -q
```

Files:
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/core/errors.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/main.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/core/config.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/database/session.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/routers/health.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/app/routers/checkins.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/tests/test_safe_errors.py`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/.env.example`
- `C:/Users/ckishor/.cline/data/workspaces/chat/fitigo/backend/SAFE_API_ERRORS.md`