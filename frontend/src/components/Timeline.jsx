import { IconBriefcase, IconCap } from './Icons.jsx'

/**
 * Frise chronologique d'une liste d'entrées datées (expériences ou diplômes).
 * Le point et le filet de gauche donnent la lecture verticale de la maquette.
 */
function TimelineList({ items, accent }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column' }}>
      {items.map((it, i) => {
        const last = i === items.length - 1
        return (
          <div key={i} style={{ display: 'flex', gap: 14, minWidth: 0 }}>
            {/* Rail : pastille + filet */}
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', flex: 'none', paddingTop: 4 }}>
              <span
                style={{
                  width: 11,
                  height: 11,
                  borderRadius: '50%',
                  border: `2.5px solid ${accent}`,
                  background: '#fff',
                  flex: 'none',
                }}
              />
              {!last && <span style={{ flex: 1, width: 2, background: 'var(--line)', marginTop: 2 }} />}
            </div>

            {/* Contenu */}
            <div style={{ flex: 1, minWidth: 0, paddingBottom: last ? 0 : 20 }}>
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  gap: 12,
                  alignItems: 'baseline',
                  flexWrap: 'wrap',
                }}
              >
                <span style={{ font: '700 14.5px/1.3 var(--font)', color: 'var(--ink)' }}>{it.titre}</span>
                {it.periode && (
                  <span style={{ fontSize: 12.5, color: 'var(--muted-2)', fontWeight: 600, flex: 'none' }}>
                    {it.periode}
                  </span>
                )}
              </div>
              {it.sousTitre && (
                <div style={{ fontSize: 12.5, color: accent, fontWeight: 600, marginTop: 3 }}>{it.sousTitre}</div>
              )}
              {it.description && (
                <div style={{ fontSize: 12.5, color: 'var(--muted)', lineHeight: 1.5, marginTop: 5 }}>
                  {it.description}
                </div>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}

function SectionHeader({ Icon, children }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 9, marginBottom: 18 }}>
      <span
        style={{
          width: 30,
          height: 30,
          borderRadius: 8,
          background: 'var(--blue-soft)',
          color: 'var(--blue)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          flex: 'none',
        }}
      >
        <Icon size={16} />
      </span>
      <h3 className="section-title">{children}</h3>
    </div>
  )
}

function periodeExp(e) {
  const fin = e.en_cours ? "Aujourd'hui" : e.fin || ''
  return [e.debut, fin].filter(Boolean).join(' — ')
}

export function ExperienceCard({ experiences }) {
  if (!experiences?.length) return null
  const items = experiences.map((e) => ({
    titre: e.poste || 'Poste',
    sousTitre: [e.entreprise, periodeExp(e)].filter(Boolean).join(' · '),
    description: e.description,
  }))
  return (
    <div className="card">
      <SectionHeader Icon={IconBriefcase}>Expériences professionnelles</SectionHeader>
      <TimelineList items={items} accent="var(--blue)" />
    </div>
  )
}

export function FormationCard({ diplomes }) {
  if (!diplomes?.length) return null
  const items = diplomes.map((d) => ({
    titre: d.titre || 'Formation',
    sousTitre: d.etablissement,
    periode: d.annee || '',
  }))
  return (
    <div className="card">
      <SectionHeader Icon={IconCap}>Formation</SectionHeader>
      <TimelineList items={items} accent="var(--green)" />
    </div>
  )
}
