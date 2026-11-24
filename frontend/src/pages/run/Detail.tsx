// Lauf-Detail: Kopf, Kennzahlen, Anforderungen, Zeitleiste, Prüfung, Antwort, Protokoll, Umgebung.
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { api, ApiError } from '../../api'
import { dateTime, duration, num, tokens } from '../../format'
import { t } from '../../texts'
import { Button, Dialog, Empty, ErrorNote, Field, Figure, Glyph, Loading, Notice, Page, RunState, Section, Tag, useToast, Verdict } from '../../ui'
import { money } from '../analysis/model'
import { StepTokens, Timeline, type RunEvent } from './Charts'
import { Fold, Log, LongText } from './Log'

const tx = t.run

type Point = { nr: number | string; ok: boolean; text: string }
type Verification = {
  verifier: string | null
  status: string
  reason: string | null
  points: Point[]
  write_attempts: string[]
  seconds: number | null
  tokens_input: number | null
  tokens_output: number | null
  cost_usd: number | null
  cost_source: string | null
  answer: string | null
  attempts: number | null
  earlier_cost: number | null
}
type Requirement = { name: string; reached: boolean; first_second: number | null; calls: number; errors: number }
type RunData = {
  id: number
  run_code: string
  batch_id: number
  code: string
  label: string
  model_id: string
  vendor: string
  platform_name: string
  task_id: string
  task_version: number
  task_title: string
  status: string
  finish_reason: string | null
  verify_status: string
  bw_system: string | null
  mcp_server: string | null
  agent_label: string | null
  thinking_label: string
  thinking_effective: boolean
  repeat: number | null
  started: string | null
  finished: string | null
  seconds: number | null
  model_seconds: number | null
  tool_seconds: number | null
  steps: number | null
  tool_calls: number | null
  tool_errors: number | null
  api_retries: number | null
  tokens_input: number | null
  tokens_new: number | null
  tokens_cache_read: number | null
  tokens_cache_write: number | null
  tokens_output: number | null
  tokens_reasoning: number | null
  cost: number | null
  cost_source: string | null
  verify_cost: number | null
  invalid: string | null
  hidden: string | null
  error: string | null
  error_kind: string | null
  answer: string | null
  last_requirement: string | null
  batch_note: string | null
  checkpoints: number | null
  verification: Verification | null
  requirements: Requirement[]
  events: RunEvent[]
  retried_as: { id: number; run_code: string } | null
  retry_of_run: { id: number; run_code: string } | null
  environment: Record<string, any>
}

export function Detail({ id }: { id: string }) {
  const [dialog, setDialog] = useState(false)
  const run = useQuery<RunData>({
    queryKey: ['run', id],
    queryFn: () => api.get(`/runs/${encodeURIComponent(id)}`),
    retry: (count, error) => !(error instanceof ApiError && error.status >= 400 && error.status < 500) && count < 1,
    refetchInterval: (query) => (['planned', 'running'].includes(query.state.data?.status ?? '') ? 3000 : false),
  })

  const toList = (
    <Link className="btn" to="/lauf">
      {tx.toList}
    </Link>
  )

  if (run.isPending) {
    return (
      <Page title={tx.pick.title} actions={toList}>
        <Loading lines={5} />
      </Page>
    )
  }
  if (!run.data) {
    // 404: unbekannte Nummer; 422: keine Zahl in der Adresse.
    const unknown = run.error instanceof ApiError && (run.error.status === 404 || run.error.status === 422)
    return (
      <Page title={tx.pick.title} actions={unknown ? undefined : toList}>
        {unknown ? (
          <Empty title={tx.unknownTitle} action={<Link className="btn btn--primary" to="/lauf">{tx.unknownAction}</Link>}>
            {tx.unknownText(id)}
          </Empty>
        ) : (
          <ErrorNote error={run.error} />
        )}
      </Page>
    )
  }

  const data = run.data
  const open = ['planned', 'running'].includes(data.status)

  return (
    <Page
      title={tx.title(data.run_code)}
      lead={[data.label, data.task_title].filter(Boolean).join(' · ')}
      actions={
        <>
          {toList}
          <Button variant={data.invalid ? 'default' : 'danger'} onClick={() => setDialog(true)}>
            {data.invalid ? tx.invalid.release : tx.invalid.mark}
          </Button>
        </>
      }
    >
      <Section>
        <div className="stack">
          {open && <Notice>{tx.notes.running}</Notice>}
          {data.invalid && <Notice kind="warn">{tx.notes.invalid(data.invalid)}</Notice>}
          {data.hidden && <Notice kind="warn">{tx.notes.hidden(data.hidden)}</Notice>}
          {data.retried_as && (
            <Notice>
              {tx.notes.retriedAs} <Link to={`/lauf/${data.retried_as.id}`}>{data.retried_as.run_code}</Link>
            </Notice>
          )}
          {data.retry_of_run && (
            <Notice>
              {tx.notes.retryOf} <Link to={`/lauf/${data.retry_of_run.id}`}>{data.retry_of_run.run_code}</Link>
            </Notice>
          )}
          <Head data={data} />
        </div>
      </Section>

      <Section title={tx.figures.title}>
        <Figures data={data} />
      </Section>

      {data.error && (
        <Section title={tx.answer.errorTitle}>
          <Notice kind="error">
            {data.error_kind && (
              <p className="small" style={{ marginBottom: 4 }}>
                {tx.answer.errorKind}: <Tag>{data.error_kind}</Tag>
              </p>
            )}
            <span style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{data.error}</span>
          </Notice>
        </Section>
      )}

      <Section title={tx.requirements.title} note={tx.requirements.note}>
        <Requirements list={data.requirements} last={data.last_requirement} />
      </Section>

      <Section title={tx.timeline.title} note={tx.timeline.note}>
        <Timeline events={data.events} runSeconds={data.seconds} verifySeconds={data.verification?.seconds ?? null} code={data.run_code} />
      </Section>

      <Section title={tx.usage.title} note={tx.usage.note}>
        <StepTokens events={data.events} code={data.run_code} />
      </Section>

      <Section title={tx.verify.title}>
        <Verify data={data} />
      </Section>

      <Section title={tx.answer.title}>
        {data.answer ? (
          <div className="panel">
            <LongText text={data.answer} limit={3000} />
          </div>
        ) : (
          <p className="muted">{tx.answer.none}</p>
        )}
      </Section>

      <Section title={tx.log.title} note={tx.log.note}>
        <Log runId={data.id} />
      </Section>

      <Section title={tx.env.title} note={tx.env.note}>
        <Environment env={data.environment} />
      </Section>

      {dialog && <InvalidDialog run={data} onClose={() => setDialog(false)} />}
    </Page>
  )
}

// --------------------------------------------------------------------------- Kopf

function Pair({ label, children }: { label: string; children: ReactNode }) {
  return (
    <>
      <dt>{label}</dt>
      <dd>{children}</dd>
    </>
  )
}

function Head({ data }: { data: RunData }) {
  const reason = data.finish_reason ? (tx.finishReason[data.finish_reason] ?? data.finish_reason) : ''
  return (
    <div className="panel grid grid--2">
      <dl className="kv">
        <Pair label={tx.head.entry}>
          <strong>{data.label}</strong>
        </Pair>
        <Pair label={tx.head.model}>
          <span className="mono">{data.model_id}</span>
          <br />
          <span className="secondary">
            {data.vendor} · {data.platform_name}
          </span>
        </Pair>
        <Pair label={tx.head.task}>
          <Link to={`/aufgaben/${encodeURIComponent(data.task_id)}`}>{data.task_id}</Link> · {tx.head.version(data.task_version)}
          {data.task_title && (
            <>
              <br />
              <span className="secondary">{data.task_title}</span>
            </>
          )}
        </Pair>
        <Pair label={tx.head.verdict}>
          <Verdict status={data.verify_status} />
        </Pair>
        <Pair label={tx.head.status}>
          <RunState status={data.status} />
          {reason && <span className="secondary"> · {reason}</span>}
        </Pair>
        {data.last_requirement && <Pair label={tx.head.lastRequirement}>{data.last_requirement}</Pair>}
      </dl>
      <dl className="kv">
        <Pair label={tx.head.system}>{data.bw_system || t.common.none}</Pair>
        <Pair label={tx.head.mcp}>{data.mcp_server || t.common.none}</Pair>
        <Pair label={tx.head.agent}>{data.agent_label || t.common.none}</Pair>
        <Pair label={tx.head.thinking}>
          {data.thinking_label}{' '}
          {data.thinking_effective === false && (
            <span className="state state--warn" title={tx.head.noEffectHint}>
              <Glyph kind="warn" />
              {tx.head.noEffect}
            </span>
          )}
        </Pair>
        <Pair label={tx.head.batch}>
          <Link to={`/live?durchgang=${data.batch_id}`}>{data.code}</Link>
          {data.repeat ? <span className="secondary"> · {tx.head.repeat(data.repeat)}</span> : null}
          {data.batch_note && <span className="secondary"> · {data.batch_note}</span>}
        </Pair>
        <Pair label={tx.head.started}>
          <span className="num">{dateTime(data.started)}</span>
        </Pair>
        {data.finished && (
          <Pair label={tx.head.finished}>
            <span className="num">{dateTime(data.finished)}</span>
          </Pair>
        )}
      </dl>
    </div>
  )
}

// --------------------------------------------------------------------------- Kennzahlen

function Figures({ data }: { data: RunData }) {
  const sub = (title: string, ...lines: (string | false | null | undefined)[]) => (
    <>
      {title}
      {lines.filter(Boolean).map((line) => (
        <span key={String(line)} className="run-figure__sub">
          {line}
        </span>
      ))}
    </>
  )
  const costLine = data.cost === null ? tx.figures.costNoPrice : data.cost === 0 && !data.cost_source ? tx.figures.costFree : (t.common.costSource[data.cost_source ?? ''] ?? data.cost_source)
  const earlier = data.verification?.earlier_cost
  return (
    <div className="figures run-figures">
      <Figure
        value={duration(data.seconds)}
        label={sub(tx.figures.seconds, data.model_seconds !== null || data.tool_seconds !== null ? tx.figures.secondsSplit(duration(data.model_seconds), duration(data.tool_seconds)) : null)}
      />
      <Figure value={num(data.steps)} label={sub(tx.figures.steps, data.api_retries ? tx.figures.retries(data.api_retries) : null)} />
      <Figure value={num(data.tool_calls)} label={sub(tx.figures.toolCalls, data.tool_calls !== null && tx.figures.toolErrors(data.tool_errors ?? 0))} />
      <Figure
        value={tokens(data.tokens_input)}
        label={sub(
          tx.figures.tokensIn,
          data.tokens_input !== null && tx.figures.tokensInSplit(num(data.tokens_new), num(data.tokens_cache_read)),
          data.tokens_cache_write ? tx.figures.cacheWrite(num(data.tokens_cache_write)) : null,
        )}
      />
      <Figure
        value={tokens(data.tokens_output)}
        label={sub(tx.figures.tokensOut, data.tokens_reasoning !== null ? tx.figures.reasoning(num(data.tokens_reasoning)) : tx.figures.reasoningUnknown)}
      />
      <Figure value={money(data.cost)} label={sub(tx.figures.cost, costLine)} />
      <Figure
        value={data.verify_cost === null ? t.common.none : money(data.verify_cost)}
        label={sub(tx.figures.verifyCost, data.verification?.verifier ? null : tx.figures.verifyNone, earlier ? tx.figures.verifyEarlier(money(earlier)) : null)}
      />
    </div>
  )
}

// --------------------------------------------------------------------------- Anforderungen

function Requirements({ list, last }: { list: Requirement[]; last: string | null }) {
  if (list.length === 0) return <p className="muted">{tx.requirements.none}</p>
  const reached = list.filter((r) => r.reached).length
  return (
    <>
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>{tx.requirements.col.name}</th>
              <th>{tx.requirements.col.state}</th>
              <th className="right">{tx.requirements.col.first}</th>
              <th className="right">{tx.requirements.col.calls}</th>
              <th className="right">{tx.requirements.col.errors}</th>
            </tr>
          </thead>
          <tbody>
            {list.map((req) => (
              <tr key={req.name}>
                <td>{req.name}</td>
                <td>
                  <span className={`state state--${req.reached ? 'pass' : 'neutral'}`}>
                    <Glyph kind={req.reached ? 'pass' : 'open'} />
                    {req.reached ? tx.requirements.reached : tx.requirements.open}
                  </span>
                </td>
                <td className="right num">{req.first_second === null ? t.common.none : `${num(req.first_second, 1)} s`}</td>
                <td className="right num">{num(req.calls)}</td>
                <td className="right num">
                  {req.errors > 0 ? (
                    <span className="state state--fail">
                      <Glyph kind="fail" />
                      {num(req.errors)}
                    </span>
                  ) : (
                    num(req.errors)
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="muted small" style={{ marginTop: 8 }}>
        {tx.requirements.summary(reached, list.length)}
        {last && ` · ${tx.head.lastRequirement}: ${last}`}
      </p>
    </>
  )
}

// --------------------------------------------------------------------------- Prüfung

function Verify({ data }: { data: RunData }) {
  const v = data.verification
  if (!v) return <p className="muted">{tx.verify.none}</p>
  const points = Array.isArray(v.points) ? v.points : []
  const ok = points.filter((p) => p.ok).length
  const writes = Array.isArray(v.write_attempts) ? v.write_attempts : []
  return (
    <div className="stack">
      {writes.length > 0 && <Notice kind="warn">{tx.verify.writeAttempts(writes.join(', '))}</Notice>}
      <div className="panel">
        <dl className="kv">
          <Pair label={tx.verify.verdict}>
            <Verdict status={v.status} />
          </Pair>
          <Pair label={tx.verify.verifier}>{v.verifier ? <span className="mono">{v.verifier}</span> : t.common.none}</Pair>
          {v.reason && <Pair label={tx.verify.reason}>{v.reason}</Pair>}
          {v.attempts !== null && v.attempts > 1 && <Pair label={tx.verify.attempts}>{num(v.attempts)}</Pair>}
          {v.seconds !== null && <Pair label={tx.verify.seconds}>{duration(v.seconds)}</Pair>}
          {v.tokens_input !== null && (
            <Pair label={tx.verify.tokens}>
              <span className="num">
                {num(v.tokens_input)} / {num(v.tokens_output)}
              </span>
            </Pair>
          )}
          {v.verifier && (
            <Pair label={tx.verify.cost}>
              <span className="num">{v.cost_usd === null ? t.common.noPrice : money(v.cost_usd)}</span>
              {v.cost_source && <span className="secondary"> · {t.common.costSource[v.cost_source] ?? v.cost_source}</span>}
              {v.earlier_cost ? <span className="secondary"> · {tx.figures.verifyEarlier(money(v.earlier_cost))}</span> : null}
            </Pair>
          )}
        </dl>
      </div>

      <div>
        <div className="row row--between" style={{ marginBottom: 8 }}>
          <strong>{tx.verify.pointsTitle}</strong>
          {points.length > 0 && <span className="muted small">{tx.verify.pointsSummary(ok, points.length)}</span>}
        </div>
        {points.length === 0 ? (
          <p className="muted">{tx.verify.pointsNone}</p>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>{tx.verify.col.nr}</th>
                  <th>{tx.verify.col.result}</th>
                  <th>{tx.verify.col.text}</th>
                </tr>
              </thead>
              <tbody>
                {points.map((point, index) => (
                  <tr key={`${point.nr}-${index}`}>
                    <td className="num">{point.nr}</td>
                    <td>
                      <span className={`state state--${point.ok ? 'pass' : 'fail'}`}>
                        <Glyph kind={point.ok ? 'pass' : 'fail'} />
                        {point.ok ? tx.verify.ok : tx.verify.failed}
                      </span>
                    </td>
                    <td style={{ overflowWrap: 'anywhere' }}>{point.text}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {data.checkpoints !== null && data.checkpoints !== points.length && points.length > 0 && (
          <p className="muted small" style={{ marginTop: 8 }}>
            {tx.verify.pointsExpected(data.checkpoints)}
          </p>
        )}
      </div>

      {v.answer && <Fold label={tx.verify.answer} text={v.answer} />}
    </div>
  )
}

// --------------------------------------------------------------------------- Umgebung

function Environment({ env }: { env: Record<string, any> }) {
  if (!env || Object.keys(env).length === 0) return <p className="muted">{tx.env.none}</p>
  const system = env.bw_system && typeof env.bw_system === 'object' ? env.bw_system : null
  const mcp = env.mcp_server && typeof env.mcp_server === 'object' ? env.mcp_server : null
  const tools: { name: string; access?: string }[] = Array.isArray(mcp?.tools) ? mcp.tools : []
  const platforms = env.platforms && typeof env.platforms === 'object' ? Object.entries(env.platforms as Record<string, any>) : []
  return (
    <details className="run-fold">
      <summary>{tx.env.show}</summary>
      <div className="stack" style={{ marginTop: 12 }}>
        <dl className="kv">
          {env.app_version && <Pair label={tx.env.app}>{String(env.app_version)}</Pair>}
          {env.agent && <Pair label={tx.env.agent}>{[env.agent, env.agent_version].filter(Boolean).join(' ')}</Pair>}
          {system && (
            <>
              <Pair label={tx.env.system}>{String(system.id ?? t.common.none)}</Pair>
              {system.url && <Pair label={tx.env.url}>{String(system.url)}</Pair>}
              {system.parent_area && <Pair label={tx.env.parentArea}>{String(system.parent_area)}</Pair>}
              {system.area_pattern && <Pair label={tx.env.areaPattern}>{String(system.area_pattern)}</Pair>}
              {system.prefix && <Pair label={tx.env.prefix}>{String(system.prefix)}</Pair>}
            </>
          )}
          {mcp && (
            <>
              <Pair label={tx.env.mcp}>{String(mcp.name ?? t.common.none)}</Pair>
              {mcp.server_name && <Pair label={tx.env.mcpServer}>{[mcp.server_name, mcp.server_version].filter(Boolean).join(' ')}</Pair>}
              {mcp.transport && <Pair label={tx.env.transport}>{String(mcp.transport)}</Pair>}
              {typeof mcp.tool_count === 'number' && (
                <Pair label={tx.env.tools}>
                  {tx.env.toolsCount(mcp.tool_count, num(mcp.token_estimate))}
                  {tools.length > 0 && (
                    <span className="run-tags" style={{ marginTop: 6 }}>
                      {tools.map((tool) => (
                        <Tag key={tool.name} title={tool.access === 'write' ? tx.env.write : tool.access === 'read' ? tx.env.read : undefined}>
                          {tool.name}
                          {tool.access ? ` · ${tool.access === 'write' ? tx.env.write : tx.env.read}` : ''}
                        </Tag>
                      ))}
                    </span>
                  )}
                </Pair>
              )}
            </>
          )}
          {platforms.map(([id, platform]) => (
            <Pair key={id} label={`${tx.env.caching} ${id}`}>
              {platform?.caching ? tx.env.cachingOn : tx.env.cachingOff}
            </Pair>
          ))}
        </dl>
        {env.system_prompt && <Fold label={tx.env.systemPrompt} text={String(env.system_prompt)} />}
        <Fold label={tx.env.raw} text={JSON.stringify(env, null, 2)} />
      </div>
    </details>
  )
}

// --------------------------------------------------------------------------- Gültigkeit

function InvalidDialog({ run, onClose }: { run: RunData; onClose: () => void }) {
  const toast = useToast()
  const client = useQueryClient()
  const releasing = Boolean(run.invalid)
  const [reason, setReason] = useState('')
  const save = useMutation({
    // Leerer Grund gibt den Lauf wieder frei.
    mutationFn: () => api.post(`/runs/${run.id}/invalid`, { reason: releasing ? '' : reason.trim() }),
    onSuccess: async () => {
      toast(releasing ? tx.invalid.released : tx.invalid.marked)
      await Promise.all(['run', 'runs', 'analysis', 'leaderboard', 'batches'].map((key) => client.invalidateQueries({ queryKey: [key] })))
      onClose()
    },
  })
  return (
    <Dialog
      title={releasing ? tx.invalid.releaseTitle(run.run_code) : tx.invalid.markTitle(run.run_code)}
      onClose={onClose}
      footer={
        <>
          <Button onClick={onClose}>{t.common.actions.cancel}</Button>
          <Button variant={releasing ? 'primary' : 'danger'} busy={save.isPending} disabled={!releasing && !reason.trim()} onClick={() => save.mutate()}>
            {releasing ? tx.invalid.release : tx.invalid.mark}
          </Button>
        </>
      }
    >
      <div className="stack">
        {releasing ? (
          <p className="secondary">{tx.invalid.releaseText(run.invalid ?? '')}</p>
        ) : (
          <>
            <p className="secondary">{tx.invalid.markText}</p>
            <Field label={tx.invalid.reason} hint={tx.invalid.reasonHint}>
              <textarea className="textarea" rows={3} value={reason} placeholder={tx.invalid.reasonPlaceholder} maxLength={300} onChange={(e) => setReason(e.target.value)} />
            </Field>
          </>
        )}
        <ErrorNote error={save.error} />
      </div>
    </Dialog>
  )
}
