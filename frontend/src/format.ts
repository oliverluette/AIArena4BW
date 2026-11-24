// Zahlen, Kosten, Dauern und Zeitpunkte in deutscher Schreibweise.

const nf = (digits: number) => new Intl.NumberFormat('de-DE', { minimumFractionDigits: digits, maximumFractionDigits: digits })

export function num(value: number | null | undefined, digits = 0): string {
  return value === null || value === undefined || Number.isNaN(value) ? '–' : nf(digits).format(value)
}

/** Kosten in Dollar; ein fehlender Preis erscheint nie als 0 $. */
export function usd(value: number | null | undefined, digits?: number): string {
  if (value === null || value === undefined) return 'kein Preis'
  const d = digits ?? (Math.abs(value) >= 100 ? 0 : Math.abs(value) >= 1 ? 2 : 3)
  return `${nf(d).format(value)} $`
}

export function tokens(value: number | null | undefined): string {
  if (value === null || value === undefined) return '–'
  if (value >= 1_000_000) return `${nf(2).format(value / 1_000_000)} Mio.`
  if (value >= 10_000) return `${nf(0).format(value / 1000)} Tsd.`
  return nf(0).format(value)
}

export function duration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return '–'
  const s = Math.round(seconds)
  if (s < 60) return `${s} s`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}:${String(s % 60).padStart(2, '0')} min`
  return `${Math.floor(m / 60)}:${String(m % 60).padStart(2, '0')} h`
}

/** Spanne zweier Dauern; steht dieselbe Einheit an beiden, erscheint sie nur einmal: „1:25–1:55 min“. */
export function durationSpan(from: number | null | undefined, to: number | null | undefined): string {
  const a = duration(from)
  const b = duration(to)
  if (a === b) return a
  const [aValue, aUnit] = a.split(' ')
  const unit = b.split(' ')[1]
  return aUnit && aUnit === unit ? `${aValue}–${b}` : `${a} – ${b}`
}

export function percent(value: number | null | undefined, digits = 0): string {
  return value === null || value === undefined ? '–' : `${nf(digits).format(value * 100)} %`
}

export function dateTime(iso: string | null | undefined): string {
  if (!iso) return '–'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })
}

export function day(iso: string | null | undefined): string {
  if (!iso) return '–'
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' })
}

/** Sekunden seit einem Zeitpunkt, für laufende Anzeigen. */
export function secondsSince(iso: string | null | undefined, now: number = Date.now()): number | null {
  if (!iso) return null
  const t = new Date(iso).getTime()
  return Number.isNaN(t) ? null : Math.max(0, (now - t) / 1000)
}

export function plural(n: number, one: string, many: string): string {
  return `${num(n)} ${n === 1 ? one : many}`
}
