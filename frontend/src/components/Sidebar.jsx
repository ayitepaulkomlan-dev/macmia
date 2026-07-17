import { IconBriefcase, IconCap, IconChart, IconSparkle, IconTarget, IconUser } from './Icons.jsx'
import logo from '/macmia-logo.png'

// L'armoire complète. Seul « Profil » est habillé pour l'instant ;
// les autres entrées restent visibles pour situer le parcours, mais
// annoncent honnêtement qu'elles ne sont pas encore ouvertes.
const SECTIONS = [
  {
    items: [{ id: 'profil', label: 'Mon profil', Icon: IconUser, ready: true }],
  },
  {
    label: 'EXPLORER',
    items: [
      { id: 'metiers', label: 'Métiers', Icon: IconBriefcase },
      { id: 'formations', label: 'Formations', Icon: IconCap },
      { id: 'competences', label: 'Compétences', Icon: IconChart },
    ],
  },
  {
    label: 'M’ORIENTER',
    items: [
      { id: 'objectifs', label: 'Mes objectifs', Icon: IconTarget },
      { id: 'recommandations', label: 'Recommandations', Icon: IconSparkle },
    ],
  },
]

export default function Sidebar({ current, onNavigate }) {
  return (
    <aside className="sidebar">
      <div className="sidebar-logo">
        <img src={logo} alt="MACMIA" />
      </div>

      <nav className="sidebar-nav" aria-label="Navigation principale">
        {SECTIONS.map((section, i) => (
          <div key={section.label || i}>
            {section.label && <div className="nav-label">{section.label}</div>}
            {section.items.map(({ id, label, Icon, ready }) => (
              <button
                key={id}
                className={`nav-btn ${current === id ? 'is-active' : ''} ${ready ? '' : 'is-todo'}`}
                onClick={() => ready && onNavigate(id)}
                disabled={!ready}
                aria-current={current === id ? 'page' : undefined}
              >
                <Icon size={18} />
                <span>{label}</span>
                {!ready && <span className="nav-soon">BIENTÔT</span>}
              </button>
            ))}
          </div>
        ))}
      </nav>

      <div
        style={{
          margin: '10px 12px 14px',
          padding: '13px 15px',
          borderRadius: 13,
          background: '#f2f6fc',
          border: '1px solid #e5ecf7',
        }}
      >
        <div style={{ font: "700 12px/1.3 var(--font)", color: 'var(--ink)' }}>IMT × France 2030</div>
        <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 5, lineHeight: 1.45 }}>
          Orientation vers les formations IA, Data et Industrie du Futur.
        </div>
      </div>
    </aside>
  )
}
