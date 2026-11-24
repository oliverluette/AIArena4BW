// Modelltabelle: Rang, Bilanz, Quote, Kennzahlen und Formkurve je Eintrag; sortierbar,
// mit Schalter „zeigen“. Ein Klick auf die Zeile markiert den Eintrag auf der ganzen Seite.
import { useMemo } from 'react'
import { duration, durationSpan, num, percent, tokens } from '../../format'
import { t } from '../../texts'
import { useSort } from '../../ui'
import { FormCurve, FormLegend } from '../../ui/FormCurve'
import { costSourceText, money, type Run, type Summary } from './model'

const tx = t.analysis.models
/** So viele Läufe zeigt die Formkurve höchstens; ältere stehen als Zahl davor. */
const FORM_MAX = 10

type Row = Summary & { stub?: boolean; rank?: number; failed?: number; open?: number }

type Props = {
  /** Kennzahlen aller Einträge nach den Filtern, auch der abgewählten (soweit geladen). */
  rows: Summary[]
  /** Läufe nach den Filtern: Grundlage von Bilanz und Formkurve. */
  runs: Run[]
  /** Alle Einträge, die nach den Filtern zur Wahl stehen. */
  available: string[]
  excluded: string[]
  onExcluded: (excluded: string[]) => void
  selected: string | null
  onSelect: (label: string) => void
}

/** Rangfolge wie auf der Übersicht: PASS-Quote, dann Kosten je bestandenem Lauf, dann Laufzeit. */
function ranking(a: Summary, b: Summary): number {
  const big = Number.POSITIVE_INFINITY
  return (b.pass_rate ?? -1) - (a.pass_rate ?? -1) || (a.cost_per_pass ?? big) - (b.cost_per_pass ?? big) || (a.seconds ?? big) - (b.seconds ?? big)
}

function formKind(run: Run): 'pass' | 'fail' | 'open' | 'invalid' {
  if (!run.valid) return 'invalid'
  return run.verify_status === 'pass' ? 'pass' : run.verify_status === 'fail' ? 'fail' : 'open'
}

export function ModelTable({ rows, runs, available, excluded, onExcluded, selected, onSelect }: Props) {
  const byLabel = useMemo(() => {
    const map = new Map<string, Run[]>()
    for (const run of runs) map.set(run.label, [...(map.get(run.label) ?? []), run])
    for (const list of map.values()) list.sort((a, b) => String(a.started ?? '').localeCompare(String(b.started ?? '')))
    return map
  }, [runs])

  const full = useMemo<Row[]>(() => {
    const ranks = new Map([...rows].sort(ranking).map((row, index) => [row.label, index + 1]))
    return rows.map((row) => {
      const failed = (byLabel.get(row.label) ?? []).filter((r) => r.valid && r.verify_status === 'fail').length
      return { ...row, rank: ranks.get(row.label), failed, open: Math.max(0, row.runs - row.passed - failed) }
    })
  }, [rows, byLabel])

  const known = new Set(rows.map((r) => r.label))
  // Abgewählte Einträge ohne geladene Kennzahlen bleiben als Zeile stehen, damit sie sich wieder einblenden lassen.
  const stubs = excluded.filter((label) => available.includes(label) && !known.has(label)).map((label) => ({ label, stub: true }) as Row)
  const { sorted, toggle, mark, sort } = useSort<Row>([...full, ...stubs], { key: 'rank', dir: 'asc' })
  const zoneOf = (row: Row | undefined) => (!row || row.stub ? '' : row.pass_rate === 1 ? 'top' : (row.pass_rate ?? 1) < 0.5 ? 'low' : 'mid')

  const head = (key: string, label: string, right = false, title?: string, wide = false) => (
    <th className={[right && 'right', wide && 'col-wide'].filter(Boolean).join(' ') || undefined} title={title}>
      <button type="button" onClick={() => toggle(key)}>
        {label}
        {mark(key)}
      </button>
    </th>
  )
  const show = (label: string, on: boolean) => onExcluded(on ? excluded.filter((x) => x !== label) : [...excluded, label])

  return (
    <>
      <div className="table-wrap">
        <table className="table table--click table--dense">
          <thead>
            <tr>
              {head('rank', tx.col.rank, false, tx.col.rankTitle)}
              {head('label', tx.col.label)}
              {head('vendor', tx.col.vendor)}
              {head('platform_name', tx.col.platform, false, undefined, true)}
              {head('thinking_label', tx.col.thinking)}
              {head('runs', tx.col.runs, true, tx.col.runsTitle)}
              {head('passed', tx.col.passed, true, tx.col.passedTitle)}
              {head('failed', tx.col.failed, true, tx.col.failedTitle)}
              {head('open', tx.col.open, true, tx.col.openTitle)}
              {head('pass_rate', tx.col.passRate, true)}
              {head('cost_per_pass', tx.col.costPerPass, true, tx.col.costPerPassTitle)}
              {head('cost', tx.col.cost, true, tx.col.costTitle, true)}
              {head('seconds', tx.col.seconds, true, tx.col.secondsTitle)}
              {head('seconds_max', tx.col.span, true)}
              {head('steps', tx.col.steps, true, undefined, true)}
              {head('tokens_new', tx.col.tokensIn, true, tx.col.tokensInTitle)}
              {head('tokens_output', tx.col.tokensOut, true)}
              <th>{tx.col.form}</th>
              <th>{tx.col.show}</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((row, index) => {
              const off = excluded.includes(row.label)
              // Nach Rang sortiert trennt eine kräftige Linie die Zonen, wie in einer Ligatabelle.
              const cut = sort.key === 'rank' && index < sorted.length - 1 && zoneOf(row) !== '' && zoneOf(sorted[index + 1]) !== '' && zoneOf(row) !== zoneOf(sorted[index + 1])
              const classes = [off && 'is-dim', row.label === selected && 'is-sel', cut && 'is-cut'].filter(Boolean).join(' ')
              const form = byLabel.get(row.label) ?? []
              const zone = zoneOf(row) === 'top' ? 'zone zone--top' : zoneOf(row) === 'low' ? 'zone zone--low' : 'zone'
              return (
                <tr key={row.label} className={classes || undefined} onClick={() => !row.stub && onSelect(row.label)}>
                  <td className="num">
                    {!row.stub && (
                      <>
                        <i className={zone} />
                        <strong>{row.rank}</strong>
                      </>
                    )}
                  </td>
                  <td className="nowrap" title={row.stub ? undefined : tx.rowTitle(row.model_id, row.mcp_server, row.agent_label)}>
                    <strong>{row.label}</strong>
                    {off && <span className="muted small"> · {tx.hiddenRow}</span>}
                  </td>
                  {row.stub ? (
                    <td colSpan={16} />
                  ) : (
                    <>
                      <td className="nowrap">{row.vendor}</td>
                      <td className="nowrap col-wide">{row.platform_name}</td>
                      <td className="nowrap">{row.thinking_label}</td>
                      <td className="right num group">{num(row.runs)}</td>
                      <td className="right num">{num(row.passed)}</td>
                      <td className="right num">{num(row.failed)}</td>
                      <td className="right num">{num(row.open)}</td>
                      <td className="right num">
                        <strong>{percent(row.pass_rate)}</strong>
                      </td>
                      <td className="right num group">
                        {row.cost_per_pass !== null ? money(row.cost_per_pass) : row.price_known ? <span title={tx.noPass}>{t.common.none}</span> : t.common.noPrice}
                      </td>
                      <td className="right num col-wide" title={row.cost_source ? costSourceText(row.cost_source) : undefined}>
                        {row.price_known || row.cost !== null ? money(row.cost) : t.common.noPrice}
                      </td>
                      <td className="right num">{duration(row.seconds)}</td>
                      <td className="right num">{row.seconds_min === null ? t.common.none : durationSpan(row.seconds_min, row.seconds_max)}</td>
                      <td className="right num col-wide">{num(row.steps, Number.isInteger(row.steps ?? 0) ? 0 : 1)}</td>
                      <td className="right num">
                        {tokens(row.tokens_new)}/{tokens(row.tokens_cache_read)}
                      </td>
                      <td className="right num">{tokens(row.tokens_output)}</td>
                      <td className="group">
                        <FormCurve runs={form.map((run) => ({ id: run.id, run_code: run.run_code, kind: formKind(run) }))} max={FORM_MAX} />
                      </td>
                    </>
                  )}
                  <td onClick={(e) => e.stopPropagation()}>
                    <input type="checkbox" checked={!off} aria-label={tx.showLabel(row.label)} onChange={(e) => show(row.label, e.target.checked)} />
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <p className="legend">
        <span>{tx.legend}</span>
        <span className="spacer" />
        <span>
          <i className="zone zone--top" />
          {tx.zoneTop}
        </span>
        <span>
          <i className="zone zone--low" />
          {tx.zoneLow}
        </span>
        <FormLegend />
      </p>
    </>
  )
}
