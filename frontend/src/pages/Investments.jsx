// Money → Investments. Answer first (worth vs put in), then holdings by value (detail in a drawer), concentration, SIPs, other assets.
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { Answer, Badge, Drawer, Empty, Facts, KV, List, Note, PageHeader, Row, Section, cx } from '../components/ui.jsx'
import { PALETTE, dateLabel, inr, pct } from '../format'
import { useAsync, useFinora } from '../store.jsx'

export default function Investments() {
  const { analysis: a, profileId, profile } = useFinora()
  const inv = a.investments
  const nw = a.net_worth.breakdown
  const raw = useAsync(() => api.dataSummary(profileId), [profileId])
  const [open, setOpen] = useState(null)
  const sectors = inv.sector_exposure || []
  const others = [['Fixed deposits', nw['Fixed deposits']], ['Retirement (EPF/PPF/NPS)', nw['Retirement (EPF/PPF/NPS)']], ['Gold', nw['Gold']], ['Real estate', nw['Real estate']], ['Cash in hand', nw['Cash in hand']]].filter(([, v]) => v)
  const holdings = [...inv.holdings].sort((x, y) => y.current - x.current)
  const readOnly = profile?.kind === 'template'
  const up = inv.total_gain >= 0
  return (
    <>
      <PageHeader title="Investments" />
      {holdings.length ? (
        <Answer eyebrow="Your market investments" tone={up ? 'good' : 'bad'}
          sub={`Prices are stored values as of ${dateLabel(inv.prices_as_of)}, not a live feed.`}>
          Worth <b className="!text-ink">{inr(inv.current_value)}</b> today, <b>{up ? '+' : '−'}{inr(Math.abs(inv.total_gain))}</b> ({pct(inv.total_gain_pct)}) {up ? 'more' : 'less'} than the {inr(inv.total_invested)} you put in.
        </Answer>
      ) : <Answer eyebrow="Your market investments" sub="Add stocks, mutual funds or SIPs under Data → Records.">No market investments recorded yet.</Answer>}
      <Facts items={[
        ['Monthly SIPs', inr(inv.sip_monthly_total), `${pct(inv.sip_to_income_pct || 0)} of income`, (inv.sip_to_income_pct || 0) >= 10 ? 'good' : 'warn'],
        ['SIPs missed (12 months)', String(inv.sips_missed_last_12m), inv.sips_missed_last_12m ? 'a missed SIP is a missed month of compounding' : 'none missed', inv.sips_missed_last_12m >= 2 ? 'bad' : 'good'],
        ['Holdings', `${inv.stock_count} stocks · ${inv.fund_count} funds`],
      ]} />

      {holdings.length > 0 && (
        <Section title="Holdings" description="Largest first. Select one for its purchase details and return.">
          <List>
            {holdings.map((h) => (
              <Row key={h.name} onClick={() => setOpen(h)} title={h.name} subtitle={`${h.type} · ${h.sector || '—'} · held ${h.years_held} years`}
                lead={<span className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-subtle text-[13px] font-semibold text-ink-2">{(h.symbol || h.name).slice(0, 2).toUpperCase()}</span>}
                value={inr(h.current)} valueSub={<span className={h.gain >= 0 ? 'text-good' : 'text-bad'}>{h.gain >= 0 ? '+' : ''}{pct(h.gain_pct)}</span>} />
            ))}
          </List>
        </Section>
      )}

      {sectors.length > 0 && (
        <Section title="Where your stocks are concentrated" description={inv.top_sector ? `${inv.top_sector.sector} is ${pct(inv.top_sector.share_of_stocks_pct, 0)} of your direct stocks.` : undefined}>
          <div className="flex h-3 max-w-3xl overflow-hidden rounded-full" role="img" aria-label={sectors.map((s) => `${s.sector} ${pct(s.share_of_stocks_pct, 0)}`).join(', ')}>
            {sectors.map((s, i) => <div key={s.sector} style={{ width: `${s.share_of_stocks_pct}%`, background: PALETTE[i % PALETTE.length] }} />)}
          </div>
          <ul className="mt-3 flex max-w-3xl flex-wrap gap-x-5 gap-y-1.5 text-[13px] text-ink-2">
            {sectors.map((s, i) => <li key={s.sector} className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: PALETTE[i % PALETTE.length] }} aria-hidden />{s.sector} <span className="num text-muted">{pct(s.share_of_stocks_pct, 0)}</span></li>)}
          </ul>
          {inv.top_sector && inv.top_sector.share_of_stocks_pct >= 50 && inv.stock_count >= 3 && <div className="mt-4 max-w-3xl"><Note tone="warn">More than half of the stock portfolio sits in one sector, which concentrates risk.</Note></div>}
        </Section>
      )}

      <div className="mt-10 grid gap-10 lg:grid-cols-2">
        <Section title="SIPs" description={inv.sips.length ? `${inr(inv.sip_monthly_total)} a month in total.` : undefined}>
          {inv.sips.length ? <List>{inv.sips.map((s) => (
            <Row key={s.scheme} title={s.scheme} subtitle={`On day ${s.sip_day} each month${s.missed_last_12m ? ` · missed ${s.missed_last_12m} in 12 months` : ''}`} value={inr(s.amount)} valueSub="per month">
              <Badge tone={s.status === 'active' ? 'good' : 'bad'}>{s.status}</Badge></Row>))}</List>
            : <p className="text-sm text-muted">No SIPs set up.</p>}
        </Section>
        <Section title="Other assets" description="Deposits, retirement accounts, gold, property and cash.">
          {others.length ? <List>{others.map(([k, v]) => <Row key={k} title={k} value={inr(v)} />)}</List> : <p className="text-sm text-muted">None recorded.</p>}
        </Section>
      </div>
      <p className="mt-8 text-micro text-faint">
        {raw.data && `Records on file: ${raw.data.tables.filter((t) => ['Stocks', 'Mutual funds', 'SIPs', 'Fixed deposits', 'Properties', 'Other assets'].includes(t.table)).map((t) => `${t.rows} ${t.table.toLowerCase()}`).join(' · ')}. `}
        {!readOnly && <Link to="/data?tab=records&type=stocks" className="text-accent hover:underline">Edit investments</Link>}
      </p>

      <Drawer open={!!open} onClose={() => setOpen(null)} title={open?.name || ''} subtitle={open && `${open.type} · ${open.sector || '—'}`}>
        {open && <>
          <div className="num text-title font-semibold">{inr(open.current, { compact: false })}</div>
          <div className={cx('num mt-1 text-sm font-medium', open.gain >= 0 ? 'text-good' : 'text-bad')}>{open.gain >= 0 ? '+' : '−'}{inr(Math.abs(open.gain), { compact: false })} ({pct(open.gain_pct)}) since purchase</div>
          <div className="mt-6"><KV rows={[['Invested', inr(open.invested, { compact: false })], ['Current value', inr(open.current, { compact: false })], ['Held for', `${open.years_held} years`],
            ['Yearly return (CAGR)', open.cagr_pct == null ? 'not meaningful for under a year' : pct(open.cagr_pct)]]} /></div>
          {open.note && <div className="mt-4"><Note>{open.note}</Note></div>}
        </>}
      </Drawer>
      {holdings.length === 0 && inv.sips.length === 0 && <Empty title="Nothing invested yet">Investments you add appear here with their gains.</Empty>}
    </>
  )
}
