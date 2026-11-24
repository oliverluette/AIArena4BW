// Wortmarke und Bildmarke „Rangliste“.

/** Bildmarke: drei waagerechte Balken abnehmender Länge; groß mit senkrechter Achse. Farbe folgt der Schrift. */
export function Mark({ size = 36, axis = true }: { size?: number; axis?: boolean }) {
  return (
    <svg role="img" aria-label="AIArena4BW Bildmarke Rangliste" viewBox="0 0 88 88" width={size} height={size} fill="currentColor">
      {axis && <rect x="8" y="10" width="5" height="68" />}
      <rect x="18" y="16" width="62" height="14" />
      <rect x="18" y="37" width="42" height="14" />
      <rect x="18" y="58" width="24" height="14" />
    </svg>
  )
}

/** Wortmarke: der Name in der Schrift der App, fett und schmal gesetzt. */
export function Wordmark({ size = 17 }: { size?: number }) {
  return (
    <span role="img" aria-label="AIArena4BW" style={{ fontSize: size, fontWeight: 700, fontStretch: 'var(--narrow)', lineHeight: 1, whiteSpace: 'nowrap' }}>
      AIArena4BW
    </span>
  )
}
