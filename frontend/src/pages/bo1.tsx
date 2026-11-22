import { useQuery } from "@tanstack/react-query"
import { useState } from "react"
import { useDecisionMonth } from "@/components/app/month"
import { ReportView } from "@/components/app/report-view"
import { PageHeader } from "@/components/app/shell"
import { ErrorBlock, LoadingBlock } from "@/components/app/states"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { api } from "@/lib/api"
import { monthLabel } from "@/lib/format"

/** BO1 (agent d'un collègue) : affichage fidèle des rapports existants, sans transformation. */
export function Bo1Page() {
  const [month] = useDecisionMonth()
  const [target, setTarget] = useState<"late" | "poor">("late")
  const [orderInput, setOrderInput] = useState("")
  const [orderId, setOrderId] = useState<string | null>(null)
  const triage = useQuery({ queryKey: ["bo1-triage", month, target], queryFn: () => api.bo1Triage({ month: month!, target, top_k: 20 }), enabled: !!month })
  const diag = useQuery({ queryKey: ["bo1-diag", orderId], queryFn: () => api.bo1Diagnosis(orderId!), enabled: !!orderId })
  const valid = /^[0-9a-fA-F]{32}$/.test(orderInput.trim())

  return (
    <div>
      <PageHeader
        title="BO1 · Commandes à risque"
        description="Agent de diagnostic préventif (développé par un collègue, non modifié) : rapports affichés tels qu'il les produit. Les scores servent à prioriser une surveillance ; ce ne sont pas des probabilités."
      />
      <Tabs defaultValue="triage" className="min-w-0">
        <TabsList>
          <TabsTrigger value="triage">Commandes à surveiller</TabsTrigger>
          <TabsTrigger value="order">Diagnostic</TabsTrigger>
        </TabsList>
        <TabsContent value="triage" className="mt-4 space-y-4">
          <div className="flex items-center gap-2 text-sm">
            <span className="text-muted-foreground">Mois d'achat {month ? monthLabel(month) : "…"} · cible</span>
            <select className="h-8 rounded-md border border-input bg-background px-2 text-sm" value={target} onChange={(e) => setTarget(e.target.value as "late" | "poor")} aria-label="Cible">
              <option value="late">retard de livraison</option>
              <option value="poor">avis 1-2 étoiles</option>
            </select>
          </div>
          {triage.isLoading && <LoadingBlock rows={8} />}
          {triage.isError && <ErrorBlock error={triage.error} />}
          {triage.data && <ReportView report={triage.data.report} evidence={triage.data.evidence} />}
        </TabsContent>
        <TabsContent value="order" className="mt-4 space-y-4">
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
          <p className="text-xs text-muted-foreground">Astuce : copiez un identifiant depuis la liste « Commandes à surveiller ».</p>
          {diag.isLoading && <LoadingBlock rows={8} />}
          {diag.isError && <ErrorBlock error={diag.error} />}
          {diag.data && <ReportView report={diag.data.report} evidence={diag.data.evidence} />}
        </TabsContent>
      </Tabs>
    </div>
  )
}
