// Libellés lisibles des sources (identifiants de preuve) : l'identifiant technique n'est jamais affiché tel quel.
import { AlertTriangle, BarChart3, Calculator, History, Info, Link2, ListChecks, MessageSquareQuote, Package, Star, Store, Trophy, Users, type LucideIcon } from "lucide-react"
import { METRIC_SHORT, monthLabel } from "./format"
import type { MetricKey } from "./api"

export interface SourceMeta {
  icon: LucideIcon
  label: string
  tone: "slate" | "blue" | "red" | "amber" | "violet" | "green"
}

const MONTH = /^20\d{2}-\d{2}$/
const metric = (m: string | undefined) => (m && m in METRIC_SHORT ? METRIC_SHORT[m as MetricKey] : null)
const mon = (m: string | undefined) => (m && MONTH.test(m) ? monthLabel(m) : null)

/** Icône, libellé et teinte d'une source à partir de son identifiant (sel:, peer:, kpi:, alr:, mdl:, ord:, rev:, ctx:). */
export function sourceMeta(id: string): SourceMeta {
  const p = id.split(":")
  const [kind, a, b, c, d] = p
  switch (kind) {
    case "kpi":
      if (a === "seller") return { icon: BarChart3, label: `${metric(d) ?? "Performance"} · ${mon(c) ?? ""}`.trim(), tone: "blue" }
      if (a === "history") return { icon: History, label: "Évolution mensuelle", tone: "blue" }
      if (a === "overview") return { icon: BarChart3, label: `Vue marketplace · ${mon(b) ?? ""}`.trim(), tone: "blue" }
      if (a === "categories") return { icon: BarChart3, label: `Catégories · ${mon(b) ?? ""}`.trim(), tone: "blue" }
      if (a === "marketplace") return { icon: BarChart3, label: "Tendance marketplace", tone: "blue" }
      return { icon: BarChart3, label: "Indicateur", tone: "blue" }
    case "alr":
      if (a === "list") return { icon: ListChecks, label: `Alertes du mois · ${mon(b) ?? ""}`.trim(), tone: "red" }
      if (a === "strength") return { icon: Star, label: "Points forts", tone: "green" }
      return { icon: AlertTriangle, label: `Alerte ${(metric(c) ?? "").toLowerCase()} · ${mon(b) ?? ""}`.replace(/\s+/g, " ").trim(), tone: "red" }
    case "peer":
      if (a === "bench") return { icon: Trophy, label: c ? `Classement · ${(metric(d) ?? "concurrents").toLowerCase()}` : "Comparaison concurrents", tone: "amber" }
      return { icon: Users, label: "Vendeurs comparables", tone: "amber" }
    case "sel":
      return { icon: Store, label: "Profil vendeur", tone: "slate" }
    case "mdl":
      if (a === "aspects") return { icon: MessageSquareQuote, label: "Avis clients", tone: "violet" }
      if (a === "expected") return { icon: Calculator, label: `Attendu vs observé${metric(d) ? ` · ${metric(d)!.toLowerCase()}` : ""}`, tone: "slate" }
      return { icon: Calculator, label: "Modèle", tone: "slate" }
    case "rev":
      return { icon: MessageSquareQuote, label: "Avis client", tone: "violet" }
    case "ord":
      if (a === "seller") return { icon: Package, label: "Commandes à problème", tone: "slate" }
      return { icon: Package, label: `Commande #${(a ?? "").slice(0, 6)}`, tone: "slate" }
    case "ctx":
      if (a === "multi") return { icon: Link2, label: "Commandes multi-vendeurs", tone: "slate" }
      if (a === "limites") return { icon: Info, label: "Limites de l'analyse", tone: "slate" }
      return { icon: Info, label: "Contexte", tone: "slate" }
    default:
      return { icon: Info, label: "Source", tone: "slate" }
  }
}

export const TONE_CLASS: Record<SourceMeta["tone"], string> = {
  slate: "border-border bg-muted text-muted-foreground",
  blue: "border-navy-soft/25 bg-navy-tint text-navy-soft",
  red: "border-burgundy/30 bg-burgundy-tint text-burgundy",
  amber: "border-butter-hover bg-butter/40 text-ink",
  violet: "border-plum/25 bg-plum-tint text-plum",
  green: "border-forest/25 bg-sage/60 text-forest",
}

export const EVIDENCE_KIND: Record<string, string> = {
  fait: "Donnée observée",
  estimation: "Analyse statistique",
  experience_autres_clients: "Comparaison et avis clients",
}
