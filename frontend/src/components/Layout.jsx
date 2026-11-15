// App shell (Phase 8 spec §5): seven task areas, responsive navigation, header with Ask + account menu.
//  ≥1280px labelled sidebar · 768–1279px icon rail · <768px top bar with a navigation drawer.
import { useEffect, useRef, useState } from 'react'
import { Link, NavLink, useLocation, useNavigate } from 'react-router-dom'
import {
  BadgeIndianRupee, BrainCircuit, ChevronDown, Clock, Compass, Database, FlaskConical, Home, LogOut, Menu, MessageSquare,
  RefreshCw, Repeat, Settings, Sparkles, TrendingUp, Wallet, X,
} from 'lucide-react'
import { api } from '../api'
import { useAuth } from '../auth.jsx'
import { useAsync, useFinora } from '../store.jsx'
import ChatPanel from './ChatPanel.jsx'
import { Badge, IconButton, cx, useConfirm, useToast } from './ui.jsx'

export const AREAS = [
  { to: '/', label: 'Home', icon: Home, end: true },
  { to: '/plan', label: 'Plan', icon: Compass },
  { to: '/money', label: 'Money', icon: Wallet },
  { to: '/future', label: 'Future', icon: TrendingUp },
  { to: '/models', label: 'Risk & Models', icon: BrainCircuit },
  { to: '/ask', label: 'Ask', icon: Sparkles },
  { to: '/data', label: 'Data', icon: Database },
]

function useBadges() {
  const { analysis, profileId } = useFinora()
  const review = useAsync(() => (profileId ? api.review(profileId) : Promise.resolve(null)), [profileId, analysis?.generated_at])
  return {
    '/plan': analysis?.alerts?.filter((a) => a.level !== 'info').length || 0,
    '/data': review.data?.total || 0,
  }
}

function NavItems({ compact, onNavigate }) {
  const badges = useBadges()
  return (
    <ul className="space-y-0.5">
      {AREAS.map(({ to, label, icon: Icon, end }) => (
        <li key={to}>
          <NavLink to={to} end={end} onClick={onNavigate} title={compact ? label : undefined} aria-label={compact ? label : undefined}
            className={({ isActive }) => cx('group relative flex items-center rounded-lg text-sm font-medium transition-colors',
              compact ? 'h-11 w-11 justify-center' : 'h-10 gap-3 px-3',
              isActive ? 'bg-accent-soft text-accent' : 'text-ink-2 hover:bg-subtle hover:text-ink')}>
            {({ isActive }) => (<>
              {isActive && !compact && <span aria-hidden className="absolute top-2 bottom-2 left-0 w-0.5 rounded-full bg-accent" />}
              <Icon size={18} aria-hidden className={isActive ? 'text-accent' : 'text-muted group-hover:text-ink'} />
              {!compact && <span className="flex-1">{label}</span>}
              {badges[to] > 0 && (compact
                ? <span aria-label={`${badges[to]} to review`} className="absolute top-1.5 right-1.5 h-2 w-2 rounded-full bg-bad" />
                : <span className="num rounded-full bg-bad-soft px-1.5 text-micro font-medium text-bad" aria-label={`${badges[to]} to review`}>{badges[to]}</span>)}
            </>)}
          </NavLink>
        </li>
      ))}
    </ul>
  )
}

function Brand({ compact }) {
  return (
    <Link to="/" className={cx('flex items-center gap-2.5 rounded-lg', compact && 'justify-center')} aria-label="Finora home">
      <span className="grid h-8 w-8 place-items-center rounded-lg bg-accent text-white"><BadgeIndianRupee size={18} aria-hidden /></span>
      {!compact && <span className="text-[17px] font-semibold tracking-tight text-ink">Finora</span>}
    </Link>
  )
}

function AccountMenu() {
  const { account, logout } = useAuth()
  const { signOut, refresh, loading } = useFinora()
  const [open, setOpen] = useState(false)
  const ref = useRef(null)
  const nav = useNavigate()
  const toast = useToast()
  useEffect(() => {
    if (!open) return
    const off = (e) => { if (!ref.current?.contains(e.target)) setOpen(false) }
    const esc = (e) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', off); document.addEventListener('keydown', esc)
    return () => { document.removeEventListener('mousedown', off); document.removeEventListener('keydown', esc) }
  }, [open])
  const name = account?.display_name || account?.email || ''
  const item = 'flex w-full items-center gap-2.5 rounded-md px-3 h-10 text-sm text-ink-2 hover:bg-subtle hover:text-ink'
  return (
    <div ref={ref} className="relative">
      <button type="button" onClick={() => setOpen((v) => !v)} aria-haspopup="menu" aria-expanded={open} aria-label="Account menu"
        className="flex h-10 items-center gap-2 rounded-lg pr-2 pl-1 hover:bg-subtle">
        <span className="grid h-8 w-8 place-items-center rounded-full bg-subtle text-[13px] font-semibold text-ink-2">{(name[0] || '?').toUpperCase()}</span>
        <ChevronDown size={14} className="text-muted" aria-hidden />
      </button>
      {open && (
        <div role="menu" className="rise absolute right-0 z-40 mt-2 w-64 rounded-xl border border-line bg-bg p-1.5 shadow-overlay">
          <div className="px-3 py-2"><div className="truncate text-sm font-medium text-ink">{account?.display_name || 'Signed in'}</div><div className="truncate text-micro text-faint">{account?.email}</div></div>
          <div className="my-1 h-px bg-line" />
          <button role="menuitem" className={item} onClick={() => { setOpen(false); nav('/settings') }}><Settings size={16} aria-hidden /> Settings</button>
          <button role="menuitem" className={item} disabled={loading}
            onClick={async () => { setOpen(false); const a = await refresh({ rerun: true }); if (a) toast('Analysis re-run with your latest data', { tone: 'good' }) }}>
            <RefreshCw size={16} aria-hidden className={loading ? 'animate-spin' : ''} /> Re-run analysis</button>
          <button role="menuitem" className={item} onClick={() => { setOpen(false); signOut(); nav('/') }}><Repeat size={16} aria-hidden /> Switch profile</button>
          <div className="my-1 h-px bg-line" />
          <button role="menuitem" className={item} onClick={() => { setOpen(false); logout() }}><LogOut size={16} aria-hidden /> Sign out</button>
        </div>
      )}
    </div>
  )
}

function SandboxBanner({ profile }) {
  const { select, refresh } = useFinora()
  const confirm = useConfirm()
  const toast = useToast()
  const [busy, setBusy] = useState(false)
  const hours = Math.max(0, Math.round((new Date(profile.expires_at + 'Z') - Date.now()) / 36e5))
  const reset = async () => {
    if (!await confirm({ title: 'Reset this demo copy?', body: 'Every change you made to this demo person is discarded and the original synthetic data is restored.', confirm: 'Reset demo', danger: true })) return
    setBusy(true)
    try { const r = await api.resetSandbox(profile.internal_id); select(r.profile.internal_id); refresh({ rerun: true }); toast('Demo copy reset', { tone: 'good' }) }
    catch (e) { toast(e.message, { tone: 'bad' }) } finally { setBusy(false) }
  }
  return (
    <div className="no-print flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-warn/20 bg-warn-soft px-4 py-2 text-[13px] text-warn sm:px-6">
      <FlaskConical size={15} aria-hidden /> <span><b className="font-semibold">Demo person, synthetic data.</b> <span className="hidden sm:inline">Your private copy of a fictional person; no real bank data is involved.</span></span>
      <span className="flex items-center gap-1"><Clock size={13} aria-hidden /> deleted in {hours} h</span>
      <div className="flex-1" />
      <button type="button" onClick={reset} disabled={busy} className="h-8 rounded-md border border-warn/30 bg-bg px-3 text-[13px] font-medium hover:bg-warn-soft disabled:opacity-50">{busy ? 'Resetting…' : 'Reset demo'}</button>
    </div>
  )
}

export default function Layout({ children }) {
  const { analysis, profile } = useFinora()
  const [chat, setChat] = useState(false)
  const [drawer, setDrawer] = useState(false)
  const loc = useLocation()
  useEffect(() => { setDrawer(false) }, [loc.pathname])
  const p = analysis?.profile
  const hs = analysis?.health_score
  const onAsk = loc.pathname === '/ask'
  // "Ask about this" links elsewhere open the panel with a pre-filled question.
  const [seed, setSeed] = useState(null)
  useEffect(() => {
    const h = (e) => { if (loc.pathname !== '/ask') { setSeed({ q: e.detail, at: Date.now() }); setChat(true) } }
    window.addEventListener('finora:ask', h)
    return () => window.removeEventListener('finora:ask', h)
  }, [loc.pathname])
  return (
    <div className="flex h-full bg-canvas">
      <a href="#main" className="skip-link">Skip to content</a>
      {/* sidebar (xl) and icon rail (md–lg) */}
      <aside aria-label="Main" className="hidden shrink-0 flex-col border-r border-line bg-canvas md:flex md:w-[72px] md:items-center xl:w-[232px] xl:items-stretch">
        <div className="flex h-16 items-center px-5 md:px-0 xl:px-5"><span className="hidden xl:block"><Brand /></span><span className="xl:hidden"><Brand compact /></span></div>
        <nav aria-label="Primary" className="flex-1 overflow-y-auto px-3 pt-2 md:px-0 xl:px-3">
          <div className="hidden xl:block"><NavItems /></div>
          <div className="xl:hidden"><NavItems compact /></div>
        </nav>
      </aside>

      {/* mobile navigation drawer */}
      {drawer && (
        <div className="fixed inset-0 z-50 md:hidden">
          <div className="fade-in absolute inset-0 bg-ink/25" onClick={() => setDrawer(false)} aria-hidden />
          <div role="dialog" aria-modal="true" aria-label="Navigation" className="slide-in relative flex h-full w-72 flex-col bg-bg shadow-overlay">
            <div className="flex h-16 items-center justify-between px-5"><Brand /><IconButton icon={X} label="Close navigation" onClick={() => setDrawer(false)} /></div>
            <nav aria-label="Primary" className="flex-1 overflow-y-auto px-3"><NavItems onNavigate={() => setDrawer(false)} /></nav>
          </div>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="relative z-30 flex h-16 shrink-0 items-center gap-2 border-b border-line bg-bg/90 px-3 backdrop-blur sm:gap-3 sm:px-6">
          <IconButton icon={Menu} label="Open navigation" onClick={() => setDrawer(true)} className="md:hidden" />
          {p ? (
            <div className="flex min-w-0 items-center gap-3">
              <div className="min-w-0">
                <div className="truncate text-sm font-semibold text-ink">{p.name}</div>
                <div className="hidden truncate text-micro text-faint sm:block">{p.age} · {p.occupation}, {p.city}{profile?.kind === 'sandbox' ? ' · demo copy' : profile?.kind === 'template' ? ' · read-only demo' : ''}</div>
              </div>
            </div>
          ) : <div className="text-sm text-muted">Loading profile…</div>}
          <div className="flex-1" />
          {hs && hs.score != null && (
            <Link to="/plan?tab=health" className="hidden sm:block" aria-label={`Financial health ${hs.score} out of 100, ${hs.band}. Open Plan, Health.`}>
              <Badge tone={hs.score >= 65 ? 'good' : hs.score >= 45 ? 'warn' : 'bad'} className="h-7 px-2.5">Health {Math.round(hs.score)} · {hs.band}</Badge>
            </Link>
          )}
          {!onAsk && (
            <button type="button" onClick={() => setChat((v) => !v)} aria-expanded={chat} aria-controls="ask-panel" aria-label="Ask Finora"
              className={cx('flex h-10 items-center gap-2 rounded-lg px-3 text-sm font-medium transition-colors',
                chat ? 'bg-accent-soft text-accent' : 'text-ink hover:bg-subtle')}>
              <MessageSquare size={17} aria-hidden /> <span className="hidden sm:inline">Ask</span>
            </button>
          )}
          <AccountMenu />
        </header>
        {profile?.kind === 'sandbox' && <SandboxBanner profile={profile} />}
        <div className="flex min-h-0 flex-1">
          <main id="main" tabIndex={-1} key={loc.pathname} className={cx('rise min-w-0 flex-1 focus:outline-none', onAsk ? 'overflow-hidden' : 'overflow-y-auto')}>
            {onAsk ? children : <div className="mx-auto w-full max-w-[1200px] px-4 py-6 sm:px-6 sm:py-8 lg:px-10">{children}</div>}
          </main>
          {chat && !onAsk && (
            <div id="ask-panel" className="no-print fixed inset-0 z-40 flex flex-col bg-bg sm:static sm:z-auto sm:w-[400px] sm:shrink-0 sm:border-l sm:border-line">
              <ChatPanel onClose={() => setChat(false)} seed={seed} />
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
