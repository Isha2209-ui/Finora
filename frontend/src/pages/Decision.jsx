import { useState } from 'react'
import { ArrowRight, Bike, Car, CheckCircle2, GraduationCap, Heart, Home, Laptop, Package, Plane, Smartphone, TriangleAlert, XCircle } from 'lucide-react'
import { api } from '../api'
import { Answer, Badge, Button, ErrorBox, Field, Input, Note, PageHeader, Section, Table, cx } from '../components/ui.jsx'
import { inr } from '../format'
import { useFinora } from '../store.jsx'

const TYPES = [['car', 'Car', Car, 9.5, 60, 1200000], ['home', 'Home', Home, 8.75, 240, 6000000], ['bike', 'Bike', Bike, 11, 36, 150000], ['phone', 'Phone', Smartphone, 15, 12, 90000],
  ['gadget', 'Gadget', Laptop, 15, 12, 150000], ['trip', 'Trip', Plane, 14, 12, 200000], ['education', 'Education', GraduationCap, 10.5, 84, 1500000], ['wedding', 'Wedding', Heart, 13, 36, 1000000], ['other', 'Other', Package, 12, 36, 300000]]
const V = { AFFORDABLE: ['good', CheckCircle2, 'border-good/40 bg-good/10 text-good'], STRETCH: ['warn', TriangleAlert, 'border-warn/40 bg-warn/10 text-warn'], 'NOT ADVISABLE': ['bad', XCircle, 'border-bad/40 bg-bad/10 text-bad'] }

export default function Decision() {
  const { profileId, analysis: a } = useFinora()
  const [f, setF] = useState({ item_type: 'car', item_name: 'New car', price: 1200000, down_payment: 240000, interest_rate: 9.5, tenure_months: 60, running_cost_monthly: '' })
  const [res, setRes] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const pick = ([t, label, , rate, n, price]) => setF({ item_type: t, item_name: t === 'other' ? 'Purchase' : `New ${label.toLowerCase()}`, price, down_payment: Math.round(price * 0.2), interest_rate: rate, tenure_months: n, running_cost_monthly: '' })
  const run = async (e) => {
    e?.preventDefault(); setBusy(true); setErr(null)
    try { setRes(await api.decision(profileId, { ...f, price: Number(f.price), down_payment: Number(f.down_payment), interest_rate: Number(f.interest_rate), tenure_months: Number(f.tenure_months), running_cost_monthly: f.running_cost_monthly === '' ? null : Number(f.running_cost_monthly) })) }
    catch (x) { setErr(x.message) } finally { setBusy(false) }
  }
  const plan = res?.plan
  const [vtone, VIcon] = plan ? V[plan.verdict] : []
  const Change = ({ label, d, fmt = (x) => x, worse = 'down' }) => {
    const bad = worse === 'down' ? d.after < d.before : d.after > d.before
    return (
      <li className="flex flex-wrap items-center justify-between gap-3 px-5 py-3.5 sm:px-6">
        <span className="text-sm text-ink-2">{label}</span>
        <span className="num flex items-center gap-2 text-sm"><span className="text-muted">{fmt(d.before)}</span><ArrowRight size={14} className="text-faint" aria-label="becomes" />
          <span className={cx('font-semibold', d.after === d.before ? 'text-ink' : bad ? 'text-bad' : 'text-good')}>{fmt(d.after)}</span></span>
      </li>
    )
  }
  return (
    <>
      <PageHeader title="What if" subtitle="Thinking about a big purchase? Finora shows its real cost and what it does to your EMIs, runway and retirement, with a verdict from fixed, published rules." />
      <ol className="space-y-8">
        <li>
          <h3 className="flex items-center gap-2 text-[15px] font-semibold text-ink"><span className="num grid h-6 w-6 place-items-center rounded-full bg-accent text-micro font-semibold text-white">1</span> What are you thinking of buying?</h3>
          <div role="radiogroup" aria-label="Kind of purchase" className="mt-3 grid grid-cols-3 gap-2 sm:grid-cols-5 lg:grid-cols-9">
            {TYPES.map((t) => { const I = t[2]; const on = f.item_type === t[0]; return (
              <button key={t[0]} type="button" role="radio" aria-checked={on} onClick={() => pick(t)}
                className={cx('flex flex-col items-center gap-1.5 rounded-lg border px-2 py-3 text-[13px] font-medium transition-colors', on ? 'border-accent bg-accent-soft text-accent ring-2 ring-accent/15' : 'border-line bg-bg text-ink-2 hover:border-control/60')}>
                <I size={18} aria-hidden />{t[1]}</button>) })}
          </div>
        </li>
        <li>
          <h3 className="flex items-center gap-2 text-[15px] font-semibold text-ink"><span className="num grid h-6 w-6 place-items-center rounded-full bg-accent text-micro font-semibold text-white">2</span> The details</h3>
          <form onSubmit={run} className="mt-3 grid gap-4 rounded-xl border border-line bg-bg p-5 sm:grid-cols-2 sm:p-6 lg:grid-cols-3">
            <Field label="Name"><Input value={f.item_name} onChange={(e) => setF({ ...f, item_name: e.target.value })} /></Field>
            <Field label="Price (₹)"><Input type="number" min={1} required value={f.price} onChange={(e) => setF({ ...f, price: e.target.value })} /></Field>
            <Field label="Down payment (₹)"><Input type="number" min={0} value={f.down_payment} onChange={(e) => setF({ ...f, down_payment: e.target.value })} /></Field>
            <Field label="Interest rate (% a year)"><Input type="number" step="0.05" min={0} max={40} value={f.interest_rate} onChange={(e) => setF({ ...f, interest_rate: e.target.value })} /></Field>
            <Field label="Loan tenure (months)"><Input type="number" min={0} max={360} value={f.tenure_months} onChange={(e) => setF({ ...f, tenure_months: e.target.value })} /></Field>
            <Field label="Running cost per month (₹)" hint="Insurance, fuel, maintenance. Blank uses a typical estimate."><Input type="number" min={0} placeholder="Typical estimate…" value={f.running_cost_monthly} onChange={(e) => setF({ ...f, running_cost_monthly: e.target.value })} /></Field>
            <div className="flex flex-wrap items-center gap-4 sm:col-span-2 lg:col-span-3">
              <Button type="submit" size="lg" loading={busy}>Should I buy it?</Button>
              <span className="text-[13px] text-muted">Compared with your income {inr(a.cash_flow.avg_monthly_income)}/mo, surplus {inr(a.cash_flow.avg_monthly_savings)}/mo and liquid savings {inr(a.liquidity.emergency_pool)}.</span>
            </div>
          </form>
        </li>
      </ol>

      <div aria-live="polite" className="mt-10">
        {err && <ErrorBox message={err} />}
        {res?.available === false && <Note tone="warn">{res.message} <a href="/data?tab=records" className="font-medium underline">Add your income and transactions</a>.</Note>}
        {plan && (<>
          <div className="mb-2 flex items-center gap-2 text-[13px] font-medium text-muted"><VIcon size={16} className={vtone === 'good' ? 'text-good' : vtone === 'warn' ? 'text-warn' : 'text-bad'} aria-hidden /> Verdict for {res.item.name}</div>
          <Answer sub={plan.reasons.map((r) => r.text).join(' ')}>
            <span className={vtone === 'good' ? 'text-good' : vtone === 'warn' ? 'text-warn' : 'text-bad'}>{plan.verdict === 'AFFORDABLE' ? 'Affordable.' : plan.verdict === 'STRETCH' ? 'A stretch.' : 'Not advisable right now.'}</span>{' '}
            An EMI of <b>{inr(plan.emi, { compact: false })}</b> a month{plan.total_interest > 0 ? <>, and <b>{inr(plan.total_interest)}</b> in interest</> : ''}.
          </Answer>
          {plan.verdict !== 'AFFORDABLE' && (res.best_option || res.max_affordable_price_same_terms > 0) && (
            <Note tone="info">{res.best_option && res.best_option !== 'Your plan' ? <>A better route: <b>{res.best_option}</b>. </> : res.best_option == null ? 'None of the alternatives makes this advisable right now. ' : null}
              {res.max_affordable_price_same_terms > 0 && <>On the same terms, up to about <b>{inr(res.max_affordable_price_same_terms)}</b> would be comfortably affordable.</>}</Note>
          )}
          <div className="mt-8 grid gap-8 lg:grid-cols-2">
            <Section title="What it changes">
              <ul className="divide-y divide-line overflow-hidden rounded-xl border border-line bg-bg">
                <Change label="EMIs as a share of income" d={plan.impact.emi_to_income_pct} fmt={(x) => `${x}%`} worse="up" />
                <Change label="Monthly surplus" d={plan.impact.monthly_surplus} fmt={(x) => inr(x)} />
                <Change label="Savings rate" d={plan.impact.savings_rate_pct} fmt={(x) => `${x}%`} />
                <Change label="Emergency runway" d={plan.impact.runway_months} fmt={(x) => `${x} months`} />
                <Change label="Liquid savings" d={plan.impact.liquid_savings} fmt={(x) => inr(x)} />
                <Change label="Financial independence age" d={{ before: plan.impact.fire_age.before ?? 99, after: plan.impact.fire_age.after ?? 99 }} fmt={(x) => (x === 99 ? '75+' : x)} worse="up" />
              </ul>
              {plan.impact.fire_delay_years > 0 && <p className="mt-3 text-sm text-warn">This delays financial independence by {plan.impact.fire_delay_years} years.</p>}
            </Section>
            <Section title="The real cost">
              <ul className="divide-y divide-line overflow-hidden rounded-xl border border-line bg-bg">
                {[['Loan amount', inr(plan.loan_amount)], ['Total interest', inr(plan.total_interest)], ['Running cost', `${inr(plan.running_cost_monthly)} a month`],
                  [`Total cost over ${plan.tco_period_months} months`, inr(plan.total_cost_of_ownership)]].map(([k, v]) => (
                  <li key={k} className="flex justify-between gap-3 px-5 py-3.5 text-sm sm:px-6"><span className="text-ink-2">{k}</span><span className="num font-semibold text-ink">{v}</span></li>))}
              </ul>
            </Section>
          </div>
          <details className="mt-8 rounded-xl border border-line bg-bg px-5 py-4">
            <summary className="cursor-pointer text-[15px] font-medium text-ink">Compare with the alternatives ({res.alternatives.length})</summary>
            <div className="mt-4"><Table dense rows={[plan, ...res.alternatives].map((o, i) => ({ id: i, ...o }))} columns={[
              { key: 'name', label: 'Option', render: (o) => <span className="font-medium">{o.name}</span> },
              { key: 'down_payment', label: 'Down payment', right: true, render: (o) => inr(o.down_payment) }, { key: 'emi', label: 'EMI', right: true, render: (o) => inr(o.emi) },
              { key: 'total_interest', label: 'Interest', right: true, render: (o) => inr(o.total_interest) },
              { key: 'r', label: 'Runway after', right: true, render: (o) => `${o.impact.runway_months.after} mo` },
              { key: 'e', label: 'EMI load', right: true, render: (o) => `${o.impact.emi_to_income_pct.after}%` },
              { key: 'verdict', label: 'Verdict', render: (o) => <Badge tone={V[o.verdict][0]}>{o.verdict}</Badge> }]} /></div>
          </details>
          <p className="mt-6 text-micro leading-4 text-faint"><b>How the verdict is decided:</b> {res.verdict_rules.replace(/\s+/g, ' ')}</p>
        </>)}
      </div>
    </>
  )
}
