import { useQuery } from "@tanstack/react-query"
import { useState } from "react"
import { useDecisionMonth } from "@/components/app/month"
import { UF_NAMES } from "@/lib/geo"
import { ReportView } from "@/components/app/report-view"
import { PageHeader } from "@/components/app/shell"
import { ErrorBlock, LoadingBlock } from "@/components/app/states"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { api } from "@/lib/api"
import { monthLabel } from "@/lib/format"

/** BO2 (agent d'un collègue) : affichage fidèle du rapport « voix du client », sans transformation. */
export function Bo2Page() {
  const [month] = useDecisionMonth()
  const [state, setState] = useState("")
  const [category, setCategory] = useState("")
  const [applied, setApplied] = useState<{ state?: string; category?: string }>({})
  const rep = useQuery({
    queryKey: ["bo2", month, applied],
    queryFn: () => api.bo2Report({ month, ...applied }),
    enabled: !!month,
  })
  return (
    <div>
      <PageHeader
        title="BO2 · Voix du client"
        description="Agent d'un collègue (non modifié). Aspects détectés par une baseline mots-clés non encore validée ; les extraits indiquent leur langue (traduction automatique ou portugais original)."
      />
      <form
        className="mb-6 flex flex-wrap items-center gap-2"
        onSubmit={(e) => {
          e.preventDefault()
          setApplied({ state: state || undefined, category: category.trim() || undefined })
        }}
      >
        <span className="text-sm text-muted-foreground">Mois d'achat {month ? monthLabel(month) : "…"}</span>
        <select
          value={state}
          onChange={(e) => setState(e.target.value)}
          className="h-9 w-52 rounded-md border border-input bg-background px-2 text-sm"
          aria-label="État du client"
        >
          <option value="">Tous les États</option>
          {Object.entries(UF_NAMES)
            .sort((x, y) => x[1].localeCompare(y[1], "fr"))
            .map(([uf, name]) => (
              <option key={uf} value={uf}>
                {name}
              </option>
            ))}
        </select>
        <Input value={category} onChange={(e) => setCategory(e.target.value)} placeholder="Catégorie (ex. bed_bath_table)" className="w-64" aria-label="Catégorie" />
        <Button type="submit" variant="outline">
          Appliquer
        </Button>
      </form>
      {rep.isLoading && <LoadingBlock rows={8} />}
      {rep.isError && <ErrorBlock error={rep.error} />}
      {rep.data && <ReportView report={rep.data.report} evidence={rep.data.evidence} />}
    </div>
  )
}
