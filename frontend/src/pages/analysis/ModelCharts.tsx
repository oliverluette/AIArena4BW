// Diagramme je Modell: waagerechte Balken, überall dieselbe feste Reihenfolge der Einträge.
import type { EChartsOption } from 'echarts'
import { useMemo, useRef, useState, type ReactNode } from 'react'
import { duration, num, percent, tokens } from '../../format'
import { t } from '../../texts'
import { Button, Check } from '../../ui'
import { baseOption, categoryColor, Chart, useChartColors, type ChartColors, type ChartHandle } from '../../ui/Chart'
import { axisNum, money, tipHtml, type Run, type Summary, SHAPES } from './model'

const tx = t.analysis.charts

const BAR = 12
const THIN_LINE = 'path://M0,4 L12,4 L12,6 L0,6 Z'

type Props = {
  summary: Summary[]
  runs: Run[]
  /** Alle Anbieter in fester Reihenfolge: Grundlage der Farben im Streudiagramm. */
  vendors: string[]
  selected: string | null
}

/** Hebt den markierten Eintrag an der Achse hervor: dieselbe gelbe Markierung wie in der Tabelle. */
function marked(option: EChartsOption, selected: string | null, c: ChartColors): EChartsOption {
  const axis = (option as any).yAxis
  if (!selected || axis?.type !== 'category') return option
  const axisLabel = {
    ...axis.axisLabel,
    formatter: (value: string) => (value === selected ? `{sel|${value}}` : value),
    rich: { sel: { backgroundColor: c.sel, color: c.selInk, fontWeight: 700, padding: [3, 5] } },
  }
  return { ...option, yAxis: { ...axis, axisLabel } } as EChartsOption
}

export function ModelCharts({ summary, runs, vendors, selected }: Props) {
  const colors = useChartColors()
  const [points, setPoints] = useState(false)
  const height = Math.max(240, summary.length * 26 + 96)

  const seconds = useMemo(() => marked(secondsOption(colors, summary, runs, points), selected, colors), [colors, summary, runs, points, selected])
  const input = useMemo(() => marked(inputOption(colors, summary), selected, colors), [colors, summary, selected])
  const output = useMemo(() => marked(outputOption(colors, summary), selected, colors), [colors, summary, selected])
  const cost = useMemo(() => marked(costOption(colors, summary), selected, colors), [colors, summary, selected])
  const worth = useMemo(() => worthOption(colors, summary, vendors, selected), [colors, summary, vendors, selected])

  return (
    <div className="grid grid--2">
      <ChartPanel
        title={tx.seconds.title}
        file={tx.seconds.file}
        option={seconds}
        height={height}
        extra={
          <Check checked={points} onChange={setPoints}>
            {tx.points}
          </Check>
        }
      />
      <ChartPanel title={tx.cost.title} file={tx.cost.file} option={cost} height={height} />
      <ChartPanel title={tx.input.title} file={tx.input.file} option={input} height={height} />
      <ChartPanel title={tx.output.title} file={tx.output.file} option={output} height={height} />
      <div className="analysis-wide">
        <ChartPanel
          title={tx.value.title}
          file={tx.value.file}
          option={worth.option}
          height={400}
          foot={worth.missing > 0 ? tx.value.missing(worth.missing) : undefined}
        />
      </div>
    </div>
  )
}

function ChartPanel(props: { title: string; file: string; option: EChartsOption; height: number; extra?: ReactNode; foot?: ReactNode }) {
  const ref = useRef<ChartHandle>(null)
  return (
    <div>
      <div className="row row--between" style={{ marginBottom: 8, minHeight: 30 }}>
        <strong>{props.title}</strong>
        <span className="row small">
          {props.extra}
          <Button small variant="quiet" onClick={() => ref.current?.download(props.file)}>
            {tx.save}
          </Button>
        </span>
      </div>
      <div className="chart-box">
        <Chart ref={ref} option={props.option} height={props.height} ariaLabel={tx.aria(props.title)} />
      </div>
      {props.foot && <p className="muted small chart-foot">{props.foot}</p>}
    </div>
  )
}

// --------------------------------------------------------------------------- Optionen

/** Gemeinsamer Rahmen: Einträge an der Y-Achse (erster oben), eine Wertachse, Tooltip je Eintrag. */
function frame(c: ChartColors, rows: Summary[], axisName: string, format: (v: number) => string, tip: (row: Summary) => string, legend: any | null): any {
  const base = baseOption(c) as any
  const byLabel = new Map(rows.map((r) => [r.label, r]))
  return {
    ...base,
    grid: { left: 8, right: 32, top: legend ? 40 : 12, bottom: 32, containLabel: true },
    legend: legend ? { ...base.legend, top: 0, left: 0, ...legend } : { show: false },
    tooltip: {
      ...base.tooltip,
      trigger: 'axis',
      axisPointer: { type: 'shadow', shadowStyle: { color: c.line } },
      formatter: (params: any) => {
        const first = Array.isArray(params) ? params[0] : params
        const row = byLabel.get(String(first?.axisValue ?? first?.name ?? ''))
        return row ? tip(row) : ''
      },
    },
    xAxis: {
      ...base.xAxis,
      type: 'value',
      min: 0,
      name: axisName,
      nameLocation: 'middle',
      nameGap: 30,
      axisLabel: { ...base.xAxis.axisLabel, formatter: format },
    },
    yAxis: {
      ...base.yAxis,
      type: 'category',
      inverse: true,
      data: rows.map((r) => r.label),
      splitLine: { show: false },
      axisLabel: { ...base.yAxis.axisLabel, width: 170, overflow: 'truncate' },
    },
  }
}

function head(row: Summary): [string, string | null, [string, string][]] {
  return [row.label, `${row.vendor} · ${row.platform_name}`, [[tx.tip.runs, num(row.runs)]]]
}

export function secondsOption(c: ChartColors, rows: Summary[], runs: Run[], points: boolean): EChartsOption {
  const index = new Map(rows.map((r, i) => [r.label, i]))
  const tip = (row: Summary) => {
    const [title, sub, lines] = head(row)
    return tipHtml(title, sub, [
      ...lines,
      [tx.tip.median, duration(row.seconds)],
      [tx.tip.span, row.seconds_min === null ? t.common.none : `${duration(row.seconds_min)} – ${duration(row.seconds_max)}`],
    ])
  }
  const legendData = [
    { name: tx.seconds.median, icon: 'rect' },
    { name: tx.seconds.span, icon: THIN_LINE },
  ]
  if (points) legendData.push({ name: tx.seconds.single, icon: 'circle' })
  const option = frame(c, rows, tx.seconds.axis, axisNum, tip, { data: legendData })
  option.series = [
    {
      type: 'bar',
      name: tx.seconds.median,
      barWidth: BAR,
      itemStyle: { color: c.bar2, borderRadius: 0 },
      data: rows.map((r) => r.seconds),
    },
    {
      type: 'custom',
      name: tx.seconds.span,
      itemStyle: { color: c.text },
      z: 3,
      encode: { x: [0, 1], y: 2 },
      data: rows.flatMap((r, i) => (r.seconds_min === null || r.seconds_max === null ? [] : [[r.seconds_min, r.seconds_max, i]])),
      renderItem: (_params: any, api: any) => {
        const a = api.coord([api.value(0), api.value(2)])
        const b = api.coord([api.value(1), api.value(2)])
        const style = { stroke: c.text, lineWidth: 2 }
        const cap = (x: number) => ({ type: 'line', shape: { x1: x, y1: a[1] - 5, x2: x, y2: a[1] + 5 }, style })
        return { type: 'group', children: [{ type: 'line', shape: { x1: a[0], y1: a[1], x2: b[0], y2: b[1] }, style }, cap(a[0]), cap(b[0])] }
      },
    },
  ]
  if (points) {
    option.series.push({
      type: 'scatter',
      name: tx.seconds.single,
      symbolSize: 8,
      z: 4,
      itemStyle: { color: c.surface, borderColor: c.text, borderWidth: 1.5 },
      data: runs.flatMap((r) => (r.seconds === null || !index.has(r.label) ? [] : [[r.seconds, index.get(r.label)]])),
    })
  }
  return option as EChartsOption
}

export function inputOption(c: ChartColors, rows: Summary[]): EChartsOption {
  const tip = (row: Summary) => {
    const [title, sub, lines] = head(row)
    return tipHtml(title, sub, [
      ...lines,
      [tx.input.fresh, tokens(row.tokens_new)],
      [tx.input.cache, tokens(row.tokens_cache_read)],
      [tx.tip.total, tokens(row.tokens_input)],
    ])
  }
  const option = frame(c, rows, tx.input.axis, axisNum, tip, {})
  // Trennfuge in der Farbe der Fläche, damit die gestapelten Teile nicht ineinanderlaufen.
  const style = (color: string) => ({ color, borderColor: c.surface, borderWidth: 1 })
  option.series = [
    { type: 'bar', name: tx.input.fresh, stack: 'input', barWidth: BAR + 2, itemStyle: style(c.bar1), data: rows.map((r) => r.tokens_new) },
    { type: 'bar', name: tx.input.cache, stack: 'input', barWidth: BAR + 2, itemStyle: style(c.bar3), data: rows.map((r) => r.tokens_cache_read) },
  ]
  return option as EChartsOption
}

export function outputOption(c: ChartColors, rows: Summary[]): EChartsOption {
  const tip = (row: Summary) => {
    const [title, sub, lines] = head(row)
    return tipHtml(title, sub, [...lines, [tx.tip.median, tokens(row.tokens_output)]])
  }
  const option = frame(c, rows, tx.output.axis, axisNum, tip, null)
  option.series = [
    { type: 'bar', name: tx.output.title, barWidth: BAR, itemStyle: { color: c.bar2, borderRadius: 0 }, data: rows.map((r) => r.tokens_output) },
  ]
  return option as EChartsOption
}

export function costOption(c: ChartColors, rows: Summary[]): EChartsOption {
  const tip = (row: Summary) => {
    const [title, sub, lines] = head(row)
    return tipHtml(title, sub, [
      ...lines,
      [tx.tip.cost, money(row.cost)],
      [tx.tip.span, row.cost_min === null || row.cost_min === undefined ? t.common.none : `${money(row.cost_min)} – ${money(row.cost_max)}`],
      [tx.tip.costPerPass, row.cost_per_pass === null ? (row.price_known ? t.common.none : t.common.noPrice) : money(row.cost_per_pass)],
    ])
  }
  const option = frame(c, rows, tx.cost.axis, axisNum, tip, null)
  option.series = [
    {
      type: 'bar',
      name: tx.cost.title,
      barWidth: BAR,
      itemStyle: { color: c.bar2, borderRadius: 0 },
      // Ohne Preis kein Balken: null statt 0.
      data: rows.map((r) => r.cost),
    },
    {
      // Beschriftung statt Balken: „kein Preis“ bzw. „kostenfrei“ am Achsenanfang.
      type: 'scatter',
      name: t.common.noPrice,
      symbolSize: 1,
      silent: true,
      itemStyle: { color: 'transparent' },
      label: { show: true, position: 'right', distance: 6, color: c.text3, fontSize: 12, formatter: (p: any) => p.data.text },
      data: rows.flatMap((r, i) => (r.cost === null ? [{ value: [0, i], text: t.common.noPrice }] : r.cost === 0 ? [{ value: [0, i], text: tx.cost.free }] : [])),
    },
  ]
  return option as EChartsOption
}

export function worthOption(c: ChartColors, rows: Summary[], vendors: string[], selected: string | null = null): { option: EChartsOption; missing: number } {
  const base = baseOption(c) as any
  const drawn = rows.filter((r) => r.cost_per_pass !== null && r.pass_percent !== null)
  const names = vendors.slice(0, c.series.length)
  const groups = [...names, ''].map((name, index) => ({
    name: name || t.analysis.compare.other,
    color: name ? categoryColor(c, vendors, name) : c.other,
    icon: name ? SHAPES[index % SHAPES.length] : 'circle',
    items: drawn.filter((r) => (names.includes(r.vendor) ? r.vendor === name : name === '')),
  }))
  const option: any = {
    ...base,
    grid: { left: 8, right: 40, top: 64, bottom: 32, containLabel: true },
    legend: { ...base.legend, data: groups.filter((g) => g.items.length > 0).map((g) => ({ name: g.name, icon: g.icon })), top: 0, left: 0, right: 0, type: 'scroll', pageTextStyle: { color: c.text2 }, pageIconColor: c.text2, pageIconInactiveColor: c.text3 },
    tooltip: {
      ...base.tooltip,
      trigger: 'item',
      formatter: (p: any) => {
        const row: Summary | undefined = p?.data?.row
        if (!row) return ''
        return tipHtml(row.label, `${row.vendor} · ${row.platform_name}`, [
          [tx.tip.runs, num(row.runs)],
          [tx.tip.passed, `${row.passed} / ${row.verified}`],
          [tx.tip.passRate, percent(row.pass_rate)],
          [tx.tip.costPerPass, money(row.cost_per_pass)],
        ])
      },
    },
    xAxis: {
      ...base.xAxis,
      type: 'value',
      min: 0,
      max: 100,
      name: tx.value.x,
      nameLocation: 'middle',
      nameGap: 30,
      axisLabel: { ...base.xAxis.axisLabel, formatter: (v: number) => num(v) },
    },
    yAxis: {
      ...base.yAxis,
      type: 'value',
      min: 0,
      name: tx.value.y,
      nameLocation: 'end',
      nameGap: 14,
      nameTextStyle: { ...base.yAxis.nameTextStyle, align: 'left' },
      axisLabel: { ...base.yAxis.axisLabel, formatter: (v: number) => axisNum(v) },
    },
    series: [
      // Gelber Hof unter dem markierten Eintrag, wie im Vergleichsdiagramm.
      {
        type: 'scatter',
        silent: true,
        z: 1,
        symbol: 'circle',
        symbolSize: 24,
        itemStyle: { color: c.sel, borderColor: c.text, borderWidth: 1 },
        tooltip: { show: false },
        data: drawn.filter((row) => row.label === selected).map((row) => [row.pass_percent, row.cost_per_pass]),
      },
      ...groups
        .filter((g) => g.items.length > 0)
        .map((g) => ({
          type: 'scatter',
          name: g.name,
          symbol: g.icon,
          symbolSize: 12,
          itemStyle: { color: g.color, borderColor: c.surface, borderWidth: 1 },
          label: { show: true, distance: 7, color: c.text, fontSize: 12, textBorderColor: c.surface, textBorderWidth: 3, formatter: (p: any) => p.data.row.label },
          labelLayout: { moveOverlap: 'shiftY', hideOverlap: true },
          data: g.items.map((row) => ({
            value: [row.pass_percent, row.cost_per_pass],
            row,
            // Rechts der Mitte steht die Beschriftung links vom Punkt, damit sie nicht am Rand abgeschnitten wird.
            label: { position: (row.pass_percent ?? 0) > 60 ? 'left' : 'right', fontWeight: row.label === selected ? 700 : 400 },
          })),
        })),
    ],
  }
  return { option: option as EChartsOption, missing: rows.length - drawn.length }
}
