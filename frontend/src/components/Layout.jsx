import { useState } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import {
  Activity, BadgeIndianRupee, Bot, BrainCircuit, CreditCard, Database, FileText, Flame, Landmark, Lightbulb, LogOut,
  Clock, Eye, FlaskConical, MessageSquare, PencilLine, PiggyBank, RefreshCw, Repeat, Scale, ScanSearch, TrendingUp, UserRound, Wallet,
} from 'lucide-react'
import { api } from '../api'
import { useAuth } from '../auth.jsx'
import { useFinora } from '../store.jsx'
import ChatPanel from './ChatPanel.jsx'
import { Badge, cx } from './ui.jsx'

const NAV = [
  ['Overview', [['/identity', 'Financial Identity', UserRound], ['/records', 'My Data (add & edit)', PencilLine], ['/accounts', 'Accounts & Cards', Landmark], ['/investments', 'Investments & Assets', TrendingUp]]],
  ['Intelligence', [['/transactions', 'Transaction Intelligence', ScanSearch], ['/forecast', 'Cash-Flow Forecast', Activity], ['/credit', 'Credit & Debt', CreditCard], ['/budget', 'Budget, Savings & Tax', PiggyBank]]],
  ['Planning', [['/fire', 'FIRE & Retirement', Flame], ['/decision', 'Decision Simulator', Scale], ['/cfo', 'AI CFO', Bot], ['/recommendations', 'Recommendations', Lightbulb]]],
  ['System', [['/reports', 'Reports', FileText], ['/models', 'Model Lab', BrainCircuit], ['/data', 'Profile & Data', Database]]],
]

function SandboxBanner({ profile }) {
  const { select, refresh } = useFinora()
  const [busy, setBusy] = useState(false)
  const hours = Math.max(0, Math.round((new Date(profile.expires_at + 'Z') - Date.now()) / 36e5))
  const reset = async () => {
    if (!window.confirm('Reset this demo copy? Every change you made to it will be discarded.')) return
    setBusy(true)
    try { const r = await api.resetSandbox(profile.internal_id); select(r.profile.internal_id); refresh({ rerun: true }) } finally { setBusy(false) }
  }
  return (
    <div className="no-print flex items-center gap-3 border-b border-warn/25 bg-warn/8 px-6 py-1.5 text-xs text-warn">
      <FlaskConical size={13} /> <span><b>Demo identity, simulated data.</b> This is your private copy of a fictional person; no real bank data is involved.</span>
      <span className="flex items-center gap-1 text-warn/80"><Clock size={12} /> deleted in {hours} h</span>
      <div className="flex-1" />
      <button onClick={reset} disabled={busy} className="rounded-md border border-warn/40 px-2 py-0.5 hover:bg-warn/15 disabled:opacity-50">{busy ? 'Resetting…' : 'Reset demo'}</button>
    </div>
  )
}

export default function Layout({ children }) {
  const { analysis, profile, signOut, refresh, loading } = useFinora()
  const { account, logout } = useAuth()
  const [chat, setChat] = useState(false)
  const loc = useLocation()
  const p = analysis?.profile
  const hs = analysis?.health_score
  const alerts = analysis?.alerts?.filter((a) => a.level !== 'info').length || 0
  return (
    <div className="flex h-full">
      <aside className="flex w-60 shrink-0 flex-col border-r border-line bg-surface/60">
        <div className="flex items-center gap-2.5 px-5 pt-5 pb-4">
          <div className="grid h-8 w-8 place-items-center rounded-lg bg-accent/15 text-accent"><BadgeIndianRupee size={19} /></div>
          <div><div className="text-[15px] font-semibold tracking-tight">Finora</div><div className="text-[10px] uppercase tracking-[0.14em] text-faint">Financial intelligence</div></div>
        </div>
        <nav className="flex-1 overflow-y-auto px-3 pb-4">
          {NAV.map(([group, items]) => (
            <div key={group} className="mt-3">
              <div className="px-2 pb-1 text-[10px] font-medium uppercase tracking-[0.14em] text-faint">{group}</div>
              {items.map(([to, label, Icon]) => (
                <NavLink key={to} to={to} className={({ isActive }) => cx('flex items-center gap-2.5 rounded-lg px-2.5 py-[7px] text-[13px] transition',
                  isActive ? 'bg-accent/12 text-accent' : 'text-muted hover:bg-raised hover:text-ink')}>
                  <Icon size={15} /> <span className="flex-1">{label}</span>
                  {to === '/recommendations' && alerts > 0 && <span className="num rounded-full bg-bad/20 px-1.5 text-[10px] text-bad">{alerts}</span>}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>
        <div className="border-t border-line p-3 text-[10.5px] leading-relaxed text-faint">
          {profile?.kind === 'private' ? 'Your own data, visible only to your account.' : 'Synthetic demo data.'} Educational guidance, not a substitute for a licensed financial advisor.
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center gap-4 border-b border-line bg-surface/40 px-6 py-3">
          {p ? (
            <div className="flex min-w-0 items-center gap-3">
              <div className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-raised text-sm font-semibold text-accent">{p.name.split(' ').map((w) => w[0]).slice(0, 2).join('')}</div>
              <div className="min-w-0">
                <div className="truncate text-sm font-medium">{p.name} <span className="font-normal text-muted">· {p.age} · {p.occupation}, {p.city}</span></div>
                <div className="num text-xs text-faint">{p.pan_masked ? `PAN ${p.pan_masked} · ` : ''}{p.internal_id}</div>
              </div>
            </div>
          ) : <div className="text-sm text-muted">Loading profile…</div>}
          {profile?.read_only && <Badge tone="warn"><Eye size={12} /> Read-only demo</Badge>}
          <div className="flex-1" />
          {hs && (hs.score == null ? <Badge><Wallet size={12} /> Health score: not enough data</Badge>
            : <Badge tone={hs.score >= 65 ? 'good' : hs.score >= 45 ? 'warn' : 'bad'}><Wallet size={12} /> Health {hs.score}/100 · {hs.band}</Badge>)}
          <button onClick={() => refresh({ rerun: true })} title="Re-run the full analysis" className="rounded-lg border border-line bg-raised p-2 text-muted hover:text-ink">
            <RefreshCw size={15} className={loading ? 'animate-spin' : ''} />
          </button>
          <button onClick={() => setChat((v) => !v)} className={cx('flex items-center gap-2 rounded-lg border px-3 py-2 text-sm', chat ? 'border-accent/50 bg-accent/15 text-accent' : 'border-line bg-raised text-ink hover:border-faint')}>
            <MessageSquare size={15} /> Ask AI CFO
          </button>
          <button onClick={signOut} title="Switch profile" className="rounded-lg border border-line bg-raised p-2 text-muted hover:text-ink"><Repeat size={15} /></button>
          <div className="hidden max-w-40 truncate text-xs text-faint xl:block" title={account?.email}>{account?.display_name || account?.email}</div>
          <button onClick={logout} title="Sign out of your account" className="rounded-lg border border-line bg-raised p-2 text-muted hover:text-ink"><LogOut size={15} /></button>
        </header>
        {profile?.kind === 'sandbox' && <SandboxBanner profile={profile} />}
        <div className="flex min-h-0 flex-1">
          <main key={loc.pathname} className="rise min-w-0 flex-1 overflow-y-auto px-6 py-6">{children}</main>
          {chat && loc.pathname !== '/cfo' && <div className="no-print w-[380px] shrink-0 border-l border-line bg-surface/60"><ChatPanel onClose={() => setChat(false)} /></div>}
        </div>
      </div>
    </div>
  )
}
