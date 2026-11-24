// Gemeinsames der Einstellungsseite: Datenformen der Schnittstelle, Bestätigungsdialog, kleine Helfer.
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { api } from '../../api'
import { t } from '../../texts'
import { Button, Dialog, Glyph } from '../../ui'

// --------------------------------------------------------------------------- Datenformen

export type BwStatus = { state: string; detail: string; host: string; ms: number | null; checked: string | null }

export type BwSystem = {
  id: string
  url: string
  client: string
  user: string
  language: string
  parent_area: string
  area_pattern: string
  prefix: string
  note: string
  is_default: boolean
  retired: boolean
  password_set: boolean
  status: BwStatus
}

export type Access = 'read' | 'write'
export type McpTool = { name: string; description: string; hint: boolean | null; access: Access; tokens: number }
export type McpTest = {
  ok: boolean
  at: string
  bw_system: string
  message?: string
  server_name?: string
  server_version?: string
  tool_count?: number
  token_estimate?: number
  tools?: McpTool[]
}
export type McpServer = {
  name: string
  is_default: boolean
  transport: 'stdio' | 'http'
  needs_path: boolean
  tool_overrides: Record<string, Access>
  verify_env: Record<string, string>
  last_test: McpTest | null
  plaintext_secrets: string[]
  safety?: string[]
}
export type McpData = { text: string; servers: McpServer[]; path_hint?: string }
export type Secret = { name: string; set: boolean }

export type PlatformType = { type: string; name: string; base_url: string; external: boolean; live_verified: boolean }
export type Platform = {
  id: string
  type: string
  type_name: string
  name: string
  base_url: string
  options: { caching?: boolean; select_all?: boolean; resource_group?: string }
  active: boolean
  external: boolean
  credentials_set: boolean
  live_verified: boolean
  last_test: { ok: boolean; message: string; at: string } | null
  catalog_fetched: string | null
  models_total: number
  models_selected: number
}

export type Quicktest = { ok: boolean; message: string; at: string; seconds?: number; kind?: string }
export type Model = {
  id: string
  platform_id: string
  platform_name?: string
  model_id: string
  name: string
  vendor: string
  vendor_name: string
  selected: boolean
  manual: boolean
  in_catalog: boolean
  price_in: number | null
  price_out: number | null
  price_cache_read: number | null
  price_cache_write: number | null
  price_edited: boolean
  context_window: number | null
  max_tools: number | null
  released: string | null
  first_seen: string | null
  note: string
  quicktest: Quicktest | null
}

export type Meta = { thinking_levels: string[]; platform_types: PlatformType[]; bw_placeholders: string[] }

export type AppSettings = {
  verify: { model: string; fallback: string; timeout_s: number; thinking: string }
  run: {
    timeout_s: number
    thinking: string
    cost_limit: number
    max_steps: number
    tool_timeout_s: number
    max_output_tokens: number
    api_retries: number
    blocked_codes: string[]
  }
}

// --------------------------------------------------------------------------- Abfragen

export function useMeta() {
  return useQuery<Meta>({ queryKey: ['meta'], queryFn: () => api.get('/meta'), staleTime: 5 * 60_000 })
}

export function useBwSystems(refetchInterval?: number) {
  return useQuery<BwSystem[]>({ queryKey: ['bw-systems'], queryFn: () => api.get('/bw-systems'), refetchInterval })
}

/** Lädt die genannten Abfragen neu, dazu immer den Status (Kopfzeile, Checkliste). */
export function useRefresh() {
  const client = useQueryClient()
  return useCallback(
    (...keys: string[]) => {
      for (const key of [...keys, 'status']) void client.invalidateQueries({ queryKey: [key] })
    },
    [client],
  )
}

/** Wert, der erst nach einer Tipp-Pause folgt. */
export function useDebounced<T>(value: T, ms: number): T {
  const [settled, setSettled] = useState(value)
  useEffect(() => {
    const id = window.setTimeout(() => setSettled(value), ms)
    return () => window.clearTimeout(id)
  }, [value, ms])
  return settled
}

// --------------------------------------------------------------------------- Bausteine

type ModalProps = { title: ReactNode; onClose: () => void; children: ReactNode; footer?: ReactNode; wide?: boolean }

/** Dialog, dessen Fokus beim Tippen bleibt, auch wenn die aufrufende Seite neu zeichnet:
    Der gemeinsame Dialog setzt den Fokus neu, sobald sich `onClose` ändert. */
export function Modal(props: ModalProps) {
  const latest = useRef(props.onClose)
  useEffect(() => {
    latest.current = props.onClose
  })
  const close = useCallback(() => latest.current(), [])
  return <Dialog {...props} onClose={close} />
}

export function Confirm(props: {
  title: string
  action: string
  children: ReactNode
  danger?: boolean
  busy?: boolean
  onConfirm: () => void
  onClose: () => void
}) {
  return (
    <Modal
      title={props.title}
      onClose={props.onClose}
      footer={
        <>
          <Button onClick={props.onClose}>{t.common.actions.cancel}</Button>
          <Button variant={props.danger ? 'danger' : 'primary'} busy={props.busy} onClick={props.onConfirm}>
            {props.action}
          </Button>
        </>
      }
    >
      <div className="stack secondary">{props.children}</div>
    </Modal>
  )
}

/** Geheimnisse erscheinen nie selbst, nur ihr Zustand. */
export function SecretState({ set, optional }: { set: boolean; optional?: boolean }) {
  const tx = t.settings.secretState
  if (set)
    return (
      <span className="state state--pass">
        <Glyph kind="pass" />
        {tx.set}
      </span>
    )
  return (
    <span className={`state state--${optional ? 'neutral' : 'warn'}`}>
      <Glyph kind={optional ? 'open' : 'warn'} />
      {optional ? tx.unset : tx.missing}
    </span>
  )
}

/** Fußzeile eines Formulardialogs: Abbrechen und die benannte Aktion. */
export function FormFoot(props: { action: string; busy?: boolean; disabled?: boolean; onCancel: () => void }) {
  return (
    <div className="dialog__foot">
      <Button onClick={props.onCancel}>{t.common.actions.cancel}</Button>
      <Button type="submit" variant="primary" busy={props.busy} disabled={props.disabled}>
        {props.action}
      </Button>
    </div>
  )
}
