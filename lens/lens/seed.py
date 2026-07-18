"""Deterministic synthetic universe for Punara Lens v0.

Seeds ONE fake Indian beauty D2C brand (canonical fixture: slug "meadow",
Meadow Botanicals — CONTRACTS.md §6). Per CONTRACTS.md §2.1 the seeder writes:

- core catalog rows: ``products`` + ``variants`` (source="shopify")
- ``raw_records`` the connector pipeline syncs from, as (source, resource):
    (shopify, customers) · (shopify, products) · (shopify, orders)
        — refunds are embedded in the order payload under "refunds"
          (mirrors Shopify's order JSON; there is no separate refunds resource)
    (razorpay, payments) · (shiprocket, shipments)
    (klaviyo, campaigns) · (klaviyo, messages) · (klaviyo, consent)
    Phase 2 (CONTRACTS.md V2.1):
    (interakt, campaigns) · (interakt, messages) · (interakt, consent)
    (gorgias, tickets) · (judgeme, reviews)
- Phase-2 direct-to-core rows (no connector exists for them by design):
  ``nps_responses`` (customer linked later via ``link_direct``) and
  ``experiments`` (the Loop Ledger has no external source system).

The seeder does NOT write core customers/orders/messages — connectors do.

Determinism: every v0 draw comes from one ``numpy.random.default_rng(seed)``;
the time anchor is the fixed constant ``HISTORY_END`` (never wall clock), so
the same (slug, months, seed, customers) is a byte-identical universe and
re-running is a no-op via the (tenant_id, source, resource, external_id)
unique constraint. ALL Phase-2 draws come from a SEPARATE stream
``numpy.random.default_rng([seed, 2])`` consumed in a fixed order (flows ->
wa campaigns -> wa messages -> tickets -> reviews -> nps), so the v0 stream
is untouched, every v0 raw record stays byte-identical, and the v0 score
values do not shift.

Money: integer paise only. Raw payloads use ``*_paise`` integer keys rather
than Shopify's decimal strings — the repo-wide money convention outranks
source cosplay (noted in CONTRACTS.md §2.1).

Identity-resolution raw material baked in: ~8% of customers place guest
orders (customer=null, keyed by phone/email) alongside account orders; ~3%
missing phones; ~1% duplicate emails with case differences; ~2% of orders
carry a zero-price sample item (Signal Score raw material).
"""

from __future__ import annotations

import calendar
from bisect import bisect_right
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import numpy as np
from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from .models import Customer, Experiment, NpsResponse, Product, RawRecord, Tenant, Variant

# --------------------------------------------------------------------- knobs

HISTORY_END = datetime(2026, 7, 1)  # fixed anchor: determinism over freshness

SEASON = {1: 0.95, 2: 0.90, 3: 0.95, 4: 1.00, 5: 1.00, 6: 0.95,
          7: 1.00, 8: 1.05, 9: 1.10, 10: 1.45, 11: 1.50, 12: 1.15}
MONTHLY_GROWTH = 1.028

# BG/NBD-flavored repeat process: per-customer purchase rate lambda ~ Gamma,
# dropout-after-purchase p ~ Beta. Calibrated to repeat rate ~25-32% and a
# heavy top-decile tail over 24 months.
LAM_SHAPE, LAM_SCALE = 0.24, 0.011          # purchases/day; heavy skew
LAM_CAP = 0.09                              # <= ~1 order / 11 days, tail sanity
DROP_A, DROP_B = 1.3, 3.2                   # mean dropout ~0.29

COD_SHARE = 0.55
RTO_COD, RTO_PREPAID = 0.18, 0.06
PAY_FAIL = 0.045                            # failed first attempt, prepaid
PAY_RETRY = 0.70                            # of failures, retried & captured
REFUND_RATE = 0.07                          # of delivered orders
CANCEL_RATE = 0.02
DEAL_HUNTER = 0.04                          # only-buys-discounted cluster
SPLIT_IDENTITY = 0.08                       # guest + account orders, same human
MISSING_PHONE = 0.03
DUP_EMAIL = 0.012
ZERO_PRICE_ITEM = 0.02
FREE_SHIP_ABOVE = 69_900                    # paise
SHIP_FEE = 7_900

OPT_EMAIL, OPT_WA, OPT_SMS = 0.70, 0.45, 0.15
REVOKE_EMAIL, REVOKE_WA, REVOKE_SMS = 0.07, 0.04, 0.03

FIRST_NAMES = [
    "Aarav", "Ananya", "Aditi", "Arjun", "Avni", "Bhavya", "Chirag", "Darsh",
    "Devika", "Diya", "Esha", "Farhan", "Gauri", "Harsh", "Ishaan", "Ishita",
    "Jhanvi", "Kabir", "Kavya", "Kriti", "Lakshmi", "Manav", "Meera", "Mihir",
    "Naina", "Neha", "Nikhil", "Nisha", "Ojas", "Pooja", "Pranav", "Priya",
    "Rahul", "Riya", "Rohan", "Sahana", "Sameer", "Sanya", "Shreya", "Siddharth",
    "Sneha", "Tanvi", "Uday", "Vanya", "Varun", "Vidya", "Yash", "Zoya",
]
LAST_NAMES = [
    "Agarwal", "Bansal", "Bhat", "Chatterjee", "Chopra", "Das", "Desai",
    "Dutta", "Gupta", "Iyer", "Jain", "Joshi", "Kapoor", "Khan", "Kulkarni",
    "Kumar", "Mehta", "Menon", "Mishra", "Mukherjee", "Nair", "Patel",
    "Pillai", "Rao", "Reddy", "Saxena", "Sen", "Shah", "Sharma", "Shetty",
    "Singh", "Sinha", "Srinivasan", "Trivedi", "Varma", "Verma",
]
EMAIL_DOMAINS = ["gmail.com", "gmail.com", "gmail.com", "gmail.com",
                 "yahoo.in", "outlook.com", "hotmail.com", "rediffmail.com"]

INGREDIENTS = [
    "Saffron", "Vetiver", "Rose", "Neem", "Turmeric", "Aloe", "Hibiscus",
    "Sandalwood", "Jasmine", "Kokum", "Moringa", "Amla", "Ubtan", "Charcoal",
    "Vitamin C", "Kumkumadi", "Tea Tree", "Onion", "Rice Water", "Cucumber",
]
# category, forms, price band (paise), variant axis values, catalog weight
CATEGORIES = [
    ("Face Care", ["Face Wash", "Face Serum", "Day Cream", "Night Cream",
                   "Clay Mask", "Under-Eye Gel", "Sunscreen SPF 50"],
     (39_900, 129_900), ["30 ml", "50 ml", "100 ml"], 0.30),
    ("Hair Care", ["Shampoo", "Conditioner", "Hair Oil", "Hair Mask",
                   "Hair Serum"], (34_900, 99_900),
     ["100 ml", "200 ml", "350 ml"], 0.22),
    ("Body Care", ["Body Lotion", "Body Wash", "Body Butter", "Body Scrub"],
     (29_900, 89_900), ["100 ml", "200 ml", "400 ml"], 0.15),
    ("Lip Care", ["Lip Balm", "Lip Tint", "Lip Scrub"],
     (29_900, 59_900), ["8 g", "15 g", "Twin Pack"], 0.10),
    ("Fragrance", ["Eau De Parfum", "Body Mist", "Solid Perfume"],
     (69_900, 249_900), ["20 ml", "50 ml", "100 ml"], 0.10),
    ("Makeup", ["Kajal", "Liquid Lipstick", "Compact", "Blush"],
     (44_900, 149_900), ["Ruby", "Coral", "Nude", "Rosewood"], 0.08),
    ("Gift Sets", ["Gift Set", "Ritual Kit"],
     (99_900, 249_900), ["Classic", "Deluxe", "Premium"], 0.05),
]
COURIERS = ["Delhivery", "BlueDart", "XpressBees", "Ecom Express", "DTDC"]
FAIL_REASONS = ["payment_timeout", "insufficient_funds", "bank_declined",
                "upi_expired"]
PREPAID_METHODS = ["upi", "card", "netbanking", "wallet"]
PREPAID_METHOD_P = [0.55, 0.25, 0.12, 0.08]
DISCOUNT_CODES = ["WELCOME10", "GLOW15", "FESTIVE20", "REGLOW15"]
DEAL_CODES = ["SALE50", "FESTIVE40", "BOGO", "MEGA35"]
CAMPAIGN_THEMES = [
    "New Launch", "Glow Ritual", "Weekend Sale", "Restock Alert",
    "Skincare 101", "Member Exclusive", "Bestseller Spotlight",
    "Monsoon Care", "Summer Essentials", "Winter Repair",
]
FESTIVE_THEMES = ["Diwali Glow Sale", "Festive Gift Guide",
                  "Big Diwali Bonanza", "Dhanteras Special"]


@dataclass(frozen=True)
class SeedReport:
    tenant_id: int
    tenant_slug: str
    months: int
    seed: int
    counts: dict[str, int]  # table/resource name -> rows written this run


# ------------------------------------------------------------------- helpers


def _iso(dt: datetime | None) -> str | None:
    return None if dt is None else dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _month_start(end: datetime, months: int, i: int) -> datetime:
    total = end.year * 12 + (end.month - 1) - months + i
    y, m = divmod(total, 12)
    return datetime(y, m + 1, 1)


def _round_price(rupees: float) -> int:
    """Snap to a ₹x49/x99 shelf price, returned in paise."""
    r = max(49, int(rupees) // 50 * 50 - 1)
    return r * 100


def _get_or_create_tenant(session: Session, slug: str) -> Tenant:
    tenant = session.scalar(select(Tenant).where(Tenant.slug == slug))
    if tenant is None:
        if slug == "meadow":  # canonical fixture, CONTRACTS.md §6
            name, domain = "Meadow Botanicals", "meadow-botanicals.myshopify.com"
        else:
            name, domain = slug.replace("-", " ").title(), f"{slug}.myshopify.com"
        tenant = Tenant(slug=slug, name=name, shopify_domain=domain,
                        base_currency="INR", plan="advisory", country="IN",
                        status="active")
        session.add(tenant)
        session.flush()
    return tenant


def _insert_raw(session: Session, tenant_id: int, source: str, resource: str,
                rows: list[tuple[str, dict[str, Any], datetime]]) -> int:
    """Bulk-insert raw records, skipping external_ids already present (no-op re-run)."""
    existing = set(session.scalars(
        select(RawRecord.external_id).where(
            RawRecord.tenant_id == tenant_id,
            RawRecord.source == source,
            RawRecord.resource == resource)))
    fresh = [
        {"tenant_id": tenant_id, "source": source, "resource": resource,
         "external_id": eid, "payload": payload, "received_at": ts}
        for eid, payload, ts in rows if eid not in existing
    ]
    if fresh:
        session.execute(insert(RawRecord), fresh)
    return len(fresh)


# ---------------------------------------------------------------- generation


def _gen_catalog(rng: np.random.Generator) -> list[dict[str, Any]]:
    """~60 products / ~180 variants with category-realistic INR pricing."""
    cat_p = np.array([c[4] for c in CATEGORIES])
    cat_p = cat_p / cat_p.sum()
    products: list[dict[str, Any]] = []
    seen: set[str] = set()
    pidx = 0
    while len(products) < 60:
        cat, forms, (lo, hi), axis, _w = CATEGORIES[int(rng.choice(len(CATEGORIES), p=cat_p))]
        title = (f"{INGREDIENTS[int(rng.integers(len(INGREDIENTS)))]} "
                 f"{forms[int(rng.integers(len(forms)))]}")
        if title in seen:
            continue
        seen.add(title)
        pidx += 1
        # beta-skewed toward the low end of the band: shelf-heavy, few heroes
        base = _round_price((lo + (hi - lo) * float(rng.beta(1.1, 3.0))) / 100)
        n_var = len(axis) if rng.random() < 0.75 else len(axis) - 1
        variants = []
        for vi in range(n_var):
            price = _round_price(base * (1 + 0.30 * vi) / 100)
            variants.append({
                "external_id": str(8_100_000_000 + pidx * 10 + vi),
                "sku": f"MB-{pidx:03d}-{vi + 1}",
                "title": axis[vi % len(axis)],
                "price_paise": price,
                "compare_at_price_paise":
                    _round_price(price * 1.25 / 100) if rng.random() < 0.2 else None,
                "cost_paise": int(price * rng.uniform(0.35, 0.55)),
            })
        products.append({
            "external_id": str(8_000_000_000 + pidx),
            "title": title, "product_type": cat, "vendor": "Meadow Botanicals",
            "status": "active", "variants": variants,
        })
    return products


def _mixed_case(rng: np.random.Generator, s: str) -> str:
    return "".join(c.upper() if rng.random() < 0.3 else c for c in s)


def _gen_customers(rng: np.random.Generator, months: int, n: int) -> list[dict[str, Any]]:
    start_months = [_month_start(HISTORY_END, months, i) for i in range(months)]
    weights = np.array([MONTHLY_GROWTH ** i * SEASON[m.month]
                        for i, m in enumerate(start_months)])
    per_month = rng.multinomial(n, weights / weights.sum())

    customers: list[dict[str, Any]] = []
    used_phones: set[str] = set()
    i = 0
    for mi, count in enumerate(per_month):
        m0 = start_months[mi]
        days = calendar.monthrange(m0.year, m0.month)[1]
        for _ in range(int(count)):
            first = FIRST_NAMES[int(rng.integers(len(FIRST_NAMES)))]
            last = LAST_NAMES[int(rng.integers(len(LAST_NAMES)))]
            email = (f"{first.lower()}.{last.lower()}{i}"
                     f"@{EMAIL_DOMAINS[int(rng.integers(len(EMAIL_DOMAINS)))]}")
            while True:
                phone = f"+91{int(rng.integers(6, 10))}" + "".join(
                    str(d) for d in rng.integers(0, 10, size=9))
                if phone not in used_phones:
                    used_phones.add(phone)
                    break
            acq = m0 + timedelta(days=float(rng.uniform(0, days)),
                                 hours=float(rng.uniform(9, 23)))
            if acq >= HISTORY_END:
                acq = HISTORY_END - timedelta(hours=1)
            c: dict[str, Any] = {
                "idx": i,
                "external_id": str(7_000_000_000 + i),
                "first_name": first, "last_name": last,
                "email": email,
                "phone": None if rng.random() < MISSING_PHONE else phone,
                "created_at": acq,
                "deal_hunter": rng.random() < DEAL_HUNTER,
                "split_identity": rng.random() < SPLIT_IDENTITY,
                "email_opt": bool(rng.random() < OPT_EMAIL),
                "wa_opt": bool(rng.random() < OPT_WA),
                "sms_opt": bool(rng.random() < OPT_SMS),
                "email_revoke_at": None, "wa_revoke_at": None, "sms_revoke_at": None,
            }
            for ch, rate in (("email", REVOKE_EMAIL), ("wa", REVOKE_WA),
                             ("sms", REVOKE_SMS)):
                if c[f"{ch}_opt"] and rng.random() < rate:
                    lo = acq + timedelta(days=30)
                    if lo < HISTORY_END:
                        span = (HISTORY_END - lo).total_seconds()
                        c[f"{ch}_revoke_at"] = lo + timedelta(
                            seconds=float(rng.uniform(0, span)))
            customers.append(c)
            i += 1

    # messy data: duplicate emails with case differences (distinct humans)
    for c in customers:
        r = rng.random()
        if c["idx"] > 50 and r < DUP_EMAIL:
            donor = customers[int(rng.integers(0, c["idx"]))]
            c["email"] = _mixed_case(rng, donor["email"])
        elif r < DUP_EMAIL + 0.02:  # plain sloppy casing of own email
            c["email"] = _mixed_case(rng, c["email"])
    return customers


def _sim_order_times(rng: np.random.Generator, acq: datetime, deal: bool) -> list[datetime]:
    lam = min(float(rng.gamma(LAM_SHAPE, LAM_SCALE)), LAM_CAP)
    p_drop = float(rng.beta(DROP_A, DROP_B))
    if deal:
        lam, p_drop = min(lam * 1.8, LAM_CAP), p_drop * 0.55
    times = [acq]
    t = acq
    while True:
        gap = float(rng.exponential(1.0 / max(lam, 1e-6)))
        if gap > (HISTORY_END - t).total_seconds() / 86400:
            break
        t = t + timedelta(days=gap)
        times.append(t)
        if rng.random() < p_drop:
            break
    return times


def _gen_orders(rng: np.random.Generator, customers: list[dict[str, Any]],
                catalog: list[dict[str, Any]]) -> list[dict[str, Any]]:
    variants = [(p, v) for p in catalog for v in p["variants"]]
    # hero SKUs via pareto, mildly biased toward affordable price points
    pop = (rng.pareto(1.2, len(variants)) + 0.05) / np.sqrt(
        [v["price_paise"] / 100 for _, v in variants])
    pop = pop / pop.sum()

    orders: list[dict[str, Any]] = []
    for c in customers:
        for k, placed in enumerate(_sim_order_times(rng, c["created_at"], c["deal_hunter"])):
            n_items = int(rng.choice([1, 2, 3], p=[0.62, 0.27, 0.11]))
            picks = rng.choice(len(variants), size=n_items, replace=False, p=pop)
            items = []
            subtotal = 0
            for vi in picks:
                p, v = variants[int(vi)]
                qty = 2 if rng.random() < 0.15 else 1
                items.append({
                    "product_external_id": p["external_id"],
                    "variant_external_id": v["external_id"],
                    "sku": v["sku"], "title": f"{p['title']} — {v['title']}",
                    "quantity": qty, "unit_price_paise": v["price_paise"],
                    "discount_paise": 0,
                })
                subtotal += qty * v["price_paise"]
            if rng.random() < ZERO_PRICE_ITEM:  # free sample; Signal material
                items.append({"product_external_id": None, "variant_external_id": None,
                              "sku": "MB-SAMPLE", "title": "Sample Sachet",
                              "quantity": 1, "unit_price_paise": 0, "discount_paise": 0})

            if c["deal_hunter"]:
                pct, codes = float(rng.uniform(0.25, 0.50)), DEAL_CODES
            elif rng.random() < 0.30:
                pct, codes = float(rng.uniform(0.10, 0.25)), DISCOUNT_CODES
            else:
                pct, codes = 0.0, []
            discount = int(subtotal * pct)
            shipping = 0 if subtotal - discount >= FREE_SHIP_ABOVE else SHIP_FEE
            total = subtotal - discount + shipping

            orders.append({
                "cust": c, "k": k, "placed_at": placed, "items": items,
                "subtotal_paise": subtotal, "discount_paise": discount,
                "shipping_paise": shipping, "tax_paise": 0, "total_paise": total,
                "discount_codes": [codes[int(rng.integers(len(codes)))]] if discount else [],
                "cod": bool(rng.random() < COD_SHARE),
                "cancelled": bool(rng.random() < CANCEL_RATE),
            })

    orders.sort(key=lambda o: (o["placed_at"], o["cust"]["idx"], o["k"]))
    for j, o in enumerate(orders):
        o["external_id"] = str(9_000_000_000 + j)
        o["order_number"] = f"MB-{10_000 + j}"
        _sim_order_outcome(rng, o)
    return orders


def _sim_order_outcome(rng: np.random.Generator, o: dict[str, Any]) -> None:
    """Payments, shipment, refunds, statuses — attached in place."""
    placed = o["placed_at"]
    o.update(cancelled_at=None, payments=[], shipment=None, refunds=[],
             financial_status="pending", fulfillment_status="unfulfilled")

    if o["cancelled"]:
        o["cancelled_at"] = placed + timedelta(hours=float(rng.uniform(1, 24)))
        o["financial_status"] = "voided"
        return

    paid = o["cod"]  # COD ships without capture
    if not o["cod"]:
        method = str(rng.choice(PREPAID_METHODS, p=PREPAID_METHOD_P))
        t0 = placed + timedelta(minutes=float(rng.uniform(1, 30)))
        if rng.random() < PAY_FAIL:
            o["payments"].append({
                "suffix": "a1", "method": method, "status": "failed",
                "failure_reason": FAIL_REASONS[int(rng.integers(len(FAIL_REASONS)))],
                "occurred_at": t0})
            if rng.random() < PAY_RETRY:
                o["payments"].append({
                    "suffix": "a2", "method": method, "status": "captured",
                    "failure_reason": None,
                    "occurred_at": t0 + timedelta(hours=float(rng.uniform(0.5, 6)))})
                paid = True
        else:
            o["payments"].append({"suffix": "a1", "method": method, "status": "captured",
                                  "failure_reason": None, "occurred_at": t0})
            paid = True
        if paid:
            o["financial_status"] = "paid"

    if not paid:  # abandoned after failed payment
        return

    shipped = placed + timedelta(days=float(rng.uniform(1, 3)),
                                 hours=float(rng.uniform(0, 12)))
    if shipped >= HISTORY_END:
        return  # not yet handed to courier at end of history
    courier = COURIERS[int(rng.integers(len(COURIERS)))]
    rto = rng.random() < (RTO_COD if o["cod"] else RTO_PREPAID)
    ship = {"courier": courier, "shipped_at": shipped, "rto": False,
            "delivered_at": None, "rto_at": None, "status": "in_transit"}
    o["shipment"] = ship
    o["fulfillment_status"] = "fulfilled"

    if rto:
        rto_at = shipped + timedelta(days=float(rng.uniform(6, 16)))
        if rto_at >= HISTORY_END:
            return  # still in transit at end of history
        ship.update(rto=True, rto_at=rto_at, status="rto_received")
        o["fulfillment_status"] = "rto"
        if o["cod"]:
            o["financial_status"] = "voided"  # cash never collected
        else:
            o["financial_status"] = "refunded"
            o["refunds"].append({
                "suffix": "r1", "amount_paise": o["total_paise"], "refund_type": "rto",
                "processed_at": rto_at + timedelta(days=float(rng.uniform(2, 6)))})
        return

    delivered = shipped + timedelta(days=float(rng.uniform(2, 9)))
    if delivered >= HISTORY_END:
        return
    ship.update(delivered_at=delivered, status="delivered")
    o["fulfillment_status"] = "delivered"
    o["financial_status"] = "paid"

    if rng.random() < REFUND_RATE:
        full = rng.random() < 0.40
        amount = o["total_paise"] if full else int(o["total_paise"] * rng.uniform(0.30, 0.60))
        processed = delivered + timedelta(days=float(rng.uniform(3, 20)))
        if processed < HISTORY_END and amount > 0:
            o["refunds"].append({
                "suffix": "r1", "amount_paise": amount,
                "refund_type": "return" if rng.random() < 0.85 else "goodwill",
                "processed_at": processed})
            o["financial_status"] = "refunded" if full else "partially_refunded"


def _gen_campaigns(rng: np.random.Generator, months: int) -> list[dict[str, Any]]:
    start = _month_start(HISTORY_END, months, 0)
    campaigns: list[dict[str, Any]] = []
    n_weeks = (HISTORY_END - start).days // 7
    ci = 0
    for w in range(n_weeks):
        for _ in range(int(rng.integers(2, 4))):  # 2-3 per week
            sent = start + timedelta(days=w * 7 + float(rng.uniform(0, 7)),
                                     hours=float(rng.uniform(9, 20)))
            if sent >= HISTORY_END:
                continue
            themes = (FESTIVE_THEMES if sent.month in (10, 11) and rng.random() < 0.5
                      else CAMPAIGN_THEMES)
            theme = themes[int(rng.integers(len(themes)))]
            channel = "sms" if rng.random() < 0.20 else "email"
            ci += 1
            campaigns.append({
                "external_id": f"KLC{ci:04d}",
                "name": f"{theme} #{ci}",
                "campaign_type": "campaign", "channel": channel,
                "subject": f"{theme} — Meadow Botanicals" if channel == "email" else None,
                "started_at": sent,
            })
    campaigns.sort(key=lambda c: (c["started_at"], c["external_id"]))
    return campaigns


def _gen_messages(rng: np.random.Generator, customers: list[dict[str, Any]],
                  campaigns: list[dict[str, Any]],
                  order_times: dict[int, list[datetime]]) -> list[dict[str, Any]]:
    acq = np.array([c["created_at"].timestamp() for c in customers])
    inf = float("inf")
    elig = {
        "email": (np.array([c["email_opt"] for c in customers]),
                  np.array([c["email_revoke_at"].timestamp() if c["email_revoke_at"] else inf
                            for c in customers])),
        "sms": (np.array([c["sms_opt"] for c in customers]),
                np.array([c["sms_revoke_at"].timestamp() if c["sms_revoke_at"] else inf
                          for c in customers])),
    }
    messages: list[dict[str, Any]] = []
    for camp in campaigns:
        ch = camp["channel"]
        send_ts = camp["started_at"].timestamp()
        opted, revoke = elig[ch]
        pool = np.flatnonzero((acq < send_ts) & opted & (revoke > send_ts))
        if len(pool) == 0:
            continue
        size = min(len(pool), max(10, int(len(pool) * rng.uniform(0.05, 0.10))))
        audience = rng.choice(pool, size=size, replace=False)
        for ci in sorted(int(x) for x in audience):
            c = customers[ci]
            sent = camp["started_at"] + timedelta(seconds=float(rng.uniform(0, 900)))
            m: dict[str, Any] = {
                "id": f"KLM{camp['external_id'][3:]}-{ci}",
                "campaign_id": camp["external_id"],
                "profile": {"id": f"KP{ci}", "email": c["email"], "phone": c["phone"]},
                "channel": ch, "sent_at": sent, "delivered_at": None,
                "opened_at": None, "clicked_at": None, "bounced_at": None,
                "unsubscribed_at": None}
            if rng.random() < (0.025 if ch == "email" else 0.01):
                m["bounced_at"] = sent + timedelta(minutes=float(rng.uniform(1, 10)))
                messages.append(m)
                continue
            delivered = sent + timedelta(minutes=float(rng.uniform(1, 10)))
            m["delivered_at"] = delivered

            # campaign attribution: order within 72h of send -> click before it
            times = order_times.get(ci, [])
            pos = bisect_right(times, sent)
            attributed = (pos < len(times)
                          and times[pos] <= sent + timedelta(hours=72)
                          and rng.random() < 0.55)
            if ch == "email":
                if attributed:
                    opened = delivered + timedelta(minutes=float(rng.uniform(10, 90)))
                    clicked = max(opened + timedelta(minutes=5),
                                  times[pos] - timedelta(hours=float(rng.uniform(0.5, 47))))
                    m["opened_at"], m["clicked_at"] = opened, clicked
                elif rng.random() < 0.35:
                    opened = delivered + timedelta(hours=float(rng.uniform(0.2, 36)))
                    m["opened_at"] = opened
                    if rng.random() < 0.09:
                        m["clicked_at"] = opened + timedelta(hours=float(rng.uniform(0.1, 12)))
            else:  # sms: no opens
                if attributed or rng.random() < 0.02:
                    m["clicked_at"] = delivered + timedelta(hours=float(rng.uniform(0.1, 24)))
            revoke_at = c["email_revoke_at" if ch == "email" else "sms_revoke_at"]
            if revoke_at and sent < revoke_at <= sent + timedelta(hours=72):
                m["unsubscribed_at"] = revoke_at
            messages.append(m)
    return messages


def _gen_consent(customers: list[dict[str, Any]]) -> list[tuple[str, dict[str, Any], datetime]]:
    rows: list[tuple[str, dict[str, Any], datetime]] = []
    for c in customers:
        profile = {"id": f"KP{c['idx']}", "email": c["email"], "phone": c["phone"]}
        for ch, opt_key, rev_key in (("email", "email_opt", "email_revoke_at"),
                                     ("whatsapp", "wa_opt", "wa_revoke_at"),
                                     ("sms", "sms_opt", "sms_revoke_at")):
            if not c[opt_key]:
                continue
            granted = c["created_at"] + timedelta(minutes=5)
            eid = f"KCON-{c['idx']}-{ch}-g"
            rows.append((eid, {"id": eid, "profile": profile, "channel": ch,
                               "action": "granted", "method": "checkout",
                               "occurred_at": _iso(granted)}, granted))
            if c[rev_key]:
                eid = f"KCON-{c['idx']}-{ch}-r"
                rows.append((eid, {"id": eid, "profile": profile, "channel": ch,
                                   "action": "revoked", "method": "unsubscribe_link",
                                   "occurred_at": _iso(c[rev_key])}, c[rev_key]))
    return rows


# ------------------------------------------------------------- phase 2 knobs

WA_DELIVER, WA_READ, WA_REPLY = 0.95, 0.65, 0.08  # whatsapp funnel
WA_ATTR = 0.50                # order <=72h after a WA send -> conversation-attributed
TICKET_RATE, TICKET_RATE_RTO = 0.045, 0.30  # ~6-7% of orders overall
CSAT_RATE = 0.40              # share of resolved tickets that leave a CSAT
REVIEW_RATE = 0.08            # of delivered orders
NPS_RATE = 0.05               # of customers with orders

TICKET_CATEGORIES = ("delivery_delay", "damaged", "refund_where", "quality")
TICKET_SUBJECTS = {
    "delivery_delay": "Where is my order? It has been days",
    "damaged": "Product arrived damaged / leaking",
    "refund_where": "Refund not received yet",
    "quality": "Product quality not as expected",
}
TICKET_CHANNELS = ["email", "whatsapp", "chat", "instagram", "phone"]
TICKET_CHANNEL_P = [0.35, 0.30, 0.20, 0.10, 0.05]

REVIEW_TEXT = {  # (title, body) pools by rating bucket
    "pos": [("Absolutely love it", "Part of my daily ritual now. Will definitely repurchase."),
            ("Works beautifully", "Saw a visible difference within two weeks. Packaging is lovely."),
            ("My new favourite", "Smells divine and feels so light. Fifth order from Meadow!")],
    "mid": [("Decent, not magical", "Does the job but nothing special for the price."),
            ("Okay product", "Took long to show results. Fragrance is a bit strong for me.")],
    "neg": [("Disappointed", "Order took forever to arrive and the pump was broken."),
            ("Not worth it", "Broke me out and support took days to reply."),
            ("Would not recommend", "Second bad experience in a row. Refund still pending.")],
}
NPS_COMMENTS = {
    "promoter": ["Love the products and the little notes in every box.",
                 "My whole skincare shelf is Meadow now."],
    "passive": ["Products are good, delivery could be faster.",
                "Nice brand, slightly pricey."],
    "detractor": ["My parcel came late and support was unhelpful.",
                  "Refund took three weeks. Not ordering again."],
}

FLOW_DEFS = [  # klaviyo lifecycle automations (Autopilot raw material)
    {"external_id": "KLF-01", "name": "Welcome Series",
     "subject": "Welcome to Meadow Botanicals"},
    {"external_id": "KLF-02", "name": "Post-Purchase Care",
     "subject": "How to get the most from your ritual"},
    {"external_id": "KLF-03", "name": "90-Day Winback",
     "subject": "We miss you — your ritual is waiting"},
]

# Loop Ledger fixtures: 14 experiments over the last 10 months.
# (name, hypothesis, score_target, status, started_days_ago, ran_days,
#  sample_size, lift_pct, significant, decision)
EXPERIMENT_FIXTURES = [
    ("Winback offer ladder A/B",
     "A stepped 10/15/20% winback ladder beats flat 15% on 60d reactivation rate by 10%.",
     "gravity", "concluded", 295, 35, 4200, 12.4, True, "shipped"),
    ("Post-purchase check-in email",
     "A day-5 care email lifts 90d second-purchase rate by 6%.",
     "flow", "concluded", 270, 42, 5100, 8.1, True, "shipped"),
    ("COD-to-prepaid nudge at checkout",
     "A Rs.50 prepaid incentive cuts COD share 8pts and RTO loss 12%.",
     "watertight", "concluded", 240, 30, 6300, 15.0, True, "shipped"),
    ("Replenishment reminder 30d vs 45d",
     "A 30d replenishment nudge beats 45d on repurchase latency by 15%.",
     "gravity", "concluded", 205, 28, 3800, 6.3, True, "shipped"),
    ("Free shipping vs 10% off threshold",
     "Free shipping above Rs.699 beats 10% off on contribution margin by 5%.",
     "watertight", "concluded", 180, 21, 5600, 4.8, True, "shipped"),
    ("Subject-line personalization",
     "First-name subject lines lift campaign open-to-order rate by 5%.",
     "flow", "concluded", 150, 28, 8800, -2.1, True, "killed"),
    ("Double SMS frequency",
     "2x weekly SMS lifts repeat revenue 8% without opt-out spike.",
     "flow", "concluded", 120, 21, 4400, -4.5, True, "killed"),
    ("Deep-discount winback (40%)",
     "A 40% winback offer beats 20% on 90d net revenue per dormant customer.",
     "gravity", "concluded", 100, 30, 2900, 1.2, False, "killed"),
    ("Festive gift-guide bundle",
     "A curated Diwali bundle lifts October AOV by 12%.",
     "gravity", "concluded", 265, 25, 3300, 2.0, False, "inconclusive"),
    ("RTO address-verification prompt",
     "A WhatsApp address confirmation on COD orders cuts RTO rate 20%.",
     "watertight", "running", 55, None, 5000, None, None, None),
    ("Slipping-stage save flow",
     "A day-75 save flow cuts slipping-to-dormant leak by 10%.",
     "flow", "running", 40, None, 3600, None, None, None),
    ("Loyalty tier teaser",
     "Showing points-to-next-tier in post-purchase email lifts 60d repeat rate 5%.",
     "gravity", "running", 20, None, 4100, None, None, None),
    ("NDR reattempt WhatsApp flow",
     "Same-day WhatsApp on failed delivery lifts reattempt success 25%.",
     "watertight", "draft", None, None, 4800, None, None, None),
    ("Birthday reward automation",
     "A birthday-month reward lifts member repeat rate 7%.",
     "flow", "draft", None, None, 2500, None, None, None),
]


# ------------------------------------------------------- phase 2 generation


def _email_flow_msg(rng: np.random.Generator, mid: str, flow_ext: str,
                    c: dict[str, Any], sent: datetime,
                    times: list[datetime]) -> dict[str, Any]:
    """One triggered flow email with funnel + 7d-click order attribution."""
    m: dict[str, Any] = {
        "id": mid, "campaign_id": flow_ext,
        "profile": {"id": f"KP{c['idx']}", "email": c["email"], "phone": c["phone"]},
        "channel": "email", "sent_at": sent, "delivered_at": None,
        "opened_at": None, "clicked_at": None, "bounced_at": None,
        "unsubscribed_at": None}
    if rng.random() < 0.025:
        m["bounced_at"] = sent + timedelta(minutes=float(rng.uniform(1, 10)))
        return m
    delivered = sent + timedelta(minutes=float(rng.uniform(1, 10)))
    m["delivered_at"] = delivered
    pos = bisect_right(times, sent)
    attributed = (pos < len(times)
                  and times[pos] <= sent + timedelta(hours=72)
                  and rng.random() < 0.45)
    if attributed:
        opened = delivered + timedelta(minutes=float(rng.uniform(10, 90)))
        m["opened_at"] = opened
        m["clicked_at"] = max(opened + timedelta(minutes=5),
                              times[pos] - timedelta(hours=float(rng.uniform(0.5, 47))))
    elif rng.random() < 0.50:  # triggered flows out-open blasts
        opened = delivered + timedelta(hours=float(rng.uniform(0.2, 36)))
        m["opened_at"] = opened
        if rng.random() < 0.12:
            m["clicked_at"] = opened + timedelta(hours=float(rng.uniform(0.1, 12)))
    return m


def _flow_send_ok(c: dict[str, Any], sent: datetime) -> bool:
    revoke = c["email_revoke_at"]
    return c["email_opt"] and sent < HISTORY_END and (revoke is None or sent < revoke)


def _gen_flows(rng: np.random.Generator, customers: list[dict[str, Any]],
               orders: list[dict[str, Any]], order_times: dict[int, list[datetime]],
               months: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Klaviyo automations: welcome / post-purchase / winback flow messages."""
    start = _month_start(HISTORY_END, months, 0)
    flow_campaigns = [
        {**f, "campaign_type": "flow", "channel": "email", "started_at": start}
        for f in FLOW_DEFS]
    messages: list[dict[str, Any]] = []
    # welcome + winback, per customer in idx order (deterministic)
    for c in customers:
        times = order_times.get(c["idx"], [])
        sent = c["created_at"] + timedelta(hours=1)
        if _flow_send_ok(c, sent):
            messages.append(_email_flow_msg(rng, f"KLFM-W-{c['idx']}", "KLF-01", c, sent, times))
        winbacks = 0
        for i, t in enumerate(times):
            nxt = times[i + 1] if i + 1 < len(times) else HISTORY_END
            if (nxt - t).days > 100 and winbacks < 2:
                sent = t + timedelta(days=90)
                if _flow_send_ok(c, sent):
                    messages.append(_email_flow_msg(
                        rng, f"KLFM-B-{c['idx']}-{winbacks}", "KLF-03", c, sent, times))
                    winbacks += 1
    # post-purchase, per delivered order in order sequence (deterministic)
    for o in orders:
        ship = o["shipment"]
        if o["cancelled"] or ship is None or ship["delivered_at"] is None:
            continue
        c = o["cust"]
        sent = ship["delivered_at"] + timedelta(days=2)
        if _flow_send_ok(c, sent):
            messages.append(_email_flow_msg(
                rng, f"KLFM-P-{o['external_id']}", "KLF-02", c, sent,
                order_times.get(c["idx"], [])))
    return flow_campaigns, messages


def _gen_wa_campaigns(rng: np.random.Generator, months: int) -> list[dict[str, Any]]:
    """Interakt WhatsApp broadcasts: 1-2 per week over the whole history."""
    start = _month_start(HISTORY_END, months, 0)
    n_weeks = (HISTORY_END - start).days // 7
    campaigns: list[dict[str, Any]] = []
    ci = 0
    for w in range(n_weeks):
        for _ in range(int(rng.integers(1, 3))):  # 1-2 per week
            sent = start + timedelta(days=w * 7 + float(rng.uniform(0, 7)),
                                     hours=float(rng.uniform(10, 20)))
            if sent >= HISTORY_END:
                continue
            themes = (FESTIVE_THEMES if sent.month in (10, 11) and rng.random() < 0.5
                      else CAMPAIGN_THEMES)
            theme = themes[int(rng.integers(len(themes)))]
            ci += 1
            campaigns.append({
                "external_id": f"WAC{ci:04d}", "name": f"{theme} (WhatsApp) #{ci}",
                "campaign_type": "campaign", "channel": "whatsapp",
                "started_at": sent})
    campaigns.sort(key=lambda c: (c["started_at"], c["external_id"]))
    return campaigns


def _gen_wa_messages(rng: np.random.Generator, customers: list[dict[str, Any]],
                     campaigns: list[dict[str, Any]],
                     order_times: dict[int, list[datetime]]) -> list[dict[str, Any]]:
    """WhatsApp funnel: ~95% delivered, ~65% read, ~8% replied/clicked,
    plus conversation-attributed orders (click backdated before the order).
    Interakt-shaped keys: read_at / failed_at (mapper: opened_at / bounced_at)."""
    acq = np.array([c["created_at"].timestamp() for c in customers])
    inf = float("inf")
    opted = np.array([c["wa_opt"] and c["phone"] is not None for c in customers])
    revoke = np.array([c["wa_revoke_at"].timestamp() if c["wa_revoke_at"] else inf
                       for c in customers])
    messages: list[dict[str, Any]] = []
    for camp in campaigns:
        send_ts = camp["started_at"].timestamp()
        pool = np.flatnonzero((acq < send_ts) & opted & (revoke > send_ts))
        if len(pool) == 0:
            continue
        size = min(len(pool), max(10, int(len(pool) * rng.uniform(0.08, 0.15))))
        audience = rng.choice(pool, size=size, replace=False)
        for ci in sorted(int(x) for x in audience):
            c = customers[ci]
            sent = camp["started_at"] + timedelta(seconds=float(rng.uniform(0, 900)))
            m: dict[str, Any] = {
                "id": f"WAM{camp['external_id'][3:]}-{ci}",
                "campaign_id": camp["external_id"],
                "profile": {"id": f"IK{ci}", "phone": c["phone"], "email": c["email"]},
                "channel": "whatsapp", "sent_at": sent, "delivered_at": None,
                "read_at": None, "clicked_at": None, "failed_at": None}
            if rng.random() > WA_DELIVER:
                m["failed_at"] = sent + timedelta(minutes=float(rng.uniform(1, 30)))
                messages.append(m)
                continue
            delivered = sent + timedelta(seconds=float(rng.uniform(5, 120)))
            m["delivered_at"] = delivered
            times = order_times.get(ci, [])
            pos = bisect_right(times, sent)
            attributed = (pos < len(times)
                          and times[pos] <= sent + timedelta(hours=72)
                          and rng.random() < WA_ATTR)
            if attributed or rng.random() < WA_READ:
                read = delivered + timedelta(minutes=float(rng.uniform(1, 600)))
                m["read_at"] = read
                if attributed:
                    m["clicked_at"] = max(read + timedelta(minutes=2),
                                          times[pos] - timedelta(hours=float(rng.uniform(0.5, 47))))
                elif rng.random() < WA_REPLY:
                    m["clicked_at"] = read + timedelta(minutes=float(rng.uniform(2, 240)))
            messages.append(m)
    return messages


def _gen_wa_consent(customers: list[dict[str, Any]]) -> list[tuple[str, dict[str, Any], datetime]]:
    """Interakt message-level consent ledger: opt-in at first touch, STOP replies."""
    rows: list[tuple[str, dict[str, Any], datetime]] = []
    for c in customers:
        if not c["wa_opt"] or c["phone"] is None:
            continue
        profile = {"id": f"IK{c['idx']}", "phone": c["phone"], "email": c["email"]}
        granted = c["created_at"] + timedelta(minutes=10)
        eid = f"IKCON-{c['idx']}-g"
        rows.append((eid, {"id": eid, "profile": profile, "channel": "whatsapp",
                           "action": "granted", "method": "whatsapp_optin",
                           "occurred_at": _iso(granted)}, granted))
        if c["wa_revoke_at"]:
            eid = f"IKCON-{c['idx']}-r"
            rows.append((eid, {"id": eid, "profile": profile, "channel": "whatsapp",
                               "action": "revoked", "method": "stop_reply",
                               "occurred_at": _iso(c["wa_revoke_at"])}, c["wa_revoke_at"]))
    return rows


def _gen_tickets(rng: np.random.Generator,
                 orders: list[dict[str, Any]]) -> tuple[list[tuple[str, dict[str, Any], datetime]], set[int]]:
    """Gorgias tickets: ~6% of orders (RTO orders far likelier); log-normal
    resolution 4-72h with ~15% breaching 72h; CSAT on ~40% of resolved."""
    rows: list[tuple[str, dict[str, Any], datetime]] = []
    ticket_customers: set[int] = set()
    for o in orders:
        ship = o["shipment"]
        if o["cancelled"] or ship is None:
            continue
        rto = ship["rto"]
        if rng.random() >= (TICKET_RATE_RTO if rto else TICKET_RATE):
            continue
        if rto:
            anchor, cat_p = ship["rto_at"], [0.55, 0.05, 0.30, 0.10]
        elif ship["delivered_at"] is not None:
            anchor, cat_p = ship["delivered_at"], [0.15, 0.30, 0.20, 0.35]
        else:  # still in transit
            anchor, cat_p = ship["shipped_at"] + timedelta(days=4), [0.85, 0.0, 0.10, 0.05]
        opened = anchor + timedelta(hours=float(rng.uniform(2, 96)))
        category = str(rng.choice(TICKET_CATEGORIES, p=cat_p))
        channel = str(rng.choice(TICKET_CHANNELS, p=TICKET_CHANNEL_P))
        if opened >= HISTORY_END:
            continue
        first_resp: datetime | None = opened + timedelta(hours=float(rng.uniform(0.2, 8)))
        # median ~14h, sigma 1.6 -> P(>72h) ~= 0.15
        hours = float(np.clip(rng.lognormal(np.log(14.0), 1.6), 1.0, 240.0))
        resolved: datetime | None = opened + timedelta(hours=hours)
        csat = None
        if resolved >= HISTORY_END:
            status, resolved = "open", None
            if first_resp >= HISTORY_END:
                first_resp = None
        else:
            status = "resolved" if rng.random() < 0.85 else "closed"
            if rng.random() < CSAT_RATE:
                if hours <= 24:
                    csat = int(rng.choice([5, 4, 3], p=[0.55, 0.35, 0.10]))
                elif hours <= 72:
                    csat = int(rng.choice([5, 4, 3, 2], p=[0.20, 0.40, 0.25, 0.15]))
                else:
                    csat = int(rng.choice([3, 2, 1], p=[0.25, 0.35, 0.40]))
        c = o["cust"]
        guest = c["split_identity"] and o["k"] % 2 == 0
        eid = f"GT{o['external_id']}"
        ticket_customers.add(c["idx"])
        rows.append((eid, {
            "id": eid, "order_external_id": o["external_id"],
            "customer": None if guest else {"external_id": c["external_id"]},
            "email": c["email"], "phone": c["phone"],
            "channel": channel, "subject": TICKET_SUBJECTS[category],
            "category": category, "status": status,
            "opened_at": _iso(opened), "first_response_at": _iso(first_resp),
            "resolved_at": _iso(resolved), "csat": csat}, opened))
    return rows, ticket_customers


def _gen_reviews(rng: np.random.Generator, orders: list[dict[str, Any]],
                 unhappy: set[int]) -> list[tuple[str, dict[str, Any], datetime]]:
    """Judge.me reviews on ~8% of delivered orders, mean ~4.1; RTO/ticket
    customers skew low."""
    rows: list[tuple[str, dict[str, Any], datetime]] = []
    for o in orders:
        ship = o["shipment"]
        if o["cancelled"] or ship is None or ship["delivered_at"] is None:
            continue
        if rng.random() >= REVIEW_RATE:
            continue
        submitted = ship["delivered_at"] + timedelta(days=float(rng.uniform(2, 25)))
        item = next((i for i in o["items"] if i["product_external_id"]), None)
        if submitted >= HISTORY_END or item is None:
            continue
        c = o["cust"]
        if c["idx"] in unhappy:
            rating = int(rng.choice([1, 2, 3, 4, 5], p=[0.22, 0.24, 0.26, 0.18, 0.10]))
        else:
            rating = int(rng.choice([1, 2, 3, 4, 5], p=[0.015, 0.03, 0.105, 0.30, 0.55]))
        bucket = "pos" if rating >= 4 else ("mid" if rating == 3 else "neg")
        pool = REVIEW_TEXT[bucket]
        title, body = pool[int(rng.integers(len(pool)))]
        if rng.random() < 0.25:
            body = None
        guest = c["split_identity"] and o["k"] % 2 == 0
        eid = f"JR{o['external_id']}"
        rows.append((eid, {
            "id": eid, "order_external_id": o["external_id"],
            "product_external_id": item["product_external_id"],
            "reviewer": {"external_id": None if guest else c["external_id"],
                         "email": c["email"], "phone": c["phone"]},
            "rating": rating, "title": title, "body": body,
            "verified": bool(rng.random() < 0.90),
            "submitted_at": _iso(submitted)}, submitted))
    return rows


def _gen_nps(rng: np.random.Generator, customers: list[dict[str, Any]],
             order_times: dict[int, list[datetime]], unhappy: set[int]) -> list[dict[str, Any]]:
    """~5% of purchasers answer NPS; promoter-leaning with a detractor cluster
    among RTO/ticket-affected customers. Written DIRECT to core."""
    rows: list[dict[str, Any]] = []
    for c in customers:
        times = order_times.get(c["idx"])
        if not times or rng.random() >= NPS_RATE:
            continue
        responded = (times[int(rng.integers(len(times)))]
                     + timedelta(days=float(rng.uniform(3, 21))))
        if responded >= HISTORY_END:
            continue
        if c["idx"] in unhappy:
            score = int(rng.choice(11, p=[0.10, 0.10, 0.12, 0.14, 0.14, 0.12,
                                          0.10, 0.08, 0.05, 0.03, 0.02]))
        else:
            score = int(rng.choice(11, p=[0.005, 0.005, 0.01, 0.01, 0.02, 0.03,
                                          0.05, 0.09, 0.19, 0.28, 0.31]))
        comment = None
        if rng.random() < 0.40:
            band = "promoter" if score >= 9 else ("passive" if score >= 7 else "detractor")
            pool = NPS_COMMENTS[band]
            comment = pool[int(rng.integers(len(pool)))]
        rows.append({
            "external_id": f"NPS-{c['idx']}",
            "customer_external_id": c["external_id"],
            "score": score, "comment": comment,
            "channel": str(rng.choice(["post_purchase_widget", "email", "whatsapp"],
                                      p=[0.5, 0.3, 0.2])),
            "responded_at": responded})
    return rows


def _write_nps(session: Session, tenant_id: int, rows: list[dict[str, Any]]) -> int:
    existing = set(session.scalars(
        select(NpsResponse.external_id).where(NpsResponse.tenant_id == tenant_id,
                                              NpsResponse.source == "punara")))
    fresh = [r for r in rows if r["external_id"] not in existing]
    for r in fresh:
        session.add(NpsResponse(tenant_id=tenant_id, source="punara", **r))
    return len(fresh)


def _write_experiments(session: Session, tenant_id: int) -> int:
    existing = set(session.scalars(
        select(Experiment.name).where(Experiment.tenant_id == tenant_id)))
    n = 0
    for (name, hypothesis, target, status, started_ago, ran_days,
         sample, lift, significant, decision) in EXPERIMENT_FIXTURES:
        if name in existing:
            continue
        started = None if started_ago is None else HISTORY_END - timedelta(days=started_ago)
        concluded = None if (started is None or ran_days is None) else started + timedelta(days=ran_days)
        session.add(Experiment(
            tenant_id=tenant_id, name=name, hypothesis=hypothesis,
            score_target=target, status=status, started_at=started,
            concluded_at=concluded, sample_size=sample, lift_pct=lift,
            significant=significant, decision=decision, created_at=HISTORY_END))
        n += 1
    return n


def link_direct(session: Session, tenant_id: int) -> int:
    """Attach seed-time direct-to-core rows (nps_responses) to synced customers.

    Runs in the nightly AFTER identity.resolve: joins customers on
    (source='shopify', external_id == nps.customer_external_id), following
    merge pointers. Idempotent — only fills NULL customer_id. Returns rows linked.
    """
    by_ext = {c.external_id: c for c in session.scalars(
        select(Customer).where(Customer.tenant_id == tenant_id,
                               Customer.source == "shopify"))}
    linked = 0
    for row in session.scalars(select(NpsResponse).where(
            NpsResponse.tenant_id == tenant_id,
            NpsResponse.customer_id.is_(None),
            NpsResponse.customer_external_id.is_not(None))):
        c = by_ext.get(row.customer_external_id)
        while c is not None and c.merged_into_customer_id is not None:
            c = session.get(Customer, c.merged_into_customer_id)
        if c is not None:
            row.customer_id = c.id
            linked += 1
    session.commit()
    return linked


# ---------------------------------------------------------------- assembling


def _write_catalog(session: Session, tenant_id: int,
                   catalog: list[dict[str, Any]]) -> tuple[int, int]:
    existing_p = {p.external_id: p.id for p in session.scalars(
        select(Product).where(Product.tenant_id == tenant_id,
                              Product.source == "shopify"))}
    existing_v = set(session.scalars(
        select(Variant.external_id).where(Variant.tenant_id == tenant_id,
                                          Variant.source == "shopify")))
    n_p = n_v = 0
    for p in catalog:
        pid = existing_p.get(p["external_id"])
        if pid is None:
            row = Product(tenant_id=tenant_id, source="shopify",
                          external_id=p["external_id"], title=p["title"],
                          product_type=p["product_type"], vendor=p["vendor"],
                          status=p["status"])
            session.add(row)
            session.flush()
            pid = row.id
            n_p += 1
        for v in p["variants"]:
            if v["external_id"] in existing_v:
                continue
            session.add(Variant(tenant_id=tenant_id, product_id=pid, source="shopify",
                                external_id=v["external_id"], sku=v["sku"],
                                title=v["title"], price_paise=v["price_paise"],
                                compare_at_price_paise=v["compare_at_price_paise"],
                                cost_paise=v["cost_paise"], currency="INR"))
            n_v += 1
    return n_p, n_v


def _order_payload(o: dict[str, Any]) -> dict[str, Any]:
    c = o["cust"]
    guest = c["split_identity"] and o["k"] % 2 == 0  # alternate orders as guest
    return {
        "id": o["external_id"], "order_number": o["order_number"],
        "created_at": _iso(o["placed_at"]), "cancelled_at": _iso(o["cancelled_at"]),
        "customer": None if guest else {"id": c["external_id"]},
        "email": None if guest and c["phone"] else c["email"],
        "phone": c["phone"],
        "financial_status": o["financial_status"],
        "fulfillment_status": o["fulfillment_status"],
        "cod": o["cod"],
        "payment_gateway": "cod" if o["cod"] else "razorpay",
        "subtotal_paise": o["subtotal_paise"], "discount_paise": o["discount_paise"],
        "shipping_paise": o["shipping_paise"], "tax_paise": o["tax_paise"],
        "total_paise": o["total_paise"], "currency": "INR",
        "discount_codes": o["discount_codes"],
        "line_items": o["items"],
        "refunds": [{"id": f"RF{o['external_id']}{r['suffix']}",
                     "amount_paise": r["amount_paise"],
                     "refund_type": r["refund_type"],
                     "processed_at": _iso(r["processed_at"])} for r in o["refunds"]],
    }


def run(session: Session, tenant_slug: str, months: int = 24, seed: int = 42,
        customers: int = 9000) -> SeedReport:
    """Seed the synthetic universe. Idempotent; commits its own work.

    ``customers`` is an extra knob beyond the CONTRACTS.md signature (default
    matches the fixture scale) so tests can seed small universes fast.
    """
    rng = np.random.default_rng(seed)
    tenant = _get_or_create_tenant(session, tenant_slug)
    tid = tenant.id

    catalog = _gen_catalog(rng)
    custs = _gen_customers(rng, months, customers)
    orders = _gen_orders(rng, custs, catalog)
    campaigns = _gen_campaigns(rng, months)
    order_times: dict[int, list[datetime]] = {}
    for o in orders:
        if not o["cancelled"]:
            order_times.setdefault(o["cust"]["idx"], []).append(o["placed_at"])
    messages = _gen_messages(rng, custs, campaigns, order_times)

    # account-linked order stats for the shopify customer payloads
    stats: dict[int, tuple[int, int]] = {}
    for o in orders:
        c = o["cust"]
        if not (c["split_identity"] and o["k"] % 2 == 0):  # account orders only
            n, tot = stats.get(c["idx"], (0, 0))
            stats[c["idx"]] = (n + 1, tot + o["total_paise"])

    counts: dict[str, int] = {}
    counts["products"], counts["variants"] = _write_catalog(session, tid, catalog)

    counts["shopify_products"] = _insert_raw(session, tid, "shopify", "products", [
        (p["external_id"],
         {"id": p["external_id"], "title": p["title"],
          "product_type": p["product_type"], "vendor": p["vendor"],
          "status": p["status"], "variants": p["variants"]},
         _month_start(HISTORY_END, months, 0))
        for p in catalog])

    counts["shopify_customers"] = _insert_raw(session, tid, "shopify", "customers", [
        (c["external_id"],
         {"id": c["external_id"], "email": c["email"], "phone": c["phone"],
          "first_name": c["first_name"], "last_name": c["last_name"],
          "created_at": _iso(c["created_at"]),
          "accepts_marketing": c["email_opt"],
          "orders_count": stats.get(c["idx"], (0, 0))[0],
          "total_spent_paise": stats.get(c["idx"], (0, 0))[1]},
         c["created_at"])
        for c in custs])

    counts["shopify_orders"] = _insert_raw(
        session, tid, "shopify", "orders",
        [(o["external_id"], _order_payload(o), o["placed_at"]) for o in orders])

    counts["razorpay_payments"] = _insert_raw(session, tid, "razorpay", "payments", [
        (f"pay_{o['external_id']}{p['suffix']}",
         {"id": f"pay_{o['external_id']}{p['suffix']}",
          "order_external_id": o["external_id"], "method": p["method"],
          "gateway": "razorpay", "status": p["status"],
          "amount_paise": o["total_paise"], "currency": "INR",
          "failure_reason": p["failure_reason"], "created_at": _iso(p["occurred_at"])},
         p["occurred_at"])
        for o in orders for p in o["payments"]])

    counts["shiprocket_shipments"] = _insert_raw(session, tid, "shiprocket", "shipments", [
        (f"SR{o['external_id']}",
         {"id": f"SR{o['external_id']}", "order_external_id": o["external_id"],
          "courier": s["courier"], "status": s["status"], "rto": s["rto"],
          "shipped_at": _iso(s["shipped_at"]), "delivered_at": _iso(s["delivered_at"]),
          "rto_at": _iso(s["rto_at"])},
         s["shipped_at"])
        for o in orders if (s := o["shipment"]) is not None])

    counts["klaviyo_campaigns"] = _insert_raw(session, tid, "klaviyo", "campaigns", [
        (c["external_id"],
         {"id": c["external_id"], "name": c["name"],
          "campaign_type": c["campaign_type"], "channel": c["channel"],
          "subject": c["subject"], "started_at": _iso(c["started_at"])},
         c["started_at"])
        for c in campaigns])

    counts["klaviyo_messages"] = _insert_raw(session, tid, "klaviyo", "messages", [
        (m["id"],
         {**m, "sent_at": _iso(m["sent_at"]), "delivered_at": _iso(m["delivered_at"]),
          "opened_at": _iso(m["opened_at"]), "clicked_at": _iso(m["clicked_at"]),
          "bounced_at": _iso(m["bounced_at"]),
          "unsubscribed_at": _iso(m["unsubscribed_at"])},
         m["sent_at"])
        for m in messages])

    counts["klaviyo_consent"] = _insert_raw(session, tid, "klaviyo", "consent",
                                            _gen_consent(custs))

    # ---- Phase 2 universe: SEPARATE deterministic stream, fixed draw order.
    # The v0 stream above is untouched -> v0 raw records stay byte-identical.
    rng2 = np.random.default_rng([seed, 2])

    flow_campaigns, flow_messages = _gen_flows(rng2, custs, orders, order_times, months)
    counts["klaviyo_campaigns"] += _insert_raw(session, tid, "klaviyo", "campaigns", [
        (f["external_id"],
         {"id": f["external_id"], "name": f["name"],
          "campaign_type": f["campaign_type"], "channel": f["channel"],
          "subject": f["subject"], "started_at": _iso(f["started_at"])},
         f["started_at"])
        for f in flow_campaigns])
    counts["klaviyo_messages"] += _insert_raw(session, tid, "klaviyo", "messages", [
        (m["id"],
         {**m, "sent_at": _iso(m["sent_at"]), "delivered_at": _iso(m["delivered_at"]),
          "opened_at": _iso(m["opened_at"]), "clicked_at": _iso(m["clicked_at"]),
          "bounced_at": _iso(m["bounced_at"]),
          "unsubscribed_at": _iso(m["unsubscribed_at"])},
         m["sent_at"])
        for m in flow_messages])

    wa_campaigns = _gen_wa_campaigns(rng2, months)
    counts["interakt_campaigns"] = _insert_raw(session, tid, "interakt", "campaigns", [
        (c["external_id"],
         {"id": c["external_id"], "name": c["name"],
          "campaign_type": c["campaign_type"], "channel": c["channel"],
          "started_at": _iso(c["started_at"])},
         c["started_at"])
        for c in wa_campaigns])
    counts["interakt_messages"] = _insert_raw(session, tid, "interakt", "messages", [
        (m["id"],
         {**m, "sent_at": _iso(m["sent_at"]), "delivered_at": _iso(m["delivered_at"]),
          "read_at": _iso(m["read_at"]), "clicked_at": _iso(m["clicked_at"]),
          "failed_at": _iso(m["failed_at"])},
         m["sent_at"])
        for m in _gen_wa_messages(rng2, custs, wa_campaigns, order_times)])
    counts["interakt_consent"] = _insert_raw(session, tid, "interakt", "consent",
                                             _gen_wa_consent(custs))

    tickets, ticket_customers = _gen_tickets(rng2, orders)
    counts["gorgias_tickets"] = _insert_raw(session, tid, "gorgias", "tickets", tickets)

    rto_customers = {o["cust"]["idx"] for o in orders
                     if o["shipment"] is not None and o["shipment"]["rto"]}
    unhappy = rto_customers | ticket_customers
    counts["judgeme_reviews"] = _insert_raw(
        session, tid, "judgeme", "reviews", _gen_reviews(rng2, orders, unhappy))

    counts["nps_responses"] = _write_nps(
        session, tid, _gen_nps(rng2, custs, order_times, unhappy))
    counts["experiments"] = _write_experiments(session, tid)

    session.commit()
    return SeedReport(tenant_id=tid, tenant_slug=tenant_slug, months=months,
                      seed=seed, counts=counts)
