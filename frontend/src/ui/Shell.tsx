// Rahmen der App: Kopfleiste mit Marke, Menü, laufendem Durchgang und BW-Status; Fußzeile mit Claim,
// Schemawechsel und Version.
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, NavLink, Outlet } from 'react-router-dom'
import { api } from '../api'
import { usd } from '../format'
import { t } from '../texts'
import { BwState, Button, ErrorNote, Glyph, Tag, useTheme } from './index'
import { Mark, Wordmark } from './Logo'

export type Status = {
  version: string
  bw: { system: string; state: string; detail: string } | null
  running: { id: number; code: string; alive: boolean } | null
  readiness: { key: string; ok: boolean; detail: string }[]
  ready: boolean
  demo?: boolean
  notice_accepted?: string | null
}

export function useStatus() {
  return useQuery<Status>({ queryKey: ['status'], queryFn: () => api.get('/status'), refetchInterval: 5000 })
}

const NAV: { to: string; label: string; end?: boolean }[] = [
  { to: '/', label: t.common.nav.overview, end: true },
  { to: '/start', label: t.common.nav.start },
  { to: '/live', label: t.common.nav.live },
  { to: '/auswertung', label: t.common.nav.analysis },
  { to: '/lauf', label: t.common.nav.run },
  { to: '/aufgaben', label: t.common.nav.tasks },
  { to: '/bereinigen', label: t.common.nav.cleanup },
  { to: '/einstellungen', label: t.common.nav.settings },
]

type BarLive = { batch: { cost?: number | null; cost_limit?: number | null } | null; progress?: { total: number; done: number } }

/** Laufender Durchgang in der Kopfleiste: Fortschritt und Kosten gegen das Limit, von jeder Seite aus sichtbar. */
function RunningNow({ id, code }: { id: number; code: string }) {
  const live = useQuery<BarLive>({ queryKey: ['bar-live', id], queryFn: () => api.get(`/live?batch=${id}`), refetchInterval: 5000 })
  const progress = live.data?.progress
  const cost = live.data?.batch?.cost ?? null
  const limit = live.data?.batch?.cost_limit ?? null
  return (
    <Link to="/live" className="bar__run" aria-label={t.common.running(code)}>
      <span className="state state--live">
        <Glyph kind="live" />
        {progress ? t.common.runningShort(code, progress.done, progress.total) : t.common.running(code)}
      </span>
      {cost !== null && limit !== null && limit > 0 && (
        <>
          <span className="bar__budget" role="img" title={t.common.budget(usd(cost, 2), usd(limit, 2))} aria-label={t.common.budget(usd(cost, 2), usd(limit, 2))}>
            <span style={{ width: `${Math.min(100, (cost / limit) * 100)}%` }} />
          </span>
          <span className="num bar__cost">{t.common.budget(usd(cost, 2), usd(limit, 2))}</span>
        </>
      )}
    </Link>
  )
}

/** Nutzungshinweis, bis er für diese Datenbank bestätigt ist. Steht über jeder Seite; Durchgänge
 * lassen sich vorher nicht starten. */
function NoticeGate() {
  const queryClient = useQueryClient()
  const accept = useMutation({
    mutationFn: () => api.post('/notice'),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['status'] })
      queryClient.invalidateQueries({ queryKey: ['start-options'] })
    },
  })
  return (
    <section className="gate" aria-labelledby="gate-title">
      <h2 id="gate-title" className="gate__title">
        <Glyph kind="warn" />
        {t.common.notice.title}
      </h2>
      <ul className="gate__points">
        {t.common.notice.points.map((point) => (
          <li key={point}>{point}</li>
        ))}
      </ul>
      <div className="gate__actions">
        <Button variant="primary" busy={accept.isPending} onClick={() => accept.mutate()}>
          {t.common.notice.accept}
        </Button>
        <span className="muted small">{t.common.notice.note}</span>
      </div>
      {accept.isError && <ErrorNote error={accept.error} />}
    </section>
  )
}

export function Shell() {
  const status = useStatus()
  const [theme, toggleTheme] = useTheme()
  const running = status.data?.running
  return (
    <div className="shell">
      <header className="bar">
        <Link to="/" className="bar__brand" aria-label={t.common.appName}>
          <Mark size={22} />
          <Wordmark size={17} />
        </Link>
        <nav className="bar__nav" aria-label="Hauptmenü">
          {NAV.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.end} className="bar__link">
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="bar__status">
          {running?.alive && <RunningNow id={running.id} code={running.code} />}
          {status.data?.demo && <Tag title={t.common.demoTitle}>{t.common.demo}</Tag>}
          {status.data &&
            !status.data.demo &&
            (status.data.bw ? (
              <Link to="/einstellungen/bw">
                <BwState status={status.data.bw} system={status.data.bw.system} />
              </Link>
            ) : (
              <Link to="/einstellungen/bw">{t.common.bw.none}</Link>
            ))}
        </div>
      </header>
      {status.data && !status.data.demo && status.data.notice_accepted === null && <NoticeGate />}
      <div className="main">
        <Outlet />
      </div>
      <footer className="foot">
        <span>{t.common.claim}</span>
        <span className="foot__right">
          <button type="button" className="btn btn--small" onClick={toggleTheme}>
            {theme === 'dark' ? t.common.theme.toLight : t.common.theme.toDark}
          </button>
          {status.data ? t.common.version(status.data.version) : ''}
        </span>
      </footer>
    </div>
  )
}
