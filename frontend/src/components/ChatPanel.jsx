import { useEffect, useRef, useState } from 'react'
import { Bot, Calculator, Send, ShieldCheck, Square, Trash2, X } from 'lucide-react'
import { api } from '../api'
import { useFinora } from '../store.jsx'
import { Badge, cx } from './ui.jsx'

const SUGGESTIONS = ['Analyse my entire financial situation.', 'How much did I spend on food last month?', 'Can I afford an ₹8 lakh car?',
  'Should I increase my SIP by ₹5,000?', 'Explain my credit risk.', 'How reliable is my cash-flow forecast?', 'What is an index fund?', 'What should I focus on first?']
const TOOL_LABEL = { affordability: 'Decision simulator', fire_forecast: 'FIRE engine', runway: 'Runway calculator', tax_comparison: 'Tax calculator',
  debts_and_payoff: 'Debt payoff simulator', credit_cards: 'Credit cards', spending_by_category: 'Spending by category', net_worth: 'Net worth',
  spending_forecast: 'Forecast model', unusual_transactions: 'Anomaly scanner', profile_summary: 'Profile summary', recommendations: 'Recommendations',
  emi_calculator: 'EMI calculator', investments: 'Portfolio', insurance: 'Insurance', goals: 'Goals', peer_comparison: 'Peer model',
  cash_flow: 'Cash flow', glossary: 'Glossary', spending: 'Transactions: spending', income: 'Income records', compare_months: 'Month comparison',
  accounts_and_balances: 'Accounts & balances', credit_risk: 'Credit-risk model (XGBoost + SHAP)', anomaly_scan: 'Anomaly scanner (experimental)',
  cash_flow_forecast: 'Forecast model (experimental)', peer_benchmark: 'Peer benchmark (US households)', category_suggestions: 'Category suggestions',
  finora_plan: 'Finora Plan', plan_what_if: 'Plan scenario engine', alerts: 'Alerts' }

export default function ChatPanel({ onClose, wide }) {
  const { profileId } = useFinora()
  const [msgs, setMsgs] = useState([])
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [status, setStatus] = useState(null)
  const end = useRef(null)

  useEffect(() => {
    api.chatHistory(profileId).then((h) => setMsgs(h.map((m) => ({ role: m.role, content: m.content, meta: m.meta })))).catch(() => {})
    api.cfoStatus().then(setStatus).catch(() => setStatus({ available: false }))
  }, [profileId])
  useEffect(() => { end.current?.scrollIntoView({ behavior: 'smooth' }) }, [msgs, busy])

  const abortRef = useRef(null)
  const patchLast = (fn) => setMsgs((m) => { const c = [...m]; c[c.length - 1] = fn(c[c.length - 1]); return c })
  const send = async (q) => {
    const message = (q ?? text).trim()
    if (!message || busy) return
    setText(''); setBusy(true)
    setMsgs((m) => [...m, { role: 'user', content: message }, { role: 'assistant', pending: true, content: '', status: 'Starting…', tools: [] }])
    const ctrl = new AbortController(); abortRef.current = ctrl
    let finished = false
    try {
      await api.chatStream(profileId, message, (ev) => {
        if (ev.type === 'status') patchLast((x) => ({ ...x, status: ev.text, ...(ev.stage === 'checking' ? { content: '' } : {}) }))
        else if (ev.type === 'plan') patchLast((x) => ({ ...x, interpretation: ev.interpretation }))
        else if (ev.type === 'tool') patchLast((x) => ({ ...x, tools: [...(x.tools || []), ev.tool] }))
        else if (ev.type === 'draft') patchLast((x) => ({ ...x, content: (x.content || '') + ev.delta }))
        else if (ev.type === 'error') { finished = true; patchLast(() => ({ role: 'assistant', content: ev.message, meta: { error: true } })) }
        else if (ev.type === 'final') {
          finished = true
          patchLast(() => ({ role: 'assistant', content: ev.answer, meta: { engine: ev.engine, tools_used: ev.tools_used, tool_calls: ev.tool_calls,
            verified: ev.verified, verified_by: ev.verified_by, mode: ev.mode, notice: ev.notice, interpretation: ev.interpretation,
            seconds: ev.trace?.latency_ms ? Math.round(ev.trace.latency_ms / 100) / 10 : null } }))
        }
      }, ctrl.signal)
      if (!finished) patchLast(() => ({ role: 'assistant', content: 'The answer was interrupted before it was checked, so it is not shown. Please ask again.', meta: { error: true } }))
    } catch (e) {
      patchLast(() => ({ role: 'assistant', content: e.name === 'AbortError' ? 'Stopped. Nothing from this answer was saved.' : `I could not answer that: ${e.message}`, meta: { error: true } }))
    } finally { setBusy(false); abortRef.current = null }
  }
  const stop = () => abortRef.current?.abort()
  const clear = async () => { await api.clearChat(profileId); setMsgs([]) }

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2 border-b border-line px-4 py-3">
        <div className="grid h-7 w-7 place-items-center rounded-lg bg-accent/15 text-accent"><Bot size={16} /></div>
        <div className="flex-1">
          <div className="text-sm font-semibold">AI CFO</div>
          <div className="text-[11px] text-muted" title={status?.reason || ''}>{status == null ? 'Checking the local model…' : status.available ? `${status.model} · running on this computer` : `Local model offline: calculator answers only${status.reason ? ` (${status.reason})` : ''}`}</div>
        </div>
        {msgs.length > 0 && <button onClick={clear} title="Clear conversation" className="p-1.5 text-faint hover:text-ink"><Trash2 size={15} /></button>}
        {onClose && <button onClick={onClose} className="p-1.5 text-faint hover:text-ink"><X size={16} /></button>}
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto px-4 py-4">
        {msgs.length === 0 && (
          <div>
            <p className="text-sm text-muted">Ask anything in your own words: general money questions, or questions about your own finances. For personal questions the assistant looks up your Finora data itself (accounts, transactions, plan, models), so there is nothing to upload. Every figure it states is checked against Finora's calculations.</p>
            <div className={cx('mt-3 grid gap-2', wide ? 'sm:grid-cols-2' : '')}>
              {SUGGESTIONS.map((s) => <button key={s} onClick={() => send(s)} className="rounded-xl border border-line bg-raised px-3 py-2 text-left text-[13px] text-ink hover:border-accent/50">{s}</button>)}
            </div>
          </div>
        )}
        {msgs.map((m, i) => (
          <div key={i} className={cx('flex', m.role === 'user' ? 'justify-end' : 'justify-start')}>
            <div className={cx('max-w-[92%] rounded-2xl px-3.5 py-2.5 text-[13.5px] leading-relaxed', m.role === 'user' ? 'bg-accent text-bg' : 'border border-line bg-raised')}>
              {m.pending ? (
                <div className="space-y-1.5">
                  <div className="text-[11px] text-muted">{m.status}</div>
                  {m.interpretation && <div className="text-[11px] text-faint">Understood as: {m.interpretation}</div>}
                  {m.tools?.length > 0 && <div className="flex flex-wrap gap-1">{[...new Set(m.tools)].map((t) => <Badge key={t}><Calculator size={10} /> {TOOL_LABEL[t] || t}</Badge>)}</div>}
                  {m.content && <div className="whitespace-pre-wrap text-muted italic"><span className="not-italic text-[10.5px] text-warn">Draft, being checked: </span>{m.content}</div>}
                </div>
              ) : <div className="whitespace-pre-wrap">{m.content}</div>}
              {!m.pending && m.meta?.interpretation && <div className="mt-1 text-[10.5px] text-faint">Understood as: {m.meta.interpretation}</div>}
              {m.role === 'assistant' && m.meta && !m.meta.error && (
                <div className="mt-2 space-y-1.5 border-t border-line pt-2">
                  {m.meta.notice && <div className="text-[11px] text-warn">{m.meta.notice}</div>}
                  <div className="flex flex-wrap items-center gap-1.5">
                    {(m.meta.tools_used || []).filter((t, k, a) => a.indexOf(t) === k).map((t) => <Badge key={t} tone="accent"><Calculator size={10} /> {TOOL_LABEL[t] || t}</Badge>)}
                    {m.meta.mode === 'general' && <Badge>general knowledge · no personal data used</Badge>}
                    {m.meta.verified === false ? <Badge tone="warn">figures could not be verified</Badge> : (m.meta.tools_used || []).length > 0 && <Badge tone="good"><ShieldCheck size={10} /> figures checked</Badge>}
                    <span className="text-[10.5px] text-faint">{m.meta.engine}{m.meta.seconds ? ` · ${m.meta.seconds}s` : ''}</span>
                  </div>
                  {(m.meta.tool_calls || []).length > 0 && <details className="text-[10.5px] text-faint"><summary className="cursor-pointer">Sources</summary>
                    <ul className="mt-1 space-y-0.5">{m.meta.tool_calls.map((c, k) => <li key={k} className="font-mono">{c.tool}({Object.entries(c.arguments || {}).map(([a, v]) => `${a}=${v}`).join(', ')}){c.error ? ` · ${c.error}` : ''}</li>)}</ul></details>}
                </div>
              )}
            </div>
          </div>
        ))}
        {busy && <div className="flex gap-1 px-2 text-accent"><span className="animate-bounce">•</span><span className="animate-bounce [animation-delay:120ms]">•</span><span className="animate-bounce [animation-delay:240ms]">•</span></div>}
        <div ref={end} />
      </div>

      <form onSubmit={(e) => { e.preventDefault(); send() }} className="border-t border-line p-3">
        <div className="flex items-end gap-2 rounded-xl border border-line bg-bg p-1.5 focus-within:border-accent">
          <textarea value={text} onChange={(e) => setText(e.target.value)} rows={1} maxLength={600} placeholder="Ask anything about money or your finances…"
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
            className="max-h-28 flex-1 resize-none bg-transparent px-2 py-1.5 text-sm outline-none placeholder:text-faint" />
          {busy ? <button type="button" onClick={stop} title="Stop" className="grid h-8 w-8 place-items-center rounded-lg border border-line text-muted hover:text-ink"><Square size={13} /></button>
            : <button disabled={!text.trim()} className="grid h-8 w-8 place-items-center rounded-lg bg-accent text-bg disabled:opacity-40"><Send size={15} /></button>}
        </div>
        <p className="mt-1.5 text-[10.5px] text-faint">Educational guidance, not a substitute for a licensed financial advisor.</p>
      </form>
    </div>
  )
}
