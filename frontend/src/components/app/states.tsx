import { AlertCircle, Inbox } from "lucide-react"
import type { ReactNode } from "react"
import { ApiError } from "@/lib/api"
import { Skeleton } from "@/components/ui/skeleton"
import { cn } from "@/lib/utils"

export function LoadingBlock({ rows = 4, className }: { rows?: number; className?: string }) {
  return (
    <div className={cn("space-y-2", className)} aria-busy="true" aria-label="Chargement">
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="h-9 w-full" />
      ))}
    </div>
  )
}

export function ErrorBlock({ error, className }: { error: unknown; className?: string }) {
  const status = error instanceof ApiError ? error.status : undefined
  const message = error instanceof Error ? error.message : String(error)
  const hint =
    status === 503
      ? "L'agent est en cours de chargement ou ses données manquent : réessayez dans quelques secondes."
      : status === 404
        ? "Élément introuvable pour ce mois de décision."
        : status === undefined
          ? "API injoignable : lancez « uvicorn backend.app.main:app --port 8000 »."
          : undefined
  return (
    <div role="alert" className={cn("flex gap-3 rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm", className)}>
      <AlertCircle className="mt-0.5 size-4 shrink-0 text-destructive" />
      <div className="space-y-1">
        <p className="font-medium text-destructive">{status ? `Erreur ${status}` : "Erreur"}</p>
        <p className="text-muted-foreground">{message}</p>
        {hint && <p className="text-muted-foreground">{hint}</p>}
      </div>
    </div>
  )
}

export function EmptyBlock({ children }: { children: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
      <Inbox className="size-5" />
      {children}
    </div>
  )
}
