import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import Analysis from './pages/Analysis'
import Cleanup from './pages/Cleanup'
import Live from './pages/Live'
import Overview from './pages/Overview'
import RunDetail from './pages/RunDetail'
import Settings from './pages/Settings'
import Start from './pages/Start'
import Tasks from './pages/Tasks'
import { ToastProvider } from './ui'
import { Shell } from './ui/Shell'

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false, staleTime: 2000 } },
})

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <BrowserRouter>
          <Routes>
            <Route element={<Shell />}>
              <Route index element={<Overview />} />
              <Route path="start" element={<Start />} />
              <Route path="live" element={<Live />} />
              <Route path="auswertung" element={<Analysis />} />
              <Route path="lauf/:id?" element={<RunDetail />} />
              <Route path="aufgaben/:id?" element={<Tasks />} />
              <Route path="bereinigen" element={<Cleanup />} />
              <Route path="einstellungen/:tab?" element={<Settings />} />
              <Route path="*" element={<Overview />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </ToastProvider>
    </QueryClientProvider>
  )
}
