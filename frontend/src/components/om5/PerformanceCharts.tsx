import { CartesianGrid, Legend, Line, LineChart, ReferenceDot, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts"
import { CHART } from "@/lib/format"
import { compactNumber, monthLong, monthTick } from "./model"
import type { Om5Mode, TrendRow } from "./types"
import { Panel } from "./ui"

const SELECTED = "#B08418"
const pctFmt = (x: number) => `${new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 1, minimumFractionDigits: 1 }).format(x * 100)} %`
const intFmt = (x: number) => new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 0 }).format(x)
const scoreFmt = (x: number) => `${new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 2, minimumFractionDigits: 2 }).format(x)} / 5`
const brlFmt = (x: number) => `${intFmt(x)} BRL`

interface Series { key: string; name: string; color: string; axis?: "left" | "right"; fmt: (x: number) => string; dash?: string }
interface ChartDef { id: string; title: string; subtitle: string; series: Series[]; leftLabel: string; rightLabel?: string; leftTick: (x: number) => string; rightTick?: (x: number) => string }

const CHARTS: ChartDef[] = [
  { id: "orders", title: "Volume de commandes", subtitle: "Commandes passées par mois", leftLabel: "Commandes", leftTick: compactNumber,
    series: [{ key: "order_count", name: "Commandes", color: "#1E3A66", fmt: intFmt }] },
  { id: "value", title: "Valeur totale des articles", subtitle: "Somme mensuelle des prix des articles (hors chiffre d'affaires net)", leftLabel: "BRL", leftTick: compactNumber,
    series: [{ key: "item_price_total", name: "Valeur des articles", color: "#B08418", fmt: brlFmt }] },
  { id: "delivery", title: "Performance de livraison", subtitle: "Part des commandes livrées en retard et expédiées tardivement", leftLabel: "% des commandes", leftTick: (x) => `${Math.round(x * 100)} %`,
    series: [
      { key: "late_rate", name: "Retard de livraison", color: "#2F6BB0", fmt: pctFmt },
      { key: "late_handover_rate", name: "Remise tardive au transporteur", color: "#7A8CA5", fmt: pctFmt, dash: "5 4" },
    ] },
  { id: "satisfaction", title: "Satisfaction client", subtitle: "Note moyenne (axe gauche) et part d'avis négatifs (axe droit)", leftLabel: "Note /5", rightLabel: "% d'avis négatifs",
    leftTick: (x) => x.toFixed(1).replace(".", ","), rightTick: (x) => `${Math.round(x * 100)} %`,
    series: [
      { key: "average_review_score", name: "Note moyenne", color: "#2F8F5B", fmt: scoreFmt },
      { key: "poor_review_rate", name: "Avis négatifs", color: "#A8325A", fmt: pctFmt, axis: "right" },
    ] },
]

interface TipProps { active?: boolean; label?: string | number; payload?: readonly { dataKey?: unknown; color?: string; name?: string | number; value?: unknown }[] }

function makeTooltip(series: Series[], month: string) {
  return function Tip({ active, label, payload }: TipProps) {
    if (!active || !payload?.length) return null
    const m = String(label)
    return (
      <div className="rounded-lg border bg-popover px-3 py-2 text-xs shadow-md">
        <p className="mb-1 font-semibold capitalize text-ink">{monthLong(m)}{m === month && <span className="ml-1.5 rounded bg-butter px-1 py-0.5 text-[10px] font-medium text-navy">mois analysé</span>}</p>
        {payload.map((p) => {
          const s = series.find((x) => x.key === p.dataKey)
          return (
            <p key={String(p.dataKey)} className="flex items-center gap-2">
              <span className="size-2 rounded-full" style={{ background: p.color }} />
              <span className="text-muted-foreground">{s?.name ?? p.name}</span>
              <span className="ml-auto pl-3 font-medium tabular-nums text-ink">{typeof p.value === "number" && s ? s.fmt(p.value) : "—"}</span>
            </p>
          )
        })}
      </div>
    )
  }
}

function TrendChart({ def, rows, month }: { def: ChartDef; rows: TrendRow[]; month: string }) {
  const dual = def.series.some((s) => s.axis === "right")
  const selected = rows.find((r) => r.purchase_month === month)
  return (
    <Panel title={def.title} subtitle={def.subtitle}>
      <div className="h-64" role="img" aria-label={`${def.title}, évolution mensuelle jusqu'à ${monthLong(month)}`}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={rows} margin={{ top: 4, right: dual ? 4 : 12, bottom: 18, left: 0 }}>
            <CartesianGrid stroke={CHART.grid} strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="purchase_month" tickFormatter={monthTick} tick={{ fontSize: 10, fill: CHART.tick }} minTickGap={18} tickLine={false}
              label={{ value: "Mois d'achat", position: "insideBottom", offset: -12, style: { fontSize: 10, fill: CHART.tick } }} />
            <YAxis yAxisId="left" tickFormatter={def.leftTick} tick={{ fontSize: 10, fill: CHART.tick }} width={58} tickLine={false} axisLine={false} domain={["auto", "auto"]}
              label={{ value: def.leftLabel, angle: -90, position: "insideLeft", offset: 4, style: { fontSize: 10, fill: CHART.tick, textAnchor: "middle" } }} />
            {dual && <YAxis yAxisId="right" orientation="right" tickFormatter={def.rightTick} tick={{ fontSize: 10, fill: CHART.tick }} width={48} tickLine={false} axisLine={false}
              label={{ value: def.rightLabel, angle: 90, position: "insideRight", offset: 14, style: { fontSize: 10, fill: CHART.tick, textAnchor: "middle" } }} />}
            <Tooltip content={makeTooltip(def.series, month)} cursor={{ stroke: CHART.reference, strokeDasharray: "3 3" }} />
            <Legend verticalAlign="top" height={26} iconType="plainline" wrapperStyle={{ fontSize: 11 }} />
            {selected && <ReferenceLine yAxisId="left" x={month} stroke={SELECTED} strokeDasharray="4 3" strokeWidth={1.5} />}
            {def.series.map((s) => (
              <Line key={s.key} yAxisId={s.axis ?? "left"} dataKey={s.key} name={s.name} stroke={s.color} strokeWidth={2.25} strokeDasharray={s.dash} dot={false} activeDot={{ r: 4 }} connectNulls />
            ))}
            {selected && def.series.map((s) => typeof selected[s.key] === "number" && (
              <ReferenceDot key={`d-${s.key}`} yAxisId={s.axis ?? "left"} x={month} y={selected[s.key] as number} r={5} fill={SELECTED} stroke="#132238" strokeWidth={1.5} ifOverflow="extendDomain" />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </Panel>
  )
}

export function PerformanceCharts({ rows, month, mode }: { rows: TrendRow[]; month: string; mode: Om5Mode }) {
  if (!rows.length) return <Panel title="Tendances mensuelles"><p className="text-sm text-muted-foreground">Aucun historique mensuel complet n'est disponible pour cette période.</p></Panel>
  return (
    <div className="space-y-3">
      <div className="grid gap-4 md:grid-cols-2">{CHARTS.map((c) => <TrendChart key={c.id} def={c} rows={rows} month={month} />)}</div>
      <p className="px-1 text-[11px] leading-relaxed text-muted-foreground">
        Mois complets uniquement{mode === "as_of" ? ` · mode « à date » : aucun mois postérieur à ${monthLong(month)} n'est affiché` : " · mode rétrospectif : l'historique complet est affiché"}.
        La ligne dorée marque le mois analysé.
      </p>
    </div>
  )
}
