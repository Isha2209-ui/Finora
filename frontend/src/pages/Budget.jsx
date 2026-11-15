// Was "Budget, Savings & Tax". Split by task (spec §4.1):
//   BudgetSection  → Money → Spending → Budget   (essentials vs lifestyle, suggested limits, recurring payments)
//   SavingsSection → Future → Savings            (savings trend, cut-back scenarios, idle money)
//   TaxSection     → Plan → Tax                  (old vs new regime, live calculator)
import { useState } from 'react'
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '../api'
import { Badge, Button, Card, Field, Input, KV, Note, PageHeader, Stat, Table, chartAxis, chartTooltip, cx, useToast } from '../components/ui.jsx'
import { axisInr, inr, monthLabel, pct } from '../format'
import { useFinora } from '../store.jsx'

export function BudgetSection() {
  const { analysis: a } = useFinora()
  const { cash_flow: cf, budget: b } = a
  return (
    <>
      <div className="grid gap-4 sm:grid-cols-3">
        <Stat label="Essentials" value={pct(cf.essential_to_income_pct, 0)} sub="of income · rent, utilities, groceries, health, fuel" />
        <Stat label="Lifestyle" value={pct(cf.discretionary_to_income_pct, 0)} tone={cf.discretionary_to_income_pct > 30 ? 'warn' : 'ink'} sub="of income · dining, shopping, travel, entertainment" />
        <Stat label="Months in deficit" value={cf.months_in_deficit == null ? '—' : `${cf.months_in_deficit} of ${cf.period?.months}`} tone={cf.months_in_deficit ? 'bad' : 'good'} sub={`spending varies ±${pct(cf.expense_volatility_pct, 0)} month to month`} />
      </div>
      <Card title="Suggested monthly limits" subtitle="Your 12-month average, the last 3 months, and a limit Finora suggests per lifestyle category" className="mt-6">
        {!b.category_limits?.length ? <p className="py-8 text-center text-sm text-muted">Limits appear once there is spending history in lifestyle categories.</p> : <>
          <div className="h-60"><ResponsiveContainer><BarChart data={b.category_limits} margin={{ left: 0 }}><CartesianGrid vertical={false} />
            <XAxis dataKey="category" {...chartAxis} /><YAxis tickFormatter={axisInr} {...chartAxis} width={48} />
            <Tooltip {...chartTooltip} formatter={(v, n) => [inr(v), n]} /><Legend wrapperStyle={{ fontSize: 12 }} />
            <Bar dataKey="12m_avg" name="12-month average" fill="#98a2b3" radius={[3, 3, 0, 0]} /><Bar dataKey="last_3m_avg" name="Last 3 months" fill="#c0396b" radius={[3, 3, 0, 0]} />
            <Bar dataKey="suggested_limit" name="Suggested limit" fill="#3157c8" radius={[3, 3, 0, 0]} /></BarChart></ResponsiveContainer></div>
          <details className="mt-3 text-sm"><summary className="cursor-pointer text-accent">View as table</summary>
            <Table dense rows={b.category_limits} columns={[{ key: 'category', label: 'Category' }, { key: '12m_avg', label: '12-month avg', right: true, render: (r) => inr(r['12m_avg']) },
              { key: 'last_3m_avg', label: 'Last 3 months', right: true, render: (r) => inr(r.last_3m_avg) }, { key: 'suggested_limit', label: 'Suggested limit', right: true, render: (r) => inr(r.suggested_limit) }]} /></details>
        </>}
      </Card>
      <Card title="Recurring payments" subtitle="Found automatically: the same merchant in 3+ months with a stable amount" className="mt-6" pad={false}>
        <Table dense rows={a.recurring_detected} empty="No recurring payments detected" caption="Recurring payments" columns={[
          { key: 'merchant', label: 'Merchant', render: (r) => <span className="font-medium">{r.merchant}</span>, sort: (r) => r.merchant }, { key: 'category', label: 'Category', sort: (r) => r.category },
          { key: 'months_seen', label: 'Months seen', right: true, sort: (r) => r.months_seen }, { key: 'stability_pct', label: 'Stability', right: true, render: (r) => pct(r.stability_pct, 0) },
          { key: 'typical_amount', label: 'Typical monthly', right: true, render: (r) => inr(r.typical_amount), sort: (r) => r.typical_amount }]} />
      </Card>
    </>
  )
}

export function SavingsSection() {
  const { analysis: a } = useFinora()
  const { cash_flow: cf, budget: b, idle_money: idle } = a
  return (
    <>
      <PageHeader title="Savings" subtitle="What you keep each month, and what changes would add to it. Figures are your actual history; the cut-back scenarios are projections." />
      <div className="grid gap-4 sm:grid-cols-2">
        <Stat label="Savings rate (12 months)" value={pct(cf.avg_savings_rate_pct)} tone={cf.avg_savings_rate_pct >= 20 ? 'good' : cf.avg_savings_rate_pct >= 0 ? 'warn' : 'bad'} sub={`${inr(cf.avg_monthly_savings)} a month · guideline 20%+`} />
        <Stat label="Idle money in low-interest accounts" value={inr(idle.idle_in_low_yield_accounts)} tone={idle.annual_opportunity_cost > 0 ? 'warn' : 'ink'} sub={`costing about ${inr(idle.annual_opportunity_cost)} a year`} />
      </div>
      <Card title="Income, spending and savings by month" subtitle="Actual history" className="mt-6">
        {!cf.monthly_series?.length ? <p className="py-10 text-center text-sm text-muted">Needs income and spending history.</p> :
          <div className="h-64"><ResponsiveContainer><LineChart data={cf.monthly_series} margin={{ left: 0, right: 8, top: 8 }}><CartesianGrid vertical={false} />
            <XAxis dataKey="month" tickFormatter={monthLabel} {...chartAxis} /><YAxis tickFormatter={axisInr} {...chartAxis} width={52} />
            <Tooltip {...chartTooltip} labelFormatter={monthLabel} formatter={(v, n) => [inr(v), n]} /><Legend wrapperStyle={{ fontSize: 12 }} />
            <Line dataKey="income" name="Income" stroke="#0e8074" strokeWidth={2} dot={false} /><Line dataKey="expenses" name="Spending" stroke="#c0396b" strokeWidth={2} dot={false} />
            <Line dataKey="savings" name="Savings" stroke="#3157c8" strokeWidth={2.5} dot={false} /></LineChart></ResponsiveContainer></div>}
      </Card>
      <Card title="If you cut lifestyle spending" subtitle={`Projection · lifestyle spending averages ${inr(b.discretionary_monthly_avg)} a month`} className="mt-6">
        <div className="grid gap-3 sm:grid-cols-3">
          {b.scenarios.map((s) => (
            <div key={s.cut_discretionary_pct} className="rounded-lg border border-line p-4">
              <div className="text-[13px] text-muted">Cut by {s.cut_discretionary_pct}%</div>
              <div className="num mt-1 text-xl font-semibold text-good">+{inr(s.monthly_saving)}<span className="text-sm font-normal text-muted"> /month</span></div>
              <div className="num mt-1 text-[13px] text-muted">{inr(s.annual_saving)} a year · savings rate → {pct(s.new_savings_rate_pct)}</div>
            </div>
          ))}
        </div>
        <div className="mt-4"><Note>{idle.explanation}</Note></div>
      </Card>
    </>
  )
}

export function TaxSection() {
  const { analysis: a } = useFinora()
  const toast = useToast()
  const [tax, setTax] = useState(a.tax)
  const db = a.tax.old?.deduction_breakup || {}
  const [form, setForm] = useState({ gross_income: a.tax.gross_income ?? '', sec_80c: db['80C'] || 0, sec_80d: db['80D'] || 0, home_loan_interest: db['24(b) home loan interest'] || 0, hra_exemption: 0 })
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const calc = async (e) => {
    e.preventDefault()
    if (!(Number(form.gross_income) > 0)) { setErr('Enter your gross annual income to compare the regimes.'); return }
    setErr(null); setBusy(true)
    try {
      setTax(await api.tax({ ...Object.fromEntries(Object.entries(form).map(([k, v]) => [k, Number(v) || 0])), gross_income: Number(form.gross_income), salaried: a.profile.employment_type === 'salaried' }))
      toast('Tax comparison updated', { tone: 'good' })
    } catch (x) { setErr(x.message) } finally { setBusy(false) }
  }
  const f = (k, label, hint) => <Field label={label} hint={hint}><Input type="number" inputMode="numeric" min={0} name={k} value={form[k]} onChange={(e) => setForm({ ...form, [k]: e.target.value })} /></Field>
  return (
    <>
      <PageHeader title={`Income tax: old vs new regime${tax.financial_year ? ` · FY ${tax.financial_year}` : ''}`} subtitle="Slabs, standard deduction and the Section 87A rebate for a resident individual under 60. Change the inputs to see how the comparison moves; nothing is saved." />
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
        <Card title="Your inputs">
          <form onSubmit={calc} className="grid gap-4 sm:grid-cols-2">
            {f('gross_income', 'Gross annual income (₹)')}
            {f('sec_80c', '80C investments', 'Up to ₹1.5 lakh')}
            {f('sec_80d', '80D health premium')}
            {f('home_loan_interest', 'Home-loan interest', 'Up to ₹2 lakh')}
            {f('hra_exemption', 'HRA exemption')}
            <div className="flex items-end"><Button type="submit" loading={busy} className="w-full">Compare regimes</Button></div>
            {err && <p role="alert" className="text-[13px] text-bad sm:col-span-2">{err}</p>}
          </form>
        </Card>
        <Card title="Result">
          {tax.available === false ? <p className="text-sm text-muted">Your income is not recorded, so there is no estimate from your profile yet. Enter a gross annual income and choose Compare regimes.</p> : <div>
            <div className="grid gap-3 sm:grid-cols-2">
              {['new', 'old'].map((r) => (
                <div key={r} className={cx('rounded-lg border p-4', tax.better_regime === r ? 'border-good/30 bg-good-soft' : 'border-line')}>
                  <div className="flex items-center justify-between text-[13px] text-muted"><span className="capitalize">{r} regime</span>{tax.better_regime === r && <Badge tone="good">Costs less</Badge>}</div>
                  <div className="num mt-1 text-xl font-semibold">{inr(tax[r].total_tax, { compact: false })}</div>
                  <div className="num mt-1 text-micro text-muted">taxable {inr(tax[r].taxable_income)} · std. deduction {inr(tax[r].standard_deduction)}{r === 'old' ? ` · deductions ${inr(tax.old.deductions)}` : ''}</div>
                </div>
              ))}
            </div>
            <p className="mt-4 text-sm text-ink-2">The <span className="font-medium text-good">{tax.better_regime} regime</span> saves {inr(tax.saving_with_better, { compact: false })}. The old regime only wins once deductions exceed about {inr(tax.old_regime_breakeven_deductions)}.</p>
            <div className="mt-3"><Note>{tax.assumptions.filter((x) => !/educational|advice/i.test(x)).join(' · ')}.</Note></div>
          </div>}
        </Card>
      </div>
    </>
  )
}

export default BudgetSection
