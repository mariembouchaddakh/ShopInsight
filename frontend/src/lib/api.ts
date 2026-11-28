// Client de l'API ShopInsight (FastAPI). Toutes les valeurs affichées viennent de ces réponses : rien n'est calculé ici.

export type MetricKey = "late" | "poor" | "handover"
export type Severity = "élevée" | "moyenne" | "faible"

export interface Line {
  text: string
  evidence: string[]
}

export interface Report {
  title: string
  narrative: string
  narrative_source: string
  facts: Line[]
  estimates: Line[]
  similar_experiences: Line[]
  actions: Line[]
  caveats: string[]
  meta: Record<string, unknown>
  section_titles?: Record<string, string> | null
}

export interface Evidence {
  id: string
  kind: string
  source: string
  payload: unknown
}

export interface ReportResponse {
  agent: "bo1" | "bo2" | "bo3" | "bo4"
  report: Report
  markdown: string
  evidence: Evidence[]
}

export interface ToolResponse<T> {
  agent: string
  tool: string
  result: T
  evidence: Evidence[]
}

export interface Meta {
  default_month: string
  decision_months: string[]
  metrics: Record<MetricKey, string>
  trained: boolean
  reference: string | null
  severity_rule: string | null
  detection: Record<"level" | "trend", { detector: string; params: Record<string, number>; min_history: number; description: string; persistence?: boolean }>
  test_summary: Record<"level" | "trend", { precision: number | null; recall: number | null; f1: number; alerts_per_month: number; lift: number | null }> | null
  validation: { folds: Record<string, string[]>; test: string[] }
  category_labels?: Record<string, string>
}

export interface SellerMetric {
  rate_90d: number | null
  known_n_90d: number
  rate_12m: number | null
  known_n_12m: number
  eligible: boolean
  alert_level: boolean
  severity: Severity | null
  alert_trend: boolean
  strength: boolean
}

export interface SellerRow {
  seller_id: string
  orders_12m: number
  main_category: string
  seller_state: string | null
  segment_volume: string | null
  segment_region: string | null
  metrics: Partial<Record<MetricKey, SellerMetric>>
}

export interface OverviewSummary {
  n_evaluated: number
  n_with_level_alert: number
  n_with_trend_alert: number
  n_with_any_alert: number
  level_alerts_by_top_severity: Record<Severity, number>
  n_with_strength: number
}

export interface OverviewFilters {
  month?: string
  q?: string
  limit?: number
  alerted_only?: boolean
  seller_state?: string
  region?: string
  main_category?: string
  segment?: string
  alert_status?: "any" | "level" | "trend" | "none"
  severity?: Severity
  trend?: "degradation" | "stable"
}

export interface Overview {
  decision_month: string
  decision_date: string
  reference_rates: Partial<Record<MetricKey, number | null>>
  n_sellers: number
  n_matching: number
  n_returned: number
  summary: OverviewSummary
  facets: { seller_state: string[]; segment_region: string[]; main_category: string[]; segment_volume: string[] }
  sellers: SellerRow[]
}

// ---- Positionnement concurrentiel (descriptif, 12 mois d'issues connues à la décision)
export interface RateBench {
  seller_rate: number | null
  seller_known_n: number
  rank: number | null
  n_ranked: number
  better_than_share: number | null
  group_median: number | null
  top_quartile_threshold: number | null
  top_quartile_median: number | null
}
export interface ValueBench {
  seller_value: number | null
  group_median: number | null
  top_quartile_median: number | null
}
export type DescriptiveKey = "median_price" | "freight_share" | "promised_days"
export interface GroupBench {
  label: string
  category?: string
  n_members: number
  metrics: Record<MetricKey, RateBench> & Record<DescriptiveKey, ValueBench>
  overall: { rank: number | null; n_ranked: number; in_top_quartile: boolean }
  volume_rank: number
  n_top_quartile: number
  min_known_n: number
}
export interface Competitor {
  seller_id: string
  main_category: string
  seller_state: string | null
  orders_12m: number
  rate_late: number | null
  rate_poor: number | null
  rate_handover: number | null
  known_n_late: number
  known_n_poor: number
  known_n_handover: number
  median_price: number | null
  freight_share: number | null
  promised_days: number | null
  distance: number | null
}
export interface Benchmark {
  seller_id: string
  decision_month: string
  category: GroupBench
  direct_competitors: GroupBench
  competitors: Competitor[]
  metric_labels: Record<string, string>
  definitions: Record<string, string>
  note: string
}
export interface Flows {
  origin_state: string | null
  orders_12m: number
  destinations: { state: string; orders: number; share: number }[]
  same_state_orders: number | null
  same_state_share: number | null
  n_destination_states: number
}

export interface MarketPoint {
  month: string
  reference_rate: number | null
  sellers_with_profile: number
  eligible: number
  alerts_level: number
  alerts_trend: number
  strengths: number
}

export interface Marketplace {
  available: boolean
  labels: Record<MetricKey, string>
  series: Partial<Record<MetricKey, MarketPoint[]>>
}

export interface AlertItem {
  metric: MetricKey
  family: "level" | "trend"
  severity: Severity | null
  recent_rate: number | null
  recent_known_n: number
  baseline: number | null
}

export interface AlertsList {
  decision_month: string
  eligible_sellers: Partial<Record<MetricKey, number>>
  n_alerted_sellers: number
  n_alerts: number
  listing: { seller_id: string; main_category: string; n_alerts: number; top_severity: Severity | null; alerts: AlertItem[] }[]
  severity_rule: string
}

export interface AlertHistoryRow {
  month: string
  seller_id: string
  metric: MetricKey
  family: "level" | "trend"
  detector: string
  status: "new" | "ongoing" | "resolved"
  severity: Severity | null
  recent_rate: number | null
  recent_known_n: number
  baseline: number | null
  eligible: boolean
}

export interface HistoryPoint {
  month: string
  rate_90d: number | null
  known_n: number
  reference: number | null
  alert_level: boolean
  alert_trend: boolean
}

export interface SellerHistory {
  available: boolean
  series: Partial<Record<MetricKey, HistoryPoint[]>>
}

export interface Health {
  status: "ok" | "degraded"
  agents: Record<string, { state: string; load_seconds?: number | null; error?: string | null }>
  config: Record<string, unknown>
}

export interface BO4Context {
  order: { order_id: string; as_of: string; observable_status: string; purchase_at: string | null; approved_at: string | null; delivered_at: string | null; promised_delivery_date: string | null; promised_date_exceeded: boolean | null; promise_state: "unknown" | "within_promise" | "exceeded" | "delivered_on_time" | "delivered_late"; customer_state: string | null; category: string | null; item_count: number | null; seller_count: number | null }
  timeline: { events: { event: string; at: string }[] }
  eta: { state: string; valid_current_estimate: boolean; p10_date?: string; p50_date?: string; p90_date?: string; target_coverage?: number; model?: string; message?: string }
}

export interface BO4ChatTurn { role: "user" | "assistant"; content: string }
export interface BO4Debug {
  intent: string
  intent_source: string
  selected_tools: string[]
  tool_calls: { tool: string; arguments: Record<string, unknown>; ok: boolean; source: string; result?: unknown; error?: string }[]
  provider: string
  model: string | null
  latency_ms: number
  evidence_references: string[]
  validation: { valid: boolean; problems: string[] }
  fallback_used: boolean
  fallback_reason: string | null
}
export interface BO4ChatResponse extends ReportResponse {
  answer: string
  answer_source: "llm_verified" | "deterministic_fallback"
  language: "fr" | "pt" | "en"
  debug: BO4Debug
}


// ---- Analyse stratégique et assistant : contenu validé contre les preuves déterministes
export type AiKind = "fait" | "hypothese" | "inconnu" | "piste"
export interface AiItem {
  texte: string
  type: AiKind
  preuves: string[]
}
export interface AiAction {
  faiblesse: string
  action: string
  priorite: "haute" | "moyenne" | "basse"
  levier?: "operationnel" | "catalogue_prix" | "delai_promis" | "experience_client" | null
  cible?: string | null
  impact?: string
  direction_attendue?: string
  information_manquante?: string
  preuves: string[]
}
export interface AiQuestion {
  texte: string
  preuves: string[]
}
export interface AiAnalysis {
  seller_id: string
  month: string
  model: string
  section_titles: Record<string, string>
  sections: Record<string, AiItem[]>
  actions: AiAction[]
  questions?: AiQuestion[]
  resume: string | null
  rejected: { section: string; item: unknown; problems: string[] }[]
  stats: { items_total: number; items_valid: number; items_rejected: number; grounding_rate: number | null }
  schema_ok: boolean
  mode?: "remontee" | "suivi" | null
  call: { latency_s: number; cached: boolean; cost: number; usage: Record<string, number> }
  disclaimer: string
}
export interface AiChatAnswer {
  model: string
  items: AiItem[]
  questions?: AiQuestion[]
  rejected: { item: unknown; problems: string[] }[]
  follow_up: string[]
  evidence?: Evidence[]
  mode?: "sans_ia"
  notice?: string
}
export interface GeoRow {
  orders: number
  share: number
  late_known: number
  late_rate: number | null
}
export interface SellerGeography {
  origin: { city: string; state: string; state_name: string; region: string | null; lat: number | null; lng: number | null } | null
  orders_12m: number
  points: { lat: number; lng: number; state: string; orders: number; late_known: number; late: number }[]
  states: (GeoRow & { state: string; state_name: string })[]
  regions: (GeoRow & { region: string })[]
  distance_bands: (GeoRow & { band: string })[]
  state_alerts?: { state: string; state_name: string; known_n: number; rate: number | null; reference_rate: number | null }[]
  median_distance_km: number | null
  n_states: number
}
export interface MarketGroup {
  group: number
  name: string
  n_sellers: number
  n_alerted: number
  top_categories: { category: string; sellers: number }[]
  regions: { region: string; sellers: number }[]
  median_orders_12m: number | null
  median_price: number | null
  median_promised_days: number | null
  median_freight_share: number | null
  median_same_state_share?: number | null
  traits?: string[]
  rank?: number
  orders_12m_total?: number
  rates: Partial<Record<MetricKey, { rate_12m: number | null; known_n: number }>>
}
export interface MarketMap {
  decision_month: string
  n_sellers: number
  groups: MarketGroup[]
  points: { seller_id: string; x: number; y: number; group: number; main_category: string; state: string | null; orders_12m: number; alerted: boolean; severity: Severity | null }[]
  marketplace: Partial<Record<MetricKey, { rate_12m: number | null }>>
  axes?: { plus: string; minus: string; variance_share: number | null }[]
  market_profile?: { median_price: number | null; median_promised_days: number | null; median_freight_share: number | null; median_orders_12m: number | null
    median_same_state_share: number | null; orders_12m_total: number; n_alerted: number }
}
export interface StateAlert {
  seller_id: string
  main_category: string | null
  state: string
  state_name: string
  known_n: number
  late: number
  rate: number | null
  reference_rate: number | null
  ratio: number | null
}
export interface StateAlerts {
  decision_month: string
  n_pairs_tested: number
  n_alerts: number
  n_sellers: number
  alerts: StateAlert[]
  rule: string
  note: string
}
export interface CallSeller {
  rank: number
  seller_id: string
  main_category: string
  category_label: string
  seller_state: string | null
  orders_12m: number | null
  top_severity: Severity | null
  n_alerts: number
  months_alerted_before: number
  main_metric: MetricKey
  reasons: string[]
  email: { subject: string; body: string }
  call_script: { step: string; text: string }[]
}
export interface CallList {
  decision_month: string
  n_candidates: number
  sellers: CallSeller[]
  priority_rule: string
}
type TrendPoint = { month: string; sellers_alerted?: number } & Partial<Record<MetricKey, { rate_90d: number | null; known_n: number }>>
export interface FamilyTrends {
  decision_month: string
  months: string[]
  families: { group: number; name: string; series: TrendPoint[] }[]
  marketplace: TrendPoint[]
}
export interface ChatBody {
  month?: string
  model: "a" | "b"
  question: string
  history: { role: "user" | "assistant"; content: string }[]
}
export interface Brief {
  overview: { decision_month: string; reference_rates: Partial<Record<MetricKey, number | null>>; summary: OverviewSummary; n_sellers: number }
  alerts: AlertsList
  categories: { decision_month: string }
}
export interface AiStatus {
  key_configured: boolean
  usable: boolean
  budget_usd: number
  models: Record<"a" | "b" | "judge", { id: string | null; free_verified: boolean }>
}

export type Om5Mode = "as_of" | "retrospective"
export interface Om5Kpi {
  metric_id: string
  label: string
  value: number | null
  unit: string
  numerator: number | null
  denominator: number | null
  period: string
  source: string
  available_at: string
  evidence_id: string
  quality_status: string
  mode: Om5Mode
  direction: "higher" | "lower"
}
export interface Om5Anomaly {
  metric_id: string
  label: string
  unit: string
  value: number | null
  baseline: number | null
  method: string
  robust_z: number | null
  q_value: number | null
  sample_size: number
  sufficient_n: boolean
  anomaly: boolean
  severity: "none" | "medium" | "high"
  evidence_id: string
}
export interface Om5Recommendation {
  metric_id: string
  severity: string
  priority_score: number
  recommendation: string
  justification: string
  evidence_id: string
}
export interface Om5Trace {
  kind?: "node" | "tool"
  tool: string
  status: "ok" | "error" | "skipped" | "deduplicated"
  duration_ms?: number
  reason?: string
  error?: string
}
export interface Om5ReportResponse {
  agent: "om5"
  report: Report & { meta: {
    partial: boolean
    evidence_valid: boolean
    anomalies: Om5Anomaly[]
    recommendations: Om5Recommendation[]
    tool_trace: Om5Trace[]
    agent_insights: Record<string, unknown>
    segments: Record<string, unknown>
    calls_used: number
    call_budget: number
    generation_mode: "groq" | "gemini" | "deterministic"
    llm_provider: string | null
    llm_model: string | null
    llm_latency_ms: number | null
    validation_status: "valid" | "invalid" | "unavailable" | "not_run"
    validation_errors: string[]
    fallback_used: boolean
    fallback_reason: string | null
    graph_engine: "langgraph"
    graph_retries: number
    contextual_recommendations: Om5ContextualRecommendation[]
    generated_content: Om5GeneratedContent | null
  } }
  markdown: string
  evidence: Evidence[]
}

export interface Om5ContextualRecommendation {
  title: string
  description: string
  business_justification: string
  related_anomaly: string
  relevant_segment_or_seller?: string | null
  priority_level: "haute" | "moyenne" | "basse"
  priority_score: number
  responsible_team: string
  timeframe: string
  expected_qualitative_benefit: string
  evidence_ids: string[]
}
export interface Om5GeneratedContent {
  executive_summary: string | { text: string; evidence_ids: string[] }
  executive_summary_evidence_ids?: string[]
  insights?: { section: string; text: string; evidence_ids: string[] }[]
  sections?: Record<string, { text: string; evidence_ids: string[] }[]>
  recommendations: Om5ContextualRecommendation[]
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

type Params = Record<string, string | number | boolean | null | undefined>

// ---- Données des graphiques BO1 / BO2 (endpoints /overview)
export interface Bo1Overview {
  month: string
  target: "late" | "poor"
  n_orders: number
  top10pct_size: number
  top10_recall_test: number
  top10_precision_test: number
  test_prevalence: number
  pr_auc_test: number
  histogram: { band: string; orders: number }[]
  deciles: { decile: number; observed_rate: number }[]
  states: { state: string; orders: number; share_top: number; share_month: number }[]
  listing: { order_id: string; state: string; category: string; promised_days: number; percentile: number; score: number }[]
  check: { n_labelled: number; base_rate: number; precision_top10pct: number; captured: number; positives: number; split: string } | null
  series: { month: string; orders: number; rate: number | null }[]
}

export interface Bo2Aspect {
  aspect: string
  label: string
  negative: number
  positive: number
  negative_share: number | null
  positive_share: number | null
}

export interface Bo2Overview {
  month: string
  state: string | null
  category: string | null
  n_reviews: number
  share_rated_1_2: number | null
  scores: { score: number; reviews: number }[]
  aspects: Bo2Aspect[]
  vs_baseline: { aspect: string; label: string; rate: number; baseline_rate: number; alert: boolean; q: number; count: number }[]
  baseline_months: string[]
  alerts: string[]
  trend: ({ month: string; n: number } & Record<string, number | string>)[]
  labels: Record<string, string>
  validation: {
    status: string
    reference: string
    human_check: { n_reviews: number; kappa_llm_vs_annotator_b: number; kappa_llm_vs_annotator_c: number; kappa_between_humans: number }
    target_f1: number
    per_aspect: Record<string, { f1_detection: number; f1_negative: number }>
    macro_f1_detection: number
    macro_f1_negative: number
  } | null
}

function url(path: string, params?: Params): string {
  const q = new URLSearchParams()
  for (const [k, v] of Object.entries(params ?? {})) if (v !== undefined && v !== null && v !== "") q.set(k, String(v))
  const s = q.toString()
  return s ? `${path}?${s}` : path
}

async function request<T>(path: string, init?: RequestInit, params?: Params): Promise<T> {
  const res = await fetch(url(path, params), init)
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail)
    } catch {
      /* réponse non JSON */
    }
    throw new ApiError(res.status, detail)
  }
  return res.json() as Promise<T>
}

export const api = {
  health: () => request<Health>("/api/health"),
  meta: () => request<Meta>("/api/bo3/meta"),
  overview: (p: OverviewFilters) => request<ToolResponse<Overview>>("/api/bo3/sellers", undefined, { ...p }),
  benchmark: (seller: string, month?: string) => request<ToolResponse<Benchmark>>(`/api/bo3/sellers/${seller}/benchmark`, undefined, { month }),
  marketplace: () => request<ToolResponse<Marketplace>>("/api/bo3/marketplace"),
  alerts: (p: { month?: string; metric?: MetricKey; top_k?: number }) => request<ToolResponse<AlertsList>>("/api/bo3/alerts", undefined, p),
  alertHistory: (p: { seller_id?: string; metric?: MetricKey; family?: string; status?: string; month?: string; until?: string; limit?: number }) =>
    request<ToolResponse<{ n_rows: number; rows: AlertHistoryRow[] }>>("/api/bo3/alert-history", undefined, p),
  audit: (seller: string, month?: string) => request<ReportResponse>(`/api/bo3/sellers/${seller}/audit`, undefined, { month }),
  history: (seller: string, month?: string, n_months = 18) =>
    request<ToolResponse<SellerHistory>>(`/api/bo3/sellers/${seller}/history`, undefined, { month, n_months }),
  bo3Ask: (question: string) =>
    request<ReportResponse>("/api/bo3/ask", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question }) }),
  bo1Triage: (p: { month: string; target: "late" | "poor"; top_k?: number }) => request<ReportResponse>("/api/bo1/triage", undefined, p),
  bo1Diagnosis: (orderId: string) => request<ReportResponse>(`/api/bo1/orders/${orderId}/diagnosis`),
  bo1Overview: (p: { month: string; target: "late" | "poor"; top_k?: number }) => request<Bo1Overview>("/api/bo1/overview", undefined, p),
  bo2Overview: (p: { month?: string; state?: string; category?: string }) => request<Bo2Overview>("/api/bo2/overview", undefined, p),
  bo2Report: (p: { month?: string; state?: string; category?: string }) => request<ReportResponse>("/api/bo2/report", undefined, p),
  bo2DefaultMonth: () => request<{ month: string }>("/api/bo2/default-month"),
  bo4Context: (orderId: string, asOf?: string) => request<ToolResponse<BO4Context>>(`/api/bo4/orders/${orderId}/context`, undefined, { as_of: asOf }),
  bo4Ask: (orderId: string, question: string, asOf?: string, history: BO4ChatTurn[] = [], model: "a" | "b" = "a") =>
    request<BO4ChatResponse>("/api/bo4/ask", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ order_id: orderId, question, as_of: asOf, history, model }) }),
  aiStatus: () => request<AiStatus>("/api/llm/status"),
  aiAnalysis: (seller: string, month: string | undefined, model: "a" | "b") =>
    request<AiAnalysis>(`/api/llm/sellers/${seller}/analysis`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ month, model }) }),
  aiChat: (seller: string, body: ChatBody) =>
    request<AiChatAnswer>(`/api/llm/sellers/${seller}/chat`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  marketChat: (body: ChatBody) =>
    request<AiChatAnswer>("/api/llm/chat", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  geography: (seller: string, month?: string) => request<ToolResponse<SellerGeography>>(`/api/bo3/sellers/${seller}/geography`, undefined, { month }),
  marketMap: (month?: string) => request<ToolResponse<MarketMap>>("/api/bo3/market-map", undefined, { month }),
  basemap: () => request<{ step: number; points: [number, number][] }>("/api/bo3/geo/basemap"),
  voiceTranslations: (seller: string, month?: string) =>
    request<{ available: boolean; translations: Record<string, { excerpt: string; original: string | null }> }>(`/api/bo3/sellers/${seller}/voice/translations`, undefined, { month }),
  stateAlerts: (month?: string) => request<ToolResponse<StateAlerts>>("/api/bo3/state-alerts", undefined, { month }),
  callList: (month?: string) => request<ToolResponse<CallList>>("/api/bo3/call-list", undefined, { month }),
  familyTrends: (month?: string) => request<ToolResponse<FamilyTrends>>("/api/bo3/market-map/trends", undefined, { month }),
  brief: (month?: string) => request<ToolResponse<Brief>>("/api/bo3/brief", undefined, { month }),
  om5Report: (month: string, mode: Om5Mode, include_agents = true) =>
    request<Om5ReportResponse>("/api/om5/report", undefined, { month, mode, include_agents }),
  om5Anomalies: (month: string, mode: Om5Mode) => request<{ month: string; mode: Om5Mode; anomalies: Om5Anomaly[] }>("/api/om5/anomalies", undefined, { month, mode }),
  om5Kpis: (month: string, mode: Om5Mode) => request<{ month: string; mode: Om5Mode; kpis: Om5Kpi[] }>("/api/om5/kpis", undefined, { month, mode }),
  om5Trends: (mode: Om5Mode) => request<{ mode: Om5Mode; rows: Record<string, number | string | boolean | null>[] }>("/api/om5/trends", undefined, { mode }),
}
