import { useQuery } from "@tanstack/react-query"
import { useSearchParams } from "react-router-dom"
import { api } from "@/lib/api"
import { monthLabel } from "@/lib/format"

/** Mois de décision partagé par les pages BO3 (paramètre d'URL ?month=AAAA-MM ; défaut : dernier mois complet). */
export function useDecisionMonth(): [string | undefined, (m: string) => void, string[]] {
  const [params, setParams] = useSearchParams()
  const meta = useQuery({ queryKey: ["meta"], queryFn: api.meta, staleTime: Infinity })
  const month = params.get("month") ?? meta.data?.default_month
  const set = (m: string) => {
    const next = new URLSearchParams(params)
    next.set("month", m)
    setParams(next, { replace: true })
  }
  return [month, set, meta.data?.decision_months ?? []]
}

export function MonthPicker() {
  const [month, setMonth, months] = useDecisionMonth()
  if (!months.length) return null
  return (
    <label className="flex items-center gap-2 text-xs text-muted-foreground">
      <span className="hidden sm:inline">Décision fin</span>
      <select
        aria-label="Mois de décision"
        className="h-8 rounded-md border border-input bg-background px-2 text-sm text-foreground shadow-xs outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
        value={month}
        onChange={(e) => setMonth(e.target.value)}
      >
        {[...months].reverse().map((m) => (
          <option key={m} value={m}>
            {monthLabel(m)}
          </option>
        ))}
      </select>
    </label>
  )
}
