// Vergleichsdiagramm: Streudiagramm mit frei wählbaren Achsen, je Lauf oder je Modell.
// Links die Steuerspalte, rechts das Diagramm über die volle Breite.
import type { EChartsOption } from 'echarts'
import { useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { num } from '../../format'
import { t } from '../../texts'
import { Button, Check, Chips, Field, Glyph } from '../../ui'
import { baseOption, categoryColor, Chart, useChartColors, type ChartColors, type ChartHandle } from '../../ui/Chart'
import {
  axisNum,
  COLOR_FIELDS,
  COLOR_KEYS,
  DEFAULT_CHART,
  FRAME_DOT,
  metricText,
  RING,
  SHAPES,
  tipHtml,
  value,
  verifyGroup,
  type AnalysisData,
  type ChartSettings,
  type ColorKey,
  type ListKey,
  type Metric,
} from './model'

const tx = t.analysis.compare

type Props = {
  data: AnalysisData
  /** Ungefilterte Ausprägungen je Merkmal, in fester Reihenfolge: Grundlage der Farben. */
  categories: Record<ListKey, string[]> | undefined
  chart: ChartSettings
  onChart: (chart: ChartSettings) => void
  /** Markierter Eintrag: bleibt in Diagramm, Tabelle und den Diagrammen je Modell gelb hervorgehoben. */
  selected: string | null
  onSelect: (label: string) => void
}

// Form der Punkte je Prüfurteil, wie in der Formkurve: gefüllt, hohl, Rahmen mit Punkt.
const SYMBOL = { pass: 'rect', fail: RING, open: FRAME_DOT } as const
export function Compare({ data, categories, chart, onChart, selected, onSelect }: Props) {
  const navigate = useNavigate()
  const colors = useChartColors()
  const ref = useRef<ChartHandle>(null)
  const [zoomEpoch, setZoomEpoch] = useState(0)
  const set = (patch: Partial<ChartSettings>) => onChart({ ...chart, ...patch })

  const metrics = useMemo<Record<string, Metric>>(
    () => (chart.level === 'model' ? { ...data.metrics, ...data.model_metrics } : data.metrics),
    [chart.level, data.metrics, data.model_metrics],
  )
  const keys = Object.keys(metrics)
  const xKey = metrics[chart.x] ? chart.x : metrics[DEFAULT_CHART.x] ? DEFAULT_CHART.x : keys[0]
  const yKey = metrics[chart.y] ? chart.y : metrics[DEFAULT_CHART.y] ? DEFAULT_CHART.y : keys[0]
  const sizeKey = metrics[chart.size] ? chart.size : ''
  // Je Modell gibt es kein einzelnes Prüfergebnis: dann färbt der Anbieter.
  const colorKey: ColorKey = chart.level === 'model' && chart.color === 'verify' ? 'vendor' : chart.color
  const colorKeys = COLOR_KEYS.filter((k) => chart.level === 'run' || k !== 'verify')

  const built = useMemo(
    () => build({ data, categories, metrics, xKey, yKey, sizeKey, colorKey, chart, colors, selected }),
    [data, categories, metrics, xKey, yKey, sizeKey, colorKey, chart, colors, selected],
  )

  const onClick = (params: any) => {
    const row = params?.data?.row
    if (!row) return
    if (chart.level === 'run') navigate(`/lauf/${row.id}`)
    else onSelect(row.label)
  }

  const missingMetrics = [...new Set([metrics[xKey]?.label, metrics[yKey]?.label])].filter(Boolean).join(' / ')

  return (
    <div className="panel panel--flush cmp">
      <div className="cmp__ctl">
        <h2 className="section__title">{tx.title}</h2>
        <Chips
          options={[
            { value: 'run', label: tx.levelRun },
            { value: 'model', label: tx.levelModel },
          ]}
          value={[chart.level]}
          onChange={(v) => v.length > 0 && set({ level: v[v.length - 1] as ChartSettings['level'] })}
          ariaLabel={tx.level}
        />
        <Field label={tx.x}>
          <MetricSelect metrics={metrics} value={xKey} onChange={(x) => set({ x })} />
        </Field>
        <Field label={tx.y}>
          <MetricSelect metrics={metrics} value={yKey} onChange={(y) => set({ y })} />
        </Field>
        <Field label={tx.size}>
          <MetricSelect metrics={metrics} value={sizeKey} onChange={(size) => set({ size })} empty={tx.sizeNone} />
        </Field>
        <Field label={tx.color}>
          <select className="select" value={colorKey} onChange={(e) => set({ color: e.target.value as ColorKey })}>
            {colorKeys.map((k) => (
              <option key={k} value={k}>
                {tx.colors[k]}
              </option>
            ))}
          </select>
        </Field>
        <Check checked={chart.logX} onChange={(logX) => set({ logX })}>
          {tx.logX}
        </Check>
        <Check checked={chart.logY} onChange={(logY) => set({ logY })}>
          {tx.logY}
        </Check>
        <Check checked={chart.labels} onChange={(labels) => set({ labels })}>
          {tx.labels}
        </Check>
        <span title={tx.onlyPassedHint}>
          <Check checked={chart.onlyPassed} onChange={(onlyPassed) => set({ onlyPassed })}>
            {tx.onlyPassed}
          </Check>
        </span>
      </div>
      <div className="cmp__main">
        {/* Der Schlüssel baut das Diagramm neu auf und setzt so den Zoom zurück. */}
        <Chart key={zoomEpoch} ref={ref} option={built.option} height={340} onClick={onClick} ariaLabel={tx.aria(metrics[xKey]?.label ?? '', metrics[yKey]?.label ?? '')} />
        <div className="cmp__foot">
          <div className="cmp__notes">
            {chart.level === 'run' && (
              <span className="row" style={{ gap: 12 }}>
                <span className="state state--pass">
                  <Glyph kind="pass" /> {tx.passed}
                </span>
                <span className="state state--fail">
                  <Glyph kind="fail" /> {tx.failed}
                </span>
                <span className="state state--neutral">
                  <Glyph kind="open" /> {tx.unverified}
                </span>
              </span>
            )}
            {chart.onlyPassed && <span>{chart.level === 'run' ? tx.onlyPassedRun : tx.onlyPassedModel}</span>}
            <span className="secondary">
              {built.drawn === 0 ? (chart.onlyPassed ? tx.noPassedPoints : tx.noPoints) : tx.drawn(built.drawn, chart.level)}
              {built.missing > 0 && ` ${tx.missing(built.missing, chart.level, missingMetrics)}`}
              {built.notPositive > 0 && ` ${tx.notPositive(built.notPositive)}`} {chart.labels && built.drawn > 1 && `${tx.labelsNote} `}
              {tx.note(chart.level)}
            </span>
          </div>
          <Button small onClick={() => setZoomEpoch((n) => n + 1)}>
            {tx.resetZoom}
          </Button>
          <Button small onClick={() => ref.current?.download(tx.fileName)}>
            {tx.save}
          </Button>
        </div>
      </div>
    </div>
  )
}

function MetricSelect(props: { metrics: Record<string, Metric>; value: string; onChange: (key: string) => void; empty?: string }) {
  return (
    <select className="select" value={props.value} onChange={(e) => props.onChange(e.target.value)}>
      {props.empty !== undefined && <option value="">{props.empty}</option>}
      {Object.entries(props.metrics).map(([key, metric]) => (
        <option key={key} value={key}>
          {metric.label}
        </option>
      ))}
    </select>
  )
}

type BuildInput = {
  data: AnalysisData
  categories: Record<ListKey, string[]> | undefined
  metrics: Record<string, Metric>
  xKey: string
  yKey: string
  sizeKey: string
  colorKey: ColorKey
  chart: ChartSettings
  colors: ChartColors
  selected?: string | null
}

type Group = { name: string; color: string; icon: string; items: any[] }

export function build(input: BuildInput): { option: EChartsOption; drawn: number; missing: number; notPositive: number } {
  const { data, metrics, xKey, yKey, sizeKey, colorKey, chart, colors } = input
  const base = baseOption(colors) as any
  const isRun = chart.level === 'run'
  // „Nur bestandene Läufe“ wirkt allein hier: je Lauf gefiltert, je Modell Mediane aus bestandenen Läufen.
  const rows: Record<string, any>[] = isRun
    ? chart.onlyPassed
      ? data.runs.filter((r) => r.passed === true)
      : data.runs
    : chart.onlyPassed
      ? (data.summary_passed ?? [])
      : data.summary
  const mx = metrics[xKey]
  const my = metrics[yKey]
  const ms = sizeKey ? metrics[sizeKey] : undefined

  // Feste Reihenfolge der Serien: folgt dem Namen der Ausprägung, nicht den gerade gezeigten Daten.
  const groups = new Map<string, Group>()
  if (colorKey === 'verify') {
    groups.set('pass', { name: tx.passed, color: colors.pass, icon: SYMBOL.pass, items: [] })
    groups.set('fail', { name: tx.failed, color: colors.fail, icon: SYMBOL.fail, items: [] })
    groups.set('open', { name: tx.unverified, color: colors.neutral, icon: SYMBOL.open, items: [] })
  } else {
    const { option } = COLOR_FIELDS[colorKey]
    const known = input.categories?.[option] ?? data.options[option] ?? []
    known.slice(0, colors.series.length).forEach((name, index) => {
      groups.set(name, { name, color: categoryColor(colors, known, name), icon: SHAPES[index % SHAPES.length], items: [] })
    })
    groups.set('', { name: tx.other, color: colors.other, icon: 'circle', items: [] })
  }

  const sizes = ms ? rows.map((r) => value(r, ms)).filter((v): v is number => v !== null) : []
  const sizeMin = sizes.length ? Math.min(...sizes) : 0
  const sizeMax = sizes.length ? Math.max(...sizes) : 0
  const plain = isRun ? 10 : 13
  const sizeOf = (row: Record<string, any>) => {
    if (!ms) return plain
    const v = value(row, ms)
    if (v === null || sizeMax <= sizeMin) return v === null ? 8 : plain
    return 8 + 22 * Math.sqrt((v - sizeMin) / (sizeMax - sizeMin))
  }

  let missing = 0
  let notPositive = 0
  let drawn = 0
  const halo: any[] = []
  const top: any[] = []
  for (const row of rows) {
    const x = value(row, mx)
    const y = value(row, my)
    if (x === null || y === null) {
      missing += 1 // kein Wert, z. B. Kosten ohne Preis: weglassen, nie als 0 zeichnen
      continue
    }
    if ((chart.logX && x <= 0) || (chart.logY && y <= 0)) {
      notPositive += 1
      continue
    }
    const verdict = verifyGroup(row.verify_status)
    let group: Group | undefined
    if (colorKey === 'verify') group = groups.get(verdict)
    else group = groups.get(String(row[COLOR_FIELDS[colorKey].field] ?? '')) ?? groups.get('')
    if (!group) continue
    drawn += 1
    const marked = Boolean(input.selected) && row.label === input.selected
    const item: any = {
      value: [x, y],
      name: isRun ? `${row.run_code} ${row.label}` : row.label,
      symbol: isRun ? SYMBOL[verdict] : group.icon,
      symbolSize: sizeOf(row),
      row,
    }
    if (marked) {
      halo.push({ value: [x, y], symbolSize: item.symbolSize + 12, name: row.label })
      // Der markierte Punkt wird über allen anderen noch einmal gezeichnet, damit ihn nichts verdeckt.
      top.push({ ...item, itemStyle: { color: group.color } })
      // Die Beschriftung des markierten Eintrags trägt der gelbe Hof: Sie steht immer, auch wenn die
      // Beschriftung sonst aus ist, und weicht keiner anderen.
      if (!isRun) item.label = { show: false }
    }
    group.items.push(item)
  }

  const shown = [...groups.values()].filter((g) => g.items.length > 0)

  // Punkte im rechten Viertel tragen ihre Beschriftung über sich, damit sie nicht am Rand abgeschnitten wird.
  const scale = (v: number) => (chart.logX ? Math.log10(v) : v)
  const xs = shown.flatMap((g) => g.items.map((i) => scale(i.value[0])))
  const xMin = Math.min(...xs)
  const xMax = Math.max(...xs)
  if (xMax > xMin) {
    for (const g of shown) {
      for (const item of g.items) {
        if ((scale(item.value[0]) - xMin) / (xMax - xMin) > 0.76) item.label = { ...item.label, position: 'top' }
      }
    }
  }
  // Punkte dicht links neben dem markierten Eintrag tragen ihre Beschriftung links, damit sie nicht
  // unter dessen gelbem Hof verschwindet.
  if (!isRun && halo.length === 1 && xMax > xMin) {
    const scaleY = (v: number) => (chart.logY ? Math.log10(v) : v)
    const ys = shown.flatMap((g) => g.items.map((i) => scaleY(i.value[1])))
    const ySpan = Math.max(...ys) - Math.min(...ys) || 1
    const [sx, sy] = [scale(halo[0].value[0]), scaleY(halo[0].value[1])]
    for (const g of shown) {
      for (const item of g.items) {
        const dx = (sx - scale(item.value[0])) / (xMax - xMin)
        if (dx > 0 && dx < 0.22 && Math.abs(sy - scaleY(item.value[1])) / ySpan < 0.08) item.label = { ...item.label, position: 'left' }
      }
    }
  }

  const tooltip = (params: any) => {
    const row = params?.data?.row
    if (!row) return ''
    const lines: [string, string][] = Object.entries(metrics).map(([key, metric]) => [metric.label, metricText(key, metric, value(row, metric))])
    if (isRun) {
      const head: [string, string][] = [
        [tx.tipTask, row.task],
        [tx.tipVerdict, t.common.verify[row.verify_status] ?? row.verify_status],
      ]
      if (row.invalid) head.push([tx.tipInvalid, row.invalid])
      return tipHtml(`${row.run_code} · ${row.label}`, `${row.vendor} · ${row.platform_name}`, [...head, ...lines])
    }
    return tipHtml(row.label, `${row.vendor} · ${row.platform_name} · ${chart.onlyPassed ? tx.tipMedianPassed : tx.tipMedian}`, [
      [tx.tipRuns, num(row.runs)],
      [tx.tipPassed, `${row.passed} / ${row.verified}`],
      ...lines,
    ])
  }

  const axis = (metric: Metric | undefined, log: boolean) => ({
    type: log ? 'log' : 'value',
    scale: true,
    name: metric?.label ?? '',
    axisLabel: { ...base.xAxis.axisLabel, formatter: (v: number) => axisNum(v) },
    minorSplitLine: { show: false },
  })

  const option: any = {
    ...base,
    grid: { left: 12, right: 72, top: 58, bottom: 30, containLabel: true },
    tooltip: { ...base.tooltip, trigger: 'item', formatter: tooltip },
    legend: {
      ...base.legend,
      type: 'scroll',
      top: 0,
      left: 0,
      right: 0,
      pageTextStyle: { color: colors.text2 },
      pageIconColor: colors.text2,
      pageIconInactiveColor: colors.text3,
      data: shown.map((g) => ({ name: g.name, icon: g.icon })),
    },
    xAxis: { ...base.xAxis, ...axis(mx, chart.logX), nameLocation: 'middle', nameGap: 30 },
    yAxis: { ...base.yAxis, ...axis(my, chart.logY), nameLocation: 'end', nameGap: 10, nameTextStyle: { ...base.yAxis.nameTextStyle, align: 'left' } },
    dataZoom: [
      { type: 'inside', xAxisIndex: 0, filterMode: 'none', zoomOnMouseWheel: 'ctrl' },
      { type: 'inside', yAxisIndex: 0, filterMode: 'none', zoomOnMouseWheel: 'ctrl' },
    ],
    series: [
      // Gelber Hof um den markierten Eintrag: dieselbe Markierung wie die Tabellenzeile. Er liegt über den
      // übrigen Punkten und Beschriftungen; der Punkt selbst folgt ganz oben in einer eigenen Reihe.
      {
        type: 'scatter',
        silent: true,
        z: 3,
        symbol: 'circle',
        data: halo,
        itemStyle: { color: colors.sel, borderColor: colors.text, borderWidth: 1 },
        label: { show: !isRun, position: 'right', distance: 6, color: colors.text, fontSize: 12, fontWeight: 700, textBorderColor: colors.surface, textBorderWidth: 3, formatter: (p: any) => p.name },
        tooltip: { show: false },
      },
      ...shown.map((g) => ({
      type: 'scatter',
      name: g.name,
      data: g.items,
      itemStyle: { color: g.color, borderColor: colors.surface, borderWidth: 1 },
      emphasis: { scale: 1.25, itemStyle: { borderColor: colors.text, borderWidth: 1.5 } },
      label: {
        show: chart.labels,
        position: 'right',
        distance: 7,
        color: colors.text,
        fontSize: 12,
        // Kontur in der Flächenfarbe: Die Schrift bleibt lesbar, wo ein Punkt oder der gelbe Hof sie berührt.
        textBorderColor: colors.surface,
        textBorderWidth: 3,
        formatter: (p: any) => (isRun ? p.data.row.run_code : p.data.row.label),
      },
      labelLayout: { moveOverlap: 'shiftY', hideOverlap: true },
      cursor: 'pointer',
      })),
      { type: 'scatter', z: 4, data: top, itemStyle: { borderColor: colors.surface, borderWidth: 1 }, label: { show: false }, cursor: 'pointer' },
    ],
  }
  return { option: option as EChartsOption, drawn, missing, notPositive }
}
