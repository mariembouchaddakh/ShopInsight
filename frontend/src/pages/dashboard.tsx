import { useQuery } from "@tanstack/react-query"
import { ArrowRight, Bell, Map as MapIcon, MessageCircle, PhoneCall, Store } from "lucide-react"
import { Link } from "react-router-dom"
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip as RTooltip, XAxis, YAxis } from "recharts"
import { useDecisionMonth } from "@/components/app/month"
import { openAssistant } from "@/components/assistant/assistant-widget"
import { CountUp } from "@/components/brand/count-up"
import { LogoMark } from "@/components/brand/logo"
import { Button } from "@/components/ui/button"
import { ErrorBlock, LoadingBlock } from "@/components/app/states"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { api, type MetricKey } from "@/lib/api"
import { CHART, METRICS, METRIC_COLOR, METRIC_SHORT, monthLabel, pct } from "@/lib/format"

const tick = { fontSize: 11, fill: CHART.tick }
// Ce que mesure chaque taux de référence (les nombres de vendeurs en alerte sont sur la page Alertes).
const METRIC_DEFINITION: Record<MetricKey, string> = {
  late: "Part des commandes de la marketplace livrées après la date annoncée, sur 12 mois.",
  poor: "Part des commandes de la marketplace notées 1 ou 2 étoiles, sur 12 mois.",
  handover: "Part des commandes remises au transporteur après la date limite, sur 12 mois.",
}

export function DashboardPage() {
  const [month] = useDecisionMonth()
  const meta = useQuery({ queryKey: ["meta"], queryFn: api.meta, staleTime: Infinity })
  const market = useQuery({ queryKey: ["marketplace"], queryFn: api.marketplace, staleTime: Infinity })

  if (market.isError) return <ErrorBlock error={market.error} />
  const series = market.data?.result.series ?? {}
  const months = (series.late ?? []).map((p) => p.month)
  const rows = months.map((m) => {
    const r: Record<string, string | number | null> = { month: m }
    for (const k of METRICS) {
      const p = series[k]?.find((x) => x.month === m)
      r[`ref_${k}`] = p?.reference_rate ?? null
      r[`alerts_${k}`] = p?.alerts_level ?? 0
    }
    return r
  })
  const at = (k: MetricKey) => series[k]?.find((p) => p.month === month)
  const ts = meta.data?.test_summary

  return (
    <div className="space-y-6">
      <section className="brand-gradient relative overflow-hidden rounded-3xl px-6 py-8 text-white shadow-[0_24px_60px_-28px_rgb(19_34_56/70%)] md:px-10">
        <LogoMark size={220} handle="rgb(246 224 141 / 60%)" className="pointer-events-none absolute -right-10 -bottom-16 rotate-12 opacity-20" />
        <p className="text-xs font-semibold tracking-[0.16em] text-butter uppercase">Tableau de bord · fin {month ? monthLabel(month) : "…"}</p>
        <h1 className="mt-2 max-w-2xl text-3xl leading-tight font-bold md:text-4xl">
          <span className="sr-only">Tableau de bord — </span>Bonjour 👋 Voici l'état de vos vendeurs ce mois-ci.</h1>
        <p className="mt-3 max-w-2xl text-sm leading-relaxed text-white/85">
          Taux calculés avec les seules informations connues à la fin du mois ; les commandes partagées entre plusieurs vendeurs sont exclues.
        </p>
        <div className="mt-6 flex flex-wrap gap-2">
          <Link to={`/bo3/sellers?month=${month ?? ""}`}>
            <Button size="lg">
              <Store className="size-4" /> Parcourir les vendeurs
            </Button>
          </Link>
          <Button size="lg" variant="outline" className="border-white/40 bg-white/10 text-white hover:bg-white/20 hover:text-white" onClick={() => openAssistant("Quels vendeurs nécessitent une action urgente ce mois-ci ?")}>
            <MessageCircle className="size-4" /> Qui traiter en priorité ?
          </Button>
        </div>
      </section>
      <div className="stagger grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {METRICS.map((k) => {
          const p = at(k)
          return (
            <Card key={k} size="sm" className="lift">
              <CardHeader>
                <CardDescription className="flex items-center gap-2">
                  <span className="size-2 rounded-full" style={{ background: METRIC_COLOR[k] }} />
                  {METRIC_SHORT[k]} — marketplace
                </CardDescription>
                <CardTitle>
                  <span className="font-display text-3xl font-bold tracking-tight">{market.isLoading ? "…" : <CountUp value={p?.reference_rate} format={(v) => pct(v)} />}</span>
                </CardTitle>
              </CardHeader>
              <CardContent className="text-xs text-muted-foreground">
                {METRIC_DEFINITION[k]}
              </CardContent>
            </Card>
          )
        })}
        <Card size="sm" className="lift">
          <CardHeader>
            <CardDescription>Fiabilité des alertes (vérifiée sur avr.–juin 2018)</CardDescription>
            <CardTitle>
              <span className="font-display text-3xl font-bold tracking-tight">{ts ? <CountUp value={ts.level.precision} format={(v) => pct(v)} /> : "…"}</span>
            </CardTitle>
          </CardHeader>
          <CardContent className="text-xs text-muted-foreground">
            {ts ? `des alertes confirmées dans les 60 jours suivants · ${pct(ts.level.recall)} des dégradations durables repérées · environ ${ts.level.alerts_per_month} alertes par mois` : "—"}
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Taux de référence de la marketplace</CardTitle>
            <CardDescription>Taux sur 12 mois d'issues connues, à chaque fin de mois.</CardDescription>
          </CardHeader>
          <CardContent className="h-64">
            {market.isLoading ? (
              <LoadingBlock rows={5} />
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={rows} margin={{ left: -10, right: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke={CHART.grid} vertical={false} />
                  <XAxis dataKey="month" tick={tick} tickFormatter={(m) => m.slice(2)} />
                  <YAxis tick={tick} tickFormatter={(v) => `${Math.round(v * 100)} %`} width={48} />
                  <RTooltip formatter={(v) => pct(v as number)} labelFormatter={(m) => monthLabel(String(m))} contentStyle={{ fontSize: 12 }} />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  {METRICS.map((k) => (
                    <Line key={k} type="linear" dataKey={`ref_${k}`} name={METRIC_SHORT[k]} stroke={METRIC_COLOR[k]} strokeWidth={2} dot={false} isAnimationActive={false} />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Vendeurs en écart avec la marketplace, par mois</CardTitle>
            <CardDescription>Nombre de vendeurs signalés (détecteur retenu sur la validation).</CardDescription>
          </CardHeader>
          <CardContent className="h-64">
            {market.isLoading ? (
              <LoadingBlock rows={5} />
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={rows} margin={{ left: -20, right: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke={CHART.grid} vertical={false} />
                  <XAxis dataKey="month" tick={tick} tickFormatter={(m) => m.slice(2)} />
                  <YAxis tick={tick} allowDecimals={false} />
                  <RTooltip labelFormatter={(m) => monthLabel(String(m))} contentStyle={{ fontSize: 12 }} />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  {METRICS.map((k) => (
                    <Bar key={k} dataKey={`alerts_${k}`} name={METRIC_SHORT[k]} stackId="a" fill={METRIC_COLOR[k]} isAnimationActive={false} />
                  ))}
                </BarChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>
      </div>

      <section className="grid gap-3 md:grid-cols-3">
        {[
          { to: "/bo3/calls", icon: PhoneCall, title: "À appeler cette semaine", text: "Les vendeurs à contacter en priorité, avec le motif, un script d'appel et un e-mail prêts." },
          { to: "/bo3/alerts", icon: Bell, title: "Alertes vendeurs", text: "Toutes les alertes du mois, leur priorité, leur historique et les retards par État de destination." },
          { to: "/bo3/market", icon: MapIcon, title: "Carte du marché", text: "Les 5 familles de vendeurs, leur profil, leur activité et leur évolution." },
        ].map((x) => (
          <Link key={x.to} to={`${x.to}?month=${month ?? ""}`} className="lift group flex gap-3 rounded-2xl border bg-card p-4">
            <span className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-butter text-ink">
              <x.icon className="size-4" />
            </span>
            <span className="min-w-0">
              <span className="flex items-center gap-1 font-semibold">
                {x.title} <ArrowRight className="size-3.5 transition-transform group-hover:translate-x-0.5" />
              </span>
              <span className="mt-0.5 block text-sm text-muted-foreground">{x.text}</span>
            </span>
          </Link>
        ))}
      </section>
    </div>
  )
}
