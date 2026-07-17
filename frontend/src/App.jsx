import { useState } from 'react'
import Sidebar from './components/Sidebar.jsx'
import Profil from './pages/Profil.jsx'

// L'armoire. Une seule porte est ouverte pour l'instant : le profil.
const PAGES = {
  profil: Profil,
}

export default function App() {
  const [page, setPage] = useState('profil')
  const Page = PAGES[page] || Profil

  return (
    <div className="app">
      <Sidebar current={page} onNavigate={setPage} />
      <main className="main">
        <Page />
      </main>
    </div>
  )
}
