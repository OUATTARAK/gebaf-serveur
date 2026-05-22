# Déployer Chantiers dans le cloud (Render)

Ce guide explique comment publier l'app sur Internet pour y accéder depuis ton téléphone, même si ton PC est éteint. On utilise **Render** : c'est simple, ça marche du premier coup avec le `render.yaml` déjà inclus dans ce dépôt.

Tarif total : **~14 USD/mois** (7 USD web service + 7 USD Postgres) pour avoir un service qui ne se met jamais en veille et conserve tes photos/justificatifs.

---

## 1. Préparer un dépôt GitHub

Render déploie depuis un dépôt Git. Si tu n'as pas encore créé de dépôt :

```powershell
cd C:\Users\Utilisateur\OneDrive\Documents\CHANTIER
git init
git add .
git commit -m "Suivi de chantiers — premier commit"
```

Crée un dépôt **privé** sur https://github.com/new (clic « New repository »), puis pousse :

```powershell
git remote add origin https://github.com/<ton-pseudo>/chantiers.git
git branch -M main
git push -u origin main
```

> **Important** : le dossier `data/` est dans `.gitignore` — ta BDD locale et tes fichiers ne sont pas envoyés sur GitHub, c'est voulu.

---

## 2. Créer le compte Render

1. Va sur https://render.com et crée un compte (gratuit)
2. Connecte ton compte GitHub (autorise Render à voir ton dépôt `chantiers`)

---

## 3. Déployer en 1 clic avec le Blueprint

Render lit le fichier `render.yaml` à la racine et crée automatiquement le web service + la base PostgreSQL + le disque persistant.

1. Dans le dashboard Render, clic **« New + »** → **« Blueprint »**
2. Sélectionne ton dépôt `chantiers`
3. Render détecte `render.yaml` et propose la configuration
4. Clic **« Apply »**

⏳ Le premier déploiement prend ~5 minutes.

---

## 4. Configurer les secrets

Une fois le service créé, va dans **chantiers → Environment** et ajoute ces variables :

| Variable | Valeur | À quoi ça sert |
|---|---|---|
| `BOOTSTRAP_ADMIN_EMAIL` | `ton@email.com` | Email du premier compte admin (utilisé seulement au tout premier démarrage) |
| `BOOTSTRAP_ADMIN_PASSWORD` | un mot de passe fort | Mot de passe du premier admin |
| `BOOTSTRAP_ADMIN_NAME` | `Ton Prénom Nom` | Nom affiché |
| `ANTHROPIC_API_KEY` | `sk-ant-...` | (Optionnel) clé Anthropic pour l'extraction IA des factures |

Clic **« Save changes »** — le service redémarre tout seul et crée ton compte admin.

> ⚠️ Une fois connecté la première fois, **change ton mot de passe** depuis `/admin/users/<ton-id>/edit` et supprime les variables `BOOTSTRAP_ADMIN_*` (elles ne servent qu'au tout premier démarrage).

---

## 5. Récupérer l'URL publique

Dans le dashboard Render, sur la page de ton service, l'URL est en haut :

```
https://chantiers-xxxx.onrender.com
```

C'est cette URL que tu mets sur ton téléphone — **HTTPS automatique**, accessible depuis n'importe où dans le monde.

---

## 6. Installer sur le téléphone (PWA)

### Android (Chrome)
1. Ouvre l'URL Render dans Chrome
2. Connecte-toi
3. Menu (⋮) → **« Ajouter à l'écran d'accueil »** ou **« Installer l'application »**
4. L'icône grue apparaît sur le téléphone — clic → lancement plein écran sans barre du navigateur

### iPhone (Safari)
1. Ouvre l'URL Render dans Safari
2. Bouton « Partager » (icône carré + flèche)
3. **« Sur l'écran d'accueil »** → Ajouter
4. Idem : icône grue, lancement plein écran

---

## 7. Domaine perso (optionnel)

Si tu veux une URL comme `chantiers.tondomaine.com` au lieu de `chantiers-xxxx.onrender.com` :

1. Dans Render → service → **Settings → Custom Domain** → ajoute ton domaine
2. Chez ton registrar (OVH, Gandi, Cloudflare...) ajoute le CNAME que Render te donne
3. Render gère le certificat HTTPS automatiquement

---

## Mise à jour de l'app

À chaque `git push` sur la branche `main`, Render redéploie automatiquement.

```powershell
cd C:\Users\Utilisateur\OneDrive\Documents\CHANTIER
# modif des fichiers...
git add .
git commit -m "Description du changement"
git push
```

---

## Alternatives à Render

Le code est compatible avec n'importe quel PaaS Python + Postgres :

- **Railway** (https://railway.app) — pareil, `Procfile` détecté auto
- **Fly.io** — free tier généreux, faut un `fly.toml` (te le dire)
- **VPS Hetzner / OVH / DigitalOcean** — ~4 USD/mois, plus de contrôle mais setup manuel (à demander)

---

## Coût détaillé Render Starter

| Composant | Tarif |
|---|---|
| Web service (Starter, 512 Mo RAM, no sleep) | 7 USD/mois |
| Postgres (Starter, 1 Go RAM, 1 Go stockage) | 7 USD/mois |
| Disque persistant 5 Go | inclus dans web service Starter |
| Trafic sortant | inclus jusqu'à 100 Go/mois |
| HTTPS / certificats | gratuit |
| **Total** | **~14 USD/mois** |

Au-delà de 1 Go de BDD ou 5 Go de fichiers, scale up les composants individuellement.

---

## Sauvegarde

Render fait des **snapshots quotidiens** automatiques de Postgres (gardés 7 jours sur Starter).

Pour sauvegarder le disque (uploads) :
- Render → service → **Disks → Snapshot** (manuel, gratuit)
- Ou : monter un export `/var/data` vers ton PC périodiquement (à scripter à la demande)

---

## Dépannage

- **« Application failed to start »** → vérifie les logs dans Render → service → Logs
- **« Login HTTP 401 après déploiement »** → vérifie que `BOOTSTRAP_ADMIN_*` sont bien définis ET que le service a redémarré une fois ces variables enregistrées
- **« Photos disparues »** → tu n'es pas sur Starter (free tier n'a pas de disque persistant), upgrade
- **App lente** → le plan Starter a 0.5 vCPU, suffisant pour quelques utilisateurs. Passer à Standard (15 USD/mois) double les ressources.
