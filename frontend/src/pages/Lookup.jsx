import { useEffect, useState } from 'react'
import { ArrowRight, BadgeIndianRupee, Clock, FlaskConical, Lock, ShieldCheck, UserPlus, UserRound } from 'lucide-react'
import { api } from '../api'
import { useAuth } from '../auth.jsx'
import { Badge, Button, Field, Input, Select } from '../components/ui.jsx'
import { useFinora } from '../store.jsx'

const PAN_RE = /^[A-Z]{5}[0-9]{4}[A-Z]$/
const hoursLeft = (iso) => Math.max(0, Math.round((new Date(iso + 'Z') - Date.now()) / 36e5))

// Start screen: explore a synthetic demo identity (as a private, expiring copy) or build your own.
// Nothing here fetches real financial data: Finora has no connection to banks, bureaus or the tax department.
export default function Lookup() {
  const { select } = useFinora()
  const { account, logout } = useAuth()
  const [templates, setTemplates] = useState(null)
  const [mine, setMine] = useState([])
  const [health, setHealth] = useState(null)
  const [busy, setBusy] = useState(null)
  const [err, setErr] = useState(null)
  const [pan, setPan] = useState('')
  const [np, setNp] = useState({ name: account?.display_name || '', age: 28, employment_type: 'salaried', city: '', monthly_income: '', bank_balance: '' })

  useEffect(() => {
    api.health().then(setHealth).catch((e) => setHealth({ error: e.message }))
    api.demoTemplates().then(setTemplates).catch((e) => setErr(e.message))
    api.profiles().then((ps) => setMine(ps.filter((p) => p.kind !== 'template'))).catch(() => {})
  }, [])

  const run = async (key, fn) => { setBusy(key); setErr(null); try { await fn() } catch (e) { setErr(e.message) } finally { setBusy(null) } }
  const explore = (id) => run(id, async () => select((await api.explore(id)).profile.internal_id))
  const byIdentifier = (e) => { e.preventDefault(); run('pan', async () => select((await api.lookup(pan)).profile.internal_id)) }
  const build = (e) => {
    e.preventDefault()
    run('build', async () => {
      const body = { name: np.name.trim(), age: Number(np.age), employment_type: np.employment_type, monthly_income: Number(np.monthly_income), bank_balance: Number(np.bank_balance || 0) }
      if (np.city.trim()) body.city = np.city.trim()
      select((await api.createProfile(body)).profile.internal_id)
    })
  }

  return (
    <div className="min-h-full px-6 py-8 lg:px-12">
      <div className="mx-auto max-w-6xl">
        <div className="flex items-center gap-3">
          <div className="grid h-10 w-10 place-items-center rounded-xl bg-accent/15 text-accent"><BadgeIndianRupee size={22} /></div>
          <div className="text-lg font-semibold tracking-tight">Finora</div>
          <div className="flex-1" />
          <span className="text-xs text-faint">{account?.email}</span>
          <button onClick={logout} className="text-xs text-accent hover:underline">Sign out</button>
        </div>

        <h1 className="mt-10 text-3xl font-semibold tracking-tight">How would you like to start?</h1>
        <p className="mt-2 max-w-2xl text-sm text-muted">Finora never connects to your bank and never uses a PAN to fetch financial data. You can explore a synthetic demo identity, or build your own from what you enter and upload.</p>
        {err && <div className="mt-4 rounded-xl border border-bad/40 bg-bad/10 px-4 py-2.5 text-sm text-bad" role="alert">{err}</div>}

        <div className="mt-6 grid gap-5 lg:grid-cols-2">
          <section className="rounded-2xl border border-line bg-surface p-5">
            <div className="flex items-center gap-2"><FlaskConical size={18} className="text-accent" /><h2 className="font-semibold">Explore demo identity</h2><Badge tone="warn">Simulated data</Badge></div>
            <p className="mt-1.5 text-sm text-muted">Four fictional people with synthetic accounts, cards, investments and 12 months of transactions. You get your own copy: change anything, reset it any time, and it is deleted after 24 hours.</p>
            <div className="mt-4 grid gap-2">
              {(templates || []).map((t) => (
                <button key={t.template_id} onClick={() => explore(t.template_id)} disabled={!!busy}
                  className="flex items-center gap-3 rounded-xl border border-line bg-bg px-3.5 py-3 text-left transition hover:border-accent/50 disabled:opacity-60">
                  <div className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-raised text-xs font-semibold text-accent">{t.name.split(' ').map((w) => w[0]).join('')}</div>
                  <div className="min-w-0 flex-1"><div className="text-sm font-medium">{t.name} <span className="font-normal text-muted">· {t.age} · {t.occupation}</span></div><div className="text-xs text-muted">{t.description}</div></div>
                  {busy === t.template_id ? <span className="text-xs text-faint">Copying…</span> : <ArrowRight size={16} className="text-faint" />}
                </button>
              ))}
              {templates === null && <div className="text-sm text-faint">Loading demo identities…</div>}
            </div>
            <form onSubmit={byIdentifier} className="mt-4 flex items-end gap-2">
              <div className="flex-1"><Field label="Or type a demo identifier (e.g. ABCDE1234F)">
                <Input value={pan} maxLength={10} spellCheck={false} autoComplete="off" placeholder="ABCDE1234F" className="font-mono tracking-widest"
                  onChange={(e) => { setPan(e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, '')); setErr(null) }} /></Field></div>
              <Button variant="ghost" loading={busy === 'pan'} disabled={!PAN_RE.test(pan)}>Open</Button>
            </form>
            <p className="mt-2 text-[11px] leading-relaxed text-faint">Only the four demo identifiers work here. A real PAN finds nothing, because Finora has no access to anyone's financial records.</p>
          </section>

          <section className="rounded-2xl border border-line bg-surface p-5">
            <div className="flex items-center gap-2"><UserPlus size={18} className="text-accent" /><h2 className="font-semibold">Build my financial identity</h2><Badge tone="good">Private</Badge></div>
            <p className="mt-1.5 text-sm text-muted">Start a profile that only your account can see. Begin with the basics; add accounts, cards and holdings, or upload a bank statement CSV, from <em>Profile &amp; Data</em>.</p>
            <form onSubmit={build} className="mt-4 grid grid-cols-2 gap-3">
              <div className="col-span-2"><Field label="Name"><Input required minLength={2} maxLength={120} value={np.name} onChange={(e) => setNp({ ...np, name: e.target.value })} /></Field></div>
              <Field label="Age"><Input type="number" required min={18} max={80} value={np.age} onChange={(e) => setNp({ ...np, age: e.target.value })} /></Field>
              <Field label="Employment"><Select value={np.employment_type} onChange={(e) => setNp({ ...np, employment_type: e.target.value })}><option value="salaried">Salaried</option><option value="self_employed">Self-employed</option></Select></Field>
              <Field label="Monthly take-home income (₹)"><Input type="number" required min={1} value={np.monthly_income} onChange={(e) => setNp({ ...np, monthly_income: e.target.value })} /></Field>
              <Field label="Main bank balance (₹)"><Input type="number" min={0} value={np.bank_balance} onChange={(e) => setNp({ ...np, bank_balance: e.target.value })} /></Field>
              <div className="col-span-2"><Field label="City (optional)"><Input maxLength={80} value={np.city} onChange={(e) => setNp({ ...np, city: e.target.value })} /></Field></div>
              <div className="col-span-2"><Button icon={UserPlus} loading={busy === 'build'} className="w-full">Create my private profile</Button></div>
            </form>
            <p className="mt-2 text-[11px] leading-relaxed text-faint">Your stated income is recorded as six months of income so the first analysis has something to work with. You can replace it with real statements later.</p>
          </section>
        </div>

        {mine.length > 0 && (
          <section className="mt-6">
            <h2 className="mb-2 text-sm font-medium text-muted">Your profiles</h2>
            <div className="grid gap-2 md:grid-cols-2 lg:grid-cols-3">
              {mine.map((p) => (
                <button key={p.internal_id} onClick={() => select(p.internal_id)} className="flex items-center gap-3 rounded-xl border border-line bg-surface px-3.5 py-3 text-left hover:border-accent/50">
                  <UserRound size={16} className="shrink-0 text-accent" />
                  <div className="min-w-0 flex-1"><div className="truncate text-sm font-medium">{p.name}</div>
                    <div className="text-xs text-muted">{p.kind === 'sandbox' ? <span className="inline-flex items-center gap-1"><Clock size={11} /> Demo copy · deleted in {hoursLeft(p.expires_at)} h</span> : 'Private profile'}</div></div>
                  <ArrowRight size={15} className="text-faint" />
                </button>
              ))}
            </div>
          </section>
        )}

        <div className="mt-6 grid gap-2 rounded-2xl border border-line bg-surface p-4 text-xs leading-relaxed text-muted md:grid-cols-2">
          <div className="flex gap-2"><ShieldCheck size={14} className="mt-0.5 shrink-0 text-accent" /> Demo identities are simulated. No bank, bureau or government system is contacted, for demos or for your own profile.</div>
          <div className="flex gap-2"><Lock size={14} className="mt-0.5 shrink-0 text-accent" /> Profiles you build are visible only to your account, and are never used to train Finora's models.</div>
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-2 text-xs">
          {health == null ? <Badge>Checking backend…</Badge> : health.error ? <Badge tone="bad">Backend offline - start it on port 8001</Badge> : (
            <>
              <Badge tone="good">Backend online</Badge><Badge>{health.database}</Badge>
              <Badge tone={Object.values(health.models).every(Boolean) ? 'good' : 'warn'}>{Object.values(health.models).filter(Boolean).length}/5 models loaded</Badge>
              <Badge tone={health.ai_cfo.available ? 'good' : 'warn'}>{health.ai_cfo.available ? `AI CFO: ${health.ai_cfo.model}` : 'AI CFO: calculator mode'}</Badge>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
