from fastapi.templating import Jinja2Templates
from pathlib import Path

from app.utils import euro, fr_date, status_badge, status_label

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Filtres Jinja
templates.env.filters["euro"] = euro
templates.env.filters["fr_date"] = fr_date
templates.env.filters["status_badge"] = status_badge
templates.env.filters["status_label"] = status_label
templates.env.globals["status_label"] = status_label
templates.env.globals["status_badge"] = status_badge


def render(request, name: str, **ctx):
    """Helper : injecte request + user dans le contexte."""
    ctx.setdefault("request", request)
    user = getattr(request.state, "user", None)
    ctx.setdefault("user", user)
    ctx.setdefault("flash", request.session.pop("flash", None) if hasattr(request, "session") else None)
    return templates.TemplateResponse(name, ctx)


def flash(request, message: str, level: str = "success"):
    request.session["flash"] = {"message": message, "level": level}
