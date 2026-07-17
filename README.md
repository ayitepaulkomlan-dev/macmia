# MACMIA

Moteur de recommandation de formations IA, Data et Industrie du Futur
pour les Grandes Écoles IMT — France 2030.

**Étape en cours : la page Profil.** L'utilisateur y dépose son CV ou importe
son profil LinkedIn ; MACMIA en relève ses compétences telles qu'elles y
figurent et les rapproche du référentiel RNCP.

---

## Architecture

```
macmia/
├── backend/                  FastAPI
│   ├── main.py               app + CORS
│   ├── core/
│   │   ├── cv_layout.py      ← votre code : blocs visuels depuis Tesseract
│   │   ├── cv_sections.py    ← votre code : titres de section (sémantique + géométrie)
│   │   ├── cv_columns.py     découpage de la page en régions AVANT l'OCR
│   │   ├── cv_lines.py       pont Block → Line
│   │   ├── cv_service.py     pipeline complet, entrée bytes → sortie dict
│   │   ├── linkedin_service.py
│   │   └── rncp.py           ← votre référentiel : 8 blocs de compétences
│   └── routers/profil.py     POST /cv, POST /linkedin, GET /health
└── frontend/                 React + Vite
    ├── public/macmia-logo.png
    └── src/
        ├── api.js            client HTTP
        ├── components/       Sidebar, CvDropzone, LinkedInCard, ProfileView
        └── pages/Profil.jsx
```

## Pipeline d'extraction

```
PDF ──► images 300 DPI (pdf2image)
     ──► sonde OCR pleine page (image_to_data, psm 1)
     ──► découpage en régions : en-tête | colonne gauche | colonne droite   ← cv_columns
     ──► OCR de chaque région séparément (psm 4)                            ← cv_service
     ──► blocs visuels                                                      ← cv_layout
     ──► lignes                                                             ← cv_lines
     ──► sections (### COMPÉTENCES, ### EXPÉRIENCE…)                        ← cv_sections
     ──► regex (e-mail, tél, LinkedIn, niveau, expérience)
     ──► LLM Ollama : compétences mot pour mot   ┐ repli par règles
                                                  ┘ si Ollama est absent
     ──► mapping RNCP par mots-clés (sans LLM, zéro hallucination)
```

## Démarrage

### Backend

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Dépendances système
sudo apt install tesseract-ocr tesseract-ocr-fra poppler-utils

cp .env.example .env        # puis ajustez si besoin
uvicorn main:app --reload --port 8000
```

Vérifier que tout est en place :

```bash
curl -s localhost:8000/api/profil/health | python3 -m json.tool
```

### Frontend

```bash
cd frontend
npm install
npm run dev                 # http://localhost:5173
```

Le proxy Vite renvoie `/api` vers `:8000` — rien à configurer en développement.

## Endpoints

| Méthode | Route                 | Rôle                                            |
| ------- | --------------------- | ----------------------------------------------- |
| `GET`   | `/api/health`         | Vie du service                                  |
| `GET`   | `/api/profil/health`  | État de Tesseract, Poppler, Ollama, LinkedIn    |
| `POST`  | `/api/profil/cv`      | `multipart/form-data` : `file` (PDF, 5 Mo max)  |
| `POST`  | `/api/profil/linkedin`| `{"url": "https://linkedin.com/in/…"}`          |

Les deux endpoints d'import renvoient le **même schéma de profil**, de sorte
que l'affichage est identique quelle que soit la source.

## Import LinkedIn

LinkedIn interdit la collecte automatique dans ses CGU et la bloque
techniquement (authentification, détection anti-bot). Trois voies existent :

| Voie                   | Coût     | Mise en œuvre                            |
| ---------------------- | -------- | ---------------------------------------- |
| **Export PDF** (défaut) | gratuit  | L'utilisateur exporte son profil depuis LinkedIn (Profil ▸ Plus ▸ Enregistrer au format PDF) et le dépose dans la zone CV : le même pipeline s'applique. |
| Proxycurl              | ~0,01 $/profil | Renseigner `PROXYCURL_API_KEY` dans `.env`. |
| API officielle         | partenariat | Réservée aux applications validées par LinkedIn. |

Sans clé configurée, l'interface n'affiche pas un bouton qui échouerait :
elle oriente vers l'export PDF.

## Variables d'environnement

| Variable            | Défaut                   | Rôle                                    |
| ------------------- | ------------------------ | --------------------------------------- |
| `TESSERACT_CMD`     | détection auto           | Chemin du binaire Tesseract             |
| `POPPLER_PATH`      | détection auto           | Dossier des binaires Poppler            |
| `OCR_LANG`          | `fra+eng`                | Langues de reconnaissance               |
| `OCR_DPI`           | `300`                    | Résolution de rastérisation             |
| `OLLAMA_URL`        | `http://localhost:11434` | Serveur LLM                             |
| `OLLAMA_MODEL`      | `llama3.1`               | Modèle d'extraction                     |
| `PROXYCURL_API_KEY` | —                        | Active l'import LinkedIn automatique    |
| `CORS_ORIGINS`      | —                        | Origines autorisées, séparées par `,`   |

Sans Ollama, l'extraction bascule sur les règles : le profil s'affiche, avec
un bandeau qui le signale, et moins de compétences sont relevées.

## Reste à habiller

Métiers · Formations · Compétences · Objectifs · Recommandations.
Les entrées sont visibles dans la barre latérale et annoncées comme non
ouvertes, pour situer le parcours sans promettre ce qui n'existe pas encore.
