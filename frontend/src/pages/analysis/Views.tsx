// Gespeicherte Ansichten: Filter und Diagrammeinstellungen unter einem Namen.
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api, errorText } from '../../api'
import { dateTime } from '../../format'
import { t } from '../../texts'
import { Button, Check, Dialog, ErrorNote, Field, Tag, useToast } from '../../ui'
import type { Settings, View } from './model'

const tx = t.analysis.views
const path = (name: string) => `/views/${encodeURIComponent(name)}`

type Props = {
  views: View[]
  current: Settings
  activeName: string
  onLoad: (view: View) => void
  onSaved: (name: string) => void
  onClose: () => void
}

export function ViewsDialog({ views, current, activeName, onLoad, onSaved, onClose }: Props) {
  const toast = useToast()
  const client = useQueryClient()
  const [name, setName] = useState(activeName)
  const [isDefault, setIsDefault] = useState(() => views.find((v) => v.name === activeName)?.is_default ?? false)
  const refresh = () => client.invalidateQueries({ queryKey: ['views'] })
  const trimmed = name.trim()
  const badName = trimmed.includes('/')

  const save = useMutation({
    mutationFn: () => api.put(path(trimmed), { settings: current, is_default: isDefault }),
    onSuccess: () => {
      toast(tx.saved(trimmed))
      onSaved(trimmed)
      return refresh()
    },
  })
  const remove = useMutation({
    mutationFn: (view: View) => api.del(path(view.name)),
    onSuccess: (_data, view) => {
      toast(tx.deleted(view.name))
      return refresh()
    },
    onError: (error) => toast(errorText(error), true),
  })
  const setDefault = useMutation({
    mutationFn: (view: View) => api.post(`${path(view.name)}/default`, { is_default: !view.is_default }),
    onSuccess: (_data, view) => {
      toast(view.is_default ? tx.defaultCleared : tx.defaultSet(view.name))
      return refresh()
    },
    onError: (error) => toast(errorText(error), true),
  })

  return (
    <Dialog title={tx.dialogTitle} onClose={onClose} wide footer={<Button onClick={onClose}>{t.common.actions.close}</Button>}>
      <p className="secondary small" style={{ marginBottom: 16 }}>
        {tx.intro}
      </p>
      <div className="row" style={{ alignItems: 'flex-end' }}>
        <div style={{ flex: 1, minWidth: 240 }}>
          <Field
            label={tx.name}
            error={badName ? tx.badName : undefined}
            hint={!badName && views.some((v) => v.name === trimmed) ? tx.overwrite : undefined}
          >
            <input className="input" value={name} placeholder={tx.namePlaceholder} maxLength={80} onChange={(e) => setName(e.target.value)} />
          </Field>
        </div>
        <Button variant="primary" disabled={!trimmed || badName} busy={save.isPending} onClick={() => save.mutate()}>
          {tx.save}
        </Button>
      </div>
      <div style={{ marginTop: 8 }}>
        <Check checked={isDefault} onChange={setIsDefault}>
          {tx.asDefault}
        </Check>
      </div>
      <ErrorNote error={save.error} />

      <h3 className="views-title">{tx.listTitle}</h3>
      {views.length === 0 ? (
        <p className="muted">{tx.none}</p>
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>{tx.col.name}</th>
                <th>{tx.col.saved}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {views.map((view) => (
                <tr key={view.name}>
                  <td>
                    <strong>{view.name}</strong> {view.is_default && <Tag>{tx.isDefault}</Tag>}
                  </td>
                  <td className="num secondary">{dateTime(view.saved)}</td>
                  <td className="right">
                    <span className="row" style={{ justifyContent: 'flex-end', flexWrap: 'nowrap' }}>
                      <Button small onClick={() => onLoad(view)}>
                        {tx.loadOne}
                      </Button>
                      <Button small disabled={setDefault.isPending} onClick={() => setDefault.mutate(view)}>
                        {view.is_default ? tx.clearDefault : tx.makeDefault}
                      </Button>
                      <Button small variant="danger" disabled={remove.isPending} onClick={() => remove.mutate(view)}>
                        {t.common.actions.delete}
                      </Button>
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Dialog>
  )
}
