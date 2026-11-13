// Thin API client. All requests go to /api (proxied to FastAPI on port 8001).
const BASE = import.meta.env.VITE_API_URL || ''

async function request(path, { method = 'GET', body, form } = {}) {
  let res
  try {
    res = await fetch(`${BASE}/api${path}`, {
      method,
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body: form || (body ? JSON.stringify(body) : undefined),
    })
  } catch {
    throw new Error('Cannot reach the Finora backend. Is it running on port 8001?')
  }
  if (!res.ok) {
    let msg = `Request failed (${res.status})`
    try {
      const j = await res.json()
      msg = typeof j.detail === 'string' ? j.detail : Array.isArray(j.detail) ? j.detail.map((d) => `${d.loc?.slice(-1)[0]}: ${d.msg}`).join('; ') : msg
    } catch { /* keep default */ }
    const err = new Error(msg); err.status = res.status; throw err
  }
  return res.json()
}

export const api = {
  health: () => request('/health'),
  lookup: (pan) => request('/lookup', { method: 'POST', body: { pan } }),
  profiles: () => request('/profiles'),
  analysis: (id) => request(`/profiles/${id}/analysis`),
  analyze: (id) => request(`/profiles/${id}/analyze`, { method: 'POST' }),
  accounts: (id) => request(`/profiles/${id}/accounts`),
  transactions: (id, params = {}) => request(`/profiles/${id}/transactions?` + new URLSearchParams(Object.fromEntries(Object.entries(params).filter(([, v]) => v !== '' && v !== null && v !== undefined && v !== false)))),
  recategorise: (id, txId, category) => request(`/profiles/${id}/transactions/${txId}`, { method: 'PATCH', body: { category } }),
  addTransaction: (id, body) => request(`/profiles/${id}/transactions`, { method: 'POST', body }),
  deleteTransaction: (id, txId) => request(`/profiles/${id}/transactions/${txId}`, { method: 'DELETE' }),
  recommendations: (id) => request(`/profiles/${id}/recommendations`),
  setRecStatus: (id, recId, status) => request(`/profiles/${id}/recommendations/${recId}`, { method: 'PATCH', body: { status } }),
  fire: (id, body) => request(`/profiles/${id}/fire`, { method: 'POST', body }),
  decision: (id, body) => request(`/profiles/${id}/decision`, { method: 'POST', body }),
  payoff: (id, extra) => request(`/profiles/${id}/payoff`, { method: 'POST', body: { extra_monthly: extra } }),
  tax: (body) => request('/tax/compare', { method: 'POST', body }),
  chat: (id, message) => request(`/profiles/${id}/chat`, { method: 'POST', body: { message } }),
  chatHistory: (id) => request(`/profiles/${id}/chat`),
  clearChat: (id) => request(`/profiles/${id}/chat`, { method: 'DELETE' }),
  briefing: (id) => request(`/profiles/${id}/briefing`),
  cfoStatus: () => request('/cfo/status'),
  reports: (id) => request(`/profiles/${id}/reports`),
  upload: (id, file, target) => { const f = new FormData(); f.append('file', file); if (target?.startsWith('account:')) f.append('account_id', target.split(':')[1]); if (target?.startsWith('card:')) f.append('card_id', target.split(':')[1]); return request(`/profiles/${id}/upload`, { method: 'POST', form: f }) },
  categorise: (texts) => request('/categorise', { method: 'POST', body: { texts } }),
  createProfile: (body) => request('/profiles', { method: 'POST', body }),
  patchProfile: (id, body) => request(`/profiles/${id}`, { method: 'PATCH', body }),
  deleteProfile: (id) => request(`/profiles/${id}`, { method: 'DELETE' }),
  dataSummary: (id) => request(`/profiles/${id}/data-summary`),
  metrics: () => request('/models/metrics'),
  retrain: () => request('/models/retrain', { method: 'POST' }),
  url: (path) => `${BASE}/api${path}`,
}
