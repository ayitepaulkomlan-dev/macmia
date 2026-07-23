"""
core/llm.py — Accès au modèle de langue, quel que soit le serveur qui l'héberge
==============================================================================
Le modèle peut tourner à trois endroits, et le code appelant n'a pas à le savoir :

  - « ollama »   : serveur Ollama (API /api/generate), en local ou distant ;
  - « openai »   : toute API compatible OpenAI (/v1/chat/completions), ce qui
                   couvre llama-cpp-python, vLLM, LM Studio, text-generation-webui ;
  - « auto »     : essaie Ollama, puis bascule sur l'API compatible OpenAI.

Cette indirection existe pour une raison pratique : le serveur GPU du projet a
un réseau filtré où l'installation d'Ollama peut échouer, alors que
llama-cpp-python y est déjà en place. Plutôt que de dépendre d'un fournisseur
précis, on parle aux deux.

Toutes les fonctions renvoient un dictionnaire déjà décodé depuis le JSON du
modèle, ou lèvent LLMError avec un message exploitable.
"""

from __future__ import annotations

import json
import logging
import os

log = logging.getLogger("macmia.llm")

# ── Configuration ─────────────────────────────────────────────────────────────
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "auto").lower()   # auto | ollama | openai
LLM_URL      = os.getenv("OLLAMA_URL", "http://localhost:11434")
LLM_MODEL    = os.getenv("OLLAMA_MODEL", "llama3.1")
LLM_TIMEOUT  = int(os.getenv("OLLAMA_TIMEOUT", "420"))
LLM_KEEP_ALIVE  = os.getenv("OLLAMA_KEEP_ALIVE", "30m")
LLM_NUM_PREDICT = int(os.getenv("OLLAMA_NUM_PREDICT", "1600"))
LLM_API_KEY  = os.getenv("LLM_API_KEY", "not-needed")


class LLMError(Exception):
    """Le modèle n'a pas pu être interrogé, ou n'a pas renvoyé de JSON."""


def _decode_json(raw: str) -> dict:
    """
    Décode la réponse du modèle.

    Même en mode JSON forcé, certains serveurs laissent passer un préambule ou
    une clôture en ```json : on isole donc l'objet entre la première accolade
    ouvrante et la dernière fermante avant de décoder.
    """
    clean = (raw or "").strip().replace("```json", "").replace("```", "").strip()
    start, end = clean.find("{"), clean.rfind("}") + 1
    if start >= 0 and end > start:
        clean = clean[start:end]
    if not clean:
        raise LLMError("Le modèle a renvoyé une réponse vide.")
    try:
        return json.loads(clean)
    except json.JSONDecodeError as e:
        raise LLMError(f"Réponse non décodable en JSON : {e}") from e


# ══════════════════════════════════════════════════════════════════════════════
# Fournisseurs
# ══════════════════════════════════════════════════════════════════════════════

def _generate_ollama(prompt: str, timeout: int) -> dict:
    """Ollama : /api/generate, avec sortie JSON contrainte au niveau du moteur."""
    import requests

    r = requests.post(
        f"{LLM_URL.rstrip('/')}/api/generate",
        json={
            "model": LLM_MODEL,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "keep_alive": LLM_KEEP_ALIVE,
            "options": {"temperature": 0, "num_predict": LLM_NUM_PREDICT},
        },
        timeout=timeout,
    )
    r.raise_for_status()
    return _decode_json(r.json().get("response", ""))


def _generate_openai(prompt: str, timeout: int) -> dict:
    """
    API compatible OpenAI : /v1/chat/completions.

    Couvre llama-cpp-python et vLLM. `response_format` n'est pas honoré par
    tous les serveurs ; l'instruction de sortie JSON figure donc aussi dans le
    message système, et _decode_json rattrape les préambules éventuels.
    """
    import requests

    r = requests.post(
        f"{LLM_URL.rstrip('/')}/v1/chat/completions",
        headers={"Authorization": f"Bearer {LLM_API_KEY}"},
        json={
            "model": LLM_MODEL,
            "messages": [
                {"role": "system", "content": "Tu réponds uniquement par un objet JSON valide, sans texte autour."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0,
            "max_tokens": LLM_NUM_PREDICT,
            "response_format": {"type": "json_object"},
        },
        timeout=timeout,
    )
    r.raise_for_status()
    data = r.json()
    try:
        contenu = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as e:
        raise LLMError(f"Réponse inattendue du serveur de modèle : {e}") from e
    return _decode_json(contenu)


_FOURNISSEURS = {"ollama": _generate_ollama, "openai": _generate_openai}


def generate_json(prompt: str, timeout: int | None = None) -> dict:
    """
    Interroge le modèle et renvoie sa réponse décodée.

    En mode « auto », Ollama est tenté en premier ; si son point d'entrée est
    absent (404) ou injoignable, on rebascule sur l'API compatible OpenAI. Une
    erreur de délai n'est en revanche jamais convertie en changement de
    fournisseur : c'est le même modèle qui est lent, pas le serveur qui manque.
    """
    import requests

    timeout = timeout or LLM_TIMEOUT

    if LLM_PROVIDER in _FOURNISSEURS:
        return _FOURNISSEURS[LLM_PROVIDER](prompt, timeout)

    try:
        return _generate_ollama(prompt, timeout)
    except requests.exceptions.Timeout:
        raise
    except Exception as e:
        log.info("Ollama indisponible (%s) — essai de l'API compatible OpenAI", e)
        return _generate_openai(prompt, timeout)


def check_llm() -> dict:
    """Diagnostic : quel fournisseur répond, et avec quels modèles."""
    import requests

    base = LLM_URL.rstrip("/")
    etat = {"url": base, "modele": LLM_MODEL, "fournisseur": LLM_PROVIDER,
            "disponible": False, "detail": ""}

    for nom, chemin, extrait in (
        ("ollama", "/api/tags", lambda d: [m["name"] for m in d.get("models", [])]),
        ("openai", "/v1/models", lambda d: [m["id"] for m in d.get("data", [])]),
    ):
        if LLM_PROVIDER not in ("auto", nom):
            continue
        try:
            r = requests.get(f"{base}{chemin}", timeout=5)
            r.raise_for_status()
            etat.update(disponible=True, fournisseur_actif=nom,
                        modeles_disponibles=extrait(r.json()))
            return etat
        except Exception as e:
            etat["detail"] = str(e)

    etat["detail"] = (
        f"Aucun serveur de modèle ne répond sur {base}. "
        "L'extraction se fera par règles seules — les compétences, diplômes et "
        "expériences restent relevés, seul le résumé de profil manquera."
    )
    return etat
