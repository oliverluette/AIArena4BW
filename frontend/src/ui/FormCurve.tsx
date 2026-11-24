// Formkurve: ein Kästchen je Lauf in zeitlicher Folge. Die Form trägt das Urteil;
// ein Klick öffnet den Lauf.
import { Link } from 'react-router-dom'
import { t } from '../texts'

export type FormKind = 'pass' | 'fail' | 'open' | 'invalid'
export type FormRun = { id: number; run_code: string; kind: FormKind }

const tx = t.analysis.models

/** Zeigt höchstens `max` Läufe; ältere stehen als Zahl davor. */
export function FormCurve({ runs, max = 10 }: { runs: FormRun[]; max?: number }) {
  const shown = runs.slice(-max)
  const offset = runs.length - shown.length
  return (
    <span className="form">
      {offset > 0 && <span className="form__more">+{offset}</span>}
      {shown.map((run, index) => (
        <Link
          key={run.id}
          to={`/lauf/${run.id}`}
          className={`is-${run.kind}`}
          title={`${run.run_code} · ${tx.form[run.kind]}`}
          aria-label={tx.formRun(offset + index + 1, tx.form[run.kind])}
          onClick={(e) => e.stopPropagation()}
        />
      ))}
    </span>
  )
}

/** Legende der Formen, wie sie Formkurve und Zustandsanzeigen verwenden. */
export function FormLegend({ kinds = ['pass', 'fail', 'open', 'invalid'] }: { kinds?: FormKind[] }) {
  return (
    <>
      {kinds.map((kind) => (
        <span key={kind}>
          <span className="form">
            <i className={`is-${kind}`} />
          </span>{' '}
          {tx.form[kind]}
        </span>
      ))}
    </>
  )
}
