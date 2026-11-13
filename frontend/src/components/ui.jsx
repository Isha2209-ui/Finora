import { AlertTriangle, Inbox, Loader2 } from 'lucide-react'

export const cx = (...a) => a.filter(Boolean).join(' ')

export function Card({ title, subtitle, action, children, className = '', pad = true }) {
  return (
    <section className={cx('rounded-2xl border border-line bg-surface', className)}>
      {(title || action) && (
        <header className="flex items-start justify-between gap-3 px-5 pt-4 pb-1">
          <div>
            {title && <h3 className="text-[13px] font-semibold tracking-wide text-ink">{title}</h3>}
            {subtitle && <p className="mt-0.5 text-xs text-muted">{subtitle}</p>}
          </div>
          {action}
        </header>
      )}
      <div className={pad ? 'p-5 pt-3' : ''}>{children}</div>
    </section>
  )
}

export function Stat({ label, value, sub, tone = 'ink', icon: Icon, hint }) {
  const color = { ink: 'text-ink', good: 'text-good', warn: 'text-warn', bad: 'text-bad', accent: 'text-accent', info: 'text-info' }[tone]
  return (
    <div className="rounded-2xl border border-line bg-surface p-4" title={hint}>
      <div className="flex items-center justify-between text-xs text-muted">
        <span>{label}</span>
        {Icon && <Icon size={15} className="text-faint" />}
      </div>
      <div className={cx('num mt-1.5 text-2xl font-semibold', color)}>{value}</div>
      {sub && <div className="mt-1 text-xs text-muted">{sub}</div>}
    </div>
  )
}

const BADGE = {
  high: 'bg-bad/15 text-bad border-bad/30', medium: 'bg-warn/15 text-warn border-warn/30', low: 'bg-info/15 text-info border-info/30',
  good: 'bg-good/15 text-good border-good/30', bad: 'bg-bad/15 text-bad border-bad/30', warn: 'bg-warn/15 text-warn border-warn/30',
  info: 'bg-info/15 text-info border-info/30', neutral: 'bg-raised text-muted border-line', accent: 'bg-accent/15 text-accent border-accent/30',
}
export function Badge({ tone = 'neutral', children, className = '' }) {
  return <span className={cx('inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium whitespace-nowrap', BADGE[tone] || BADGE.neutral, className)}>{children}</span>
}

export function Button({ children, variant = 'primary', className = '', loading, icon: Icon, ...p }) {
  const v = {
    primary: 'bg-accent text-bg hover:bg-accent/90 font-semibold',
    ghost: 'border border-line bg-raised text-ink hover:border-faint',
    danger: 'border border-bad/40 bg-bad/10 text-bad hover:bg-bad/20',
  }[variant]
  return (
    <button {...p} disabled={p.disabled || loading}
      className={cx('inline-flex items-center justify-center gap-2 rounded-xl px-3.5 py-2 text-sm transition disabled:opacity-50 disabled:cursor-not-allowed', v, className)}>
      {loading ? <Loader2 size={15} className="animate-spin" /> : Icon ? <Icon size={15} /> : null}
      {children}
    </button>
  )
}

export function Field({ label, hint, children }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs text-muted">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-[11px] text-faint">{hint}</span>}
    </label>
  )
}
export const inputCls = 'w-full rounded-xl border border-line bg-bg px-3 py-2 text-sm text-ink outline-none placeholder:text-faint focus:border-accent'
export const Input = (p) => <input {...p} className={cx(inputCls, p.className)} />
export const Select = ({ children, ...p }) => <select {...p} className={cx(inputCls, p.className)}>{children}</select>

export function Loading({ label = 'Loading…', full }) {
  return (
    <div className={cx('flex items-center justify-center gap-3 text-sm text-muted', full ? 'h-[60vh]' : 'py-10')}>
      <Loader2 className="animate-spin text-accent" size={18} /> {label}
    </div>
  )
}
export function ErrorBox({ message, onRetry }) {
  return (
    <div className="flex items-start gap-3 rounded-2xl border border-bad/30 bg-bad/10 p-4 text-sm text-bad">
      <AlertTriangle size={18} className="mt-0.5 shrink-0" />
      <div className="flex-1"><div className="font-medium">Something went wrong</div><div className="mt-0.5 text-bad/90">{message}</div></div>
      {onRetry && <Button variant="ghost" onClick={onRetry}>Retry</Button>}
    </div>
  )
}
export function Empty({ title = 'Nothing here yet', children }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-10 text-center text-sm text-muted">
      <Inbox className="text-faint" /> <div className="font-medium text-ink">{title}</div>{children && <div className="max-w-md">{children}</div>}
    </div>
  )
}

export function PageHeader({ title, subtitle, children }) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
        {subtitle && <p className="mt-1 max-w-3xl text-sm text-muted">{subtitle}</p>}
      </div>
      <div className="flex flex-wrap items-center gap-2">{children}</div>
    </div>
  )
}

export function Table({ columns, rows, empty = 'No rows', dense, onRow, rowClass }) {
  if (!rows?.length) return <Empty title={empty} />
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-line text-left text-[11px] uppercase tracking-wider text-faint">
            {columns.map((c) => <th key={c.key} className={cx('px-3 py-2 font-medium', c.right && 'text-right')}>{c.label}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={r.id ?? i} onClick={onRow ? () => onRow(r) : undefined}
              className={cx('border-b border-line/60 last:border-0', onRow && 'cursor-pointer hover:bg-raised/60', rowClass?.(r))}>
              {columns.map((c) => (
                <td key={c.key} className={cx('px-3 align-top', dense ? 'py-1.5' : 'py-2.5', c.right && 'num text-right', c.className)}>
                  {c.render ? c.render(r, i) : r[c.key]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function Meter({ value, max = 100, tone = 'accent', label }) {
  const w = Math.max(0, Math.min(100, (value / max) * 100))
  const bg = { accent: 'bg-accent', good: 'bg-good', warn: 'bg-warn', bad: 'bg-bad', info: 'bg-info' }[tone]
  return (
    <div>
      {label && <div className="mb-1 flex justify-between text-xs text-muted">{label}</div>}
      <div className="h-2 overflow-hidden rounded-full bg-raised"><div className={cx('h-full rounded-full', bg)} style={{ width: `${w}%` }} /></div>
    </div>
  )
}

export function KV({ rows }) {
  return (
    <dl className="divide-y divide-line/60 text-sm">
      {rows.filter(Boolean).map(([k, v, t]) => (
        <div key={k} className="flex items-baseline justify-between gap-4 py-2">
          <dt className="text-muted">{k}</dt>
          <dd className={cx('num text-right font-medium', t === 'good' && 'text-good', t === 'bad' && 'text-bad', t === 'warn' && 'text-warn')}>{v}</dd>
        </div>
      ))}
    </dl>
  )
}

export function Note({ children, tone = 'neutral' }) {
  const c = { neutral: 'border-line bg-raised/50 text-muted', warn: 'border-warn/30 bg-warn/10 text-warn', info: 'border-info/30 bg-info/10 text-info' }[tone]
  return <p className={cx('rounded-xl border px-3 py-2 text-xs leading-relaxed', c)}>{children}</p>
}

export const chartTooltip = {
  contentStyle: { background: '#0e1524', border: '1px solid #1f2a40', borderRadius: 10, fontSize: 12, color: '#e6edf7' },
  labelStyle: { color: '#8695ad', marginBottom: 4 }, itemStyle: { color: '#e6edf7' }, cursor: { fill: '#ffffff08' },
}
