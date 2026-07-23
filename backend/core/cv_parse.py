"""
core/cv_parse.py — Lecture déterministe des sections d'un CV
============================================================
Ce module est la source de vérité de l'extraction : il lit ce que l'OCR et la
segmentation ont isolé, sans modèle de langue, donc sans invention possible.

Principe directeur : **ne jamais perdre une ligne en silence**. Chaque parseur
renvoie ce qu'il a su structurer *et* la liste des lignes qu'il n'a pas su
rattacher. L'appelant peut ainsi les afficher plutôt que de les escamoter.

Les mises en page de CV étant libres, les parseurs raisonnent sur des signaux
larges plutôt que sur un format attendu. Pour les diplômes en particulier,
l'entrée est délimitée par l'apparition d'une année — pas par un ordre imposé
entre l'intitulé et l'établissement, qui varie d'un CV à l'autre :

    Wild Code School - Anglet, France.              ← établissement d'abord
    Formation en Développement Web (1 an) 2021.     ← diplôme, année en fin

    Master Économétrie & Statistiques               ← intitulé d'abord
    Université Paris-Dauphine — 2019
"""

from __future__ import annotations

import re
import unicodedata

# ── Signaux lexicaux ──────────────────────────────────────────────────────────

ANNEE_RE = re.compile(r"\b(19[5-9]\d|20[0-4]\d)\b")

# Puces et tirets d'énumération, dans leurs variantes typographiques et OCR
PUCE_RE = re.compile(r"^\s*[-–—•·▪▸►*+o○●‣⁃]\s*")

ETABLISSEMENT_MOTS = (
    "ecole", "école", "universite", "université", "institut", "school", "faculte",
    "faculté", "lycee", "lycée", "college", "collège", "iut", "cnam", "cfa",
    "academy", "academie", "académie", "campus", "center", "centre de formation",
    "polytech", "ensam", "esc ", "insa", "epitech", "epita", "hei", "estp",
    "university", "college", "sup de", "isep", "efrei", "ynov", "openclassrooms",
)

DIPLOME_MOTS = (
    "master", "licence", "bachelor", "doctorat", "phd", "ingenieur", "ingénieur",
    "diplome", "diplôme", "diplomé", "diplômé", "baccalaureat", "baccalauréat",
    "bac ", "dut", "bts", "mba", "msc", "bsc", "formation", "certificat",
    "certification", "titre professionnel", "cursus", "cycle", "prepa", "prépa",
    "deug", "dess", "dea", "cap ", "bep ", "mastere", "mastère", "post-graduate",
)

NIVEAU_LANGUE_RE = re.compile(
    r"\b(natif|native|maternelle?|bilingue|courant|couramment|intermediaire|"
    r"intermédiaire|debutant|débutant|scolaire|notions?|fluent|"
    r"[ABC][12])\b",
    re.IGNORECASE,
)

LANGUES_CONNUES = (
    "francais", "français", "anglais", "english", "espagnol", "spanish", "allemand",
    "german", "italien", "portugais", "arabe", "chinois", "mandarin", "russe",
    "japonais", "neerlandais", "néerlandais", "polonais", "turc", "hindi", "wolof",
    "ewe", "mina", "kabye", "swahili", "lingala", "bambara",
)

# Graphie d'affichage, l'OCR et la casse d'origine étant peu fiables
LANGUES_AFFICHAGE = {
    "francais": "Français", "english": "Anglais", "spanish": "Espagnol",
    "german": "Allemand", "neerlandais": "Néerlandais",
}


def _norm(s: str) -> str:
    """Minuscule sans accents — pour comparer malgré l'OCR et la casse."""
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def _compile_mots(mots: tuple) -> list:
    """
    Compile des motifs encadrés de frontières alphabétiques.

    La recherche en sous-chaîne est piégeuse sur ce vocabulaire : « Bordeaux »
    contient « dea », « escalade » contient « esc », « information » contient
    « iut » à l'envers dans certaines graphies OCR. Un établissement se
    retrouverait alors classé comme diplôme.
    """
    return [re.compile(rf"(?<![a-z]){re.escape(m.strip())}(?![a-z])") for m in mots]


_ETAB_PATTERNS = None
_DIPL_PATTERNS = None


def _lignes(section_text: str) -> list:
    """Lignes non vides d'une section, titre de section exclu."""
    return [l.strip() for l in (section_text or "").split("\n") if l.strip()]


def _sans_puce(ligne: str) -> str:
    return PUCE_RE.sub("", ligne).strip()


def _est_titre_section(ligne: str) -> bool:
    """Le titre de section lui-même ne fait pas partie du contenu."""
    n = _norm(_sans_puce(ligne)).rstrip(" :.")
    return n in {
        "formation", "formations", "education", "diplomes", "diplome", "etudes",
        "parcours academique", "cursus", "competences", "competence", "skills",
        "langues", "languages", "experience", "experiences",
        "experience professionnelle", "experiences professionnelles",
    }


# ══════════════════════════════════════════════════════════════════════════════
# Diplômes
# ══════════════════════════════════════════════════════════════════════════════

def _role_ligne(ligne: str) -> str:
    """'etablissement', 'diplome' ou 'inconnu', d'après le vocabulaire employé."""
    global _ETAB_PATTERNS, _DIPL_PATTERNS
    if _ETAB_PATTERNS is None:
        _ETAB_PATTERNS = _compile_mots(ETABLISSEMENT_MOTS)
        _DIPL_PATTERNS = _compile_mots(DIPLOME_MOTS)

    n = _norm(ligne)
    etab = any(p.search(n) for p in _ETAB_PATTERNS)
    dipl = any(p.search(n) for p in _DIPL_PATTERNS)
    if dipl and not etab:
        return "diplome"
    if etab and not dipl:
        return "etablissement"
    if dipl and etab:
        # « Diplômé d'une École de Commerce » : le verbe l'emporte sur le lieu
        return "diplome"
    return "inconnu"


def _nettoie_intitule(ligne: str) -> str:
    """Retire l'année, la ponctuation terminale et les puces — garde le reste tel quel."""
    s = _sans_puce(ligne)
    s = ANNEE_RE.sub("", s)
    s = re.sub(r"\s*[-–—:,]\s*$", "", s.strip())
    s = re.sub(r"\s{2,}", " ", s)
    return s.strip(" .;,-–—:")


def _scinde_ligne_unique(texte: str) -> tuple:
    """
    Sépare « Master Data Science, Université de Montpellier » en intitulé et
    établissement. Quand une entrée tient sur une seule ligne, l'établissement
    suit souvent une virgule ou un tiret : on ne le scinde que si le fragment
    de droite porte bien un vocabulaire d'établissement, pour ne pas couper un
    intitulé qui contient simplement une virgule.
    """
    for sep in (",", " - ", " – ", " — ", " | "):
        if sep not in texte:
            continue
        gauche, _, droite = texte.partition(sep)
        gauche, droite = gauche.strip(), droite.strip()
        if len(gauche) < 3 or len(droite) < 3:
            continue
        if _role_ligne(droite) == "etablissement" and _role_ligne(gauche) != "etablissement":
            return gauche, droite
    return texte, ""


def _entree_vers_diplome(entree: list) -> dict | None:
    """Transforme un groupe de lignes en un diplôme structuré."""
    annees = [int(a) for l in entree for a in ANNEE_RE.findall(l)]
    # Une entrée peut porter une plage (2019-2021) : l'année de diplôme est la dernière
    annee = max(annees) if annees else 0

    titre, etablissement = "", ""
    candidats = [(l, _role_ligne(l)) for l in entree]
    attribues = set()

    for l, role in candidats:
        texte = _nettoie_intitule(l)
        if not texte:
            continue
        if role == "diplome" and not titre:
            titre = texte
            attribues.add(texte)
        elif role == "etablissement" and not etablissement:
            etablissement = texte
            attribues.add(texte)

    # Lignes au vocabulaire neutre (« INSEEC - Bordeaux, France. ») : elles
    # comblent le champ encore vide plutôt que d'être écartées.
    restants = [t for t in (_nettoie_intitule(l) for l, _ in candidats)
                if t and t not in attribues]
    if restants:
        if titre and not etablissement:
            etablissement = restants[0]
        elif etablissement and not titre:
            titre = max(restants, key=len)
        elif not titre and not etablissement:
            titre = max(restants, key=len)
            autres = [r for r in restants if r != titre]
            if autres:
                etablissement = autres[0]

    # Entrée tenant sur une seule ligne : l'établissement y est peut-être inclus
    if titre and not etablissement:
        titre, etablissement = _scinde_ligne_unique(titre)

    if not (titre or etablissement):
        return None
    return {
        "titre": titre or etablissement,
        "etablissement": etablissement if titre else "",
        "annee": annee,
    }


def _groupe_entrees(lignes: list) -> list:
    """
    Regroupe les lignes en entrées de formation.

    Deux délimiteurs, choisis selon ce que le CV offre :
      - les puces, quand elles sont présentes — elles marquent explicitement le
        début de chaque entrée, y compris lorsque l'année figure sur la ligne
        de titre et que l'établissement suit en dessous ;
      - l'apparition d'une année sinon, seul repère commun aux mises en page
        sans puces.
    """
    debuts_puce = [i for i, l in enumerate(lignes) if PUCE_RE.match(l)]
    if len(debuts_puce) >= 2:
        entrees = []
        for rang, depart in enumerate(debuts_puce):
            fin = debuts_puce[rang + 1] if rang + 1 < len(debuts_puce) else len(lignes)
            entrees.append(lignes[depart:fin])
        if debuts_puce[0] > 0:  # lignes avant la première puce
            entrees.insert(0, lignes[: debuts_puce[0]])
        return entrees

    entrees, courante = [], []
    for ligne in lignes:
        courante.append(ligne)
        if ANNEE_RE.search(ligne):
            entrees.append(courante)
            courante = []
    if courante:  # entrée finale sans année : conservée malgré tout
        entrees.append(courante)
    return entrees


def parse_diplomes(section_text: str) -> tuple:
    """
    Découpe la section Formation en diplômes.

    Renvoie (diplomes, lignes_non_structurees).
    """
    lignes = [l for l in _lignes(section_text) if not _est_titre_section(l)]
    if not lignes:
        return [], []

    diplomes, non_structurees = [], []
    for entree in _groupe_entrees(lignes):
        d = _entree_vers_diplome(entree)
        if d:
            diplomes.append(d)
        else:
            non_structurees.extend(entree)

    return diplomes, non_structurees


# ══════════════════════════════════════════════════════════════════════════════
# Compétences
# ══════════════════════════════════════════════════════════════════════════════

_SEPARATEURS = re.compile(r"\s*[|;·•]\s*|\s{3,}")


def parse_competences(section_text: str) -> tuple:
    """
    Relève les compétences d'une section, sous les formes courantes :
      - une par ligne, avec ou sans puce
      - « Catégorie : a, b, c » → a, b, c
      - séparées par |, ;, • ou de larges espaces

    Renvoie (competences, lignes_non_structurees).
    """
    competences, seen = [], set()

    def ajoute(txt: str):
        t = txt.strip(" .;,·•-–—")
        if not t or len(t) < 2 or len(t) > 160:
            return
        key = _norm(t)
        if key in seen:
            return
        seen.add(key)
        competences.append(t)

    for ligne in _lignes(section_text):
        if _est_titre_section(ligne):
            continue
        ligne = _sans_puce(ligne)

        # « Catégorie : valeur1, valeur2 » — on garde les valeurs, pas l'étiquette
        m = re.match(r"^([^:]{2,45})\s*:\s*(.+)$", ligne)
        if m:
            valeurs = m.group(2)
            morceaux = [p for p in re.split(r",|\bet\b", valeurs) if p.strip()]
            # Une valeur unique et longue est une phrase, pas une liste
            if len(morceaux) > 1:
                for p in morceaux:
                    ajoute(p)
            else:
                ajoute(valeurs)
            continue

        parts = [p for p in _SEPARATEURS.split(ligne) if p and p.strip()]
        if len(parts) > 1:
            for p in parts:
                ajoute(p)
        else:
            ajoute(ligne)

    return competences, []


# ══════════════════════════════════════════════════════════════════════════════
# Langues
# ══════════════════════════════════════════════════════════════════════════════

def parse_langues(section_text: str) -> tuple:
    """
    Relève les langues et leur niveau : « Anglais C1 », « Français : natif »,
    « Espagnol (courant) ». Renvoie (langues, lignes_non_structurees).
    """
    langues, seen = [], set()

    for ligne in _lignes(section_text):
        if _est_titre_section(ligne):
            continue
        ligne = _sans_puce(ligne)
        n = _norm(ligne)

        for langue in LANGUES_CONNUES:
            if langue not in n:
                continue
            nom = LANGUES_AFFICHAGE.get(langue, langue.capitalize())
            if _norm(nom) in seen:
                break
            # Le niveau est cherché après le nom de la langue
            suite = ligne[n.find(langue) + len(langue):]
            m = NIVEAU_LANGUE_RE.search(suite) or NIVEAU_LANGUE_RE.search(ligne)
            niveau = m.group(1).capitalize() if m else ""
            if niveau.lower() in ("maternelle", "maternel", "native"):
                niveau = "Natif"
            seen.add(_norm(nom))
            langues.append({"langue": nom, "niveau": niveau})
            break

    return langues, []


# ══════════════════════════════════════════════════════════════════════════════
# Fusion LLM ↔ règles
# ══════════════════════════════════════════════════════════════════════════════

def _cle_diplome(d: dict) -> str:
    return _norm(f"{d.get('titre','')} {d.get('etablissement','')}")[:60]


def fusionne_diplomes(a: list, b: list) -> list:
    """
    Union de deux relevés de diplômes, sans doublon.

    L'union — et non l'intersection — est délibérée : un diplôme vu par un seul
    des deux relevés doit subsister. C'est ce qui empêche qu'une formation
    disparaisse parce qu'un seul des deux lecteurs l'a manquée.
    """
    fusion, vus = [], set()
    for source in (a or [], b or []):
        for d in source:
            if not d or not (d.get("titre") or d.get("etablissement")):
                continue
            k = _cle_diplome(d)
            if k in vus:
                # Complète l'entrée déjà retenue si elle était plus pauvre
                for existant in fusion:
                    if _cle_diplome(existant) == k:
                        if not existant.get("annee") and d.get("annee"):
                            existant["annee"] = d["annee"]
                        if not existant.get("etablissement") and d.get("etablissement"):
                            existant["etablissement"] = d["etablissement"]
                continue
            vus.add(k)
            fusion.append(dict(d))
    return fusion


def fusionne_listes(a: list, b: list) -> list:
    """Union de deux listes de chaînes, sans doublon, ordre de a préservé."""
    fusion, vus = [], set()
    for source in (a or [], b or []):
        for item in source:
            if not isinstance(item, str):
                continue
            t = item.strip()
            k = _norm(t)
            if not t or k in vus:
                continue
            vus.add(k)
            fusion.append(t)
    return fusion


def fusionne_langues(a: list, b: list) -> list:
    """Union de deux relevés de langues ; le niveau non vide l'emporte."""
    fusion, index = [], {}
    for source in (a or [], b or []):
        for l in source:
            if not isinstance(l, dict) or not l.get("langue"):
                continue
            k = _norm(l["langue"])
            if k in index:
                if not index[k].get("niveau") and l.get("niveau"):
                    index[k]["niveau"] = l["niveau"]
                continue
            entry = {"langue": l["langue"], "niveau": l.get("niveau", "")}
            index[k] = entry
            fusion.append(entry)
    return fusion
