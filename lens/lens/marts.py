"""Mart builds: events/dims/facts -> the six marts, inside DuckDB.

Semantics (documented once, used everywhere):
- "valid order" = fact_orders row with cancelled_at IS NULL. Revenue counts
  placed order value regardless of payment state (v0 honesty: what leaks is
  measured by leak_facts, not silently excluded from revenue).
- oi = customer_order_index, falling back to a deterministic ROW_NUMBER per
  customer for rows the connector has not indexed. oi > 1 == repeat order.
- as_of / clock = MAX(placed_at) for the tenant, never wall clock, so seeded
  data and tests are deterministic.
- repeat_rate = repeat_revenue / total_revenue (matches the /revenue contract
  example arithmetic).
- Leak attribution (honest rules):
  * rto_cod: full total_paise of COD orders whose shipment RTO'd, in the month
    of rto_at (fallback shipped_at, then placed_at). No recovered-value data
    in v0, so nothing is netted out.
  * failed_payments: one loss per order — MAX failed attempt amount — only for
    orders never subsequently paid (no captured payment AND financial_status
    not paid/refunded), in the month of the last failed attempt. Orderless
    failed attempts each count once.
  * discount_abuse: per valid order, discount beyond 30% of subtotal
    (integer paise arithmetic), in the month placed.
  * preventable_churn: per slipping CUSTOMER (their latest slipping month in
    retention_facts, repeat customers only — cumulative_orders >= 2), their
    lifetime monthly run-rate (cumulative_revenue // months since acquisition,
    inclusive) — the expected value the business is currently not collecting.
    orders_affected = 0.

ponytail: marts are full DELETE+INSERT per tenant per build; incremental
builds are the upgrade when tenants outgrow single-file DuckDB.
"""

from __future__ import annotations

from .olap import get_conn

# Shared CTE fragment: valid orders with a deterministic order index.
_O = """
    SELECT order_id, customer_id, placed_at, total_paise, subtotal_paise,
           discount_paise, cod, financial_status,
           COALESCE(customer_order_index,
                    CASE WHEN customer_id IS NULL THEN 1
                         ELSE ROW_NUMBER() OVER (PARTITION BY customer_id
                                                 ORDER BY placed_at, order_id) END
           ) AS oi
    FROM fact_orders WHERE tenant_id = $t AND cancelled_at IS NULL
"""

_SEGMENT_CASE = """
    CASE
      WHEN r_q >= 4 AND f_q >= 4 THEN 'champions'
      WHEN r_q >= 3 AND f_q >= 4 THEN 'loyal'
      WHEN r_q = 1 AND f_q >= 4 THEN 'cant_lose'
      WHEN r_q <= 2 AND f_q >= 3 THEN 'at_risk'
      WHEN r_q >= 4 AND f_q BETWEEN 2 AND 3 THEN 'potential_loyalist'
      WHEN r_q >= 4 AND f_q = 1 THEN 'new'
      WHEN r_q = 3 AND f_q <= 2 THEN 'promising'
      WHEN r_q = 3 AND f_q = 3 THEN 'needs_attention'
      WHEN r_q = 2 AND f_q <= 2 THEN 'about_to_sleep'
      ELSE 'hibernating'
    END
"""

_RFM_CURRENT = f"""
INSERT INTO rfm_current
WITH b AS (
  SELECT MAX(placed_at)::DATE AS as_of
  FROM fact_orders WHERE tenant_id = $t AND cancelled_at IS NULL
),
agg AS (
  SELECT o.customer_id,
         date_diff('day', MAX(o.placed_at)::DATE, b.as_of) AS recency_days,
         COUNT(*) AS frequency,
         SUM(o.total_paise) AS monetary_paise,
         b.as_of AS as_of
  FROM ({_O}) o CROSS JOIN b
  WHERE o.customer_id IS NOT NULL
  GROUP BY o.customer_id, b.as_of
),
q AS (
  -- tie-aware quintiles: equal raw values share a bucket (min-rank, so the
  -- 70%+ frequency=1 tie is always f_q=1 and can never read as 'champions').
  -- NTILE would split ties across buckets arbitrarily; CUME_DIST would push
  -- a heavy bottom tie UP into bucket 4. PERCENT_RANK is deterministic
  -- without a tiebreak.
  SELECT *,
    LEAST(5, 1 + CAST(FLOOR(5 * PERCENT_RANK() OVER (ORDER BY recency_days DESC)) AS TINYINT)) AS r_q,
    LEAST(5, 1 + CAST(FLOOR(5 * PERCENT_RANK() OVER (ORDER BY frequency)) AS TINYINT)) AS f_q,
    LEAST(5, 1 + CAST(FLOOR(5 * PERCENT_RANK() OVER (ORDER BY monetary_paise)) AS TINYINT)) AS m_q
  FROM agg
)
SELECT $t, q.customer_id, q.recency_days, q.frequency, q.monetary_paise,
       q.r_q, q.f_q, q.m_q, {_SEGMENT_CASE} AS rfm_segment,
       c.lifecycle_stage, c.whatsapp_opted_in, q.as_of
FROM q JOIN dim_customers c
  ON c.tenant_id = $t AND c.customer_id = q.customer_id
"""

_COHORT_RETENTION = f"""
INSERT INTO cohort_retention
WITH o AS ({_O}),
oc AS (SELECT * FROM o WHERE customer_id IS NOT NULL),
firsts AS (
  SELECT customer_id, date_trunc('month', MIN(placed_at))::DATE AS cohort_month
  FROM oc GROUP BY 1
),
sizes AS (SELECT cohort_month, COUNT(*) AS cohort_size FROM firsts GROUP BY 1),
cell AS (
  SELECT f.cohort_month,
         date_diff('month', f.cohort_month,
                   date_trunc('month', oc.placed_at)::DATE) AS months_since,
         COUNT(DISTINCT oc.customer_id) AS active_customers,
         COUNT(*) AS orders_n,
         COALESCE(SUM(oc.total_paise) FILTER (WHERE oc.oi > 1), 0) AS repeat_rev
  FROM oc JOIN firsts f USING (customer_id)
  GROUP BY 1, 2
)
SELECT $t, c.cohort_month, c.months_since, s.cohort_size, c.active_customers,
       c.active_customers / s.cohort_size::DOUBLE AS retention_rate,
       c.repeat_rev, c.orders_n / c.active_customers::DOUBLE
FROM cell c JOIN sizes s USING (cohort_month)
"""

_RETENTION_FACTS = f"""
INSERT INTO retention_facts
WITH o AS ({_O}),
oc AS (SELECT * FROM o WHERE customer_id IS NOT NULL),
firsts AS (
  SELECT customer_id, date_trunc('month', MIN(placed_at))::DATE AS acq
  FROM oc GROUP BY 1
),
b AS (SELECT date_trunc('month', MAX(placed_at))::DATE AS max_month FROM oc),
spine AS (
  SELECT customer_id, acq, CAST(m AS DATE) AS month FROM (
    SELECT f.customer_id, f.acq,
           unnest(generate_series(f.acq::TIMESTAMP, b.max_month::TIMESTAMP,
                                  INTERVAL 1 MONTH)) AS m
    FROM firsts f CROSS JOIN b
  )
),
om AS (
  SELECT customer_id, date_trunc('month', placed_at)::DATE AS month,
         COUNT(*) AS n, SUM(total_paise) AS rev, MAX(placed_at) AS last_at
  FROM oc GROUP BY 1, 2
),
rto AS (
  -- one row per order (multi-shipment orders must not double-count)
  SELECT ord.customer_id,
         date_trunc('month', COALESCE(s.rto_at, s.shipped_at, ord.placed_at))::DATE AS month,
         COUNT(*) AS n
  FROM (SELECT order_id, MIN(rto_at) AS rto_at, MIN(shipped_at) AS shipped_at
        FROM fact_shipments WHERE tenant_id = $t AND rto GROUP BY 1) s
  JOIN fact_orders ord ON ord.tenant_id = $t AND ord.order_id = s.order_id
  WHERE ord.customer_id IS NOT NULL
  GROUP BY 1, 2
),
ref AS (
  SELECT customer_id, date_trunc('month', processed_at)::DATE AS month,
         SUM(amount_paise) AS amt
  FROM fact_refunds WHERE tenant_id = $t AND customer_id IS NOT NULL
  GROUP BY 1, 2
),
j AS (
  SELECT sp.customer_id, sp.month, sp.acq,
         COALESCE(om.n, 0) AS orders_in_month,
         COALESCE(om.rev, 0) AS rev_in_month,
         SUM(COALESCE(om.n, 0)) OVER w AS cum_orders,
         SUM(COALESCE(om.rev, 0)) OVER w AS cum_rev,
         MAX(om.last_at) OVER w AS last_order_at,
         COALESCE(rto.n, 0) AS rto_n, COALESCE(ref.amt, 0) AS ref_amt
  FROM spine sp
  LEFT JOIN om  ON om.customer_id = sp.customer_id AND om.month = sp.month
  LEFT JOIN rto ON rto.customer_id = sp.customer_id AND rto.month = sp.month
  LEFT JOIN ref ON ref.customer_id = sp.customer_id AND ref.month = sp.month
  WINDOW w AS (PARTITION BY sp.customer_id ORDER BY sp.month ROWS UNBOUNDED PRECEDING)
)
SELECT $t, customer_id, month, orders_in_month, rev_in_month,
       cum_orders, cum_rev,
       -- lifecycle snapshot at month end, same rules the connector applies live
       CASE
         WHEN dsl > 365 THEN 'lost'
         WHEN dsl > 180 THEN 'dormant'
         WHEN dsl >= 90 THEN
           CASE WHEN dsl < 120 AND cum_orders >= 4 THEN 'loyal' ELSE 'slipping' END
         WHEN cum_orders >= 4 THEN 'loyal'
         WHEN cum_orders >= 2 THEN 'active'
         ELSE 'new'
       END AS lifecycle_stage,
       dsl, orders_in_month > 0, rto_n, ref_amt, acq
FROM (SELECT *, date_diff('day', last_order_at::DATE, last_day(month)) AS dsl FROM j)
"""

# attribution = last click <= 7d before the order (CONTRACTS §4.3)
_CAMPAIGN_ROI = f"""
INSERT INTO campaign_roi
WITH m AS (SELECT * FROM fact_messages WHERE tenant_id = $t),
agg AS (
  SELECT campaign_id, COUNT(*) AS sends, COUNT(delivered_at) AS delivered,
         COUNT(opened_at) AS unique_opens, COUNT(clicked_at) AS unique_clicks,
         COUNT(unsubscribed_at) AS unsubscribes, COUNT(bounced_at) AS bounces
  FROM m WHERE campaign_id IS NOT NULL GROUP BY 1
),
o AS (SELECT * FROM ({_O}) WHERE customer_id IS NOT NULL),
clicks AS (
  SELECT campaign_id, customer_id, clicked_at FROM m
  WHERE clicked_at IS NOT NULL AND campaign_id IS NOT NULL AND customer_id IS NOT NULL
),
attr AS (
  SELECT o.order_id, o.total_paise, c.campaign_id,
         ROW_NUMBER() OVER (PARTITION BY o.order_id ORDER BY c.clicked_at DESC) AS rn
  FROM o JOIN clicks c
    ON c.customer_id = o.customer_id
   AND c.clicked_at <= o.placed_at
   AND c.clicked_at >= o.placed_at - INTERVAL 7 DAY
),
attr1 AS (
  SELECT campaign_id, COUNT(*) AS n, SUM(total_paise) AS rev
  FROM attr WHERE rn = 1 GROUP BY 1
)
SELECT $t, dc.campaign_id, dc.name, dc.channel, dc.campaign_type,
       COALESCE(a.sends, 0), COALESCE(a.delivered, 0), COALESCE(a.unique_opens, 0),
       COALESCE(a.unique_clicks, 0), COALESCE(a.unsubscribes, 0),
       COALESCE(a.bounces, 0), COALESCE(t1.n, 0), COALESCE(t1.rev, 0),
       CASE WHEN COALESCE(a.sends, 0) = 0 THEN 0
            ELSE COALESCE(t1.rev, 0) // a.sends END
FROM dim_campaigns dc
LEFT JOIN agg a ON a.campaign_id = dc.campaign_id
LEFT JOIN attr1 t1 ON t1.campaign_id = dc.campaign_id
WHERE dc.tenant_id = $t
"""

_LEAK_FACTS = f"""
INSERT INTO leak_facts
WITH mrev AS (
  SELECT date_trunc('month', placed_at)::DATE AS month, SUM(total_paise) AS rev
  FROM fact_orders WHERE tenant_id = $t AND cancelled_at IS NULL GROUP BY 1
),
rto AS (
  -- collapse shipments to one row per order first: a re-shipped order must
  -- not count its full value twice
  SELECT date_trunc('month', COALESCE(s.rto_at, s.shipped_at, o.placed_at))::DATE AS month,
         SUM(o.total_paise) AS amt, COUNT(*) AS n
  FROM (SELECT order_id, MIN(rto_at) AS rto_at, MIN(shipped_at) AS shipped_at
        FROM fact_shipments WHERE tenant_id = $t AND rto GROUP BY 1) s
  JOIN fact_orders o ON o.tenant_id = $t AND o.order_id = s.order_id
  WHERE o.cod
  GROUP BY 1
),
f0 AS (
  SELECT p.order_id, MAX(p.amount_paise) AS amt, MAX(p.occurred_at) AS occurred
  FROM fact_payments p
  JOIN fact_orders o ON o.tenant_id = p.tenant_id AND o.order_id = p.order_id
  WHERE p.tenant_id = $t AND p.status = 'failed'
    AND o.financial_status NOT IN ('paid', 'partially_refunded', 'refunded')
    AND NOT EXISTS (SELECT 1 FROM fact_payments c
                    WHERE c.tenant_id = p.tenant_id AND c.order_id = p.order_id
                      AND c.status = 'captured')
  GROUP BY p.order_id
),
f1 AS (
  SELECT CAST(NULL AS BIGINT) AS order_id, amount_paise AS amt, occurred_at AS occurred
  FROM fact_payments WHERE tenant_id = $t AND status = 'failed' AND order_id IS NULL
),
failed AS (
  SELECT date_trunc('month', occurred)::DATE AS month, SUM(amt) AS amt, COUNT(*) AS n
  FROM (SELECT * FROM f0 UNION ALL SELECT * FROM f1) GROUP BY 1
),
disc AS (
  SELECT date_trunc('month', placed_at)::DATE AS month,
         SUM(discount_paise - (subtotal_paise * 3) // 10) AS amt, COUNT(*) AS n
  FROM fact_orders
  WHERE tenant_id = $t AND cancelled_at IS NULL AND subtotal_paise > 0
    AND discount_paise > (subtotal_paise * 3) // 10
  GROUP BY 1
),
churn AS (
  -- per-customer, not per customer-month: one leak entry per slipping
  -- customer (their latest slipping month), and only customers with a real
  -- trailing run-rate (>= 2 orders). The per-month accrual booked ~40% of
  -- revenue as leak.
  SELECT month,
         SUM(cumulative_revenue_paise
             // (date_diff('month', acquisition_month, month) + 1)) AS amt
  FROM (
    SELECT customer_id, month, cumulative_revenue_paise, acquisition_month
    FROM retention_facts
    WHERE tenant_id = $t AND lifecycle_stage = 'slipping' AND cumulative_orders >= 2
    QUALIFY ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY month DESC) = 1
  )
  GROUP BY 1
),
u AS (
            SELECT month, 'rto_cod'           AS leak_type, amt, n FROM rto
  UNION ALL SELECT month, 'failed_payments'   AS leak_type, amt, n FROM failed
  UNION ALL SELECT month, 'discount_abuse'    AS leak_type, amt, n FROM disc
  UNION ALL SELECT month, 'preventable_churn' AS leak_type, amt, 0 FROM churn
)
SELECT $t, u.month, u.leak_type, u.amt, u.n,
       CASE WHEN COALESCE(m.rev, 0) = 0 THEN 0.0
            ELSE u.amt / m.rev::DOUBLE END AS revenue_share
FROM u LEFT JOIN mrev m USING (month)
WHERE u.amt > 0
"""

_EXECUTIVE_KPIS = f"""
INSERT INTO executive_kpis
WITH o AS ({_O}),
firsts AS (
  SELECT customer_id, date_trunc('month', MIN(placed_at))::DATE AS acq
  FROM o WHERE customer_id IS NOT NULL GROUP BY 1
),
mon AS (
  SELECT date_trunc('month', placed_at)::DATE AS month,
         SUM(total_paise) AS rev,
         COALESCE(SUM(total_paise) FILTER (WHERE oi > 1), 0) AS rrev,
         COUNT(*) AS n_orders
  FROM o GROUP BY 1
),
cmon AS (
  SELECT date_trunc('month', o.placed_at)::DATE AS month,
         COUNT(DISTINCT o.customer_id)
           FILTER (WHERE f.acq = date_trunc('month', o.placed_at)::DATE) AS newc,
         COUNT(DISTINCT o.customer_id)
           FILTER (WHERE f.acq < date_trunc('month', o.placed_at)::DATE) AS retc
  FROM o JOIN firsts f USING (customer_id)
  WHERE o.customer_id IS NOT NULL GROUP BY 1
),
ref AS (
  SELECT date_trunc('month', processed_at)::DATE AS month, SUM(amount_paise) AS amt
  FROM fact_refunds WHERE tenant_id = $t GROUP BY 1
),
disc AS (
  SELECT date_trunc('month', placed_at)::DATE AS month, SUM(discount_paise) AS amt
  FROM fact_orders WHERE tenant_id = $t AND cancelled_at IS NULL GROUP BY 1
),
lf AS (
  SELECT month,
         COALESCE(SUM(amount_paise) FILTER (WHERE leak_type = 'rto_cod'), 0) AS rto,
         COALESCE(SUM(amount_paise) FILTER (WHERE leak_type = 'failed_payments'), 0) AS fp,
         SUM(amount_paise) AS total
  FROM leak_facts WHERE tenant_id = $t GROUP BY 1
)
SELECT $t, m.month, m.rev, m.rrev,
       CASE WHEN m.rev = 0 THEN 0.0 ELSE m.rrev / m.rev::DOUBLE END AS repeat_rate,
       m.n_orders, m.rev // m.n_orders AS aov_paise,
       COALESCE(c.newc, 0), COALESCE(c.retc, 0),
       COALESCE(l.rto, 0), COALESCE(l.fp, 0), COALESCE(r.amt, 0),
       COALESCE(d.amt, 0), COALESCE(l.total, 0)
FROM mon m
LEFT JOIN cmon c USING (month)
LEFT JOIN ref r USING (month)
LEFT JOIN disc d USING (month)
LEFT JOIN lf l USING (month)
"""

# ---------------------------------------------------------------- Phase 2 marts
# Semantics (CONTRACTS V2.5):
# - cx_facts month spine = union of activity months (delivery, rto, ticket
#   open/resolve, review, nps, orders placed). rto_rate = rto orders / orders
#   that reached a terminal outcome that month (delivered + rto). breach =
#   resolution strictly > 72h, over tickets RESOLVED in the month.
# - messaging_facts attribution: last click <= 7d before the order PER CHANNEL
#   (an order can credit one campaign per channel); revenue lands in the
#   order's placed month. revenue_per_message_paise = attributed revenue //
#   delivered — for whatsapp this IS revenue-per-conversation (Bet 6); a
#   bounced send never opened a conversation, so `delivered` is the honest
#   denominator on every channel.
# - automation_facts: campaign_roi rows (v1 single-winner attribution) mapped
#   to the six canonical moments via flow external ids KLF-01/02/03; the other
#   three moments have no covering flow in the seed, by design.
#   automated_revenue_share is per-row: this moment's attributed revenue over
#   ALL message-attributed revenue (sum the covered rows for Autopilot's
#   tenant-level share).

_CX_FACTS = """
INSERT INTO cx_facts
WITH dlv AS (
  -- shipments collapsed to one row per order before anything else (v0 lesson)
  SELECT date_trunc('month', delivered_at)::DATE AS month, COUNT(*) AS n,
         median(date_diff('day', shipped_at, delivered_at)) AS med_days
  FROM (SELECT order_id, MIN(shipped_at) AS shipped_at, MIN(delivered_at) AS delivered_at
        FROM fact_shipments WHERE tenant_id = $t AND delivered_at IS NOT NULL
        GROUP BY 1)
  GROUP BY 1
),
rto AS (
  SELECT date_trunc('month', COALESCE(rto_at, shipped_at))::DATE AS month, COUNT(*) AS n
  FROM (SELECT order_id, MIN(rto_at) AS rto_at, MIN(shipped_at) AS shipped_at
        FROM fact_shipments WHERE tenant_id = $t AND rto GROUP BY 1)
  GROUP BY 1
),
ord AS (
  SELECT date_trunc('month', placed_at)::DATE AS month, COUNT(*) AS n
  FROM fact_orders WHERE tenant_id = $t AND cancelled_at IS NULL GROUP BY 1
),
tik AS (
  SELECT date_trunc('month', opened_at)::DATE AS month, COUNT(*) AS n
  FROM fact_tickets WHERE tenant_id = $t GROUP BY 1
),
res AS (
  SELECT date_trunc('month', resolved_at)::DATE AS month,
         median(date_diff('second', opened_at, resolved_at) / 3600.0) AS med_hours,
         AVG(CASE WHEN date_diff('second', opened_at, resolved_at) > 72 * 3600
                  THEN 1.0 ELSE 0.0 END) AS breach,
         AVG(csat) AS avg_csat
  FROM fact_tickets WHERE tenant_id = $t AND resolved_at IS NOT NULL GROUP BY 1
),
rvw AS (
  SELECT date_trunc('month', submitted_at)::DATE AS month, COUNT(*) AS n,
         AVG(rating) AS avg_rating
  FROM fact_reviews WHERE tenant_id = $t GROUP BY 1
),
np AS (
  SELECT date_trunc('month', responded_at)::DATE AS month, COUNT(*) AS n,
         100.0 * (AVG(CASE WHEN score >= 9 THEN 1.0 ELSE 0.0 END)
                - AVG(CASE WHEN score <= 6 THEN 1.0 ELSE 0.0 END)) AS nps
  FROM fact_nps WHERE tenant_id = $t GROUP BY 1
),
months AS (
  SELECT month FROM dlv UNION SELECT month FROM rto UNION SELECT month FROM ord
  UNION SELECT month FROM tik UNION SELECT month FROM res
  UNION SELECT month FROM rvw UNION SELECT month FROM np
)
SELECT $t, month,
       COALESCE(dlv.n, 0), dlv.med_days,
       COALESCE(rto.n, 0),
       CASE WHEN COALESCE(dlv.n, 0) + COALESCE(rto.n, 0) = 0 THEN NULL
            ELSE COALESCE(rto.n, 0) / (COALESCE(dlv.n, 0) + COALESCE(rto.n, 0))::DOUBLE END,
       COALESCE(tik.n, 0),
       CASE WHEN COALESCE(ord.n, 0) = 0 THEN NULL
            ELSE COALESCE(tik.n, 0) / ord.n::DOUBLE END,
       res.med_hours, res.breach, res.avg_csat,
       COALESCE(rvw.n, 0), rvw.avg_rating,
       COALESCE(np.n, 0), np.nps
FROM months
LEFT JOIN dlv USING (month) LEFT JOIN rto USING (month) LEFT JOIN ord USING (month)
LEFT JOIN tik USING (month) LEFT JOIN res USING (month) LEFT JOIN rvw USING (month)
LEFT JOIN np USING (month)
WHERE month IS NOT NULL
"""

_MESSAGING_FACTS = f"""
INSERT INTO messaging_facts
WITH m AS (SELECT * FROM fact_messages WHERE tenant_id = $t),
agg AS (
  SELECT date_trunc('month', sent_at)::DATE AS month, channel,
         COUNT(*) AS sends, COUNT(delivered_at) AS delivered,
         COUNT(opened_at) AS opened_or_read, COUNT(clicked_at) AS clicked,
         COUNT(bounced_at) AS bounced, COUNT(unsubscribed_at) AS unsubscribed
  FROM m GROUP BY 1, 2
),
o AS (SELECT * FROM ({_O}) WHERE customer_id IS NOT NULL),
clicks AS (
  SELECT customer_id, channel, clicked_at FROM m
  WHERE clicked_at IS NOT NULL AND customer_id IS NOT NULL
),
attr AS (
  -- per-channel last click <= 7d before the order (CONTRACTS V2.5)
  SELECT o.order_id, o.total_paise, o.placed_at, c.channel,
         ROW_NUMBER() OVER (PARTITION BY o.order_id, c.channel
                            ORDER BY c.clicked_at DESC) AS rn
  FROM o JOIN clicks c
    ON c.customer_id = o.customer_id
   AND c.clicked_at <= o.placed_at
   AND c.clicked_at >= o.placed_at - INTERVAL 7 DAY
),
attr1 AS (
  SELECT date_trunc('month', placed_at)::DATE AS month, channel,
         COUNT(*) AS n, SUM(total_paise) AS rev
  FROM attr WHERE rn = 1 GROUP BY 1, 2
)
SELECT $t, month, channel,
       COALESCE(a.sends, 0), COALESCE(a.delivered, 0),
       COALESCE(a.opened_or_read, 0), COALESCE(a.clicked, 0),
       COALESCE(a.bounced, 0),
       CASE WHEN COALESCE(a.sends, 0) = 0 THEN 0.0
            ELSE a.bounced / a.sends::DOUBLE END,
       COALESCE(a.unsubscribed, 0),
       COALESCE(t1.n, 0), COALESCE(t1.rev, 0),
       CASE WHEN COALESCE(a.delivered, 0) = 0 THEN 0
            ELSE COALESCE(t1.rev, 0) // a.delivered END
FROM agg a FULL JOIN attr1 t1 USING (month, channel)
"""

# canonical high-value lifecycle moments (CONTRACTS V2.4/V2.5); the seed covers
# exactly the first three via klaviyo flows KLF-01/02/03.
MOMENTS = ("welcome", "post_purchase", "winback", "replenishment",
           "cod_confirmation", "abandoned_checkout")

_AUTOMATION_FACTS = """
INSERT INTO automation_facts
WITH tot AS (
  SELECT COALESCE(SUM(attributed_revenue_paise), 0) AS all_rev
  FROM campaign_roi WHERE tenant_id = $t
),
cov AS (
  SELECT mm.moment, dc.campaign_id, r.sends, r.attributed_orders,
         r.attributed_revenue_paise
  FROM (VALUES ('welcome', 'KLF-01'), ('post_purchase', 'KLF-02'),
               ('winback', 'KLF-03'), ('replenishment', NULL),
               ('cod_confirmation', NULL), ('abandoned_checkout', NULL)
       ) AS mm(moment, ext)
  LEFT JOIN dim_campaigns dc
    ON dc.tenant_id = $t AND dc.external_id = mm.ext AND dc.campaign_type = 'flow'
  LEFT JOIN campaign_roi r
    ON r.tenant_id = $t AND r.campaign_id = dc.campaign_id
)
SELECT $t, c.moment, c.campaign_id IS NOT NULL, c.campaign_id,
       COALESCE(c.sends, 0), COALESCE(c.attributed_orders, 0),
       COALESCE(c.attributed_revenue_paise, 0),
       CASE WHEN t.all_rev = 0 THEN 0.0
            ELSE COALESCE(c.attributed_revenue_paise, 0) / t.all_rev::DOUBLE END
FROM cov c CROSS JOIN tot t
"""

_EXPERIMENT_FACTS = """
INSERT INTO experiment_facts
SELECT tenant_id, experiment_id, name, score_target, status, decision,
       started_at, concluded_at, date_trunc('month', started_at)::DATE,
       sample_size, lift_pct, significant,
       CASE WHEN started_at IS NULL OR concluded_at IS NULL THEN NULL
            ELSE date_diff('day', started_at, concluded_at) END
FROM fact_experiments WHERE tenant_id = $t
"""

# build order matters: leak_facts reads retention_facts; executive_kpis reads
# leak_facts; automation_facts reads campaign_roi.
_MARTS: list[tuple[str, str]] = [
    ("rfm_current", _RFM_CURRENT),
    ("cohort_retention", _COHORT_RETENTION),
    ("retention_facts", _RETENTION_FACTS),
    ("campaign_roi", _CAMPAIGN_ROI),
    ("leak_facts", _LEAK_FACTS),
    ("executive_kpis", _EXECUTIVE_KPIS),
    ("cx_facts", _CX_FACTS),
    ("messaging_facts", _MESSAGING_FACTS),
    ("automation_facts", _AUTOMATION_FACTS),
    ("experiment_facts", _EXPERIMENT_FACTS),
]


def build(tenant_id: int) -> None:
    """Full-replace all ten marts for this tenant. Idempotent."""
    con = get_conn()
    try:
        for name, sql in _MARTS:
            con.execute(f"DELETE FROM {name} WHERE tenant_id = ?", [tenant_id])
            con.execute(sql, {"t": tenant_id})
    finally:
        con.close()
