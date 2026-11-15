// Sign in / create account. Accounts are local to this Finora server: e-mail + password (argon2id-hashed), httpOnly session cookie.
// There is no password recovery in this local version (no e-mail service); the page says so instead of offering a dead link.
import { useRef, useState } from 'react'
import { ArrowRight, BadgeIndianRupee, Eye, EyeOff, Lock, ShieldCheck, Sparkles } from 'lucide-react'
import { useAuth } from '../auth.jsx'
import { Button, Field, Input, cx } from '../components/ui.jsx'

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

const POINTS = [
  [Sparkles, 'A plan, not a dashboard', 'Finora reads your accounts and statements and tells you the few things that matter, with the evidence.'],
  [ShieldCheck, 'Honest about its models', 'Every model shows its status, its data and its limits. Unusual never means fraud.'],
  [Lock, 'Private by design', 'Your profiles are visible only to your account. The AI assistant runs on this computer.'],
]

export default function SignIn() {
  const { login, register } = useAuth()
  const [mode, setMode] = useState('signin')
  const [form, setForm] = useState({ email: '', password: '', name: '' })
  const [errors, setErrors] = useState({})
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)
  const [show, setShow] = useState(false)
  const refs = { email: useRef(null), password: useRef(null) }
  const creating = mode === 'register'
  const set = (k) => (e) => { setForm((f) => ({ ...f, [k]: e.target.value })); setErr(null); setErrors((x) => ({ ...x, [k]: null })) }

  const validate = () => {
    const v = {}
    if (!EMAIL_RE.test(form.email.trim())) v.email = 'Enter an e-mail address like name@example.com.'
    if (!form.password) v.password = 'Enter your password.'
    else if (creating && form.password.length < 10) v.password = 'Use at least 10 characters. A short phrase of a few words works well.'
    setErrors(v)
    const first = ['email', 'password'].find((k) => v[k])
    if (first) refs[first].current?.focus()
    return !first
  }
  const submit = async (e) => {
    e.preventDefault()
    if (!validate()) return
    setBusy(true); setErr(null)
    try {
      if (creating) await register(form.email.trim(), form.password, form.name.trim())
      else await login(form.email.trim(), form.password)
    } catch (ex) { setErr(ex.message) } finally { setBusy(false) }
  }
  const switchMode = () => { setMode(creating ? 'signin' : 'register'); setErr(null); setErrors({}) }

  return (
    <div className="grid min-h-full bg-bg lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      <div className="hidden flex-col justify-between border-r border-line bg-canvas px-14 py-12 lg:flex">
        <div className="flex items-center gap-2.5"><span className="grid h-9 w-9 place-items-center rounded-lg bg-accent text-white"><BadgeIndianRupee size={20} aria-hidden /></span><span className="text-lg font-semibold tracking-tight">Finora</span></div>
        <div>
          <h1 className="max-w-md text-[34px] leading-[42px] font-semibold tracking-tight text-ink">Understand your money. Decide with evidence.</h1>
          <ul className="mt-10 max-w-md space-y-7">
            {POINTS.map(([I, t, d]) => (
              <li key={t} className="flex gap-4"><span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-bg text-accent shadow-xs ring-1 ring-line"><I size={18} aria-hidden /></span>
                <div><div className="text-[15px] font-semibold text-ink">{t}</div><div className="mt-1 text-sm leading-6 text-muted">{d}</div></div></li>
            ))}
          </ul>
        </div>
        <p className="text-micro text-faint">Finora · financial intelligence</p>
      </div>

      <div className="flex items-center justify-center px-5 py-12 sm:px-8">
        <div className="w-full max-w-[380px]">
          <div className="mb-10 flex items-center gap-2.5 lg:hidden"><span className="grid h-9 w-9 place-items-center rounded-lg bg-accent text-white"><BadgeIndianRupee size={20} aria-hidden /></span><span className="text-lg font-semibold tracking-tight">Finora</span></div>
          <h2 className="text-title font-semibold tracking-tight text-ink">{creating ? 'Create your account' : 'Sign in to Finora'}</h2>
          <p className="mt-2 text-[15px] text-muted">{creating ? 'Just an e-mail and a password. No verification e-mail is sent in this local version.' : 'Welcome back. Use the e-mail and password you registered with.'}</p>
          <form onSubmit={submit} noValidate className="mt-8 space-y-5">
            {creating && <Field label="Name (optional)"><Input name="name" value={form.name} onChange={set('name')} maxLength={80} autoComplete="name" /></Field>}
            <Field label="E-mail" error={errors.email}>
              <Input ref={refs.email} type="email" name="email" inputMode="email" spellCheck={false} value={form.email} onChange={set('email')} autoComplete="email"
                aria-invalid={!!errors.email} autoFocus={window.matchMedia?.('(pointer: fine)').matches} placeholder="name@example.com" />
            </Field>
            <Field id="pw" label="Password" error={errors.password} hint={creating ? 'At least 10 characters. A short phrase of a few words works well.' : undefined}>
              <div className="relative">
                <Input id="pw" ref={refs.password} type={show ? 'text' : 'password'} name="password" maxLength={128} value={form.password} onChange={set('password')}
                  autoComplete={creating ? 'new-password' : 'current-password'} aria-invalid={!!errors.password} aria-describedby={errors.password ? 'pw-err' : creating ? 'pw-hint' : undefined} className="pr-11" />
                <button type="button" onClick={() => setShow((v) => !v)} aria-label={show ? 'Hide password' : 'Show password'} aria-pressed={show}
                  className="absolute top-0 right-0 grid h-10 w-10 place-items-center text-muted hover:text-ink">{show ? <EyeOff size={17} aria-hidden /> : <Eye size={17} aria-hidden />}</button>
              </div>
            </Field>
            {err && <div role="alert" className="rounded-lg border border-bad/25 bg-bad-soft px-3.5 py-2.5 text-sm text-bad">{err}</div>}
            <Button type="submit" size="lg" loading={busy} className="w-full">{busy ? (creating ? 'Creating account…' : 'Signing in…') : <>{creating ? 'Create account' : 'Sign in'} <ArrowRight size={16} aria-hidden /></>}</Button>
          </form>
          <p className="mt-6 text-sm text-muted">
            {creating ? 'Already have an account?' : 'New to Finora?'}{' '}
            <button type="button" onClick={switchMode} className="font-medium text-accent hover:underline">{creating ? 'Sign in' : 'Create an account'}</button>
          </p>
          {!creating && <p className="mt-3 text-[13px] leading-5 text-faint">Forgot your password? This local version has no e-mail recovery, so a new account is the way back in.</p>}
          <div className={cx('mt-10 border-t border-line pt-6 text-[13px] leading-5 text-muted')}>
            <p className="flex gap-2"><Lock size={15} className="mt-0.5 shrink-0 text-faint" aria-hidden /> Passwords are stored only as argon2id hashes. Your session is an httpOnly cookie that page scripts cannot read.</p>
          </div>
        </div>
      </div>
    </div>
  )
}
