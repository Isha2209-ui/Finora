"""Income-tax comparison: old vs new regime, FY 2026-27 (AY 2027-28), resident individual below 60.

Rules (Budget 2026 kept the slabs unchanged; verified Nov 2026):
  New regime : 0-4L nil, 4-8L 5%, 8-12L 10%, 12-16L 15%, 16-20L 20%, 20-24L 25%, >24L 30%
               standard deduction Rs 75,000 (salaried); Sec 87A rebate up to Rs 60,000 when
               taxable income <= Rs 12L, with marginal relief just above Rs 12L.
  Old regime : 0-2.5L nil, 2.5-5L 5%, 5-10L 20%, >10L 30%
               standard deduction Rs 50,000 (salaried); Sec 87A rebate up to Rs 12,500 when
               taxable income <= Rs 5L; deductions such as 80C (max 1.5L), 80D, 24(b) (max 2L), HRA.
  Both       : 4% health & education cess. Surcharge (income above Rs 50L) is NOT modelled.
Educational estimate only - not tax filing advice.
"""
from __future__ import annotations

FY = "2026-27"
NEW_SLABS = [(400000, 0.0), (800000, 0.05), (1200000, 0.10), (1600000, 0.15), (2000000, 0.20), (2400000, 0.25), (float("inf"), 0.30)]
OLD_SLABS = [(250000, 0.0), (500000, 0.05), (1000000, 0.20), (float("inf"), 0.30)]
CESS = 0.04
LIMIT_80C, LIMIT_24B, LIMIT_80D_SELF = 150000, 200000, 25000


def slab_tax(taxable: float, slabs) -> float:
    tax, lower = 0.0, 0.0
    for upper, rate in slabs:
        if taxable > lower:
            tax += (min(taxable, upper) - lower) * rate
        lower = upper
    return tax


def new_regime(gross: float, salaried: bool = True) -> dict:
    std = 75000 if salaried else 0
    taxable = max(0.0, gross - std)
    tax = slab_tax(taxable, NEW_SLABS)
    rebate = 0.0
    if taxable <= 1200000:
        rebate = min(tax, 60000)
    else:  # marginal relief: tax cannot exceed the income above Rs 12 lakh
        rebate = max(0.0, tax - (taxable - 1200000))
    tax_after = tax - rebate
    cess = tax_after * CESS
    return {"regime": "new", "standard_deduction": std, "deductions": 0.0, "taxable_income": round(taxable),
            "tax_before_rebate": round(tax), "rebate_or_relief": round(rebate), "cess": round(cess),
            "total_tax": round(tax_after + cess)}


def old_regime(gross: float, salaried: bool = True, sec_80c: float = 0, sec_80d: float = 0,
               home_loan_interest: float = 0, hra_exemption: float = 0, other: float = 0) -> dict:
    std = 50000 if salaried else 0
    d = {"80C": min(sec_80c, LIMIT_80C), "80D": min(sec_80d, LIMIT_80D_SELF),
         "24(b) home loan interest": min(home_loan_interest, LIMIT_24B), "HRA exemption": hra_exemption, "Other": other}
    total_d = sum(d.values())
    taxable = max(0.0, gross - std - total_d)
    tax = slab_tax(taxable, OLD_SLABS)
    rebate = min(tax, 12500) if taxable <= 500000 else 0.0
    tax_after = tax - rebate
    cess = tax_after * CESS
    return {"regime": "old", "standard_deduction": std, "deductions": round(total_d),
            "deduction_breakup": {k: round(v) for k, v in d.items() if v}, "taxable_income": round(taxable),
            "tax_before_rebate": round(tax), "rebate_or_relief": round(rebate), "cess": round(cess),
            "total_tax": round(tax_after + cess)}


def hra_exemption(basic_annual: float, hra_received: float, rent_paid_annual: float, metro: bool) -> float:
    if rent_paid_annual <= 0 or hra_received <= 0:
        return 0.0
    return max(0.0, min(hra_received, rent_paid_annual - 0.10 * basic_annual, (0.5 if metro else 0.4) * basic_annual))


def compare(gross: float, salaried: bool = True, **old_kwargs) -> dict:
    n, o = new_regime(gross, salaried), old_regime(gross, salaried, **old_kwargs)
    better = "new" if n["total_tax"] <= o["total_tax"] else "old"
    # deductions needed for the old regime to break even
    lo, hi = 0.0, gross
    for _ in range(40):
        mid = (lo + hi) / 2
        if old_regime(gross, salaried, other=mid)["total_tax"] > n["total_tax"]:
            lo = mid
        else:
            hi = mid
    return {"financial_year": FY, "gross_income": round(gross), "new": n, "old": o, "better_regime": better,
            "saving_with_better": abs(n["total_tax"] - o["total_tax"]),
            "old_regime_breakeven_deductions": round(hi),
            "assumptions": ["Resident individual below 60", "No surcharge (applies above Rs 50 lakh)",
                            "Educational estimate, not tax-filing advice"]}
