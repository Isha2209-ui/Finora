// Plan → Actions (rule-based recommendations, below the ranked plan steps). Accept / dismiss / reopen persist via the API.
import { Check, RotateCcw, X } from 'lucide-react'
import { api } from '../api'
import { AskAbout, Badge, Button, Card, Empty, ErrorBox, Loading, PageHeader, Segmented, Stat, cx, useToast, useUrlParam } from '../components/ui.jsx'
import { present } from '../components/models.js'
import { inr } from '../format'
import { useAsync, useFinora } from '../store.jsx'

const FILTERS = [{ id: 'open', label: 'Open' }, { id: 'accepted', label: 'Accepted' }, { id: 'dismissed', label: 'Dismissed' }, { id: 'all', label: 'All' }]

export default function Recommendations() {
  const { profileId, profile } = useFinora()
  const toast = useToast()
  const { data, loading, error, reload } = useAsync(() => api.recommendations(profileId), [profileId])
  const [filter, setFilter] = useUrlParam('status', FILTERS.map((f) => f.id))
  if (loading && !data) return <Loading />
  if (error) return <ErrorBox message={error} onRetry={reload} />
  const readOnly = profile?.kind === 'template'
  const open = data.filter((r) => r.status === 'open')
  const shown = data.filter((r) => filter === 'all' || r.status === filter)
  const set = async (r, status) => {
    try { await api.setRecStatus(profileId, r.id, status); await reload(); toast(status === 'open' ? 'Recommendation reopened' : `Marked as ${status}`, { tone: 'good' }) }
    catch (e) { toast(e.message, { tone: 'bad' }) }
  }
  const impact = open.reduce((s, r) => s + (r.impact_inr > 0 ? r.impact_inr : 0), 0)
  return (
    <div className="mt-12">
      <PageHeader title="All recommendations" subtitle="Each one comes from a rule that combines model findings with your numbers, with its evidence, why it matters, what to do and the rupee impact where it can be calculated." />
      <div className="grid gap-4 sm:grid-cols-3">
        <Stat label="Open" value={open.length} sub={`${open.filter((r) => r.priority === 'high').length} high priority`} />
        <Stat label="Quantified yearly impact" value={inr(impact)} tone="good" sub="open items with a calculated impact" />
        <Stat label="Accepted / dismissed" value={`${data.filter((r) => r.status === 'accepted').length} / ${data.filter((r) => r.status === 'dismissed').length}`} />
      </div>
      <div className="mt-6"><Segmented label="Show recommendations" options={FILTERS} value={filter} onChange={setFilter} /></div>
      <div className="mt-4 space-y-3">
        {shown.length === 0 && <Card><Empty title={`No ${filter === 'all' ? '' : filter + ' '}recommendations`} /></Card>}
        {shown.map((r) => (
          <article key={r.id} className={cx('rounded-xl border bg-bg p-5 sm:p-6', r.status !== 'open' ? 'border-line' : r.priority === 'high' ? 'border-bad/25' : 'border-line')}>
            <div className="flex flex-wrap items-start gap-4">
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2"><h3 className="text-[15px] font-semibold text-ink">{r.finding}</h3><Badge tone={r.priority}>{r.priority} priority</Badge>
                  {r.status !== 'open' && <Badge tone={r.status === 'accepted' ? 'good' : 'neutral'}>{r.status}</Badge>}</div>
                <dl className="mt-3 grid gap-x-6 gap-y-2 text-sm sm:grid-cols-[120px_1fr]">
                  <dt className="text-faint">Evidence</dt><dd className="num text-ink-2">{r.evidence}</dd>
                  <dt className="text-faint">Why it matters</dt><dd className="text-muted">{present(r.explanation)}</dd>
                  <dt className="text-faint">What to do</dt><dd className="font-medium text-ink">{r.action}</dd>
                  {r.impact_text && <><dt className="text-faint">Impact</dt><dd className="num text-good">{r.impact_text}</dd></>}
                </dl>
                <div className="mt-3 flex flex-wrap items-center gap-4 text-micro text-faint"><span>Source: {present(r.source)}</span><AskAbout q={`Explain this recommendation: ${r.finding}`} /></div>
              </div>
              {!readOnly && <div className="flex gap-2">
                {r.status === 'open' ? (<>
                  <Button size="sm" variant="secondary" icon={Check} onClick={() => set(r, 'accepted')}>Accept</Button>
                  <Button size="sm" variant="quiet" icon={X} onClick={() => set(r, 'dismissed')}>Dismiss</Button>
                </>) : <Button size="sm" variant="secondary" icon={RotateCcw} onClick={() => set(r, 'open')}>Reopen</Button>}
              </div>}
            </div>
          </article>
        ))}
      </div>
    </div>
  )
}
