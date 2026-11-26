import { useState } from "react"
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip as RTooltip, XAxis, YAxis } from "recharts"
import type { FamilyTrends, MetricKey } from "@/lib/api"
import { CHART, METRICS, METRIC_COLOR, METRIC_SHORT, monthLabel, pct } from "@/lib/format"
import { cn } from "@/lib/utils"

// Ce que mesure chaque indicateur, en clair (titre du graphique et phrase de lecture).
export const METRIC_MEANING: Record<MetricKey, { what: string; verb: string }> = {
  handover: { what: "commandes remises au transporteur après la date limite", verb: "ont été remises au transporteur après la date limite" },
  late: { what: "commandes livrées après la date annoncée au client", verb: "ont été livrées après la date annoncée" },
  poor: { what: "commandes notées 1 ou 2 étoiles par le client", verb: "ont reçu une note de 1 ou 2 étoiles" },
}

type Row = { month: string; family: number | null; market: number | null }

function pts(d: number) {
  return `${d > 0 ? "+" : "−"}${Math.abs(d).toLocaleString("fr-FR", { maximumFractionDigits: 1, minimumFractionDigits: 1 })} point${Math.abs(d) >= 2 ? "s" : ""}`
}

/** Évolution mensuelle d'une famille (composition fixe) comparée à l'ensemble de la marketplace, pour l'indicateur choisi. */
export function FamilyTrend({ trends, group, label }: { trends: FamilyTrends; group: number; label: string }) {
  const [metric, setMetric] = useState<MetricKey>("late")
  const fam = trends.families.find((f) => f.group === group)
  if (!fam) return null
  const rows: Row[] = fam.series.map((p, i) => ({ month: p.month, family: p[metric]?.rate_90d ?? null, market: trends.marketplace[i]?.[metric]?.rate_90d ?? null }))
  const last = rows[rows.length - 1], prev = rows[rows.length - 2]
  const d = last.family != null && prev?.family != null ? (last.family - prev.family) * 100 : null
  return (
    <div className="space-y-3">
      <div className="space-y-1.5">
        <h4 className="text-sm font-semibold">Évolution sur {rows.length} mois</h4>
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="text-muted-foreground">Indicateur affiché :</span>
          <div className="flex rounded-full border bg-muted/50 p-0.5 font-medium" role="tablist" aria-label="Indicateur affiché">
            {METRICS.map((k) => (
              <button
                key={k}
                role="tab"
                aria-selected={metric === k}
                onClick={() => setMetric(k)}
                className={cn("rounded-full px-2.5 py-1 transition", metric === k ? "bg-butter text-ink shadow-sm" : "text-muted-foreground hover:text-foreground")}
              >
                {METRIC_SHORT[k]}
              </button>
            ))}
          </div>
        </div>
      </div>
      <p className="rounded-xl bg-muted/60 px-3 py-2.5 text-sm leading-relaxed">
        En {monthLabel(last.month)}, <b>{pct(last.family)}</b> des commandes de la {label.toLowerCase()} {METRIC_MEANING[metric].verb}, contre{" "}
        <b>{pct(last.market)}</b> pour l'ensemble de la marketplace, sur les 90 derniers jours
        {d !== null && Math.abs(d) >= 0.05 ? (
          <>
            {" "}
            (<span className={d > 0 ? "font-semibold text-burgundy" : "font-semibold text-forest"}>{pts(d)}</span> par rapport à {monthLabel(prev.month)})
          </>
        ) : (
          " (stable par rapport au mois précédent)"
        )}
        .
      </p>
      <p className="text-xs font-medium text-muted-foreground">
        Part des {METRIC_MEANING[metric].what}, calculée sur les 90 jours précédant chaque fin de mois (fenêtre courte pour voir les évolutions ; les taux des
        cartes ci-dessus portent sur 12 mois, d'où des valeurs différentes).
      </p>
      <div className="h-48">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={rows} margin={{ left: -12, right: 8, top: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={CHART.grid} vertical={false} />
            <XAxis dataKey="month" tick={{ fontSize: 10, fill: CHART.tick }} tickFormatter={(m) => monthLabel(String(m))} />
            <YAxis tick={{ fontSize: 10, fill: CHART.tick }} tickFormatter={(v) => `${Math.round(v * 100)} %`} width={44} />
            <RTooltip contentStyle={{ fontSize: 12 }} labelFormatter={(m) => monthLabel(String(m))} formatter={(v, n) => [pct(v as number), n]} />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <Line type="monotone" dataKey="family" name={label} stroke={METRIC_COLOR[metric]} strokeWidth={2.4} dot={{ r: 3 }} isAnimationActive={false} />
            <Line type="monotone" dataKey="market" name="Ensemble de la marketplace" stroke={CHART.reference} strokeWidth={1.8} strokeDasharray="5 4" dot={false} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <p className="text-[11px] text-muted-foreground">
        Chaque point utilise uniquement les données connues à la fin du mois ; la famille garde la composition du mois choisi.
      </p>
    </div>
  )
}

/** Vendeurs en alerte ce mois-ci et variation par rapport au mois précédent. */
export function AlertDelta({ trends, group }: { trends?: FamilyTrends; group: number }) {
  const s = trends?.families.find((f) => f.group === group)?.series
  if (!s || s.length < 2) return null
  const now = s[s.length - 1].sellers_alerted ?? 0, before = s[s.length - 2].sellers_alerted ?? 0
  if (now === before) return <span className="text-muted-foreground">(stable)</span>
  return (
    <span className={cn("font-semibold", now > before ? "text-burgundy" : "text-forest")}>
      ({now > before ? "+" : "−"}
      {Math.abs(now - before)} vs mois précédent)
    </span>
  )
}
