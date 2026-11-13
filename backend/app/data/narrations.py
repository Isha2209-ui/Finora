"""Realistic Indian bank / card statement narrations.

Each bank formats its statement text differently. These templates reproduce the
*shape* of real narrations (UPI, POS, NACH, NEFT, ATM ...) so that:
  * demo statements look real, and
  * the Transaction Categoriser can be trained on some formats and tested on
    formats it has never seen.
All merchant names are generic Indian brands/descriptions; UPI handles and
reference numbers are random.
"""
from __future__ import annotations

import random

# category -> merchants (display name, short code used in narrations)
MERCHANTS: dict[str, list[tuple[str, str]]] = {
    "Dining": [("Swiggy", "SWIGGY"), ("Zomato", "ZOMATO"), ("Starbucks", "STARBUCKS"), ("Haldiram's", "HALDIRAMS"),
               ("Domino's Pizza", "DOMINOS"), ("McDonald's", "MCDONALDS"), ("Barbeque Nation", "BARBEQUENATION"),
               ("Chaayos", "CHAAYOS"), ("Third Wave Coffee", "THIRDWAVECOFFEE"), ("KFC", "KFC"),
               ("Local Dhaba", "SHARMA DHABA"), ("EatSure", "EATSURE")],
    "Groceries": [("BigBasket", "BIGBASKET"), ("Blinkit", "BLINKIT"), ("Zepto", "ZEPTO"), ("DMart", "DMART"),
                  ("Reliance Fresh", "RELIANCEFRESH"), ("More Supermarket", "MORE RETAIL"), ("Swiggy Instamart", "INSTAMART"),
                  ("Local Kirana", "GUPTA KIRANA STORE"), ("Nature's Basket", "NATURESBASKET")],
    "Shopping": [("Amazon", "AMAZON"), ("Flipkart", "FLIPKART"), ("Myntra", "MYNTRA"), ("Ajio", "AJIO"),
                 ("Nykaa", "NYKAA"), ("Croma", "CROMA"), ("Reliance Digital", "RELIANCEDIGITAL"), ("Decathlon", "DECATHLON"),
                 ("H&M", "HM HENNES"), ("Lifestyle", "LIFESTYLE STORES"), ("Tata CLiQ", "TATACLIQ"), ("IKEA", "IKEA INDIA")],
    "Travel": [("Uber", "UBER"), ("Ola", "OLACABS"), ("Rapido", "RAPIDO"), ("IRCTC", "IRCTC"), ("MakeMyTrip", "MAKEMYTRIP"),
               ("IndiGo", "INDIGO"), ("Air India", "AIRINDIA"), ("Delhi Metro", "DMRC"), ("redBus", "REDBUS"),
               ("Goibibo", "GOIBIBO"), ("FASTag", "FASTAG")],
    "Fuel": [("Indian Oil", "IOCL"), ("HP Petrol Pump", "HPCL"), ("Bharat Petroleum", "BPCL"), ("Shell", "SHELL INDIA")],
    "Entertainment": [("BookMyShow", "BOOKMYSHOW"), ("PVR INOX", "PVRINOX"), ("Steam", "STEAMGAMES"),
                      ("District by Zomato", "DISTRICT"), ("Smaaash", "SMAAASH"), ("Paytm Insider", "INSIDER")],
    "Subscriptions": [("Netflix", "NETFLIX"), ("Spotify", "SPOTIFY"), ("Amazon Prime", "AMAZONPRIME"),
                      ("JioCinema", "JIOCINEMA"), ("YouTube Premium", "YOUTUBEPREMIUM"), ("Cult.fit", "CULTFIT"),
                      ("Google One", "GOOGLE ONE"), ("Disney+ Hotstar", "HOTSTAR")],
    "Utilities": [("Electricity Bill", "BESCOM"), ("Electricity Bill", "TATA POWER"), ("Electricity Bill", "JVVNL"),
                  ("Airtel", "AIRTEL"), ("Jio", "JIO"), ("ACT Fibernet", "ACTFIBERNET"), ("Water Bill", "WATER BOARD"),
                  ("Gas Cylinder", "INDANE GAS"), ("Piped Gas", "IGL"), ("Vi", "VODAFONEIDEA")],
    "Health": [("Apollo Pharmacy", "APOLLOPHARMACY"), ("PharmEasy", "PHARMEASY"), ("1mg", "TATA1MG"),
               ("Practo", "PRACTO"), ("Max Hospital", "MAXHEALTHCARE"), ("Dr Lal PathLabs", "LALPATHLABS"),
               ("Netmeds", "NETMEDS")],
    "Education": [("Coursera", "COURSERA"), ("Udemy", "UDEMY"), ("Unacademy", "UNACADEMY"), ("Amazon Books", "AMAZON BOOKS"),
                  ("School Fees", "DPS SCHOOL FEES")],
    "Insurance": [("LIC Premium", "LIC OF INDIA"), ("HDFC Ergo", "HDFCERGO"), ("Star Health", "STARHEALTH"),
                  ("ICICI Prudential Life", "ICICIPRULIFE"), ("Niva Bupa", "NIVABUPA")],
    "Rent": [("House Rent", "RENT")],
    "EMI": [("Loan EMI", "LOAN EMI")],
    "Investment": [("SIP", "SIP")],
    "Card Payment": [("Credit Card Bill", "CC PAYMENT")],
    "Transfer": [("Own Account Transfer", "SELF TRANSFER")],
    "Cash": [("ATM Withdrawal", "ATM")],
}

CITIES = ["BANGALORE", "MUMBAI", "DELHI", "JAIPUR", "PUNE", "GURGAON", "NOIDA", "HYDERABAD", "CHENNAI"]
PSP = ["ybl", "okaxis", "okicici", "paytm", "axl", "ibl", "oksbi", "icici", "hdfcbank"]
IFSC = ["HDFC0000001", "ICIC0000104", "SBIN0001234", "UTIB0000553", "KKBK0000958", "YESB0000001"]

# ---------------------------------------------------------------- formats
# Each format: f(code, merchant, rng) -> narration string


def _ref(rng, n=12):
    return "".join(rng.choice("0123456789") for _ in range(n))


def _handle(code, rng):
    return f"{code.lower().replace(' ', '')[:12]}@{rng.choice(PSP)}"


def fmt_hdfc_upi(code, m, rng):
    return f"UPI-{code}-{_handle(code, rng)}-{rng.choice(IFSC)}-{_ref(rng)}-UPI"


def fmt_sbi_upi(code, m, rng):
    return f"UPI/DR/{_ref(rng)}/{code[:10]}/{rng.choice(['YESB', 'ICIC', 'AXIS', 'HDFC'])}/{_handle(code, rng)}/Payment"


def fmt_icici_upi(code, m, rng):
    return f"UPI/{_ref(rng)}/{m}/{_handle(code, rng)}/{rng.choice(['ICICI Bank', 'Yes Bank', 'Axis Bank'])}"


def fmt_axis_upi(code, m, rng):
    return f"UPI/P2M/{_ref(rng)}/{code} {rng.choice(['LIMITED', 'PVT LTD', 'INDIA', ''])}".strip()


def fmt_kotak_upi(code, m, rng):
    return f"UPI/{code.title()}/{_ref(rng)}/{rng.choice(['Pay', 'Payment from Ph', 'Sent using Paytm'])}"


def fmt_card_pos(code, m, rng):
    return f"POS {rng.randint(4000, 5599)}XXXXXXXX{rng.randint(1000, 9999)} {code} {rng.choice(CITIES)}"


def fmt_card_online(code, m, rng):
    return f"{code} {rng.choice(['INDIA PVT LTD', 'ONLINE', 'RETAIL', 'TECHNOLOGIES'])} {rng.choice(CITIES)} IN"


def fmt_card_ecom(code, m, rng):
    return f"PAYU*{code} {rng.choice(['BANGALORE', 'GURGAON', 'MUMBAI'])}"


def fmt_razorpay(code, m, rng):
    return f"RAZ*{code.title().replace(' ', '')} {rng.choice(CITIES)} IND"


def fmt_billdesk(code, m, rng):
    return f"BIL/BPAY/{_ref(rng, 9)}/{code}/{rng.choice(['ONLINE', 'AUTOPAY'])}"


def fmt_imps(code, m, rng):
    return f"IMPS/P2A/{_ref(rng)}/{code}/{rng.choice(IFSC)[:4]}"


def fmt_neft(code, m, rng):
    return f"NEFT DR-{rng.choice(IFSC)}-{code}-NETBANK, MUM-N{_ref(rng, 9)}"


def fmt_paytm_wallet(code, m, rng):
    return f"PAYTM*{code.title()} {rng.choice(['Wallet', 'UPI'])} {_ref(rng, 8)}"


def fmt_gpay(code, m, rng):
    return f"Paid to {m} via Google Pay UPI Ref {_ref(rng)}"


def fmt_phonepe(code, m, rng):
    return f"PhonePe UPI {m} {_ref(rng, 10)}"


FORMATS = {
    "hdfc_upi": fmt_hdfc_upi, "sbi_upi": fmt_sbi_upi, "icici_upi": fmt_icici_upi, "axis_upi": fmt_axis_upi,
    "kotak_upi": fmt_kotak_upi, "card_pos": fmt_card_pos, "card_online": fmt_card_online, "card_ecom": fmt_card_ecom,
    "razorpay": fmt_razorpay, "billdesk": fmt_billdesk, "imps": fmt_imps, "neft": fmt_neft,
    "paytm_wallet": fmt_paytm_wallet, "gpay": fmt_gpay, "phonepe": fmt_phonepe,
}
BANK_UPI_FORMAT = {"HDFC Bank": "hdfc_upi", "State Bank of India": "sbi_upi", "ICICI Bank": "icici_upi",
                   "Axis Bank": "axis_upi", "Kotak Mahindra Bank": "kotak_upi", "IDFC First Bank": "gpay",
                   "Punjab National Bank": "phonepe"}
CARD_FORMATS = ["card_pos", "card_online", "card_ecom", "razorpay"]


def special_narration(category: str, rng: random.Random, *, lender: str = "", bank: str = "",
                      scheme: str = "", card: str = "", city: str = "") -> str:
    """Narrations for non-merchant transactions (EMI, SIP, rent, ATM, transfers, card bills)."""
    if category == "EMI":
        return rng.choice([f"ACH D- {lender.upper()}-{_ref(rng, 10)}", f"NACH/DR/{lender.upper()} EMI/{_ref(rng, 8)}",
                           f"ECS/{lender.upper()}/LOAN {_ref(rng, 8)}"])
    if category == "Investment":
        return rng.choice([f"ACH D- BSE LTD-{scheme.upper()[:18]}", f"NACH/DR/CAMS {scheme.upper()[:16]} SIP",
                           f"BSE STAR MF SIP {_ref(rng, 8)}"])
    if category == "Rent":
        return rng.choice([f"IMPS/P2A/{_ref(rng)}/RENT {rng.choice(['OCT', 'NOV', 'FLAT', 'HOUSE'])}",
                           f"UPI-LANDLORD RENT-{_handle('rent', rng)}-{_ref(rng)}", "NEFT DR-RENT PAYMENT-MONTHLY RENT"])
    if category == "Cash":
        return rng.choice([f"ATM WDL {bank.split()[0].upper()} ATM {city.upper() or rng.choice(CITIES)}",
                           f"NWD-{_ref(rng, 6)}-{rng.choice(CITIES)}", f"ATW-{rng.randint(4000, 5599)}XXXXXX ATM CASH"])
    if category == "Card Payment":
        return rng.choice([f"CC PAYMENT {card.upper()} XX{rng.randint(1000, 9999)}", f"BIL/ONL/{card.upper()} CREDIT CARD",
                           f"CREDIT CARD BILL PAYMENT {card.upper()}"])
    if category == "Transfer":
        return rng.choice([f"IMPS/SELF TRANSFER/{_ref(rng)}", f"NEFT DR-OWN ACCOUNT TRF-{bank.upper()[:10]}",
                           f"UPI-SELF-{_handle('self', rng)}-{_ref(rng)}"])
    if category == "Insurance":
        return rng.choice([f"ACH D- {lender.upper() or 'LIC OF INDIA'}-PREMIUM", f"BIL/BPAY/{lender.upper()} PREMIUM"])
    raise ValueError(category)


def merchant_narration(category: str, rng: random.Random, fmt: str | None = None) -> tuple[str, str, str]:
    """Returns (raw_description, merchant_display_name, format_name)."""
    m, code = rng.choice(MERCHANTS[category])
    fmt = fmt or rng.choice(list(FORMATS))
    return FORMATS[fmt](code, m, rng), m, fmt
