// Data → Profile & privacy: what is stored, export, demo reset and deletion. (Adding a transaction moved to Money → Transactions;
// profile details are edited in Settings → Profiles.)
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Download, RotateCcw, Trash2 } from 'lucide-react'
import { api } from '../api'
import { Answer, Button, ButtonLink, ErrorBox, Loading, PageHeader, Section, useConfirm } from '../components/ui.jsx'
import { useAsync, useFinora } from '../store.jsx'

export default function DataManagement() {
  const { profileId, profile, analysis: a, refresh, signOut, select } = useFinora()
  const sum = useAsync(() => api.dataSummary(profileId), [profileId])
  const [busy, setBusy] = useState(null)
  const [err, setErr] = useState(null)
  const ask = useConfirm()
  const wrap = async (key, fn) => { setBusy(key); setErr(null); try { await fn() } catch (e) { setErr(e.message) } finally { setBusy(null) } }
  const del = () => wrap('del', async () => { if (!await ask({ title: `Delete ${a.profile.name}?`, body: 'The profile and all of its data are deleted permanently. This cannot be undone.', confirm: 'Delete profile', danger: true })) return; await api.deleteProfile(profileId); signOut() })
  const sandbox = profile?.kind === 'sandbox'
  const resetDemo = async () => {
    if (!await ask({ title: 'Reset this demo copy?', body: 'Every change you made to this demo person is discarded and the original synthetic data is restored.', confirm: 'Reset demo', danger: true })) return
    wrap('reset', async () => { const r = await api.resetSandbox(profileId); select(r.profile.internal_id); refresh({ rerun: true }) })
  }
  const stored = (sum.data?.tables || []).filter((t) => t.rows > 0)
  return (
    <>
      <PageHeader title="Profile & privacy" subtitle="What Finora holds for this profile, and your controls over it." />
      {err && <div className="mb-4"><ErrorBox message={err} /></div>}
      <Answer eyebrow={sandbox ? 'Demo copy · synthetic data' : profile?.kind === 'template' ? 'Read-only demo template' : 'Private profile'}
        sub={sandbox ? 'A private copy of a fictional person, deleted automatically after 24 hours.' : 'Visible only to your account and never used to train Finora’s models.'}>
        Finora holds <b>{sum.data ? stored.reduce((n, t) => n + t.rows, 0).toLocaleString('en-IN') : '…'}</b> records for {a.profile.name}, across {stored.length} kinds of data.
      </Answer>
      <div className="grid gap-8 lg:grid-cols-2">
        <Section title="What is stored" description="Read live from the database.">
          {sum.loading && !sum.data ? <Loading /> : (
            <ul className="divide-y divide-line overflow-hidden rounded-xl border border-line bg-bg">
              {(sum.data?.tables || []).map((t) => <li key={t.table} className="flex justify-between gap-3 px-5 py-3 text-sm sm:px-6"><span className={t.rows ? 'text-ink-2' : 'text-faint'}>{t.table}</span><span className="num text-muted">{t.rows.toLocaleString('en-IN')}</span></li>)}
            </ul>
          )}
          <p className="mt-3 text-[13px] text-muted">Edit any of it under <Link to="/data?tab=records" className="font-medium text-accent hover:underline">Records</Link>; profile details are in <Link to="/settings?tab=profiles" className="font-medium text-accent hover:underline">Settings</Link>.</p>
        </Section>
        <div>
          <Section title="Your controls">
            <ul className="divide-y divide-line overflow-hidden rounded-xl border border-line bg-bg">
              <li className="flex flex-wrap items-center justify-between gap-3 px-5 py-4 sm:px-6"><div><div className="text-[15px] font-medium text-ink">Export everything</div><div className="text-[13px] text-muted">A zip of CSV files, or a PDF report</div></div>
                <ButtonLink to="/data?tab=reports" variant="secondary" icon={Download}>Export</ButtonLink></li>
              {sandbox && <li className="flex flex-wrap items-center justify-between gap-3 px-5 py-4 sm:px-6"><div><div className="text-[15px] font-medium text-ink">Reset the demo</div><div className="text-[13px] text-muted">Discard your changes to this demo person</div></div>
                <Button variant="secondary" icon={RotateCcw} loading={busy === 'reset'} onClick={resetDemo}>Reset demo</Button></li>}
            </ul>
          </Section>
          {sum.data?.can_delete && (
            <Section title="Danger zone" className="mt-8">
              <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-bad/30 bg-bad-soft/40 px-5 py-4 sm:px-6">
                <div><div className="text-[15px] font-medium text-ink">Delete this profile</div><div className="text-[13px] text-muted">Deletes the profile and all of its data. This cannot be undone.</div></div>
                <Button variant="danger" icon={Trash2} loading={busy === 'del'} onClick={del}>Delete profile</Button>
              </div>
            </Section>
          )}
          {sum.data && !sum.data.can_delete && <p className="mt-6 text-[13px] text-faint">Demo templates are read-only and cannot be deleted.</p>}
          <Section title="Privacy" className="mt-8">
            <ul className="space-y-2.5 text-[13px] leading-5 text-muted">
              <li>Finora never connects to a bank, bureau or government system. Only what you enter or import is stored.</li>
              <li>The AI assistant runs on this computer; nothing you ask is sent to a cloud service.</li>
              <li>Imported statement files are deleted once an import finishes or is cancelled.</li>
            </ul>
          </Section>
        </div>
      </div>
    </>
  )
}
