// Live: laufender bzw. gewählter Durchgang mit Fortschritt, aktuellem Lauf und Aktionen.
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { api, errorText } from '../api'
import { dateTime, duration, num, percent, secondsSince, usd } from '../format'
import '../styles/live.css'
import { t } from '../texts'
import { Button, Dialog, Empty, ErrorNote, Field, Figure, Glyph, Loading, Meter, Notice, Page, RunState, Section, Tag, Verdict, useNow, useSort, useToast } from '../ui'
import { useStatus } from '../ui/Shell'

const tx = t.live

type Batch = {
  id: number
  code: string
  status: string
  status_message: string | null
  created: string | null
  started: string | null
  finished: string | null
  bw_system: string | null
  mcp_server: string | null
  repeats: number | null
  thinking: string | null
  verifier: string | null
  fallback_verifier: string | null
  cost_limit: number | null
  note: string | null
  hidden: string | null
  agent: string
  other_agent: boolean
  verifier_name: string | null
  fallback_name: string | null
  cancel_requested: number
  alive: boolean
  stale: boolean
  cost: number | null
}
type Run = {
  id: number
  run_code: string
  task_id: string
  task_version: number
  task_title: string | null
  model_id: string
  model_name: string
  vendor: string
  thinking: string | null
  status: string
  phase: string | null
  action: string | null
  started: string | null
  finished: string | null
  seconds: number | null
  steps: number | null
  tool_calls: number | null
  tool_errors: number | null
  last_requirement: string | null
  cost: number | null
  cost_source: string | null
  invalid: string | null
  retry_of: number | null
  /** Kennung des Laufs, der diesen ersetzt hat. */
  retried_as: string | null
  /** Kennung des Laufs, den dieser wiederholt. */
  retry_of_code: string | null
  error: string | null
  verify_status: string | null
  verify_cost: number | null
  verify_reason: string | null
}
type Requirement = { name: string; reached: boolean; calls: number; errors: number }
type ToolEvent = {
  phase: string
  seconds: number | null
  step: number | null
  kind: string
  tool: string | null
  requirement: string | null
  is_error: number
  text: string | null
  duration: number | null
}
type Current = {
  id: number
  requirements: Requirement[]
  timeout_s: number | null
  task_title: string
  recent: ToolEvent[]
  verify_steps: number
  /** Zeitpunkt des ersten Prüfereignisses; null, solange die Prüfung noch nichts gemeldet hat. */
  verify_started: string | null
  verify_timeout_s: number | null
}
type Progress = { total: number; done: number; passed: number; failed: number; invalid: number }
type LiveState = { batch: Batch | null; runs?: Run[]; current?: Current | null; progress?: Progress; now?: string }
type Snap = { state: LiveState; at: number }
type BatchRow = { id: number; code: string; created: string; status: string; alive: boolean }

const CAN_STREAM = typeof EventSource !== 'undefined'
const MAX_RUNS = 99
/** Abgeschlossene Läufe; nur sie lassen sich wiederholen. */
const FINAL = new Set(['finished', 'error', 'timeout', 'step_limit', 'cancelled', 'skipped', 'mcp_missing', 'no_result'])
/** Läufe mit diesen Status haben gearbeitet: Fehlt der Preis, heißt das „kein Preis“, nicht „noch nichts“. */
const WORKED = new Set(['finished', 'error', 'timeout', 'step_limit'])
/** Urteile, bei denen sich eine neue Prüfung lohnt. */
const UNSETTLED = new Set(['error', 'unclear', 'invalid', 'not_verified'])
/** Ein eben geplanter Durchgang braucht einen Moment, bis sein Prozess läuft; erst danach gilt er als liegengeblieben. */
const START_GRACE_MS = 4000

// --------------------------------------------------------------------------- Daten

/** Zustand des Durchgangs als Ereignisstrom; fällt die Verbindung aus, wird alle 2 s abgefragt.
    Der Strom schreibt in den Abfragespeicher: So steht der letzte Stand beim Zurückkehren sofort da. */
function useLive(batch: number | null) {
  const key = batch === null ? '' : `?batch=${batch}`
  const queryClient = useQueryClient()
  const [fallen, setFallen] = useState<string | null>(null)
  const polling = !CAN_STREAM || fallen === key
  const query = useQuery<Snap>({
    queryKey: ['live', key],
    queryFn: async () => ({ state: await api.get<LiveState>(`/live${key}`), at: Date.now() }),
    enabled: polling,
    refetchInterval: polling ? 2000 : false,
    retry: false,
    staleTime: Infinity,
  })

  useEffect(() => {
    if (!CAN_STREAM) return
    const source = new EventSource(`/api/live/stream${key}`)
    source.onmessage = (event) => {
      try {
        queryClient.setQueryData<Snap>(['live', key], { state: JSON.parse(event.data), at: Date.now() })
      } catch {
        /* unlesbare Nachricht: die nächste folgt in einer Sekunde */
      }
    }
    source.onerror = () => {
      source.close()
      setFallen(key)
    }
    return () => source.close()
  }, [key, queryClient])

  return { snap: query.data ?? null, failure: polling && query.error ? errorText(query.error) : '' }
}

// --------------------------------------------------------------------------- Seite

export default function Live() {
  const [params, setParams] = useSearchParams()
  const raw = params.get('durchgang')
  const chosen = raw && /^\d+$/.test(raw) ? Number(raw) : null
  const { snap, failure } = useLive(chosen)
  const batches = useQuery<BatchRow[]>({ queryKey: ['batches'], queryFn: () => api.get('/batches'), refetchInterval: 5000 })
  const list = batches.data ?? []
  const batch = snap?.state.batch ?? null
  const shownId = batch?.id ?? chosen
  const choose = (value: string) => setParams(value ? { durchgang: value } : {})

  const picker = list.length > 0 && (
    <label className="row">
      <span className="secondary small">{tx.pick.label}</span>
      <select className="select live-pick" value={shownId === null ? '' : String(shownId)} onChange={(e) => choose(e.target.value)}>
        {shownId === null && <option value="">{tx.pick.none}</option>}
        {shownId !== null && !list.some((b) => b.id === shownId) && <option value={shownId}>{batch?.code ?? shownId}</option>}
        {list.map((b) => (
          <option key={b.id} value={b.id}>
            {tx.pick.option(b.code, dateTime(b.created), b.status === 'running' && !b.alive ? tx.head.stale : (t.common.batchStatus[b.status] ?? b.status))}
          </option>
        ))}
      </select>
    </label>
  )

  return (
    <Page title={tx.title} lead={tx.lead} actions={picker || undefined}>
      {failure && (
        <Section>
          <Notice kind="error">{snap ? tx.connection.lost(failure, new Date(snap.at).toLocaleTimeString('de-DE')) : tx.connection.lostEmpty(failure)}</Notice>
        </Section>
      )}
      {!snap && !failure && <Loading lines={5} />}
      {snap && !batch && chosen === null && (
        <Empty title={tx.empty.title} action={<Link className="btn btn--primary" to="/start">{tx.empty.action}</Link>}>
          {tx.empty.text}
        </Empty>
      )}
      {snap && !batch && chosen !== null && (
        <Empty title={tx.notFound.title} action={<Button onClick={() => choose('')}>{tx.notFound.action}</Button>}>
          {tx.notFound.text}
        </Empty>
      )}
      {snap && batch && <BatchView key={batch.id} batch={batch} snap={snap} />}
    </Page>
  )
}

type DialogKind = 'cancel' | 'hide' | 'retry' | 'reverify' | 'output'

function BatchView({ batch, snap }: { batch: Batch; snap: Snap }) {
  const { state } = snap
  const runs = useMemo(() => state.runs ?? [], [state.runs])
  const progress = state.progress ?? { total: runs.length, done: 0, passed: 0, failed: 0, invalid: 0 }
  const status = useStatus()
  const queryClient = useQueryClient()
  const toast = useToast()
  const [dialog, setDialog] = useState<DialogKind | null>(null)
  // Fest, damit ein offener Dialog bei den sekündlichen Aktualisierungen den Fokus behält.
  const close = useCallback(() => setDialog(null), [])

  // Uhr des Servers: Die Laufzeit läuft im Sekundentakt mit, auch zwischen zwei Nachrichten.
  const now = useNow(batch.alive || batch.status === 'planned')
  // Seit wann der Durchgang in diesem Status gesehen wird (Ableitung beim Rendern, kein Effekt).
  const [seen, setSeen] = useState(() => ({ status: batch.status, at: Date.now() }))
  if (seen.status !== batch.status) setSeen({ status: batch.status, at: Date.now() })
  const serverNow = state.now ? Date.parse(state.now) : NaN
  const clock = Math.max(now, snap.at) + (Number.isNaN(serverNow) ? 0 : serverNow - snap.at)

  const refresh = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ['batches'] })
    queryClient.invalidateQueries({ queryKey: ['status'] })
  }, [queryClient])
  const failed = (error: unknown) => toast(errorText(error), true)

  const markStale = useMutation({
    mutationFn: () => api.post<{ runs: number }>(`/batches/${batch.id}/stale`),
    onSuccess: (result) => {
      refresh()
      toast(tx.toast.stale(result.runs))
    },
    onError: failed,
  })
  const unhide = useMutation({
    mutationFn: () => api.post(`/batches/${batch.id}/hidden`, { reason: '' }),
    onSuccess: () => {
      refresh()
      toast(tx.toast.unhidden)
    },
    onError: failed,
  })

  const runPlanned = useMutation({
    mutationFn: () => api.post(`/batches/${batch.id}/start`),
    onSuccess: () => {
      refresh()
      toast(tx.toast.started)
    },
  })

  const own = !batch.other_agent
  const running = batch.status === 'running' && batch.alive
  const busyElsewhere = status.data?.running?.alive && status.data.running.id !== batch.id ? status.data.running : null
  const settled = batch.status !== 'running' && batch.status !== 'planned'
  const canRepeat = own && settled && !busyElsewhere
  // Geplant, aber ohne Prozess: z. B. nach einem Neustart des Rechners vor dem ersten Lauf.
  const idlePlanned = own && batch.status === 'planned' && !batch.alive && now - seen.at >= START_GRACE_MS

  // Kandidaten und Vorschläge für die beiden Wiederholen-Dialoge.
  const retryRuns = runs.filter((r) => FINAL.has(r.status) && !r.retried_as)
  const retrySuggested = retryRuns.filter((r) => r.invalid || r.status === 'skipped').map((r) => r.id)
  const verifyRuns = runs.filter((r) => FINAL.has(r.status) && r.status !== 'skipped' && !r.retried_as)
  const verifySuggested = verifyRuns.filter((r) => !r.invalid && UNSETTLED.has(r.verify_status || 'not_verified')).map((r) => r.id)
  const freeNumbers = MAX_RUNS - runs.reduce((max, r) => Math.max(max, Number(r.run_code.slice(-2)) || 0), 0)

  const currentRun = state.current ? runs.find((r) => r.id === state.current?.id) : undefined
  const limit = batch.cost_limit ?? 0
  const cost = batch.cost ?? 0
  const share = limit > 0 ? cost / limit : 0

  return (
    <>
      <Section>
        <div className="panel stack">
          <div className="row row--between">
            <div className="row">
              <span className="live-code">{batch.code}</span>
              <RunState status={batch.stale ? 'error' : batch.status} batch />
              {batch.stale && <span className="muted small">· {tx.head.stale}</span>}
              {batch.hidden && <Tag title={batch.hidden}>{tx.head.hidden}</Tag>}
              {!own && <Tag>{tx.head.otherAgent(batch.agent)}</Tag>}
            </div>
            <div className="row">
              {running && (
                <Button variant="danger" disabled={Boolean(batch.cancel_requested)} onClick={() => setDialog('cancel')}>
                  {batch.cancel_requested ? tx.action.cancelRequested : tx.action.cancel}
                </Button>
              )}
              {idlePlanned && (
                <Button variant="primary" disabled={Boolean(busyElsewhere)} busy={runPlanned.isPending} onClick={() => runPlanned.mutate()}>
                  {tx.action.runPlanned}
                </Button>
              )}
              {canRepeat && <Button onClick={() => setDialog('retry')}>{tx.action.retry}</Button>}
              {canRepeat && <Button onClick={() => setDialog('reverify')}>{tx.action.reverify}</Button>}
              {batch.hidden ? (
                <Button busy={unhide.isPending} onClick={() => unhide.mutate()}>
                  {tx.action.unhide}
                </Button>
              ) : (
                <Button onClick={() => setDialog('hide')}>{tx.action.hide}</Button>
              )}
              <Button onClick={() => setDialog('output')}>{tx.action.output}</Button>
            </div>
          </div>
          <dl className="kv live-facts">
            <dt>{tx.head.system}</dt>
            <dd>{batch.bw_system || t.common.none}</dd>
            <dt>{tx.head.server}</dt>
            <dd>{batch.mcp_server || t.common.none}</dd>
            <dt>{tx.head.verifier}</dt>
            <dd title={batch.verifier ?? undefined}>{batch.verifier_name || batch.verifier || tx.head.noModel}</dd>
            <dt>{tx.head.fallback}</dt>
            <dd title={batch.fallback_verifier ?? undefined}>{batch.fallback_name || batch.fallback_verifier || tx.head.noModel}</dd>
            <dt>{tx.head.thinking}</dt>
            <dd>{batch.thinking || t.common.thinking['']}</dd>
            <dt>{tx.head.repeats}</dt>
            <dd className="num">{num(batch.repeats)}</dd>
            <dt>{batch.started ? tx.head.started : tx.head.created}</dt>
            <dd className="num">{dateTime(batch.started ?? batch.created)}</dd>
            {batch.finished && (
              <>
                <dt>{tx.head.finished}</dt>
                <dd className="num">{dateTime(batch.finished)}</dd>
              </>
            )}
            {batch.note && (
              <>
                <dt>{tx.head.note}</dt>
                <dd className="live-facts__wide">{batch.note}</dd>
              </>
            )}
          </dl>
          {batch.status_message && <Notice kind={batch.status === 'error' ? 'error' : batch.status === 'cancelled' ? 'warn' : 'info'}>{batch.status_message}</Notice>}
          {running && Boolean(batch.cancel_requested) && <Notice kind="warn">{tx.notice.cancelRequested}</Notice>}
          {batch.stale && (
            <Notice kind="warn">
              <div className="stack">
                <span>{tx.notice.stale}</span>
                <div>
                  <Button small busy={markStale.isPending} onClick={() => markStale.mutate()}>
                    {tx.action.stale}
                  </Button>
                </div>
              </div>
            </Notice>
          )}
          {idlePlanned && <Notice kind="warn">{busyElsewhere ? tx.notice.plannedBusy(busyElsewhere.code) : tx.notice.planned}</Notice>}
          <ErrorNote error={runPlanned.error} />
          {batch.hidden && <Notice>{tx.notice.hidden(batch.hidden)}</Notice>}
          {!own && <Notice>{tx.notice.otherAgent(batch.agent)}</Notice>}
          {own && settled && busyElsewhere && <Notice>{tx.notice.otherRunning(busyElsewhere.code)}</Notice>}
          {own && running && <p className="muted small">{tx.notice.selfRunning}</p>}
        </div>
      </Section>

      <Section title={tx.progress.title}>
        <div className="panel live-progress">
          <div className="stack">
            <div className="figures">
              <Figure value={`${num(progress.done)} / ${num(progress.total)}`} label={tx.progress.done} />
              <Figure value={num(progress.passed)} label={<Mark tone="pass" glyph="pass" text={tx.progress.passed} />} />
              <Figure value={num(progress.failed)} label={<Mark tone="fail" glyph="fail" text={tx.progress.failed} />} />
              <Figure value={num(progress.invalid)} label={<Mark tone="warn" glyph="invalid" text={tx.progress.invalid} />} />
            </div>
            <Meter value={progress.done} max={progress.total} />
          </div>
          <div className="stack">
            <Figure value={usd(cost, cost < 1 ? 3 : 2)} label={tx.progress.cost} />
            {limit > 0 ? (
              <>
                <Meter value={cost} max={limit} warn={share >= 0.8} />
                <span className="secondary small num">{tx.progress.ofLimit(usd(limit, 2), percent(share))}</span>
                {share >= 0.8 && <Mark tone="warn" glyph="warn" text={share >= 1 ? tx.progress.reached : tx.progress.nearLimit} wrap />}
              </>
            ) : (
              <span className="secondary small">{tx.progress.noLimit}</span>
            )}
          </div>
        </div>
      </Section>

      {state.current && currentRun && (
        <CurrentRun run={currentRun} current={state.current} clock={clock} live={batch.alive} />
      )}

      <RunTable runs={runs} clock={clock} live={batch.alive} />

      {dialog === 'cancel' && <CancelDialog batch={batch} onClose={close} onDone={refresh} />}
      {dialog === 'hide' && <HideDialog batch={batch} onClose={close} onDone={refresh} />}
      {dialog === 'output' && <OutputDialog batch={batch} onClose={close} />}
      {dialog === 'retry' && (
        <RunPickerDialog
          title={tx.retry.title(batch.code)}
          text={tx.retry.text}
          warning={tx.retry.warning}
          emptyText={tx.retry.empty}
          runs={retryRuns}
          suggested={retrySuggested}
          max={freeNumbers}
          maxNote={tx.retry.free(freeNumbers)}
          maxError={tx.retry.tooMany(freeNumbers)}
          confirm={tx.retry.confirm}
          submit={(ids) => api.post<{ runs: string[] }>(`/batches/${batch.id}/retry`, { runs: ids })}
          onDone={(result) => {
            refresh()
            toast(tx.toast.retry(result.runs ?? []))
          }}
          onClose={close}
        />
      )}
      {dialog === 'reverify' && (
        <RunPickerDialog
          title={tx.reverify.title(batch.code)}
          text={tx.reverify.text}
          warning={tx.reverify.warning}
          emptyText={tx.reverify.empty}
          runs={verifyRuns}
          suggested={verifySuggested}
          confirm={tx.reverify.confirm}
          submit={(ids) => api.post(`/batches/${batch.id}/reverify`, { runs: ids })}
          onDone={(_result, ids) => {
            refresh()
            toast(tx.toast.reverify(ids.length))
          }}
          onClose={close}
        />
      )}
    </>
  )
}

/** Zustand mit Zeichen und Text. */
function Mark(props: { tone: 'pass' | 'fail' | 'warn' | 'neutral' | 'live'; glyph: 'pass' | 'fail' | 'open' | 'invalid' | 'warn' | 'dot'; text: ReactNode; wrap?: boolean }) {
  return (
    <span className={`state state--${props.tone}`} style={props.wrap ? { whiteSpace: 'normal', alignItems: 'flex-start' } : undefined}>
      <Glyph kind={props.glyph} />
      <span>{props.text}</span>
    </span>
  )
}

// --------------------------------------------------------------------------- Aktueller Lauf

function CurrentRun(props: { run: Run; current: Current; clock: number; live: boolean }) {
  const { run, current, clock, live } = props
  const verifying = run.phase === 'verify'

  // Laufzeit: in der Aufgabe seit dem Start des Laufs, in der Prüfung seit ihrem ersten Ereignis.
  const elapsed = verifying ? (live ? secondsSince(current.verify_started, clock) : null) : live ? secondsSince(run.started, clock) : run.seconds
  const limit = verifying ? current.verify_timeout_s : current.timeout_s
  const step = verifying ? current.verify_steps : (run.steps ?? 0)
  const action = run.action || tx.now.waiting
  const latest = verifying ? [] : (run.last_requirement ?? '').split(' | ')
  const reached = current.requirements.filter((r) => r.reached).length
  const recent = [...current.recent].reverse()

  return (
    <Section title={tx.now.title}>
      <div className="grid grid--side">
        <div className="panel stack">
          <div className="row row--between">
            <div>
              <div className="row">
                <Link to={`/lauf/${run.id}`} title={tx.now.open}>
                  <strong>{run.run_code}</strong>
                </Link>
                <strong title={run.model_id}>{run.model_name}</strong>
                <span className="muted">{run.vendor}</span>
                {run.thinking && <Tag>{t.common.thinking[run.thinking] ?? run.thinking}</Tag>}
              </div>
              <div className="secondary small">{tx.now.task(current.task_title, run.task_id, run.task_version)}</div>
            </div>
            <Mark tone={live ? 'live' : 'neutral'} glyph={live ? 'dot' : 'open'} text={t.common.phase[run.phase ?? ''] ?? run.phase ?? t.common.none} />
          </div>

          <div className="live-step" aria-live="off">
            <span className="live-step__num">{step > 0 ? tx.now.step(step) : tx.now.noStep}</span>
            <span className="live-step__action" key={`${step}-${action}`}>
              {action}
            </span>
            {live && <div className="live-step__scan" aria-hidden />}
          </div>

          <div>
            <div className="live-time">
              <span>
                <span className="secondary">{verifying ? tx.now.timeVerify : tx.now.time}</span>{' '}
                <strong className="num">{duration(elapsed)}</strong>
              </span>
              {limit ? <span className="secondary small num">{tx.now.ofLimit(duration(limit))}</span> : null}
            </div>
            {limit && elapsed !== null ? <Meter value={elapsed} max={limit} warn={elapsed / limit >= 0.8} /> : null}
          </div>

          <dl className="kv">
            {verifying && (
              <>
                <dt>{t.common.phase.task}</dt>
                <dd className="num">
                  {tx.now.taskTook(duration(run.seconds))} · {t.common.runStatus[run.status] ?? run.status}
                </dd>
              </>
            )}
            <dt>{tx.now.toolCalls}</dt>
            <dd className="num">{num(run.tool_calls ?? 0)}</dd>
            <dt>{tx.now.toolErrors}</dt>
            <dd className="num">{num(run.tool_errors ?? 0)}</dd>
            <dt>{tx.now.requirement}</dt>
            <dd>{run.last_requirement || t.common.none}</dd>
          </dl>
        </div>

        <div className="panel panel--flush" style={{ marginTop: 0 }}>
          <div className="row row--between" style={{ padding: 'var(--sp-4) var(--sp-4) var(--sp-2)' }}>
            <strong>{tx.now.reqTitle}</strong>
            <span className="muted small">{tx.now.reqNote(reached, current.requirements.length)}</span>
          </div>
          {current.requirements.length === 0 ? (
            <p className="muted small" style={{ padding: '0 var(--sp-4) var(--sp-4)' }}>
              {tx.now.reqEmpty}
            </p>
          ) : (
            <table className="table">
              <thead>
                <tr>
                  <th>{tx.now.reqCol.name}</th>
                  <th>{tx.now.reqCol.state}</th>
                  <th className="right">{tx.now.reqCol.calls}</th>
                  <th className="right">{tx.now.reqCol.errors}</th>
                </tr>
              </thead>
              <tbody>
                {current.requirements.map((req) => (
                  <tr key={req.name}>
                    <td>
                      {req.name}
                      {latest.includes(req.name) && <div className="muted">{tx.now.latest}</div>}
                    </td>
                    <td>{req.reached ? <Mark tone="pass" glyph="pass" text={tx.now.reached} /> : <Mark tone="neutral" glyph="open" text={tx.now.notReached} />}</td>
                    <td className="right num">{num(req.calls)}</td>
                    <td className="right num">{req.errors > 0 ? <span className="state state--warn">{num(req.errors)}</span> : num(0)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      <div className="panel panel--flush" style={{ marginTop: 'var(--sp-4)' }}>
        <div style={{ padding: 'var(--sp-4) var(--sp-4) var(--sp-2)' }}>
          <strong>{tx.now.recentTitle}</strong>
        </div>
        {recent.length === 0 ? (
          <p className="muted small" style={{ padding: '0 var(--sp-4) var(--sp-4)' }}>
            {tx.now.recentEmpty}
          </p>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th className="right">{tx.now.recentCol.at}</th>
                  <th>{tx.now.recentCol.phase}</th>
                  <th className="right">{tx.now.recentCol.step}</th>
                  <th>{tx.now.recentCol.tool}</th>
                  <th>{tx.now.recentCol.requirement}</th>
                  <th className="right">{tx.now.recentCol.took}</th>
                  <th>{tx.now.recentCol.result}</th>
                </tr>
              </thead>
              <tbody>
                {recent.map((event, index) => {
                  const isError = Boolean(event.is_error) || event.kind === 'error'
                  return (
                    <tr key={`${recent.length - index}-${event.phase}-${event.seconds}`}>
                      <td className="right num">{duration(event.seconds)}</td>
                      <td>{t.common.phase[event.phase] ?? event.phase}</td>
                      <td className="right num">{num(event.step)}</td>
                      <td className="mono">{event.tool || t.common.none}</td>
                      <td className="secondary">{event.requirement || t.common.none}</td>
                      <td className="right num">{event.duration === null ? t.common.none : tx.now.seconds(num(event.duration, 1))}</td>
                      <td>
                        <div className="row" style={{ flexWrap: 'nowrap' }}>
                          {isError ? <Mark tone="fail" glyph="fail" text={tx.now.error} /> : <Mark tone="pass" glyph="pass" text={tx.now.ok} />}
                          {event.text && (
                            <span className="secondary live-remark" title={event.text}>
                              {event.text}
                            </span>
                          )}
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </Section>
  )
}

// --------------------------------------------------------------------------- Tabelle der Läufe

function RunTable({ runs, clock, live }: { runs: Run[]; clock: number; live: boolean }) {
  const navigate = useNavigate()
  const rows = runs.map((run, order) => ({
    ...run,
    order,
    time: run.status === 'running' ? (live ? secondsSince(run.started, clock) : null) : run.seconds,
    verdict: run.verify_status ?? '',
  }))
  const sort = useSort(rows, { key: 'order', dir: 'asc' })
  const head = (key: string, label: string, right?: boolean) => (
    <th className={right ? 'right' : undefined}>
      <button type="button" onClick={() => sort.toggle(key)}>
        {label}
        {sort.mark(key)}
      </button>
    </th>
  )
  if (runs.length === 0) return null
  return (
    <Section title={tx.runs.title} note={tx.runs.note(runs.length)}>
      <div className="table-wrap">
        <table className="table table--click">
          <thead>
            <tr>
              {head('order', tx.runs.col.code)}
              {head('model_name', tx.runs.col.model)}
              {head('thinking', tx.runs.col.thinking)}
              {head('task_id', tx.runs.col.task)}
              {head('status', tx.runs.col.status)}
              {head('verdict', tx.runs.col.verdict)}
              {head('time', tx.runs.col.time, true)}
              {head('steps', tx.runs.col.steps, true)}
              {head('cost', tx.runs.col.cost, true)}
              <th>{tx.runs.col.remark}</th>
            </tr>
          </thead>
          <tbody>
            {sort.sorted.map((run) => {
              const verifying = run.phase === 'verify' && live
              const judged = run.verify_status || (FINAL.has(run.status) && run.status !== 'skipped' && !verifying)
              return (
                <tr
                  key={run.id}
                  className={run.invalid || run.status === 'skipped' || run.status === 'planned' ? 'is-dim' : ''}
                  onClick={() => navigate(`/lauf/${run.id}`)}
                >
                  <td>
                    <Link to={`/lauf/${run.id}`} onClick={(e) => e.stopPropagation()} style={{ textDecoration: 'none' }}>
                      <strong>{run.run_code}</strong>
                    </Link>
                  </td>
                  <td title={run.model_id}>
                    {run.model_name} <span className="muted">· {run.vendor}</span>
                  </td>
                  <td>{t.common.thinking[run.thinking ?? ''] ?? run.thinking}</td>
                  <td>
                    <div className="row" style={{ flexWrap: 'nowrap', gap: 6 }} title={tx.now.task(run.task_title ?? '', run.task_id, run.task_version)}>
                      <span className="live-task">{run.task_title || run.task_id}</span>
                      <span className="muted">{tx.runs.version(run.task_version)}</span>
                    </div>
                  </td>
                  <td>
                    <RunState status={run.status} />
                    {verifying && <span className="state state--live small"> · {tx.runs.verifying}</span>}
                  </td>
                  <td title={run.verify_reason ?? undefined}>{judged ? <Verdict status={run.verify_status} /> : t.common.none}</td>
                  <td className="right num">{duration(run.time)}</td>
                  <td className="right num">{run.status === 'planned' || run.status === 'skipped' ? t.common.none : num(run.steps)}</td>
                  <td
                    className="right num"
                    title={tx.runs.costTitle(t.common.costSource[run.cost_source ?? ''] ?? '', run.verify_cost !== null ? usd(run.verify_cost) : null) || undefined}
                  >
                    {run.cost !== null ? usd(run.cost) : WORKED.has(run.status) ? t.common.noPrice : t.common.none}
                  </td>
                  <td>
                    <div className="row" style={{ flexWrap: 'nowrap' }}>
                      <Marks run={run} />
                      <Remark run={run} />
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </Section>
  )
}

/** Vermerke eines Laufs: wiederholt, ungültig, Wiederholung eines anderen. */
function Marks({ run }: { run: Run }) {
  return (
    <>
      {run.retried_as ? <Tag title={run.invalid ?? undefined}>{tx.runs.retriedAs(run.retried_as)}</Tag> : run.invalid ? <Tag title={run.invalid}>{tx.runs.invalid}</Tag> : null}
      {run.retry_of_code && <Tag>{tx.runs.retryOf(run.retry_of_code)}</Tag>}
    </>
  )
}

/** Grund, warum ein Lauf nicht zählt, sonst seine Fehlermeldung. */
function Remark({ run }: { run: Run }) {
  const text = run.invalid && !run.retried_as ? run.invalid : run.error
  if (!text) return null
  return (
    <span className="secondary live-remark" title={run.error && run.error !== text ? `${text} – ${run.error}` : text}>
      {text}
    </span>
  )
}

// --------------------------------------------------------------------------- Dialoge

function CancelDialog({ batch, onClose, onDone }: { batch: Batch; onClose: () => void; onDone: () => void }) {
  const toast = useToast()
  const cancel = useMutation({
    mutationFn: () => api.post(`/batches/${batch.id}/cancel`),
    onSuccess: () => {
      onDone()
      toast(tx.toast.cancel)
      onClose()
    },
  })
  return (
    <Dialog
      title={tx.cancel.title(batch.code)}
      onClose={onClose}
      footer={
        <>
          <Button onClick={onClose}>{tx.cancel.keep}</Button>
          <Button variant="danger" busy={cancel.isPending} onClick={() => cancel.mutate()}>
            {tx.cancel.confirm}
          </Button>
        </>
      }
    >
      <div className="stack">
        <p>{tx.cancel.text}</p>
        <ErrorNote error={cancel.error} />
      </div>
    </Dialog>
  )
}

function HideDialog({ batch, onClose, onDone }: { batch: Batch; onClose: () => void; onDone: () => void }) {
  const toast = useToast()
  const [reason, setReason] = useState('')
  const input = useRef<HTMLInputElement>(null)
  // Der Dialog nimmt beim Öffnen den Fokus; danach gehört er ins Eingabefeld.
  useEffect(() => input.current?.focus(), [])
  const hide = useMutation({
    mutationFn: () => api.post(`/batches/${batch.id}/hidden`, { reason: reason.trim() }),
    onSuccess: () => {
      onDone()
      toast(tx.toast.hidden)
      onClose()
    },
  })
  const ready = reason.trim() !== ''
  return (
    <Dialog
      title={tx.hide.title(batch.code)}
      onClose={onClose}
      footer={
        <>
          <Button onClick={onClose}>{t.common.actions.cancel}</Button>
          <Button variant="primary" disabled={!ready} busy={hide.isPending} onClick={() => hide.mutate()}>
            {tx.hide.confirm}
          </Button>
        </>
      }
    >
      <form
        className="stack"
        onSubmit={(e) => {
          e.preventDefault()
          if (ready && !hide.isPending) hide.mutate()
        }}
      >
        <p className="secondary">{tx.hide.text}</p>
        <Field label={tx.hide.reason}>
          <input className="input" value={reason} onChange={(e) => setReason(e.target.value)} placeholder={tx.hide.reasonPlaceholder} maxLength={200} ref={input} />
        </Field>
        <ErrorNote error={hide.error} />
      </form>
    </Dialog>
  )
}

function OutputDialog({ batch, onClose }: { batch: Batch; onClose: () => void }) {
  const output = useQuery({
    queryKey: ['batch-output', batch.id],
    queryFn: () => api.text('GET', `/batches/${batch.id}/output`),
    refetchInterval: batch.alive ? 3000 : false,
    staleTime: 0,
    gcTime: 0,
  })
  const pre = useRef<HTMLPreElement>(null)
  // Angezeigt wird das Ende der Datei: nach jeder Aktualisierung dorthin blättern.
  useEffect(() => {
    if (pre.current) pre.current.scrollTop = pre.current.scrollHeight
  }, [output.data])
  return (
    <Dialog
      wide
      title={tx.output.title(batch.code)}
      onClose={onClose}
      footer={
        <>
          <Button busy={output.isFetching} onClick={() => output.refetch()}>
            {tx.output.refresh}
          </Button>
          <Button variant="primary" onClick={onClose}>
            {t.common.actions.close}
          </Button>
        </>
      }
    >
      <div className="stack">
        <p className="secondary small">
          {tx.output.text} {batch.alive && tx.output.auto}
        </p>
        {output.isLoading && <Loading />}
        <ErrorNote error={output.error} />
        {output.data !== undefined && (output.data.trim() ? <pre className="live-output" ref={pre}>{output.data}</pre> : <Notice>{tx.output.empty}</Notice>)}
      </div>
    </Dialog>
  )
}

/** Läufe wählen und eine Aktion darauf auslösen: Läufe wiederholen oder nur die Prüfung. */
function RunPickerDialog<R>(props: {
  title: string
  text: string
  warning: string
  emptyText: string
  runs: Run[]
  suggested: number[]
  max?: number
  maxNote?: string
  maxError?: string
  confirm: (n: number) => string
  submit: (ids: number[]) => Promise<R>
  onDone: (result: R, ids: number[]) => void
  onClose: () => void
}) {
  const { runs, onClose, onDone } = props
  const [picked, setPicked] = useState<number[]>(props.suggested)
  // In der Reihenfolge der Läufe; was inzwischen nicht mehr wählbar ist, fällt heraus.
  const ids = runs.filter((r) => picked.includes(r.id)).map((r) => r.id)
  const tooMany = props.max !== undefined && ids.length > props.max
  const action = useMutation({
    mutationFn: () => props.submit(ids),
    onSuccess: (result) => {
      onDone(result, ids)
      onClose()
    },
  })
  const toggle = (id: number) => setPicked((list) => (list.includes(id) ? list.filter((x) => x !== id) : [...list, id]))

  return (
    <Dialog
      wide
      title={props.title}
      onClose={onClose}
      footer={
        <>
          <Button onClick={onClose}>{t.common.actions.cancel}</Button>
          <Button variant="primary" disabled={ids.length === 0 || tooMany} busy={action.isPending} onClick={() => action.mutate()}>
            {props.confirm(ids.length)}
          </Button>
        </>
      }
    >
      <div className="stack">
        <p className="secondary">{props.text}</p>
        {runs.length > 0 && <Notice kind="warn">{props.warning}</Notice>}
        {runs.length === 0 ? (
          <Notice>{props.emptyText}</Notice>
        ) : (
          <>
            <div className="row">
              <Button small disabled={props.suggested.length === 0} onClick={() => setPicked(props.suggested)}>
                {tx.picker.suggested}
              </Button>
              <Button small onClick={() => setPicked(runs.map((r) => r.id))}>
                {tx.picker.all}
              </Button>
              <Button small variant="quiet" disabled={ids.length === 0} onClick={() => setPicked([])}>
                {tx.picker.none}
              </Button>
              <span className="spacer" />
              <span className="muted small">
                {tx.picker.chosen(ids.length, runs.length)}
                {props.maxNote ? ` · ${props.maxNote}` : ''}
              </span>
            </div>
            <div className="table-wrap">
              <table className="table table--click live-table">
                <thead>
                  <tr>
                    <th className="live-pick-cell" />
                    <th>{tx.picker.col.run}</th>
                    <th>{tx.picker.col.model}</th>
                    <th>{tx.picker.col.task}</th>
                    <th>{tx.picker.col.status}</th>
                    <th>{tx.picker.col.verdict}</th>
                    <th>{tx.picker.col.remark}</th>
                  </tr>
                </thead>
                <tbody>
                  {runs.map((run) => {
                    const checked = ids.includes(run.id)
                    return (
                      <tr key={run.id} className={checked ? 'is-picked' : ''} onClick={() => toggle(run.id)}>
                        <td>
                          <span className="check">
                            <input type="checkbox" checked={checked} aria-label={tx.picker.pick(run.run_code)} onClick={(e) => e.stopPropagation()} onChange={() => toggle(run.id)} />
                          </span>
                        </td>
                        <td>
                          <strong>{run.run_code}</strong>
                        </td>
                        <td title={run.model_id}>
                          {run.model_name}
                          {run.thinking && <span className="muted"> · {t.common.thinking[run.thinking] ?? run.thinking}</span>}
                        </td>
                        <td>
                          <span className="live-task" title={run.task_id}>
                            {run.task_title || run.task_id}
                          </span>
                        </td>
                        <td>
                          <RunState status={run.status} />
                        </td>
                        <td>{run.status === 'skipped' && !run.verify_status ? t.common.none : <Verdict status={run.verify_status} />}</td>
                        <td>
                          <div className="row" style={{ flexWrap: 'nowrap' }}>
                            {props.suggested.includes(run.id) && <Tag>{tx.picker.suggestedTag}</Tag>}
                            {run.retry_of_code && <Tag>{tx.runs.retryOf(run.retry_of_code)}</Tag>}
                            <Remark run={run} />
                          </div>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </>
        )}
        {tooMany && props.maxError && <Notice kind="warn">{props.maxError}</Notice>}
        <ErrorNote error={action.error} />
      </div>
    </Dialog>
  )
}
