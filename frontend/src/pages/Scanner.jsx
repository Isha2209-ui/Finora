// Risk & Models → Unusual activity. The real Isolation Forest (trained on Oklahoma cardholder histories) applied to this profile's
// own transactions; a flag means "unusual for you".
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { ClipboardCheck } from 'lucide-react'
import { Answer, AskAbout, Badge, ButtonLink, Card, Drawer, Empty, KV, List, Note, PageHeader, Row, Section, Trust, chartAxis, chartTooltip } from '../components/ui.jsx'
import { dateLabel, inr } from '../format'
import { useFinora } from '../store.jsx'

export default function Scanner() {
  const { analysis: a } = useFinora()
  const an = a.ml.anomaly || {}
  const dist = an.score_distribution
  const bins = (dist?.bins || []).map((b) => ({ ...b, label: b.from.toFixed(2), above: b.from >= dist.threshold }))
  const flagged = an.flagged || []
  const [open, setOpen] = useState(null)
  if (an.available === false) return <><PageHeader title="Unusual activity" /><Card><Empty title="The scanner could not run">{an.note || a.ml_errors?.anomaly}</Empty></Card></>
  return (
    <>
      <PageHeader title="Unusual activity" />
      <Answer eyebrow="Spending that is unusual for you"
        sub={an.transactions_scored ? `Rent, EMIs, SIPs, insurance and transfers are not scored.` : undefined}>
        {!an.transactions_scored ? 'There is nothing to scan yet.'
          : flagged.length === 0 ? <>None of your <b>{an.transactions_scored}</b> transactions look unusual.</>
            : <><b>{flagged.length}</b> of your {an.transactions_scored} transactions look unusual for you, <b>{inr(an.flagged_amount_total || 0)}</b> in total.</>}
      </Answer>
      <Trust model="anomaly" className="mb-8" />

      {!an.transactions_scored ? <Empty title="Nothing to scan yet">Add transactions under Data → Records or import a statement.</Empty> : flagged.length > 0 && (
        <Section title="Flagged transactions" description="Select one to see why it was flagged.">
          <List>
            {flagged.map((x) => (
              <Row key={x.transaction_id} onClick={() => setOpen(x)} lead={<Badge tone={x.severity}>{x.severity}</Badge>}
                title={x.merchant || x.category} subtitle={`${dateLabel(x.date)} · ${x.category} · ${x.times_typical}× your typical amount`}
                value={inr(x.amount, { compact: false })} valueSub={x.source} />
            ))}
          </List>
          <p className="mt-3 text-[13px] text-muted">{an.severity_rule}</p>
        </Section>
      )}

      <Section title="How the scanner decides" className="mt-10">
        <div className="space-y-3">
          <details className="rounded-xl border border-line bg-bg px-5 py-4"><summary className="cursor-pointer text-[15px] font-medium text-ink">Scores for every scanned transaction</summary>
            {bins.length ? <div className="mt-4 h-56" role="img" aria-label={`Distribution of anomaly scores; ${flagged.length} transactions are above the flagging threshold of ${dist?.threshold}`}>
              <ResponsiveContainer><BarChart data={bins} margin={{ left: -18 }}><CartesianGrid vertical={false} />
                <XAxis dataKey="label" {...chartAxis} interval={4} /><YAxis allowDecimals={false} {...chartAxis} />
                <Tooltip {...chartTooltip} labelFormatter={(l) => `score from ${l}`} /><Bar dataKey="count" name="Transactions" radius={[3, 3, 0, 0]}>{bins.map((b) => <Cell key={b.label} fill={b.above ? '#c4320a' : '#c9cfd8'} />)}</Bar></BarChart></ResponsiveContainer></div>
              : <p className="mt-3 text-sm text-muted">No scores yet.</p>}
            <p className="mt-3 text-sm leading-6 text-muted">Red bars are above the flagging threshold ({dist?.threshold}). The model isolates each transaction with random splits; transactions that separate quickly from your usual pattern score higher. On the data it was tested on, about 1.4% of a later year's transactions were flagged.</p>
          </details>
          <details className="rounded-xl border border-line bg-bg px-5 py-4"><summary className="cursor-pointer text-[15px] font-medium text-ink">Review workspace and model details</summary>
            <p className="mt-3 text-sm leading-6 text-muted">People can label flagged and unflagged transactions in the review workspace without seeing the model's output; the labels are stored with the model's records.</p>
            <div className="mt-4 flex flex-wrap gap-2"><ButtonLink to="/models?tab=lab&model=anomaly" variant="secondary">Model details</ButtonLink>
              <ButtonLink to="/models/review" variant="secondary" icon={ClipboardCheck}>Open the review workspace</ButtonLink></div>
          </details>
        </div>
      </Section>

      <Drawer open={!!open} onClose={() => setOpen(null)} title={open?.merchant || open?.category || ''} subtitle={open && `${dateLabel(open.date)} · ${open.category} · ${open.source}`}>
        {open && <>
          <div className="num text-title font-semibold">{inr(open.amount, { compact: false })}</div>
          <div className="mt-2"><Badge tone={open.severity}>{open.severity} · unusual for you</Badge></div>
          <h3 className="mt-6 text-[13px] font-medium text-ink-2">Why it was flagged</h3>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-ink-2">{open.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
          <div className="mt-6"><KV rows={[['Your typical amount in this category', inr(open.typical_amount)], ['Times typical', `${open.times_typical}×`], ['Anomaly score', open.anomaly_score]]} /></div>
          <div className="mt-6 flex flex-wrap gap-4"><AskAbout q={`Why is my ${inr(open.amount, { compact: false })} ${open.category} transaction at ${open.merchant} on ${open.date} unusual?`} />
            <Link to={`/money?tab=transactions&q=${encodeURIComponent(open.merchant || '')}`} className="text-[13px] font-medium text-accent hover:underline">Find it in transactions</Link></div>
        </>}
      </Drawer>
    </>
  )
}
