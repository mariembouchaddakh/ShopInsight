import { Bar, BarChart, CartesianGrid, LabelList, ResponsiveContainer, Tooltip as RTooltip, XAxis, YAxis } from "recharts"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import type { Flows } from "@/lib/api"
import { CHART, monthLabel, num, pct } from "@/lib/format"
import { SourcePills } from "@/components/evidence/source-pill"
import { catLabel } from "@/lib/categories"
import { stateName } from "@/lib/geo"

type Row = { name: string; orders: number; share: number }

function ShareBars({ rows, color, height }: { rows: Row[]; color: string; height: number }) {
  return (
    <div style={{ height }} className="min-w-0">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={rows} layout="vertical" margin={{ left: 4, right: 56 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={CHART.grid} horizontal={false} />
          <XAxis type="number" hide domain={[0, "dataMax"]} />
          <YAxis type="category" dataKey="name" width={120} tick={{ fontSize: 11, fill: CHART.tick }} interval={0} />
          <RTooltip
            contentStyle={{ fontSize: 12 }}
            cursor={{ fill: "rgba(0,0,0,0.04)" }}
            formatter={(v, _n, item) => [`${num(v as number)} commandes (${pct((item.payload as Row).share)})`, "Commandes"]}
          />
          <Bar dataKey="orders" fill={color} radius={[0, 4, 4, 0]} isAnimationActive={false}>
            <LabelList dataKey="share" position="right" formatter={(v) => pct(v as number, 0)} style={{ fontSize: 11, fill: CHART.tick }} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

/** Flux sortants (État du vendeur → États des clients) et répartition des catégories sur 12 mois (commandes mono-vendeur). */
export function FlowsAndMix({
  flows,
  categories,
  monthly = [],
  showDestinations = true,
  evidenceId,
  onOpen,
}: {
  flows: Flows
  categories: { category: string; orders: number; share: number }[]
  monthly?: { month: string; orders: number }[]
  showDestinations?: boolean
  evidenceId: string
  onOpen: (id: string) => void
}) {
  const dest = flows.destinations.map((d) => ({ name: d.state === flows.origin_state ? `${stateName(d.state)} (même État)` : stateName(d.state), orders: d.orders, share: d.share }))
  const cats = categories.map((c) => ({ name: catLabel(c.category), orders: c.orders, share: c.share }))
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">Catalogue et volume</CardTitle>
        <CardDescription>
          Ce que vend ce vendeur et son volume mois par mois, sur les 12 mois avant la décision
          {flows.same_state_share !== null ? ` · ${pct(flows.same_state_share)} de ses commandes restent dans son propre État` : ""}.
        </CardDescription>
        <SourcePills ids={[evidenceId]} onOpen={onOpen} />
      </CardHeader>
      <CardContent className="grid gap-6 md:grid-cols-2">
        {showDestinations && <div className="min-w-0 space-y-1">
          <h3 className="text-xs font-semibold">
            {flows.origin_state ? `${stateName(flows.origin_state)} → États des clients` : "États des clients"}
          </h3>
          <ShareBars rows={dest} color="#2F6BB0" height={Math.max(160, dest.length * 26)} />
        </div>}
        <div className={showDestinations ? "min-w-0 space-y-1" : "min-w-0 space-y-1 md:col-span-2"}>
          <h3 className="text-xs font-semibold">Répartition des catégories vendues</h3>
          <ShareBars rows={cats} color="#2F6BB0" height={Math.max(160, cats.length * 26)} />
        </div>
        {monthly.length > 0 && (
          <div className="min-w-0 space-y-1 md:col-span-2">
            <h3 className="text-xs font-semibold">Volume de commandes par mois d'achat (12 derniers mois)</h3>
            <div className="h-48">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={monthly} margin={{ left: -16, right: 8, top: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke={CHART.grid} vertical={false} />
                  <XAxis dataKey="month" tick={{ fontSize: 11, fill: CHART.tick }} tickFormatter={(m) => monthLabel(String(m))} interval="preserveStartEnd" />
                  <YAxis tick={{ fontSize: 11, fill: CHART.tick }} allowDecimals={false} width={44} />
                  <RTooltip contentStyle={{ fontSize: 12 }} cursor={{ fill: "rgba(0,0,0,0.04)" }} labelFormatter={(m) => monthLabel(String(m))} formatter={(v) => [`${num(v as number)} commandes`, "Volume"]} />
                  <Bar dataKey="orders" fill="#2F6BB0" radius={[4, 4, 0, 0]} isAnimationActive={false} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
