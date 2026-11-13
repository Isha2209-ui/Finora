"""Unit tests: every core formula is checked against hand-worked or textbook values."""
import pytest

from app.services import decision as D
from app.services import fire as F
from app.services import pan as P
from app.services import tax as T
from app.services.calculations import pct, simulate_payoff


def test_emi_textbook_values():
    assert D.emi(1_000_000, 9, 60) == pytest.approx(20758.36, abs=0.01)     # standard EMI table
    assert D.emi(5_000_000, 8.5, 240) == pytest.approx(43391.16, abs=0.01)
    assert D.emi(120_000, 0, 12) == 10_000                                  # zero-interest loan
    assert D.emi(0, 10, 12) == 0


def test_future_value_matches_closed_form():
    # Rs 10,000 a month at 1% a month for 120 months = 10000 * ((1.01^120 - 1) / 0.01)
    assert F.future_value(0, 10_000, 1.01 ** 12 - 1, 10) == pytest.approx(2_300_386.89, rel=1e-6)
    assert F.future_value(100_000, 0, 0.10, 5) == pytest.approx(161_051.0, rel=1e-6)
    # step-up path equals the plain path when step-up is zero
    assert F.future_value(50_000, 5_000, 0.08, 7, 0.0) == pytest.approx(F.future_value(50_000, 5_000, 0.08, 7, 1e-12), rel=1e-6)


def test_real_return():
    assert F.real_rate(0.11, 0.06) == pytest.approx(0.0471698, abs=1e-6)


def test_fire_number_and_ordering():
    r = F.project(2_000_000, 30_000, 30, 600_000, retirement_age_target=50)
    assert r["fire_number"] == round(600_000 / 0.033)
    assert r["lean_fire_number"] < r["fire_number"] < r["fat_fire_number"]
    assert r["lean_fire_age"] <= r["fire_age"] <= r["fat_fire_age"]
    assert 0 <= r["success_probability_pct"] <= 100


def test_fire_more_investment_is_never_later():
    a = F.project(1_000_000, 20_000, 30, 600_000, retirement_age_target=55)
    b = F.project(1_000_000, 40_000, 30, 600_000, retirement_age_target=55)
    assert b["fire_age"] <= a["fire_age"]
    assert b["success_probability_pct"] >= a["success_probability_pct"]


def test_fire_is_reproducible():
    assert F.project(1e6, 2e4, 30, 6e5, retirement_age_target=55) == F.project(1e6, 2e4, 30, 6e5, retirement_age_target=55)


def test_new_regime_fy2026_27():
    assert T.new_regime(1_275_000)["total_tax"] == 0                       # 12L taxable after 75k std deduction -> full rebate
    # 15L taxable: 20k + 40k + 45k = 105,000 + 4% cess
    assert T.new_regime(1_575_000)["total_tax"] == 109_200
    # 26L taxable: 20+40+60+80+100 = 300k + 30% of 2L = 360k; + cess
    assert T.new_regime(2_675_000)["total_tax"] == round(360_000 * 1.04)
    # marginal relief just above 12L: tax cannot exceed the extra income
    assert T.new_regime(1_285_000)["total_tax"] == round(10_000 * 1.04)


def test_old_regime_fy2026_27():
    # 10L gross - 50k std - 1.5L 80C = 8L taxable: 12,500 + 60,000 = 72,500 + cess
    assert T.old_regime(1_000_000, sec_80c=150_000)["total_tax"] == 75_400
    assert T.old_regime(550_000)["total_tax"] == 0                         # 5L taxable -> 87A rebate
    assert T.old_regime(1_000_000, sec_80c=500_000)["deductions"] == 150_000  # 80C capped


def test_tax_compare_picks_cheaper():
    c = T.compare(1_500_000, True, sec_80c=150_000)
    assert c["better_regime"] == ("new" if c["new"]["total_tax"] <= c["old"]["total_tax"] else "old")
    assert c["saving_with_better"] == abs(c["new"]["total_tax"] - c["old"]["total_tax"])


def test_pct_guards_zero_division():
    assert pct(5, 0) is None and pct(None, 10) is None and pct(1, 4) == 25.0


def test_payoff_avalanche_never_costs_more_than_snowball():
    debts = [{"name": "card", "balance": 100_000, "rate": 42, "payment": 5_000},
             {"name": "small", "balance": 20_000, "rate": 10, "payment": 2_000},
             {"name": "car", "balance": 400_000, "rate": 9, "payment": 10_000}]
    av, sb = simulate_payoff(debts, 5_000, "avalanche"), simulate_payoff(debts, 5_000, "snowball")
    assert av["total_interest"] <= sb["total_interest"]
    assert av["months_to_debt_free"] < 600
    assert simulate_payoff(debts, 20_000, "avalanche")["months_to_debt_free"] < av["months_to_debt_free"]


def test_pan_validation_hash_mask():
    assert P.is_valid("abcde1234f") and not P.is_valid("ABCD1234F") and not P.is_valid("12345ABCDE")
    assert P.mask("ABCDE1234F") == "ABCDE****F"
    assert P.hash_pan("abcde1234f") == P.hash_pan(" ABCDE1234F ") and len(P.hash_pan("ABCDE1234F")) == 64
    assert "ABCDE1234F" not in P.hash_pan("ABCDE1234F")
