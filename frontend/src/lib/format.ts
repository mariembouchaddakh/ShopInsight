import type { MetricKey, Severity } from "./api"

export const METRICS: MetricKey[] = ["late", "poor", "handover"]

export const METRIC_SHORT: Record<MetricKey, string> = {
  late: "Retard de livraison",
  poor: "Avis 1-2 étoiles",
  handover: "Expédition tardive",
}

export function pct(x: number | null | undefined, digits = 1): string {
  if (x === null || x === undefined || Number.isNaN(x)) return "—"
  return `${(x * 100).toLocaleString("fr-FR", { minimumFractionDigits: digits, maximumFractionDigits: digits })} %`
}

export function num(x: number | null | undefined): string {
  if (x === null || x === undefined) return "—"
  return x.toLocaleString("fr-FR")
}

export function monthLabel(m: string): string {
  const [y, mo] = m.split("-").map(Number)
  return new Date(y, mo - 1, 1).toLocaleDateString("fr-FR", { month: "short", year: "numeric" })
}

export function dateLabel(value: string | null | undefined, withTime = false): string {
  if (!value) return "—"
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleDateString(
    "fr-FR",
    withTime ? { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" } : undefined,
  )
}

export function shortId(id: string): string {
  return `${id.slice(0, 8)}…`
}

export const SEVERITY_STYLE: Record<Severity, string> = {
  élevée: "bg-burgundy-tint text-burgundy border-burgundy/30",
  moyenne: "bg-amber-tint text-amber-ink border-amber-ink/25",
  faible: "bg-muted text-muted-foreground border-border",
}

export const STATUS_LABEL: Record<string, string> = { new: "nouvelle", ongoing: "en cours", resolved: "résolue" }

export const FAMILY_LABEL: Record<string, string> = { level: "niveau", trend: "tendance" }

// Couleurs des séries (palette marine / bordeaux / moutarde, dérivées de la charte) : valeurs fixes car les attributs SVG
// ne résolvent pas toujours var(--…). Validées avec le contrôle daltonisme de la méthode dataviz (toutes paires, fond blanc) :
// séparation CVD ΔE ≥ 15, contraste ≥ 3:1. Le bordeaux d'ALERTE (#8B1E3F) reste distinct du bordeaux de série (#A8325A).
export const METRIC_COLOR: Record<MetricKey, string> = {
  late: "#2F6BB0",
  poor: "#A8325A",
  handover: "#B08418",
}
export const CHART = { grid: "#E2E8F0", tick: "#475569", reference: "#94A3B8", alert: "#8B1E3F" }

export function plural(n: number, one: string, many: string): string {
  return `${n.toLocaleString("fr-FR")} ${n > 1 ? many : one}`
}
