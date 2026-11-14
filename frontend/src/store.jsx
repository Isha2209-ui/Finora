import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { api } from './api'
import { useAuth } from './auth.jsx'

const Ctx = createContext(null)
export const useFinora = () => useContext(Ctx)

// Holds the selected profile and its analysis. Only the internal profile ID is kept in the
// browser (sessionStorage) - never the PAN.
export function FinoraProvider({ children }) {
  const [profileId, setProfileId] = useState(() => sessionStorage.getItem('finora.profile') || null)
  const [analysis, setAnalysis] = useState(null)
  const [profile, setProfile] = useState(null) // ownership info: kind, read_only, expires_at
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const { account } = useAuth()
  // Signing out of the account (or a 401) forgets the selected profile too.
  useEffect(() => { if (account === null) { setProfileId(null); setAnalysis(null) } }, [account])

  const load = useCallback(async (id, { rerun = false } = {}) => {
    if (!id) return
    setLoading(true); setError(null)
    try {
      const [p, a] = await Promise.all([api.profile(id), rerun ? api.analyze(id) : api.analysis(id)])
      setProfile(p); setAnalysis(a)
      return a
    }
    catch (e) { setError(e.message); if (e.status === 404) { sessionStorage.removeItem('finora.profile'); setProfileId(null) } }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { if (profileId && account) load(profileId); else setAnalysis(null) }, [profileId, account, load])

  const select = (id) => { sessionStorage.setItem('finora.profile', id); setAnalysis(null); setProfileId(id) }
  const signOut = () => { sessionStorage.removeItem('finora.profile'); setProfileId(null); setAnalysis(null) }
  const refresh = (opts) => load(profileId, opts)

  return <Ctx.Provider value={{ profileId, profile, analysis, loading, error, select, signOut, refresh }}>{children}</Ctx.Provider>
}

// Small hook for page-level requests: { data, loading, error, reload }
export function useAsync(fn, deps = []) {
  const [state, setState] = useState({ data: null, loading: true, error: null })
  const run = useCallback(async () => {
    setState((s) => ({ ...s, loading: true, error: null }))
    try { setState({ data: await fn(), loading: false, error: null }) }
    catch (e) { setState({ data: null, loading: false, error: e.message }) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)
  useEffect(() => { run() }, [run])
  return { ...state, reload: run }
}
