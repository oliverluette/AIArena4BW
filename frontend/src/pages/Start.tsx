// Durchgang starten: Auswahl, Vorlage aus einem früheren Durchgang, mitlaufende Vorschau und Start.
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { day, duration, num, usd } from '../format'
import '../styles/start.css'
import { t } from '../texts'
import { BwState, Button, Chips, Empty, ErrorNote, Field, Figure, Glyph, Loading, Notice, Page, Section, useToast } from '../ui'

const tx = t.start

type BwSystem = { id: string; note: string; status: { state: string; detail: string } | null }
type McpServer = { name: string; last_test: { ok?: boolean; tool_count?: number } | null }
type Task = { id: string; version: number; title: string; checkpoints: number; timeout_s: number | null }
type Model = {
  id: string
  model_id: string
  name: string
  vendor: string
  vendor_name: string
  platform_id: string
  platform_name: string
  price_in: number | null
  price_out: number | null
}
type Options = {
  bw_systems: BwSystem[]
  default_bw_system: string | null
  mcp_servers: McpServer[]
  default_mcp_server: string | null
  tasks: Task[]
  models: Model[]
  all_models: { id: string; name: string }[]
  settings: { verify: { model: string; fallback: string }; run: { thinking: unknown; cost_limit: number } }
  thinking_levels: string[]
  templates?: Template[] // fehlt, solange noch ein älterer Stand der App läuft
  notice_accepted?: boolean
  busy: boolean
}
type Warning = { kind: string; text: string }
type Template = { id: number; code: string; created: string; note: string; repeats: number; tasks: number; models: number }
type TemplateData = {
  id: number
  code: string
  spec: {
    bw_system: string | null
    mcp_server: string | null
    tasks: string[]
    models: string[]
    thinking: string[]
    repeats: number
    verifier: string
    fallback: string
    cost_limit: number | null
    note: string
  }
  notes: Warning[]
}
/** Die Angaben eines Durchgangs. Filter und Suche der Modellliste gehören nicht dazu. */
type Form = {
  system: string
  server: string
  taskIds: string[]
  modelIds: string[]
  levels: string[]
  repeats: number
  verifier: string
  fallback: string
  costLimit: string
  note: string
}
type Preview = {
  code: string
  runs: number
  combinations: number
  repeats: number
  levels: string[]
  cost_limit: number
  verifier: string
  fallback: string
  estimate: { usd: number | null; known: number; total: number }
  warnings: Warning[]
}

/** Gewicht der Hinweise aus der Vorschau; unbekannte Arten gelten als Warnung. */
const WARNING_KIND: Record<string, 'error' | 'warn' | 'info'> = {
  bw_down: 'error',
  data: 'info',
  verifier_fallback: 'info',
  no_reasoning: 'warn',
}

/** Gewicht der Hinweise zu einer Vorlage: Was fehlt, ist eine Warnung; eine neue Aufgabenversion nur ein Hinweis. */
const TEMPLATE_NOTE_KIND: Record<string, 'warn' | 'info'> = { task_version: 'info' }

const REPEATS = ['1', '2', '3', '4', '5', '6', '7', '8', '9']

export default function Start() {
  const options = useQuery<Options>({ queryKey: ['start-options'], queryFn: () => api.get('/start-options'), refetchInterval: 10000 })
  const data = options.data
  const ready = data && data.bw_systems.length > 0 && data.mcp_servers.length > 0 && data.models.length > 0 && data.tasks.length > 0
  return (
    <Page title={tx.title} lead={tx.lead}>
      {options.isLoading && <Loading lines={5} />}
      <ErrorNote error={options.error} />
      {data && !ready && <Missing options={data} />}
      {data && ready && <StartForm options={data} />}
    </Page>
  )
}

/** Leerer Zustand: sagt, was fehlt und wo es eingerichtet wird. */
function Missing({ options }: { options: Options }) {
  const items = [
    { ok: options.bw_systems.length > 0, text: tx.missing.bw },
    { ok: options.mcp_servers.length > 0, text: tx.missing.mcp },
    { ok: options.models.length > 0, text: tx.missing.models },
    { ok: options.tasks.length > 0, text: tx.missing.tasks },
  ]
  const onlyTasks = items.slice(0, 3).every((item) => item.ok)
  return (
    <Empty
      title={tx.missing.title}
      action={
        onlyTasks ? (
          <Link className="btn btn--primary" to="/aufgaben">{tx.missing.tasksAction}</Link>
        ) : (
          <Link className="btn btn--primary" to="/einstellungen">{tx.missing.settings}</Link>
        )
      }
    >
      <p>{tx.missing.text}</p>
      <ul style={{ listStyle: 'none', padding: 0, margin: '12px 0 0' }}>
        {items.map((item) => (
          <li key={item.text} className={`state state--${item.ok ? 'pass' : 'neutral'}`} style={{ display: 'flex', padding: '3px 0' }}>
            <Glyph kind={item.ok ? 'pass' : 'open'} />
            <span style={{ color: 'var(--text)', fontWeight: 400 }}>{item.text}</span>
            <span className="muted" style={{ fontWeight: 400 }}>· {item.ok ? tx.missing.done : tx.missing.open}</span>
          </li>
        ))}
      </ul>
    </Empty>
  )
}

function StartForm({ options }: { options: Options }) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const toast = useToast()
  const { settings } = options
  const templates = options.templates ?? []

  const [form, setForm] = useState<Form>(() => initialForm(options))
  const { system, server, taskIds, modelIds, levels, repeats, verifier, fallback, costLimit, note } = form
  const set = (patch: Partial<Form>) => setForm((current) => ({ ...current, ...patch }))
  const pick = (field: 'taskIds' | 'modelIds', id: string) => setForm((current) => ({ ...current, [field]: toggle(current[field], id) }))
  // Die zuletzt übernommene Vorlage; key hält den Stand direkt nach der Übernahme fest.
  const [applied, setApplied] = useState<{ id: number; code: string; notes: Warning[]; key: string } | null>(null)
  const [platforms, setPlatforms] = useState<string[]>([])
  const [vendors, setVendors] = useState<string[]>([])
  const [search, setSearch] = useState('')

  // Die Auswahl folgt den Optionen: Was es nicht mehr gibt, fällt heraus.
  const systemId = options.bw_systems.some((s) => s.id === system) ? system : options.bw_systems[0].id
  const serverName = options.mcp_servers.some((s) => s.name === server) ? server : options.mcp_servers[0].name
  const chosenSystem = options.bw_systems.find((s) => s.id === systemId)
  const chosenServer = options.mcp_servers.find((s) => s.name === serverName)
  const chosenTasks = options.tasks.filter((task) => taskIds.includes(task.id)).map((task) => task.id)
  const chosenModels = options.models.filter((model) => modelIds.includes(model.id)).map((model) => model.id)

  const limit = parseLimit(costLimit)
  const limitError = limit === 'invalid'
  const spec = {
    bw_system: systemId,
    mcp_server: serverName,
    tasks: chosenTasks,
    models: chosenModels,
    thinking: levels,
    repeats,
    verifier,
    fallback,
    cost_limit: limitError ? null : limit,
  }
  const complete = chosenTasks.length > 0 && chosenModels.length > 0 && !limitError

  // Vorschau: entprellt, damit nicht jeder Klick eine Anfrage auslöst.
  const specKey = JSON.stringify(spec)
  const previewKey = useDebounced(specKey, 350)
  const settled = specKey === previewKey
  const preview = useQuery<Preview>({
    queryKey: ['batch-preview', previewKey],
    queryFn: () => api.post('/batches/preview', JSON.parse(previewKey)),
    enabled: complete && settled,
    placeholderData: keepPreviousData,
    retry: false,
    staleTime: 0,
    refetchInterval: 15000,
  })
  const shown = complete ? preview.data : undefined
  const previewError = complete && settled ? preview.error : null
  const current = settled && !preview.isPlaceholderData && !preview.isError && Boolean(preview.data)

  const startBatch = useMutation({
    mutationFn: () => api.post<{ id: number; code: string }>('/batches', { ...spec, note: note.trim() }),
    onSuccess: (batch) => {
      queryClient.invalidateQueries({ queryKey: ['batches'] })
      queryClient.invalidateQueries({ queryKey: ['status'] })
      queryClient.invalidateQueries({ queryKey: ['start-options'] })
      // Die Live-Seite soll den neuen Durchgang zeigen, nicht kurz noch den letzten Stand des vorigen.
      queryClient.removeQueries({ queryKey: ['live'] })
      toast(tx.started(batch.code))
      navigate('/live')
    },
  })

  const modelNames = useMemo(() => new Map(options.all_models.map((m) => [m.id, m.name])), [options.all_models])
  const nameOf = (id: string) => (id ? (modelNames.get(id) ?? id) : tx.extra.notSet)

  // Modelle eingrenzen: Plattform und Anbieter über Chips, dazu die Suche.
  const platformOptions = useMemo(() => distinct(options.models.map((m) => ({ value: m.platform_id, label: m.platform_name }))), [options.models])
  const vendorOptions = useMemo(() => distinct(options.models.map((m) => ({ value: m.vendor, label: m.vendor_name || m.vendor }))), [options.models])
  const needle = search.trim().toLowerCase()
  const visible = options.models.filter(
    (m) =>
      (platforms.length === 0 || platforms.includes(m.platform_id)) &&
      (vendors.length === 0 || vendors.includes(m.vendor)) &&
      (!needle || `${m.name} ${m.vendor_name} ${m.platform_name} ${m.id}`.toLowerCase().includes(needle)),
  )
  const visibleIds = visible.map((m) => m.id)
  const hiddenChosen = chosenModels.filter((id) => !visibleIds.includes(id)).length
  const allVisibleChosen = visible.length > 0 && visibleIds.every((id) => modelIds.includes(id))
  const filtered = platforms.length > 0 || vendors.length > 0 || needle !== ''

  const resetFilters = () => {
    setPlatforms([])
    setVendors([])
    setSearch('')
  }
  const levelOrder = (a: string, b: string) => options.thinking_levels.indexOf(a) - options.thinking_levels.indexOf(b)

  // Vorlage: übernimmt alle Angaben eines früheren Durchgangs; „Zurücksetzen“ stellt die Vorgaben wieder her.
  const loadTemplate = useMutation({
    mutationFn: (id: number) => api.get<TemplateData>(`/batches/${id}/template`),
    onSuccess: (template) => {
      const next = fromTemplate(template.spec, options)
      setForm(next)
      setApplied({ id: template.id, code: template.code, notes: template.notes, key: formKey(next) })
      resetFilters()
    },
  })
  const pristine = !applied && !filtered && formKey(form) === formKey(initialForm(options))
  const reset = () => {
    setForm(initialForm(options))
    setApplied(null)
    resetFilters()
    loadTemplate.reset()
    startBatch.reset()
  }

  return (
    <div className="grid grid--side">
      <div>
        <Section title={tx.env.title} note={tx.env.note}>
          <div className="form-grid">
            <Field label={tx.env.system} hint={<BwState status={chosenSystem?.status} />}>
              <select className="select" value={systemId} onChange={(e) => set({ system: e.target.value })}>
                {options.bw_systems.map((s) => (
                  <option key={s.id} value={s.id}>{s.id}</option>
                ))}
              </select>
            </Field>
            <Field
              label={tx.env.server}
              hint={chosenServer?.last_test?.ok ? tx.env.tools(chosenServer.last_test.tool_count ?? 0) : tx.env.untested}
            >
              <select className="select" value={serverName} onChange={(e) => set({ server: e.target.value })}>
                {options.mcp_servers.map((s) => (
                  <option key={s.name} value={s.name}>{s.name}</option>
                ))}
              </select>
            </Field>
          </div>
        </Section>

        <Section title={tx.tasks.title} note={tx.tasks.chosen(chosenTasks.length, options.tasks.length)}>
          <div className="table-wrap">
            <table className="table table--click start-table">
              <thead>
                <tr>
                  <th className="start-pick" />
                  <th>{tx.tasks.col.task}</th>
                  <th className="right">{tx.tasks.col.version}</th>
                  <th className="right">{tx.tasks.col.timeout}</th>
                  <th className="right">{tx.tasks.col.checkpoints}</th>
                </tr>
              </thead>
              <tbody>
                {options.tasks.map((task) => {
                  const picked = taskIds.includes(task.id)
                  return (
                    <tr key={task.id} className={picked ? 'is-picked' : ''} onClick={() => pick('taskIds', task.id)}>
                      <td>
                        <Pick checked={picked} label={tx.tasks.pick(task.title)} onChange={() => pick('taskIds', task.id)} />
                      </td>
                      <td>
                        <strong>{task.title}</strong>
                        <div className="muted">{task.id}</div>
                      </td>
                      <td className="right num">{task.version}</td>
                      <td className="right num">{duration(task.timeout_s)}</td>
                      <td className="right num">{num(task.checkpoints)}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </Section>

        <Section
          title={tx.models.title}
          note={tx.models.chosen(chosenModels.length, options.models.length) + (hiddenChosen > 0 ? tx.models.hidden(hiddenChosen) : '')}
        >
          <div className="stack">
            <div className="start-filter">
              {platformOptions.length > 1 && (
                <>
                  <span className="secondary small">{tx.models.platform}</span>
                  <Chips options={platformOptions} value={platforms} onChange={setPlatforms} ariaLabel={tx.models.platform} />
                </>
              )}
              {vendorOptions.length > 1 && (
                <>
                  <span className="secondary small">{tx.models.vendor}</span>
                  <Chips options={vendorOptions} value={vendors} onChange={setVendors} ariaLabel={tx.models.vendor} />
                </>
              )}
            </div>
            <div className="row">
              <input
                className="input start-search"
                type="search"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder={tx.models.searchPlaceholder}
                aria-label={tx.models.search}
              />
              <span className="spacer" />
              {allVisibleChosen ? (
                <Button small onClick={() => set({ modelIds: modelIds.filter((id) => !visibleIds.includes(id)) })}>{tx.models.clearVisible}</Button>
              ) : (
                <Button small disabled={visible.length === 0} onClick={() => set({ modelIds: [...new Set([...modelIds, ...visibleIds])] })}>
                  {tx.models.selectVisible(visible.length)}
                </Button>
              )}
              <Button small variant="quiet" disabled={chosenModels.length === 0} onClick={() => set({ modelIds: [] })}>
                {tx.models.clearAll}
              </Button>
            </div>
            {visible.length === 0 ? (
              <Notice>
                {tx.models.noneVisible}{' '}
                {filtered && (
                  <Button small variant="quiet" onClick={resetFilters}>
                    {tx.models.resetFilters}
                  </Button>
                )}
              </Notice>
            ) : (
              <div className="start-models table-wrap">
                <table className="table table--click start-table">
                  <thead>
                    <tr>
                      <th className="start-pick" />
                      <th>{tx.models.col.model}</th>
                      <th>{tx.models.col.vendor}</th>
                      <th>{tx.models.col.platform}</th>
                      <th className="right">{tx.models.col.price}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visible.map((model) => {
                      const picked = modelIds.includes(model.id)
                      return (
                        <tr key={model.id} className={picked ? 'is-picked' : ''} onClick={() => pick('modelIds', model.id)}>
                          <td>
                            <Pick checked={picked} label={tx.models.pick(model.name)} onChange={() => pick('modelIds', model.id)} />
                          </td>
                          <td title={model.id}>
                            <strong>{model.name}</strong>
                          </td>
                          <td className="secondary">{model.vendor_name || model.vendor}</td>
                          <td className="secondary">{model.platform_name}</td>
                          <td className="right num">{price(model)}</td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}
            <p className="muted small">
              <Link to="/einstellungen">{tx.models.more}</Link>
            </p>
          </div>
        </Section>

        <Section title={tx.scope.title}>
          <div className="stack">
            <Group label={tx.scope.thinking} hint={tx.scope.thinkingHint}>
              <Chips
                options={options.thinking_levels}
                value={levels}
                onChange={(value) => set({ levels: value.length ? [...value].sort(levelOrder) : [''] })}
                label={(value) => t.common.thinking[value] ?? value}
                ariaLabel={tx.scope.thinking}
              />
            </Group>
            <Group label={tx.scope.repeats} hint={tx.scope.repeatsHint}>
              <Chips
                options={REPEATS}
                value={[String(repeats)]}
                single
                onChange={(value) => {
                  if (value.length) set({ repeats: Number(value[0]) })
                }}
                ariaLabel={tx.scope.repeats}
              />
            </Group>
          </div>
        </Section>

        <Section title={tx.template.title} note={tx.template.note}>
          <div className="stack">
            <div className="start-template">
              <Field label={tx.template.label}>
                <select
                  className="select"
                  value={applied ? String(applied.id) : ''}
                  disabled={templates.length === 0 || loadTemplate.isPending}
                  onChange={(e) => loadTemplate.mutate(Number(e.target.value))}
                >
                  <option value="" disabled>
                    {templates.length > 0 ? tx.template.placeholder : tx.template.none}
                  </option>
                  {templates.map((item) => (
                    <option key={item.id} value={item.id}>
                      {tx.template.option(item.code, day(item.created), item.tasks, item.models, item.repeats, item.note)}
                    </option>
                  ))}
                </select>
              </Field>
              <Button disabled={pristine} title={tx.template.resetTitle} onClick={reset}>
                {tx.template.reset}
              </Button>
            </div>
            <ErrorNote error={loadTemplate.error} />
            {applied && <Notice>{applied.key === formKey(form) ? tx.template.applied(applied.code) : tx.template.appliedChanged(applied.code)}</Notice>}
            {applied?.notes.map((item, index) => (
              <Notice key={`${item.kind}-${index}`} kind={TEMPLATE_NOTE_KIND[item.kind] ?? 'warn'}>
                {item.text}
              </Notice>
            ))}
          </div>
        </Section>

        <Section title={tx.extra.title} note={tx.extra.note}>
          <div className="form-grid">
            <Field label={tx.extra.verifier}>
              <select className="select" value={verifier} onChange={(e) => set({ verifier: e.target.value })}>
                <option value="">{tx.extra.asSet(nameOf(settings.verify.model))}</option>
                <ModelOptions models={options.all_models} />
              </select>
            </Field>
            <Field label={tx.extra.fallback} hint={tx.extra.fallbackHint}>
              <select className="select" value={fallback} onChange={(e) => set({ fallback: e.target.value })}>
                <option value="">{tx.extra.asSet(nameOf(settings.verify.fallback))}</option>
                <ModelOptions models={options.all_models} />
              </select>
            </Field>
            <Field label={tx.extra.costLimit} hint={tx.extra.costLimitHint} error={limitError ? tx.extra.costLimitError : undefined}>
              <input
                className="input"
                inputMode="decimal"
                value={costLimit}
                onChange={(e) => set({ costLimit: e.target.value })}
                placeholder={tx.extra.costLimitPlaceholder(limitText(settings.run.cost_limit))}
                aria-invalid={limitError || undefined}
              />
            </Field>
            <Field label={tx.extra.noteLabel} wide>
              <input className="input" value={note} onChange={(e) => set({ note: e.target.value })} placeholder={tx.extra.notePlaceholder} maxLength={200} />
            </Field>
          </div>
        </Section>
      </div>

      <aside className="start-side" aria-label={tx.preview.title}>
        <div className="panel stack">
          <h2 className="section__title">{tx.preview.title}</h2>
          {!complete && !limitError && <p className="secondary">{tx.preview.incomplete}</p>}
          {limitError && <Notice kind="error">{tx.extra.costLimitError}</Notice>}
          {previewError && <ErrorNote error={previewError} />}
          {complete && !shown && !previewError && <Loading lines={4} />}
          {shown && !previewError && (
            <div className="stack" aria-busy={!current || undefined} style={{ opacity: current ? 1 : 0.55, transition: 'opacity 0.15s var(--ease)' }}>
              <div className="figures">
                <Figure value={shown.code} label={tx.preview.code} />
                <Figure value={num(shown.runs)} label={tx.preview.runs(shown.combinations, shown.repeats)} />
              </div>
              {shown.estimate.usd !== null ? (
                <Figure value={tx.preview.estimate(usd(shown.estimate.usd, 2))} label={tx.preview.estimateLabel(shown.estimate.known, shown.estimate.total)} />
              ) : (
                <p className="secondary small">{tx.preview.noEstimate}</p>
              )}
              <dl className="kv">
                <dt>{tx.preview.verifier}</dt>
                <dd>{nameOf(shown.verifier)}</dd>
                <dt>{tx.preview.fallback}</dt>
                <dd>{nameOf(shown.fallback)}</dd>
                <dt>{tx.preview.costLimit}</dt>
                <dd className="num">{limitText(shown.cost_limit)}</dd>
                <dt>{tx.preview.thinking}</dt>
                <dd>{shown.levels.map((level) => t.common.thinking[level] ?? level).join(', ')}</dd>
              </dl>
              {shown.estimate.usd !== null && shown.cost_limit > 0 && shown.estimate.usd > shown.cost_limit && <Notice kind="warn">{tx.preview.overLimit}</Notice>}
              {shown.warnings.map((warning, index) => (
                <Notice key={`${warning.kind}-${index}`} kind={WARNING_KIND[warning.kind] ?? 'warn'}>
                  {warning.text}
                </Notice>
              ))}
            </div>
          )}
          {options.busy && (
            <Notice kind="warn">
              {tx.busy} <Link to="/live">{tx.busyLink}</Link>
            </Notice>
          )}
          {options.notice_accepted === false && <Notice kind="warn">{tx.noticeMissing}</Notice>}
          <Button variant="primary" disabled={options.busy || !current || options.notice_accepted === false} busy={startBatch.isPending} onClick={() => startBatch.mutate()}>
            {tx.startAction}
          </Button>
          {current && shown && !options.busy && <p className="muted small">{tx.startHint(shown.runs)}</p>}
          <ErrorNote error={startBatch.error} />
        </div>
      </aside>
    </div>
  )
}

/** Auswahlkästchen einer Tabellenzeile; die Zeile selbst schaltet ebenfalls um. */
function Pick(props: { checked: boolean; label: string; onChange: () => void }) {
  return (
    <span className="check">
      <input type="checkbox" checked={props.checked} aria-label={props.label} onClick={(e) => e.stopPropagation()} onChange={props.onChange} />
    </span>
  )
}

/** Beschriftete Gruppe von Chips (kein <label>, weil darin mehrere Schaltflächen liegen). */
function Group(props: { label: string; hint?: string; children: ReactNode }) {
  return (
    <div className="field">
      <span className="field__label">{props.label}</span>
      {props.children}
      {props.hint && <span className="field__hint">{props.hint}</span>}
    </div>
  )
}

function ModelOptions({ models }: { models: { id: string; name: string }[] }) {
  return (
    <>
      {models.map((model) => (
        <option key={model.id} value={model.id}>
          {tx.extra.modelOption(model.name, model.id.split(':')[0])}
        </option>
      ))}
    </>
  )
}

function useDebounced<T>(value: T, ms: number): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const id = window.setTimeout(() => setDebounced(value), ms)
    return () => window.clearTimeout(id)
  }, [value, ms])
  return debounced
}

function distinct(items: { value: string; label: string }[]): { value: string; label: string }[] {
  const seen = new Map<string, { value: string; label: string }>()
  for (const item of items) if (!seen.has(item.value)) seen.set(item.value, item)
  return [...seen.values()].sort((a, b) => a.label.localeCompare(b.label, 'de'))
}

function toggle(list: string[], id: string): string[] {
  return list.includes(id) ? list.filter((x) => x !== id) : [...list, id]
}

/** Die Vorgaben: Standardsystem und -server, Denkstufen aus den Einstellungen, sonst leer. */
function initialForm(options: Options): Form {
  return {
    system: options.default_bw_system ?? '',
    server: options.default_mcp_server ?? '',
    taskIds: options.tasks.length === 1 ? [options.tasks[0].id] : [],
    modelIds: [],
    levels: initialLevels(options.settings.run.thinking, options.thinking_levels),
    repeats: 1,
    verifier: '',
    fallback: '',
    costLimit: '',
    note: '',
  }
}

/** Die Angaben einer Vorlage. Was es nicht mehr gibt, liefert die App nicht mit; dort gilt die Vorgabe. */
function fromTemplate(spec: TemplateData['spec'], options: Options): Form {
  const base = initialForm(options)
  return {
    system: spec.bw_system ?? base.system,
    server: spec.mcp_server ?? base.server,
    taskIds: spec.tasks,
    modelIds: spec.models,
    levels: spec.thinking.length ? spec.thinking : [''],
    repeats: spec.repeats,
    verifier: spec.verifier,
    fallback: spec.fallback,
    costLimit: spec.cost_limit === null ? '' : String(spec.cost_limit).replace('.', ','),
    note: spec.note,
  }
}

/** Vergleichswert der Angaben; die Reihenfolge des Anklickens zählt nicht. */
function formKey(form: Form): string {
  return JSON.stringify({ ...form, taskIds: [...form.taskIds].sort(), modelIds: [...form.modelIds].sort(), levels: [...form.levels].sort() })
}

/** Denkstufen aus den Einstellungen: Text mit Kommas oder Liste; unbekannte Werte fallen heraus. */
function initialLevels(value: unknown, known: string[]): string[] {
  const items = Array.isArray(value) ? value.map((v) => String(v ?? '')) : String(value ?? '').split(',')
  const levels = items.map((v) => v.trim().toLowerCase()).filter((v) => known.includes(v))
  return levels.length ? [...new Set(levels)] : ['']
}

/** Kostenlimit aus dem Feld: leer = Vorgabe (null), sonst eine Zahl ab 0; auch mit Komma. */
function parseLimit(text: string): number | null | 'invalid' {
  const trimmed = text.trim()
  if (!trimmed) return null
  const value = Number(trimmed.replace(',', '.'))
  return Number.isFinite(value) && value >= 0 ? value : 'invalid'
}

function limitText(value: number | null | undefined): string {
  return value ? usd(value, 2) : tx.extra.noLimit
}

/** Preis je 1 Mio. Tokens; ein fehlender Preis erscheint nie als 0 $. */
function price(model: Model): string {
  if (model.price_in === null || model.price_in === undefined) return t.common.noPrice
  if (!model.price_in && !model.price_out) return tx.models.free
  return `${usd(model.price_in, 2)} / ${model.price_out === null || model.price_out === undefined ? t.common.none : usd(model.price_out, 2)}`
}
