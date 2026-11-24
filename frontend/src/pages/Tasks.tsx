// Aufgaben: Liste, Editor mit Platzhaltern und Vorschau, Versionsschutz.
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api, ApiError } from '../api'
import { day, duration, num } from '../format'
import '../styles/tasks.css'
import { t } from '../texts'
import { Button, Dialog, Empty, ErrorNote, Field, Loading, Notice, Page, Section, Tabs, Tag, useToast } from '../ui'

const tx = t.tasks

type Requirement = { name: string; tools: string[] }
type HistoryEntry = { version?: number; datum?: string; notiz?: string }
type Task = {
  id: string
  version: number
  title: string
  prompt: string
  verify_prompt: string
  requirements: Requirement[]
  checkpoints: number | null
  timeout_s: number
  history: HistoryEntry[]
  used_runs: number
  versions?: number[]
  used_versions?: Record<string, number>
  content_hash?: string
  stored_only?: boolean
}
type Meta = { placeholders: Record<string, string>; tasks_dir: string }
type Preview = { prompt: string; verify_prompt: string; values: Record<string, string>; errors: string[]; hints: string[] }

/** Eine Anforderung im Formular; `key` hält die Zeile beim Umsortieren fest. */
type Row = { key: number; name: string; tools: string }
type Draft = { id: string; title: string; timeout: string; checkpoints: string; rows: Row[]; prompt: string; verify: string }
type Mode = 'create' | 'edit' | 'view'

const ID_PATTERN = /^[a-z0-9][a-z0-9-]{1,48}[a-z0-9]$/
const DEFAULT_TIMEOUT = '900'
const LIST = '/aufgaben'
const NEW = '/aufgaben?neu=1'
const taskPath = (id: string, version?: number | null) => `/aufgaben/${encodeURIComponent(id)}${version ? `?version=${version}` : ''}`
const copyPath = (id: string, version?: number | null) => `/aufgaben?kopie=${encodeURIComponent(id)}${version ? `&version=${version}` : ''}`

let rowKey = 0
const newRow = (name = '', tools = ''): Row => ({ key: ++rowKey, name, tools })

function toDraft(task: Task | null): Draft {
  return {
    id: task?.id ?? '',
    title: task?.title ?? '',
    timeout: task ? String(task.timeout_s) : DEFAULT_TIMEOUT,
    checkpoints: task?.checkpoints === null || task?.checkpoints === undefined ? '' : String(task.checkpoints),
    rows: (task?.requirements ?? []).map((r) => newRow(r.name, (r.tools ?? []).join(', '))),
    prompt: task?.prompt ?? '',
    verify: task?.verify_prompt ?? '',
  }
}

/** Ganze Zahlen als Zahl, alles andere unverändert: Dann erklärt das Backend, was nicht passt. */
function whole(value: string): number | string {
  const text = value.trim()
  return /^\d+$/.test(text) ? Number(text) : text
}

function toPayload(draft: Draft) {
  return {
    id: draft.id.trim(),
    title: draft.title.trim(),
    timeout_s: whole(draft.timeout),
    checkpoints: draft.checkpoints.trim() === '' ? null : whole(draft.checkpoints),
    requirements: draft.rows.map((row) => ({
      name: row.name.trim(),
      tools: row.tools
        .split(',')
        .map((part) => part.trim())
        .filter(Boolean),
    })),
    prompt: draft.prompt,
    verify_prompt: draft.verify,
  }
}

/** Inhalt so, wie das Backend ihn speichert: Leerraum an den Rändern zählt nicht als Änderung. */
function fingerprint(draft: Draft): string {
  const payload = toPayload(draft)
  return JSON.stringify({ ...payload, prompt: payload.prompt.trim(), verify_prompt: payload.verify_prompt.trim() })
}

function freeId(base: string, taken: string[]): string {
  const stem = `${base.slice(0, 40).replace(/-+$/, '')}-kopie`
  if (!taken.includes(stem)) return stem
  for (let n = 2; ; n++) if (!taken.includes(`${stem}-${n}`)) return `${stem}-${n}`
}

function withCode(text: string): ReactNode {
  return text.split('`').map((part, index) => (index % 2 ? <code key={index}>{part}</code> : part))
}

function useMeta() {
  return useQuery<Meta>({ queryKey: ['meta'], queryFn: () => api.get('/meta'), staleTime: 5 * 60_000 })
}

function useDebounced<T>(value: T, ms: number): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const id = window.setTimeout(() => setDebounced(value), ms)
    return () => window.clearTimeout(id)
  }, [value, ms])
  return debounced
}

/** Warnt vor dem Verlassen mit ungespeicherten Änderungen: beim Schließen oder Neuladen über den
    Browser, bei Verweisen der App (Menü, Kopfzeile) und eigenen Sprüngen über einen Dialog. */
function useLeaveGuard(dirty: boolean) {
  const navigate = useNavigate()
  const [pending, setPending] = useState<string | null>(null)

  useEffect(() => {
    if (!dirty) return
    const onUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault()
      event.returnValue = ''
    }
    const onClick = (event: MouseEvent) => {
      if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return
      const anchor = event.target instanceof Element ? event.target.closest<HTMLAnchorElement>('a[href]') : null
      if (!anchor || (anchor.target && anchor.target !== '_self') || anchor.hasAttribute('download')) return
      if (anchor.origin !== window.location.origin) return
      const target = anchor.pathname + anchor.search + anchor.hash
      if (target === window.location.pathname + window.location.search + window.location.hash) return
      event.preventDefault()
      event.stopPropagation()
      setPending(target)
    }
    window.addEventListener('beforeunload', onUnload)
    document.addEventListener('click', onClick, true)
    return () => {
      window.removeEventListener('beforeunload', onUnload)
      document.removeEventListener('click', onClick, true)
    }
  }, [dirty])

  const go = useCallback(
    (to: string) => {
      if (dirty) setPending(to)
      else navigate(to)
    },
    [dirty, navigate],
  )
  const stay = useCallback(() => setPending(null), [])
  const leave = useCallback(() => {
    setPending(null)
    if (pending) navigate(pending)
  }, [navigate, pending])
  return { go, pending, stay, leave }
}

// --------------------------------------------------------------------------- Seite

export default function Tasks() {
  const { id } = useParams()
  const [params] = useSearchParams()
  const versionText = params.get('version') ?? ''
  const version = /^\d+$/.test(versionText) ? Number(versionText) : null
  const copyOf = params.get('kopie')
  if (id) return <ExistingTask key={id} id={id} version={version} />
  if (copyOf) return <NewTask key={`kopie:${copyOf}:${version}`} copyOf={copyOf} version={version} />
  if (params.has('neu')) return <NewTask key="neu" copyOf={null} version={null} />
  return <TaskList />
}

function TaskList() {
  const navigate = useNavigate()
  const list = useQuery<Task[]>({ queryKey: ['tasks'], queryFn: () => api.get('/tasks') })
  const meta = useMeta()
  const rows = list.data ?? []
  const create = (
    <Link className="btn btn--primary" to={NEW}>
      {tx.newTask}
    </Link>
  )
  return (
    <Page title={tx.title} lead={tx.lead} actions={create}>
      {list.isLoading && <Loading />}
      <ErrorNote error={list.error} />
      {list.data && rows.length === 0 && (
        <Empty title={tx.list.emptyTitle} action={create}>
          {tx.list.emptyText}
        </Empty>
      )}
      {rows.length > 0 && (
        <Section title={tx.list.title} note={meta.data ? tx.list.folder(meta.data.tasks_dir) : undefined}>
          <div className="table-wrap">
            <table className="table table--click">
              <thead>
                <tr>
                  <th>{tx.list.col.id}</th>
                  <th>{tx.list.col.title}</th>
                  <th className="right">{tx.list.col.version}</th>
                  <th className="right">{tx.list.col.timeout}</th>
                  <th className="right">{tx.list.col.checkpoints}</th>
                  <th className="right">{tx.list.col.requirements}</th>
                  <th className="right">{tx.list.col.runs}</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {rows.map((task) => (
                  <tr
                    key={task.id}
                    onClick={(event) => {
                      if (!(event.target as Element).closest('a, button')) navigate(taskPath(task.id))
                    }}
                  >
                    <td className="nowrap">
                      <Link to={taskPath(task.id)}>
                        <strong>{task.id}</strong>
                      </Link>
                    </td>
                    <td>{task.title}</td>
                    <td className="right num">{task.version}</td>
                    <td className="right num">{duration(task.timeout_s)}</td>
                    <td className="right num">{num(task.checkpoints)}</td>
                    <td className="right num">{task.requirements.length}</td>
                    <td className="right num">{num(task.used_runs)}</td>
                    <td className="right">
                      <Link className="btn btn--small" to={copyPath(task.id)} aria-label={tx.list.copyOf(task.id)}>
                        {tx.copy}
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>
      )}
    </Page>
  )
}

const backToList = (
  <Link className="btn" to={LIST}>
    {tx.allTasks}
  </Link>
)

/** Neue Aufgabe: leer oder als Kopie einer vorhandenen (auch einer älteren Version). */
function NewTask({ copyOf, version }: { copyOf: string | null; version: number | null }) {
  const list = useQuery<Task[]>({ queryKey: ['tasks'], queryFn: () => api.get('/tasks') })
  const source = useQuery<Task>({
    queryKey: version === null ? ['task', copyOf] : ['task', copyOf, version],
    queryFn: () => api.get(`/tasks/${encodeURIComponent(copyOf ?? '')}${version === null ? '' : `?version=${version}`}`),
    enabled: copyOf !== null,
    retry: false,
  })
  if (list.isLoading || (copyOf !== null && source.isLoading)) {
    return (
      <Page title={tx.newTask}>
        <Loading lines={5} />
      </Page>
    )
  }
  if (copyOf !== null && !source.data) {
    return (
      <Page title={tx.newTask} actions={backToList}>
        <Empty title={tx.edit.missingTitle} action={backToList}>
          {source.error instanceof ApiError && source.error.status !== 404 ? source.error.message : tx.edit.missingText(copyOf)}
        </Empty>
      </Page>
    )
  }
  const taken = (list.data ?? []).map((task) => task.id)
  return <Editor mode="create" source={source.data ?? null} current={null} taken={taken} />
}

/** Vorhandene Aufgabe: aktuelle Version zum Bearbeiten, ältere benutzte Versionen nur lesend. */
function ExistingTask({ id, version }: { id: string; version: number | null }) {
  const [revision, setRevision] = useState(0)
  const current = useQuery<Task>({ queryKey: ['task', id], queryFn: () => api.get(`/tasks/${encodeURIComponent(id)}`), retry: false })
  const wantsOld = version !== null && current.data !== undefined && version !== current.data.version
  const old = useQuery<Task>({
    queryKey: ['task', id, version],
    queryFn: () => api.get(`/tasks/${encodeURIComponent(id)}?version=${version}`),
    enabled: wantsOld,
    retry: false,
  })

  if (current.isLoading || (wantsOld && old.isLoading)) {
    return (
      <Page title={id}>
        <Loading lines={5} />
      </Page>
    )
  }
  if (!current.data) {
    const missing = current.error instanceof ApiError && current.error.status === 404
    return (
      <Page title={tx.title} actions={backToList}>
        {missing ? (
          <Empty title={tx.edit.missingTitle} action={backToList}>
            {tx.edit.missingText(id)}
          </Empty>
        ) : (
          <ErrorNote error={current.error} />
        )}
      </Page>
    )
  }
  if (wantsOld && !old.data) {
    return (
      <Page title={id} actions={backToList}>
        <Empty
          title={tx.edit.versionMissing(version)}
          action={
            <Link className="btn btn--primary" to={taskPath(id)}>
              {tx.view.openCurrent(current.data.version)}
            </Link>
          }
        >
          {old.error instanceof ApiError && old.error.status !== 404 ? old.error.message : null}
        </Empty>
      </Page>
    )
  }
  const shown = wantsOld ? old.data! : current.data
  return (
    <Editor
      key={`${shown.version}:${shown.content_hash ?? ''}:${revision}`}
      mode={wantsOld ? 'view' : 'edit'}
      source={shown}
      current={current.data}
      taken={[]}
      onSaved={() => setRevision((n) => n + 1)}
    />
  )
}

// --------------------------------------------------------------------------- Editor

function Editor(props: {
  mode: Mode
  /** Inhalt, mit dem das Formular beginnt; beim Anlegen die Vorlage der Kopie oder null. */
  source: Task | null
  /** Aktuelle Version der Aufgabe (Sperre, Versionen, Historie); null beim Anlegen. */
  current: Task | null
  /** Vergebene IDs, damit eine neue nicht kollidiert. */
  taken: string[]
  onSaved?: () => void
}) {
  const { mode, source, current, taken } = props
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const toast = useToast()
  const meta = useMeta()

  const [initial] = useState<Draft>(() => {
    const draft = toDraft(source)
    return mode === 'create' && source ? { ...draft, id: freeId(source.id, taken), title: tx.create.copyTitle(source.title) } : draft
  })
  const [draft, setDraft] = useState<Draft>(initial)
  const [unlocked, setUnlocked] = useState(false)
  const [noteOpen, setNoteOpen] = useState(false)
  const [tab, setTab] = useState<'prompt' | 'verify'>('prompt')

  const runs = current?.used_runs ?? 0
  const used = mode === 'edit' && runs > 0
  const readOnly = mode === 'view' || (used && !unlocked)
  const dirty = mode !== 'view' && fingerprint(draft) !== fingerprint(initial)
  const nextVersion = current ? Math.max(current.version, ...Object.keys(current.used_versions ?? {}).map(Number)) + 1 : 1
  const guard = useLeaveGuard(dirty)

  const body = JSON.stringify(toPayload(draft))
  const debounced = useDebounced(body, 400)
  const preview = useQuery<Preview>({
    queryKey: ['task-preview', debounced],
    queryFn: () => api.post('/tasks/preview', JSON.parse(debounced)),
    placeholderData: keepPreviousData,
    gcTime: 10_000,
  })

  const save = useMutation({
    mutationFn: (extra: { create?: boolean; note?: string; confirm_new_version?: boolean }) =>
      api.post<Task>('/tasks', { ...toPayload(draft), ...extra }),
    onSuccess: (saved) => {
      queryClient.setQueryData(['task', saved.id], saved)
      queryClient.invalidateQueries({ queryKey: ['tasks'] })
      setNoteOpen(false)
      if (mode === 'create') {
        toast(tx.saved.created(saved.id))
        navigate(taskPath(saved.id))
      } else {
        toast(current && saved.version !== current.version ? tx.saved.version(saved.version) : t.common.saved)
        props.onSaved?.()
      }
    },
  })
  const resetSave = save.reset

  const change = (patch: Partial<Draft> | ((draft: Draft) => Draft)) => {
    setDraft((old) => (typeof patch === 'function' ? patch(old) : { ...old, ...patch }))
    if (save.isError) resetSave()
  }
  const changeRow = (key: number, patch: Partial<Row>) =>
    change((old) => ({ ...old, rows: old.rows.map((row) => (row.key === key ? { ...row, ...patch } : row)) }))
  const moveRow = (index: number, delta: number) =>
    change((old) => {
      const rows = [...old.rows]
      const [row] = rows.splice(index, 1)
      rows.splice(index + delta, 0, row)
      return { ...old, rows }
    })

  const idError =
    mode !== 'create' || draft.id === ''
      ? null
      : !ID_PATTERN.test(draft.id)
        ? tx.form.idInvalid
        : taken.includes(draft.id)
          ? tx.form.idTaken(draft.id)
          : null
  const timeout = whole(draft.timeout)

  const onSave = () => {
    if (mode === 'create') save.mutate({ create: true, note: source ? tx.create.copyNote(source.id, source.version) : undefined })
    else if (used) setNoteOpen(true)
    else save.mutate({})
  }
  const discard = () => {
    setDraft(initial)
    setUnlocked(false)
    resetSave()
  }
  const closeNote = useCallback(() => {
    setNoteOpen(false)
    resetSave()
  }, [resetSave])

  const lead =
    mode === 'create'
      ? source
        ? tx.create.copyLead(source.id, source.version)
        : tx.create.lead
      : mode === 'edit'
        ? `${current!.title} · ${tx.edit.lead(current!.version, runs)}`
        : source!.title
  const copyTarget = source && mode !== 'create' ? copyPath(source.id, mode === 'view' ? source.version : null) : null

  return (
    <Page
      title={mode === 'create' ? tx.newTask : source!.id}
      lead={lead}
      actions={
        <>
          <Button onClick={() => guard.go(LIST)}>{tx.allTasks}</Button>
          {copyTarget && !(used && !unlocked) && <Button onClick={() => guard.go(copyTarget)}>{tx.copy}</Button>}
        </>
      }
    >
      {mode === 'view' && current && source && (
        <Notice>
          <p>{tx.view.notice(source.version, current.version, source.used_runs)}</p>
          <div className="row tasks-notice-actions">
            <Button small variant="primary" onClick={() => guard.go(taskPath(current.id))}>
              {tx.view.openCurrent(current.version)}
            </Button>
          </div>
        </Notice>
      )}
      {used && !unlocked && current && (
        <Notice kind="warn">
          <p>{tx.lock.locked(current.version, runs)}</p>
          <p>{tx.lock.advice}</p>
          <div className="row tasks-notice-actions">
            <Button small variant="primary" onClick={() => guard.go(copyPath(current.id))}>
              {tx.copy}
            </Button>
            <Button small onClick={() => setUnlocked(true)}>
              {tx.lock.unlock}
            </Button>
          </div>
        </Notice>
      )}
      {used && unlocked && current && (
        <Notice kind="warn">
          <p>{tx.lock.unlocked(current.version, nextVersion)}</p>
          {!dirty && (
            <div className="row tasks-notice-actions">
              <Button small onClick={() => setUnlocked(false)}>
                {tx.lock.relock}
              </Button>
            </div>
          )}
        </Notice>
      )}

      <div className="tasks-editor">
        <div className="tasks-form">
          <Section title={tx.form.base}>
            <div className="panel">
              <div className="form-grid">
                <Field label={tx.form.id} hint={mode === 'create' ? tx.form.idHint : tx.form.idFixed} error={idError}>
                  <input
                    className="input mono"
                    value={draft.id}
                    readOnly={mode !== 'create'}
                    spellCheck={false}
                    autoCapitalize="off"
                    maxLength={50}
                    onChange={(event) => change({ id: event.target.value })}
                  />
                </Field>
                <Field
                  label={tx.form.timeout}
                  hint={typeof timeout === 'number' && timeout >= 60 ? tx.form.timeoutHint(duration(timeout)) : tx.form.timeoutRange}
                >
                  <input
                    className="input num"
                    inputMode="numeric"
                    value={draft.timeout}
                    readOnly={readOnly}
                    onChange={(event) => change({ timeout: event.target.value })}
                  />
                </Field>
                <Field label={tx.form.checkpoints} hint={tx.form.checkpointsHint}>
                  <input
                    className="input num"
                    inputMode="numeric"
                    value={draft.checkpoints}
                    readOnly={readOnly}
                    onChange={(event) => change({ checkpoints: event.target.value })}
                  />
                </Field>
                <Field label={tx.form.title} hint={tx.form.titleHint} wide>
                  <input className="input" value={draft.title} readOnly={readOnly} onChange={(event) => change({ title: event.target.value })} />
                </Field>
              </div>
            </div>
          </Section>

          <Section title={tx.req.title} note={withCode(tx.req.note)}>
            {draft.rows.length === 0 ? (
              <p className="muted small">{readOnly ? tx.req.emptyLocked : tx.req.empty}</p>
            ) : (
              <table className="table tasks-reqs">
                <thead>
                  <tr>
                    <th className="right">{tx.req.no}</th>
                    <th>{tx.req.name}</th>
                    <th>{tx.req.tools}</th>
                    {!readOnly && <th />}
                  </tr>
                </thead>
                <tbody>
                  {draft.rows.map((row, index) => (
                    <tr key={row.key}>
                      <td className="right num muted">{index + 1}</td>
                      <td className="tasks-reqs__name">
                        <input
                          className="input"
                          value={row.name}
                          readOnly={readOnly}
                          placeholder={tx.req.namePlaceholder}
                          aria-label={tx.req.nameLabel(index + 1)}
                          onChange={(event) => changeRow(row.key, { name: event.target.value })}
                        />
                      </td>
                      <td>
                        <input
                          className="input mono"
                          value={row.tools}
                          readOnly={readOnly}
                          spellCheck={false}
                          placeholder={tx.req.toolsPlaceholder}
                          aria-label={tx.req.toolsLabel(index + 1)}
                          onChange={(event) => changeRow(row.key, { tools: event.target.value })}
                        />
                      </td>
                      {!readOnly && (
                        <td className="right nowrap">
                          <Button small variant="quiet" disabled={index === 0} onClick={() => moveRow(index, -1)}>
                            {tx.req.up}
                          </Button>
                          <Button small variant="quiet" disabled={index === draft.rows.length - 1} onClick={() => moveRow(index, 1)}>
                            {tx.req.down}
                          </Button>
                          <Button
                            small
                            variant="quiet"
                            onClick={() => change((old) => ({ ...old, rows: old.rows.filter((other) => other.key !== row.key) }))}
                          >
                            {tx.req.remove}
                          </Button>
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            {!readOnly && (
              <div className="row tasks-reqs__add">
                <Button small onClick={() => change((old) => ({ ...old, rows: [...old.rows, newRow()] }))}>
                  {tx.req.add}
                </Button>
              </div>
            )}
          </Section>

          <Section title={tx.form.prompt} note={tx.form.promptNote}>
            <textarea
              className="textarea tasks-text"
              rows={18}
              value={draft.prompt}
              readOnly={readOnly}
              spellCheck={false}
              aria-label={tx.form.prompt}
              onFocus={() => setTab('prompt')}
              onChange={(event) => change({ prompt: event.target.value })}
            />
          </Section>

          <Section title={tx.form.verify} note={tx.form.verifyNote}>
            <textarea
              className="textarea tasks-text"
              rows={18}
              value={draft.verify}
              readOnly={readOnly}
              spellCheck={false}
              aria-label={tx.form.verify}
              onFocus={() => setTab('verify')}
              onChange={(event) => change({ verify: event.target.value })}
            />
          </Section>

          {!readOnly && (
            <div className="tasks-savebar">
              {!noteOpen && save.isError && (
                <div className="tasks-savebar__error">
                  <ErrorNote error={save.error} />
                </div>
              )}
              <span className={`state state--${dirty || mode === 'create' ? 'warn' : 'neutral'}`}>
                {mode === 'create' ? tx.bar.notCreated : dirty ? tx.bar.dirty : tx.bar.clean}
              </span>
              <span className="row">
                <Button disabled={!dirty} onClick={discard}>
                  {tx.bar.discard}
                </Button>
                <Button variant="primary" busy={save.isPending} disabled={mode === 'create' ? idError !== null : !dirty} onClick={onSave}>
                  {mode === 'create' ? tx.bar.create : used ? tx.bar.saveAs(nextVersion) : tx.bar.save(current!.version)}
                </Button>
              </span>
            </div>
          )}
        </div>

        <aside className="tasks-side panel">
          {!readOnly && (
            <Section title={tx.side.checkTitle}>
              <ErrorNote error={preview.error} />
              {preview.data && preview.data.errors.length > 0 && (
                <Notice kind="error">
                  <p>{tx.side.errors}</p>
                  <ul className="tasks-issues">
                    {preview.data.errors.map((text) => (
                      <li key={text}>{text}</li>
                    ))}
                  </ul>
                </Notice>
              )}
              {preview.data && preview.data.hints.length > 0 && (
                <Notice kind="warn">
                  <p>{tx.side.hints}</p>
                  <ul className="tasks-issues">
                    {preview.data.hints.map((text) => (
                      <li key={text}>{text}</li>
                    ))}
                  </ul>
                </Notice>
              )}
              {preview.data && preview.data.errors.length + preview.data.hints.length === 0 && <Notice kind="ok">{tx.side.ok}</Notice>}
              {!preview.data && preview.isLoading && <Loading lines={2} />}
            </Section>
          )}

          <Section title={tx.side.placeholdersTitle} note={tx.side.placeholdersNote}>
            {meta.isLoading && <Loading lines={4} />}
            <ErrorNote error={meta.error} />
            {meta.data && (
              <table className="table tasks-placeholders">
                <thead>
                  <tr>
                    <th>{tx.side.col.placeholder}</th>
                    <th>{tx.side.col.meaning}</th>
                    <th>{tx.side.col.value}</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(meta.data.placeholders).map(([name, meaning]) => (
                    <tr key={name}>
                      <td>
                        <code>{`{${name}}`}</code>
                      </td>
                      <td className="secondary">{meaning}</td>
                      <td className="mono">{preview.data?.values[name] ?? t.common.none}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Section>

          <Section title={tx.side.previewTitle} note={tx.side.previewNote}>
            <Tabs
              tabs={[
                { id: 'prompt', label: tx.side.tabPrompt },
                { id: 'verify', label: tx.side.tabVerify },
              ]}
              value={tab}
              onChange={setTab}
            />
            {!preview.data && preview.isLoading && <Loading lines={6} />}
            {preview.data &&
              ((tab === 'prompt' ? preview.data.prompt : preview.data.verify_prompt).trim() ? (
                <pre className="tasks-preview">{tab === 'prompt' ? preview.data.prompt : preview.data.verify_prompt}</pre>
              ) : (
                <p className="muted small">{tx.side.previewEmpty}</p>
              ))}
          </Section>
        </aside>
      </div>

      {mode !== 'create' && current && source && (
        <Section>
          <div className="grid grid--side">
            <div>
              <h2 className="section__title tasks-subtitle">{tx.history.title}</h2>
              {current.history.length === 0 ? (
                <p className="muted small">{tx.history.empty}</p>
              ) : (
                <table className="table">
                  <thead>
                    <tr>
                      <th className="right">{tx.history.col.version}</th>
                      <th>{tx.history.col.date}</th>
                      <th>{tx.history.col.note}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[...current.history].reverse().map((entry, index) => (
                      <tr key={index}>
                        <td className="right num">{entry.version ?? t.common.none}</td>
                        <td className="num">{day(entry.datum)}</td>
                        <td>{entry.notiz}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
            <div>
              <h2 className="section__title tasks-subtitle">{tx.versions.title}</h2>
              <p className="section__note tasks-subnote">{tx.versions.note}</p>
              <table className="table">
                <thead>
                  <tr>
                    <th>{tx.versions.col.version}</th>
                    <th className="right">{tx.versions.col.runs}</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {[...(current.versions ?? [current.version])].reverse().map((version) => (
                    <tr key={version}>
                      <td className="num">
                        {version} {version === current.version && <Tag>{tx.versions.current}</Tag>}
                      </td>
                      <td className="right num">{num(current.used_versions?.[String(version)] ?? 0)}</td>
                      <td className="right">
                        {version === source.version ? (
                          <span className="muted">{tx.versions.shown}</span>
                        ) : (
                          <Button
                            small
                            aria-label={tx.versions.showLabel(version)}
                            onClick={() => guard.go(taskPath(current.id, version === current.version ? null : version))}
                          >
                            {tx.versions.show}
                          </Button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </Section>
      )}

      {noteOpen && current && (
        <VersionDialog
          version={current.version}
          runs={runs}
          next={nextVersion}
          busy={save.isPending}
          error={save.error}
          onClose={closeNote}
          onSave={(note) => save.mutate({ confirm_new_version: true, note })}
        />
      )}
      {guard.pending !== null && (
        <Dialog
          title={tx.leave.title}
          onClose={guard.stay}
          footer={
            <>
              <Button onClick={guard.stay}>{tx.leave.stay}</Button>
              <Button variant="danger" onClick={guard.leave}>
                {tx.leave.leave}
              </Button>
            </>
          }
        >
          <p>{tx.leave.text}</p>
        </Dialog>
      )}
    </Page>
  )
}

/** Speichern einer benutzten Version: nur als neue Version und nur mit Änderungsnotiz. */
function VersionDialog(props: {
  version: number
  runs: number
  next: number
  busy: boolean
  error: unknown
  onClose: () => void
  onSave: (note: string) => void
}) {
  const [note, setNote] = useState('')
  const field = useRef<HTMLTextAreaElement>(null)
  useEffect(() => field.current?.focus(), [])
  return (
    <Dialog
      title={tx.versionDialog.title(props.next)}
      onClose={props.onClose}
      footer={
        <>
          <Button onClick={props.onClose}>{t.common.actions.cancel}</Button>
          <Button variant="primary" busy={props.busy} disabled={note.trim() === ''} onClick={() => props.onSave(note.trim())}>
            {tx.versionDialog.title(props.next)}
          </Button>
        </>
      }
    >
      <div className="stack">
        <p>{tx.versionDialog.text(props.version, props.runs, props.next)}</p>
        <Field label={tx.versionDialog.note} hint={tx.versionDialog.noteHint}>
          <textarea
            ref={field}
            className="textarea"
            rows={3}
            value={note}
            placeholder={tx.versionDialog.notePlaceholder}
            onChange={(event) => setNote(event.target.value)}
          />
        </Field>
        <ErrorNote error={props.error} />
      </div>
    </Dialog>
  )
}
