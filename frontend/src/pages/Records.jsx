import { useCallback, useEffect, useMemo, useState } from 'react'
import { ArrowDown, ArrowUp, CheckCircle2, CircleDashed, Pencil, Plus, Save, Trash2, X } from 'lucide-react'
import { api } from '../api'
import { Badge, Button, Card, Drawer, Empty, ErrorBox, Field, IconButton, Input, Loading, Note, PageHeader, Select, cx, useConfirm, useToast } from '../components/ui.jsx'
import { useSearchParams } from 'react-router-dom'
import { inr, pct } from '../format'
import { useFinora } from '../store.jsx'

// Manual entry for every part of the financial identity. The forms are built from /api/records/schema, so the
// browser enforces the same rules the server enforces. After every change the analysis is re-run and the
// "what changed" panel shows the effect on the real numbers.

const LABELS = {
  bank_name: 'Bank', account_type: 'Type', last4: 'Last 4 digits', balance: 'Balance (₹)', interest_rate: 'Interest rate (%)', is_primary: 'Primary account',
  issuer: 'Issuer', card_name: 'Card name', credit_limit: 'Credit limit (₹)', outstanding: 'Outstanding (₹)', min_due: 'Minimum due (₹)', due_day: 'Due day of month', apr: 'Interest rate APR (%)',
  loan_type: 'Loan type', lender: 'Lender', principal: 'Amount borrowed (₹)', emi: 'EMI (₹/month)', tenure_months: 'Total tenure (months)', remaining_months: 'Months remaining', property_id: 'Secured on property',
  kind: 'Kind', insurer: 'Insurer', cover: 'Cover (₹)', annual_premium: 'Annual premium (₹)',
  symbol: 'Symbol', company: 'Company', sector: 'Sector', quantity: 'Quantity', avg_buy_price: 'Average buy price (₹)', current_price: 'Current price (₹)', buy_date: 'Buy date',
  scheme: 'Scheme', fund_type: 'Fund type', units: 'Units', avg_nav: 'Average NAV (₹)', current_nav: 'Current NAV (₹)', start_date: 'Start date',
  amount: 'Amount (₹)', sip_day: 'SIP day', status: 'Status', missed_last_12m: 'Missed in last 12 months',
  bank: 'Bank', maturity_date: 'Maturity date', description: 'Description', value: 'Current value (₹)', liquidity: 'Liquidity',
  city: 'City', purchase_value: 'Purchase price (₹)', purchase_date: 'Purchase date', current_value: 'Current value (₹)', monthly_rent: 'Monthly rent (₹)', is_self_occupied: 'Self-occupied',
  name: 'Name', target_amount: 'Target (₹)', target_date: 'Target date', current_amount: 'Saved so far (₹)',
  source: 'Source', date: 'Date', account_id: 'Bank account', card_id: 'Credit card', category: 'Category', frequency: 'Frequency', day_of_month: 'Day of month', type: 'Debit / credit',
}
const label = (n) => LABELS[n] || n.replace(/_/g, ' ')
const REF_TYPE = { account_id: 'bank_accounts', card_id: 'credit_cards', property_id: 'properties' }

// Key outputs compared before and after a change, so the effect of each entry is visible.
const KEYS = [
  ['Net worth', (a) => a.net_worth.net_worth, inr], ['Total liabilities', (a) => a.net_worth.total_liabilities, inr],
  ['Avg monthly income', (a) => a.cash_flow.avg_monthly_income, inr], ['Avg monthly expenses', (a) => a.cash_flow.avg_monthly_expenses, inr],
  ['Savings rate', (a) => a.cash_flow.avg_savings_rate_pct, (x) => pct(x)], ['Emergency runway', (a) => a.liquidity.runway_months, (x) => (x == null ? '—' : `${x} mo`)],
  ['EMI / income', (a) => a.debt.emi_to_income_pct, (x) => pct(x)], ['Credit utilisation', (a) => a.credit.overall_utilisation_pct, (x) => pct(x)],
  ['Health score', (a) => a.health_score.score, (x) => (x == null ? '—' : `${x}/100`)], ['FIRE age', (a) => (a.fire.available === false ? null : a.fire.fire_age), (x) => (x == null ? '—' : x)],
  ['Recommendations', (a) => a.recommendations.length, (x) => x], ['Data completeness', (a) => a.completeness?.score_pct, (x) => (x == null ? '—' : `${x}%`)],
]
const snapshot = (a) => Object.fromEntries(KEYS.map(([k, f]) => [k, f(a)]))

function fieldDefault(f) {
  if (f.default !== null && f.default !== undefined) return f.default
  return f.type === 'checkbox' ? false : ''
}

function RecordForm({ schema, initial, refs, onSave, onCancel, busy, error }) {
  const [v, setV] = useState(() => Object.fromEntries(schema.fields.map((f) => [f.name, initial?.[f.name] ?? fieldDefault(f)])))
  const set = (n, val) => setV((s) => ({ ...s, [n]: val }))
  const submit = (e) => {
    e.preventDefault()
    const body = {}
    for (const f of schema.fields) {
      let x = v[f.name]
      if (x === '' || x === undefined) { if (f.required) body[f.name] = x; else if (initial && initial[f.name] != null) body[f.name] = null; continue }
      if (f.type === 'number' || f.ref) x = Number(x)
      body[f.name] = x
    }
    if (initial) for (const k of Object.keys(body)) if (body[k] === initial[k]) delete body[k]   // PATCH only what changed
    onSave(body)
  }
  return (
    <form onSubmit={submit} className="grid gap-4 sm:grid-cols-2">
      {schema.fields.map((f) => {
        const r = f.rules || {}
        const common = { value: v[f.name] ?? '', onChange: (e) => set(f.name, e.target.value), required: f.required && !initial }
        let input
        if (f.ref) {
          input = <Select {...common}><option value="">{f.required ? 'Choose…' : 'None'}</option>{(refs[REF_TYPE[f.ref]] || []).map((o) => <option key={o.id} value={o.id}>{o._title}</option>)}</Select>
        } else if (f.type === 'select') {
          input = <Select {...common}>{!f.required && f.default == null && <option value="">Choose…</option>}{f.options.map((o) => <option key={o} value={o}>{String(o).replace(/_/g, ' ')}</option>)}</Select>
        } else if (f.type === 'checkbox') {
          return (
            <label key={f.name} className="flex items-center gap-2 self-end pb-2 text-sm text-muted">
              <input type="checkbox" checked={!!v[f.name]} onChange={(e) => set(f.name, e.target.checked)} className="accent-[var(--color-accent)]" /> {label(f.name)}
            </label>
          )
        } else {
          input = <Input {...common} type={f.type === 'number' ? 'number' : f.type === 'date' ? 'date' : 'text'} step="any"
            min={r.ge ?? (r.gt !== undefined ? r.gt : undefined)} max={r.le} minLength={r.min_length} maxLength={r.max_length}
            pattern={r.pattern ? r.pattern.replace(/^\^|\$$/g, '') : undefined} inputMode={f.name === 'last4' ? 'numeric' : undefined} />
        }
        return <Field key={f.name} label={`${label(f.name)}${f.required ? '' : ' (optional)'}`} hint={f.help}>{input}</Field>
      })}
      {error && <p role="alert" className="rounded-lg border border-bad/25 bg-bad-soft px-3 py-2 text-sm text-bad sm:col-span-2">{error.replace(/^record:\s*/i, '')}</p>}
      <div className="flex items-end gap-2 pt-2 sm:col-span-2">
        <Button icon={Save} loading={busy}>{initial ? 'Save changes' : 'Save'}</Button>
        <Button type="button" variant="ghost" icon={X} onClick={onCancel}>Cancel</Button>
      </div>
    </form>
  )
}

function Impact({ before, after }) {
  if (!before || !after) return null
  const rows = KEYS.map(([k, , fmt]) => [k, before[k], after[k], fmt]).filter(([, b, a]) => b !== a)
  return (
    <Card title="What this change did to your numbers" subtitle="Recomputed by the same pipeline the demo identities use">
      {rows.length === 0 ? <p className="text-sm text-muted">No headline figure changed (the record may affect detail pages only).</p> : (
        <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
          {rows.map(([k, b, a, fmt]) => {
            const up = typeof a === 'number' && typeof b === 'number' ? a > b : null
            return (
              <div key={k} className="rounded-xl border border-line bg-bg px-3 py-2 text-sm">
                <div className="text-xs text-muted">{k}</div>
                <div className="num mt-0.5 flex items-center gap-1.5">{fmt(b)} <span className="text-faint">→</span> <b>{fmt(a)}</b>
                  {up !== null && (up ? <ArrowUp size={13} className="text-faint" /> : <ArrowDown size={13} className="text-faint" />)}</div>
              </div>
            )
          })}
        </div>
      )}
    </Card>
  )
}

function display(f, val) {
  if (val === null || val === undefined || val === '') return '—'
  if (f.type === 'checkbox') return val ? 'Yes' : 'No'
  if (f.type === 'number' && /amount|balance|limit|outstanding|due$|principal|emi|cover|premium|price|value|nav|rent/.test(f.name) && !/rate|apr|day/.test(f.name)) return inr(val)
  return String(val).replace(/_/g, ' ')
}

export default function Records({ only, title, subtitle }) {
  const { profileId, profile, analysis, refresh } = useFinora()
  const confirm = useConfirm()
  const toast = useToast()
  const [sp, setSp] = useSearchParams()
  const readOnly = !!profile?.read_only
  const [schema, setSchema] = useState(null)
  const [counts, setCounts] = useState({})
  const type = only || sp.get('type') || 'bank_accounts'
  const setType = (t) => setSp((prev) => { const n = new URLSearchParams(prev); n.set('type', t); return n })
  const [items, setItems] = useState(null)
  const [refs, setRefs] = useState({})
  const [mode, setMode] = useState(null)         // null | 'add' | record being edited
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const [impact, setImpact] = useState(null)

  const t = useMemo(() => schema?.find((s) => s.type === type), [schema, type])
  const loadType = useCallback(async () => {
    setItems(null)
    const [list, c] = await Promise.all([api.records(profileId, type), api.recordCounts(profileId)])
    setItems(list.items); setCounts(c)
  }, [profileId, type])
  const loadRefs = useCallback(async () => {
    const out = {}
    for (const k of ['bank_accounts', 'credit_cards', 'properties']) out[k] = (await api.records(profileId, k)).items
    setRefs(out)
  }, [profileId])

  useEffect(() => { api.recordSchema().then(setSchema).catch((e) => setErr(e.message)) }, [])
  useEffect(() => { loadType().catch((e) => setErr(e.message)); setMode(null) }, [loadType])
  useEffect(() => { loadRefs().catch(() => {}) }, [loadRefs])

  const change = async (fn) => {
    setBusy(true); setErr(null)
    const before = analysis ? snapshot(analysis) : null
    try {
      await fn()
      setMode(null)
      const a = await refresh({ rerun: true })
      await Promise.all([loadType(), loadRefs()])
      if (a) setImpact({ before, after: snapshot(a), what: t.label })
      toast(`${t.label}: saved and analysis updated`, { tone: 'good' })
    } catch (e) { if (e.message !== 'Cancelled.') setErr(e.message) } finally { setBusy(false) }
  }
  const save = (body) => change(() => (mode === 'add' ? api.createRecord(profileId, type, body) : api.updateRecord(profileId, type, mode.id, body)))
  const remove = (r) => change(async () => {
    if (!await confirm({ title: `Delete “${r._title}”?`, body: 'This record is removed from your profile and the analysis is re-run.', confirm: 'Delete', danger: true })) throw new Error('Cancelled.')
    try { await api.deleteRecord(profileId, type, r.id) } catch (e) {
      if (e.status !== 409) throw e
      if (!await confirm({ title: 'Delete linked records too?', body: e.message, confirm: 'Delete all', danger: true })) throw new Error('Cancelled.')
      await api.deleteRecord(profileId, type, r.id, true)
    }
  })

  if (!schema) return err ? <ErrorBox message={err} /> : <Loading />
  const groups = [...new Set(schema.map((s) => s.group))]
  const comp = analysis?.completeness
  const visible = t ? t.fields.filter((f) => !['description', 'missed_last_12m', 'is_primary', 'liquidity'].includes(f.name) || type === 'transactions').slice(0, 4) : []

  return (
    <>
      <PageHeader title={title || 'Your records'} subtitle={subtitle || 'Add, correct or remove anything Finora knows about you. Every change re-runs the full analysis — nothing is estimated or filled in for you.'} />
      {readOnly && <div className="mb-4"><Note tone="warn">This demo template is read-only. Use “Explore demo identity” to get your own editable copy.</Note></div>}
      {comp && !only && (
        <Card className="mb-4" title={`Data completeness ${comp.score_pct}%`} subtitle={comp.note}>
          <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-5">
            {comp.items.map((i) => (
              <div key={i.item} className={cx('rounded-xl border px-3 py-2 text-xs', i.present ? 'border-good/25 bg-good/5' : 'border-line bg-bg')} title={i.hint || ''}>
                <div className="flex items-center gap-1.5 font-medium">{i.present ? <CheckCircle2 size={13} className="text-good" /> : <CircleDashed size={13} className="text-faint" />} {i.item}</div>
                {!i.present && i.affects.length > 0 && <div className="mt-1 text-faint">Needed for: {i.affects.slice(0, 3).join(', ')}</div>}
              </div>
            ))}
          </div>
        </Card>
      )}
      {impact && <div className="mb-4"><Impact before={impact.before} after={impact.after} /></div>}
      {err && !mode && <div className="mb-4"><ErrorBox message={err} /></div>}

      <div className={cx('grid gap-6', !only && 'lg:grid-cols-[220px_1fr]')}>
        {!only && <nav aria-label="Record types" className="space-y-4">
          {groups.map((g) => (
            <div key={g}>
              <div className="px-2 pb-1 text-[10px] font-medium uppercase tracking-[0.14em] text-faint">{g}</div>
              {schema.filter((s) => s.group === g).map((s) => (
                <button key={s.type} type="button" onClick={() => setType(s.type)} aria-current={s.type === type ? 'true' : undefined}
                  className={cx('flex h-9 w-full items-center justify-between rounded-md px-2.5 text-left text-sm', s.type === type ? 'bg-accent-soft font-medium text-accent' : 'text-ink-2 hover:bg-subtle hover:text-ink')}>
                  <span>{s.label}</span><span className="num text-[11px] text-faint">{counts[s.type] ?? ''}</span>
                </button>
              ))}
            </div>
          ))}
        </nav>}

        <Card title={t.label} subtitle={`Feeds: ${t.affects}`}
          action={!readOnly && !mode && <Button icon={Plus} onClick={() => { setErr(null); setMode('add') }}>Add</Button>}>
          <Drawer open={!!mode} onClose={() => { setMode(null); setErr(null) }} title={mode === 'add' ? `Add ${t.label.toLowerCase().replace(/s$/, '')}` : `Edit ${mode?._title || ''}`} subtitle={`Feeds: ${t.affects}`}>
            {mode && <RecordForm key={mode === 'add' ? 'add' : mode.id} schema={t} initial={mode === 'add' ? null : mode} refs={refs} busy={busy} error={err} onSave={save} onCancel={() => { setMode(null); setErr(null) }} />}
          </Drawer>
          {items === null ? <Loading /> : items.length === 0 ? (
            <Empty title={`No ${t.label.toLowerCase()} yet`}>{readOnly ? null : 'If you have none, leave this empty - Finora will not assume any.'}</Empty>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead><tr className="border-b border-line text-left text-[11px] uppercase tracking-wider text-faint">
                  <th className="px-3 py-2 font-medium">Record</th>
                  {visible.map((f) => <th key={f.name} className="px-3 py-2 font-medium">{label(f.name)}</th>)}
                  {!readOnly && <th />}
                </tr></thead>
                <tbody>
                  {items.map((r) => (
                    <tr key={r.id} className="border-b border-line/60 last:border-0">
                      <td className="px-3 py-2 font-medium">{r._title}{r.category_source === 'model' && <Badge tone="info" className="ml-2">ML category</Badge>}</td>
                      {visible.map((f) => <td key={f.name} className="num px-3 py-2 text-muted">{display(f, r[f.name])}</td>)}
                      {!readOnly && <td className="whitespace-nowrap px-3 py-2 text-right">
                        <IconButton icon={Pencil} label={`Edit ${r._title}`} size={15} onClick={() => setMode(r)} className="h-9 w-9" />
                        <IconButton icon={Trash2} label={`Delete ${r._title}`} size={15} onClick={() => remove(r)} className="h-9 w-9 hover:bg-bad-soft hover:text-bad" />
                      </td>}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>
    </>
  )
}
