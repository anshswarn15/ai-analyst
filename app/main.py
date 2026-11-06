"""Application factory. Run with:  uvicorn app.main:app --reload"""
import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.agent.agent import DataAnalystAgent
from app.api.auth import router as auth_router
from app.api.routes import router
from app.config import Settings
from app.core.auth import AuthStore
from app.core.session import SessionStore
from app.llm.client import LLMClient, LLMError, OpenAICompatClient
from app.logging_config import setup_logging

log = logging.getLogger("datapilot")


def create_app(settings: Settings | None = None, llm: LLMClient | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    setup_logging(settings.log_level)

    app = FastAPI(title="DataPilot - AI Data Analyst", version="1.0.0",
                  description="Upload CSVs and analyse them in natural language.")
    app.state.settings = settings
    app.state.store = SessionStore(settings)
    app.state.agent = DataAnalystAgent(llm or OpenAICompatClient(settings), settings)
    app.state.auth = AuthStore(settings.auth_db_path, settings.session_secret)
    app.state.auth.bootstrap(settings.app_username, settings.app_password)

    @app.middleware("http")
    async def access_log(request: Request, call_next):
        rid, start = uuid.uuid4().hex[:8], time.monotonic()
        public_paths = {"/login", "/signup", "/logout", "/api/health"}
        if settings.auth_enabled and request.url.path not in public_paths:
            if not app.state.auth.verify_token(request.cookies.get("dp_auth")):
                if request.url.path.startswith("/api/"):
                    return JSONResponse({"detail": "Sign in required."}, status_code=401)
                return RedirectResponse("/login", status_code=303)
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        if request.url.path.startswith("/api"):
            log.info("http rid=%s method=%s path=%s status=%s ms=%d", rid, request.method,
                     request.url.path, response.status_code, (time.monotonic() - start) * 1000)
        return response

    @app.exception_handler(LLMError)
    async def llm_error_handler(_: Request, exc: LLMError):
        return JSONResponse({"detail": str(exc)}, status_code=502)

    @app.exception_handler(Exception)
    async def unhandled(_: Request, exc: Exception):
        log.exception("unhandled_error path=%s", _.url.path)
        return JSONResponse({"detail": "Internal server error."}, status_code=500)

    app.include_router(auth_router)
    app.include_router(router)

    if settings.static_dir.exists():
        app.mount("/static", StaticFiles(directory=settings.static_dir), name="static")

        @app.get("/", include_in_schema=False)
        def index():
            return FileResponse(settings.static_dir / "index.html")

    if not settings.llm_configured:
        log.warning("LLM not configured: set LLM_PROVIDER and an API key in .env (uploads/dashboard/SQL still work)")
    return app


app = create_app()
