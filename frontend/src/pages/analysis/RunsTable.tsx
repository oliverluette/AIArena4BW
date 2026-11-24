// Tabelle der gefilterten Läufe; jede Zeile öffnet das Lauf-Detail.
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { duration, num, tokens } from '../../format'
import { t } from '../../texts'
import { Button, RunState, Tag, useSort, Verdict } from '../../ui'
import { money, type Run } from './model'

const tx = t.analysis.runs
const FIRST = 25

export function RunsTable({ runs, selected }: { runs: Run[]; selected: string | null }) {
  const navigate = useNavigate()
  const [all, setAll] = useState(false)
  const { sorted, toggle, mark } = useSort<Run>(runs, { key: 'started', dir: 'desc' })
  const shown = all ? sorted : sorted.slice(0, FIRST)

  const head = (key: string, label: string, right = false) => (
    <th className={right ? 'right' : undefined}>
      <button type="button" onClick={() => toggle(key)}>
        {label}
        {mark(key)}
      </button>
    </th>
  )

  return (
    <>
      <div className="table-wrap">
        <table className="table table--click table--dense">
          <thead>
            <tr>
              {head('run_code', tx.col.code)}
              {head('label', tx.col.label)}
              {head('model_id', tx.col.modelId)}
              {head('task', tx.col.task)}
              {head('verify_status', tx.col.verdict)}
              {head('status', tx.col.status)}
              {head('seconds', tx.col.seconds, true)}
              {head('steps', tx.col.steps, true)}
              {head('tokens_input', tx.col.tokens, true)}
              {head('cost', tx.col.cost, true)}
              {head('invalid', tx.col.note)}
            </tr>
          </thead>
          <tbody>
            {shown.map((run) => (
              <tr key={run.id} className={[!run.valid && 'is-dim', run.label === selected && 'is-sel'].filter(Boolean).join(' ') || undefined} onClick={() => navigate(`/lauf/${run.id}`)}>
                <td>
                  <Link to={`/lauf/${run.id}`} onClick={(e) => e.stopPropagation()}>
                    <strong>{run.run_code}</strong>
                  </Link>
                </td>
                <td className="nowrap">{run.label}</td>
                <td className="mono nowrap">{run.model_id}</td>
                <td className="nowrap">{run.task}</td>
                <td>
                  <Verdict status={run.verify_status} />
                </td>
                <td>
                  <RunState status={run.status} />
                </td>
                <td className="right num">{duration(run.seconds)}</td>
                <td className="right num">{num(run.steps)}</td>
                <td className="right num">
                  {tokens(run.tokens_input)} / {tokens(run.tokens_output)}
                </td>
                <td className="right num">{money(run.cost)}</td>
                <td className="secondary">
                  {run.invalid && (
                    <>
                      <Tag title={run.invalid}>{tx.invalid}</Tag> {run.invalid}{' '}
                    </>
                  )}
                  {run.hidden && <Tag title={run.hidden}>{tx.hidden}</Tag>} {run.retry_of && <Tag>{tx.retry}</Tag>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!all && sorted.length > FIRST && (
        <p style={{ marginTop: 8 }}>
          <Button small onClick={() => setAll(true)}>
            {tx.more(sorted.length)}
          </Button>
        </p>
      )}
    </>
  )
}
