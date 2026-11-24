// Einstellungen: BW-Systeme, MCP-Server, LLM-Plattformen, Prüfung, Vorgaben.
import { Link, useNavigate, useParams } from 'react-router-dom'
import { t } from '../texts'
import { Glyph, Page, Section, Tabs } from '../ui'
import { useStatus, type Status } from '../ui/Shell'
import BwSystems from './settings/BwSystems'
import { RunDefaults, VerifySettings } from './settings/General'
import McpServers from './settings/McpServers'
import Platforms from './settings/Platforms'
import '../styles/settings.css'

const tx = t.settings

const TABS = ['bw', 'mcp', 'plattformen', 'pruefung', 'vorgaben'] as const
type TabId = (typeof TABS)[number]

/** Wo sich ein offener Punkt der Checkliste erledigen lässt. */
const READY_TAB: Record<string, TabId> = {
  bw_system: 'bw',
  bw_password: 'bw',
  mcp_server: 'mcp',
  models: 'plattformen',
  verifier: 'pruefung',
}

export default function Settings() {
  const params = useParams()
  const navigate = useNavigate()
  const status = useStatus()
  const tab: TabId = TABS.find((id) => id === params.tab) ?? 'bw'

  return (
    <Page title={tx.title} lead={tx.lead}>
      {status.data && !status.data.ready && <Readiness items={status.data.readiness} current={tab} />}
      <div className="settings-tabs">
        <Tabs tabs={TABS.map((id) => ({ id, label: tx.tabs[id] }))} value={tab} onChange={(id) => navigate(`/einstellungen/${id}`)} />
      </div>
      {tab === 'bw' && <BwSystems />}
      {tab === 'mcp' && <McpServers />}
      {tab === 'plattformen' && <Platforms />}
      {tab === 'pruefung' && <VerifySettings />}
      {tab === 'vorgaben' && <RunDefaults />}
    </Page>
  )
}

/** Was für den ersten Durchgang noch fehlt; verschwindet, sobald alles erledigt ist. */
function Readiness({ items, current }: { items: Status['readiness']; current: TabId }) {
  const open = items.filter((item) => !item.ok).length
  return (
    <Section title={tx.ready.title} note={tx.ready.note(items.length - open, items.length)}>
      <ul className="panel settings-ready">
        {items.map((item) => {
          const target = READY_TAB[item.key]
          const text = tx.ready.items[item.key]
          return (
            <li key={item.key}>
              <span className={`state state--${item.ok ? 'pass' : 'warn'}`}>
                <Glyph kind={item.ok ? 'pass' : 'open'} />
                {item.ok ? tx.ready.done : tx.ready.open}
              </span>
              <span>
                {text?.label ?? item.key}
                {!item.ok && text && <span className="muted"> · {text.todo}</span>}
              </span>
              {!item.ok && target && (target === current ? <span className="muted">{tx.ready.here}</span> : <Link to={`/einstellungen/${target}`}>{tx.ready.go(tx.tabs[target])}</Link>)}
            </li>
          )
        })}
      </ul>
    </Section>
  )
}
