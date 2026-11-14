import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowLeft, ChevronLeft, ChevronRight } from 'lucide-react'
import { api } from '../api'
import { Badge, Button, Card, ErrorBox, Input, KV, Loading, Note, PageHeader } from '../components/ui.jsx'
import { useAsync } from '../store.jsx'

// Blinded review of the unusual-spending model. The server sends each transaction WITHOUT the model's score, flag or the
// sampling group, in a fixed random order, so a reviewer's judgement cannot be influenced by the model.
const CHOICES = [['usual', 'Usual for this cardholder'], ['somewhat_unusual', 'Somewhat unusual'], ['very_unusual', 'Very unusual'], ['cannot_tell', 'Cannot tell']]
const usd = (v) => `$${Number(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`

export default function AnomalyReview() {
  const { data, loading, error, reload } = useAsync(() => api.anomalyReview(), [])
  const [i, setI] = useState(null)
  const [note, setNote] = useState('')
  const [saving, setSaving] = useState(false)
  const [local, setLocal] = useState({})
  const items = data?.items || []
  const firstOpen = useMemo(() => Math.max(0, items.findIndex((it) => !it.your_label)), [items])
  if (loading && !data) return <Loading full />
  if (error) return <ErrorBox message={error} onRetry={reload} />
  const idx = i ?? firstOpen
  const it = items[idx]
  const labelOf = (x) => local[x.item_id] || x.your_label?.label
  const done = items.filter(labelOf).length
  const save = async (label) => {
    setSaving(true)
    try {
      await api.anomalyLabel(it.item_id, label, note)
      setLocal((l) => ({ ...l, [it.item_id]: label })); setNote('')
      if (idx < items.length - 1) setI(idx + 1)
    } finally { setSaving(false) }
  }
  const h = it?.holder_category_history || {}
  return (
    <>
      <PageHeader title="Review: is this transaction unusual?" subtitle={data.instructions}>
        <Link to="/models"><Button variant="ghost" icon={ArrowLeft}>Model Lab</Button></Link>
      </PageHeader>
      <div className="mb-4"><Note>Real, de-identified US government purchase-card transactions (Oklahoma, FY2024). Cardholder names are removed. You are judging unusualness, not fraud. Your labels are stored under your account and are never filled in automatically.</Note></div>
      <div className="mb-3 flex items-center justify-between text-sm"><span className="text-muted">{done} of {items.length} reviewed</span>
        <div className="h-2 w-48 overflow-hidden rounded-full bg-raised"><div className="h-full bg-accent" style={{ width: `${(done / Math.max(1, items.length)) * 100}%` }} /></div></div>
      {it && <Card title={`${it.merchant}`} subtitle={`${it.merchant_category} · ${it.date}`} action={<Badge>{it.item_id}</Badge>}>
        <div className="grid gap-6 md:grid-cols-2">
          <div><div className="num text-3xl font-semibold">{usd(it.amount)}</div><div className="mt-1 text-sm text-muted">Finora category: {it.category}</div></div>
          <KV rows={[[`This cardholder's ${it.category} purchases (same year)`, h.transactions], ['Their typical amount (median)', usd(h.median)],
            ['Their middle half', `${usd(h.p25)} – ${usd(h.p75)}`], ['Their largest other one', usd(h.max_other)],
            ['Their transactions that month', it.holder_transactions_that_month], [`${it.category} purchases that day`, it.same_day_same_category]]} />
        </div>
        <div className="mt-4 flex flex-wrap gap-2">{CHOICES.map(([k, t]) => <Button key={k} variant={labelOf(it) === k ? 'primary' : 'ghost'} loading={saving} onClick={() => save(k)}>{t}</Button>)}</div>
        <div className="mt-3"><Input placeholder="Optional note (why?)" value={note} maxLength={500} onChange={(e) => setNote(e.target.value)} /></div>
        <div className="mt-4 flex justify-between"><Button variant="ghost" icon={ChevronLeft} disabled={idx === 0} onClick={() => setI(idx - 1)}>Previous</Button>
          <Button variant="ghost" disabled={idx >= items.length - 1} onClick={() => setI(idx + 1)}>Next <ChevronRight size={14} /></Button></div>
      </Card>}
    </>
  )
}
