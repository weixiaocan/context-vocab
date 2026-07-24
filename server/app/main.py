from __future__ import annotations

import logging
from urllib.parse import quote

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel

from app.api import collect, dictionary, review
from app.auth import COOKIE_NAME, valid_access_token
from app.config import load_settings
from app.db import connect, init_db
from app.scheduler import start_scheduler

logging.basicConfig(level=logging.INFO)


class LoginRequest(BaseModel):
    token: str


def create_app() -> FastAPI:
    settings = load_settings()
    app = FastAPI(title="Vocab Flashcard")
    app.state.settings = settings
    app.state.db = connect(settings.db_path)
    init_db(app.state.db)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def require_access_token(request, call_next):
        if request.method == "OPTIONS" or request.url.path in {"/health", "/login"}:
            return await call_next(request)
        supplied = request.headers.get("X-Access-Token") or request.cookies.get(COOKIE_NAME)
        if valid_access_token(settings.access_token, supplied):
            return await call_next(request)
        if request.method == "GET" and request.url.path.startswith("/review"):
            destination = quote(request.url.path, safe="/")
            return RedirectResponse(f"/login?next={destination}", status_code=303)
        return JSONResponse({"detail": "invalid access token"}, status_code=401)

    app.include_router(dictionary.router)
    app.include_router(collect.router)
    app.include_router(review.router)

    @app.get("/health")
    def health() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/login", response_class=HTMLResponse)
    def login_page() -> HTMLResponse:
        return HTMLResponse(
            """
            <!doctype html>
            <html lang="zh-CN"><head><meta charset="utf-8">
            <meta name="viewport" content="width=device-width,initial-scale=1">
            <title>生词卡登录</title>
            <style>
            body{max-width:420px;margin:72px auto;padding:0 20px;font:16px/1.6 system-ui;color:#252723}
            input,button{width:100%;box-sizing:border-box;padding:12px;border-radius:9px;font:inherit}
            input{border:1px solid #bbb}button{margin-top:14px;border:0;background:#526849;color:#fff}
            #error{color:#a33}
            </style></head><body><h1>生词卡</h1><p>此设备首次访问，请输入访问密钥。</p>
            <input id="token" type="password" autocomplete="current-password">
            <button id="login">登录并记住此设备</button><p id="error"></p>
            <script>
            const requested=new URLSearchParams(location.search).get("next")||"/review";
            const next=requested.startsWith("/")&&!requested.startsWith("//")?requested:"/review";
            document.getElementById("login").onclick=async()=>{
              const token=document.getElementById("token").value;
              const response=await fetch("/login",{method:"POST",headers:{"Content-Type":"application/json"},
                body:JSON.stringify({token})});
              if(response.ok)location.href=next;
              else document.getElementById("error").textContent="访问密钥不正确";
            };
            </script></body></html>
            """
        )

    @app.post("/login")
    def login(payload: LoginRequest) -> JSONResponse:
        if not valid_access_token(settings.access_token, payload.token):
            return JSONResponse({"detail": "invalid access token"}, status_code=401)
        response = JSONResponse({"ok": True})
        response.set_cookie(
            COOKIE_NAME,
            payload.token,
            max_age=180 * 24 * 60 * 60,
            httponly=True,
            secure=settings.public_base_url.startswith("https://"),
            samesite="strict",
        )
        return response

    @app.on_event("startup")
    def on_startup() -> None:
        app.state.scheduler = start_scheduler(settings)

    @app.on_event("shutdown")
    def on_shutdown() -> None:
        app.state.db.close()
        scheduler = getattr(app.state, "scheduler", None)
        if scheduler:
            scheduler.shutdown(wait=False)

    return app


app = create_app()
