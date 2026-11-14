import { useState } from 'react'
import { ArrowRight, Bike, Car, CheckCircle2, GraduationCap, Heart, Home, Laptop, Package, Plane, Smartphone, TriangleAlert, XCircle } from 'lucide-react'
import { api } from '../api'
import { Badge, Button, Card, ErrorBox, Field, Input, Note, PageHeader, Table, cx } from '../components/ui.jsx'
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
  const [, VIcon, vcls] = plan ? V[plan.verdict] : []
  const Imp = ({ label, d, fmt = (x) => x, worse = 'down' }) => {
    const bad = worse === 'down' ? d.after < d.before : d.after > d.before
    return <div className="rounded-xl bg-raised p-3"><div className="text-xs text-muted">{label}</div><div className="num mt-1 flex items-center gap-2 text-sm"><span className="text-muted">{fmt(d.before)}</span><ArrowRight size={13} className="text-faint" /><span className={cx('font-semibold', d.after === d.before ? '' : bad ? 'text-bad' : 'text-good')}>{fmt(d.after)}</span></div></div>
  }
  return (
    <>
      <PageHeader title="Decision Simulator" subtitle="Thinking about a big purchase? See the real cost and what it does to your EMIs, runway and retirement date - with a verdict from fixed, published rules." />
      <div className="grid gap-4 xl:grid-cols-[380px_1fr]">
        <Card title="What are you considering?">
          <div className="grid grid-cols-3 gap-2">
            {TYPES.map((t) => { const I = t[2]; return <button key={t[0]} type="button" onClick={() => pick(t)} className={cx('flex flex-col items-center gap-1 rounded-xl border px-2 py-2.5 text-xs', f.item_type === t[0] ? 'border-accent/60 bg-accent/10 text-accent' : 'border-line bg-raised text-muted hover:text-ink')}><I size={17} />{t[1]}</button> })}
          </div>
          <form onSubmit={run} className="mt-4 grid grid-cols-2 gap-3">
            <div className="col-span-2"><Field label="Name"><Input value={f.item_name} onChange={(e) => setF({ ...f, item_name: e.target.value })} /></Field></div>
            <Field label="Price (₹)"><Input type="number" min={1} required value={f.price} onChange={(e) => setF({ ...f, price: e.target.value })} /></Field>
            <Field label="Down payment (₹)"><Input type="number" min={0} value={f.down_payment} onChange={(e) => setF({ ...f, down_payment: e.target.value })} /></Field>
            <Field label="Interest rate (% a year)"><Input type="number" step="0.05" min={0} max={40} value={f.interest_rate} onChange={(e) => setF({ ...f, interest_rate: e.target.value })} /></Field>
            <Field label="Loan tenure (months)"><Input type="number" min={0} max={360} value={f.tenure_months} onChange={(e) => setF({ ...f, tenure_months: e.target.value })} /></Field>
            <div className="col-span-2"><Field label="Running cost per month (₹)" hint="Insurance, fuel, maintenance. Leave blank for a typical estimate."><Input type="number" min={0} placeholder="auto" value={f.running_cost_monthly} onChange={(e) => setF({ ...f, running_cost_monthly: e.target.value })} /></Field></div>
            <div className="col-span-2"><Button loading={busy} className="w-full">Should I buy it?</Button></div>
          </form>
          <p className="mt-3 text-xs text-faint">Your position: income {inr(a.cash_flow.avg_monthly_income)}/mo · surplus {inr(a.cash_flow.avg_monthly_savings)}/mo · liquid savings {inr(a.liquidity.emergency_pool)}</p>
        </Card>

        <div className="space-y-4">
          {err && <ErrorBox message={err} />}
          {res?.available === false && <Card title="Not enough information for a verdict"><p className="text-sm text-muted">{res.message}</p>
            <a href="/records" className="mt-3 inline-block text-sm text-accent hover:underline">Add your income and transactions →</a></Card>}
          {!plan && !err && res?.available !== false && <Card><div className="py-16 text-center text-sm text-muted">Enter the details and press <span className="text-ink">Should I buy it?</span><br />Finora compares your plan with alternatives such as a bigger down payment or waiting.</div></Card>}
          {plan && (<>
            <div className={cx('rounded-2xl border p-5', vcls)}>
              <div className="flex items-center gap-3"><VIcon size={28} /><div><div className="text-xs uppercase tracking-wider opacity-80">Verdict for {res.item.name}</div><div className="text-2xl font-semibold tracking-tight">{plan.verdict}</div></div>
                <div className="num ml-auto text-right text-ink"><div className="text-xs text-muted">EMI</div><div className="text-xl font-semibold">{inr(plan.emi, { compact: false })}</div></div></div>
              <ul className="mt-3 space-y-1 text-sm text-ink">{plan.reasons.map((r) => <li key={r.text} className="flex gap-2"><span className={r.level === 'block' ? 'text-bad' : r.level === 'warn' ? 'text-warn' : 'text-good'}>●</span>{r.text}</li>)}</ul>
              {plan.verdict !== 'AFFORDABLE' && <p className="mt-3 text-sm text-ink">{res.best_option && res.best_option !== 'Your plan' ? <>A better route: <b>{res.best_option}</b>. </> : res.best_option == null ? <>None of the alternatives makes this advisable right now. </> : null}
                {res.max_affordable_price_same_terms > 0 && <>On the same terms, up to about <b>{inr(res.max_affordable_price_same_terms)}</b> would be comfortably affordable.</>}</p>}
            </div>
            <Card title="The real cost">
              <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
                {[['Loan amount', inr(plan.loan_amount)], ['Total interest', inr(plan.total_interest)], ['Running cost', `${inr(plan.running_cost_monthly)}/mo`], [`Total cost over ${plan.tco_period_months} months`, inr(plan.total_cost_of_ownership)]].map(([k, v]) => <div key={k} className="rounded-xl bg-raised p-3"><div className="text-xs text-muted">{k}</div><div className="num mt-1 font-semibold">{v}</div></div>)}
              </div>
            </Card>
            <Card title="What it does to your finances">
              <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
                <Imp label="EMIs as % of income" d={plan.impact.emi_to_income_pct} fmt={(x) => `${x}%`} worse="up" />
                <Imp label="Monthly surplus" d={plan.impact.monthly_surplus} fmt={(x) => inr(x)} />
                <Imp label="Savings rate" d={plan.impact.savings_rate_pct} fmt={(x) => `${x}%`} />
                <Imp label="Emergency runway" d={plan.impact.runway_months} fmt={(x) => `${x} mo`} />
                <Imp label="Liquid savings" d={plan.impact.liquid_savings} fmt={(x) => inr(x)} />
                <Imp label="FIRE age" d={{ before: plan.impact.fire_age.before ?? 99, after: plan.impact.fire_age.after ?? 99 }} fmt={(x) => (x === 99 ? '75+' : x)} worse="up" />
              </div>
              {plan.impact.fire_delay_years > 0 && <p className="mt-3 text-sm text-warn">This delays financial independence by {plan.impact.fire_delay_years} years.</p>}
            </Card>
            <Card title="Compare the options" pad={false}>
              <Table dense rows={[plan, ...res.alternatives]} columns={[
                { key: 'name', label: 'Option', render: (o) => <span className="font-medium">{o.name}</span> },
                { key: 'down_payment', label: 'Down payment', right: true, render: (o) => inr(o.down_payment) }, { key: 'emi', label: 'EMI', right: true, render: (o) => inr(o.emi) },
                { key: 'total_interest', label: 'Interest', right: true, render: (o) => inr(o.total_interest) },
                { key: 'r', label: 'Runway after', right: true, render: (o) => `${o.impact.runway_months.after} mo` },
                { key: 'e', label: 'EMI load', right: true, render: (o) => `${o.impact.emi_to_income_pct.after}%` },
                { key: 'verdict', label: 'Verdict', render: (o) => <Badge tone={V[o.verdict][0]}>{o.verdict}</Badge> }]} />
            </Card>
            <Note><b>How the verdict is decided:</b> {res.verdict_rules.replace(/\s+/g, ' ')} · {res.disclaimer}</Note>
          </>)}
        </div>
      </div>
    </>
  )
}
