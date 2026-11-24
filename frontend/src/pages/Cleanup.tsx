// BW bereinigen: Objekte der Läufe im BW suchen, Liste prüfen, nach Bestätigung löschen.
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Fragment, useCallback, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { dateTime, num } from '../format'
import '../styles/cleanup.css'
import { t } from '../texts'
import { Button, BwState, Check, Chips, Dialog, Empty, ErrorNote, Field, Glyph, Loading, Meter, Notice, Page, RunState, Section, useToast } from '../ui'

const tx = t.cleanup

type Obj = {
  type: string
  name: string
  run?: string
  code?: string
  bw_status?: string
  title?: string
  via?: string
  source_system?: string
  result?: string // open | deleted | error
  message?: string
}
type Scope = { codes?: string[]; runs?: string[] }
type Job = {
  id: number
  created: string
  finished: string | null
  status: string // planned | running | done | error | cancelled
  bw_system: string
  mcp_server: string
  scope: Scope
  objects: Obj[]
  rest: Obj[]
  cancel_requested?: number
  message: string | null
}
type Batch = { id: number; code: string; bw_system: string | null; mcp_server: string | null; created: string; runs: number }
type Server = { name: string; is_default: boolean; tested: boolean; supported: boolean | null }
type System = {
  id: string
  is_default: boolean
  password_set: boolean
  prefix: string
  area_pattern: string
  status: { state: string; detail: string } | null
}
type State = { jobs: Job[]; batches: Batch[]; servers: Server[]; bw_systems: System[]; busy: boolean; blocked_codes: string[] }
type SearchRequest = { bw_system: string; mcp_server: string; codes: string[]; runs: string[] }
type Found = { request: SearchRequest; objects: Obj[] }

const RUN_PATTERN = /^([A-Z]\d{3}|[A-Z]{3}\d{2})$/
const EXAMPLE_RUN = 'AAA03'
const objectKey = (obj: Obj) => `${obj.type}:${obj.name}:${obj.source_system ?? ''}`
const parseRuns = (text: string) => [...new Set(text.toUpperCase().split(/[\s,;]+/).filter(Boolean))]
const sameRequest = (a: SearchRequest, b: SearchRequest) => JSON.stringify(a) === JSON.stringify(b)

/** Ein Auftrag läuft oder ist eben erst geplant. Ein geplanter, der nie anläuft, gilt nach zwei
    Minuten als hängengeblieben, damit er die Seite nicht dauerhaft sperrt. */
function isActive(job: Job): boolean {
  if (job.status === 'running') return true
  return job.status === 'planned' && Date.now() - new Date(job.created).getTime() < 120_000
}

function groupByRun(objects: Obj[]): [string, Obj[]][] {
  const groups = new Map<string, Obj[]>()
  for (const obj of objects) groups.set(obj.run ?? '', [...(groups.get(obj.run ?? '') ?? []), obj])
  return [...groups.entries()].sort(([a], [b]) => (a === '' ? 1 : b === '' ? -1 : a.localeCompare(b)))
}

function Step({ n, children }: { n: number; children: ReactNode }) {
  return (
    <>
      <span className="cleanup-step">{n}</span>
      {children}
    </>
  )
}

export default function Cleanup() {
  const queryClient = useQueryClient()
  const toast = useToast()
  const state = useQuery<State>({
    queryKey: ['cleanup'],
    queryFn: () => api.get('/cleanup'),
    refetchInterval: (query) => (query.state.data?.jobs.some(isActive) ? 2000 : 15000),
  })

  const [systemId, setSystemId] = useState<string | null>(null)
  const [serverName, setServerName] = useState<string | null>(null)
  const [allSystems, setAllSystems] = useState(false)
  const [codes, setCodes] = useState<string[]>([])
  const [runsText, setRunsText] = useState('')
  const [found, setFound] = useState<Found | null>(null)
  const [checked, setChecked] = useState<Set<string>>(new Set())
  const [confirming, setConfirming] = useState(false)
  const [shownId, setShownId] = useState<number | null>(null)
  const [openJobs, setOpenJobs] = useState<Set<number>>(new Set())

  const data = state.data
  const systems = data?.bw_systems ?? []
  const servers = data?.servers ?? []
  const jobs = data?.jobs ?? []
  const system = systems.find((s) => s.id === systemId) ?? systems.find((s) => s.is_default) ?? systems[0]
  const server = servers.find((s) => s.name === serverName) ?? servers.find((s) => s.is_default) ?? servers[0]
  const batchesOf = (id: string | undefined, all: boolean) => (data?.batches ?? []).filter((b) => all || b.bw_system === id)
  const batches = batchesOf(system?.id, allSystems)
  const extraCodes = (data?.blocked_codes ?? []).filter((code) => !(data?.batches ?? []).some((b) => b.code === code))
  const runCodes = parseRuns(runsText)
  const badRuns = runCodes.filter((run) => !RUN_PATTERN.test(run))

  // Ein laufender Auftrag gehört in Schritt 3, auch nach dem Neuladen der Seite.
  const activeJob = jobs.find(isActive)
  if (activeJob && activeJob.id !== shownId) setShownId(activeJob.id)
  const shownJob = jobs.find((job) => job.id === shownId)

  const request: SearchRequest = { bw_system: system?.id ?? '', mcp_server: server?.name ?? '', codes: [...codes].sort(), runs: runCodes }
  const current = found && sameRequest(found.request, request) ? found : null
  const selected = current ? current.objects.filter((obj) => checked.has(objectKey(obj))) : []
  const blocked = Boolean(data?.busy) || Boolean(activeJob) || server?.supported === false
  const hasScope = request.codes.length + request.runs.length > 0
  const canSearch = !blocked && Boolean(system && server) && hasScope && badRuns.length === 0

  const search = useMutation({
    mutationFn: (body: SearchRequest) => api.post<{ objects: Obj[] }>('/cleanup/search', body),
    onMutate: () => setShownId(null),
    onSuccess: (result, body) => {
      setFound({ request: body, objects: result.objects })
      setChecked(new Set(result.objects.map(objectKey)))
    },
  })
  const start = useMutation({
    mutationFn: (body: Found) =>
      api.post<{ id: number }>('/cleanup/jobs', {
        bw_system: body.request.bw_system,
        mcp_server: body.request.mcp_server,
        objects: body.objects,
        scope: { codes: body.request.codes, runs: body.request.runs },
      }),
    onSuccess: (result) => {
      setShownId(result.id)
      setConfirming(false)
      setFound(null)
      toast(tx.del.started)
      return queryClient.invalidateQueries({ queryKey: ['cleanup'] })
    },
  })
  const cancel = useMutation({
    mutationFn: (id: number) => api.post(`/cleanup/jobs/${id}/cancel`),
    onSuccess: () => {
      toast(tx.job.cancelSent)
      return queryClient.invalidateQueries({ queryKey: ['cleanup'] })
    },
    onError: (error) => toast(error.message, true),
  })
  const resetStart = start.reset
  const closeConfirm = useCallback(() => {
    setConfirming(false)
    resetStart()
  }, [resetStart])

  const toggle = (keys: string[], on: boolean) =>
    setChecked((old) => {
      const next = new Set(old)
      for (const key of keys) {
        if (on) next.add(key)
        else next.delete(key)
      }
      return next
    })
  const toggleCode = (code: string) => setCodes((old) => (old.includes(code) ? old.filter((c) => c !== code) : [...old, code]))
  const chooseSystem = (id: string) => {
    setSystemId(id)
    if (!allSystems) setCodes((old) => old.filter((code) => extraCodes.includes(code)))
  }
  const showAllSystems = (all: boolean) => {
    setAllSystems(all)
    if (!all) {
      const visible = new Set([...batchesOf(system?.id, false).map((b) => b.code), ...extraCodes])
      setCodes((old) => old.filter((code) => visible.has(code)))
    }
  }
  /** Übernimmt den Umfang eines Auftrags in Schritt 1 und sucht sofort neu. */
  const searchAgain = (job: Job) => {
    const jobCodes = [...(job.scope.codes ?? [])].sort()
    const jobRuns = job.scope.runs ?? []
    const visible = new Set([...batchesOf(job.bw_system, false).map((b) => b.code), ...extraCodes])
    setSystemId(job.bw_system)
    setServerName(job.mcp_server)
    setAllSystems(jobCodes.some((code) => !visible.has(code)))
    setCodes(jobCodes)
    setRunsText(jobRuns.join(', '))
    search.mutate({ bw_system: job.bw_system, mcp_server: job.mcp_server, codes: jobCodes, runs: parseRuns(jobRuns.join(',')) })
  }
  const canRepeat = (job: Job) =>
    !blocked && systems.some((s) => s.id === job.bw_system) && servers.some((s) => s.name === job.mcp_server && s.supported !== false)

  const earlier = jobs.filter((job) => job.id !== shownJob?.id)
  const searchNote = search.isPending
    ? tx.check.searching
    : activeJob
      ? tx.jobRunning
      : data?.busy
        ? tx.check.blockedBusy
        : server?.supported === false
          ? tx.check.blockedServer
          : badRuns.length > 0
            ? tx.check.fixRuns
            : !hasScope
              ? tx.check.needScope
              : tx.check.hint
  const scopeText = tx.scope(request.codes, request.runs)

  return (
    <Page title={tx.title} lead={tx.lead}>
      {state.isLoading && <Loading lines={5} />}
      <ErrorNote error={state.error} />

      {data && !system && (
        <Empty
          title={tx.noSystemTitle}
          action={
            <Link className="btn btn--primary" to="/einstellungen/bw">
              {tx.noSystemAction}
            </Link>
          }
        >
          {tx.noSystemText}
        </Empty>
      )}
      {data && system && !server && (
        <Empty
          title={tx.noServerTitle}
          action={
            <Link className="btn btn--primary" to="/einstellungen/mcp">
              {tx.noServerAction}
            </Link>
          }
        >
          {tx.noServerText}
        </Empty>
      )}

      {data && system && server && (
        <>
          {data.busy && (
            <Notice kind="warn">
              {tx.busy} <Link to="/live">{tx.busyAction}</Link>
            </Notice>
          )}

          <Section title={<Step n={1}>{tx.select.title}</Step>}>
            <div className="stack">
              <div className="panel">
                <div className="form-grid">
                  <Field label={tx.select.system} hint={<BwState status={system.status} />}>
                    <select className="select" value={system.id} onChange={(event) => chooseSystem(event.target.value)}>
                      {systems.map((s) => (
                        <option key={s.id} value={s.id}>
                          {s.id}
                          {s.is_default ? ` (${tx.select.isDefault})` : ''}
                        </option>
                      ))}
                    </select>
                  </Field>
                  <Field label={tx.select.server}>
                    <select className="select" value={server.name} onChange={(event) => setServerName(event.target.value)}>
                      {servers.map((s) => (
                        <option key={s.name} value={s.name}>
                          {s.name}
                          {s.is_default ? ` (${tx.select.isDefault})` : ''}
                          {s.supported === false ? ` – ${tx.select.serverUnsupportedShort}` : s.supported === null ? ` – ${tx.select.serverUntestedShort}` : ''}
                        </option>
                      ))}
                    </select>
                  </Field>
                </div>
                <p className="muted small cleanup-convention">
                  {tx.select.convention(system.area_pattern.replace('{RUN}', EXAMPLE_RUN), `${system.prefix}${EXAMPLE_RUN}`, EXAMPLE_RUN)}
                </p>
              </div>

              {system.status?.state !== 'ok' && (
                <Notice kind="warn">
                  {tx.select.systemNotReady(system.id, system.status?.detail ?? '')} <Link to="/einstellungen/bw">{tx.select.openSystems}</Link>
                </Notice>
              )}
              {!system.password_set && (
                <Notice kind="warn">
                  {tx.select.passwordMissing(system.id)} <Link to="/einstellungen/bw">{tx.select.openSystems}</Link>
                </Notice>
              )}
              {server.supported === false && (
                <Notice kind="error">
                  {tx.select.serverUnsupported(server.name)} <Link to="/einstellungen/mcp">{tx.select.openServers}</Link>
                </Notice>
              )}
              {server.supported === null && (
                <Notice>
                  {tx.select.serverUntested(server.name)} <Link to="/einstellungen/mcp">{tx.select.openServers}</Link>
                </Notice>
              )}

              <div>
                <div className="row row--between">
                  <div>
                    <h3 className="cleanup-sub">{tx.select.batches}</h3>
                    <p className="section__note">{allSystems ? tx.select.batchesNoteAll : tx.select.batchesNote(system.id)}</p>
                  </div>
                  {(allSystems || (data.batches ?? []).some((b) => b.bw_system !== system.id)) && (
                    <Check checked={allSystems} onChange={showAllSystems}>
                      {tx.select.allSystems}
                    </Check>
                  )}
                </div>
                {batches.length === 0 ? (
                  <p className="muted small cleanup-none">{tx.select.noBatches(system.id)}</p>
                ) : (
                  <div className="cleanup-batches">
                    <table className="table table--click">
                      <thead>
                        <tr>
                          <th className="cleanup-check" />
                          <th>{tx.select.col.code}</th>
                          <th>{tx.select.col.date}</th>
                          <th className="right">{tx.select.col.runs}</th>
                          {allSystems && <th>{tx.select.col.system}</th>}
                          <th>{tx.select.col.server}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {batches.map((batch) => (
                          <tr
                            key={batch.id}
                            onClick={(event) => {
                              if (!(event.target as Element).closest('label')) toggleCode(batch.code)
                            }}
                          >
                            <td className="cleanup-check">
                              <label className="check">
                                <input
                                  type="checkbox"
                                  checked={codes.includes(batch.code)}
                                  aria-label={tx.select.pick(batch.code)}
                                  onChange={() => toggleCode(batch.code)}
                                />
                              </label>
                            </td>
                            <td>
                              <strong>{batch.code}</strong>
                            </td>
                            <td className="num">{dateTime(batch.created)}</td>
                            <td className="right num">{num(batch.runs)}</td>
                            {allSystems && <td>{batch.bw_system || t.common.none}</td>}
                            <td className="secondary">{batch.mcp_server || t.common.none}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>

              <div className="form-grid">
                {extraCodes.length > 0 && (
                  <div className="field field--wide">
                    <span className="field__label">{tx.select.extraCodes}</span>
                    <Chips
                      options={extraCodes}
                      value={codes.filter((code) => extraCodes.includes(code))}
                      onChange={(value) => setCodes((old) => [...old.filter((code) => !extraCodes.includes(code)), ...value])}
                      ariaLabel={tx.select.extraCodes}
                    />
                    <span className="field__hint">{tx.select.extraCodesHint}</span>
                  </div>
                )}
                <Field label={tx.select.runs} hint={tx.select.runsHint} error={badRuns.length > 0 ? tx.select.runsInvalid(badRuns) : null} wide>
                  <input
                    className="input mono cleanup-runs"
                    value={runsText}
                    placeholder={tx.select.runsPlaceholder}
                    spellCheck={false}
                    autoCapitalize="characters"
                    onChange={(event) => setRunsText(event.target.value)}
                  />
                </Field>
              </div>
            </div>
          </Section>

          <Section title={<Step n={2}>{tx.check.title}</Step>}>
            <div className="stack">
              <div className="row">
                <Button variant="primary" busy={search.isPending} disabled={!canSearch} onClick={() => search.mutate(request)}>
                  {tx.check.search}
                </Button>
                <span className="muted small">
                  {searchNote}
                </span>
              </div>
              {search.isPending && <Loading lines={4} />}
              <ErrorNote error={search.error} />
              {found && !current && !search.isPending && <Notice>{tx.check.stale}</Notice>}
              {current && !search.isPending && current.objects.length === 0 && (
                <Empty title={tx.check.emptyTitle}>{tx.check.emptyText(current.request.bw_system, scopeText)}</Empty>
              )}
              {current && !search.isPending && current.objects.length > 0 && (
                <>
                  <div>
                    <p>{tx.check.found(current.objects.length, groupByRun(current.objects).length, current.request.bw_system)}</p>
                    <p className="muted small">{tx.check.order}</p>
                  </div>
                  <ObjectTable objects={current.objects} selection={{ checked, toggle }} />
                  <p className="secondary num">{tx.check.selected(selected.length, current.objects.length)}</p>
                </>
              )}
            </div>
          </Section>

          <Section title={<Step n={3}>{tx.del.title}</Step>}>
            {shownJob ? (
              <JobView
                job={shownJob}
                cancelling={cancel.isPending}
                onCancel={() => cancel.mutate(shownJob.id)}
                onSearchAgain={canRepeat(shownJob) ? () => searchAgain(shownJob) : undefined}
              />
            ) : shownId !== null ? (
              <Loading lines={3} />
            ) : current && current.objects.length > 0 && !search.isPending ? (
              <div className="panel row row--between">
                <span>{selected.length > 0 ? tx.del.ready(selected.length, current.request.bw_system) : tx.del.none}</span>
                <Button variant="danger" disabled={selected.length === 0 || blocked} onClick={() => setConfirming(true)}>
                  {selected.length > 0 ? tx.del.button(selected.length) : tx.del.buttonNone}
                </Button>
              </div>
            ) : (
              <p className="muted">{tx.del.waiting}</p>
            )}
          </Section>
        </>
      )}

      {data && (
        <Section title={tx.jobs.title} note={earlier.length > 0 ? tx.jobs.note : undefined}>
          {earlier.length === 0 ? (
            <p className="muted">{tx.jobs.empty}</p>
          ) : (
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>{tx.jobs.col.date}</th>
                    <th>{tx.jobs.col.system}</th>
                    <th>{tx.jobs.col.scope}</th>
                    <th>{tx.jobs.col.status}</th>
                    <th>{tx.jobs.col.message}</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {earlier.map((job) => {
                    const open = openJobs.has(job.id)
                    return (
                      <Fragment key={job.id}>
                        <tr>
                          <td className="num">{dateTime(job.created)}</td>
                          <td>
                            {job.bw_system} <span className="muted">· {job.mcp_server}</span>
                          </td>
                          <td className="secondary">
                            {tx.scope(job.scope.codes ?? [], job.scope.runs ?? [])} · {tx.objects(job.objects.length)}
                          </td>
                          <td>
                            <RunState status={job.status} batch />
                          </td>
                          <td className="secondary cleanup-message">{job.message || (job.status === 'planned' ? tx.job.stuck : t.common.none)}</td>
                          <td className="right">
                            <Button
                              small
                              aria-expanded={open}
                              onClick={() =>
                                setOpenJobs((old) => {
                                  const next = new Set(old)
                                  if (open) next.delete(job.id)
                                  else next.add(job.id)
                                  return next
                                })
                              }
                            >
                              {open ? tx.jobs.hide : tx.jobs.show}
                            </Button>
                          </td>
                        </tr>
                        {open && (
                          <tr className="cleanup-detail">
                            <td colSpan={6}>
                              <ObjectTable objects={job.objects} results={{ currentKey: null, finished: true }} />
                              {job.rest.length > 0 && (
                                <>
                                  <h3 className="cleanup-sub cleanup-rest">{tx.job.restTitle(job.rest.length)}</h3>
                                  <ObjectTable objects={job.rest} />
                                </>
                              )}
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Section>
      )}

      {confirming && current && selected.length > 0 && (
        <Dialog
          title={tx.del.confirmTitle(selected.length, current.request.bw_system)}
          onClose={closeConfirm}
          footer={
            <>
              <Button onClick={closeConfirm}>{t.common.actions.cancel}</Button>
              <Button variant="danger" busy={start.isPending} onClick={() => start.mutate({ request: current.request, objects: selected })}>
                {tx.del.confirm(selected.length)}
              </Button>
            </>
          }
        >
          <div className="stack">
            <p>{tx.del.confirmText(selected.length, current.request.bw_system, current.request.mcp_server)}</p>
            <dl className="kv">
              <dt>{tx.del.confirmScope}</dt>
              <dd>{scopeText}</dd>
              <dt>{tx.del.confirmTypes}</dt>
              <dd>{typeSummary(selected)}</dd>
            </dl>
            <ErrorNote error={start.error} />
          </div>
        </Dialog>
      )}
    </Page>
  )
}

/** „3 × InfoObject, 1 × aDSO, 1 × InfoArea“ in der Reihenfolge der Liste. */
function typeSummary(objects: Obj[]): string {
  const counts = new Map<string, number>()
  for (const obj of objects) counts.set(obj.type, (counts.get(obj.type) ?? 0) + 1)
  return [...counts.entries()].map(([type, count]) => `${count} × ${tx.types[type] ?? type}`).join(', ')
}

// --------------------------------------------------------------------------- Auftrag

function JobView(props: { job: Job; cancelling: boolean; onCancel: () => void; onSearchAgain?: () => void }) {
  const { job } = props
  const active = isActive(job)
  const total = job.objects.length
  const done = job.objects.filter((obj) => obj.result && obj.result !== 'open').length
  const next = job.status === 'running' ? job.objects.find((obj) => !obj.result || obj.result === 'open') : undefined
  const kind = job.status === 'done' ? 'ok' : job.status === 'error' ? 'error' : 'warn'
  return (
    <div className="stack">
      <div className="panel stack">
        <div className="row row--between">
          <span className="row">
            <RunState status={job.status} batch />
            <strong>{tx.job.heading(job.id, job.bw_system)}</strong>
            <span className="secondary">{tx.scope(job.scope.codes ?? [], job.scope.runs ?? [])}</span>
          </span>
          <span className="row">
            <span className="secondary num">{tx.job.progress(done, total)}</span>
            {active && (
              <Button busy={props.cancelling} disabled={Boolean(job.cancel_requested)} onClick={props.onCancel}>
                {tx.job.cancel}
              </Button>
            )}
          </span>
        </div>
        <Meter value={done} max={total} warn={job.objects.some((obj) => obj.result === 'error')} />
        {active && Boolean(job.cancel_requested) && <p className="muted small">{tx.job.cancelRequested}</p>}
      </div>

      {!active && <Notice kind={kind}>{job.status === 'planned' ? tx.job.stuck : job.message || tx.job.noMessage[job.status] || job.status}</Notice>}

      <ObjectTable objects={job.objects} results={{ currentKey: next ? objectKey(next) : null, finished: !active }} />

      {!active && job.rest.length > 0 && (
        <div>
          <h3 className="cleanup-sub">{tx.job.restTitle(job.rest.length)}</h3>
          <p className="section__note cleanup-rest-note">{tx.job.restNote}</p>
          <ObjectTable objects={job.rest} />
        </div>
      )}
      {!active && props.onSearchAgain && (job.rest.length > 0 || job.status !== 'done') && (
        <div className="row">
          <Button onClick={props.onSearchAgain}>{tx.job.searchAgain}</Button>
        </div>
      )}
    </div>
  )
}

// --------------------------------------------------------------------------- Objektliste

function BwObjectState({ status }: { status: string | undefined }) {
  const key = (status ?? '').toLowerCase()
  const look = key === 'active' ? (['pass', 'pass'] as const) : key === 'inactive' ? (['open', 'warn'] as const) : (['dot', 'neutral'] as const)
  return (
    <span className={`state state--${look[1]}`}>
      <Glyph kind={look[0]} />
      {tx.bwStatus[key] ?? (status || tx.bwStatus.unknown)}
    </span>
  )
}

function ResultState({ result, current, finished }: { result: string | undefined; current: boolean; finished: boolean }) {
  if (result === 'deleted') {
    return (
      <span className="state state--pass">
        <Glyph kind="pass" />
        {tx.result.deleted}
      </span>
    )
  }
  if (result === 'error') {
    return (
      <span className="state state--fail">
        <Glyph kind="fail" />
        {tx.result.error}
      </span>
    )
  }
  if (current) {
    return (
      <span className="state state--live">
        <Glyph kind="live" />
        {tx.result.current}
      </span>
    )
  }
  return (
    <span className="state state--neutral">
      <Glyph kind={finished ? 'skip' : 'open'} />
      {finished ? tx.result.skipped : tx.result.open}
    </span>
  )
}

/** Objekte nach Lauf gruppiert, je Lauf in Löschreihenfolge. Mit `selection` lassen sich Objekte
    abwählen, mit `results` zeigt die Liste das Ergebnis eines Auftrags. */
function ObjectTable(props: {
  objects: Obj[]
  selection?: { checked: Set<string>; toggle: (keys: string[], on: boolean) => void }
  results?: { currentKey: string | null; finished: boolean }
}) {
  const { objects, selection, results } = props
  const box = (keys: string[], label: string) => {
    const count = keys.filter((key) => selection!.checked.has(key)).length
    return (
      <label className="check">
        <input
          type="checkbox"
          checked={count === keys.length}
          aria-label={label}
          ref={(element) => {
            if (element) element.indeterminate = count > 0 && count < keys.length
          }}
          onChange={(event) => selection!.toggle(keys, event.target.checked)}
        />
      </label>
    )
  }
  return (
    <div className="table-wrap">
      <table className="table cleanup-objects">
        <thead>
          <tr>
            {selection && <th className="cleanup-check">{box(objects.map(objectKey), tx.check.selectAll)}</th>}
            <th>{tx.table.type}</th>
            <th>{tx.table.name}</th>
            {!results && <th>{tx.table.status}</th>}
            {!results && <th>{tx.table.title}</th>}
            <th>{tx.table.via}</th>
            {results && <th>{tx.table.result}</th>}
            {results && <th>{tx.table.message}</th>}
          </tr>
        </thead>
        <tbody>
          {groupByRun(objects).map(([run, group]) => (
            <Fragment key={run}>
              <tr className="cleanup-group">
                {selection && <td className="cleanup-check">{box(group.map(objectKey), run ? tx.check.selectRun(run) : tx.check.selectAll)}</td>}
                <td colSpan={5}>{run ? tx.table.run(run, group.length) : tx.table.noRun(group.length)}</td>
              </tr>
              {group.map((obj) => {
                const key = objectKey(obj)
                const label = tx.types[obj.type] ?? obj.type
                return (
                  <tr key={key} className={selection && !selection.checked.has(key) ? 'is-dim' : undefined}>
                    {selection && <td className="cleanup-check">{box([key], tx.check.selectOne(label, obj.name))}</td>}
                    <td className="nowrap" title={obj.type}>
                      {label}
                    </td>
                    <td className="nowrap">
                      <span className="mono">{obj.name}</span>
                      {obj.source_system && <span className="muted"> ({obj.source_system})</span>}
                    </td>
                    {!results && (
                      <td>
                        <BwObjectState status={obj.bw_status} />
                      </td>
                    )}
                    {!results && <td className="secondary">{obj.title || t.common.none}</td>}
                    <td className="nowrap">{obj.via ? <span className="mono">{obj.via}</span> : <span className="muted">{t.common.none}</span>}</td>
                    {results && (
                      <td>
                        <ResultState result={obj.result} current={key === results.currentKey} finished={results.finished} />
                      </td>
                    )}
                    {results && <td className="secondary cleanup-message">{obj.message || ''}</td>}
                  </tr>
                )
              })}
            </Fragment>
          ))}
        </tbody>
      </table>
    </div>
  )
}
