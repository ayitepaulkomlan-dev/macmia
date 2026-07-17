import { useRef, useState } from 'react'
import { IconFile, IconUpload, IconX } from './Icons.jsx'

const MAX_MB = 5

/**
 * Dépôt d'un CV PDF, par glisser-déposer ou par sélection.
 * La validation de format et de taille se fait ici pour répondre
 * immédiatement, sans aller-retour serveur.
 */
export default function CvDropzone({ file, onPick, onClear, loading, disabled }) {
  const [over, setOver] = useState(false)
  const [localError, setLocalError] = useState('')
  const inputRef = useRef(null)

  function validate(f) {
    if (!f.name.toLowerCase().endsWith('.pdf')) {
      return 'Déposez un fichier PDF. Les autres formats ne sont pas encore lus.'
    }
    if (f.size > MAX_MB * 1024 * 1024) {
      return `Ce fichier fait ${(f.size / 1024 / 1024).toFixed(1)} Mo. La limite est de ${MAX_MB} Mo.`
    }
    return ''
  }

  function accept(f) {
    if (!f) return
    const err = validate(f)
    setLocalError(err)
    if (!err) onPick(f)
  }

  const idle = !file && !loading

  return (
    <div>
      <label
        onDragOver={(e) => {
          e.preventDefault()
          if (!disabled) setOver(true)
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => {
          e.preventDefault()
          setOver(false)
          if (!disabled) accept(e.dataTransfer.files?.[0])
        }}
        style={{
          display: 'flex',
          flexDirection: idle ? 'column' : 'row',
          alignItems: 'center',
          justifyContent: 'center',
          gap: idle ? 8 : 12,
          minHeight: 148,
          padding: 20,
          borderRadius: 14,
          border: `1.5px dashed ${over ? 'var(--blue)' : file ? '#c9dcc9' : '#d4d9e2'}`,
          background: over ? '#f5f9ff' : file ? '#f6fbf7' : 'var(--surface)',
          cursor: disabled ? 'default' : 'pointer',
          textAlign: 'center',
          transition: 'border-color .15s, background .15s',
          minWidth: 0,
        }}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".pdf"
          style={{ display: 'none' }}
          disabled={disabled}
          onChange={(e) => {
            accept(e.target.files?.[0])
            e.target.value = ''
          }}
        />

        {loading && (
          <>
            <div className="spinner spinner-blue" style={{ width: 26, height: 26, borderWidth: 3 }} />
            <div style={{ font: "700 13.5px/1.3 var(--font)", color: 'var(--ink)' }}>Analyse du CV…</div>
            <div style={{ fontSize: 12, color: 'var(--muted-2)' }}>
              Lecture des colonnes, des sections et des compétences. Comptez 30 à 60 secondes.
            </div>
          </>
        )}

        {idle && (
          <>
            <div
              style={{
                width: 46,
                height: 46,
                borderRadius: 12,
                background: 'var(--blue-soft)',
                color: 'var(--blue)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <IconUpload size={21} />
            </div>
            <div style={{ font: "700 13.5px/1.3 var(--font)", color: 'var(--ink)' }}>
              Glissez votre CV ici
            </div>
            <div style={{ fontSize: 12, color: 'var(--muted-2)' }}>
              ou cliquez pour parcourir · PDF, {MAX_MB} Mo max
            </div>
          </>
        )}

        {file && !loading && (
          <>
            <div
              style={{
                width: 42,
                height: 42,
                flex: 'none',
                borderRadius: 11,
                background: 'var(--surface)',
                color: 'var(--green)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                border: '1px solid #dcefe2',
              }}
            >
              <IconFile size={19} />
            </div>
            <div style={{ flex: 1, minWidth: 0, textAlign: 'left' }}>
              <div
                style={{
                  font: "700 13.5px/1.3 var(--font)",
                  color: 'var(--ink)',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}
              >
                {file.name}
              </div>
              <div style={{ fontSize: 11.5, color: 'var(--green)', fontWeight: 600, marginTop: 2 }}>
                Analysé · {(file.size / 1024).toFixed(0)} Ko
              </div>
            </div>
            <span
              role="button"
              tabIndex={0}
              aria-label="Retirer le CV"
              onClick={(e) => {
                e.preventDefault()
                setLocalError('')
                onClear()
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault()
                  onClear()
                }
              }}
              style={{ flex: 'none', cursor: 'pointer', padding: 6, display: 'flex', color: 'var(--muted-2)' }}
            >
              <IconX size={16} />
            </span>
          </>
        )}
      </label>

      {localError && (
        <div style={{ marginTop: 8, fontSize: 12, color: 'var(--red)', fontWeight: 600 }}>{localError}</div>
      )}
    </div>
  )
}
