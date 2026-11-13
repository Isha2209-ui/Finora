import { useState } from 'react'
import { Archive, FileDown, FileSpreadsheet, FileText } from 'lucide-react'
import { api } from '../api'
import { Button, Card, Note, PageHeader, Table } from '../components/ui.jsx'
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
  return (
    <>
      <PageHeader title="Intelligence Reports" subtitle="A complete written report of this profile, generated from the same numbers shown on screen." />
      <div className="grid gap-4 xl:grid-cols-3">
        <Card title="Financial Intelligence Report" subtitle={`For ${a.profile.name} · PDF, about 8 pages`} className="xl:col-span-2">
          <ol className="grid gap-x-6 gap-y-1.5 text-sm text-muted md:grid-cols-2">{SECTIONS.map((s, i) => <li key={s}><span className="num mr-2 text-faint">{String(i + 1).padStart(2, '0')}</span>{s}</li>)}</ol>
          <div className="mt-5 flex flex-wrap gap-2">
            <Button icon={FileText} loading={busy === 'pdf'} onClick={() => go('pdf', `/profiles/${profileId}/report.pdf`, 'Finora_Report.pdf')}>Generate PDF report</Button>
            <Button variant="ghost" icon={FileText} loading={busy === 'pdfai'} onClick={() => go('pdfai', `/profiles/${profileId}/report.pdf?use_llm=true`, 'Finora_Report.pdf')}>PDF with AI-written summary</Button>
          </div>
          {err && <p className="mt-3 text-sm text-bad">{err}</p>}
          <div className="mt-4"><Note>The AI-written summary is used only if the local model is running and its numbers pass verification; otherwise the rule-written summary is used.</Note></div>
        </Card>
        <Card title="Data exports">
          <div className="space-y-2">
            <Button variant="ghost" icon={FileSpreadsheet} className="w-full justify-start" loading={busy === 'csv'} onClick={() => go('csv', `/profiles/${profileId}/transactions.csv`, 'transactions.csv')}>Transactions (CSV)</Button>
            <Button variant="ghost" icon={Archive} className="w-full justify-start" loading={busy === 'zip'} onClick={() => go('zip', `/profiles/${profileId}/export.zip`, 'Finora_Export.zip')}>Everything (zip of 9 CSV files)</Button>
          </div>
          <p className="mt-3 text-xs text-muted">The zip contains transactions, monthly summary, category totals, holdings, net worth, flagged transactions, recommendations, category forecast and the FIRE projection.</p>
        </Card>
      </div>
      <Card title="Previously generated" className="mt-4" pad={false}>
        <Table dense rows={hist.data || []} empty="No reports generated yet" columns={[
          { key: 'file', label: 'File', render: (r) => <span className="flex items-center gap-2 font-mono text-xs"><FileDown size={13} className="text-faint" />{r.file}</span> },
          { key: 'created_at', label: 'Generated', right: true, render: (r) => new Date(r.created_at + 'Z').toLocaleString('en-IN') }]} />
      </Card>
    </>
  )
}
