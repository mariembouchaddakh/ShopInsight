import { useMutation, useQuery } from "@tanstack/react-query"
import { ArrowLeft, Copy, FileDown, MapPin, MessageCircle, ShieldAlert, ShieldCheck, ShieldQuestion, Sparkles } from "lucide-react"
import { useState } from "react"
import { Link, useParams } from "react-router-dom"
import { Pill, SeverityBadge } from "@/components/app/badges"
import { useDecisionMonth } from "@/components/app/month"
import { ErrorBlock, LoadingBlock } from "@/components/app/states"
import { openAssistant, useAiSlot } from "@/components/assistant/assistant-widget"
import { BilanPanel } from "@/components/bo3/ai-bilan"
import { CompetitiveLandscape } from "@/components/bo3/competitive"
import { FlowsAndMix } from "@/components/bo3/flows"
import { SellerMap } from "@/components/bo3/seller-map"
import { Trajectory } from "@/components/bo3/trajectory"
import { VoiceAndOrders, type Orders, type Voice } from "@/components/bo3/voice-orders"
import { CountUp } from "@/components/brand/count-up"
import { EvidenceDrawer } from "@/components/evidence/evidence-drawer"
import { SourcePills } from "@/components/evidence/source-pill"
import { Button } from "@/components/ui/button"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { api, type Evidence, type Flows, type MetricKey, type Severity } from "@/lib/api"
import { METRICS, METRIC_COLOR, monthLabel, num, pct } from "@/lib/format"
import { cn } from "@/lib/utils"
import { catLabel } from "@/lib/categories"
import { stateName } from "@/lib/geo"

type Observed = {
  recent_rate: number | null
  recent_known_n: number
  recent_events: number
  orders_recent: number
  year_rate: number | null
  peer_rate: number | null
  ratio_to_peers: number | null
}
type Family = { alert: boolean; eligible: boolean; severity: Severity | null }
type Det = { families: { level: Family; trend: Family } }
type Strength = { items: { metric: MetricKey; strength: boolean }[] }
type Profile = {
  orders_12m: number
  main_category?: string
  seller_state?: string | null
  insufficient: boolean
  descriptive_segment?: { volume: string; region: string }
  flows?: Flows
  category_distribution?: { category: string; orders: number; share: number }[]
  monthly_orders?: { month: string; orders: number }[]
  median_price?: number | null
  mean_promised_days?: number | null
}

// Libellés et explications en langage courant pour les trois indicateurs.
const KPI_TEXT: Record<MetricKey, { title: string; explain: string }> = {
  handover: { title: "Expédition tardive", explain: "Part des commandes confiées au transporteur après la date limite fixée au vendeur." },
  late: { title: "Livraison en retard", explain: "Part des commandes arrivées chez le client après la date annoncée." },
  poor: { title: "Avis négatifs", explain: "Part des commandes notées 1 ou 2 étoiles par le client." },
}
const ORDER: MetricKey[] = ["handover", "late", "poor"]

function payload<T>(ev: Evidence[], id: string): T | undefined {
  return ev.find((e) => e.id === id)?.payload as T | undefined
}

function KpiCard({ k, obs, det, strong, ids, onOpen }: { k: MetricKey; obs?: Observed; det?: Det; strong: boolean; ids: string[]; onOpen: (id: string) => void }) {
  const lv = det?.families.level
  const tr = det?.families.trend
  const bad = !!lv?.alert
  return (
    <div className={cn("lift flex min-w-0 flex-col gap-3 rounded-2xl border bg-card p-5", bad && "border-burgundy/30 bg-burgundy-tint/70")}>
      <div className="flex items-start justify-between gap-2">
        <p className="flex items-center gap-2 text-sm font-medium">
          <span className="size-2.5 rounded-full" style={{ background: METRIC_COLOR[k] }} />
          {KPI_TEXT[k].title}
        </p>
        <span className="flex flex-wrap justify-end gap-1">
          {lv?.alert && <SeverityBadge severity={lv.severity} />}
          {tr?.alert && <Pill tone="blue">en dégradation</Pill>}
          {strong && <Pill tone="green">point fort</Pill>}
        </span>
      </div>
      <div>
        <p className="font-display text-4xl font-bold tracking-tight">{obs?.recent_known_n ? <CountUp value={obs.recent_rate} format={(v) => pct(v)} /> : "—"}</p>
        <p className="mt-1 text-xs text-muted-foreground">
          {obs?.recent_known_n ? (
            <>
              sur les 90 derniers jours · marketplace <b className="text-foreground">{pct(obs.peer_rate)}</b>
              {obs.ratio_to_peers ? (
                <span className={cn("ml-1 font-medium", obs.ratio_to_peers > 1 ? "text-burgundy" : "text-forest")}>
                  {obs.ratio_to_peers > 1
                    ? `soit ${obs.ratio_to_peers.toLocaleString("fr-FR", { maximumFractionDigits: 1 })} fois plus`
                    : "en dessous de la marketplace"}
                </span>
              ) : null}
            </>
          ) : (
            "aucune commande dont l'issue est connue sur 90 jours"
          )}
        </p>
      </div>
      <p className="text-xs leading-relaxed text-muted-foreground">
        {KPI_TEXT[k].explain}
        {obs?.recent_known_n ? ` ${num(obs.recent_events)} cas sur ${num(obs.recent_known_n)} commandes.` : ""}
      </p>
      <SourcePills ids={ids} onOpen={onOpen} className="mt-auto" />
    </div>
  )
}

function Health({ alerts, severities }: { alerts: { metric: MetricKey; family: string }[]; severities: (Severity | null)[] }) {
  const top = (["élevée", "moyenne", "faible"] as Severity[]).find((s) => severities.includes(s))
  const [Icon, label, desc, cls] = top
    ? top === "élevée"
      ? [ShieldAlert, "Situation critique", "Écart marqué et persistant : action prioritaire", "border-burgundy/30 bg-burgundy-tint text-burgundy"]
      : [ShieldAlert, "À surveiller de près", "Écart significatif avec la marketplace", "border-amber-ink/25 bg-amber-tint text-amber-ink"]
    : alerts.length
      ? [ShieldQuestion, "Dégradation récente", "Moins bon que son propre passé (signal faible)", "border-navy-soft/25 bg-navy-tint text-navy-soft"]
      : [ShieldCheck, "Situation saine", "Aucune alerte ce mois-ci", "border-forest/25 bg-sage text-forest"]
  return (
    <div className={cn("flex items-center gap-3 rounded-2xl border px-4 py-3", cls)}>
      <Icon className={cn("size-6 shrink-0", top === "élevée" && "animate-pulse")} />
      <div>
        <p className="text-sm font-semibold">{label}</p>
        <p className="text-xs opacity-80">{desc}</p>
      </div>
    </div>
  )
}

export function SellerAuditPage() {
  const { sellerId = "" } = useParams()
  const [month] = useDecisionMonth()
  const [open, setOpen] = useState<string | null>(null)
  const [tab, setTab] = useState<string>("bilan")
  const slot = useAiSlot()
  const audit = useQuery({ queryKey: ["audit", sellerId, month], queryFn: () => api.audit(sellerId, month), enabled: !!month })
  const ev = audit.data?.evidence ?? []
  const meta = (audit.data?.report.meta ?? {}) as { seller_id?: string; month?: string; decision_date?: string; alerts?: { metric: MetricKey; family: string }[] }
  const sid = meta.seller_id ?? sellerId
  const s8 = sid.slice(0, 8)
  const M = meta.month ?? month ?? ""
  const prof = payload<Profile>(ev, `sel:${s8}:${M}`)
  const strengths = payload<Strength>(ev, `alr:strength:${s8}:${M}`)
  const ok = !!prof && !prof.insufficient
  const bench = useQuery({ queryKey: ["benchmark", sid, M], queryFn: () => api.benchmark(sid, M), enabled: ok && !!M })
  // L'analyse vit au niveau de la page : elle reste affichée quand on change d'onglet.
  const analysis = useMutation({ mutationKey: ["analysis", sid, M], mutationFn: () => api.aiAnalysis(sid, M, slot) })
  const alerts = meta.alerts ?? []
  const dets = Object.fromEntries(METRICS.map((k) => [k, payload<Det>(ev, `alr:${s8}:${M}:${k}`)])) as Record<MetricKey, Det | undefined>
  const severities = METRICS.map((k) => (dets[k]?.families.level.alert ? dets[k]!.families.level.severity : null))

  return (
    <div className="space-y-8">
      <div className="space-y-6">
        <Link to={`/bo3/sellers?month=${month ?? ""}`} className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
          <ArrowLeft className="size-3" /> Tous les vendeurs
        </Link>

        <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0 space-y-3">
            <p className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">Audit vendeur · fin {M ? monthLabel(M) : "…"}</p>
            <h1 className="flex items-center gap-2 text-4xl font-bold tracking-tight">
              Vendeur <span className="font-mono">{s8}</span>
              <button className="text-muted-foreground hover:text-foreground" onClick={() => navigator.clipboard?.writeText(sid)} aria-label="Copier l'identifiant complet" title={sid}>
                <Copy className="size-4" />
              </button>
            </h1>
            {ok && (
              <div className="flex flex-wrap items-center gap-1.5">
                {prof.main_category && <Pill className="h-6 px-2.5 text-xs">{catLabel(prof.main_category)}</Pill>}
                {prof.seller_state && (
                  <Pill className="h-6 px-2.5 text-xs">
                    <MapPin className="mr-1 size-3" /> {stateName(prof.seller_state)}
                  </Pill>
                )}
                {prof.descriptive_segment && (
                  <Pill tone="blue" className="h-6 px-2.5 text-xs">
                    {prof.descriptive_segment.volume} · {prof.descriptive_segment.region}
                  </Pill>
                )}
                <Pill className="h-6 px-2.5 text-xs">{num(prof.orders_12m)} commandes / 12 mois</Pill>
              </div>
            )}
            <p className="text-sm text-muted-foreground">Seules les informations connues à la fin du mois sont utilisées.</p>
          </div>
          <div className="flex flex-col gap-3 sm:flex-row lg:flex-col lg:items-end">
            {audit.data && ok && <Health alerts={alerts} severities={severities} />}
            {audit.data && (
              <div className="flex flex-wrap gap-2 lg:justify-end">
                <a href={`/api/reports/sellers/${sid}.pdf?month=${M}&include_ai=true&model=${slot}`}>
                  <Button size="lg">
                    <FileDown className="size-4" /> Télécharger le Bilan PDF
                  </Button>
                </a>
                <Button size="lg" variant="outline" onClick={() => openAssistant()}>
                  <MessageCircle className="size-4" /> Assistant
                </Button>
              </div>
            )}
          </div>
        </div>
        {analysis.isSuccess && <p className="text-xs text-muted-foreground lg:text-right">Le PDF inclut l'analyse stratégique générée.</p>}
      </div>

      {audit.isLoading && <LoadingBlock rows={8} />}
      {audit.isError && <ErrorBlock error={audit.error} />}
      {audit.data && prof?.insufficient && (
        <p className="rounded-2xl border p-5 text-sm text-muted-foreground">
          Seulement {prof.orders_12m} commandes sur 12 mois : trop peu pour comparer ce vendeur de façon fiable ce mois-ci.
        </p>
      )}
      {audit.data && ok && (
        <>
          <div className="stagger grid gap-4 md:grid-cols-3">
            {ORDER.map((k) => (
              <KpiCard
                key={k}
                k={k}
                obs={payload<Observed>(ev, `kpi:seller:${s8}:${M}:${k}`)}
                det={dets[k]}
                strong={!!strengths?.items.find((i) => i.metric === k && i.strength)}
                ids={[`kpi:seller:${s8}:${M}:${k}`, `alr:${s8}:${M}:${k}`]}
                onOpen={setOpen}
              />
            ))}
          </div>

          <Tabs value={tab} onValueChange={(v) => setTab(String(v))} className="min-w-0 gap-6">
            <TabsList className="h-auto flex-wrap justify-start">
              <TabsTrigger value="bilan">
                <Sparkles className="size-3.5" /> Bilan & plan d'action
              </TabsTrigger>
              <TabsTrigger value="concurrence">Concurrence & classement</TabsTrigger>
              <TabsTrigger value="flux">Clients, catalogue & historique</TabsTrigger>
              <TabsTrigger value="voix">Voix du client & commandes</TabsTrigger>
            </TabsList>

            <TabsContent value="bilan" className="space-y-6">
              <BilanPanel alerted={alerts.length > 0} analysis={analysis} onOpen={setOpen} />
            </TabsContent>

            <TabsContent value="concurrence" className="space-y-3">
              <div className="flex justify-end">
                <Link to={`/bo3/market?month=${M}&seller=${sid}`} className="text-sm font-semibold text-ink hover:underline">
                  Voir ce vendeur sur la carte du marché →
                </Link>
              </div>
              {bench.isLoading && <LoadingBlock rows={6} />}
              {bench.isError && <ErrorBlock error={bench.error} />}
              {bench.data && <CompetitiveLandscape bench={bench.data.result} evidenceId={`peer:bench:${s8}:${M}`} onOpen={setOpen} />}
            </TabsContent>

            <TabsContent value="flux" className="space-y-6">
              <SellerMap seller={sid} month={M} onOpen={setOpen} />
              {prof.flows && prof.flows.destinations.length > 0 && (
                <FlowsAndMix
                  flows={prof.flows}
                  categories={prof.category_distribution ?? []}
                  monthly={prof.monthly_orders}
                  showDestinations={false}
                  evidenceId={`sel:${s8}:${M}`}
                  onOpen={setOpen}
                />
              )}
              <Trajectory seller={sid} month={M} onOpen={setOpen} />
            </TabsContent>

            <TabsContent value="voix">
              <VoiceAndOrders
                voice={payload<Voice>(ev, `mdl:aspects:seller:${s8}:${M}`)}
                orders={payload<Orders>(ev, `ord:seller:${s8}:${M}`)}
                ids={{ voice: `mdl:aspects:seller:${s8}:${M}`, orders: `ord:seller:${s8}:${M}` }}
                onOpen={setOpen}
                seller={sid}
                month={M}
              />
            </TabsContent>
          </Tabs>
        </>
      )}
      <EvidenceDrawer evidence={ev} openId={open} onClose={() => setOpen(null)} />
    </div>
  )
}
