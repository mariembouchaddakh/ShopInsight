import type { Evidence, Om5Anomaly, Om5ContextualRecommendation, Om5Kpi, Om5Mode, Om5ReportResponse, Om5Trace } from "@/lib/api"

/**
 * Types OM5 locaux : ils décrivent des champs que l'API renvoie déjà (vérifiés sur des réponses réelles) mais que
 * `lib/api.ts` (fichier partagé) ne déclare pas. Aucun contrat d'API n'est modifié.
 */
export type { Evidence, Om5Anomaly, Om5ContextualRecommendation, Om5Kpi, Om5Mode, Om5Trace }

export type Om5Meta = Om5ReportResponse["report"]["meta"]

export interface Om5Comparison {
  metric_id: string
  label: string
  unit: string
  direction: "higher" | "lower"
  period: string
  value: number | null
  previous_period: string | null
  previous_value: number | null
  absolute_change: number | null
  relative_change_pct: number | null
  percentage_point_change: number | null
  historical_median: number | null
  year_over_year?: { absolute_change: number | null; relative_change_pct: number | null; percentage_point_change: number | null } | null
}

export interface Om5AnomalyRow extends Om5Anomaly {
  p_value?: number | null
  direction?: "higher" | "lower"
  period?: string
}

export interface Om5SegmentRow {
  segment: string
  value: number | null
  sample_size: number
  contribution_abs: number
  sufficient_n: boolean
}

export interface Om5SegmentBlock {
  evidence_id: string
  metric_id: string
  caution?: string
  segments: Record<string, Om5SegmentRow[]>
}

export interface Om5AgentInsight {
  evidence_id?: string
  result?: AgentResult | null
  error?: string
}

/** Rapport d'un agent BO (BO1/BO2 : rapport standard ; BO3 : aperçu marketplace). */
export interface AgentResult {
  title?: string
  narrative?: string
  facts?: { text: string; evidence?: string[] }[]
  estimates?: { text: string; evidence?: string[] }[]
  actions?: { text: string; evidence?: string[] }[]
  caveats?: string[]
  overview?: { summary?: { n_evaluated?: number; n_with_any_alert?: number; level_alerts_by_top_severity?: Record<string, number> }; n_sellers?: number }
  alerts?: {
    n_alerted_sellers?: number
    n_alerts?: number
    listing?: { seller_id: string; main_category?: string; n_alerts: number; top_severity?: string | null }[]
  }
}

export type TrendRow = Record<string, number | string | boolean | null>

export interface Om5View {
  month: string
  mode: Om5Mode
  title: string
  narrative: string
  meta: Om5Meta
  facts: { text: string; evidence: string[] }[]
  caveats: string[]
  comparisons: Om5Comparison[]
  anomalies: Om5AnomalyRow[]
  detected: Om5AnomalyRow[]
  segments: Record<string, Om5SegmentBlock>
  agents: Record<string, Om5AgentInsight>
  evidence: Evidence[]
  kpis: Om5Kpi[]
  trends: TrendRow[]
}
