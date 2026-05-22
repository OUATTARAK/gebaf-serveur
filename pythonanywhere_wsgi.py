"""Pont WSGI pour PythonAnywhere.

PythonAnywhere ne supporte pas ASGI nativement (pas d'uvicorn). On adapte
notre app FastAPI (ASGI) en application WSGI via a2wsgi.

INSTRUCTIONS :
1. Copie ce fichier dans : /var/www/<TON_PSEUDO>_pythonanywhere_com_wsgi.py
2. Adapte la ligne PROJECT_PATH avec ton vrai pseudo PythonAnywhere
3. Adapte les variables d'environnement ci-dessous (admin, infos société)
4. Recharge la web app depuis le dashboard PythonAnywhere
"""
import os
import sys

# === À PERSONNALISER ===
PA_USERNAME = "TON_PSEUDO_PA"           # ton pseudo PythonAnywhere
PROJECT_NAME = "gebaf-serveur"          # nom du dossier projet (= nom du repo)
# ========================

PROJECT_PATH = f"/home/{PA_USERNAME}/{PROJECT_NAME}"
if PROJECT_PATH not in sys.path:
    sys.path.insert(0, PROJECT_PATH)

# Données stockées hors du venv pour qu'un re-deploy ne les efface pas
os.environ.setdefault("CHANTIER_DATA_DIR", f"/home/{PA_USERNAME}/chantier_data")
os.environ.setdefault("CHANTIER_UPLOAD_DIR", f"/home/{PA_USERNAME}/chantier_data/uploads")

# Bootstrap admin au premier démarrage (peut être supprimé après 1ère connexion)
os.environ.setdefault("BOOTSTRAP_ADMIN_EMAIL", "ouattaradavid26@yahoo.fr")
os.environ.setdefault("BOOTSTRAP_ADMIN_PASSWORD", "J'aimemesenfants1*")
os.environ.setdefault("BOOTSTRAP_ADMIN_NAME", "DAVID")

# Clé Anthropic (optionnelle — l'IA pour les factures fournisseurs)
# Décommente la ligne suivante et colle ta clé :
# os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-...")

# Adaptateur ASGI → WSGI
from a2wsgi import ASGIMiddleware
from app.main import app as asgi_app

application = ASGIMiddleware(asgi_app)
