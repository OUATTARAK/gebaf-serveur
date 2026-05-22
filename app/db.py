import os
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session

ROOT = Path(__file__).resolve().parent.parent

# Répertoire de données : surchargeable via env (utile pour disque persistant cloud).
DATA_DIR = Path(os.environ.get("CHANTIER_DATA_DIR") or (ROOT / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR = Path(os.environ.get("CHANTIER_UPLOAD_DIR") or (DATA_DIR / "uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# URL BDD : env var > SQLite local par défaut.
# Render/Railway/Heroku fournissent DATABASE_URL (postgres://...).
DB_URL_ENV = os.environ.get("DATABASE_URL", "").strip()
if DB_URL_ENV:
    # SQLAlchemy 2.0 attend "postgresql://" et non "postgres://".
    if DB_URL_ENV.startswith("postgres://"):
        DB_URL_ENV = DB_URL_ENV.replace("postgres://", "postgresql://", 1)
    DATABASE_URL = DB_URL_ENV
    _is_sqlite = False
else:
    DB_PATH = DATA_DIR / "chantier.db"
    DATABASE_URL = f"sqlite:///{DB_PATH}"
    _is_sqlite = True

if _is_sqlite:
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        future=True,
    )
else:
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_recycle=300,
        future=True,
    )

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_schema():
    from app import models  # noqa: F401 — enregistre les mappings
    Base.metadata.create_all(bind=engine)
