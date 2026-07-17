"""
core/linkedin_service.py — Import d'un profil LinkedIn
======================================================
LinkedIn bloque le scraping direct (authentification obligatoire, détection
anti-bot, et interdiction explicite dans ses CGU). Trois voies existent, le
service les expose derrière une interface commune :

  1. "pdf"       — l'utilisateur exporte son profil en PDF depuis LinkedIn
                   (Profil ▸ Plus ▸ Enregistrer au format PDF) et le dépose.
                   Aucune clé, aucun coût, conforme aux CGU. Voie par défaut.
  2. "proxycurl" — API tierce payante qui gère la collecte légalement de son
                   côté. Nécessite PROXYCURL_API_KEY. ~0,01 $/profil.
  3. "official"  — API LinkedIn officielle (OAuth + partenariat approuvé).
                   Réservée aux applications validées par LinkedIn.

La sortie est normalisée sur le même schéma que `cv_service.extract_cv`,
de sorte que le frontend affiche un profil identique quelle que soit la source.
"""

from __future__ import annotations

import os
import re
import logging
from datetime import datetime

from .rncp import RNCP_REFERENTIEL
from .cv_service import map_to_rncp

log = logging.getLogger("macmia.linkedin")

ANNEE_COURANTE = datetime.now().year

PROXYCURL_API_KEY = os.getenv("PROXYCURL_API_KEY", "")
PROXYCURL_URL = "https://nubela.co/proxycurl/api/v2/linkedin"

LINKEDIN_URL_RE = re.compile(
    r"^(?:https?://)?(?:[\w]+\.)?linkedin\.com/in/(?P<slug>[\w\-À-ſ%]+)/?",
    re.IGNORECASE,
)


class LinkedInError(Exception):
    """Erreur métier remontée à l'API (message affichable à l'utilisateur)."""


def parse_profile_url(url: str) -> str:
    """Valide une URL LinkedIn et renvoie son identifiant public (slug)."""
    url = (url or "").strip()
    if not url:
        raise LinkedInError("Renseignez l'adresse de votre profil LinkedIn.")
    m = LINKEDIN_URL_RE.match(url)
    if not m:
        raise LinkedInError(
            "Adresse LinkedIn non reconnue. Format attendu : "
            "https://www.linkedin.com/in/votre-identifiant"
        )
    return m.group("slug")


def available_providers() -> dict:
    """Indique au frontend quelles voies d'import sont réellement utilisables."""
    return {
        "pdf": {
            "disponible": True,
            "libelle": "Export PDF LinkedIn",
            "aide": "Profil ▸ Plus ▸ Enregistrer au format PDF, puis déposez le fichier.",
        },
        "proxycurl": {
            "disponible": bool(PROXYCURL_API_KEY),
            "libelle": "API Proxycurl",
            "aide": "Nécessite la variable d'environnement PROXYCURL_API_KEY.",
        },
        "official": {
            "disponible": False,
            "libelle": "API LinkedIn officielle",
            "aide": "Nécessite un partenariat validé par LinkedIn.",
        },
    }


# ══════════════════════════════════════════════════════════════════════════════
# Provider : Proxycurl
# ══════════════════════════════════════════════════════════════════════════════

def _fetch_proxycurl(profile_url: str) -> dict:
    import requests

    if not PROXYCURL_API_KEY:
        raise LinkedInError(
            "L'import automatique LinkedIn n'est pas configuré sur ce serveur. "
            "Exportez votre profil en PDF depuis LinkedIn et déposez-le dans la zone CV."
        )

    try:
        r = requests.get(
            PROXYCURL_URL,
            params={"url": profile_url, "skills": "include", "use_cache": "if-present"},
            headers={"Authorization": f"Bearer {PROXYCURL_API_KEY}"},
            timeout=30,
        )
    except requests.RequestException as e:
        raise LinkedInError(f"Le service d'import LinkedIn est injoignable : {e}") from e

    if r.status_code == 404:
        raise LinkedInError("Ce profil LinkedIn est introuvable ou n'est pas public.")
    if r.status_code == 401:
        raise LinkedInError("La clé d'accès au service d'import LinkedIn est invalide.")
    if r.status_code == 429:
        raise LinkedInError("Quota d'import LinkedIn atteint. Réessayez plus tard.")
    if not r.ok:
        raise LinkedInError(f"L'import LinkedIn a échoué (code {r.status_code}).")

    return r.json()


def _normalize_proxycurl(raw: dict, profile_url: str) -> dict:
    """Convertit la réponse Proxycurl vers le schéma de profil MACMIA."""
    nom = " ".join(filter(None, [raw.get("first_name"), raw.get("last_name")])).strip()
    nom = nom or raw.get("full_name", "")

    ville = ", ".join(filter(None, [raw.get("city"), raw.get("country_full_name")]))

    # Compétences : champ skills + technologies citées dans les expériences
    competences = list(raw.get("skills") or [])

    # Diplômes
    diplomes = []
    for e in raw.get("education") or []:
        annee = 0
        fin = e.get("ends_at") or {}
        if isinstance(fin, dict) and fin.get("year"):
            annee = int(fin["year"])
        titre = " ".join(filter(None, [e.get("degree_name"), e.get("field_of_study")])).strip()
        if titre or e.get("school"):
            diplomes.append({
                "titre": titre or "Formation",
                "etablissement": e.get("school") or "",
                "annee": annee,
            })

    # Expérience : années depuis la première prise de poste
    annees_exp = 0
    debuts = []
    for x in raw.get("experiences") or []:
        d = x.get("starts_at") or {}
        if isinstance(d, dict) and d.get("year"):
            debuts.append(int(d["year"]))
    if debuts:
        annees_exp = max(0, ANNEE_COURANTE - min(debuts))

    # Poste actuel
    poste = raw.get("occupation") or ""
    if not poste:
        for x in raw.get("experiences") or []:
            if not x.get("ends_at"):
                poste = x.get("title") or ""
                break

    # Langues
    langues = [{"langue": l, "niveau": ""} for l in (raw.get("languages") or [])]

    # Niveau d'études déduit du diplôme le plus élevé
    niveau = ""
    for d in diplomes:
        t = (d["titre"] or "").lower()
        if any(k in t for k in ["doctorat", "phd", "ph.d"]):
            niveau = "Doctorat"; break
        if any(k in t for k in ["master", "mba", "ingénieur", "ingenieur", "msc"]):
            niveau = "Master"
        elif any(k in t for k in ["licence", "bachelor", "bsc"]) and not niveau:
            niveau = "Licence"

    competences_rncp = map_to_rncp(competences)
    blocs_rncp = [
        {"id": bid, "label": RNCP_REFERENTIEL[bid]["label"], "competences": c}
        for bid, c in competences_rncp.items() if c
    ]

    return {
        "source": "linkedin",
        "profil_url": profile_url,
        "nom": nom,
        "poste_actuel": poste,
        "email": raw.get("personal_email") or "",
        "telephone": (raw.get("personal_numbers") or [""])[0] if raw.get("personal_numbers") else "",
        "linkedin": profile_url,
        "github": "",
        "localisation": ville,
        "niveau_etudes": niveau,
        "annees_experience": annees_exp,
        "resume_profil": raw.get("summary") or "",
        "competences_brutes": competences,
        "competences_rncp": competences_rncp,
        "blocs_rncp": blocs_rncp,
        "diplomes": diplomes,
        "langues": langues,
        "experiences": [
            {
                "titre": x.get("title") or "",
                "entreprise": x.get("company") or "",
                "debut": (x.get("starts_at") or {}).get("year") if isinstance(x.get("starts_at"), dict) else None,
                "fin": (x.get("ends_at") or {}).get("year") if isinstance(x.get("ends_at"), dict) else None,
                "description": x.get("description") or "",
            }
            for x in (raw.get("experiences") or [])
        ],
        "meta": {"provider": "proxycurl", "photo": raw.get("profile_pic_url") or ""},
    }


# ══════════════════════════════════════════════════════════════════════════════
# Point d'entrée
# ══════════════════════════════════════════════════════════════════════════════

def import_profile(profile_url: str, provider: str = "auto") -> dict:
    """
    Importe un profil LinkedIn depuis son URL publique.
    `provider` : "auto" (Proxycurl si configuré) | "proxycurl".
    Lève LinkedInError avec un message affichable si l'import n'est pas possible.
    """
    parse_profile_url(profile_url)  # validation

    if provider in ("auto", "proxycurl"):
        raw = _fetch_proxycurl(profile_url)
        return _normalize_proxycurl(raw, profile_url)

    raise LinkedInError(f"Voie d'import inconnue : {provider}")
