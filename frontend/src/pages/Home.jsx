// Home: a calm starting point, not a dashboard. Greeting, one status sentence, the top three priorities, and where to go next.
// All figures come from GET /profiles/{id}/plan (the same source as Plan). Missing data is explained, never filled in.
import { Link } from 'react-router-dom'
import { ArrowRight, CircleDashed, Compass, FileUp, PencilLine, Sparkles, Wallet } from 'lucide-react'
import { AskAbout, ErrorBox, Skeleton, cx } from '../components/ui.jsx'
import { present } from '../components/models.js'
import { inr, num } from '../format'
import { useFinora } from '../store.jsx'
import { usePlan } from './Plan.jsx'

const SEV = { high: 'bg-bad', medium: 'bg-warn', low: 'bg-info', info: 'bg-faint', good: 'bg-good' }

function status(p) {
  const parts = []
  if (p.surplus != null) parts.push(p.surplus >= 0 ? `You keep ${inr(p.surplus)} a month${p.savings_rate_pct != null ? ` (${num(p.savings_rate_pct, 0)}% of income)` : ''}` : `You spend ${inr(-p.surplus)} a month more than you earn`)
  if (p.runway_months != null) parts.push(`your savings would cover ${num(p.runway_months, 1)} months of spending`)
  if (p.health_score != null) { const b = (p.health_band || '').toLowerCase(); parts.push(b ? (/^needs|^at risk/.test(b) ? `your financial health ${b}` : `your financial health is ${b}`) : `your health score is ${num(p.health_score, 0)}`) }
  if (!parts.length) return null
  const s = parts.join(', ')
  return s.charAt(0).toUpperCase() + s.slice(1) + '.'
}

const TILES = [
  ['/money?tab=spending', Wallet, 'Review spending', 'Where your money goes and what changed.'],
  ['/data?tab=import', FileUp, 'Import a statement', 'Bring in a bank or card CSV.'],
  ['/ask', Sparkles, 'Ask Finora', 'Questions in your own words, answered from your data.'],
  ['/plan?tab=plan', Compass, 'See your plan', 'What your chosen steps would change.'],
]

export default function Home() {
  const { profile } = useFinora()
  const { plan, err, load } = usePlan()
  const name = (plan?.profile?.name || '').split(' ')[0]
  const p = plan?.picture
  const top = plan?.diagnosis?.slice(0, 3) || []
  const readOnly = profile?.kind === 'template'
  return (
    <div>
      <section className="rounded-2xl bg-gradient-to-b from-[#eef2fc] to-canvas px-5 pt-8 pb-8 sm:px-8 sm:pt-10">
        <div className="text-micro font-medium uppercase tracking-[0.06em] text-accent">Home</div>
        <h1 className="mt-2 text-display font-semibold tracking-tight text-ink">{plan ? (name ? `Good to see you, ${name}.` : 'Welcome back.') : <Skeleton className="h-10 w-80" />}</h1>
        {err ? <div className="mt-4 max-w-xl"><ErrorBox message={err} onRetry={load} /></div>
          : !plan ? <Skeleton className="mt-3 h-6 w-[min(560px,90%)]" />
            : <p className="mt-3 max-w-2xl text-[17px] leading-7 text-ink-2">{status(p) || 'Finora does not know enough about your money yet to describe it. Add your income and some spending to begin.'}</p>}
        {p && <p className="mt-2 text-[13px] text-muted">Based on {num(p.months_of_data)} months of data{p.completeness_pct != null ? ` · ${p.completeness_pct}% of your profile filled in` : ''}. <Link to="/money?tab=overview" className="font-medium text-accent hover:underline">Net worth {inr(p.net_worth)}</Link></p>}
      </section>

      <div className="pb-6">
        {plan && !plan.available ? (
          <section className="mt-2 rounded-xl border border-line bg-bg p-6">
            <h2 className="text-heading font-semibold text-ink">Let’s get your numbers in</h2>
            <p className="mt-1 max-w-xl text-sm leading-6 text-muted">Finora needs your income and some spending history before it can suggest anything. It never guesses these numbers.</p>
            <ol className="mt-5 space-y-3">
              {[['/data?tab=import', FileUp, 'Import a bank or card statement', 'The fastest way: income and spending in one step.'],
                ['/data?tab=records&type=income', PencilLine, 'Or add your income by hand', 'Then accounts, cards, loans and investments.']].map(([to, I, t, d]) => (
                <li key={to}><Link to={to} className="flex items-center gap-3 rounded-lg border border-line px-4 py-3 hover:border-accent/40">
                  <I size={18} className="text-accent" aria-hidden /><span className="min-w-0 flex-1"><span className="block text-sm font-medium text-ink">{t}</span><span className="block text-[13px] text-muted">{d}</span></span><ArrowRight size={16} className="text-faint" aria-hidden /></Link></li>))}
            </ol>
            {readOnly && <p className="mt-4 text-[13px] text-warn">This demo template is read-only; explore a demo copy to add data.</p>}
          </section>
        ) : (
          <section aria-labelledby="pri" className="mt-2">
            <div className="flex flex-wrap items-end justify-between gap-3">
              <h2 id="pri" className="text-heading font-semibold text-ink">What needs your attention</h2>
              {plan && <Link to="/plan" className="inline-flex items-center gap-1 text-[13px] font-medium text-accent hover:underline">All {plan.diagnosis.length} findings <ArrowRight size={14} aria-hidden /></Link>}
            </div>
            <ol className="mt-4 divide-y divide-line overflow-hidden rounded-xl border border-line bg-bg">
              {!plan && [0, 1, 2].map((i) => <li key={i} className="px-5 py-4"><Skeleton className="h-5 w-2/3" /><Skeleton className="mt-2 h-4 w-1/2" /></li>)}
              {plan && top.length === 0 && <li className="flex items-center gap-3 px-5 py-5 text-sm text-muted"><CircleDashed size={18} aria-hidden /> Nothing needs attention right now.</li>}
              {top.map((d) => (
                <li key={d.code} className="flex flex-wrap items-start gap-x-4 gap-y-2 px-5 py-4">
                  <span className={cx('mt-2 h-2 w-2 shrink-0 rounded-full', SEV[d.severity] || 'bg-faint')} aria-hidden />
                  <div className="min-w-0 flex-1 basis-64">
                    <div className="text-[15px] font-medium text-ink">{d.finding}</div>
                    <div className="mt-0.5 text-[13px] leading-5 text-muted">{present(d.why)}</div>
                  </div>
                  <div className="flex items-center gap-4 pl-6 sm:pl-0">
                    <AskAbout q={`Explain this finding: ${d.finding}`} />
                    <Link to="/plan?tab=priorities" className="inline-flex items-center gap-1 text-[13px] font-medium text-ink-2 hover:text-accent">Evidence <ArrowRight size={14} aria-hidden /></Link>
                  </div>
                </li>
              ))}
            </ol>
            {plan?.actions?.length > 0 && <p className="mt-3 text-[13px] text-muted">{plan.actions.length} {plan.actions.length === 1 ? 'step' : 'steps'} would move your numbers. <Link to="/plan?tab=actions" className="font-medium text-accent hover:underline">See what to do</Link></p>}
          </section>
        )}

        <section aria-labelledby="next" className="mt-12">
          <h2 id="next" className="text-heading font-semibold text-ink">Where to next</h2>
          <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {TILES.filter(([to]) => !(readOnly && to.startsWith('/data'))).map(([to, I, t, d]) => (
              <Link key={to} to={to} className="group rounded-xl border border-line bg-bg p-4 transition-colors hover:border-accent/40">
                <I size={20} className="text-accent" aria-hidden />
                <div className="mt-3 flex items-center gap-1 text-[15px] font-semibold text-ink">{t}<ArrowRight size={14} className="opacity-0 transition-opacity group-hover:opacity-100" aria-hidden /></div>
                <div className="mt-0.5 text-[13px] leading-5 text-muted">{d}</div>
              </Link>
            ))}
          </div>
        </section>
        <p className="mt-10 text-micro text-faint">{plan?.picture?.data_notice}</p>
      </div>
    </div>
  )
}
