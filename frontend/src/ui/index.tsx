// Gemeinsame Bausteine der Oberfläche. Gestaltung: styles/base.css.
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ButtonHTMLAttributes,
  type ReactNode,
} from 'react'
import { t } from '../texts'

// --------------------------------------------------------------------------- Seite

export function Page(props: { title: string; lead?: ReactNode; actions?: ReactNode; meta?: ReactNode; aside?: ReactNode; asideLabel?: string; children: ReactNode }) {
  useEffect(() => {
    document.title = `${props.title} – ${t.common.appName}`
  }, [props.title])
  return (
    <div className="page-wrap">
      {props.aside && (
        <aside className="facets" aria-label={props.asideLabel}>
          {props.aside}
        </aside>
      )}
      <div className="page">
        <header className={`page__head${props.meta ? ' page__head--meta' : ''}`}>
          <div>
            <h1 className="page__title">{props.title}</h1>
            {props.lead && <p className="page__lead">{props.lead}</p>}
          </div>
          {props.actions && <div className="page__actions">{props.actions}</div>}
          {props.meta && <div className="page__meta">{props.meta}</div>}
        </header>
        {props.children}
      </div>
    </div>
  )
}

export function Section(props: { title?: ReactNode; note?: ReactNode; actions?: ReactNode; children: ReactNode; id?: string }) {
  return (
    <section className="section" id={props.id}>
      {(props.title || props.actions) && (
        <div className="section__head">
          <div>
            {props.title && <h2 className="section__title">{props.title}</h2>}
            {props.note && <p className="section__note">{props.note}</p>}
          </div>
          {props.actions && <div className="row">{props.actions}</div>}
        </div>
      )}
      {props.children}
    </section>
  )
}

// --------------------------------------------------------------------------- Schaltflächen, Felder

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'default' | 'primary' | 'danger' | 'quiet'
  small?: boolean
  busy?: boolean
}

export function Button({ variant = 'default', small, busy, className, children, disabled, ...rest }: ButtonProps) {
  const classes = ['btn', variant !== 'default' && `btn--${variant}`, small && 'btn--small', className].filter(Boolean).join(' ')
  return (
    <button type="button" className={classes} disabled={disabled || busy} aria-busy={busy || undefined} {...rest}>
      {children}
    </button>
  )
}

export function Field(props: { label: ReactNode; hint?: ReactNode; error?: ReactNode; wide?: boolean; children: ReactNode }) {
  return (
    <label className={`field${props.wide ? ' field--wide' : ''}`}>
      <span className="field__label">{props.label}</span>
      {props.children}
      {props.hint && <span className="field__hint">{props.hint}</span>}
      {props.error && <span className="field__error">{props.error}</span>}
    </label>
  )
}

export function Check(props: { checked: boolean; onChange: (value: boolean) => void; children: ReactNode; disabled?: boolean }) {
  return (
    <label className="check">
      <input type="checkbox" checked={props.checked} disabled={props.disabled} onChange={(e) => props.onChange(e.target.checked)} />
      <span>{props.children}</span>
    </label>
  )
}

/** Auswahlchips: alle Werte sichtbar, gewählte hervorgehoben. */
export function Chips<T extends string>(props: {
  options: readonly T[] | { value: T; label: ReactNode }[]
  value: T[]
  onChange: (value: T[]) => void
  single?: boolean
  label?: (value: T) => ReactNode
  ariaLabel?: string
}) {
  const items: { value: T; label: ReactNode }[] = (props.options as any[]).map((o) =>
    typeof o === 'string' ? { value: o as T, label: props.label ? props.label(o as T) : o } : o,
  )
  const toggle = (value: T) => {
    if (props.single) return props.onChange(props.value.includes(value) ? [] : [value])
    props.onChange(props.value.includes(value) ? props.value.filter((v) => v !== value) : [...props.value, value])
  }
  return (
    <div className="chips" role="group" aria-label={props.ariaLabel}>
      {items.map((item) => (
        <button key={item.value} type="button" className="chip" aria-pressed={props.value.includes(item.value)} onClick={() => toggle(item.value)}>
          {item.label}
        </button>
      ))}
    </div>
  )
}

export function Tabs<T extends string>(props: { tabs: { id: T; label: ReactNode }[]; value: T; onChange: (id: T) => void }) {
  return (
    <div className="tabs" role="tablist">
      {props.tabs.map((tab) => (
        <button key={tab.id} type="button" role="tab" className="tab" aria-selected={tab.id === props.value} onClick={() => props.onChange(tab.id)}>
          {tab.label}
        </button>
      ))}
    </div>
  )
}

// --------------------------------------------------------------------------- Zustände

type GlyphKind = 'pass' | 'fail' | 'open' | 'invalid' | 'warn' | 'live' | 'dot' | 'skip'

/** Zeichen je Zustand: Die Form trägt die Bedeutung, nicht nur die Farbe. */
export function Glyph({ kind, size = 12 }: { kind: GlyphKind; size?: number }) {
  const common = { width: size, height: size, viewBox: '0 0 12 12', 'aria-hidden': true } as const
  switch (kind) {
    case 'pass':
      return (
        <svg {...common}>
          <rect x="1" y="1" width="10" height="10" fill="currentColor" />
        </svg>
      )
    case 'fail':
      return (
        <svg {...common}>
          <rect x="2" y="2" width="8" height="8" fill="none" stroke="currentColor" strokeWidth="2" />
        </svg>
      )
    case 'open':
      return (
        <svg {...common}>
          <rect x="1.5" y="1.5" width="9" height="9" fill="none" stroke="currentColor" strokeWidth="1.2" />
          <circle cx="6" cy="6" r="1.8" fill="currentColor" />
        </svg>
      )
    case 'invalid':
      return (
        <svg {...common}>
          <rect x="1.5" y="1.5" width="9" height="9" fill="none" stroke="currentColor" strokeWidth="1.2" />
          <path d="M3.5 6 H8.5" stroke="currentColor" strokeWidth="1.8" />
        </svg>
      )
    case 'warn':
      return (
        <svg {...common}>
          <path d="M6 1 L11.2 10.5 H0.8 Z" fill="currentColor" />
        </svg>
      )
    case 'live':
      return (
        <svg {...common}>
          <circle cx="6" cy="6" r="4" fill="none" stroke="currentColor" strokeWidth="2.4" />
        </svg>
      )
    case 'skip':
      return (
        <svg {...common}>
          <path d="M2 6 H10" stroke="currentColor" strokeWidth="2" />
        </svg>
      )
    default:
      return (
        <svg {...common}>
          <circle cx="6" cy="6" r="2.5" fill="currentColor" />
        </svg>
      )
  }
}

const VERIFY: Record<string, { glyph: GlyphKind; tone: string }> = {
  pass: { glyph: 'pass', tone: 'pass' },
  fail: { glyph: 'fail', tone: 'fail' },
  unclear: { glyph: 'open', tone: 'warn' },
  invalid: { glyph: 'invalid', tone: 'warn' },
  error: { glyph: 'warn', tone: 'warn' },
  not_verified: { glyph: 'open', tone: 'neutral' },
}

/** Prüfurteil eines Laufs. */
export function Verdict({ status, short }: { status: string | null | undefined; short?: boolean }) {
  const key = status || 'not_verified'
  const look = VERIFY[key] ?? VERIFY.not_verified
  const label = t.common.verify[key] ?? key
  return (
    <span className={`state state--${look.tone}`} title={short ? label : undefined}>
      <Glyph kind={look.glyph} />
      {!short && label}
    </span>
  )
}

const RUN: Record<string, { glyph: GlyphKind; tone: string }> = {
  planned: { glyph: 'dot', tone: 'neutral' },
  running: { glyph: 'live', tone: 'live' },
  finished: { glyph: 'dot', tone: 'neutral' },
  error: { glyph: 'warn', tone: 'warn' },
  timeout: { glyph: 'warn', tone: 'warn' },
  step_limit: { glyph: 'warn', tone: 'warn' },
  cancelled: { glyph: 'skip', tone: 'neutral' },
  skipped: { glyph: 'skip', tone: 'neutral' },
  mcp_missing: { glyph: 'warn', tone: 'warn' },
  no_result: { glyph: 'warn', tone: 'warn' },
  done: { glyph: 'dot', tone: 'neutral' },
}

/** Technischer Status eines Laufs oder Durchgangs. */
export function RunState({ status, batch }: { status: string; batch?: boolean }) {
  const look = RUN[status] ?? RUN.finished
  const label = (batch ? t.common.batchStatus[status] : t.common.runStatus[status]) ?? status
  return (
    <span className={`state state--${look.tone}`}>
      <Glyph kind={look.glyph} />
      {label}
    </span>
  )
}

const BW: Record<string, { glyph: GlyphKind; tone: string }> = {
  ok: { glyph: 'pass', tone: 'pass' },
  partly: { glyph: 'warn', tone: 'warn' },
  down: { glyph: 'fail', tone: 'fail' },
  unknown: { glyph: 'open', tone: 'neutral' },
}

/** Erreichbarkeit eines BW-Systems: Zeichen, Text und Erklärung beim Darüberfahren. */
export function BwState({ status, system }: { status: { state: string; detail: string } | null | undefined; system?: string }) {
  const state = status?.state ?? 'unknown'
  const look = BW[state] ?? BW.unknown
  return (
    <span className={`state state--${look.tone}`} title={status?.detail}>
      <Glyph kind={look.glyph} />
      {system ? `${system} ${t.common.bw[state]}` : t.common.bw[state]}
    </span>
  )
}

export function Tag({ children, title }: { children: ReactNode; title?: string }) {
  return (
    <span className="tag" title={title}>
      {children}
    </span>
  )
}

export function Notice(props: { kind?: 'info' | 'warn' | 'error' | 'ok'; children: ReactNode }) {
  const kind = props.kind ?? 'info'
  const glyph = ({ info: 'dot', warn: 'warn', error: 'fail', ok: 'pass' } as const)[kind]
  return (
    <div className={`notice${kind === 'info' ? '' : ` notice--${kind}`}`} role={kind === 'error' ? 'alert' : 'status'}>
      <span className="notice__icon">
        <Glyph kind={glyph} />
      </span>
      <div>{props.children}</div>
    </div>
  )
}

export function Empty(props: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="empty">
      <p className="empty__title">{props.title}</p>
      {props.children && <div className="empty__text">{props.children}</div>}
      {props.action}
    </div>
  )
}

export function Figure({ value, label }: { value: ReactNode; label: ReactNode }) {
  return (
    <div className="figure">
      <span className="figure__value">{value}</span>
      <span className="figure__label">{label}</span>
    </div>
  )
}

export function Meter({ value, max, warn }: { value: number; max: number; warn?: boolean }) {
  const width = max > 0 ? Math.min(100, (value / max) * 100) : 0
  return (
    <div className="meter" role="progressbar" aria-valuenow={Math.round(width)} aria-valuemin={0} aria-valuemax={100}>
      <div className={`meter__fill${warn ? ' meter__fill--warn' : ''}`} style={{ width: `${width}%` }} />
    </div>
  )
}

export function Loading({ lines = 3 }: { lines?: number }) {
  return (
    <div className="stack" aria-busy="true" aria-label={t.common.loading}>
      {Array.from({ length: lines }, (_, i) => (
        <div key={i} className="skeleton" style={{ width: `${88 - i * 14}%` }} />
      ))}
    </div>
  )
}

export function ErrorNote({ error }: { error: unknown }) {
  if (!error) return null
  return <Notice kind="error">{error instanceof Error ? error.message : String(error)}</Notice>
}

// --------------------------------------------------------------------------- Dialog, Meldungen

export function Dialog(props: { title: ReactNode; onClose: () => void; children: ReactNode; footer?: ReactNode; wide?: boolean }) {
  const ref = useRef<HTMLDivElement>(null)
  // onClose darf sich bei jedem Neuzeichnen ändern, ohne dass der Dialog den Fokus neu setzt.
  const close = useRef(props.onClose)
  close.current = props.onClose
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null
    if (!ref.current?.contains(document.activeElement)) ref.current?.focus()
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') close.current()
    }
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('keydown', onKey)
      previous?.focus?.()
    }
  }, [])
  return (
    <div className="dialog-backdrop" onMouseDown={(e) => e.target === e.currentTarget && close.current()}>
      <div className={`dialog${props.wide ? ' dialog--wide' : ''}`} role="dialog" aria-modal="true" tabIndex={-1} ref={ref}>
        <h2 className="dialog__title">{props.title}</h2>
        {props.children}
        {props.footer && <div className="dialog__foot">{props.footer}</div>}
      </div>
    </div>
  )
}

type Toast = { id: number; text: string; error?: boolean }
const ToastContext = createContext<(text: string, error?: boolean) => void>(() => {})

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const push = useCallback((text: string, error?: boolean) => {
    const id = Date.now() + Math.random()
    setToasts((list) => [...list, { id, text, error }])
    window.setTimeout(() => setToasts((list) => list.filter((x) => x.id !== id)), error ? 9000 : 3500)
  }, [])
  return (
    <ToastContext.Provider value={push}>
      {children}
      <div className="toasts" aria-live="polite">
        {toasts.map((toast) => (
          <div key={toast.id} className={`toast${toast.error ? ' toast--error' : ''}`}>
            {toast.text}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

/** Kurze Rückmeldung nach einer Aktion: toast('Gespeichert') bzw. toast(text, true) für Fehler. */
export function useToast() {
  return useContext(ToastContext)
}

// --------------------------------------------------------------------------- Farbschema

export function useTheme(): [string, () => void] {
  const [theme, setTheme] = useState(() => document.documentElement.dataset.theme || 'light')
  const toggle = useCallback(() => {
    setTheme((current) => {
      const next = current === 'dark' ? 'light' : 'dark'
      document.documentElement.dataset.theme = next
      try {
        localStorage.setItem('aiarena.theme', next)
      } catch {
        /* ohne Speicher gilt das Schema nur für diese Sitzung */
      }
      return next
    })
  }, [])
  return [theme, toggle]
}

/** Aktuelles Farbschema; löst neu aus, wenn es wechselt (z. B. für Diagramme). */
export function useThemeName(): string {
  const [theme, setTheme] = useState(() => document.documentElement.dataset.theme || 'light')
  useEffect(() => {
    const observer = new MutationObserver(() => setTheme(document.documentElement.dataset.theme || 'light'))
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
    return () => observer.disconnect()
  }, [])
  return theme
}

/** Sekundentakt für laufende Anzeigen. */
export function useNow(active = true, intervalMs = 1000): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!active) return
    const id = window.setInterval(() => setNow(Date.now()), intervalMs)
    return () => window.clearInterval(id)
  }, [active, intervalMs])
  return now
}

/** Sortierbare Tabellen: liefert sortierte Zeilen und die Angaben für die Kopfzeile. */
export function useSort<T>(rows: T[], initial: { key: keyof T | string; dir: 'asc' | 'desc' }) {
  const [sort, setSort] = useState(initial)
  const sorted = useMemo(() => {
    const factor = sort.dir === 'asc' ? 1 : -1
    return [...rows].sort((a: any, b: any) => {
      const x = a[sort.key]
      const y = b[sort.key]
      if (x === y) return 0
      if (x === null || x === undefined) return 1
      if (y === null || y === undefined) return -1
      return (typeof x === 'number' && typeof y === 'number' ? x - y : String(x).localeCompare(String(y), 'de')) * factor
    })
  }, [rows, sort])
  const toggle = (key: string) => setSort((s) => (s.key === key ? { key, dir: s.dir === 'asc' ? 'desc' : 'asc' } : { key, dir: 'desc' }))
  const mark = (key: string) =>
    sort.key === key ? (
      <svg className="sort-mark" width="8" height="8" viewBox="0 0 8 8" aria-hidden>
        <path d={sort.dir === 'asc' ? 'M4 1 L7.5 7 H0.5 Z' : 'M0.5 1 H7.5 L4 7 Z'} fill="currentColor" />
      </svg>
    ) : null
  return { sorted, toggle, mark, sort }
}

export type { ButtonProps }
