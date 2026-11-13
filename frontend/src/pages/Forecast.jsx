import { Bar, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { TrendingDown, TrendingUp } from 'lucide-react'
import { Badge, Card, Empty, KV, Note, PageHeader, Stat, Table, chartTooltip } from '../components/ui.jsx'
import { axisInr, inr, monthLabel, pct } from '../format'
import { useFinora } from '../store.jsx'

export default function Forecast() {
  const { analysis: a } = useFinora()
  const fc = a.ml.forecast
  const cf = a.cash_flow
  if (!fc?.available) return (<><PageHeader title="Cash-Flow Forecast" /><Card><Empty title="Not enough history">{fc?.note || a.ml_errors?.forecast || 'At least 6 months of transactions are needed.'}</Empty></Card></>)
  const series = [...cf.monthly_series.map((m) => ({ month: m.month, actual: m.expenses, income: m.income })),
    { month: fc.prediction_month, predicted: fc.predicted_total_expense, low: fc.range.low, high: fc.range.high, income: fc.expected_income }]
  fc.actual_vs_predicted.forEach((p) => { const r = series.find((s) => s.month === p.month); if (r) r.backtest = p.predicted })
  return (
    <>
      <PageHeader title="Cash-Flow Forecast" subtitle="An XGBoost model predicts next month's spending from your recent pattern. It is trained only on earlier months and tested on later ones, and has never seen this profile's data." />
      <div className="grid gap-4 md:grid-cols-4">
        <Stat label={`Predicted spend · ${monthLabel(fc.prediction_month)}`} value={inr(fc.predicted_total_expense)} tone="accent"
          sub={`likely ${inr(fc.range.low)} – ${inr(fc.range.high)}`} hint={fc.range.confidence} />
        <Stat label="Versus last month" value={`${fc.change_vs_last_month >= 0 ? '+' : ''}${pct(fc.change_vs_last_month_pct)}`} tone={fc.change_vs_last_month > 0 ? 'warn' : 'good'}
          icon={fc.change_vs_last_month > 0 ? TrendingUp : TrendingDown} sub={`last month ${inr(fc.last_month_actual)} · 3-mo avg ${inr(fc.three_month_avg)}`} />
        <Stat label={`Projected ${fc.projected_status}`} value={inr(Math.abs(fc.projected_surplus))} tone={fc.projected_status === 'surplus' ? 'good' : 'bad'} sub={`expected income ${inr(fc.expected_income)}`} />
        <Stat label="Bank balance at month end" value={inr(fc.projected_bank_balance_end_of_month)} tone={fc.cash_crunch_warning ? 'bad' : 'ink'}
          sub={`now ${inr(fc.current_bank_balance)} · after ${inr(fc.planned_investments)} of SIPs`} />
      </div>
      {fc.festive_month && <div className="mt-3"><Note tone="info">{monthLabel(fc.prediction_month)} is flagged as a festive-season month in the model's calendar, which usually lifts shopping.</Note></div>}

      <Card title="Spending: actual, back-tested predictions and next month" subtitle="Dashed line = what the model would have predicted for past months (out-of-sample)" className="mt-4">
        <div className="h-72"><ResponsiveContainer>
          <ComposedChart data={series} margin={{ left: 0, right: 8, top: 8 }}><CartesianGrid vertical={false} />
            <XAxis dataKey="month" tickFormatter={monthLabel} tickLine={false} axisLine={false} /><YAxis tickFormatter={axisInr} tickLine={false} axisLine={false} width={52} />
            <Tooltip {...chartTooltip} labelFormatter={monthLabel} formatter={(v, n) => [inr(v), n]} /><Legend wrapperStyle={{ fontSize: 12 }} />
            <Bar dataKey="actual" name="Actual spend" fill="#334155" radius={[4, 4, 0, 0]} />
            <Bar dataKey="predicted" name="Forecast" fill="#2dd4bf" radius={[4, 4, 0, 0]} />
            <Line dataKey="backtest" name="Model back-test" stroke="#2dd4bf" strokeDasharray="5 4" strokeWidth={2} dot={{ r: 3 }} connectNulls />
            <Line dataKey="income" name="Income" stroke="#60a5fa" strokeWidth={1.5} dot={false} />
          </ComposedChart></ResponsiveContainer></div>
      </Card>

      <div className="mt-4 grid gap-4 xl:grid-cols-3">
        <Card title="Category forecast and suggested budgets" className="xl:col-span-2" pad={false}>
          <Table dense rows={fc.category_predictions} columns={[
            { key: 'category', label: 'Category', render: (c) => <span className="font-medium">{c.category}</span> },
            { key: 'last_month', label: 'Last month', right: true, render: (c) => inr(c.last_month) },
            { key: 'three_month_avg', label: '3-mo avg', right: true, render: (c) => inr(c.three_month_avg) },
            { key: 'predicted', label: 'Predicted', right: true, render: (c) => <span className="font-medium text-accent">{inr(c.predicted)}</span> },
            { key: 'trend', label: 'Trend', render: (c) => <Badge tone={c.trend === 'rising' ? 'warn' : c.trend === 'falling' ? 'good' : 'neutral'}>{c.trend} {c.change_vs_3m_avg_pct != null && `${c.change_vs_3m_avg_pct > 0 ? '+' : ''}${c.change_vs_3m_avg_pct}%`}</Badge> },
            { key: 'suggested_budget', label: 'Suggested budget', right: true, render: (c) => inr(c.suggested_budget) },
          ]} />
        </Card>
        <Card title="How reliable is this?">
          <KV rows={[['Back-test on this profile', `${fc.backtest_on_this_person.months} months`], ['Average error', inr(fc.backtest_on_this_person.mae)],
            ['As share of typical spend', pct((fc.backtest_on_this_person.mae / cf.avg_monthly_expenses) * 100)], ['Range shown', '≈ 80% interval']]} />
          <div className="mt-3 space-y-2"><Note>{fc.backtest_on_this_person.note}</Note>
            <Note>Personal spending is noisy from month to month, so a 10–15% error is normal. See Model Lab for the comparison with a simple 3-month average.</Note></div>
          {fc.top_increase_drivers.length > 0 && <p className="mt-3 text-sm">Pushing next month up: <span className="font-medium text-warn">{fc.top_increase_drivers.join(', ')}</span></p>}
        </Card>
      </div>
    </>
  )
}
