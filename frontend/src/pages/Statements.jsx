import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { AlertTriangle, CheckCircle2, Circle, FileSpreadsheet, Loader2, RotateCcw, ShieldCheck, Upload, X } from 'lucide-react'
import { api } from '../api'
import { Badge, Button, Card, ErrorBox, Field, Input, KV, Note, PageHeader, Select, Table, cx } from '../components/ui.jsx'
import { dateLabel, inr, num } from '../format'
import { useFinora } from '../store.jsx'

const ROLE_LABEL = { date: 'Date', description: 'Description / narration', debit: 'Debit (money out)', credit: 'Credit (money in)',
  amount: 'Single amount column', drcr: 'Dr/Cr indicator', balance: 'Running balance', value_date: 'Value date', ref: 'Reference no.', category: 'Category' }
const STAGES = [['reading', 'Reading the file'], ['parsing', 'Dates, amounts and balances'], ['categorising', 'ML categorisation'],
  ['patterns', 'Salary, transfers, refunds'], ['duplicates', 'Duplicate check'], ['saving', 'Saving'], ['analysis', 'Refreshing your analysis']]
const ORDER = STAGES.map((s) => s[0])

// A small SYNTHETIC statement for trying the flow (clearly labelled; not anyone's data).
function sampleStatement() {
  const lines = ['SAMPLE BANK (synthetic demo file),,,,', ',,,,', 'Date,Narration,Withdrawal,Deposit,Balance']
  let bal = 60000
  const rows = []
  const add = (d, desc, out, inn) => rows.push([d, desc, out, inn])
  for (const [m, y] of [['08', 2026], ['09', 2026], ['10', 2026]]) {
    add(`01/${m}/${y}`, 'NEFT CR-HDFC0000123-ACME TECHNOLOGIES PVT LTD-PAYOUT', 0, 82000)
    add(`03/${m}/${y}`, 'NACH/DR/HDFC BANK EMI/88231190', 12500, 0)
    add(`05/${m}/${y}`, 'IMPS/P2A/412345678901/RENT FLAT', 22000, 0)
    add(`07/${m}/${y}`, 'UPI/DR/402918376152/NETFLIX/YESB/netflix@ybl/Payment', 649, 0)
    add(`08/${m}/${y}`, 'UPI/DR/402918376152/SWIGGY/YESB/swiggy@ybl/Payment', 540 + Number(m) * 7, 0)
    add(`10/${m}/${y}`, 'BSE STAR MF SIP 77812231', 8000, 0)
    add(`12/${m}/${y}`, 'BIL/BPAY/556677889/AIRTEL/AUTOPAY', 799, 0)
    add(`14/${m}/${y}`, 'UPI/DR/402918371111/BIGBASKET/ICIC/bigbasket@ybl/Payment', 2900 + Number(m) * 11, 0)
    add(`16/${m}/${y}`, 'POS 4521XXXXXXXX8812 AMAZON BANGALORE', 1999, 0)
    add(`18/${m}/${y}`, 'ATM WDL HDFC ATM PUNE', 3000, 0)
    add(`22/${m}/${y}`, 'UPI/CR/509912345678/RAHUL SHARMA/okaxis/dinner split', 0, 850)
  }
  add('20/10/2026', 'REFUND POS 4521XXXXXXXX8812 AMAZON BANGALORE', 0, 1999)
  add('25/10/2026', 'POS 4521XXXXXXXX8812 CROMA MUMBAI', 46500, 0)
  const key = (d) => d.split('/').reverse().join('')
  rows.sort((a, b) => key(a[0]).localeCompare(key(b[0])))          // date order, so the running balance reconciles
  for (const [d, desc, out, inn] of rows) { bal += (inn || 0) - (out || 0); lines.push(`${d},"${desc}",${out || ''},${inn || ''},${bal.toFixed(2)}`) }
  return new File([lines.join('\n')], 'sample_synthetic_statement.csv', { type: 'text/csv' })
}

export default function Statements() {
  const { profileId, profile, refresh } = useFinora()
  const readOnly = profile?.kind === 'template'
  const [phase, setPhase] = useState('pick')        // pick | preview | running | result
  const [imp, setImp] = useState(null)
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)
  const [history, setHistory] = useState(null)
  const loadHistory = () => api.imports(profileId).then(setHistory).catch(() => {})
  useEffect(() => { loadHistory() }, [profileId]) // eslint-disable-line react-hooks/exhaustive-deps

  const upload = async (file) => {
    if (!file) return
    setErr(null); setBusy(true)
    try { const p = await api.importPreview(profileId, file); setImp(p); setPhase('preview') }
    catch (e) { setErr(e.message) } finally { setBusy(false) }
  }
  const reset = () => { setImp(null); setPhase('pick'); setErr(null); loadHistory() }

  return (
    <>
      <PageHeader title="Import Statements" subtitle="Bring in one or two years of bank or credit-card statements (CSV, up to 25 MB / 150,000 rows). Finora detects the layout, categorises every line with its ML model, finds salary, transfers, refunds and card payments, and feeds everything into the same analysis as the rest of your data.">
        <Link to="/insights"><Button variant="ghost">Statement Intelligence</Button></Link>
        <Link to="/review"><Button variant="ghost">Review & corrections</Button></Link>
      </PageHeader>
      {err && <div className="mb-4"><ErrorBox message={err} /></div>}
      {readOnly && <div className="mb-4"><Note tone="warn">This is a read-only demo template. Open your demo copy (sandbox) or your own profile to import statements.</Note></div>}
      {phase === 'pick' && !readOnly && <Picker onFile={upload} busy={busy} />}
      {phase === 'preview' && imp && <Preview imp={imp} profileId={profileId} onCancel={reset} onError={setErr}
        onStarted={(s) => { setImp({ ...imp, ...s }); setPhase('running') }} />}
      {phase === 'running' && imp && <Progress profileId={profileId} imp={imp}
        onDone={(s) => { setImp(s); setPhase('result'); refresh({ rerun: false }); loadHistory() }} />}
      {phase === 'result' && imp && <Result imp={imp} profileId={profileId} onAgain={reset} onUndone={() => { reset(); refresh({ rerun: false }) }} />}
      <History history={history} profileId={profileId} readOnly={readOnly} onChange={() => { loadHistory(); refresh({ rerun: false }) }} />
    </>
  )
}

function Picker({ onFile, busy }) {
  const ref = useRef(null)
  const [over, setOver] = useState(false)
  return (
    <Card>
      <div onDragOver={(e) => { e.preventDefault(); setOver(true) }} onDragLeave={() => setOver(false)}
        onDrop={(e) => { e.preventDefault(); setOver(false); onFile(e.dataTransfer.files[0]) }}
        className={cx('flex flex-col items-center gap-3 rounded-2xl border-2 border-dashed px-6 py-10 text-center transition', over ? 'border-accent bg-accent/5' : 'border-line')}>
        {busy ? <Loader2 className="animate-spin text-accent" size={28} /> : <FileSpreadsheet className="text-accent" size={28} />}
        <div className="text-sm font-medium">{busy ? 'Reading the file and detecting its layout…' : 'Drop a statement CSV here'}</div>
        <div className="max-w-xl text-xs text-muted">Most Indian bank and card exports work as they are: header lines above the table and summaries below it are skipped, any column order, comma / semicolon / tab separated, newest-first or oldest-first. Nothing is saved until you confirm.</div>
        <input ref={ref} type="file" accept=".csv,.txt,text/csv" hidden onChange={(e) => onFile(e.target.files[0])} />
        <div className="flex gap-2"><Button icon={Upload} loading={busy} onClick={() => ref.current.click()}>Choose file</Button>
          <Button variant="ghost" disabled={busy} onClick={() => onFile(sampleStatement())}>Try a synthetic sample</Button></div>
      </div>
      <div className="mt-3 grid gap-2 text-xs text-muted md:grid-cols-3">
        <div className="flex gap-2"><ShieldCheck size={14} className="mt-0.5 shrink-0 text-accent" /> Finora never connects to your bank. Only the file you choose is read, and it is deleted once the import finishes or is cancelled (a preview you never confirm is deleted after 24 hours).</div>
        <div className="flex gap-2"><ShieldCheck size={14} className="mt-0.5 shrink-0 text-accent" /> An account balance is only updated from a statement whose running balances reconcile, and you can decline it.</div>
        <div className="flex gap-2"><ShieldCheck size={14} className="mt-0.5 shrink-0 text-accent" /> Money from senders Finora does not recognise is not counted as income until you confirm it.</div>
      </div>
    </Card>
  )
}

function Preview({ imp, profileId, onCancel, onStarted, onError }) {
  const d = imp.detection
  const needsMap = !!d.needs_mapping
  const [kind, setKind] = useState(d.suggested_kind || 'bank')
  const [target, setTarget] = useState(() => (d.suggested_kind === 'card' ? (imp.cards[0] ? `card:${imp.cards[0].id}` : '') : (imp.accounts[0] ? `account:${imp.accounts[0].id}` : 'new')))
  const [mapping, setMapping] = useState(d.mapping || {})
  const [editMap, setEditMap] = useState(needsMap)
  const [newAcc, setNewAcc] = useState({ bank_name: '', last4: '', account_type: 'savings', balance: '' })
  const [updateBalance, setUpdateBalance] = useState(false)
  const [overlapOk, setOverlapOk] = useState(false)
  const [again, setAgain] = useState(false)
  const [busy, setBusy] = useState(false)
  const b = d.balance || {}
  const acc = target.startsWith('account:') ? imp.accounts.find((a) => `account:${a.id}` === target) : null
  const options = kind === 'card' ? imp.cards.map((c) => [`card:${c.id}`, c.label]) : [...imp.accounts.map((a) => [`account:${a.id}`, a.label]), ['new', '+ Create a new account from this statement']]
  useEffect(() => { if (!options.find(([v]) => v === target)) setTarget(options[0]?.[0] || '') }, [kind]) // eslint-disable-line react-hooks/exhaustive-deps
  // a statement-verified balance may be refreshed by a newer statement by default; a balance you typed only if you tick the box
  useEffect(() => { setUpdateBalance(acc?.balance_source === 'statement') }, [target]) // eslint-disable-line react-hooks/exhaustive-deps
  const tgtKey = target === 'new' ? null : target.replace(':', '|')
  const clash = (d.overlap || []).find((o) => o.share_pct >= 50 && `${o.kind}|${o.id}` !== tgtKey)
  const partial = (d.overlap || []).filter((o) => o.share_pct < 50 && `${o.kind}|${o.id}` !== tgtKey)

  const start = async () => {
    setBusy(true); onError(null)
    try {
      const body = { statement_kind: kind, update_balance: updateBalance, allow_same_file: again, allow_overlap: overlapOk }
      if (target.startsWith('account:')) body.account_id = Number(target.split(':')[1])
      else if (target.startsWith('card:')) body.card_id = Number(target.split(':')[1])
      else body.new_account = { bank_name: newAcc.bank_name, last4: newAcc.last4, account_type: newAcc.account_type, ...(newAcc.balance !== '' ? { balance: Number(newAcc.balance) } : {}) }
      if (editMap) body.mapping = mapping
      onStarted(await api.importStart(profileId, imp.id, body))
    } catch (e) { onError(e.message) } finally { setBusy(false) }
  }
  const cancel = async () => { try { await api.importCancel(profileId, imp.id) } catch { /* already gone */ } onCancel() }

  return (
    <div className="grid gap-4 xl:grid-cols-3">
      <Card className="xl:col-span-2" title={`${imp.filename} · what Finora found`} subtitle="Check this before importing. Nothing has been saved yet."
        action={<Badge tone={needsMap ? 'warn' : 'accent'}>{d.layout}</Badge>}>
        {needsMap && <div className="mb-3"><Note tone="warn">Finora could not recognise these column names. Tell it which column is which below (missing: {d.missing.join(', ')}).</Note></div>}
        {!needsMap && (
          <div className="grid gap-3 md:grid-cols-4">
            <Mini label="Rows" value={num(imp.rows_total)} sub={`${num(d.rows_valid)} of ${num(d.rows_parsed)} read cleanly`} />
            <Mini label="Period" value={d.date_from ? `${dateLabel(d.date_from)} – ${dateLabel(d.date_to)}` : '—'} sub={`${d.months_covered} months in the preview · ${d.file_order}`} />
            <Mini label="Amounts" value={d.layout_kind} sub={`${num(d.debits)} debits · ${num(d.credits)} credits`} />
            <Mini label="Format" value={d.date_format ? d.date_format.replaceAll('%', '') : 'mixed'} sub={`${d.encoding} · ${d.delimiter} separated · header on line ${d.header_line}`} />
          </div>
        )}
        {!needsMap && (
          <div className={cx('mt-3 flex items-start gap-2 rounded-xl border px-3 py-2 text-xs', b.verified ? 'border-good/30 bg-good/10 text-good' : 'border-line bg-raised/50 text-muted')}>
            {b.verified ? <CheckCircle2 size={15} className="mt-0.5 shrink-0" /> : <AlertTriangle size={15} className="mt-0.5 shrink-0" />}
            <div>{b.verified ? <>Running balances reconcile ({b.reconciled_pct}% of {num(b.checked)} rows in the preview). Closing balance <b className="num">{inr(b.closing_balance, { compact: false })}</b> on {dateLabel(b.closing_date)}; the full file is checked again during import.</>
              : b.present ? <>A balance column exists but {b.reason?.toLowerCase() || 'it does not reconcile'} No account balance will be changed.</>
                : <>No running balance in this file, so Finora cannot establish a balance from it. Your account balance stays as it is.</>}</div>
          </div>
        )}
        {(d.warnings || []).map((w) => <div key={w} className="mt-2"><Note tone="warn">{w}</Note></div>)}
        {Object.keys(d.dropped || {}).length > 0 && <p className="mt-2 text-xs text-muted">Skipped in the preview: {Object.entries(d.dropped).map(([k, v]) => `${v} × ${k}`).join(' · ')}</p>}
        {d.sample?.length > 0 && <div className="mt-3"><Table dense rows={d.sample} columns={[
          { key: 'date', label: 'Date', render: (r) => dateLabel(r.date) },
          { key: 'description', label: 'Description', className: 'max-w-[380px] truncate font-mono text-[11.5px]' },
          { key: 'amount', label: 'Amount', right: true, render: (r) => <span className={r.type === 'credit' ? 'text-good' : ''}>{r.type === 'credit' ? '+' : '−'}{inr(r.amount, { compact: false })}</span> },
          { key: 'balance', label: 'Balance', right: true, render: (r) => r.balance == null ? '—' : inr(r.balance, { compact: false }) }]} /></div>}
        {needsMap && d.raw_sample && <div className="mt-3 overflow-x-auto"><table className="w-full text-xs"><thead><tr>{d.headers.map((h) => <th key={h} className="border-b border-line px-2 py-1 text-left text-faint">{h}</th>)}</tr></thead>
          <tbody>{d.raw_sample.map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j} className="border-b border-line/50 px-2 py-1 font-mono">{c}</td>)}</tr>)}</tbody></table></div>}
        <div className="mt-3">
          {!needsMap && <button className="text-xs text-accent hover:underline" onClick={() => setEditMap(!editMap)}>{editMap ? 'Use the detected columns' : 'Adjust column mapping'}</button>}
          {editMap && (
            <div className="mt-2 grid gap-2 md:grid-cols-3">
              {Object.keys(ROLE_LABEL).map((role) => (
                <Field key={role} label={ROLE_LABEL[role]}>
                  <Select value={mapping[role] || ''} onChange={(e) => setMapping({ ...mapping, [role]: e.target.value || null })}>
                    <option value="">— not in this file —</option>{d.headers.map((h) => <option key={h} value={h}>{h}</option>)}
                  </Select>
                </Field>
              ))}
            </div>
          )}
        </div>
      </Card>

      <Card title="Where does it belong?" subtitle="Rows are attributed to this account or card">
        <div className="space-y-3">
          <Field label="Statement type">
            <div className="grid grid-cols-2 gap-2">{[['bank', 'Bank account'], ['card', 'Credit card']].map(([k, l]) => (
              <button key={k} onClick={() => setKind(k)} className={cx('rounded-xl border px-3 py-2 text-sm', kind === k ? 'border-accent bg-accent/10 text-accent' : 'border-line text-muted')}>{l}</button>))}</div>
          </Field>
          {options.length ? <Field label={kind === 'card' ? 'Card' : 'Account'}><Select value={target} onChange={(e) => setTarget(e.target.value)}>{options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</Select></Field>
            : <Note tone="warn">Add this card under <Link className="underline" to="/records">My Data</Link> first, then import its statement.</Note>}
          {target === 'new' && (
            <div className="grid grid-cols-2 gap-2">
              <div className="col-span-2"><Field label="Bank name"><Input value={newAcc.bank_name} onChange={(e) => setNewAcc({ ...newAcc, bank_name: e.target.value })} placeholder="HDFC Bank" /></Field></div>
              <Field label="Last 4 digits"><Input value={newAcc.last4} maxLength={4} onChange={(e) => setNewAcc({ ...newAcc, last4: e.target.value.replace(/\D/g, '') })} /></Field>
              <Field label="Type"><Select value={newAcc.account_type} onChange={(e) => setNewAcc({ ...newAcc, account_type: e.target.value })}><option value="savings">Savings</option><option value="salary">Salary</option><option value="current">Current</option></Select></Field>
              <div className="col-span-2"><Field label="Current balance (₹)" hint={b.verified ? 'Leave empty to use the verified closing balance from the statement.' : 'Required: this statement has no balance Finora can verify.'}>
                <Input type="number" value={newAcc.balance} onChange={(e) => setNewAcc({ ...newAcc, balance: e.target.value })} /></Field></div>
            </div>
          )}
          {kind === 'bank' && acc && b.verified && (
            <label className="flex items-start gap-2 text-xs text-muted"><input type="checkbox" className="mt-0.5" checked={updateBalance} onChange={(e) => setUpdateBalance(e.target.checked)} />
              <span>{acc.balance_source === 'statement' ? `Refresh ${acc.label}'s balance` : `Replace the balance you entered for ${acc.label} (${inr(acc.balance)})`} with the statement's verified closing balance ({inr(b.closing_balance)} as of {dateLabel(b.closing_date)}).{acc.balance_as_of ? ` Now recorded: ${inr(acc.balance)} as of ${dateLabel(acc.balance_as_of)}.` : ' Left unticked, your balance stays as it is.'}</span></label>
          )}
          {!clash && partial.length > 0 && <Note>{partial.map((o) => `${num(o.rows_matching)} rows are already recorded on ${o.label}`).join('; ')}. They will be skipped, not counted twice.</Note>}
          {clash && (
            <label className="flex items-start gap-2 rounded-xl border border-warn/30 bg-warn/10 p-2 text-xs text-warn"><input type="checkbox" className="mt-0.5" checked={overlapOk} onChange={(e) => setOverlapOk(e.target.checked)} />
              <span>{num(clash.rows_matching)} of these rows ({clash.share_pct}%) are already recorded on <b>{clash.label}</b>. If this is the same statement, attach it there instead. Import to the chosen {kind === 'card' ? 'card' : 'account'} anyway?</span></label>
          )}
          {imp.same_file_imported?.length > 0 && (
            <label className="flex items-start gap-2 rounded-xl border border-warn/30 bg-warn/10 p-2 text-xs text-warn"><input type="checkbox" className="mt-0.5" checked={again} onChange={(e) => setAgain(e.target.checked)} />
              <span>This exact file was imported on {dateLabel(imp.same_file_imported[0].created_at)}. Import again anyway? Rows already present are skipped.</span></label>
          )}
          <div className="flex gap-2 pt-1"><Button loading={busy} disabled={!target || (imp.same_file_imported?.length > 0 && !again) || (clash && !overlapOk)} onClick={start} className="flex-1">Import this statement</Button>
            <Button variant="ghost" icon={X} onClick={cancel}>Cancel</Button></div>
        </div>
      </Card>
    </div>
  )
}

function Mini({ label, value, sub }) {
  return <div className="rounded-xl border border-line bg-raised/40 p-3"><div className="text-[11px] text-muted">{label}</div><div className="mt-0.5 truncate text-sm font-semibold">{value}</div>{sub && <div className="mt-0.5 text-[11px] text-faint">{sub}</div>}</div>
}

function Progress({ profileId, imp, onDone }) {
  const [s, setS] = useState(imp)
  const [cancelling, setCancelling] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  useEffect(() => { if (s.stage !== 'analysis') return; const t0 = Date.now(); const t = setInterval(() => setElapsed(Math.round((Date.now() - t0) / 1000)), 1000); return () => clearInterval(t) }, [s.stage])
  useEffect(() => {
    let alive = true
    const tick = async () => {
      try {
        const x = await api.importStatus(profileId, imp.id)
        if (!alive) return
        setS(x)
        if (['done', 'failed', 'cancelled'].includes(x.status)) { onDone(x); return }
      } catch { /* keep polling */ }
      if (alive) setTimeout(tick, 400)
    }
    tick()
    return () => { alive = false }
  }, [profileId, imp.id]) // eslint-disable-line react-hooks/exhaustive-deps
  const cur = ORDER.indexOf(s.stage)
  return (
    <Card title={`Importing ${imp.filename}`} subtitle="You can leave this page; the import continues in the background.">
      <div className="flex items-center justify-between text-sm"><span className="font-medium">{s.stage_label || 'Starting…'}</span><span className="num text-muted">{Math.round(s.pct || 0)}%</span></div>
      <div className="mt-2 h-2.5 overflow-hidden rounded-full bg-raised"><div className="h-full rounded-full bg-accent transition-all duration-300" style={{ width: `${s.pct || 1}%` }} /></div>
      {s.stage === 'analysis' && <div className="mt-1 text-xs text-muted">Your transactions are saved. Recomputing every figure (cash flow, health score, models, recommendations) with them: <span className="num">{elapsed}s</span>. Large files can take 15–20 s.</div>}
      {s.stage_total > 0 && s.stage !== 'analysis' && <div className="mt-1 text-xs text-faint num">{num(s.stage_done)} / {num(s.stage_total)} {s.stage === 'categorising' ? 'distinct narrations' : 'rows'}</div>}
      <ol className="mt-4 grid gap-1.5 text-xs md:grid-cols-4">{STAGES.map(([k, l], i) => (
        <li key={k} className={cx('flex items-center gap-1.5', i < cur ? 'text-good' : i === cur ? 'text-accent' : 'text-faint')}>
          {i < cur ? <CheckCircle2 size={13} /> : i === cur ? <Loader2 size={13} className="animate-spin" /> : <Circle size={13} />} {l}</li>))}</ol>
      {s.stage !== 'analysis' && <div className="mt-4"><Button variant="ghost" icon={X} loading={cancelling} onClick={async () => { setCancelling(true); try { await api.importCancel(profileId, imp.id) } catch { /* finished */ } }}>Cancel import</Button></div>}
    </Card>
  )
}

function Result({ imp, profileId, onAgain, onUndone }) {
  const [busy, setBusy] = useState(false)
  if (imp.status !== 'done') {
    return <Card><div className="flex items-start gap-3 text-sm"><AlertTriangle className="text-warn" size={18} /><div><div className="font-medium">{imp.status === 'cancelled' ? 'Import cancelled' : 'Import failed'}</div>
      <div className="mt-1 text-muted">{imp.error}</div><Button className="mt-3" variant="ghost" onClick={onAgain}>Import another file</Button></div></div></Card>
  }
  const s = imp.summary
  const bal = s.balance || {}
  const decided = s.decided_by || {}
  const undo = async () => { if (!window.confirm('Remove every row this import added and restore the previous balance?')) return; setBusy(true); try { await api.importUndo(profileId, imp.id); onUndone() } finally { setBusy(false) } }
  return (
    <div className="grid gap-4 xl:grid-cols-3">
      <Card className="xl:col-span-2" title={`${imp.filename} imported`} subtitle={`${dateLabel(s.date_from)} – ${dateLabel(s.date_to)} · ${s.months_covered} months · ${num(s.rows_per_second)} rows/s · ${s.seconds}s`}
        action={<Badge tone="good"><CheckCircle2 size={12} /> Done</Badge>}>
        <div className="grid gap-3 md:grid-cols-4">
          <Mini label="Transactions added" value={num(s.transactions_added)} sub={`${num(s.categorised_by_model)} categorised by the ML model`} />
          <Mini label="Income records" value={num(s.income_records_added)} sub={Object.entries(s.income_by_source).map(([k, v]) => `${k} ${inr(v)}`).join(' · ') || 'none recognised'} />
          <Mini label="Already imported" value={num(s.duplicates_skipped)} sub="skipped, never counted twice" />
          <Mini label="Needs your review" value={num(s.needs_review)} sub={`${num(s.unrecognised_credits)} unrecognised credits`} />
        </div>
        <div className="mt-3 grid gap-3 md:grid-cols-2">
          <KV rows={[['Own-account transfers', num(s.transfers)], ['Card bill payments', num(s.card_payments)], ['Refunds (reduce spending)', num(s.refunds)],
            ['Invested (cash flow)', inr(s.investment_outflow)], s.possible_duplicates ? ['Possible duplicates of hand-entered rows', num(s.possible_duplicates), 'warn'] : null]} />
          <div>
            <div className="mb-1 text-xs text-muted">Who decided each row</div>
            <div className="flex flex-wrap gap-1.5">{Object.entries(decided).map(([k, v]) => <Badge key={k} tone={k === 'model' ? 'accent' : k === 'user_rule' ? 'good' : 'info'}>{{ model: 'ML model', rule: 'Rules', given: 'File', user_rule: 'Your rules' }[k] || k} · {num(v)}</Badge>)}</div>
            <div className="mb-1 mt-3 text-xs text-muted">Biggest spending categories</div>
            <div className="flex flex-wrap gap-1.5">{Object.entries(s.spend_by_category).slice(0, 8).map(([c, v]) => <Badge key={c}>{c} · {inr(v)}</Badge>)}</div>
            {s.money_moved && Object.keys(s.money_moved).length > 0 && <><div className="mb-1 mt-3 text-xs text-muted">Money moved, not spent</div>
              <div className="flex flex-wrap gap-1.5">{Object.entries(s.money_moved).map(([c, v]) => <Badge key={c} tone="info">{c} · {inr(v)}</Badge>)}</div></>}
          </div>
        </div>
        {s.rows_dropped > 0 && <p className="mt-3 text-xs text-muted">Not imported: {Object.entries(s.dropped).map(([k, v]) => `${v} × ${k}`).join(' · ')}</p>}
        {(s.warnings || []).map((w) => <div key={w} className="mt-2"><Note tone="warn">{w}</Note></div>)}
      </Card>
      <Card title="Balance" subtitle="Never invented">
        <div className={cx('rounded-xl border p-3 text-sm', bal.applied ? 'border-good/30 bg-good/10' : 'border-line bg-raised/40')}>
          {bal.verified && <div className="num text-lg font-semibold">{inr(bal.closing_balance, { compact: false })}</div>}
          {bal.verified && <div className="text-xs text-muted">verified closing balance on {dateLabel(bal.closing_date)} ({bal.reconciled_pct}% of running balances reconcile)</div>}
          <div className="mt-1 text-xs">{bal.reason}</div>
        </div>
        <div className="mt-4 flex flex-col gap-2">
          {s.needs_review > 0 && <Link to={`/review?import=${imp.id}`}><Button className="w-full">Review {num(s.needs_review)} uncertain rows</Button></Link>}
          <Link to="/insights"><Button variant="ghost" className="w-full">Open Statement Intelligence</Button></Link>
          <Button variant="ghost" onClick={onAgain}>Import another statement</Button>
          <Button variant="danger" icon={RotateCcw} loading={busy} onClick={undo}>Undo this import</Button>
        </div>
      </Card>
    </div>
  )
}

function History({ history, profileId, readOnly, onChange }) {
  const [busy, setBusy] = useState(null)
  if (!history?.items?.length) return null
  const label = (r) => r.card_id ? history.cards.find((c) => c.id === r.card_id)?.label : history.accounts.find((a) => a.id === r.account_id)?.label
  const tone = { done: 'good', failed: 'bad', cancelled: 'neutral', undone: 'neutral', running: 'accent', queued: 'accent', preview: 'warn' }
  const undo = async (r) => { if (!window.confirm(`Undo the import of ${r.filename}?`)) return; setBusy(r.id); try { await api.importUndo(profileId, r.id); onChange() } finally { setBusy(null) } }
  return (
    <Card className="mt-4" title="Import history" pad={false}>
      <Table dense rows={history.items} columns={[
        { key: 'filename', label: 'File', render: (r) => <span className="font-medium">{r.filename}</span> },
        { key: 'status', label: 'Status', render: (r) => <Badge tone={tone[r.status]}>{r.status}</Badge> },
        { key: 'to', label: 'Attributed to', render: (r) => r.summary?.target_label || label(r) || <span className="text-faint">—</span> },
        { key: 'period', label: 'Period', render: (r) => r.summary ? `${dateLabel(r.summary.date_from)} – ${dateLabel(r.summary.date_to)}` : '—' },
        { key: 'added', label: 'Added', right: true, render: (r) => r.summary ? num(r.summary.transactions_added + r.summary.income_records_added) : '—' },
        { key: 'dup', label: 'Skipped dupes', right: true, render: (r) => r.summary ? num(r.summary.duplicates_skipped) : '—' },
        { key: 'when', label: 'When', render: (r) => dateLabel(r.created_at) },
        { key: 'x', label: '', render: (r) => r.status === 'done' && !readOnly ? <button className="text-xs text-bad hover:underline" disabled={busy === r.id} onClick={() => undo(r)}>{busy === r.id ? 'Undoing…' : 'Undo'}</button> : r.error ? <span className="text-[11px] text-faint" title={r.error}>why?</span> : null },
      ]} />
    </Card>
  )
}
