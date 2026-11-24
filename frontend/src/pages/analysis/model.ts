// Datenformen und Hilfen der Auswertung (Vertrag: src/aiarena4bw/analysis.py).
import { num, usd } from '../../format'
import { t } from '../../texts'

export const LIST_KEYS = ['tasks', 'systems', 'batches', 'thinking', 'vendors', 'platforms', 'mcp', 'agents', 'models'] as const
export type ListKey = (typeof LIST_KEYS)[number]

export type Filters = Record<ListKey | 'excluded', string[]> & {
  include_hidden: boolean
  include_invalid: boolean
  only_platform: string
}

export const COLOR_KEYS = ['verify', 'vendor', 'platform', 'thinking', 'mcp', 'agent'] as const
export type ColorKey = (typeof COLOR_KEYS)[number]

export type ChartSettings = {
  x: string
  y: string
  size: string
  color: ColorKey
  level: 'run' | 'model'
  logX: boolean
  logY: boolean
  labels: boolean
  /** Nur im Vergleichsdiagramm: nur bestandene Läufe bzw. Mediane aus bestandenen Läufen. */
  onlyPassed: boolean
}

export type Settings = { filters: Filters; chart: ChartSettings }

export const DEFAULT_FILTERS: Filters = {
  tasks: [],
  systems: [],
  batches: [],
  thinking: [],
  vendors: [],
  platforms: [],
  mcp: [],
  agents: [],
  models: [],
  excluded: [],
  include_hidden: false,
  include_invalid: false,
  only_platform: '',
}

export const DEFAULT_CHART: ChartSettings = {
  x: 'seconds',
  y: 'cost',
  size: '',
  color: 'verify',
  level: 'run',
  logX: false,
  logY: false,
  labels: false,
  onlyPassed: false,
}

const strings = (value: unknown): string[] => (Array.isArray(value) ? value.filter((v) => typeof v === 'string') : [])
const text = (value: unknown, fallback: string): string => (typeof value === 'string' ? value : fallback)

/** Macht aus gespeicherten Einstellungen eine vollständige Ansicht; fehlende oder fremde Felder bekommen die Vorgabe. */
export function normalize(raw: unknown): Settings {
  const source = raw && typeof raw === 'object' ? (raw as Record<string, any>) : {}
  const f = source.filters && typeof source.filters === 'object' ? source.filters : {}
  const c = source.chart && typeof source.chart === 'object' ? source.chart : {}
  const filters = { ...DEFAULT_FILTERS }
  for (const key of [...LIST_KEYS, 'excluded'] as const) filters[key] = strings(f[key])
  filters.include_hidden = Boolean(f.include_hidden)
  filters.include_invalid = Boolean(f.include_invalid)
  filters.only_platform = text(f.only_platform, '')
  return {
    filters,
    chart: {
      x: text(c.x, DEFAULT_CHART.x) || DEFAULT_CHART.x,
      y: text(c.y, DEFAULT_CHART.y) || DEFAULT_CHART.y,
      size: text(c.size, ''),
      color: (COLOR_KEYS as readonly string[]).includes(c.color) ? c.color : DEFAULT_CHART.color,
      level: c.level === 'model' ? 'model' : 'run',
      logX: Boolean(c.logX),
      logY: Boolean(c.logY),
      labels: Boolean(c.labels),
      onlyPassed: Boolean(c.onlyPassed),
    },
  }
}

export function filtersActive(filters: Filters): boolean {
  return JSON.stringify(filters) !== JSON.stringify(DEFAULT_FILTERS)
}

export type Metric = { field: string; label: string; digits: number }

export type Run = {
  id: number
  run_code: string
  code: string
  label: string
  task: string
  vendor: string
  platform_name: string
  thinking_label: string
  mcp_server: string
  agent_label: string
  status: string
  verify_status: string
  started: string | null
  seconds: number | null
  steps: number | null
  tokens_input: number | null
  tokens_output: number | null
  cost: number | null
  cost_source: string | null
  valid: boolean
  invalid: string | null
  hidden: string | null
  retry_of: number | null
  [field: string]: any
}

export type Summary = {
  label: string
  model_id: string
  vendor: string
  platform_name: string
  thinking_label: string
  mcp_server: string
  agent_label: string
  runs: number
  verified: number
  passed: number
  pass_rate: number | null
  pass_percent: number | null
  seconds: number | null
  seconds_min: number | null
  seconds_max: number | null
  steps: number | null
  tokens_input: number | null
  tokens_new: number | null
  tokens_cache_read: number | null
  tokens_output: number | null
  price_known: boolean
  cost: number | null
  cost_per_pass: number | null
  cost_source: string | null
  [field: string]: any
}

export type AnalysisData = {
  runs: Run[]
  summary: Summary[]
  /** Wie summary, aber Mediane nur aus bestandenen Läufen; fehlt bei älterem Backend. */
  summary_passed?: Summary[]
  options: Record<ListKey | 'excluded', string[]>
  counts: { all: number; shown: number; invalid: number; hidden: number }
  metrics: Record<string, Metric>
  model_metrics: Record<string, Metric>
  platforms: { id: string; name: string }[]
}

export type View = { name: string; saved: string; is_default: boolean; settings: unknown }

/** Feld eines Laufs bzw. Eintrags und Auswahlliste der ungefilterten Ausprägungen je Farbmerkmal. */
export const COLOR_FIELDS: Record<Exclude<ColorKey, 'verify'>, { field: string; option: ListKey }> = {
  vendor: { field: 'vendor', option: 'vendors' },
  platform: { field: 'platform_name', option: 'platforms' },
  thinking: { field: 'thinking_label', option: 'thinking' },
  mcp: { field: 'mcp_server', option: 'mcp' },
  agent: { field: 'agent_label', option: 'agents' },
}

const MONEY = new Set(['cost', 'verify_cost', 'cost_per_pass'])

export function value(row: Record<string, any>, metric: Metric | undefined): number | null {
  if (!metric) return null
  const v = row[metric.field]
  return typeof v === 'number' && Number.isFinite(v) ? v : null
}

/** Kosten in Dollar; sehr kleine Beträge mit einer Stelle mehr, damit sie nicht zu 0,00x $ verschwimmen. */
export function money(v: number | null | undefined): string {
  return typeof v === 'number' && v !== 0 && Math.abs(v) < 0.01 ? usd(v, 4) : usd(v)
}

/** Kennzahl als Text: Kosten in Dollar, fehlender Preis nie als 0 $. */
export function metricText(key: string, metric: Metric, v: number | null): string {
  if (MONEY.has(key)) return v === null ? (key === 'cost' ? t.common.noPrice : t.common.none) : money(v)
  if (v === null) return t.common.none
  return num(v, Number.isInteger(v) ? metric.digits : Math.max(metric.digits, 1))
}

const axisFormat = new Intl.NumberFormat('de-DE', { maximumFractionDigits: 4 })

/** Achsenbeschriftung in deutscher Schreibweise, ohne überflüssige Nachkommastellen. */
export function axisNum(v: number): string {
  return axisFormat.format(v)
}

export function escapeHtml(value: unknown): string {
  return String(value ?? '').replace(/[&<>"']/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[ch] ?? ch)
}

/** Tooltip: Überschrift, optionale Unterzeile, dann Zeilen „Benennung – Wert“. */
export function tipHtml(title: string, sub: string | null, rows: [string, string][]): string {
  const lines = rows
    .map(
      ([label, v]) =>
        `<div style="display:flex;justify-content:space-between;gap:20px"><span style="opacity:.75">${escapeHtml(label)}</span><span style="font-variant-numeric:tabular-nums;white-space:nowrap">${escapeHtml(v)}</span></div>`,
    )
    .join('')
  return `<div style="font-weight:600">${escapeHtml(title)}</div>${sub ? `<div style="opacity:.75;margin-bottom:6px">${escapeHtml(sub)}</div>` : '<div style="height:6px"></div>'}${lines}`
}

/** Kreuz als Punktform für „nicht bestanden“. */
export const CROSS = 'path://M2,0 L5,3 L8,0 L10,2 L7,5 L10,8 L8,10 L5,7 L2,10 L0,8 L3,5 L0,2 Z'

/** Hohles Quadrat für „nicht bestanden“ und Rahmen mit Punkt für „ungeprüft“: dieselben Formen wie in der Formkurve. */
export const RING = 'path://M0,0 H10 V10 H0 Z M2,2 V8 H8 V2 Z'
export const FRAME_DOT = 'path://M0,0 H10 V10 H0 Z M1,1 V9 H9 V1 Z M5,3.2 A1.8,1.8 0 1 1 4.99,3.2 Z'

/** Je Ausprägung eine eigene Form, damit Reihen nicht nur an der Farbe hängen. */
export const SHAPES = [
  'circle',
  'rect',
  'triangle',
  'diamond',
  CROSS,
  'path://M4,0 H6 V4 H10 V6 H6 V10 H4 V6 H0 V4 H4 Z',
  'path://M0,0 H10 L5,10 Z',
  'path://M2.5,0 H7.5 L10,5 L7.5,10 H2.5 L0,5 Z',
]

export function verifyGroup(status: string | null | undefined): 'pass' | 'fail' | 'open' {
  return status === 'pass' ? 'pass' : status === 'fail' ? 'fail' : 'open'
}

export function costSourceText(source: string | null | undefined): string {
  if (!source) return t.common.none
  return source
    .split('/')
    .map((part) => t.common.costSource[part] ?? part)
    .join(' / ')
}

/** Speichert Text als Datei über einen unsichtbaren Verweis. */
export function saveText(content: string, fileName: string, mime: string): void {
  const url = URL.createObjectURL(new Blob([content], { type: mime }))
  const link = document.createElement('a')
  link.href = url
  link.download = fileName
  link.click()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}
