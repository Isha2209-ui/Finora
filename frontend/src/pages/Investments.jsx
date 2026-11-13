import { Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '../api'
import { Badge, Card, Empty, ErrorBox, Loading, Note, PageHeader, Stat, Table, chartTooltip } from '../components/ui.jsx'
import { PALETTE, dateLabel, inr, pct } from '../format'
import { useAsync, useFinora } from '../store.jsx'

export default function Investments() {
  const { analysis: a, profileId } = useFinora()
  const inv = a.investments
  const nw = a.net_worth.breakdown
  const raw = useAsync(() => api.dataSummary(profileId), [profileId])
  const sectors = inv.sector_exposure
  const others = [['Fixed deposits', nw['Fixed deposits']], ['Gold', nw['Gold']], ['Retirement (EPF/PPF/NPS)', nw['Retirement (EPF/PPF/NPS)']], ['Real estate', nw['Real estate']], ['Cash in hand', nw['Cash in hand']], ['Bank balances', nw['Bank balances']]].filter(([, v]) => v)
  const gains = inv.holdings.map((h) => ({ name: h.symbol || h.name.split(' ').slice(0, 2).join(' '), gain: h.gain_pct, full: h.name }))
  return (
    <>
      <PageHeader title="Investments & Assets" subtitle="Stocks, mutual funds, SIPs, deposits, property, gold and cash - with gains, concentration and SIP discipline." />
      <div className="grid gap-4 md:grid-cols-4">
        <Stat label="Market investments" value={inr(inv.current_value)} sub={`Invested ${inr(inv.total_invested)}`} />
        <Stat label="Total gain" value={`${inv.total_gain >= 0 ? '+' : ''}${inr(inv.total_gain)}`} tone={inv.total_gain >= 0 ? 'good' : 'bad'} sub={`${pct(inv.total_gain_pct)} absolute return`} />
        <Stat label="Monthly SIPs" value={inr(inv.sip_monthly_total)} sub={`${pct(inv.sip_to_income_pct || 0)} of income`} tone={(inv.sip_to_income_pct || 0) >= 10 ? 'good' : 'warn'} />
        <Stat label="SIPs missed (12 mo)" value={inv.sips_missed_last_12m} tone={inv.sips_missed_last_12m >= 2 ? 'bad' : 'good'} sub={`${inv.stock_count} stocks · ${inv.fund_count} funds`} />
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-3">
        <Card title="Holdings" subtitle={`Prices as of ${dateLabel(inv.prices_as_of)} (stored values, not a live feed)`} className="xl:col-span-2" pad={false}>
          <Table dense rows={inv.holdings} empty="No market investments" columns={[
            { key: 'name', label: 'Holding', render: (h) => <div><div className="font-medium">{h.name}</div><div className="text-xs text-muted">{h.type} · {h.sector} · held {h.years_held}y</div></div> },
            { key: 'invested', label: 'Invested', right: true, render: (h) => inr(h.invested) },
            { key: 'current', label: 'Current', right: true, render: (h) => inr(h.current) },
            { key: 'gain', label: 'Gain', right: true, render: (h) => <span className={h.gain >= 0 ? 'text-good' : 'text-bad'}>{h.gain >= 0 ? '+' : ''}{inr(h.gain)}</span> },
            { key: 'gain_pct', label: 'Return', right: true, render: (h) => <span className={h.gain >= 0 ? 'text-good' : 'text-bad'}>{pct(h.gain_pct)}</span> },
            { key: 'cagr_pct', label: 'CAGR', right: true, render: (h) => h.cagr_pct == null ? <span className="text-faint" title={h.note}>n/a</span> : pct(h.cagr_pct) },
          ]} />
        </Card>
        <Card title="Stock sector exposure" subtitle={inv.top_sector ? `Largest: ${inv.top_sector.sector} at ${pct(inv.top_sector.share_of_stocks_pct, 0)}` : null}>
          {sectors.length ? (<>
            <div className="h-44"><ResponsiveContainer><PieChart><Pie data={sectors} dataKey="value" nameKey="sector" innerRadius={42} outerRadius={72} paddingAngle={2} stroke="none">
              {sectors.map((_, i) => <Cell key={i} fill={PALETTE[i % PALETTE.length]} />)}</Pie><Tooltip {...chartTooltip} formatter={(v) => inr(v)} /></PieChart></ResponsiveContainer></div>
            <ul className="space-y-1 text-[13px]">{sectors.map((s, i) => <li key={s.sector} className="flex items-center gap-2"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: PALETTE[i % PALETTE.length] }} /><span className="flex-1 text-muted">{s.sector}</span><span className="num">{pct(s.share_of_stocks_pct, 0)}</span></li>)}</ul>
            {inv.top_sector && inv.top_sector.share_of_stocks_pct >= 50 && inv.stock_count >= 3 && <div className="mt-3"><Note tone="warn">More than half of the stock portfolio sits in one sector - concentration risk.</Note></div>}
          </>) : <Empty title="No direct stocks" />}
        </Card>
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        <Card title="Return by holding" subtitle="Absolute return since purchase">
          {gains.length ? <div style={{ height: Math.max(180, gains.length * 30) }}><ResponsiveContainer>
            <BarChart data={gains} layout="vertical" margin={{ left: 10, right: 20 }}><CartesianGrid horizontal={false} />
              <XAxis type="number" tickFormatter={(v) => `${v}%`} tickLine={false} axisLine={false} /><YAxis type="category" dataKey="name" width={96} tickLine={false} axisLine={false} />
              <Tooltip {...chartTooltip} formatter={(v) => `${v}%`} labelFormatter={(l, p) => p?.[0]?.payload.full || l} />
              <Bar dataKey="gain" name="Return" radius={[0, 4, 4, 0]}>{gains.map((g, i) => <Cell key={i} fill={g.gain >= 0 ? '#34d399' : '#f87171'} />)}</Bar></BarChart>
          </ResponsiveContainer></div> : <Empty />}
        </Card>
        <div className="space-y-4">
          <Card title="SIPs" pad={false}>
            <Table dense rows={inv.sips} empty="No SIPs set up" columns={[
              { key: 'scheme', label: 'Scheme', render: (s) => <span className="font-medium">{s.scheme}</span> },
              { key: 'amount', label: 'Monthly', right: true, render: (s) => inr(s.amount) },
              { key: 'sip_day', label: 'Day', right: true },
              { key: 'status', label: 'Status', render: (s) => <Badge tone={s.status === 'active' ? 'good' : 'bad'}>{s.status}</Badge> },
              { key: 'missed_last_12m', label: 'Missed (12 mo)', right: true, render: (s) => <span className={s.missed_last_12m ? 'text-bad' : 'text-good'}>{s.missed_last_12m}</span> },
            ]} />
          </Card>
          <Card title="Other assets" subtitle="Deposits, retirement accounts, gold, property and cash">
            <ul className="divide-y divide-line/60 text-sm">{others.map(([k, v]) => <li key={k} className="flex justify-between py-2"><span className="text-muted">{k}</span><span className="num font-medium">{inr(v)}</span></li>)}</ul>
            {a.goals.length > 0 && <div className="mt-4"><div className="mb-2 text-xs font-medium text-muted">Goals</div>
              {a.goals.map((g) => <div key={g.name} className="mb-2 text-sm"><div className="flex justify-between"><span>{g.name}</span><span className="num text-muted">{inr(g.current)} / {inr(g.target)}</span></div>
                <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-raised"><div className="h-full rounded-full bg-accent" style={{ width: `${Math.min(100, g.progress_pct)}%` }} /></div>
                <div className="mt-0.5 text-[11px] text-faint">needs about {inr(g.monthly_needed_at_7pct)}/month for {g.months_left} months</div></div>)}</div>}
          </Card>
        </div>
      </div>
      {raw.data && <p className="mt-4 text-xs text-faint">Records on file: {raw.data.tables.filter((t) => ['Stocks', 'Mutual funds', 'SIPs', 'Fixed deposits', 'Properties', 'Other assets'].includes(t.table)).map((t) => `${t.rows} ${t.table.toLowerCase()}`).join(' · ')}</p>}
    </>
  )
}
