import { useState } from 'react'
import { Archive, FileDown, FileSpreadsheet, FileText } from 'lucide-react'
import { api } from '../api'
import { Button, ErrorBox, PageHeader, Section, Table } from '../components/ui.jsx'
import { useAsync, useFinora } from '../store.jsx'

const SECTIONS = ['Financial profile and headline numbers', 'Overall summary with the CFO briefing', 'Financial identity and net worth', 'Income and expenditure, month by month',
  'Transaction anomaly analysis', 'Cash-flow forecast and category budgets', 'Credit, loans and EMI assessment', 'Savings, budget and liquidity', 'Investments',
  'FIRE forecast', 'Protection and peer comparison', 'Concerns and personalised recommendations', 'Model evaluation']

async function download(url, fallbackName) {
  const res = await fetch(url)
  if (!res.ok) throw new Error(`Download failed (${res.status})`)
  const name = /filename="([^"]+)"/.exec(res.headers.get('Content-Disposition') || '')?.[1] || fallbackName
  const a = document.createElement('a'); a.href = URL.createObjectURL(await res.blob()); a.download = name; a.click(); URL.revokeObjectURL(a.href)
}

export default function Reports() {
  const { profileId, analysis: a } = useFinora()
  const hist = useAsync(() => api.reports(profileId), [profileId])
  const [busy, setBusy] = useState(null)
  const [err, setErr] = useState(null)
  const go = async (key, path, name) => { setBusy(key); setErr(null); try { await download(api.url(path), name); hist.reload() } catch (e) { setErr(e.message) } finally { setBusy(null) } }
  const out = [
    ['pdf', FileText, 'Financial Intelligence Report', `A written report for ${a.profile.name}, about 8 pages, generated from the same numbers shown on screen.`, 'Generate PDF', `/profiles/${profileId}/report.pdf`, 'Finora_Report.pdf'],
    ['pdfai', FileText, 'Report with an AI-written summary', 'The same report; the summary is written by the local model only if its numbers pass verification, otherwise the rule-written one is used.', 'Generate PDF', `/profiles/${profileId}/report.pdf?use_llm=true`, 'Finora_Report.pdf'],
    ['csv', FileSpreadsheet, 'Transactions', 'Every transaction as a CSV file.', 'Download CSV', `/profiles/${profileId}/transactions.csv`, 'transactions.csv'],
    ['zip', Archive, 'Everything', 'Nine CSV files: transactions, monthly summary, categories, holdings, net worth, flags, recommendations, forecast and FIRE.', 'Download zip', `/profiles/${profileId}/export.zip`, 'Finora_Export.zip'],
  ]
  return (
    <>
      <PageHeader title="Reports & export" subtitle="Take your analysis and data with you." />
      {err && <div className="mb-4"><ErrorBox message={err} /></div>}
      <ul className="divide-y divide-line overflow-hidden rounded-xl border border-line bg-bg">
        {out.map(([k, I, t, d, label, path, name]) => (
          <li key={k} className="flex flex-wrap items-center gap-4 px-5 py-4 sm:px-6">
            <span className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-accent-soft text-accent"><I size={18} aria-hidden /></span>
            <div className="min-w-0 flex-1 basis-64"><div className="text-[15px] font-medium text-ink">{t}</div><div className="text-[13px] leading-5 text-muted">{d}</div></div>
            <Button variant="secondary" icon={FileDown} loading={busy === k} onClick={() => go(k, path, name)}>{busy === k ? 'Preparing…' : label}</Button>
          </li>
        ))}
      </ul>
      <details className="mt-6 rounded-xl border border-line bg-bg px-5 py-4"><summary className="cursor-pointer text-[15px] font-medium text-ink">What the PDF report contains</summary>
        <ol className="mt-3 grid gap-x-6 gap-y-1.5 text-sm text-muted md:grid-cols-2">{SECTIONS.map((x, i) => <li key={x}><span className="num mr-2 text-faint">{String(i + 1).padStart(2, '0')}</span>{x}</li>)}</ol></details>
      <Section title="Previously generated" className="mt-10">
        <div className="overflow-hidden rounded-xl border border-line bg-bg"><Table dense rows={hist.data || []} empty="No reports generated yet" caption="Previously generated reports" columns={[
          { key: 'file', label: 'File', render: (r) => <span className="font-mono text-micro">{r.file}</span> },
          { key: 'created_at', label: 'Generated', right: true, render: (r) => new Date(r.created_at + 'Z').toLocaleString('en-IN') }]} /></div>
      </Section>
    </>
  )
}
