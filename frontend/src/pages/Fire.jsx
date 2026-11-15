import { useEffect, useState } from 'react'
import { Area, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Flame, RotateCcw } from 'lucide-react'
import { api } from '../api'
import { Answer, Badge, Button, Card, Facts, Field, Input, KV, Loading, Note, PageHeader, Section, Table, chartAxis, chartTooltip } from '../components/ui.jsx'
import { axisInr, inr, pct } from '../format'
import { useFinora } from '../store.jsx'

export default function Fire() {
  const { analysis: a, profileId } = useFinora()
  const base = a.fire.inputs
  const init = { monthly_investment: base.monthly_investment, retirement_age: a.profile.retirement_age_target, annual_expenses: base.annual_expenses,
    nominal_return_pct: base.nominal_return_pct, inflation_pct: base.inflation_pct, withdrawal_rate_pct: base.withdrawal_rate_pct, step_up_pct: base.annual_step_up_pct }
  const [p, setP] = useState(init)
  const [r, setR] = useState(null)
  const [typed, setTyped] = useState('')
  useEffect(() => { const t = setTimeout(() => api.fire(profileId, p).then(setR).catch(() => {}), 180); return () => clearTimeout(t) }, [profileId, p])
  if (!r) return <Loading label="Projecting…" />
  if (r.available === false) return (
    <>
      <PageHeader title="Retirement" />
      <Card title="A projection needs your yearly expenses" subtitle={r.reason}>
        <KV rows={[['Invested towards retirement (known)', inr(r.inputs.current_corpus)], ['Going in each month (your SIPs)', inr(r.inputs.monthly_investment)]]} />
        <form className="mt-4 flex flex-wrap items-end gap-2" onSubmit={(e) => { e.preventDefault(); if (Number(typed) > 0) setP({ ...p, annual_expenses: Number(typed) }) }}>
          <div className="w-64"><Field label="Expected yearly expenses in retirement (₹)"><Input type="number" min={1} required value={typed} onChange={(e) => setTyped(e.target.value)} /></Field></div>
          <Button type="submit" icon={Flame}>Project with this figure</Button>
        </form>
        <div className="mt-3"><Note>Finora will not guess your expenses. A figure you type here is used only for this projection and is labelled as yours; add transactions or upload a statement to have it measured.</Note></div>
      </Card>
    </>
  )
  const liq = r.runway
  const changed = JSON.stringify(p) !== JSON.stringify(init)
  const S = ({ k, label, min, max, step, fmt, hint }) => (
    <div>
      <div className="flex items-baseline justify-between gap-3"><label htmlFor={`fire-${k}`} className="text-sm font-medium text-ink-2">{label}</label><span className="num text-sm font-semibold text-accent" aria-hidden>{fmt(p[k])}</span></div>
      <input id={`fire-${k}`} type="range" min={min} max={max} step={step} value={p[k]} aria-valuetext={String(fmt(p[k]))} onChange={(e) => setP({ ...p, [k]: Number(e.target.value) })} className="mt-2 w-full" />
      {hint && <div className="mt-1 text-micro text-faint">{hint}</div>}
    </div>
  )
  const maxInv = Math.max(200000, Math.round(base.monthly_investment * 4 / 10000) * 10000)
  const expBase = base.annual_expenses ?? p.annual_expenses
  const rw = (x) => (x == null ? '—' : `${x} months`)
  const gap = r.fire_age != null ? Math.round((r.fire_age - r.retirement_age_target) * 10) / 10 : null
  return (
    <>
      <PageHeader title="Retirement">{changed && <Button variant="secondary" icon={RotateCcw} onClick={() => setP(init)}>Reset to my data</Button>}</PageHeader>
      {r.expenses_source === 'entered by you for this projection' && <div className="mb-6"><Note tone="info">Using yearly expenses you entered ({inr(p.annual_expenses)}), not measured spending.</Note></div>}
      <Answer eyebrow="Projection · when your investments could pay for your life" tone={r.on_track ? 'good' : 'bad'}
        sub={`You would need ${inr(r.fire_number)} invested (${inr(r.inputs.annual_expenses)} a year ÷ ${r.inputs.withdrawal_rate_pct}% withdrawal). You have ${inr(r.inputs.current_corpus)} so far, ${pct(r.progress_pct)} of the way.`}>
        {r.fire_age == null ? <>At this pace you would <b>not reach financial independence by 75</b>.</>
          : r.on_track ? <>You are <b>on track</b>: financially independent around age <b>{r.fire_age}</b>, at or before your target of {r.retirement_age_target}.</>
            : <>At this pace you could be financially independent at <b>{r.fire_age}</b>, {gap} years after your target of {r.retirement_age_target}.</>}
      </Answer>

      <div className="grid gap-8 lg:grid-cols-[320px_minmax(0,1fr)]">
        <div className="space-y-6 rounded-xl border border-line bg-bg p-5 sm:p-6">
          <h3 className="text-[15px] font-semibold text-ink">Adjust your plan</h3>
          <S k="monthly_investment" label="Invest each month" min={0} max={maxInv} step={1000} fmt={(v) => inr(v, { compact: false })} />
          <S k="retirement_age" label="Retire at age" min={Math.max(35, a.profile.age + 2)} max={70} step={1} fmt={(v) => v} />
          <S k="annual_expenses" label="Yearly spending in retirement" min={Math.round(expBase * 0.5 / 10000) * 10000} max={Math.round(expBase * 2 / 10000) * 10000} step={10000} fmt={(v) => inr(v)} hint="In today's rupees" />
          <details className="group">
            <summary className="cursor-pointer text-sm font-medium text-accent">More assumptions</summary>
            <div className="mt-4 space-y-5">
              <S k="nominal_return_pct" label="Expected return" min={6} max={15} step={0.5} fmt={(v) => `${v}%`} />
              <S k="inflation_pct" label="Inflation" min={3} max={9} step={0.5} fmt={(v) => `${v}%`} />
              <S k="withdrawal_rate_pct" label="Safe withdrawal rate" min={2.5} max={5} step={0.1} fmt={(v) => `${v}%`} />
              <S k="step_up_pct" label="Yearly increase in investment" min={0} max={15} step={1} fmt={(v) => `${v}%`} />
            </div>
          </details>
          {!r.on_track && r.monthly_investment_needed_for_target && <div className="rounded-lg border border-warn/25 bg-warn-soft p-3 text-sm text-warn">To retire at {r.retirement_age_target}, invest about <b>{inr(r.monthly_investment_needed_for_target, { compact: false })}</b> a month.</div>}
        </div>
        <div className="min-w-0">
          <Facts items={[
            [`Invested by ${r.retirement_age_target}`, inr(r.corpus_at_target_age), r.on_track ? 'enough for your target' : `short by ${inr(r.shortfall_at_target_age)}`, r.on_track ? 'good' : 'bad'],
            ['Chance of success', pct(r.success_probability_pct, 0), `${(r.monte_carlo?.runs ?? 0).toLocaleString('en-IN')} simulated markets`, r.success_probability_pct >= 70 ? 'good' : r.success_probability_pct >= 40 ? 'warn' : 'bad'],
          ]} />
          <div className="mt-6 h-72" role="img" aria-label={`Projected investments rising to ${inr(r.projection.at(-1)?.corpus)} by age ${r.projection.at(-1)?.age}, against a FIRE number of ${inr(r.fire_number)}`}>
            <ResponsiveContainer>
              <ComposedChart data={r.projection} margin={{ left: 0, right: 12, top: 16 }}>
                <defs><linearGradient id="fc" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#3157c8" stopOpacity={0.18} /><stop offset="100%" stopColor="#3157c8" stopOpacity={0} /></linearGradient></defs>
                <CartesianGrid vertical={false} /><XAxis dataKey="age" {...chartAxis} /><YAxis tickFormatter={axisInr} {...chartAxis} width={56} />
                <Tooltip {...chartTooltip} formatter={(v, n) => [inr(v), n]} labelFormatter={(l) => `Age ${l}`} />
                <Area type="monotone" dataKey="corpus" name="Projected investments" stroke="#3157c8" strokeWidth={2} fill="url(#fc)" />
                <Line type="monotone" dataKey="fire_number" name="Needed (FIRE number)" stroke="#8a92a2" strokeDasharray="6 4" dot={false} />
                <ReferenceLine x={r.retirement_age_target} stroke="#656d7f" strokeDasharray="3 3" label={{ value: `target ${r.retirement_age_target}`, fill: '#656d7f', fontSize: 12, position: 'insideTopRight' }} />
                {r.fire_age && <ReferenceLine x={Math.round(r.fire_age)} stroke="#13794a" label={{ value: `independent ${r.fire_age}`, fill: '#13794a', fontSize: 12, position: 'insideTopLeft' }} />}
              </ComposedChart>
            </ResponsiveContainer>
          </div>
          <p className="mt-2 text-micro text-faint">{r.note}</p>
        </div>
      </div>

      <Section title="The detail" className="mt-12">
        <div className="space-y-3">
          <details className="rounded-xl border border-line bg-bg px-5 py-4"><summary className="cursor-pointer text-[15px] font-medium text-ink">Lean, regular and fat FIRE</summary>
            <div className="mt-4"><Table dense rows={[
              { id: 1, t: 'Lean FIRE', d: '70% of current lifestyle', n: r.lean_fire_number, a: r.lean_fire_age },
              { id: 2, t: 'Regular FIRE', d: 'current lifestyle', n: r.fire_number, a: r.fire_age },
              { id: 3, t: 'Fat FIRE', d: '150% of current lifestyle', n: r.fat_fire_number, a: r.fat_fire_age },
            ]} columns={[{ key: 't', label: 'Type', render: (x) => <div><div className="font-medium">{x.t}</div><div className="text-micro text-muted">{x.d}</div></div> },
              { key: 'n', label: 'Needed', right: true, render: (x) => inr(x.n) }, { key: 'a', label: 'Age', right: true, render: (x) => x.a ?? '75+' }]} />
              <p className="mt-3 text-sm text-muted">Coast FIRE (enough today to reach the FIRE number by 60 with no new investing): {inr(r.coast_fire_number)} — <Badge tone={r.coast_fire_reached ? 'good' : 'neutral'}>{r.coast_fire_reached ? 'reached' : 'not yet'}</Badge></p></div>
          </details>
          <details className="rounded-xl border border-line bg-bg px-5 py-4"><summary className="cursor-pointer text-[15px] font-medium text-ink">Projected investments by age</summary>
            <div className="mt-4"><Table dense rows={r.corpus_by_age.map((x) => ({ id: x.age, ...x }))} columns={[{ key: 'age', label: 'Age' }, { key: 'a', label: "In today's rupees", right: true, render: (x) => inr(x.corpus_todays_rupees) },
              { key: 'b', label: 'In future rupees', right: true, render: (x) => <span className="text-muted">{inr(x.corpus_future_rupees)}</span> }]} /></div>
          </details>
          <details className="rounded-xl border border-line bg-bg px-5 py-4"><summary className="cursor-pointer text-[15px] font-medium text-ink">Assumptions, simulation range and runway</summary>
            <div className="mt-4"><KV rows={[['Real return (after inflation)', pct(r.inputs.real_return_pct)], ['Simulated outcome range at target (10th–90th percentile)', `${inr(r.monte_carlo?.p10)} – ${inr(r.monte_carlo?.p90)}`],
              ['Liquid savings', inr(liq.emergency_pool)], ['Runway at current spending', rw(liq.runway_months)], ['Runway on essentials only', rw(liq.runway_months_essentials_only)]]} />
              <div className="mt-3 space-y-2"><Note>{r.corpus_definition} {r.expense_definition}</Note><Note>{liq.definition}</Note></div></div>
          </details>
        </div>
      </Section>
    </>
  )
}
