"""Financial Intelligence Report - PDF (ReportLab) and CSV exports."""
from __future__ import annotations

import io
import zipfile
from datetime import datetime

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

INK, TEAL, MUTED, LINE, SOFT = colors.HexColor("#0F172A"), colors.HexColor("#0D9488"), colors.HexColor("#64748B"), colors.HexColor("#CBD5E1"), colors.HexColor("#F1F5F9")
PRI = {"high": colors.HexColor("#DC2626"), "medium": colors.HexColor("#D97706"), "low": colors.HexColor("#2563EB")}


def rs(x, dash="-") -> str:
    """Rupee formatting with Indian lakh/crore units ('Rs' because core PDF fonts lack the rupee glyph)."""
    if x is None:
        return dash
    x = float(x)
    sign = "-" if x < 0 else ""
    a = abs(x)
    if a >= 1e7:
        return f"{sign}Rs {a / 1e7:.2f} Cr"
    if a >= 1e5:
        return f"{sign}Rs {a / 1e5:.2f} L"
    return f"{sign}Rs {a:,.0f}"


NA = "Not available"


def pc(x) -> str:
    """Percent, or 'Not available' - never 'None%'."""
    return NA if x is None else f"{x}%"


def nv(x, unit: str = "") -> str:
    return NA if x is None else f"{x}{unit}"


def _t(s) -> str:
    return str(s).replace("₹", "Rs ").replace("×", "x").replace("•", "*").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_pdf(a: dict, briefing_text: str | None = None, metrics: dict | None = None) -> bytes:
    ss = getSampleStyleSheet()
    H1 = ParagraphStyle("H1", parent=ss["Heading1"], fontSize=15, textColor=INK, spaceBefore=10, spaceAfter=6)
    H2 = ParagraphStyle("H2", parent=ss["Heading2"], fontSize=11.5, textColor=TEAL, spaceBefore=8, spaceAfter=4)
    P = ParagraphStyle("P", parent=ss["BodyText"], fontSize=9.2, leading=13, textColor=INK)
    S = ParagraphStyle("S", parent=P, fontSize=8, textColor=MUTED, leading=11)
    C = ParagraphStyle("C", parent=P, fontSize=8.5, leading=11)
    story = []

    def table(rows, widths=None, header=True, zebra=True):
        data = [[Paragraph(_t(c), C) if not isinstance(c, Paragraph) else c for c in r] for r in rows]
        t = Table(data, colWidths=widths, repeatRows=1 if header else 0)
        st = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, -1), 0.3, LINE),
              ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5), ("TOPPADDING", (0, 0), (-1, -1), 3.5),
              ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5)]
        if header:
            st += [("BACKGROUND", (0, 0), (-1, 0), INK), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white)]
            data[0] = [Paragraph(f"<font color='white'><b>{_t(c)}</b></font>", C) for c in rows[0]]
            t = Table(data, colWidths=widths, repeatRows=1)
        if zebra:
            st += [("ROWBACKGROUNDS", (0, 1 if header else 0), (-1, -1), [colors.white, SOFT])]
        t.setStyle(TableStyle(st))
        story.append(t)
        story.append(Spacer(1, 6))

    def kv(pairs, cols=2):
        rows, row = [], []
        for k, v in pairs:
            row += [Paragraph(f"<font color='#64748B'>{_t(k)}</font>", C), Paragraph(f"<b>{_t(v)}</b>", C)]
            if len(row) == cols * 2:
                rows.append(row)
                row = []
        if row:
            rows.append(row + [""] * (cols * 2 - len(row)))
        table(rows, widths=[42 * mm, 45 * mm] * cols, header=False, zebra=False)

    p, cf, nw, liq = a["profile"], a["cash_flow"], a["net_worth"], a["liquidity"]
    cred, debt, inv, fire, ins, hs = a["credit"], a["debt"], a["investments"], a["fire"], a["insurance"], a["health_score"]
    ml = a["ml"]
    comp = a.get("completeness") or {}
    synthetic = "Synthetic" in a.get("data_notice", "")

    # ---------------- cover
    story += [Spacer(1, 30 * mm), Paragraph("<font color='#0D9488'><b>FINORA</b></font>", ParagraphStyle("B", parent=H1, fontSize=30, alignment=TA_CENTER)),
              Paragraph("Financial Intelligence Report", ParagraphStyle("B2", parent=H1, fontSize=16, alignment=TA_CENTER)), Spacer(1, 8 * mm)]
    kv([("Name", p["name"]), ("Profile ID", p["internal_id"]), ("PAN (masked)", p["pan_masked"] or "-"), ("Age", p["age"]),
        ("Occupation", p["occupation"]), ("City", p["city"]), ("Period analysed", f"{cf['period']['from']} to {cf['period']['to']}" if cf.get("period") else "No history yet"),
        ("Generated", datetime.now().strftime("%d %b %Y, %H:%M"))])
    story.append(Spacer(1, 6 * mm))
    fire_ok = fire.get("available", True)
    kv([("Net worth", rs(nw["net_worth"])), ("Financial health score", f"{hs['score']}/100 ({hs['band']})" if hs["score"] is not None else NA),
        ("Savings rate", pc(cf["avg_savings_rate_pct"])), ("Emergency runway", nv(liq["runway_months"], " months")),
        ("FIRE age (projected)", (fire["fire_age"] or "Beyond 75") if fire_ok else NA), ("Open recommendations", len(a["recommendations"]))])
    if comp.get("missing"):
        story.append(Paragraph(f"Data completeness {comp['score_pct']}%. Not yet provided: {_t(', '.join(comp['missing']))}. "
                               "Results that depend on missing data are shown as 'Not available' rather than estimated.", S))
    story.append(Paragraph(_t(a["data_notice"]) + " This report is educational guidance, not a substitute for a licensed financial advisor.", S))
    story.append(PageBreak())

    # ---------------- 1 summary
    story.append(Paragraph("1. Overall financial summary", H1))
    if briefing_text:
        story.append(Paragraph(_t(briefing_text), P))
        story.append(Spacer(1, 4))
    table([["Pillar", "Score (0-100)"]] + [[k, v] for k, v in hs["pillars"].items()]
          + [[k, f"Not assessed - {why}"] for k, why in (hs.get("not_assessed") or {}).items()], widths=[60 * mm, 110 * mm])
    story.append(Paragraph(_t(hs["method"]), S))

    # ---------------- 2 identity
    story.append(Paragraph("2. Financial identity and net worth", H1))
    table([["Asset class", "Value"]] + [[k, rs(v)] for k, v in nw["breakdown"].items()] + [["Total assets", rs(nw["total_assets"])]], widths=[100 * mm, 50 * mm])
    if not nw["breakdown"]:
        story.append(Paragraph("No assets recorded yet.", P))
    if nw["liabilities"]:
        table([["Liability", "Outstanding"]] + [[k, rs(v)] for k, v in nw["liabilities"].items()] + [["Total liabilities", rs(nw["total_liabilities"])]], widths=[100 * mm, 50 * mm])
    al = a["allocation"]
    kv([("Net worth", rs(nw["net_worth"])), ("Debt to assets", pc(nw["debt_to_assets_pct"])),
        ("Equity share of financial assets", pc(al["financial_assets_equity_pct"])), ("Age-based guide", pc(al["suggested_equity_pct_for_age"]))])

    # ---------------- 3 income & expenses
    story.append(Paragraph("3. Income and expenditure", H1))
    for note in (cf.get("reason"), cf.get("income_note"), cf.get("spending_note")):
        if note:
            story.append(Paragraph(_t(note), S))
    def money(x):
        return NA if x is None else rs(x)
    kv([("Average monthly income", money(cf["avg_monthly_income"])), ("Average monthly expenses", money(cf["avg_monthly_expenses"])),
        ("Average monthly savings", money(cf["avg_monthly_savings"])), ("Savings rate", pc(cf["avg_savings_rate_pct"])),
        ("Essentials / income", pc(cf["essential_to_income_pct"])), ("Discretionary / income", pc(cf["discretionary_to_income_pct"])),
        ("EMI / income", pc(cf["emi_to_income_pct"])), ("Months in deficit", nv(cf["months_in_deficit"]))])
    if cf["monthly_series"]:
        table([["Month", "Income", "Expenses", "Savings"]] + [[m["month"], money(m["income"]), money(m["expenses"]), money(m["savings"])] for m in cf["monthly_series"]],
              widths=[35 * mm, 40 * mm, 40 * mm, 40 * mm])
    if cf["category_totals"]:
        table([["Category", "Type", "Monthly average", "Share of spend"]] + [[c["category"], c["type"], rs(c["monthly_avg"]), pc(c["share_of_spend_pct"])] for c in cf["category_totals"][:12]],
              widths=[45 * mm, 35 * mm, 40 * mm, 35 * mm])
    cr = cf.get("cleaning_report")
    if cr:
        story.append(Paragraph(f"Data cleaning: {cr['rows_in']} rows in, {cr['duplicates_removed']} duplicates removed, {cr['refunds']} refunds netted off, "
                               f"{cr['non_expense_rows']} transfers/card payments/investments excluded from spending, {cr['one_time_large_flagged']} one-time large spends flagged.", S))

    # ---------------- 4 anomalies
    story.append(Paragraph("4. Transaction anomaly analysis (Isolation Forest)", H1))
    an = ml.get("anomaly", {})
    if an.get("available") is False or "transactions_scored" not in an:
        story.append(Paragraph("Unusual-spending detection is not active: no anomaly model has passed its acceptance criteria yet "
                               "(the real-data model awaits a blinded human review). Nothing in this report is flagged by a model.", P))
    else:
        story.append(Paragraph(f"{an.get('transactions_scored', 0)} transactions scored; {an.get('flagged_count', 0)} flagged as unusual "
                               f"(total {rs(an.get('flagged_amount_total'))}). {_t(an.get('disclaimer', ''))}", P))
        if an.get("model_note"):
            story.append(Paragraph(_t(an["model_note"]), S))
    if an.get("flagged"):
        table([["Date", "Merchant / category", "Source", "Amount", "x typical", "Severity", "Reason"]] +
              [[f["date"], f"{f['merchant'] or ''} ({f['category']})", f["source"], rs(f["amount"]), f["times_typical"], f["severity"], f["reasons"][0]]
               for f in an["flagged"][:10]], widths=[19 * mm, 30 * mm, 28 * mm, 20 * mm, 14 * mm, 16 * mm, 50 * mm])

    # ---------------- 5 forecast
    story.append(Paragraph("5. Cash-flow forecast (XGBoost)", H1))
    fc = ml.get("forecast", {})
    if fc.get("available"):
        kv([("Forecast month", fc["prediction_month"]), ("Predicted spending", rs(fc["predicted_total_expense"])),
            ("Likely range", f"{rs(fc['range']['low'])} to {rs(fc['range']['high'])}"), ("Last month actual", rs(fc["last_month_actual"])),
            ("Expected income", NA if fc["expected_income"] is None else rs(fc["expected_income"])),
            (f"Projected {fc['projected_status']}" if fc["projected_status"] else "Projected surplus",
             NA if fc["projected_surplus"] is None else rs(abs(fc["projected_surplus"])))])
        table([["Category", "Predicted", "3-month average", "Change", "Suggested budget"]] +
              [[c["category"], rs(c["predicted"]), rs(c["three_month_avg"]), f"{c['change_vs_3m_avg_pct']}%", rs(c["suggested_budget"])] for c in fc["category_predictions"]],
              widths=[38 * mm, 32 * mm, 34 * mm, 24 * mm, 34 * mm])
    else:
        story.append(Paragraph(_t("No approved forecasting model: the model trained on real data so far (one UK account) did not beat "
                                  "a simple 3-month average, so Finora does not forecast." if fc.get("model_status") == "awaiting_approved_model"
                                  else (fc.get("note") or "Not enough history to forecast.")), P))

    # ---------------- 6 credit & debt
    story.append(Paragraph("6. Credit, loans and EMI assessment", H1))
    if cred.get("has_cards"):
        table([["Card", "Limit", "Outstanding", "Utilisation", "Min-only (6m)", "Delays (6m)"]] +
              [[c["card"], rs(c["limit"]), rs(c["outstanding"]), f"{c['utilisation_pct']}% ({c['utilisation_band']})",
                nv(c["months_paid_minimum_only_last6"]), nv(c["months_delayed_last6"])]
               for c in cred["cards"]], widths=[42 * mm, 24 * mm, 26 * mm, 32 * mm, 22 * mm, 20 * mm])
        risk = ml.get("credit_risk", {})
        if risk.get("cards"):
            story.append(Paragraph(f"Credit-risk model: estimated probability of missing next month's payment is <b>{risk['overall_default_probability_pct']}%</b> "
                                   f"({risk['overall_risk_band']}); average across the training population is {risk['population_base_rate_pct']}%. {_t(risk['interpretation'])}", P))
            w = max(risk["cards"], key=lambda c: c["default_probability_pct"])
            table([["Top factors for " + w["card"], "Effect"]] + [[f["factor"], f["effect"]] for f in w["top_factors"]], widths=[100 * mm, 50 * mm])
        elif risk.get("note"):
            story.append(Paragraph(_t(risk["note"]), S))
    else:
        story.append(Paragraph("No credit cards on file.", P))
    if debt["has_debt"] and debt["loans"]:
        table([["Loan", "Balance", "EMI", "Rate", "Months left", "EMI / income"]] +
              [[f"{l['loan_type']} ({l['lender']})", rs(l["balance"]), rs(l["emi"]), f"{l['interest_rate']}%", l["remaining_months"], pc(l["emi_share_of_income_pct"])] for l in debt["loans"]],
              widths=[52 * mm, 26 * mm, 22 * mm, 16 * mm, 22 * mm, 24 * mm])
    kv([("Total EMIs", rs(debt["total_emi"])), ("EMI to income", f"{pc(debt['emi_to_income_pct'])} ({debt['risk_band']})"),
        ("Total debt", rs(debt["total_debt"])), ("Average interest rate", f"{debt['weighted_avg_rate_pct']}%")])

    # ---------------- 7 savings, budget, liquidity
    story.append(Paragraph("7. Savings, budget and liquidity", H1))
    kv([("Liquid savings", rs(liq["emergency_pool"])), ("Emergency fund", nv(liq["emergency_fund_months"], " of 6 months")),
        ("Runway if income stops", nv(liq["runway_months"], " months")), ("Runway on essentials only", nv(liq["runway_months_essentials_only"], " months"))])
    if a["budget"]["scenarios"]:
        table([["Cut discretionary by", "Monthly saving", "Annual saving", "New savings rate"]] +
              [[f"{s['cut_discretionary_pct']}%", rs(s["monthly_saving"]), rs(s["annual_saving"]), pc(s["new_savings_rate_pct"])] for s in a["budget"]["scenarios"]],
              widths=[40 * mm, 38 * mm, 38 * mm, 38 * mm])

    # ---------------- 8 investments
    story.append(Paragraph("8. Investments", H1))
    kv([("Invested", rs(inv["total_invested"])), ("Current value", rs(inv["current_value"])), ("Gain", f"{rs(inv['total_gain'])} ({pc(inv['total_gain_pct'])})"),
        ("Monthly SIPs", rs(inv["sip_monthly_total"]) + (f" ({inv['sip_to_income_pct']}% of income)" if inv["sip_to_income_pct"] is not None else ""))])
    if inv["holdings"]:
        table([["Holding", "Type", "Invested", "Current", "Gain"]] + [[h["name"], h["sector"], rs(h["invested"]), rs(h["current"]), pc(h["gain_pct"])] for h in inv["holdings"][:12]],
              widths=[62 * mm, 30 * mm, 24 * mm, 24 * mm, 18 * mm])
    story.append(Paragraph(f"Prices are stored values as of {inv['prices_as_of']}, not live market data.", S))

    # ---------------- 9 FIRE
    story.append(Paragraph("9. Financial independence (FIRE) forecast", H1))
    fi = fire["inputs"]
    if not fire_ok:
        story.append(Paragraph(_t(fire["reason"]), P))
        kv([("Current corpus", rs(fi["current_corpus"])), ("Monthly investment", rs(fi["monthly_investment"]))])
    else:
        kv([("FIRE number", rs(fire["fire_number"])), ("Current corpus", f"{rs(fi['current_corpus'])} ({fire['progress_pct']}%)"),
        ("Monthly investment", rs(fi["monthly_investment"])), ("Projected FIRE age", fire["fire_age"] or "Beyond 75"),
        ("Lean / Fat FIRE age", f"{fire['lean_fire_age'] or '-'} / {fire['fat_fire_age'] or '-'}"), ("Coast FIRE reached", "Yes" if fire["coast_fire_reached"] else "No"),
        (f"Corpus at target age {fire['retirement_age_target']}", rs(fire["corpus_at_target_age"])), ("Success probability", f"{fire['success_probability_pct']}%"),
        ("Investment needed for target", rs(fire["monthly_investment_needed_for_target"])), ("Assumptions", f"{fi['nominal_return_pct']}% return, {fi['inflation_pct']}% inflation, {fi['withdrawal_rate_pct']}% withdrawal")])
        story.append(Paragraph(_t(fire["corpus_definition"]) + " " + _t(fire["note"]), S))

    # ---------------- 10 protection + peers
    story.append(Paragraph("10. Protection and peer comparison", H1))
    kv([("Term life cover", rs(ins["term_cover"])), ("Guideline", rs(ins["recommended_term_cover"]) if ins["recommended_term_cover"] is not None else NA + " (needs income)"), ("Health cover", rs(ins["health_cover"])), ("Guideline", rs(ins["recommended_health_cover"]))])
    pe = ml.get("peers", {})
    if pe.get("comparison"):
        story.append(Paragraph(f"Closest peer group: <b>{_t(pe['peer_group'])}</b> " + (f"({pe['peer_group_share_pct']}% of US households, about {pe['peer_group_households_millions']} million of {pe['population_households_millions']} million)" if "peer_group_share_pct" in pe else f"({pe.get('peer_group_size')} of {pe.get('population_size')} people)") + ".", P))
        ratios = pe.get("units", "").startswith("ratios")       # SCF comparison values are ratios, not percentages
        u, who = ("", "US households") if ratios else ("%", "people")
        table([["Metric", "You", "Peer median", "All US households" if ratios else "Everyone", "Better than"]] +
              [[c["metric"], f"{c['you']}{u}", f"{c['peer_group_median']}{u}", f"{c['everyone_median']}{u}", f"{c['better_than_pct_of_people']}% of {who}"]
               for c in pe["comparison"]],
              widths=[50 * mm, 22 * mm, 28 * mm, 24 * mm, 36 * mm])
    if pe.get("note"):
        story.append(Paragraph(_t(pe["note"]), S))

    # ---------------- 11 recommendations
    story.append(PageBreak())
    story.append(Paragraph("11. Financial concerns and personalised recommendations", H1))
    if not a["recommendations"]:
        story.append(Paragraph("No recommendations yet. Most rules need income and spending history; see data completeness above.", P))
    for i, r in enumerate(a["recommendations"], 1):
        col = PRI[r["priority"]].hexval()[2:]
        story.append(Paragraph(f"<font color='#{col}'><b>[{r['priority'].upper()}]</b></font> <b>{i}. {_t(r['finding'])}</b>", P))
        story.append(Paragraph(f"<b>Evidence:</b> {_t(r['evidence'])}", C))
        story.append(Paragraph(f"<b>Why it matters:</b> {_t(r['explanation'])}", C))
        story.append(Paragraph(f"<b>Action:</b> {_t(r['action'])}" + (f" <b>Impact:</b> {_t(r['impact_text'])}" if r.get("impact_text") else ""), C))
        story.append(Paragraph(f"Source: {_t(r['source'])}", S))
        story.append(Spacer(1, 5))

    # ---------------- 12 model evaluation
    if metrics:
        story.append(Paragraph("12. Model evaluation", H1))
        rows = [["Model", "Trained on", "Key result", "Baseline"]]
        m = metrics.get("credit_risk")
        if m:
            x = m["test"]["xgboost"]
            rows.append(["Credit risk (XGBoost)", "30,000 real card accounts (Taiwan, 2005)",
                         f"Test ROC-AUC {x['roc_auc']} (5-fold CV {m['cross_validation']['xgboost_roc_auc_mean']})",
                         f"Logistic regression {m['test']['logistic_regression_baseline']['roc_auc']}"])
        m = metrics.get("categoriser")
        if m:
            h = m["held_out_merchants_oklahoma"]
            rows.append(["Merchant categoriser", f"{m['training']['rows']:,} real US card descriptors",
                         f"Macro-F1 {h['macro_f1']} on merchants never seen", f"Keyword rules {h['keyword_rule_macro_f1']}"])
        m = metrics.get("anomaly")
        if m:
            rows.append(["Unusual-spending detector", f"{m['training_transactions']:,} real cardholder transactions",
                         "Accuracy not yet measured (blinded human review pending)", "-"])
        m = metrics.get("forecast")
        if m:
            e = m["evaluation"]
            rows.append(["Spending forecast (experimental)", "One real UK person's account (MoneyVis)",
                         f"MAE GBP {e['xgboost']['mae']:,.0f} over {e['test_months']} months", f"3-month average GBP {e['baseline_moving_average_3m']['mae']:,.0f}"])
        m = metrics.get("peers")
        if m:
            rows.append(["Peer groups (K-Means)", "US households (Federal Reserve SCF 2022)",
                         f"k={m['chosen_k']}, stable across imputations (ARI {m['stability']['cross_implicate_ari_mean']})", "-"])
        table(rows, widths=[42 * mm, 42 * mm, 52 * mm, 38 * mm])
        story.append(Paragraph("Every active model is trained on real data and measured on data it did not see during training. None is "
                               "trained on Indian data: credit risk is a Taiwan 2005 benchmark, merchant categories come from US purchase "
                               "cards, the forecast is trained on one UK person, and peer groups are US households. Models without an "
                               "approved real-data version are not used.", S))

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(18 * mm, 10 * mm, f"Finora - Financial Intelligence Report - {p['name']} - "
                          + ("synthetic demonstration data" if synthetic else "based on data entered or uploaded by the account holder"))
        canvas.drawRightString(192 * mm, 10 * mm, f"Page {doc.page}")
        canvas.restoreState()

    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=18 * mm,
                      title=f"Finora report - {p['name']}", author="Finora").build(story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()


def build_csv_zip(a: dict, transactions: list[dict]) -> bytes:
    """A zip of CSV files: transactions, monthly summary, categories, holdings, flagged, recommendations, forecast."""
    files = {
        "transactions.csv": pd.DataFrame(transactions),
        "monthly_summary.csv": pd.DataFrame(a["cash_flow"]["monthly_series"]),
        "category_totals.csv": pd.DataFrame(a["cash_flow"]["category_totals"]),
        "holdings.csv": pd.DataFrame(a["investments"]["holdings"]),
        "net_worth.csv": pd.DataFrame([{"item": k, "value": v, "kind": "asset"} for k, v in a["net_worth"]["breakdown"].items()] +
                                      [{"item": k, "value": v, "kind": "liability"} for k, v in a["net_worth"]["liabilities"].items()]),
        "flagged_transactions.csv": pd.DataFrame([{**f, "reasons": " | ".join(f["reasons"])} for f in a["ml"].get("anomaly", {}).get("flagged", [])]),
        "recommendations.csv": pd.DataFrame(a["recommendations"]),
        "forecast_categories.csv": pd.DataFrame(a["ml"].get("forecast", {}).get("category_predictions", [])),
        "fire_projection.csv": pd.DataFrame(a["fire"]["projection"]),
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, df in files.items():
            z.writestr(name, df.to_csv(index=False))
    return buf.getvalue()
