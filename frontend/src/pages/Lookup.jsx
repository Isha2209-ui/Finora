// Start (signed in, no profile chosen): explore a synthetic demo person (private, expiring copy) or build your own profile.
// Nothing here fetches real financial data: Finora has no connection to banks, bureaus or the tax department.
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowRight, BadgeIndianRupee, Clock, FlaskConical, Lock, LogOut, ShieldCheck, UserPlus, UserRound } from 'lucide-react'
import { api } from '../api'
import { useAuth } from '../auth.jsx'
import { Badge, Button, Field, Input, Select, cx } from '../components/ui.jsx'
import { useFinora } from '../store.jsx'

const PAN_RE = /^[A-Z]{5}[0-9]{4}[A-Z]$/
const hoursLeft = (iso) => Math.max(0, Math.round((new Date(iso + 'Z') - Date.now()) / 36e5))

export default function Lookup() {
  const { select } = useFinora()
  const { account, logout } = useAuth()
  const [templates, setTemplates] = useState(null)
  const [mine, setMine] = useState(null)
  const [health, setHealth] = useState(null)
  const [busy, setBusy] = useState(null)
  const [err, setErr] = useState(null)
  const [pan, setPan] = useState('')
  const [path, setPath] = useState('demo')
  const [np, setNp] = useState({ name: account?.display_name || '', age: 28, employment_type: 'salaried', city: '', retirement_age_target: 60 })
  const navigate = useNavigate()

  useEffect(() => {
    api.health().then(setHealth).catch((e) => setHealth({ error: e.message }))
    api.demoTemplates().then(setTemplates).catch((e) => setErr(e.message))
    api.profiles().then((ps) => setMine(ps.filter((p) => p.kind !== 'template'))).catch(() => setMine([]))
  }, [])

  const run = async (key, fn) => { setBusy(key); setErr(null); try { await fn() } catch (e) { setErr(e.message) } finally { setBusy(null) } }
  const open = (id) => { select(id); navigate('/') }
  const explore = (id) => run(id, async () => open((await api.explore(id)).profile.internal_id))
  const byIdentifier = (e) => { e.preventDefault(); run('pan', async () => open((await api.lookup(pan)).profile.internal_id)) }
  const build = (e) => {
    e.preventDefault()
    run('build', async () => {
      const body = { name: np.name.trim(), age: Number(np.age), employment_type: np.employment_type, retirement_age_target: Number(np.retirement_age_target) }
      if (np.city.trim()) body.city = np.city.trim()
      select((await api.createProfile(body)).profile.internal_id)
      navigate('/data?tab=records')
    })
  }
  const first = (account?.display_name || '').split(' ')[0]

  return (
    <div className="min-h-full bg-canvas">
      <header className="flex h-16 items-center gap-3 border-b border-line bg-bg px-4 sm:px-8">
        <span className="grid h-8 w-8 place-items-center rounded-lg bg-accent text-white"><BadgeIndianRupee size={18} aria-hidden /></span>
        <span className="text-[17px] font-semibold tracking-tight">Finora</span>
        <div className="flex-1" />
        <span className="hidden truncate text-[13px] text-muted sm:block">{account?.email}</span>
        <Button variant="quiet" size="sm" icon={LogOut} onClick={logout}>Sign out</Button>
      </header>

      <main id="main" className="mx-auto max-w-4xl px-4 py-10 sm:px-8 sm:py-14">
        <h1 className="text-display font-semibold tracking-tight text-ink">{first ? `Welcome, ${first}.` : 'Welcome to Finora.'}</h1>
        <p className="mt-3 max-w-2xl text-[15px] leading-7 text-muted">Finora turns accounts, statements and records into a plan you can act on. It never connects to your bank and never uses a PAN to fetch data, so start with a demo person or with your own numbers.</p>
        {err && <div className="mt-6 rounded-lg border border-bad/25 bg-bad-soft px-4 py-3 text-sm text-bad" role="alert">{err}</div>}

        {mine?.length > 0 && (
          <section className="mt-10" aria-labelledby="mine">
            <h2 id="mine" className="text-heading font-semibold text-ink">Continue where you left off</h2>
            <div className="mt-3 grid gap-2 sm:grid-cols-2">
              {mine.map((p) => (
                <button key={p.internal_id} type="button" onClick={() => open(p.internal_id)} className="flex items-center gap-3 rounded-xl border border-line bg-bg px-4 py-3.5 text-left transition-colors hover:border-accent/40">
                  <UserRound size={18} className="shrink-0 text-accent" aria-hidden />
                  <div className="min-w-0 flex-1"><div className="truncate text-[15px] font-medium text-ink">{p.name}</div>
                    <div className="text-[13px] text-muted">{p.kind === 'sandbox' ? <span className="inline-flex items-center gap-1"><Clock size={12} aria-hidden /> Demo copy · deleted in {hoursLeft(p.expires_at)} h</span> : 'Your private profile'}</div></div>
                  <ArrowRight size={16} className="text-faint" aria-hidden />
                </button>
              ))}
            </div>
          </section>
        )}

        <section className="mt-10" aria-labelledby="start">
          <h2 id="start" className="text-heading font-semibold text-ink">{mine?.length ? 'Or start something new' : 'How would you like to start?'}</h2>
          <div role="radiogroup" aria-label="Way to start" className="mt-3 grid gap-3 sm:grid-cols-2">
            {[['demo', FlaskConical, 'Explore a demo person', 'Synthetic people with 12 months of data. Your own copy, deleted after 24 hours.'],
              ['own', UserPlus, 'Start with my own data', 'A private profile only you can see. Add records or import a statement.']].map(([id, I, t, d]) => (
              <button key={id} type="button" role="radio" aria-checked={path === id} onClick={() => setPath(id)}
                className={cx('flex gap-3 rounded-xl border bg-bg p-4 text-left transition-colors', path === id ? 'border-accent ring-2 ring-accent/15' : 'border-line hover:border-control/60')}>
                <span className={cx('grid h-9 w-9 shrink-0 place-items-center rounded-lg', path === id ? 'bg-accent text-white' : 'bg-subtle text-muted')}><I size={18} aria-hidden /></span>
                <span><span className="block text-[15px] font-semibold text-ink">{t}</span><span className="mt-0.5 block text-[13px] leading-5 text-muted">{d}</span></span>
              </button>
            ))}
          </div>

          <div className="mt-4 rounded-xl border border-line bg-bg p-5 sm:p-6">
            {path === 'demo' ? (
              <>
                <div className="flex flex-wrap items-center gap-2"><h3 className="text-[15px] font-semibold text-ink">Choose a demo person</h3><Badge tone="warn">Synthetic data</Badge></div>
                <div className="mt-4 grid gap-2">
                  {(templates || []).map((t) => (
                    <button key={t.template_id} type="button" onClick={() => explore(t.template_id)} disabled={!!busy}
                      className="flex items-center gap-3 rounded-lg border border-line px-4 py-3 text-left transition-colors hover:border-accent/40 hover:bg-accent-soft/40 disabled:opacity-60">
                      <span className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-subtle text-[13px] font-semibold text-ink-2">{t.name.split(' ').map((w) => w[0]).join('')}</span>
                      <span className="min-w-0 flex-1"><span className="block text-sm font-medium text-ink">{t.name} <span className="font-normal text-muted">· {t.age} · {t.occupation}</span></span><span className="block text-[13px] text-muted">{t.description}</span></span>
                      {busy === t.template_id ? <span className="text-[13px] text-muted" role="status">Copying…</span> : <ArrowRight size={16} className="text-faint" aria-hidden />}
                    </button>
                  ))}
                  {templates === null && <div className="text-sm text-muted" role="status">Loading demo people…</div>}
                </div>
                <form onSubmit={byIdentifier} className="mt-5 flex flex-wrap items-end gap-2 border-t border-line pt-5">
                  <div className="min-w-[220px] flex-1"><Field label="Or open a demo by its identifier" hint="Only the four demo identifiers work. A real PAN finds nothing: Finora has no access to anyone's records.">
                    <Input value={pan} maxLength={10} spellCheck={false} autoComplete="off" placeholder="ABCDE1234F" className="font-mono tracking-widest"
                      onChange={(e) => { setPan(e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, '')); setErr(null) }} /></Field></div>
                  <Button type="submit" variant="secondary" loading={busy === 'pan'} disabled={!PAN_RE.test(pan)} className="mb-[22px]">Open</Button>
                </form>
              </>
            ) : (
              <>
                <div className="flex flex-wrap items-center gap-2"><h3 className="text-[15px] font-semibold text-ink">Create your private profile</h3><Badge tone="good">Private</Badge></div>
                <p className="mt-1 text-[13px] text-muted">It starts empty. Next you add accounts, income, cards, loans and investments, or import a statement. Finora never fills in numbers for you.</p>
                <form onSubmit={build} className="mt-5 grid gap-4 sm:grid-cols-2">
                  <div className="sm:col-span-2"><Field label="Name"><Input name="name" autoComplete="name" required minLength={2} maxLength={120} value={np.name} onChange={(e) => setNp({ ...np, name: e.target.value })} /></Field></div>
                  <Field label="Age"><Input type="number" required min={18} max={80} value={np.age} onChange={(e) => setNp({ ...np, age: e.target.value })} /></Field>
                  <Field label="Employment"><Select value={np.employment_type} onChange={(e) => setNp({ ...np, employment_type: e.target.value })}><option value="salaried">Salaried</option><option value="self_employed">Self-employed</option></Select></Field>
                  <Field label="City (optional)"><Input autoComplete="address-level2" maxLength={80} value={np.city} onChange={(e) => setNp({ ...np, city: e.target.value })} /></Field>
                  <Field label="Target retirement age"><Input type="number" required min={30} max={75} value={np.retirement_age_target} onChange={(e) => setNp({ ...np, retirement_age_target: e.target.value })} /></Field>
                  <div className="sm:col-span-2"><Button type="submit" icon={UserPlus} loading={busy === 'build'} className="w-full sm:w-auto">Create my private profile</Button></div>
                </form>
              </>
            )}
          </div>
        </section>

        <div className="mt-10 grid gap-4 text-[13px] leading-5 text-muted sm:grid-cols-2">
          <p className="flex gap-2.5"><ShieldCheck size={16} className="mt-0.5 shrink-0 text-faint" aria-hidden /> Demo people are simulated. No bank, bureau or government system is contacted, for demos or for your own profile.</p>
          <p className="flex gap-2.5"><Lock size={16} className="mt-0.5 shrink-0 text-faint" aria-hidden /> Profiles you build are visible only to your account and are never used to train Finora's models.</p>
        </div>
        <div className="mt-6 flex flex-wrap items-center gap-2" aria-label="System status">
          {health == null ? <Badge>Checking backend…</Badge> : health.error ? <Badge tone="bad">Backend offline — start it on port 8001</Badge> : (
            <>
              <Badge tone="good">Backend online</Badge>
              <Badge tone={Object.values(health.models).every(Boolean) ? 'good' : 'warn'}>{Object.values(health.models).filter(Boolean).length}/5 models loaded</Badge>
              <Badge tone={health.ai_cfo.available ? 'good' : 'warn'}>{health.ai_cfo.available ? `AI CFO: ${health.ai_cfo.model} (local)` : 'AI CFO: calculator mode'}</Badge>
            </>
          )}
        </div>
      </main>
    </div>
  )
}
