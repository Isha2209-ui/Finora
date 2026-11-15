// The AI CFO conversation (Phase 7 engine, Phase 8 presentation). One component for the side panel and the Ask page.
// Streaming states, "Draft, being checked", interpretation, sources, Stop and the nothing-saved notice are Phase 7 behaviour.
import { useEffect, useMemo, useRef, useState } from 'react'
import { ArrowUp, Calculator, ChevronDown, Cpu, ShieldCheck, Sparkles, Square, Trash2, X } from 'lucide-react'
import { api } from '../api'
import { useFinora } from '../store.jsx'
import { Badge, IconButton, cx, useConfirm } from './ui.jsx'

const GENERAL = ['What is an index fund?', 'Explain the rule of 72.']
const PERSONAL = ['Where does most of my money go?', 'How much did I spend on dining last month?', 'Can I afford an ₹8 lakh car?',
  'How reliable is my cash-flow forecast?', 'Explain my credit risk.', 'What should I focus on first?']
export const TOOL_LABEL = { affordability: 'Decision simulator', fire_forecast: 'FIRE engine', runway: 'Runway calculator', tax_comparison: 'Tax calculator',
  debts_and_payoff: 'Debt payoff', credit_cards: 'Credit cards', spending_by_category: 'Spending by category', net_worth: 'Net worth',
  spending_forecast: 'Forecast model', unusual_transactions: 'Anomaly scanner', profile_summary: 'Profile summary', recommendations: 'Recommendations',
  emi_calculator: 'EMI calculator', investments: 'Portfolio', insurance: 'Insurance', goals: 'Goals', peer_comparison: 'Peer model',
  cash_flow: 'Cash flow', glossary: 'Glossary', spending: 'Spending', income: 'Income', compare_months: 'Month comparison', transactions: 'Transactions',
  accounts_and_balances: 'Accounts & balances', credit_risk: 'Credit risk (XGBoost + SHAP)', anomaly_scan: 'Anomaly scanner (Isolation Forest)',
  cash_flow_forecast: 'Cash-flow forecast (XGBoost)', peer_benchmark: 'Peer benchmarking (K-Means)', category_suggestions: 'Categoriser (TF-IDF)',
  finora_plan: 'Finora Plan', plan_what_if: 'Plan scenarios', alerts: 'Alerts', health_score: 'Health score', model_info: 'Model Lab' }
const PAGE = 30
const clean = (t) => String(t || '').replace(/\n*\s*Educational guidance, not a substitute for a licensed financial advisor\.?/g, '').trim()

function Message({ m }) {
  const user = m.role === 'user'
  return (
    <div className={cx('flex', user ? 'justify-end' : 'justify-start')}>
      <div className={cx('max-w-[88%] text-[15px] leading-6', user ? 'rounded-2xl rounded-br-md bg-accent px-4 py-2.5 text-white' : 'w-full max-w-[680px] text-ink')}>
        {m.pending ? (
          <div className="space-y-2" aria-busy="true">
            <div className="flex items-center gap-2 text-[13px] text-muted"><span className="h-2 w-2 animate-pulse rounded-full bg-accent" aria-hidden />{m.status}</div>
            {m.interpretation && <div className="text-[13px] text-faint">Understood as: {m.interpretation}</div>}
            {m.tools?.length > 0 && <div className="flex flex-wrap gap-1.5">{[...new Set(m.tools)].map((t) => <Badge key={t}><Calculator size={11} aria-hidden /> {TOOL_LABEL[t] || t}</Badge>)}</div>}
            {m.content && <div className="rounded-lg border border-dashed border-warn/40 bg-warn-soft/50 px-3 py-2 whitespace-pre-wrap text-ink-2">
              <div className="mb-1 text-micro font-medium text-warn">Draft, being checked — not an answer yet</div>{m.content}</div>}
          </div>
        ) : user ? <div className="whitespace-pre-wrap">{m.content}</div> : (
          <div className={cx(m.meta?.error && 'rounded-lg border border-line bg-subtle px-3 py-2 text-ink-2')}>
            <div className="whitespace-pre-wrap">{m.content}</div>
            {m.meta?.interpretation && <div className="mt-2 text-[13px] text-faint">Understood as: {m.meta.interpretation}</div>}
            {m.meta && !m.meta.error && (
              <div className="mt-3 space-y-2">
                {m.meta.notice && <div className="rounded-md bg-warn-soft px-2.5 py-1.5 text-[13px] text-warn">{m.meta.notice}</div>}
                <div className="flex flex-wrap items-center gap-1.5">
                  {(m.meta.tools_used || []).filter((t, k, a) => a.indexOf(t) === k).map((t) => <Badge key={t} tone="accent"><Calculator size={11} aria-hidden /> {TOOL_LABEL[t] || t}</Badge>)}
                  {m.meta.mode === 'general' && <Badge>General knowledge · no personal data used</Badge>}
                  {m.meta.verified === false ? <Badge tone="warn">Figures could not be verified</Badge>
                    : (m.meta.tools_used || []).length > 0 && <Badge tone="good"><ShieldCheck size={11} aria-hidden /> Figures checked</Badge>}
                  <span className="text-micro text-faint">{m.meta.engine}{m.meta.seconds ? ` · ${m.meta.seconds}s` : ''}</span>
                </div>
                {(m.meta.tool_calls || []).length > 0 && (
                  <details className="text-[13px] text-muted">
                    <summary className="cursor-pointer select-none hover:text-ink">Sources ({m.meta.tool_calls.length})</summary>
                    <ul className="mt-1.5 space-y-1 text-micro">{m.meta.tool_calls.map((c, k) => (
                      <li key={k} className="font-mono break-all text-faint">{c.tool}({Object.entries(c.arguments || {}).map(([a, v]) => `${a}=${v}`).join(', ')}){c.error ? ` · ${c.error}` : ''}</li>))}</ul>
                  </details>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

export default function ChatPanel({ onClose, seed, variant = 'panel' }) {
  const { profileId, analysis } = useFinora()
  const confirm = useConfirm()
  const [msgs, setMsgs] = useState([])
  const [loaded, setLoaded] = useState(false)
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [status, setStatus] = useState(null)
  const [shown, setShown] = useState(PAGE)
  const [announce, setAnnounce] = useState('')
  const scroller = useRef(null)
  const input = useRef(null)
  const abortRef = useRef(null)
  const page = variant === 'page'

  useEffect(() => {
    setLoaded(false)
    api.chatHistory(profileId).then((h) => setMsgs(h.map((m) => ({ role: m.role, content: m.role === 'assistant' ? clean(m.content) : m.content, meta: m.meta })))).catch(() => {}).finally(() => setLoaded(true))
    api.cfoStatus().then(setStatus).catch(() => setStatus({ available: false }))
  }, [profileId])
  useEffect(() => { if (seed?.q) { setText(seed.q); setTimeout(() => input.current?.focus(), 0) } }, [seed])
  useEffect(() => { const el = scroller.current; if (el) el.scrollTop = el.scrollHeight }, [msgs, busy])
  useEffect(() => {
    const esc = (e) => { if (e.key === 'Escape' && abortRef.current) { e.preventDefault(); abortRef.current.abort() } }
    document.addEventListener('keydown', esc)
    return () => document.removeEventListener('keydown', esc)
  }, [])

  // Suggestions from the user's real priorities, plus a couple of general ones.
  const suggestions = useMemo(() => {
    const fromAlerts = (analysis?.alerts || []).filter((a) => a.level !== 'info').slice(0, 2).map((a) => `Explain: ${a.title}`)
    return [...fromAlerts, ...PERSONAL].slice(0, 6).concat(GENERAL.slice(0, page ? 2 : 1))
  }, [analysis, page])

  const patchLast = (fn) => setMsgs((m) => { const c = [...m]; c[c.length - 1] = fn(c[c.length - 1]); return c })
  const send = async (q) => {
    const message = (q ?? text).trim()
    if (!message || busy) return
    setText(''); setBusy(true); setAnnounce('Finora is answering')
    setMsgs((m) => [...m, { role: 'user', content: message }, { role: 'assistant', pending: true, content: '', status: 'Starting…', tools: [] }])
    const ctrl = new AbortController(); abortRef.current = ctrl
    let finished = false
    try {
      await api.chatStream(profileId, message, (ev) => {
        if (ev.type === 'status') patchLast((x) => ({ ...x, status: ev.text, ...(ev.stage === 'checking' ? { content: '' } : {}) }))
        else if (ev.type === 'plan') patchLast((x) => ({ ...x, interpretation: ev.interpretation }))
        else if (ev.type === 'tool') patchLast((x) => ({ ...x, tools: [...(x.tools || []), ev.tool] }))
        else if (ev.type === 'draft') patchLast((x) => ({ ...x, content: (x.content || '') + ev.delta }))
        else if (ev.type === 'error') { finished = true; patchLast(() => ({ role: 'assistant', content: ev.message, meta: { error: true } })); setAnnounce(ev.message) }
        else if (ev.type === 'final') {
          finished = true
          patchLast(() => ({ role: 'assistant', content: clean(ev.answer), meta: { engine: ev.engine, tools_used: ev.tools_used, tool_calls: ev.tool_calls,
            verified: ev.verified, verified_by: ev.verified_by, mode: ev.mode, notice: ev.notice, interpretation: ev.interpretation,
            seconds: ev.trace?.latency_ms ? Math.round(ev.trace.latency_ms / 100) / 10 : null } }))
          setAnnounce(ev.answer)
        }
      }, ctrl.signal)
      if (!finished) patchLast(() => ({ role: 'assistant', content: 'The answer was interrupted before it was checked, so it is not shown. Please ask again.', meta: { error: true } }))
    } catch (e) {
      const msg = e.name === 'AbortError' ? 'Stopped. Nothing from this answer was saved.' : `I could not answer that: ${e.message}`
      patchLast(() => ({ role: 'assistant', content: msg, meta: { error: true } })); setAnnounce(msg)
    } finally { setBusy(false); abortRef.current = null; input.current?.focus() }
  }
  const stop = () => abortRef.current?.abort()
  const clear = async () => {
    if (!await confirm({ title: 'Clear this conversation?', body: 'All questions and answers for this profile are deleted. Your financial data is not affected.', confirm: 'Clear conversation', danger: true })) return
    await api.clearChat(profileId); setMsgs([]); setShown(PAGE)
  }
  const visible = msgs.slice(Math.max(0, msgs.length - shown))
  const model = status == null ? 'Checking the local model…' : status.available ? `${status.model} · runs on this computer` : `Local model offline — calculator answers only${status.reason ? ` (${status.reason})` : ''}`

  return (
    <div className="flex h-full min-h-0 flex-col bg-bg">
      <div className={cx('flex items-center gap-3 border-b border-line px-4', page ? 'h-14 sm:px-6' : 'h-16')}>
        <span className="grid h-8 w-8 place-items-center rounded-lg bg-gradient-to-br from-accent to-[#6e52d9] text-white"><Sparkles size={16} aria-hidden /></span>
        <div className="min-w-0 flex-1">
          <div className="text-sm font-semibold text-ink">Finora AI CFO</div>
          <div className="flex items-center gap-1 truncate text-micro text-faint" title={status?.reason || ''}><Cpu size={11} aria-hidden /> {model}</div>
        </div>
        {msgs.length > 0 && <IconButton icon={Trash2} label="Clear conversation" onClick={clear} disabled={busy} size={16} />}
        {onClose && <IconButton icon={X} label="Close Ask panel" onClick={onClose} />}
      </div>

      <div ref={scroller} className={cx('min-h-0 flex-1 overflow-y-auto', page ? 'px-4 py-6 sm:px-8' : 'px-4 py-5')} style={{ overscrollBehavior: 'contain' }}>
        <div className={cx('space-y-6', page && 'mx-auto max-w-[760px]')}>
          {loaded && msgs.length === 0 && (
            <div>
              <h2 className="text-heading font-semibold text-ink">Ask anything about money</h2>
              <p className="mt-1.5 text-sm leading-6 text-muted">General questions, or questions about your own finances. For personal questions Finora looks up your data itself and checks every figure against its own calculations before showing it.</p>
              <div className={cx('mt-4 grid gap-2', page && 'sm:grid-cols-2')}>
                {suggestions.map((s) => (
                  <button key={s} type="button" onClick={() => send(s)}
                    className="rounded-lg border border-line bg-bg px-3.5 py-2.5 text-left text-sm text-ink-2 transition-colors hover:border-accent/40 hover:bg-accent-soft hover:text-ink">{s}</button>
                ))}
              </div>
            </div>
          )}
          {msgs.length > shown && (
            <div className="text-center"><button type="button" onClick={() => setShown((n) => n + PAGE)} className="inline-flex items-center gap-1 rounded-md px-3 h-8 text-[13px] text-accent hover:bg-accent-soft">
              <ChevronDown size={14} className="rotate-180" aria-hidden /> Show {Math.min(PAGE, msgs.length - shown)} earlier messages</button></div>
          )}
          {visible.map((m, i) => <Message key={msgs.length - visible.length + i} m={m} />)}
        </div>
      </div>
      <div className="sr-only" aria-live="polite">{announce}</div>

      <form onSubmit={(e) => { e.preventDefault(); send() }} className={cx('border-t border-line bg-bg', page ? 'px-4 py-4 sm:px-8' : 'p-3')}>
        <div className={cx('rounded-xl border border-control/60 bg-bg p-1.5 shadow-xs focus-within:border-accent focus-within:ring-2 focus-within:ring-accent/15', page && 'mx-auto max-w-[760px]')}>
          <label htmlFor={`ask-input-${variant}`} className="sr-only">Your question</label>
          <div className="flex items-end gap-2">
            <textarea id={`ask-input-${variant}`} ref={input} value={text} onChange={(e) => setText(e.target.value)} rows={1} maxLength={600}
              placeholder="Ask about your money…" autoComplete="off"
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
              className="max-h-32 min-h-10 flex-1 resize-none bg-transparent px-2.5 py-2 text-[15px] text-ink placeholder:text-faint focus-visible:outline-none" />
            {busy
              ? <button type="button" onClick={stop} aria-label="Stop answering (Esc)" title="Stop (Esc)" className="grid h-10 w-10 place-items-center rounded-lg border border-line text-ink hover:bg-subtle"><Square size={14} aria-hidden /></button>
              : <button type="submit" aria-label="Send question" disabled={!text.trim()} className="grid h-10 w-10 place-items-center rounded-lg bg-gradient-to-br from-accent to-[#6e52d9] text-white disabled:opacity-40"><ArrowUp size={18} aria-hidden /></button>}
          </div>
        </div>
        <p className={cx('mt-2 text-micro text-faint', page && 'mx-auto max-w-[760px]')}>Enter to send · Shift+Enter for a new line · Esc stops an answer.</p>
      </form>
    </div>
  )
}
