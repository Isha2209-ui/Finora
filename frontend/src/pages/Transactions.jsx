import { useEffect, useState } from 'react'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { ChevronLeft, ChevronRight, Download, Flag, Search } from 'lucide-react'
import { api } from '../api'
import { Badge, Button, Card, ErrorBox, Input, Loading, Note, PageHeader, Select, Stat, Table, chartTooltip, cx } from '../components/ui.jsx'
import { dateLabel, inr, monthLabel } from '../format'
import { useFinora } from '../store.jsx'

const PAGE = 25

export default function Transactions() {
  const { profileId, refresh } = useFinora()
  const [f, setF] = useState({ category: '', source: '', month: '', search: '', flagged_only: false })
  const [page, setPage] = useState(0)
  const [data, setData] = useState(null)
  const [sources, setSources] = useState([])
  const [err, setErr] = useState(null)
  const [open, setOpen] = useState(null)

  const load = () => api.transactions(profileId, { ...f, limit: PAGE, offset: page * PAGE }).then((d) => { setData(d); setErr(null) }).catch((e) => setErr(e.message))
  useEffect(() => { const t = setTimeout(load, f.search ? 250 : 0); return () => clearTimeout(t) }, [profileId, f, page]) // eslint-disable-line
  useEffect(() => { api.accounts(profileId).then((a) => setSources([...a.accounts.map((x) => [`account:${x.id}`, `${x.bank_name} ${x.account_masked}`]), ...a.card_ids.map((c) => [`card:${c.id}`, c.label])])).catch(() => {}) }, [profileId])
  const set = (k, v) => { setPage(0); setF((s) => ({ ...s, [k]: v })) }
  const recat = async (tx, category) => { await api.recategorise(profileId, tx.id, category); await load(); refresh() }

  if (err) return <ErrorBox message={err} onRetry={load} />
  if (!data) return <Loading full />
  const s = data.anomaly_summary
  const pages = Math.max(1, Math.ceil(data.total / PAGE))
  return (
    <>
      <PageHeader title="Transaction Intelligence" subtitle="Every transaction across all accounts and cards, categorised and scored by the Isolation Forest anomaly model.">
        <a href={api.url(`/profiles/${profileId}/transactions.csv`)}><Button variant="ghost" icon={Download}>CSV</Button></a>
      </PageHeader>
      <div className="grid gap-4 md:grid-cols-4">
        <Stat label="Transactions scored" value={s.transactions_scored} sub="fixed payments (rent, EMI, SIPs) are not scored" />
        <Stat label="Flagged as unusual" value={s.flagged_count} tone={s.flagged_count ? 'warn' : 'good'} icon={Flag} sub={`total ${inr(s.flagged_amount_total)}`} />
        <Stat label="High severity" value={data.flagged.filter((x) => x.severity === 'high').length} tone="bad" sub="8× or more above your typical amount" />
        <Stat label="Categories affected" value={s.by_category?.length || 0} sub={(s.by_category || []).map((c) => c.category).slice(0, 3).join(', ') || '—'} />
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-3">
        <Card title="Flagged transactions" subtitle={s.severity_rule} className="xl:col-span-2">
          {!s.transactions_scored ? <p className="py-6 text-center text-sm text-muted">No transactions yet. Add them under My Data or upload a statement.</p> : data.flagged.length === 0 ? <p className="py-6 text-center text-sm text-good">Nothing unusual found.</p> : (
            <ul className="max-h-80 space-y-2 overflow-y-auto pr-1">
              {data.flagged.map((x) => (
                <li key={x.transaction_id} className="rounded-xl border border-line bg-raised/50 p-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge tone={x.severity}>{x.severity}</Badge>
                    <span className="font-medium">{x.merchant || x.category}</span><span className="text-xs text-muted">{dateLabel(x.date)} · {x.category} · {x.source}</span>
                    <span className="num ml-auto font-semibold">{inr(x.amount, { compact: false })}</span>
                  </div>
                  <ul className="mt-1.5 list-disc space-y-0.5 pl-5 text-xs text-muted">{x.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
                  <div className="num mt-1 text-[11px] text-faint">typical {inr(x.typical_amount)} · {x.times_typical}× · anomaly score {x.anomaly_score}</div>
                </li>
              ))}
            </ul>
          )}
          <div className="mt-3"><Note>{s.disclaimer}</Note></div>
        </Card>
        <Card title="Flags by month">
          <div className="h-56"><ResponsiveContainer><BarChart data={s.by_month || []} margin={{ left: -18 }}><CartesianGrid vertical={false} />
            <XAxis dataKey="month" tickFormatter={monthLabel} tickLine={false} axisLine={false} interval={1} /><YAxis allowDecimals={false} tickLine={false} axisLine={false} />
            <Tooltip {...chartTooltip} labelFormatter={monthLabel} /><Bar dataKey="flagged" name="Flagged" fill="#fbbf24" radius={[4, 4, 0, 0]} /></BarChart></ResponsiveContainer></div>
          <ul className="mt-2 space-y-1 text-[13px]">{(s.by_category || []).map((c) => <li key={c.category} className="flex justify-between"><span className="text-muted">{c.category} · {c.count}</span><span className="num">{inr(c.amount)}</span></li>)}</ul>
        </Card>
      </div>

      <Card title="All transactions" subtitle={`${data.total} matching`} className="mt-4" pad={false}
        action={<label className="flex cursor-pointer items-center gap-2 text-xs text-muted"><input type="checkbox" checked={f.flagged_only} onChange={(e) => set('flagged_only', e.target.checked)} className="accent-[#2dd4bf]" /> Flagged only</label>}>
        <div className="grid gap-2 px-5 pb-3 md:grid-cols-4">
          <div className="relative"><Search size={14} className="absolute top-2.5 left-3 text-faint" /><Input placeholder="Search merchant or text" value={f.search} onChange={(e) => set('search', e.target.value)} className="pl-8" /></div>
          <Select value={f.category} onChange={(e) => set('category', e.target.value)}><option value="">All categories</option>{data.categories.map((c) => <option key={c}>{c}</option>)}</Select>
          <Select value={f.source} onChange={(e) => set('source', e.target.value)}><option value="">All accounts & cards</option>{sources.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</Select>
          <Select value={f.month} onChange={(e) => set('month', e.target.value)}><option value="">All months</option>{data.months.map((m) => <option key={m} value={m}>{monthLabel(m)}</option>)}</Select>
        </div>
        <Table dense rows={data.items} empty="No transactions match these filters" onRow={(r) => setOpen(open === r.id ? null : r.id)} rowClass={(r) => r.flagged ? 'bg-warn/[0.06]' : ''} columns={[
          { key: 'date', label: 'Date', render: (r) => <span className="num whitespace-nowrap text-muted">{dateLabel(r.date)}</span> },
          { key: 'description', label: 'Description', render: (r) => (
            <div className="max-w-[420px]"><div className="truncate font-medium">{r.merchant || r.description}</div><div className="truncate font-mono text-[11px] text-faint">{r.description}</div>
              {open === r.id && r.reasons && <ul className="mt-1 list-disc pl-4 text-xs text-warn">{r.reasons.map((x) => <li key={x}>{x}</li>)}</ul>}</div>) },
          { key: 'category', label: 'Category', render: (r) => (
            <select value={r.category || ''} onClick={(e) => e.stopPropagation()} onChange={(e) => recat(r, e.target.value)} title={`Category source: ${r.category_source}`}
              className={cx('rounded-lg border bg-bg px-1.5 py-1 text-xs outline-none', r.category_source === 'model' ? 'border-info/40 text-info' : r.category_source === 'user' ? 'border-accent/40 text-accent' : 'border-line text-ink')}>
              {data.categories.map((c) => <option key={c}>{c}</option>)}</select>) },
          { key: 'source', label: 'Source', render: (r) => <span className="whitespace-nowrap text-xs text-muted">{r.source}</span> },
          { key: 'flag', label: 'Anomaly', render: (r) => r.flagged ? <Badge tone={r.severity}>{r.severity}</Badge> : r.anomaly_score != null ? <span className="num text-xs text-faint">{r.anomaly_score.toFixed(2)}</span> : <span className="text-xs text-faint">not scored</span> },
          { key: 'amount', label: 'Amount', right: true, render: (r) => <span className={cx('font-medium', r.type === 'credit' && 'text-good')}>{r.type === 'credit' ? '+' : ''}{inr(r.amount, { compact: false })}</span> },
        ]} />
        <div className="flex items-center justify-between border-t border-line px-5 py-3 text-xs text-muted">
          <span>Category colour: <span className="text-info">blue = predicted by the model</span>, <span className="text-accent">teal = corrected by you</span>. Click a flagged row for the reasons.</span>
          <span className="flex items-center gap-2"><button disabled={page === 0} onClick={() => setPage(page - 1)} className="rounded-lg border border-line p-1 disabled:opacity-30"><ChevronLeft size={14} /></button>
            <span className="num">Page {page + 1} of {pages}</span>
            <button disabled={page + 1 >= pages} onClick={() => setPage(page + 1)} className="rounded-lg border border-line p-1 disabled:opacity-30"><ChevronRight size={14} /></button></span>
        </div>
      </Card>
    </>
  )
}
