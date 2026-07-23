import { ExperienceCard, FormationCard } from './Timeline.jsx'
import CoveragePanel from './CoveragePanel.jsx'
import { IconAlert, IconMail, IconPhone, IconPin } from './Icons.jsx'

const COMPLETENESS_FIELDS = [
  ['nom', 'Nom'],
  ['poste_actuel', 'Poste'],
  ['email', 'E-mail'],
  ['telephone', 'Téléphone'],
  ['localisation', 'Localisation'],
  ['niveau_etudes', 'Niveau d’études'],
  ['annees_experience', 'Expérience'],
  ['competences_brutes', 'Compétences'],
  ['diplomes', 'Diplômes'],
  ['langues', 'Langues'],
]

function isFilled(value) {
  if (Array.isArray(value)) return value.length > 0
  if (typeof value === 'number') return value > 0
  return Boolean(value && String(value).trim())
}

function completeness(profil) {
  const filled = COMPLETENESS_FIELDS.filter(([k]) => isFilled(profil[k]))
  const missing = COMPLETENESS_FIELDS.filter(([k]) => !isFilled(profil[k])).map(([, label]) => label)
  return { pct: Math.round((filled.length / COMPLETENESS_FIELDS.length) * 100), missing }
}

function initials(nom) {
  if (!nom) return '—'
  return nom.split(/\s+/).filter(Boolean).map((n) => n[0]).join('').slice(0, 2).toUpperCase()
}

function Contact({ Icon, children }) {
  if (!children) return null
  return (
    <span style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12.5, color: 'var(--muted)' }}>
      <Icon size={14} />
      {children}
    </span>
  )
}

export default function ProfileView({ profil }) {
  const { pct, missing } = completeness(profil)
  const blocs = profil.blocs_rncp || []
  const degraded = profil.source === 'regles'
  const nonStructure = profil.meta?.non_structure || {}
  const aDuTexteNonRattache = Object.values(nonStructure).some((v) => v?.length)
  const hasExp = (profil.experiences || []).length > 0
  const hasFormation = (profil.diplomes || []).length > 0

  return (
    <div className="rise" style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      {/* Identité (pleine largeur) */}
      <div className="card card-xl">
        <div style={{ display: 'flex', gap: 20, alignItems: 'center', flexWrap: 'wrap' }}>
          <div style={{ width: 72, height: 72, flex: 'none', borderRadius: '50%', background: 'var(--blue-soft)', color: 'var(--blue)', display: 'flex', alignItems: 'center', justifyContent: 'center', font: '800 26px/1 var(--font)' }}>
            {initials(profil.nom)}
          </div>
          <div style={{ flex: 1, minWidth: 200 }}>
            <div style={{ font: '800 20px/1.1 var(--font)', color: 'var(--ink)' }}>{profil.nom || 'Nom non détecté'}</div>
            <div style={{ fontSize: 13.5, color: 'var(--muted)', marginTop: 4 }}>
              {[profil.poste_actuel, profil.annees_experience ? `${profil.annees_experience} ans d’expérience` : ''].filter(Boolean).join(' · ') || 'Poste non détecté'}
            </div>
            <div style={{ display: 'flex', gap: 16, marginTop: 11, flexWrap: 'wrap' }}>
              <Contact Icon={IconPin}>{profil.localisation}</Contact>
              <Contact Icon={IconMail}>{profil.email}</Contact>
              <Contact Icon={IconPhone}>{profil.telephone}</Contact>
            </div>
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', margin: '22px 0 8px' }}>
          <span style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--ink-3)' }}>Complétude de mon profil</span>
          <span style={{ fontSize: 12.5, fontWeight: 800, color: pct >= 70 ? 'var(--green)' : 'var(--amber)' }}>{pct}%</span>
        </div>
        <div className="progress-track"><div className="progress-fill" style={{ width: `${pct}%` }} /></div>
        {missing.length > 0 && (
          <div style={{ fontSize: 11.5, color: 'var(--muted-2)', marginTop: 9 }}>Non détecté dans le document : {missing.join(', ')}.</div>
        )}
      </div>

      {degraded && (
        <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start', background: 'var(--blue-soft)', border: '1px solid var(--blue-border)', borderRadius: 12, padding: '13px 15px', color: 'var(--ink-2)' }}>
          <IconAlert size={16} />
          <div style={{ fontSize: 12.5, lineHeight: 1.5 }}>
            <strong>Relevé par règles.</strong> Le modèle de langue n’a pas répondu : votre parcours,
            vos diplômes et vos compétences ont été lus directement dans le document. Seul le résumé
            de profil, qui demande une reformulation, n’a pas pu être rédigé.
          </div>
        </div>
      )}

      {/* Corps : contenu principal + panneau latéral */}
      <div className="profile-cols">
        <div style={{ display: 'flex', flexDirection: 'column', gap: 20, minWidth: 0 }}>
          {profil.resume_profil && (
            <div className="card">
              <h3 className="section-title" style={{ marginBottom: 12 }}>Résumé</h3>
              <p style={{ fontSize: 13, color: 'var(--ink-3)', lineHeight: 1.65 }}>{profil.resume_profil}</p>
            </div>
          )}

          {hasExp && <ExperienceCard experiences={profil.experiences} />}
          {hasFormation && <FormationCard diplomes={profil.diplomes} />}

          <div className="card">
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 15 }}>
              <h3 className="section-title">Mes compétences</h3>
              <span className="chip chip-blue">{(profil.competences_brutes || []).length} relevées</span>
            </div>
            {(profil.competences_brutes || []).length === 0 ? (
              <div style={{ fontSize: 12.5, color: 'var(--muted-2)', lineHeight: 1.5 }}>
                Aucune compétence relevée. Vérifiez que votre CV comporte une section « Compétences » clairement titrée.
              </div>
            ) : (
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                {profil.competences_brutes.map((c, i) => <span key={i} className="skill-tag">{c}</span>)}
              </div>
            )}
          </div>

          {blocs.length > 0 && (
            <div className="card">
              <div>
                <h3 className="section-title">Compétences par bloc RNCP</h3>
                <p style={{ fontSize: 12.5, color: 'var(--muted)', marginTop: 6, lineHeight: 1.5 }}>
                  Vos compétences rapprochées du référentiel France Compétences. Les libellés sont ceux de votre CV, jamais reformulés.
                </p>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 16, marginTop: 16 }}>
                {blocs.map((b) => (
                  <div key={b.id}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 9 }}>
                      <span style={{ font: '800 10px/1 var(--font)', letterSpacing: 0.4, color: 'var(--blue)', background: 'var(--blue-soft)', borderRadius: 5, padding: '4px 6px' }}>{b.id.split('_')[0]}</span>
                      <span style={{ font: '700 12.5px/1 var(--font)', color: 'var(--ink-2)' }}>{b.label}</span>
                    </div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 7 }}>
                      {b.competences.map((c, i) => <span key={i} className="skill-tag">{c}</span>)}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        <aside style={{ display: 'flex', flexDirection: 'column', gap: 16, minWidth: 0 }}>
          <CoveragePanel couverture={profil.couverture_rncp} />
          <div className="card">
            <h3 className="section-title" style={{ marginBottom: 12 }}>Parcours</h3>
            <div className="meta-row">
              <span className="meta-key">Expérience</span>
              <span className="meta-val">{profil.annees_experience ? `${profil.annees_experience} ans` : '—'}</span>
            </div>
            <div className="meta-row">
              <span className="meta-key">Niveau d’études</span>
              <span className="meta-val">{profil.niveau_etudes || '—'}</span>
            </div>
            {(profil.langues || []).length > 0 && (
              <div className="meta-row" style={{ borderBottom: 'none' }}>
                <span className="meta-key">Langues</span>
                <span style={{ display: 'flex', gap: 5, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                  {profil.langues.map((l, i) => <span key={i} className="chip chip-gray">{l.langue}{l.niveau ? ` · ${l.niveau}` : ''}</span>)}
                </span>
              </div>
            )}
          </div>
        </aside>
      </div>

      {profil.meta && (
        <details className="card" style={{ padding: '16px 22px' }}>
          <summary style={{ cursor: 'pointer', font: '700 12.5px/1 var(--font)', color: 'var(--ink-3)' }}>Ce que le lecteur a vu dans le document</summary>
          <div style={{ marginTop: 14, fontSize: 12, color: 'var(--muted)', lineHeight: 1.7 }}>
            {profil.meta.pages} page(s) · {profil.meta.blocs_ocr} blocs de texte · {profil.meta.caracteres} caractères · relevé par {profil.source === 'llm+regles' ? 'règles et modèle de langue' : 'règles'}
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 12 }}>
              {(profil.meta.sections || []).map((s, i) => (
                <span key={i} className={`chip ${s.confiance === 'semantic' ? 'chip-green' : 'chip-gray'}`} title={s.confiance === 'semantic' ? 'Titre de section reconnu' : 'Détecté à la mise en forme'}>
                  {s.titre || s.categorie}
                </span>
              ))}
            </div>

            {/* Rien ne disparaît en silence : ce que les règles n'ont pas su
                rattacher est montré tel quel plutôt qu'écarté. */}
            {aDuTexteNonRattache && (
              <div style={{ marginTop: 16, paddingTop: 14, borderTop: '1px solid var(--line-3)' }}>
                <div style={{ font: '700 12px/1 var(--font)', color: 'var(--ink-3)', marginBottom: 8 }}>
                  Lu dans le document, non rattaché
                </div>
                {Object.entries(nonStructure).map(([section, lignes]) => (
                  <div key={section} style={{ marginBottom: 8 }}>
                    <span style={{ color: 'var(--muted-2)', textTransform: 'capitalize' }}>{section} : </span>
                    {lignes.join(' · ')}
                  </div>
                ))}
              </div>
            )}
          </div>
        </details>
      )}
    </div>
  )
}
