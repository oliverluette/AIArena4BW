// Laufauswahl: eingrenzen nach Anbieter und Modell-Eintrag, Zeile öffnet den Lauf.
import { useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../../api'
import { dateTime } from '../../format'
import { t } from '../../texts'
import { Button, Chips, Empty, ErrorNote, Field, Loading, Page, Section, Tag, Verdict } from '../../ui'

const tx = t.run.pick
const FIRST = 200

type Item = { id: number; run_code: string; code: string; label: string; vendor: string; task: string; verify_status: string; status: string; valid: boolean; started: string | null }

export function Picker() {
  const navigate = useNavigate()
  const runs = useQuery<Item[]>({ queryKey: ['runs'], queryFn: () => api.get('/runs') })
  const [vendors, setVendors] = useState<string[]>([])
  const [label, setLabel] = useState('')
  const [all, setAll] = useState(false)

  const list = useMemo(() => runs.data ?? [], [runs.data])
  const vendorOptions = useMemo(() => [...new Set(list.map((r) => r.vendor))].sort((a, b) => a.localeCompare(b, 'de')), [list])
  const byVendor = useMemo(() => (vendors.length ? list.filter((r) => vendors.includes(r.vendor)) : list), [list, vendors])
  const labelOptions = useMemo(() => [...new Set(byVendor.map((r) => r.label))].sort((a, b) => a.localeCompare(b, 'de')), [byVendor])
  // Passt der gewählte Eintrag nicht mehr zum Anbieter, gilt er nicht.
  const activeLabel = labelOptions.includes(label) ? label : ''
  const rows = activeLabel ? byVendor.filter((r) => r.label === activeLabel) : byVendor
  const shown = all ? rows : rows.slice(0, FIRST)

  if (runs.isPending) {
    return (
      <Page title={tx.title} lead={tx.lead}>
        <Loading lines={5} />
      </Page>
    )
  }
  if (list.length === 0) {
    return (
      <Page title={tx.title} lead={tx.lead}>
        <ErrorNote error={runs.error} />
        {!runs.error && (
          <Empty title={tx.emptyTitle} action={<Link className="btn btn--primary" to="/start">{tx.emptyAction}</Link>}>
            {tx.emptyText}
          </Empty>
        )}
      </Page>
    )
  }

  return (
    <Page title={tx.title} lead={tx.lead}>
      <Section>
        <div className="panel run-pick">
          <div className="field">
            <span className="field__label">{tx.vendor}</span>
            <Chips options={vendorOptions} value={vendors} onChange={setVendors} ariaLabel={tx.vendor} />
          </div>
          <Field label={tx.model}>
            <select className="select" value={activeLabel} onChange={(e) => setLabel(e.target.value)}>
              <option value="">{tx.modelAll}</option>
              {labelOptions.map((o) => (
                <option key={o} value={o}>
                  {o}
                </option>
              ))}
            </select>
          </Field>
        </div>
      </Section>

      <Section note={tx.count(rows.length, list.length)}>
        {rows.length === 0 ? (
          <Empty
            title={tx.nothing}
            action={
              <Button
                onClick={() => {
                  setVendors([])
                  setLabel('')
                }}
              >
                {tx.reset}
              </Button>
            }
          />
        ) : (
          <div className="table-wrap">
            <table className="table table--click">
              <thead>
                <tr>
                  <th>{tx.col.code}</th>
                  <th>{tx.col.label}</th>
                  <th>{tx.col.task}</th>
                  <th>{tx.col.verdict}</th>
                  <th>{tx.col.date}</th>
                </tr>
              </thead>
              <tbody>
                {shown.map((run) => (
                  <tr key={run.id} className={run.valid ? undefined : 'is-dim'} onClick={() => navigate(`/lauf/${run.id}`)}>
                    <td>
                      <Link to={`/lauf/${run.id}`} onClick={(e) => e.stopPropagation()}>
                        <strong>{run.run_code}</strong>
                      </Link>{' '}
                      {!run.valid && <Tag>{tx.invalid}</Tag>}
                    </td>
                    <td>
                      {run.label} <span className="muted">· {run.vendor}</span>
                    </td>
                    <td className="secondary">{run.task}</td>
                    <td>
                      <Verdict status={run.verify_status} />
                    </td>
                    <td className="num secondary">{dateTime(run.started)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {!all && rows.length > FIRST && (
          <p style={{ marginTop: 12 }}>
            <Button small onClick={() => setAll(true)}>
              {tx.more(rows.length)}
            </Button>
          </p>
        )}
      </Section>
    </Page>
  )
}
