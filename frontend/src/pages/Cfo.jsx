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
      <PageHeader title="AI CFO" subtitle="Your personal finance assistant. It picks the right calculator or model, then explains the result - and every figure it states is checked against that result before you see it." />
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
              {[['1 · Route', 'Rules recognise the question and choose the calculator or model. Open-ended questions use the language model’s tool-calling.'],
                ['2 · Compute', 'The backend runs the calculation on your real data. The language model never does arithmetic.'],
                ['3 · Explain', 'The local model (Qwen via Ollama, or Nemotron) writes a plain-language explanation of the result.'],
                ['4 · Verify', 'Every number in the explanation is checked against the computed result. If one does not match, the text is discarded and a rule-written answer is shown.']].map(([t, d]) => (
                <li key={t} className="rounded-xl bg-raised p-3"><div className="text-xs font-semibold text-accent">{t}</div><div className="mt-1 text-xs leading-relaxed text-muted">{d}</div></li>))}
            </ol>
          </Card>
        </div>
        <div className="h-[calc(100vh-190px)] min-h-[520px] overflow-hidden rounded-2xl border border-line bg-surface xl:sticky xl:top-0"><ChatPanel wide /></div>
      </div>
    </>
  )
}
