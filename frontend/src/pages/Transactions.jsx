// Money → Transactions. Stripe-style table: search + filter chips + sort in the URL, server-side paging, row → detail drawer.
// Category corrections, suggestion accept/reject and delete all go through the existing API and re-run the analysis.
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Download, Flag, Plus, Search, Trash2 } from 'lucide-react'
import { api } from '../api'
import { AskAbout, Badge, Button, Card, Drawer, Empty, ErrorBox, Field, Input, KV, Loading, Note, Select, cx, useConfirm, useToast, useUrlParam, useUrlUpdate } from '../components/ui.jsx'
import { dateLabel, inr, monthLabel } from '../format'
import { useFinora } from '../store.jsx'

const PAGE = 25
const SORTS = [['date_desc', 'Newest first'], ['date_asc', 'Oldest first'], ['amount_desc', 'Largest amount'], ['amount_asc', 'Smallest amount']]

export default function Transactions({ suggestedOnly = false }) {
  const { profileId, profile, refresh } = useFinora()
  const confirm = useConfirm()
  const toast = useToast()
  const readOnly = profile?.kind === 'template'
  const [search, setSearch] = useUrlParam('q', null, '')
  const [category, setCategory] = useUrlParam('category', null, '')
  const [source, setSource] = useUrlParam('source', null, '')
  const [month, setMonth] = useUrlParam('month', null, '')
  const [flagged, setFlagged] = useUrlParam('flagged', null, '')
  const [sort, setSort] = useUrlParam('sort', SORTS.map((s) => s[0]))
  const [pageRaw, setPage] = useUrlParam('page', null, '1')
  const page = Math.max(0, (Number(pageRaw) || 1) - 1)
  const update = useUrlUpdate()
  const [typed, setTyped] = useState(search)
  const [data, setData] = useState(null)
  const [sources, setSources] = useState([])
  const [err, setErr] = useState(null)
  const [open, setOpen] = useState(null)
  const [busy, setBusy] = useState(false)
  const [adding, setAdding] = useState(false)

  const params = { search, category, source, month, flagged_only: flagged === '1', suggested_only: suggestedOnly, sort, limit: PAGE, offset: page * PAGE }
  const load = () => api.transactions(profileId, params).then((d) => { setData(d); setErr(null); return d }).catch((e) => setErr(e.message))
  useEffect(() => { load() }, [profileId, search, category, source, month, flagged, sort, page, suggestedOnly]) // eslint-disable-line
  useEffect(() => { const t = setTimeout(() => { if (typed !== search) update({ q: typed, page: null }) }, 300); return () => clearTimeout(t) }, [typed]) // eslint-disable-line
  useEffect(() => { api.accounts(profileId).then((a) => setSources([...a.accounts.map((x) => [`account:${x.id}`, `${x.bank_name} ${x.account_masked}`]), ...a.card_ids.map((c) => [`card:${c.id}`, c.label])])).catch(() => {}) }, [profileId])
  const filter = (setter) => (v) => setter(v || null, { also: { page: null } })

  const act = async (fn, okMsg) => {
    setBusy(true)
    try { await fn(); const d = await load(); setOpen((o) => (o ? d?.items.find((x) => x.id === o.id) || null : null)); refresh(); toast(okMsg, { tone: 'good' }) }
    catch (e) { toast(e.message, { tone: 'bad' }) } finally { setBusy(false) }
  }
  const recat = (tx, c) => act(() => api.recategorise(profileId, tx.id, c), `Category set to ${c}`)
  const decide = (tx, action) => act(() => api.decideSuggestion(profileId, tx.id, action), action === 'accept' ? 'Suggestion accepted' : 'Suggestion rejected — choose the right category')
  const remove = async (tx) => {
    if (!await confirm({ title: 'Delete this transaction?', body: `${tx.merchant || tx.description} · ${inr(tx.amount, { compact: false })} on ${dateLabel(tx.date)}. It is removed from your profile and the analysis is re-run.`, confirm: 'Delete transaction', danger: true })) return
    await act(() => api.deleteTransaction(profileId, tx.id), 'Transaction deleted'); setOpen(null)
  }

  if (err && !data) return <ErrorBox message={err} onRetry={load} />
  if (!data) return <Loading label="Loading transactions…" />
  const s = data.anomaly_summary
  const pages = Math.max(1, Math.ceil(data.total / PAGE))
  const active = [search, category, source, month, flagged].filter(Boolean).length
  return (
    <>
      {!suggestedOnly && s.available !== false && s.flagged_count > 0 && (
        <Link to="/models?tab=unusual" className="mb-5 flex flex-wrap items-center gap-2 rounded-lg border border-warn/25 bg-warn-soft px-4 py-3 text-sm text-warn hover:bg-warn-soft/70">
          <Flag size={15} aria-hidden /> {s.flagged_count} transactions look unusual for you ({inr(s.flagged_amount_total)}).
          <span className="ml-auto font-medium">Review in Unusual activity →</span>
        </Link>
      )}
      <Card pad={false}>
        <div className="flex flex-wrap items-end gap-3 border-b border-line px-4 py-4 sm:px-5">
          <div className="relative w-full sm:w-64">
            <label htmlFor="tx-search" className="mb-1.5 block text-[13px] font-medium text-ink-2">Search</label>
            <Search size={15} className="pointer-events-none absolute bottom-3 left-3 text-faint" aria-hidden />
            <Input id="tx-search" type="search" placeholder="Merchant or description…" value={typed} onChange={(e) => setTyped(e.target.value)} className="pl-9" autoComplete="off" />
          </div>
          <div className="w-[calc(50%-6px)] sm:w-44"><Field label="Category"><Select value={category} onChange={(e) => filter(setCategory)(e.target.value)}><option value="">All categories</option>{data.categories.map((c) => <option key={c}>{c}</option>)}</Select></Field></div>
          <div className="w-[calc(50%-6px)] sm:w-52"><Field label="Account or card"><Select value={source} onChange={(e) => filter(setSource)(e.target.value)}><option value="">All accounts & cards</option>{sources.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</Select></Field></div>
          <div className="w-[calc(50%-6px)] sm:w-36"><Field label="Month"><Select value={month} onChange={(e) => filter(setMonth)(e.target.value)}><option value="">All months</option>{data.months.map((m) => <option key={m} value={m}>{monthLabel(m)}</option>)}</Select></Field></div>
          <div className="w-[calc(50%-6px)] sm:w-40"><Field label="Sort"><Select value={sort} onChange={(e) => setSort(e.target.value, { also: { page: null } })}>{SORTS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</Select></Field></div>
          {!suggestedOnly && <label className="flex h-10 cursor-pointer items-center gap-2 text-sm text-ink-2"><input type="checkbox" checked={flagged === '1'} onChange={(e) => filter(setFlagged)(e.target.checked ? '1' : '')} className="h-4 w-4 accent-[var(--color-accent)]" /> Unusual only</label>}
          <div className="flex-1" />
          {!suggestedOnly && !readOnly && <Button variant="secondary" icon={Plus} onClick={() => setAdding(true)}>Add transaction</Button>}
          {!suggestedOnly && <a href={api.url(`/profiles/${profileId}/transactions.csv`)} className="inline-flex h-10 items-center gap-2 rounded-md border border-control/60 bg-bg px-4 text-sm font-medium text-ink shadow-xs hover:bg-subtle" download><Download size={16} aria-hidden /> Export CSV</a>}
        </div>
        <div className="flex flex-wrap items-center gap-2 px-4 py-2.5 text-[13px] text-muted sm:px-5" aria-live="polite">
          <span className="num">{data.total.toLocaleString('en-IN')} {suggestedOnly ? 'suggested categories awaiting a decision' : 'transactions'}</span>
          {active > 0 && <button type="button" onClick={() => { setTyped(''); update({ q: null, category: null, source: null, month: null, flagged: null, page: null }) }} className="text-accent hover:underline">Clear filters</button>}
        </div>
        {data.items.length === 0 ? <Empty title={suggestedOnly ? 'No suggestions waiting' : 'No transactions match'}>{suggestedOnly ? 'Every model-suggested category has been accepted or corrected.' : 'Try a different search or clear the filters.'}</Empty> : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm"><caption className="sr-only">Transactions</caption>
              <thead><tr className="border-y border-line-strong bg-subtle/70 text-left text-micro uppercase tracking-[0.04em] text-muted">
                <th scope="col" className="py-2.5 pr-3 pl-4 font-medium sm:pl-5">Date</th><th scope="col" className="px-3 py-2.5 font-medium">Description</th>
                <th scope="col" className="px-3 py-2.5 font-medium">Category</th><th scope="col" className="hidden px-3 py-2.5 font-medium lg:table-cell">Account</th>
                <th scope="col" className="py-2.5 pr-4 pl-3 text-right font-medium sm:pr-5">Amount</th></tr></thead>
              <tbody className={cx(busy && 'opacity-60')}>
                {data.items.map((r) => (
                  <tr key={r.id} tabIndex={0} onClick={() => setOpen(r)} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setOpen(r) } }}
                    aria-label={`${r.merchant || r.description}, ${inr(r.amount, { compact: false })}, ${dateLabel(r.date)}. Open details.`}
                    className="cursor-pointer border-b border-line last:border-0 hover:bg-subtle/70 focus-visible:bg-accent-soft">
                    <td className="num py-3 pr-3 pl-4 whitespace-nowrap text-muted sm:pl-5">{dateLabel(r.date)}</td>
                    <td className="max-w-[260px] px-3 py-3 sm:max-w-[380px]"><div className="flex items-center gap-2"><span className="truncate font-medium text-ink">{r.merchant || r.description}</span>{r.flagged && <Badge tone={r.severity}>unusual</Badge>}</div>
                      <div className="truncate font-mono text-micro text-faint">{r.description}</div></td>
                    <td className="px-3 py-3">{r.category ? <span className="inline-flex items-center gap-1.5">{r.category}{r.category_source === 'model' && <Badge tone="accent">suggested</Badge>}</span> : <Badge tone="warn">needs a category</Badge>}</td>
                    <td className="hidden px-3 py-3 whitespace-nowrap text-[13px] text-muted lg:table-cell">{r.source}</td>
                    <td className={cx('num py-3 pr-4 pl-3 text-right font-medium whitespace-nowrap sm:pr-5', r.type === 'credit' ? 'text-good' : 'text-ink')}>{r.type === 'credit' ? '+' : ''}{inr(r.amount, { compact: false })}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {pages > 1 && (
          <nav aria-label="Transaction pages" className="flex items-center justify-between gap-3 border-t border-line px-4 py-3 text-[13px] text-muted sm:px-5">
            <span className="num">Page {page + 1} of {pages}</span>
            <div className="flex gap-2">
              <Button size="sm" variant="secondary" disabled={page === 0} onClick={() => setPage(page > 1 ? String(page) : null)}>Previous</Button>
              <Button size="sm" variant="secondary" disabled={page + 1 >= pages} onClick={() => setPage(String(page + 2))}>Next</Button>
            </div>
          </nav>
        )}
      </Card>

      <AddTransaction open={adding} onClose={() => setAdding(false)} sources={sources} profileId={profileId}
        onAdded={async (r) => { setAdding(false); await load(); refresh({ rerun: true }); toast(`Added and categorised as ${r.category}${r.category_source === 'model' ? ' (suggested by the model)' : ''}`, { tone: 'good' }) }} />
      <Drawer open={!!open} onClose={() => setOpen(null)} title={open?.merchant || open?.description || ''} subtitle={open && `${dateLabel(open.date)} · ${open.source}`}
        footer={open && !readOnly && <Button variant="danger" icon={Trash2} onClick={() => remove(open)} disabled={busy}>Delete transaction</Button>}>
        {open && <>
          <div className={cx('num text-title font-semibold', open.type === 'credit' ? 'text-good' : 'text-ink')}>{open.type === 'credit' ? '+' : ''}{inr(open.amount, { compact: false })}</div>
          <div className="mt-1 font-mono text-micro break-all text-faint">{open.description}</div>
          <div className="mt-6">
            <Field label="Category" hint={open.category_source === 'model' ? `Suggested by the categoriser (${Math.round((open.confidence || 0) * 100)}% confidence). Accept it or choose another.` : `Set by: ${open.category_source || 'not set'}`}>
              <Select value={open.category || ''} disabled={readOnly || busy} onChange={(e) => recat(open, e.target.value)}>
                {!open.category && <option value="" disabled>Choose a category</option>}
                {data.categories.map((c) => <option key={c}>{c}</option>)}
              </Select>
            </Field>
            {open.category_source === 'model' && open.category && !readOnly && (
              <div className="mt-3 flex flex-wrap gap-2">
                <Button size="sm" variant="secondary" onClick={() => decide(open, 'accept')} disabled={busy}>Accept “{open.category}”</Button>
                <Button size="sm" variant="quiet" onClick={() => decide(open, 'reject')} disabled={busy}>Reject suggestion</Button>
              </div>
            )}
            {open.needs_review && open.review_reason && <div className="mt-3"><Note tone="warn">{open.review_reason}</Note></div>}
          </div>
          <div className="mt-6">
            <h3 className="text-[13px] font-medium text-ink-2">Unusual-spending check</h3>
            {open.flagged ? <div className="mt-2 space-y-2"><Badge tone={open.severity}>{open.severity} · flagged as unusual</Badge>
              <ul className="list-disc space-y-1 pl-5 text-sm text-ink-2">{open.reasons.map((x) => <li key={x}>{x}</li>)}</ul>
              <p className="text-micro text-faint">Unusual for you compared with your own history.</p></div>
              : <p className="mt-1 text-sm text-muted">{open.anomaly_score != null ? `Not flagged (anomaly score ${open.anomaly_score.toFixed(2)}).` : 'Not scored (fixed payments such as rent, EMIs and SIPs are not scored).'}</p>}
          </div>
          <div className="mt-6"><KV rows={[['Type', open.type === 'credit' ? 'Money in' : 'Money out'], ['Account', open.source], open.balance_after != null && ['Balance after', inr(open.balance_after, { compact: false })], open.import_id && ['Imported', `import #${open.import_id}`]]} /></div>
          <div className="mt-6"><AskAbout q={`Tell me about my ${inr(open.amount, { compact: false })} transaction at ${open.merchant || open.description} on ${open.date}.`} /></div>
          {readOnly && <div className="mt-6"><Note tone="warn">This demo template is read-only. Explore a demo copy to make changes.</Note></div>}
        </>}
      </Drawer>
    </>
  )
}

function AddTransaction({ open, onClose, sources, profileId, onAdded }) {
  const [tx, setTx] = useState({ date: new Date().toISOString().slice(0, 10), amount: '', description: '', type: 'debit', target: '' })
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const target = tx.target || sources[0]?.[0] || ''
  const submit = async (e) => {
    e.preventDefault()
    if (!target) { setErr('Add a bank account or card first (Data → Records).'); return }
    setBusy(true); setErr(null)
    try {
      const r = await api.addTransaction(profileId, { date: tx.date, amount: Number(tx.amount), description: tx.description, type: tx.type,
        ...(target.startsWith('card:') ? { card_id: Number(target.split(':')[1]) } : { account_id: Number(target.split(':')[1]) }) })
      setTx({ ...tx, amount: '', description: '' }); onAdded(r)
    } catch (x) { setErr(x.message) } finally { setBusy(false) }
  }
  return (
    <Drawer open={open} onClose={onClose} title="Add a transaction" subtitle="Leave the category to the model: it reads the description.">
      <form onSubmit={submit} className="grid gap-4 sm:grid-cols-2">
        <Field label="Date"><Input type="date" required value={tx.date} onChange={(e) => setTx({ ...tx, date: e.target.value })} /></Field>
        <Field label="Amount (₹)"><Input type="number" min={1} step="any" required inputMode="decimal" value={tx.amount} onChange={(e) => setTx({ ...tx, amount: e.target.value })} /></Field>
        <div className="sm:col-span-2"><Field label="Description as on the statement" hint="For example UPI/DR/123456789012/ZOMATO/HDFC/zomato@ybl"><Input required minLength={2} value={tx.description} onChange={(e) => setTx({ ...tx, description: e.target.value })} autoComplete="off" /></Field></div>
        <Field label="Account or card"><Select value={target} onChange={(e) => setTx({ ...tx, target: e.target.value })}>{sources.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</Select></Field>
        <Field label="Type"><Select value={tx.type} onChange={(e) => setTx({ ...tx, type: e.target.value })}><option value="debit">Money out</option><option value="credit">Money in (refund)</option></Select></Field>
        {err && <p role="alert" className="text-[13px] text-bad sm:col-span-2">{err}</p>}
        <div className="flex gap-2 sm:col-span-2"><Button type="submit" icon={Plus} loading={busy}>Add transaction</Button><Button type="button" variant="secondary" onClick={onClose}>Cancel</Button></div>
      </form>
    </Drawer>
  )
}
