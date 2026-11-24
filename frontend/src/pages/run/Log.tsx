// Protokoll eines Laufs oder seiner Prüfung, lesbar aufbereitet.
import { useQuery } from '@tanstack/react-query'
import { useState, type ReactNode } from 'react'
import { api } from '../../api'
import { duration, num, usd } from '../../format'
import { t } from '../../texts'
import { Button, ErrorNote, Glyph, Loading, Notice, Tabs, Tag } from '../../ui'

const tx = t.run.log
const PAGE = 200

type LogData = { available: boolean; format?: 'jsonl' | 'text'; entries: Record<string, any>[]; text: string; truncated: boolean }
type Phase = 'task' | 'verify'

export function Log({ runId }: { runId: number }) {
  const [phase, setPhase] = useState<Phase>('task')
  const log = useQuery<LogData>({ queryKey: ['run-log', runId, phase], queryFn: () => api.get(`/runs/${runId}/log?phase=${phase}`) })

  return (
    <div>
      <Tabs
        tabs={[
          { id: 'task', label: tx.task },
          { id: 'verify', label: tx.verify },
        ]}
        value={phase}
        onChange={setPhase}
      />
      {log.isPending && <Loading />}
      <ErrorNote error={log.error} />
      {log.data && <LogBody key={phase} data={log.data} />}
    </div>
  )
}

function LogBody({ data }: { data: LogData }) {
  const [limit, setLimit] = useState(PAGE)
  if (!data.available) return <Notice>{tx.missing}</Notice>
  return (
    <div className="stack">
      {data.truncated && <Notice kind="warn">{tx.truncated}</Notice>}
      {data.format === 'text' ? (
        <>
          <div>
            <strong>{tx.raw}</strong>
            <p className="muted small">{tx.rawNote}</p>
          </div>
          <pre className="run-pre run-pre--tall">{data.text}</pre>
        </>
      ) : data.entries.length === 0 ? (
        <p className="muted">{tx.emptyEntries}</p>
      ) : (
        <>
          <ol className="run-log">
            {data.entries.slice(0, limit).map((entry, index) => (
              <Entry key={index} entry={entry} />
            ))}
          </ol>
          {data.entries.length > limit && (
            <div>
              <Button small onClick={() => setLimit((n) => n + PAGE)}>
                {tx.more(Math.min(PAGE, data.entries.length - limit))}
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  )
}

function Entry({ entry }: { entry: Record<string, any> }) {
  const type = String(entry.type ?? '')
  const failed = type === 'error' || (type === 'tool_result' && Boolean(entry.is_error))
  const title = type === 'tool_result' && entry.name ? `${tx.type.tool_result}: ${entry.name}` : (tx.type[type] ?? tx.unknownType(type))
  return (
    <li className={`run-log__entry${failed ? ' run-log__entry--error' : ''}`}>
      <div className="run-log__head">
        <span className="num muted run-log__time">{typeof entry.s === 'number' ? tx.seconds(num(entry.s, 1)) : ''}</span>
        <strong>{title}</strong>
        {entry.step !== undefined && entry.step !== null && <span className="muted">{tx.step(entry.step)}</span>}
        {type === 'tool_result' && (
          <>
            {typeof entry.duration === 'number' && <span className="muted num">{tx.duration(num(entry.duration, 2))}</span>}
            <span className={`state state--${entry.is_error ? 'fail' : 'pass'}`}>
              <Glyph kind={entry.is_error ? 'fail' : 'pass'} />
              {entry.is_error ? tx.isError : tx.isOk}
            </span>
          </>
        )}
        {type === 'error' && (
          <span className="state state--fail">
            <Glyph kind="fail" />
            {tx.isError}
          </span>
        )}
      </div>
      <div className="run-log__body">
        <Body type={type} entry={entry} />
      </div>
    </li>
  )
}

function Body({ type, entry }: { type: string; entry: Record<string, any> }) {
  switch (type) {
    case 'meta':
      return <Meta entry={entry} />
    case 'response':
      return <Response entry={entry} />
    case 'tool_result':
      return <LongText text={asText(entry.text)} />
    case 'error':
      return (
        <>
          <div className="row small secondary">
            {entry.kind && (
              <span>
                {tx.kind}: <Tag>{String(entry.kind)}</Tag>
              </span>
            )}
            {entry.status !== undefined && entry.status !== null && (
              <span>
                {tx.httpStatus}: {String(entry.status)}
              </span>
            )}
          </div>
          <LongText text={asText(entry.message ?? entry.error)} />
        </>
      )
    case 'end':
      return <End entry={entry} />
    default:
      return <LongText text={pretty(strip(entry))} />
  }
}

function Meta({ entry }: { entry: Record<string, any> }) {
  const tools: string[] = Array.isArray(entry.tools) ? entry.tools.map(String) : []
  const limits = entry.limits && typeof entry.limits === 'object' ? Object.entries(entry.limits as Record<string, unknown>) : []
  return (
    <>
      <dl className="kv">
        {entry.agent && <Pair label={tx.meta.agent}>{[entry.agent, entry.agent_version].filter(Boolean).join(' ')}</Pair>}
        {entry.model && <Pair label={tx.meta.model}>{String(entry.model)}</Pair>}
        {entry.thinking !== undefined && <Pair label={tx.meta.thinking}>{t.common.thinking[entry.thinking ?? ''] ?? String(entry.thinking)}</Pair>}
        {typeof entry.caching === 'boolean' && <Pair label={tx.meta.caching}>{entry.caching ? t.common.yes : t.common.no}</Pair>}
        {tools.length > 0 && (
          <Pair label={`${tx.meta.tools} (${tools.length})`}>
            <span className="run-tags">
              {tools.map((name) => (
                <Tag key={name}>{name}</Tag>
              ))}
            </span>
          </Pair>
        )}
        {limits.length > 0 && <Pair label={tx.meta.limits}>{limits.map(([key, v]) => `${tx.limits[key] ?? key} ${String(v)}`).join(' · ')}</Pair>}
      </dl>
      {entry.system && <Fold label={tx.meta.system} text={asText(entry.system)} />}
      {entry.prompt && <Fold label={tx.meta.prompt} text={asText(entry.prompt)} />}
    </>
  )
}

function Response({ entry }: { entry: Record<string, any> }) {
  const calls: Record<string, any>[] = Array.isArray(entry.tool_calls) ? entry.tool_calls : []
  const usage = entry.usage && typeof entry.usage === 'object' ? entry.usage : null
  const text = asText(entry.text)
  return (
    <>
      {usage && (
        <p className="small muted num">
          {tx.usage(num(usage.input_total), num(usage.cache_read ?? 0), num(usage.output))}
          {typeof usage.reasoning === 'number' && ` · ${tx.reasoning(num(usage.reasoning))}`}
          {entry.stop && ` · ${tx.stop}: ${String(entry.stop)}`}
        </p>
      )}
      {text ? <LongText text={text} /> : calls.length === 0 && <p className="muted small">{tx.noText}</p>}
      {calls.map((call, index) => {
        const unreadable = call.arguments === null || call.arguments === undefined
        const args = unreadable ? asText(call.raw) : pretty(call.arguments)
        return (
          <div key={call.id ?? index} className="run-log__call">
            <div className="row small">
              <span className="muted">{tx.call}</span>
              <strong className="mono">{String(call.name ?? '')}</strong>
              {unreadable && <Tag>{tx.badArguments}</Tag>}
            </div>
            {args && args !== '{}' ? <LongText text={args} code /> : <p className="muted small">{tx.noArguments}</p>}
          </div>
        )
      })}
    </>
  )
}

function End({ entry }: { entry: Record<string, any> }) {
  const usage = entry.usage && typeof entry.usage === 'object' ? entry.usage : null
  return (
    <>
      <dl className="kv">
        {entry.status && <Pair label={tx.status}>{t.common.runStatus[entry.status] ?? String(entry.status)}</Pair>}
        {entry.finish_reason && <Pair label={tx.summary.reason}>{t.run.finishReason[entry.finish_reason] ?? String(entry.finish_reason)}</Pair>}
        {entry.steps !== undefined && <Pair label={tx.summary.steps}>{num(entry.steps)}</Pair>}
        {entry.tool_calls !== undefined && <Pair label={tx.summary.toolCalls}>{num(entry.tool_calls)}</Pair>}
        {typeof entry.seconds === 'number' && <Pair label={tx.summary.seconds}>{duration(entry.seconds)}</Pair>}
        {usage && <Pair label={tx.summary.tokens}>{tx.usage(num(usage.input_total), num(usage.cache_read ?? 0), num(usage.output))}</Pair>}
        {'cost' in entry && <Pair label={tx.summary.cost}>{usd(entry.cost)}</Pair>}
      </dl>
      {entry.error && <LongText text={asText(entry.error)} />}
    </>
  )
}

function Pair({ label, children }: { label: string; children: ReactNode }) {
  return (
    <>
      <dt>{label}</dt>
      <dd>{children}</dd>
    </>
  )
}

/** Langer Text klappt ein: Der Anfang bleibt lesbar, der Rest öffnet sich auf Wunsch. */
export function LongText({ text, code, limit = 700 }: { text: string; code?: boolean; limit?: number }) {
  const [open, setOpen] = useState(false)
  if (!text) return null
  const lines = text.split('\n')
  const long = text.length > limit || lines.length > 14
  const shown = long && !open ? `${lines.slice(0, 14).join('\n').slice(0, limit).trimEnd()} …` : text
  return (
    <div>
      <pre className={`run-pre${code ? ' run-pre--code' : ''}`}>{shown}</pre>
      {long && (
        <Button small variant="quiet" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
          {open ? t.common.actions.close : tx.expand(num(text.length))}
        </Button>
      )}
    </div>
  )
}

/** Eingeklappter Abschnitt mit Überschrift, z. B. Systemtext. */
export function Fold({ label, text }: { label: string; text: string }) {
  return (
    <details className="run-fold">
      <summary>{label}</summary>
      <pre className="run-pre">{text}</pre>
    </details>
  )
}

function asText(value: unknown): string {
  if (value === null || value === undefined) return ''
  return typeof value === 'string' ? value : pretty(value)
}

function pretty(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2) ?? ''
  } catch {
    return String(value)
  }
}

function strip(entry: Record<string, any>): Record<string, any> {
  const rest = { ...entry }
  for (const key of ['ts', 's', 'type']) delete rest[key]
  return rest
}
