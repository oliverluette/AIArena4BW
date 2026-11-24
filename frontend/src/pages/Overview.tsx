// Übersicht: laufender Durchgang, Rangliste je Aufgabe, alle Durchgänge.
import { useQuery } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { dateTime, duration, num, percent, usd } from '../format'
import { t } from '../texts'
import { Empty, ErrorNote, Glyph, Loading, Page, RunState, Section, Tag } from '../ui'
import { FormCurve, FormLegend, type FormKind } from '../ui/FormCurve'
import { useStatus } from '../ui/Shell'

const tx = t.overview

type Entry = {
  label: string
  vendor: string
  rank: number
  passed: number
  verified: number
  pass_rate: number | null
  cost_per_pass: number | null
  seconds_finished: number | null
  runs: number
  /** Läufe des Eintrags in zeitlicher Folge; fehlt bei älterem Backend. */
  form?: { id: number; run_code: string; verdict: FormKind }[]
}
type Board = { task: string; task_id: string; task_version: number; runs: number; entries: Entry[] }

export default function Overview() {
  const navigate = useNavigate()
  const status = useStatus()
  const batches = useQuery<any[]>({ queryKey: ['batches'], queryFn: () => api.get('/batches'), refetchInterval: 5000 })
  const boards = useQuery<Board[]>({ queryKey: ['leaderboard'], queryFn: () => api.get('/leaderboard'), refetchInterval: 15000 })

  const notReady = status.data && !status.data.ready
  const list = batches.data ?? []
  const counted = list.filter((b) => !b.hidden)
  const verified = counted.reduce((sum, b) => sum + (b.verified || 0), 0)
  const passed = counted.reduce((sum, b) => sum + (b.passed || 0), 0)
  const cost = list.reduce((sum, b) => sum + (b.cost || 0), 0)
  const models = new Set((boards.data ?? []).flatMap((b) => b.entries.map((e) => e.label))).size
  const running = list.find((b) => b.status === 'running' && b.alive)

  return (
    <Page title={tx.title} lead={tx.lead} actions={<Link className="btn btn--primary" to="/start">{t.common.nav.start}</Link>}>
      {notReady && (
        <Section>
          <Empty title={tx.setupTitle} action={<Link className="btn btn--primary" to="/einstellungen">{tx.setupAction}</Link>}>
            <p>{tx.setupText}</p>
            <ul style={{ listStyle: 'none', padding: 0, margin: '12px 0 0' }}>
              {status.data!.readiness.map((item) => (
                <li key={item.key} className={`state state--${item.ok ? 'pass' : 'neutral'}`} style={{ display: 'flex', padding: '3px 0' }}>
                  <Glyph kind={item.ok ? 'pass' : 'open'} />
                  <span style={{ color: 'var(--text)', fontWeight: 400 }}>{tx.readiness[item.key] ?? item.key}</span>
                </li>
              ))}
            </ul>
          </Empty>
        </Section>
      )}

      {running && (
        <Section title={tx.runningTitle}>
          <Link to="/live" className="panel row row--between" style={{ textDecoration: 'none' }}>
            <span className="row">
              <span className="state state--live">
                <Glyph kind="live" size={14} />
              </span>
              <strong>{running.code}</strong>
              <span className="secondary">{tx.scope(running.run_count, running.model_count, running.task_count)}</span>
            </span>
            <span className="secondary num">
              {running.runs_done} / {running.run_count} · {usd(running.cost)}
            </span>
          </Link>
        </Section>
      )}

      {!notReady && list.length === 0 && !batches.isLoading && (
        <Section>
          <Empty title={tx.emptyTitle} action={<Link className="btn btn--primary" to="/start">{tx.emptyAction}</Link>}>
            {tx.emptyText}
          </Empty>
        </Section>
      )}

      {verified > 0 && (
        <Section>
          <p className="summary">
            <strong>{percent(passed / verified)}</strong> {tx.figures.passRate} · <strong>{num(verified)}</strong> {tx.figures.runs} · <strong>{num(models)}</strong>{' '}
            {tx.figures.models} · <strong>{usd(cost, cost >= 100 ? 0 : 2)}</strong> {tx.figures.cost}
          </p>
        </Section>
      )}

      {list.length > 0 && (
        <Section title={tx.boardTitle} note={tx.boardNote}>
          {boards.isLoading && <Loading />}
          <ErrorNote error={boards.error} />
          {boards.data && boards.data.length === 0 && <p className="muted">{tx.boardEmpty}</p>}
          <div className="grid grid--2">
            {(boards.data ?? []).slice(0, 4).map((board) => (
              <Leaderboard key={board.task} board={board} />
            ))}
          </div>
          {(boards.data ?? []).length > 0 && (
            <p className="legend">
              <span>{tx.board.legend}</span>
              <span className="spacer" />
              <span>
                <i className="zone zone--top" />
                {t.analysis.models.zoneTop}
              </span>
              <span>
                <i className="zone zone--low" />
                {t.analysis.models.zoneLow}
              </span>
              <FormLegend kinds={['pass', 'fail', 'open']} />
            </p>
          )}
        </Section>
      )}

      {list.length > 0 && (
        <Section title={tx.batchesTitle} note={tx.batchesNote(list.length)}>
          <div className="table-wrap">
            <table className="table table--click">
              <thead>
                <tr>
                  <th>{tx.col.code}</th>
                  <th>{tx.col.date}</th>
                  <th>{tx.col.status}</th>
                  <th>{tx.col.system}</th>
                  <th>{tx.col.scope}</th>
                  <th className="right">{tx.col.passed}</th>
                  <th className="right">{tx.col.cost}</th>
                  <th>{tx.col.note}</th>
                </tr>
              </thead>
              <tbody>
                {list.map((b) => (
                  <tr key={b.id} className={b.hidden ? 'is-dim' : ''} onClick={() => navigate(`/live?durchgang=${b.id}`)}>
                    <td>
                      <strong>{b.code}</strong>
                    </td>
                    <td className="num">{dateTime(b.created)}</td>
                    <td>
                      <RunState status={b.status === 'running' && !b.alive ? 'error' : b.status} batch />
                      {b.status === 'running' && !b.alive && <span className="muted small"> · {tx.stale}</span>}
                    </td>
                    <td>
                      {b.bw_system || '–'} <span className="muted">· {b.mcp_server || '–'}</span>
                    </td>
                    <td className="secondary">{tx.scope(b.run_count, b.model_count, b.task_count)}</td>
                    <td className="right num">{b.verified ? `${b.passed} / ${b.verified}` : '–'}</td>
                    <td className="right num">{b.cost > 0 || !b.unpriced ? usd(b.cost, 2) : t.common.noPrice}</td>
                    <td className="secondary">
                      {b.hidden && <Tag title={b.hidden}>{tx.hidden}</Tag>} {b.other_agent && <Tag>{tx.otherAgent(b.agent)}</Tag>}{' '}
                      {b.status_message || b.note}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>
      )}
      <ErrorNote error={batches.error} />
    </Page>
  )
}

/** Rangliste einer Aufgabe als Tabellenstand: Rang mit Zonenquadrat, Bilanz, Quote, Kosten je Erfolg, Laufzeit. */
function Leaderboard({ board }: { board: Board }) {
  const top = board.entries.slice(0, 8)
  const zone = (entry: Entry) => (entry.pass_rate === 1 ? 'zone zone--top' : entry.pass_rate !== null && entry.pass_rate < 0.5 ? 'zone zone--low' : 'zone')
  return (
    <div className="panel panel--flush">
      <div className="row row--between board-head">
        <strong>{board.task}</strong>
        <span className="secondary small">
          {t.common.units.runs[1]}: {board.runs}
        </span>
      </div>
      <table className="table">
        <thead>
          <tr>
            <th title={tx.board.rankTitle}>{tx.board.rank}</th>
            <th>{tx.board.model}</th>
            <th>{tx.board.vendor}</th>
            <th className="right" title={tx.board.runsTitle}>
              {tx.board.runs}
            </th>
            <th className="right" title={tx.board.passedTitle}>
              {tx.board.passed}
            </th>
            <th className="right">{tx.board.rate}</th>
            <th className="right" title={tx.board.costTitle}>
              {tx.board.cost}
            </th>
            <th className="right" title={tx.board.secondsTitle}>
              {tx.board.seconds}
            </th>
            <th>{tx.board.form}</th>
          </tr>
        </thead>
        <tbody>
          {top.map((entry) => (
            <tr key={entry.label} title={tx.boardPass(entry.passed, entry.verified)}>
              <td className="num">
                <i className={zone(entry)} />
                <strong>{entry.rank}</strong>
              </td>
              <td className="nowrap">
                <strong>{entry.label}</strong>
              </td>
              <td className="nowrap">{entry.vendor}</td>
              <td className="right num">{num(entry.runs)}</td>
              <td className="right num">{num(entry.passed)}</td>
              <td className="right num">
                <strong>{percent(entry.pass_rate)}</strong>
              </td>
              <td className="right num">{entry.cost_per_pass !== null ? usd(entry.cost_per_pass) : t.common.none}</td>
              <td className="right num">{duration(entry.seconds_finished)}</td>
              <td>
                <FormCurve runs={(entry.form ?? []).map((run) => ({ id: run.id, run_code: run.run_code, kind: run.verdict }))} max={8} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {board.entries.length > top.length && (
        <p className="small board-more">
          <Link to="/auswertung">{tx.boardMore(board.entries.length - top.length)}</Link>
        </p>
      )}
    </div>
  )
}
