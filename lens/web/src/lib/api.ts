/** Typed client for the Punara Lens /v1 REST API (CONTRACTS.md §3).
 *  All fetching is client-side; the build never touches the API. */

export const API_BASE =
  process.env.NEXT_PUBLIC_LENS_API ?? "http://127.0.0.1:8010";

/** Thrown when the API process is unreachable (connection refused etc.). */
export class ApiOffline extends Error {
  constructor() {
    super("Lens API offline");
    this.name = "ApiOffline";
  }
}

export class ApiError extends Error {
  constructor(public status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
  }
}

// ---- payload types (verbatim shapes from CONTRACTS.md §3) ----

export interface Tenant {
  id: number;
  slug: string;
  name: string;
  shopify_domain: string;
  base_currency: string;
  plan: string;
  status: string;
}

export interface Overview {
  as_of: string | null;
  window_months: number;
  total_revenue_paise: number;
  repeat_revenue_paise: number;
  repeat_rate: number;
  orders: number;
  customers: number;
  new_customers_last_month: number;
  aov_paise: number;
  leak_total_paise: number;
  /** v0: gravity/flow/signal/watertight/ciq_partial; v2: all nine + ciq. */
  scores: Record<string, number>;
}

export interface ScoreEntry {
  score: string;
  value: number | null;
  status: "computed" | "phase_2";
  /** numbers are 0-100 sub-scores (or *_paise / *_raw); strings are
   *  *_note siblings and ciq's coverage ("9/9"). */
  components: Record<string, number | string>;
}

export interface ScoresPayload {
  computed_at: string;
  definition_version: string;
  scores: ScoreEntry[];
}

export interface ScoreHistoryPoint {
  computed_at: string;
  value: number;
  definition_version: string;
}

export interface CohortCell {
  months_since: number;
  active_customers: number;
  retention_rate: number;
  repeat_revenue_paise: number;
}

export interface Cohort {
  cohort_month: string;
  cohort_size: number;
  cells: CohortCell[];
}

export interface RfmSegment {
  segment: string;
  customers: number;
  revenue_paise: number;
  avg_recency_days: number;
  avg_frequency: number;
  avg_monetary_paise: number;
}

export interface RfmCell {
  r_quintile: number;
  f_quintile: number;
  customers: number;
  revenue_paise: number;
}

export interface RfmPayload {
  as_of: string | null;
  segments: RfmSegment[];
  grid: RfmCell[];
}

export interface RevenueMonth {
  month: string;
  revenue_paise: number;
  repeat_revenue_paise: number;
  orders: number;
  new_customers: number;
  returning_customers: number;
  repeat_rate: number;
  aov_paise: number;
}

export interface LeakLine {
  leak_type: string;
  amount_paise: number;
  orders_affected: number;
  revenue_share: number;
}

export interface LeaksPayload {
  window_months: number;
  total_paise: number;
  annualized_paise: number;
  revenue_share: number;
  leaks: LeakLine[];
  monthly: { month: string; leak_type: string; amount_paise: number }[];
}

export interface CustomerRow {
  id: number;
  lifecycle_stage: string;
  rfm_segment: string;
  orders_count: number;
  total_spent_paise: number;
  first_order_at: string;
  last_order_at: string;
  recency_days: number;
  whatsapp_opted_in: boolean;
}

export interface CustomersPage {
  data: CustomerRow[];
  page: number;
  page_size: number;
  total: number;
}

export interface CustomerOrder {
  id: number;
  order_number: string;
  placed_at: string;
  total_paise: number;
  cod: boolean;
  financial_status: string;
  fulfillment_status: string;
}

// ---- Phase 2 (CONTRACTS.md V2.7) ----

export interface PredictionBlock {
  p_alive: number;
  expected_orders_90d: number;
  ltv_12m_paise: number;
  churn_band: string; // high | medium | low
  model_version: string;
  scored_at: string;
}

export interface TopRiskCustomer {
  customer_id: number;
  p_alive: number;
  expected_orders_90d: number;
  ltv_12m_paise: number;
  churn_band: string;
  rfm_segment: string;
  lifecycle_stage: string;
  orders_count: number;
  total_spent_paise: number;
  last_order_at?: string; // not in the V2.7 payload spec; rendered if served
}

export interface PredictionsPayload {
  model_version: string;
  scored_at: string;
  customers_scored: number;
  band_counts: Record<string, number>;
  expected_orders_90d_total: number;
  ltv_12m_deciles_paise: number[];
  at_risk_ltv_paise: number;
  top_risk: TopRiskCustomer[];
  page: number;
  page_size: number;
  total: number;
}

export interface Experiment {
  id: number;
  name: string;
  hypothesis: string | null;
  score_target: string | null;
  status: string; // draft | running | concluded
  started_at: string | null;
  concluded_at: string | null;
  sample_size: number | null;
  lift_pct: number | null;
  significant: boolean | null;
  decision: string | null; // shipped | killed | inconclusive | null
}

/** cx_facts mart row (monthly, ascending). */
export interface CxMonth {
  month: string;
  orders_delivered: number;
  median_delivery_days: number | null;
  rto_orders: number;
  rto_rate: number;
  tickets_opened: number;
  ticket_rate: number;
  median_resolution_hours: number | null;
  breach_rate: number | null;
  avg_csat: number | null;
  reviews: number;
  avg_review_rating: number | null;
  nps_responses: number;
  nps: number | null; // -100..100
}

/** messaging_facts mart row (tenant x month x channel). */
export interface MessagingMonth {
  month: string;
  channel: string; // email | sms | whatsapp
  sends: number;
  delivered: number;
  opened_or_read: number;
  clicked: number;
  bounced: number;
  bounce_rate: number;
  unsubscribed: number;
  attributed_orders: number;
  attributed_revenue_paise: number;
  revenue_per_message_paise: number;
}

export interface WhatsappSummary {
  sends: number;
  read_rate: number;
  reply_rate: number;
  attributed_revenue_paise: number;
  revenue_per_conversation_paise: number; // the Bet 6 number
}

export interface MessagingPayload {
  months: MessagingMonth[];
  whatsapp_summary: WhatsappSummary | null;
}

/** Customer-detail voice/CX rows — seam not pinned in CONTRACTS V2.7;
 *  typed from the core tables, rendered only when the API serves them. */
export interface CustomerTicket {
  id: number;
  subject?: string | null;
  category: string;
  status: string;
  opened_at: string;
  resolved_at: string | null;
  csat: number | null;
}

export interface CustomerReview {
  id: number;
  rating: number;
  title?: string | null;
  verified?: boolean;
  submitted_at: string;
}

export interface CustomerNps {
  id?: number;
  score: number;
  responded_at: string;
}

export interface CustomerDetail {
  id: number;
  name: string;
  email: string;
  phone: string;
  lifecycle_stage: string;
  rfm_segment: string;
  orders_count: number;
  total_spent_paise: number;
  first_order_at: string;
  last_order_at: string;
  consent: { email: boolean; whatsapp: boolean; sms: boolean };
  identities: { identity_type: string; identity_value: string }[];
  orders: CustomerOrder[];
  /** null before the first ml run; absent on a pre-v2 API. */
  prediction?: PredictionBlock | null;
  tickets?: CustomerTicket[];
  reviews?: CustomerReview[];
  nps?: CustomerNps[];
}

/** campaign_roi mart rows — endpoint added to CONTRACTS.md by frontend agent;
 *  every consumer degrades gracefully if the API doesn't serve it yet. */
export interface CampaignRoi {
  campaign_id: number;
  campaign_name: string;
  channel: string;
  campaign_type: string;
  sends: number;
  delivered: number;
  unique_opens: number;
  unique_clicks: number;
  unsubscribes: number;
  bounces: number;
  attributed_orders: number;
  attributed_revenue_paise: number;
  revenue_per_message_paise: number;
}

// ---- fetch core ----

async function get<T>(path: string): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  } catch {
    throw new ApiOffline(); // connection refused / DNS / CORS -> offline panel
  }
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      detail = ((await res.json()) as { detail?: string }).detail ?? detail;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

const data = async <T>(path: string): Promise<T> =>
  (await get<{ data: T }>(path)).data;

// ---- endpoints ----

export const getTenants = () => data<Tenant[]>("/v1/tenants");
export const getOverview = (t: number) => data<Overview>(`/v1/tenants/${t}/overview`);
export const getScores = (t: number) => data<ScoresPayload>(`/v1/tenants/${t}/scores`);
export const getScoreHistory = (t: number, name: string) =>
  data<ScoreHistoryPoint[]>(`/v1/tenants/${t}/scores/${name}/history`);
export const getCohorts = (t: number) =>
  data<{ cohorts: Cohort[] }>(`/v1/tenants/${t}/cohorts`);
export const getRfm = (t: number) => data<RfmPayload>(`/v1/tenants/${t}/rfm`);
export const getRevenue = (t: number) => data<RevenueMonth[]>(`/v1/tenants/${t}/revenue`);
export const getLeaks = (t: number) => data<LeaksPayload>(`/v1/tenants/${t}/leaks`);

export const getCustomers = (
  t: number,
  opts: { segment?: string; page?: number; page_size?: number } = {},
) => {
  const q = new URLSearchParams();
  if (opts.segment) q.set("segment", opts.segment);
  if (opts.page) q.set("page", String(opts.page));
  if (opts.page_size) q.set("page_size", String(opts.page_size));
  const qs = q.toString();
  return get<CustomersPage>(`/v1/tenants/${t}/customers${qs ? `?${qs}` : ""}`);
};

export const getCustomer = (t: number, key: number) =>
  data<CustomerDetail>(`/v1/tenants/${t}/customers/${key}`);

/** null on 404: endpoint not on this API build, or no data yet
 *  (e.g. predictions before the first ml run). */
async function dataOr404<T>(path: string): Promise<T | null> {
  try {
    return await data<T>(path);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) return null;
    throw e;
  }
}

export const getCampaigns = (t: number) =>
  dataOr404<CampaignRoi[]>(`/v1/tenants/${t}/campaigns`);

export const getPredictions = (t: number, page = 1, page_size = 50) =>
  dataOr404<PredictionsPayload>(
    `/v1/tenants/${t}/predictions?page=${page}&page_size=${page_size}`,
  );

export const getExperiments = (t: number) =>
  dataOr404<Experiment[]>(`/v1/tenants/${t}/experiments`);

export const getCx = (t: number) => dataOr404<CxMonth[]>(`/v1/tenants/${t}/cx`);

/** CONTRACTS pins "rows plus a whatsapp_summary object" but not the key the
 *  rows hang off — normalize the plausible spellings once, here. */
export async function getMessaging(t: number): Promise<MessagingPayload | null> {
  const raw = await dataOr404<unknown>(`/v1/tenants/${t}/messaging`);
  if (raw == null) return null;
  if (Array.isArray(raw))
    return { months: raw as MessagingMonth[], whatsapp_summary: null };
  const o = raw as Record<string, unknown>;
  const months = (o.months ?? o.rows ?? o.facts ?? []) as MessagingMonth[];
  const summary = (o.whatsapp_summary as WhatsappSummary | undefined) ?? null;
  return { months, whatsapp_summary: summary };
}

// ---- default tenant (the seeded demo tenant is tenants[0]) ----

let tenantPromise: Promise<Tenant | null> | null = null;

export function firstTenant(): Promise<Tenant | null> {
  if (!tenantPromise) {
    tenantPromise = getTenants()
      .then((ts) => ts[0] ?? null)
      .catch((e) => {
        tenantPromise = null; // don't cache failures
        throw e;
      });
  }
  return tenantPromise;
}
