"""Safe public errors; diagnostic locations stay in server logs, never responses."""
import logging
import re
from pathlib import Path
from uuid import uuid4

from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

logger = logging.getLogger('fitigo.errors')


def request_id(scope):
    state = scope.setdefault('state', {})
    if 'error_request_id' not in state:
        # Do not trust a client-provided ID or log arbitrary header contents.
        state['error_request_id'] = uuid4().hex
    return state['error_request_id']


def log_failure(scope, exc):
    """No exception messages, SQL parameters, request bodies/URLs or locals.

    Log frame locations without source lines. SQLAlchemy exception strings can
    contain passwords/payment data, so logger.exception/str(exc) are not safe.
    """
    frames = []
    trace = exc.__traceback__
    while trace:
        code = trace.tb_frame.f_code
        frames.append(f'{Path(code.co_filename).name}:{trace.tb_lineno}:{code.co_name}')
        trace = trace.tb_next
    logger.error('API failure request_id=%s exception_type=%s frames=%s',
                 request_id(scope), type(exc).__name__, ' > '.join(frames[-20:]))


def server_error(scope, status_code=500):
    message = ('Service temporarily unavailable. Try again shortly. For payments, refresh the existing payment status before retrying.'
               if status_code in {502, 503, 504} else
               'Unable to complete this request. Please try again. For payments, check the existing payment status before retrying.')
    code = 'SERVICE_UNAVAILABLE' if status_code in {502, 503, 504} else 'INTERNAL_SERVER_ERROR'
    return JSONResponse(status_code=status_code, content={'detail': message, 'code': code, 'request_id': request_id(scope)},
                        headers={'Cache-Control': 'no-store', 'X-Request-ID': request_id(scope)})


class SafeErrorsMiddleware:
    """Catch endpoint/dependency/middleware failures before Starlette debug output.

    Register inside CORS so even failure responses retain allowed-origin headers.
    Never append an exception to a response that has already started streaming.
    """
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        request_id(scope)
        started = False

        async def track(message):
            nonlocal started
            if message['type'] == 'http.response.start':
                started = True
            await send(message)

        try:
            await self.app(scope, receive, track)
        except Exception as exc:
            log_failure(scope, exc)
            if not started:
                await server_error(scope)(scope, receive, send)
            # For already-started responses, do not emit diagnostics or a second
            # response. Transport closes incomplete streams; background errors
            # are recorded only in the sanitized server log.


_diagnostic = re.compile(r'traceback|sqlalchemy|pymysql|alembic|\[SQL:|SELECT\s+.+\s+FROM|INSERT\s+INTO|'
                         r'UPDATE\s+.+\s+SET|[A-Za-z]:[\\/]|/(?:home|usr|var|etc)/|'
                         r'password_hash|(?:secret|password|authorization)\s*[:=]|Bearer\s+|'
                         r'://[^\s]+:[^\s]+@', re.I | re.S)


def public_detail(detail):
    fallback = 'Unable to complete this request. Check your input and try again.'
    if isinstance(detail, str):
        return detail if len(detail) <= 300 and not _diagnostic.search(detail) else fallback
    if isinstance(detail, dict):
        result = {}
        code = detail.get('code')
        if isinstance(code, str) and re.fullmatch(r'[A-Z][A-Z0-9_]{0,79}', code):
            result['code'] = code
        if isinstance(detail.get('message'), str):
            result['message'] = public_detail(detail['message'])
        return result or fallback
    return fallback


async def http_error(request, exc: HTTPException):
    if exc.status_code >= 500:
        log_failure(request.scope, exc)
        return server_error(request.scope, exc.status_code)
    # Keep only standard operational headers, never arbitrary diagnostic headers.
    headers = {k: v for k, v in (exc.headers or {}).items()
               if k.lower() in {'www-authenticate', 'retry-after', 'allow'}}
    headers.update({'Cache-Control': 'no-store', 'X-Request-ID': request_id(request.scope)})
    return JSONResponse(status_code=exc.status_code,
        content={'detail': public_detail(exc.detail), 'request_id': request_id(request.scope)}, headers=headers)


async def validation_error(request, exc: RequestValidationError):
    # Pydantic's input/ctx and custom-validator messages can echo complete request
    # bodies (including passwords). Return only schema-declared field names and
    # controlled messages, not exc.body or the original errors dictionary.
    fields = set()
    route = request.scope.get('route')
    dependant = getattr(route, 'dependant', None)

    def collect(dep):
        if dep is None:
            return
        for group in ('body_params', 'query_params', 'path_params', 'header_params', 'cookie_params'):
            for field in getattr(dep, group, []):
                fields.add(field.alias)
                fields.update(getattr(field.type_, 'model_fields', {}))
        for child in getattr(dep, 'dependencies', []):
            collect(child)

    collect(dependant)
    errors = []
    for error in exc.errors()[:50]:
        kind = error.get('type', '')
        message = {'missing': 'This field is required.', 'extra_forbidden': 'Unexpected field.',
                   'json_invalid': 'Request body must be valid JSON.'}.get(kind, 'Invalid value for this field.')
        loc = [part if isinstance(part, int) or part in fields or part in {'body', 'query', 'path', 'header', 'cookie'} else 'field'
               for part in error.get('loc', ()) if isinstance(part, (str, int))]
        errors.append({'loc': loc, 'msg': message, 'type': 'missing' if kind == 'missing' else 'validation_error'})
    return JSONResponse(status_code=422, content={'detail': errors, 'request_id': request_id(request.scope)},
                        headers={'Cache-Control': 'no-store', 'X-Request-ID': request_id(request.scope)})


async def unexpected_error(request, exc):
    # Fallback for failures outside the application middleware boundary.
    log_failure(request.scope, exc)
    return server_error(request.scope)