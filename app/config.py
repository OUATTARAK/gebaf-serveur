import os
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SECRET_FILE = ROOT / "data" / ".session_secret"


def _load_or_create_secret() -> str:
    SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
    if SECRET_FILE.exists():
        return SECRET_FILE.read_text().strip()
    secret = secrets.token_urlsafe(48)
    SECRET_FILE.write_text(secret)
    return secret


SESSION_SECRET = os.environ.get("CHANTIER_SECRET") or _load_or_create_secret()

# Société émettrice (modifiable dans /admin/settings plus tard, hardcodé pour MVP)
COMPANY = {
    "name": "Mon Entreprise BTP",
    "address": "1 rue de l'Exemple\n75000 Paris",
    "phone": "01 23 45 67 89",
    "email": "contact@monentreprise.fr",
    "siret": "",
    "rcs": "",
    "iban": "",
    "tva_intra": "",
}
