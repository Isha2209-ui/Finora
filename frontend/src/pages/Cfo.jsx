import { Bell, CalendarDays, Info, ShieldAlert, TriangleAlert } from 'lucide-react'
import { api } from '../api'
import ChatPanel from '../components/ChatPanel.jsx'
import { Badge, Card, ErrorBox, Loading, PageHeader } from '../components/ui.jsx'
import { monthLabel } from '../format'
import { useAsync, useFinora } from '../store.jsx'

const ICON = { critical: [ShieldAlert, 'text-bad'], warning: [TriangleAlert, 'text-warn'], info: [Info, 'text-info'] }

export default function Cfo() {
  const { profileId } = useFinora()
  const b = useAsync(() => api.briefing(profileId), [profileId])
  return (
    <>
      <PageHeader title="AI CFO" subtitle="Ask anything in your own words. A language model running on this computer reads your question, looks up your Finora data and models itself, and answers; every figure it states is checked against Finora's calculations." />
      <div className="grid gap-4 xl:grid-cols-[1fr_440px]">
        <div className="space-y-4">
          <Card title={b.data ? `Monthly briefing · ${monthLabel(b.data.month)}` : 'Monthly briefing'} action={b.data && <Badge tone="accent"><CalendarDays size={11} /> {b.data.engine === 'rules' ? 'rule-written' : b.data.engine}</Badge>}>
            {b.loading ? <Loading label="Preparing your briefing…" /> : b.error ? <ErrorBox message={b.error} onRetry={b.reload} /> : (
              <>
                <p className="text-[15px] leading-relaxed">{b.data.briefing}</p>
                <div className="mt-4 text-xs font-medium uppercase tracking-wider text-faint">This month's priorities</div>
                <ol className="mt-2 space-y-2">
                  {b.data.priorities.map((p, i) => (
                    <li key={i} className="flex gap-3 rounded-xl border border-line bg-raised/50 p-3 text-sm">
                      <span className="num grid h-6 w-6 shrink-0 place-items-center rounded-full bg-accent/15 text-xs text-accent">{i + 1}</span>
                      <div><div className="font-medium">{p.finding} <Badge tone={p.priority} className="ml-1">{p.priority}</Badge></div><div className="mt-0.5 text-muted">{p.action}</div></div>
                    </li>
                  ))}
                </ol>
              </>
            )}
          </Card>
          <Card title="Alerts" action={<Bell size={15} className="text-faint" />}>
            {b.data?.alerts?.length ? (
              <ul className="space-y-2">
                {b.data.alerts.map((al) => { const [I, c] = ICON[al.level] || ICON.info; return (
                  <li key={al.code} className="flex items-start gap-2.5 text-sm"><I size={16} className={`mt-0.5 shrink-0 ${c}`} /><div><div className="font-medium">{al.title}</div><div className="text-xs text-muted">{al.detail}</div></div></li>) })}
              </ul>
            ) : <p className="text-sm text-muted">No alerts right now.</p>}
          </Card>
          <Card title="How the assistant stays accurate">
            <ol className="grid gap-3 text-sm md:grid-cols-4">
              {[['1 · Plan', 'Qwen 2.5 (3B), running locally through Ollama, turns your question into a short plan (what to look up, which category, period and count), using what this conversation has already established. Finora checks the plan before anything runs. Nothing leaves this computer.'],
                ['2 · Look up', 'Finora runs the planned look-ups (spending, transactions, accounts, plan, credit risk, forecast, scanner, peers, what-ifs) and does the arithmetic itself. The tools only read your signed-in profile.'],
                ['3 · Answer', 'It writes the answer from the tool results, with each model\'s limitations. It cannot change anything in Finora.'],
                ['4 · Verify', 'Every figure is checked against this question\'s results, and the answer must cover what was asked (category, period, count). If it fails, it is rewritten once; if that fails, a calculator-written answer is shown instead.']].map(([t, d]) => (
                <li key={t} className="rounded-xl bg-raised p-3"><div className="text-xs font-semibold text-accent">{t}</div><div className="mt-1 text-xs leading-relaxed text-muted">{d}</div></li>))}
            </ol>
          </Card>
        </div>
        <div className="h-[calc(100vh-190px)] min-h-[520px] overflow-hidden rounded-2xl border border-line bg-surface xl:sticky xl:top-0"><ChatPanel wide /></div>
      </div>
    </>
  )
}
