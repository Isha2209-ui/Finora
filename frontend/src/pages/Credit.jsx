import { useEffect, useState } from 'react'
import { ShieldAlert, ShieldCheck } from 'lucide-react'
import { api } from '../api'
import { Badge, Button, Card, Empty, ErrorBox, Field, Input, KV, Meter, Note, PageHeader, Select, Stat, Table, Trust, cx } from '../components/ui.jsx'
import { inr, pct } from '../format'
import { useFinora } from '../store.jsx'

const bandTone = { low: 'good', moderate: 'warn', high: 'bad', 'very high': 'bad', none: 'good' }

export function CreditRiskSection() {
  const { analysis: a } = useFinora()
  const risk = a.ml.credit_risk
  return (
    <>
      <PageHeader title="Credit risk" subtitle="How likely each of your cards is to miss next month's payment, from an XGBoost model trained on 30,000 real card accounts, with SHAP showing what drove each result." />
      <Trust model="credit_risk" className="mb-6" />
      <Card title="Your cards" subtitle={risk?.cards ? `Population average in the training data: ${risk.population_base_rate_pct}%` : undefined}>
        {!risk?.cards ? <Empty title="No card history to score">{risk?.note || 'Add a credit card with its statement history under Data → Records.'}</Empty> : (
          <div className="space-y-6">
            {risk.cards.map((c) => (
              <div key={c.last4}>
                <div className="flex flex-wrap items-center justify-between gap-2"><span className="text-sm font-medium">{c.card} ••{c.last4}</span><Badge tone={bandTone[c.risk_band]}>{c.default_probability_pct}% · {c.risk_band}</Badge></div>
                <div className="mt-2"><Meter value={c.default_probability_pct} tone={bandTone[c.risk_band]} /></div>
                <div className="mt-3 text-micro font-medium uppercase tracking-[0.04em] text-faint">What moved this result</div>
                <ul className="mt-1.5 space-y-1.5 text-[13px]">
                  {c.top_factors.map((f) => (
                    <li key={f.factor} className="flex flex-wrap items-center gap-2">
                      <span className={`num w-14 shrink-0 text-right font-mono ${f.shap > 0 ? 'text-bad' : 'text-good'}`}>{f.shap > 0 ? '+' : ''}{f.shap.toFixed(2)}</span>
                      <div className="h-1.5 w-24 overflow-hidden rounded-full bg-subtle" aria-hidden><div className={f.shap > 0 ? 'h-full bg-bad' : 'h-full bg-good'} style={{ width: `${Math.min(100, Math.abs(f.shap) * 60)}%` }} /></div>
                      <span className="min-w-0 text-ink-2">{f.factor} <span className="text-faint">= {f.value}</span> · {f.effect}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
            <Note>{risk.interpretation}</Note>
          </div>
        )}
      </Card>
      <CreditWhatIf />
    </>
  )
}

export function DebtsSection() {
  const { analysis: a, profileId } = useFinora()
  const { debt } = a
  const [extra, setExtra] = useState(0)
  const [plan, setPlan] = useState(null)
  const [err, setErr] = useState(null)
  useEffect(() => { const t = setTimeout(() => api.payoff(profileId, extra).then((p) => { setPlan(p); setErr(null) }).catch((e) => setErr(e.message)), 200); return () => clearTimeout(t) }, [profileId, extra])
  return (
    <>
      <div className="grid gap-4 sm:grid-cols-2">
        <Stat label="Total debt" value={inr(debt.total_debt || 0)} sub={debt.has_debt ? `average rate ${pct(debt.weighted_avg_rate_pct)}` : 'debt-free'} tone={debt.has_debt ? 'ink' : 'good'} />
        <Stat label="EMIs / income" value={pct(debt.emi_to_income_pct, 0)} tone={bandTone[debt.risk_band]} sub={`${inr(debt.total_emi)} a month · ${debt.risk_band}`} />
      </div>
      <Card title="Loans" subtitle={debt.note} className="mt-6" pad={false}>
        <Table dense rows={debt.loans} empty="No loans recorded" caption="Loans" columns={[
          { key: 'loan_type', label: 'Loan', render: (l) => <div><div className="font-medium">{l.loan_type}</div><div className="text-micro text-muted">{l.lender}{l.secured_by_property ? ' · secured by property' : ''}</div></div> },
          { key: 'balance', label: 'Outstanding', right: true, render: (l) => inr(l.balance), sort: (l) => l.balance },
          { key: 'emi', label: 'EMI', right: true, render: (l) => inr(l.emi), sort: (l) => l.emi },
          { key: 'interest_rate', label: 'Rate', right: true, render: (l) => pct(l.interest_rate), sort: (l) => l.interest_rate },
          { key: 'remaining_months', label: 'Months left', right: true, sort: (l) => l.remaining_months },
          { key: 'remaining_interest', label: 'Interest still to pay', right: true, render: (l) => l.never_paid_off ? <span className="text-bad">Never cleared at this EMI</span> : inr(l.remaining_interest) },
        ]} />
        {debt.has_debt && <div className="px-5 pb-5 sm:px-6"><Meter value={debt.emi_to_income_pct || 0} max={60} tone={bandTone[debt.risk_band]} label={<><span>EMI load</span><span className="num">{pct(debt.emi_to_income_pct, 0)} of income (comfortable limit 40%)</span></>} /></div>}
      </Card>
      <Card title="Payoff planner" subtitle="A month-by-month simulation of every loan and card. Avalanche clears the highest interest first; snowball the smallest balance first." className="mt-6">
        {err ? <ErrorBox message={err} /> : !plan ? <p className="text-sm text-muted" role="status">Simulating…</p> : !plan.has_debt ? <p className="py-6 text-center text-sm text-good">No debt to plan for.</p> : (
          <div className="grid gap-8 lg:grid-cols-[300px_1fr]">
            <div>
              <label htmlFor="extra-pay" className="text-[13px] font-medium text-ink-2">Extra payment per month</label>
              <div className="num mt-1 text-2xl font-semibold text-accent" aria-live="polite">{inr(extra, { compact: false })}</div>
              <input id="extra-pay" type="range" min={0} max={50000} step={1000} value={extra} onChange={(e) => setExtra(Number(e.target.value))} className="mt-2 w-full" aria-valuetext={inr(extra, { compact: false })} />
              {extra > 0 && plan.vs_no_extra && <div className="mt-3 rounded-lg border border-good/25 bg-good-soft p-3 text-sm text-good">Debt-free {plan.vs_no_extra.months_saved} months sooner, saving {inr(plan.vs_no_extra.interest_saved)} in interest.</div>}
              {plan.avalanche.paid_off === false ? (
                <div role="status" className="mt-3 rounded-lg border border-bad/25 bg-bad-soft p-3 text-sm text-bad">
                  At these payments {plan.avalanche.never_paid_off.join(', ')} {plan.avalanche.never_paid_off.length > 1 ? 'are' : 'is'} never paid off: the monthly payment does not cover the interest. Add an extra payment to see a debt-free date.
                </div>
              ) : <div className="mt-3"><KV rows={[['Avalanche: months to debt-free', plan.avalanche.months_to_debt_free], ['Avalanche: total interest', inr(plan.avalanche.total_interest)],
                ['Snowball: months to debt-free', plan.snowball.months_to_debt_free], ['Snowball: total interest', inr(plan.snowball.total_interest)],
                ['Avalanche saves', inr(plan.interest_saved_by_avalanche), plan.interest_saved_by_avalanche > 0 ? 'good' : undefined]]} /></div>}
            </div>
            <div>
              <div className="mb-2 text-[13px] font-medium text-ink-2">Order in which debts are cleared (avalanche)</div>
              <ol className="space-y-2">
                {plan.avalanche.payoff_order.map((p, i) => { const d = plan.debts.find((x) => x.name === p.debt); return (
                  <li key={p.debt} className="flex flex-wrap items-center gap-3 rounded-lg border border-line px-3 py-2.5 text-sm">
                    <span className="num grid h-6 w-6 place-items-center rounded-full bg-accent-soft text-micro font-medium text-accent">{i + 1}</span>
                    <span className="min-w-0 flex-1"><span className="font-medium">{p.debt}</span> <span className="text-[13px] text-muted">· {inr(d?.balance)} at {d?.rate}%</span></span>
                    <span className="num text-[13px] text-muted">cleared in month {p.paid_off_in_month}</span>
                  </li>) })}
              </ol>
            </div>
          </div>
        )}
      </Card>
    </>
  )
}

const STATUS = [[-2, 'No card use'], [-1, 'Paid in full'], [0, 'Paid part (revolving)'], [1, '1 month late'], [2, '2 months late'], [3, '3+ months late']]

function CreditWhatIf() {
  const [age, setAge] = useState(30)
  const [limit, setLimit] = useState(100000)
  const [months, setMonths] = useState(Array.from({ length: 6 }, () => ({ status: 0, bill: 40000, paid: 5000 })))
  const [res, setRes] = useState(null)
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)
  const set = (i, k, v) => setMonths((m) => m.map((x, j) => (j === i ? { ...x, [k]: Number(v) } : x)))
  const run = async () => {
    setBusy(true); setErr(null)
    try { setRes(await api.creditScore({ age: Number(age), credit_limit: Number(limit), months })) } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }
  return (
    <Card title="Try the model: score a card history" subtitle="Enter six months of a card's statements (most recent first). The credit-risk model scores it and SHAP shows what drove the result. Nothing is saved." className="mt-6">
      <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_340px]">
        <form onSubmit={(e) => { e.preventDefault(); run() }}>
          <div className="mb-4 grid max-w-md grid-cols-2 gap-3">
            <Field label="Age"><Input type="number" min={18} max={100} value={age} onChange={(e) => setAge(e.target.value)} /></Field>
            <Field label="Credit limit (₹)"><Input type="number" min={1} value={limit} onChange={(e) => setLimit(e.target.value)} /></Field>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[460px] text-sm"><caption className="sr-only">Six months of card statements</caption>
              <thead><tr className="text-left text-micro uppercase tracking-[0.04em] text-muted"><th scope="col" className="pb-2 font-medium">Month</th><th scope="col" className="pb-2 font-medium">Payment status</th><th scope="col" className="pb-2 font-medium">Bill (₹)</th><th scope="col" className="pb-2 font-medium">Paid (₹)</th></tr></thead>
              <tbody>{months.map((m, i) => { const lbl = i === 0 ? 'Latest month' : `${i} month${i > 1 ? 's' : ''} back`; return (
                <tr key={i}><th scope="row" className="py-1 pr-2 text-left text-[13px] font-normal text-muted">{i === 0 ? 'Latest' : `${i} back`}</th>
                  <td className="py-1 pr-2"><Select aria-label={`${lbl}: payment status`} value={m.status} onChange={(e) => set(i, 'status', e.target.value)} className="h-9 text-[13px]">{STATUS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</Select></td>
                  <td className="py-1 pr-2"><Input aria-label={`${lbl}: bill`} type="number" value={m.bill} onChange={(e) => set(i, 'bill', e.target.value)} className="h-9 text-[13px]" /></td>
                  <td className="py-1"><Input aria-label={`${lbl}: paid`} type="number" min={0} value={m.paid} onChange={(e) => set(i, 'paid', e.target.value)} className="h-9 text-[13px]" /></td></tr>) })}</tbody></table>
          </div>
          <Button type="submit" loading={busy} className="mt-4">Score with the model</Button>
          {err && <p role="alert" className="mt-2 text-[13px] text-bad">{err}</p>}
        </form>
        <div aria-live="polite">
          {!res ? <p className="text-sm text-muted">The result appears here: the probability of missing next month's payment, its band, and every input's contribution.</p> : <>
            <div className="flex items-baseline gap-3"><span className="num text-3xl font-semibold">{res.default_probability_pct}%</span><Badge tone={bandTone[res.risk_band]}>{res.risk_band}</Badge></div>
            <p className="text-xs text-muted">Average in the training data: {res.population_base_rate_pct}% · model {res.model.version} (test ROC-AUC {res.model.test_roc_auc})</p>
            <ul className="mt-3 space-y-1 text-xs">{res.factors.slice(0, 8).map((f) => (
              <li key={f.factor} className="flex items-center gap-2"><span className={`num w-12 shrink-0 text-right font-mono ${f.shap > 0 ? 'text-bad' : 'text-good'}`}>{f.shap > 0 ? '+' : ''}{f.shap.toFixed(2)}</span>
                <span className="text-muted">{f.factor} <span className="text-faint">= {f.value}</span> · {f.effect}</span></li>))}</ul>
            </>}
        </div>
      </div>
    </Card>
  )
}
