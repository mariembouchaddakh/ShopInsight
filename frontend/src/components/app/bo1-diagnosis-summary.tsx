import { Clock, Package, Star, Users } from "lucide-react"
import { Card, CardContent } from "@/components/ui/card"
import type { Evidence } from "@/lib/api"
import { catLabel } from "@/lib/categories"
import { pct } from "@/lib/format"
import { stateName } from "@/lib/geo"

type Risk = {
  band: string
  percentile_points: number
  band_observed_rate: number | null
  base_rate_test: number
  band_n: number
}
type Drivers = { drivers: { group: string; delta_percentile_points: number }[] }
type Similar = { k: number; n_late: number; n_reviewed: number; n_poor: number }
type Ctx = { customer_state: string; primary_category: string; promised_days: number | null; distance_km: number | null; item_price_total: number | null; freight_total: number | null }

const BAND = {
  élevé: { color: "#9f2842", bg: "bg-[#9f2842]/8", label: "Risque élevé" },
  modéré: { color: "#B08418", bg: "bg-[#B08418]/8", label: "Risque modéré" },
  faible: { color: "#2F8F5B", bg: "bg-[#2F8F5B]/8", label: "Risque faible" },
} as const

function payload<T>(ev: Evidence[], id: string): T | null {
  const e = ev.find((x) => x.id === id)
  return (e?.payload as T) ?? null
}

function RiskCard({ title, icon: Icon, risk, drivers }: { title: string; icon: typeof Clock; risk: Risk; drivers: Drivers | null }) {
  const b = BAND[risk.band as keyof typeof BAND] ?? BAND.faible
  const lift = risk.band_observed_rate != null && risk.base_rate_test ? risk.band_observed_rate / risk.base_rate_test : null
  const top = (drivers?.drivers ?? []).filter((d) => d.delta_percentile_points > 0).slice(0, 3)
  const max = Math.max(10, ...top.map((d) => d.delta_percentile_points))
  return (
    <Card className={`${b.bg} border-0 ring-1 ring-inset`} style={{ ["--tw-ring-color" as string]: `${b.color}33` }}>
      <CardContent className="space-y-4 pt-5">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="flex items-center gap-1.5 text-sm text-muted-foreground">
              <Icon className="size-4" /> {title}
            </p>
            <p className="mt-1 font-display text-2xl font-bold" style={{ color: b.color }}>
              {b.label}
            </p>
          </div>
          <div className="text-right">
            <p className="font-display text-3xl font-bold tabular-nums">{risk.percentile_points}</p>
            <p className="text-[11px] text-muted-foreground">percentile / 100</p>
          </div>
        </div>
        <div>
          <div className="relative h-2.5 rounded-full bg-gradient-to-r from-[#2F8F5B]/35 via-[#B08418]/35 to-[#9f2842]/45">
            <span
              className="absolute top-1/2 size-4 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white shadow"
              style={{ left: `${Math.min(99, Math.max(1, risk.percentile_points))}%`, background: b.color }}
            />
          </div>
          <div className="relative mt-1 h-3.5 text-[10.5px] text-muted-foreground">
            <span className="absolute left-0">0</span>
            <span className="absolute left-[70%] -translate-x-1/2">70 · modéré</span>
            <span className="absolute left-[90%] -translate-x-1/2">90</span>
            <span className="absolute right-0">100</span>
          </div>
        </div>
        {risk.band_observed_rate != null && (
          <p className="text-sm">
            Dans cette tranche, <strong>{pct(risk.band_observed_rate)}</strong> des commandes ont eu ce problème, contre {pct(risk.base_rate_test)} en moyenne
            {lift && lift > 1.15 ? <strong> (×{lift.toLocaleString("fr-FR", { maximumFractionDigits: 1 })})</strong> : null}.
          </p>
        )}
        {top.length === 0 && <p className="text-xs text-muted-foreground">Aucun facteur ne domine : le risque vient de plusieurs petits effets combinés.</p>}
        {top.length > 0 && (
          <div className="space-y-1.5">
            <p className="text-xs font-semibold text-muted-foreground">Ce qui pousse le score vers le haut</p>
            {top.map((d) => (
              <div key={d.group} className="grid grid-cols-[1fr_90px] items-center gap-2 text-xs">
                <span className="truncate">{d.group}</span>
                <div className="flex items-center gap-1.5">
                  <div className="h-1.5 flex-1 rounded-full bg-muted">
                    <div className="h-1.5 rounded-full" style={{ width: `${(d.delta_percentile_points / max) * 100}%`, background: b.color }} />
                  </div>
                  <span className="w-8 text-right tabular-nums">+{Math.round(d.delta_percentile_points)}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

/** Résumé visuel du diagnostic BO1, construit uniquement à partir des preuves renvoyées par l'agent. */
export function Bo1DiagnosisSummary({ evidence, orderId }: { evidence: Evidence[]; orderId: string }) {
  const late = payload<Risk>(evidence, `mdl:late:${orderId}`)
  const poor = payload<Risk>(evidence, `mdl:poor:${orderId}`)
  if (!late || !poor) return null
  const ctx = payload<Ctx>(evidence, `ord:${orderId}`)
  const sim = payload<Similar>(evidence, `ord:${orderId}:similar`)
  return (
    <div className="space-y-4">
      {ctx && (
        <div className="flex flex-wrap gap-x-5 gap-y-2 rounded-2xl border bg-card px-4 py-3 text-sm">
          <span className="font-mono text-xs text-muted-foreground">#{orderId.slice(0, 8)}</span>
          <span>
            <span className="text-muted-foreground">Vers</span> <strong>{stateName(ctx.customer_state)}</strong>
          </span>
          <span>
            <Package className="mr-1 inline size-3.5 text-muted-foreground" />
            {catLabel(ctx.primary_category)}
          </span>
          {ctx.promised_days != null && (
            <span>
              <span className="text-muted-foreground">Délai promis</span> <strong>{ctx.promised_days} j</strong>
            </span>
          )}
          {ctx.distance_km != null && (
            <span>
              <span className="text-muted-foreground">Distance vendeur</span> <strong>{ctx.distance_km.toLocaleString("fr-FR")} km</strong>
            </span>
          )}
          {ctx.item_price_total != null && (
            <span>
              <span className="text-muted-foreground">Panier</span> <strong>{ctx.item_price_total.toLocaleString("fr-FR")} R$</strong>
              {ctx.freight_total != null && <span className="text-muted-foreground"> + port {ctx.freight_total.toLocaleString("fr-FR")} R$</span>}
            </span>
          )}
        </div>
      )}
      <div className="grid gap-4 lg:grid-cols-2">
        <RiskCard title="Retard de livraison" icon={Clock} risk={late} drivers={payload<Drivers>(evidence, `mdl:late:drivers:${orderId}`)} />
        <RiskCard title="Avis de 1 ou 2 étoiles" icon={Star} risk={poor} drivers={payload<Drivers>(evidence, `mdl:poor:drivers:${orderId}`)} />
      </div>
      {sim && sim.k > 0 && (
        <div className="flex items-center gap-3 rounded-2xl border bg-card px-4 py-3 text-sm">
          <Users className="size-4 shrink-0 text-muted-foreground" />
          <span>
            Sur <strong>{sim.k}</strong> commandes comparables déjà livrées avant cet achat, <strong>{sim.n_late}</strong> {sim.n_late > 1 ? "sont arrivées" : "est arrivée"} en retard
            {sim.n_reviewed ? (
              <>
                {" "}et <strong>{sim.n_poor}</strong> sur {sim.n_reviewed} ont reçu 1-2 étoiles
              </>
            ) : null}
            .
          </span>
          <span className="ml-auto hidden gap-1 sm:flex" aria-hidden>
            {Array.from({ length: sim.k }).map((_, i) => (
              <span key={i} className={`size-3 rounded-sm ${i < sim.n_late ? "bg-[#9f2842]" : "bg-[#2F8F5B]/40"}`} />
            ))}
          </span>
        </div>
      )}
    </div>
  )
}
