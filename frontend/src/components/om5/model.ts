import { catLabel } from "@/lib/categories"
import { stateName } from "@/lib/geo"
import { monthLabel } from "@/lib/format"
import type {
  AgentResult, Om5AgentInsight, Om5AnomalyRow, Om5Comparison, Om5Kpi, Om5Meta, Om5Mode, Om5Trace, Om5View, TrendRow,
} from "./types"
import type { Om5ReportResponse } from "@/lib/api"

/* ------------------------------------------------------------------ formats (locale fr-FR) */
const nf = (max: number, min = 0) => new Intl.NumberFormat("fr-FR", { maximumFractionDigits: max, minimumFractionDigits: min })

export function monthLong(m: string): string {
  const [y, mo] = m.split("-").map(Number)
  return new Date(y, mo - 1, 1).toLocaleDateString("fr-FR", { month: "long", year: "numeric" })
}
export function monthTick(m: string): string {
  const [y, mo] = m.split("-").map(Number)
  return `${new Date(y, mo - 1, 1).toLocaleDateString("fr-FR", { month: "short" }).replace(".", "")} ${String(y).slice(2)}`
}

export function signed(x: number, max = 1): string {
  const s = nf(max, max).format(Math.abs(x))
  return `${x > 0 ? "+" : x < 0 ? "−" : ""}${s}`
}

export interface FormattedValue { main: string; unit: string }

export function formatValue(unit: string, v: number | null | undefined): FormattedValue {
  if (v == null || Number.isNaN(v)) return { main: "—", unit: "" }
  if (unit === "ratio") return { main: nf(1, 1).format(v * 100), unit: "%" }
  if (unit === "BRL") return { main: nf(0).format(v), unit: "BRL" }
  if (/toiles/.test(unit)) return { main: nf(2, 2).format(v), unit: "/ 5" }
  if (unit === "jours") return { main: nf(1, 1).format(v), unit: "jours" }
  if (["commandes", "avis", "vendeurs"].includes(unit)) return { main: nf(0).format(v), unit }
  return { main: nf(2).format(v), unit }
}
export function formatInline(unit: string, v: number | null | undefined): string {
  const f = formatValue(unit, v)
  return f.unit ? `${f.main} ${f.unit}` : f.main
}

/** Axe/infobulle : valeurs compactes. */
export function compactNumber(v: number): string {
  return new Intl.NumberFormat("fr-FR", { notation: "compact", maximumFractionDigits: 1 }).format(v)
}

/* ------------------------------------------------------------------ variations */
export interface Variation {
  text: string
  sign: -1 | 0 | 1
  /** true : évolution dans le sens souhaité ; false : sens défavorable ; null : neutre / stable. */
  favorable: boolean | null
  basis: string
}

export function variationOf(c: Om5Comparison | undefined): Variation | null {
  if (!c) return null
  const isRatio = c.unit === "ratio"
  const raw = isRatio ? c.percentage_point_change : c.relative_change_pct
  if (raw == null || Number.isNaN(raw)) return null
  const flat = isRatio ? Math.abs(raw) < 0.1 : Math.abs(raw) < 0.5
  const sign = flat ? 0 : raw > 0 ? 1 : -1
  const text = flat ? "Stable" : isRatio ? `${signed(raw, 1)} pt` : `${signed(raw, 1)} %`
  const favorable = sign === 0 ? null : (sign > 0) === (c.direction === "higher")
  const basis = c.previous_period ? `vs ${monthLabel(c.previous_period)}` : "vs mois précédent"
  return { text, sign: sign as -1 | 0 | 1, favorable, basis }
}

/* ------------------------------------------------------------------ build the view */
const asRows = <T,>(x: unknown): T[] => (Array.isArray(x) ? (x as T[]) : [])

export function buildView(args: {
  month: string
  mode: Om5Mode
  report: Om5ReportResponse
  kpis: Om5Kpi[]
  trends: TrendRow[]
}): Om5View {
  const { report, month, mode } = args
  const meta = report.report.meta as Om5Meta
  const raw = meta as unknown as { comparisons?: { comparisons?: Om5Comparison[] }; segments?: Om5View["segments"]; agent_insights?: Record<string, Om5AgentInsight> }
  const anomalies = asRows<Om5AnomalyRow>(meta.anomalies)
  return {
    month,
    mode,
    title: report.report.title,
    narrative: report.report.narrative,
    meta,
    facts: report.report.facts ?? [],
    caveats: report.report.caveats ?? [],
    comparisons: asRows<Om5Comparison>(raw.comparisons?.comparisons),
    anomalies,
    detected: anomalies.filter((a) => a.anomaly),
    segments: (raw.segments ?? {}) as Om5View["segments"],
    agents: (raw.agent_insights ?? {}) as Record<string, Om5AgentInsight>,
    evidence: report.evidence ?? [],
    kpis: args.kpis,
    trends: args.trends,
  }
}

/** Mois complets uniquement ; en mode « à date », jamais au-delà de la période de décision. */
export function visibleTrends(rows: TrendRow[], month: string, mode: Om5Mode): TrendRow[] {
  return rows.filter((r) => r.is_complete_period !== false && (mode !== "as_of" || String(r.purchase_month) <= month))
}

export function metricLabel(v: Om5View, id: string): string {
  return v.anomalies.find((a) => a.metric_id === id)?.label ?? v.comparisons.find((c) => c.metric_id === id)?.label ?? v.kpis.find((k) => k.metric_id === id)?.label ?? id
}

/* ------------------------------------------------------------------ status labels */
export type Tone = "good" | "warn" | "bad" | "neutral" | "info"

export interface Health { key: "stable" | "attention" | "partial"; label: string; tone: Tone; detail: string }

export function health(v: Om5View): Health {
  const n = v.detected.length
  const high = v.detected.filter((a) => a.severity === "high").length
  if (v.meta.partial) return { key: "partial", label: "Analyse partielle", tone: "warn", detail: "Certaines sources n'ont pas pu être consolidées." }
  if (n === 0) return { key: "stable", label: "Situation stable", tone: "good", detail: "Aucune dégradation statistiquement significative ce mois-ci." }
  return {
    key: "attention",
    label: "Attention requise",
    tone: high ? "bad" : "warn",
    detail: `${n} anomalie${n > 1 ? "s" : ""} détectée${n > 1 ? "s" : ""}${high ? ` dont ${high} de sévérité élevée` : ""}.`,
  }
}

/** Ne revendique « analyse intelligente » que si le texte vient réellement d'un LLM, sans repli. */
export function provenance(v: Om5View): { llm: boolean; label: string } {
  const llm = v.meta.generation_mode !== "deterministic" && !v.meta.fallback_used
  return { llm, label: llm ? "Analyse intelligente" : "Synthèse automatique de secours" }
}

/** « Analyse vérifiée » uniquement si validation et citations sont réellement valides, et le rapport complet. */
export function verification(v: Om5View): { verified: boolean; label: string } {
  const verified = v.meta.validation_status === "valid" && v.meta.evidence_valid && !v.meta.partial
  if (verified) return { verified, label: "Analyse vérifiée" }
  if (v.meta.partial) return { verified, label: "Analyse partielle" }
  return { verified, label: "Vérification non concluante" }
}

/* ------------------------------------------------------------------ anomalies */
export interface AnomalyReading {
  current: string
  baseline: string
  delta: string
  worse: boolean
  severity: string
  interpretation: string
}

export function readAnomaly(a: Om5AnomalyRow): AnomalyReading {
  const current = formatInline(a.unit, a.value)
  const baseline = a.baseline == null ? "—" : formatInline(a.unit, a.baseline)
  let delta = "—"
  let multiple = ""
  if (a.value != null && a.baseline != null) {
    if (a.unit === "ratio") delta = `${signed((a.value - a.baseline) * 100, 1)} pt`
    else if (/toiles/.test(a.unit)) delta = `${signed(a.value - a.baseline, 2)} étoile`
    else if (a.baseline !== 0) delta = `${signed(((a.value - a.baseline) / Math.abs(a.baseline)) * 100, 1)} %`
    if (a.unit === "ratio" && a.baseline > 0 && a.value / a.baseline >= 1.5) multiple = ` (×${nf(1, 1).format(a.value / a.baseline)})`
  }
  const worse = a.value != null && a.baseline != null && (a.direction === "higher" ? a.value < a.baseline : a.value > a.baseline)
  const interpretation = a.baseline == null
    ? `${a.label} : ${current}.`
    : `${a.label} à ${current}, contre ${baseline} en référence historique${multiple}. ${worse ? "Dégradation" : "Écart"} au-delà de la variation habituelle.`
  return { current, baseline, delta, worse, severity: a.severity === "high" ? "Élevée" : a.severity === "medium" ? "Modérée" : "Faible", interpretation }
}

/* ------------------------------------------------------------------ segments */
export interface SegmentBar { label: string; share: number; rate: string; n: number; excess: string }

/** Segments (région / catégorie) situés du côté défavorable du taux global ; écart = événements en excès vs taux global. */
export function segmentBars(v: Om5View, metricId: string, dim: "state" | "category"): SegmentBar[] {
  const block = v.segments[metricId]
  const rows = block?.segments?.[dim] ?? []
  const anomaly = v.anomalies.find((a) => a.metric_id === metricId)
  if (!anomaly || anomaly.value == null) return []
  const higherIsBetter = anomaly.direction === "higher"
  const picked = rows
    .filter((r) => r.sufficient_n && r.value != null && (higherIsBetter ? r.value < anomaly.value! : r.value > anomaly.value!))
    .sort((a, b) => b.contribution_abs - a.contribution_abs)
    .slice(0, 6)
  const max = Math.max(...picked.map((r) => r.contribution_abs), 0)
  return picked.map((r) => ({
    label: dim === "state" ? stateName(r.segment) : catLabel(r.segment),
    share: max ? r.contribution_abs / max : 0,
    rate: formatInline(anomaly.unit, r.value),
    n: r.sample_size,
    excess: `${nf(1, 1).format(r.contribution_abs)} commandes en excès`,
  }))
}

/** Indicateurs en taux pour lesquels l'API fournit une décomposition par segment exploitable. */
export function segmentMetrics(v: Om5View): string[] {
  return Object.keys(v.segments).filter((id) => v.anomalies.find((a) => a.metric_id === id)?.unit === "ratio")
}

/* ------------------------------------------------------------------ agents */
export type AgentKey = "bo1" | "bo2" | "bo3"
export type AgentState = "done" | "not_needed" | "unavailable" | "failed"
type TraceRow = Om5Trace & { args?: Record<string, unknown> }

export const AGENT_STATE_LABEL: Record<AgentState, string> = {
  done: "Analyse réalisée",
  not_needed: "Investigation non nécessaire",
  unavailable: "Analyse indisponible",
  failed: "Échec de l'investigation",
}

export function agentStatus(v: Om5View, key: AgentKey): { state: AgentState; trigger: string | null; error: string | null } {
  const call = (v.meta.tool_trace as TraceRow[]).find((t) => t.tool === `collect_${key}_insights`)
  const trigger = typeof call?.args?.reason === "string" ? (call.args.reason as string) : null
  const insight = v.agents[key]
  if (insight?.error || call?.status === "error") return { state: "failed", trigger, error: insight?.error ?? call?.error ?? null }
  if (insight?.result) return { state: "done", trigger, error: null }
  // Appel réussi sans résultat exploitable → indisponible ; jamais appelé ou ignoré → non nécessaire (jamais « réalisée »).
  if (call && call.status === "ok") return { state: "unavailable", trigger, error: null }
  return { state: "not_needed", trigger, error: null }
}

const ORDER_LINE = /^Commande [0-9a-f]{16,}/i

/** Retire le jargon statistique (z, q) des textes des agents BO pour l'affichage business. */
export function plainText(s: string): string {
  return s.replace(/\s*\([^)]*\b(?:z|q)\s*=\s*[^)]*\)/g, "").replace(/\s{2,}/g, " ").trim()
}

export interface AgentReading {
  summary: string | null
  findings: string[]
  extra: string[]
  indicators: { label: string; value: string }[]
  actions: string[]
  caveats: string[]
  sellers: { id: string; category: string; alerts: number; severity: string }[]
}

export function readAgent(key: AgentKey, r: AgentResult | null | undefined): AgentReading {
  const empty: AgentReading = { summary: null, findings: [], extra: [], indicators: [], actions: [], caveats: [], sellers: [] }
  if (!r) return empty
  const texts = (xs?: { text: string }[]) => (xs ?? []).map((x) => plainText(x.text)).filter((t) => t && !ORDER_LINE.test(t))
  if (key === "bo3") {
    const s = r.overview?.summary
    const ind: AgentReading["indicators"] = []
    const alerted = r.alerts?.n_alerted_sellers ?? s?.n_with_any_alert
    if (r.overview?.n_sellers != null || s?.n_evaluated != null) ind.push({ label: "Vendeurs évalués", value: nf(0).format(s?.n_evaluated ?? r.overview!.n_sellers!) })
    if (alerted != null) ind.push({ label: "Vendeurs en alerte", value: nf(0).format(alerted) })
    if (r.alerts?.n_alerts != null) ind.push({ label: "Alertes émises", value: nf(0).format(r.alerts.n_alerts) })
    const high = s?.level_alerts_by_top_severity?.["élevée"]
    if (high != null) ind.push({ label: "Sévérité élevée", value: nf(0).format(high) })
    const listing = r.alerts?.listing ?? []
    return {
      ...empty,
      indicators: ind,
      summary: alerted != null ? `${nf(0).format(alerted)} vendeur${alerted > 1 ? "s" : ""} présentent au moins une alerte de performance ce mois-ci.` : null,
      sellers: listing.slice(0, 5).map((x) => ({ id: x.seller_id, category: x.main_category ?? "—", alerts: x.n_alerts, severity: x.top_severity ?? "—" })),
    }
  }
  const est = texts(r.estimates)
  const facts = texts(r.facts)
  // BO2 : le premier « fait » porte sur toutes les commandes et diffère du périmètre OM5 → réservé aux détails.
  const lead = key === "bo2" ? est : [...facts, ...est]
  return {
    ...empty,
    summary: r.narrative ? plainText(r.narrative) : null,
    findings: lead.slice(0, 3),
    extra: [...(key === "bo2" ? facts : []), ...lead.slice(3)],
    actions: texts(r.actions),
    caveats: (r.caveats ?? []).map(plainText),
  }
}

export const AGENT_META: Record<AgentKey, { code: string; title: string; objective: string }> = {
  bo1: { code: "BO1", title: "Diagnostic logistique", objective: "Identifier les commandes les plus exposées au retard de livraison." },
  bo2: { code: "BO2", title: "Satisfaction client", objective: "Comprendre les motifs d'insatisfaction exprimés dans les avis." },
  bo3: { code: "BO3", title: "Performance vendeurs", objective: "Repérer les vendeurs dont les indicateurs se dégradent." },
}

/* ------------------------------------------------------------------ recommendations */
export interface Rec {
  key: string
  title: string
  description: string
  justification: string
  level: "haute" | "moyenne" | "basse" | null
  score: number
  team: string | null
  timeframe: string | null
  benefit: string | null
  related: string | null
  segment: string | null
  evidenceIds: string[]
  preventive: boolean
}

const HEX_ID = /^[0-9a-f]{24,}$/i

export function buildRecommendations(v: Om5View): Rec[] {
  const ctx = v.meta.contextual_recommendations ?? []
  let recs: Rec[]
  if (ctx.length) {
    recs = ctx.map((r, i) => ({
      key: `${r.related_anomaly}-${i}`,
      title: r.title,
      description: r.description,
      justification: r.business_justification,
      level: r.priority_level,
      score: r.priority_score,
      team: r.responsible_team,
      timeframe: r.timeframe,
      benefit: r.expected_qualitative_benefit,
      related: r.related_anomaly && r.related_anomaly !== "none" ? metricLabel(v, r.related_anomaly) : null,
      segment: r.relevant_segment_or_seller ? (HEX_ID.test(r.relevant_segment_or_seller) ? `Vendeur ${r.relevant_segment_or_seller.slice(0, 8)}…` : r.relevant_segment_or_seller) : null,
      evidenceIds: r.evidence_ids,
      preventive: !v.detected.length || !r.related_anomaly || r.related_anomaly === "none",
    }))
  } else {
    // Repli : recommandations déterministes (champs d'équipe/délai/bénéfice non fournis → non affichés).
    recs = (v.meta.recommendations ?? []).map((r, i) => ({
      key: `${r.metric_id}-${i}`,
      title: `Traiter : ${metricLabel(v, r.metric_id)}`,
      description: r.recommendation,
      justification: r.justification,
      level: r.severity === "high" ? "haute" : r.severity === "medium" ? "moyenne" : "basse",
      score: r.priority_score,
      team: null, timeframe: null, benefit: null,
      related: metricLabel(v, r.metric_id), segment: null,
      evidenceIds: [r.evidence_id],
      preventive: false,
    }))
  }
  return recs.sort((a, b) => Number(a.preventive) - Number(b.preventive) || b.score - a.score)
}

export const LEVEL_LABEL = { haute: "Priorité haute", moyenne: "Priorité moyenne", basse: "Priorité basse" } as const

/* ------------------------------------------------------------------ evidence labels */
export function evidenceLabel(v: Om5View, id: string): string {
  const parts = id.split(":")
  const metric = parts[parts.length - 1]
  const kind = parts[1]
  if (kind === "bo1") return "Diagnostic logistique (BO1)"
  if (kind === "bo2") return "Satisfaction client (BO2)"
  if (kind === "bo3") return "Performance vendeurs (BO3)"
  if (kind === "kpi") return `Indicateur — ${metricLabel(v, metric)}`
  if (kind === "anomaly") return `Anomalie — ${metricLabel(v, metric)}`
  if (kind === "segments") return `Analyse par segment — ${metricLabel(v, metric)}`
  if (kind === "comparison") return "Comparaison historique"
  return id
}

/* ------------------------------------------------------------------ workflow */
export type StageState = "done" | "skipped" | "failed" | "unknown"
export interface Stage { id: string; title: string; state: StageState; warn: boolean; caption: string }

export function buildWorkflow(v: Om5View): Stage[] {
  const trace = v.meta.tool_trace as TraceRow[]
  const node = (name: string) => trace.find((t) => t.tool === name && t.kind !== "tool")
  const st = (...names: string[]): StageState => {
    const rows = names.map(node).filter(Boolean) as TraceRow[]
    if (!rows.length) return "unknown"
    if (rows.some((r) => r.status === "error")) return "failed"
    if (rows.every((r) => r.status === "skipped" || r.status === "deduplicated")) return "skipped"
    return "done"
  }
  const n = v.detected.length
  const quiet = n === 0
  const called = (["bo1", "bo2", "bo3"] as AgentKey[]).filter((k) => agentStatus(v, k).state === "done")
  const notNeeded = (s: StageState): StageState => (s === "unknown" && quiet ? "skipped" : s)
  const recs = buildRecommendations(v)
  const ver = verification(v)
  return [
    { id: "collect", title: "Collecte des données", state: st("kpi"), warn: false, caption: `${v.kpis.length || v.anomalies.length} indicateurs calculés` },
    { id: "perf", title: "Analyse des performances", state: st("comparisons"), warn: false, caption: "Comparaison avec l'historique" },
    { id: "anomaly", title: "Détection des anomalies", state: st("anomaly_detection", "segment_analysis"), warn: false, caption: quiet ? "Aucune anomalie significative" : `${n} anomalie${n > 1 ? "s" : ""} détectée${n > 1 ? "s" : ""}` },
    { id: "plan", title: "Planification des investigations", state: notNeeded(st("planner")), warn: false, caption: quiet ? "Aucune investigation nécessaire" : called.length ? `${called.length} agent${called.length > 1 ? "s" : ""} sélectionné${called.length > 1 ? "s" : ""}` : "Aucun agent sélectionné" },
    { id: "agents", title: "Collaboration des agents spécialisés", state: notNeeded(st("agent_execution")), warn: false, caption: called.length ? called.map((k) => k.toUpperCase()).join(" · ") : quiet ? "Non sollicités" : "Aucun résultat disponible" },
    { id: "reco", title: "Génération des recommandations", state: st("consolidation", "prioritization", "llm_generation"), warn: v.meta.fallback_used || v.meta.generation_mode === "deterministic", caption: v.meta.fallback_used || v.meta.generation_mode === "deterministic" ? "Synthèse automatique de secours" : `${recs.length} action${recs.length > 1 ? "s" : ""} proposée${recs.length > 1 ? "s" : ""}` },
    { id: "verify", title: "Vérification des résultats", state: st("validation"), warn: !ver.verified, caption: ver.verified ? "Citations vérifiées" : ver.label },
    { id: "final", title: "Rapport final", state: st("final_report"), warn: v.meta.partial, caption: v.meta.partial ? "Rapport partiel" : "Rapport complet" },
  ]
}
