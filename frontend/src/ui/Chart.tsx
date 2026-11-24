// Hülle um ECharts: folgt dem Farbschema, passt sich der Breite an, kann als Bild gespeichert werden.
import * as echarts from 'echarts'
import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef } from 'react'
import { useThemeName } from './index'

export type ChartColors = {
  surface: string
  text: string
  text2: string
  text3: string
  line: string
  lineStrong: string
  pass: string
  fail: string
  warn: string
  neutral: string
  accent: string
  bar1: string
  bar2: string
  bar3: string
  series: string[]
  other: string
  sel: string
  selInk: string
}

const FONT = "'Archivo Variable', Arial, sans-serif"

function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim()
}

/** Farben des aktuellen Schemas für Diagramme. */
export function useChartColors(): ChartColors {
  const theme = useThemeName()
  return useMemo(
    () => ({
      surface: cssVar('--chart-surface'),
      text: cssVar('--text'),
      text2: cssVar('--text-2'),
      text3: cssVar('--text-3'),
      line: cssVar('--chart-grid'),
      lineStrong: cssVar('--line-strong'),
      pass: cssVar('--pass'),
      fail: cssVar('--fail'),
      warn: cssVar('--warn'),
      neutral: cssVar('--neutral'),
      accent: cssVar('--accent'),
      bar1: cssVar('--bar-1'),
      bar2: cssVar('--bar-2'),
      bar3: cssVar('--bar-3'),
      series: [1, 2, 3, 4, 5, 6, 7, 8].map((i) => cssVar(`--series-${i}`)),
      other: cssVar('--series-other'),
      sel: cssVar('--sel'),
      selInk: cssVar('--sel-ink'),
    }),
    // Das Schema steht nicht im Rumpf, löst aber das Neulesen der CSS-Variablen aus.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [theme],
  )
}

// Große Anbieter haben feste Plätze, damit z. B. Anthropic in jedem Diagramm dieselbe Farbe trägt
// und nicht wegen der alphabetischen Reihenfolge unter „übrige“ fällt.
const VENDOR_SLOTS = ['Anthropic', 'OpenAI', 'Google', 'Mistral AI', 'Qwen (Alibaba)', 'DeepSeek', 'Meta', 'xAI']

/** Feste Farbe je Ausprägung: folgt dem Namen, nie dem Rang. Ab der neunten Ausprägung „übrige“. */
export function categoryColor(colors: ChartColors, categories: string[], value: string): string {
  const vendors = categories.some((c) => VENDOR_SLOTS.includes(c))
  const ordered = vendors ? [...VENDOR_SLOTS, ...categories.filter((c) => !VENDOR_SLOTS.includes(c))] : categories
  const index = ordered.indexOf(value)
  return index >= 0 && index < colors.series.length ? colors.series[index] : colors.other
}

/** Gemeinsame Grundeinstellungen: zurückhaltende Achsen und Gitter, Schrift der App. */
export function baseOption(c: ChartColors): echarts.EChartsOption {
  const axis = {
    axisLine: { lineStyle: { color: c.lineStrong } },
    axisTick: { show: false },
    axisLabel: { color: c.text, fontSize: 12 },
    splitLine: { lineStyle: { color: c.line } },
    nameTextStyle: { color: c.text2, fontSize: 12 },
  }
  return {
    backgroundColor: 'transparent',
    textStyle: { fontFamily: FONT, color: c.text },
    // Diagramme stehen sofort: keine Einblendung beim Zeichnen.
    animation: false,
    grid: { left: 8, right: 24, top: 24, bottom: 8, containLabel: true },
    tooltip: {
      backgroundColor: c.text,
      borderWidth: 0,
      padding: [8, 12],
      textStyle: { color: c.surface, fontSize: 13, fontFamily: FONT },
      extraCssText: 'border-radius:3px; box-shadow:0 12px 32px rgba(16,22,18,.25); max-width:360px; white-space:normal; font-variant-numeric:tabular-nums;',
    },
    legend: { textStyle: { color: c.text2, fontSize: 12 }, icon: 'rect', itemWidth: 12, itemHeight: 12, inactiveColor: c.text3 },
    xAxis: axis as any,
    yAxis: axis as any,
  }
}

export type ChartHandle = { download: (name: string) => void }

type Props = {
  option: echarts.EChartsOption
  height?: number
  onClick?: (params: any) => void
  ariaLabel: string
}

export const Chart = forwardRef<ChartHandle, Props>(function Chart({ option, height = 320, onClick, ariaLabel }, ref) {
  const element = useRef<HTMLDivElement>(null)
  const chart = useRef<echarts.ECharts | null>(null)
  const click = useRef(onClick)
  click.current = onClick

  useEffect(() => {
    if (!element.current) return
    const instance = echarts.init(element.current, undefined, { renderer: 'canvas' })
    chart.current = instance
    instance.on('click', (params) => click.current?.(params))
    const observer = new ResizeObserver(() => instance.resize())
    observer.observe(element.current)
    return () => {
      observer.disconnect()
      instance.dispose()
      chart.current = null
    }
  }, [])

  useEffect(() => {
    chart.current?.setOption(option, { notMerge: true })
  }, [option])

  useImperativeHandle(ref, () => ({
    download(name: string) {
      const instance = chart.current
      if (!instance) return
      const url = instance.getDataURL({ type: 'png', pixelRatio: 2, backgroundColor: cssVar('--chart-surface') })
      const link = document.createElement('a')
      link.href = url
      link.download = `${name}.png`
      link.click()
    },
  }))

  return <div ref={element} role="img" aria-label={ariaLabel} style={{ width: '100%', height, cursor: onClick ? 'pointer' : undefined }} />
})
