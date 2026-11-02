"""Lintel backend: the web app at /app, the JSON API at /api, the marketing site at /site.
Run: uvicorn backend.app:app --port 8002"""
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import db
from .errors import ApiError
from .routers import auth as auth_routes, firm, plugin, projects, rules

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"


@asynccontextmanager
async def lifespan(_):
    db.conn()  # open the database and apply migrations before the first request
    yield


app = FastAPI(title="Lintel", docs_url=None, redoc_url=None, lifespan=lifespan)
for r in (auth_routes, firm, projects, rules, plugin):
    app.include_router(r.router)
app.mount("/static", StaticFiles(directory=WEB), name="static")


def _marketing_site():
    """Built marketing site; built on the fly (into /tmp when the checkout is read-only, e.g. Vercel)."""
    built = ROOT / "site" / "public"
    if (built / "index.html").exists() or not (ROOT / "site" / "build.py").exists():
        return built
    import importlib.util
    spec = importlib.util.spec_from_file_location("lintel_site_build", ROOT / "site" / "build.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    try:
        return mod.main(built)
    except OSError:
        return mod.main(Path(os.environ.get("TMPDIR", "/tmp")) / "lintel-site")


SITE = _marketing_site()
if SITE.exists():
    app.mount("/site", StaticFiles(directory=SITE, html=True), name="site")


# ---- errors in one shape ---------------------------------------------------

@app.exception_handler(ApiError)
def api_error(_, exc: ApiError):
    headers = {"Retry-After": str(exc.extra["retry_after"])} if "retry_after" in exc.extra else None
    return JSONResponse(exc.body(), status_code=exc.status, headers=headers)


_CODES = {400: "bad_request", 401: "unauthenticated", 403: "forbidden", 404: "not_found", 405: "not_allowed",
          409: "conflict", 422: "invalid", 429: "rate_limited"}


@app.exception_handler(StarletteHTTPException)
def http_error(_, exc: StarletteHTTPException):
    msg = exc.detail if isinstance(exc.detail, str) and exc.status_code != 404 else (
        "Not found." if exc.status_code == 404 else "Request failed.")
    return JSONResponse({"error": {"code": _CODES.get(exc.status_code, "error"), "message": msg}}, status_code=exc.status_code)


@app.exception_handler(RequestValidationError)
def validation_error(_, exc: RequestValidationError):
    errs = exc.errors()
    if any(e.get("type") == "json_invalid" for e in errs):
        return JSONResponse({"error": {"code": "bad_request", "message": "Malformed JSON."}}, status_code=400)
    fields = {".".join(str(p) for p in e.get("loc", [])[1:]) or "body": e.get("msg", "Invalid.") for e in errs}
    return JSONResponse({"error": {"code": "invalid", "message": "Some fields need attention.", "fields": fields}}, status_code=422)


# ---- security headers ------------------------------------------------------

CSP = ("default-src 'self'; script-src 'self' https://cdn.jsdelivr.net; "
       "style-src 'self' https://fonts.googleapis.com 'unsafe-inline'; font-src https://fonts.gstatic.com; "
       "img-src 'self' data:; connect-src 'self'; frame-ancestors 'self'")


@app.middleware("http")
async def headers(request: Request, call_next):
    resp = await call_next(request)
    h = resp.headers
    h.setdefault("Content-Security-Policy", CSP)
    h.setdefault("X-Content-Type-Options", "nosniff")
    h.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    h.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    if request.url.scheme == "https":
        h.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    if request.url.path.startswith("/api/"):
        h.setdefault("Cache-Control", "no-store")
    return resp


# ---- pages -----------------------------------------------------------------

def shell():
    return FileResponse(WEB / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/", include_in_schema=False)
def index(panel: str | None = None):
    if panel:  # the Rhino plugin's WebView opens /?panel=<project key>
        return RedirectResponse(f"/app/p/{panel}?panel=1")
    return RedirectResponse("/site/" if SITE.exists() else "/app")


for path in ("/app", "/app/{rest:path}", "/login", "/signup", "/reset", "/invite/{token}"):
    app.add_api_route(path, shell, methods=["GET"], include_in_schema=False)
