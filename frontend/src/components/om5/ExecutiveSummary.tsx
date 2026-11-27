import { CalendarDays, CircleAlert, CircleCheck, ShieldCheck, Sparkles } from "lucide-react"
import type { ReactNode } from "react"
import { cn } from "@/lib/utils"
import { health, monthLong, provenance, verification } from "./model"
import type { Om5View } from "./types"

function Chip({ children, icon, accent }: { children: ReactNode; icon?: ReactNode; accent?: "gold" | "good" | "warn" | "bad" }) {
  return (
    <span className={cn(
      "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ring-1 ring-inset [&>svg]:size-3.5",
      accent === "gold" && "bg-butter/15 text-butter ring-butter/35",
      accent === "good" && "bg-emerald-400/15 text-emerald-200 ring-emerald-300/30",
      accent === "warn" && "bg-butter/20 text-butter ring-butter/40",
      accent === "bad" && "bg-rose-400/15 text-rose-200 ring-rose-300/30",
      !accent && "bg-white/10 text-white/85 ring-white/20",
    )}>
      {icon}
      {children}
    </span>
  )
}

export function ExecutiveSummary({ view }: { view: Om5View }) {
  const h = health(view)
  const prov = provenance(view)
  const ver = verification(view)
  const n = view.detected.length
  return (
    <section aria-labelledby="om5-exec" className="relative overflow-hidden rounded-2xl bg-navy p-6 text-white shadow-[0_10px_30px_-14px_rgb(19_34_56/60%)] md:p-8">
      <span aria-hidden className="absolute inset-y-0 left-0 w-1.5 bg-butter" />
      <div className="flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="grid size-9 place-items-center rounded-xl bg-butter text-navy"><Sparkles className="size-5" /></span>
            <h2 id="om5-exec" className="font-display text-lg font-semibold tracking-tight">Synthèse exécutive</h2>
            <Chip accent={prov.llm ? "gold" : "warn"}>{prov.label}</Chip>
            <Chip accent={ver.verified ? "good" : "warn"} icon={ver.verified ? <ShieldCheck /> : <CircleAlert />}>{ver.label}</Chip>
          </div>
          <p className="mt-4 max-w-4xl text-[1.0625rem] leading-8 text-white/95">{view.narrative}</p>
          {!prov.llm && (
            <p className="mt-3 max-w-3xl text-xs leading-relaxed text-white/70">
              Cette synthèse a été produite automatiquement à partir des indicateurs calculés, sans rédaction par le modèle de langage.
            </p>
          )}
        </div>

        <dl className="grid shrink-0 grid-cols-3 gap-3 text-sm lg:w-[22rem] lg:grid-cols-1">
          <div className="rounded-xl bg-white/[0.07] p-3.5 ring-1 ring-white/10">
            <dt className="flex items-center gap-1.5 text-xs text-white/65"><CalendarDays className="size-3.5" /> Mois analysé</dt>
            <dd className="mt-1 font-display text-lg font-semibold capitalize">{monthLong(view.month)}</dd>
          </div>
          <div className="rounded-xl bg-white/[0.07] p-3.5 ring-1 ring-white/10">
            <dt className="text-xs text-white/65">Anomalies détectées</dt>
            <dd className="mt-1 font-display text-lg font-semibold tabular-nums">{n}</dd>
          </div>
          <div className="rounded-xl bg-white/[0.07] p-3.5 ring-1 ring-white/10">
            <dt className="text-xs text-white/65">Santé globale</dt>
            <dd className="mt-1">
              <Chip accent={h.tone === "good" ? "good" : h.tone === "bad" ? "bad" : "warn"} icon={h.tone === "good" ? <CircleCheck /> : <CircleAlert />}>{h.label}</Chip>
            </dd>
          </div>
        </dl>
      </div>
    </section>
  )
}
