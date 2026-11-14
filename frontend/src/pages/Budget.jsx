import { useState } from 'react'
import { Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '../api'
import { Badge, Button, Card, Field, Input, KV, Meter, Note, PageHeader, Stat, Table, chartTooltip } from '../components/ui.jsx'
import { PALETTE, axisInr, inr, monthLabel, pct } from '../format'
import { useFinora } from '../store.jsx'

export default function Budget() {
  const { analysis: a } = useFinora()
  const { cash_flow: cf, budget: b, liquidity: liq, idle_money: idle, insurance: ins } = a
  const cats = cf.category_totals.filter((c) => c.total > 0)
  const [tax, setTax] = useState(a.tax)
  const db = a.tax.old?.deduction_breakup || {}
  const [form, setForm] = useState({ gross_income: a.tax.gross_income ?? '', sec_80c: db['80C'] || 0, sec_80d: db['80D'] || 0, home_loan_interest: db['24(b) home loan interest'] || 0, hra_exemption: 0 })
  const [busy, setBusy] = useState(false)
  const calc = async () => { setBusy(true); try { setTax(await api.tax({ ...Object.fromEntries(Object.entries(form).map(([k, v]) => [k, Number(v) || 0])), gross_income: Number(form.gross_income) || 1, salaried: a.profile.employment_type === 'salaried' })) } finally { setBusy(false) } }
  return (
    <>
      <PageHeader title="Budget, Savings & Tax" subtitle="Where the money goes, what cutting back would free up, and which tax regime costs less." />
      <div className="grid gap-4 md:grid-cols-4">
        <Stat label="Savings rate (12 mo)" value={pct(cf.avg_savings_rate_pct)} tone={cf.avg_savings_rate_pct >= 20 ? 'good' : cf.avg_savings_rate_pct >= 0 ? 'warn' : 'bad'} sub={`${inr(cf.avg_monthly_savings)} a month · guideline 20%+`} />
        <Stat label="Essentials / income" value={pct(cf.essential_to_income_pct, 0)} sub="rent, utilities, groceries, health, fuel…" />
        <Stat label="Discretionary / income" value={pct(cf.discretionary_to_income_pct, 0)} tone={cf.discretionary_to_income_pct > 30 ? 'warn' : 'ink'} sub="dining, shopping, travel, entertainment" />
        <Stat label="Months in deficit" value={cf.months_in_deficit == null ? '—' : `${cf.months_in_deficit} of ${cf.period.months}`} tone={cf.months_in_deficit ? 'bad' : 'good'} sub={`spending varies ±${pct(cf.expense_volatility_pct, 0)}`} />
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-3">
        <Card title="Income, spending and savings" className="xl:col-span-2">
          <div className="h-64"><ResponsiveContainer><LineChart data={cf.monthly_series} margin={{ left: 0, right: 8, top: 8 }}><CartesianGrid vertical={false} />
            <XAxis dataKey="month" tickFormatter={monthLabel} tickLine={false} axisLine={false} /><YAxis tickFormatter={axisInr} tickLine={false} axisLine={false} width={52} />
            <Tooltip {...chartTooltip} labelFormatter={monthLabel} formatter={(v, n) => [inr(v), n]} /><Legend wrapperStyle={{ fontSize: 12 }} />
            <Line dataKey="income" name="Income" stroke="#60a5fa" strokeWidth={2} dot={false} /><Line dataKey="expenses" name="Spending" stroke="#fb7185" strokeWidth={2} dot={false} />
            <Line dataKey="savings" name="Savings" stroke="#34d399" strokeWidth={2} dot={false} /></LineChart></ResponsiveContainer></div>
        </Card>
        <Card title="Spending by category" subtitle="Monthly average">
          <div className="h-40"><ResponsiveContainer><PieChart><Pie data={cats} dataKey="monthly_avg" nameKey="category" innerRadius={40} outerRadius={68} paddingAngle={1.5} stroke="none">
            {cats.map((_, i) => <Cell key={i} fill={PALETTE[i % PALETTE.length]} />)}</Pie><Tooltip {...chartTooltip} formatter={(v) => inr(v)} /></PieChart></ResponsiveContainer></div>
          <ul className="max-h-36 space-y-1 overflow-y-auto text-[13px]">{cats.map((c, i) => <li key={c.category} className="flex items-center gap-2"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: PALETTE[i % PALETTE.length] }} /><span className="flex-1 text-muted">{c.category}</span><span className="num">{inr(c.monthly_avg)}</span><span className="num w-10 text-right text-faint">{pct(c.share_of_spend_pct, 0)}</span></li>)}</ul>
        </Card>
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        <Card title="What if you cut discretionary spending?" subtitle={`Discretionary spending averages ${inr(b.discretionary_monthly_avg)} a month`}>
          <div className="grid grid-cols-3 gap-3">
            {b.scenarios.map((s) => (
              <div key={s.cut_discretionary_pct} className="rounded-xl border border-line bg-raised/50 p-3 text-center">
                <div className="text-xs text-muted">Cut by {s.cut_discretionary_pct}%</div><div className="num mt-1 text-lg font-semibold text-good">+{inr(s.monthly_saving)}</div>
                <div className="text-[11px] text-muted">a month · {inr(s.annual_saving)} a year</div><div className="num mt-1 text-xs">savings rate → {pct(s.new_savings_rate_pct)}</div>
              </div>
            ))}
          </div>
          <div className="mt-4 h-52"><ResponsiveContainer><BarChart data={b.category_limits} margin={{ left: 0 }}><CartesianGrid vertical={false} />
            <XAxis dataKey="category" tickLine={false} axisLine={false} /><YAxis tickFormatter={axisInr} tickLine={false} axisLine={false} width={48} />
            <Tooltip {...chartTooltip} formatter={(v, n) => [inr(v), n]} /><Legend wrapperStyle={{ fontSize: 12 }} />
            <Bar dataKey="12m_avg" name="12-month average" fill="#334155" radius={[3, 3, 0, 0]} /><Bar dataKey="last_3m_avg" name="Last 3 months" fill="#fb7185" radius={[3, 3, 0, 0]} />
            <Bar dataKey="suggested_limit" name="Suggested limit" fill="#2dd4bf" radius={[3, 3, 0, 0]} /></BarChart></ResponsiveContainer></div>
        </Card>
        <div className="space-y-4">
          <Card title="Emergency fund and idle money">
            <Meter value={liq.emergency_fund_months || 0} max={6} tone={(liq.emergency_fund_months || 0) >= 6 ? 'good' : (liq.emergency_fund_months || 0) >= 3 ? 'warn' : 'bad'}
              label={<><span>Emergency fund: {inr(liq.emergency_pool)}</span><span className="num">{liq.emergency_fund_months} of 6 months</span></>} />
            <div className="mt-2"><KV rows={[['Gap to 6 months', inr(liq.emergency_fund_gap), liq.emergency_fund_gap > 0 ? 'warn' : 'good'], ['Idle money in low-interest accounts', inr(idle.idle_in_low_yield_accounts)],
              ['Costing you per year', inr(idle.annual_opportunity_cost), idle.annual_opportunity_cost > 0 ? 'warn' : undefined]]} /></div>
            <div className="mt-2"><Note>{idle.explanation}</Note></div>
          </Card>
          <Card title="Protection">
            <KV rows={[['Term life cover', `${inr(ins.term_cover)} of ${inr(ins.recommended_term_cover)}`, ins.term_gap > 0 ? 'warn' : 'good'], ['Health cover', `${inr(ins.health_cover)} of ${inr(ins.recommended_health_cover)}`, ins.health_gap > 0 ? 'warn' : 'good']]} />
            <div className="mt-2"><Note>{ins.note}</Note></div>
          </Card>
        </div>
      </div>

      <Card title="Recurring payments detected" subtitle="Found automatically: same merchant in 3+ months with a stable amount" className="mt-4" pad={false}>
        <Table dense rows={a.recurring_detected} empty="No recurring payments detected" columns={[
          { key: 'merchant', label: 'Merchant', render: (r) => <span className="font-medium">{r.merchant}</span> }, { key: 'category', label: 'Category' },
          { key: 'months_seen', label: 'Months seen', right: true }, { key: 'stability_pct', label: 'Amount stability', right: true, render: (r) => pct(r.stability_pct, 0) },
          { key: 'typical_amount', label: 'Typical monthly', right: true, render: (r) => inr(r.typical_amount) }]} />
      </Card>

      <Card title={`Income tax: old vs new regime${tax.financial_year ? ` · FY ${tax.financial_year}` : ''}`} subtitle="Slabs, standard deduction and Section 87A rebate for a resident individual under 60" className="mt-4">
        <div className="grid gap-6 xl:grid-cols-[1fr_1.2fr]">
          <div className="grid grid-cols-2 gap-3">
            <Field label="Gross annual income (₹)"><Input type="number" value={form.gross_income} onChange={(e) => setForm({ ...form, gross_income: e.target.value })} /></Field>
            <Field label="80C investments (max 1.5 L)"><Input type="number" value={form.sec_80c} onChange={(e) => setForm({ ...form, sec_80c: e.target.value })} /></Field>
            <Field label="80D health premium"><Input type="number" value={form.sec_80d} onChange={(e) => setForm({ ...form, sec_80d: e.target.value })} /></Field>
            <Field label="Home-loan interest (max 2 L)"><Input type="number" value={form.home_loan_interest} onChange={(e) => setForm({ ...form, home_loan_interest: e.target.value })} /></Field>
            <Field label="HRA exemption"><Input type="number" value={form.hra_exemption} onChange={(e) => setForm({ ...form, hra_exemption: e.target.value })} /></Field>
            <div className="flex items-end"><Button onClick={calc} loading={busy} className="w-full">Compare</Button></div>
          </div>
          {tax.available === false ? <div className="text-sm text-muted">Your income is not recorded, so there is no estimate from your profile. Type a gross annual income and press Compare.</div> : <div>
            <div className="grid grid-cols-2 gap-3">
              {['new', 'old'].map((r) => (
                <div key={r} className={`rounded-xl border p-3 ${tax.better_regime === r ? 'border-good/40 bg-good/10' : 'border-line bg-raised/50'}`}>
                  <div className="flex items-center justify-between text-xs text-muted"><span className="capitalize">{r} regime</span>{tax.better_regime === r && <Badge tone="good">cheaper</Badge>}</div>
                  <div className="num mt-1 text-xl font-semibold">{inr(tax[r].total_tax, { compact: false })}</div>
                  <div className="num mt-1 text-[11px] text-muted">taxable {inr(tax[r].taxable_income)} · std. deduction {inr(tax[r].standard_deduction)}{r === 'old' ? ` · deductions ${inr(tax.old.deductions)}` : ''}</div>
                </div>
              ))}
            </div>
            <p className="mt-3 text-sm">The <span className="font-medium text-good">{tax.better_regime} regime</span> saves {inr(tax.saving_with_better, { compact: false })}. The old regime only wins once deductions exceed about {inr(tax.old_regime_breakeven_deductions)}.</p>
            <div className="mt-2"><Note>{tax.assumptions.join(' · ')}.</Note></div>
          </div>}
        </div>
      </Card>
    </>
  )
}
