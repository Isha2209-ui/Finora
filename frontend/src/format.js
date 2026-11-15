// Number and money formatting (Indian units).
export const inr = (x, { compact = true, dash = '—' } = {}) => {
  if (x === null || x === undefined || Number.isNaN(Number(x))) return dash
  const n = Number(x), a = Math.abs(n), s = n < 0 ? '−' : ''
  if (compact && a >= 1e7) return `${s}₹${(a / 1e7).toFixed(2)} Cr`
  if (compact && a >= 1e5) return `${s}₹${(a / 1e5).toFixed(2)} L`
  return `${s}₹${Math.round(a).toLocaleString('en-IN')}`
}
export const inrFull = (x) => inr(x, { compact: false })
export const pct = (x, d = 1, dash = '—') => (x === null || x === undefined ? dash : `${Number(x).toFixed(d)}%`)
export const num = (x, d = 0, dash = '—') => (x === null || x === undefined ? dash : Number(x).toLocaleString('en-IN', { maximumFractionDigits: d, minimumFractionDigits: d }))
export const axisInr = (v) => { const a = Math.abs(v); return a >= 1e7 ? `${(v / 1e7).toFixed(1)}Cr` : a >= 1e5 ? `${(v / 1e5).toFixed(1)}L` : a >= 1e3 ? `${Math.round(v / 1e3)}k` : `${v}` }
export const monthLabel = (m) => { if (!m) return ''; const [y, mo] = m.split('-'); return `${['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][Number(mo) - 1]} ’${y.slice(2)}` }
export const dateLabel = (d) => { if (!d) return ''; const x = new Date(d); return x.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: '2-digit' }) }
export const PALETTE = ['#3157c8', '#0e8074', '#6e52d9', '#b8640a', '#c0396b', '#667085', '#226aa8', '#13794a', '#8a5a00', '#98a2b3']
export const tone = { good: '#13794a', warn: '#b8640a', bad: '#c4320a', info: '#0e8074', accent: '#3157c8', muted: '#656d7f' }
