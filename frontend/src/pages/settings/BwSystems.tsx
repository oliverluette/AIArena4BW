// Einstellungen > BW-Systeme: Liste mit Erreichbarkeit, Anlegen und Ändern im Dialog.
import { useMutation } from '@tanstack/react-query'
import { useState, type ChangeEvent, type FormEvent } from 'react'
import { api, errorText } from '../../api'
import { dateTime } from '../../format'
import { t } from '../../texts'
import { Button, BwState, Empty, ErrorNote, Field, Loading, Notice, Section, Tag, useToast } from '../../ui'
import { Confirm, FormFoot, Modal, SecretState, useBwSystems, useRefresh, type BwStatus, type BwSystem } from './shared'

const tx = t.settings.bw
const path = (id: string) => `/bw-systems/${encodeURIComponent(id)}`

export default function BwSystems() {
  const toast = useToast()
  const refresh = useRefresh()
  const systems = useBwSystems(20000)
  const [editing, setEditing] = useState<BwSystem | 'new' | null>(null)
  const [removing, setRemoving] = useState<BwSystem | null>(null)
  const fail = (error: unknown) => toast(errorText(error), true)

  const check = useMutation({
    mutationFn: (id: string) => api.post<BwStatus>(`${path(id)}/check`),
    onSuccess: (status, id) => {
      toast(tx.checked(id, t.common.bw[status.state] ?? status.state, status.detail))
      refresh('bw-systems')
    },
    onError: fail,
  })
  const makeDefault = useMutation({
    mutationFn: (id: string) => api.post(`${path(id)}/default`),
    onSuccess: (_data, id) => {
      toast(tx.defaultSet(id))
      refresh('bw-systems')
    },
    onError: fail,
  })
  const reactivate = useMutation({
    mutationFn: (system: BwSystem) => api.put(path(system.id), { ...fields(system), retired: false }),
    onSuccess: (_data, system) => {
      toast(tx.reactivated(system.id))
      refresh('bw-systems')
    },
    onError: fail,
  })
  const remove = useMutation({
    mutationFn: (system: BwSystem) => api.del<{ result: string }>(path(system.id)),
    onSuccess: (data, system) => {
      toast(data.result === 'retired' ? tx.removedRetired(system.id) : tx.removedDeleted(system.id))
      setRemoving(null)
      refresh('bw-systems')
    },
    onError: (error) => {
      setRemoving(null)
      fail(error)
    },
  })

  const list = systems.data ?? []
  return (
    <div role="tabpanel">
      <Section
        title={tx.title}
        note={tx.note}
        actions={
          list.length > 0 && (
            <Button variant="primary" onClick={() => setEditing('new')}>
              {tx.add}
            </Button>
          )
        }
      >
        {systems.isLoading && <Loading />}
        <ErrorNote error={systems.error} />
        {systems.data && list.length === 0 && (
          <Empty
            title={tx.emptyTitle}
            action={
              <Button variant="primary" onClick={() => setEditing('new')}>
                {tx.add}
              </Button>
            }
          >
            {tx.emptyText}
          </Empty>
        )}
        {list.length > 0 && (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>{tx.col.system}</th>
                  <th>{tx.col.state}</th>
                  <th>{tx.col.password}</th>
                  <th>{tx.col.naming}</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {list.map((system) => (
                  <tr key={system.id} className={system.retired ? 'is-dim' : ''}>
                    <td>
                      <div className="row">
                        <strong>{system.id}</strong>
                        {system.is_default && <Tag title={tx.defaultHint}>{tx.default}</Tag>}
                        {system.retired && <Tag title={tx.retiredHint}>{tx.retired}</Tag>}
                      </div>
                      <div className="muted">{tx.connection(system.url, system.client, system.user, system.language)}</div>
                      {system.note && <div className="muted">{system.note}</div>}
                    </td>
                    <td>
                      {system.retired ? (
                        <span className="muted">{tx.notChecked}</span>
                      ) : (
                        <>
                          <BwState status={system.status} />
                          <div className="muted">
                            {system.status.detail}
                            {system.status.checked && ` · ${tx.checkedAt(dateTime(system.status.checked))}`}
                          </div>
                        </>
                      )}
                    </td>
                    <td>
                      <SecretState set={system.password_set} />
                    </td>
                    <td>
                      <div className="mono">{system.parent_area}</div>
                      <div className="muted mono">
                        {system.area_pattern} · {system.prefix}
                      </div>
                    </td>
                    <td>
                      <div className="row settings-actions">
                        {!system.retired && (
                          <Button small variant="quiet" busy={check.isPending && check.variables === system.id} onClick={() => check.mutate(system.id)}>
                            {tx.check}
                          </Button>
                        )}
                        {!system.retired && !system.is_default && (
                          <Button small variant="quiet" busy={makeDefault.isPending && makeDefault.variables === system.id} onClick={() => makeDefault.mutate(system.id)}>
                            {tx.makeDefault}
                          </Button>
                        )}
                        {system.retired && (
                          <Button small variant="quiet" busy={reactivate.isPending && reactivate.variables?.id === system.id} onClick={() => reactivate.mutate(system)}>
                            {tx.reactivate}
                          </Button>
                        )}
                        <Button small variant="quiet" onClick={() => setEditing(system)}>
                          {t.common.actions.edit}
                        </Button>
                        {!system.retired && (
                          <Button small variant="quiet" onClick={() => setRemoving(system)}>
                            {tx.remove}
                          </Button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      {editing && <BwDialog system={editing === 'new' ? null : editing} onClose={() => setEditing(null)} />}
      {removing && (
        <Confirm
          title={tx.removeTitle(removing.id)}
          action={tx.removeAction(removing.id)}
          danger
          busy={remove.isPending}
          onConfirm={() => remove.mutate(removing)}
          onClose={() => setRemoving(null)}
        >
          <p>{tx.removeText}</p>
        </Confirm>
      )}
    </div>
  )
}

type Form = {
  id: string
  url: string
  client: string
  user: string
  password: string
  language: string
  parent_area: string
  area_pattern: string
  prefix: string
  note: string
}

function fields(system: BwSystem | null): Form {
  return {
    id: system?.id ?? '',
    url: system?.url ?? '',
    client: system?.client ?? '',
    user: system?.user ?? '',
    password: '',
    language: system?.language ?? 'DE',
    parent_area: system?.parent_area ?? 'ZBENCH_AI',
    area_pattern: system?.area_pattern ?? 'ZBENCH_{RUN}',
    prefix: system?.prefix ?? 'ZB',
    note: system?.note ?? '',
  }
}

function BwDialog({ system, onClose }: { system: BwSystem | null; onClose: () => void }) {
  const toast = useToast()
  const refresh = useRefresh()
  const [form, setForm] = useState<Form>(() => fields(system))
  const bind = (key: keyof Form) => ({
    value: form[key],
    onChange: (event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setForm((current) => ({ ...current, [key]: event.target.value })),
  })

  const save = useMutation({
    mutationFn: () => {
      // Ein leeres Passwort lässt das gespeicherte unverändert.
      const body = { ...form, password: form.password || undefined, retired: system?.retired ?? false }
      return system ? api.put<BwSystem>(path(system.id), body) : api.post<BwSystem>('/bw-systems', body)
    },
    onSuccess: (saved) => {
      toast(tx.saved(saved.id))
      refresh('bw-systems')
      onClose()
    },
  })
  const submit = (event: FormEvent) => {
    event.preventDefault()
    save.mutate()
  }

  const exampleArea = form.area_pattern.toUpperCase().replace('{RUN}', 'AAA01')
  return (
    <Modal title={system ? tx.editTitle(system.id) : tx.addTitle} onClose={onClose}>
      <form className="stack" onSubmit={submit} autoComplete="off">
        <div className="form-grid">
          <Field label={tx.field.id} hint={system ? tx.field.idFixed : tx.field.idHint}>
            <input className="input" {...bind('id')} disabled={!!system} required maxLength={32} placeholder="A4H" />
          </Field>
          <Field label={tx.field.language}>
            <input className="input" {...bind('language')} maxLength={2} placeholder="DE" />
          </Field>
          <Field label={tx.field.url} hint={tx.field.urlHint} wide>
            <input className="input" {...bind('url')} required placeholder="https://host:44300" inputMode="url" />
          </Field>
          <Field label={tx.field.client}>
            <input className="input" {...bind('client')} placeholder="100" inputMode="numeric" />
          </Field>
          <Field label={tx.field.user}>
            <input className="input" {...bind('user')} autoComplete="off" />
          </Field>
          <Field label={tx.field.password} hint={system?.password_set ? tx.field.passwordSet : tx.field.passwordMissing} wide>
            <input className="input" type="password" {...bind('password')} autoComplete="new-password" placeholder={system?.password_set ? tx.field.passwordKeep : ''} />
          </Field>
          <Field label={tx.field.parentArea} hint={tx.field.parentAreaHint}>
            <input className="input mono" {...bind('parent_area')} required />
          </Field>
          <Field label={tx.field.areaPattern} hint={tx.field.areaPatternHint}>
            <input className="input mono" {...bind('area_pattern')} required />
          </Field>
          <Field label={tx.field.prefix} hint={tx.field.prefixHint}>
            <input className="input mono" {...bind('prefix')} required maxLength={2} />
          </Field>
          <p className="field--wide field__hint">{tx.example(exampleArea, `${form.prefix.toUpperCase()}AAA01`)}</p>
          <Field label={tx.field.note} wide>
            <textarea className="textarea" rows={2} {...bind('note')} />
          </Field>
        </div>
        {save.error && <Notice kind="error">{errorText(save.error)}</Notice>}
        <FormFoot action={system ? tx.saveEdit : tx.saveNew} busy={save.isPending} onCancel={onClose} />
      </form>
    </Modal>
  )
}
