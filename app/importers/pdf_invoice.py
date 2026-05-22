"""Extraction d'une facture fournisseur depuis PDF ou image.

Stratégie :
1. Extraction texte (pdfplumber pour PDF, OCR ignoré ici — image renvoie texte vide).
2. Heuristiques regex (FR) sur le texte : date, totaux, TVA, n° facture, fournisseur.
3. Si ANTHROPIC_API_KEY est défini, on envoie le fichier à Claude pour extraction JSON structurée
   qui complète/écrase les heuristiques.
"""
from __future__ import annotations
from pathlib import Path
from datetime import date, datetime
import os
import re
import base64
from typing import Any


# -------- Texte --------

def extract_text_from_pdf(path: Path) -> str:
    try:
        import pdfplumber
    except Exception:
        return ""
    text_parts = []
    try:
        with pdfplumber.open(str(path)) as pdf:
            for page in pdf.pages:
                t = page.extract_text() or ""
                text_parts.append(t)
    except Exception:
        return ""
    return "\n".join(text_parts)


# -------- Heuristiques --------

_MONTHS_FR = {
    "janvier": 1, "jan": 1, "février": 2, "fevrier": 2, "fev": 2, "fév": 2,
    "mars": 3, "mar": 3, "avril": 4, "avr": 4, "mai": 5,
    "juin": 6, "juillet": 7, "juil": 7, "août": 8, "aout": 8,
    "septembre": 9, "sept": 9, "sep": 9, "octobre": 10, "oct": 10,
    "novembre": 11, "nov": 11, "décembre": 12, "decembre": 12, "déc": 12, "dec": 12,
}


def _parse_amount(s: str) -> float | None:
    s = s.replace("\xa0", "").replace(" ", "").replace(",", ".")
    # garde uniquement chiffres et points
    s = re.sub(r"[^\d.\-]", "", s)
    if not s:
        return None
    # si plusieurs points → garder seulement le dernier comme décimal
    if s.count(".") > 1:
        parts = s.split(".")
        s = "".join(parts[:-1]) + "." + parts[-1]
    try:
        return float(s)
    except ValueError:
        return None


def _find_amount_near(text: str, patterns: list[str]) -> float | None:
    """Cherche la première occurrence d'un mot-clé suivi d'un montant."""
    for pat in patterns:
        m = re.search(pat + r"[^\d\n]{0,30}([\d \xa0.,]+)", text, re.IGNORECASE)
        if m:
            v = _parse_amount(m.group(1))
            if v is not None and v > 0:
                return v
    return None


def _find_date(text: str) -> date | None:
    # JJ/MM/AAAA ou JJ-MM-AAAA
    m = re.search(r"\b([0-3]?\d)[/\-\.]([0-1]?\d)[/\-\.](20\d{2})\b", text)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            pass
    # JJ mois AAAA
    m = re.search(r"\b([0-3]?\d)\s+([a-zéûôA-ZÉÛÔ]{3,9})\s+(20\d{2})\b", text)
    if m:
        mois = m.group(2).lower()
        if mois in _MONTHS_FR:
            try:
                return date(int(m.group(3)), _MONTHS_FR[mois], int(m.group(1)))
            except ValueError:
                pass
    # AAAA-MM-JJ
    m = re.search(r"\b(20\d{2})-([0-1]?\d)-([0-3]?\d)\b", text)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass
    return None


def _find_supplier(text: str) -> str | None:
    """Première ligne non vide significative, ou ligne contenant 'SAS|SARL|EURL|SA|SCI'."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    # cherche ligne avec forme juridique
    for line in lines[:15]:
        if re.search(r"\b(SARL|SAS|SA|EURL|SCI|SASU|SNC|GIE)\b", line, re.IGNORECASE):
            return line[:120]
    # sinon première ligne significative (> 4 caractères, pas un en-tête générique)
    for line in lines[:5]:
        if len(line) > 4 and not re.match(r"^(FACTURE|DEVIS|N°|NUMERO|PAGE)", line, re.IGNORECASE):
            return line[:120]
    return None


def _find_invoice_number(text: str) -> str | None:
    patterns = [
        r"facture\s*[n°#:\-]*\s*([A-Z0-9\-/\.]{3,25})",
        r"n[°o]\s*facture\s*[:\-]?\s*([A-Z0-9\-/\.]{3,25})",
        r"invoice\s*[n°#:\-]*\s*([A-Z0-9\-/\.]{3,25})",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return m.group(1).strip(".-/")
    return None


def heuristic_extract(text: str) -> dict:
    """Extraction par regex. Retourne dict partiel, valeurs None si non trouvées."""
    ht = _find_amount_near(text, [
        r"total\s*h\.?t\.?", r"montant\s*h\.?t\.?", r"sous[\s\-]*total", r"net\s*ht",
    ])
    ttc = _find_amount_near(text, [
        r"total\s*t\.?t\.?c\.?", r"montant\s*t\.?t\.?c\.?",
        r"net\s*à\s*payer", r"total\s*à\s*payer", r"à\s*payer", r"total\s*ttc",
    ])
    tva_amt = _find_amount_near(text, [
        r"total\s*t\.?v\.?a\.?", r"montant\s*t\.?v\.?a\.?", r"^t\.?v\.?a\.?",
    ])
    # Si HT et TTC connus, TVA % calculé
    tva_rate = None
    if ht and ttc and ht > 0:
        rate = (ttc - ht) / ht * 100
        # arrondir au taux usuel
        for std in (0, 5.5, 10, 20):
            if abs(rate - std) < 1.5:
                tva_rate = std
                break
        else:
            tva_rate = round(rate, 1)
    elif tva_amt and ht:
        tva_rate = round(tva_amt / ht * 100, 1)

    # Si seulement TTC connu et un taux usuel détecté dans le texte
    if not ht and ttc:
        m = re.search(r"tva\s*([0-9]{1,2}(?:[.,]\d)?)\s*%", text, re.IGNORECASE)
        if m:
            rate = float(m.group(1).replace(",", "."))
            tva_rate = rate
            ht = round(ttc / (1 + rate / 100), 2)

    return {
        "date": _find_date(text),
        "supplier_name": _find_supplier(text),
        "invoice_number": _find_invoice_number(text),
        "amount_ht": ht,
        "amount_ttc": ttc,
        "tva_rate": tva_rate,
        "tva_amount": tva_amt,
        "raw_text_excerpt": text[:600] if text else "",
    }


# -------- LLM (Claude) --------

def claude_extract(path: Path, text_fallback: str = "") -> dict | None:
    """Extraction via Claude si une clé API est définie (DB > env var). Retourne None si indisponible."""
    try:
        from app.settings_store import get_anthropic_key
        api_key = get_anthropic_key()
    except Exception:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    try:
        import anthropic
    except Exception:
        return None

    client = anthropic.Anthropic(api_key=api_key)
    ext = path.suffix.lower()
    content_blocks = []

    if ext == ".pdf":
        try:
            data = base64.standard_b64encode(path.read_bytes()).decode()
            content_blocks.append({
                "type": "document",
                "source": {"type": "base64", "media_type": "application/pdf", "data": data},
            })
        except Exception:
            return None
    elif ext in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
        media = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
                 "gif": "image/gif", "webp": "image/webp"}.get(ext.lstrip("."), "image/jpeg")
        try:
            data = base64.standard_b64encode(path.read_bytes()).decode()
            content_blocks.append({
                "type": "image",
                "source": {"type": "base64", "media_type": media, "data": data},
            })
        except Exception:
            return None
    else:
        # autre format : envoie le texte extrait
        if not text_fallback:
            return None

    prompt = (
        "Voici une facture fournisseur. Extrais les informations suivantes en JSON STRICT, "
        "sans aucun texte autour, avec exactement ces clés :\n"
        '{\n'
        '  "supplier_name": string,\n'
        '  "invoice_number": string,\n'
        '  "date": "YYYY-MM-DD",\n'
        '  "amount_ht": number,\n'
        '  "tva_rate": number,\n'
        '  "amount_ttc": number,\n'
        '  "description": string,\n'
        '  "lines": [{"description": string, "quantity": number, "unit": string, "unit_price_ht": number}]\n'
        '}\n'
        "Si une info est absente, mets null. Les montants sont des nombres sans devise. "
        "La date est au format ISO (YYYY-MM-DD). Réponds UNIQUEMENT par le JSON."
    )
    if text_fallback and not content_blocks:
        prompt += "\n\nContenu de la facture (texte) :\n" + text_fallback[:8000]
    content_blocks.append({"type": "text", "text": prompt})

    try:
        msg = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=2000,
            messages=[{"role": "user", "content": content_blocks}],
        )
        raw = msg.content[0].text if msg.content else ""
    except Exception as e:
        return {"_error": str(e)}

    # parse JSON (tolère un ```json ... ``` autour)
    import json
    m = re.search(r"\{[\s\S]*\}", raw)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None

    # normalise la date
    parsed_date = None
    if data.get("date"):
        try:
            parsed_date = datetime.strptime(data["date"], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            pass

    return {
        "supplier_name": data.get("supplier_name"),
        "invoice_number": data.get("invoice_number"),
        "date": parsed_date,
        "amount_ht": data.get("amount_ht"),
        "amount_ttc": data.get("amount_ttc"),
        "tva_rate": data.get("tva_rate"),
        "description": data.get("description"),
        "lines": data.get("lines") or [],
        "_source": "llm",
    }


def extract_invoice(path: Path) -> dict:
    """Pipeline complet : heuristique + Claude si dispo, fusion des résultats."""
    text = extract_text_from_pdf(path) if path.suffix.lower() == ".pdf" else ""
    heur = heuristic_extract(text) if text else {
        "date": None, "supplier_name": None, "invoice_number": None,
        "amount_ht": None, "amount_ttc": None, "tva_rate": None, "tva_amount": None,
        "raw_text_excerpt": "",
    }

    warnings = []
    llm = claude_extract(path, text_fallback=text)
    source = "heuristics"
    final = dict(heur)

    if llm:
        if llm.get("_error"):
            warnings.append(f"Claude a renvoyé une erreur : {llm['_error']} — extraction locale utilisée")
        else:
            source = "llm"
            # Le LLM prime quand il a une valeur (None = on garde l'heuristique)
            for k in ("supplier_name", "invoice_number", "date", "amount_ht",
                     "amount_ttc", "tva_rate", "description"):
                v = llm.get(k)
                if v not in (None, ""):
                    final[k] = v
            if llm.get("lines"):
                final["lines"] = llm["lines"]
    elif not text:
        warnings.append("Aucun texte n'a pu être extrait du fichier (PDF scanné ou image). "
                        "Configure une clé Anthropic dans ANTHROPIC_API_KEY pour l'extraction par IA.")

    final["source"] = source
    final["lines"] = final.get("lines") or []

    return {
        "kind": "depense_facture",
        "data": final,
        "warnings": warnings,
    }
