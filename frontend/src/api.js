// Thin API client. All requests go to /api (proxied to FastAPI on port 8001), so cookies stay same-origin.
// The session lives in an httpOnly cookie the page cannot read. State-changing requests echo the CSRF token
// (from the readable finora_csrf cookie) in the X-CSRF-Token header.
const BASE = import.meta.env.VITE_API_URL || ''

let onUnauthorized = () => {}
export const setUnauthorizedHandler = (fn) => { onUnauthorized = fn }

const csrfToken = () => document.cookie.split('; ').find((c) => c.startsWith('finora_csrf='))?.slice('finora_csrf='.length) || ''

async function request(path, { method = 'GET', body, form, quiet401 = false } = {}) {
  let res
  const headers = {}
  if (body) headers['Content-Type'] = 'application/json'
  if (method !== 'GET') headers['X-CSRF-Token'] = decodeURIComponent(csrfToken())
  try {
    res = await fetch(`${BASE}/api${path}`, {
      method, headers, credentials: 'include',
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
    const err = new Error(msg); err.status = res.status
    if (res.status === 401 && !quiet401) onUnauthorized()
    throw err
  }
  return res.json()
}

export const api = {
  me: () => request('/auth/me', { quiet401: true }),
  login: (email, password) => request('/auth/login', { method: 'POST', body: { email, password }, quiet401: true }),
  register: (email, password, display_name) => request('/auth/register', { method: 'POST', body: { email, password, display_name } }),
  logout: () => request('/auth/logout', { method: 'POST', quiet401: true }),
  activity: () => request('/auth/activity'),
  health: () => request('/health'),
  lookup: (pan) => request('/lookup', { method: 'POST', body: { pan } }),
  demoTemplates: () => request('/demo/templates'),
  explore: (template_id) => request('/demo/explore', { method: 'POST', body: { template_id } }),
  resetSandbox: (id) => request(`/profiles/${id}/reset`, { method: 'POST' }),
  profiles: () => request('/profiles'),
  profile: (id) => request(`/profiles/${id}`),
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
  recordSchema: () => request('/records/schema'),
  recordCounts: (id) => request(`/profiles/${id}/records`),
  records: (id, type) => request(`/profiles/${id}/records/${type}`),
  createRecord: (id, type, body) => request(`/profiles/${id}/records/${type}`, { method: 'POST', body }),
  updateRecord: (id, type, itemId, body) => request(`/profiles/${id}/records/${type}/${itemId}`, { method: 'PATCH', body }),
  deleteRecord: (id, type, itemId, cascade = false) => request(`/profiles/${id}/records/${type}/${itemId}${cascade ? '?cascade=true' : ''}`, { method: 'DELETE' }),
  metrics: () => request('/models/metrics'),
  retrain: () => request('/models/retrain', { method: 'POST' }),
  url: (path) => `${BASE}/api${path}`,
}
