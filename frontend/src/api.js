// Client HTTP de l'API MACMIA.
// En dev, VITE_API_BASE est vide : le proxy Vite renvoie /api vers :8000.
const BASE = import.meta.env.VITE_API_BASE || ''

/** Extrait le message d'erreur lisible renvoyé par FastAPI (champ `detail`). */
async function readError(res, fallback) {
  try {
    const data = await res.json()
    if (typeof data?.detail === 'string') return data.detail
    if (Array.isArray(data?.detail)) return data.detail.map((d) => d.msg).join(', ')
  } catch {
    /* réponse non JSON */
  }
  return fallback
}

/** Analyse un CV PDF et renvoie le profil structuré. */
export async function uploadCv(file) {
  const form = new FormData()
  form.append('file', file)

  const res = await fetch(`${BASE}/api/profil/cv`, { method: 'POST', body: form })
  if (!res.ok) throw new Error(await readError(res, "L'analyse du CV a échoué."))
  return res.json()
}

/** Importe un profil depuis son URL LinkedIn publique. */
export async function importLinkedIn(url) {
  const res = await fetch(`${BASE}/api/profil/linkedin`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url }),
  })
  if (!res.ok) throw new Error(await readError(res, "L'import LinkedIn a échoué."))
  return res.json()
}

/** État des dépendances d'extraction côté serveur. */
export async function fetchHealth() {
  const res = await fetch(`${BASE}/api/profil/health`)
  if (!res.ok) throw new Error('Le serveur ne répond pas.')
  return res.json()
}
