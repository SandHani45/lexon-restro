# tenants/tax_regimes.py
"""
Single source of truth for everything that differs between tax
jurisdictions -- rate options, labels, currency, and which India-specific
mechanisms (CGST/SGST split, Composition Scheme, HSN/SAC) even apply.

Keyed by Tenant.country. Every receipt/report/setup-screen template or
service should read Outlet's tax_* / currency_symbol properties (see
tenants/models.py, right after Outlet.uses_utgst) rather than branching on
`tenant.country == 'AE'` directly in five different places -- that
duplication is exactly what caused GSTIN/CGST/SGST to be hardcoded
independently across bill.html, qsr_bill.html, public_bill.html,
thermal_receipt.html, and printing_service.py in the first place.

UAE VAT figures below are sourced from the Federal Tax Authority / UAE
VAT Decree-Law (Federal Decree-Law No. 8 of 2017, as amended) as of 2026:
flat 5% standard rate on all F&B, no reduced rate for food, TRN is a
15-digit FTA-issued number, most restaurant bills qualify as "simplified"
tax invoices (under AED 10,000). No CGST/SGST-style split exists in UAE
VAT -- it's a single tax line, unlike India's dual intra-state GST.
"""
from decimal import Decimal

TAX_REGIMES = {
    "IN": {
        "tax_label": "GST",
        "reg_label": "GSTIN",
        "currency_symbol": "₹",
        "currency_code": "INR",
        "rate_options": [
            (Decimal("0"),  "0% — Exempt"),
            (Decimal("5"),  "5% — Non-AC Restaurant"),
            (Decimal("12"), "12% — Packaged Food"),
            (Decimal("18"), "18% — AC / Liquor License"),
            (Decimal("28"), "28% — 5-Star / Premium (rare)"),
        ],
        "supports_cgst_sgst_split": True,
        "supports_composition_scheme": True,
        "supports_hsn_sac": True,
        "supports_statutory_export": True,  # GSTR-1
    },
    "AE": {
        "tax_label": "VAT",
        "reg_label": "TRN",
        "currency_symbol": "AED",
        "currency_code": "AED",
        "rate_options": [
            (Decimal("0"), "0% — Zero-rated"),
            (Decimal("5"), "5% — Standard Rate"),
        ],
        "supports_cgst_sgst_split": False,
        "supports_composition_scheme": False,
        "supports_hsn_sac": False,
        "supports_statutory_export": False,  # no VAT201 e-filing export built
    },
}

DEFAULT_COUNTRY = "IN"


def get_regime(country):
    """Never raises -- an unknown/blank country falls back to India's regime
    (the pre-existing default behavior for every tenant created before this
    field existed)."""
    return TAX_REGIMES.get(country, TAX_REGIMES[DEFAULT_COUNTRY])
