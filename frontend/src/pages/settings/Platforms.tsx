// Einstellungen > LLM-Plattformen: Liste, Anlegen und Ändern, Verbindungstest, Katalog.
import { useMutation, useQuery } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { api, errorText } from '../../api'
import { dateTime } from '../../format'
import { t } from '../../texts'
import { Button, Check, Empty, ErrorNote, Field, Glyph, Loading, Notice, Section, useToast } from '../../ui'
import Models from './Models'
import { Confirm, FormFoot, Modal, SecretState, useMeta, useRefresh, type Platform, type PlatformType } from './shared'

const tx = t.settings.platforms
const path = (id: string) => `/platforms/${encodeURIComponent(id)}`
/** Typen, die ohne Zugangsdaten auskommen können (lokale Server). */
const keyOptional = (type: string) => type === 'openai'

function Verified({ live }: { live: boolean }) {
  return (
    <span className={`state state--${live ? 'pass' : 'neutral'}`} title={live ? tx.liveHint : tx.mockHint}>
      <Glyph kind={live ? 'pass' : 'open'} />
      {live ? tx.live : tx.mock}
    </span>
  )
}

function LastTest({ platform }: { platform: Platform }) {
  const test = platform.last_test
  if (!test) return <span className="muted">{tx.untested}</span>
  return (
    <>
      <span className={`state state--${test.ok ? 'pass' : 'fail'}`} title={test.message}>
        <Glyph kind={test.ok ? 'pass' : 'fail'} />
        {test.ok ? tx.testOk : tx.testFailed}
      </span>
      <div className="muted num">{dateTime(test.at)}</div>
    </>
  )
}

export default function Platforms() {
  const platforms = useQuery<Platform[]>({ queryKey: ['platforms'], queryFn: () => api.get('/platforms') })
  const meta = useMeta()
  const [chosen, setChosen] = useState<string | null>(null)
  const [editing, setEditing] = useState<Platform | 'new' | null>(null)
  const list = platforms.data ?? []
  const current = list.find((p) => p.id === chosen) ?? list[0]
  const types = meta.data?.platform_types ?? []

  const add = (
    <Button variant="primary" disabled={types.length === 0} onClick={() => setEditing('new')}>
      {tx.add}
    </Button>
  )
  return (
    <div role="tabpanel">
      <Section title={tx.title} note={tx.note} actions={list.length > 0 && add}>
        {platforms.isLoading && <Loading />}
        <ErrorNote error={platforms.error} />
        <ErrorNote error={meta.error} />
        {platforms.data && list.length === 0 && (
          <Empty title={tx.emptyTitle} action={add}>
            {tx.emptyText}
          </Empty>
        )}
        {list.length > 0 && (
          <div className="table-wrap">
            <table className="table table--click">
              <thead>
                <tr>
                  <th>{tx.col.platform}</th>
                  <th>{tx.col.type}</th>
                  <th>{tx.col.state}</th>
                  <th>{tx.col.test}</th>
                  <th className="right">{tx.col.models}</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {list.map((platform) => {
                  const selected = platform.id === current.id
                  return (
                    <tr key={platform.id} className={selected ? 'is-selected' : ''} onClick={() => setChosen(platform.id)}>
                      <td>
                        <strong>{platform.name}</strong>
                        <div className="muted mono">{platform.id}</div>
                      </td>
                      <td>
                        {platform.type_name}
                        <div>
                          <Verified live={platform.live_verified} />
                        </div>
                      </td>
                      <td>
                        <span className={`state state--${platform.active ? 'pass' : 'neutral'}`}>
                          <Glyph kind={platform.active ? 'pass' : 'skip'} />
                          {platform.active ? tx.active : tx.inactive}
                        </span>
                        <div className="muted">
                          {tx.credentials}: <SecretState set={platform.credentials_set} optional={keyOptional(platform.type)} />
                        </div>
                      </td>
                      <td>
                        <LastTest platform={platform} />
                      </td>
                      <td className="right num">
                        {tx.modelCount(platform.models_selected, platform.models_total)}
                        {platform.options.select_all && <div className="muted">{tx.selectAllShort}</div>}
                      </td>
                      <td>
                        <div className="row settings-actions">
                          {selected ? (
                            <span className="state state--neutral">
                              <Glyph kind="dot" />
                              {tx.shown}
                            </span>
                          ) : (
                            <Button small variant="quiet" onClick={() => setChosen(platform.id)}>
                              {tx.show}
                            </Button>
                          )}
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      {current && <PlatformDetail key={current.id} platform={current} onEdit={() => setEditing(current)} />}

      {editing && (
        <PlatformDialog
          platform={editing === 'new' ? null : editing}
          types={types}
          taken={list.map((p) => p.id)}
          onSaved={(id) => setChosen(id)}
          onClose={() => setEditing(null)}
        />
      )}
    </div>
  )
}

// --------------------------------------------------------------------------- gewählte Plattform

function PlatformDetail({ platform, onEdit }: { platform: Platform; onEdit: () => void }) {
  const toast = useToast()
  const refresh = useRefresh()
  const [removing, setRemoving] = useState(false)
  const fail = (error: unknown) => toast(errorText(error), true)

  const test = useMutation({
    mutationFn: () => api.post<{ ok: boolean; message: string }>(`${path(platform.id)}/test`),
    onSuccess: (result) => {
      toast(result.ok ? tx.testDone(platform.name) : tx.testFailedToast(platform.name, result.message), !result.ok)
      refresh('platforms')
    },
    onError: fail,
  })
  const catalog = useMutation({
    mutationFn: () => api.post<{ count: number }>(`${path(platform.id)}/catalog`),
    onSuccess: (result) => {
      toast(tx.catalogDone(platform.name, result.count))
      refresh('platforms', 'platform-models', 'models')
    },
    onError: fail,
  })
  const remove = useMutation({
    mutationFn: () => api.del<{ result: string }>(path(platform.id)),
    onSuccess: (data) => {
      toast(data.result === 'deactivated' ? tx.removedDeactivated(platform.name) : tx.removedDeleted(platform.name))
      refresh('platforms', 'platform-models', 'models')
    },
    onError: fail,
    onSettled: () => setRemoving(false),
  })

  const lastTest = platform.last_test
  return (
    <Section
      title={platform.name}
      note={tx.detailNote(platform.type_name, platform.base_url, platform.catalog_fetched ? dateTime(platform.catalog_fetched) : null)}
      actions={
        <>
          <Button busy={test.isPending} onClick={() => test.mutate()}>
            {test.isPending ? tx.testRunning : tx.test}
          </Button>
          <Button busy={catalog.isPending} onClick={() => catalog.mutate()}>
            {catalog.isPending ? tx.catalogRunning : tx.catalog}
          </Button>
          <Button onClick={onEdit}>{t.common.actions.edit}</Button>
          <Button variant="danger" onClick={() => setRemoving(true)}>
            {tx.remove}
          </Button>
        </>
      }
    >
      <div className="stack">
        {!platform.credentials_set && !keyOptional(platform.type) && <Notice kind="warn">{tx.noCredentials}</Notice>}
        {!platform.active && <Notice>{tx.inactiveHint}</Notice>}
        {lastTest && !lastTest.ok && (
          <Notice kind="error">
            <strong>{tx.testFailedAt(dateTime(lastTest.at))}</strong>
            <br />
            {lastTest.message}
          </Notice>
        )}
        {lastTest?.ok && (
          <Notice kind="ok">
            {tx.testOkAt(dateTime(lastTest.at))}
            {lastTest.message && ` · ${lastTest.message}`}
          </Notice>
        )}
        <Models platform={platform} onCatalog={() => catalog.mutate()} catalogBusy={catalog.isPending} />
      </div>
      {removing && (
        <Confirm title={tx.removeTitle(platform.name)} action={tx.removeAction(platform.name)} danger busy={remove.isPending} onConfirm={() => remove.mutate()} onClose={() => setRemoving(false)}>
          <p>{tx.removeText}</p>
        </Confirm>
      )}
    </Section>
  )
}

// --------------------------------------------------------------------------- Dialog

function PlatformDialog(props: { platform: Platform | null; types: PlatformType[]; taken: string[]; onSaved: (id: string) => void; onClose: () => void }) {
  const { platform, types, onClose } = props
  const toast = useToast()
  const refresh = useRefresh()
  const [type, setType] = useState(platform?.type ?? types[0]?.type ?? '')
  // null = Vorschlag bzw. Vorgabe des Typs, bis der Nutzer selbst etwas einträgt.
  const [idInput, setIdInput] = useState<string | null>(null)
  const [urlInput, setUrlInput] = useState<string | null>(platform ? platform.base_url : null)
  const [name, setName] = useState(platform?.name ?? '')
  const [credentials, setCredentials] = useState('')
  const [group, setGroup] = useState(platform?.options.resource_group ?? 'default')
  const [caching, setCaching] = useState(platform?.options.caching ?? true)
  const [active, setActive] = useState(platform?.active ?? true)

  const info = types.find((x) => x.type === type)
  const id = platform ? platform.id : (idInput ?? freeId(type, props.taken))
  const baseUrl = urlInput ?? info?.base_url ?? ''
  const isAiCore = type === 'sapaicore'
  const keyError = isAiCore && credentials.trim() && !isJsonObject(credentials) ? tx.field.serviceKeyInvalid : undefined

  const save = useMutation({
    mutationFn: () => {
      const body = {
        id,
        type,
        name,
        base_url: baseUrl,
        active,
        options: { caching, ...(isAiCore ? { resource_group: group } : {}) },
        // Leere Zugangsdaten lassen die gespeicherten unverändert.
        ...(credentials.trim() ? { credentials: credentials.trim() } : {}),
      }
      return platform ? api.put<Platform>(path(platform.id), body) : api.post<Platform>('/platforms', body)
    },
    onSuccess: (saved) => {
      toast(platform ? tx.saved(saved.name) : tx.created(saved.name))
      refresh('platforms', 'models')
      props.onSaved(saved.id)
      onClose()
    },
  })
  const submit = (event: FormEvent) => {
    event.preventDefault()
    if (!keyError) save.mutate()
  }

  const credentialsHint = platform?.credentials_set ? tx.field.credentialsSet : keyOptional(type) ? tx.field.credentialsOptional : tx.field.credentialsMissing
  return (
    <Modal title={platform ? tx.editTitle(platform.name) : tx.addTitle} onClose={onClose}>
      <form className="stack" onSubmit={submit} autoComplete="off">
        <div className="form-grid">
          <Field label={tx.field.type} hint={platform ? tx.field.typeFixed : info && (info.live_verified ? tx.liveHint : tx.mockHint)}>
            <select className="select" value={type} disabled={!!platform} onChange={(event) => setType(event.target.value)}>
              {types.map((x) => (
                <option key={x.type} value={x.type}>
                  {x.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label={tx.field.id} hint={platform ? tx.field.idFixed : tx.field.idHint(id)}>
            <input className="input mono" value={id} disabled={!!platform} onChange={(event) => setIdInput(event.target.value)} required maxLength={32} spellCheck={false} />
          </Field>
          <Field label={tx.field.name} wide>
            <input className="input" value={name} onChange={(event) => setName(event.target.value)} placeholder={info?.name} />
          </Field>
          <Field label={tx.field.baseUrl} hint={isAiCore ? tx.field.baseUrlAiCore : tx.field.baseUrlHint} wide>
            <input className="input mono" value={baseUrl} onChange={(event) => setUrlInput(event.target.value)} placeholder={info?.base_url} inputMode="url" spellCheck={false} />
          </Field>
          {isAiCore ? (
            <>
              <Field label={tx.field.serviceKey} hint={credentialsHint} error={keyError} wide>
                <textarea
                  className="textarea textarea--code"
                  rows={7}
                  spellCheck={false}
                  value={credentials}
                  onChange={(event) => setCredentials(event.target.value)}
                  placeholder={platform?.credentials_set ? tx.field.credentialsKeep : tx.field.serviceKeyPlaceholder}
                />
              </Field>
              <Field label={tx.field.resourceGroup} hint={tx.field.resourceGroupHint}>
                <input className="input mono" value={group} onChange={(event) => setGroup(event.target.value)} placeholder="default" spellCheck={false} />
              </Field>
            </>
          ) : (
            <Field label={keyOptional(type) ? tx.field.apiKeyOptional : tx.field.apiKey} hint={credentialsHint} wide>
              <input
                className="input"
                type="password"
                autoComplete="new-password"
                value={credentials}
                onChange={(event) => setCredentials(event.target.value)}
                placeholder={platform?.credentials_set ? tx.field.credentialsKeep : ''}
              />
            </Field>
          )}
        </div>
        <div className="stack settings-checks">
          <Check checked={caching} onChange={setCaching}>
            {tx.field.caching}
          </Check>
          <Check checked={active} onChange={setActive}>
            {tx.field.active}
          </Check>
        </div>
        {info?.external && <p className="muted small">{tx.externalHint}</p>}
        {save.error && <Notice kind="error">{errorText(save.error)}</Notice>}
        <FormFoot action={platform ? tx.saveEdit : tx.saveNew} busy={save.isPending} disabled={!type} onCancel={onClose} />
      </form>
    </Modal>
  )
}

/** Vorschlag für die Kennung: der Typ, bei Mehrfachnutzung mit laufender Nummer. */
function freeId(type: string, taken: string[]): string {
  if (!taken.includes(type)) return type
  for (let n = 2; ; n++) if (!taken.includes(`${type}${n}`)) return `${type}${n}`
}

function isJsonObject(text: string): boolean {
  try {
    const value = JSON.parse(text)
    return typeof value === 'object' && value !== null && !Array.isArray(value)
  } catch {
    return false
  }
}
