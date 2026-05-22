"""Initialise la base et crée le premier utilisateur admin.

Usage:
    python -m scripts.init_db
"""
import sys
import getpass
from pathlib import Path

# Permet d'exécuter directement sans -m si lancé depuis CHANTIER/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import init_schema, SessionLocal
from app.models import User, UserRole
from app.auth import hash_password


def main():
    init_schema()
    db = SessionLocal()
    try:
        existing_admin = db.query(User).filter(User.role == UserRole.ADMIN).first()
        if existing_admin:
            print(f"[OK] Un admin existe deja : {existing_admin.email}")
            return
        print("=== Creation du premier compte administrateur ===")
        email = input("Email : ").strip().lower()
        full_name = input("Nom complet : ").strip()
        while True:
            pw = getpass.getpass("Mot de passe : ")
            pw2 = getpass.getpass("Confirmer : ")
            if pw == pw2 and len(pw) >= 6:
                break
            print("Erreur : mots de passe differents ou trop courts (6 caracteres min)")
        u = User(
            email=email, full_name=full_name,
            role=UserRole.ADMIN, password_hash=hash_password(pw),
            active=True,
        )
        db.add(u)
        db.commit()
        print(f"[OK] Admin {email} cree. Lancez : python -m uvicorn app.main:app")
    finally:
        db.close()


if __name__ == "__main__":
    main()
