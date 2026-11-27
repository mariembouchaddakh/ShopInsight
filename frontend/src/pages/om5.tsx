import { useQuery } from "@tanstack/react-query"
import { Activity, Bot, CheckCircle2, Download, Network, ShieldAlert, Sparkles } from "lucide-react"
import { useSearchParams } from "react-router-dom"
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts"
import { PageHeader } from "@/components/app/shell"
import { EmptyBlock, ErrorBlock, LoadingBlock } from "@/components/app/states"
import { useDecisionMonth } from "@/components/app/month"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { api, type Om5Kpi, type Om5Mode } from "@/lib/api"
import { CHART, monthLabel } from "@/lib/format"

const tracked = ["order_count", "item_price_total", "late_rate", "poor_review_rate", "average_review_score", "active_seller_count", "alerted_seller_count"]
const colors: Record<string, string> = { order_count: "#315c4f", item_price_total: "#ca8a04", late_rate: "#9f2842", poor_review_rate: "#c45d33", average_review_score: "#466a9f" }

function value(k: Om5Kpi) {
  if (k.value == null) return "Indisponible"
  if (k.unit === "ratio") return `${(k.value * 100).toFixed(1)} %`
  if (k.unit === "BRL") return `${k.value.toLocaleString("fr-FR", { maximumFractionDigits: 0 })} BRL`
  return `${k.value.toLocaleString("fr-FR", { maximumFractionDigits: 2 })} ${k.unit}`
}

export function Om5Page() {
  const [month] = useDecisionMonth()
  const [params, setParams] = useSearchParams()
  const mode = (params.get("mode") === "retrospective" ? "retrospective" : "as_of") as Om5Mode
  const report = useQuery({ queryKey: ["om5-report", month, mode], queryFn: () => api.om5Report(month!, mode), enabled: !!month, staleTime: 60_000 })
  const kpis = useQuery({ queryKey: ["om5-kpis", month, mode], queryFn: () => api.om5Kpis(month!, mode), enabled: !!month, staleTime: 60_000 })
  const trends = useQuery({ queryKey: ["om5-trends", mode], queryFn: () => api.om5Trends(mode), staleTime: 60_000 })
  const setMode = (next: Om5Mode) => { const p = new URLSearchParams(params); p.set("mode", next); setParams(p, { replace: true }) }

  if (report.isError) return <ErrorBlock error={report.error} />
  const meta = report.data?.report.meta
  const selected = kpis.data?.kpis.filter((k) => tracked.includes(k.metric_id)) ?? []
  const anomalyRows = meta?.anomalies.filter((x) => x.anomaly) ?? []
  const contextual = meta?.contextual_recommendations ?? []

  return (
    <div className="space-y-6">
      <PageHeader title="Pilotage autonome OM5" description={`Surveillance marketplace sur les données Olist historiques · ${month ? monthLabel(month) : "chargement"}. Les alertes assistent l'investigation et ne déclenchent aucune sanction automatique.`}
        actions={<div className="flex gap-2"><Button variant={mode === "as_of" ? "default" : "outline"} onClick={() => setMode("as_of")}>À date</Button><Button variant={mode === "retrospective" ? "default" : "outline"} onClick={() => setMode("retrospective")}>Rétrospectif</Button></div>} />

      {report.isLoading || kpis.isLoading ? <LoadingBlock rows={6} /> : (
        <>
          <Card className={meta?.generation_mode === "gemini" ? "border-amber-300 bg-amber-50/30" : ""}>
            <CardHeader><div className="flex flex-wrap items-center justify-between gap-2"><CardTitle className="flex items-center gap-2"><Sparkles className="size-4" /> Synthèse exécutive</CardTitle><div className="flex gap-2"><Badge variant={meta?.generation_mode === "gemini" ? "default" : "outline"}>{meta?.generation_mode === "gemini" ? `Gemini · ${meta.llm_model}` : "Rapport déterministe"}</Badge><Badge variant={meta?.validation_status === "valid" ? "default" : "outline"}>Validation: {meta?.validation_status ?? "—"}</Badge>{meta?.partial && <Badge variant="destructive">Partiel</Badge>}</div></div></CardHeader>
            <CardContent><p className="max-w-5xl leading-7">{report.data?.report.narrative}</p>{meta?.fallback_used && <p className="mt-3 text-xs text-muted-foreground">Repli activé: {meta.fallback_reason}</p>}<p className="mt-3 text-xs text-muted-foreground">Données Olist historiques 2016–2018 · ceci n'est pas un suivi temps réel.</p></CardContent>
          </Card>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            {selected.map((k) => <Card key={k.metric_id} size="sm" className="lift"><CardHeader><CardDescription>{k.label}</CardDescription><CardTitle className="font-display text-2xl">{value(k)}</CardTitle></CardHeader><CardContent className="text-xs text-muted-foreground">n={k.denominator ?? "—"} · {k.quality_status}</CardContent></Card>)}
          </div>

          <div className="grid gap-4 lg:grid-cols-[1.5fr_1fr]">
            <Card><CardHeader><CardTitle>Tendances mensuelles</CardTitle><CardDescription>Mois complets uniquement · valeurs issues du mode {mode === "as_of" ? "à date" : "rétrospectif"}.</CardDescription></CardHeader><CardContent className="h-72">
              {trends.isLoading ? <LoadingBlock rows={5} /> : <ResponsiveContainer width="100%" height="100%"><LineChart data={trends.data?.rows ?? []}><CartesianGrid stroke={CHART.grid} strokeDasharray="3 3" vertical={false} /><XAxis dataKey="purchase_month" tick={{ fontSize: 10 }} /><YAxis yAxisId="rates" tickFormatter={(x) => `${Math.round(x * 100)}%`} width={42} /><Tooltip /><Legend />
                <Line yAxisId="rates" dataKey="late_rate" name="Retard" stroke={colors.late_rate} dot={false} strokeWidth={2} />
                <Line yAxisId="rates" dataKey="poor_review_rate" name="Avis négatifs" stroke={colors.poor_review_rate} dot={false} strokeWidth={2} />
              </LineChart></ResponsiveContainer>}
            </CardContent></Card>
            <Card><CardHeader><CardTitle className="flex items-center gap-2"><ShieldAlert className="size-4" /> Anomalies</CardTitle><CardDescription>Effectifs et incertitude pris en compte.</CardDescription></CardHeader><CardContent className="space-y-3">
              {!anomalyRows.length ? <EmptyBlock>Aucune dégradation statistiquement signalée.</EmptyBlock> : anomalyRows.map((a) => <div key={a.metric_id} className="rounded-xl border p-3"><div className="flex items-center justify-between"><span className="font-medium">{a.label}</span><Badge variant="destructive">{a.severity}</Badge></div><p className="mt-1 text-xs text-muted-foreground">{a.method} · n={a.sample_size} · q={a.q_value?.toFixed(4) ?? "—"}</p></div>)}
            </CardContent></Card>
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card><CardHeader><CardTitle>Recommandations prioritaires</CardTitle><CardDescription>Score heuristique documenté, non appris.</CardDescription></CardHeader><CardContent className="space-y-3">
              {contextual.length ? contextual.map((r, i) => <div key={`${r.related_anomaly}-${i}`} className="rounded-xl bg-muted/50 p-3"><div className="flex justify-between gap-3"><strong>{r.title}</strong><Badge>{r.priority_score}/100</Badge></div><p className="mt-1 text-sm">{r.description}</p><p className="mt-1 text-xs text-muted-foreground">{r.business_justification} · {r.responsible_team} · {r.timeframe}</p><p className="mt-1 truncate text-[11px] text-muted-foreground">{r.evidence_ids.join(" · ")}</p></div>) : meta?.recommendations.length ? meta.recommendations.map((r) => <div key={r.metric_id} className="rounded-xl bg-muted/50 p-3"><div className="flex justify-between gap-3"><strong>{r.metric_id}</strong><Badge>{r.priority_score}/100</Badge></div><p className="mt-1 text-sm">{r.recommendation}</p><p className="mt-1 text-xs text-muted-foreground">{r.justification}</p></div>) : <EmptyBlock>Surveillance standard recommandée.</EmptyBlock>}
            </CardContent></Card>
            <Card><CardHeader><CardTitle className="flex items-center gap-2"><Network className="size-4" /> Workflow agentique</CardTitle><CardDescription>{meta?.calls_used ?? 0}/{meta?.call_budget ?? 0} appels · preuves {meta?.evidence_valid ? "validées" : "à vérifier"}.</CardDescription></CardHeader><CardContent className="space-y-2">
              {meta?.tool_trace.map((t, i) => <div key={`${t.tool}-${i}`} className="flex items-center gap-3 rounded-lg border px-3 py-2 text-sm"><span className={`size-2 rounded-full ${t.status === "ok" ? "bg-emerald-600" : t.status === "error" ? "bg-destructive" : "bg-muted-foreground"}`} /><span className="min-w-0 flex-1 truncate">{t.tool}</span><span className="text-xs text-muted-foreground">{t.status} {t.duration_ms != null ? `· ${t.duration_ms} ms` : ""}</span></div>)}
              <p className="pt-2 flex items-center gap-2 text-xs text-muted-foreground"><Bot className="size-3" /> Agents consultés dynamiquement : {Object.keys(meta?.agent_insights ?? {}).map((x) => x.toUpperCase()).join(", ") || "aucun — aucun appel inutile"}.</p>
            </CardContent></Card>
          </div>

          <Card><CardHeader><CardTitle className="flex items-center gap-2"><Activity className="size-4" /> Rapport et preuves</CardTitle><CardDescription>Faits, estimations et actions restent séparés et cités.</CardDescription></CardHeader><CardContent>
            <div className="flex flex-wrap items-center gap-2"><Badge variant={meta?.evidence_valid ? "default" : "destructive"}>{meta?.evidence_valid ? <><CheckCircle2 className="size-3" /> Citations valides</> : "Validation en échec"}</Badge>{meta?.partial && <Badge variant="outline">Rapport partiel</Badge>}
              <a href={`/api/om5/report.pdf?month=${month}&mode=${mode}`}><Button variant="outline"><Download className="size-4" /> PDF</Button></a>
              <a href={`/api/om5/kpis.csv?month=${month}&mode=${mode}`}><Button variant="outline"><Download className="size-4" /> KPI CSV</Button></a>
              <a href={`/api/om5/evidence.csv?month=${month}&mode=${mode}`}><Button variant="outline"><Download className="size-4" /> Preuves CSV</Button></a>
            </div>
            <div className="mt-4 grid gap-3 md:grid-cols-2">{report.data?.report.facts.map((line, i) => <div key={i} className="rounded-lg border p-3 text-sm"><p>{line.text}</p><p className="mt-1 truncate text-[11px] text-muted-foreground">{line.evidence.join(" · ")}</p></div>)}</div>
          </CardContent></Card>
        </>
      )}
    </div>
  )
}
