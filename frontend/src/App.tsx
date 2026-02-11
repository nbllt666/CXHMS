import { Routes, Route } from 'react-router-dom'
import { Layout } from './components/Layout'
import { ChatPage } from './pages/ChatPage'
import { MemoriesPage } from './pages/MemoriesPage'
import { ArchivePage } from './pages/ArchivePage'
import { SettingsPage } from './pages/SettingsPage'
import { AcpPage } from './pages/AcpPage'
import { ToolsPage } from './pages/ToolsPage'
import { AgentsPage } from './pages/AgentsPage'
import { useThemeStore } from './store/themeStore'
import { ErrorBoundary } from './components/ErrorBoundary'

function App() {
  const { theme } = useThemeStore()

  return (
    <ErrorBoundary>
      <div className={theme}>
        <Routes>
          <Route path="/" element={<Layout />}>
            <Route index element={<ChatPage />} />
            <Route path="memories" element={<MemoriesPage />} />
            <Route path="archive" element={<ArchivePage />} />
            <Route path="agents" element={<AgentsPage />} />
            <Route path="acp" element={<AcpPage />} />
            <Route path="tools" element={<ToolsPage />} />
            <Route path="settings" element={<SettingsPage />} />
          </Route>
        </Routes>
      </div>
    </ErrorBoundary>
  )
}

export default App
