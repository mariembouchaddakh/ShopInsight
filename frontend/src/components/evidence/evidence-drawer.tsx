/* eslint-disable @typescript-eslint/no-explicit-any */
import { CalendarDays, MapPin, Package, Star, Truck } from "lucide-react"
import type { ReactNode } from "react"
import { Pill, SeverityBadge } from "@/components/app/badges"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet"
import type { Evidence, MetricKey } from "@/lib/api"
import { EVIDENCE_KIND, sourceMeta, TONE_CLASS } from "@/lib/evidence"
import { METRIC_SHORT, monthLabel, num, pct } from "@/lib/format"
import { cn } from "@/lib/utils"
import { catLabel } from "@/lib/categories"
import { stateName } from "@/lib/geo"

// Contenu des preuves : renvoyé tel quel par les outils déterministes ; seule la présentation est faite ici.
type P = Record<string, any>

const metricName = (m: string) => (m in METRIC_SHORT ? METRIC_SHORT[m as MetricKey] : m)
const days = (v: number | null | undefined) => (v === null || v === undefined ? "—" : `${v.toLocaleString("fr-FR")} j`)
const money = (v: number | null | undefined) => (v === null || v === undefined ? "—" : `${v.toLocaleString("fr-FR")} R$`)

function Rows({ rows }: { rows: [string, ReactNode][] }) {
  return (
    <dl className="divide-y rounded-lg border text-sm">
      {rows.map(([k, v]) => (
        <div key={k} className="flex items-baseline justify-between gap-4 px-3 py-2">
          <dt className="text-muted-foreground">{k}</dt>
          <dd className="text-right font-medium tabular-nums [overflow-wrap:anywhere]">{v}</dd>
        </div>
      ))}
    </dl>
  )
}

function Mini({ head, rows }: { head: string[]; rows: ReactNode[][] }) {
  return (
    <div className="overflow-x-auto rounded-lg border">
      <table className="w-full text-xs">
        <thead className="bg-muted/50 text-muted-foreground">
          <tr>
            {head.map((h, i) => (
              <th key={h} className={cn("px-2.5 py-2 font-medium", i ? "text-right" : "text-left")}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y">
          {rows.map((r, i) => (
            <tr key={i}>
              {r.map((c, j) => (
                <td key={j} className={cn("px-2.5 py-1.5 tabular-nums", j ? "text-right" : "text-left")}>
                  {c}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function H({ children }: { children: ReactNode }) {
  return <h4 className="pt-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">{children}</h4>
}

export function Stars({ score }: { score: number }) {
  return (
    <span className="inline-flex" aria-label={`${score} étoile${score > 1 ? "s" : ""} sur 5`}>
      {[1, 2, 3, 4, 5].map((i) => (
        <Star key={i} className={cn("size-3.5", i <= score ? "fill-[#D9A82E] text-[#D9A82E]" : "text-muted-foreground/40")} />
      ))}
    </span>
  )
}

/** Carte d'avis client : note, aspect critiqué, extrait (traduit ou original portugais). */
export function ReviewCard({ q }: { q: P }) {
  return (
    <figure className="space-y-2 rounded-lg border bg-muted/20 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Stars score={Number(q.score)} />
        {q.aspect && <Pill tone="muted">{q.aspect}</Pill>}
      </div>
      <blockquote className="text-sm leading-relaxed [overflow-wrap:anywhere]">« {q.excerpt} »</blockquote>
      <figcaption className="text-[11px] text-muted-foreground">
        {q.machine_translated ? "Traduction automatique de l'avis" : "Avis original en portugais (traduction non disponible)"}
      </figcaption>
    </figure>
  )
}

/** Chronologie d'une commande : achat → problèmes connus à la date de décision. */
export function OrderTimeline({ o }: { o: P }) {
  const steps: { icon: typeof Package; text: string; bad?: boolean }[] = [
    { icon: CalendarDays, text: `Achat le ${new Date(o.purchase_date).toLocaleDateString("fr-FR")} · ${catLabel(o.category)}` },
  ]
  if (o.handover_delay_days !== null && o.handover_delay_days !== undefined)
    steps.push({ icon: Package, text: `Remise au transporteur ${o.handover_delay_days} j après la date limite`, bad: true })
  if (o.late_days !== null && o.late_days !== undefined) steps.push({ icon: Truck, text: `Livrée ${o.late_days} j après la date annoncée`, bad: true })
  if (o.review_score !== null && o.review_score !== undefined) steps.push({ icon: Star, text: `Avis du client : ${o.review_score}/5`, bad: o.review_score <= 2 })
  return (
    <div className="space-y-2 rounded-lg border p-3">
      <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
        <span className="font-medium">Commande #{String(o.order_id).slice(0, 8)}</span>
        <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
          <MapPin className="size-3" /> {stateName(o.customer_state)}
        </span>
      </div>
      <ol className="relative space-y-2 border-l pl-4">
        {steps.map((s, i) => (
          <li key={i} className="relative text-xs">
            <span className={cn("absolute top-0.5 -left-[22px] flex size-3 items-center justify-center rounded-full border bg-background", s.bad && "border-burgundy bg-burgundy-tint")} />
            <span className={cn("inline-flex items-center gap-1.5", s.bad && "text-burgundy")}>
              <s.icon className="size-3" /> {s.text}
            </span>
          </li>
        ))}
      </ol>
      {o.problems?.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {o.problems.map((p: string) => (
            <Pill key={p} tone="red">
              {p}
            </Pill>
          ))}
        </div>
      )}
    </div>
  )
}

function Kpi({ p }: { p: P }) {
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-2">
        <div className="rounded-lg border p-3">
          <p className="text-xs text-muted-foreground">Vendeur · 90 derniers jours</p>
          <p className="text-2xl font-semibold tabular-nums">{pct(p.recent_rate)}</p>
          <p className="text-[11px] text-muted-foreground">
            {num(p.recent_events)} cas sur {num(p.recent_known_n)} commandes dont l'issue est connue
          </p>
        </div>
        <div className="rounded-lg border p-3">
          <p className="text-xs text-muted-foreground">Marketplace</p>
          <p className="text-2xl font-semibold tabular-nums">{pct(p.peer_rate ?? p.marketplace_rate)}</p>
          <p className="text-[11px] text-muted-foreground">référence de comparaison</p>
        </div>
      </div>
      <Rows
        rows={[
          ["Marge d'incertitude (95 %)", `${pct(p.recent_ci95?.[0])} – ${pct(p.recent_ci95?.[1])}`],
          ["Vendeur · 12 mois", `${pct(p.year_rate)} (${num(p.year_known_n)} commandes)`],
          ["Écart à la marketplace", p.ratio_to_peers ? `× ${p.ratio_to_peers.toLocaleString("fr-FR")}` : "—"],
          ["Lecture", p.funnel_position ?? "—"],
          ["Commandes récentes", num(p.orders_recent)],
        ]}
      />
    </div>
  )
}

function AlertCard({ p }: { p: P }) {
  const fam: [string, string][] = [
    ["level", "Écart à la marketplace"],
    ["trend", "Dégradation par rapport à son passé"],
  ]
  return (
    <div className="space-y-3">
      {fam.map(([k, title]) => {
        const x = p.families?.[k]
        if (!x) return null
        return (
          <div key={k} className="space-y-2 rounded-lg border p-3">
            <div className="flex items-center justify-between gap-2">
              <p className="text-sm font-medium">{title}</p>
              {x.alert ? (
                <span className="flex gap-1">
                  <Pill tone="red">alerte</Pill>
                  <SeverityBadge severity={x.severity} />
                </span>
              ) : x.eligible ? (
                <Pill tone="green">pas d'alerte</Pill>
              ) : (
                <Pill>volume insuffisant</Pill>
              )}
            </div>
            <p className="text-xs text-muted-foreground">
              {pct(x.recent_rate)} sur 90 jours ({num(x.recent_known_n)} commandes) contre {pct(x.baseline)} pour{" "}
              {k === "level" ? "la marketplace" : "son propre historique"}.
              {x.alert_previous_month ? " Déjà signalé le mois précédent." : ""}
            </p>
          </div>
        )
      })}
      {p.past_alerts?.length > 0 && (
        <>
          <H>Alertes précédentes</H>
          <Mini
            head={["Mois", "Type", "Statut"]}
            rows={p.past_alerts.map((a: P) => [
              monthLabel(a.month),
              a.family === "level" ? "écart à la marketplace" : "dégradation",
              { new: "nouvelle", ongoing: "en cours", resolved: "résolue" }[a.status as string] ?? a.status,
            ])}
          />
        </>
      )}
    </div>
  )
}

function HistoryCard({ p }: { p: P }) {
  const series: Record<string, P[]> = p.series ?? {}
  const months = [...new Set(Object.values(series).flatMap((s) => s.map((x) => x.month)))].sort()
  const keys = Object.keys(series)
  return (
    <Mini
      head={["Mois", ...keys.map(metricName)]}
      rows={months.map((m) => [
        monthLabel(m),
        ...keys.map((k) => {
          const x = series[k].find((y) => y.month === m)
          if (!x || !x.known_n) return "—"
          return (
            <span className={cn((x.alert_level || x.alert_trend) && "font-semibold text-burgundy")}>
              {pct(x.rate_90d)} <span className="text-muted-foreground">({x.known_n})</span>
            </span>
          )
        }),
      ])}
    />
  )
}

function ProfileCard({ p }: { p: P }) {
  if (p.insufficient) return <p className="text-sm text-muted-foreground">Seulement {num(p.orders_12m)} commandes sur 12 mois : profil non établi.</p>
  const fl = p.flows ?? {}
  return (
    <div className="space-y-3">
      <Rows
        rows={[
          ["Catégorie principale", catLabel(p.main_category)],
          ["État du vendeur", stateName(p.seller_state)],
          ["Commandes sur 12 mois", num(p.orders_12m)],
          ["Prix médian", money(p.median_price)],
          ["Délai annoncé moyen", days(p.mean_promised_days)],
          ["Envois hors de son État", fl.interstate_share !== undefined ? pct(fl.interstate_share) : "—"],
          ...(p.descriptive_segment ? ([["Profil", `${p.descriptive_segment.volume} · ${p.descriptive_segment.region}`]] as [string, string][]) : []),
        ]}
      />
      {p.category_distribution?.length > 0 && (
        <>
          <H>Catégories vendues</H>
          <Mini head={["Catégorie", "Commandes", "Part"]} rows={p.category_distribution.map((c: P) => [catLabel(c.category), num(c.orders), pct(c.share)])} />
        </>
      )}
      {fl.destinations?.length > 0 && (
        <>
          <H>Destinations des commandes</H>
          <Mini head={["État client", "Commandes", "Part"]} rows={fl.destinations.map((c: P) => [stateName(c.state), num(c.orders), pct(c.share)])} />
        </>
      )}
    </div>
  )
}

function BenchGroup({ g, title }: { g: P; title: string }) {
  const rate = (["handover", "late", "poor"] as const).filter((k) => g.metrics?.[k])
  return (
    <div className="space-y-2">
      <H>
        {title} · {num(g.n_members)} vendeurs
      </H>
      <Mini
        head={["Indicateur", "Vendeur", "Rang", "Médiane", "Meilleur quart"]}
        rows={rate.map((k) => {
          const x = g.metrics[k]
          return [metricName(k), pct(x.seller_rate), x.rank ? `${x.rank} / ${x.n_ranked}` : "—", pct(x.group_median), pct(x.top_quartile_threshold)]
        })}
      />
    </div>
  )
}

function BenchCard({ p }: { p: P }) {
  if (p.metric) {
    const rows: [string, ReactNode][] = []
    for (const [k, t] of [
      ["category", "Catégorie"],
      ["direct_competitors", "Concurrents directs"],
    ] as const) {
      const x = p[k]
      if (x) rows.push([`${t} · rang`, x.rank ? `${x.rank} / ${x.n_ranked}` : "non classé"], [`${t} · médiane`, pct(x.group_median)], [`${t} · meilleur quart`, pct(x.top_quartile_threshold)])
    }
    return <Rows rows={[["Vendeur · 12 mois", pct(p.category?.seller_rate)], ["Marketplace", pct(p.marketplace_rate)], ...rows]} />
  }
  return (
    <div className="space-y-3">
      {p.category && <BenchGroup g={p.category} title={p.category.label ?? "Catégorie"} />}
      {p.direct_competitors && <BenchGroup g={p.direct_competitors} title="Concurrents directs" />}
      {p.competitors?.length > 0 && (
        <>
          <H>Concurrents directs les plus proches</H>
          <Mini
            head={["Vendeur", "Commandes", "Expédition tardive", "Retard", "Avis négatifs"]}
            rows={p.competitors.slice(0, 10).map((c: P) => [
              <span className="font-mono">{String(c.seller_id).slice(0, 8)}</span>,
              num(c.orders_12m),
              pct(c.rate_handover),
              pct(c.rate_late),
              pct(c.rate_poor),
            ])}
          />
        </>
      )}
    </div>
  )
}

function VoiceCard({ p }: { p: P }) {
  if (!p.available) return <p className="text-sm text-muted-foreground">Avis clients indisponibles.</p>
  const max = Math.max(1, ...(p.top_negative ?? []).map((r: P) => r.negative))
  return (
    <div className="space-y-3">
      <p className="text-sm">
        {num(p.n_written_reviews)} avis écrits sur 12 mois, dont <b>{pct(p.share_rated_1_2)}</b> notés 1 ou 2 étoiles.
      </p>
      <H>Sujets les plus critiqués</H>
      <ul className="space-y-1.5">
        {(p.top_negative ?? []).map((r: P) => (
          <li key={r.aspect} className="space-y-0.5 text-xs">
            <div className="flex justify-between gap-2">
              <span>{r.label}</span>
              <span className="tabular-nums text-muted-foreground">{num(r.negative)} avis</span>
            </div>
            <div className="h-1.5 rounded-full bg-muted">
              <div className="h-1.5 rounded-full bg-plum" style={{ width: `${(100 * r.negative) / max}%` }} />
            </div>
          </li>
        ))}
      </ul>
      {p.quotes?.length > 0 && (
        <>
          <H>Ce que disent les clients</H>
          {p.quotes.map((q: P) => (
            <ReviewCard key={q.review_id} q={q} />
          ))}
        </>
      )}
    </div>
  )
}

function CategoriesCard({ p }: { p: P }) {
  const labels: Record<string, string> = p.labels ?? {}
  return (
    <div className="space-y-3">
      {Object.entries(p.highest_rate_categories ?? {}).map(([m, rows]) => (
        <div key={m} className="space-y-1.5">
          <H>
            {metricName(m)} · marketplace {pct(p.marketplace_90d?.[m]?.rate_90d)}
          </H>
          <Mini head={["Catégorie", "Taux 90 j", "Commandes"]} rows={(rows as P[]).map((r) => [catLabel(r.category), pct(r.rate_90d), num(r.known_n)])} />
        </div>
      ))}
      {p.categories_with_most_alerted_sellers?.length > 0 && (
        <>
          <H>Catégories avec le plus de vendeurs en alerte</H>
          <Mini
            head={["Catégorie", "En alerte", "Évalués"]}
            rows={p.categories_with_most_alerted_sellers.map((r: P) => [catLabel(r.category), num(r.sellers_alerted), num(r.sellers_evaluated)])}
          />
        </>
      )}
      {Object.keys(labels).length === 0 && null}
    </div>
  )
}

function AlertListCard({ p }: { p: P }) {
  return (
    <div className="space-y-3">
      <p className="text-sm">
        {num(p.n_alerted_sellers)} vendeurs en alerte ({num(p.n_alerts)} alertes).
      </p>
      <Mini
        head={["Vendeur", "Catégorie", "Priorité", "Alertes"]}
        rows={(p.listing ?? []).map((r: P) => [
          <span className="font-mono">{String(r.seller_id).slice(0, 8)}</span>,
          catLabel(r.main_category),
          r.top_severity ? <SeverityBadge severity={r.top_severity} /> : "tendance",
          (r.alerts as P[]).map((a) => `${metricName(a.metric).toLowerCase()} ${pct(a.recent_rate)}`).join(" · "),
        ])}
      />
    </div>
  )
}

const LABELS: Record<string, string> = {
  n_evaluated: "Vendeurs évalués",
  n_with_level_alert: "Vendeurs en écart à la marketplace",
  n_with_trend_alert: "Vendeurs en dégradation",
  n_with_any_alert: "Vendeurs avec au moins une alerte",
  n_with_strength: "Vendeurs avec un point fort",
  multi_seller_orders_12m: "Commandes multi-vendeurs (12 mois)",
  single_seller_orders_12m: "Commandes mono-vendeur (12 mois)",
  multi_share: "Part multi-vendeurs",
  observed_events: "Cas observés",
  expected_events: "Cas attendus",
  oe_ratio: "Rapport observé / attendu",
  n_orders_scored: "Commandes analysées",
}

/** Rendu générique lisible (sources des autres agents) : libellés humanisés, valeurs formatées, jamais de JSON brut. */
function Generic({ p, depth = 0 }: { p: unknown; depth?: number }): ReactNode {
  if (p === null || p === undefined) return <span className="text-muted-foreground">—</span>
  if (typeof p === "number") return <span className="tabular-nums">{p > 0 && p < 1 && !Number.isInteger(p) ? pct(p) : num(p)}</span>
  if (typeof p === "boolean") return p ? "oui" : "non"
  if (typeof p === "string") return <span className="[overflow-wrap:anywhere]">{p}</span>
  if (Array.isArray(p)) {
    if (!p.length) return <span className="text-muted-foreground">aucun</span>
    if (p.every((x) => typeof x !== "object" || x === null)) return <span>{p.map(String).join(", ")}</span>
    if (depth > 1) return <span className="text-muted-foreground">{p.length} éléments</span>
    return (
      <ul className="space-y-2">
        {p.slice(0, 12).map((x, i) => (
          <li key={i} className="rounded-md border p-2">
            <Generic p={x} depth={depth + 1} />
          </li>
        ))}
      </ul>
    )
  }
  const entries = Object.entries(p as P).filter(([k]) => !["seller_id", "decision_month", "metric", "note", "method", "model"].includes(k))
  return (
    <dl className="space-y-1.5 text-sm">
      {entries.map(([k, v]) => (
        <div key={k} className={cn(typeof v === "object" && v !== null ? "space-y-1" : "flex items-baseline justify-between gap-4")}>
          <dt className="text-xs text-muted-foreground">{LABELS[k] ?? (k.charAt(0).toUpperCase() + k.slice(1)).replace(/_/g, " ")}</dt>
          <dd className="text-right">
            <Generic p={v} depth={depth + 1} />
          </dd>
        </div>
      ))}
    </dl>
  )
}

function Body({ ev }: { ev: Evidence }) {
  const id = ev.id
  const p = (ev.payload ?? {}) as P
  if (id.startsWith("kpi:seller:")) return <Kpi p={p} />
  if (id.startsWith("kpi:history:")) return <HistoryCard p={p} />
  if (id.startsWith("kpi:categories:")) return <CategoriesCard p={p} />
  if (id.startsWith("kpi:overview:")) return <Generic p={{ ...p.summary, reference_rates: undefined }} />
  if (id.startsWith("alr:list:")) return <AlertListCard p={p} />
  if (id.startsWith("alr:strength:"))
    return (
      <Mini
        head={["Indicateur", "Vendeur · 12 mois", "Référence", "Point fort"]}
        rows={(p.items ?? []).map((i: P) => [i.label, pct(i.year_rate), pct(i.reference_rate), i.strength ? "oui" : "non"])}
      />
    )
  if (id.startsWith("alr:")) return <AlertCard p={p} />
  if (id.startsWith("sel:")) return <ProfileCard p={p} />
  if (id.startsWith("peer:bench:")) return <BenchCard p={p} />
  if (id.startsWith("peer:"))
    return p.benchmark ? (
      <BenchCard p={p.benchmark} />
    ) : (
      <Mini head={["Vendeur", "Catégorie", "Commandes"]} rows={(p.peers ?? []).map((x: P) => [String(x.seller_id).slice(0, 8), catLabel(x.main_category), num(x.orders_12m)])} />
    )
  if (id.startsWith("mdl:aspects:")) return <VoiceCard p={p} />
  if (id.startsWith("rev:")) return <ReviewCard q={p} />
  if (id.startsWith("ord:seller:"))
    return (
      <div className="space-y-2">
        <p className="text-sm">
          {num(p.orders_with_known_problem)} commandes sur {num(p.orders_recent)} (90 derniers jours) avaient déjà un problème connu.
        </p>
        {(p.shown ?? []).map((o: P) => (
          <OrderTimeline key={o.order_id} o={o} />
        ))}
      </div>
    )
  if (id.startsWith("ord:") && p.purchase_date) return <OrderTimeline o={p} />
  if (id === "ctx:limites")
    return (
      <ul className="list-disc space-y-1.5 pl-5 text-sm text-muted-foreground">
        {(p.limites ?? []).map((c: string, i: number) => (
          <li key={i}>{c}</li>
        ))}
      </ul>
    )
  return <Generic p={p} />
}

/** Tiroir de source : fiche lisible de la preuve (tableau d'indicateurs, avis client, chronologie de commande…). */
export function EvidenceDrawer({ evidence, openId, onClose }: { evidence: Evidence[]; openId: string | null; onClose: () => void }) {
  const ev = evidence.find((e) => e.id === openId)
  const meta = openId ? sourceMeta(openId) : null
  const Icon = meta?.icon
  return (
    <Sheet open={openId !== null} onOpenChange={(o) => !o && onClose()}>
      <SheetContent side="right" className="w-full sm:max-w-lg">
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2">
            {Icon && meta && (
              <span className={cn("flex size-7 items-center justify-center rounded-full border", TONE_CLASS[meta.tone])}>
                <Icon className="size-3.5" />
              </span>
            )}
            {meta?.label ?? "Source"}
          </SheetTitle>
          <SheetDescription>{ev ? EVIDENCE_KIND[ev.kind] ?? "Source" : "Cette source n'est pas disponible dans cette vue."}</SheetDescription>
        </SheetHeader>
        {ev && (
          <ScrollArea className="h-[calc(100vh-8rem)] px-4 pb-8">
            <Body ev={ev} />
          </ScrollArea>
        )}
      </SheetContent>
    </Sheet>
  )
}
