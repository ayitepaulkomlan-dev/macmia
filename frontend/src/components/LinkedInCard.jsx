import { useState } from 'react'
import { IconCheck, IconLink, IconX } from './Icons.jsx'

/**
 * Import d'un profil LinkedIn par son URL publique.
 *
 * `available` reflète ce que le serveur sait réellement faire : sans clé
 * d'API configurée, LinkedIn refuse la collecte automatique. Plutôt que
 * d'afficher un bouton qui échouera, on oriente vers l'export PDF, qui
 * passe par le même pipeline d'analyse et fonctionne toujours.
 */
export default function LinkedInCard({ available, connected, profileUrl, onImport, onClear, loading }) {
  const [url, setUrl] = useState('')

  return (
    <div
      className="card"
      style={{ padding: 20, display: 'flex', flexDirection: 'column', gap: 12, borderRadius: 14, minWidth: 0 }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <div
          style={{
            width: 38,
            height: 38,
            flex: 'none',
            borderRadius: 9,
            background: 'var(--linkedin)',
            color: '#fff',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            font: "800 15px/1 var(--font)",
          }}
        >
          in
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ font: "700 13.5px/1.3 var(--font)", color: 'var(--ink)' }}>Profil LinkedIn</div>
          <div style={{ fontSize: 11.5, color: 'var(--muted-2)', marginTop: 2 }}>
            Reprenez votre parcours sans ressaisie
          </div>
        </div>
      </div>

      {connected ? (
        <>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              background: '#eefaf2',
              borderRadius: 9,
              padding: '9px 12px',
              color: 'var(--green)',
            }}
          >
            <IconCheck size={15} />
            <span
              style={{
                font: "700 12px/1.3 var(--font)",
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}
            >
              {profileUrl?.replace(/^https?:\/\/(www\.)?/, '') || 'Profil importé'}
            </span>
          </div>
          <button className="btn btn-ghost" style={{ width: '100%' }} onClick={onClear}>
            <IconX size={14} />
            Retirer
          </button>
        </>
      ) : available ? (
        <>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              border: '1px solid var(--line-2)',
              borderRadius: 10,
              padding: '9px 12px',
              background: '#fafbfd',
              color: 'var(--muted-2)',
            }}
          >
            <IconLink size={14} />
            <input
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && url.trim() && onImport(url.trim())}
              placeholder="linkedin.com/in/votre-identifiant"
              disabled={loading}
              style={{
                flex: 1,
                minWidth: 0,
                border: 'none',
                outline: 'none',
                background: 'none',
                font: "400 12.5px/1 var(--font)",
                color: 'var(--ink)',
              }}
            />
          </div>
          <button
            className="btn btn-linkedin"
            onClick={() => onImport(url.trim())}
            disabled={loading || !url.trim()}
          >
            {loading ? <span className="spinner" style={{ borderTopColor: 'var(--linkedin)' }} /> : null}
            {loading ? 'Import en cours…' : 'Importer mon profil'}
          </button>
        </>
      ) : (
        <div
          style={{
            background: 'var(--blue-soft)',
            border: '1px solid var(--blue-border)',
            borderRadius: 10,
            padding: '11px 13px',
          }}
        >
          <div style={{ font: "700 12px/1.4 var(--font)", color: 'var(--ink-2)' }}>
            Passez par l’export PDF
          </div>
          <div style={{ fontSize: 11.5, color: 'var(--muted)', lineHeight: 1.5, marginTop: 4 }}>
            LinkedIn n’autorise pas la collecte automatique depuis ce serveur. Sur votre profil,
            ouvrez <strong>Plus ▸ Enregistrer au format PDF</strong>, puis déposez le fichier dans
            la zone de gauche : il passe par la même analyse.
          </div>
        </div>
      )}
    </div>
  )
}
