import { Loader2 } from "lucide-react"
import { Skeleton } from "@/components/ui/skeleton"

/** Squelette de page. Aucune progression simulée : le message décrit seulement ce que le serveur fait réellement. */
export function Om5Loading() {
  return (
    <div aria-busy="true" aria-live="polite" className="space-y-5">
      <div className="flex items-center gap-2.5 rounded-xl bg-navy-tint px-4 py-3 text-sm text-navy-soft">
        <Loader2 className="size-4 animate-spin" />
        <span>Analyse en cours de génération : calcul des indicateurs, détection des anomalies, puis rédaction et vérification de la synthèse. Cela peut prendre quelques secondes.</span>
      </div>
      <Skeleton className="h-44 w-full rounded-2xl" />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">{Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-44 rounded-2xl" />)}</div>
      <div className="grid gap-4 xl:grid-cols-[1fr_24rem]">
        <Skeleton className="h-80 rounded-2xl" />
        <Skeleton className="h-80 rounded-2xl" />
      </div>
    </div>
  )
}
