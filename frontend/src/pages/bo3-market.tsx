import { useQuery } from "@tanstack/react-query"
import { AlertTriangle, Lightbulb, MousePointerClick, Store } from "lucide-react"
import { useMemo, useState } from "react"
import { useNavigate, useSearchParams } from "react-router-dom"
import { SeverityBadge } from "@/components/app/badges"
import { useDecisionMonth } from "@/components/app/month"
import { PageHeader } from "@/components/app/shell"
import { ErrorBlock, LoadingBlock } from "@/components/app/states"
import { openAssistant } from "@/components/assistant/assistant-widget"
import { AlertDelta, FamilyTrend } from "@/components/bo3/family-trend"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { api, type FamilyTrends, type MarketGroup, type MarketMap, type MetricKey } from "@/lib/api"
import { catLabel } from "@/lib/categories"
import { METRICS, METRIC_COLOR, METRIC_SHORT, monthLabel, num, pct, shortId } from "@/lib/format"
import { stateName } from "@/lib/geo"
import { cn } from "@/lib/utils"

const HIGHLIGHT = "#2F6BB0"
const MUTED = "#CBD5E1"
const ALERT = "#8B1E3F"
type Pt = MarketMap["points"][number]
type Hover = { x: number; y: number; p: Pt } | null
type Scale = { sx: (x: number) => number; sy: (y: number) => number }

const famLabel = (g: MarketGroup) => `Famille ${g.rank ?? g.group + 1}`
const share = (a: number, b: number) => (b ? a / b : 0)

/** Échelle commune à toutes les cartes (bornes robustes 1er–99e centile : quelques profils atypiques n'écrasent pas la vue). */
function useScale(points: Pt[] | undefined, W: number, H: number, pad: number): Scale | null {
  return useMemo(() => {
    if (!points?.length) return null
    const q = (a: number[], f: number) => [...a].sort((u, v) => u - v)[Math.floor(f * (a.length - 1))]
    const xs = points.map((p) => p.x), ys = points.map((p) => p.y)
    const [x0, x1, y0, y1] = [q(xs, 0.01), q(xs, 0.99), q(ys, 0.01), q(ys, 0.99)]
    const sx = (x: number) => pad + ((Math.min(Math.max(x, x0), x1) - x0) / (x1 - x0 || 1)) * (W - 2 * pad)
    const sy = (y: number) => H - pad - ((Math.min(Math.max(y, y0), y1) - y0) / (y1 - y0 || 1)) * (H - 2 * pad)
    return { sx, sy }
  }, [points, W, H, pad])
}

/** Nuage de fond en un seul tracé (léger même avec 1 500 points). */
function cloud(points: Pt[], s: Scale) {
  return points.map((p) => `M${s.sx(p.x).toFixed(1)} ${s.sy(p.y).toFixed(1)}h0`).join("")
}

/** « Ce qu'il faut retenir » : constats tirés des chiffres de la carte (on désigne simplement la famille la plus haute sur chaque mesure). */
function Takeaways({ d }: { d: MarketMap }) {
  const mp = d.market_profile
  if (!mp) return null
  const gs = d.groups
  const top = (f: (g: MarketGroup) => number) => [...gs].sort((a, b) => f(b) - f(a))[0]
  const byOrders = top((x) => x.orders_12m_total ?? 0)
  const byAlerts = top((x) => x.n_alerted)
  const late = top((x) => x.rates.late?.rate_12m ?? 0)
  const poor = top((x) => x.rates.poor?.rate_12m ?? 0)
  const items = [
    <>
      <b>
        {famLabel(byOrders)} · {byOrders.name}
      </b>{" "}
      : {num(byOrders.n_sellers)} vendeurs ({pct(share(byOrders.n_sellers, d.n_sellers), 0)} des vendeurs) mais{" "}
      <b>{pct(share(byOrders.orders_12m_total ?? 0, mp.orders_12m_total), 0)} des commandes</b> de l'année : c'est le cœur de l'activité.
    </>,
    byAlerts.n_alerted > 0 ? (
      <>
        <b>
          {num(byAlerts.n_alerted)} des {num(mp.n_alerted)} vendeurs en alerte
        </b>{" "}
        appartiennent à la {famLabel(byAlerts).toLowerCase()} ({byAlerts.name}), en partie parce qu'une alerte exige un volume minimal de commandes.
      </>
    ) : null,
    <>
      Les retards de livraison sont les plus fréquents dans la {famLabel(late).toLowerCase()} ({late.name}) : <b>{pct(late.rates.late?.rate_12m)}</b> des commandes,
      contre {pct(d.marketplace.late?.rate_12m)} pour l'ensemble de la marketplace.
    </>,
    <>
      Les avis négatifs (1-2 étoiles) sont les plus fréquents dans la {famLabel(poor).toLowerCase()} ({poor.name}) : <b>{pct(poor.rates.poor?.rate_12m)}</b>, contre{" "}
      {pct(d.marketplace.poor?.rate_12m)} pour l'ensemble.
    </>,
  ].filter(Boolean)
  return (
    <section className="rounded-2xl border border-butter-hover bg-butter/25 p-5">
      <h2 className="mb-3 flex items-center gap-2 font-display text-lg font-bold">
        <Lightbulb className="size-5" /> Ce qu'il faut retenir
      </h2>
      <ul className="space-y-2 text-sm leading-relaxed">
        {items.map((t, i) => (
          <li key={i} className="flex gap-2.5">
            <span className="mt-2 size-1.5 shrink-0 rounded-full bg-ink" />
            <span>{t}</span>
          </li>
        ))}
      </ul>
    </section>
  )
}

/** Barre de caractéristique : valeur de la famille (barre bleue) et médiane de la marketplace (trait noir). */
function TraitBar({ label, value, market, max, fmt }: { label: string; value: number | null | undefined; market: number | null | undefined; max: number; fmt: (v: number) => string }) {
  if (value == null) return null
  return (
    <div className="space-y-1">
      <div className="flex items-baseline justify-between gap-2 text-xs whitespace-nowrap">
        <span className="text-muted-foreground">{label}</span>
        <span className="tabular-nums">
          <b>{fmt(value)}</b>
          {market != null && <span className="text-muted-foreground"> (marché {fmt(market)})</span>}
        </span>
      </div>
      <div className="relative h-1.5 rounded-full bg-muted">
        <div className="h-1.5 rounded-full bg-[#2F6BB0]" style={{ width: `${Math.min(100, (100 * value) / max)}%` }} />
        {market != null && <div className="absolute -top-0.5 h-2.5 w-0.5 rounded bg-ink" style={{ left: `${Math.min(100, (100 * market) / max)}%` }} />}
      </div>
    </div>
  )
}

/** Portrait d'une famille : sa place sur la carte, son profil commercial, son activité et sa performance face au marché. */
function FamilyCard({ g, d, trends, maxes, active, onSelect, cloudPath, scale }: {
  g: MarketGroup; d: MarketMap; trends?: FamilyTrends; maxes: Record<string, number>; active: boolean; onSelect: () => void; cloudPath: string; scale: Scale
}) {
  const mp = d.market_profile
  const members = d.points.filter((p) => p.group === g.group)
  return (
    <button onClick={onSelect} className={cn("lift flex min-w-0 flex-col gap-3 rounded-2xl border bg-card p-4 text-left", active && "border-ink ring-2 ring-butter")}>
      <div>
        <p className="text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">{famLabel(g)}</p>
        <p className="font-display text-base leading-snug font-bold">{g.name}</p>
      </div>
      <svg viewBox="0 0 220 110" className="h-auto w-full rounded-lg bg-muted/40" role="img" aria-label={`Position de la ${famLabel(g)} sur la carte du marché`}>
        <path d={cloudPath} stroke={MUTED} strokeWidth={2.2} strokeLinecap="round" />
        {members.map((p) => (
          <circle key={p.seller_id} cx={scale.sx(p.x)} cy={scale.sy(p.y)} r={1.7} fill={HIGHLIGHT} />
        ))}
      </svg>
      <div className="grid grid-cols-3 gap-1.5 text-center">
        {[
          ["Vendeurs", num(g.n_sellers)],
          ["Commandes / an", num(g.orders_12m_total)],
          ["Part des commandes", pct(share(g.orders_12m_total ?? 0, mp?.orders_12m_total ?? 0), 0)],
        ].map(([l, v]) => (
          <div key={l} className="rounded-lg bg-muted/50 px-1 py-1.5">
            <p className="text-[10px] leading-tight text-muted-foreground">{l}</p>
            <p className="font-display text-sm font-bold">{v}</p>
          </div>
        ))}
      </div>
      <div className="space-y-2">
        <TraitBar label="Prix médian" value={g.median_price} market={mp?.median_price} max={maxes.price} fmt={(v) => `${Math.round(v)} R$`} />
        <TraitBar label="Délai annoncé" value={g.median_promised_days} market={mp?.median_promised_days} max={maxes.delay} fmt={(v) => `${v.toLocaleString("fr-FR", { maximumFractionDigits: 1 })} j`} />
        <TraitBar label="Frais de port / prix" value={g.median_freight_share} market={mp?.median_freight_share} max={maxes.freight} fmt={(v) => pct(v, 0)} />
        <TraitBar label="Clients du même État" value={g.median_same_state_share} market={mp?.median_same_state_share} max={maxes.local} fmt={(v) => pct(v, 0)} />
      </div>
      <div className="space-y-1 border-t pt-2.5">
        {METRICS.map((k: MetricKey) => {
          const v = g.rates[k]?.rate_12m ?? null, m = d.marketplace[k]?.rate_12m ?? null
          const worse = v != null && m != null && v > m
          return (
            <p key={k} className="flex items-center justify-between gap-2 text-xs whitespace-nowrap">
              <span className="flex items-center gap-1.5">
                <span className="size-2 rounded-full" style={{ background: METRIC_COLOR[k] }} />
                {METRIC_SHORT[k]}
              </span>
              <span className={cn("rounded-full px-1.5 font-semibold tabular-nums", worse ? "bg-burgundy-tint text-burgundy" : "bg-sage text-forest")}>
                {pct(v)} <span className="font-normal opacity-80">/ {pct(m)}</span>
              </span>
            </p>
          )
        })}
        <p className="pt-1 text-[11px] text-muted-foreground">Taux sur les 12 derniers mois : famille / ensemble de la marketplace</p>
      </div>
      <p className={cn("text-xs font-medium", g.n_alerted ? "text-burgundy" : "text-muted-foreground")}>
        <AlertTriangle className="mr-1 inline size-3.5" />
        {num(g.n_alerted)} vendeur{g.n_alerted > 1 ? "s" : ""} en alerte <AlertDelta trends={trends} group={g.group} />
      </p>
    </button>
  )
}

/** Carte du marché : familles de vendeurs au même modèle d'activité (descriptif), leurs caractéristiques, leur activité et leur évolution. */
export function MarketPage() {
  const [month] = useDecisionMonth()
  const [params] = useSearchParams()
  const focusSeller = params.get("seller")
  const nav = useNavigate()
  const q = useQuery({ queryKey: ["market-map", month], queryFn: () => api.marketMap(month), enabled: !!month })
  const tq = useQuery({ queryKey: ["family-trends", month], queryFn: () => api.familyTrends(month), enabled: !!month })
  const d = q.data?.result
  const trends = tq.data?.result
  const [sel, setSel] = useState<number | null>(null)
  const [hover, setHover] = useState<Hover>(null)
  const focus = d?.points.find((p) => p.seller_id === focusSeller)
  const active = sel ?? focus?.group ?? d?.groups[0]?.group ?? null
  const g = d?.groups.find((x) => x.group === active)
  const byGroup = useMemo(() => new Map((d?.groups ?? []).map((x) => [x.group, x])), [d])
  const big = useScale(d?.points, 640, 420, 16)
  const mini = useScale(d?.points, 220, 110, 6)
  const miniCloud = useMemo(() => (d && mini ? cloud(d.points, mini) : ""), [d, mini])
  const maxes = useMemo(() => {
    const gs = d?.groups ?? []
    const mx = (f: (x: MarketGroup) => number | null | undefined) => Math.max(1e-6, ...gs.map((x) => f(x) ?? 0)) * 1.1
    return { price: mx((x) => x.median_price), delay: mx((x) => x.median_promised_days), freight: mx((x) => x.median_freight_share), local: mx((x) => x.median_same_state_share) }
  }, [d])
  const hoverFam = hover ? byGroup.get(hover.p.group) : undefined

  return (
    <div className="space-y-8">
      <PageHeader
        title="Carte du marché"
        description={
          <>
            Les {d ? num(d.n_sellers) : "…"} vendeurs actifs à fin {month ? monthLabel(month) : "…"}, regroupés en 5 familles qui partagent le même modèle d'activité (niveau de
            prix, délai annoncé, volume, poids des frais de port, part de clients locaux). Les familles sont numérotées de la plus nombreuse (1) à la moins nombreuse (5).
          </>
        }
        actions={
          <Button variant="outline" onClick={() => openAssistant("Quelles catégories concentrent le plus de vendeurs en alerte ?")}>
            Interroger l'assistant
          </Button>
        }
      />
      {q.isError && <ErrorBlock error={q.error} />}
      {q.isLoading && <LoadingBlock rows={10} />}
      {d && big && mini && (
        <>
          <Takeaways d={d} />

          <section className="space-y-3">
            <div>
              <h2 className="font-display text-xl font-bold">Portrait des 5 familles</h2>
              <p className="text-sm text-muted-foreground">
                Pour chaque famille : sa place sur la carte (en bleu), son profil commercial comparé à la médiane du marché (trait noir), son activité et sa performance.
                Taux sur fond bordeaux : moins bons que la marketplace ; sur fond vert : meilleurs. Cliquez sur une famille pour l'explorer plus bas.
              </p>
            </div>
            <div className="stagger grid gap-4 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-5">
              {d.groups.map((x) => (
                <FamilyCard key={x.group} g={x} d={d} trends={trends} maxes={maxes} active={active === x.group} onSelect={() => setSel(x.group)} cloudPath={miniCloud} scale={mini} />
              ))}
            </div>
          </section>

          <section className="grid gap-6 xl:grid-cols-5">
            <Card className="xl:col-span-3">
              <CardHeader>
                <CardTitle className="text-base">Positionnement de tous les vendeurs</CardTitle>
                <CardDescription>
                  Chaque point est un vendeur ; deux vendeurs proches ont un modèle d'activité semblable. Survolez un point pour l'identifier, cliquez pour ouvrir son bilan.
                </CardDescription>
                <div className="flex flex-wrap gap-x-4 gap-y-1 pt-1 text-xs">
                  <span className="inline-flex items-center gap-1.5">
                    <span className="size-2.5 rounded-full bg-[#2F6BB0]" /> {g ? `${famLabel(g)} (sélectionnée)` : "famille choisie"}
                  </span>
                  <span className="inline-flex items-center gap-1.5">
                    <span className="size-2.5 rounded-full bg-[#CBD5E1]" /> autres familles
                  </span>
                  <span className="inline-flex items-center gap-1.5">
                    <span className="size-3 rounded-full border-2 border-burgundy" /> vendeur en alerte
                  </span>
                  <span className="inline-flex items-center gap-1.5 text-muted-foreground">
                    <MousePointerClick className="size-3.5" /> tous les points sont cliquables
                  </span>
                </div>
              </CardHeader>
              <CardContent>
                {d.axes?.length === 2 && <p className="mb-1.5 text-center text-[11px] font-medium text-muted-foreground">↑ {d.axes[1].plus}</p>}
                <div className="relative">
                  <svg viewBox="0 0 640 420" className="h-auto w-full rounded-xl bg-muted/30" role="img" aria-label="Carte des vendeurs par modèle d'activité">
                    {d.points.map((p) => {
                      const inSel = p.group === active
                      const x = big.sx(p.x), y = big.sy(p.y)
                      return (
                        <g
                          key={p.seller_id}
                          className="cursor-pointer"
                          onMouseEnter={() => setHover({ x, y, p })}
                          onMouseLeave={() => setHover(null)}
                          onClick={() => nav(`/bo3/sellers/${p.seller_id}?month=${month}`)}
                        >
                          <circle cx={x} cy={y} r={p.alerted ? 8 : 5} fill="transparent" />
                          <circle cx={x} cy={y} r={inSel ? 2.4 + Math.min(4, Math.sqrt(p.orders_12m) / 7) : 2.4} fill={inSel ? HIGHLIGHT : MUTED} fillOpacity={inSel ? 0.8 : 0.75} />
                          {p.alerted && <circle cx={x} cy={y} r={6.5} fill="none" stroke={ALERT} strokeWidth={1.8} />}
                        </g>
                      )
                    })}
                    {focus && (
                      <g transform={`translate(${big.sx(focus.x)} ${big.sy(focus.y)})`} pointerEvents="none">
                        <circle r={11} fill="none" stroke="#132238" strokeWidth={2} />
                        <text y={-15} textAnchor="middle" fontSize={11} fontWeight={700} fill="#132238">
                          {shortId(focus.seller_id)}
                        </text>
                      </g>
                    )}
                  </svg>
                  {hover && (
                    <div
                      className="pointer-events-none absolute z-10 w-64 -translate-x-1/2 -translate-y-full rounded-lg border bg-popover px-3 py-2 text-xs shadow-lg"
                      style={{ left: `${(100 * hover.x) / 640}%`, top: `${(100 * hover.y) / 420}%`, marginTop: -12 }}
                    >
                      <p className="font-mono font-semibold">Vendeur {shortId(hover.p.seller_id)}</p>
                      <p className="text-muted-foreground">
                        {catLabel(hover.p.main_category)} · {stateName(hover.p.state)} · {num(hover.p.orders_12m)} commandes / an
                      </p>
                      {hoverFam && (
                        <p className="text-muted-foreground">
                          {famLabel(hoverFam)} · {hoverFam.name}
                        </p>
                      )}
                      {hover.p.alerted && <p className="mt-1 font-semibold text-burgundy">En alerte ce mois-ci{hover.p.severity ? ` · priorité ${hover.p.severity}` : " · dégradation récente"}</p>}
                      <p className="mt-1 text-[10px] text-muted-foreground">Cliquez pour ouvrir son bilan</p>
                    </div>
                  )}
                </div>
                {d.axes?.length === 2 && (
                  <>
                    <p className="mt-1.5 text-center text-[11px] font-medium text-muted-foreground">↓ {d.axes[1].minus}</p>
                    <div className="mt-2 flex justify-between gap-4 text-[11px] font-medium text-muted-foreground">
                      <span>← {d.axes[0].minus}</span>
                      <span className="text-right">{d.axes[0].plus} →</span>
                    </div>
                  </>
                )}
              </CardContent>
            </Card>

            {g && (
              <Card className="pop-in xl:col-span-2" key={g.group}>
                <CardHeader>
                  <CardDescription>{famLabel(g)} · détail</CardDescription>
                  <CardTitle className="font-display text-xl">{g.name}</CardTitle>
                </CardHeader>
                <CardContent className="space-y-6">
                  {trends && <FamilyTrend trends={trends} group={g.group} label={famLabel(g)} />}
                  {g.n_alerted > 0 && (
                    <div className="space-y-2">
                      <h4 className="flex items-center gap-1.5 text-sm font-semibold">
                        <AlertTriangle className="size-4 text-burgundy" /> Vendeurs en alerte dans cette famille
                      </h4>
                      <ul className="divide-y rounded-xl border">
                        {d.points
                          .filter((p) => p.group === g.group && p.alerted)
                          .sort((a, b) => b.orders_12m - a.orders_12m)
                          .slice(0, 8)
                          .map((p) => (
                            <li key={p.seller_id}>
                              <button
                                onClick={() => nav(`/bo3/sellers/${p.seller_id}?month=${month}`)}
                                className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-xs hover:bg-muted/50"
                              >
                                <span className="flex min-w-0 items-center gap-2">
                                  <Store className="size-3.5 shrink-0 text-muted-foreground" />
                                  <span className="font-mono font-medium">{shortId(p.seller_id)}</span>
                                  <span className="truncate text-muted-foreground">{catLabel(p.main_category)}</span>
                                </span>
                                {p.severity ? <SeverityBadge severity={p.severity} /> : <span className="shrink-0 text-navy-soft">dégradation récente</span>}
                              </button>
                            </li>
                          ))}
                      </ul>
                    </div>
                  )}
                  <div className="grid grid-cols-2 gap-4 text-xs">
                    <div className="space-y-1.5">
                      <h4 className="font-semibold">Principales catégories</h4>
                      {g.top_categories.map((c) => (
                        <p key={c.category} className="flex justify-between gap-2">
                          <span className="truncate">{catLabel(c.category)}</span>
                          <span className="text-muted-foreground tabular-nums">{num(c.sellers)} vendeurs</span>
                        </p>
                      ))}
                    </div>
                    <div className="space-y-1.5">
                      <h4 className="font-semibold">Régions des vendeurs</h4>
                      {g.regions.map((r) => (
                        <p key={r.region} className="flex justify-between gap-2">
                          <span>{r.region}</span>
                          <span className="text-muted-foreground tabular-nums">{num(r.sellers)}</span>
                        </p>
                      ))}
                    </div>
                  </div>
                </CardContent>
              </Card>
            )}
          </section>
        </>
      )}
    </div>
  )
}
