// Settings (account menu). Only what the backend supports: account details (read-only), security activity, sign-out, profiles.
// Password change and preferences have no backend endpoint in this version, so they are listed as unavailable, not faked.
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { LogOut, Repeat } from 'lucide-react'
import { api } from '../api'
import { useAuth } from '../auth.jsx'
import Area from '../components/Area.jsx'
import { Badge, Button, Card, ErrorBox, Field, Input, KV, Loading, Note, PageHeader, Select, Table, useConfirm, useToast } from '../components/ui.jsx'
import { useAsync, useFinora } from '../store.jsx'

function Account() {
  const { account } = useAuth()
  return (
    <>
      <PageHeader title="Account" subtitle="The account you signed in with. These details are read-only in this version." />
      <Card><KV rows={[['E-mail', account?.email], ['Name', account?.display_name || '—'], account?.created_at && ['Created', new Date(account.created_at).toLocaleDateString('en-IN')]]} /></Card>
      <Card title="Not available in this version" className="mt-6">
        <ul className="space-y-3 text-sm text-muted">
          <li className="flex gap-3"><Badge>Unavailable</Badge> Changing your e-mail, name or password: the backend has no endpoint for it yet.</li>
          <li className="flex gap-3"><Badge>Unavailable</Badge> Preferences (currency, notifications, theme): Finora uses rupees and a light theme throughout.</li>
        </ul>
      </Card>
    </>
  )
}

function Security() {
  const { logout } = useAuth()
  const act = useAsync(() => api.activity(), [])
  return (
    <>
      <PageHeader title="Security" subtitle="Your recent sign-ins and data events, from Finora's audit log. Only your own account's events are shown.">
        <Button variant="secondary" icon={LogOut} onClick={logout}>Sign out</Button>
      </PageHeader>
      <Note>Passwords are stored only as argon2id hashes. Your session is an httpOnly cookie that page scripts cannot read, and state-changing requests carry a CSRF token.</Note>
      <Card title="Recent activity" className="mt-6" pad={false}>
        {act.loading ? <Loading /> : act.error ? <div className="p-5"><ErrorBox message={act.error} onRetry={act.reload} /></div> : (
          <Table dense pageSize={15} rows={(act.data?.events || act.data || []).map((e, i) => ({ id: i, ...e }))} empty="No activity recorded yet" caption="Recent account activity" columns={[
            { key: 'at', label: 'When', render: (e) => <span className="num whitespace-nowrap text-muted">{e.at || e.created_at ? new Date(e.at || e.created_at).toLocaleString('en-IN') : '—'}</span> },
            { key: 'event', label: 'Event', render: (e) => <span className="font-medium">{e.event || e.action || e.kind}</span> },
            { key: 'outcome', label: 'Outcome', render: (e) => e.outcome ? <Badge tone={e.outcome === 'success' || e.outcome === 'ok' ? 'good' : e.outcome === 'denied' || e.outcome === 'failure' ? 'bad' : 'neutral'}>{e.outcome}</Badge> : null },
            { key: 'detail', label: 'Detail', render: (e) => <span className="break-words text-muted">{typeof e.detail === 'string' ? e.detail : e.detail ? JSON.stringify(e.detail) : ''}</span> },
          ]} />
        )}
      </Card>
    </>
  )
}

function Profiles() {
  const { profileId, profile, select, signOut, refresh } = useFinora()
  const nav = useNavigate()
  const confirm = useConfirm()
  const toast = useToast()
  const list = useAsync(() => api.profiles(), [])
  const editable = profile && !profile.read_only
  const [form, setForm] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const start = () => setForm({ name: profile.name || '', age: profile.age || '', occupation: profile.occupation || '', city: profile.city || '', employment_type: profile.employment_type || 'salaried', retirement_age_target: profile.retirement_age_target || 60 })
  const save = async (e) => {
    e.preventDefault(); setBusy(true); setErr(null)
    try {
      const body = { name: form.name.trim(), age: Number(form.age), retirement_age_target: Number(form.retirement_age_target), employment_type: form.employment_type }
      if (form.occupation.trim()) body.occupation = form.occupation.trim()
      if (form.city.trim()) body.city = form.city.trim()
      await api.patchProfile(profileId, body)
      await refresh({ rerun: true }); setForm(null); list.reload(); toast('Profile details saved', { tone: 'good' })
    } catch (x) { setErr(x.message) } finally { setBusy(false) }
  }
  const del = async (p) => {
    if (!await confirm({ title: `Delete “${p.name}”?`, body: 'The profile and all of its data are deleted permanently. This cannot be undone.', confirm: 'Delete profile', danger: true })) return
    try { await api.deleteProfile(p.internal_id); toast('Profile deleted', { tone: 'good' }); if (p.internal_id === profileId) { signOut(); nav('/') } else list.reload() }
    catch (x) { toast(x.message, { tone: 'bad' }) }
  }
  const mine = (list.data || []).filter((p) => p.kind !== 'template')
  return (
    <>
      <PageHeader title="Profiles" subtitle="The financial profiles on your account. Demo copies are deleted after 24 hours; private profiles stay until you delete them.">
        <Button variant="secondary" icon={Repeat} onClick={() => { signOut(); nav('/') }}>Switch or create profile</Button>
      </PageHeader>
      <Card title="Current profile" subtitle={profile?.kind === 'sandbox' ? 'Demo copy (synthetic data)' : profile?.kind === 'template' ? 'Read-only demo template' : 'Private profile'}
        action={editable && !form && <Button size="sm" variant="secondary" onClick={start}>Edit details</Button>}>
        {!form ? <KV rows={[['Name', profile?.name], ['Age', profile?.age], ['Occupation', profile?.occupation || '—'], ['City', profile?.city || '—'], ['Target retirement age', profile?.retirement_age_target]]} /> : (
          <form onSubmit={save} className="grid gap-4 sm:grid-cols-2">
            <Field label="Name"><Input required minLength={2} maxLength={120} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
            <Field label="Age"><Input type="number" required min={18} max={80} value={form.age} onChange={(e) => setForm({ ...form, age: e.target.value })} /></Field>
            <Field label="Occupation"><Input maxLength={80} value={form.occupation} onChange={(e) => setForm({ ...form, occupation: e.target.value })} /></Field>
            <Field label="City"><Input maxLength={80} value={form.city} onChange={(e) => setForm({ ...form, city: e.target.value })} /></Field>
            <Field label="Employment"><Select value={form.employment_type} onChange={(e) => setForm({ ...form, employment_type: e.target.value })}><option value="salaried">Salaried</option><option value="self_employed">Self-employed</option></Select></Field>
            <Field label="Target retirement age"><Input type="number" required min={30} max={75} value={form.retirement_age_target} onChange={(e) => setForm({ ...form, retirement_age_target: e.target.value })} /></Field>
            {err && <p role="alert" className="text-[13px] text-bad sm:col-span-2">{err}</p>}
            <div className="flex gap-2 sm:col-span-2"><Button type="submit" loading={busy}>Save details</Button><Button type="button" variant="secondary" onClick={() => setForm(null)}>Cancel</Button></div>
          </form>
        )}
      </Card>
      <Card title="All your profiles" className="mt-6" pad={false}>
        {list.loading ? <Loading /> : list.error ? <div className="p-5"><ErrorBox message={list.error} onRetry={list.reload} /></div> : (
          <Table rows={mine.map((p) => ({ id: p.internal_id, ...p }))} empty="No profiles of your own yet" caption="Your profiles" columns={[
            { key: 'name', label: 'Name', render: (p) => <span className="font-medium">{p.name}{p.internal_id === profileId && <Badge tone="accent" className="ml-2">current</Badge>}</span> },
            { key: 'kind', label: 'Type', render: (p) => p.kind === 'sandbox' ? 'Demo copy' : 'Private' },
            { key: 'x', label: '', right: true, render: (p) => <div className="flex justify-end gap-2">
              {p.internal_id !== profileId && <Button size="sm" variant="secondary" onClick={() => { select(p.internal_id); nav('/') }}>Open</Button>}
              <Button size="sm" variant="danger" onClick={() => del(p)}>Delete</Button></div> },
          ]} />
        )}
      </Card>
    </>
  )
}

export default function Settings() {
  return <Area title="Settings" subtitle="Your account, its security, and your profiles."
    tabs={[{ id: 'account', label: 'Account', render: () => <Account /> }, { id: 'security', label: 'Security', render: () => <Security /> }, { id: 'profiles', label: 'Profiles', render: () => <Profiles /> }]} />
}
