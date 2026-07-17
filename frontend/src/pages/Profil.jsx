import { useEffect, useState } from 'react'
import { fetchHealth, importLinkedIn, uploadCv } from '../api.js'
import CvDropzone from '../components/CvDropzone.jsx'
import LinkedInCard from '../components/LinkedInCard.jsx'
import ProfileView from '../components/ProfileView.jsx'
import { IconAlert, IconUser } from '../components/Icons.jsx'

export default function Profil() {
  const [profil, setProfil] = useState(null)
  const [file, setFile] = useState(null)
  const [cvLoading, setCvLoading] = useState(false)
  const [liLoading, setLiLoading] = useState(false)
  const [error, setError] = useState('')
  const [health, setHealth] = useState(null)

  useEffect(() => {
    fetchHealth()
      .then(setHealth)
      .catch(() => setHealth({ unreachable: true }))
  }, [])

  async function handleCv(picked) {
    setError('')
    setCvLoading(true)
    try {
      const data = await uploadCv(picked)
      setProfil(data)
      setFile(picked)
    } catch (e) {
      setError(e.message)
      setFile(null)
    } finally {
      setCvLoading(false)
    }
  }

  async function handleLinkedIn(url) {
    setError('')
    setLiLoading(true)
    try {
      const data = await importLinkedIn(url)
      setProfil(data)
    } catch (e) {
      setError(e.message)
    } finally {
      setLiLoading(false)
    }
  }

  const linkedinAvailable = Boolean(health?.linkedin?.proxycurl?.disponible)
  const linkedinConnected = profil?.source === 'linkedin'
  const ocrDown = health && !health.unreachable && !health.cv?.tesseract
  const popplerDown = health && !health.unreachable && health.cv?.tesseract && !health.cv?.poppler
  // Le serveur sait quelle consigne s'applique à son système : on la relaie
  // telle quelle plutôt que d'en figer une côté navigateur.
  const ocrHint = typeof health?.cv?.details?.tesseract === 'string' ? health.cv.details.tesseract : ''
  const popplerHint = typeof health?.cv?.details?.poppler === 'string' ? health.cv.details.poppler : ''

  return (
    <div className="page">
      <div style={{ marginBottom: 22 }}>
        <h1 className="page-title">Mon profil</h1>
        <p className="page-sub">
          Déposez votre CV ou importez votre profil LinkedIn. MACMIA en tire vos compétences
          telles qu’elles y figurent, et les rapproche du référentiel RNCP.
        </p>
      </div>

      {/* ── Sources ──────────────────────────────────────────────────── */}
      <div className="grid-2" style={{ marginBottom: 22 }}>
        <CvDropzone
          file={file}
          loading={cvLoading}
          disabled={cvLoading || ocrDown || popplerDown}
          onPick={handleCv}
          onClear={() => {
            setFile(null)
            setProfil(null)
            setError('')
          }}
        />
        <LinkedInCard
          available={linkedinAvailable}
          connected={linkedinConnected}
          profileUrl={profil?.profil_url}
          loading={liLoading}
          onImport={handleLinkedIn}
          onClear={() => setProfil(null)}
        />
      </div>

      {/* ── Serveur injoignable ou OCR absent ────────────────────────── */}
      {health?.unreachable && (
        <Banner tone="red">
          <strong>L’API ne répond pas.</strong> Démarrez le serveur —{' '}
          <code>uvicorn main:app --port 8000</code> depuis le dossier <code>backend</code>.
        </Banner>
      )}
      {ocrDown && (
        <Banner tone="red">
          <strong>Le lecteur de CV est indisponible.</strong> {ocrHint || 'Tesseract est introuvable.'}
        </Banner>
      )}
      {popplerDown && (
        <Banner tone="red">
          <strong>Le lecteur de CV est indisponible.</strong> {popplerHint || 'Poppler est introuvable.'}
        </Banner>
      )}
      {error && <Banner tone="red">{error}</Banner>}

      {/* ── Profil ou état vide ──────────────────────────────────────── */}
      {profil ? (
        <ProfileView profil={profil} />
      ) : (
        !cvLoading && (
          <div
            className="card"
            style={{ padding: 48, textAlign: 'center', display: 'flex', flexDirection: 'column', alignItems: 'center' }}
          >
            <div
              style={{
                width: 54,
                height: 54,
                borderRadius: 14,
                background: 'var(--blue-soft)',
                color: 'var(--blue)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                marginBottom: 16,
              }}
            >
              <IconUser size={24} />
            </div>
            <div style={{ font: "800 16px/1.3 var(--font)", color: 'var(--ink)' }}>
              Votre profil se construit ici
            </div>
            <p style={{ fontSize: 13.5, color: 'var(--muted)', lineHeight: 1.6, maxWidth: 420, marginTop: 10 }}>
              Déposez votre CV en PDF. MACMIA lit chaque colonne séparément, repère vos sections,
              et en relève vos compétences sans jamais les reformuler.
            </p>
          </div>
        )
      )}
    </div>
  )
}

function Banner({ tone, children }) {
  const tones = {
    red: { bg: 'var(--red-soft)', border: '#f6d5d9', color: '#8a2b35' },
    amber: { bg: 'var(--amber-soft)', border: '#f6e0cd', color: '#7a4a18' },
  }
  const t = tones[tone] || tones.amber
  return (
    <div
      className="rise"
      style={{
        display: 'flex',
        gap: 10,
        alignItems: 'flex-start',
        background: t.bg,
        border: `1px solid ${t.border}`,
        borderRadius: 12,
        padding: '13px 15px',
        color: t.color,
        marginBottom: 22,
        fontSize: 12.5,
        lineHeight: 1.55,
      }}
      role="status"
    >
      <IconAlert size={16} />
      <div>{children}</div>
    </div>
  )
}
