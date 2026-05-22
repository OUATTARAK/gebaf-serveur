"""Accès lecture/écriture aux paramètres applicatifs (table settings)."""
import os
from sqlalchemy.orm import Session
from app.models import Setting
from app.db import SessionLocal


COMPANY_DEFAULTS = {
    "company.name": "Mon Entreprise BTP",
    "company.address": "",
    "company.phone": "",
    "company.email": "",
    "company.siret": "",
    "company.rcs": "",
    "company.iban": "",
    "company.tva_intra": "",
}

ALL_KEYS = list(COMPANY_DEFAULTS.keys()) + ["anthropic.api_key"]


def get(db: Session, key: str, default=None):
    s = db.query(Setting).filter(Setting.key == key).first()
    return s.value if s and s.value else default


def set_(db: Session, key: str, value):
    s = db.query(Setting).filter(Setting.key == key).first()
    if s:
        s.value = value or None
    else:
        db.add(Setting(key=key, value=value or None))


def get_company(db: Session) -> dict:
    """Renvoie les infos société (DB > défauts)."""
    out = {}
    for k, default in COMPANY_DEFAULTS.items():
        short = k.split(".", 1)[1]
        out[short] = get(db, k, default) or default
    return out


def get_anthropic_key(db: Session | None = None) -> str | None:
    """Renvoie la clé Anthropic : DB > variable d'environnement."""
    if db is not None:
        v = get(db, "anthropic.api_key")
        if v:
            return v.strip()
    # fallback : DB en accès direct si pas de session
    if db is None:
        try:
            tmp = SessionLocal()
            try:
                v = get(tmp, "anthropic.api_key")
                if v:
                    return v.strip()
            finally:
                tmp.close()
        except Exception:
            pass
    return os.environ.get("ANTHROPIC_API_KEY")
