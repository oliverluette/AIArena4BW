// Einstellungen > Prüfung und > Vorgaben für Durchgänge.
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, errorText } from '../../api'
import { duration } from '../../format'
import { t } from '../../texts'
import { Button, Check, Empty, ErrorNote, Field, Loading, Notice, Section, useToast } from '../../ui'
import { useMeta, useRefresh, type AppSettings, type Model } from './shared'

const tx = t.settings.general

function useSettings() {
  return useQuery<AppSettings>({ queryKey: ['settings'], queryFn: () => api.get('/settings') })
}

/** Speichert einen Abschnitt der Vorgaben und übernimmt die Antwort als neuen Stand. */
function useSave(done: () => void) {
  const toast = useToast()
  const refresh = useRefresh()
  const client = useQueryClient()
  return useMutation({
    mutationFn: (body: Partial<{ [K in keyof AppSettings]: Partial<AppSettings[K]> }>) => api.put<AppSettings>('/settings', body),
    onSuccess: (saved) => {
      client.setQueryData(['settings'], saved)
      done()
      toast(t.common.saved)
      refresh('settings')
    },
  })
}

/** Zahl aus einem Eingabefeld; null, wenn sie fehlt, negativ oder nicht ganzzahlig ist. */
function parse(text: string, integer: boolean): number | null {
  const trimmed = text.trim().replace(',', '.')
  const value = Number(trimmed)
  if (!trimmed || !Number.isFinite(value) || value < 0 || (integer && !Number.isInteger(value))) return null
  return value
}

const asText = (value: number) => String(value).replace('.', ',')

function ThinkingSelect({ value, levels, onChange }: { value: string; levels: string[]; onChange: (value: string) => void }) {
  const options = levels.includes(value) ? levels : [...levels, value]
  return (
    <select className="select" value={value} onChange={(event) => onChange(event.target.value)}>
      {options.map((level) => (
        <option key={level} value={level}>
          {t.common.thinking[level] ?? level}
        </option>
      ))}
    </select>
  )
}

// --------------------------------------------------------------------------- Prüfung

export function VerifySettings() {
  const settings = useSettings()
  const meta = useMeta()
  const all = useQuery<Model[]>({ queryKey: ['models'], queryFn: () => api.get('/models') })
  const selectable = useQuery<Model[]>({ queryKey: ['models', 'selectable'], queryFn: () => api.get('/models?selectable=true') })

  if (settings.isLoading || all.isLoading || selectable.isLoading) return <Loading />
  if (!settings.data) return <ErrorNote error={settings.error} />
  return (
    <div role="tabpanel">
      <Section title={tx.verify.title} note={tx.verify.note}>
        <ErrorNote error={all.error} />
        {all.data && all.data.length === 0 ? (
          <Empty
            title={tx.verify.emptyTitle}
            action={
              <Link className="btn btn--primary" to="/einstellungen/plattformen">
                {tx.verify.emptyAction}
              </Link>
            }
          >
            {tx.verify.emptyText}
          </Empty>
        ) : (
          <VerifyForm saved={settings.data.verify} all={all.data ?? []} selectable={selectable.data ?? []} levels={meta.data?.thinking_levels ?? ['']} />
        )}
      </Section>
    </div>
  )
}

type Verify = AppSettings['verify']

function VerifyForm({ saved, all, selectable, levels }: { saved: Verify; all: Model[]; selectable: Model[]; levels: string[] }) {
  const [draft, setDraft] = useState<Partial<Record<keyof Verify, string>>>({})
  const [narrow, setNarrow] = useState(selectable.length > 0)
  const save = useSave(() => setDraft({}))
  const value = {
    model: draft.model ?? saved.model,
    fallback: draft.fallback ?? saved.fallback,
    timeout_s: draft.timeout_s ?? asText(saved.timeout_s),
    thinking: draft.thinking ?? saved.thinking,
  }
  const set = (key: keyof Verify) => (text: string) => setDraft((current) => ({ ...current, [key]: text }))
  const timeout = parse(value.timeout_s, true)
  const dirty = value.model !== saved.model || value.fallback !== saved.fallback || value.thinking !== saved.thinking || timeout !== saved.timeout_s
  const offered = narrow ? selectable : all

  return (
    <div className="grid grid--side">
      <div className="panel stack">
        <div className="form-grid">
          <Field label={tx.verify.model} hint={tx.verify.modelHint} wide>
            <ModelSelect value={value.model} models={offered} empty={tx.verify.modelNone} onChange={set('model')} />
          </Field>
          <Field label={tx.verify.fallback} hint={tx.verify.fallbackHint} wide>
            <ModelSelect value={value.fallback} models={offered} empty={tx.verify.fallbackNone} onChange={set('fallback')} />
          </Field>
          <div className="field--wide">
            <Check checked={narrow} onChange={setNarrow}>
              {tx.verify.narrow(selectable.length, all.length)}
            </Check>
          </div>
          <Field label={tx.verify.timeout} hint={timeout !== null ? tx.seconds(duration(timeout)) : undefined} error={timeout === null ? tx.needInteger : undefined}>
            <input className="input num" inputMode="numeric" value={value.timeout_s} onChange={(event) => set('timeout_s')(event.target.value)} />
          </Field>
          <Field label={tx.verify.thinking} hint={tx.verify.thinkingHint}>
            <ThinkingSelect value={value.thinking} levels={levels} onChange={set('thinking')} />
          </Field>
        </div>
        {!value.model && <Notice kind="warn">{tx.verify.noModel}</Notice>}
        {value.model && value.model === value.fallback && <Notice kind="warn">{tx.verify.same}</Notice>}
        {value.model && !value.fallback && <Notice>{tx.verify.noFallback}</Notice>}
        {save.error && <Notice kind="error">{errorText(save.error)}</Notice>}
        <div className="row">
          <Button variant="primary" busy={save.isPending} disabled={!dirty || timeout === null} onClick={() => timeout !== null && save.mutate({ verify: { ...value, timeout_s: timeout } })}>
            {tx.verify.save}
          </Button>
          <Button disabled={Object.keys(draft).length === 0} onClick={() => setDraft({})}>
            {tx.discard}
          </Button>
        </div>
      </div>
      <aside className="stack">
        <Notice>{tx.verify.never}</Notice>
        <p className="muted small">{tx.verify.readOnly}</p>
        <p className="muted small">{tx.verify.perBatch}</p>
      </aside>
    </div>
  )
}

function ModelSelect(props: { value: string; models: Model[]; empty: string; onChange: (value: string) => void }) {
  const groups = useMemo(() => {
    const out = new Map<string, Model[]>()
    for (const model of props.models) {
      const name = model.platform_name ?? model.platform_id
      out.set(name, [...(out.get(name) ?? []), model])
    }
    return [...out.entries()]
  }, [props.models])
  const listed = !props.value || props.models.some((model) => model.id === props.value)
  return (
    <select className="select" value={props.value} onChange={(event) => props.onChange(event.target.value)}>
      <option value="">{props.empty}</option>
      {!listed && <option value={props.value}>{tx.verify.unlisted(props.value)}</option>}
      {groups.map(([platform, models]) => (
        <optgroup key={platform} label={platform}>
          {models.map((model) => (
            <option key={model.id} value={model.id}>
              {model.name} · {model.model_id}
            </option>
          ))}
        </optgroup>
      ))}
    </select>
  )
}

// --------------------------------------------------------------------------- Vorgaben

type Run = AppSettings['run']
type NumberKey = 'timeout_s' | 'cost_limit' | 'max_steps' | 'tool_timeout_s' | 'max_output_tokens' | 'api_retries'

const NUMBERS: { key: NumberKey; integer: boolean; seconds?: boolean }[] = [
  { key: 'timeout_s', integer: true, seconds: true },
  { key: 'cost_limit', integer: false },
  { key: 'max_steps', integer: true },
  { key: 'tool_timeout_s', integer: true, seconds: true },
  { key: 'max_output_tokens', integer: true },
  { key: 'api_retries', integer: true },
]

export function RunDefaults() {
  const settings = useSettings()
  const meta = useMeta()
  if (settings.isLoading) return <Loading />
  if (!settings.data) return <ErrorNote error={settings.error} />
  return (
    <div role="tabpanel">
      <Section title={tx.run.title} note={tx.run.note}>
        <RunForm saved={settings.data.run} levels={meta.data?.thinking_levels ?? ['']} />
      </Section>
    </div>
  )
}

function RunForm({ saved, levels }: { saved: Run; levels: string[] }) {
  const [draft, setDraft] = useState<Partial<Record<keyof Run, string>>>({})
  const save = useSave(() => setDraft({}))
  const set = (key: keyof Run) => (text: string) => setDraft((current) => ({ ...current, [key]: text }))

  const texts = Object.fromEntries(NUMBERS.map(({ key }) => [key, draft[key] ?? asText(saved[key])])) as Record<NumberKey, string>
  const numbers = Object.fromEntries(NUMBERS.map(({ key, integer }) => [key, parse(texts[key], integer)])) as Record<NumberKey, number | null>
  const thinking = draft.thinking ?? saved.thinking
  const codesText = draft.blocked_codes ?? saved.blocked_codes.join(', ')
  const codes = codesText.split(/[,;\s]+/).map((code) => code.trim().toUpperCase()).filter(Boolean)
  const badCodes = codes.filter((code) => !/^([A-Z]|[A-Z]{3})$/.test(code))

  const valid = NUMBERS.every(({ key }) => numbers[key] !== null) && badCodes.length === 0
  const dirty =
    NUMBERS.some(({ key }) => numbers[key] !== saved[key]) ||
    thinking !== saved.thinking ||
    [...new Set(codes)].sort().join(',') !== [...saved.blocked_codes].sort().join(',')

  return (
    <div className="panel stack">
      <div className="form-grid">
        {NUMBERS.map(({ key, integer, seconds }) => {
          const value = numbers[key]
          const hint = seconds && value !== null ? `${tx.run.field[key].hint} ${tx.seconds(duration(value))}` : tx.run.field[key].hint
          return (
            <Field key={key} label={tx.run.field[key].label} hint={hint} error={value === null ? (integer ? tx.needInteger : tx.needNumber) : undefined}>
              <input className="input num" inputMode={integer ? 'numeric' : 'decimal'} value={texts[key]} onChange={(event) => set(key)(event.target.value)} />
            </Field>
          )
        })}
        <Field label={tx.run.thinking} hint={tx.run.thinkingHint}>
          <ThinkingSelect value={thinking} levels={levels} onChange={set('thinking')} />
        </Field>
        <Field label={tx.run.blocked} hint={tx.run.blockedHint} error={badCodes.length > 0 ? tx.run.blockedBad(badCodes) : undefined} wide>
          <input className="input mono" value={codesText} onChange={(event) => set('blocked_codes')(event.target.value)} placeholder="AAA, AAB" spellCheck={false} />
        </Field>
      </div>
      {save.error && <Notice kind="error">{errorText(save.error)}</Notice>}
      <div className="row">
        <Button variant="primary" busy={save.isPending} disabled={!dirty || !valid} onClick={() => save.mutate({ run: { ...(numbers as Record<NumberKey, number>), thinking, blocked_codes: codes } })}>
          {tx.run.save}
        </Button>
        <Button disabled={Object.keys(draft).length === 0} onClick={() => setDraft({})}>
          {tx.discard}
        </Button>
      </div>
    </div>
  )
}
