from datetime import date, datetime
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models import Devis, Facture, Chantier, AuditLog


# -------- Formatage --------

def euro(value) -> str:
    """Formate un montant en F CFA (sans décimales, séparateur de milliers)."""
    if value is None:
        return "—"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "—"
    # F CFA : pas de décimales, espace comme séparateur de milliers
    s = f"{int(round(v)):,}".replace(",", " ")
    return f"{s} F CFA"


def fr_date(d) -> str:
    if not d:
        return "—"
    if isinstance(d, datetime):
        return d.strftime("%d/%m/%Y %H:%M")
    if isinstance(d, date):
        return d.strftime("%d/%m/%Y")
    return str(d)


def status_badge(status) -> str:
    """Retourne une classe Bootstrap pour un statut."""
    mapping = {
        "prospect": "secondary", "devis": "info", "en_cours": "primary",
        "en_pause": "warning", "termine": "success", "annule": "dark",
        "brouillon": "secondary", "envoye": "info", "envoyee": "info",
        "accepte": "success", "refuse": "danger", "expire": "warning",
        "partiellement_payee": "warning", "payee": "success",
        "en_retard": "danger", "annulee": "dark",
        "planifiee": "info", "terminee": "success",
    }
    key = status.value if hasattr(status, "value") else str(status)
    return mapping.get(key, "secondary")


def status_label(status) -> str:
    """Libellé FR pour un enum."""
    mapping = {
        "prospect": "Prospect", "devis": "Devis envoyé", "en_cours": "En cours",
        "en_pause": "En pause", "termine": "Terminé", "annule": "Annulé",
        "brouillon": "Brouillon", "envoye": "Envoyé", "envoyee": "Envoyée",
        "accepte": "Accepté", "refuse": "Refusé", "expire": "Expiré",
        "partiellement_payee": "Partiel.", "payee": "Payée",
        "en_retard": "En retard", "annulee": "Annulée",
        "planifiee": "Planifiée", "terminee": "Terminée",
        "particulier": "Particulier", "professionnel": "Pro",
        "collectivite": "Collectivité",
        "fournisseur": "Fournisseur", "artisan": "Artisan",
        "sous_traitant": "Sous-traitant", "autre": "Autre",
        "materiaux": "Matériaux", "sous_traitance": "Sous-traitance",
        "location": "Location", "transport": "Transport",
        "fournitures": "Fournitures", "main_oeuvre": "Main d'œuvre",
        "photo_avant": "Photo avant", "photo_apres": "Photo après",
        "photo_chantier": "Photo chantier", "plan": "Plan",
        "contrat": "Contrat", "attestation": "Attestation",
        "facture_recue": "Facture reçue",
        "admin": "Administrateur", "manager": "Coordinateur",
        "worker": "Ouvrier", "accountant": "Comptable",
        "viewer": "Lecture seule",
    }
    key = status.value if hasattr(status, "value") else str(status)
    return mapping.get(key, key)


# -------- Numérotation --------

def next_chantier_ref(db: Session) -> str:
    year = date.today().year
    prefix = f"CH{year}-"
    last = (
        db.query(Chantier)
        .filter(Chantier.reference.like(f"{prefix}%"))
        .order_by(Chantier.id.desc())
        .first()
    )
    if last and last.reference and last.reference.startswith(prefix):
        try:
            n = int(last.reference[len(prefix):]) + 1
        except ValueError:
            n = 1
    else:
        n = 1
    return f"{prefix}{n:04d}"


def next_devis_number(db: Session) -> str:
    year = date.today().year
    prefix = f"DV{year}-"
    last = (
        db.query(Devis)
        .filter(Devis.number.like(f"{prefix}%"))
        .order_by(Devis.id.desc())
        .first()
    )
    if last and last.number and last.number.startswith(prefix):
        try:
            n = int(last.number[len(prefix):]) + 1
        except ValueError:
            n = 1
    else:
        n = 1
    return f"{prefix}{n:04d}"


def next_facture_number(db: Session) -> str:
    year = date.today().year
    prefix = f"FA{year}-"
    last = (
        db.query(Facture)
        .filter(Facture.number.like(f"{prefix}%"))
        .order_by(Facture.id.desc())
        .first()
    )
    if last and last.number and last.number.startswith(prefix):
        try:
            n = int(last.number[len(prefix):]) + 1
        except ValueError:
            n = 1
    else:
        n = 1
    return f"{prefix}{n:04d}"


# -------- Audit --------

def audit(db: Session, user_id: int | None, action: str, entity_type: str | None = None,
          entity_id: int | None = None, details: str | None = None):
    log = AuditLog(
        user_id=user_id, action=action, entity_type=entity_type,
        entity_id=entity_id, details=details,
    )
    db.add(log)
    # commit géré par l'appelant


# -------- Calculs métier --------

def compute_chantier_marge(chantier: Chantier) -> dict:
    """Retourne CA facturé, dépenses, marge brute (€ et %)."""
    facture_total = sum(f.total_ht for f in chantier.factures if f.status not in ("annulee",))
    facture_paye = sum(f.paid_amount or 0 for f in chantier.factures)
    depenses_total = sum(d.amount_ht for d in chantier.depenses)
    devis_accepte = sum(
        d.total_ht for d in chantier.devis
        if d.status and d.status.value == "accepte"
    )
    marge_eur = facture_total - depenses_total
    marge_pct = (marge_eur / facture_total * 100) if facture_total else 0
    return {
        "ca_facture_ht": round(facture_total, 2),
        "ca_paye": round(facture_paye, 2),
        "depenses_ht": round(depenses_total, 2),
        "devis_accepte_ht": round(devis_accepte, 2),
        "marge_eur": round(marge_eur, 2),
        "marge_pct": round(marge_pct, 1),
    }


def recompute_devis_totals(devis: Devis):
    total_ht = sum(item.quantity * item.unit_price_ht for item in devis.items)
    devis.total_ht = round(total_ht, 2)
    devis.total_ttc = round(total_ht * (1 + devis.tva_rate / 100), 2)


def recompute_facture_totals(facture: Facture):
    total_ht = sum(item.quantity * item.unit_price_ht for item in facture.items)
    facture.total_ht = round(total_ht, 2)
    facture.total_ttc = round(total_ht * (1 + facture.tva_rate / 100), 2)
    # Recalcule status selon paiements
    paid = facture.paid_amount or 0
    if facture.status and facture.status.value in ("brouillon", "annulee"):
        return
    if paid <= 0:
        # status reste envoyée ou en_retard
        if facture.due_date and facture.due_date < date.today():
            from app.models import FactureStatus
            facture.status = FactureStatus.EN_RETARD
    elif paid >= facture.total_ttc - 0.01:
        from app.models import FactureStatus
        facture.status = FactureStatus.PAYEE
    else:
        from app.models import FactureStatus
        facture.status = FactureStatus.PARTIELLEMENT_PAYEE
