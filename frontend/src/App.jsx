import { Navigate, Route, Routes } from 'react-router-dom'
import ErrorBoundary from './components/ErrorBoundary.jsx'
import Layout from './components/Layout.jsx'
import { ErrorBox, Loading } from './components/ui.jsx'
import Accounts from './pages/Accounts.jsx'
import Budget from './pages/Budget.jsx'
import Cfo from './pages/Cfo.jsx'
import Credit from './pages/Credit.jsx'
import DataManagement from './pages/DataManagement.jsx'
import Decision from './pages/Decision.jsx'
import Fire from './pages/Fire.jsx'
import Forecast from './pages/Forecast.jsx'
import Identity from './pages/Identity.jsx'
import Insights from './pages/Insights.jsx'
import Investments from './pages/Investments.jsx'
import Lookup from './pages/Lookup.jsx'
import ModelLab from './pages/ModelLab.jsx'
import Recommendations from './pages/Recommendations.jsx'
import Records from './pages/Records.jsx'
import Reports from './pages/Reports.jsx'
import Review from './pages/Review.jsx'
import Statements from './pages/Statements.jsx'
import Transactions from './pages/Transactions.jsx'
import { useAuth } from './auth.jsx'
import SignIn from './pages/SignIn.jsx'
import { useFinora } from './store.jsx'

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
            <Routes>
              <Route path="/" element={<Navigate to="/identity" replace />} />
              <Route path="/identity" element={<Identity />} />
              <Route path="/records" element={<Records />} />
              <Route path="/accounts" element={<Accounts />} />
              <Route path="/investments" element={<Investments />} />
              <Route path="/statements" element={<Statements />} />
              <Route path="/insights" element={<Insights />} />
              <Route path="/review" element={<Review />} />
              <Route path="/transactions" element={<Transactions />} />
              <Route path="/forecast" element={<Forecast />} />
              <Route path="/credit" element={<Credit />} />
              <Route path="/budget" element={<Budget />} />
              <Route path="/fire" element={<Fire />} />
              <Route path="/decision" element={<Decision />} />
              <Route path="/cfo" element={<Cfo />} />
              <Route path="/recommendations" element={<Recommendations />} />
              <Route path="/reports" element={<Reports />} />
              <Route path="/models" element={<ModelLab />} />
              <Route path="/data" element={<DataManagement />} />
              <Route path="*" element={<Navigate to="/identity" replace />} />
            </Routes>
            </ErrorBoundary>
          )}
    </Layout>
  )
}
