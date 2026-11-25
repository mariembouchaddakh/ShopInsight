import { useMutation, useQuery } from "@tanstack/react-query"
import { CalendarClock, CheckCircle2, Clock3, History, MessageCircleQuestion, PackageCheck, Search } from "lucide-react"
import { useState } from "react"
import { ReportView } from "@/components/app/report-view"
import { PageHeader } from "@/components/app/shell"
import { ErrorBlock, LoadingBlock } from "@/components/app/states"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { api } from "@/lib/api"
import { catLabel } from "@/lib/categories"
import { dateLabel } from "@/lib/format"

const QUESTIONS = ["Où en est ma commande ?", "Quand devrait-elle arriver ?", "D'autres clients ont-ils connu un retard similaire ?", "Que puis-je faire si la date promise est dépassée ?"]
const label: Record<string, string> = { ordered: "Commande créée", approved: "Paiement approuvé", shipped: "Remise au transporteur", delivered: "Livrée" }
const statusLabel: Record<string, string> = { ordered: "Commande créée", approved: "Paiement approuvé", shipped: "Remise au transporteur", delivered: "Livrée" }
const etaLabel: Record<string, string> = { observed_delivered: "Livraison constatée", expired: "Estimation initiale expirée", approval_time_estimate: "Estimation à l'approbation", gradient_boosting: "Modèle Gradient Boosting", regional_empirical: "Référence régionale", global_empirical: "Référence globale" }

export function Bo4Page() {
  const [draft, setDraft] = useState("")
  const [orderId, setOrderId] = useState("")
  const [asOf, setAsOf] = useState("2018-08-31")
  const [question, setQuestion] = useState(QUESTIONS[0])
  const asOfTimestamp = asOf ? `${asOf}T23:59:59` : undefined
  const context = useQuery({ queryKey: ["bo4-context", orderId, asOf], queryFn: () => api.bo4Context(orderId, asOfTimestamp), enabled: orderId.length >= 8, retry: false })
  const ask = useMutation({ mutationFn: () => api.bo4Ask(orderId, question, asOfTimestamp) })
  const c = context.data?.result
  return <div>
    <PageHeader title="BO4 · Assistant client" description={<>Démonstration historique Olist : faits vérifiés à la date choisie, intervalle statistique et expériences comparables. La <b>date de simulation BO4</b> ci-dessous est indépendante du mois de décision utilisé dans les analyses vendeurs BO3. Aucun suivi GPS en temps réel.</>} />
    <Card className="mb-6"><CardContent className="pt-6"><form className="flex flex-col gap-3 md:flex-row" onSubmit={(e) => { e.preventDefault(); setOrderId(draft.trim()); ask.reset() }}>
      <div className="relative flex-1"><Search className="absolute top-2.5 left-3 size-4 text-muted-foreground"/><Input className="pl-9" value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="Identifiant de commande" aria-label="Identifiant de commande" /></div>
      <Input type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)} className="md:w-44" aria-label="Date de simulation historique" />
      <Button type="submit">Consulter</Button>
    </form></CardContent></Card>
    {context.isLoading && <LoadingBlock rows={7}/>} {context.isError && <ErrorBlock error={context.error}/>}
    {c && <>
      <div className="mb-6 grid gap-4 md:grid-cols-3">
        <Card><CardHeader><CardTitle className="flex items-center gap-2 text-base"><PackageCheck className="size-4"/>Statut vérifié</CardTitle></CardHeader><CardContent><p className="text-2xl font-semibold">{statusLabel[c.order.observable_status] ?? c.order.observable_status}</p><p className="mt-1 text-xs text-muted-foreground">Observable au {dateLabel(c.order.as_of)}</p></CardContent></Card>
        <Card><CardHeader><CardTitle className="flex items-center gap-2 text-base"><CalendarClock className="size-4"/>Estimation de livraison</CardTitle></CardHeader><CardContent>{c.eta.valid_current_estimate ? <><p className="text-lg font-semibold">{dateLabel(c.eta.p10_date)} — {dateLabel(c.eta.p90_date)}</p><p className="text-sm text-muted-foreground">Médiane {dateLabel(c.eta.p50_date)} · couverture cible 80 %</p></> : <p className="text-sm text-muted-foreground">{c.eta.message}</p>}<Badge variant="outline" className="mt-3">{etaLabel[c.eta.model ?? c.eta.state] ?? "Estimation de livraison"}</Badge></CardContent></Card>
        <Card><CardHeader><CardTitle className="flex items-center gap-2 text-base"><Clock3 className="size-4"/>Date promise</CardTitle></CardHeader><CardContent><p className="text-2xl font-semibold">{dateLabel(c.order.promised_delivery_date)}</p><p className="mt-1 text-xs text-muted-foreground">Fait issu de la commande</p></CardContent></Card>
      </div>
      <div className="mb-6 grid gap-4 lg:grid-cols-2">
        <Card><CardHeader><CardTitle className="flex items-center gap-2"><History className="size-4"/>Jalons observables</CardTitle></CardHeader><CardContent className="space-y-4">{c.timeline.events.map((e) => <div key={e.event} className="flex gap-3"><CheckCircle2 className="mt-0.5 size-4 text-forest"/><div><p className="text-sm font-medium">{label[e.event] ?? e.event}</p><p className="text-xs text-muted-foreground">{dateLabel(e.at, true)}</p></div></div>)}</CardContent></Card>
        <Card><CardHeader><CardTitle>Commandes historiques comparables</CardTitle></CardHeader><CardContent className="space-y-3">{c.similar_orders.cases.length ? c.similar_orders.cases.map((x) => <div key={x.order_id} className="rounded-lg border p-3 text-sm"><div className="flex justify-between"><span>#{x.order_id.slice(0,8)}</span><Badge variant="outline">{x.customer_state ?? "—"}</Badge></div><p className="mt-1 text-muted-foreground">{catLabel(x.primary_category)} · {x.delivery_duration_days?.toFixed(1) ?? "—"} jours</p></div>) : <p className="text-sm text-muted-foreground">Pas assez de cas antérieurs pertinents.</p>}</CardContent></Card>
      </div>
      <Card className="mb-6"><CardHeader><CardTitle className="flex items-center gap-2"><MessageCircleQuestion className="size-4"/>Poser une question</CardTitle></CardHeader><CardContent><div className="mb-3 flex flex-wrap gap-2">{QUESTIONS.map((q) => <Button key={q} type="button" size="sm" variant={question===q?"default":"outline"} onClick={() => setQuestion(q)}>{q}</Button>)}</div><form className="flex gap-2" onSubmit={(e)=>{e.preventDefault();ask.mutate()}}><Input aria-label="Question client" value={question} onChange={(e)=>setQuestion(e.target.value)}/><Button type="submit" disabled={ask.isPending}>Répondre</Button></form></CardContent></Card>
      {ask.isPending && <LoadingBlock rows={5}/>} {ask.isError && <ErrorBlock error={ask.error}/>} {ask.data && <ReportView report={ask.data.report} evidence={ask.data.evidence}/>}
    </>}
  </div>
}
