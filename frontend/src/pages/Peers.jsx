import { Link } from 'react-router-dom'
import { Users } from 'lucide-react'
import { Badge, Button, Card, Empty, Note, PageHeader, Stat, Table } from '../components/ui.jsx'
import { useFinora } from '../store.jsx'

// Peer Benchmarking: K-Means groups learned from the Federal Reserve's Survey of Consumer Finances 2022 (US households,
// survey-weighted, 5 imputations). Shows where this profile's ratios fall among US households.
const fmt = (v) => (v == null ? '-' : Number(v).toLocaleString('en-IN', { maximumFractionDigits: 2 }))

export default function Peers() {
  const { analysis: a } = useFinora()
  const p = a.ml.peers || {}
  return (
    <>
      <PageHeader title="Peer Benchmarking" subtitle="How your savings, debt and assets compare with similar US households, using groups learned from a national survey." />
      <div className="mb-4"><Note tone="warn">These are <b>US household</b> benchmarks (Federal Reserve Survey of Consumer Finances 2022), not Indian ones, and a Finora
        profile may be one person rather than a household. The survey uses gross income while Finora sees take-home pay, so your ratios to income read higher than
        a US household's would; card balances are measured differently.</Note></div>
      {p.available === false || !p.comparison ? (
        <Card><Empty title="Not enough information to compare yet">{p.note || a.ml_errors?.peers || 'Add income and a few months of spending, plus your accounts and debts, under My Data.'}</Empty></Card>
      ) : <>
        <div className="grid gap-4 md:grid-cols-3">
          <Stat label="Your closest peer group" value={p.peer_group} icon={Users} />
          <Stat label="Share of US households in it" value={`${p.peer_group_share_pct}%`} sub={`about ${p.peer_group_households_millions} million of ${p.population_households_millions} million households`} />
          <Stat label="Model" value={p.model_info?.version || '-'} sub="K-Means, survey-weighted, stable across 5 imputations" />
        </div>
        <Card title="Your ratios against US households" subtitle={`Values are ${p.units || 'ratios'}; "better than" is the survey-weighted share of US households you beat on that measure`} className="mt-4" pad={false}>
          <Table dense rows={p.comparison} columns={[
            { key: 'metric', label: 'Measure', render: (c) => <span className="font-medium">{c.metric}</span> },
            { key: 'you', label: 'You', right: true, render: (c) => fmt(c.you) },
            { key: 'peer_group_median', label: 'Your group (median)', right: true, render: (c) => fmt(c.peer_group_median) },
            { key: 'everyone_median', label: 'All US households (median)', right: true, render: (c) => fmt(c.everyone_median) },
            { key: 'better_than_pct_of_people', label: 'Better than', right: true, render: (c) => <Badge tone={c.better_than_pct_of_people >= 70 ? 'good' : c.better_than_pct_of_people <= 30 ? 'bad' : 'neutral'}>{c.better_than_pct_of_people}% of households</Badge> },
          ]} />
        </Card>
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <Card title="Where you stand out">
            <p className="text-sm"><span className="text-good">Stronger than most:</span> {p.strengths?.length ? p.strengths.join(', ') : 'no single measure stands out'}</p>
            <p className="mt-2 text-sm"><span className="text-bad">Weaker than most:</span> {p.weaknesses?.length ? p.weaknesses.join(', ') : 'nothing notable'}</p>
          </Card>
          <Card title="The three US household groups">
            <ul className="space-y-1 text-sm">{(p.all_groups || []).map((g) => <li key={g.name} className="flex justify-between"><span className={g.name === p.peer_group ? 'font-medium text-accent' : 'text-muted'}>{g.name}</span><span className="num">{g.share_pct}%</span></li>)}</ul>
            <div className="mt-3"><Link to="/models"><Button variant="ghost">How the groups were built</Button></Link></div>
          </Card>
        </div>
        {p.note && <div className="mt-4"><Note>{p.note}</Note></div>}
      </>}
    </>
  )
}
