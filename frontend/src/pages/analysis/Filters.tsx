// Filterspalte der Auswertung: Ankreuzlisten mit der Zahl der Läufe je Wert; lange Listen als
// Auswahlfeld mit ausgeschriebenen gewählten Werten.
import { useMemo } from 'react'
import { t } from '../../texts'
import { Button, Field } from '../../ui'
import { DEFAULT_FILTERS, filtersActive, type AnalysisData, type Filters as FilterState, type ListKey, type Run } from './model'

const tx = t.analysis.filter

/** Feld eines Laufs je Filter (Vertrag: src/aiarena4bw/analysis.py). */
const FIELD: Record<ListKey, string> = {
  tasks: 'task',
  systems: 'bw_system',
  batches: 'code',
  thinking: 'thinking_label',
  vendors: 'vendor',
  platforms: 'platform_name',
  mcp: 'mcp_server',
  agents: 'agent_label',
  models: 'label',
}
/** Ab dieser Länge wird aus der Ankreuzliste ein Auswahlfeld. */
const LONG = 14

type Props = {
  data: AnalysisData | undefined
  /** Alle Läufe ohne Filter: Grundlage der Zahl je Wert, auch für gerade abgewählte Werte. */
  all: Run[] | undefined
  filters: FilterState
  onChange: (filters: FilterState) => void
}

export function Filters({ data, all, filters, onChange }: Props) {
  const options = data?.options
  const counts = data?.counts
  const set = (patch: Partial<FilterState>) => onChange({ ...filters, ...patch })
  // Gewählte Werte bleiben sichtbar, auch wenn ein Filter davor sie gerade ausschließt.
  const list = (key: ListKey) => [...new Set([...(options?.[key] ?? []), ...filters[key]])]

  // Zahl der Läufe je Wert: so viele blieben, wenn dieser Wert gewählt wäre und alle übrigen Filter gelten.
  // Mit der Einschränkung auf eine Plattform rechnet nur das Backend; dann zählen die gezeigten Läufe.
  const perValue = useMemo(() => {
    const keys = Object.keys(FIELD) as ListKey[]
    const result = {} as Record<ListKey, Map<string, number>>
    for (const key of keys) result[key] = new Map()
    const exact = Boolean(all) && !filters.only_platform
    for (const run of (exact ? all : data?.runs) ?? []) {
      if (exact && ((!filters.include_invalid && !run.valid) || (!filters.include_hidden && run.hidden) || filters.excluded.includes(run.label))) continue
      const fits = (key: ListKey) => filters[key].length === 0 || filters[key].includes(String(run[FIELD[key]] ?? ''))
      for (const key of keys) {
        if (exact && !keys.every((other) => other === key || fits(other))) continue
        const value = String(run[FIELD[key]] ?? '')
        result[key].set(value, (result[key].get(value) ?? 0) + 1)
      }
    }
    return result
  }, [all, data?.runs, filters])

  const facet = (key: ListKey, hint?: string) => {
    const values = list(key)
    if (values.length > LONG) {
      return <MultiPick label={tx[key]} hint={hint} options={options?.[key] ?? []} value={filters[key]} onChange={(v) => set({ [key]: v })} />
    }
    return <Facet label={tx[key]} options={values} chosen={filters[key]} counts={perValue[key]} onChange={(v) => set({ [key]: v })} />
  }

  return (
    <div className="facet-list">
      <div className="facet-list__head">
        <h2 className="section__title">{tx.title}</h2>
        <Button small disabled={!filtersActive(filters)} onClick={() => onChange({ ...DEFAULT_FILTERS })}>
          {tx.resetShort}
        </Button>
      </div>
      {facet('tasks')}
      {facet('systems')}
      {facet('batches')}
      {facet('thinking')}
      {facet('vendors')}
      {facet('platforms')}
      {facet('mcp')}
      {facet('agents')}
      {facet('models', tx.modelsHint)}

      <fieldset className="facet">
        <legend>{tx.validity}</legend>
        <label className="facet__row">
          <input type="checkbox" checked={filters.include_invalid} onChange={(e) => set({ include_invalid: e.target.checked })} />
          <span className="facet__name">{tx.includeInvalid}</span>
          <span className="facet__n">{counts?.invalid ?? ''}</span>
        </label>
        <label className="facet__row">
          <input type="checkbox" checked={filters.include_hidden} onChange={(e) => set({ include_hidden: e.target.checked })} />
          <span className="facet__name">{tx.includeHidden}</span>
          <span className="facet__n">{counts?.hidden ?? ''}</span>
        </label>
      </fieldset>

      <Field label={tx.onlyPlatform}>
        <select className="select" value={filters.only_platform} onChange={(e) => set({ only_platform: e.target.value })}>
          <option value="">{tx.onlyPlatformOff}</option>
          {(data?.platforms ?? []).map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
      </Field>

      {filters.excluded.length > 0 && <p className="secondary">{tx.excluded(filters.excluded.length)}</p>}
    </div>
  )
}

/** Ankreuzliste: Ohne eigene Auswahl zählen alle Werte, deshalb sind dann alle angekreuzt. */
function Facet(props: { label: string; options: string[]; chosen: string[]; counts: Map<string, number>; onChange: (value: string[]) => void }) {
  const { options, chosen } = props
  const all = chosen.length === 0
  const toggle = (value: string) => {
    const base = all ? options : chosen
    const next = base.includes(value) ? base.filter((v) => v !== value) : [...base, value]
    // Alles oder nichts angekreuzt heißt: kein Filter.
    props.onChange(next.length === 0 || options.every((o) => next.includes(o)) ? [] : next)
  }
  const short = options.length > 1 && options.every((o) => o.length <= 5)
  // Ein einziger Wert lässt nichts zu wählen: Benennung, Wert und Zahl stehen in einer Zeile.
  if (options.length === 1 && all) {
    return (
      <div className="facet facet--one">
        <span className="facet__title">{props.label}</span>
        <span className="facet__name" title={options[0]}>
          {options[0] || t.common.none}
        </span>
        <span className="facet__n">{props.counts.get(options[0]) ?? 0}</span>
      </div>
    )
  }
  return (
    <fieldset className="facet">
      <legend>{props.label}</legend>
      {options.length === 0 && <span className="secondary">{tx.noValues}</span>}
      <div className={short ? 'facet__two' : undefined}>
        {options.map((option) => (
          <div key={option} className="facet__row">
            <label>
              <input type="checkbox" checked={all || chosen.includes(option)} onChange={() => toggle(option)} />
              <span className="facet__name" title={option}>
                {option || t.common.none}
              </span>
            </label>
            {options.length > 1 && !short && (
              <button type="button" className="facet__only" aria-label={tx.onlyLabel(option)} onClick={() => props.onChange([option])}>
                {tx.only}
              </button>
            )}
            <span className="facet__n">{props.counts.get(option) ?? 0}</span>
          </div>
        ))}
      </div>
    </fieldset>
  )
}

/** Mehrfachauswahl für lange Listen: Auswahlfeld zum Hinzufügen, gewählte Werte ausgeschrieben und einzeln entfernbar. */
function MultiPick(props: { label: string; hint?: string; options: string[]; value: string[]; onChange: (value: string[]) => void }) {
  const open = props.options.filter((o) => !props.value.includes(o))
  const placeholder = open.length > 0 ? tx.add(props.label) : props.options.length > 0 ? tx.allChosen : tx.noValues
  return (
    <div className="field">
      <Field label={<strong className="facet__title">{props.label}</strong>} hint={props.hint}>
        <select
          className="select"
          value=""
          disabled={open.length === 0}
          onChange={(e) => e.target.value && props.onChange([...props.value, e.target.value])}
        >
          <option value="">{placeholder}</option>
          {open.map((o) => (
            <option key={o} value={o}>
              {o}
            </option>
          ))}
        </select>
      </Field>
      {props.value.length > 0 ? (
        <div className="picked">
          {props.value.map((v) => (
            <span key={v} className="tag picked__item">
              {v}
              <button type="button" aria-label={tx.remove(v)} title={tx.remove(v)} onClick={() => props.onChange(props.value.filter((x) => x !== v))}>
                <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden>
                  <path d="M1.5 1.5 L8.5 8.5 M8.5 1.5 L1.5 8.5" stroke="currentColor" strokeWidth="1.6" />
                </svg>
              </button>
            </span>
          ))}
        </div>
      ) : (
        <span className="secondary">{tx.noneChosen}</span>
      )}
    </div>
  )
}
