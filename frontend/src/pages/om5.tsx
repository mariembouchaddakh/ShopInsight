import { useQuery } from "@tanstack/react-query"
import { CircleAlert, ClipboardCheck, FileText, LayoutDashboard, Search } from "lucide-react"
import { useMemo, useState } from "react"
import { useSearchParams } from "react-router-dom"
import { ErrorBlock } from "@/components/app/states"
import { useDecisionMonth } from "@/components/app/month"
import { Button } from "@/components/ui/button"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { AgentInvestigationCards } from "@/components/om5/AgentInvestigationCards"
import { AnomalyCenter } from "@/components/om5/AnomalyCenter"
import { ExecutiveSummary } from "@/components/om5/ExecutiveSummary"
import { KpiCards } from "@/components/om5/KpiCards"
import { Om5Loading } from "@/components/om5/LoadingState"
import { OM5Header } from "@/components/om5/OM5Header"
import { PerformanceCharts } from "@/components/om5/PerformanceCharts"
import { RecommendationCards } from "@/components/om5/RecommendationCards"
import { ReportPanel } from "@/components/om5/ReportPanel"
import { SegmentContributions } from "@/components/om5/SegmentContributions"
import { TechnicalDetails } from "@/components/om5/TechnicalDetails"
import { VerifiedFindings } from "@/components/om5/VerifiedFindings"
import { WorkflowTimeline } from "@/components/om5/WorkflowTimeline"
import { buildView, health, visibleTrends, verification } from "@/components/om5/model"
import type { Om5Mode, TrendRow } from "@/components/om5/types"
import { Notice } from "@/components/om5/ui"
import { api } from "@/lib/api"

type TabId = "overview" | "investigations" | "plan" | "report"
const TABS: { id: TabId; label: string; icon: typeof LayoutDashboard }[] = [
  { id: "overview", label: "Vue globale", icon: LayoutDashboard },
  { id: "investigations", label: "Investigations", icon: Search },
  { id: "plan", label: "Plan d'action", icon: ClipboardCheck },
  { id: "report", label: "Rapport", icon: FileText },
]

// Le rapport déclenche une génération LLM côté serveur : on le charge une seule fois par (mois, mode) et on le partage
// entre les onglets. Pas de rechargement au focus de la fenêtre ni au changement d'onglet.
const ONCE = { staleTime: 15 * 60_000, refetchOnWindowFocus: false, refetchOnReconnect: false } as const

export function Om5Page() {
  const [month] = useDecisionMonth()
  const [params, setParams] = useSearchParams()
  const mode = (params.get("mode") === "retrospective" ? "retrospective" : "as_of") as Om5Mode
  const [tab, setTab] = useState<TabId>("overview")

  const report = useQuery({ queryKey: ["om5-report", month, mode], queryFn: () => api.om5Report(month!, mode), enabled: !!month, ...ONCE })
  const kpis = useQuery({ queryKey: ["om5-kpis", month, mode], queryFn: () => api.om5Kpis(month!, mode), enabled: !!month, staleTime: 60_000 })
  const trends = useQuery({ queryKey: ["om5-trends", mode], queryFn: () => api.om5Trends(mode), staleTime: 60_000 })
  const setMode = (next: Om5Mode) => { const p = new URLSearchParams(params); p.set("mode", next); setParams(p, { replace: true }) }

  const view = useMemo(
    () => (report.data && month ? buildView({ month, mode, report: report.data, kpis: kpis.data?.kpis ?? [], trends: (trends.data?.rows ?? []) as TrendRow[] }) : null),
    [report.data, kpis.data, trends.data, month, mode],
  )
  const rows = useMemo(() => (view && month ? visibleTrends(view.trends, month, mode) : []), [view, month, mode])

  const base = month ? `month=${month}&mode=${mode}` : ""
  const status = view ? { label: health(view).key === "partial" ? "Analyse partielle" : verification(view).verified ? "Analyse terminée et vérifiée" : "Analyse terminée", tone: health(view).key === "partial" || !verification(view).verified ? ("warn" as const) : ("good" as const) } : null

  return (
    <div className="pb-8">
      <OM5Header month={month} mode={mode} onMode={setMode} status={report.isError ? { label: "Analyse indisponible", tone: "bad" } : status} pdfHref={view ? `/api/om5/report.pdf?${base}` : null} />

      {report.isError ? (
        <div className="space-y-3">
          <ErrorBlock error={report.error} />
          <Button variant="outline" onClick={() => report.refetch()}>Relancer l'analyse</Button>
        </div>
      ) : !view || !month ? (
        <Om5Loading />
      ) : (
        <div className="space-y-5">
          {view.meta.partial && (
            <Notice tone="warn" icon={<CircleAlert />} title="Rapport partiel">
              Une partie des sources n'a pas pu être consolidée : les conclusions ci-dessous doivent être lues avec prudence.
            </Notice>
          )}
          {(view.meta.fallback_used || view.meta.generation_mode === "deterministic") && (
            <Notice tone="warn" icon={<CircleAlert />} title="Synthèse automatique de secours">
              La rédaction par le modèle de langage n'a pas été retenue pour ce rapport. Les indicateurs, anomalies et scores restent calculés de façon déterministe.
            </Notice>
          )}
          {kpis.isError && <Notice tone="warn" icon={<CircleAlert />} title="Indicateurs indisponibles">Les cartes d'indicateurs n'ont pas pu être chargées pour ce mois.</Notice>}

          <Tabs value={tab} onValueChange={(v) => setTab(v as TabId)} className="gap-5">
            <TabsList variant="line" className="h-auto w-full justify-start gap-1 overflow-x-auto border-b border-border p-0 pb-px">
              {TABS.map((t) => (
                <TabsTrigger key={t.id} value={t.id} className="h-10 flex-none gap-2 rounded-none px-4 text-sm data-active:font-semibold data-active:text-ink after:bottom-[-1px] after:h-[3px] after:bg-butter-hover">
                  <t.icon /> {t.label}
                </TabsTrigger>
              ))}
            </TabsList>

            <TabsContent value="overview" className="space-y-5 outline-none">
              <ExecutiveSummary view={view} />
              {kpis.isLoading ? <Om5KpiSkeleton /> : <KpiCards view={view} trends={rows} />}
              <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_25rem]">
                <div className="min-w-0">
                  {trends.isError
                    ? <Notice tone="warn" icon={<CircleAlert />} title="Tendances indisponibles">L'historique mensuel n'a pas pu être chargé.</Notice>
                    : <PerformanceCharts rows={rows} month={month} mode={mode} />}
                </div>
                <div className="min-w-0 space-y-5">
                  <AnomalyCenter view={view} limit={3} onSeeAll={() => setTab("investigations")} />
                </div>
              </div>
              <RecommendationCards view={view} limit={3} compact />
            </TabsContent>

            <TabsContent value="investigations" className="space-y-5 outline-none">
              <AnomalyCenter view={view} />
              <SegmentContributions view={view} />
              <AgentInvestigationCards view={view} />
              <VerifiedFindings view={view} />
            </TabsContent>

            <TabsContent value="plan" className="space-y-5 outline-none">
              <RecommendationCards view={view} />
            </TabsContent>

            <TabsContent value="report" className="space-y-5 outline-none">
              <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_26rem]">
                <ReportPanel view={view} base={base} />
                <WorkflowTimeline view={view} />
              </div>
              <TechnicalDetails view={view} />
            </TabsContent>
          </Tabs>
        </div>
      )}
    </div>
  )
}

function Om5KpiSkeleton() {
  return <div aria-busy="true" className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">{Array.from({ length: 4 }).map((_, i) => <div key={i} className="h-44 animate-pulse rounded-2xl bg-muted" />)}</div>
}
