import { Link } from 'react-router-dom'
import { Bar, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Answer, Badge, Card, Empty, Facts, KV, Note, PageHeader, Section, Table, Trust, chartAxis, chartTooltip } from '../components/ui.jsx'
import { present } from '../components/models.js'
import { axisInr, inr, monthLabel, pct } from '../format'
import { useFinora } from '../store.jsx'

export default function Forecast() {
  const { analysis: a } = useFinora()
  const fc = a.ml.forecast
  const cf = a.cash_flow
  if (!fc?.available) return (<><PageHeader title="Cash flow" /><Card><Empty title={fc?.model_status === 'awaiting_approved_model' ? 'No approved forecasting model yet' : 'Not enough history'}>{fc?.model_status === 'awaiting_approved_model'
    ? (fc.note || 'No forecasting model is switched on.') + ' Model Lab shows its status. Your past spending is on Money → Transactions.'
    : fc?.note || a.ml_errors?.forecast || 'At least 6 months of transactions are needed.'}</Empty></Card></>)
  const series = [...cf.monthly_series.map((m) => ({ month: m.month, actual: m.expenses, income: m.income })),
    { month: fc.prediction_month, predicted: fc.predicted_total_expense, low: fc.range.low, high: fc.range.high, income: fc.expected_income }]
  fc.actual_vs_predicted.forEach((p) => { const r = series.find((s) => s.month === p.month); if (r) r.backtest = p.predicted })
  const ev = fc.model_info?.evaluation
  return (
    <>
      <PageHeader title="Cash flow" />
      <Answer eyebrow={`Forecast for ${monthLabel(fc.prediction_month)} · not yet happened`}
        sub={`Likely between ${inr(fc.range.low)} and ${inr(fc.range.high)}. Last month you spent ${inr(fc.last_month_actual)}.`}>
        Next month you are likely to spend about <b>{inr(fc.predicted_total_expense)}</b>, {fc.projected_status === 'surplus'
          ? <>leaving <b className="text-good">{inr(fc.projected_surplus)}</b> of your expected {inr(fc.expected_income)} income.</>
          : <>which is <b className="text-bad">{inr(Math.abs(fc.projected_surplus))}</b> more than your expected {inr(fc.expected_income)} income.</>}
      </Answer>
      <Trust model="forecast" className="mb-6" />
      <Facts items={[
        ['Simple 3-month average', inr(fc.three_month_avg), 'the baseline to compare with'],
        ['Bank balance at month end', inr(fc.projected_bank_balance_end_of_month), `projected · now ${inr(fc.current_bank_balance)}, after ${inr(fc.planned_investments)} of SIPs`, fc.cash_crunch_warning ? 'bad' : undefined],
        fc.top_increase_drivers?.length > 0 && ['Pushing it up', fc.top_increase_drivers.slice(0, 2).join(', '), 'categories rising', 'warn'],
      ]} />
      {fc.festive_month && fc.model_scope !== 'single-person' && <div className="mt-4"><Note tone="info">{monthLabel(fc.prediction_month)} is a festive-season month in the model's calendar, which usually lifts shopping.</Note></div>}

      <Section title="Your spending, month by month" description="Bars are what you actually spent; the blue bar is the forecast. The dashed line is what the model would have predicted for past months." className="mt-10">
        <div className="h-72" role="img" aria-label={`Monthly spending with a forecast of ${inr(fc.predicted_total_expense)} for ${monthLabel(fc.prediction_month)}`}>
          <ResponsiveContainer>
            <ComposedChart data={series} margin={{ left: 0, right: 8, top: 8 }}><CartesianGrid vertical={false} />
              <XAxis dataKey="month" tickFormatter={monthLabel} {...chartAxis} /><YAxis tickFormatter={axisInr} {...chartAxis} width={52} />
              <Tooltip {...chartTooltip} labelFormatter={monthLabel} formatter={(v, n) => [inr(v), n]} /><Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar dataKey="actual" name="Actual spend" fill="#c9cfd8" radius={[4, 4, 0, 0]} />
              <Bar dataKey="predicted" name="Forecast" fill="#3157c8" radius={[4, 4, 0, 0]} />
              <Line dataKey="backtest" name="Model back-test" stroke="#3157c8" strokeDasharray="5 4" strokeWidth={2} dot={{ r: 3 }} connectNulls />
              <Line dataKey="income" name="Income" stroke="#0e8074" strokeWidth={1.5} dot={false} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </Section>

      <Section title="Accuracy and detail" className="mt-10">
        <div className="space-y-3">
          {ev && <details open className="rounded-xl border border-line bg-bg px-5 py-4"><summary className="cursor-pointer text-[15px] font-medium text-ink">Test results against a simple average</summary>
            <div className="mt-4"><KV rows={[['XGBoost forecast (this model)', inr(fc.predicted_total_expense)], ['Simple 3-month average (not a model)', inr(fc.three_month_avg)],
              ['Average error on test data (XGBoost vs average)', `£${ev.xgboost_mae.toLocaleString()} vs £${ev.baseline_3m_average_mae.toLocaleString()}`],
              ['Test months', ev.test_months]]} />
              {present(`${ev.note || ''} ${fc.model_note || ''}`) && <p className="mt-3 text-[13px] leading-5 text-muted">{present(`${ev.note || ''} ${fc.model_note || ''}`)} Errors are in pounds because the test account was British.</p>}</div>
          </details>}
          {!ev && present(fc.model_note) && <p className="text-[13px] text-muted">{present(fc.model_note)}</p>}
          <details className="rounded-xl border border-line bg-bg px-5 py-4"><summary className="cursor-pointer text-[15px] font-medium text-ink">Back-test on your own history</summary>
            <div className="mt-4"><KV rows={[['Months tested', fc.backtest_on_this_person.months], ['Average error', inr(fc.backtest_on_this_person.mae)],
              ['As a share of typical spending', pct((fc.backtest_on_this_person.mae / cf.avg_monthly_expenses) * 100)], ['Range shown', 'about 80% of outcomes']]} />
              <div className="mt-3"><Note>{fc.backtest_on_this_person.note} Personal spending is noisy month to month, so a 10–15% error is normal.</Note></div></div>
          </details>
          <details className="rounded-xl border border-line bg-bg px-5 py-4"><summary className="cursor-pointer text-[15px] font-medium text-ink">By category</summary>
            <div className="mt-4">{fc.category_forecast_available === false
              ? <p className="text-sm text-muted">Per-category forecasts need a model trained on real category spending, and none is approved yet. Your actual category spending is under Money → Spending.</p>
              : <Table dense rows={fc.category_predictions.map((c) => ({ id: c.category, ...c }))} columns={[
                { key: 'category', label: 'Category', render: (c) => <span className="font-medium">{c.category}</span> },
                { key: 'three_month_avg', label: '3-month avg', right: true, render: (c) => inr(c.three_month_avg) },
                { key: 'predicted', label: 'Forecast', right: true, render: (c) => <span className="font-medium text-accent">{inr(c.predicted)}</span> },
                { key: 'trend', label: 'Trend', render: (c) => <Badge tone={c.trend === 'rising' ? 'warn' : c.trend === 'falling' ? 'good' : 'neutral'}>{c.trend}</Badge> },
                { key: 'suggested_budget', label: 'Suggested budget', right: true, render: (c) => inr(c.suggested_budget) }]} />}</div>
          </details>
        </div>
        <p className="mt-4 text-[13px] text-muted"><Link to="/models?tab=lab&model=forecast" className="font-medium text-accent hover:underline">Full model comparison in Model Lab</Link></p>
      </Section>
    </>
  )
}
