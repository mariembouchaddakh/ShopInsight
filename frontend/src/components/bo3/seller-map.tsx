import { useQuery } from "@tanstack/react-query"
import { MapPin, Route, Store } from "lucide-react"
import { useMemo, useState } from "react"
import { ErrorBlock, LoadingBlock } from "@/components/app/states"
import { SourcePills } from "@/components/evidence/source-pill"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { api, type SellerGeography } from "@/lib/api"
import { num, pct } from "@/lib/format"
import { MAP_H, MAP_W, project, stateName } from "@/lib/geo"
import { cn } from "@/lib/utils"

// Teinte unique par mode (palette séquentielle à une teinte) : volume = sarcelle, retards = rampe claire → terracotta foncé.
const VOLUME = "#2F6BB0"
const LATE_RAMP = ["#F7DDE5", "#E9A9BC", "#CC6688", "#A8325A", "#6E1430"]
const lateColor = (r: number) => LATE_RAMP[Math.min(LATE_RAMP.length - 1, Math.floor(r / 0.05))] // tranches de 5 points

type Mode = "volume" | "late"
type Hover = { x: number; y: number; title: string; body: string } | null

export function useBasemap() {
  return useQuery({ queryKey: ["basemap"], queryFn: api.basemap, staleTime: Infinity })
}

/** Fond de carte du Brésil dessiné à partir des données (centroïdes postaux), sans fichier ni service externe. */
export function Basemap({ points }: { points: [number, number][] }) {
  return (
    <g aria-hidden>
      {points.map(([lng, lat], i) => {
        const [x, y] = project(lng, lat)
        return <circle key={i} cx={x} cy={y} r={1.15} fill="#D5DCE5" />
      })}
    </g>
  )
}

function Bars({ rows, label }: { rows: { name: string; orders: number; share: number; late_rate: number | null; late_known: number }[]; label: string }) {
  const max = Math.max(1, ...rows.map((r) => r.orders))
  return (
    <div className="space-y-2">
      <h4 className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">{label}</h4>
      <ul className="space-y-2">
        {rows.map((r) => (
          <li key={r.name} className="space-y-1 text-sm">
            <div className="flex items-baseline justify-between gap-2">
              <span className="truncate">{r.name}</span>
              <span className="shrink-0 text-xs text-muted-foreground tabular-nums">
                {num(r.orders)} cmd · {pct(r.share, 0)}
                {r.late_rate !== null && (
                  <span className={cn("ml-1.5 font-medium", r.late_rate >= 0.1 ? "text-burgundy" : "text-foreground")}>
                    · {pct(r.late_rate)} en retard
                  </span>
                )}
              </span>
            </div>
            <div className="h-1.5 rounded-full bg-muted">
              <div className="h-1.5 rounded-full" style={{ width: `${(100 * r.orders) / max}%`, background: VOLUME }} />
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}

/** Carte des clients d'un vendeur : d'où il expédie, où vont ses commandes, et où ses livraisons arrivent en retard. */
export function SellerMap({ seller, month, onOpen }: { seller: string; month: string; onOpen: (id: string) => void }) {
  const geo = useQuery({ queryKey: ["geography", seller, month], queryFn: () => api.geography(seller, month), enabled: !!month })
  const base = useBasemap()
  const [mode, setMode] = useState<Mode>("volume")
  const [hover, setHover] = useState<Hover>(null)
  const g: SellerGeography | undefined = geo.data?.result
  const bubbles = useMemo(() => [...(g?.points ?? [])].sort((a, b) => b.orders - a.orders), [g])
  if (geo.isError) return <ErrorBlock error={geo.error} />
  if (geo.isLoading || !g) return <LoadingBlock rows={6} />
  const maxOrders = Math.max(1, ...bubbles.map((p) => p.orders))
  const radius = (n: number) => 2.2 + 9 * Math.sqrt(n / maxOrders)
  const origin = g.origin?.lat != null && g.origin.lng != null ? project(g.origin.lng, g.origin.lat) : null
  const s8 = seller.slice(0, 8)

  return (
    <Card>
      <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <CardTitle className="flex items-center gap-2 text-base">
            <MapPin className="size-4" /> Carte des clients
          </CardTitle>
          <CardDescription>
            Clients livrés dans {num(g.n_states)} États sur 12 mois
            {g.origin ? ` · expédition depuis ${g.origin.city} (${g.origin.state_name})` : ""}
            {g.median_distance_km !== null ? ` · distance médiane au client : ${num(g.median_distance_km)} km` : ""}.
          </CardDescription>
          <SourcePills ids={[`sel:geo:${s8}:${month}`]} onOpen={onOpen} className="mt-2" />
        </div>
        <div className="flex shrink-0 rounded-full border bg-muted/50 p-0.5 text-xs font-medium" role="tablist" aria-label="Affichage de la carte">
          {(
            [
              ["volume", "Volume"],
              ["late", "Retards de livraison"],
            ] as const
          ).map(([k, l]) => (
            <button
              key={k}
              role="tab"
              aria-selected={mode === k}
              onClick={() => setMode(k)}
              className={cn("rounded-full px-3 py-1 transition", mode === k ? "bg-background shadow-sm" : "text-muted-foreground hover:text-foreground")}
            >
              {l}
            </button>
          ))}
        </div>
      </CardHeader>
      <CardContent className="grid gap-8 lg:grid-cols-5">
        <div className="relative min-w-0 lg:col-span-3">
          <svg viewBox={`-6 -6 ${MAP_W + 12} ${MAP_H + 12}`} className="h-auto w-full" role="img" aria-label="Carte du Brésil : clients du vendeur">
            {base.data && <Basemap points={base.data.points} />}
            {bubbles.map((p, i) => {
              const [x, y] = project(p.lng, p.lat)
              const rate = p.late_known ? p.late / p.late_known : 0
              const fill = mode === "volume" ? VOLUME : p.late_known >= 3 ? lateColor(rate) : "#CBD5E1"
              return (
                <circle
                  key={i}
                  cx={x}
                  cy={y}
                  r={radius(p.orders)}
                  fill={fill}
                  fillOpacity={mode === "volume" ? 0.55 : 0.85}
                  stroke="white"
                  strokeWidth={0.8}
                  className="cursor-pointer transition-[r] duration-200 hover:brightness-110"
                  onMouseEnter={() =>
                    setHover({
                      x,
                      y,
                      title: stateName(p.state),
                      body: `${num(p.orders)} commande${p.orders > 1 ? "s" : ""}${p.late_known ? ` · ${num(p.late)} en retard sur ${num(p.late_known)} livrées` : ""}`,
                    })
                  }
                  onMouseLeave={() => setHover(null)}
                />
              )
            })}
            {origin && (
              <g transform={`translate(${origin[0]} ${origin[1]})`}>
                <circle r={13} fill="rgb(246 224 141 / 55%)" className="animate-ping" style={{ transformOrigin: "center", animationDuration: "2.4s" }} />
                <circle r={7.5} fill="#132238" stroke="#F6E08D" strokeWidth={2} />
                <path d="M-3.2 -1.2h6.4v4.2h-6.4z M-3.6 -1.2l1-2.4h5.2l1 2.4" fill="#F6E08D" />
              </g>
            )}
          </svg>
          {hover && (
            <div
              className="pointer-events-none absolute z-10 -translate-x-1/2 -translate-y-full rounded-lg border bg-popover px-3 py-2 text-xs shadow-lg"
              style={{ left: `${(100 * (hover.x + 6)) / (MAP_W + 12)}%`, top: `${(100 * (hover.y + 6)) / (MAP_H + 12)}%`, marginTop: -10 }}
            >
              <p className="font-semibold">{hover.title}</p>
              <p className="text-muted-foreground">{hover.body}</p>
            </div>
          )}
          <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-muted-foreground">
            <span className="inline-flex items-center gap-1.5">
              <Store className="size-3.5 text-ink" /> Entrepôt du vendeur
            </span>
            <span className="inline-flex items-center gap-1.5">
              <svg width="30" height="14" aria-hidden>
                <circle cx="5" cy="9" r="3" fill={mode === "volume" ? VOLUME : LATE_RAMP[2]} fillOpacity="0.6" />
                <circle cx="20" cy="7" r="6" fill={mode === "volume" ? VOLUME : LATE_RAMP[2]} fillOpacity="0.6" />
              </svg>
              taille = nombre de commandes
            </span>
            {mode === "late" && (
              <span className="inline-flex items-center gap-1.5">
                retard :
                {LATE_RAMP.map((c, i) => (
                  <span key={c} className="inline-flex items-center gap-0.5">
                    <span className="size-2.5 rounded-sm" style={{ background: c }} />
                    {i === 0 ? "< 5 %" : i === LATE_RAMP.length - 1 ? "≥ 20 %" : ""}
                  </span>
                ))}
                <span className="ml-1 inline-flex items-center gap-0.5">
                  <span className="size-2.5 rounded-sm bg-[#CBD5E1]" /> trop peu de livraisons
                </span>
              </span>
            )}
          </div>
        </div>
        <div className="min-w-0 space-y-6 lg:col-span-2">
          {(g.state_alerts?.length ?? 0) > 0 && (
            <div className="space-y-2 rounded-xl border border-burgundy/30 bg-burgundy-tint p-3">
              <h4 className="text-xs font-semibold tracking-wide text-burgundy uppercase">États où ses livraisons dérapent</h4>
              {g.state_alerts!.map((a) => (
                <p key={a.state} className="text-sm leading-relaxed">
                  <b>{a.state_name}</b> : {pct(a.rate)} des livraisons en retard ({num(a.known_n)} livraisons), contre {pct(a.reference_rate)} pour les autres
                  vendeurs vers cet État.
                </p>
              ))}
              <p className="text-[11px] text-muted-foreground">Signal descriptif : à recouper avec le transporteur utilisé vers cet État.</p>
            </div>
          )}
          <Bars label="Par grande région" rows={g.regions.map((r) => ({ ...r, name: r.region }))} />
          {g.distance_bands.length > 0 && (
            <div className="space-y-2">
              <h4 className="flex items-center gap-1.5 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                <Route className="size-3.5" /> Retard selon la distance
              </h4>
              <div className="grid grid-cols-3 gap-2">
                {g.distance_bands.map((b) => (
                  <div key={b.band} className="rounded-xl border p-2.5 text-center">
                    <p className="text-[11px] text-muted-foreground">{b.band}</p>
                    <p className="font-display text-lg font-bold">{b.late_rate === null ? "—" : pct(b.late_rate)}</p>
                    <p className="text-[11px] text-muted-foreground">{num(b.orders)} commandes</p>
                  </div>
                ))}
              </div>
            </div>
          )}
          <Bars label="Principaux États clients" rows={g.states.slice(0, 6).map((r) => ({ ...r, name: r.state_name }))} />
        </div>
      </CardContent>
    </Card>
  )
}
