from datetime import date, timedelta
from fastapi import APIRouter, Request, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, extract

from app.db import get_db
from app.auth import require_user
from app.models import (
    Chantier, ChantierStatus, Facture, FactureStatus, Devis, DevisStatus,
    Depense, Intervention, InterventionStatus, HeuresTravail, User,
)
from app.routes import render

router = APIRouter()


@router.get("/")
def dashboard(request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    today = date.today()
    month_start = today.replace(day=1)

    # Compteurs chantiers
    chantiers_en_cours = db.query(Chantier).filter(Chantier.status == ChantierStatus.EN_COURS).count()
    chantiers_total = db.query(Chantier).count()

    # CA du mois (factures émises non annulées)
    ca_mois = db.query(func.coalesce(func.sum(Facture.total_ht), 0)).filter(
        Facture.date >= month_start,
        Facture.date <= today,
        Facture.status != FactureStatus.ANNULEE,
        Facture.status != FactureStatus.BROUILLON,
    ).scalar() or 0

    # Encaissements du mois (somme paid_amount × ratio non rigoureux, on prend paiements via table si dispo)
    from app.models import Paiement
    encaisse_mois = db.query(func.coalesce(func.sum(Paiement.amount), 0)).filter(
        Paiement.date >= month_start,
        Paiement.date <= today,
    ).scalar() or 0

    # Factures impayées
    impayees = db.query(Facture).filter(
        Facture.status.in_([FactureStatus.ENVOYEE, FactureStatus.PARTIELLEMENT_PAYEE, FactureStatus.EN_RETARD])
    ).order_by(Facture.due_date.asc().nullsfirst()).limit(10).all()
    reste_impaye = sum(f.reste_a_payer for f in db.query(Facture).filter(
        Facture.status.in_([FactureStatus.ENVOYEE, FactureStatus.PARTIELLEMENT_PAYEE, FactureStatus.EN_RETARD])
    ).all())

    # Devis en attente
    devis_attente = db.query(Devis).filter(Devis.status == DevisStatus.ENVOYE).count()

    # Interventions à venir (7 jours)
    week_end = today + timedelta(days=7)
    from datetime import datetime
    interventions = db.query(Intervention).filter(
        Intervention.start_dt >= datetime.combine(today, datetime.min.time()),
        Intervention.start_dt <= datetime.combine(week_end, datetime.max.time()),
        Intervention.status != InterventionStatus.ANNULEE,
    ).order_by(Intervention.start_dt.asc()).limit(10).all()

    # Dernier chantiers actifs
    chantiers_recents = db.query(Chantier).filter(
        Chantier.status.in_([ChantierStatus.EN_COURS, ChantierStatus.DEVIS, ChantierStatus.EN_PAUSE])
    ).order_by(Chantier.id.desc()).limit(8).all()

    # Mes heures du mois
    mes_heures = db.query(func.coalesce(func.sum(HeuresTravail.hours), 0)).filter(
        HeuresTravail.user_id == user.id,
        HeuresTravail.date >= month_start,
    ).scalar() or 0

    # Total dépenses du mois
    depenses_mois = db.query(func.coalesce(func.sum(Depense.amount_ht), 0)).filter(
        Depense.date >= month_start,
        Depense.date <= today,
    ).scalar() or 0

    return render(
        request, "dashboard.html",
        chantiers_en_cours=chantiers_en_cours,
        chantiers_total=chantiers_total,
        ca_mois=ca_mois,
        encaisse_mois=encaisse_mois,
        impayees=impayees,
        reste_impaye=reste_impaye,
        devis_attente=devis_attente,
        interventions=interventions,
        chantiers_recents=chantiers_recents,
        mes_heures=mes_heures,
        depenses_mois=depenses_mois,
        today=today,
    )


@router.get("/health")
def health():
    return {"ok": True}
