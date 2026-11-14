import { Link } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { ClipboardCheck, FlaskConical, Radar } from 'lucide-react'
import { Badge, Button, Card, Empty, Note, PageHeader, Stat, chartTooltip } from '../components/ui.jsx'
import { dateLabel, inr } from '../format'
import { useFinora } from '../store.jsx'

// Anomaly Detection Scanner: the real Isolation Forest (trained on Oklahoma cardholder histories) applied to this profile's
// own transactions. Experimental and not human-validated; a flag means "unusual for you", never "fraud".
export default function Scanner() {
  const { analysis: a } = useFinora()
  const an = a.ml.anomaly || {}
  const info = an.model_info || {}
  const dist = an.score_distribution
  const bins = (dist?.bins || []).map((b) => ({ ...b, label: b.from.toFixed(2), above: b.from >= dist.threshold }))
  const flagged = an.flagged || []
  return (
    <>
      <PageHeader title="Anomaly Detection Scanner" subtitle="An Isolation Forest scores every spending transaction against your own history and flags the ones that look unusual for you." />
      <div className="mb-4 space-y-2">
        <Note tone="warn"><b>Experimental, not human-validated.</b> The blinded human review of this model's flags is not complete. A flag means the
          transaction looks unusual compared with your own history. It is not a fraud finding, and the model's accuracy against human judgement is not yet measured.</Note>
        {an.model_note && <Note>{an.model_note}</Note>}
      </div>
      {an.available === false ? <Card><Empty title="The scanner could not run">{an.note || a.ml_errors?.anomaly}</Empty></Card> : <>
        <div className="grid gap-4 md:grid-cols-4">
          <Stat label="Transactions scanned" value={an.transactions_scored ?? 0} sub="rent, EMIs, SIPs, insurance and transfers are not scored" icon={Radar} />
          <Stat label="Flagged as unusual" value={an.flagged_count ?? 0} tone={an.flagged_count ? 'warn' : 'good'} sub={an.transactions_scored ? `${((an.flagged_count / an.transactions_scored) * 100).toFixed(1)}% of scanned` : ''} />
          <Stat label="Amount flagged" value={inr(an.flagged_amount_total || 0)} />
          <Stat label="Model version" value={info.version || '-'} sub="Isolation Forest, 300 trees" icon={FlaskConical} />
        </div>
        <div className="mt-4 grid gap-4 xl:grid-cols-3">
          <Card title="Flagged transactions" subtitle={an.severity_rule} className="xl:col-span-2">
            {!an.transactions_scored ? <Empty title="Nothing to scan yet">Add transactions under My Data or import a statement.</Empty>
              : flagged.length === 0 ? <p className="py-6 text-center text-sm text-good">Nothing unusual found in your history.</p> : (
              <ul className="space-y-2">
                {flagged.map((x) => (
                  <li key={x.transaction_id} className="rounded-xl border border-line bg-raised/50 p-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge tone={x.severity}>{x.severity}</Badge>
                      <span className="font-medium">{x.merchant || x.category}</span>
                      <span className="text-xs text-muted">{dateLabel(x.date)} · {x.category} · {x.source}</span>
                      <span className="num ml-auto font-semibold">{inr(x.amount, { compact: false })}</span>
                    </div>
                    <ul className="mt-1.5 list-disc space-y-0.5 pl-5 text-xs text-muted">{x.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
                    <div className="num mt-1 text-[11px] text-faint">anomaly score {x.anomaly_score} · typical {inr(x.typical_amount)} · {x.times_typical}× typical</div>
                  </li>))}
              </ul>)}
            <div className="mt-3"><Note>{an.disclaimer || 'Unusual does not mean fraudulent.'}</Note></div>
          </Card>
          <Card title="Anomaly scores" subtitle="Every scanned transaction; higher = more unusual for you">
            {bins.length ? <div className="h-56"><ResponsiveContainer><BarChart data={bins} margin={{ left: -18 }}><CartesianGrid vertical={false} />
              <XAxis dataKey="label" tickLine={false} axisLine={false} interval={4} /><YAxis allowDecimals={false} tickLine={false} axisLine={false} />
              <Tooltip {...chartTooltip} labelFormatter={(l) => `score from ${l}`} /><Bar dataKey="count" name="Transactions" radius={[3, 3, 0, 0]}>{bins.map((b) => <Cell key={b.label} fill={b.above ? '#f87171' : '#fbbf24'} />)}</Bar></BarChart></ResponsiveContainer></div>
              : <p className="text-sm text-muted">No scores yet.</p>}
            <div className="mt-3 space-y-2 text-xs text-muted">
              <p>Red bars are above the model's flagging threshold ({dist?.threshold}). How to read it: the model isolates each transaction with random splits; ones that separate quickly from your usual pattern get higher scores. About 1.4% of a later year's transactions were flagged on the data it was tested on.</p>
              <div className="flex flex-wrap gap-2"><Link to="/models"><Button variant="ghost">Model details</Button></Link>
                <Link to="/models/review"><Button variant="ghost" icon={ClipboardCheck}>Help validate it</Button></Link></div>
            </div>
          </Card>
        </div>
      </>}
    </>
  )
}
