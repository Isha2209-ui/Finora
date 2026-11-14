import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { api, setUnauthorizedHandler } from './api'

const Ctx = createContext(null)
export const useAuth = () => useContext(Ctx)

// The signed-in account. The session token itself is an httpOnly cookie - JavaScript never sees it.
export function AuthProvider({ children }) {
  const [account, setAccount] = useState(undefined) // undefined = checking, null = signed out
  const signedOut = useCallback(() => {
    sessionStorage.removeItem('finora.profile')
    setAccount(null)
  }, [])

  useEffect(() => {
    setUnauthorizedHandler(signedOut)
    api.me().then((r) => setAccount(r.account)).catch(() => setAccount(null))
  }, [signedOut])

  const login = async (email, password) => setAccount((await api.login(email, password)).account)
  const register = async (email, password, name) => setAccount((await api.register(email, password, name)).account)
  const logout = async () => { try { await api.logout() } finally { signedOut() } }

  return <Ctx.Provider value={{ account, login, register, logout }}>{children}</Ctx.Provider>
}
