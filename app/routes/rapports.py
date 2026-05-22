from datetime import date, timedelta
from fastapi import APIRouter, Request, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, extract

from app.db import get_db
from app.auth import require_user
from app.models import (
    Facture, FactureStatus, Chantier, ChantierStatus, Depense,
    HeuresTravail, User, Paiement,
)
from app.utils import compute_chantier_marge
from app.routes import render

router = APIRouter()


@router.get("/rapports")
def rapports(
    request: Request, db: Session = Depends(get_db), user: User = Depends(require_user),
    year: int | None = None,
):
    today = date.today()
    y = year or today.year

    # CA mensuel (factures non annulées/brouillons)
    ca_par_mois = []
    enc_par_mois = []
    dep_par_mois = []
    for m in range(1, 13):
        ca = db.query(func.coalesce(func.sum(Facture.total_ht), 0)).filter(
            extract("year", Facture.date) == y,
            extract("month", Facture.date) == m,
            Facture.status != FactureStatus.ANNULEE,
            Facture.status != FactureStatus.BROUILLON,
        ).scalar() or 0
        ca_par_mois.append(float(ca))
        enc = db.query(func.coalesce(func.sum(Paiement.amount), 0)).filter(
            extract("year", Paiement.date) == y,
            extract("month", Paiement.date) == m,
        ).scalar() or 0
        enc_par_mois.append(float(enc))
        dep = db.query(func.coalesce(func.sum(Depense.amount_ht), 0)).filter(
            extract("year", Depense.date) == y,
            extract("month", Depense.date) == m,
        ).scalar() or 0
        dep_par_mois.append(float(dep))

    # Marge par chantier (en cours ou terminés cette année)
    chantiers = db.query(Chantier).filter(
        Chantier.status.in_([ChantierStatus.EN_COURS, ChantierStatus.TERMINE, ChantierStatus.EN_PAUSE])
    ).all()
    chantier_marges = []
    for c in chantiers:
        m = compute_chantier_marge(c)
        if m["ca_facture_ht"] or m["depenses_ht"]:
            chantier_marges.append({"chantier": c, **m})
    chantier_marges.sort(key=lambda x: x["marge_eur"], reverse=True)

    # Top fournisseurs (par montant)
    top_suppliers = db.query(
        Depense.supplier_id, func.sum(Depense.amount_ht).label("total")
    ).filter(
        extract("year", Depense.date) == y,
        Depense.supplier_id.isnot(None),
    ).group_by(Depense.supplier_id).order_by(func.sum(Depense.amount_ht).desc()).limit(10).all()
    from app.models import Contact
    top_supplier_rows = []
    for sid, total in top_suppliers:
        supplier = db.query(Contact).filter(Contact.id == sid).first()
        top_supplier_rows.append({"supplier": supplier, "total": float(total or 0)})

    # Heures par utilisateur (année)
    heures_par_user = db.query(
        User.full_name, func.sum(HeuresTravail.hours).label("total")
    ).join(HeuresTravail, HeuresTravail.user_id == User.id).filter(
        extract("year", HeuresTravail.date) == y
    ).group_by(User.id).order_by(func.sum(HeuresTravail.hours).desc()).all()

    # KPIs
    ca_annee = sum(ca_par_mois)
    enc_annee = sum(enc_par_mois)
    dep_annee = sum(dep_par_mois)
    marge_annee = ca_annee - dep_annee
    marge_pct = (marge_annee / ca_annee * 100) if ca_annee else 0

    return render(request, "rapports.html",
                  year=y,
                  ca_par_mois=ca_par_mois,
                  enc_par_mois=enc_par_mois,
                  dep_par_mois=dep_par_mois,
                  chantier_marges=chantier_marges[:20],
                  top_supplier_rows=top_supplier_rows,
                  heures_par_user=[(n, float(t or 0)) for n, t in heures_par_user],
                  ca_annee=ca_annee, enc_annee=enc_annee, dep_annee=dep_annee,
                  marge_annee=marge_annee, marge_pct=marge_pct,
                  years_avail=[today.year - 2, today.year - 1, today.year, today.year + 1])
