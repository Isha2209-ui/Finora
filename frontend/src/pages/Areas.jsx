// The five tabbed areas (spec §4.1). Each tab renders an existing, working page component; nothing is re-implemented here.
import { lazy, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'
import Area from '../components/Area.jsx'
import { Badge, ModelExplainer, PageHeader, Trust } from '../components/ui.jsx'
import { MODELS } from '../components/models.js'
import { inr } from '../format'
import { useFinora } from '../store.jsx'
import { TryCategoriser } from './ModelLab.jsx'

const Accounts = lazy(() => import('./Accounts.jsx'))
const Investments = lazy(() => import('./Investments.jsx'))
const Transactions = lazy(() => import('./Transactions.jsx'))
const Spending = lazy(() => import('./Insights.jsx'))
const Forecast = lazy(() => import('./Forecast.jsx'))
const Fire = lazy(() => import('./Fire.jsx'))
const Decision = lazy(() => import('./Decision.jsx'))
const Peers = lazy(() => import('./Peers.jsx'))
const Scanner = lazy(() => import('./Scanner.jsx'))
const ModelLab = lazy(() => import('./ModelLab.jsx'))
const Statements = lazy(() => import('./Statements.jsx'))
const Review = lazy(() => import('./Review.jsx'))
const Records = lazy(() => import('./Records.jsx'))
const Goals = lazy(() => import('./Goals.jsx'))
const Reports = lazy(() => import('./Reports.jsx'))
const DataManagement = lazy(() => import('./DataManagement.jsx'))
const Recommendations = lazy(() => import('./Recommendations.jsx'))
const Identity = lazy(() => import('./Identity.jsx').then((m) => ({ default: m.MoneyOverview })))
const Health = lazy(() => import('./Identity.jsx').then((m) => ({ default: m.HealthSection })))
const Savings = lazy(() => import('./Budget.jsx').then((m) => ({ default: m.SavingsSection })))
const Tax = lazy(() => import('./Budget.jsx').then((m) => ({ default: m.TaxSection })))
const CreditRisk = lazy(() => import('./Credit.jsx').then((m) => ({ default: m.CreditRiskSection })))
const Debts = lazy(() => import('./Credit.jsx').then((m) => ({ default: m.DebtsSection })))
const PlanSection = lazy(() => import('./Plan.jsx').then((m) => ({ default: m.PlanSection })))

function useGoTo() {
  const [, setSp] = useSearchParams()
  return (tab) => { setSp(new URLSearchParams({ tab })); document.getElementById('main')?.scrollTo?.({ top: 0 }) }
}

export function PlanArea() {
  const goTo = useGoTo()
  return <Area title="Plan" subtitle="What needs attention, what to do about it, and what it would change. Findings are facts from your numbers; actions are suggestions you choose to accept."
    tabs={[
      { id: 'priorities', label: 'Priorities', render: () => <PlanSection section="priorities" goTo={goTo} /> },
      { id: 'actions', label: 'Actions', render: () => <PlanSection section="actions" goTo={goTo} extra={<Recommendations />} /> },
      { id: 'plan', label: 'Your plan', render: () => <PlanSection section="plan" goTo={goTo} /> },
      { id: 'health', label: 'Health', render: () => <Health /> },
      { id: 'goals', label: 'Goals', render: () => <Goals /> },
      { id: 'tax', label: 'Tax', render: () => <Tax /> },
    ]} />
}

export function MoneyArea() {
  return <Area title="Money" subtitle="Everything you own and owe, every transaction, and where it goes."
    tabs={[
      { id: 'overview', label: 'Overview', render: () => <Identity /> },
      { id: 'accounts', label: 'Accounts & cards', render: () => <Accounts /> },
      { id: 'transactions', label: 'Transactions', render: () => <Transactions /> },
      { id: 'spending', label: 'Spending', render: () => <Spending /> },
      { id: 'investments', label: 'Investments', render: () => <Investments /> },
      { id: 'debts', label: 'Debts', render: () => <Debts /> },
    ]} />
}

export function FutureArea() {
  return <Area title="Future" subtitle="Projections built from your actual history. Anything marked as a forecast, projection or what-if has not happened."
    tabs={[
      { id: 'cash-flow', label: 'Cash flow', render: () => <Forecast /> },
      { id: 'retirement', label: 'Retirement', render: () => <Fire /> },
      { id: 'what-if', label: 'What if', render: () => <Decision /> },
      { id: 'savings', label: 'Savings', render: () => <Savings /> },
    ]} />
}

export function ModelsArea() {
  return <Area title="Risk & Models" subtitle="Finora's six machine-learning features: what each one does, the data it learned from, its result for you, and its limits."
    tabs={[
      { id: 'overview', label: 'Overview', render: () => <ModelsOverview /> },
      { id: 'credit-risk', label: 'Credit risk', render: () => <CreditRisk /> },
      { id: 'peers', label: 'Peers', render: () => <Peers /> },
      { id: 'categoriser', label: 'Categoriser', render: () => <Categoriser /> },
      { id: 'unusual', label: 'Unusual activity', render: () => <Scanner /> },
      { id: 'lab', label: 'Model Lab', render: () => <ModelLab /> },
    ]} />
}

export function DataArea() {
  return <Area title="Data" subtitle="Bring your data in, check it, edit it, export it, and control your profile."
    tabs={[
      { id: 'import', label: 'Import', render: () => <Statements /> },
      { id: 'review', label: 'Review', render: () => <Review /> },
      { id: 'records', label: 'Records', render: () => <Records /> },
      { id: 'reports', label: 'Reports & export', render: () => <Reports /> },
      { id: 'profile', label: 'Profile & privacy', render: () => <DataManagement /> },
    ]} />
}

// ---------------------------------------------------------------- Risk & Models → Overview: the six capabilities, each with its algorithm and your result
function ModelsOverview() {
  const { analysis: a } = useFinora()
  const [explain, setExplain] = useState(null)
  const ml = a.ml
  const cr = ml.credit_risk, pe = ml.peers, an = ml.anomaly, fc = ml.forecast
  const result = {
    credit_risk: cr?.cards ? `${cr.overall_default_probability_pct}% chance of a missed payment · ${cr.overall_risk_band}` : 'No card history to score yet',
    peers: pe?.available === false || !pe?.peer_group ? 'Needs income, spending and balances' : `Closest group: ${pe.peer_group}`,
    categoriser: 'Suggests a category for every transaction',
    anomaly: an?.available === false ? 'Not available for this profile' : `${an?.flagged_count ?? 0} of ${an?.transactions_scored ?? 0} transactions flagged`,
    forecast: fc?.available === false || fc?.predicted_total_expense == null ? 'Needs six months of transactions' : `${inr(fc.predicted_total_expense)} predicted for ${fc.prediction_month}`,
  }
  return (
    <>
      <PageHeader title="Your models at a glance" subtitle="Six machine-learning capabilities, each computed on your data. Open one to use it, or see how it works." />
      <ul className="divide-y divide-line overflow-hidden rounded-xl border border-line bg-bg">
        {Object.entries(MODELS).map(([key, m]) => (
          <li key={key} className="grid gap-x-6 gap-y-3 px-5 py-5 sm:px-6 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)_auto] lg:items-center">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2"><h3 className="text-[15px] font-semibold text-ink">{m.name}</h3><Badge tone="accent">{m.algorithm}</Badge></div>
              <p className="mt-1 text-[13px] leading-5 text-muted">{m.purpose}</p>
            </div>
            <div className="num text-sm text-ink-2">{result[key]}</div>
            <div className="flex items-center gap-4">
              <button type="button" onClick={() => setExplain(key)} className="text-[13px] font-medium text-ink-2 hover:text-accent">How it works</button>
              <Link to={m.to} className="inline-flex items-center gap-1 text-[13px] font-medium text-accent hover:underline">Open <ArrowRight size={14} aria-hidden /></Link>
            </div>
          </li>
        ))}
        <li className="grid gap-3 px-5 py-5 sm:px-6 lg:grid-cols-[1fr_auto] lg:items-center">
          <div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><h3 className="text-[15px] font-semibold text-ink">Model Lab and provenance</h3><Badge>All models</Badge></div>
            <p className="mt-1 text-[13px] leading-5 text-muted">Algorithms, versions, datasets, training runs, evaluation metrics and the review workspace.</p></div>
          <Link to="/models?tab=lab" className="inline-flex items-center gap-1 text-[13px] font-medium text-accent hover:underline">Open <ArrowRight size={14} aria-hidden /></Link>
        </li>
      </ul>
      {explain && <ModelExplainer model={explain} open={!!explain} onClose={() => setExplain(null)} />}
    </>
  )
}

function Categoriser() {
  return (
    <>
      <PageHeader title="Transaction categoriser" subtitle="Suggests a spending category from each transaction's description. It never overwrites a category you set; every suggestion waits for you to accept or correct it." />
      <Trust model="categoriser" className="mb-8" />
      <h3 className="text-[15px] font-semibold text-ink">Suggestions waiting for you</h3>
      <p className="mt-0.5 mb-3 text-[13px] text-muted">Open a row to accept the suggested category or choose the right one.</p>
      <div className="mb-8"><SuggestedTransactions /></div>
      <TryCategoriser />
    </>
  )
}

const SuggestedTransactions = lazy(() => import('./Transactions.jsx').then((m) => ({ default: () => <m.default suggestedOnly /> })))
