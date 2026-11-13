import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { CreditCard, Landmark } from 'lucide-react'
import { api } from '../api'
import { Badge, Card, Empty, ErrorBox, Loading, Meter, PageHeader, Stat, Table, chartTooltip } from '../components/ui.jsx'
import { axisInr, inr, monthLabel, pct } from '../format'
import { useAsync, useFinora } from '../store.jsx'

const STATUS = (s) => s === -2 ? ['no use', 'neutral'] : s === -1 ? ['paid in full', 'good'] : s === 0 ? ['part paid', 'warn'] : [`${s} mo late`, 'bad']
const band = { healthy: 'good', elevated: 'warn', high: 'bad', critical: 'bad' }

export default function Accounts() {
  const { profileId } = useFinora()
  const { data, loading, error, reload } = useAsync(() => api.accounts(profileId), [profileId])
  if (loading) return <Loading full />
  if (error) return <ErrorBox message={error} onRetry={reload} />
  const { accounts, cards, credit_summary: cs, spend_by_source: src, credit_risk: risk } = data
  const bank = accounts.reduce((s, a) => s + a.balance, 0)
  return (
    <>
      <PageHeader title="Accounts & Cards" subtitle="Every bank account and credit card, analysed together and individually." />
      <div className="grid gap-4 md:grid-cols-4">
        <Stat label="Bank accounts" value={accounts.length} sub={`Total balance ${inr(bank)}`} icon={Landmark} />
        <Stat label="Credit cards" value={cards.length} sub={cards.length ? `Total limit ${inr(cs.total_limit)}` : 'None on file'} icon={CreditCard} />
        <Stat label="Card outstanding" value={inr(cs.total_outstanding || 0)} tone={(cs.overall_utilisation_pct || 0) >= 50 ? 'bad' : 'ink'} sub={cards.length ? `${pct(cs.overall_utilisation_pct, 0)} utilisation overall` : '—'} />
        <Stat label="Interest on card balances" value={inr(cs.est_interest_per_month || 0)} tone={(cs.est_interest_per_month || 0) > 500 ? 'bad' : 'good'} sub="estimated per month" />
      </div>

      <Card title="Bank accounts" className="mt-4" pad={false}>
        <Table rows={accounts} columns={[
          { key: 'bank_name', label: 'Bank', render: (a) => <span className="font-medium">{a.bank_name} {a.is_primary && <Badge tone="accent" className="ml-1">primary</Badge>}</span> },
          { key: 'account_type', label: 'Type', render: (a) => <span className="capitalize text-muted">{a.account_type}</span> },
          { key: 'account_masked', label: 'Account', render: (a) => <span className="num font-mono text-muted">{a.account_masked}</span> },
          { key: 'interest_rate', label: 'Interest', right: true, render: (a) => pct(a.interest_rate) },
          { key: 'transactions', label: 'Transactions', right: true },
          { key: 'balance', label: 'Balance', right: true, render: (a) => <span className="font-medium">{inr(a.balance, { compact: false })}</span> },
        ]} />
      </Card>

      <h2 className="mt-6 mb-3 text-sm font-semibold">Credit cards</h2>
      {cards.length === 0 ? <Card><Empty title="No credit cards on this profile" /></Card> : (
        <div className="grid gap-4 xl:grid-cols-2">
          {cards.map((c) => {
            const r = risk?.cards?.find((x) => x.last4 === c.last4)
            return (
              <Card key={c.last4} title={`${c.card} ••${c.last4}`} subtitle={`Limit ${inr(c.limit)} · APR ${c.apr_pct}% · bill due on day ${c.due_day}`}
                action={<Badge tone={band[c.utilisation_band]}>{c.utilisation_band}</Badge>}>
                <Meter value={c.utilisation_pct} tone={band[c.utilisation_band]} label={<><span>Outstanding {inr(c.outstanding, { compact: false })}</span><span className="num">{pct(c.utilisation_pct, 0)} used</span></>} />
                <div className="mt-3 grid grid-cols-3 gap-3 text-center text-xs">
                  <div className="rounded-xl bg-raised p-2"><div className="text-muted">Minimum due</div><div className="num mt-0.5 text-sm font-medium">{inr(c.min_due)}</div></div>
                  <div className="rounded-xl bg-raised p-2"><div className="text-muted">Interest / month</div><div className="num mt-0.5 text-sm font-medium">{inr(c.est_interest_per_month)}</div></div>
                  <div className="rounded-xl bg-raised p-2"><div className="text-muted">Default risk</div><div className={`num mt-0.5 text-sm font-medium ${r && r.default_probability_pct >= 30 ? 'text-bad' : 'text-good'}`}>{r ? `${r.default_probability_pct}%` : '—'}</div></div>
                </div>
                <div className="mt-3 h-36">
                  <ResponsiveContainer>
                    <BarChart data={c.statements} margin={{ left: 0, right: 4 }}>
                      <CartesianGrid vertical={false} /><XAxis dataKey="month" tickFormatter={monthLabel} tickLine={false} axisLine={false} interval={1} />
                      <YAxis tickFormatter={axisInr} tickLine={false} axisLine={false} width={44} />
                      <Tooltip {...chartTooltip} labelFormatter={monthLabel} formatter={(v, n) => [inr(v), n]} />
                      <Bar dataKey="bill" name="Statement balance" fill="#334155" radius={[3, 3, 0, 0]} />
                      <Bar dataKey="paid" name="Paid" radius={[3, 3, 0, 0]}>{c.statements.map((s, i) => <Cell key={i} fill={s.status > 0 ? '#f87171' : s.status === 0 ? '#fbbf24' : '#34d399'} />)}</Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {c.statements.slice(-6).map((s) => { const [t, tone] = STATUS(s.status); return <Badge key={s.month} tone={tone}>{monthLabel(s.month)}: {t}</Badge> })}
                </div>
              </Card>
            )
          })}
        </div>
      )}

      <Card title="Where the spending happens" subtitle="Average monthly spend by account and card (transfers, card bill payments and investments excluded)" className="mt-4">
        <div className="space-y-2.5">
          {src.map((s) => <Meter key={s.source} value={s.monthly_avg} max={src[0].monthly_avg} tone={s.kind === 'card' ? 'info' : 'accent'}
            label={<><span className="flex items-center gap-2">{s.kind === 'card' ? <CreditCard size={12} /> : <Landmark size={12} />}{s.source}</span><span className="num">{inr(s.monthly_avg)}/mo</span></>} />)}
        </div>
      </Card>
    </>
  )
}
