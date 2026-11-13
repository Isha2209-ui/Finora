import { useEffect, useRef, useState } from 'react'
import { Plus, Trash2, Upload, UserPlus } from 'lucide-react'
import { api } from '../api'
import { Badge, Button, Card, ErrorBox, Field, Input, Loading, Note, PageHeader, Select, Table } from '../components/ui.jsx'
import { useAsync, useFinora } from '../store.jsx'

const SAMPLE = `Date,Narration,Withdrawal,Deposit
02/11/2026,UPI/DR/402918376152/SWIGGY/YESB/swiggy@ybl/Payment,640,
03/11/2026,POS 4521XXXXXXXX8812 AMAZON BANGALORE,2499,
04/11/2026,UPI/DR/402918371111/BIGBASKET/ICIC/bigbasket@ybl/Payment,3180,
05/11/2026,BIL/BPAY/556677889/AIRTEL/AUTOPAY,799,
06/11/2026,UPI/DR/402918372222/UBER/AXIS/uber@okaxis/Payment,412,
07/11/2026,POS 4521XXXXXXXX8812 MYNTRA MUMBAI,38500,
08/11/2026,ATM WDL HDFC ATM JAIPUR,5000,
`

export default function DataManagement() {
  const { profileId, analysis: a, refresh, select, signOut } = useFinora()
  const sum = useAsync(() => api.dataSummary(profileId), [profileId])
  const [targets, setTargets] = useState([])
  const [target, setTarget] = useState('')
  const [up, setUp] = useState(null)
  const [busy, setBusy] = useState(null)
  const [err, setErr] = useState(null)
  const file = useRef(null)
  const [tx, setTx] = useState({ date: '2026-10-30', amount: '', description: '', type: 'debit' })
  const [txMsg, setTxMsg] = useState(null)
  const [np, setNp] = useState({ name: '', pan: '', age: 28, monthly_income: 80000, bank_balance: 100000, employment_type: 'salaried' })
  const [prof, setProf] = useState({ age: a.profile.age, retirement_age_target: a.profile.retirement_age_target, occupation: a.profile.occupation, city: a.profile.city })
  useEffect(() => { api.accounts(profileId).then((d) => { const t = [...d.accounts.map((x) => [`account:${x.id}`, `${x.bank_name} ${x.account_masked}`]), ...d.card_ids.map((c) => [`card:${c.id}`, c.label])]; setTargets(t); setTarget(t[0]?.[0] || '') }).catch(() => {}) }, [profileId])

  const wrap = async (key, fn) => { setBusy(key); setErr(null); try { await fn() } catch (e) { setErr(e.message) } finally { setBusy(null) } }
  const upload = (f) => wrap('up', async () => { const r = await api.upload(profileId, f, target); setUp(r); sum.reload(); refresh({ rerun: true }) })
  const uploadSample = () => upload(new File([SAMPLE], 'sample_statement.csv', { type: 'text/csv' }))
  const addTx = (e) => { e.preventDefault(); wrap('tx', async () => { const r = await api.addTransaction(profileId, { ...tx, amount: Number(tx.amount), ...(target.startsWith('card:') ? { card_id: Number(target.split(':')[1]) } : { account_id: Number(target.split(':')[1]) }) }); setTxMsg(`Added as ${r.category} (${r.category_source === 'model' ? 'predicted by the model' : 'set by you'}).`); setTx({ ...tx, amount: '', description: '' }); sum.reload(); refresh({ rerun: true }) }) }
  const create = (e) => { e.preventDefault(); wrap('np', async () => { const r = await api.createProfile({ ...np, age: Number(np.age), monthly_income: Number(np.monthly_income), bank_balance: Number(np.bank_balance) }); select(r.profile.internal_id) }) }
  const saveProf = () => wrap('prof', async () => { await api.patchProfile(profileId, { ...prof, age: Number(prof.age), retirement_age_target: Number(prof.retirement_age_target) }); refresh({ rerun: true }) })
  const del = () => wrap('del', async () => { if (!window.confirm(`Delete ${a.profile.name} and all of its data? This cannot be undone.`)) return; await api.deleteProfile(profileId); signOut() })

  return (
    <>
      <PageHeader title="Profile & Data" subtitle="Upload a statement, add transactions, edit the profile or create a new one. Every change re-runs the analysis." />
      {err && <div className="mb-4"><ErrorBox message={err} /></div>}
      <div className="grid gap-4 xl:grid-cols-2">
        <Card title="Upload a bank or card statement (CSV)" subtitle="Columns are detected automatically. Each line is cleaned and categorised by the ML model, and duplicates are skipped.">
          <div className="grid grid-cols-[1fr_auto] gap-2"><Select value={target} onChange={(e) => setTarget(e.target.value)}>{targets.map(([v, l]) => <option key={v} value={v}>Add to: {l}</option>)}</Select>
            <input ref={file} type="file" accept=".csv,text/csv" hidden onChange={(e) => e.target.files[0] && upload(e.target.files[0])} />
            <Button icon={Upload} loading={busy === 'up'} onClick={() => file.current.click()}>Choose CSV</Button></div>
          <button onClick={uploadSample} className="mt-2 text-xs text-accent hover:underline">No file handy? Upload a 7-line sample statement (includes one unusual purchase)</button>
          {up && (
            <div className="mt-3 rounded-xl border border-good/30 bg-good/10 p-3 text-sm">
              <div className="font-medium text-good">{up.filename}: {up.transactions_added} transactions added{up.income_records_added ? `, ${up.income_records_added} income records` : ''}{up.duplicates_skipped ? `, ${up.duplicates_skipped} duplicates skipped` : ''}</div>
              <div className="mt-1 text-xs text-muted">{up.rows_in_file} rows read · {up.rows_dropped} invalid dropped · {up.categorised_by_model} categorised by the model · layout: {up.layout}</div>
              <div className="mt-2 flex flex-wrap gap-1.5">{Object.entries(up.by_category).map(([c, n]) => <Badge key={c} tone="accent">{c} · {n}</Badge>)}</div>
              {up.low_confidence_count > 0 && <div className="mt-2 text-xs text-warn">{up.low_confidence_count} low-confidence line(s) to review in Transaction Intelligence: {up.low_confidence.slice(0, 3).map((l) => `"${l.description.slice(0, 28)}…" → ${l.predicted}`).join('; ')}</div>}
            </div>
          )}
          <div className="mt-3"><Note>Accepted layouts: <code>Date, Narration, Amount[, Type]</code> or <code>Date, Narration, Withdrawal, Deposit</code>. Bank header lines above the table are ignored. Dates are read day-first.</Note></div>
        </Card>

        <Card title="Add a transaction" subtitle="Leave the category to the model - it reads the description">
          <form onSubmit={addTx} className="grid grid-cols-2 gap-3">
            <Field label="Date"><Input type="date" required value={tx.date} onChange={(e) => setTx({ ...tx, date: e.target.value })} /></Field>
            <Field label="Amount (₹)"><Input type="number" min={1} required value={tx.amount} onChange={(e) => setTx({ ...tx, amount: e.target.value })} /></Field>
            <div className="col-span-2"><Field label="Description as on the statement"><Input required minLength={2} placeholder="UPI/DR/123456789012/ZOMATO/HDFC/zomato@ybl" value={tx.description} onChange={(e) => setTx({ ...tx, description: e.target.value })} /></Field></div>
            <Field label="Type"><Select value={tx.type} onChange={(e) => setTx({ ...tx, type: e.target.value })}><option value="debit">Debit (money out)</option><option value="credit">Credit (refund)</option></Select></Field>
            <div className="flex items-end"><Button icon={Plus} loading={busy === 'tx'} className="w-full">Add</Button></div>
          </form>
          {txMsg && <p className="mt-2 text-sm text-good">{txMsg}</p>}
        </Card>

        <Card title="This profile" subtitle={`${a.profile.internal_id} · PAN ${a.profile.pan_masked}`}>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Age"><Input type="number" min={18} max={80} value={prof.age} onChange={(e) => setProf({ ...prof, age: e.target.value })} /></Field>
            <Field label="Target retirement age"><Input type="number" min={30} max={75} value={prof.retirement_age_target} onChange={(e) => setProf({ ...prof, retirement_age_target: e.target.value })} /></Field>
            <Field label="Occupation"><Input value={prof.occupation} onChange={(e) => setProf({ ...prof, occupation: e.target.value })} /></Field>
            <Field label="City"><Input value={prof.city} onChange={(e) => setProf({ ...prof, city: e.target.value })} /></Field>
          </div>
          <div className="mt-3 flex gap-2"><Button loading={busy === 'prof'} onClick={saveProf}>Save and re-analyse</Button>
            {sum.data?.can_delete && <Button variant="danger" icon={Trash2} loading={busy === 'del'} onClick={del}>Delete profile</Button>}</div>
          {sum.data && !sum.data.can_delete && <p className="mt-2 text-xs text-faint">The four built-in demo profiles cannot be deleted.</p>}
        </Card>

        <Card title="Records in the database" subtitle="Row counts for this profile, read live from the database" pad={false}>
          {sum.loading && !sum.data ? <Loading /> : <Table dense rows={sum.data?.tables || []} columns={[{ key: 'table', label: 'Table' }, { key: 'rows', label: 'Rows', right: true }]} />}
        </Card>

        <Card title="Create a new profile" subtitle="Then upload a statement to fill it. The PAN is stored only as a hash." className="xl:col-span-2">
          <form onSubmit={create} className="grid gap-3 md:grid-cols-4">
            <Field label="Name"><Input required minLength={2} value={np.name} onChange={(e) => setNp({ ...np, name: e.target.value })} /></Field>
            <Field label="PAN (any valid-format test value)"><Input required maxLength={10} placeholder="TESTP1234Q" className="font-mono uppercase" value={np.pan} onChange={(e) => setNp({ ...np, pan: e.target.value.toUpperCase() })} /></Field>
            <Field label="Age"><Input type="number" min={18} max={80} value={np.age} onChange={(e) => setNp({ ...np, age: e.target.value })} /></Field>
            <Field label="Employment"><Select value={np.employment_type} onChange={(e) => setNp({ ...np, employment_type: e.target.value })}><option value="salaried">Salaried</option><option value="self_employed">Self-employed</option></Select></Field>
            <Field label="Monthly income (₹)"><Input type="number" min={1} value={np.monthly_income} onChange={(e) => setNp({ ...np, monthly_income: e.target.value })} /></Field>
            <Field label="Bank balance (₹)"><Input type="number" min={0} value={np.bank_balance} onChange={(e) => setNp({ ...np, bank_balance: e.target.value })} /></Field>
            <div className="flex items-end md:col-span-2"><Button icon={UserPlus} loading={busy === 'np'}>Create and open</Button></div>
          </form>
        </Card>
      </div>
    </>
  )
}
