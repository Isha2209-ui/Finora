import { useEffect, useState } from 'react'
import { ArrowRight, BadgeIndianRupee, Bot, BrainCircuit, Flame, Lock, ShieldCheck } from 'lucide-react'
import { api } from '../api'
import { Badge, Button, cx } from '../components/ui.jsx'
import { useFinora } from '../store.jsx'

const DEMOS = [
  ['ABCDE1234F', 'Salaried, balanced saver'], ['PQRST5678K', 'High spender, three credit cards'],
  ['LMNOP2345D', 'Home, car and personal loans'], ['XYZAB9876C', 'Freelancer, irregular income'],
]
const PAN_RE = /^[A-Z]{5}[0-9]{4}[A-Z]$/

export default function Lookup() {
  const { select } = useFinora()
  const [pan, setPan] = useState('')
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)
  const [health, setHealth] = useState(null)
  useEffect(() => { api.health().then(setHealth).catch((e) => setHealth({ error: e.message })) }, [])

  const hint = pan.length === 0 ? null : pan.length < 10 ? `${10 - pan.length} more character${pan.length === 9 ? '' : 's'}` : PAN_RE.test(pan) ? null : 'Format: 5 letters, 4 digits, 1 letter'
  const submit = async (value) => {
    const v = (value ?? pan).toUpperCase().trim()
    if (!PAN_RE.test(v)) { setErr('Enter a valid PAN: 5 letters, 4 digits, then 1 letter (for example ABCDE1234F).'); return }
    setBusy(true); setErr(null)
    try { const r = await api.lookup(v); select(r.profile.internal_id) }
    catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  return (
    <div className="grid min-h-full lg:grid-cols-[1.1fr_1fr]">
      <div className="relative hidden flex-col justify-between overflow-hidden border-r border-line bg-surface p-12 lg:flex">
        <div className="pointer-events-none absolute -top-32 -left-32 h-96 w-96 rounded-full bg-accent/10 blur-3xl" />
        <div className="relative flex items-center gap-3">
          <div className="grid h-10 w-10 place-items-center rounded-xl bg-accent/15 text-accent"><BadgeIndianRupee size={22} /></div>
          <div className="text-lg font-semibold tracking-tight">Finora</div>
        </div>
        <div className="relative">
          <h1 className="max-w-lg text-4xl font-semibold leading-tight tracking-tight">Most finance apps show you your numbers. <span className="text-accent">Finora understands them.</span></h1>
          <p className="mt-4 max-w-md text-muted">One place for every account, card, investment, loan and asset - analysed by trained models, projected to financial independence, and explained by an AI CFO.</p>
          <div className="mt-8 grid max-w-lg grid-cols-3 gap-3 text-sm">
            {[[BrainCircuit, '5 ML models', 'each measured against a simple baseline'], [Flame, 'FIRE forecast', 'retirement age, corpus and runway'], [Bot, 'AI CFO', 'answers only with verified numbers']].map(([I, t, d]) => (
              <div key={t} className="rounded-2xl border border-line bg-raised/60 p-3"><I size={17} className="text-accent" /><div className="mt-2 font-medium">{t}</div><div className="mt-0.5 text-xs text-muted">{d}</div></div>
            ))}
          </div>
        </div>
        <div className="relative text-xs text-faint">Academic project · synthetic demonstration data · educational guidance only</div>
      </div>

      <div className="flex items-center justify-center p-8">
        <div className="w-full max-w-md">
          <h2 className="text-2xl font-semibold tracking-tight">Open a financial profile</h2>
          <p className="mt-1.5 text-sm text-muted">Enter a PAN to retrieve the financial identity linked to it.</p>
          <form onSubmit={(e) => { e.preventDefault(); submit() }} className="mt-6">
            <label className="mb-1.5 block text-xs text-muted">PAN</label>
            <div className={cx('flex items-center gap-2 rounded-2xl border bg-surface p-2 pl-4', err ? 'border-bad/60' : 'border-line focus-within:border-accent')}>
              <input autoFocus value={pan} maxLength={10} spellCheck={false} autoComplete="off" placeholder="ABCDE1234F"
                onChange={(e) => { setPan(e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, '')); setErr(null) }}
                className="num w-full bg-transparent font-mono text-xl tracking-[0.28em] outline-none placeholder:tracking-[0.28em] placeholder:text-faint/60" />
              <Button loading={busy} icon={ArrowRight} disabled={pan.length !== 10}>Retrieve</Button>
            </div>
            <div className="mt-1.5 h-5 text-xs">{err ? <span className="text-bad">{err}</span> : hint ? <span className="text-faint">{hint}</span> : null}</div>
          </form>

          <div className="mt-5">
            <div className="mb-2 text-xs text-muted">Demo profiles</div>
            <div className="grid gap-2">
              {DEMOS.map(([p, d]) => (
                <button key={p} onClick={() => { setPan(p); submit(p) }} className="flex items-center justify-between rounded-xl border border-line bg-surface px-3.5 py-2.5 text-left hover:border-accent/50">
                  <span className="num font-mono text-sm tracking-widest">{p}</span><span className="text-xs text-muted">{d}</span>
                </button>
              ))}
            </div>
          </div>

          <div className="mt-6 space-y-2 rounded-2xl border border-line bg-surface p-4 text-xs leading-relaxed text-muted">
            <div className="flex gap-2"><Lock size={14} className="mt-0.5 shrink-0 text-accent" /> The PAN is sent in the request body, stored only as a salted hash, and shown masked everywhere else.</div>
            <div className="flex gap-2"><ShieldCheck size={14} className="mt-0.5 shrink-0 text-accent" /> These are fictional identifiers mapped to synthetic profiles. A real PAN gives no access to anyone's finances - a production system would use the RBI Account Aggregator framework with user consent.</div>
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
    </div>
  )
}
