// Finora Daylight component library (docs/PHASE_8_DESIGN_SPECIFICATION.md §10, PHASE_8_WEB_GUIDELINES.md).
// Existing exports keep their props so every page keeps working; new primitives are added below them.
import { cloneElement, createContext, isValidElement, useCallback, useContext, useEffect, useId, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Link, useSearchParams } from 'react-router-dom'
import { MessageCircleQuestion, AlertTriangle, ArrowDown, ArrowUp, ArrowUpDown, CheckCircle2, ChevronRight, Cpu, Inbox, Info, Loader2, X } from 'lucide-react'
import { MODELS } from './models.js'

export const cx = (...a) => a.filter(Boolean).join(' ')

// ---------------------------------------------------------------- surfaces
export function Card({ title, subtitle, action, children, className = '', pad = true }) {
  return (
    <section className={cx('rounded-xl border border-line bg-bg', className)}>
      {(title || action) && (
        <header className="flex flex-wrap items-start justify-between gap-3 px-5 pt-5 pb-1 sm:px-6">
          <div className="min-w-0">
            {title && <h3 className="text-[15px] font-semibold text-ink">{title}</h3>}
            {subtitle && <p className="mt-0.5 text-[13px] leading-5 text-muted">{subtitle}</p>}
          </div>
          {action}
        </header>
      )}
      <div className={pad ? 'p-5 pt-3 sm:px-6 sm:pb-6' : ''}>{children}</div>
    </section>
  )
}

/** A page section: heading + optional description + content, separated by whitespace rather than borders. */
export function Section({ title, description, action, children, className = '' }) {
  return (
    <section className={cx('mt-10 first:mt-0', className)}>
      {(title || action) && (
        <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
          <div className="min-w-0">
            {title && <h2 className="text-heading font-semibold text-ink">{title}</h2>}
            {description && <p className="mt-1 max-w-2xl text-[13px] leading-5 text-muted">{description}</p>}
          </div>
          {action}
        </div>
      )}
      {children}
    </section>
  )
}

export function Stat({ label, value, sub, tone = 'ink', icon: Icon, hint }) {
  const color = { ink: 'text-ink', good: 'text-good', warn: 'text-warn', bad: 'text-bad', accent: 'text-accent', info: 'text-info' }[tone]
  return (
    <div className="rounded-xl border border-line bg-bg p-5" title={hint}>
      <div className="flex items-center justify-between gap-2 text-[13px] text-muted">
        <span>{label}</span>
        {Icon && <Icon size={16} className="text-faint" aria-hidden />}
      </div>
      <div className={cx('num mt-2 text-[22px] leading-7 font-semibold tracking-tight', color)}>{value}</div>
      {sub && <div className="mt-1 text-[13px] leading-5 text-muted">{sub}</div>}
    </div>
  )
}

const BADGE = {
  high: 'bg-bad-soft text-bad border-bad/25', medium: 'bg-warn-soft text-warn border-warn/25', low: 'bg-accent-soft text-accent border-accent/20',
  good: 'bg-good-soft text-good border-good/25', bad: 'bg-bad-soft text-bad border-bad/25', warn: 'bg-warn-soft text-warn border-warn/25',
  info: 'bg-accent-soft text-info border-info/20', neutral: 'bg-subtle text-muted border-line', accent: 'bg-accent-soft text-accent border-accent/20',
}
export function Badge({ tone = 'neutral', children, className = '' }) {
  return <span className={cx('inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-micro font-medium whitespace-nowrap', BADGE[tone] || BADGE.neutral, className)}>{children}</span>
}

// ---------------------------------------------------------------- buttons
const BTN = {
  primary: 'bg-accent text-white shadow-xs hover:bg-accent-hover font-medium',
  secondary: 'border border-control/60 bg-bg text-ink shadow-xs hover:bg-subtle',
  ghost: 'border border-control/60 bg-bg text-ink shadow-xs hover:bg-subtle',
  quiet: 'text-accent hover:bg-accent-soft',
  danger: 'border border-bad/40 bg-bg text-bad hover:bg-bad-soft',
  'danger-solid': 'bg-bad text-white hover:bg-bad/90 font-medium',
}
const SIZE = { sm: 'h-8 px-3 text-[13px]', md: 'h-10 px-4 text-sm', lg: 'h-11 px-5 text-[15px]' }
export function Button({ children, variant = 'primary', size = 'md', className = '', loading, icon: Icon, ...p }) {
  return (
    <button {...p} disabled={p.disabled || loading} aria-busy={loading || undefined}
      className={cx('inline-flex items-center justify-center gap-2 rounded-md transition-[background-color,border-color,color,box-shadow] duration-150 disabled:cursor-not-allowed disabled:opacity-50',
        BTN[variant] || BTN.primary, SIZE[size], className)}>
      {loading ? <Loader2 size={16} className="animate-spin" aria-hidden /> : Icon ? <Icon size={16} aria-hidden /> : null}
      {children}
    </button>
  )
}
/** Icon-only button: `label` is required and becomes the accessible name and tooltip. */
export function IconButton({ icon: Icon, label, className = '', size = 18, ...p }) {
  return (
    <button type="button" aria-label={label} title={label} {...p}
      className={cx('inline-grid h-10 w-10 place-items-center rounded-md text-muted transition-colors hover:bg-subtle hover:text-ink disabled:opacity-50', className)}>
      <Icon size={size} aria-hidden />
    </button>
  )
}
export function ButtonLink({ to, children, variant = 'secondary', size = 'md', icon: Icon, className = '' }) {
  return (
    <Link to={to} className={cx('inline-flex items-center justify-center gap-2 rounded-md transition-colors', BTN[variant], SIZE[size], className)}>
      {Icon && <Icon size={16} aria-hidden />}{children}
    </Link>
  )
}

// ---------------------------------------------------------------- forms
/** Label + control + hint/error. The label names only the control; hint and error are linked with aria-describedby.
 *  Pass `id` when the control is wrapped (e.g. an input with a show-password button) and put the same id on the control. */
export function Field({ label, hint, error, children, id }) {
  const auto = useId()
  const cid = id || (isValidElement(children) && children.props.id) || auto
  const hid = `${cid}-hint`, eid = `${cid}-err`
  const describedBy = [error ? eid : null, hint && !error ? hid : null].filter(Boolean).join(' ') || undefined
  const control = isValidElement(children) && !id
    ? cloneElement(children, { id: cid, 'aria-describedby': describedBy, 'aria-invalid': error ? true : children.props['aria-invalid'] })
    : children
  return (
    <div className="block">
      <label htmlFor={cid} className="mb-1.5 block text-[13px] font-medium text-ink-2">{label}</label>
      {control}
      {error ? <span id={eid} role="alert" className="mt-1.5 block text-[13px] text-bad">{error}</span>
        : hint && <span id={hid} className="mt-1.5 block text-micro leading-4 text-faint">{hint}</span>}
    </div>
  )
}
export const inputCls = 'w-full rounded-md border border-control/70 bg-bg px-3 h-10 text-sm text-ink shadow-xs placeholder:text-faint/80 ' +
  'transition-[border-color,box-shadow] focus:border-accent focus:ring-2 focus:ring-accent/20 focus-visible:outline-none disabled:bg-subtle disabled:text-muted'
export const Input = (p) => <input {...p} className={cx(inputCls, p.type === 'range' && 'h-auto border-0 px-0 shadow-none focus:ring-0', p.className)} />
export const Select = ({ children, ...p }) => <select {...p} className={cx(inputCls, 'pr-8', p.className)}>{children}</select>
export const Textarea = (p) => <textarea {...p} className={cx(inputCls, 'h-auto py-2', p.className)} />

// ---------------------------------------------------------------- states
export function Loading({ label = 'Loading…', full }) {
  return (
    <div role="status" aria-live="polite" className={cx('flex items-center justify-center gap-3 text-sm text-muted', full ? 'h-[60vh]' : 'py-10')}>
      <Loader2 className="animate-spin text-accent" size={18} aria-hidden /> {label}
    </div>
  )
}
export function Skeleton({ className = '' }) {
  return <div aria-hidden className={cx('animate-pulse rounded-md bg-subtle', className)} />
}
export function ErrorBox({ message, onRetry }) {
  return (
    <div role="alert" className="flex items-start gap-3 rounded-xl border border-bad/25 bg-bad-soft p-4 text-sm text-bad">
      <AlertTriangle size={18} className="mt-0.5 shrink-0" aria-hidden />
      <div className="min-w-0 flex-1"><div className="font-medium">Something went wrong</div><div className="mt-0.5 break-words text-bad/90">{message}</div></div>
      {onRetry && <Button variant="secondary" size="sm" onClick={onRetry}>Try again</Button>}
    </div>
  )
}
export function Empty({ title = 'Nothing here yet', children, icon: Icon = Inbox, action }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-4 py-12 text-center text-sm text-muted">
      <div className="mb-1 grid h-11 w-11 place-items-center rounded-full bg-subtle text-faint"><Icon size={20} aria-hidden /></div>
      <div className="font-medium text-ink">{title}</div>
      {children && <div className="max-w-md leading-6">{children}</div>}
      {action && <div className="mt-3">{action}</div>}
    </div>
  )
}

/** Inside an area tab, a page header becomes a section heading (one h1 per screen: the area's). */
export const EmbeddedCtx = createContext(false)
export function PageHeader({ title, subtitle, children, eyebrow }) {
  const embedded = useContext(EmbeddedCtx)
  // Inside an area the tab already names the page: keep the heading for screen readers, show only the lead and actions.
  if (embedded) return (
    <div className={cx('flex flex-wrap items-start justify-between gap-4', (subtitle || children) && 'mb-6')}>
      <h2 className="sr-only">{title}</h2>
      {subtitle && <p className="max-w-3xl text-sm leading-6 text-muted">{subtitle}</p>}
      {children && <div className="flex flex-wrap items-center gap-2">{children}</div>}
    </div>
  )
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        {eyebrow && <div className="mb-1 text-micro font-medium uppercase tracking-[0.06em] text-faint">{eyebrow}</div>}
        <h1 className="text-title font-semibold tracking-tight text-ink">{title}</h1>
        {subtitle && <p className="mt-1.5 max-w-3xl text-[15px] leading-6 text-muted">{subtitle}</p>}
      </div>
      {children && <div className="flex flex-wrap items-center gap-2">{children}</div>}
    </div>
  )
}

// ---------------------------------------------------------------- table (Stripe pattern)
/** Columns: {key, label, right, render, sort: (row) => value, className}. Rows are sortable when a column has `sort`.
 *  `onRow` makes each row keyboard-activatable (Enter/Space) as well as clickable. `pageSize` paginates. */
export function Table({ columns, rows, empty = 'No rows', dense, onRow, rowClass, pageSize, caption }) {
  const [sort, setSort] = useState(null)
  const [page, setPage] = useState(0)
  useEffect(() => { setPage(0) }, [rows])
  if (!rows?.length) return <Empty title={empty} />
  let data = rows
  if (sort) {
    const col = columns.find((c) => c.key === sort.key)
    data = [...rows].sort((a, b) => { const x = col.sort(a), y = col.sort(b); return (x > y ? 1 : x < y ? -1 : 0) * sort.dir })
  }
  const pages = pageSize ? Math.ceil(data.length / pageSize) : 1
  if (pageSize) data = data.slice(page * pageSize, (page + 1) * pageSize)
  return (
    <div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          {caption && <caption className="sr-only">{caption}</caption>}
          <thead>
            <tr className="border-b border-line-strong bg-subtle/70 text-left text-micro uppercase tracking-[0.04em] text-muted">
              {columns.map((c) => (
                <th key={c.key} scope="col" aria-sort={sort?.key === c.key ? (sort.dir > 0 ? 'ascending' : 'descending') : undefined}
                  className={cx('px-3 py-2.5 font-medium whitespace-nowrap first:pl-4 last:pr-4', c.right && 'text-right')}>
                  {c.sort ? (
                    <button type="button" onClick={() => setSort((s) => (s?.key === c.key ? (s.dir > 0 ? { key: c.key, dir: -1 } : null) : { key: c.key, dir: 1 }))}
                      className={cx('inline-flex items-center gap-1 uppercase hover:text-ink', c.right && 'flex-row-reverse')}>
                      {c.label}{sort?.key === c.key ? (sort.dir > 0 ? <ArrowUp size={12} aria-hidden /> : <ArrowDown size={12} aria-hidden />) : <ArrowUpDown size={12} className="opacity-50" aria-hidden />}
                    </button>
                  ) : c.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.map((r, i) => (
              <tr key={r.id ?? i} onClick={onRow ? () => onRow(r) : undefined}
                tabIndex={onRow ? 0 : undefined} onKeyDown={onRow ? (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onRow(r) } } : undefined}
                className={cx('border-b border-line last:border-0', onRow && 'cursor-pointer hover:bg-subtle/70 focus-visible:bg-accent-soft', rowClass?.(r))}>
                {columns.map((c) => (
                  <td key={c.key} className={cx('px-3 align-top first:pl-4 last:pr-4', dense ? 'py-2' : 'py-3', c.right && 'num text-right', c.className)}>
                    {c.render ? c.render(r, i) : r[c.key]}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {pageSize && pages > 1 && (
        <nav aria-label="Table pages" className="flex items-center justify-between gap-3 border-t border-line px-4 py-2.5 text-[13px] text-muted">
          <span className="num">{page * pageSize + 1}–{Math.min(rows.length, (page + 1) * pageSize)} of {rows.length}</span>
          <div className="flex gap-2">
            <Button size="sm" variant="secondary" disabled={page === 0} onClick={() => setPage(page - 1)}>Previous</Button>
            <Button size="sm" variant="secondary" disabled={page + 1 >= pages} onClick={() => setPage(page + 1)}>Next</Button>
          </div>
        </nav>
      )}
    </div>
  )
}

export function Meter({ value, max = 100, tone = 'accent', label }) {
  const w = Math.max(0, Math.min(100, (value / max) * 100))
  const bg = { accent: 'bg-accent', good: 'bg-good', warn: 'bg-warn', bad: 'bg-bad', info: 'bg-info' }[tone]
  return (
    <div>
      {label && <div className="mb-1.5 flex justify-between text-[13px] text-muted">{label}</div>}
      <div className="h-2 overflow-hidden rounded-full bg-subtle" role="meter" aria-valuenow={value} aria-valuemin={0} aria-valuemax={max}>
        <div className={cx('h-full rounded-full', bg)} style={{ width: `${w}%` }} />
      </div>
    </div>
  )
}

export function KV({ rows }) {
  return (
    <dl className="divide-y divide-line text-sm">
      {rows.filter(Boolean).map(([k, v, t]) => (
        <div key={k} className="flex items-baseline justify-between gap-4 py-2.5">
          <dt className="text-muted">{k}</dt>
          <dd className={cx('num text-right font-medium', { good: 'text-good', bad: 'text-bad', warn: 'text-warn' }[t] || 'text-ink')}>{v}</dd>
        </div>
      ))}
    </dl>
  )
}

export function Note({ children, tone = 'neutral' }) {
  const c = { neutral: 'border-line bg-subtle/60 text-ink-2', warn: 'border-warn/25 bg-warn-soft text-warn', info: 'border-accent/20 bg-accent-soft text-info',
    good: 'border-good/25 bg-good-soft text-good', bad: 'border-bad/25 bg-bad-soft text-bad' }[tone]
  const Icon = { warn: AlertTriangle, bad: AlertTriangle, good: CheckCircle2 }[tone] || Info
  return (
    <div className={cx('flex items-start gap-2.5 rounded-lg border px-3.5 py-2.5 text-[13px] leading-5', c)}>
      <Icon size={15} className="mt-0.5 shrink-0" aria-hidden /><div className="min-w-0">{children}</div>
    </div>
  )
}

export const chartTooltip = {
  contentStyle: { background: '#ffffff', border: '1px solid #e4e7ec', borderRadius: 10, fontSize: 12, color: '#1d2433', boxShadow: '0 4px 12px rgba(16,24,40,.08)' },
  labelStyle: { color: '#5b6475', marginBottom: 4 }, itemStyle: { color: '#1d2433' }, cursor: { fill: '#3157c80d' },
}
export const chartAxis = { tick: { fontSize: 12, fill: '#656d7f' }, axisLine: false, tickLine: false }

// ---------------------------------------------------------------- model identity (which model powers a result, and how it works)
/** "Model: XGBoost + SHAP · How it works" — opens a drawer explaining the model; technical records are one click further, in Model Lab. */
export function Trust({ model, className = '' }) {
  const [open, setOpen] = useState(false)
  const m = MODELS[model]
  if (!m) return null
  return (
    <div className={cx('flex flex-wrap items-center gap-x-3 gap-y-1.5 text-[13px]', className)}>
      <Badge tone="accent"><Cpu size={12} aria-hidden /> Model: {m.algorithm}</Badge>
      <button type="button" onClick={() => setOpen(true)} className="inline-flex items-center gap-0.5 font-medium text-accent hover:underline">How it works <ChevronRight size={13} aria-hidden /></button>
      <ModelExplainer model={model} open={open} onClose={() => setOpen(false)} />
    </div>
  )
}
export function ModelExplainer({ model, open, onClose }) {
  const m = MODELS[model]
  if (!m) return null
  return (
    <Drawer open={open} onClose={onClose} title={m.name} subtitle={`Powered by ${m.algorithm}`}
      footer={<ButtonLink to={`/models?tab=lab&model=${model}`} variant="secondary">Technical details in Model Lab</ButtonLink>}>
      <p className="text-[15px] leading-6 text-ink-2">{m.purpose}</p>
      <h3 className="mt-6 text-[13px] font-semibold text-ink">What it looks at</h3>
      <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-ink-2">{m.inputs.map((x) => <li key={x}>{x}</li>)}</ul>
      <h3 className="mt-6 text-[13px] font-semibold text-ink">How it works</h3>
      <p className="mt-1.5 text-sm leading-6 text-ink-2">{m.how}</p>
      <p className="mt-2 text-sm leading-6 text-ink-2">{m.explain}</p>
      <h3 className="mt-6 text-[13px] font-semibold text-ink">Reading the result</h3>
      <p className="mt-1.5 text-sm leading-6 text-ink-2">{m.read}</p>
      <h3 className="mt-6 text-[13px] font-semibold text-ink">Data</h3>
      <p className="mt-1.5 text-sm leading-6 text-ink-2">{m.data}</p>
    </Drawer>
  )
}

// ---------------------------------------------------------------- tabs (URL-synced) and segmented control
/** Reads/writes `?tab=` (or `param`). Returns [value, set]. Unknown values fall back to the first option. */
export function useUrlParam(param, options, fallback) {
  const [sp, setSp] = useSearchParams()
  const raw = sp.get(param)
  const value = options && !options.includes(raw) ? (fallback ?? options[0]) : (raw ?? fallback)
  // `also` updates other params in the SAME navigation (consecutive setSearchParams calls in one tick do not chain).
  const set = useCallback((v, { replace = false, also = {} } = {}) => {
    setSp((prev) => {
      // Switching tab starts that tab fresh (its own ?view= and filters belong to the previous tab).
      const n = param === 'tab' ? new URLSearchParams() : new URLSearchParams(prev)
      for (const [k, x] of Object.entries({ [param]: v, ...also })) { if (x == null || x === '') n.delete(k); else n.set(k, x) }
      return n
    }, { replace })
  }, [param, setSp])
  return [value, set]
}

/** Atomic multi-key URL update: update({ q: 'x', page: null }). */
export function useUrlUpdate() {
  const [, setSp] = useSearchParams()
  return useCallback((obj, { replace = false } = {}) => setSp((prev) => {
    const n = new URLSearchParams(prev)
    for (const [k, x] of Object.entries(obj)) { if (x == null || x === '') n.delete(k); else n.set(k, x) }
    return n
  }, { replace }), [setSp])
}

export function Tabs({ tabs, value, onChange, label = 'Sections' }) {
  const ref = useRef(null)
  const onKey = (e, i) => {
    const d = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0
    if (!d) return
    e.preventDefault()
    const n = (i + d + tabs.length) % tabs.length
    onChange(tabs[n].id)
    ref.current?.querySelectorAll('[role=tab]')[n]?.focus()
  }
  return (
    <div className="-mx-4 mb-8 overflow-x-auto border-b border-line px-4 sm:mx-0 sm:px-0">
      <div ref={ref} role="tablist" aria-label={label} className="flex min-w-max gap-6">
        {tabs.map((t, i) => {
          const on = t.id === value
          return (
            <button key={t.id} type="button" role="tab" aria-selected={on} tabIndex={on ? 0 : -1} onClick={() => onChange(t.id)} onKeyDown={(e) => onKey(e, i)}
              className={cx('relative -mb-px flex h-11 items-center gap-2 border-b-2 text-sm font-medium whitespace-nowrap transition-colors',
                on ? 'border-accent text-ink' : 'border-transparent text-muted hover:text-ink')}>
              {t.label}
              {t.count ? <span className={cx('num rounded-full px-1.5 text-micro', on ? 'bg-accent-soft text-accent' : 'bg-subtle text-muted')}>{t.count}</span> : null}
            </button>
          )
        })}
      </div>
    </div>
  )
}

export function Segmented({ options, value, onChange, label }) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex max-w-full flex-wrap gap-1 rounded-lg bg-subtle p-1">
      {options.map((o) => {
        const on = o.id === value
        return (
          <button key={o.id} type="button" role="radio" aria-checked={on} onClick={() => onChange(o.id)}
            className={cx('h-8 rounded-md px-3 text-[13px] font-medium transition-colors', on ? 'bg-bg text-ink shadow-xs' : 'text-muted hover:text-ink')}>
            {o.label}
          </button>
        )
      })}
    </div>
  )
}

// ---------------------------------------------------------------- overlays: drawer, confirm modal, toast
function useFocusTrap(open, onClose) {
  const ref = useRef(null)
  useEffect(() => {
    if (!open) return
    const prev = document.activeElement
    const el = ref.current
    const focusables = () => [...el.querySelectorAll('button,[href],input,select,textarea,[tabindex]:not([tabindex="-1"])')].filter((x) => !x.disabled)
    setTimeout(() => (focusables()[0] || el)?.focus(), 0)
    const onKey = (e) => {
      if (e.key === 'Escape') { e.stopPropagation(); onClose?.() }
      if (e.key === 'Tab') {
        const f = focusables(); if (!f.length) return
        if (e.shiftKey && document.activeElement === f[0]) { e.preventDefault(); f[f.length - 1].focus() }
        else if (!e.shiftKey && document.activeElement === f[f.length - 1]) { e.preventDefault(); f[0].focus() }
      }
    }
    document.addEventListener('keydown', onKey)
    const ov = document.body.style.overflow; document.body.style.overflow = 'hidden'
    return () => { document.removeEventListener('keydown', onKey); document.body.style.overflow = ov; prev?.focus?.() }
  }, [open]) // eslint-disable-line react-hooks/exhaustive-deps
  return ref
}

export function Drawer({ open, onClose, title, subtitle, children, footer, width = 'sm:w-[480px]' }) {
  const ref = useFocusTrap(open, onClose)
  const id = useId()
  if (!open) return null
  // Portal to <body>: an animated ancestor (transform) would otherwise become the containing block of this fixed overlay.
  return createPortal(
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="fade-in absolute inset-0 bg-ink/25" onClick={onClose} aria-hidden />
      <div ref={ref} role="dialog" aria-modal="true" aria-labelledby={id} tabIndex={-1}
        className={cx('slide-in relative flex h-full w-full flex-col bg-bg shadow-overlay sm:rounded-l-xl', width)} style={{ overscrollBehavior: 'contain' }}>
        <header className="flex items-start justify-between gap-3 border-b border-line px-5 py-4 sm:px-6">
          <div className="min-w-0">
            <h2 id={id} className="text-heading font-semibold text-ink">{title}</h2>
            {subtitle && <p className="mt-0.5 text-[13px] text-muted">{subtitle}</p>}
          </div>
          <IconButton icon={X} label="Close" onClick={onClose} className="-mr-2" />
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5 sm:px-6">{children}</div>
        {footer && <footer className="flex flex-wrap justify-end gap-2 border-t border-line px-5 py-3 sm:px-6">{footer}</footer>}
      </div>
    </div>, document.body)
}

export function Modal({ open, onClose, title, children, footer }) {
  const ref = useFocusTrap(open, onClose)
  const id = useId()
  if (!open) return null
  return createPortal(
    <div className="fixed inset-0 z-[60] grid place-items-center p-4">
      <div className="fade-in absolute inset-0 bg-ink/30" onClick={onClose} aria-hidden />
      <div ref={ref} role="dialog" aria-modal="true" aria-labelledby={id} tabIndex={-1} className="rise relative w-full max-w-[440px] rounded-xl bg-bg p-6 shadow-overlay">
        <h2 id={id} className="text-heading font-semibold text-ink">{title}</h2>
        <div className="mt-2 text-sm leading-6 text-muted">{children}</div>
        {footer && <div className="mt-6 flex flex-wrap justify-end gap-2">{footer}</div>}
      </div>
    </div>, document.body)
}

const OverlayCtx = createContext(null)
/** Provides confirm() (replaces window.confirm) and toast(). */
export function OverlayProvider({ children }) {
  const [ask, setAsk] = useState(null)
  const [toasts, setToasts] = useState([])
  const confirm = useCallback((opts) => new Promise((resolve) => setAsk({ ...(typeof opts === 'string' ? { title: opts } : opts), resolve })), [])
  const toast = useCallback((message, { tone = 'neutral', action, ms = 4500 } = {}) => {
    const id = Math.random().toString(36).slice(2)
    setToasts((t) => [...t, { id, message, tone, action }])
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), ms)
  }, [])
  const close = (v) => { ask?.resolve(v); setAsk(null) }
  return (
    <OverlayCtx.Provider value={{ confirm, toast }}>
      {children}
      <Modal open={!!ask} onClose={() => close(false)} title={ask?.title}
        footer={<><Button variant="secondary" onClick={() => close(false)}>{ask?.cancel || 'Cancel'}</Button>
          <Button variant={ask?.danger ? 'danger-solid' : 'primary'} onClick={() => close(true)}>{ask?.confirm || 'Confirm'}</Button></>}>
        {ask?.body}
      </Modal>
      <div aria-live="polite" role="status" className="pointer-events-none fixed inset-x-0 bottom-4 z-[70] flex flex-col items-center gap-2 px-4">
        {toasts.map((t) => (
          <div key={t.id} className="rise pointer-events-auto flex max-w-md items-center gap-3 rounded-lg bg-ink px-4 py-2.5 text-sm text-white shadow-overlay">
            {t.tone === 'good' ? <CheckCircle2 size={16} className="text-[#7ee2a8]" aria-hidden /> : t.tone === 'bad' ? <AlertTriangle size={16} className="text-[#ffb59a]" aria-hidden /> : null}
            <span>{t.message}</span>
            {t.action && <button type="button" onClick={t.action.onClick} className="ml-1 font-medium text-[#b8c8f5] hover:underline">{t.action.label}</button>}
          </div>
        ))}
      </div>
    </OverlayCtx.Provider>
  )
}
export const useConfirm = () => useContext(OverlayCtx).confirm
export const useToast = () => useContext(OverlayCtx).toast

/** "Ask about this": opens the Ask panel with a pre-filled question (never sent automatically). */
export function AskAbout({ q, className = '' }) {
  return (
    <button type="button" onClick={() => window.dispatchEvent(new CustomEvent('finora:ask', { detail: q }))}
      className={cx('inline-flex items-center gap-1 text-[13px] font-medium text-accent hover:underline', className)}>
      <MessageCircleQuestion size={14} aria-hidden /> Ask about this
    </button>
  )
}

// ---------------------------------------------------------------- answer-first composition (Phase 8 mid-review)
/** The page's answer in one sentence, with an optional eyebrow and supporting line. Replaces rows of equal stat cards. */
export function Answer({ eyebrow, children, sub, tone, action }) {
  return (
    <div className="mb-8 flex flex-wrap items-end justify-between gap-6">
      <div className="min-w-0 max-w-3xl">
        {eyebrow && <div className="mb-2 text-[13px] font-medium text-muted">{eyebrow}</div>}
        <p className={cx('text-[26px] leading-[34px] font-semibold tracking-tight text-ink sm:text-[30px] sm:leading-[38px]', tone === 'good' && '[&_b]:text-good', tone === 'bad' && '[&_b]:text-bad', '[&_b]:font-semibold')}>{children}</p>
        {sub && <p className="mt-2 text-[15px] leading-6 text-muted">{sub}</p>}
      </div>
      {action}
    </div>
  )
}
/** 2–4 supporting facts in a quiet inline row (not cards). items: [label, value, note?, tone?] */
export function Facts({ items, className = '' }) {
  return (
    <dl className={cx('grid gap-x-8 gap-y-4 border-y border-line py-5 sm:grid-cols-2 lg:grid-flow-col lg:auto-cols-fr lg:grid-cols-none', className)}>
      {items.filter(Boolean).map(([k, v, note, tone]) => (
        <div key={k} className="min-w-0">
          <dt className="text-[13px] text-muted">{k}</dt>
          <dd className={cx('num mt-1 text-lg font-semibold', { good: 'text-good', bad: 'text-bad', warn: 'text-warn' }[tone] || 'text-ink')}>{v}</dd>
          {note && <dd className="mt-0.5 text-[13px] leading-5 text-muted">{note}</dd>}
        </div>
      ))}
    </dl>
  )
}
/** A list row with leading mark, title/subtitle, trailing value; clickable rows open details. */
export function Row({ lead, title, subtitle, value, valueSub, onClick, children }) {
  const C = onClick ? 'button' : 'div'
  return (
    <li>
      <C type={onClick ? 'button' : undefined} onClick={onClick}
        className={cx('flex w-full items-center gap-4 px-5 py-4 text-left sm:px-6', onClick && 'transition-colors hover:bg-subtle/70')}>
        {lead}
        <span className="min-w-0 flex-1"><span className="block truncate text-[15px] font-medium text-ink">{title}</span>{subtitle && <span className="block truncate text-[13px] text-muted">{subtitle}</span>}</span>
        {children}
        {value != null && <span className="text-right"><span className="num block text-[15px] font-semibold text-ink">{value}</span>{valueSub && <span className="block text-[13px] text-muted">{valueSub}</span>}</span>}
      </C>
    </li>
  )
}
export const List = ({ children, className = '' }) => <ul className={cx('divide-y divide-line overflow-hidden rounded-xl border border-line bg-bg', className)}>{children}</ul>
