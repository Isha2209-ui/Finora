import { useEffect, useState } from 'react'
import { Area, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Flame, RotateCcw } from 'lucide-react'
import { api } from '../api'
import { Badge, Button, Card, KV, Loading, Meter, Note, PageHeader, Stat, Table, chartTooltip } from '../components/ui.jsx'
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
  if (!r) return <Loading full label="Projecting…" />
  if (r.available === false) return (
    <>
      <PageHeader title="FIRE & Retirement" subtitle="Financial Independence, Retire Early: when your investments can pay for your life." />
      <Card title="A projection needs your yearly expenses" subtitle={r.reason}>
        <KV rows={[['Invested towards retirement (known)', inr(r.inputs.current_corpus)], ['Going in each month (your SIPs)', inr(r.inputs.monthly_investment)]]} />
        <form className="mt-4 flex flex-wrap items-end gap-2" onSubmit={(e) => { e.preventDefault(); if (Number(typed) > 0) setP({ ...p, annual_expenses: Number(typed) }) }}>
          <label className="block"><span className="mb-1 block text-xs text-muted">Expected yearly expenses in retirement (₹)</span>
            <input type="number" min={1} required value={typed} onChange={(e) => setTyped(e.target.value)} className="w-56 rounded-xl border border-line bg-bg px-3 py-2 text-sm" /></label>
          <Button icon={Flame}>Project with this figure</Button>
        </form>
        <div className="mt-3"><Note>Finora will not guess your expenses. A figure you type here is used only for this projection and is labelled as yours; add transactions or upload a statement to have it measured.</Note></div>
      </Card>
    </>
  )
  const liq = r.runway
  const changed = JSON.stringify(p) !== JSON.stringify(init)
  const S = ({ k, label, min, max, step, fmt }) => (
    <div><div className="flex justify-between text-xs"><span className="text-muted">{label}</span><span className="num font-medium text-accent">{fmt(p[k])}</span></div>
      <input type="range" min={min} max={max} step={step} value={p[k]} onChange={(e) => setP({ ...p, [k]: Number(e.target.value) })} className="mt-1 w-full" /></div>
  )
  const maxInv = Math.max(200000, Math.round(base.monthly_investment * 4 / 10000) * 10000)
  const expBase = base.annual_expenses ?? p.annual_expenses
  const rw = (x) => (x == null ? '—' : `${x} mo`)
  return (
    <>
      <PageHeader title="FIRE & Retirement" subtitle="Financial Independence, Retire Early: when your investments can pay for your life. Projections update live as you move the sliders.">
        {changed && <Button variant="ghost" icon={RotateCcw} onClick={() => setP(init)}>Reset to my data</Button>}
      </PageHeader>
      {r.expenses_source === 'entered by you for this projection' && <div className="mb-4"><Note tone="info">Using yearly expenses you entered ({inr(p.annual_expenses)}), not measured spending.</Note></div>}
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
        <Stat label="FIRE age" value={r.fire_age ?? '75+'} tone={r.on_track ? 'good' : 'warn'} icon={Flame} sub={r.fire_age ? `${r.years_to_fire} years from now · baseline ${r.baseline.fire_age ?? '75+'}` : 'not reached by 75 at this pace'} />
        <Stat label="FIRE number" value={inr(r.fire_number)} sub={`${inr(r.inputs.annual_expenses)}/yr ÷ ${r.inputs.withdrawal_rate_pct}%`} />
        <Stat label={`Corpus at ${r.retirement_age_target}`} value={inr(r.corpus_at_target_age)} tone={r.on_track ? 'good' : 'bad'} sub={r.on_track ? 'on track for your target' : `short by ${inr(r.shortfall_at_target_age)}`} />
        <Stat label="Success probability" value={pct(r.success_probability_pct, 0)} tone={r.success_probability_pct >= 70 ? 'good' : r.success_probability_pct >= 40 ? 'warn' : 'bad'} sub={`${(r.monte_carlo?.runs ?? 0).toLocaleString()} market scenarios`} />
        <Stat label="Runway if income stops" value={rw(liq.runway_months)} tone={liq.runway_months == null ? 'ink' : liq.runway_months >= 6 ? 'good' : liq.runway_months >= 3 ? 'warn' : 'bad'} sub={liq.runway_months == null ? 'needs measured monthly expenses' : `${rw(liq.runway_months_essentials_only)} on essentials only`} />
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-[1fr_330px]">
        <Card title="Projected corpus vs FIRE number" subtitle={r.note}>
          <div className="h-80"><ResponsiveContainer>
            <ComposedChart data={r.projection} margin={{ left: 0, right: 12, top: 10 }}>
              <defs><linearGradient id="fc" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#2dd4bf" stopOpacity={0.35} /><stop offset="100%" stopColor="#2dd4bf" stopOpacity={0} /></linearGradient></defs>
              <CartesianGrid vertical={false} /><XAxis dataKey="age" tickLine={false} axisLine={false} /><YAxis tickFormatter={axisInr} tickLine={false} axisLine={false} width={56} />
              <Tooltip {...chartTooltip} formatter={(v, n) => [inr(v), n]} labelFormatter={(l) => `Age ${l}`} />
              <Area type="monotone" dataKey="corpus" name="Projected corpus" stroke="#2dd4bf" strokeWidth={2} fill="url(#fc)" />
              <Line type="monotone" dataKey="fire_number" name="FIRE number" stroke="#fbbf24" strokeDasharray="6 4" dot={false} />
              <ReferenceLine x={r.retirement_age_target} stroke="#60a5fa" strokeDasharray="3 3" label={{ value: `target ${r.retirement_age_target}`, fill: '#60a5fa', fontSize: 11, position: 'insideTopRight' }} />
              {r.fire_age && <ReferenceLine x={Math.round(r.fire_age)} stroke="#34d399" label={{ value: `FIRE ${r.fire_age}`, fill: '#34d399', fontSize: 11, position: 'insideTopLeft' }} />}
            </ComposedChart></ResponsiveContainer></div>
          <div className="mt-2"><Meter value={r.progress_pct} tone="accent" label={<><span>Progress to FIRE number</span><span className="num">{inr(r.inputs.current_corpus)} of {inr(r.fire_number)} · {pct(r.progress_pct)}</span></>} /></div>
        </Card>
        <Card title="What if…" subtitle="Change an assumption">
          <div className="space-y-4">
            <S k="monthly_investment" label="Monthly investment" min={0} max={maxInv} step={1000} fmt={(v) => inr(v, { compact: false })} />
            <S k="retirement_age" label="Target retirement age" min={Math.max(35, a.profile.age + 2)} max={70} step={1} fmt={(v) => v} />
            <S k="annual_expenses" label="Annual expenses in retirement" min={Math.round(expBase * 0.5 / 10000) * 10000} max={Math.round(expBase * 2 / 10000) * 10000} step={10000} fmt={(v) => inr(v)} />
            <S k="nominal_return_pct" label="Expected return" min={6} max={15} step={0.5} fmt={(v) => `${v}%`} />
            <S k="inflation_pct" label="Inflation" min={3} max={9} step={0.5} fmt={(v) => `${v}%`} />
            <S k="withdrawal_rate_pct" label="Safe withdrawal rate" min={2.5} max={5} step={0.1} fmt={(v) => `${v}%`} />
            <S k="step_up_pct" label="Yearly increase in investment" min={0} max={15} step={1} fmt={(v) => `${v}%`} />
          </div>
          {!r.on_track && r.monthly_investment_needed_for_target && <div className="mt-4 rounded-xl border border-warn/30 bg-warn/10 p-3 text-sm text-warn">To retire at {r.retirement_age_target} you would need to invest about <b>{inr(r.monthly_investment_needed_for_target, { compact: false })}</b> a month.</div>}
        </Card>
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-3">
        <Card title="Types of FIRE">
          <Table dense rows={[
            { t: 'Lean FIRE', d: '70% of current lifestyle', n: r.lean_fire_number, a: r.lean_fire_age },
            { t: 'Regular FIRE', d: 'current lifestyle', n: r.fire_number, a: r.fire_age },
            { t: 'Fat FIRE', d: '150% of current lifestyle', n: r.fat_fire_number, a: r.fat_fire_age },
          ]} columns={[{ key: 't', label: 'Type', render: (x) => <div><div className="font-medium">{x.t}</div><div className="text-xs text-muted">{x.d}</div></div> },
            { key: 'n', label: 'Corpus needed', right: true, render: (x) => inr(x.n) }, { key: 'a', label: 'Age', right: true, render: (x) => x.a ?? '75+' }]} />
          <div className="mt-3 flex items-center justify-between rounded-xl bg-raised p-3 text-sm"><div><div className="font-medium">Coast FIRE</div><div className="text-xs text-muted">corpus that reaches the FIRE number by 60 with no new investing</div></div>
            <div className="text-right"><div className="num">{inr(r.coast_fire_number)}</div><Badge tone={r.coast_fire_reached ? 'good' : 'neutral'}>{r.coast_fire_reached ? 'reached' : 'not yet'}</Badge></div></div>
        </Card>
        <Card title="Estimated corpus by age" subtitle="Current savings + monthly investment + expected return">
          <Table dense rows={r.corpus_by_age} columns={[{ key: 'age', label: 'Age' }, { key: 'a', label: "In today's rupees", right: true, render: (x) => inr(x.corpus_todays_rupees) },
            { key: 'b', label: 'In future rupees', right: true, render: (x) => <span className="text-muted">{inr(x.corpus_future_rupees)}</span> }]} />
        </Card>
        <Card title="Runway and assumptions">
          <KV rows={[['Liquid savings', inr(liq.emergency_pool)], ['Runway at current spending', rw(liq.runway_months)], ['Runway including stocks and equity funds', rw(liq.runway_months_incl_market)],
            ['Real return (after inflation)', pct(r.inputs.real_return_pct)], ['Monte Carlo outcome range at target', `${inr(r.monte_carlo?.p10)} – ${inr(r.monte_carlo?.p90)}`]]} />
          <div className="mt-2 space-y-2"><Note>{liq.definition}</Note><Note>{r.corpus_definition} {r.expense_definition}</Note></div>
        </Card>
      </div>
    </>
  )
}
