// Lauf-Detail: ohne Nummer die Laufauswahl, mit Nummer der einzelne Lauf.
import { useParams } from 'react-router-dom'
import { Detail } from './run/Detail'
import { Picker } from './run/Picker'
import '../styles/run.css'

export default function RunDetail() {
  const { id } = useParams()
  // Der Schlüssel setzt beim Wechsel des Laufs alle Zustände der Seite zurück.
  return id ? <Detail key={id} id={id} /> : <Picker />
}
