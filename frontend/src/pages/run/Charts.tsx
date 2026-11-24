// Diagramme des Lauf-Details: Zeitleiste der Werkzeugaufrufe und Tokens je Schritt.
import type { EChartsOption } from 'echarts'
import { useMemo, useRef, useState } from 'react'
import { num } from '../../format'
import { t } from '../../texts'
import { Button, Chips } from '../../ui'
import { baseOption, Chart, useChartColors, type ChartColors, type ChartHandle } from '../../ui/Chart'
import { axisNum, CROSS, tipHtml } from '../analysis/model'

const tx = t.run

export type RunEvent = {
  phase: string
  seconds: number | null
  duration: number | null
  step: number | null
  kind: string
  tool: string | null
  requirement: string | null
  tokens_input: number | null
  tokens_output: number | null
  is_error: number | boolean
  text: string | null
}

type TimelineProps = { events: RunEvent[]; runSeconds: number | null; verifySeconds: number | null; code: string }

export function Timeline({ events, runSeconds, verifySeconds, code }: TimelineProps) {
  const colors = useChartColors()
  const ref = useRef<ChartHandle>(null)
  const built = useMemo(() => timelineOption(colors, events, runSeconds, verifySeconds), [colors, events, runSeconds, verifySeconds])

  if (built.drawn === 0) return <p className="muted">{tx.timeline.empty}</p>
  return (
    <div>
      <div className="row row--between small" style={{ marginBottom: 6, alignItems: 'flex-end' }}>
        <span className="secondary">
          {built.hasVerify && tx.timeline.verifyNote}
          {built.untimed > 0 && ` ${tx.timeline.untimed(built.untimed)}`}
        </span>
        <Button small onClick={() => ref.current?.download(tx.timeline.file(code))}>
          {tx.timeline.save}
        </Button>
      </div>
      <div className="run-chart">
        <Chart ref={ref} option={built.option} height={built.height} ariaLabel={tx.timeline.aria} />
      </div>
    </div>
  )
}

const fmtSeconds = (v: number | null | undefined) => (v === null || v === undefined ? t.common.none : `${num(v, 1)} s`)

export function timelineOption(c: ChartColors, events: RunEvent[], runSeconds: number | null, verifySeconds: number | null) {
  const base = baseOption(c) as any
  const timed = events.filter((e) => (e.kind === 'tool' || e.kind === 'step') && typeof e.seconds === 'number')
  const untimed = events.filter((e) => (e.kind === 'tool' || e.kind === 'step') && typeof e.seconds !== 'number').length
  const end = (phase: string) => Math.max(0, ...timed.filter((e) => e.phase === phase).map((e) => e.seconds as number))
  const hasVerify = timed.some((e) => e.phase === 'verify')
  // Die Zeiten der Prüfung zählen ab Prüfbeginn: hinter die Aufgabe setzen, damit beide Phasen getrennt erkennbar sind.
  const taskEnd = Math.max(runSeconds ?? 0, end('task'))
  const total = hasVerify ? taskEnd + Math.max(verifySeconds ?? 0, end('verify')) : taskEnd
  const offset = (e: RunEvent) => (e.phase === 'verify' ? taskEnd : 0)

  const tools = [...new Set(timed.filter((e) => e.kind === 'tool').map((e) => e.tool || t.common.none))]
  const hasSteps = timed.some((e) => e.kind === 'step')
  const rows = hasSteps ? [tx.timeline.stepRow, ...tools] : tools
  const rowOf = (e: RunEvent) => rows.indexOf(e.kind === 'step' ? tx.timeline.stepRow : e.tool || t.common.none)

  const bars = (failed: boolean) =>
    timed
      .filter((e) => e.kind === 'tool' && Boolean(e.is_error) === failed)
      .map((e) => {
        const stop = (e.seconds as number) + offset(e)
        return { value: [Math.max(offset(e), stop - (e.duration ?? 0)), stop, rowOf(e)], event: e }
      })

  const renderBar = (color: string, cross: boolean) => (_params: any, api: any) => {
    const a = api.coord([api.value(0), api.value(2)])
    const b = api.coord([api.value(1), api.value(2)])
    const width = Math.max(3, b[0] - a[0])
    const children: any[] = [
      // Unsichtbare, größere Fläche: Auch sehr kurze Aufrufe lassen sich mit der Maus treffen.
      { type: 'rect', shape: { x: a[0] - 5, y: a[1] - 11, width: width + 10, height: 22 }, style: { fill: 'transparent' } },
      { type: 'rect', shape: { x: a[0], y: a[1] - 6, width, height: 12 }, style: { fill: color } },
    ]
    if (cross) {
      // Fehler tragen zusätzlich ein Kreuz: nicht nur die Farbe unterscheidet.
      const x = a[0] + width / 2
      const line = (dy: number) => ({ type: 'line', shape: { x1: x - 5, y1: a[1] - dy, x2: x + 5, y2: a[1] + dy }, style: { stroke: c.text, lineWidth: 2 } })
      children.push(line(5), line(-5))
    }
    return { type: 'group', children }
  }

  const tooltip = (params: any) => {
    const e: RunEvent | undefined = params?.data?.event
    if (!e) return ''
    const phase = t.common.phase[e.phase] ?? e.phase
    if (e.kind === 'step') {
      return tipHtml(tx.timeline.step, null, [
        [tx.timeline.tip.phase, phase],
        [tx.timeline.tip.stepNo, num(e.step)],
        [tx.timeline.tip.at, fmtSeconds(e.seconds)],
      ])
    }
    const lines: [string, string][] = [
      [tx.timeline.tip.phase, phase],
      [tx.timeline.tip.stepNo, num(e.step)],
      [tx.timeline.tip.from, fmtSeconds(e.duration === null ? e.seconds : Math.max(0, (e.seconds as number) - e.duration))],
      [tx.timeline.tip.duration, fmtSeconds(e.duration)],
    ]
    if (e.requirement) lines.push([tx.timeline.tip.requirement, e.requirement])
    lines.push([tx.timeline.tip.result, e.is_error ? tx.timeline.tip.failed : tx.timeline.tip.ok])
    return tipHtml(e.tool || tx.timeline.tool, e.is_error && e.text ? e.text : null, lines)
  }

  const okBars = bars(false)
  const errorBars = bars(true)
  const steps = timed.filter((e) => e.kind === 'step').map((e) => ({ value: [(e.seconds as number) + offset(e), rowOf(e)], event: e }))

  const series: any[] = []
  const legend: any[] = []
  const custom = (name: string, color: string, cross: boolean, data: any[]) => ({
    type: 'custom',
    name,
    itemStyle: { color },
    encode: { x: [0, 1], y: 2 },
    data,
    renderItem: renderBar(color, cross),
    z: cross ? 3 : 2,
  })
  if (okBars.length > 0) {
    series.push(custom(tx.timeline.tool, c.bar2, false, okBars))
    legend.push({ name: tx.timeline.tool, icon: 'rect' })
  }
  if (errorBars.length > 0) {
    series.push(custom(tx.timeline.error, c.fail, true, errorBars))
    legend.push({ name: tx.timeline.error, icon: CROSS })
  }
  if (steps.length > 0) {
    series.push({
      type: 'scatter',
      name: tx.timeline.step,
      symbol: 'diamond',
      symbolSize: 9,
      itemStyle: { color: c.neutral, borderColor: c.surface, borderWidth: 1 },
      data: steps,
    })
    legend.push({ name: tx.timeline.step, icon: 'diamond' })
  }
  if (series.length > 0 && hasVerify) {
    // Phasen als beschriftete Bereiche: Aufgabe ohne Tönung, Prüfung leicht getönt.
    series[0].markArea = {
      silent: true,
      label: { color: c.text2, fontSize: 12, position: 'top', distance: 4 },
      data: [
        [{ name: tx.timeline.phaseTask, xAxis: 0, itemStyle: { color: 'transparent' } }, { xAxis: taskEnd }],
        [{ name: tx.timeline.phaseVerify, xAxis: taskEnd, itemStyle: { color: c.line } }, { xAxis: total }],
      ],
    }
    series[0].markLine = {
      silent: true,
      symbol: 'none',
      label: { show: false },
      lineStyle: { color: c.lineStrong, width: 1, type: 'solid' },
      data: [{ xAxis: taskEnd }],
    }
  }

  const option: any = {
    ...base,
    grid: { left: 8, right: 32, top: 64, bottom: 32, containLabel: true },
    legend: { ...base.legend, top: 0, left: 0, data: legend },
    tooltip: { ...base.tooltip, trigger: 'item', formatter: tooltip },
    xAxis: {
      ...base.xAxis,
      type: 'value',
      min: 0,
      max: Math.max(1, Math.ceil(total)),
      name: tx.timeline.axis,
      nameLocation: 'middle',
      nameGap: 30,
      axisLabel: { ...base.xAxis.axisLabel, formatter: (v: number) => axisNum(v) },
    },
    yAxis: {
      ...base.yAxis,
      type: 'category',
      inverse: true,
      data: rows,
      splitLine: { show: true, lineStyle: { color: c.line } },
      axisLabel: { ...base.yAxis.axisLabel, width: 170, overflow: 'truncate' },
    },
    dataZoom: [{ type: 'inside', xAxisIndex: 0, filterMode: 'none', zoomOnMouseWheel: 'ctrl' }],
    series,
  }
  return {
    option: option as EChartsOption,
    drawn: okBars.length + errorBars.length + steps.length,
    untimed,
    hasVerify,
    height: Math.max(200, rows.length * 30 + 120),
  }
}

// --------------------------------------------------------------------------- Tokens je Schritt

export function StepTokens({ events, code }: { events: RunEvent[]; code: string }) {
  const colors = useChartColors()
  const ref = useRef<ChartHandle>(null)
  const usage = useMemo(() => events.filter((e) => e.kind === 'usage' && (e.tokens_input !== null || e.tokens_output !== null)), [events])
  const phases = useMemo(() => [...new Set(usage.map((e) => e.phase))], [usage])
  const [chosen, setChosen] = useState('task')
  const phase = phases.includes(chosen) ? chosen : (phases[0] ?? 'task')
  const rows = useMemo(() => usage.filter((e) => e.phase === phase), [usage, phase])
  const option = useMemo(() => usageOption(colors, rows), [colors, rows])

  if (usage.length === 0) return <p className="muted">{tx.usage.empty}</p>
  return (
    <div>
      {phases.length > 1 && (
        <div style={{ marginBottom: 12 }}>
          <Chips
            options={phases.map((p) => ({ value: p, label: t.common.phase[p] ?? p }))}
            value={[phase]}
            onChange={(v) => v.length > 0 && setChosen(v[v.length - 1])}
            ariaLabel={tx.timeline.tip.phase}
          />
        </div>
      )}
      <div className="row small" style={{ marginBottom: 6, justifyContent: 'flex-end' }}>
        <Button small onClick={() => ref.current?.download(tx.usage.file(code))}>
          {tx.timeline.save}
        </Button>
      </div>
      <div className="run-chart">
        <Chart ref={ref} option={option} height={300} ariaLabel={tx.usage.aria} />
      </div>
    </div>
  )
}

export function usageOption(c: ChartColors, rows: RunEvent[]): EChartsOption {
  const base = baseOption(c) as any
  const labels = rows.map((e, i) => String(e.step ?? i + 1))
  const option: any = {
    ...base,
    grid: { left: 8, right: 24, top: 64, bottom: 32, containLabel: true },
    legend: { ...base.legend, top: 0, left: 0 },
    tooltip: {
      ...base.tooltip,
      trigger: 'axis',
      axisPointer: { type: 'shadow', shadowStyle: { color: c.line } },
      formatter: (params: any) => {
        const first = Array.isArray(params) ? params[0] : params
        const e = rows[first?.dataIndex]
        if (!e) return ''
        return tipHtml(tx.usage.tipStep(labels[first.dataIndex]), null, [
          [tx.usage.input, num(e.tokens_input)],
          [tx.usage.output, num(e.tokens_output)],
          [tx.usage.tipAt, fmtSeconds(e.seconds)],
        ])
      },
    },
    xAxis: {
      ...base.xAxis,
      type: 'category',
      data: labels,
      name: tx.usage.axisX,
      nameLocation: 'middle',
      nameGap: 30,
      splitLine: { show: false },
    },
    yAxis: {
      ...base.yAxis,
      type: 'value',
      name: tx.usage.axisY,
      nameLocation: 'end',
      nameGap: 14,
      nameTextStyle: { ...base.yAxis.nameTextStyle, align: 'left' },
      axisLabel: { ...base.yAxis.axisLabel, formatter: (v: number) => axisNum(v) },
    },
    series: [
      { type: 'bar', name: tx.usage.input, barMaxWidth: 12, barGap: '25%', itemStyle: { color: c.bar3, borderRadius: [2, 2, 0, 0] }, data: rows.map((e) => e.tokens_input) },
      { type: 'bar', name: tx.usage.output, barMaxWidth: 12, itemStyle: { color: c.bar1, borderRadius: [2, 2, 0, 0] }, data: rows.map((e) => e.tokens_output) },
    ],
  }
  return option as EChartsOption
}
