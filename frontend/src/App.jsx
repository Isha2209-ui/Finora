import { Navigate, Route, Routes } from 'react-router-dom'
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
import Investments from './pages/Investments.jsx'
import Lookup from './pages/Lookup.jsx'
import ModelLab from './pages/ModelLab.jsx'
import Recommendations from './pages/Recommendations.jsx'
import Reports from './pages/Reports.jsx'
import Transactions from './pages/Transactions.jsx'
import { useFinora } from './store.jsx'

export default function App() {
  const { profileId, analysis, loading, error, refresh } = useFinora()
  if (!profileId) return <Routes><Route path="*" element={<Lookup />} /></Routes>
  return (
    <Layout>
      {error ? <ErrorBox message={error} onRetry={() => refresh()} />
        : !analysis || loading && !analysis ? <Loading full label="Running models and calculations…" />
          : (
            <Routes>
              <Route path="/" element={<Navigate to="/identity" replace />} />
              <Route path="/identity" element={<Identity />} />
              <Route path="/accounts" element={<Accounts />} />
              <Route path="/investments" element={<Investments />} />
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
          )}
    </Layout>
  )
}
