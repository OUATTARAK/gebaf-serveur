# Déployer sur PythonAnywhere (gratuit, sans carte bancaire)

Guide complet pour mettre l'app en ligne sur **PythonAnywhere** — accessible depuis ton téléphone partout dans le monde, PC peut être éteint, **100 % gratuit**.

**Limites du gratuit à connaître :**
- 100 secondes de CPU par jour (largement assez pour usage chantier normal)
- 512 Mo de disque
- L'app reste en ligne tant qu'elle est visitée (sinon mise en veille après 3 mois)
- URL imposée : `tonpseudo.pythonanywhere.com`
- **Pas d'accès Internet sortant gratuit** → l'extraction IA des factures (Claude API) ne fonctionnera pas sur le cloud. Les autres extractions (Excel, PDF par heuristiques) marchent.

---

## Étape 1. Créer le compte PythonAnywhere

1. Va sur https://www.pythonanywhere.com/registration/register/beginner/
2. **Username** : choisis un pseudo simple sans accent (ex: `ouattarak`, `davidbtp`...) → c'est ce qui apparaîtra dans l'URL
3. Email + mot de passe + accepter conditions
4. **Aucune carte bancaire demandée**

⚠️ Note bien ton pseudo PythonAnywhere — il sert pour les commandes suivantes.

---

## Étape 2. Cloner le code depuis GitHub

1. Dans le dashboard PythonAnywhere, clic sur l'onglet **Consoles** (en haut)
2. Clic sur **Bash** → un terminal Linux s'ouvre dans ton navigateur
3. Tape (ou copie-colle ligne par ligne) :

```bash
cd ~
git clone https://github.com/OUATTARAK/gebaf-serveur.git
cd gebaf-serveur
```

---

## Étape 3. Créer le venv et installer les dépendances

Toujours dans la console Bash PythonAnywhere :

```bash
mkvirtualenv --python=python3.10 chantier-venv
pip install -r requirements.txt
```

⏳ L'installation prend ~3-5 min. Sois patient, ne ferme pas l'onglet.

---

## Étape 4. Configurer la Web App

1. Retour au dashboard PythonAnywhere → onglet **Web** (en haut)
2. Clic **« Add a new web app »**
3. Suivant → **« Manual configuration »** (PAS Flask/Django — on configure nous-mêmes)
4. Choisis **Python 3.10**
5. Suivant → terminer

Tu arrives sur la page de configuration de ta web app. Repère ces sections :

**Section "Virtualenv"** :
- Colle : `/home/TON_PSEUDO/.virtualenvs/chantier-venv`
- Remplace `TON_PSEUDO` par ton vrai pseudo PythonAnywhere

**Section "Code"** :
- **Source code** : `/home/TON_PSEUDO/gebaf-serveur`
- **Working directory** : `/home/TON_PSEUDO/gebaf-serveur`

**Section "Static files"** (clic « Enter URL », « Enter path » pour ajouter une ligne) :
| URL | Directory |
|---|---|
| `/static/` | `/home/TON_PSEUDO/gebaf-serveur/app/static/` |

---

## Étape 5. Adapter le fichier WSGI

Dans la section **« Code »** de la page Web, clic sur le lien du **WSGI configuration file** (chemin du genre `/var/www/tonpseudo_pythonanywhere_com_wsgi.py`).

Un éditeur s'ouvre dans le navigateur. **Supprime tout le contenu** et remplace par :

```python
import os, sys

PA_USERNAME = "TON_PSEUDO_PA"   # ← REMPLACE par ton vrai pseudo PythonAnywhere
PROJECT_NAME = "gebaf-serveur"

PROJECT_PATH = f"/home/{PA_USERNAME}/{PROJECT_NAME}"
if PROJECT_PATH not in sys.path:
    sys.path.insert(0, PROJECT_PATH)

# Données persistantes (hors du venv)
os.environ.setdefault("CHANTIER_DATA_DIR", f"/home/{PA_USERNAME}/chantier_data")
os.environ.setdefault("CHANTIER_UPLOAD_DIR", f"/home/{PA_USERNAME}/chantier_data/uploads")

# Compte admin créé automatiquement au 1er démarrage
os.environ.setdefault("BOOTSTRAP_ADMIN_EMAIL", "ouattaradavid26@yahoo.fr")
os.environ.setdefault("BOOTSTRAP_ADMIN_PASSWORD", "J'aimemesenfants1*")
os.environ.setdefault("BOOTSTRAP_ADMIN_NAME", "DAVID")

from a2wsgi import ASGIMiddleware
from app.main import app as asgi_app

application = ASGIMiddleware(asgi_app)
```

⚠️ **N'oublie pas de remplacer `TON_PSEUDO_PA` par ton vrai pseudo** (3 endroits si tu utilises pas la f-string, sinon 1 seul à la ligne `PA_USERNAME = "..."`).

Clic **« Save »** en haut de l'éditeur.

---

## Étape 6. Créer le dossier de données

Retour dans la console Bash :

```bash
mkdir -p ~/chantier_data/uploads
```

---

## Étape 7. Démarrer l'app

1. Retour onglet **Web**
2. Tout en haut de la page, gros bouton vert **« Reload »**
3. Attendre 10-20 secondes

L'URL de ton app : **`https://TON_PSEUDO.pythonanywhere.com`**

Clic dessus → tu devrais voir la page de connexion.

Connecte-toi avec :
- Email : `ouattaradavid26@yahoo.fr`
- Mot de passe : `J'aimemesenfants1*`

---

## Étape 8. Sécuriser : changer le mot de passe

Une fois connecté :
1. Va dans **Admin → Utilisateurs**
2. Clic sur ton compte → **Modifier**
3. Change le mot de passe pour un nouveau, fort
4. Enregistre

**Ensuite, retire le bootstrap** : édite le fichier WSGI (étape 5) et supprime les 3 lignes `BOOTSTRAP_ADMIN_*`. Reload la web app.

---

## Étape 9. Installer sur le téléphone (PWA)

### Android (Chrome)
1. Ouvre `https://TON_PSEUDO.pythonanywhere.com` dans Chrome
2. Connecte-toi
3. Menu (⋮) → **« Ajouter à l'écran d'accueil »** ou **« Installer l'application »**
4. L'icône grue apparaît sur ton téléphone

### iPhone (Safari)
1. Ouvre l'URL dans Safari
2. Bouton **Partager** (carré + flèche)
3. **« Sur l'écran d'accueil »** → Ajouter

---

## Mettre à jour l'app plus tard

Quand tu modifies le code sur ton PC :

```powershell
# Sur ton PC
cd C:\Users\Utilisateur\OneDrive\Documents\CHANTIER
git add .
git commit -m "ce que tu as changé"
git push
```

Puis sur PythonAnywhere (console Bash) :

```bash
cd ~/gebaf-serveur
git pull
```

Puis dans l'onglet **Web** → bouton **« Reload »**.

---

## Dépannage

### « Something went wrong » au chargement de l'URL
→ Onglet **Web** → **Error log** (en bas). Cherche la dernière erreur.

### Sessions/cookies qui ne marchent pas
→ Vérifie que dans `CHANTIER_DATA_DIR` (`~/chantier_data`) il y a bien le fichier `.session_secret` (créé au 1er démarrage).

### L'app est lente
→ PythonAnywhere gratuit donne 100 sec CPU/jour. Si tu dépasses, l'app est ralentie 24h. Pour un usage chantier normal (quelques requêtes par jour) c'est largement suffisant. Si tu prévois un usage intense (5+ utilisateurs actifs), passer en plan Hacker (5 USD/mois).

### Je veux activer l'IA pour les factures
→ Le plan gratuit bloque les requêtes vers `api.anthropic.com`. Il faut soit :
- Passer au plan Hacker payant (5 USD/mois, débloque tout)
- Continuer à utiliser l'app en local pour l'extraction IA (clé déjà dans Paramètres locaux)
