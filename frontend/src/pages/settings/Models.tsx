// Modelle einer Plattform: Vorauswahl, Suche und Filter, Preise, Kurztest.
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { memo, useCallback, useDeferredValue, useMemo, useState, type ChangeEvent, type FormEvent } from 'react'
import { api, errorText } from '../../api'
import { dateTime, day, num, tokens } from '../../format'
import { t } from '../../texts'
import { Button, Check, Chips, Empty, ErrorNote, Field, Glyph, Loading, Notice, Tag, useSort, useToast } from '../../ui'
import { Confirm, FormFoot, Modal, useRefresh, type Model, type Platform, type Quicktest } from './shared'

const tx = t.settings.models
/** So viele Zeilen zeigt die Tabelle zunächst; weitere kommen auf Wunsch dazu. */
const PAGE = 60
const VENDORS_SHOWN = 12
const NEW_DAYS = 30

type Props = { platform: Platform; onCatalog: () => void; catalogBusy: boolean }

export default function Models({ platform, onCatalog, catalogBusy }: Props) {
  const toast = useToast()
  const refresh = useRefresh()
  const client = useQueryClient()
  const key = useMemo(() => ['platform-models', platform.id], [platform.id])
  const url = `/platforms/${encodeURIComponent(platform.id)}`
  const models = useQuery<Model[]>({ queryKey: key, queryFn: () => api.get(`${url}/models`) })

  const [search, setSearch] = useState('')
  const [vendors, setVendors] = useState<string[]>([])
  const [allVendors, setAllVendors] = useState(false)
  const [onlyNew, setOnlyNew] = useState(false)
  const [onlySelected, setOnlySelected] = useState(false)
  const [limit, setLimit] = useState(PAGE)
  const [editing, setEditing] = useState<Model | null>(null)
  const [removing, setRemoving] = useState<Model | null>(null)
  const [adding, setAdding] = useState(false)
  const [asking, setAsking] = useState<'clear' | 'all' | null>(null)
  const needle = useDeferredValue(search).trim().toLowerCase()

  const all = useMemo(() => models.data ?? [], [models.data])
  const fresh = useMemo(() => newIds(all), [all])
  const vendorOptions = useMemo(() => {
    const counts = new Map<string, { label: string; count: number }>()
    for (const model of all) {
      const entry = counts.get(model.vendor) ?? { label: model.vendor_name, count: 0 }
      entry.count += 1
      counts.set(model.vendor, entry)
    }
    return [...counts.entries()].sort((a, b) => b[1].count - a[1].count || a[1].label.localeCompare(b[1].label, 'de')).map(([value, entry]) => ({ value, label: `${entry.label} · ${entry.count}` }))
  }, [all])
  const filtered = useMemo(
    () =>
      all.filter(
        (model) =>
          (!needle || model.name.toLowerCase().includes(needle) || model.model_id.toLowerCase().includes(needle)) &&
          (vendors.length === 0 || vendors.includes(model.vendor)) &&
          (!onlyNew || fresh.has(model.id)) &&
          (!onlySelected || model.selected),
      ),
    [all, needle, vendors, onlyNew, onlySelected, fresh],
  )
  const { sorted, toggle: sortBy, mark } = useSort<Model>(filtered, { key: 'vendor_name', dir: 'asc' })
  const shown = sorted.slice(0, limit)
  const selectedCount = all.reduce((sum, model) => sum + (model.selected ? 1 : 0), 0)
  /** Jede Filteränderung beginnt wieder mit der ersten Seite. */
  const filter = <T,>(apply: (value: T) => void) => (value: T) => {
    apply(value)
    setLimit(PAGE)
  }

  const select = useMutation({
    mutationFn: (change: { id: string; selected: boolean }) => api.patch('/model', change),
    onMutate: async (change) => {
      await client.cancelQueries({ queryKey: key })
      client.setQueryData<Model[]>(key, (old) => old?.map((model) => (model.id === change.id ? { ...model, selected: change.selected } : model)))
    },
    onSuccess: () => refresh('platforms', 'models'),
    onError: (error) => {
      toast(errorText(error), true)
      refresh('platform-models', 'platforms', 'models')
    },
  })
  const selection = useMutation({
    mutationFn: (body: { select_all: boolean; selected?: string[] }) => api.put(`${url}/selection`, body),
    onSuccess: (_data, body) => {
      toast(body.selected ? tx.cleared : body.select_all ? tx.selectAllOn : tx.selectAllOff)
      refresh('platform-models', 'platforms', 'models')
    },
    onError: (error) => toast(errorText(error), true),
    onSettled: () => setAsking(null),
  })
  const remove = useMutation({
    mutationFn: (model: Model) => api.post('/model/delete', { id: model.id }),
    onSuccess: async (_data, model) => {
      // Die Antwort sagt nicht, ob gelöscht oder nur abgewählt wurde: an der neuen Liste ablesen.
      await client.invalidateQueries({ queryKey: key })
      const kept = client.getQueryData<Model[]>(key)?.some((m) => m.id === model.id)
      toast(kept ? tx.removedKept(model.name) : tx.removedDeleted(model.name))
      refresh('platforms', 'models')
    },
    onError: (error) => toast(errorText(error), true),
    onSettled: () => setRemoving(null),
  })
  const { mutate: mutateSelected } = select
  const toggleSelected = useCallback((id: string, selected: boolean) => mutateSelected({ id, selected }), [mutateSelected])

  /** „Alle“ überschreibt eine von Hand getroffene Auswahl: dann erst nachfragen. */
  const chooseAll = (value: boolean) => {
    if (value && selectedCount > 0 && selectedCount < all.length) setAsking('all')
    else selection.mutate({ select_all: value })
  }

  if (models.isLoading) return <Loading />
  if (!models.data) return <ErrorNote error={models.error} />

  const addButton = <Button onClick={() => setAdding(true)}>{tx.add}</Button>
  const visibleVendors = allVendors ? vendorOptions : vendorOptions.filter((option, index) => index < VENDORS_SHOWN || vendors.includes(option.value))
  return (
    <div className="stack">
      {all.length === 0 ? (
        <Empty
          title={tx.emptyTitle}
          action={
            <div className="row">
              <Button variant="primary" busy={catalogBusy} onClick={onCatalog}>
                {t.settings.platforms.catalog}
              </Button>
              {addButton}
            </div>
          }
        >
          {tx.emptyText}
        </Empty>
      ) : (
        <>
          <div className="panel stack">
            <div className="row row--between">
              <div className="row">
                <strong>{tx.selectedCount(selectedCount, all.length)}</strong>
                <Check checked={!!platform.options.select_all} disabled={selection.isPending} onChange={chooseAll}>
                  {tx.selectAll}
                </Check>
              </div>
              <div className="row">
                <Button small disabled={selectedCount === 0} onClick={() => setAsking('clear')}>
                  {tx.clear}
                </Button>
                {addButton}
              </div>
            </div>
            <div className="row">
              <input
                className="input settings-search"
                type="search"
                aria-label={tx.search}
                placeholder={tx.search}
                value={search}
                onChange={(event) => filter(setSearch)(event.target.value)}
              />
              <Check checked={onlyNew} onChange={filter(setOnlyNew)}>
                <span title={tx.onlyNewHint}>{tx.onlyNew(NEW_DAYS, fresh.size)}</span>
              </Check>
              <Check checked={onlySelected} onChange={filter(setOnlySelected)}>
                {tx.onlySelected}
              </Check>
            </div>
            {vendorOptions.length > 1 && (
              <div className="row">
                <Chips options={visibleVendors} value={vendors} onChange={filter(setVendors)} ariaLabel={tx.vendors} />
                {vendorOptions.length > VENDORS_SHOWN && (
                  <Button small variant="quiet" onClick={() => setAllVendors(!allVendors)}>
                    {allVendors ? tx.vendorsLess : tx.vendorsMore(vendorOptions.length)}
                  </Button>
                )}
              </div>
            )}
          </div>

          <p className="muted small">{tx.priceNote}</p>
          {sorted.length === 0 ? (
            <p className="muted">{tx.noMatch}</p>
          ) : (
            <div className="table-wrap">
              <table className="table settings-models">
                <thead>
                  <tr>
                    <th>
                      <button type="button" onClick={() => sortBy('selected')}>
                        {tx.col.selected}
                        {mark('selected')}
                      </button>
                    </th>
                    <th>
                      <button type="button" onClick={() => sortBy('name')}>
                        {tx.col.model}
                        {mark('name')}
                      </button>
                    </th>
                    <th>
                      <button type="button" onClick={() => sortBy('vendor_name')}>
                        {tx.col.vendor}
                        {mark('vendor_name')}
                      </button>
                    </th>
                    <th className="right">
                      <button type="button" onClick={() => sortBy('context_window')}>
                        {tx.col.context}
                        {mark('context_window')}
                      </button>
                    </th>
                    <th className="right">
                      <button type="button" onClick={() => sortBy('price_in')}>
                        {tx.col.priceIn}
                        {mark('price_in')}
                      </button>
                    </th>
                    <th className="right">
                      <button type="button" onClick={() => sortBy('price_out')}>
                        {tx.col.priceOut}
                        {mark('price_out')}
                      </button>
                    </th>
                    <th className="right">{tx.col.cache}</th>
                    <th className="right">{tx.col.maxTools}</th>
                    <th>{tx.col.quicktest}</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {shown.map((model) => (
                    <ModelRow key={model.id} model={model} isNew={fresh.has(model.id)} onToggle={toggleSelected} onEdit={setEditing} onRemove={setRemoving} />
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {sorted.length > 0 && (
            <div className="row">
              <span className="muted small">{tx.shownCount(shown.length, sorted.length, all.length)}</span>
              {sorted.length > shown.length && (
                <>
                  <Button small onClick={() => setLimit(limit + PAGE)}>
                    {tx.more(Math.min(PAGE, sorted.length - shown.length))}
                  </Button>
                  <Button small variant="quiet" onClick={() => setLimit(sorted.length)}>
                    {tx.showAll(sorted.length)}
                  </Button>
                </>
              )}
            </div>
          )}
        </>
      )}

      {adding && <AddDialog platform={platform} onClose={() => setAdding(false)} />}
      {editing && <ModelDialog model={editing} onClose={() => setEditing(null)} />}
      {removing && (
        <Confirm title={tx.removeTitle(removing.name)} action={tx.removeAction} danger busy={remove.isPending} onConfirm={() => remove.mutate(removing)} onClose={() => setRemoving(null)}>
          <p className="mono">{removing.id}</p>
          <p>{tx.removeText}</p>
        </Confirm>
      )}
      {asking === 'clear' && (
        <Confirm
          title={tx.clearTitle(platform.name)}
          action={tx.clearAction(selectedCount)}
          danger
          busy={selection.isPending}
          onConfirm={() => selection.mutate({ select_all: false, selected: [] })}
          onClose={() => setAsking(null)}
        >
          <p>{tx.clearText}</p>
        </Confirm>
      )}
      {asking === 'all' && (
        <Confirm
          title={tx.allTitle(platform.name)}
          action={tx.allAction(all.length)}
          busy={selection.isPending}
          onConfirm={() => selection.mutate({ select_all: true })}
          onClose={() => setAsking(null)}
        >
          <p>{tx.allText(selectedCount)}</p>
        </Confirm>
      )}
    </div>
  )
}

/** „Neu“: in den letzten 30 Tagen erschienen; ohne Erscheinungsdatum zählt, wann das Modell
    im Katalog auftauchte – außer beim allerersten Abruf, der sonst alles als neu zeigte. */
function newIds(models: Model[]): Set<string> {
  const since = Date.now() - NEW_DAYS * 86_400_000
  const stamps = models.map((model) => model.first_seen).filter((value): value is string => !!value)
  const firstFetch = stamps.length ? stamps.reduce((a, b) => (a < b ? a : b)) : null
  const out = new Set<string>()
  for (const model of models) {
    const date = model.released ?? (model.first_seen && model.first_seen !== firstFetch ? model.first_seen : null)
    if (date && new Date(date).getTime() >= since) out.add(model.id)
  }
  return out
}

// --------------------------------------------------------------------------- Zeile

type RowProps = {
  model: Model
  isNew: boolean
  onToggle: (id: string, selected: boolean) => void
  onEdit: (model: Model) => void
  onRemove: (model: Model) => void
}

const ModelRow = memo(function ModelRow({ model, isNew, onToggle, onEdit, onRemove }: RowProps) {
  const toast = useToast()
  const refresh = useRefresh()
  const quick = useMutation({
    mutationFn: () => api.post<Quicktest>('/model/quicktest', { id: model.id }),
    onSuccess: (result) => toast(result.ok ? tx.quick.done(model.name) : tx.quick.failed(model.name, result.message), !result.ok),
    onError: (error) => toast(errorText(error), true),
    onSettled: () => refresh('platform-models', 'models'),
  })
  const test = model.quicktest
  const noCache = model.price_cache_read === null && model.price_cache_write === null
  return (
    <tr className={model.selected ? '' : 'is-dim'}>
      <td>
        <input
          type="checkbox"
          className="settings-box"
          aria-label={tx.selectLabel(model.name)}
          checked={model.selected}
          onChange={(event) => onToggle(model.id, event.target.checked)}
        />
      </td>
      <td>
        <div className="row settings-name">
          <strong>{model.name}</strong>
          {isNew && <Tag title={model.released ? tx.tag.released(day(model.released)) : undefined}>{tx.tag.new}</Tag>}
          {model.manual && <Tag>{tx.tag.manual}</Tag>}
          {!model.in_catalog && !model.manual && <Tag title={tx.tag.goneHint}>{tx.tag.gone}</Tag>}
        </div>
        <div className="muted mono">{model.model_id}</div>
        {model.note && <div className="muted">{model.note}</div>}
      </td>
      <td>{model.vendor_name}</td>
      <td className="right num">{tokens(model.context_window)}</td>
      <td className="right num">
        <Price value={model.price_in} />
      </td>
      <td className="right num">
        <Price value={model.price_out} />
        {model.price_edited && <div className="muted">{tx.priceEdited}</div>}
      </td>
      <td className="right num">
        {noCache ? (
          <Price value={null} />
        ) : (
          <>
            <Price value={model.price_cache_read} /> · <Price value={model.price_cache_write} />
          </>
        )}
      </td>
      <td className="right num">{model.max_tools === null ? t.common.none : num(model.max_tools)}</td>
      <td>
        {quick.isPending ? (
          <span className="state state--live">
            <Glyph kind="live" />
            {tx.quick.running}
          </span>
        ) : test ? (
          <>
            <span className={`state state--${test.ok ? 'pass' : 'fail'}`} title={test.message}>
              <Glyph kind={test.ok ? 'pass' : 'fail'} />
              {test.ok ? tx.quick.ok : tx.quick.fail}
            </span>
            <div className="muted num">{dateTime(test.at)}</div>
          </>
        ) : (
          <span className="muted">{tx.quick.none}</span>
        )}
      </td>
      <td>
        <div className="row settings-actions">
          <Button small variant="quiet" disabled={quick.isPending} onClick={() => quick.mutate()}>
            {tx.quick.run}
          </Button>
          <Button small variant="quiet" onClick={() => onEdit(model)}>
            {t.common.actions.edit}
          </Button>
          <Button small variant="quiet" onClick={() => onRemove(model)}>
            {tx.remove}
          </Button>
        </div>
      </td>
    </tr>
  )
})

// Preise je 1 Mio. Tokens reichen von Bruchteilen eines Cents bis zu zweistelligen Dollarbeträgen.
const priceFormat = new Intl.NumberFormat('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 4 })

/** Ein fehlender Preis erscheint nie als 0 $. */
function Price({ value }: { value: number | null }) {
  return value === null ? <span className="muted">{t.common.noPrice}</span> : <>{priceFormat.format(value)} $</>
}

// --------------------------------------------------------------------------- Dialoge

const PRICE_KEYS = ['price_in', 'price_out', 'price_cache_read', 'price_cache_write'] as const
type EditKey = 'name' | 'note' | 'max_tools' | (typeof PRICE_KEYS)[number]

const asText = (value: number | string | null) => (value === null ? '' : String(value).replace('.', ','))

function ModelDialog({ model, onClose }: { model: Model; onClose: () => void }) {
  const toast = useToast()
  const refresh = useRefresh()
  const initial: Record<EditKey, string> = {
    name: model.name,
    note: model.note,
    max_tools: asText(model.max_tools),
    price_in: asText(model.price_in),
    price_out: asText(model.price_out),
    price_cache_read: asText(model.price_cache_read),
    price_cache_write: asText(model.price_cache_write),
  }
  const [form, setForm] = useState(initial)
  const bind = (key: EditKey) => ({
    value: form[key],
    onChange: (event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setForm((current) => ({ ...current, [key]: event.target.value })),
  })
  // Nur Geändertes senden: Jeder gesendete Preis gilt dem Backend als von Hand gepflegt.
  const changed = (Object.keys(initial) as EditKey[]).filter((key) => form[key].trim() !== initial[key].trim())

  const save = useMutation({
    mutationFn: () => api.patch<Model>('/model', { id: model.id, ...Object.fromEntries(changed.map((key) => [key, form[key].trim()])) }),
    onSuccess: (saved) => {
      toast(tx.saved(saved.name))
      refresh('platform-models', 'models')
      onClose()
    },
  })
  const submit = (event: FormEvent) => {
    event.preventDefault()
    if (changed.length === 0) onClose()
    else save.mutate()
  }

  return (
    <Modal title={tx.editTitle(model.name)} onClose={onClose}>
      <form className="stack" onSubmit={submit} autoComplete="off">
        <p className="muted mono">{model.id}</p>
        <div className="form-grid">
          <Field label={tx.field.name} wide>
            <input className="input" {...bind('name')} placeholder={model.model_id} />
          </Field>
          {PRICE_KEYS.map((key) => (
            <Field key={key} label={tx.field[key]}>
              <input className="input num" {...bind(key)} inputMode="decimal" placeholder={t.common.noPrice} />
            </Field>
          ))}
          <p className="field--wide field__hint">{model.price_edited ? tx.field.priceEdited : tx.field.priceHint}</p>
          <Field label={tx.field.max_tools} hint={tx.field.maxToolsHint}>
            <input className="input num" {...bind('max_tools')} inputMode="numeric" placeholder={tx.field.maxToolsNone} />
          </Field>
          <Field label={tx.field.note} wide>
            <textarea className="textarea" rows={2} {...bind('note')} />
          </Field>
        </div>
        {model.quicktest && (
          <Notice kind={model.quicktest.ok ? 'ok' : 'warn'}>
            {tx.quick.last(dateTime(model.quicktest.at))}: {model.quicktest.message}
          </Notice>
        )}
        {save.error && <Notice kind="error">{errorText(save.error)}</Notice>}
        <FormFoot action={tx.save} busy={save.isPending} onCancel={onClose} />
      </form>
    </Modal>
  )
}

function AddDialog({ platform, onClose }: { platform: Platform; onClose: () => void }) {
  const toast = useToast()
  const refresh = useRefresh()
  const [modelId, setModelId] = useState('')
  const [name, setName] = useState('')
  const save = useMutation({
    mutationFn: () => api.post<Model>(`/platforms/${encodeURIComponent(platform.id)}/models`, { model_id: modelId.trim(), name: name.trim() }),
    onSuccess: (saved) => {
      toast(tx.added(saved.name))
      refresh('platform-models', 'platforms', 'models')
      onClose()
    },
  })
  const submit = (event: FormEvent) => {
    event.preventDefault()
    save.mutate()
  }
  return (
    <Modal title={tx.addTitle(platform.name)} onClose={onClose}>
      <form className="stack" onSubmit={submit} autoComplete="off">
        <p className="secondary">{tx.addText}</p>
        <Field label={tx.field.modelId} hint={tx.field.modelIdHint(`${platform.id}:${modelId.trim() || tx.field.modelIdSample}`)}>
          <input className="input mono" value={modelId} onChange={(event) => setModelId(event.target.value)} required spellCheck={false} placeholder={tx.field.modelIdSample} />
        </Field>
        <Field label={tx.field.nameOptional}>
          <input className="input" value={name} onChange={(event) => setName(event.target.value)} />
        </Field>
        {save.error && <Notice kind="error">{errorText(save.error)}</Notice>}
        <FormFoot action={tx.addAction} busy={save.isPending} onCancel={onClose} />
      </form>
    </Modal>
  )
}
