import { useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Link } from 'react-router-dom'
import { ArrowLeft, ArrowRight, Check, ChevronDown, Info, Pencil, ShieldCheck, Sparkles, Trash2, X } from 'lucide-react'
import { api } from '../api'
import { AskAbout, ErrorBox, Loading, cx } from '../components/ui.jsx'
import { present } from '../components/models.js'
import { inr, num } from '../format'
import { useFinora } from '../store.jsx'

// ------------------------------------------------------------------ metric vocabulary (one place, used everywhere)
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const ym = (d) => (d ? `${MONTHS[Number(d.slice(5, 7)) - 1]} ${d.slice(0, 4)}` : null)
const METRICS = [
  { key: 'surplus', label: 'Monthly surplus', fmt: (m) => (m.surplus == null ? '—' : `${inr(m.surplus)}`), delta: 'surplus',
    better: 'up', explain: 'Income minus spending each month, after anything the plan sets aside. Money the plan moves into debt, savings or investments lowers it on purpose.' },
  { key: 'debt_free', label: 'Debt-free', fmt: (m) => (!m.has_debt ? 'No debt' : m.debt_free_date ? ym(m.debt_free_date) : 'Not within 50 years'),
    delta: 'debt_free_months', better: 'down', unit: 'months',
    explain: 'When every recorded loan and card balance reaches zero, paying the highest interest rate first.' },
  { key: 'runway', label: 'Runway in 12 months', fmt: (m) => (m.runway_months == null ? '—' : `${num(m.runway_months, 1)} months`),
    delta: 'runway_months', better: 'up', unit: 'months', explain: 'How many months your emergency savings would cover your spending a year from now, after any goals due before then.' },
  { key: 'health', label: 'Health score', fmt: (m) => (m.health_score == null ? '—' : num(m.health_score, 1)), delta: 'health_score',
    better: 'up', unit: 'points', explain: 'Finora’s 0–100 score: savings, emergency fund, debt, credit use, protection and investing.' },
  { key: 'fire', label: 'Financial independence', fmt: (m) => (m.fire_age == null ? 'Not before 75' : `Age ${num(m.fire_age, 1)}`),
    delta: 'fire_age', better: 'down', unit: 'years', explain: 'The age at which your investments could cover your spending (in today’s rupees).' },
]

function deltaText(metric, d) {
  if (d == null || Math.abs(d) < 0.005) return null
  if (metric.key === 'surplus') return `${d > 0 ? '+' : '−'}${inr(Math.abs(d))} a month`
  if (metric.key === 'debt_free') return `${Math.abs(d)} months ${d < 0 ? 'sooner' : 'later'}`
  if (metric.key === 'fire') return `${num(Math.abs(d), 1)} years ${d < 0 ? 'earlier' : 'later'}`
  return `${d > 0 ? '+' : '−'}${num(Math.abs(d), 1)} ${metric.unit}`
}
function deltaTone(metric, d) {
  if (d == null || Math.abs(d) < 0.005) return 'text-faint'
  if (metric.key === 'surplus') return d > 0 ? 'text-good' : 'text-info'          // money set aside on purpose is not "bad"
  const good = metric.better === 'up' ? d > 0 : d < 0
  return good ? 'text-good' : 'text-warn'
}

// ------------------------------------------------------------------ page
export default function Plan() {
  const { profileId, refresh } = useFinora()
  const [plan, setPlan] = useState(null)
  const [err, setErr] = useState(null)
  const [step, setStep] = useState(0)
  const [detail, setDetail] = useState(null)
  const load = async () => { try { setPlan(await api.plan(profileId)); setErr(null) } catch (e) { setErr(e.message) } }
  useEffect(() => { setPlan(null); load() }, [profileId]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (plan && step === 0 && plan.assumptions.length) setStep(2) }, [plan?.assumptions.length]) // eslint-disable-line react-hooks/exhaustive-deps

  if (err) return <ErrorBox message={err} onRetry={load} />
  if (!plan) return <Loading full label="Putting your plan together…" />
  const apply = (p) => { setPlan(p); refresh?.({ rerun: false }) }
  const first = (plan.profile?.name || '').split(' ')[0]
  const open = plan.actions.filter((a) => a.status === 'open').length

  return (
    <div className="mx-auto max-w-5xl pb-16">
      <header className="pt-2 pb-8">
        <div className="text-xs font-medium uppercase tracking-[0.16em] text-accent">Finora Plan</div>
        <h1 className="mt-2 text-[28px] font-semibold leading-tight tracking-tight">{first ? `${first}, here is where you stand.` : 'Here is where you stand.'}</h1>
        <p className="mt-2 max-w-2xl text-[15px] leading-relaxed text-muted">
          {plan.available
            ? <>Finora read {num(plan.picture.months_of_data)} months of your money, found {plan.diagnosis.length} things worth knowing and {plan.actions.length} {plan.actions.length === 1 ? 'step' : 'steps'} that would move your numbers. {open ? 'Take them one at a time.' : ''}</>
            : <>Finora can describe what it knows so far. To suggest steps it needs your income and some spending history.</>}
        </p>
      </header>

      <Picture p={plan.picture} />

      <Stepper step={step} setStep={setStep} counts={[plan.diagnosis.length, plan.actions.length, plan.assumptions.length]} />

      <div className="mt-6">
        {step === 0 && <Findings items={plan.diagnosis} onNext={() => setStep(1)} />}
        {step === 1 && (plan.available
          ? <Actions plan={plan} profileId={profileId} onPlan={apply} onDetail={setDetail} onDone={() => setStep(2)} />
          : <NeedsData />)}
        {step === 2 && <YourPlan plan={plan} profileId={profileId} onPlan={apply} onBack={() => setStep(1)} />}
      </div>

      <p className="mt-10 flex items-start gap-2 text-xs leading-relaxed text-faint"><ShieldCheck size={14} className="mt-0.5 shrink-0" />
        {plan.method.history} {plan.picture.data_notice}</p>
      {detail && <Detail code={detail} profileId={profileId} onClose={() => setDetail(null)} />}
    </div>
  )
}

// ------------------------------------------------------------------ Phase 8: one plan step per Plan tab (Priorities / Actions / Your plan)
export function usePlan() {
  const { profileId } = useFinora()
  const [plan, setPlan] = useState(null)
  const [err, setErr] = useState(null)
  const load = async () => { try { setPlan(await api.plan(profileId)); setErr(null) } catch (e) { setErr(e.message) } }
  useEffect(() => { setPlan(null); load() }, [profileId]) // eslint-disable-line react-hooks/exhaustive-deps
  return { plan, setPlan, err, load }
}

export function PlanSection({ section, goTo, extra }) {
  const { profileId, refresh } = useFinora()
  const { plan, setPlan, err, load } = usePlan()
  const [detail, setDetail] = useState(null)
  if (err) return <ErrorBox message={err} onRetry={load} />
  if (!plan) return <Loading label="Putting your plan together…" />
  const apply = (p) => { setPlan(p); refresh?.({ rerun: false }) }
  return (
    <div className="pb-6">
      {section === 'priorities' && <Findings items={plan.diagnosis} onNext={() => goTo('actions')} />}
      {section === 'actions' && (plan.available
        ? <Actions plan={plan} profileId={profileId} onPlan={apply} onDetail={setDetail} onDone={() => goTo('plan')} />
        : <NeedsData />)}
      {section === 'actions' && extra}
      {section === 'plan' && <YourPlan plan={plan} profileId={profileId} onPlan={apply} onBack={() => goTo('actions')} />}
      <p className="mt-10 flex items-start gap-2 text-micro leading-4 text-faint"><ShieldCheck size={14} className="mt-0.5 shrink-0" aria-hidden />
        {plan.method.history} {plan.picture.data_notice}</p>
      {detail && <Detail code={detail} profileId={profileId} onClose={() => setDetail(null)} />}
    </div>
  )
}

// ------------------------------------------------------------------ the picture
function Tip({ text }) {
  const [on, setOn] = useState(false)
  return (
    <span className="relative inline-flex" onMouseEnter={() => setOn(true)} onMouseLeave={() => setOn(false)}>
      <button type="button" aria-label="What is this?" onClick={() => setOn(!on)} className="text-faint hover:text-muted"><Info size={13} /></button>
      {on && <span className="absolute left-1/2 top-5 z-20 w-64 -translate-x-1/2 rounded-xl border border-line bg-surface p-3 text-xs font-normal leading-relaxed text-muted shadow-xl">{text}</span>}
    </span>
  )
}

function Picture({ p }) {
  const [more, setMore] = useState(false)
  const hero = [
    ['Monthly surplus', p.surplus == null ? '—' : inr(p.surplus), p.savings_rate_pct == null ? 'needs income and spending' : `${num(p.savings_rate_pct, 0)}% of income kept`, METRICS[0].explain],
    ['Net worth', inr(p.net_worth), 'everything you own minus what you owe', 'Assets at stored values minus all loans and card balances.'],
    ['Runway', p.runway_months == null ? '—' : `${num(p.runway_months, 1)} mo`, 'if income stopped today', 'Bank, cash, FDs and debt funds divided by your average monthly spending. Shares are left out because they can fall when you need them.'],
    ['Health score', p.health_score == null ? '—' : num(p.health_score, 0), p.health_band || '', METRICS[3].explain],
  ]
  const rest = [
    ['Income', p.income == null ? 'Not known yet' : `${inr(p.income)} a month`], ['Spending', p.expenses == null ? 'Not known yet' : `${inr(p.expenses)} a month`],
    ['In the bank', inr(p.balances)], ['Debt', p.debt ? `${inr(p.debt)} · EMIs ${inr(p.emi)}/mo${p.emi_to_income_pct != null ? ` (${num(p.emi_to_income_pct, 0)}% of income)` : ''}` : 'None recorded'],
    ['Investments', `${inr(p.investments)}${p.sip_monthly ? ` · SIPs ${inr(p.sip_monthly)}/mo` : ''}`],
    ['Financial independence', p.fire_available ? `${p.fire_age ? `Age ${num(p.fire_age, 1)}` : 'Not before 75'} · ${num(p.fire_progress_pct, 0)}% of the way` : 'Needs spending history'],
    ['Data completeness', `${p.completeness_pct ?? 0}%`],
  ]
  return (
    <section>
      <div className="grid gap-px overflow-hidden rounded-3xl border border-line bg-line sm:grid-cols-2 lg:grid-cols-4">
        {hero.map(([l, v, s, tip]) => (
          <div key={l} className="bg-surface px-6 py-5">
            <div className="flex items-center gap-1.5 text-xs text-muted">{l} <Tip text={tip} /></div>
            <div className="num mt-2 text-[26px] font-semibold tracking-tight">{v}</div>
            <div className="mt-1 text-xs text-faint">{s}</div>
          </div>
        ))}
      </div>
      <button onClick={() => setMore(!more)} className="mt-3 flex items-center gap-1 text-xs text-muted hover:text-ink">
        <ChevronDown size={14} className={cx('transition', more && 'rotate-180')} /> {more ? 'Hide the full picture' : 'Show the full picture'}
      </button>
      {more && (
        <dl className="mt-3 grid gap-x-10 gap-y-3 rounded-xl border border-line bg-bg/60 px-6 py-5 text-sm sm:grid-cols-2">
          {rest.map(([k, v]) => <div key={k} className="flex justify-between gap-4 border-b border-line/50 pb-2"><dt className="text-muted">{k}</dt><dd className="num text-right">{v}</dd></div>)}
        </dl>
      )}
    </section>
  )
}

// ------------------------------------------------------------------ guided steps
function Stepper({ step, setStep, counts }) {
  const steps = ['What we found', 'What to do', 'Your plan']
  return (
    <nav className="mt-10 flex items-center gap-2" aria-label="Plan steps">
      {steps.map((s, i) => (
        <button key={s} onClick={() => setStep(i)} aria-current={step === i ? 'step' : undefined}
          className={cx('group flex items-center gap-2.5 rounded-full px-4 py-2 text-sm transition', step === i ? 'bg-ink text-bg' : 'text-muted hover:bg-raised hover:text-ink')}>
          <span className={cx('grid h-5 w-5 place-items-center rounded-full text-[11px] font-semibold', step === i ? 'bg-bg text-ink' : 'bg-raised text-muted group-hover:text-ink')}>{i + 1}</span>
          {s}{counts[i] ? <span className={cx('num text-xs', step === i ? 'text-bg/60' : 'text-faint')}>{counts[i]}</span> : null}
        </button>
      ))}
    </nav>
  )
}

const SEV = { high: 'bg-bad', medium: 'bg-warn', low: 'bg-info', info: 'bg-faint', good: 'bg-good' }

function Findings({ items, onNext }) {
  const [open, setOpen] = useState(0)
  return (
    <section>
      <p className="mb-4 text-sm text-muted">Each finding comes from your own numbers. Open one to see the evidence and where it comes from.</p>
      <ol className="divide-y divide-line overflow-hidden rounded-xl border border-line bg-bg">
        {items.map((d, i) => (
          <li key={d.code}>
            <button onClick={() => setOpen(open === i ? -1 : i)} className="flex w-full items-center gap-4 px-6 py-4 text-left hover:bg-subtle/70">
              <span className={cx('h-2 w-2 shrink-0 rounded-full', SEV[d.severity] || 'bg-faint')} />
              <span className="flex-1 text-[15px]">{d.finding}</span>
              <ChevronDown size={16} className={cx('text-faint transition', open === i && 'rotate-180')} />
            </button>
            {open === i && (
              <div className="grid gap-4 px-6 pb-5 pl-12 text-sm sm:grid-cols-2">
                <Fact label="Evidence">{d.evidence}</Fact>
                <Fact label="Why it matters">{present(d.why)}</Fact>
                <Fact label="Source">{present(d.source)}</Fact>
                <Fact label="How sure">{present(d.confidence)}</Fact>
                <div className="flex flex-wrap gap-4 sm:col-span-2">
                  <Link to={d.detail_link} className="text-[13px] font-medium text-accent hover:underline">See the details →</Link>
                  <AskAbout q={`Explain this finding: ${d.finding}`} />
                </div>
              </div>
            )}
          </li>
        ))}
      </ol>
      <div className="mt-6 flex justify-end"><Primary onClick={onNext}>See what to do <ArrowRight size={15} /></Primary></div>
    </section>
  )
}

const Fact = ({ label, children }) => <div><div className="text-[11px] uppercase tracking-wider text-faint">{label}</div><div className="mt-1 leading-relaxed text-ink/90">{children}</div></div>
const Primary = ({ children, className = '', ...p }) => <button type="button" {...p} className={cx('inline-flex h-10 items-center gap-2 rounded-md bg-accent px-4 text-sm font-medium text-white shadow-xs transition-colors hover:bg-accent-hover disabled:opacity-50', className)}>{children}</button>
const Quiet = ({ children, className = '', ...p }) => <button type="button" {...p} className={cx('inline-flex h-10 items-center gap-2 rounded-md border border-control/60 bg-bg px-4 text-sm font-medium text-ink shadow-xs transition-colors hover:bg-subtle disabled:opacity-50', className)}>{children}</button>

function NeedsData() {
  return (
    <section className="rounded-xl border border-line bg-bg px-6 py-8 text-center">
      <Sparkles className="mx-auto text-accent" size={22} />
      <h2 className="mt-3 text-lg font-semibold">Your plan needs a little more to work with</h2>
      <p className="mx-auto mt-2 max-w-md text-sm text-muted">Add your income and some spending (or import a bank statement). Finora never guesses these numbers, so it waits until it knows them.</p>
      <div className="mt-5 flex justify-center gap-2"><Link to="/data?tab=import"><Primary>Import a statement</Primary></Link><Link to="/data?tab=records"><Quiet>Add it by hand</Quiet></Link></div>
    </section>
  )
}

// ------------------------------------------------------------------ actions: one at a time
const FIELD = {
  extra_debt_repayment: [['amount', 'Extra each month (₹)', 500]], spending_cap: [['amount', 'Spend this much less each month (₹)', 100]],
  emergency_fund_contribution: [['amount', 'Set aside each month (₹)', 500]], sip: [['amount', 'Invest each month (₹)', 500]],
  delayed_purchase: [['months_delay', 'Delay by (months)', 1]],
}

function Actions({ plan, profileId, onPlan, onDetail, onDone }) {
  const [i, setI] = useState(0)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const acts = plan.actions
  if (!acts.length) return <section className="rounded-xl border border-line bg-bg px-6 py-8 text-center text-sm text-muted">No step would improve your numbers right now. Finora will suggest some when your data changes.</section>
  const a = acts[Math.min(i, acts.length - 1)]
  const readOnly = plan.read_only
  const run = async (fn, advance = true) => {
    setBusy(true); setErr(null)
    try { const r = await fn(); onPlan(r.plan); if (advance) setI((x) => (x + 1 < acts.length ? x + 1 : x)) } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }
  const accept = (params) => run(() => api.planAccept(profileId, { kind: a.kind, params, source_code: a.code, title: a.title }))
  return (
    <section>
      <div className="mb-4 flex items-center justify-between text-sm text-muted">
        <span>Step {i + 1} of {acts.length} · ranked by how much it moves your numbers</span>
        <div className="flex items-center gap-1.5">{acts.map((x, k) => (
          <button key={x.code} aria-label={`Action ${k + 1}`} onClick={() => setI(k)}
            className={cx('h-2 rounded-full transition-all', k === i ? 'w-6 bg-ink' : x.status === 'accepted' ? 'w-2 bg-good' : x.status === 'dismissed' ? 'w-2 bg-line' : 'w-2 bg-faint')} />))}</div>
      </div>
      <ActionCard key={a.code} a={a} profileId={profileId} readOnly={readOnly} busy={busy} err={err}
        onAccept={accept} onDismiss={() => run(() => api.planDismiss(profileId, a.code))}
        onRestore={() => run(() => api.planRestore(profileId, a.code), false)} onDetail={() => onDetail(a.code)} />
      <div className="mt-6 flex items-center justify-between">
        <Quiet onClick={() => setI(Math.max(0, i - 1))} disabled={i === 0}><ArrowLeft size={15} /> Previous</Quiet>
        {i + 1 < acts.length ? <Quiet onClick={() => setI(i + 1)}>Next step <ArrowRight size={15} /></Quiet> : <Primary onClick={onDone}>Review your plan <ArrowRight size={15} /></Primary>}
      </div>
    </section>
  )
}

function ActionCard({ a, profileId, readOnly, busy, err, onAccept, onDismiss, onRestore, onDetail }) {
  const [editing, setEditing] = useState(false)
  const [params, setParams] = useState(a.params)
  const [live, setLive] = useState(null)
  const timer = useRef(null)
  useEffect(() => {
    if (!editing) return
    clearTimeout(timer.current)
    timer.current = setTimeout(async () => {
      try { setLive(await api.planPreview(profileId, [{ kind: a.kind, params, source_code: a.code }], false)) } catch (e) { setLive({ error: e.message }) }
    }, 350)
    return () => clearTimeout(timer.current)
  }, [params, editing]) // eslint-disable-line react-hooks/exhaustive-deps
  const shown = editing && live && !live.error ? { scenario: live.scenario, effect: live.effect, impact: live.impact } : a
  return (
    <article className={cx('rounded-3xl border bg-surface p-7 transition', a.status === 'accepted' ? 'border-good/40' : 'border-line', a.status === 'dismissed' && 'opacity-60')}>
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="rounded-full bg-raised px-2.5 py-1 text-muted">#{a.rank} · {a.kind_label}</span>
        {a.status === 'accepted' && <span className="flex items-center gap-1 rounded-full bg-good/15 px-2.5 py-1 text-good"><Check size={12} /> In your plan</span>}
        {a.status === 'dismissed' && <span className="rounded-full bg-raised px-2.5 py-1 text-faint">Dismissed</span>}
      </div>
      <h2 className="mt-4 text-[22px] font-semibold leading-snug tracking-tight">{a.title}</h2>
      <p className="mt-2 text-[15px] leading-relaxed text-muted">{a.step}</p>
      <p className="mt-3 text-sm leading-relaxed text-faint"><span className="text-muted">Why: </span>{a.evidence}</p>

      <div className="mt-6 flex flex-wrap items-baseline gap-x-3 gap-y-1">
        {shown.impact?.inr != null && <span className="num text-[34px] font-semibold tracking-tight text-good">{inr(shown.impact.inr)}</span>}
        <span className="text-sm text-muted">{shown.impact?.label}</span>
      </div>

      {editing && (
        <div className="mt-5 rounded-2xl border border-line bg-bg/60 p-4">
          {FIELD[a.kind].map(([f, label, step]) => (
            <label key={f} className="block text-xs text-muted">{label}
              <input type="number" min={step} step={step} value={params[f] ?? ''} onChange={(e) => setParams({ ...params, [f]: Number(e.target.value) })}
                className="num mt-1.5 h-10 w-full rounded-md border border-control/70 bg-bg px-3 text-base text-ink shadow-xs focus:border-accent focus:ring-2 focus:ring-accent/20 focus-visible:outline-none" />
            </label>
          ))}
          {live?.error && <p className="mt-2 text-xs text-warn">{live.error}</p>}
          {live?.over_committed && <p className="mt-2 text-xs text-warn">This sets aside more than you have left each month.</p>}
          <p className="mt-2 text-[11px] text-faint">The numbers below update as you type. Nothing is saved until you add it to your plan.</p>
        </div>
      )}

      <Effects baseline={a.baseline} scenario={shown.scenario} effect={shown.effect} />

      {err && <p className="mt-4 text-sm text-bad">{err}</p>}
      <div className="mt-6 flex flex-wrap items-center gap-2">
        {readOnly ? <p className="text-xs text-faint">This is a read-only demo template. Open your own copy of the demo to build a plan.</p> : a.status === 'dismissed'
          ? <Quiet onClick={onRestore} disabled={busy}>Bring it back</Quiet>
          : <>
            <Primary onClick={() => onAccept(editing ? params : a.params)} disabled={busy || (editing && live?.error)}><Check size={15} /> {a.status === 'accepted' ? 'Update in plan' : 'Add to my plan'}</Primary>
            <Quiet onClick={() => { setEditing(!editing); setParams(a.params); setLive(null) }} disabled={busy}><Pencil size={14} /> {editing ? 'Cancel edit' : 'Edit'}</Quiet>
            {a.status !== 'accepted' && <Quiet onClick={onDismiss} disabled={busy}><X size={14} /> Not for me</Quiet>}
          </>}
        <button onClick={onDetail} className="ml-auto text-sm text-accent hover:underline">How this is calculated</button>
      </div>
    </article>
  )
}

function Effects({ baseline, scenario, effect }) {
  return (
    <div className="mt-6 grid gap-px overflow-hidden rounded-2xl border border-line bg-line sm:grid-cols-5">
      {METRICS.map((m) => {
        const d = effect?.[m.delta]
        return (
          <div key={m.key} className="bg-bg/40 px-4 py-3">
            <div className="flex items-center gap-1 text-[11px] text-faint">{m.label} <Tip text={m.explain} /></div>
            <div className="num mt-1.5 text-sm font-medium">{m.fmt(scenario || baseline)}</div>
            <div className={cx('num mt-0.5 text-[11px]', deltaTone(m, d))}>{deltaText(m, d) || 'no change'}</div>
          </div>
        )
      })}
    </div>
  )
}

// ------------------------------------------------------------------ the plan itself
function YourPlan({ plan, profileId, onPlan, onBack }) {
  const [busy, setBusy] = useState(null)
  const [err, setErr] = useState(null)
  const remove = async (x) => { setBusy(x.id); setErr(null); try { onPlan((await api.planRemove(profileId, x.id)).plan) } catch (e) { setErr(e.message) } finally { setBusy(null) } }
  const describe = (x) => x.kind === 'delayed_purchase' ? `${x.params.months_delay} months later` : `${inr(x.params.amount)} a month`
  if (!plan.assumptions.length) {
    return (
      <section className="rounded-3xl border border-dashed border-line px-6 py-12 text-center">
        <h2 className="text-lg font-semibold">Your plan is empty</h2>
        <p className="mx-auto mt-2 max-w-md text-sm text-muted">Add a step from “What to do” and Finora will show how your numbers change, compared with carrying on as you are.</p>
        <Primary className="mt-5" onClick={onBack}>Choose a step <ArrowRight size={15} /></Primary>
      </section>
    )
  }
  return (
    <section className="space-y-6">
      <div className="rounded-3xl border border-line bg-surface p-7">
        <h2 className="text-lg font-semibold">If you follow your plan</h2>
        <p className="mt-1 text-sm text-muted">Compared with carrying on as you are. Calculated from your history plus the steps below; your records are not changed.</p>
        <div className="mt-5 divide-y divide-line">
          {METRICS.map((m) => {
            const d = plan.plan_effect?.[m.delta]
            return (
              <div key={m.key} className="grid grid-cols-[1.4fr_1fr_1fr_1.2fr] items-center gap-3 py-3 text-sm">
                <span className="flex items-center gap-1.5 text-muted">{m.label} <Tip text={m.explain} /></span>
                <span className="num text-faint">{m.fmt(plan.baseline)}</span>
                <span className="num font-medium">{m.fmt(plan.with_plan)}</span>
                <span className={cx('num text-right text-xs', deltaTone(m, d))}>{deltaText(m, d) || 'no change'}</span>
              </div>
            )
          })}
        </div>
        <div className="mt-1 grid grid-cols-[1.4fr_1fr_1fr_1.2fr] gap-3 text-[11px] text-faint"><span /><span>As you are</span><span>With the plan</span><span /></div>
        {plan.over_committed && <p className="mt-4 rounded-xl bg-warn/10 px-3 py-2 text-xs text-warn">Your plan sets aside more each month than you have left. Lower an amount or remove a step.</p>}
      </div>

      <div>
        <h3 className="mb-3 text-sm font-medium text-muted">Steps in your plan</h3>
        <ul className="divide-y divide-line overflow-hidden rounded-xl border border-line bg-bg">
          {plan.assumptions.map((x) => (
            <li key={x.id} className="flex items-center gap-4 px-6 py-4">
              <Check size={16} className="shrink-0 text-good" />
              <div className="flex-1"><div className="text-[15px]">{x.title}</div><div className="num mt-0.5 text-xs text-faint">{x.kind_label} · {describe(x)}</div></div>
              {!plan.read_only && <button onClick={() => remove(x)} disabled={busy === x.id} className="flex items-center gap-1 text-xs text-faint hover:text-bad"><Trash2 size={13} /> Remove</button>}
            </li>
          ))}
        </ul>
        {err && <p className="mt-2 text-sm text-bad">{err}</p>}
        <p className="mt-3 text-xs text-faint">These are assumptions, not payments. Finora never records a payment you have not made.</p>
      </div>
    </section>
  )
}

// ------------------------------------------------------------------ advanced detail (on demand)
function Detail({ code, profileId, onClose }) {
  const [d, setD] = useState(null)
  const [err, setErr] = useState(null)
  useEffect(() => { api.planAction(profileId, code).then(setD).catch((e) => setErr(e.message)) }, [code, profileId])
  const rows = useMemo(() => !d ? [] : [
    ['Monthly surplus', inr(d.baseline.surplus), inr(d.scenario.surplus)],
    ['Debt-free (months)', d.baseline.has_debt ? (d.baseline.debt_free_months ?? 'Never at these payments') : '—', d.scenario.has_debt ? (d.scenario.debt_free_months ?? 'Never at these payments') : '—'],
    ['Interest still to pay', inr(d.baseline.debt_interest), inr(d.scenario.debt_interest)],
    ['Emergency pool in 12 months', inr(d.baseline.pool_in_12m), inr(d.scenario.pool_in_12m)],
    ['Runway in 12 months', num(d.baseline.runway_months, 2), num(d.scenario.runway_months, 2)],
    ['Health score in 12 months', num(d.baseline.health_score, 1), num(d.scenario.health_score, 1)],
    ['FIRE age', d.baseline.fire_age ?? 'not before 75', d.scenario.fire_age ?? 'not before 75'],
    ['Invested by target retirement age', inr(d.baseline.corpus_at_target_age), inr(d.scenario.corpus_at_target_age)],
  ], [d])
  // Portal to <body>: the page container keeps a transform from its entrance animation, which would trap a fixed panel.
  return createPortal(
    <div className="fixed inset-0 z-40 flex justify-end bg-black/40" onClick={onClose}>
      <aside className="h-full w-full max-w-lg overflow-y-auto border-l border-line bg-surface p-7" onClick={(e) => e.stopPropagation()} role="dialog" aria-label="How this is calculated">
        <div className="flex items-start justify-between gap-4">
          <div><div className="text-xs uppercase tracking-[0.14em] text-faint">How this is calculated</div><h2 className="mt-1 text-lg font-semibold">{d?.action.title || '…'}</h2></div>
          <button onClick={onClose} aria-label="Close" className="text-faint hover:text-ink"><X size={18} /></button>
        </div>
        {err && <p className="mt-4 text-sm text-bad">{err}</p>}
        {d && (
          <>
            <p className="mt-3 text-sm leading-relaxed text-muted">{d.action.step}</p>
            <table className="mt-6 w-full text-sm">
              <thead><tr className="text-left text-[11px] uppercase tracking-wider text-faint"><th className="pb-2 font-medium" /><th className="pb-2 font-medium">As you are</th><th className="pb-2 font-medium">With this step</th></tr></thead>
              <tbody className="divide-y divide-line/60">{rows.map(([k, b, s]) => <tr key={k}><td className="py-2 pr-3 text-muted">{k}</td><td className="num py-2 text-faint">{b}</td><td className="num py-2">{s}</td></tr>)}</tbody>
            </table>
            {d.scenario.goals_paid_within_12m?.length > 0 && <p className="mt-4 text-xs text-muted">Goals paid from savings within 12 months in this scenario: {d.scenario.goals_paid_within_12m.map((g) => `${g.name} (${inr(g.amount)}, month ${g.in_months})`).join(', ')}.</p>}
            <h3 className="mt-7 text-sm font-medium">Method</h3>
            <dl className="mt-2 space-y-2 text-xs leading-relaxed text-muted">{Object.entries(d.method).map(([k, v]) => <div key={k}><dt className="inline font-medium capitalize text-ink/80">{k.replace('_', ' ')}: </dt><dd className="inline">{v}</dd></div>)}</dl>
            <p className="mt-6 flex items-start gap-2 rounded-xl bg-raised/60 px-3 py-2 text-xs text-muted"><ShieldCheck size={14} className="mt-0.5 shrink-0 text-accent" /> Every figure is the scenario minus the baseline, computed from your records. Nothing has been paid or changed.</p>
          </>
        )}
      </aside>
    </div>, document.body)
}
