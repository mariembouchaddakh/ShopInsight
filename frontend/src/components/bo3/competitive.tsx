import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip as RTooltip, XAxis, YAxis } from "recharts"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import type { Benchmark, GroupBench, MetricKey, RateBench } from "@/lib/api"
import { CHART, METRICS, METRIC_COLOR, METRIC_SHORT, num, pct, shortId } from "@/lib/format"
import { stateName } from "@/lib/geo"
import { cn } from "@/lib/utils"
import { SourcePills } from "@/components/evidence/source-pill"
import { catLabel } from "@/lib/categories"

// Palette catégorielle validée (ordre fixe) : vendeur, médiane catégorie, médiane concurrents directs, seuil du meilleur quart.
// validée (séries adjacentes, fond blanc) : vendeur marine, médiane catégorie moutarde, médiane concurrents prune, meilleur quart vert forêt
export const BENCH_COLOR = { seller: "#2F6BB0", category: "#B08418", direct: "#7357B8", top: "#2F8F5B" }

/** Jauge de rang : à gauche le meilleur (rang 1), zone verte = meilleur quart du groupe. Rang 1 = taux le plus bas. */
export function RankGauge({ rank, n, label, compact = false }: { rank: number | null; n: number; label: string; compact?: boolean }) {
  const pos = rank && n > 1 ? (rank - 1) / (n - 1) : 0
  return (
    <div className="min-w-0 space-y-1">
      <div className="flex items-baseline justify-between gap-2">
        <span className={cn("truncate text-muted-foreground", compact ? "text-[11px]" : "text-xs")}>{label}</span>
        <span className={cn("shrink-0 font-semibold tabular-nums", compact ? "text-xs" : "text-sm")}>
          {rank ? (
            <>
              Rang #{num(rank)} <span className="font-normal text-muted-foreground">/ {num(n)}</span>
            </>
          ) : (
            <span className="font-normal text-muted-foreground">non classé</span>
          )}
        </span>
      </div>
      <div
        className={cn("relative rounded-full bg-muted", compact ? "h-1.5" : "h-2")}
        role="img"
        aria-label={rank ? `${label} : rang ${rank} sur ${n} (1 = meilleur)` : `${label} : non classé`}
      >
        <div className="absolute inset-y-0 left-0 w-1/4 rounded-l-full bg-sage" title="Meilleur quart du groupe" />
        {rank && (
          <div
            className={cn("absolute top-1/2 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-background bg-foreground", compact ? "size-2.5" : "size-3.5")}
            style={{ left: `${pos * 100}%` }}
          />
        )}
      </div>
    </div>
  )
}

function GroupPanel({ g, title, metrics }: { g: GroupBench; title: string; metrics: MetricKey[] }) {
  return (
    <div className="min-w-0 space-y-3 rounded-lg border p-3">
      <div>
        <h3 className="text-sm font-semibold">{title}</h3>
        <p className="text-xs text-muted-foreground [overflow-wrap:anywhere]">
          {g.label} · {num(g.n_members)} vendeurs · rang par volume #{num(g.volume_rank)}
          {g.overall.in_top_quartile ? " · dans le meilleur quart" : ""}
        </p>
      </div>
      <RankGauge rank={g.overall.rank} n={g.overall.n_ranked} label="Classement global (trois taux)" />
      <div className="space-y-2">
        {metrics.map((k) => {
          const x: RateBench = g.metrics[k]
          return (
            <div key={k} className="space-y-0.5">
              <RankGauge compact rank={x.rank} n={x.n_ranked} label={METRIC_SHORT[k]} />
              {x.seller_rate === null && <p className="text-[11px] text-muted-foreground">non classé : moins de {g.min_known_n} commandes dont l'issue est connue</p>}
            </div>
          )
        })}
      </div>
    </div>
  )
}

/** Paysage concurrentiel : rangs (catégorie, concurrents directs), comparaison côte à côte et liste des concurrents directs. */
export function CompetitiveLandscape({ bench, evidenceId, onOpen }: { bench: Benchmark; evidenceId: string; onOpen: (id: string) => void }) {
  const metrics = METRICS.filter((k) => bench.category.metrics[k])
  const c = bench.category.metrics
  const dmet = bench.direct_competitors.metrics
  const chart = metrics.map((k) => ({
    metric: METRIC_SHORT[k],
    seller: c[k].seller_rate,
    category: c[k].group_median,
    direct: dmet[k].group_median,
    top: c[k].top_quartile_threshold,
  }))
  const desc: { key: "median_price" | "freight_share" | "promised_days"; label: string; fmt: (v: number | null) => string }[] = [
    { key: "median_price", label: "Prix médian", fmt: (v) => (v === null ? "—" : `${v.toLocaleString("fr-FR")} R$`) },
    { key: "freight_share", label: "Part du port", fmt: (v) => pct(v) },
    { key: "promised_days", label: "Délai promis moyen", fmt: (v) => (v === null ? "—" : `${v.toLocaleString("fr-FR")} j`) },
  ]
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">Positionnement concurrentiel</CardTitle>
        <CardDescription>
          Descriptif : taux sur 12 mois d'issues connues à la décision ; rang 1 = taux le plus bas. Les alertes restent calibrées sur la marketplace. Concurrents
          directs : 20 vendeurs les plus proches par catégories vendues, volume, prix, part du port et délai promis (aucune issue n'entre dans la similarité).
        </CardDescription>
        <SourcePills ids={[evidenceId]} onOpen={onOpen} />
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="grid gap-3 md:grid-cols-2">
          <GroupPanel g={bench.category} title="Dans sa catégorie" metrics={metrics} />
          <GroupPanel g={bench.direct_competitors} title="Parmi ses concurrents directs" metrics={metrics} />
        </div>

        <div className="grid gap-4 lg:grid-cols-5">
          <div className="h-64 min-w-0 lg:col-span-3">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chart} layout="vertical" margin={{ left: 8, right: 16 }} barGap={2} barCategoryGap="22%">
                <CartesianGrid strokeDasharray="3 3" stroke={CHART.grid} horizontal={false} />
                <XAxis type="number" tick={{ fontSize: 11, fill: CHART.tick }} tickFormatter={(v) => `${Math.round(v * 100)} %`} />
                <YAxis type="category" dataKey="metric" width={110} tick={{ fontSize: 11, fill: CHART.tick }} />
                <RTooltip contentStyle={{ fontSize: 12 }} formatter={(v, name) => [pct(v as number), name]} cursor={{ fill: "rgba(0,0,0,0.04)" }} />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Bar dataKey="seller" name="Vendeur" fill={BENCH_COLOR.seller} radius={[0, 4, 4, 0]} isAnimationActive={false} />
                <Bar dataKey="category" name="Médiane catégorie" fill={BENCH_COLOR.category} radius={[0, 4, 4, 0]} isAnimationActive={false} />
                <Bar dataKey="direct" name="Médiane concurrents directs" fill={BENCH_COLOR.direct} radius={[0, 4, 4, 0]} isAnimationActive={false} />
                <Bar dataKey="top" name="Seuil du meilleur quart (catégorie)" fill={BENCH_COLOR.top} radius={[0, 4, 4, 0]} isAnimationActive={false} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="min-w-0 overflow-x-auto rounded-lg border lg:col-span-2">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Profil commercial</TableHead>
                  <TableHead className="text-right">Vendeur</TableHead>
                  <TableHead className="text-right">Médiane cat.</TableHead>
                  <TableHead className="text-right">Meilleur quart cat.</TableHead>
                  <TableHead className="text-right">Médiane conc.</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {desc.map(({ key, label, fmt }) => (
                  <TableRow key={key}>
                    <TableCell className="text-xs">{label}</TableCell>
                    <TableCell className="text-right text-xs font-medium tabular-nums">{fmt(bench.category.metrics[key].seller_value)}</TableCell>
                    <TableCell className="text-right text-xs tabular-nums">{fmt(bench.category.metrics[key].group_median)}</TableCell>
                    <TableCell className="text-right text-xs tabular-nums">{fmt(bench.category.metrics[key].top_quartile_median)}</TableCell>
                    <TableCell className="text-right text-xs tabular-nums">{fmt(bench.direct_competitors.metrics[key].group_median)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <p className="px-3 py-2 text-[11px] text-muted-foreground">Meilleur quart : 25 % des vendeurs de la catégorie au meilleur classement global (médiane du groupe).</p>
          </div>
        </div>

        <div className="space-y-3">
          <div className="flex flex-wrap items-end justify-between gap-2">
            <div>
              <h3 className="font-display text-base font-bold">Concurrents directs les plus proches</h3>
              <p className="text-xs text-muted-foreground">Vendeurs à l'activité la plus semblable : mêmes catégories, volume, prix, frais de port et délai annoncé.</p>
            </div>
            <p className="flex items-center gap-3 text-[11px] text-muted-foreground">
              <span className="inline-flex items-center gap-1"><span className="size-2 rounded-full bg-forest-mark" /> fait mieux que ce vendeur (barres « Vendeur » ci-dessus)</span>
              <span className="inline-flex items-center gap-1"><span className="size-2 rounded-full bg-burgundy" /> fait moins bien</span>
            </p>
          </div>
          <div className="overflow-x-auto rounded-xl border">
            <Table>
              <TableHeader>
                <TableRow className="bg-muted/40">
                  <TableHead>Vendeur</TableHead>
                  <TableHead>Localisation</TableHead>
                  <TableHead className="text-right">Commandes (12 mois)</TableHead>
                  {metrics.map((k) => (
                    <TableHead key={k} className="text-right">
                      <span className="inline-flex items-center gap-1">
                        <span className="size-2 rounded-full" style={{ background: METRIC_COLOR[k] }} />
                        {METRIC_SHORT[k]}
                      </span>
                    </TableHead>
                  ))}
                  <TableHead className="text-right">Prix médian</TableHead>
                  <TableHead className="text-right">Délai annoncé</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {bench.competitors.map((x) => (
                  <TableRow key={x.seller_id} className="transition-colors hover:bg-muted/40">
                    <TableCell>
                      <a href={`/bo3/sellers/${x.seller_id}?month=${bench.decision_month}`} className="font-mono text-xs font-medium hover:text-ink hover:underline hover:underline">
                        {shortId(x.seller_id)}
                      </a>
                      <div className="text-[11px] text-muted-foreground">{catLabel(x.main_category)}</div>
                    </TableCell>
                    <TableCell className="text-xs">{stateName(x.seller_state)}</TableCell>
                    <TableCell className="text-right text-xs tabular-nums">{num(x.orders_12m)}</TableCell>
                    {metrics.map((k) => {
                      const v = x[`rate_${k}`]
                      const own = c[k].seller_rate
                      const better = v !== null && own !== null ? v < own : null
                      return (
                        <TableCell key={k} className="text-right text-xs tabular-nums" title={`Calculé sur ${num(x[`known_n_${k}`])} commandes dont l'issue est connue`}>
                          {v === null ? (
                            <span className="text-muted-foreground">—</span>
                          ) : (
                            <span className="inline-flex items-center justify-end gap-1.5">
                              {better !== null && v !== own && <span className={cn("size-1.5 rounded-full", better ? "bg-forest-mark" : "bg-burgundy")} aria-label={better ? "fait mieux" : "fait moins bien"} />}
                              {pct(v)}
                            </span>
                          )}
                        </TableCell>
                      )
                    })}
                    <TableCell className="text-right text-xs tabular-nums">{x.median_price === null ? "—" : `${x.median_price.toLocaleString("fr-FR")} R$`}</TableCell>
                    <TableCell className="text-right text-xs tabular-nums">{x.promised_days === null ? "—" : `${x.promised_days.toLocaleString("fr-FR")} j`}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          <p className="text-[11px] leading-relaxed text-muted-foreground">
            Taux sur 12 mois, calculés sur les commandes dont l'issue était connue à la date du bilan (survolez un taux pour voir sur combien de commandes).
            « — » : moins de {bench.category.min_known_n} commandes évaluées, taux non significatif.
          </p>
        </div>
      </CardContent>
    </Card>
  )
}
