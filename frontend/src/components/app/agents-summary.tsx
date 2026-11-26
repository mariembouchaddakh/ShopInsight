import { useQuery } from "@tanstack/react-query"
import { Activity, ArrowRight, Bot, MessageSquareText, PackageSearch, Store } from "lucide-react"
import type { ReactNode } from "react"
import { Link } from "react-router-dom"
import { api } from "@/lib/api"
import { monthLabel, num } from "@/lib/format"

function AgentCard({ to, icon, code, title, value, text, loading }: { to: string; icon: ReactNode; code: string; title: string; value: ReactNode; text: ReactNode; loading?: boolean }) {
  return (
    <Link to={to} className="lift group flex min-w-0 flex-col gap-2 rounded-2xl border bg-card p-4">
      <span className="flex items-center gap-2">
        <span className="flex size-8 shrink-0 items-center justify-center rounded-xl bg-butter text-ink">{icon}</span>
        <span className="min-w-0">
          <span className="block text-[10px] font-semibold tracking-[0.14em] text-muted-foreground uppercase">{code}</span>
          <span className="flex items-center gap-1 text-sm font-semibold">
            {title} <ArrowRight className="size-3.5 transition-transform group-hover:translate-x-0.5" />
          </span>
        </span>
      </span>
      <span className="font-display text-2xl font-bold tracking-tight">{loading ? "…" : value}</span>
      <span className="text-xs leading-snug text-muted-foreground">{loading ? "chargement…" : text}</span>
    </Link>
  )
}

/** Une carte par agent : le chiffre clé du mois et un lien vers sa page. */
export function AgentsSummary({ month }: { month: string | undefined }) {
  const m = month ?? undefined
  const bo1 = useQuery({ queryKey: ["bo1-overview", month, "late"], queryFn: () => api.bo1Overview({ month: month!, target: "late", top_k: 15 }), enabled: !!month, retry: false })
  const bo2 = useQuery({ queryKey: ["bo2-overview", month, {}], queryFn: () => api.bo2Overview({ month: m }), enabled: !!month, retry: false })
  const bo3 = useQuery({ queryKey: ["alerts-summary", month], queryFn: () => api.alerts({ month: m, top_k: 1 }), enabled: !!month, retry: false })
  const om5 = useQuery({ queryKey: ["om5-anomalies", month], queryFn: () => api.om5Anomalies(month!, "as_of"), enabled: !!month, retry: false })
  const q = month ? `?month=${month}` : ""
  const om5Hits = om5.data?.anomalies.filter((a) => a.severity !== "none") ?? []
  const topCritique = bo2.data ? [...bo2.data.aspects].filter((a) => a.aspect !== "satisfaction_globale").sort((x, y) => y.negative - x.negative)[0] : null
  return (
    <section className="space-y-3">
      <div className="flex items-end justify-between gap-2">
        <h2 className="text-lg font-semibold">Les 5 agents ce mois-ci</h2>
        <span className="text-xs text-muted-foreground">{month ? monthLabel(month) : ""}</span>
      </div>
      <div className="stagger grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <AgentCard
          to={`/bo1${q}`}
          icon={<PackageSearch className="size-4" />}
          code="BO1 · commandes"
          title="Commandes à risque"
          loading={bo1.isLoading}
          value={bo1.data ? num(bo1.data.top10pct_size) : "—"}
          text={bo1.data ? `commandes à surveiller sur ${num(bo1.data.n_orders)} (risque de retard)` : "données indisponibles pour ce mois"}
        />
        <AgentCard
          to={`/bo2${q}`}
          icon={<MessageSquareText className="size-4" />}
          code="BO2 · avis"
          title="Voix du client"
          loading={bo2.isLoading}
          value={bo2.data ? (bo2.data.alerts.length ? `${bo2.data.alerts.length} hausse${bo2.data.alerts.length > 1 ? "s" : ""}` : "stable") : "—"}
          text={bo2.data ? (bo2.data.alerts.length ? `plaintes en hausse : ${bo2.data.alerts.join(", ")}` : `aucune plainte en hausse ; première critique : ${topCritique?.label ?? "—"}`) : "données indisponibles"}
        />
        <AgentCard
          to={`/bo3/alerts${q}`}
          icon={<Store className="size-4" />}
          code="BO3 · vendeurs"
          title="Alertes vendeurs"
          loading={bo3.isLoading}
          value={bo3.data ? num(bo3.data.result.n_alerted_sellers) : "—"}
          text={bo3.data ? `vendeurs en écart avec la marketplace (${num(bo3.data.result.n_alerts)} alertes)` : "données indisponibles"}
        />
        <AgentCard
          to="/bo4"
          icon={<Bot className="size-4" />}
          code="BO4 · clients"
          title="Assistant client"
          value="Chat"
          text="suivi d'une commande, fenêtre de livraison estimée et expériences de clients comparables"
        />
        <AgentCard
          to={`/om5${q}`}
          icon={<Activity className="size-4" />}
          code="OM5 · pilotage"
          title="Monitoring autonome"
          loading={om5.isLoading}
          value={om5.data ? `${om5Hits.length} anomalie${om5Hits.length > 1 ? "s" : ""}` : "—"}
          text={om5.data ? (om5Hits.length ? om5Hits.map((a) => a.label).join(", ") : "aucun KPI anormal") : "données indisponibles"}
        />
      </div>
    </section>
  )
}
