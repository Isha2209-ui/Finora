import { useState } from 'react'
import { Check, RotateCcw, X } from 'lucide-react'
import { api } from '../api'
import { Badge, Card, Empty, ErrorBox, Loading, PageHeader, Stat, cx } from '../components/ui.jsx'
import { inr } from '../format'
import { useAsync, useFinora } from '../store.jsx'

export default function Recommendations() {
  const { profileId } = useFinora()
  const { data, loading, error, reload } = useAsync(() => api.recommendations(profileId), [profileId])
  const [filter, setFilter] = useState('open')
  if (loading && !data) return <Loading full />
  if (error) return <ErrorBox message={error} onRetry={reload} />
  const open = data.filter((r) => r.status === 'open')
  const shown = data.filter((r) => filter === 'all' || r.status === filter)
  const set = async (r, status) => { await api.setRecStatus(profileId, r.id, status); reload() }
  const impact = open.reduce((s, r) => s + (r.impact_inr > 0 ? r.impact_inr : 0), 0)
  return (
    <>
      <PageHeader title="Recommendations" subtitle="Each recommendation is produced by a rule that combines model findings with your numbers. It shows its evidence, why it matters, what to do and the rupee impact when that can be calculated." />
      <div className="grid gap-4 md:grid-cols-4">
        <Stat label="Open" value={open.length} />
        <Stat label="High priority" value={open.filter((r) => r.priority === 'high').length} tone="bad" />
        <Stat label="Quantified yearly impact" value={inr(impact)} tone="good" sub="sum of open items with a calculated impact" />
        <Stat label="Accepted / dismissed" value={`${data.filter((r) => r.status === 'accepted').length} / ${data.filter((r) => r.status === 'dismissed').length}`} />
      </div>
      <div className="mt-4 flex gap-2">
        {['open', 'accepted', 'dismissed', 'all'].map((f) => <button key={f} onClick={() => setFilter(f)} className={cx('rounded-full border px-3 py-1 text-xs capitalize', filter === f ? 'border-accent/50 bg-accent/15 text-accent' : 'border-line text-muted hover:text-ink')}>{f}</button>)}
      </div>
      <div className="mt-3 space-y-3">
        {shown.length === 0 && <Card><Empty title={`No ${filter} recommendations`} /></Card>}
        {shown.map((r, i) => (
          <article key={r.id} className={cx('rounded-2xl border bg-surface p-5', r.status !== 'open' ? 'border-line opacity-70' : r.priority === 'high' ? 'border-bad/30' : 'border-line')}>
            <div className="flex flex-wrap items-start gap-3">
              <span className="num grid h-7 w-7 shrink-0 place-items-center rounded-full bg-raised text-xs text-muted">{i + 1}</span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2"><h3 className="text-[15px] font-semibold">{r.finding}</h3><Badge tone={r.priority}>{r.priority} priority</Badge>
                  {r.status !== 'open' && <Badge tone={r.status === 'accepted' ? 'good' : 'neutral'}>{r.status}</Badge>}</div>
                <dl className="mt-3 grid gap-x-6 gap-y-2 text-sm md:grid-cols-[110px_1fr]">
                  <dt className="text-faint">Evidence</dt><dd className="num text-ink/90">{r.evidence}</dd>
                  <dt className="text-faint">Why it matters</dt><dd className="text-muted">{r.explanation}</dd>
                  <dt className="text-faint">What to do</dt><dd className="font-medium text-accent">{r.action}</dd>
                  {r.impact_text && <><dt className="text-faint">Impact</dt><dd className="num text-good">{r.impact_text}</dd></>}
                </dl>
                <div className="mt-3 text-[11px] text-faint">Source: {r.source}</div>
              </div>
              <div className="flex gap-2">
                {r.status === 'open' ? (<>
                  <button onClick={() => set(r, 'accepted')} title="I'll do this" className="flex items-center gap-1 rounded-lg border border-good/40 bg-good/10 px-2.5 py-1.5 text-xs text-good hover:bg-good/20"><Check size={13} /> Accept</button>
                  <button onClick={() => set(r, 'dismissed')} title="Not relevant" className="flex items-center gap-1 rounded-lg border border-line bg-raised px-2.5 py-1.5 text-xs text-muted hover:text-ink"><X size={13} /> Dismiss</button>
                </>) : <button onClick={() => set(r, 'open')} className="flex items-center gap-1 rounded-lg border border-line bg-raised px-2.5 py-1.5 text-xs text-muted hover:text-ink"><RotateCcw size={13} /> Reopen</button>}
              </div>
            </div>
          </article>
        ))}
      </div>
    </>
  )
}
