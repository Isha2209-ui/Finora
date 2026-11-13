import { useEffect, useRef, useState } from 'react'
import { Bot, Calculator, Send, ShieldCheck, Trash2, X } from 'lucide-react'
import { api } from '../api'
import { useFinora } from '../store.jsx'
import { Badge, cx } from './ui.jsx'

const SUGGESTIONS = ['How am I doing financially?', 'Can I afford a ₹12 lakh car?', 'When can I retire?', 'How long would my savings last if I lost my job?',
  'How should I pay off my debt?', 'Which tax regime is better for me?', 'What will I spend next month?', 'Any unusual transactions?']
const TOOL_LABEL = { affordability: 'Decision simulator', fire_forecast: 'FIRE engine', runway: 'Runway calculator', tax_comparison: 'Tax calculator',
  debts_and_payoff: 'Debt payoff simulator', credit_cards: 'Credit analysis + risk model', spending_by_category: 'Spending analysis', net_worth: 'Net-worth calculator',
  spending_forecast: 'Forecast model', unusual_transactions: 'Anomaly model', profile_summary: 'Profile summary', recommendations: 'Recommendation engine',
  emi_calculator: 'EMI calculator', investments: 'Portfolio analysis', insurance: 'Insurance check', goals: 'Goal tracker', peer_comparison: 'Peer model',
  cash_flow: 'Cash-flow analysis', glossary: 'Glossary' }

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

  const send = async (q) => {
    const message = (q ?? text).trim()
    if (!message || busy) return
    setText(''); setBusy(true)
    setMsgs((m) => [...m, { role: 'user', content: message }])
    try {
      const r = await api.chat(profileId, message)
      setMsgs((m) => [...m, { role: 'assistant', content: r.answer, meta: { engine: r.engine, tools_used: r.tools_used, trace: r.trace } }])
    } catch (e) {
      setMsgs((m) => [...m, { role: 'assistant', content: `I could not answer that: ${e.message}`, meta: { error: true } }])
    } finally { setBusy(false) }
  }
  const clear = async () => { await api.clearChat(profileId); setMsgs([]) }

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2 border-b border-line px-4 py-3">
        <div className="grid h-7 w-7 place-items-center rounded-lg bg-accent/15 text-accent"><Bot size={16} /></div>
        <div className="flex-1">
          <div className="text-sm font-semibold">AI CFO</div>
          <div className="text-[11px] text-muted">{status == null ? 'Checking model…' : status.available ? `${status.model} · running locally` : 'Calculator mode (language model offline)'}</div>
        </div>
        {msgs.length > 0 && <button onClick={clear} title="Clear conversation" className="p-1.5 text-faint hover:text-ink"><Trash2 size={15} /></button>}
        {onClose && <button onClick={onClose} className="p-1.5 text-faint hover:text-ink"><X size={16} /></button>}
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto px-4 py-4">
        {msgs.length === 0 && (
          <div>
            <p className="text-sm text-muted">Ask about your cash flow, investments, taxes, cards, debt, goals, big purchases or retirement. Every number comes from Finora's calculators and models - the assistant never does its own maths.</p>
            <div className={cx('mt-3 grid gap-2', wide ? 'sm:grid-cols-2' : '')}>
              {SUGGESTIONS.map((s) => <button key={s} onClick={() => send(s)} className="rounded-xl border border-line bg-raised px-3 py-2 text-left text-[13px] text-ink hover:border-accent/50">{s}</button>)}
            </div>
          </div>
        )}
        {msgs.map((m, i) => (
          <div key={i} className={cx('flex', m.role === 'user' ? 'justify-end' : 'justify-start')}>
            <div className={cx('max-w-[92%] rounded-2xl px-3.5 py-2.5 text-[13.5px] leading-relaxed', m.role === 'user' ? 'bg-accent text-bg' : 'border border-line bg-raised')}>
              <div className="whitespace-pre-wrap">{m.content}</div>
              {m.role === 'assistant' && m.meta?.tools_used?.length > 0 && (
                <div className="mt-2 flex flex-wrap items-center gap-1.5 border-t border-line pt-2">
                  {m.meta.tools_used.map((t) => <Badge key={t} tone="accent"><Calculator size={10} /> {TOOL_LABEL[t] || t}</Badge>)}
                  <Badge tone="good"><ShieldCheck size={10} /> numbers verified</Badge>
                  <span className="text-[10.5px] text-faint">{m.meta.engine === 'rules' ? 'written by rules' : `explained by ${m.meta.engine}`}</span>
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
          <textarea value={text} onChange={(e) => setText(e.target.value)} rows={1} maxLength={600} placeholder="Ask your CFO…"
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
            className="max-h-28 flex-1 resize-none bg-transparent px-2 py-1.5 text-sm outline-none placeholder:text-faint" />
          <button disabled={busy || !text.trim()} className="grid h-8 w-8 place-items-center rounded-lg bg-accent text-bg disabled:opacity-40"><Send size={15} /></button>
        </div>
        <p className="mt-1.5 text-[10.5px] text-faint">Educational guidance, not a substitute for a licensed financial advisor.</p>
      </form>
    </div>
  )
}
