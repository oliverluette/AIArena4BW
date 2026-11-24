// Einstellungen > MCP-Server: JSON-Editor mit Prüfung, Test je Server, Einstufung der Werkzeuge,
// Umgebungswerte der Prüfung, benannte Geheimnisse.
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Fragment, useState, type FormEvent } from 'react'
import { api, errorText } from '../../api'
import { dateTime, num } from '../../format'
import { t } from '../../texts'
import { Button, Empty, ErrorNote, Field, Figure, Glyph, Loading, Notice, Section, Tag, useToast } from '../../ui'
import {
  Confirm,
  FormFoot,
  Modal,
  SecretState,
  useBwSystems,
  useDebounced,
  useMeta,
  useRefresh,
  type Access,
  type BwSystem,
  type McpData,
  type McpServer,
  type McpTest,
  type McpTool,
  type Secret,
} from './shared'

const tx = t.settings.mcp
const serverPath = (name: string) => `/mcp/${encodeURIComponent(name)}`

type Validation = { ok: boolean; message?: string; servers?: string[]; warnings?: string[] }

export default function McpServers() {
  const mcp = useQuery<McpData>({ queryKey: ['mcp'], queryFn: () => api.get('/mcp') })
  const secrets = useQuery<Secret[]>({ queryKey: ['secrets'], queryFn: () => api.get('/secrets') })
  const systems = useBwSystems()
  const meta = useMeta()

  if (mcp.isLoading) return <Loading />
  if (!mcp.data) return <ErrorNote error={mcp.error} />
  return (
    <div role="tabpanel">
      <Section title={tx.title} note={tx.note}>
        <div className="grid grid--side">
          <Editor data={mcp.data} secrets={secrets.data} />
          <aside className="stack">
            <Notice kind="warn">{tx.trust}</Notice>
            <div className="panel">
              <h3 className="settings-subtitle">{tx.placeholders.title}</h3>
              <p className="muted small">{tx.placeholders.note}</p>
              <dl className="kv settings-placeholders">
                {(meta.data?.bw_placeholders ?? []).map((name) => (
                  <Fragment key={name}>
                    <dt className="mono">{`\${${name}}`}</dt>
                    <dd>{tx.placeholders.bw[name] ?? ''}</dd>
                  </Fragment>
                ))}
                <dt className="mono">{'${SECRET:name}'}</dt>
                <dd>{tx.placeholders.secret}</dd>
              </dl>
            </div>
          </aside>
        </div>
      </Section>

      <Servers servers={mcp.data.servers} systems={systems.data ?? []} />
      <Secrets secrets={secrets.data} loading={secrets.isLoading} error={secrets.error} />
    </div>
  )
}

// --------------------------------------------------------------------------- Editor

function Editor({ data, secrets }: { data: McpData; secrets: Secret[] | undefined }) {
  const toast = useToast()
  const refresh = useRefresh()
  const client = useQueryClient()
  const [draft, setDraft] = useState<string | null>(null)
  const text = draft ?? data.text
  const dirty = text !== data.text
  const settled = useDebounced(text, 350)
  const check = useQuery<Validation>({
    queryKey: ['mcp-validate', settled],
    queryFn: () => api.post('/mcp/validate', { text: settled }),
    placeholderData: keepPreviousData,
    staleTime: 60_000,
    gcTime: 60_000,
  })
  const checking = settled !== text || check.isFetching
  const result = check.data

  const save = useMutation({
    mutationFn: () => api.put<McpData>('/mcp', { text }),
    onSuccess: (saved) => {
      client.setQueryData<McpData>(['mcp'], (old) => ({ ...old, ...saved }))
      setDraft(null)
      toast(tx.saved)
      refresh('mcp')
    },
  })

  // Was das Speichern bewirkt, bevor es geschieht: Server, die im Text fehlen, verschwinden.
  const dropped = dirty && result?.ok ? data.servers.map((s) => s.name).filter((name) => !result.servers?.includes(name)) : []
  const known = new Set((secrets ?? []).filter((s) => s.set).map((s) => s.name))
  const missingSecrets = secrets ? [...new Set([...text.matchAll(/\$\{SECRET:([^}]+)\}/g)].map((m) => m[1]))].filter((name) => !known.has(name)) : []
  const needsPath = !!data.path_hint && text.includes(data.path_hint)

  return (
    <div className="stack">
      <textarea
        className="textarea textarea--code settings-editor"
        aria-label={tx.editorLabel}
        spellCheck={false}
        autoCapitalize="off"
        autoCorrect="off"
        value={text}
        onChange={(event) => {
          setDraft(event.target.value)
          if (save.error) save.reset()
        }}
      />
      <div className="row row--between">
        <span aria-live="polite">
          {checking ? (
            <span className="muted">{tx.checking}</span>
          ) : result?.ok ? (
            <span className="state state--pass">
              <Glyph kind="pass" />
              {tx.valid(result.servers ?? [])}
            </span>
          ) : result ? (
            <span className="state state--fail">
              <Glyph kind="fail" />
              {tx.invalid}
            </span>
          ) : null}
          {dirty && !checking && <span className="muted"> · {tx.unsaved}</span>}
        </span>
        <span className="row">
          <Button disabled={!dirty} onClick={() => setDraft(null)}>
            {tx.discard}
          </Button>
          <Button variant="primary" busy={save.isPending} disabled={!dirty || (!checking && result?.ok === false)} onClick={() => save.mutate()}>
            {tx.save}
          </Button>
        </span>
      </div>
      {!checking && result && !result.ok && <Notice kind="error">{result.message}</Notice>}
      <ErrorNote error={check.error} />
      {save.error && <Notice kind="error">{errorText(save.error)}</Notice>}
      {!checking && result?.ok && (result.warnings ?? []).map((warning) => (
        <Notice key={warning} kind="warn">
          {warning}
        </Notice>
      ))}
      {needsPath && <Notice kind="warn">{tx.needsPath(data.path_hint ?? '')}</Notice>}
      {missingSecrets.length > 0 && <Notice kind="warn">{tx.missingSecrets(missingSecrets)}</Notice>}
      {dropped.length > 0 && <Notice kind="warn">{tx.dropped(dropped)}</Notice>}
      <p className="muted small">{tx.saveHint}</p>
    </div>
  )
}

// --------------------------------------------------------------------------- Server

function TestState({ test }: { test: McpTest | null }) {
  if (!test) return <span className="muted">{tx.server.untested}</span>
  return (
    <span className={`state state--${test.ok ? 'pass' : 'fail'}`} title={test.message}>
      <Glyph kind={test.ok ? 'pass' : 'fail'} />
      {test.ok ? tx.server.testOk : tx.server.testFailed}
    </span>
  )
}

function Servers({ servers, systems }: { servers: McpServer[]; systems: BwSystem[] }) {
  const toast = useToast()
  const refresh = useRefresh()
  const [chosen, setChosen] = useState<string | null>(null)
  const current = servers.find((s) => s.name === chosen) ?? servers.find((s) => s.is_default) ?? servers[0]

  const makeDefault = useMutation({
    mutationFn: (name: string) => api.post(`${serverPath(name)}/default`),
    onSuccess: (_data, name) => {
      toast(tx.server.defaultSet(name))
      refresh('mcp')
    },
    onError: (error) => toast(errorText(error), true),
  })

  if (servers.length === 0)
    return (
      <Section title={tx.server.title}>
        <Empty title={tx.server.emptyTitle}>{tx.server.emptyText}</Empty>
      </Section>
    )
  return (
    <>
      <Section title={tx.server.title} note={tx.server.note}>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>{tx.server.col.name}</th>
                <th>{tx.server.col.transport}</th>
                <th>{tx.server.col.test}</th>
                <th className="right">{tx.server.col.tools}</th>
                <th className="right">{tx.server.col.tokens}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {servers.map((server) => (
                <tr key={server.name} className={server.name === current.name ? 'is-selected' : ''}>
                  <td>
                    <div className="row">
                      <strong>{server.name}</strong>
                      {server.is_default && <Tag title={tx.server.defaultHint}>{tx.server.default}</Tag>}
                    </div>
                  </td>
                  <td>{tx.server.transport[server.transport] ?? server.transport}</td>
                  <td>
                    <TestState test={server.last_test} />
                    {server.last_test && <div className="muted num">{tx.server.testedAt(dateTime(server.last_test.at), server.last_test.bw_system)}</div>}
                  </td>
                  <td className="right num">{server.last_test?.ok ? num(server.last_test.tool_count) : t.common.none}</td>
                  <td className="right num">{server.last_test?.ok ? num(server.last_test.token_estimate) : t.common.none}</td>
                  <td>
                    <div className="row settings-actions">
                      {!server.is_default && (
                        <Button small variant="quiet" busy={makeDefault.isPending && makeDefault.variables === server.name} onClick={() => makeDefault.mutate(server.name)}>
                          {tx.server.makeDefault}
                        </Button>
                      )}
                      {servers.length > 1 &&
                        (server.name === current.name ? (
                          <span className="state state--neutral">
                            <Glyph kind="dot" />
                            {tx.server.shown}
                          </span>
                        ) : (
                          <Button small variant="quiet" onClick={() => setChosen(server.name)}>
                            {tx.server.show}
                          </Button>
                        ))}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>
      <ServerDetail key={current.name} server={current} systems={systems} />
    </>
  )
}

function ServerDetail({ server, systems }: { server: McpServer; systems: BwSystem[] }) {
  const toast = useToast()
  const refresh = useRefresh()
  const active = systems.filter((s) => !s.retired)
  const [picked, setPicked] = useState<string | null>(null)
  const system = picked ?? active.find((s) => s.is_default)?.id ?? active[0]?.id ?? ''

  const test = useMutation({
    mutationFn: () => api.post<McpTest>(`${serverPath(server.name)}/test`, system ? { bw_system: system } : {}),
    onSuccess: (result) => {
      toast(result.ok ? tx.test.done(server.name, result.tool_count ?? 0) : tx.test.failed(server.name), !result.ok)
      refresh('mcp')
    },
    onError: (error) => toast(errorText(error), true),
  })
  const result = server.last_test

  return (
    <Section title={tx.test.title(server.name)} note={tx.test.note}>
      <div className="stack">
        <div className="panel">
          <div className="row settings-testbar">
            <Field label={tx.test.system}>
              <select className="select" value={system} onChange={(event) => setPicked(event.target.value)} disabled={active.length === 0}>
                {active.length === 0 && <option value="">{tx.test.noSystem}</option>}
                {active.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.id}
                    {s.is_default ? ` (${t.settings.bw.default})` : ''}
                  </option>
                ))}
              </select>
            </Field>
            <Button variant="primary" busy={test.isPending} onClick={() => test.mutate()}>
              {test.isPending ? tx.test.running : tx.test.run}
            </Button>
          </div>
          {active.length === 0 && <p className="muted small">{tx.test.noSystemHint}</p>}
        </div>

        {server.safety && server.safety.length > 0 && (
          <Notice kind="warn">
            <p style={{ margin: 0 }}>{tx.test.safety}</p>
            <ul className="settings-safety">
              {server.safety.map((text) => (
                <li key={text}>{text}</li>
              ))}
            </ul>
          </Notice>
        )}
        {server.needs_path && <Notice kind="warn">{tx.test.needsPath}</Notice>}
        {!result && !server.needs_path && <p className="muted">{tx.test.none}</p>}
        {result && !result.ok && (
          <Notice kind="error">
            <strong>{tx.test.failedAt(dateTime(result.at), result.bw_system)}</strong>
            <br />
            {result.message}
          </Notice>
        )}
        {result?.ok && (
          <>
            <div className="figures">
              <Figure value={num(result.tool_count)} label={tx.test.tools} />
              <Figure value={num(result.token_estimate)} label={tx.test.tokens} />
            </div>
            <dl className="kv">
              <dt>{tx.test.serverName}</dt>
              <dd>
                {result.server_name || t.common.none}
                {result.server_version && <span className="muted"> · {tx.test.version(result.server_version)}</span>}
              </dd>
              <dt>{tx.test.at}</dt>
              <dd>{tx.server.testedAt(dateTime(result.at), result.bw_system)}</dd>
            </dl>
            <Tools server={server} tools={result.tools ?? []} />
          </>
        )}

        <VerifyEnv server={server} />
      </div>
    </Section>
  )
}

/** Einstufung eines Werkzeugs: Überschreibung, sonst Angabe des Servers, sonst Stand des letzten Tests. */
function accessOf(server: McpServer, tool: McpTool): Access {
  const override = server.tool_overrides[tool.name]
  if (override) return override
  if (tool.hint !== null) return tool.hint ? 'read' : 'write'
  return tool.access
}

function Tools({ server, tools }: { server: McpServer; tools: McpTool[] }) {
  const toast = useToast()
  const refresh = useRefresh()
  const client = useQueryClient()
  const save = useMutation({
    mutationFn: (overrides: Record<string, Access>) => api.put<McpServer>(`${serverPath(server.name)}/options`, { tool_overrides: overrides }),
    onSuccess: (saved) => {
      client.setQueryData<McpData>(['mcp'], (old) => old && { ...old, servers: old.servers.map((s) => (s.name === saved.name ? saved : s)) })
      toast(tx.tools.saved)
      refresh('mcp')
    },
    onError: (error) => toast(errorText(error), true),
  })
  const change = (tool: string, value: string) => {
    const next = { ...server.tool_overrides }
    if (value === 'read' || value === 'write') next[tool] = value
    else delete next[tool]
    save.mutate(next)
  }
  const reading = tools.filter((tool) => accessOf(server, tool) === 'read').length

  if (tools.length === 0) return <Notice kind="warn">{tx.tools.empty}</Notice>
  return (
    <div>
      <h3 className="settings-subtitle">{tx.tools.title}</h3>
      <p className="muted small">{tx.tools.note(reading, tools.length - reading)}</p>
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>{tx.tools.col.name}</th>
              <th>{tx.tools.col.hint}</th>
              <th className="right">{tx.tools.col.tokens}</th>
              <th>{tx.tools.col.access}</th>
              <th>{tx.tools.col.override}</th>
            </tr>
          </thead>
          <tbody>
            {tools.map((tool) => {
              const access = accessOf(server, tool)
              return (
                <tr key={tool.name}>
                  <td>
                    <span className="mono">{tool.name}</span>
                    {tool.description && <div className="muted settings-clip">{tool.description}</div>}
                  </td>
                  <td className="secondary">{tool.hint === null ? tx.tools.hintNone : tool.hint ? tx.tools.hintRead : tx.tools.hintWrite}</td>
                  <td className="right num">{num(tool.tokens)}</td>
                  <td>
                    <span className={`state state--${access === 'read' ? 'neutral' : 'warn'}`}>
                      <Glyph kind={access === 'read' ? 'open' : 'invalid'} />
                      {tx.tools.access[access]}
                    </span>
                  </td>
                  <td>
                    <select
                      className="select settings-select"
                      aria-label={tx.tools.overrideLabel(tool.name)}
                      value={server.tool_overrides[tool.name] ?? ''}
                      disabled={save.isPending}
                      onChange={(event) => change(tool.name, event.target.value)}
                    >
                      <option value="">{tx.tools.byDefault}</option>
                      <option value="read">{tx.tools.access.read}</option>
                      <option value="write">{tx.tools.access.write}</option>
                    </select>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <p className="muted small">{tx.tools.stale}</p>
    </div>
  )
}

type Pair = [name: string, value: string]

function VerifyEnv({ server }: { server: McpServer }) {
  const toast = useToast()
  const refresh = useRefresh()
  const client = useQueryClient()
  const [draft, setDraft] = useState<Pair[] | null>(null)
  const rows: Pair[] = draft ?? Object.entries(server.verify_env)
  const update = (index: number, part: 0 | 1, value: string) => setDraft(rows.map((row, i) => (i === index ? (part === 0 ? [value, row[1]] : [row[0], value]) : row)))

  const save = useMutation({
    mutationFn: () => {
      const env = Object.fromEntries(rows.map(([name, value]) => [name.trim(), value]).filter(([name]) => name))
      return api.put<McpServer>(`${serverPath(server.name)}/options`, { verify_env: env })
    },
    onSuccess: (saved) => {
      client.setQueryData<McpData>(['mcp'], (old) => old && { ...old, servers: old.servers.map((s) => (s.name === saved.name ? saved : s)) })
      setDraft(null)
      toast(tx.env.saved)
      refresh('mcp')
    },
    onError: (error) => toast(errorText(error), true),
  })

  return (
    <div className="panel">
      <h3 className="settings-subtitle">{tx.env.title}</h3>
      <p className="muted small">{tx.env.note}</p>
      {server.transport !== 'stdio' ? (
        <p className="secondary">{tx.env.stdioOnly}</p>
      ) : (
        <div className="stack settings-env">
          {rows.length === 0 && <p className="secondary">{tx.env.empty}</p>}
          {rows.map(([name, value], index) => (
            <div key={index} className="settings-pair">
              <input className="input mono" aria-label={tx.env.name} placeholder={tx.env.name} spellCheck={false} value={name} onChange={(event) => update(index, 0, event.target.value)} />
              <input className="input mono" aria-label={tx.env.value} placeholder={tx.env.value} spellCheck={false} value={value} onChange={(event) => update(index, 1, event.target.value)} />
              <Button small variant="quiet" onClick={() => setDraft(rows.filter((_, i) => i !== index))}>
                {tx.env.remove}
              </Button>
            </div>
          ))}
          <div className="row">
            <Button small onClick={() => setDraft([...rows, ['', '']])}>
              {tx.env.add}
            </Button>
            <Button small variant="primary" busy={save.isPending} disabled={draft === null} onClick={() => save.mutate()}>
              {tx.env.save}
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}

// --------------------------------------------------------------------------- Geheimnisse

function Secrets({ secrets, loading, error }: { secrets: Secret[] | undefined; loading: boolean; error: unknown }) {
  const toast = useToast()
  const refresh = useRefresh()
  const [editing, setEditing] = useState<Secret | 'new' | null>(null)
  const [removing, setRemoving] = useState<Secret | null>(null)
  const remove = useMutation({
    mutationFn: (name: string) => api.del(`/secrets/${encodeURIComponent(name)}`),
    onSuccess: (_data, name) => {
      toast(tx.secrets.removed(name))
      refresh('secrets')
    },
    onError: (failure) => toast(errorText(failure), true),
    onSettled: () => setRemoving(null),
  })
  const list = secrets ?? []

  return (
    <Section title={tx.secrets.title} note={tx.secrets.note} actions={<Button onClick={() => setEditing('new')}>{tx.secrets.add}</Button>}>
      {loading && <Loading lines={2} />}
      <ErrorNote error={error} />
      {secrets && list.length === 0 && <p className="muted">{tx.secrets.empty}</p>}
      {list.length > 0 && (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>{tx.secrets.col.name}</th>
                <th>{tx.secrets.col.placeholder}</th>
                <th>{tx.secrets.col.state}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {list.map((secret) => (
                <tr key={secret.name}>
                  <td>
                    <strong>{secret.name}</strong>
                  </td>
                  <td className="mono">{`\${SECRET:${secret.name}}`}</td>
                  <td>
                    <SecretState set={secret.set} />
                  </td>
                  <td>
                    <div className="row settings-actions">
                      <Button small variant="quiet" onClick={() => setEditing(secret)}>
                        {tx.secrets.replace}
                      </Button>
                      <Button small variant="quiet" onClick={() => setRemoving(secret)}>
                        {tx.secrets.remove}
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {editing && <SecretDialog secret={editing === 'new' ? null : editing} onClose={() => setEditing(null)} />}
      {removing && (
        <Confirm
          title={tx.secrets.removeTitle(removing.name)}
          action={tx.secrets.removeAction}
          danger
          busy={remove.isPending}
          onConfirm={() => remove.mutate(removing.name)}
          onClose={() => setRemoving(null)}
        >
          <p>{tx.secrets.removeText(removing.name)}</p>
        </Confirm>
      )}
    </Section>
  )
}

function SecretDialog({ secret, onClose }: { secret: Secret | null; onClose: () => void }) {
  const toast = useToast()
  const refresh = useRefresh()
  const [name, setName] = useState(secret?.name ?? '')
  const [value, setValue] = useState('')
  const save = useMutation({
    mutationFn: () => api.put(`/secrets/${encodeURIComponent(name.trim())}`, { value }),
    onSuccess: () => {
      toast(tx.secrets.saved(name.trim()))
      refresh('secrets')
      onClose()
    },
  })
  const submit = (event: FormEvent) => {
    event.preventDefault()
    save.mutate()
  }
  return (
    <Modal title={secret ? tx.secrets.replaceTitle(secret.name) : tx.secrets.addTitle} onClose={onClose}>
      <form className="stack" onSubmit={submit} autoComplete="off">
        <Field label={tx.secrets.field.name} hint={secret ? undefined : tx.secrets.field.nameHint}>
          <input className="input mono" value={name} onChange={(event) => setName(event.target.value)} disabled={!!secret} required pattern="[A-Za-z0-9_\-]+" spellCheck={false} />
        </Field>
        <Field label={tx.secrets.field.value} hint={tx.secrets.field.valueHint}>
          <input className="input" type="password" value={value} onChange={(event) => setValue(event.target.value)} required autoComplete="new-password" />
        </Field>
        {save.error && <Notice kind="error">{errorText(save.error)}</Notice>}
        <FormFoot action={tx.secrets.save} busy={save.isPending} onCancel={onClose} />
      </form>
    </Modal>
  )
}
