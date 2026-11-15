// Money → Accounts & cards. Answer first ("how much do I have, what do I owe on cards"), then two calm lists.
// Per-card detail (statements chart, payment history, model risk) lives in a drawer. Data: GET /profiles/{id}/accounts.
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { ArrowRight, CreditCard, Landmark, Pencil } from 'lucide-react'
import { api } from '../api'
import { Answer, Badge, Drawer, Empty, ErrorBox, Facts, KV, List, Loading, Meter, PageHeader, Row, Section, chartAxis, chartTooltip, cx } from '../components/ui.jsx'
import { axisInr, inr, monthLabel, pct } from '../format'
import { useAsync, useFinora } from '../store.jsx'

const STATUS = (s) => s === -2 ? ['no use', 'neutral'] : s === -1 ? ['paid in full', 'good'] : s === 0 ? ['part paid', 'warn'] : [`${s} mo late`, 'bad']
const band = { healthy: 'good', elevated: 'warn', high: 'bad', critical: 'bad' }
const Mark = ({ icon: I, tone = 'accent' }) => <span className={cx('grid h-10 w-10 shrink-0 place-items-center rounded-full', tone === 'accent' ? 'bg-accent-soft text-accent' : 'bg-subtle text-ink-2')}><I size={18} aria-hidden /></span>

export default function Accounts() {
  const { profileId, profile } = useFinora()
  const { data, loading, error, reload } = useAsync(() => api.accounts(profileId), [profileId])
  const [acct, setAcct] = useState(null)
  const [card, setCard] = useState(null)
  if (loading) return <Loading label="Loading accounts…" />
  if (error) return <ErrorBox message={error} onRetry={reload} />
  const { accounts, cards, credit_summary: cs, spend_by_source: src, credit_risk: risk } = data
  const bank = accounts.reduce((s, a) => s + a.balance, 0)
  const readOnly = profile?.kind === 'template'
  if (!accounts.length && !cards.length) return (
    <Empty title="No accounts or cards yet" action={!readOnly && <Link to="/data?tab=records&type=bank_accounts" className="text-sm font-medium text-accent hover:underline">Add a bank account</Link>}>
      Add your bank accounts and cards, or import a statement, and they appear here with their balances.</Empty>
  )
  const top = src?.[0]
  return (
    <>
      <PageHeader title="Accounts & cards" />
      <Answer eyebrow="Your accounts and cards"
        sub={cards.length ? `Card interest is about ${inr(cs.est_interest_per_month || 0)} a month${(cs.est_interest_per_month || 0) === 0 ? ', because you pay in full' : ''}.` : 'No credit cards on file.'}>
        You have <b>{inr(bank)}</b> across {accounts.length} bank account{accounts.length === 1 ? '' : 's'}
        {cards.length ? <>, and owe <b>{inr(cs.total_outstanding || 0)}</b> on {cards.length} card{cards.length === 1 ? '' : 's'} ({pct(cs.overall_utilisation_pct, 0)} of the limit).</> : '.'}
      </Answer>

      <Section title="Bank accounts" description="Select an account for its details and transactions.">
        <List>
          {accounts.map((a) => (
            <Row key={a.id} onClick={() => setAcct(a)} lead={<Mark icon={Landmark} />}
              title={<>{a.bank_name} {a.is_primary && <Badge tone="accent" className="ml-1.5 align-middle">primary</Badge>}</>}
              subtitle={`${a.account_type ? a.account_type[0].toUpperCase() + a.account_type.slice(1) : 'Account'} · ${a.account_masked} · ${pct(a.interest_rate)} interest`}
              value={inr(a.balance, { compact: false })} valueSub={`${a.transactions} transactions`} />
          ))}
        </List>
      </Section>

      <Section title="Credit cards" description={cards.length ? 'How much of each limit you use, and how you have been paying.' : undefined}>
        {cards.length === 0 ? <p className="text-sm text-muted">No credit cards on this profile.</p> : (
          <List>
            {cards.map((c) => (
              <Row key={c.last4} onClick={() => setCard(c)} lead={<Mark icon={CreditCard} tone="neutral" />} title={`${c.card} ••${c.last4}`}
                subtitle={`Limit ${inr(c.limit)} · bill due on day ${c.due_day}`} value={inr(c.outstanding, { compact: false })} valueSub="outstanding">
                <span className="hidden w-40 sm:block"><Meter value={c.utilisation_pct} tone={band[c.utilisation_band]} label={<><span>{pct(c.utilisation_pct, 0)} used</span><Badge tone={band[c.utilisation_band]}>{c.utilisation_band}</Badge></>} /></span>
              </Row>
            ))}
          </List>
        )}
      </Section>

      {src?.length > 0 && (
        <Section title="Where your spending happens" description="Average monthly spend by account and card. Transfers, card bills and investments are excluded.">
          {top && <p className="mb-4 text-sm text-ink-2">Most of it goes through <b className="font-semibold">{top.source}</b> ({inr(top.monthly_avg)} a month).</p>}
          <div className="max-w-2xl space-y-3">
            {src.map((s) => <Meter key={s.source} value={s.monthly_avg} max={src[0].monthly_avg} tone={s.kind === 'card' ? 'info' : 'accent'}
              label={<><span className="flex items-center gap-2">{s.kind === 'card' ? <CreditCard size={13} aria-hidden /> : <Landmark size={13} aria-hidden />}{s.source}</span><span className="num">{inr(s.monthly_avg)}/mo</span></>} />)}
          </div>
        </Section>
      )}

      <Drawer open={!!acct} onClose={() => setAcct(null)} title={acct ? `${acct.bank_name} ${acct.account_masked}` : ''} subtitle={acct?.account_type}>
        {acct && <>
          <div className="num text-title font-semibold">{inr(acct.balance, { compact: false })}</div>
          <div className="mt-6"><KV rows={[['Interest rate', pct(acct.interest_rate)], ['Transactions recorded', acct.transactions], ['Primary account', acct.is_primary ? 'Yes' : 'No'],
            acct.balance_as_of && ['Balance as of', acct.balance_as_of], acct.balance_source && ['Balance from', acct.balance_source]]} /></div>
          <div className="mt-6 flex flex-col gap-2">
            <Link to={`/money?tab=transactions&source=account:${acct.id}`} className="inline-flex items-center gap-1 text-sm font-medium text-accent hover:underline">See its transactions <ArrowRight size={14} aria-hidden /></Link>
            {!readOnly && <Link to="/data?tab=records&type=bank_accounts" className="inline-flex items-center gap-1 text-sm font-medium text-accent hover:underline"><Pencil size={14} aria-hidden /> Edit bank accounts</Link>}
          </div>
        </>}
      </Drawer>

      <Drawer open={!!card} onClose={() => setCard(null)} title={card ? `${card.card} ••${card.last4}` : ''} subtitle={card && `Limit ${inr(card.limit)} · APR ${card.apr_pct}% · bill due on day ${card.due_day}`}>
        {card && (() => { const r = risk?.cards?.find((x) => x.last4 === card.last4); return <>
          <Meter value={card.utilisation_pct} tone={band[card.utilisation_band]} label={<><span>Outstanding {inr(card.outstanding, { compact: false })}</span><span className="num">{pct(card.utilisation_pct, 0)} of limit</span></>} />
          <Facts className="mt-6" items={[['Minimum due', inr(card.min_due)], ['Interest / month', inr(card.est_interest_per_month)],
            ['Risk of missing a payment', r ? `${r.default_probability_pct}%` : '—', r ? 'credit-risk model' : 'not scored', r && r.default_probability_pct >= 30 ? 'bad' : undefined]]} />
          <h3 className="mt-6 text-[13px] font-medium text-ink-2">Statements and payments</h3>
          <div className="mt-2 h-40" role="img" aria-label={`Statement balances and payments for the last ${card.statements.length} months`}>
            <ResponsiveContainer><BarChart data={card.statements} margin={{ left: 0, right: 4 }}>
              <CartesianGrid vertical={false} /><XAxis dataKey="month" tickFormatter={monthLabel} {...chartAxis} interval={1} />
              <YAxis tickFormatter={axisInr} {...chartAxis} width={44} /><Tooltip {...chartTooltip} labelFormatter={monthLabel} formatter={(v, n) => [inr(v), n]} />
              <Bar dataKey="bill" name="Statement balance" fill="#98a2b3" radius={[3, 3, 0, 0]} />
              <Bar dataKey="paid" name="Paid" radius={[3, 3, 0, 0]}>{card.statements.map((s, i) => <Cell key={i} fill={s.status > 0 ? '#c4320a' : s.status === 0 ? '#b8640a' : '#13794a'} />)}</Bar>
            </BarChart></ResponsiveContainer>
          </div>
          <div className="mt-3 flex flex-wrap gap-1.5">{card.statements.slice(-6).map((s) => { const [t, tone] = STATUS(s.status); return <Badge key={s.month} tone={tone}>{monthLabel(s.month)}: {t}</Badge> })}</div>
          <Link to="/models?tab=credit-risk" className="mt-6 inline-flex items-center gap-1 text-sm font-medium text-accent hover:underline">Why the model gives this risk <ArrowRight size={14} aria-hidden /></Link>
        </>})()}
      </Drawer>
    </>
  )
}
