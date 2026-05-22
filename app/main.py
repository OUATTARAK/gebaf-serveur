from pathlib import Path
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import SESSION_SECRET
from app.db import init_schema, SessionLocal
from app.models import User
from app.routes import templates
from app.routes.auth import router as auth_router
from app.routes.dashboard import router as dashboard_router
from app.routes.chantiers import router as chantiers_router
from app.routes.clients import router as clients_router
from app.routes.contacts import router as contacts_router
from app.routes.devis import router as devis_router
from app.routes.factures import router as factures_router
from app.routes.depenses import router as depenses_router
from app.routes.documents import router as documents_router
from app.routes.planning import router as planning_router
from app.routes.heures import router as heures_router
from app.routes.rapports import router as rapports_router
from app.routes.admin import router as admin_router
from app.routes.imports import router as imports_router

app = FastAPI(title="Suivi de chantiers")

STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

PUBLIC_PATHS = {"/login", "/health", "/sw.js", "/manifest.json", "/favicon.ico"}


# PWA : service worker + manifest servis depuis la racine pour scope global
from fastapi.responses import FileResponse

@app.get("/sw.js", include_in_schema=False)
def service_worker():
    return FileResponse(STATIC_DIR / "sw.js", media_type="application/javascript",
                        headers={"Service-Worker-Allowed": "/", "Cache-Control": "no-cache"})

@app.get("/manifest.json", include_in_schema=False)
def manifest():
    return FileResponse(STATIC_DIR / "manifest.json", media_type="application/manifest+json")

@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return FileResponse(STATIC_DIR / "icons" / "favicon-64.png", media_type="image/png")


@app.middleware("http")
async def auth_redirect(request: Request, call_next):
    path = request.url.path
    if path.startswith("/static") or path in PUBLIC_PATHS:
        return await call_next(request)
    user_id = request.session.get("user_id")
    if not user_id and path != "/login":
        return RedirectResponse(url=f"/login?next={path}", status_code=303)
    # Charge l'utilisateur dans request.state pour les templates
    if user_id:
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.id == user_id, User.active == True).first()  # noqa
            request.state.user = user
            if not user:
                request.session.clear()
                return RedirectResponse(url="/login", status_code=303)
        finally:
            db.close()
    return await call_next(request)


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    if exc.status_code in (401, 403):
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "user": getattr(request.state, "user", None),
             "code": exc.status_code, "detail": exc.detail or "Accès refusé"},
            status_code=exc.status_code,
        )
    if exc.status_code == 404:
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "user": getattr(request.state, "user", None),
             "code": 404, "detail": "Page ou ressource introuvable"},
            status_code=404,
        )
    return HTMLResponse(f"<h1>{exc.status_code}</h1><p>{exc.detail}</p>", status_code=exc.status_code)


# Registration des routes
app.include_router(auth_router)
app.include_router(dashboard_router)
app.include_router(chantiers_router)
app.include_router(clients_router)
app.include_router(contacts_router)
app.include_router(devis_router)
app.include_router(factures_router)
app.include_router(depenses_router)
app.include_router(documents_router)
app.include_router(planning_router)
app.include_router(heures_router)
app.include_router(rapports_router)
app.include_router(admin_router)
app.include_router(imports_router)

# SessionMiddleware doit être ajouté EN DERNIER pour être l'outermost
# (Starlette wrap les middlewares dans l'ordre inverse de l'ajout)
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET, max_age=60 * 60 * 24 * 14)


@app.on_event("startup")
def on_startup():
    init_schema()
    _bootstrap_admin_from_env()


def _bootstrap_admin_from_env():
    """Crée un compte admin si BOOTSTRAP_ADMIN_EMAIL/PASSWORD est défini et qu'aucun admin
    n'existe. Utile pour le premier démarrage en cloud (Render, Railway, etc.) où l'on
    ne peut pas lancer un script interactif. Idempotent : ne re-crée rien si admin existant.
    """
    import os
    email = os.environ.get("BOOTSTRAP_ADMIN_EMAIL", "").strip().lower()
    pw = os.environ.get("BOOTSTRAP_ADMIN_PASSWORD", "").strip()
    name = os.environ.get("BOOTSTRAP_ADMIN_NAME", "Administrateur").strip()
    if not email or not pw:
        return
    from app.db import SessionLocal
    from app.models import User, UserRole
    from app.auth import hash_password
    db = SessionLocal()
    try:
        if db.query(User).filter(User.role == UserRole.ADMIN).first():
            return
        u = User(email=email, full_name=name, role=UserRole.ADMIN,
                 password_hash=hash_password(pw), active=True)
        db.add(u)
        db.commit()
        print(f"[bootstrap] Admin {email} créé depuis env vars")
    finally:
        db.close()
