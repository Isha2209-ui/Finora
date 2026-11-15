// Money → Overview (what you own and owe) and Plan → Health (score, pillars, emergency fund, protection).
// Was the single "Financial Identity" page; split so each figure has one home (spec §4.2).
import { Link } from 'react-router-dom'
import { Area, AreaChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { ArrowRight, Info } from 'lucide-react'
import { Card, KV, Meter, Note, PageHeader, chartAxis, chartTooltip, cx } from '../components/ui.jsx'
import { PALETTE, axisInr, inr, monthLabel, pct } from '../format'
import { useFinora } from '../store.jsx'

function Completeness({ a }) {
  if (!a.completeness?.missing?.length) return null
  return (
    <Link to="/data?tab=records" className="mb-6 flex flex-wrap items-center gap-2 rounded-lg border border-accent/20 bg-accent-soft px-4 py-3 text-sm text-info hover:bg-accent-soft/70">
      <Info size={16} aria-hidden /> Data completeness {a.completeness.score_pct}%. Not yet provided: {a.completeness.missing.slice(0, 4).join(', ')}. Results that need them show “—”.
      <span className="ml-auto inline-flex items-center gap-1 font-medium">Add data <ArrowRight size={14} aria-hidden /></span>
    </Link>
  )
}

export function MoneyOverview() {
  const { analysis: a } = useFinora()
  const { net_worth: nw, liquidity: liq, allocation: al } = a
  const assets = Object.entries(nw.breakdown).map(([name, value]) => ({ name, value })).filter((x) => x.value > 0).sort((x, y) => y.value - x.value)
  const liabs = Object.entries(nw.liabilities).map(([name, value]) => ({ name, value })).sort((x, y) => y.value - x.value)
  const change = nw.change_over_period
  return (
    <>
      <Completeness a={a} />
      <div className="flex flex-wrap items-end justify-between gap-6">
        <div>
          <div className="text-[13px] font-medium text-muted">Net worth</div>
          <div className={cx('num mt-1 text-display font-semibold tracking-tight', nw.net_worth < 0 ? 'text-bad' : 'text-ink')}>{inr(nw.net_worth)}</div>
          <div className="mt-1 text-sm text-muted">
            {inr(nw.total_assets)} owned − {inr(nw.total_liabilities)} owed
            {change != null && <> · <span className={change >= 0 ? 'text-good' : 'text-bad'}>{change >= 0 ? '+' : '−'}{inr(Math.abs(change))}</span> over the period</>}
          </div>
        </div>
      </div>

      <Card title="How your net worth has moved" subtitle="Month-end assets minus liabilities" className="mt-6">
        {nw.history.length < 2 ? <p className="py-14 text-center text-sm text-muted">A trend needs month-end history, which builds up as you import statements.</p> : <div className="h-60" role="img" aria-label={`Net worth trend from ${monthLabel(nw.history[0].month)} (${inr(nw.history[0].net_worth)}) to ${monthLabel(nw.history.at(-1).month)} (${inr(nw.history.at(-1).net_worth)})`}>
          <ResponsiveContainer>
            <AreaChart data={nw.history} margin={{ left: 0, right: 8, top: 8 }}>
              <defs><linearGradient id="nw" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#3157c8" stopOpacity={0.18} /><stop offset="100%" stopColor="#3157c8" stopOpacity={0} /></linearGradient></defs>
              <CartesianGrid vertical={false} /><XAxis dataKey="month" tickFormatter={monthLabel} {...chartAxis} />
              <YAxis tickFormatter={axisInr} {...chartAxis} width={52} domain={['auto', 'auto']} />
              <Tooltip {...chartTooltip} formatter={(v) => inr(v)} labelFormatter={monthLabel} />
              <Area type="monotone" dataKey="net_worth" name="Net worth" stroke="#3157c8" strokeWidth={2} fill="url(#nw)" />
            </AreaChart>
          </ResponsiveContainer>
        </div>}
      </Card>

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <Card title="What you own" subtitle={`${inr(nw.total_assets)} across ${assets.length} asset classes`}>
          <div className="flex flex-col items-center gap-4 sm:flex-row">
            <div className="h-40 w-40 shrink-0" aria-hidden>
              <ResponsiveContainer><PieChart><Pie data={assets} dataKey="value" innerRadius={46} outerRadius={72} paddingAngle={2} stroke="none">
                {assets.map((_, i) => <Cell key={i} fill={PALETTE[i % PALETTE.length]} />)}</Pie><Tooltip {...chartTooltip} formatter={(v) => inr(v)} /></PieChart></ResponsiveContainer>
            </div>
            <ul className="w-full min-w-0 flex-1 space-y-2 text-sm">
              {assets.map((x, i) => (
                <li key={x.name} className="flex items-center gap-2.5"><span className="h-2.5 w-2.5 shrink-0 rounded-sm" style={{ background: PALETTE[i % PALETTE.length] }} aria-hidden />
                  <span className="flex-1 truncate text-ink-2">{x.name}</span><span className="num font-medium">{inr(x.value)}</span></li>
              ))}
            </ul>
          </div>
        </Card>
        <Card title="What you owe" subtitle={liabs.length ? `${inr(nw.total_liabilities)} · ${pct(nw.debt_to_assets_pct)} of what you own` : 'Nothing owed'}
          action={liabs.length ? <Link to="/money?tab=debts" className="text-[13px] font-medium text-accent hover:underline">Payoff plan</Link> : null}>
          {liabs.length ? (
            <ul className="space-y-4 text-sm">
              {liabs.map((l) => (<li key={l.name}><div className="flex justify-between gap-3"><span className="text-ink-2">{l.name}</span><span className="num font-medium">{inr(l.value)}</span></div>
                <div className="mt-1.5"><Meter value={l.value} max={liabs[0].value} tone="bad" /></div></li>))}
            </ul>
          ) : <p className="py-8 text-center text-sm text-good">Debt-free. No loans or card balances.</p>}
        </Card>
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <Card title="How quickly you can reach it" subtitle="Your assets by how fast they turn into cash">
          <KV rows={[['Immediately (bank, cash)', inr(liq.immediate)], ['Within a week (FDs, debt funds)', inr(liq.within_a_week)], ['Market-linked (stocks, equity funds)', inr(liq.market_linked)], ['Locked (property, EPF/PPF, jewellery)', inr(liq.locked)]]} />
        </Card>
        <Card title="Asset mix vs an age-based guide" subtitle={al.note}>
          <div className="space-y-3">
            {Object.entries(al.allocation_pct).filter(([, v]) => v > 0).map(([k, v], i) => (
              <Meter key={k} value={v} tone="accent" label={<><span className="flex items-center gap-2"><span className="h-2 w-2 rounded-sm" style={{ background: PALETTE[i] }} aria-hidden />{k}</span><span className="num">{pct(v)} · {inr(al.allocation[k])}</span></>} />
            ))}
          </div>
          <p className="mt-4 text-[13px] text-muted">Equity is {pct(al.financial_assets_equity_pct)} of financial assets; the guide for age {a.profile.age} is about {al.suggested_equity_pct_for_age}%.</p>
        </Card>
      </div>
      <p className="mt-6 text-micro text-faint">{a.data_notice}</p>
    </>
  )
}

export function HealthSection() {
  const { analysis: a } = useFinora()
  const { health_score: hs, liquidity: liq, insurance: ins } = a
  const pillars = Object.entries(hs.pillars)
  const tone = (v) => (v == null ? 'text-faint' : v >= 65 ? 'text-good' : v >= 45 ? 'text-warn' : 'text-bad')
  return (
    <>
      <PageHeader title="Financial health" subtitle={hs.method} />
      <div className="grid gap-6 lg:grid-cols-[280px_1fr]">
        <Card>
          <div className="text-[13px] font-medium text-muted">Health score</div>
          <div className="mt-1 flex items-baseline gap-2"><span className={cx('num text-[44px] leading-none font-semibold', tone(hs.score))}>{hs.score == null ? '—' : Math.round(hs.score)}</span><span className="text-sm text-muted">/ 100</span></div>
          <div className={cx('mt-1 text-sm font-medium', tone(hs.score))}>{hs.band}</div>
          {Object.keys(hs.not_assessed || {}).length > 0 && <p className="mt-3 text-micro leading-4 text-faint">Not assessed: {Object.entries(hs.not_assessed).map(([k, v]) => `${k} (${v})`).join('; ')}. Pillars without data are left out, not scored as zero.</p>}
        </Card>
        <Card title="The pillars behind the score" subtitle="Each pillar is 0–100 against a published threshold">
          <ul className="grid gap-4 sm:grid-cols-2">
            {pillars.map(([k, v]) => (
              <li key={k}><Meter value={v ?? 0} tone={v == null ? 'info' : v >= 65 ? 'good' : v >= 45 ? 'warn' : 'bad'}
                label={<><span className="font-medium text-ink-2">{k}</span><span className={cx('num', tone(v))}>{v == null ? 'not assessed' : Math.round(v)}</span></>} /></li>
            ))}
          </ul>
        </Card>
      </div>
      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <Card title="Emergency fund" subtitle="Money you could reach quickly, measured in months of your expenses">
          <Meter value={liq.emergency_fund_months || 0} max={6} tone={(liq.emergency_fund_months || 0) >= 6 ? 'good' : (liq.emergency_fund_months || 0) >= 3 ? 'warn' : 'bad'}
            label={<><span>{inr(liq.emergency_pool)} set aside</span><span className="num">{liq.emergency_fund_months == null ? 'needs monthly expenses' : `${liq.emergency_fund_months} of 6 months`}</span></>} />
          <div className="mt-3"><KV rows={[['Runway if income stopped', liq.runway_months == null ? '—' : `${liq.runway_months} months`],
            ['Gap to 6 months', inr(liq.emergency_fund_gap), liq.emergency_fund_gap > 0 ? 'warn' : 'good']]} /></div>
        </Card>
        <Card title="Protection" subtitle="Insurance cover against the recommended amount">
          <KV rows={[['Term life cover', `${inr(ins.term_cover)} of ${inr(ins.recommended_term_cover)}`, ins.term_gap > 0 ? 'warn' : 'good'],
            ['Health cover', `${inr(ins.health_cover)} of ${inr(ins.recommended_health_cover)}`, ins.health_gap > 0 ? 'warn' : 'good']]} />
          <div className="mt-3"><Note>{ins.note}</Note></div>
        </Card>
      </div>
    </>
  )
}

export default MoneyOverview
