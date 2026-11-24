// Sprachdatei der Oberfläche: je Seite eine Datei, hier zusammengeführt.
import { analysis } from './analysis'
import { cleanup } from './cleanup'
import { common } from './common'
import { live } from './live'
import { overview } from './overview'
import { run } from './run'
import { settings } from './settings'
import { start } from './start'
import { tasks } from './tasks'

export const t = { common, overview, start, live, analysis, run, tasks, cleanup, settings }
