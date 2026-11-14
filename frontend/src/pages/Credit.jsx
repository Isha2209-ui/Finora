import { useEffect, useState } from 'react'
import { ShieldAlert, ShieldCheck } from 'lucide-react'
import { api } from '../api'
import { Badge, Card, Empty, KV, Meter, Note, PageHeader, Stat, Table, cx } from '../components/ui.jsx'
import { inr, pct } from '../format'
import { useFinora } from '../store.jsx'

const bandTone = { low: 'good', moderate: 'warn', high: 'bad', 'very high': 'bad', none: 'good' }

export default function Credit() {
  const { analysis: a, profileId } = useFinora()
  const { credit, debt } = a
  const risk = a.ml.credit_risk
  const [extra, setExtra] = useState(0)
  const [plan, setPlan] = useState(null)
  useEffect(() => { const t = setTimeout(() => api.payoff(profileId, extra).then(setPlan).catch(() => {}), 200); return () => clearTimeout(t) }, [profileId, extra])
  return (
    <>
      <PageHeader title="Credit & Debt" subtitle="Card-default risk from a model trained on 30,000 real card accounts, plus loans, EMI load and the cheapest way out of debt." />
      <div className="grid gap-4 md:grid-cols-4">
        <Stat label="Risk of missing a card payment" value={risk?.has_cards && risk.cards ? `${risk.overall_default_probability_pct}%` : '—'} tone={bandTone[risk?.overall_risk_band] || 'ink'}
          icon={risk?.overall_risk_band === 'low' ? ShieldCheck : ShieldAlert} sub={risk?.cards ? `${risk.overall_risk_band} · population average ${risk.population_base_rate_pct}%` : 'no cards'} />
        <Stat label="Card utilisation" value={credit.has_cards ? pct(credit.overall_utilisation_pct, 0) : '—'} tone={!credit.has_cards ? 'ink' : credit.overall_utilisation_pct < 30 ? 'good' : credit.overall_utilisation_pct < 50 ? 'warn' : 'bad'} sub="under 30% is healthy" />
        <Stat label="EMIs / income" value={pct(debt.emi_to_income_pct, 0)} tone={bandTone[debt.risk_band]} sub={`${inr(debt.total_emi)} a month · ${debt.risk_band}`} />
        <Stat label="Total debt" value={inr(debt.total_debt || 0)} sub={debt.has_debt ? `average rate ${pct(debt.weighted_avg_rate_pct)}` : 'debt-free'} tone={debt.has_debt ? 'ink' : 'good'} />
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        <Card title="Credit-risk model: why this score" subtitle="XGBoost on the UCI credit-default dataset; contributions computed with SHAP">
          {!risk?.cards ? <Empty title="No card history to score">{risk?.note}</Empty> : (
            <div className="space-y-4">
              {risk.cards.map((c) => (
                <div key={c.last4}>
                  <div className="flex items-center justify-between"><span className="text-sm font-medium">{c.card} ••{c.last4}</span><Badge tone={bandTone[c.risk_band]}>{c.default_probability_pct}% · {c.risk_band}</Badge></div>
                  <div className="mt-1.5"><Meter value={c.default_probability_pct} tone={bandTone[c.risk_band]} /></div>
                  <ul className="mt-2 space-y-1 text-xs">
                    {c.top_factors.map((f) => (
                      <li key={f.factor} className="flex items-center gap-2">
                        <span className={`num w-14 shrink-0 text-right font-mono ${f.shap > 0 ? 'text-bad' : 'text-good'}`}>{f.shap > 0 ? '+' : ''}{f.shap.toFixed(2)}</span>
                        <div className="h-1.5 w-24 overflow-hidden rounded-full bg-raised"><div className={f.shap > 0 ? 'h-full bg-bad' : 'h-full bg-good'} style={{ width: `${Math.min(100, Math.abs(f.shap) * 60)}%` }} /></div>
                        <span className="text-muted">{f.factor} <span className="text-faint">= {f.value}</span> · {f.effect}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
              <Note>{risk.interpretation}</Note>
            </div>
          )}
          <div className="mt-3"><Note tone="warn">Model-generated estimate, not an official credit score. Trained on 30,000 Taiwanese card accounts (2005); test ROC-AUC 0.783 against 0.760 for a logistic-regression baseline. Not validated for Indian borrowers.</Note></div>
        </Card>
        <Card title="Loans" subtitle={debt.note} pad={false}>
          <Table dense rows={debt.loans} empty="No loans" columns={[
            { key: 'loan_type', label: 'Loan', render: (l) => <div><div className="font-medium">{l.loan_type}</div><div className="text-xs text-muted">{l.lender}{l.secured_by_property ? ' · secured by property' : ''}</div></div> },
            { key: 'balance', label: 'Balance', right: true, render: (l) => inr(l.balance) },
            { key: 'emi', label: 'EMI', right: true, render: (l) => inr(l.emi) },
            { key: 'interest_rate', label: 'Rate', right: true, render: (l) => pct(l.interest_rate) },
            { key: 'remaining_months', label: 'Months left', right: true },
            { key: 'remaining_interest', label: 'Interest still to pay', right: true, render: (l) => inr(l.remaining_interest) },
          ]} />
          {debt.has_debt && <div className="px-5 pb-4"><Meter value={debt.emi_to_income_pct || 0} max={60} tone={bandTone[debt.risk_band]} label={<><span>EMI load</span><span className="num">{pct(debt.emi_to_income_pct, 0)} of income (comfortable limit 40%)</span></>} /></div>}
        </Card>
      </div>

      <CreditWhatIf />

      <Card title="Debt payoff planner" subtitle="Month-by-month simulation of every loan and card. Avalanche = highest interest first; snowball = smallest balance first." className="mt-4">
        {!plan?.has_debt ? <p className="py-6 text-center text-sm text-good">No debt to plan for.</p> : (
          <div className="grid gap-6 xl:grid-cols-[320px_1fr]">
            <div>
              <label className="text-xs text-muted">Extra payment per month</label>
              <div className="num mt-1 text-2xl font-semibold text-accent">{inr(extra, { compact: false })}</div>
              <input type="range" min={0} max={50000} step={1000} value={extra} onChange={(e) => setExtra(Number(e.target.value))} className="mt-2 w-full" />
              {extra > 0 && <div className="mt-3 rounded-xl border border-good/30 bg-good/10 p-3 text-sm text-good">Debt-free {plan.vs_no_extra.months_saved} months sooner, saving {inr(plan.vs_no_extra.interest_saved)} in interest.</div>}
              <div className="mt-3"><KV rows={[['Avalanche: months to debt-free', plan.avalanche.months_to_debt_free], ['Avalanche: total interest', inr(plan.avalanche.total_interest)],
                ['Snowball: months to debt-free', plan.snowball.months_to_debt_free], ['Snowball: total interest', inr(plan.snowball.total_interest)],
                ['Avalanche saves', inr(plan.interest_saved_by_avalanche), plan.interest_saved_by_avalanche > 0 ? 'good' : undefined]]} /></div>
            </div>
            <div>
              <div className="mb-2 text-xs text-muted">Order in which debts are cleared (avalanche)</div>
              <ol className="space-y-2">
                {plan.avalanche.payoff_order.map((p, i) => { const d = plan.debts.find((x) => x.name === p.debt); return (
                  <li key={p.debt} className="flex items-center gap-3 rounded-xl border border-line bg-raised/50 px-3 py-2 text-sm">
                    <span className="num grid h-6 w-6 place-items-center rounded-full bg-accent/15 text-xs text-accent">{i + 1}</span>
                    <span className="flex-1"><span className="font-medium">{p.debt}</span> <span className="text-xs text-muted">· {inr(d?.balance)} at {d?.rate}%</span></span>
                    <span className="num text-xs text-muted">cleared in month {p.paid_off_in_month}</span>
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
  const cell = 'w-full rounded-lg border border-line bg-bg px-2 py-1 text-xs outline-none focus:border-accent'
  return (
    <Card title="Score a card history" subtitle="Enter six months of a card's statements (most recent first). The real credit-risk model scores it and SHAP shows what drove the result. Nothing is saved." className="mt-4">
      <div className="grid gap-6 xl:grid-cols-[1fr_380px]">
        <div>
          <div className="mb-3 flex flex-wrap gap-3 text-xs">
            <label className="flex items-center gap-2">Age <input type="number" min={18} max={100} value={age} onChange={(e) => setAge(e.target.value)} className={cx(cell, 'w-20')} /></label>
            <label className="flex items-center gap-2">Credit limit (₹) <input type="number" min={1} value={limit} onChange={(e) => setLimit(e.target.value)} className={cx(cell, 'w-32')} /></label>
          </div>
          <table className="w-full text-xs"><thead><tr className="text-left text-faint"><th className="py-1 font-medium">Month</th><th className="font-medium">Payment status</th><th className="font-medium">Bill (₹)</th><th className="font-medium">Paid (₹)</th></tr></thead>
            <tbody>{months.map((m, i) => (
              <tr key={i}><td className="py-1 pr-2 text-muted">{i === 0 ? 'Latest' : `${i} back`}</td>
                <td className="pr-2"><select value={m.status} onChange={(e) => set(i, 'status', e.target.value)} className={cell}>{STATUS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></td>
                <td className="pr-2"><input type="number" value={m.bill} onChange={(e) => set(i, 'bill', e.target.value)} className={cell} /></td>
                <td><input type="number" min={0} value={m.paid} onChange={(e) => set(i, 'paid', e.target.value)} className={cell} /></td></tr>))}</tbody></table>
          <button onClick={run} disabled={busy} className="mt-3 rounded-xl bg-accent px-4 py-2 text-sm font-medium text-bg disabled:opacity-50">{busy ? 'Scoring…' : 'Score with the model'}</button>
          {err && <p className="mt-2 text-xs text-bad">{err}</p>}
        </div>
        <div>
          {!res ? <p className="text-sm text-muted">The result appears here: the probability of missing next month's payment, its band, and every input's contribution.</p> : <>
            <div className="flex items-baseline gap-3"><span className="num text-3xl font-semibold">{res.default_probability_pct}%</span><Badge tone={bandTone[res.risk_band]}>{res.risk_band}</Badge></div>
            <p className="text-xs text-muted">Average in the training data: {res.population_base_rate_pct}% · model {res.model.version} (test ROC-AUC {res.model.test_roc_auc})</p>
            <ul className="mt-3 space-y-1 text-xs">{res.factors.slice(0, 8).map((f) => (
              <li key={f.factor} className="flex items-center gap-2"><span className={`num w-12 shrink-0 text-right font-mono ${f.shap > 0 ? 'text-bad' : 'text-good'}`}>{f.shap > 0 ? '+' : ''}{f.shap.toFixed(2)}</span>
                <span className="text-muted">{f.factor} <span className="text-faint">= {f.value}</span> · {f.effect}</span></li>))}</ul>
            <div className="mt-3"><Note tone="warn">{res.limitation}</Note></div></>}
        </div>
      </div>
    </Card>
  )
}
