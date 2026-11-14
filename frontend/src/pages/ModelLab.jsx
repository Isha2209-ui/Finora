import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Bot, ClipboardCheck, Database, FlaskConical, Info } from 'lucide-react'
import { api } from '../api'
import { Badge, Button, Card, ErrorBox, KV, Loading, Note, PageHeader, chartTooltip } from '../components/ui.jsx'
import { useAsync } from '../store.jsx'

// Model Lab: what each model was trained on, how it was tested, and whether it is in use. Built from /api/models/lab.
const TITLES = {
  credit_risk: 'Credit Risk Analysis', categoriser: 'Transaction Categorisation', anomaly: 'Anomaly Detection Scanner',
  forecast: 'Cash-Flow Forecasting', peers: 'Peer Benchmarking', anomaly_ulb_benchmark: 'ULB fraud research benchmark (not a Finora feature)',
}
const TONE = { verified_real: 'good', suggestion_only: 'warn', not_human_validated: 'warn', experimental: 'warn', awaiting_review: 'warn', trained_not_active: 'neutral',
  awaiting_training: 'bad', benchmark: 'neutral', legacy_synthetic: 'bad' }
const FEATURE = { credit_risk: '/credit', categoriser: '/transactions', anomaly: '/scanner', forecast: '/forecast', peers: '/peers' }
const fmt = (v, d = 3) => (v == null ? '-' : typeof v === 'number' ? Number(v.toFixed(d)).toLocaleString() : String(v))

const Versus = ({ rows, lowerBetter }) => {
  const max = Math.max(...rows.map((r) => r[1] || 0)) || 1
  return (
    <div className="space-y-2">{rows.map(([label, v, main]) => (
      <div key={label}><div className="flex justify-between text-xs"><span className={main ? 'font-medium text-ink' : 'text-muted'}>{label}</span><span className="num">{fmt(v)}</span></div>
        <div className="mt-1 h-2 overflow-hidden rounded-full bg-raised"><div className={main ? 'h-full rounded-full bg-accent' : 'h-full rounded-full bg-faint'} style={{ width: `${((v || 0) / max) * 100}%` }} /></div></div>))}
      <div className="text-[11px] text-faint">{lowerBetter ? 'Lower is better' : 'Higher is better'}</div></div>
  )
}

function Headline({ name, m }) {
  if (!m) return null
  if (name === 'credit_risk') {
    const t = m.test || {}, x = t.xgboost || {}
    return <div className="grid gap-4 md:grid-cols-2">
      <Versus rows={[['XGBoost (test ROC-AUC)', x.roc_auc, true], ['Logistic regression', t.logistic_regression_baseline?.roc_auc], ['Rule: "late last month"', t.rule_baseline_delayed_last_month?.roc_auc]]} />
      <KV rows={[['Split', `${m.split?.train?.toLocaleString()} / ${m.split?.validation?.toLocaleString()} / ${m.split?.test?.toLocaleString()} (train / validation / test)`],
        ['5-fold CV ROC-AUC', `${fmt(m.cross_validation?.xgboost_roc_auc_mean)} ± ${fmt(m.cross_validation?.xgboost_roc_auc_std)}`],
        ['PR-AUC', fmt(x.pr_auc)], [`Precision / recall at ${x.threshold}`, `${fmt(x.precision)} / ${fmt(x.recall)}`], ['F1', fmt(x.f1)]]} /></div>
  }
  if (name === 'categoriser') {
    const h = m.held_out_merchants_oklahoma || {}, d = m.independent_test_dc || {}, mv = m.independent_test_moneyvis_uk_personal || {}
    return <div className="grid gap-4 md:grid-cols-2">
      <Versus rows={[['Model: merchants never seen (macro-F1)', h.macro_f1, true], ['Keyword rules: same test', h.keyword_rule_macro_f1],
        ['Model: DC purchase cards', d.macro_f1], ['Model: UK personal account', mv.macro_f1]]} />
      <KV rows={[['Training descriptors', m.training?.rows?.toLocaleString()], ['Merchant groups', m.training?.merchant_groups?.toLocaleString()],
        ['Held-out merchants: accuracy', fmt(h.accuracy)], ['DC unseen merchants: macro-F1', fmt(d.unseen_merchants_only?.macro_f1)],
        ['Bank-side categories', m.bank_side_categories]]} /></div>
  }
  if (name === 'anomaly') {
    return <KV rows={[['Train / test', `${m.train_period} → ${m.test_period}`], ['Training transactions', m.training_transactions?.toLocaleString()],
      ['Flag rate (train / later year)', `${fmt(m.flag_rate_train * 100, 2)}% / ${fmt(m.flag_rate_test * 100, 2)}%`],
      ['Stability across random seeds (Jaccard)', Object.values(m.flag_stability_jaccard_vs_seeds || {}).map((v) => fmt(v)).join(', ')],
      ['Overlap with the "3× usual" rule', fmt(m.overlap_model_and_rule_test)], ['Accuracy', m.accuracy, 'warn']]} />
  }
  if (name === 'anomaly_ulb_benchmark') {
    const f = m.isolation_forest || {}, r = m.rule_amount_above_day1_p99 || {}
    return <div className="grid gap-4 md:grid-cols-2">
      <Versus rows={[['Isolation Forest PR-AUC', f.pr_auc, true], ['Amount rule PR-AUC', r.pr_auc]]} />
      <KV rows={[['Test (day 2)', `${m.test_day2_rows?.toLocaleString()} transactions, ${m.test_fraud_rows} confirmed frauds`],
        ['Isolation Forest precision / recall', `${fmt(f.precision)} / ${fmt(f.recall)}`], ['False-positive rate', fmt(f.false_positive_rate, 4)],
        ['Rule precision / recall', `${fmt(r.precision)} / ${fmt(r.recall)}`]]} />
        {m.false_alarm_investigation && <p className="mt-2 text-xs text-muted">Why most flags are false alarms: frauds are {fmt(m.false_alarm_investigation.base_rate * 100, 2)}% of transactions, so flagging 1.5% can be at most ~10% precise even with a perfect ranking. Flagging the top 0.1% instead: precision {fmt(m.false_alarm_investigation.by_alert_budget[0].precision * 100, 1)}%, recall {fmt(m.false_alarm_investigation.by_alert_budget[0].recall * 100, 1)}%.</p>}</div>
  }
  if (name === 'forecast') {
    const e = m.evaluation || {}
    return <div className="grid gap-4 md:grid-cols-2">
      <div><Versus lowerBetter rows={[['XGBoost: average error', e.xgboost?.mae, true], ['3-month moving average', e.baseline_moving_average_3m?.mae], ['Same as last month', e.baseline_last_month?.mae]]} />
        <div className="mt-2"><KV rows={[['Test months', e.test_months], ['RMSE (XGBoost / 3-month average)', `${fmt(e.xgboost?.rmse, 0)} / ${fmt(e.baseline_moving_average_3m?.rmse, 0)}`],
          ['Versus 3-month average', `${e.mae_improvement_vs_moving_average_pct > 0 ? '+' : ''}${e.mae_improvement_vs_moving_average_pct}%`, e.beats_moving_average_on_mae ? 'good' : 'bad'], ['Currency', m.currency]]} /></div></div>
      {m.actual_vs_predicted && <div className="h-48"><ResponsiveContainer><LineChart data={m.actual_vs_predicted} margin={{ left: -6, right: 8 }}><CartesianGrid vertical={false} />
        <XAxis dataKey="month" tickLine={false} axisLine={false} minTickGap={30} /><YAxis tickLine={false} axisLine={false} width={44} /><Tooltip {...chartTooltip} /><Legend wrapperStyle={{ fontSize: 11 }} />
        <Line dataKey="actual" name="Actual" stroke="#e2e8f0" dot={false} strokeWidth={1.5} /><Line dataKey="xgboost" name="XGBoost" stroke="#2dd4bf" dot={false} />
        <Line dataKey="moving_average_3m" name="3-month average" stroke="#5b6a84" dot={false} strokeDasharray="4 3" /></LineChart></ResponsiveContainer></div>}
    </div>
  }
  if (name === 'peers') {
    const s = m.stability || {}
    return <div className="grid gap-4 md:grid-cols-2">
      <div><div className="h-36"><ResponsiveContainer><BarChart data={m.k_scan} margin={{ left: -14 }}><CartesianGrid vertical={false} /><XAxis dataKey="k" tickFormatter={(k) => `k=${k}`} tickLine={false} axisLine={false} />
        <YAxis tickLine={false} axisLine={false} /><Tooltip {...chartTooltip} /><Bar dataKey="silhouette_implicate1" name="Silhouette" fill="#2dd4bf" radius={[4, 4, 0, 0]} /></BarChart></ResponsiveContainer></div>
        <KV rows={[['Chosen k', `${m.chosen_k} (${m.chosen_by})`], ['Agreement across the 5 implicates (ARI)', `mean ${fmt(s.cross_implicate_ari_mean)}, min ${fmt(s.cross_implicate_ari_min)}`],
          ['Households in the survey', `${(m.verification?.families ?? m.data?.families)?.toLocaleString()} (${m.data?.records_used?.toLocaleString()} survey records = 5 imputations each)`],
          ['US households represented (weighted)', m.verification ? `${m.verification.stacked_weight_total_millions} million, each counted once` : '-'],
          ['Same group in all 5 imputations', m.verification ? `${m.verification.families_in_one_group_across_all_their_implicates_pct}% of households` : '-']]} /></div>
      <ul className="space-y-2 text-xs">{(m.groups || []).map((g) => <li key={g.id} className="rounded-lg border border-line p-2"><div className="flex justify-between font-medium"><span>{g.name}</span><span className="num text-muted">{g.weighted_share_pct}% of US households</span></div>
        <div className="mt-1 text-muted">Median: {fmt(g.median.liquid_months, 1)} months of liquid savings · debt {fmt(g.median.debt_to_income, 2)}× income · net worth {fmt(g.median.networth_to_income, 1)}× income</div></li>)}</ul></div>
  }
  return null
}

function Provenance({ p }) {
  if (!p) return null
  const env = p.environment || {}
  return (
    <details className="mt-3 rounded-xl border border-line p-3 text-xs">
      <summary className="cursor-pointer select-none font-medium text-muted">Datasets, training run and reproducibility</summary>
      <div className="mt-3 space-y-3">
        {(p.datasets || []).map((d) => (
          <div key={d.key} className="rounded-lg bg-raised p-2">
            <div className="flex flex-wrap items-center gap-2 font-medium"><Database size={12} /> {d.name} <Badge>{d.role}</Badge><Badge tone="good">{d.observations || 'real'} observations</Badge></div>
            <div className="mt-1 text-muted">{[d.publisher, d.geography, d.collection_period, d.records && `${Number(d.records).toLocaleString()} records`, d.licence && `licence: ${d.licence}`].filter(Boolean).join(' · ')}</div>
            {d.source_url && <div className="mt-1 break-all text-faint">{d.source_url}</div>}
            {(d.files || []).length > 0 && <div className="mt-1 text-faint">{d.files.length} file(s){d.files[0]?.sha256 ? ` · first SHA-256 ${d.files[0].sha256.slice(0, 16)}…` : ''}</div>}
            {d.known_biases && <div className="mt-1 text-muted">Known biases: {d.known_biases}</div>}
          </div>))}
        <KV rows={[['Version', p.version], ['Trained', p.training_finished && new Date(p.training_finished).toLocaleString('en-IN')],
          ['Time / peak memory', `${p.training_seconds}s / ${p.peak_memory_mb} MB`], ['Machine', [env.machine, env.chip, env.memory_gb && `${env.memory_gb} GB`].filter(Boolean).join(' · ')],
          ['Where', env.trained_locally ? 'Trained locally; no remote services' : '-'], ['Libraries', Object.entries(env.libraries || {}).map(([k, v]) => `${k} ${v}`).join(', ')],
          ['Artifact SHA-256', p.artifact?.sha256], ['Reproduce', p.reproducible || p.command]]} />
        {p.methodology && <p className="text-muted">{p.methodology}</p>}
      </div>
    </details>
  )
}

export default function ModelLab() {
  const { data, loading, error, reload } = useAsync(() => api.modelLab(), [])
  const [texts, setTexts] = useState('STARBUCKS STORE 01234\nSHELL OIL 57444\nUPI/DR/402918376152/SWIGGY/YESB/swiggy@ybl/Payment\nNACH/DR/BAJAJ FINANCE EMI/88213344')
  const [preds, setPreds] = useState(null)
  if (loading && !data) return <Loading full />
  if (error) return <ErrorBox message={error} onRetry={reload} />
  const tryCat = async () => setPreds(await api.categorise(texts.split('\n').map((s) => s.trim()).filter(Boolean)))
  const ai = data.ai_cfo
  return (
    <>
      <PageHeader title="Model Lab" subtitle="Every model, the real data it learned from, how it was tested, and whether Finora uses it. Figures are measured on data the model did not see during training." />
      {data.model_set === 'legacy-synthetic' && <div className="mb-4"><Note tone="warn">Development rollback is on: the legacy synthetic-trained models are loaded. Their results are not real-data results.</Note></div>}
      <div className="mb-4 flex flex-wrap gap-2 text-xs">{data.models.map((m) => <Badge key={m.name} tone={TONE[m.status]}>{TITLES[m.name]}: {m.status_text}</Badge>)}</div>

      <div className="space-y-4">
        {data.models.map((m) => (
          <Card key={m.name} title={TITLES[m.name]} subtitle={m.metrics?.task} action={<div className="flex flex-wrap items-center gap-2">{FEATURE[m.name] && <Link to={FEATURE[m.name]}><Button variant="ghost">Open feature</Button></Link>}<Badge tone={TONE[m.status]}>{m.status_text}</Badge></div>}>
            {m.label && <div className="mb-3"><Note tone={m.status === 'verified_real' ? 'info' : 'warn'}>{m.label}</Note></div>}
            {m.deployment_policy && <div className="mb-3"><Note tone="warn">{m.deployment_policy}</Note></div>}
            {!m.provenance && <p className="text-sm text-muted">No real-data version yet. Finora does not use a synthetic model in its place; features that need it say so.</p>}
            <Headline name={m.name} m={m.metrics} />
            {m.acceptance && m.name !== 'anomaly_ulb_benchmark' && <div className="mt-3 rounded-xl border border-line p-3 text-xs">
              <div className="mb-1 font-medium text-muted">Acceptance criteria (set before activation) · {m.acceptance.passed ? <span className="text-good">all passed</span> : <span className="text-bad">not met</span>}</div>
              <ul className="space-y-0.5">{m.acceptance.checks.map((c) => <li key={c.criterion} className="flex gap-2"><span className={c.passed ? 'text-good' : 'text-bad'}>{c.passed ? '✓' : '✗'}</span><span className="text-muted">{c.criterion}</span><span className="num ml-auto text-faint">{String(c.value)}</span></li>)}</ul></div>}
            {m.name === 'anomaly' && m.provenance && <div className="mt-3 flex flex-wrap items-center gap-3 text-xs text-muted"><ClipboardCheck size={14} />
              Blinded human review: {m.metrics?.human_review?.items} transactions, sampled in 3 strata with known selection probabilities. Reviewers never see the model's output.
              <Link to="/models/review"><Button variant="ghost">Open the review</Button></Link></div>}
            {m.name === 'categoriser' && m.provenance && <div className="mt-4 grid gap-3 md:grid-cols-2"><div>
              <div className="mb-1 flex items-center gap-2 text-xs text-muted"><FlaskConical size={13} /> Try it: one line per transaction</div>
              <textarea value={texts} onChange={(e) => setTexts(e.target.value)} rows={4} className="w-full rounded-xl border border-line bg-bg p-2 font-mono text-[11px] outline-none focus:border-accent" />
              <Button variant="ghost" className="mt-2" onClick={tryCat}>Categorise</Button></div>
              {preds && <ul className="space-y-1 self-end text-xs">{preds.map((p, i) => <li key={i} className="flex items-center gap-2"><Badge tone={p.source === 'rule' ? 'neutral' : p.needs_review ? 'warn' : 'accent'}>{p.category || 'not set'}</Badge>
                <span className="text-faint">{p.source === 'rule' ? 'bank rule' : p.source === 'model' ? `model ${Math.round((p.confidence || 0) * 100)}%` : 'no model'}</span><span className="truncate text-muted">{p.text}</span></li>)}</ul>}</div>}
            {(m.provenance?.limitations || m.metrics?.limitations) && <div className="mt-3 flex gap-2 text-xs text-muted"><Info size={14} className="mt-0.5 shrink-0" />{m.provenance?.limitations || m.metrics?.limitations}</div>}
            <Provenance p={m.provenance} />
            {m.activated_at && <div className="mt-2 text-[11px] text-faint">Active since {new Date(m.activated_at).toLocaleString('en-IN')} · {m.activation_reason}</div>}
          </Card>))}

        <Card title="AI CFO" subtitle={ai.family} action={<Badge>Pretrained, not trained by Finora</Badge>}>
          <KV rows={[['Installed model', `${ai.installed_tag} (digest ${ai.installed_digest}, ${ai.installed_size})`], ['Configured model', ai.configured_model, ai.discrepancy ? 'warn' : undefined]]} />
          {ai.discrepancy && <div className="mt-2"><Note tone="warn">{ai.discrepancy}</Note></div>}
          <div className="mt-2 flex gap-2 text-xs text-muted"><Bot size={14} className="mt-0.5 shrink-0" />{ai.note}</div>
        </Card>
      </div>
    </>
  )
}
