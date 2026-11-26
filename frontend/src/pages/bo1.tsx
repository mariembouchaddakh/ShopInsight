import { useQuery } from "@tanstack/react-query"
import { Search, ShieldCheck, Target, TriangleAlert } from "lucide-react"
import { useState } from "react"
import { Bar, BarChart, CartesianGrid, Cell, Legend, ResponsiveContainer, Tooltip as RTooltip, XAxis, YAxis } from "recharts"
import { useDecisionMonth } from "@/components/app/month"
import { ReportView } from "@/components/app/report-view"
import { PageHeader } from "@/components/app/shell"
import { ErrorBlock, LoadingBlock } from "@/components/app/states"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { api } from "@/lib/api"
import { catLabel } from "@/lib/categories"
import { CHART, METRIC_COLOR, monthLabel, num, pct } from "@/lib/format"
import { stateName } from "@/lib/geo"

const tick = { fontSize: 11, fill: CHART.tick }
const TARGET_LABEL = { late: "retard de livraison", poor: "avis 1-2 étoiles" } as const
const TARGET_COLOR = { late: METRIC_COLOR.late, poor: METRIC_COLOR.poor } as const

function Kpi({ icon: Icon, label, value, hint }: { icon: typeof Target; label: string; value: string; hint: string }) {
  return (
    <Card size="sm" className="lift">
      <CardHeader>
        <CardDescription className="flex items-center gap-2">
          <Icon className="size-3.5" /> {label}
        </CardDescription>
        <CardTitle>
          <span className="font-display text-3xl font-bold tracking-tight">{value}</span>
        </CardTitle>
      </CardHeader>
      <CardContent className="text-xs text-muted-foreground">{hint}</CardContent>
    </Card>
  )
}

/** BO1 : commandes à risque. Graphiques construits à partir du modèle de l'agent ; rapports complets dans l'onglet Diagnostic. */
export function Bo1Page() {
  const [month] = useDecisionMonth()
  const [tab, setTab] = useState("triage")
  const [target, setTarget] = useState<"late" | "poor">("late")
  const [orderInput, setOrderInput] = useState("")
  const [orderId, setOrderId] = useState<string | null>(null)
  const ov = useQuery({ queryKey: ["bo1-overview", month, target], queryFn: () => api.bo1Overview({ month: month!, target, top_k: 15 }), enabled: !!month })
  const triage = useQuery({ queryKey: ["bo1-triage", month, target], queryFn: () => api.bo1Triage({ month: month!, target, top_k: 20 }), enabled: !!month && tab === "report" })
  const diag = useQuery({ queryKey: ["bo1-diag", orderId], queryFn: () => api.bo1Diagnosis(orderId!), enabled: !!orderId })
  const valid = /^[0-9a-fA-F]{32}$/.test(orderInput.trim())
  const color = TARGET_COLOR[target]
  const d = ov.data
  const lift = d ? d.top10_precision_test / d.test_prevalence : null
  const openOrder = (id: string) => {
    setOrderInput(id)
    setOrderId(id)
    setTab("order")
  }

  return (
    <div>
      <PageHeader
        title="Commandes à risque"
        description="Dès qu'une commande est approuvée, l'agent BO1 estime son risque de retard ou de mauvais avis à partir des seules informations connues à ce moment. Les scores servent à prioriser une surveillance ; ce ne sont pas des probabilités."
      />
      <Tabs value={tab} onValueChange={(v) => setTab(String(v))} className="min-w-0">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <TabsList>
            <TabsTrigger value="triage">Vue d'ensemble</TabsTrigger>
            <TabsTrigger value="order">Diagnostic d'une commande</TabsTrigger>
            <TabsTrigger value="report">Rapport de l'agent</TabsTrigger>
          </TabsList>
          <div className="flex items-center gap-2 text-sm">
            <span className="text-muted-foreground">Commandes de {month ? monthLabel(month) : "…"} · risque de</span>
            <select className="h-8 rounded-md border border-input bg-background px-2 text-sm" value={target} onChange={(e) => setTarget(e.target.value as "late" | "poor")} aria-label="Cible">
              <option value="late">retard de livraison</option>
              <option value="poor">avis 1-2 étoiles</option>
            </select>
          </div>
        </div>

        <TabsContent value="triage" className="mt-5 space-y-5">
          {ov.isLoading && <LoadingBlock rows={8} />}
          {ov.isError && <ErrorBlock error={ov.error} />}
          {d && (
            <>
              <div className="stagger grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                <Kpi icon={Search} label="Commandes analysées" value={num(d.n_orders)} hint={`approuvées en ${monthLabel(d.month)}, chacune notée par le modèle`} />
                <Kpi icon={TriangleAlert} label="À surveiller en priorité" value={num(d.top10pct_size)} hint="les 10 % au score le plus élevé" />
                <Kpi
                  icon={Target}
                  label="Efficacité du tri (test)"
                  value={lift ? `×${lift.toLocaleString("fr-FR", { maximumFractionDigits: 1 })}` : "—"}
                  hint={`${pct(d.top10_precision_test)} de ${TARGET_LABEL[target]} dans le top 10 %, contre ${pct(d.test_prevalence)} en moyenne ; ${pct(d.top10_recall_test, 0)} des cas captés`}
                />
                <Kpi
                  icon={ShieldCheck}
                  label="Vérifié après coup sur ce mois"
                  value={d.check ? pct(d.check.precision_top10pct) : "—"}
                  hint={
                    d.check
                      ? `de ${TARGET_LABEL[target]} dans le top 10 %, contre ${pct(d.check.base_rate)} pour l'ensemble du mois${d.check.split !== "test" ? " (mois utilisé pour l'entraînement)" : ""}`
                      : "issues pas encore connues pour ce mois"
                  }
                />
              </div>

              <div className="grid gap-4 lg:grid-cols-2">
                <Card>
                  <CardHeader>
                    <CardTitle className="text-sm">Plus le score est élevé, plus le risque est réel</CardTitle>
                    <CardDescription>Taux observé de {TARGET_LABEL[target]} par dixième de score, sur la période de test (avr.–août 2018).</CardDescription>
                  </CardHeader>
                  <CardContent className="h-64">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={d.deciles} margin={{ left: -10, right: 8 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke={CHART.grid} vertical={false} />
                        <XAxis dataKey="decile" tick={tick} tickFormatter={(v) => `D${v}`} />
                        <YAxis tick={tick} tickFormatter={(v) => `${Math.round(v * 100)} %`} width={48} />
                        <RTooltip formatter={(v) => [pct(v as number), "taux observé"]} labelFormatter={(v) => `Dixième ${v} (${v === 10 ? "scores les plus élevés" : v === 1 ? "scores les plus bas" : "…"})`} contentStyle={{ fontSize: 12 }} />
                        <Bar dataKey="observed_rate" isAnimationActive={false} radius={[4, 4, 0, 0]}>
                          {d.deciles.map((x) => (
                            <Cell key={x.decile} fill={color} fillOpacity={x.decile === 10 ? 1 : 0.35 + x.decile * 0.05} />
                          ))}
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  </CardContent>
                </Card>
                <Card>
                  <CardHeader>
                    <CardTitle className="text-sm">Où se trouvent les commandes à surveiller</CardTitle>
                    <CardDescription>États de destination les plus présents dans le top 10 %, comparés à leur poids dans le mois.</CardDescription>
                  </CardHeader>
                  <CardContent className="h-64">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={d.states.map((s) => ({ ...s, name: stateName(s.state) }))} layout="vertical" margin={{ left: 10, right: 8 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke={CHART.grid} horizontal={false} />
                        <XAxis type="number" tick={tick} tickFormatter={(v) => `${Math.round(v * 100)} %`} />
                        <YAxis type="category" dataKey="name" tick={tick} width={130} interval={0} />
                        <RTooltip formatter={(v) => pct(v as number)} contentStyle={{ fontSize: 12 }} />
                        <Legend wrapperStyle={{ fontSize: 11 }} />
                        <Bar dataKey="share_top" name="part du top 10 %" fill={color} isAnimationActive={false} radius={[0, 4, 4, 0]} />
                        <Bar dataKey="share_month" name="part de toutes les commandes" fill={CHART.reference} isAnimationActive={false} radius={[0, 4, 4, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </CardContent>
                </Card>
              </div>

              <Card>
                <CardHeader>
                  <CardTitle className="text-sm">Les {d.listing.length} commandes au risque le plus élevé</CardTitle>
                  <CardDescription>Cliquez sur une commande pour obtenir son diagnostic complet : causes, commandes similaires, actions.</CardDescription>
                </CardHeader>
                <CardContent className="overflow-x-auto">
                  <table className="w-full min-w-[640px] text-sm">
                    <thead>
                      <tr className="border-b text-left text-xs text-muted-foreground">
                        <th className="py-2 pr-3 font-medium">Commande</th>
                        <th className="py-2 pr-3 font-medium">Destination</th>
                        <th className="py-2 pr-3 font-medium">Catégorie</th>
                        <th className="py-2 pr-3 font-medium">Délai promis</th>
                        <th className="w-56 py-2 font-medium">Score de risque</th>
                      </tr>
                    </thead>
                    <tbody>
                      {d.listing.map((o) => (
                        <tr key={o.order_id} className="cursor-pointer border-b last:border-0 hover:bg-muted/50" onClick={() => openOrder(o.order_id)}>
                          <td className="py-2 pr-3 font-mono text-xs text-[#2F6BB0] underline-offset-2 hover:underline">{o.order_id.slice(0, 12)}…</td>
                          <td className="py-2 pr-3">{stateName(o.state)}</td>
                          <td className="py-2 pr-3">{catLabel(o.category)}</td>
                          <td className="py-2 pr-3">{o.promised_days} j</td>
                          <td className="py-2">
                            <div className="flex items-center gap-2">
                              <div className="h-2 flex-1 rounded-full bg-muted">
                                <div className="h-2 rounded-full" style={{ width: `${Math.round(o.score * 100)}%`, background: color }} />
                              </div>
                              <span className="w-10 text-right text-xs tabular-nums">{o.score.toLocaleString("fr-FR", { maximumFractionDigits: 2, minimumFractionDigits: 2 })}</span>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </CardContent>
              </Card>
            </>
          )}
        </TabsContent>

        <TabsContent value="order" className="mt-5 space-y-4">
          <form
            className="flex max-w-xl gap-2"
            onSubmit={(e) => {
              e.preventDefault()
              if (valid) setOrderId(orderInput.trim().toLowerCase())
            }}
          >
            <Input value={orderInput} onChange={(e) => setOrderInput(e.target.value)} placeholder="Identifiant de commande (32 caractères hexadécimaux)" className="font-mono" aria-label="Identifiant de commande" />
            <Button type="submit" disabled={!valid}>
              Diagnostiquer
            </Button>
          </form>
          <p className="text-xs text-muted-foreground">Astuce : cliquez sur une commande dans la vue d'ensemble.</p>
          {diag.isLoading && <LoadingBlock rows={8} />}
          {diag.isError && <ErrorBlock error={diag.error} />}
          {diag.data && <ReportView report={diag.data.report} evidence={diag.data.evidence} />}
        </TabsContent>

        <TabsContent value="report" className="mt-5 space-y-4">
          {triage.isLoading && <LoadingBlock rows={8} />}
          {triage.isError && <ErrorBlock error={triage.error} />}
          {triage.data && <ReportView report={triage.data.report} evidence={triage.data.evidence} />}
        </TabsContent>
      </Tabs>
    </div>
  )
}
