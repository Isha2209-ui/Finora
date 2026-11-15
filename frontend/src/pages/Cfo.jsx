// Ask: the local AI CFO (Phase 7 engine). Conversation in its own scroll container; briefing, alerts and method in a side rail.
import { Bell, CalendarDays, Info, ShieldAlert, TriangleAlert } from 'lucide-react'
import { api } from '../api'
import ChatPanel from '../components/ChatPanel.jsx'
import { Badge, ErrorBox, Loading } from '../components/ui.jsx'
import { present } from '../components/models.js'
import { monthLabel } from '../format'
import { useAsync, useFinora } from '../store.jsx'

const ICON = { critical: [ShieldAlert, 'text-bad'], warning: [TriangleAlert, 'text-warn'], info: [Info, 'text-info'] }
const STEPS = [
  ['Plan', 'The local model (Qwen 2.5, 3B, via Ollama) turns your question into a short plan: what to look up, which category, period and count. Finora checks the plan before anything runs.'],
  ['Look up', 'Finora runs the planned look-ups on your signed-in profile only and does the arithmetic itself.'],
  ['Answer', 'The answer is written from those results, with each model’s limitations. It cannot change anything in Finora.'],
  ['Verify', 'Every figure is checked against this question’s results and the question itself. A failing draft is rewritten once, then replaced by a calculator-written answer.'],
]

export default function Cfo() {
  const { profileId } = useFinora()
  const b = useAsync(() => api.briefing(profileId), [profileId])
  return (
    <div className="flex h-full min-h-0">
      <h1 className="sr-only">Ask Finora</h1>
      <section aria-label="Conversation" className="flex min-w-0 flex-1 flex-col"><ChatPanel variant="page" /></section>
      <aside aria-label="Briefing and method" className="hidden w-[340px] shrink-0 overflow-y-auto border-l border-line bg-canvas px-5 py-6 xl:block">
        <div className="flex items-center justify-between"><h2 className="text-[15px] font-semibold text-ink">{b.data ? `Briefing · ${monthLabel(b.data.month)}` : 'Monthly briefing'}</h2>
          {b.data && <Badge tone="accent"><CalendarDays size={11} aria-hidden /> {b.data.engine === 'rules' ? 'rule-written' : b.data.engine}</Badge>}</div>
        {b.loading ? <Loading label="Preparing your briefing…" /> : b.error ? <div className="mt-3"><ErrorBox message={b.error} onRetry={b.reload} /></div> : (
          <>
            <p className="mt-2 text-sm leading-6 text-ink-2">{b.data.briefing}</p>
            {b.data.priorities.length > 0 && <>
              <h3 className="mt-5 text-micro font-medium uppercase tracking-[0.06em] text-faint">This month’s priorities</h3>
              <ol className="mt-2 space-y-2">{b.data.priorities.map((p, i) => (
                <li key={i} className="rounded-lg border border-line bg-bg p-3 text-[13px]"><div className="font-medium text-ink">{p.finding}</div><div className="mt-0.5 text-muted">{p.action}</div></li>))}</ol>
            </>}
          </>
        )}
        <h2 className="mt-8 flex items-center gap-2 text-[15px] font-semibold text-ink"><Bell size={15} className="text-faint" aria-hidden /> Alerts</h2>
        {b.data?.alerts?.length ? (
          <ul className="mt-2 space-y-2">{b.data.alerts.map((al) => { const [I, c] = ICON[al.level] || ICON.info; return (
            <li key={al.code} className="flex items-start gap-2.5 text-[13px]"><I size={15} className={`mt-0.5 shrink-0 ${c}`} aria-hidden /><div><div className="font-medium text-ink">{al.title}</div><div className="text-muted">{present(al.detail)}</div></div></li>) })}</ul>
        ) : <p className="mt-2 text-[13px] text-muted">{b.loading ? '' : 'No alerts right now.'}</p>}
        <h2 className="mt-8 text-[15px] font-semibold text-ink">How answers are checked</h2>
        <ol className="mt-3 space-y-3">{STEPS.map(([t, d], i) => (
          <li key={t} className="flex gap-3 text-[13px]"><span className="num grid h-6 w-6 shrink-0 place-items-center rounded-full bg-accent-soft text-micro font-semibold text-accent">{i + 1}</span>
            <div><div className="font-medium text-ink">{t}</div><div className="mt-0.5 leading-5 text-muted">{d}</div></div></li>))}</ol>
        <p className="mt-6 text-micro leading-4 text-faint">Nothing you ask leaves this computer.</p>
      </aside>
    </div>
  )
}
