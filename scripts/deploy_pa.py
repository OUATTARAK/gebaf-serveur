#!/usr/bin/env python3
"""Déploiement automatique sur PythonAnywhere.

À lancer DANS une console Bash PythonAnywhere, après avoir cloné le repo.
Le script utilise l'API PythonAnywhere pour configurer toute la Web App
automatiquement : venv, dépendances, fichier WSGI, mappings statiques, reload.

Usage :
    cd ~/gebaf-serveur
    python3 scripts/deploy_pa.py
"""
import os
import sys
import json
import getpass
import subprocess
import urllib.request
import urllib.error
from pathlib import Path

PROJECT_NAME = "gebaf-serveur"
VENV_NAME = "chantier-venv"

HOME = Path.home()
USERNAME = HOME.name
PROJECT_PATH = HOME / PROJECT_NAME
VENV_PATH = HOME / ".virtualenvs" / VENV_NAME
DATA_DIR = HOME / "chantier_data"
DOMAIN = f"{USERNAME.lower()}.pythonanywhere.com"
WSGI_FILE_PATH = f"/var/www/{USERNAME.lower()}_pythonanywhere_com_wsgi.py"

PA_API_BASE = f"https://www.pythonanywhere.com/api/v0/user/{USERNAME}"


# -------- Helpers --------

def sh(cmd, check=True):
    print(f"  $ {cmd}")
    return subprocess.run(cmd, shell=True, check=check, executable="/bin/bash")


def get_token():
    token = os.environ.get("PA_TOKEN", "").strip()
    if token:
        print("Token API détecté dans PA_TOKEN.")
        return token
    print()
    print("=" * 64)
    print("  Récupère ton token API PythonAnywhere :")
    print()
    print("  1. Ouvre dans un nouvel onglet :")
    print(f"     https://www.pythonanywhere.com/user/{USERNAME}/account/#api_token")
    print("  2. Clique « Create a new API token »")
    print("  3. Copie le token affiché (longue chaîne de caractères)")
    print("=" * 64)
    print()
    print("Colle le token ci-dessous et appuie sur Entrée.")
    print("(le token est invisible à la frappe, c'est normal)")
    token = getpass.getpass("Token : ").strip()
    if not token:
        sys.exit("Aucun token fourni, annulation.")
    return token


def api(method, path, data=None):
    """Appelle l'API PythonAnywhere. Retourne dict, list ou {_error: code}."""
    url = f"{PA_API_BASE}{path}"
    headers = {"Authorization": f"Token {TOKEN}"}
    body = None
    if data is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(data).encode()
    req = urllib.request.Request(url, method=method, headers=headers, data=body)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            content = resp.read()
            if not content:
                return {"_status": resp.status}
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                return {"_status": resp.status, "_raw": content[:300].decode(errors="replace")}
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:400]
        return {"_error": e.code, "_detail": detail}
    except urllib.error.URLError as e:
        return {"_error": -1, "_detail": str(e)}


def upload_file(server_path: str, content: str) -> bool:
    """Upload un contenu texte via l'API Files (multipart)."""
    url = f"{PA_API_BASE}/files/path{server_path}"
    boundary = "----pa-form-boundary-xyz"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="content"; filename="upload"\r\n'
        f"Content-Type: application/octet-stream\r\n\r\n"
        f"{content}\r\n"
        f"--{boundary}--\r\n"
    ).encode("utf-8")
    req = urllib.request.Request(
        url, method="POST", data=body,
        headers={
            "Authorization": f"Token {TOKEN}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status in (200, 201)
    except urllib.error.HTTPError as e:
        print(f"    ERR upload {server_path} : {e.code} {e.read().decode(errors='replace')[:200]}")
        return False


# -------- Main --------

print()
print("=" * 64)
print(f"  Déploiement PythonAnywhere")
print(f"  Pseudo  : {USERNAME}")
print(f"  Domain  : {DOMAIN}")
print(f"  Projet  : {PROJECT_PATH}")
print("=" * 64)

if not (PROJECT_PATH / "app" / "main.py").exists():
    sys.exit(
        f"ERR : {PROJECT_PATH}/app/main.py introuvable.\n"
        "Lance d'abord :\n"
        f"  cd ~ && git clone https://github.com/OUATTARAK/gebaf-serveur.git"
    )

TOKEN = get_token()

# 1. Créer venv (sans virtualenvwrapper, plus fiable)
print()
print(">> [1/8] Création du venv...")
if VENV_PATH.exists() and (VENV_PATH / "bin" / "python").exists():
    print(f"  Venv existant : {VENV_PATH}")
else:
    # Cherche un python 3.10/3.11 disponible
    for py in ("python3.10", "python3.11", "python3.9", "python3"):
        try:
            r = subprocess.run([py, "--version"], capture_output=True, check=True)
            print(f"  Utilisation de {py} ({r.stdout.decode().strip()})")
            sh(f"{py} -m venv {VENV_PATH}")
            break
        except (FileNotFoundError, subprocess.CalledProcessError):
            continue
    else:
        sys.exit("Aucun Python 3.x trouvé. Anormal sur PythonAnywhere.")

# 2. Installer dépendances
print()
print(">> [2/8] Installation des dépendances (3-5 min, beaucoup de lignes vont défiler)...")
print("   N'APPUIE PAS Ctrl+C même si c'est long — laisse aller jusqu'au bout.")
print()
sh(f"{VENV_PATH}/bin/pip install --upgrade pip 2>&1 | tail -3")
sh(f"{VENV_PATH}/bin/pip install -r {PROJECT_PATH}/requirements.txt")
print()
print("  Installation terminée.")

# 3. Dossier data
print()
print(">> [3/8] Création du dossier de données...")
(DATA_DIR / "uploads").mkdir(parents=True, exist_ok=True)
print(f"  OK : {DATA_DIR}")

# 4. Web App : créer si absente
print()
print(">> [4/8] Vérification de la Web App...")
r = api("GET", f"/webapps/{DOMAIN}/")
if r.get("_error") == 404:
    print("  Création de la Web App...")
    r = api("POST", "/webapps/", data={
        "domain_name": DOMAIN,
        "python_version": "python310",
    })
    if r.get("_error"):
        # Essai python39 en fallback
        r = api("POST", "/webapps/", data={
            "domain_name": DOMAIN,
            "python_version": "python39",
        })
    if r.get("_error"):
        sys.exit(f"  ERR création : {r}")
    print(f"  OK : {DOMAIN}")
elif r.get("_error"):
    sys.exit(f"  ERR : {r}")
else:
    print(f"  Web App existante : {DOMAIN}")

# 5. Configurer virtualenv + source
print()
print(">> [5/8] Configuration venv + code source...")
r = api("PATCH", f"/webapps/{DOMAIN}/", data={
    "virtualenv_path": str(VENV_PATH),
    "source_directory": str(PROJECT_PATH),
})
if r.get("_error"):
    print(f"  WARN : {r}")
else:
    print("  OK")

# 6. Écrire le fichier WSGI
print()
print(">> [6/8] Écriture du fichier WSGI...")
wsgi_content = f'''"""WSGI pour PythonAnywhere — généré par scripts/deploy_pa.py"""
import os, sys

PROJECT_PATH = "{PROJECT_PATH}"
if PROJECT_PATH not in sys.path:
    sys.path.insert(0, PROJECT_PATH)

os.environ.setdefault("CHANTIER_DATA_DIR", "{DATA_DIR}")
os.environ.setdefault("CHANTIER_UPLOAD_DIR", "{DATA_DIR}/uploads")

# Compte admin auto au 1er démarrage (à retirer après 1ère connexion réussie)
os.environ.setdefault("BOOTSTRAP_ADMIN_EMAIL", "ouattaradavid26@yahoo.fr")
os.environ.setdefault("BOOTSTRAP_ADMIN_PASSWORD", "J'aimemesenfants1*")
os.environ.setdefault("BOOTSTRAP_ADMIN_NAME", "DAVID")

from a2wsgi import ASGIMiddleware
from app.main import app as asgi_app

application = ASGIMiddleware(asgi_app)
'''
if upload_file(WSGI_FILE_PATH, wsgi_content):
    print(f"  OK : {WSGI_FILE_PATH}")
else:
    print("  WARN : upload WSGI échoué, fais-le à la main si nécessaire")

# 7. Mapping statique /static/
print()
print(">> [7/8] Mapping fichiers statiques...")
static_url = "/static/"
static_path = str(PROJECT_PATH / "app" / "static")
existing = api("GET", f"/webapps/{DOMAIN}/static_files/")
already = False
if isinstance(existing, list):
    for s in existing:
        if s.get("url") == static_url:
            already = True
            break
if already:
    print(f"  Mapping {static_url} déjà présent")
else:
    r = api("POST", f"/webapps/{DOMAIN}/static_files/", data={
        "url": static_url, "path": static_path,
    })
    if r.get("_error"):
        print(f"  WARN : {r}")
    else:
        print(f"  OK : {static_url} → {static_path}")

# 8. Reload
print()
print(">> [8/8] Reload de la Web App...")
r = api("POST", f"/webapps/{DOMAIN}/reload/")
if r.get("_error"):
    print(f"  WARN reload : {r}")
else:
    print("  OK")

print()
print("=" * 64)
print(f"  DÉPLOIEMENT TERMINÉ")
print()
print(f"  URL          : https://{DOMAIN}")
print(f"  Email        : ouattaradavid26@yahoo.fr")
print(f"  Mot de passe : J'aimemesenfants1*")
print()
print("  ⚠ Change ton mot de passe après la 1ère connexion :")
print("     Admin → Utilisateurs → Modifier ton compte")
print("=" * 64)
