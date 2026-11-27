import { ArrowDownRight, ArrowUpRight, Banknote, Clock, Minus, Package, Star, Store, ThumbsDown, Users } from "lucide-react"
import type { ComponentType } from "react"
import { Line, LineChart, ResponsiveContainer, YAxis } from "recharts"
import { cn } from "@/lib/utils"
import { formatValue, monthLong, signed, variationOf, type Tone, type Variation } from "./model"
import type { Om5Kpi, Om5View, TrendRow } from "./types"
import { TONE } from "./tone"
import { Pill } from "./ui"

interface Cfg {
  id: string
  title: string
  icon: ComponentType<{ className?: string }>
  /** Colonne de /api/om5/trends utilisée pour la sparkline (absente → pas de sparkline). */
  trend?: string
  note?: string
}

const CONFIG: Cfg[] = [
  { id: "order_count", title: "Nombre de commandes", icon: Package, trend: "order_count" },
  { id: "item_price_total", title: "Valeur totale des articles", icon: Banknote, trend: "item_price_total", note: "Somme des prix des articles — ni chiffre d'affaires net, ni bénéfice." },
  { id: "late_rate", title: "Taux de retard", icon: Clock, trend: "late_rate" },
  { id: "average_review_score", title: "Satisfaction moyenne", icon: Star, trend: "average_review_score" },
  { id: "poor_review_rate", title: "Taux d'avis négatifs", icon: ThumbsDown, trend: "poor_review_rate" },
  { id: "active_seller_count", title: "Vendeurs actifs", icon: Users },
  { id: "alerted_seller_count", title: "Vendeurs en alerte", icon: Store },
]

function status(v: Om5View, k: Om5Kpi | undefined, id: string): { tone: Tone; label: string } {
  const a = v.anomalies.find((x) => x.metric_id === id)
  if (a) {
    if (a.anomaly) return a.severity === "high" ? { tone: "bad", label: "Anomalie élevée" } : { tone: "warn", label: "Anomalie modérée" }
    return { tone: "good", label: "Dans la norme" }
  }
  if (k && k.quality_status !== "complete") return { tone: "warn", label: "Données partielles" }
  if (id === "alerted_seller_count") {
    const d = v.kpis.find((x) => x.metric_id === "alerted_seller_change")?.value
    return d != null && d > 0 ? { tone: "warn", label: "En hausse" } : { tone: "neutral", label: "Sous suivi" }
  }
  return { tone: "neutral", label: "Sous suivi" }
}

function variation(v: Om5View, id: string): Variation | null {
  if (id === "alerted_seller_count") {
    const d = v.kpis.find((x) => x.metric_id === "alerted_seller_change")?.value
    if (d == null) return null
    const sign = d === 0 ? 0 : d > 0 ? 1 : -1
    return { text: sign === 0 ? "Stable" : `${signed(d, 0)} vendeur${Math.abs(d) > 1 ? "s" : ""}`, sign, favorable: sign === 0 ? null : sign < 0, basis: "vs mois précédent" }
  }
  return variationOf(v.comparisons.find((c) => c.metric_id === id))
}

function Spark({ rows, col, month, label }: { rows: TrendRow[]; col: string; month: string; label: string }) {
  const data = rows.filter((r) => typeof r[col] === "number").map((r) => ({ m: String(r.purchase_month), y: r[col] as number }))
  if (data.length < 3) return <p className="h-10 text-[11px] text-muted-foreground">Historique insuffisant</p>
  const last = data.find((d) => d.m === month) ?? data[data.length - 1]
  return (
    <div className="h-10" role="img" aria-label={`Évolution mensuelle — ${label}, jusqu'à ${monthLong(last.m)}`}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 4, right: 4, bottom: 4, left: 4 }}>
          <YAxis hide domain={["dataMin", "dataMax"]} />
          <Line type="monotone" dataKey="y" stroke="#1E3A66" strokeWidth={1.75} isAnimationActive={false}
            dot={(p: { cx?: number; cy?: number; payload?: { m: string }; index?: number }) =>
              p.payload?.m === last.m && p.cx != null && p.cy != null
                ? <circle key={`d-${p.index}`} cx={p.cx} cy={p.cy} r={3.5} fill="#F6E08D" stroke="#132238" strokeWidth={1.5} />
                : <g key={`d-${p.index}`} />} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

export function KpiCards({ view, trends }: { view: Om5View; trends: TrendRow[] }) {
  return (
    <section aria-label="Indicateurs clés" className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      {CONFIG.map((c) => {
        const k = view.kpis.find((x) => x.metric_id === c.id)
        const f = k ? formatValue(k.unit, k.value) : { main: "—", unit: "" }
        const st = status(view, k, c.id)
        const va = variation(view, c.id)
        const Icon = c.icon
        const Arrow = !va || va.sign === 0 ? Minus : va.sign > 0 ? ArrowUpRight : ArrowDownRight
        const vTone: Tone = !va || va.favorable == null ? "neutral" : va.favorable ? "good" : st.tone === "bad" ? "bad" : "warn"
        return (
          <article key={c.id} className="lift flex flex-col gap-3 rounded-2xl bg-card p-5 shadow-[0_1px_2px_rgb(19_34_56/6%)] ring-1 ring-foreground/10">
            <div className="flex items-start justify-between gap-2">
              <span className="grid size-10 place-items-center rounded-xl bg-navy-tint text-navy-soft"><Icon className="size-5" /></span>
              <Pill tone={st.tone}>{st.label}</Pill>
            </div>
            <div>
              <h3 className="text-[0.8rem] font-medium text-muted-foreground">{c.title}</h3>
              <p className="mt-1 flex items-baseline gap-1.5">
                <span className="font-display text-[1.9rem] leading-none font-bold tracking-tight text-ink tabular-nums">{k && k.value != null ? f.main : "Indisponible"}</span>
                {k && k.value != null && f.unit && <span className="text-sm font-medium text-muted-foreground">{f.unit}</span>}
              </p>
            </div>
            <p className={cn("flex items-center gap-1.5 text-xs", TONE[vTone].text)}>
              <Arrow className="size-4" aria-hidden />
              {va ? <><span className="font-semibold">{va.text}</span><span className="text-muted-foreground">{va.basis}</span></> : <span className="text-muted-foreground">Variation historique non disponible</span>}
            </p>
            {c.trend ? <Spark rows={trends} col={c.trend} month={view.month} label={c.title} /> : <p className="h-10 text-[11px] leading-snug text-muted-foreground">Pas d'historique mensuel fourni pour cet indicateur.</p>}
            {c.note && <p className="text-[11px] leading-snug text-muted-foreground">{c.note}</p>}
          </article>
        )
      })}
    </section>
  )
}
