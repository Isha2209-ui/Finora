import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowDownRight, ArrowUpRight, CalendarClock, Plus } from 'lucide-react'
import { Bar, BarChart, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '../api'
import { Badge, Card, Empty, ErrorBox, Field, Loading, Note, Segmented, Select, Stat, Table, chartTooltip, cx, useUrlParam } from '../components/ui.jsx'
import { BudgetSection } from './Budget.jsx'
import { PALETTE, axisInr, dateLabel, inr, monthLabel, num, pct } from '../format'
import { useAsync, useFinora } from '../store.jsx'

const KIND_TONE = { bill: 'info', subscription: 'accent', loan: 'warn', investment: 'good', 'regular spend': 'neutral' }
const FREQ = { monthly: 'monthly', quarterly: 'quarterly', yearly: 'yearly' }

const VIEWS = [
  { id: 'where', label: 'Where it goes' }, { id: 'changed', label: 'What changed' }, { id: 'repeats', label: 'What repeats' },
  { id: 'merchants', label: 'Who I pay' }, { id: 'income', label: 'Income' }, { id: 'investing', label: 'Investing' },
  { id: 'unusual', label: 'Unusual spending' }, { id: 'budget', label: 'Budget' },
]

/** Money → Spending (was "Statement Intelligence"): one question at a time, real data from /insights, filters in the URL. */
export function SpendingSection() {
  const { profileId, profile } = useFinora()
  const [view, setView] = useUrlParam('view', VIEWS.map((v) => v.id))
  const [months, setMonths] = useUrlParam('months', null, '')
  const [source, setSource] = useUrlParam('source', null, '')
  const params = { months, ...(source.startsWith('account:') ? { account_id: source.split(':')[1] } : source.startsWith('card:') ? { card_id: source.split(':')[1] } : {}) }
  const q = useAsync(() => api.insights(profileId, params), [profileId, months, source])
  const i = q.data
  const readOnly = profile?.kind === 'template'
  return (
    <>
      <div className="mb-5 flex flex-wrap items-end gap-3">
        <div className="w-full sm:w-60"><Field label="Account or card"><Select value={source} onChange={(e) => setSource(e.target.value || null)}>
          <option value="">All accounts & cards</option>
          {i?.filters?.accounts.map((a) => <option key={a.id} value={`account:${a.id}`}>{a.label}</option>)}
          {i?.filters?.cards.map((c) => <option key={c.id} value={`card:${c.id}`}>{c.label}</option>)}
        </Select></Field></div>
        <div className="w-full sm:w-44"><Field label="Period"><Select value={months} onChange={(e) => setMonths(e.target.value || null)}>
          <option value="">Whole history</option><option value="24">Last 24 months</option><option value="12">Last 12 months</option><option value="6">Last 6 months</option><option value="3">Last 3 months</option>
        </Select></Field></div>
        <div className="flex-1" />
        {!readOnly && <Link to="/data?tab=import" className="inline-flex h-10 items-center rounded-md border border-control/60 bg-bg px-4 text-sm font-medium text-ink shadow-xs hover:bg-subtle">Import statements</Link>}
      </div>
      {q.loading && !i ? <Loading label="Reading every transaction…" /> : q.error ? <ErrorBox message={q.error} onRetry={q.reload} />
        : !i.available ? <Card><Empty title="No transactions yet" action={!readOnly && <Link className="text-sm font-medium text-accent hover:underline" to="/data?tab=import">Import a statement</Link>}>{i.reason}</Empty></Card>
          : (
            <div className={cx('transition-opacity', q.loading && 'opacity-60')} aria-busy={q.loading}>
              <Coverage i={i} />
              <Kpis i={i} />
              <div className="mt-8 mb-5"><Segmented label="Spending question" options={VIEWS} value={view} onChange={setView} /></div>
              {view === 'where' && <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]"><Where w={i.where} /><Trend t={i.trend} /></div>}
              {view === 'changed' && <Changes c={i.changes} />}
              {view === 'repeats' && <Recurring r={i.recurring} profileId={profileId} readOnly={readOnly} />}
              {view === 'merchants' && <Merchants m={i.merchants} />}
              {view === 'income' && <Income inc={i.income} />}
              {view === 'investing' && <Investments inv={i.investments} />}
              {view === 'unusual' && <Unusual u={i.unusual} />}
              {view === 'budget' && <BudgetSection />}
              {i.notes.length > 0 && <div className="mt-6 space-y-2">{i.notes.map((n) => <Note key={n}>{n}</Note>)}</div>}
            </div>
          )}
    </>
  )
}
export default SpendingSection

function Coverage({ i }) {
  const cov = i.coverage
  return (
    <div className="mb-5 flex flex-wrap items-center gap-2 text-[13px] text-muted">
      <Badge>{dateLabel(cov.from)} – {dateLabel(cov.to)}</Badge><Badge>{cov.months} months</Badge>
      <Badge>{num(cov.transactions)} transactions</Badge>
      {cov.imported_transactions > 0 && <Badge tone="accent">{num(cov.imported_transactions)} imported</Badge>}
      <Badge tone="accent">{num(cov.categorised_by_model)} categorised by the ML model</Badge>
      {cov.corrected_by_you > 0 && <Badge tone="good">{num(cov.corrected_by_you)} corrected by you</Badge>}
      {i.review.needs_review > 0 && <Link to="/data?tab=review"><Badge tone="warn">{num(i.review.needs_review)} need review →</Badge></Link>}
      {cov.partial_months.length > 0 && <span className="text-faint">Partial months: {cov.partial_months.map(monthLabel).join(', ')}</span>}
    </div>
  )
}

function Kpis({ i }) {
  const w = i.where, inc = i.income
  const saved = inc && w ? inc.avg_monthly - w.avg_monthly_spend : null
  return (
    <div className="grid gap-4 sm:grid-cols-3">
      <Stat label="Spent per month" value={inr(w?.avg_monthly_spend)} sub={w ? `${inr(w.total_spend)} in total · ${inr(w.refunds)} refunded` : 'no spending data'} />
      <Stat label="Income per month" value={inr(inc?.avg_monthly)} sub={inc ? `${inc.sources.length} source${inc.sources.length === 1 ? '' : 's'} · salary ${pct(inc.salary_share_pct, 0)}` : 'no income records here'} />
      <Stat label="Kept per month" value={saved == null ? '—' : inr(saved)} tone={saved == null ? 'ink' : saved >= 0 ? 'good' : 'bad'} sub={saved == null ? 'needs income and spending' : `${pct(saved / inc.avg_monthly * 100, 0)} of income`} />
    </div>
  )
}

function Where({ w }) {
  if (!w) return <Card title="Where your money goes"><Empty title="No spending yet" /></Card>
  const max = w.categories[0]?.total || 1
  return (
    <Card title="Where your money goes" subtitle={`${inr(w.total_spend)} spent · average ${inr(w.avg_monthly_spend)} a month`}>
      <div className="mb-3 flex h-3 overflow-hidden rounded-full">{w.groups.map((g, k) => <div key={g.group} title={`${g.group} ${pct(g.share_pct, 0)}`} style={{ width: `${g.share_pct}%`, background: PALETTE[k] }} />)}</div>
      <div className="mb-3 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-muted">{w.groups.map((g, k) => <span key={g.group} className="flex items-center gap-1"><span className="h-2 w-2 rounded-sm" style={{ background: PALETTE[k] }} />{g.group} {pct(g.share_pct, 0)}</span>)}</div>
      <ul className="max-h-[300px] space-y-2 overflow-y-auto pr-1">{w.categories.map((c) => (
        <li key={c.category}>
          <div className="flex justify-between text-[13px]"><span>{c.category} <span className="text-[11px] text-faint">{c.kind === 'lifestyle' ? 'lifestyle' : c.kind === 'essential' ? 'essential' : ''}</span></span>
            <span className="num">{inr(c.per_month)}<span className="text-faint">/mo</span> <span className="ml-1 text-faint">{pct(c.share_pct, 0)}</span></span></div>
          <div className="mt-1 h-1.5 rounded-full bg-raised"><div className="h-full rounded-full bg-accent/70" style={{ width: `${(c.total / max) * 100}%` }} /></div>
        </li>))}</ul>
    </Card>
  )
}

function Trend({ t, className }) {
  const hasIncome = t.months.some((m) => m.income != null)
  return (
    <Card className={className} title="How spending changes over time" subtitle={hasIncome ? 'Monthly spending by category, with income for comparison' : 'Monthly spending by category'}>
      <div className="h-80"><ResponsiveContainer><ComposedChart data={t.months} margin={{ left: 0, right: 8, top: 8 }}>
        <CartesianGrid vertical={false} /><XAxis dataKey="month" tickFormatter={monthLabel} tickLine={false} axisLine={false} minTickGap={16} />
        <YAxis tickFormatter={axisInr} tickLine={false} axisLine={false} width={52} />
        <Tooltip {...chartTooltip} labelFormatter={monthLabel} formatter={(v, n) => [inr(v), n]} />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        {t.series.map((s, k) => <Bar key={s} dataKey={s} stackId="s" fill={PALETTE[k % PALETTE.length]} />)}
        {hasIncome && <Line dataKey="income" name="Income" stroke="#1d2433" strokeWidth={2} dot={false} strokeDasharray="4 3" />}
      </ComposedChart></ResponsiveContainer></div>
    </Card>
  )
}

function Changes({ c }) {
  if (!c?.available) return <Card title="What changed"><Empty title="Not enough history">{c?.reason}</Empty></Card>
  const d = c.total_recent_per_month - c.total_before_per_month
  return (
    <Card title="What changed" subtitle={`Average per month: ${c.recent.map(monthLabel).join(', ')} vs ${c.before.map(monthLabel).join(', ')}`}>
      <div className="mb-3 flex items-baseline gap-2"><span className="num text-2xl font-semibold">{inr(c.total_recent_per_month)}</span>
        <span className={cx('num flex items-center text-sm', d > 0 ? 'text-bad' : 'text-good')}>{d > 0 ? <ArrowUpRight size={15} /> : <ArrowDownRight size={15} />}{inr(Math.abs(d))} a month</span>
        <span className="text-xs text-muted">vs {inr(c.total_before_per_month)}</span></div>
      <ul className="space-y-1.5 text-[13px]">{c.categories.slice(0, 9).map((r) => (
        <li key={r.category} className="flex items-center gap-2"><span className="flex-1">{r.category}</span>
          <span className="num text-faint">{inr(r.before_per_month)} →</span><span className="num w-20 text-right">{inr(r.recent_per_month)}</span>
          <span className={cx('num w-24 text-right text-xs', r.change > 0 ? 'text-bad' : 'text-good')}>{r.change > 0 ? '+' : '−'}{inr(Math.abs(r.change))}{r.change_pct != null ? ` (${r.change_pct > 0 ? '+' : ''}${Math.round(r.change_pct)}%)` : ''}</span></li>))}</ul>
      {c.year_over_year && <p className="mt-3 text-xs text-muted">{monthLabel(c.year_over_year.month)}: {inr(c.year_over_year.spend)} spent vs {inr(c.year_over_year.spend_year_ago)} in {monthLabel(c.year_over_year.compared_with)}.</p>}
    </Card>
  )
}

function Merchants({ m }) {
  if (!m.length) return <Card title="Largest merchants"><Empty /></Card>
  const max = m[0].total
  return (
    <Card title="Largest merchants" subtitle="Who receives the most of your spending (transfers, card bills and investments excluded)" pad={false}>
      <Table dense rows={m} columns={[
        { key: 'merchant', label: 'Merchant', render: (r) => <div><div className="font-medium">{r.merchant}</div><div className="mt-0.5 h-1 w-full rounded-full bg-raised"><div className="h-full rounded-full bg-accent/60" style={{ width: `${(r.total / max) * 100}%` }} /></div></div> },
        { key: 'category', label: 'Category', render: (r) => <Badge>{r.category}</Badge> },
        { key: 'count', label: 'Times', right: true, render: (r) => num(r.count) },
        { key: 'avg_ticket', label: 'Typical', right: true, render: (r) => inr(r.avg_ticket) },
        { key: 'total', label: 'Total', right: true, render: (r) => <span className="font-medium">{inr(r.total)}</span> },
        { key: 'share_pct', label: 'Share', right: true, render: (r) => pct(r.share_pct, 0) }]} />
    </Card>
  )
}

function Recurring({ r, profileId, readOnly }) {
  const [added, setAdded] = useState({})
  const [err, setErr] = useState(null)
  const add = async (it) => {
    setErr(null)
    const freq = FREQ[it.cadence]
    try {
      await api.createRecord(profileId, 'recurring', { name: it.merchant.slice(0, 80), category: it.category, amount: freq ? it.typical_amount : it.monthly_equivalent,
        frequency: freq || 'monthly', day_of_month: Math.min(28, Number(it.last_date.slice(8, 10))) })
      setAdded({ ...added, [it.merchant]: true })
    } catch (e) { setErr(e.message) }
  }
  return (
    <Card title="Recurring commitments" subtitle="Payments that repeat at a steady interval and a steady amount: rent, EMIs, SIPs, bills and subscriptions" pad={false}
      action={<div className="flex flex-wrap gap-1.5 pr-1">{Object.entries(r.by_kind || {}).map(([k, v]) => <Badge key={k} tone={KIND_TONE[k]}>{k} {inr(v)}/mo</Badge>)}</div>}>
      {err && <div className="px-5"><Note tone="warn">{err}</Note></div>}
      {r.items.length ? <Table dense rows={r.items} rowClass={(x) => x.status === 'stopped' && 'opacity-55'} columns={[
        { key: 'merchant', label: 'Paid to', render: (x) => <span className="font-medium">{x.merchant}</span> },
        { key: 'kind', label: 'Kind', render: (x) => <Badge tone={KIND_TONE[x.kind]}>{x.kind}</Badge> },
        { key: 'cadence', label: 'Every', render: (x) => x.cadence },
        { key: 'typical_amount', label: 'Amount', right: true, render: (x) => inr(x.typical_amount) },
        { key: 'monthly_equivalent', label: 'Per month', right: true, render: (x) => inr(x.monthly_equivalent) },
        { key: 'occurrences', label: 'Seen', right: true, render: (x) => `${x.occurrences}×` },
        { key: 'next', label: 'Next expected', render: (x) => x.status === 'active' ? <span className="flex items-center gap-1"><CalendarClock size={12} className="text-faint" />{dateLabel(x.next_expected)}</span> : <span className="text-faint">stopped {dateLabel(x.last_date)}</span> },
        { key: 'x', label: '', render: (x) => x.already_recorded || added[x.merchant] ? <span className="text-[13px] text-good">In your records</span>
          : !readOnly && x.status === 'active' && <button type="button" onClick={() => add(x)} className="flex items-center gap-1 text-[13px] text-accent hover:underline"><Plus size={13} aria-hidden />Add to my records</button> }]} />
        : <p className="px-5 pb-4 text-sm text-muted">No repeating payments found yet. They need at least three occurrences at a steady interval.</p>}
    </Card>
  )
}

function Income({ inc }) {
  if (!inc) return <Card title="Income patterns"><Empty title="No income records">Income comes from salary and other credits Finora recognises in statements, or from income you add under Data → Records.</Empty></Card>
  const s = inc.salary
  return (
    <Card title="Income patterns" subtitle={`${inr(inc.total)} received · ${inr(inc.avg_monthly)} a month on average`}>
      {s && (
        <div className="mb-3 grid grid-cols-3 gap-2 text-center">
          <div className="rounded-xl bg-raised/50 p-2"><div className="text-[11px] text-muted">Salary arrived</div><div className="num font-semibold">{s.months_received} of {s.months_covered} months</div></div>
          <div className="rounded-xl bg-raised/50 p-2"><div className="text-[11px] text-muted">Usually on</div><div className="num font-semibold">day {s.typical_day}</div></div>
          <div className="rounded-xl bg-raised/50 p-2"><div className="text-[11px] text-muted">Latest ({monthLabel(s.latest_month)})</div><div className="num font-semibold">{inr(s.latest_monthly)}</div></div>
        </div>
      )}
      <div className="h-48"><ResponsiveContainer><BarChart data={inc.months} margin={{ left: 0, right: 8 }}>
        <CartesianGrid vertical={false} /><XAxis dataKey="month" tickFormatter={monthLabel} tickLine={false} axisLine={false} minTickGap={16} />
        <YAxis tickFormatter={axisInr} tickLine={false} axisLine={false} width={52} /><Tooltip {...chartTooltip} labelFormatter={monthLabel} formatter={(v, n) => [inr(v), n]} />
        {inc.sources.map((x, k) => <Bar key={x.source} dataKey={x.source} stackId="i" fill={PALETTE[(k + 1) % PALETTE.length]} />)}
      </BarChart></ResponsiveContainer></div>
      <ul className="mt-2 space-y-1 text-[13px]">{inc.sources.map((x, k) => <li key={x.source} className="flex items-center gap-2"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: PALETTE[(k + 1) % PALETTE.length] }} /><span className="flex-1">{x.source}</span><span className="num text-faint">{x.count}×</span><span className="num w-24 text-right">{inr(x.total)}</span><span className="num w-10 text-right text-faint">{pct(x.share_pct, 0)}</span></li>)}</ul>
      {s?.changes?.length > 0 && <div className="mt-3 space-y-1">{s.changes.map((c) => <Note key={c.month} tone={c.change_pct > 0 ? 'info' : 'warn'}>Salary changed in {monthLabel(c.month)}: {inr(c.from)} → {inr(c.to)} ({c.change_pct > 0 ? '+' : ''}{c.change_pct}%).</Note>)}</div>}
    </Card>
  )
}

function Investments({ inv }) {
  if (!inv) return <Card title="Investment cash flows"><Empty /></Card>
  const any = inv.total_invested > 0 || inv.total_withdrawn > 0
  return (
    <Card title="Investment cash flows" subtitle="Money moved into and out of investments, as seen in your transactions">
      <div className="mb-3 grid grid-cols-3 gap-2 text-center">
        <div className="rounded-xl bg-raised/50 p-2"><div className="text-[11px] text-muted">Put in</div><div className="num font-semibold text-good">{inr(inv.total_invested)}</div></div>
        <div className="rounded-xl bg-raised/50 p-2"><div className="text-[11px] text-muted">Taken out</div><div className="num font-semibold">{inr(inv.total_withdrawn)}</div></div>
        <div className="rounded-xl bg-raised/50 p-2"><div className="text-[11px] text-muted">EMIs paid</div><div className="num font-semibold text-warn">{inr(inv.emi_paid)}</div></div>
      </div>
      {any ? <div className="h-40"><ResponsiveContainer><BarChart data={inv.months} margin={{ left: 0, right: 8 }}>
        <CartesianGrid vertical={false} /><XAxis dataKey="month" tickFormatter={monthLabel} tickLine={false} axisLine={false} minTickGap={16} />
        <YAxis tickFormatter={axisInr} tickLine={false} axisLine={false} width={52} /><Tooltip {...chartTooltip} labelFormatter={monthLabel} formatter={(v, n) => [inr(v), n]} />
        <Bar dataKey="invested" name="Invested" fill="#13794a" /><Bar dataKey="withdrawn" name="Withdrawn" fill="#0e8074" />
      </BarChart></ResponsiveContainer></div> : <p className="text-sm text-muted">No investment transactions in this period.</p>}
      {inv.destinations.length > 0 && <ul className="mt-2 space-y-1 text-[13px]">{inv.destinations.map((d) => <li key={d.name} className="flex justify-between"><span>{d.name}</span><span className="num">{inr(d.total)} <span className="text-faint">· {d.count}×</span></span></li>)}</ul>}
      <div className="mt-3"><Note>{inv.note} {inv.recorded_sips ? `You have ${inv.recorded_sips} SIP(s) recorded (${inr(inv.recorded_sip_monthly)} a month).` : ''}</Note></div>
    </Card>
  )
}

function Unusual({ u }) {
  if (!u) return null
  const none = !u.months.length && !u.category_spikes.length && !u.large_one_offs.length
  return (
    <Card title="Unusual spending" subtitle="Statistically unusual for you, compared with your own history." action={<Link to="/money?tab=transactions" className="text-xs text-accent hover:underline">Anomaly model by transaction →</Link>}>
      {none ? <p className="text-sm text-good">Nothing stands out in this period.</p> : (
        <div className="grid gap-4 md:grid-cols-3">
          <div><div className="mb-1 text-xs font-medium text-muted">Expensive months</div>{u.months.length ? u.months.map((m) => <div key={m.month} className="text-[13px]">{monthLabel(m.month)}: <b className="num">{inr(m.spend)}</b> <span className="text-faint">vs typical {inr(m.typical)}</span></div>) : <p className="text-xs text-faint">None</p>}</div>
          <div><div className="mb-1 text-xs font-medium text-muted">Categories above their usual (latest month)</div>{u.category_spikes.length ? u.category_spikes.map((s) => <div key={s.category} className="text-[13px]">{s.category}: <b className="num">{inr(s.spend)}</b> <span className="text-faint">vs {inr(s.usual)}{s.times_usual ? ` (${s.times_usual}×)` : ''}</span></div>) : <p className="text-xs text-faint">None</p>}</div>
          <div><div className="mb-1 text-xs font-medium text-muted">Large one-off purchases</div>{u.large_one_offs.length ? u.large_one_offs.slice(0, 6).map((x, k) => <div key={k} className="truncate text-[13px]" title={x.description}>{dateLabel(x.date)} · <b className="num">{inr(x.amount)}</b> <span className="text-faint">{x.category}</span></div>) : <p className="text-xs text-faint">None</p>}</div>
        </div>
      )}
      <p className="mt-3 text-[11px] text-faint">{u.method}</p>
    </Card>
  )
}
