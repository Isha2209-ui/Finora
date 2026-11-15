// Plan → Goals: are you on track? Progress per goal from the analysis (goals_progress), then the editor (Records) to add or change goals.
import { Answer, Meter, PageHeader, Section } from '../components/ui.jsx'
import { dateLabel, inr, pct } from '../format'
import { useFinora } from '../store.jsx'
import Records from './Records.jsx'

export default function Goals() {
  const { analysis: a } = useFinora()
  const goals = a.goals || []
  const need = goals.filter((g) => !g.overdue).reduce((s, g) => s + (g.monthly_needed_at_7pct || 0), 0)      // display sum of the per-goal figures (overdue goals have no monthly figure)
  const surplus = a.cash_flow?.avg_monthly_savings
  return (
    <>
      <PageHeader title="Goals" />
      {goals.length > 0 ? (
        <Answer eyebrow="What you are saving towards"
          sub={surplus != null ? `Together they need about ${inr(need)} a month if savings grow at an assumed 7% a year; you keep about ${inr(surplus)} a month today.` : 'Add income and spending to compare with what you keep each month.'}>
          You have <b>{goals.length}</b> goal{goals.length === 1 ? '' : 's'}, <b>{pct(goals.reduce((s, g) => s + Math.min(g.current, g.target), 0) / Math.max(1, goals.reduce((s, g) => s + g.target, 0)) * 100, 0)}</b> funded overall.
        </Answer>
      ) : <Answer eyebrow="What you are saving towards" sub="Goals feed your plan, retirement and savings projections.">No goals yet. Add one below.</Answer>}
      {goals.length > 0 && (
        <ul className="divide-y divide-line overflow-hidden rounded-xl border border-line bg-bg">
          {goals.map((g) => (
            <li key={g.name} className="grid gap-3 px-5 py-4 sm:grid-cols-[minmax(0,1fr)_280px] sm:items-center sm:px-6">
              <div className="min-w-0">
                <div className="text-[15px] font-medium text-ink">{g.name}</div>
                <div className="num mt-0.5 text-[13px] text-muted">{inr(g.current)} of {inr(g.target)} · by {dateLabel(g.target_date)}{g.reached ? '' : g.overdue ? ' · target date passed' : ` · ${g.months_left} month${g.months_left === 1 ? '' : 's'} left`}</div>
                <div className="num mt-0.5 text-[13px] text-ink-2">{g.reached ? 'Goal reached. Nothing more to set aside.'
                  : g.overdue ? `${inr(Math.max(0, g.target - g.current))} still needed. Move the target date to see a monthly amount.`
                  : `Set aside ${inr(g.monthly_needed_at_7pct)}/month with 7% assumed growth, or ${inr(g.monthly_needed)}/month with none`}</div>
              </div>
              <Meter value={g.progress_pct} tone={g.progress_pct >= 75 ? 'good' : 'accent'} label={<><span>Funded</span><span className="num font-medium text-ink">{pct(g.progress_pct, 0)}</span></>} />
            </li>
          ))}
        </ul>
      )}
      {goals.length > 0 && (
        <details className="mt-4 rounded-xl border border-line bg-bg px-5 py-4">
          <summary className="cursor-pointer text-sm font-medium text-ink">How the monthly amounts are worked out</summary>
          <p className="mt-2 text-sm leading-6 text-muted">The gap between the target and what you have now is spread over the months left. The first figure assumes your savings earn 7% a year along the way; the second assumes they earn nothing. The growth rate is an assumption for planning, not an expected or promised return.</p>
        </details>
      )}
      <Section title="Add or change goals" className="mt-10">
        <Records only="goals" title="Goals" subtitle="Each change re-runs the analysis." />
      </Section>
    </>
  )
}
