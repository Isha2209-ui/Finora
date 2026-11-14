import { useState } from 'react'
import { ArrowRight, BadgeIndianRupee, KeyRound, Lock, ShieldCheck } from 'lucide-react'
import { useAuth } from '../auth.jsx'
import { Button, Field, Input, cx } from '../components/ui.jsx'

// Sign in / create account. Accounts are local to this Finora server: e-mail + password (argon2id-hashed).
export default function SignIn() {
  const { login, register } = useAuth()
  const [mode, setMode] = useState('signin')
  const [form, setForm] = useState({ email: '', password: '', name: '' })
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)
  const set = (k) => (e) => { setForm((f) => ({ ...f, [k]: e.target.value })); setErr(null) }
  const creating = mode === 'register'

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true); setErr(null)
    try {
      if (creating) await register(form.email.trim(), form.password, form.name.trim())
      else await login(form.email.trim(), form.password)
    } catch (ex) { setErr(ex.message) } finally { setBusy(false) }
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
          <h1 className="max-w-lg text-4xl font-semibold leading-tight tracking-tight">Your financial identity, <span className="text-accent">kept to yourself.</span></h1>
          <p className="mt-4 max-w-md text-muted">Sign in to explore a synthetic demo identity or build your own. Profiles you create are visible only to your account.</p>
        </div>
        <div className="relative text-xs text-faint">Academic project · educational guidance only, not licensed financial advice</div>
      </div>

      <div className="flex items-center justify-center p-8">
        <div className="w-full max-w-sm">
          <h2 className="text-2xl font-semibold tracking-tight">{creating ? 'Create your account' : 'Sign in to Finora'}</h2>
          <p className="mt-1.5 text-sm text-muted">{creating ? 'E-mail and password. No verification e-mail is sent in this local version.' : 'Use the e-mail and password you registered with.'}</p>
          <form onSubmit={submit} className="mt-6 space-y-3">
            {creating && <Field label="Name (optional)"><Input value={form.name} onChange={set('name')} maxLength={80} autoComplete="name" /></Field>}
            <Field label="E-mail"><Input type="email" required value={form.email} onChange={set('email')} autoComplete="email" autoFocus /></Field>
            <Field label="Password" hint={creating ? 'At least 10 characters. A short phrase of a few words works well.' : undefined}>
              <Input type="password" required minLength={creating ? 10 : 1} maxLength={128} value={form.password} onChange={set('password')}
                autoComplete={creating ? 'new-password' : 'current-password'} />
            </Field>
            <div className={cx('min-h-5 text-xs', err ? 'text-bad' : 'text-faint')} role="alert">{err}</div>
            <Button loading={busy} icon={creating ? KeyRound : ArrowRight} className="w-full justify-center">{creating ? 'Create account' : 'Sign in'}</Button>
          </form>
          <button onClick={() => { setMode(creating ? 'signin' : 'register'); setErr(null) }} className="mt-4 text-sm text-accent hover:underline">
            {creating ? 'Already have an account? Sign in' : 'New here? Create an account'}
          </button>

          <div className="mt-8 space-y-2 rounded-2xl border border-line bg-surface p-4 text-xs leading-relaxed text-muted">
            <div className="flex gap-2"><Lock size={14} className="mt-0.5 shrink-0 text-accent" /> Passwords are stored only as argon2id hashes. Your session is an httpOnly cookie that page scripts cannot read.</div>
            <div className="flex gap-2"><ShieldCheck size={14} className="mt-0.5 shrink-0 text-accent" /> Finora never connects to your bank. Demo identities are synthetic; your own profile contains only what you enter or upload.</div>
          </div>
        </div>
      </div>
    </div>
  )
}
