// An area page (Plan, Money, Future, Risk & Models, Data): title, one-line purpose, URL-synced tabs (?tab=), tab content.
import { Suspense } from 'react'
import { EmbeddedCtx, Loading, PageHeader, Tabs, useUrlParam } from './ui.jsx'
import ErrorBoundary from './ErrorBoundary.jsx'

export default function Area({ title, subtitle, tabs, actions }) {
  const ids = tabs.map((t) => t.id)
  const [tab, setTab] = useUrlParam('tab', ids)
  const cur = tabs.find((t) => t.id === tab) || tabs[0]
  return (
    <>
      <PageHeader title={title} subtitle={subtitle}>{actions}</PageHeader>
      <Tabs tabs={tabs} value={cur.id} onChange={setTab} label={`${title} sections`} />
      <div role="tabpanel" aria-label={cur.label} key={cur.id} className="rise">
        <EmbeddedCtx.Provider value={true}>
          <ErrorBoundary><Suspense fallback={<Loading />}>{cur.render()}</Suspense></ErrorBoundary>
        </EmbeddedCtx.Provider>
      </div>
    </>
  )
}
