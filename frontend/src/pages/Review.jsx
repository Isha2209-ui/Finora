import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Check, ChevronDown, ChevronRight, Trash2 } from 'lucide-react'
import { api } from '../api'
import { Badge, Button, Card, Empty, ErrorBox, Loading, Note, PageHeader, Select, Table, cx } from '../components/ui.jsx'
import { dateLabel, inr, num } from '../format'
import { useAsync, useFinora } from '../store.jsx'

const SPENDING = ['Rent', 'Groceries', 'Utilities', 'Health', 'Education', 'Insurance', 'Fuel', 'Dining', 'Shopping', 'Travel', 'Entertainment',
  'Subscriptions', 'EMI', 'Cash']
const MOVES = ['Transfer', 'Card Payment', 'Investment']

export default function Review() {
  const { profileId, profile, refresh } = useFinora()
  const [params] = useSearchParams()
  const importId = params.get('import')
  const q = useAsync(() => api.review(profileId, { import_id: importId }), [profileId, importId])
  const rules = useAsync(() => api.categoryRules(profileId), [profileId])
  const [err, setErr] = useState(null)
  const readOnly = profile?.kind === 'template'
  const after = () => { q.reload(); rules.reload(); refresh({ rerun: false }) }
  return (
    <>
      <PageHeader title="Review & Corrections" subtitle="Rows Finora is not sure about, grouped by who the money went to or came from. One decision fixes the whole group; tick “remember” and the next statement from the same counterparty is classified your way.">
        <Link to="/statements"><Button variant="ghost">Import statements</Button></Link>
        <Link to="/insights"><Button variant="ghost">Statement Intelligence</Button></Link>
      </PageHeader>
      {err && <div className="mb-4"><ErrorBox message={err} /></div>}
      {importId && <div className="mb-3"><Note>Showing rows from one import. <Link className="underline" to="/review">Show everything that needs review</Link>.</Note></div>}
      {q.loading && !q.data ? <Loading /> : q.error ? <ErrorBox message={q.error} onRetry={q.reload} /> : !q.data.groups.length ? (
        <Card><Empty title="Nothing to review">Every imported row was classified confidently, or you have already reviewed it. Corrections are still possible from <Link className="text-accent underline" to="/transactions">Transaction Intelligence</Link>.</Empty></Card>
      ) : (
        <>
          <p className="mb-3 text-sm text-muted"><b className="text-ink num">{num(q.data.total)}</b> rows need a decision, in {num(q.data.groups.length)} groups.</p>
          <div className="space-y-3">{q.data.groups.map((g) => <Group key={`${g.merchant}|${g.type}|${g.classified_as}`} g={g} profileId={profileId} readOnly={readOnly}
            incomeTypes={q.data.income_types} onDone={after} onError={setErr} />)}</div>
        </>
      )}
      <Card className="mt-4" title="Remembered corrections" subtitle="Applied to future imports before the ML model is consulted" pad={false}>
        {rules.data?.length ? <Table dense rows={rules.data} columns={[
          { key: 'merchant_key', label: 'Counterparty' }, { key: 'category', label: 'Always classified as', render: (r) => <Badge tone="good">{r.category}</Badge> },
          { key: 'created_at', label: 'Since', render: (r) => dateLabel(r.created_at) },
          { key: 'x', label: '', render: (r) => !readOnly && <button className="text-faint hover:text-bad" onClick={async () => { await api.deleteRule(profileId, r.id); rules.reload() }}><Trash2 size={14} /></button> }]} />
          : <p className="px-5 pb-4 text-sm text-muted">None yet.</p>}
      </Card>
    </>
  )
}

function Group({ g, profileId, readOnly, incomeTypes, onDone, onError }) {
  const [open, setOpen] = useState(false)
  const [choice, setChoice] = useState('')
  const [remember, setRemember] = useState(true)
  const [busy, setBusy] = useState(false)
  const credit = g.type === 'credit'
  const items = g.items.map((i) => ({ kind: i.kind, id: i.id }))
  const run = async (fn) => { setBusy(true); onError(null); try { await fn(); onDone() } catch (e) { onError(e.message) } finally { setBusy(false) } }
  const apply = () => run(() => {
    const [kind, value] = choice.split(':')
    return api.reviewClassify(profileId, { items, remember, apply_to_similar: true, ...(kind === 'income' ? { income_type: value } : { category: value }) })
  })
  const confirm = () => run(() => api.reviewConfirm(profileId, items))
  return (
    <Card pad={false}>
      <div className="flex flex-wrap items-center gap-3 px-5 py-3">
        <button onClick={() => setOpen(!open)} className="text-faint hover:text-ink">{open ? <ChevronDown size={16} /> : <ChevronRight size={16} />}</button>
        <div className="min-w-[180px] flex-1">
          <div className="flex items-center gap-2 font-medium">{g.merchant} <Badge tone={credit ? 'good' : 'neutral'}>{credit ? 'money in' : 'money out'}</Badge></div>
          <div className="mt-0.5 text-xs text-muted">{num(g.count)} row{g.count > 1 ? 's' : ''} · {inr(g.total)} · now: <b>{g.classified_as}</b></div>
          {g.reason && <div className="mt-0.5 text-xs text-warn">{g.reason}</div>}
        </div>
        {!readOnly && (
          <div className="flex flex-wrap items-center gap-2">
            <div className="w-60"><Select value={choice} onChange={(e) => setChoice(e.target.value)}>
              <option value="">It is actually…</option>
              {credit && <optgroup label="Income">{incomeTypes.map((t) => <option key={t} value={`income:${t}`}>{t}</option>)}</optgroup>}
              <optgroup label="Not spending">{MOVES.map((c) => <option key={c} value={`cat:${c}`}>{c === 'Transfer' ? 'Transfer (my own money / repayment)' : c}</option>)}</optgroup>
              <optgroup label={credit ? 'Refund of…' : 'Spending'}>{SPENDING.map((c) => <option key={c} value={`cat:${c}`}>{c}</option>)}</optgroup>
            </Select></div>
            <label className="flex items-center gap-1 text-xs text-muted"><input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} /> remember</label>
            <Button loading={busy} disabled={!choice} onClick={apply}>Apply to {g.count}</Button>
            <Button variant="ghost" icon={Check} disabled={busy} onClick={confirm}>Looks right</Button>
          </div>
        )}
      </div>
      {open && <div className={cx('border-t border-line')}><Table dense rows={g.items} columns={[
        { key: 'date', label: 'Date', render: (r) => dateLabel(r.date) },
        { key: 'description', label: 'As on the statement', className: 'max-w-[420px] truncate font-mono text-[11.5px]' },
        { key: 'source', label: 'Account / card' },
        { key: 'confidence', label: 'Confidence', right: true, render: (r) => r.confidence == null ? '—' : `${Math.round(r.confidence * 100)}%` },
        { key: 'amount', label: 'Amount', right: true, render: (r) => <span className={r.type === 'credit' ? 'text-good' : ''}>{inr(r.amount, { compact: false })}</span> }]} /></div>}
    </Card>
  )
}
