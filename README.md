# Suivi de chantiers

Application web locale de coordination de chantiers tous corps d'état : chantiers, clients, devis, factures, dépenses, photos, planning, heures, rapports. Multi-utilisateurs avec rôles.

## Démarrage rapide

1. **Installation** (une seule fois) : double-cliquer sur `install.bat`
   - Installe Python 3.13 si nécessaire
   - Crée un venv hors OneDrive (évite les conflits de synchro)
   - Installe les dépendances
   - Demande email/mot de passe pour créer le premier compte **administrateur**

2. **Démarrage** : double-cliquer sur `run.bat`
   - Ouvre l'application sur http://localhost:8000
   - Aussi accessible depuis le téléphone/tablette sur le même WiFi via l'IP/nom de la machine

3. Aller sur http://localhost:8000, se connecter avec le compte admin, puis créer les autres utilisateurs depuis le menu **Admin → Utilisateurs**.

## Fonctionnalités

- **Chantiers** : référence auto (CH2026-0001), client, adresse, dates, budget, statut, marge calculée
- **Devis** : numérotation auto, lignes, PDF imprimable, statuts (brouillon → envoyé → accepté), conversion en facture en un clic
- **Factures** : PDF, échéances, statuts, suivi des paiements (virement/chèque/espèces/CB), marquage automatique « en retard »
- **Dépenses** : par chantier, catégories (matériaux, sous-traitance...), TVA, justificatif joint
- **Documents** : photos avant/après, plans, contrats, attestations — visualisation en galerie
- **Planning** : calendrier mensuel, interventions avec assigné interne ou artisan externe
- **Heures** : saisie par chantier et par personne, tarif horaire optionnel, total par période
- **Rapports** : CA/encaissé/dépenses mensuels, marge par chantier, top fournisseurs, heures par personne
- **Audit** : journal complet des actions sensibles

## Rôles

| Rôle | Accès |
|---|---|
| **Administrateur** | Tout, plus gestion utilisateurs et audit |
| **Coordinateur** (manager) | Chantiers, clients, contacts, devis, factures, dépenses, planning |
| **Comptable** (accountant) | Factures, paiements, dépenses, rapports |
| **Ouvrier** (worker) | Voit les chantiers, saisit ses heures, photos, ses dépenses |
| **Lecture seule** (viewer) | Consultation uniquement |

## Personnaliser les informations de votre entreprise

Pour faire apparaître votre raison sociale / SIRET / IBAN sur les PDF de devis et factures, éditez le dictionnaire `COMPANY` dans `app/config.py` :

```python
COMPANY = {
    "name": "Mon Entreprise BTP",
    "address": "1 rue Exemple\n75000 Paris",
    "phone": "01 23 45 67 89",
    "email": "contact@monentreprise.fr",
    "siret": "12345678900012",
    "rcs": "Paris B 123 456 789",
    "iban": "FR76 ...",
    "tva_intra": "FR12345678900",
}
```

## Données

- Base : `data/chantier.db` (SQLite)
- Fichiers uploadés (justificatifs, photos, documents) : `data/uploads/`
- Secret de session : `data/.session_secret` (généré automatiquement, **à conserver**)

**Sauvegarde** : copier tout le dossier `data/` régulièrement (clé USB, disque externe, cloud séparé).

## Stack technique

- Backend : FastAPI + SQLAlchemy 2 + SQLite
- Frontend : Jinja2 + Bootstrap 5 + Chart.js
- PDF : ReportLab
- Auth : sessions cookies + bcrypt

## Arborescence

```
CHANTIER/
  app/
    main.py              # Entrée FastAPI
    config.py            # Infos société, secret session
    db.py                # SQLAlchemy
    models.py            # Tables (User, Chantier, Devis, Facture, ...)
    auth.py              # Sessions, hash, permissions
    utils.py             # Numérotation, formatage, calcul marge
    pdf.py               # Génération PDF devis/factures
    routes/              # Un fichier par domaine fonctionnel
    templates/           # Pages Jinja2
    static/              # CSS + JS
  scripts/init_db.py     # Création de la base + admin
  data/                  # BDD + uploads (jamais versionné)
  install.bat            # Setup initial
  run.bat                # Démarre le serveur
```

## Problèmes courants

- **« Le venv n'existe pas »** au démarrage → relancer `install.bat`
- **Port 8000 occupé** → éditer `run.bat`, changer `--port 8000` → `--port 8080`
- **Impossible d'accéder depuis le téléphone** → vérifier le pare-feu Windows (autoriser uvicorn / port 8000)
- **Oubli du mot de passe admin** → arrêter l'app, supprimer `data/chantier.db`, relancer `install.bat`

## Évolutions possibles

- Notifications par email pour les factures en retard
- Export comptable (FEC)
- Application mobile (responsive déjà OK, PWA à venir)
- Synchronisation cloud / multi-sites
