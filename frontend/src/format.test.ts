import { describe, expect, it } from 'vitest'
import { duration, durationSpan, num, percent, plural, tokens, usd } from './format'

describe('format', () => {
  it('zeigt einen fehlenden Preis nie als 0 $', () => {
    expect(usd(null)).toBe('kein Preis')
    expect(usd(undefined)).toBe('kein Preis')
    expect(usd(0)).toBe('0,000 $')
  })
  it('wählt die Nachkommastellen nach Größe', () => {
    expect(usd(0.0312)).toBe('0,031 $')
    expect(usd(4.5)).toBe('4,50 $')
    expect(usd(1234.5)).toBe('1.235 $')
  })
  it('formatiert Dauern', () => {
    expect(duration(42)).toBe('42 s')
    expect(duration(131)).toBe('2:11 min')
    expect(duration(3725)).toBe('1:02 h')
    expect(duration(null)).toBe('–')
  })
  it('nennt bei einer Spanne dieselbe Einheit nur einmal', () => {
    expect(durationSpan(30, 35)).toBe('30–35 s')
    expect(durationSpan(85, 115)).toBe('1:25–1:55 min')
    expect(durationSpan(37, 69)).toBe('37 s – 1:09 min')
    expect(durationSpan(32, 32)).toBe('32 s')
    expect(durationSpan(null, null)).toBe('–')
  })
  it('kürzt große Token-Zahlen', () => {
    expect(tokens(950)).toBe('950')
    expect(tokens(61000)).toBe('61 Tsd.')
    expect(tokens(1250000)).toBe('1,25 Mio.')
  })
  it('formatiert Zahlen, Anteile und Mengen', () => {
    expect(num(1234.5, 1)).toBe('1.234,5')
    expect(percent(0.875)).toBe('88 %')
    expect(plural(1, 'Lauf', 'Läufe')).toBe('1 Lauf')
    expect(plural(3, 'Lauf', 'Läufe')).toBe('3 Läufe')
  })
})
