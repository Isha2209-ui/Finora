// Risk & Models → Peers. K-Means groups learned from the Federal Reserve's Survey of Consumer Finances 2022 (US households,
// survey-weighted, 5 imputations). Answer first; each measure as "better than X% of households".
import { Link } from 'react-router-dom'
import { Answer, Card, Empty, Meter, PageHeader, Section, Trust } from '../components/ui.jsx'
import { present } from '../components/models.js'
import { useFinora } from '../store.jsx'

const fmt = (v) => (v == null ? '—' : Number(v).toLocaleString('en-IN', { maximumFractionDigits: 2 }))

export default function Peers() {
  const { analysis: a } = useFinora()
  const p = a.ml.peers || {}
  if (p.available === false || !p.comparison) return (
    <><PageHeader title="Peers" />
      <Card><Empty title="Not enough information to compare yet">{p.note || a.ml_errors?.peers || 'Add income and a few months of spending, plus your accounts and debts, under Data → Records.'}</Empty></Card></>
  )
  const strong = p.strengths?.length ? p.strengths.join(', ') : null
  const weak = p.weaknesses?.length ? p.weaknesses.join(', ') : null
  return (
    <>
      <PageHeader title="Peers" />
      <Answer eyebrow="How you compare with similar households"
        sub={[strong && `You do better than most on ${strong}.`, weak && `You trail most on ${weak}.`].filter(Boolean).join(' ') || 'No single measure stands out.'}>
        You are closest to <b>{p.peer_group}</b>, a group that is {p.peer_group_share_pct}% of US households.
      </Answer>
      <Trust model="peers" className="mb-8" />

      <Section title="Measure by measure" description={`Values are ${p.units || 'ratios'}. The bar shows the survey-weighted share of US households you do better than.`}>
        <ul className="divide-y divide-line overflow-hidden rounded-xl border border-line bg-bg">
          {p.comparison.map((c) => (
            <li key={c.metric} className="grid gap-3 px-5 py-4 sm:grid-cols-[minmax(0,1fr)_260px] sm:items-center sm:px-6">
              <div className="min-w-0">
                <div className="text-[15px] font-medium text-ink">{c.metric}</div>
                <div className="num mt-0.5 text-[13px] text-muted">You {fmt(c.you)} · your group {fmt(c.peer_group_median)} · all US households {fmt(c.everyone_median)} (medians)</div>
              </div>
              <Meter value={c.better_than_pct_of_people} tone={c.better_than_pct_of_people >= 70 ? 'good' : c.better_than_pct_of_people <= 30 ? 'bad' : 'accent'}
                label={<><span>Better than</span><span className="num font-medium text-ink">{c.better_than_pct_of_people}% of households</span></>} />
            </li>
          ))}
        </ul>
      </Section>

      <div className="mt-10 grid gap-8 lg:grid-cols-2">
        <Section title="The US household groups">
          <ul className="divide-y divide-line overflow-hidden rounded-xl border border-line bg-bg">
            {(p.all_groups || []).map((g) => (
              <li key={g.name} className="flex items-center justify-between gap-3 px-5 py-3.5 text-sm sm:px-6">
                <span className={g.name === p.peer_group ? 'font-semibold text-accent' : 'text-ink-2'}>{g.name}{g.name === p.peer_group && ' · your group'}</span>
                <span className="num text-muted">{g.share_pct}% of households</span>
              </li>))}
          </ul>
          <p className="mt-3 text-[13px] text-muted">About {p.peer_group_households_millions} million of {p.population_households_millions} million US households are in your group. <Link to="/models?tab=lab&model=peers" className="font-medium text-accent hover:underline">How the groups were built</Link></p>
        </Section>
        <Section title="Where the benchmark comes from">
          <p className="text-sm leading-6 text-ink-2">Groups are learned from the Federal Reserve's Survey of Consumer Finances 2022. Your ratios are computed from your Finora data and matched to the nearest group.</p>
          {p.note && <p className="mt-2 text-sm leading-6 text-muted">{present(p.note)}</p>}
        </Section>
      </div>
    </>
  )
}
