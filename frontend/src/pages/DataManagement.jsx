import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Plus, Trash2, Upload } from 'lucide-react'
import { api } from '../api'
import { Button, Card, ErrorBox, Field, Input, Loading, Note, PageHeader, Select, Table } from '../components/ui.jsx'
import { useAsync, useFinora } from '../store.jsx'

export default function DataManagement() {
  const { profileId, analysis: a, refresh, signOut } = useFinora()
  const sum = useAsync(() => api.dataSummary(profileId), [profileId])
  const [targets, setTargets] = useState([])
  const [target, setTarget] = useState('')
  const [busy, setBusy] = useState(null)
  const [err, setErr] = useState(null)
  const [tx, setTx] = useState({ date: '2026-10-30', amount: '', description: '', type: 'debit' })
  const [txMsg, setTxMsg] = useState(null)
  const [prof, setProf] = useState({ age: a.profile.age, retirement_age_target: a.profile.retirement_age_target, occupation: a.profile.occupation, city: a.profile.city })
  useEffect(() => { api.accounts(profileId).then((d) => { const t = [...d.accounts.map((x) => [`account:${x.id}`, `${x.bank_name} ${x.account_masked}`]), ...d.card_ids.map((c) => [`card:${c.id}`, c.label])]; setTargets(t); setTarget(t[0]?.[0] || '') }).catch(() => {}) }, [profileId])

  const wrap = async (key, fn) => { setBusy(key); setErr(null); try { await fn() } catch (e) { setErr(e.message) } finally { setBusy(null) } }
  const addTx = (e) => { e.preventDefault(); wrap('tx', async () => { const r = await api.addTransaction(profileId, { ...tx, amount: Number(tx.amount), ...(target.startsWith('card:') ? { card_id: Number(target.split(':')[1]) } : { account_id: Number(target.split(':')[1]) }) }); setTxMsg(`Added as ${r.category} (${r.category_source === 'model' ? 'predicted by the model' : 'set by you'}).`); setTx({ ...tx, amount: '', description: '' }); sum.reload(); refresh({ rerun: true }) }) }
  const saveProf = () => wrap('prof', async () => { await api.patchProfile(profileId, { ...prof, age: Number(prof.age), retirement_age_target: Number(prof.retirement_age_target) }); refresh({ rerun: true }) })
  const del = () => wrap('del', async () => { if (!window.confirm(`Delete ${a.profile.name} and all of its data? This cannot be undone.`)) return; await api.deleteProfile(profileId); signOut() })

  return (
    <>
      <PageHeader title="Profile & Data" subtitle="Add transactions or edit the profile; import statements from Import Statements. Every change re-runs the analysis. New profiles are started from the start screen." />
      {err && <div className="mb-4"><ErrorBox message={err} /></div>}
      <div className="grid gap-4 xl:grid-cols-2">
        <Card title="Bank & card statements" subtitle="One or two years of history at a time, with layout detection, live progress, review and undo">
          <p className="text-sm text-muted">Statements are imported on their own page: Finora shows what it detected before anything is saved, categorises every line with the ML model, recognises salary, transfers, refunds and card payments, and only updates a balance that reconciles.</p>
          <div className="mt-3 flex flex-wrap gap-2"><Link to="/statements"><Button icon={Upload}>Import statements</Button></Link>
            <Link to="/insights"><Button variant="ghost">Statement Intelligence</Button></Link><Link to="/review"><Button variant="ghost">Review & corrections</Button></Link></div>
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

        <Card title="This profile" subtitle={`${a.profile.internal_id}${a.profile.pan_masked ? ` · PAN ${a.profile.pan_masked}` : ''}`}>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Age"><Input type="number" min={18} max={80} value={prof.age} onChange={(e) => setProf({ ...prof, age: e.target.value })} /></Field>
            <Field label="Target retirement age"><Input type="number" min={30} max={75} value={prof.retirement_age_target} onChange={(e) => setProf({ ...prof, retirement_age_target: e.target.value })} /></Field>
            <Field label="Occupation"><Input value={prof.occupation} onChange={(e) => setProf({ ...prof, occupation: e.target.value })} /></Field>
            <Field label="City"><Input value={prof.city} onChange={(e) => setProf({ ...prof, city: e.target.value })} /></Field>
          </div>
          <div className="mt-3 flex gap-2"><Button loading={busy === 'prof'} onClick={saveProf}>Save and re-analyse</Button>
            {sum.data?.can_delete && <Button variant="danger" icon={Trash2} loading={busy === 'del'} onClick={del}>Delete profile</Button>}</div>
          {sum.data && !sum.data.can_delete && <p className="mt-2 text-xs text-faint">Demo templates are read-only and cannot be deleted.</p>}
        </Card>

        <Card title="Records in the database" subtitle="Row counts for this profile, read live from the database" pad={false}>
          {sum.loading && !sum.data ? <Loading /> : <Table dense rows={sum.data?.tables || []} columns={[{ key: 'table', label: 'Table' }, { key: 'rows', label: 'Rows', right: true }]} />}
        </Card>

      </div>
    </>
  )
}
