import { useQuery } from "@tanstack/react-query"
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip as RTooltip, XAxis, YAxis } from "recharts"
import { ErrorBlock, LoadingBlock } from "@/components/app/states"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { api, type HistoryPoint, type MetricKey } from "@/lib/api"
import { CHART, METRICS, METRIC_COLOR, METRIC_SHORT, monthLabel, num, pct } from "@/lib/format"
import { SourcePills } from "@/components/evidence/source-pill"

type Point = { month: string } & Partial<Record<MetricKey, number | null>> & Partial<Record<`${MetricKey}_p`, HistoryPoint>>

/** Trajectoire sur 18 mois : taux sur 90 jours de chaque indicateur à chaque fin de mois (données connues à cette date), marqueurs d'alerte. */
export function Trajectory({ seller, month, onOpen }: { seller: string; month: string; onOpen: (id: string) => void }) {
  const h = useQuery({ queryKey: ["history", seller, month], queryFn: () => api.history(seller, month, 18), enabled: !!month })
  if (h.isError) return <ErrorBlock error={h.error} />
  const series = h.data?.result.series ?? {}
  const byMonth = new Map<string, Point>()
  for (const k of METRICS)
    for (const p of series[k] ?? []) {
      const row = byMonth.get(p.month) ?? { month: p.month }
      row[k] = p.known_n ? p.rate_90d : null
      row[`${k}_p`] = p
      byMonth.set(p.month, row)
    }
  const data = [...byMonth.values()].sort((a, b) => a.month.localeCompare(b.month))
  const metrics = METRICS.filter((k) => series[k]?.length)
  const nAlerts = data.reduce((s, r) => s + metrics.filter((k) => r[`${k}_p`]?.alert_level || r[`${k}_p`]?.alert_trend).length, 0)

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">Trajectoire sur 18 mois</CardTitle>
        <CardDescription>
          Taux sur 90 jours à chaque fin de mois, avec les seules données connues à cette date. Grand point cerclé de rouge : alerte (écart à la marketplace ou dégradation récente) ce
          mois-là ({num(nAlerts)} au total) ; point creux : moins de 10 issues connues (peu fiable).
        </CardDescription>
        <SourcePills ids={[`kpi:history:${seller.slice(0, 8)}:${month}`]} onOpen={onOpen} />
      </CardHeader>
      <CardContent className="h-72">
        {h.isLoading ? (
          <LoadingBlock rows={5} />
        ) : data.length < 2 ? (
          <p className="text-sm text-muted-foreground">Historique trop court pour un graphique.</p>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ left: -10, right: 8 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={CHART.grid} vertical={false} />
              <XAxis dataKey="month" tick={{ fontSize: 11, fill: CHART.tick }} tickFormatter={(m) => m.slice(2)} />
              <YAxis tick={{ fontSize: 11, fill: CHART.tick }} tickFormatter={(v) => `${Math.round(v * 100)} %`} width={48} />
              <RTooltip
                contentStyle={{ fontSize: 12 }}
                labelFormatter={(m) => monthLabel(String(m))}
                formatter={(v, name, item) => {
                  const k = METRICS.find((x) => METRIC_SHORT[x] === name)
                  const p = k ? (item.payload as Point)[`${k}_p`] : undefined
                  const flags = p ? [p.alert_level && "écart à la marketplace", p.alert_trend && "dégradation récente"].filter(Boolean).join(", ") : ""
                  return [`${pct(v as number)}${p ? `  sur ${p.known_n} commandes · marketplace ${pct(p.reference)}` : ""}${flags ? ` · ${flags}` : ""}`, name]
                }}
              />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              {metrics.map((k) => (
                <Line
                  key={k}
                  type="linear"
                  dataKey={k}
                  name={METRIC_SHORT[k]}
                  stroke={METRIC_COLOR[k]}
                  strokeWidth={2}
                  connectNulls
                  isAnimationActive={false}
                  dot={(props) => {
                    const { cx, cy, payload, index } = props as { cx: number; cy: number; payload: Point; index: number }
                    const p = payload[`${k}_p`]
                    if (cx == null || cy == null || !p) return <g key={`${k}-${index}`} />
                    const alert = p.alert_level || p.alert_trend
                    const weak = p.known_n < 10
                    return (
                      <g key={`${k}-${index}`}>
                        {alert && <circle cx={cx} cy={cy} r={7} fill="none" stroke={CHART.alert} strokeWidth={2} />}
                        <circle cx={cx} cy={cy} r={alert ? 4.5 : 3} fill={weak ? "#ffffff" : METRIC_COLOR[k]} stroke={METRIC_COLOR[k]} strokeWidth={weak ? 1.5 : 0} />
                      </g>
                    )
                  }}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        )}
      </CardContent>
    </Card>
  )
}
