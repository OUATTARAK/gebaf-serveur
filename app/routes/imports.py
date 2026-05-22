"""Routes d'import de fichiers.

Workflow :
1. GET  /imports/new        → page de choix + upload
2. POST /imports/new        → traite le fichier, redirige vers preview
3. GET  /imports/preview/{token} → écran de revue + validation
4. POST /imports/confirm/{token} → crée les entités
"""
from __future__ import annotations
from pathlib import Path
from uuid import uuid4
from datetime import date
import json
import os
from fastapi import APIRouter, Request, Depends, Form, HTTPException, UploadFile, File
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.db import get_db, UPLOAD_DIR
from app.auth import require_user, can_edit
from app.models import (
    Chantier, ChantierStatus, Client, ClientType, Contact, ContactType,
    Depense, DepenseCategory, Devis, DevisItem, DevisStatus, User,
)
from app.utils import audit, next_chantier_ref, next_devis_number, recompute_devis_totals
from app.routes import render, flash
from app.importers.excel_io import (
    extract_devis_lines, extract_chantiers, extract_clients,
)
from app.importers.pdf_invoice import extract_invoice

router = APIRouter()

IMPORT_TMP_DIR = UPLOAD_DIR / "_imports"
IMPORT_TMP_DIR.mkdir(parents=True, exist_ok=True)


# -------- Utilitaires --------

def _save_extraction(token: str, payload: dict) -> None:
    """Sauvegarde un dict en JSON dans le tmp dir."""
    path = IMPORT_TMP_DIR / f"{token}.json"
    path.write_text(json.dumps(payload, default=str, ensure_ascii=False), encoding="utf-8")


def _load_extraction(token: str) -> dict | None:
    path = IMPORT_TMP_DIR / f"{token}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _delete_extraction(token: str) -> None:
    for f in IMPORT_TMP_DIR.glob(f"{token}.*"):
        try:
            f.unlink()
        except OSError:
            pass


def _parse_date(s):
    if not s:
        return None
    if isinstance(s, date):
        return s
    try:
        return date.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def _f(s, default=0.0):
    try:
        return float(str(s).replace(",", ".").strip())
    except (ValueError, AttributeError, TypeError):
        return default


def _client_type_from_raw(raw: str) -> ClientType:
    raw = (raw or "").lower()
    if "pro" in raw or "entrepr" in raw or "sarl" in raw or "sas" in raw:
        return ClientType.PROFESSIONNEL
    if "collect" in raw or "mair" in raw or "public" in raw:
        return ClientType.COLLECTIVITE
    return ClientType.PARTICULIER


def _status_chantier_from_raw(raw: str) -> ChantierStatus:
    raw = (raw or "").lower()
    if not raw:
        return ChantierStatus.PROSPECT
    for v in ChantierStatus:
        if v.value in raw or raw in v.value:
            return v
    if "cours" in raw or "actif" in raw:
        return ChantierStatus.EN_COURS
    if "termin" in raw or "fini" in raw:
        return ChantierStatus.TERMINE
    if "pause" in raw or "arret" in raw:
        return ChantierStatus.EN_PAUSE
    if "annul" in raw:
        return ChantierStatus.ANNULE
    return ChantierStatus.PROSPECT


# -------- Routes --------

@router.get("/imports/new")
def imports_new(request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    from app.settings_store import get_anthropic_key
    has_anthropic = bool(get_anthropic_key(db))
    chantiers = db.query(Chantier).order_by(Chantier.reference.desc()).all()
    return render(request, "imports/start.html",
                  has_anthropic=has_anthropic, chantiers=chantiers)


@router.post("/imports/new")
async def imports_upload(
    request: Request, db: Session = Depends(get_db), user: User = Depends(require_user),
    kind: str = Form(...),  # devis_lines | chantiers | clients | depense_facture
    file: UploadFile = File(...),
    chantier_id: str = Form(""),  # pour depense_facture
):
    if not file or not file.filename:
        flash(request, "Aucun fichier reçu", "danger")
        return RedirectResponse(url="/imports/new", status_code=303)

    # Sauvegarde temporaire
    token = uuid4().hex
    ext = Path(file.filename).suffix
    tmp_name = f"{token}{ext}"
    tmp_path = IMPORT_TMP_DIR / tmp_name
    tmp_path.write_bytes(await file.read())

    try:
        if kind == "devis_lines":
            result = extract_devis_lines(tmp_path)
        elif kind == "chantiers":
            result = extract_chantiers(tmp_path)
        elif kind == "clients":
            result = extract_clients(tmp_path)
        elif kind == "depense_facture":
            result = extract_invoice(tmp_path)
        else:
            flash(request, f"Type d'import inconnu : {kind}", "danger")
            return RedirectResponse(url="/imports/new", status_code=303)
    except Exception as e:
        flash(request, f"Erreur d'extraction : {e}", "danger")
        return RedirectResponse(url="/imports/new", status_code=303)

    # Stocke le résultat + métadonnées
    payload = {
        "kind": result["kind"],
        "data": result["data"],
        "warnings": result.get("warnings", []),
        "tmp_file": tmp_name,
        "original_name": file.filename,
        "chantier_id": int(chantier_id) if chantier_id else None,
    }
    _save_extraction(token, payload)
    return RedirectResponse(url=f"/imports/preview/{token}", status_code=303)


@router.get("/imports/preview/{token}")
def imports_preview(
    request: Request, token: str,
    db: Session = Depends(get_db), user: User = Depends(require_user),
):
    payload = _load_extraction(token)
    if not payload:
        flash(request, "Import expiré ou introuvable", "warning")
        return RedirectResponse(url="/imports/new", status_code=303)

    kind = payload["kind"]
    chantiers = db.query(Chantier).order_by(Chantier.reference.desc()).all()
    suppliers = db.query(Contact).filter(
        Contact.type.in_([ContactType.FOURNISSEUR, ContactType.SOUS_TRAITANT, ContactType.ARTISAN])
    ).order_by(Contact.name).all()

    return render(request, f"imports/preview_{kind}.html",
                  token=token, payload=payload,
                  chantiers=chantiers, suppliers=suppliers,
                  ChantierStatus=ChantierStatus, ClientType=ClientType,
                  DevisStatus=DevisStatus, DepenseCategory=DepenseCategory)


@router.post("/imports/cancel/{token}")
def imports_cancel(request: Request, token: str, user: User = Depends(require_user)):
    _delete_extraction(token)
    flash(request, "Import annulé", "warning")
    return RedirectResponse(url="/imports/new", status_code=303)


# -------- Confirmations par type --------

@router.post("/imports/confirm/{token}/devis_lines")
async def confirm_devis_lines(
    request: Request, token: str,
    db: Session = Depends(get_db), user: User = Depends(require_user),
):
    if not can_edit(user, "devis"):
        raise HTTPException(403)
    payload = _load_extraction(token)
    if not payload:
        flash(request, "Import expiré", "warning")
        return RedirectResponse(url="/imports/new", status_code=303)
    form = await request.form()
    chantier_id = int(form.get("chantier_id"))

    d = Devis(
        number=next_devis_number(db),
        chantier_id=chantier_id,
        date=date.today(),
        tva_rate=_f(form.get("tva_rate"), 20.0),
        status=DevisStatus.BROUILLON,
        notes=form.get("notes") or None,
    )
    db.add(d); db.flush()

    descs = form.getlist("item_description")
    qtys = form.getlist("item_quantity")
    units = form.getlist("item_unit")
    pus = form.getlist("item_unit_price")
    keep = form.getlist("item_keep")  # cases cochées
    for i, desc in enumerate(descs):
        if str(i) not in keep:
            continue
        if not desc.strip():
            continue
        db.add(DevisItem(
            devis_id=d.id, ordering=i,
            description=desc.strip(),
            quantity=_f(qtys[i] if i < len(qtys) else 1, 1.0),
            unit=(units[i] if i < len(units) else "u") or "u",
            unit_price_ht=_f(pus[i] if i < len(pus) else 0),
        ))
    db.flush(); db.refresh(d)
    recompute_devis_totals(d)
    audit(db, user.id, "import.devis_lines", "devis", d.id,
          f"{len(keep)} lignes depuis {payload.get('original_name')}")
    db.commit()
    _delete_extraction(token)
    flash(request, f"Devis {d.number} créé depuis l'import ({len(keep)} lignes)", "success")
    return RedirectResponse(url=f"/devis/{d.id}", status_code=303)


@router.post("/imports/confirm/{token}/chantiers")
async def confirm_chantiers(
    request: Request, token: str,
    db: Session = Depends(get_db), user: User = Depends(require_user),
):
    if not can_edit(user, "chantier"):
        raise HTTPException(403)
    payload = _load_extraction(token)
    if not payload:
        flash(request, "Import expiré", "warning")
        return RedirectResponse(url="/imports/new", status_code=303)
    form = await request.form()
    keep_idx = set(form.getlist("row_keep"))
    created = 0
    for i, row in enumerate(payload["data"]["rows"]):
        if str(i) not in keep_idx:
            continue
        # Client : recherche par nom, sinon création si demandé
        client_id = None
        client_name = (row.get("client_name") or "").strip()
        if client_name:
            existing = db.query(Client).filter(Client.name == client_name).first()
            if existing:
                client_id = existing.id
            else:
                cl = Client(name=client_name, type=ClientType.PARTICULIER)
                db.add(cl); db.flush()
                client_id = cl.id

        ref = row.get("reference") or next_chantier_ref(db)
        c = Chantier(
            reference=ref,
            name=row["name"],
            client_id=client_id,
            address=row.get("address"),
            start_date=_parse_date(row.get("start_date")),
            end_date=_parse_date(row.get("end_date")),
            budget_ht=row.get("budget_ht") or 0,
            status=_status_chantier_from_raw(row.get("status_raw") or ""),
            created_by=user.id,
        )
        db.add(c); created += 1
    db.flush()
    audit(db, user.id, "import.chantiers", details=f"{created} chantiers depuis {payload.get('original_name')}")
    db.commit()
    _delete_extraction(token)
    flash(request, f"{created} chantier(s) créé(s)", "success")
    return RedirectResponse(url="/chantiers", status_code=303)


@router.post("/imports/confirm/{token}/clients")
async def confirm_clients(
    request: Request, token: str,
    db: Session = Depends(get_db), user: User = Depends(require_user),
):
    if not can_edit(user, "client"):
        raise HTTPException(403)
    payload = _load_extraction(token)
    if not payload:
        flash(request, "Import expiré", "warning")
        return RedirectResponse(url="/imports/new", status_code=303)
    form = await request.form()
    keep_idx = set(form.getlist("row_keep"))
    created = 0; skipped = 0
    for i, row in enumerate(payload["data"]["rows"]):
        if str(i) not in keep_idx:
            continue
        if db.query(Client).filter(Client.name == row["name"]).first():
            skipped += 1
            continue
        c = Client(
            name=row["name"],
            type=_client_type_from_raw(row.get("type_raw")),
            email=row.get("email"), phone=row.get("phone"),
            address=row.get("address"), siret=row.get("siret"),
            notes=row.get("notes"),
        )
        db.add(c); created += 1
    audit(db, user.id, "import.clients", details=f"{created} clients depuis {payload.get('original_name')}")
    db.commit()
    _delete_extraction(token)
    msg = f"{created} client(s) créé(s)"
    if skipped:
        msg += f" — {skipped} doublons ignorés"
    flash(request, msg, "success")
    return RedirectResponse(url="/clients", status_code=303)


@router.post("/imports/confirm/{token}/depense_facture")
async def confirm_depense_facture(
    request: Request, token: str,
    db: Session = Depends(get_db), user: User = Depends(require_user),
):
    if not can_edit(user, "depense"):
        raise HTTPException(403)
    payload = _load_extraction(token)
    if not payload:
        flash(request, "Import expiré", "warning")
        return RedirectResponse(url="/imports/new", status_code=303)
    form = await request.form()

    # Promouvoir le fichier tmp en justificatif définitif
    tmp_file = payload.get("tmp_file")
    receipt_name = None
    if tmp_file:
        src = IMPORT_TMP_DIR / tmp_file
        if src.exists():
            receipt_name = f"depense_{uuid4().hex}{Path(tmp_file).suffix}"
            (UPLOAD_DIR / receipt_name).write_bytes(src.read_bytes())

    chantier_id = int(form.get("chantier_id"))
    supplier_id = form.get("supplier_id")
    supplier_id = int(supplier_id) if supplier_id else None

    # Création éventuelle du fournisseur depuis le nom extrait
    new_supplier_name = (form.get("new_supplier_name") or "").strip()
    if new_supplier_name and not supplier_id:
        sup = Contact(name=new_supplier_name, type=ContactType.FOURNISSEUR)
        db.add(sup); db.flush()
        supplier_id = sup.id

    ht = _f(form.get("amount_ht"))
    tva = _f(form.get("tva_rate"), 20.0)
    ttc = round(ht * (1 + tva / 100), 2)

    d = Depense(
        chantier_id=chantier_id,
        date=_parse_date(form.get("date_val")) or date.today(),
        supplier_id=supplier_id,
        category=DepenseCategory(form.get("category", "materiaux")),
        description=form.get("description", "").strip() or "Facture importée",
        amount_ht=ht, tva_rate=tva, amount_ttc=ttc,
        receipt_path=receipt_name,
        created_by=user.id,
    )
    db.add(d); db.flush()
    audit(db, user.id, "import.depense_facture", "depense", d.id,
          f"depuis {payload.get('original_name')}")
    db.commit()
    _delete_extraction(token)
    flash(request, f"Dépense créée ({ttc:.0f} F CFA TTC) depuis la facture", "success")
    return RedirectResponse(url=f"/chantiers/{chantier_id}#depenses", status_code=303)
