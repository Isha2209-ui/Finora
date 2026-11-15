import { Suspense, lazy } from 'react'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import ErrorBoundary from './components/ErrorBoundary.jsx'
import Layout from './components/Layout.jsx'
import { ErrorBox, Loading } from './components/ui.jsx'
import { useAuth } from './auth.jsx'
import Lookup from './pages/Lookup.jsx'
import SignIn from './pages/SignIn.jsx'
import { useFinora } from './store.jsx'

const Home = lazy(() => import('./pages/Home.jsx'))
const Ask = lazy(() => import('./pages/Cfo.jsx'))
const Settings = lazy(() => import('./pages/Settings.jsx'))
const AnomalyReview = lazy(() => import('./pages/AnomalyReview.jsx'))
const PlanArea = lazy(() => import('./pages/Areas.jsx').then((m) => ({ default: m.PlanArea })))
const MoneyArea = lazy(() => import('./pages/Areas.jsx').then((m) => ({ default: m.MoneyArea })))
const FutureArea = lazy(() => import('./pages/Areas.jsx').then((m) => ({ default: m.FutureArea })))
const ModelsArea = lazy(() => import('./pages/Areas.jsx').then((m) => ({ default: m.ModelsArea })))
const DataArea = lazy(() => import('./pages/Areas.jsx').then((m) => ({ default: m.DataArea })))

// Old routes → new area + tab (spec §4.1 redirect table). Any query on the old URL is kept (e.g. /review?import=12).
const REDIRECTS = {
  '/identity': '/money?tab=overview', '/insights': '/money?tab=spending', '/budget': '/money?tab=spending&view=budget',
  '/credit': '/models?tab=credit-risk', '/forecast': '/future?tab=cash-flow', '/fire': '/future?tab=retirement', '/decision': '/future?tab=what-if',
  '/cfo': '/ask', '/recommendations': '/plan?tab=actions', '/statements': '/data?tab=import', '/review': '/data?tab=review',
  '/records': '/data?tab=records', '/reports': '/data?tab=reports', '/accounts': '/money?tab=accounts', '/investments': '/money?tab=investments',
  '/transactions': '/money?tab=transactions', '/scanner': '/models?tab=unusual', '/peers': '/models?tab=peers',
}
function Redirect({ to }) {
  const { search } = useLocation()
  const extra = search.replace(/^\?/, '')
  return <Navigate replace to={extra ? `${to}${to.includes('?') ? '&' : '?'}${extra}` : to} />
}
// Old "/data" (Profile & Data) with no tab is the new Data area's default tab, so it needs no redirect.

export default function App() {
  const { account } = useAuth()
  const { profileId, analysis, loading, error, refresh } = useFinora()
  if (account === undefined) return <Loading full label="Checking your session…" />
  if (account === null) return <Routes><Route path="*" element={<SignIn />} /></Routes>
  if (!profileId) return <Routes><Route path="*" element={<Lookup />} /></Routes>
  return (
    <Layout>
      {error ? <ErrorBox message={error} onRetry={() => refresh()} />
        : !analysis || loading && !analysis ? <Loading full label="Running models and calculations…" />
          : (
            <ErrorBoundary>
              <Suspense fallback={<Loading />}>
                <Routes>
                  <Route path="/" element={<Home />} />
                  <Route path="/plan" element={<PlanArea />} />
                  <Route path="/money" element={<MoneyArea />} />
                  <Route path="/future" element={<FutureArea />} />
                  <Route path="/models" element={<ModelsArea />} />
                  <Route path="/models/review" element={<AnomalyReview />} />
                  <Route path="/ask" element={<Ask />} />
                  <Route path="/data" element={<DataArea />} />
                  <Route path="/settings" element={<Settings />} />
                  {Object.entries(REDIRECTS).map(([from, to]) => <Route key={from} path={from} element={<Redirect to={to} />} />)}
                  <Route path="*" element={<Navigate to="/" replace />} />
                </Routes>
              </Suspense>
            </ErrorBoundary>
          )}
    </Layout>
  )
}
