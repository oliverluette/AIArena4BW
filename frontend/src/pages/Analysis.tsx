// Auswertung: Filterspalte, Vergleichsdiagramm, Modelltabelle, Läufe, Diagramme je Modell, Ansichten.
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, errorText } from '../api'
import { t } from '../texts'
import { Button, Empty, ErrorNote, Loading, Page, Section, useToast } from '../ui'
import { Compare } from './analysis/Compare'
import { Filters } from './analysis/Filters'
import { ModelCharts } from './analysis/ModelCharts'
import { ModelTable } from './analysis/ModelTable'
import { RunsTable } from './analysis/RunsTable'
import { ViewsDialog } from './analysis/Views'
import { DEFAULT_FILTERS, normalize, saveText, type AnalysisData, type ChartSettings, type Filters as FilterState, type Settings, type View } from './analysis/model'
import '../styles/analysis.css'

const tx = t.analysis

type Current = { settings: Settings; view: string }

// Stand der Seite, solange die App offen ist: Die Standardansicht wird nur beim ersten Öffnen geladen;
// wer aus dem Lauf-Detail zurückkommt, findet Filter und Diagramm unverändert vor.
let remembered: Current | null = null

// Alle Ausprägungen ohne Filter: feste Grundlage der Kategoriefarben.
const EVERYTHING = { include_hidden: true, include_invalid: true }

export default function Analysis() {
  const toast = useToast()
  const views = useQuery<View[]>({ queryKey: ['views'], queryFn: () => api.get('/views') })
  const [own, setOwn] = useState<Current | null>(remembered)
  const [dialog, setDialog] = useState(false)
  // Markierter Eintrag: bleibt in Diagramm, Modelltabelle, Läufen und den Diagrammen je Modell gelb.
  const [selected, setSelected] = useState<string | null>(null)
  const select = (label: string) => setSelected((current) => (current === label ? null : label))
  const [exporting, setExporting] = useState(false)

  const start = useMemo<Current | null>(() => {
    if (views.isPending) return null
    const preset = views.data?.find((v) => v.is_default)
    return { settings: normalize(preset?.settings), view: preset?.name ?? '' }
  }, [views.isPending, views.data])
  const current = own ?? start
  const filters = current?.settings.filters

  const apply = (next: Current) => {
    remembered = next
    setOwn(next)
  }
  const setFilters = (next: FilterState) => current && apply({ ...current, settings: { ...current.settings, filters: next } })
  const setChart = (next: ChartSettings) => current && apply({ ...current, settings: { ...current.settings, chart: next } })

  const query = useQuery<AnalysisData>({
    queryKey: ['analysis', filters],
    queryFn: () => api.post('/analysis', filters),
    enabled: Boolean(filters),
    placeholderData: keepPreviousData,
  })
  const everything = useQuery<AnalysisData>({ queryKey: ['analysis', EVERYTHING], queryFn: () => api.post('/analysis', EVERYTHING) })
  // Kennzahlen auch der abgewählten Einträge, damit die Modelltabelle sie weiter zeigen kann.
  const hasExcluded = (filters?.excluded.length ?? 0) > 0
  const unexcluded = useQuery<AnalysisData>({
    queryKey: ['analysis', { ...filters, excluded: [] }],
    queryFn: () => api.post('/analysis', { ...filters, excluded: [] }),
    enabled: Boolean(filters) && hasExcluded,
    placeholderData: keepPreviousData,
  })

  const data = query.data
  const viewList = views.data ?? []
  const activeView = viewList.find((v) => v.name === current?.view)
  const changed = Boolean(activeView && current) && JSON.stringify(normalize(activeView!.settings)) !== JSON.stringify(current!.settings)

  const loadView = (view: View) => {
    apply({ settings: normalize(view.settings), view: view.name })
    toast(tx.views.loaded(view.name))
  }

  const exportCsv = async () => {
    if (!filters) return
    setExporting(true)
    try {
      const csv = await api.text('POST', '/analysis/csv', filters)
      // Die Kennung am Anfang lässt Tabellenprogramme die Umlaute richtig lesen.
      saveText(String.fromCharCode(0xfeff) + csv, `${tx.runs.csvFile}-${new Date().toISOString().slice(0, 10)}.csv`, 'text/csv;charset=utf-8')
      toast(tx.runs.csvDone)
    } catch (error) {
      toast(errorText(error), true)
    } finally {
      setExporting(false)
    }
  }

  const actions = (
    <>
      {viewList.length > 0 && (
        <select
          className="select"
          style={{ width: 'auto', minWidth: 190 }}
          value={activeView?.name ?? ''}
          aria-label={tx.views.loadLabel}
          onChange={(e) => {
            const view = viewList.find((v) => v.name === e.target.value)
            if (view) loadView(view)
          }}
        >
          <option value="">{tx.views.load}</option>
          {viewList.map((v) => (
            <option key={v.name} value={v.name}>
              {tx.views.option(v.name, v.is_default, v.name === activeView?.name && changed)}
            </option>
          ))}
        </select>
      )}
      <Button
        disabled={!current}
        onClick={() => {
          // Stand festhalten: Ändert sich im Dialog die Standardansicht, bleibt die Seite, wie sie ist.
          if (current) apply(current)
          setDialog(true)
        }}
      >
        {tx.views.manage}
      </Button>
      <Button busy={exporting} disabled={!data || data.runs.length === 0} onClick={exportCsv}>
        {tx.runs.csv}
      </Button>
    </>
  )
  const counts = data?.counts
  const meta = counts && (
    <>
      <strong>{tx.filter.shown(counts.shown, counts.all)}</strong>
      {counts.invalid > 0 && <> · {tx.filter.invalid(counts.invalid)}</>}
    </>
  )

  const noRuns = (everything.data ?? data)?.counts.all === 0

  let body
  if (noRuns) {
    body = (
      <Empty title={tx.emptyTitle} action={<Link className="btn btn--primary" to="/start">{tx.emptyAction}</Link>}>
        {tx.emptyText}
      </Empty>
    )
  } else if (!current || !data) {
    body = (
      <>
        <ErrorNote error={query.error} />
        {!query.error && <Loading lines={5} />}
      </>
    )
  } else {
    const { settings } = current
    const nothing = data.counts.shown === 0
    const tableRows = hasExcluded && unexcluded.data ? unexcluded.data.summary : data.summary
    body = (
      <>
        <ErrorNote error={query.error} />
        <Section>
          {nothing ? (
            <Empty title={tx.nothingTitle} action={<Button onClick={() => setFilters({ ...DEFAULT_FILTERS })}>{tx.filter.reset}</Button>}>
              {tx.nothingText}
            </Empty>
          ) : (
            <Compare data={data} categories={everything.data?.options} chart={settings.chart} onChart={setChart} selected={selected} onSelect={select} />
          )}
        </Section>

        {(data.summary.length > 0 || hasExcluded) && (
          <Section
            title={tx.models.title}
            note={tx.models.note}
            actions={
              <Button small disabled={!hasExcluded} onClick={() => setFilters({ ...settings.filters, excluded: [] })}>
                {tx.models.showAll}
              </Button>
            }
          >
            <ModelTable
              rows={tableRows}
              runs={data.runs}
              selected={selected}
              onSelect={select}
              available={data.options.excluded ?? []}
              excluded={settings.filters.excluded}
              onExcluded={(excluded) => setFilters({ ...settings.filters, excluded })}
            />
          </Section>
        )}

        {data.runs.length > 0 && (
          <Section title={tx.runs.title} note={tx.runs.note(data.runs.length)}>
            <RunsTable runs={data.runs} selected={selected} />
          </Section>
        )}

        {data.summary.length > 0 && (
          <Section title={tx.charts.title} note={tx.charts.note}>
            <ModelCharts summary={data.summary} runs={data.runs} vendors={everything.data?.options.vendors ?? data.options.vendors} selected={selected} />
          </Section>
        )}
      </>
    )
  }

  return (
    <Page
      title={tx.title}
      actions={noRuns ? undefined : actions}
      meta={noRuns ? undefined : meta}
      aside={noRuns || !current ? undefined : <Filters data={data} all={everything.data?.runs} filters={current.settings.filters} onChange={setFilters} />}
      asideLabel={tx.filter.title}
    >
      <ErrorNote error={views.error} />
      {body}
      {dialog && current && (
        <ViewsDialog
          views={viewList}
          current={current.settings}
          activeName={current.view}
          onLoad={(view) => {
            loadView(view)
            setDialog(false)
          }}
          onSaved={(name) => apply({ ...current, view: name })}
          onClose={() => setDialog(false)}
        />
      )}
    </Page>
  )
}
