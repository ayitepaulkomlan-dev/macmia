"""
routers/profil.py — Endpoints de construction du profil (CV + LinkedIn)
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from core.cv_service import CVExtractionError, check_dependencies, extract_cv
from core.linkedin_service import LinkedInError, available_providers, import_profile

log = logging.getLogger("macmia.api")

router = APIRouter(prefix="/api/profil", tags=["profil"])

MAX_UPLOAD_MB = 5
ACCEPTED_SUFFIXES = (".pdf",)


class LinkedInRequest(BaseModel):
    url: str = Field(..., description="URL publique du profil LinkedIn")
    provider: str = Field("auto", description='"auto" | "proxycurl"')


@router.get("/health")
def health():
    """Diagnostic des dépendances d'extraction (Tesseract, Poppler, Ollama)."""
    return {
        "cv": check_dependencies(),
        "linkedin": available_providers(),
    }


@router.post("/cv")
async def upload_cv(file: UploadFile = File(...)):
    """
    Extrait un profil structuré depuis un CV PDF.
    Pipeline : OCR zoné → sections → regex + LLM → mapping RNCP.
    """
    name = file.filename or "cv.pdf"
    if not name.lower().endswith(ACCEPTED_SUFFIXES):
        raise HTTPException(400, "Format non pris en charge. Déposez un fichier PDF.")

    content = await file.read()
    size_mb = len(content) / (1024 * 1024)
    if size_mb > MAX_UPLOAD_MB:
        raise HTTPException(400, f"Fichier trop volumineux ({size_mb:.1f} Mo). Limite : {MAX_UPLOAD_MB} Mo.")
    if not content:
        raise HTTPException(400, "Le fichier est vide.")

    try:
        profil = extract_cv(content, filename=name)
    except CVExtractionError as e:
        raise HTTPException(422, str(e)) from e
    except Exception as e:
        log.exception("Échec de l'extraction du CV")
        raise HTTPException(500, f"L'analyse du CV a échoué : {e}") from e

    log.info("CV analysé : %s — %d compétences (source: %s)",
             name, len(profil["competences_brutes"]), profil["source"])
    return profil


@router.post("/linkedin")
def linkedin(payload: LinkedInRequest):
    """Importe un profil depuis son URL LinkedIn publique."""
    try:
        return import_profile(payload.url, provider=payload.provider)
    except LinkedInError as e:
        raise HTTPException(422, str(e)) from e
    except Exception as e:
        log.exception("Échec de l'import LinkedIn")
        raise HTTPException(500, f"L'import LinkedIn a échoué : {e}") from e
