import { Link } from 'react-router-dom'
import { Area, AreaChart, CartesianGrid, Cell, Pie, PieChart, PolarAngleAxis, PolarGrid, Radar, RadarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { AlertTriangle, ArrowRight, Flame, Info, Landmark, ShieldAlert, TrendingUp, Wallet } from 'lucide-react'
import { Badge, Card, KV, Meter, PageHeader, Stat, chartTooltip, cx } from '../components/ui.jsx'
import { PALETTE, axisInr, inr, monthLabel, pct } from '../format'
import { useFinora } from '../store.jsx'

export default function Identity() {
  const { analysis: a } = useFinora()
  const { net_worth: nw, cash_flow: cf, liquidity: liq, health_score: hs, allocation: al, fire, credit, debt, investments: inv, ml } = a
  const assets = Object.entries(nw.breakdown).map(([name, value]) => ({ name, value })).sort((x, y) => y.value - x.value)
  const liabs = Object.entries(nw.liabilities).map(([name, value]) => ({ name, value })).sort((x, y) => y.value - x.value)
  const pillars = Object.entries(hs.pillars).map(([k, v]) => ({ pillar: k, score: v }))
  const risk = ml.credit_risk
  return (
    <>
      <PageHeader title="Financial Identity" subtitle={`Everything ${a.profile.name.split(' ')[0]} owns and owes, in one place - across ${Object.keys(nw.breakdown).length} asset classes` + (cf.period ? `, analysed for ${cf.period.months} months (${monthLabel(cf.period.from)} – ${monthLabel(cf.period.to)}).` : '. No income or spending history yet.')} />
      {a.completeness?.missing?.length > 0 && (
        <Link to="/records" className="mb-5 flex items-center gap-2 rounded-xl border border-info/30 bg-info/10 px-3.5 py-2.5 text-sm text-info">
          <Info size={15} /> Data completeness {a.completeness.score_pct}%. Not yet provided: {a.completeness.missing.slice(0, 4).join(', ')}. Results that need them show “—”. <span className="ml-auto flex items-center gap-1">Add data <ArrowRight size={13} /></span>
        </Link>
      )}

      {a.alerts.filter((x) => x.level !== 'info').length > 0 && (
        <div className="mb-5 grid gap-2 md:grid-cols-2">
          {a.alerts.filter((x) => x.level !== 'info').slice(0, 4).map((al_) => (
            <Link to="/recommendations" key={al_.code} className={cx('flex items-start gap-2.5 rounded-xl border px-3.5 py-2.5 text-sm', al_.level === 'critical' ? 'border-bad/30 bg-bad/10' : 'border-warn/30 bg-warn/10')}>
              {al_.level === 'critical' ? <ShieldAlert size={16} className="mt-0.5 shrink-0 text-bad" /> : <AlertTriangle size={16} className="mt-0.5 shrink-0 text-warn" />}
              <div className="min-w-0"><div className="font-medium">{al_.title}</div><div className="truncate text-xs text-muted">{al_.detail}</div></div>
            </Link>
          ))}
        </div>
      )}

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <Stat label="Net worth" value={inr(nw.net_worth)} tone={nw.net_worth >= 0 ? 'ink' : 'bad'} icon={Wallet}
          sub={nw.change_over_period != null ? `${nw.change_over_period >= 0 ? '▲' : '▼'} ${inr(Math.abs(nw.change_over_period))} over 12 months` : null} />
        <Stat label="Total assets" value={inr(nw.total_assets)} icon={TrendingUp} sub={`Liabilities ${inr(nw.total_liabilities)} · ${pct(nw.debt_to_assets_pct)} of assets`} />
        <Stat label="Monthly surplus (avg)" value={inr(cf.avg_monthly_savings)} tone={cf.avg_monthly_savings == null ? 'ink' : cf.avg_monthly_savings >= 0 ? 'good' : 'bad'} icon={Landmark}
          sub={cf.avg_monthly_savings == null ? `Needs ${[!cf.income_known && 'income', !cf.spending_known && 'spending history'].filter(Boolean).join(' and ')}` : `Income ${inr(cf.avg_monthly_income)} · spend ${inr(cf.avg_monthly_expenses)} · saves ${pct(cf.avg_savings_rate_pct)}`} />
        {fire.available === false
          ? <Stat label="FIRE age (projected)" value="—" icon={Flame} sub="Needs spending history to know your yearly expenses" />
          : <Stat label="FIRE age (projected)" value={fire.fire_age ?? '75+'} tone={fire.on_track ? 'good' : 'warn'} icon={Flame}
              sub={`Target ${fire.retirement_age_target} · ${pct(fire.progress_pct)} of FIRE number · runway ${liq.runway_months ?? '—'} mo`} />}
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-3">
        <Card title="Net worth trend" subtitle="Month-end assets minus liabilities" className="xl:col-span-2">
          {nw.history.length < 2 ? <p className="py-20 text-center text-sm text-muted">A trend needs month-end history, which builds up from your statements over time.</p> : <div className="h-64">
            <ResponsiveContainer>
              <AreaChart data={nw.history} margin={{ left: 0, right: 8, top: 8 }}>
                <defs><linearGradient id="nw" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#2dd4bf" stopOpacity={0.35} /><stop offset="100%" stopColor="#2dd4bf" stopOpacity={0} /></linearGradient></defs>
                <CartesianGrid vertical={false} /><XAxis dataKey="month" tickFormatter={monthLabel} tickLine={false} axisLine={false} />
                <YAxis tickFormatter={axisInr} tickLine={false} axisLine={false} width={52} domain={['auto', 'auto']} />
                <Tooltip {...chartTooltip} formatter={(v) => inr(v)} labelFormatter={monthLabel} />
                <Area type="monotone" dataKey="net_worth" name="Net worth" stroke="#2dd4bf" strokeWidth={2} fill="url(#nw)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>}
        </Card>
        <Card title="Financial health score" subtitle={hs.method}>
          <div className="flex items-baseline gap-3"><div className={cx('num text-5xl font-semibold', hs.score == null ? 'text-faint' : hs.score >= 65 ? 'text-good' : hs.score >= 45 ? 'text-warn' : 'text-bad')}>{hs.score ?? '—'}</div><div className="text-sm text-muted">/ 100 · {hs.band}</div></div>
          {Object.keys(hs.not_assessed || {}).length > 0 && <p className="mt-1 text-xs text-faint">Not assessed: {Object.entries(hs.not_assessed).map(([k, v]) => `${k} (${v})`).join('; ')}.</p>}
          <div className="mt-1 h-48">
            <ResponsiveContainer>
              <RadarChart data={pillars} outerRadius="62%" margin={{ left: 30, right: 30 }}><PolarGrid stroke="#1f2a40" /><PolarAngleAxis dataKey="pillar" tick={{ fontSize: 10.5, fill: '#8695ad' }} />
                <Radar dataKey="score" stroke="#2dd4bf" fill="#2dd4bf" fillOpacity={0.25} /><Tooltip {...chartTooltip} /></RadarChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-3">
        <Card title="What you own" subtitle={`Total ${inr(nw.total_assets)}`}>
          <div className="flex items-center gap-3">
            <div className="h-44 w-44 shrink-0">
              <ResponsiveContainer><PieChart><Pie data={assets} dataKey="value" innerRadius={48} outerRadius={78} paddingAngle={2} stroke="none">
                {assets.map((_, i) => <Cell key={i} fill={PALETTE[i % PALETTE.length]} />)}</Pie><Tooltip {...chartTooltip} formatter={(v) => inr(v)} /></PieChart></ResponsiveContainer>
            </div>
            <ul className="min-w-0 flex-1 space-y-1.5 text-[13px]">
              {assets.map((x, i) => (
                <li key={x.name} className="flex items-center gap-2"><span className="h-2.5 w-2.5 shrink-0 rounded-sm" style={{ background: PALETTE[i % PALETTE.length] }} />
                  <span className="flex-1 truncate text-muted">{x.name}</span><span className="num">{inr(x.value)}</span></li>
              ))}
            </ul>
          </div>
        </Card>
        <Card title="What you owe" subtitle={`Total ${inr(nw.total_liabilities)}`}>
          {liabs.length ? (
            <ul className="space-y-3 text-sm">
              {liabs.map((l) => (<li key={l.name}><div className="flex justify-between"><span className="text-muted">{l.name}</span><span className="num">{inr(l.value)}</span></div>
                <div className="mt-1"><Meter value={l.value} max={liabs[0].value} tone="bad" /></div></li>))}
            </ul>
          ) : <p className="py-8 text-center text-sm text-good">Debt-free. No loans or card balances.</p>}
        </Card>
        <Card title="Liquidity" subtitle="How quickly money can be reached">
          <KV rows={[['Immediate (bank, cash)', inr(liq.immediate)], ['Within a week (FDs, debt funds)', inr(liq.within_a_week)], ['Market-linked (stocks, equity funds)', inr(liq.market_linked)], ['Locked (property, EPF/PPF, jewellery)', inr(liq.locked)]]} />
          <div className="mt-3"><Meter value={liq.emergency_fund_months || 0} max={6} tone={(liq.emergency_fund_months || 0) >= 6 ? 'good' : (liq.emergency_fund_months || 0) >= 3 ? 'warn' : 'bad'}
            label={<><span>Emergency fund</span><span className="num">{liq.emergency_fund_months == null ? 'needs monthly expenses' : `${liq.emergency_fund_months} of 6 months`}</span></>} /></div>
        </Card>
      </div>

      <div className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MiniLink to="/credit" title="Credit" value={credit.has_cards ? pct(credit.overall_utilisation_pct, 0) : 'No cards'} sub={credit.has_cards ? `utilisation · default risk ${risk?.overall_default_probability_pct ?? '—'}% (${risk?.overall_risk_band ?? '—'})` : 'Nothing to report'}
          tone={!credit.has_cards ? 'neutral' : credit.overall_utilisation_pct < 30 ? 'good' : credit.overall_utilisation_pct < 50 ? 'warn' : 'bad'} />
        <MiniLink to="/credit" title="Debt load" value={pct(debt.emi_to_income_pct, 0)} sub={debt.risk_band === 'unknown' ? 'EMI share needs your income' : `of income goes to EMIs · ${debt.risk_band}`} tone={{ none: 'good', low: 'good', moderate: 'warn', high: 'bad', 'very high': 'bad' }[debt.risk_band]} />
        <MiniLink to="/investments" title="Investments" value={inr(inv.current_value)} sub={inv.total_gain_pct == null ? `No holdings recorded · SIPs ${inr(inv.sip_monthly_total)}/mo` : `${inv.total_gain >= 0 ? '+' : ''}${pct(inv.total_gain_pct)} overall · SIPs ${inr(inv.sip_monthly_total)}/mo`} tone={inv.total_gain >= 0 ? 'good' : 'bad'} />
        <MiniLink to="/transactions" title="Unusual transactions" value={ml.anomaly?.available === false ? '—' : (ml.anomaly?.flagged_count ?? 0)} sub={ml.anomaly?.available === false ? 'awaiting an approved model' : `flagged of ${ml.anomaly?.transactions_scored ?? 0} scored`} tone={(ml.anomaly?.flagged?.some((f) => f.severity === 'high')) ? 'warn' : 'good'} />
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        <Card title="Asset allocation vs age-based guide" subtitle={al.note}>
          <div className="space-y-2.5">
            {Object.entries(al.allocation_pct).filter(([, v]) => v > 0).map(([k, v], i) => (
              <Meter key={k} value={v} tone="accent" label={<><span className="flex items-center gap-2"><span className="h-2 w-2 rounded-sm" style={{ background: PALETTE[i] }} />{k}</span><span className="num">{pct(v)} · {inr(al.allocation[k])}</span></>} />
            ))}
          </div>
          <div className="mt-3 flex items-center gap-2 text-xs text-muted"><Info size={13} /> Equity is {pct(al.financial_assets_equity_pct)} of financial assets; the guide for age {a.profile.age} is about {al.suggested_equity_pct_for_age}%.</div>
        </Card>
        <Card title="Top priorities" action={<Link to="/recommendations" className="flex items-center gap-1 text-xs text-accent">All {a.recommendations.length} <ArrowRight size={12} /></Link>}>
          <ul className="space-y-2.5">
            {a.recommendations.length === 0 && <li className="text-sm text-muted">No recommendations yet - most checks need income and spending history.</li>}
            {a.recommendations.slice(0, 4).map((r) => (
              <li key={r.code} className="flex items-start gap-2.5 text-sm"><Badge tone={r.priority}>{r.priority}</Badge>
                <div className="min-w-0"><div className="font-medium">{r.finding}</div><div className="text-xs text-muted">{r.action}</div></div></li>
            ))}
          </ul>
        </Card>
      </div>
      <p className="mt-4 text-xs text-faint">{a.data_notice}</p>
    </>
  )
}

function MiniLink({ to, title, value, sub, tone }) {
  const c = { good: 'text-good', warn: 'text-warn', bad: 'text-bad', neutral: 'text-ink' }[tone] || 'text-ink'
  return (
    <Link to={to} className="group rounded-2xl border border-line bg-surface p-4 hover:border-accent/40">
      <div className="flex items-center justify-between text-xs text-muted"><span>{title}</span><ArrowRight size={13} className="opacity-0 transition group-hover:opacity-100" /></div>
      <div className={cx('num mt-1.5 text-2xl font-semibold', c)}>{value}</div><div className="mt-1 text-xs text-muted">{sub}</div>
    </Link>
  )
}
