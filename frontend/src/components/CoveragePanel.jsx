import { IconCheck } from './Icons.jsx'

/**
 * Anneau de progression en SVG. La valeur affichée est la couverture du
 * référentiel RNCP — une mesure vérifiable (part des 8 blocs pourvus), et
 * non une note d'employabilité que rien ne fonderait à ce stade.
 */
function Gauge({ value }) {
  const size = 132
  const stroke = 13
  const r = (size - stroke) / 2
  const c = 2 * Math.PI * r
  const dash = (value / 100) * c
  const tone = value >= 66 ? 'var(--green)' : value >= 33 ? 'var(--amber)' : 'var(--red)'

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label={`Couverture ${value}%`}>
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#eef0f4" strokeWidth={stroke} />
      <circle
        cx={size / 2}
        cy={size / 2}
        r={r}
        fill="none"
        stroke={tone}
        strokeWidth={stroke}
        strokeLinecap="round"
        strokeDasharray={`${dash} ${c - dash}`}
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
        style={{ transition: 'stroke-dasharray .6s ease' }}
      />
      <text
        x="50%"
        y="50%"
        dominantBaseline="central"
        textAnchor="middle"
        style={{ font: '800 30px/1 var(--font)', fill: 'var(--ink)' }}
      >
        {value}
      </text>
    </svg>
  )
}

export default function CoveragePanel({ couverture }) {
  if (!couverture) return null
  const { score, forces = [], ecarts = [] } = couverture

  const verdict =
    score >= 66
      ? 'Profil bien couvert sur le référentiel IA / Data.'
      : score >= 33
        ? 'Bonne base, quelques blocs à renforcer.'
        : 'Profil à consolider sur plusieurs blocs.'

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Jauge */}
      <div className="card" style={{ textAlign: 'center' }}>
        <div style={{ fontSize: 12.5, color: 'var(--muted)', marginBottom: 12 }}>Couverture du référentiel</div>
        <div style={{ display: 'flex', justifyContent: 'center' }}>
          <Gauge value={score} />
        </div>
        <div style={{ fontSize: 12.5, color: 'var(--muted)', marginTop: 12, lineHeight: 1.5 }}>{verdict}</div>
      </div>

      {/* Forces + écarts */}
      {(forces.length > 0 || ecarts.length > 0) && (
        <div className="card">
          {forces.length > 0 && (
            <>
              <div style={{ font: '700 13px/1 var(--font)', color: 'var(--ink)', marginBottom: 12 }}>
                Points forts
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 9, marginBottom: ecarts.length ? 18 : 0 }}>
                {forces.slice(0, 4).map((f) => (
                  <div key={f.id} style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
                    <span style={{ color: 'var(--green)', flex: 'none', marginTop: 1 }}>
                      <IconCheck size={15} />
                    </span>
                    <span style={{ fontSize: 12.5, color: 'var(--ink-3)', lineHeight: 1.4 }}>
                      {f.label}
                      <span style={{ color: 'var(--muted-2)' }}> · {f.nb}</span>
                    </span>
                  </div>
                ))}
              </div>
            </>
          )}

          {ecarts.length > 0 && (
            <>
              <div style={{ font: '700 13px/1 var(--font)', color: 'var(--ink)', marginBottom: 12 }}>
                À renforcer
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
                {ecarts.slice(0, 4).map((e) => (
                  <div key={e.id} style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
                    <span
                      style={{
                        width: 7,
                        height: 7,
                        borderRadius: '50%',
                        background: '#7c5cd6',
                        flex: 'none',
                        marginTop: 5,
                      }}
                    />
                    <span style={{ fontSize: 12.5, color: 'var(--ink-3)', lineHeight: 1.4 }}>{e.label}</span>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  )
}
