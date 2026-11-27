import { CalendarDays, Database, Download, Loader2 } from "lucide-react"
import { buttonVariants } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { monthLong, type Tone } from "./model"
import type { Om5Mode } from "./types"
import { Pill } from "./ui"

const MODES: { id: Om5Mode; label: string; hint: string }[] = [
  { id: "as_of", label: "À date", hint: "Uniquement les informations connues à la fin du mois" },
  { id: "retrospective", label: "Rétrospectif", hint: "Informations consolidées, y compris postérieures au mois" },
]

export function OM5Header({ month, mode, onMode, status, pdfHref }: {
  month: string | undefined
  mode: Om5Mode
  onMode: (m: Om5Mode) => void
  /** null : analyse en cours de génération. */
  status: { label: string; tone: Tone } | null
  pdfHref: string | null
}) {
  return (
    <header className="mb-6 flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
      <div className="min-w-0">
        <h1 className="font-display text-3xl font-bold tracking-tight text-ink md:text-[2rem]">Centre de pilotage intelligent</h1>
        <p className="mt-1.5 max-w-2xl text-sm leading-relaxed text-muted-foreground">
          Analyse des performances, détection des anomalies et recommandations stratégiques.
        </p>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <Pill tone="info" icon={<CalendarDays />}>{month ? <span className="capitalize">{monthLong(month)}</span> : "Chargement du mois…"}</Pill>
          {status ? <Pill tone={status.tone}>{status.label}</Pill> : <Pill tone="neutral" icon={<Loader2 className="animate-spin" />}>Analyse en cours</Pill>}
          <Pill tone="neutral" icon={<Database />}>Données Olist historiques 2016–2018 · rejeu mensuel, pas de temps réel</Pill>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3 lg:justify-end">
        <div role="radiogroup" aria-label="Mode temporel" className="inline-flex rounded-xl bg-muted p-1 ring-1 ring-foreground/5">
          {MODES.map((m) => (
            <button
              key={m.id}
              type="button"
              role="radio"
              aria-checked={mode === m.id}
              title={m.hint}
              onClick={() => onMode(m.id)}
              className={cn(
                "rounded-lg px-3.5 py-1.5 text-sm font-medium transition-colors outline-none focus-visible:ring-2 focus-visible:ring-ring/60",
                mode === m.id ? "bg-navy text-white shadow-sm" : "text-muted-foreground hover:text-ink",
              )}
            >
              {m.label}
            </button>
          ))}
        </div>
        {pdfHref ? (
          <a href={pdfHref} className={cn(buttonVariants({ variant: "default", size: "lg" }), "h-9 px-3.5 shadow-sm")}>
            <Download /> Télécharger le rapport
          </a>
        ) : (
          <span aria-disabled="true" className={cn(buttonVariants({ variant: "default", size: "lg" }), "h-9 px-3.5 opacity-50")}>
            <Download /> Télécharger le rapport
          </span>
        )}
      </div>
    </header>
  )
}
