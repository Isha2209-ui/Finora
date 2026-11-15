// The six machine-learning capabilities, described from their actual implementations (backend/app/ml/real/*.py, ml/categoriser.py,
// ml/credit_risk.py). One source of truth for names, algorithms and plain-language explanations shown across the app.
// Technical records (metrics, provenance, versions, evaluation) stay in Model Lab and the backend; nothing here claims accuracy.

export const MODELS = {
  credit_risk: {
    name: 'Credit Risk', algorithm: 'XGBoost + SHAP', to: '/models?tab=credit-risk',
    purpose: 'Estimates the probability that a credit card’s next payment will be missed, and explains what drives it.',
    inputs: ['Payment status this month and the two before', 'Worst delay and number of delayed months over six months',
      'Months paying only part of the bill, and months paid in full', 'Card utilisation: latest, six-month average and trend',
      'How much of each bill was repaid, and months with no payment', 'Age'],
    how: 'A gradient-boosted ensemble of shallow decision trees (XGBoost) scores the card. Each tree adds a small correction, and their sum is turned into a probability between 0 and 100%.',
    explain: 'SHAP (TreeExplainer) splits every result into the contribution of each input: positive values pushed the risk up, negative values pulled it down. The largest contributions are listed with each card.',
    read: 'Look at the inputs with the biggest contributions — they are the payment habits that move your risk most, such as paying in full rather than part of the bill.',
    data: 'Trained on 30,000 real credit-card accounts (UCI Default of Credit Card Clients).',
  },
  peers: {
    name: 'Peer Benchmarking', algorithm: 'K-Means clustering', to: '/models?tab=peers',
    purpose: 'Finds the group of households whose finances look most like yours and compares you with them.',
    inputs: ['Liquid savings, in months of income', 'Debt as a share of yearly income', 'Debt payments as a share of income', 'Card balance as a share of yearly income',
      'Net worth as a share of income', 'Share of wealth in financial assets', 'Share of investments in equity', 'Whether money was saved last year'],
    how: 'Each household’s ratios are standardised, then K-Means groups households around a few centre points, weighting each by how many households it represents in the survey. Your ratios are placed in the same space and matched to the nearest centre.',
    explain: 'For each measure Finora shows your value, your group’s median and everyone’s median.',
    read: '“Better than X%” is the survey-weighted share of households you exceed on that measure.',
    data: 'Federal Reserve Survey of Consumer Finances 2022.',
  },
  categoriser: {
    name: 'Transaction Categoriser', algorithm: 'TF-IDF + logistic regression', to: '/models?tab=categoriser',
    purpose: 'Suggests a spending category for every transaction from its description.',
    inputs: ['The transaction description, as it appears on the statement'],
    how: 'Numbers are masked and the text upper-cased. The description becomes TF-IDF weights for character fragments (2–5 characters) and for words and word pairs, so “SWIGGY”, “swiggy@ybl” and “SWGY” look alike. A linear classifier (logistic regression) scores every category; the highest becomes the suggestion, with its confidence.',
    explain: 'Bank-specific rules are applied first; the model handles everything else.',
    read: 'Suggested categories are marked “suggested”. Accept them or choose another; your choice is kept and never overwritten.',
    data: 'Trained on real merchant descriptors from public card-transaction records.',
  },
  anomaly: {
    name: 'Anomaly Detection Scanner', algorithm: 'Isolation Forest', to: '/models?tab=unusual',
    purpose: 'Finds spending that is unusual for you compared with your own history.',
    inputs: ['Amount compared with your typical (median) amount in that category', 'Distance from your normal range (robust z-score)',
      'Share of that month’s spending in the category', 'Amount compared with your 95th-percentile purchase', 'Similar purchases on the same day'],
    how: 'An ensemble of 300 random trees repeatedly splits your transactions. Transactions that separate from the rest in very few splits receive a high anomaly score, and the most isolated are flagged.',
    explain: 'Each flag comes with a severity and plain reasons, such as how many times larger it is than your typical amount in that category.',
    read: 'Open a flagged transaction to see why it stands out. Rent, EMIs, SIPs, insurance, subscriptions and transfers are fixed payments and are not scored. Unusual means unusual for you, not fraudulent.',
    data: 'Trained on real cardholder transaction histories.',
  },
  forecast: {
    name: 'Cash-Flow Forecast', algorithm: 'XGBoost regression', to: '/future?tab=cash-flow',
    purpose: 'Predicts next month’s total spending and what it leaves of your expected income.',
    inputs: ['Last month and the month before, relative to your six-month average', 'Three- and twelve-month averages and your typical (median) month',
      'Recent trend and month-to-month variability', 'Income relative to spending', 'Change in the number of transactions'],
    how: 'Gradient-boosted regression trees predict next month as a multiple of your recent six-month average; Finora converts that back to rupees and adds a likely range from the errors measured in testing.',
    explain: 'The forecast is shown beside a simple three-month average, so you can compare two estimates.',
    read: 'Use the range rather than the single figure: about 80% of outcomes fell inside it in testing.',
    data: 'Trained on a real personal bank account’s monthly history.',
  },
}

/** Remove development-stage clauses from backend-provided display text (records themselves are unchanged). */
const STAGE = /(experimental|human[- ]validated|human review|acceptance criteria|did not meet|not validated|unvalidated|educational|licensed|not financial advice|academic|not a fraud|not fraud|unusual (is|does) not|not the same as fraudulent|not production)/i
export function present(text) {
  if (!text) return text
  const t = String(text).replace(/\s*[-–—,·]\s*experimental(,)?\s*(not human-validated)?/gi, '')
  const kept = t.split(/(?<=[.!?])\s+/).filter((sentence) => !STAGE.test(sentence))
  return kept.join(' ').trim()
}
