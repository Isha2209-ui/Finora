import { useState } from 'react'
import { Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { CheckCircle2, FlaskConical, RefreshCw, XCircle } from 'lucide-react'
import { api } from '../api'
import { Badge, Button, Card, ErrorBox, Input, KV, Loading, Note, PageHeader, Table, chartTooltip, cx } from '../components/ui.jsx'
import { inr, pct } from '../format'
import { useAsync } from '../store.jsx'

const Beat = ({ ok }) => ok ? <Badge tone="good"><CheckCircle2 size={11} /> beats baseline</Badge> : <Badge tone="bad"><XCircle size={11} /> does not beat baseline</Badge>
const Versus = ({ rows, unit = '', lowerBetter }) => (
  <div className="space-y-2">{rows.map(([label, v, main]) => { const max = Math.max(...rows.map((r) => r[1])); return (
    <div key={label}><div className="flex justify-between text-xs"><span className={main ? 'font-medium text-ink' : 'text-muted'}>{label}</span><span className="num">{v}{unit}</span></div>
      <div className="mt-1 h-2 overflow-hidden rounded-full bg-raised"><div className={cx('h-full rounded-full', main ? 'bg-accent' : 'bg-faint')} style={{ width: `${(v / max) * 100}%` }} /></div></div>) })}
    <div className="text-[11px] text-faint">{lowerBetter ? 'Lower is better' : 'Higher is better'}</div></div>
)

export default function ModelLab() {
  const { data: m, loading, error, reload } = useAsync(() => api.metrics(), [])
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState(null)
  const [texts, setTexts] = useState('UPI/DR/402918376152/SWIGGY/YESB/swiggy@ybl/Payment\nPOS 4521XXXXXXXX8812 CROMA MUMBAI\nNACH/DR/BAJAJ FINANCE EMI/88213344\nATM WDL SBI ATM JAIPUR')
  const [preds, setPreds] = useState(null)
  if (loading && !m) return <Loading full />
  if (error) return <ErrorBox message={error} onRetry={reload} />
  const { credit_risk: cr, categoriser: ct, anomaly: an, forecast: fc, peers: pe } = m
  const retrain = async () => { setBusy(true); setMsg(null); try { const r = await api.retrain(); setMsg(`Retrained at ${new Date(r.trained_at).toLocaleTimeString()} - ${Object.entries(r.training_seconds).map(([k, v]) => `${k} ${v}s`).join(', ')}`); reload() } catch (e) { setMsg(e.message) } finally { setBusy(false) } }
  const tryCat = async () => setPreds(await api.categorise(texts.split('\n').map((s) => s.trim()).filter(Boolean)))
  const cm = ct.confusion_matrix_unseen_formats
  const cmMax = Math.max(...cm.matrix.flat())
  return (
    <>
      <PageHeader title="Model Lab" subtitle="How every model was trained, what it was tested on, and whether it actually beats the simple rule you could have written instead. All figures are measured on data the model did not see during training.">
        <Button variant="ghost" icon={RefreshCw} loading={busy} onClick={retrain}>Retrain all models</Button>
      </PageHeader>
      {msg && <div className="mb-4"><Note tone="info">{msg}</Note></div>}
      <div className="mb-4 flex flex-wrap gap-2 text-xs"><Badge>Last trained {new Date(m.trained_at).toLocaleString('en-IN')}</Badge><Badge>Random seed {m.seed} (reproducible)</Badge>
        <Badge>{m.population_users} synthetic users · {m.population_transactions.toLocaleString()} transactions</Badge><Badge tone="accent">{cr.rows.toLocaleString()} real credit-card accounts</Badge></div>

      {/* 1 credit risk */}
      <Card title="1 · Credit-risk model" subtitle={`${cr.model} · ${cr.dataset}`} action={<Beat ok={cr.beats_logistic_regression} />}>
        <div className="grid gap-6 xl:grid-cols-3">
          <div><Versus rows={[['XGBoost', cr.xgboost.roc_auc, true], ['Logistic regression', cr.baseline_logistic_regression.roc_auc], ['Rule: "was late last month"', cr.baseline_rule_delayed_last_month.roc_auc]]} />
            <div className="mt-3"><KV rows={[['ROC-AUC (hold-out 20%)', cr.xgboost.roc_auc], ['ROC-AUC (5-fold cross-validation)', `${cr.cv_roc_auc_mean} ± ${cr.cv_roc_auc_std}`], ['PR-AUC', cr.xgboost.pr_auc],
              [`Precision / recall at ${cr.threshold}`, `${cr.xgboost.precision} / ${cr.xgboost.recall}`], ['Train / test rows', `${cr.train_rows.toLocaleString()} / ${cr.test_rows.toLocaleString()}`], ['Default rate in data', pct(cr.default_rate_pct)]]} /></div></div>
          <div><div className="mb-1 text-xs text-muted">ROC curve (test set)</div><div className="h-56"><ResponsiveContainer><LineChart data={cr.roc_curve} margin={{ left: -14, right: 8 }}><CartesianGrid />
            <XAxis dataKey="fpr" type="number" domain={[0, 1]} tickLine={false} axisLine={false} /><YAxis domain={[0, 1]} tickLine={false} axisLine={false} />
            <Tooltip {...chartTooltip} formatter={(v) => v.toFixed(2)} labelFormatter={(l) => `False-positive rate ${Number(l).toFixed(2)}`} />
            <ReferenceLine segment={[{ x: 0, y: 0 }, { x: 1, y: 1 }]} stroke="#5b6a84" strokeDasharray="4 4" /><Line dataKey="tpr" name="True-positive rate" stroke="#2dd4bf" strokeWidth={2} dot={false} /></LineChart></ResponsiveContainer></div>
            <div className="num mt-2 grid grid-cols-2 gap-1 text-center text-xs">{[['True negatives', cr.confusion_matrix.tn, 'bg-good/10'], ['False positives', cr.confusion_matrix.fp, 'bg-warn/10'], ['False negatives', cr.confusion_matrix.fn, 'bg-bad/10'], ['True positives', cr.confusion_matrix.tp, 'bg-good/10']].map(([k, v, c]) => <div key={k} className={cx('rounded-lg p-2', c)}><div className="text-muted">{k}</div><div className="text-sm font-semibold">{v.toLocaleString()}</div></div>)}</div></div>
          <div><div className="mb-1 text-xs text-muted">What the model relies on</div><div className="h-64"><ResponsiveContainer><BarChart data={cr.feature_importance.slice(0, 8)} layout="vertical" margin={{ left: 60, right: 10 }}>
            <XAxis type="number" hide /><YAxis type="category" dataKey="feature" width={150} tickLine={false} axisLine={false} tick={{ fontSize: 10 }} /><Tooltip {...chartTooltip} /><Bar dataKey="importance" fill="#2dd4bf" radius={[0, 4, 4, 0]} /></BarChart></ResponsiveContainer></div></div>
        </div>
        <div className="mt-3"><Note>{cr.limitations}</Note></div>
      </Card>

      {/* 2 categoriser */}
      <Card title="2 · Transaction categoriser" subtitle={ct.model} className="mt-4" action={<Beat ok={ct.beats_keyword_rule} />}>
        <div className="grid gap-6 xl:grid-cols-3">
          <div><Versus rows={[['Model: statement formats never seen', ct.unseen_formats_test.macro_f1, true], ['Keyword rules: same test', ct.unseen_formats_test.keyword_rule_macro_f1], ['Model: formats seen in training', ct.seen_formats_test.macro_f1]]} />
            <div className="mt-3"><KV rows={[['Macro-F1 on unseen formats', ct.unseen_formats_test.macro_f1], ['Formats held out', ct.held_out_formats.join(', ')], ['Training narrations', ct.training_rows.toLocaleString()], ['Categories', ct.categories.length],
              ['Accuracy on never-seen merchants', pct(ct.never_seen_merchants_test.accuracy * 100), 'warn']]} /></div>
            <div className="mt-2"><Note tone="warn">Honest limit: a brand name the model has never seen ({ct.never_seen_merchants_test.merchants_held_out.slice(0, 3).join(', ')}…) is mostly guessed wrong. Those come back with low confidence and are marked for review; your corrections are saved.</Note></div></div>
          <div><div className="mb-1 text-xs text-muted">Confusion matrix on unseen formats (rows = true, columns = predicted)</div>
            <div className="overflow-x-auto"><table className="num border-separate border-spacing-[2px] text-[9px]"><tbody>
              {cm.matrix.map((row, i) => <tr key={i}><td className="pr-1 text-right text-muted">{cm.labels[i]}</td>{row.map((v, j) => <td key={j} title={`${cm.labels[i]} → ${cm.labels[j]}: ${v}`} className="h-4 w-4 rounded-[3px] text-center"
                style={{ background: v === 0 ? '#141d30' : i === j ? `rgba(45,212,191,${0.25 + 0.75 * v / cmMax})` : 'rgba(248,113,113,0.8)', color: v && i !== j ? '#fff' : 'transparent' }}>{v || ''}</td>)}</tr>)}
            </tbody></table></div></div>
          <div><div className="mb-1 flex items-center gap-2 text-xs text-muted"><FlaskConical size={13} /> Try it: paste statement lines</div>
            <textarea value={texts} onChange={(e) => setTexts(e.target.value)} rows={5} className="w-full rounded-xl border border-line bg-bg p-2 font-mono text-[11px] outline-none focus:border-accent" />
            <Button variant="ghost" className="mt-2" onClick={tryCat}>Categorise</Button>
            {preds && <ul className="mt-2 space-y-1 text-xs">{preds.map((p, i) => <li key={i} className="flex items-center gap-2"><Badge tone={p.needs_review ? 'warn' : 'accent'}>{p.category}</Badge><span className="num text-muted">{pct(p.confidence * 100, 0)}</span>
              <span className="text-faint">rule says: {p.keyword_rule}</span></li>)}</ul>}</div>
        </div>
      </Card>

      {/* 3 anomaly + 4 forecast */}
      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        <Card title="3 · Anomaly detector" subtitle={`${an.model} · ${an.n_estimators} trees · ${an.training_transactions.toLocaleString()} training transactions`} action={<Beat ok={an.beats_rule_on_f1} />}>
          <Versus rows={[['Isolation Forest: F1', an.isolation_forest.f1, true], ['Rule "over 3× your usual": F1', an.baseline_rule_3x_category_median.f1]]} />
          <div className="mt-3"><Table dense rows={[{ n: 'Isolation Forest', ...an.isolation_forest }, { n: 'Rule: over 3× category median', ...an.baseline_rule_3x_category_median }]} columns={[
            { key: 'n', label: 'Method' }, { key: 'precision', label: 'Precision', right: true }, { key: 'recall', label: 'Recall', right: true }, { key: 'f1', label: 'F1', right: true }, { key: 'flagged', label: 'Flagged', right: true }]} /></div>
          <p className="mt-2 text-xs text-muted">Tested on {an.test_users} held-out users ({an.test_transactions.toLocaleString()} transactions) containing {an.planted_anomalies_in_test} planted unusual transactions. The model catches most of them while raising about half as many false alarms as the rule.</p>
          <div className="mt-2"><Note>{an.limitations}</Note></div>
        </Card>
        <Card title="4 · Cash-flow forecaster" subtitle={`${fc.model}`} action={<Beat ok={fc.total_expense.beats_baseline} />}>
          <Versus lowerBetter rows={[['XGBoost: average error (₹)', fc.total_expense.xgboost.mae, true], ['3-month average', fc.total_expense.baseline_3_month_average.mae], ['Same as last month', fc.total_expense.baseline_last_month.mae]]} />
          <div className="mt-3"><KV rows={[['Split', `chronological · test ${fc.split.test_months.join(', ')}`], ['Error as % of spend (MAPE)', `${fc.total_expense.xgboost.mape_pct}% vs ${fc.total_expense.baseline_3_month_average.mape_pct}%`],
            ['Improvement over 3-month average', pct(fc.total_expense.improvement_vs_3m_average_pct), 'good'], ['Category model improvement', pct(fc.category_expense.improvement_vs_3m_average_pct), 'good'],
            ['Train / test rows', `${fc.total_expense.train_rows.toLocaleString()} / ${fc.total_expense.test_rows.toLocaleString()}`]]} /></div>
          <div className="mt-2 h-36"><ResponsiveContainer><BarChart data={fc.total_expense.by_test_month} margin={{ left: -6 }}><CartesianGrid vertical={false} /><XAxis dataKey="month" tickLine={false} axisLine={false} /><YAxis tickLine={false} axisLine={false} width={48} />
            <Tooltip {...chartTooltip} formatter={(v, n) => [inr(v), n]} /><Legend wrapperStyle={{ fontSize: 11 }} /><Bar dataKey="xgboost_mae" name="XGBoost error" fill="#2dd4bf" radius={[3, 3, 0, 0]} /><Bar dataKey="baseline_3m_mae" name="3-month average error" fill="#5b6a84" radius={[3, 3, 0, 0]} /></BarChart></ResponsiveContainer></div>
          <div className="mt-2"><Note>{fc.limitations}</Note></div>
        </Card>
      </div>

      {/* 5 peers */}
      <Card title="5 · Peer groups" subtitle={`${pe.model} on ${pe.users} users · ${pe.features.length} behaviour features · k chosen by silhouette score`} className="mt-4">
        <div className="grid gap-6 xl:grid-cols-3">
          <div><div className="h-44"><ResponsiveContainer><BarChart data={pe.k_scan} margin={{ left: -14 }}><CartesianGrid vertical={false} /><XAxis dataKey="k" tickLine={false} axisLine={false} tickFormatter={(k) => `k=${k}`} /><YAxis tickLine={false} axisLine={false} />
            <Tooltip {...chartTooltip} /><Bar dataKey="silhouette" name="Silhouette" radius={[4, 4, 0, 0]}>{pe.k_scan.map((s) => <Cell key={s.k} fill={s.k === pe.chosen_k ? '#2dd4bf' : '#334155'} />)}</Bar></BarChart></ResponsiveContainer></div>
            <KV rows={[['Chosen k', pe.chosen_k], ['Silhouette', pe.silhouette], ['Davies-Bouldin', pe.davies_bouldin], ['Agreement with hidden generator groups (ARI)', pe.adjusted_rand_vs_generator_archetypes]]} /></div>
          <div className="xl:col-span-2 overflow-x-auto"><table className="w-full text-xs"><thead><tr className="border-b border-line text-left text-faint"><th className="py-2 pr-3 font-medium">Cluster (named from its centre)</th><th className="px-2 text-right font-medium">Size</th>{pe.features.map((f) => <th key={f} className="px-2 text-right font-medium">{f}</th>)}</tr></thead>
            <tbody>{pe.clusters.map((c) => <tr key={c.cluster} className="border-b border-line/60"><td className="py-2 pr-3 font-medium">{c.cluster}</td><td className="num px-2 text-right">{c.size}</td>{pe.features.map((f) => <td key={f} className="num px-2 text-right text-muted">{c.means[f]}%</td>)}</tr>)}</tbody></table>
            <div className="mt-3"><Note>{pe.limitations}</Note></div></div>
        </div>
      </Card>
    </>
  )
}
