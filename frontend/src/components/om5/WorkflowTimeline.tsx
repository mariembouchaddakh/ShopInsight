import { Activity, Database, FileText, ListChecks, Radar, ShieldCheck, Sparkles, Users, Workflow } from "lucide-react"
import type { ComponentType } from "react"
import { cn } from "@/lib/utils"
import { buildWorkflow, type Stage, type StageState, type Tone } from "./model"
import type { Om5View } from "./types"
import { Panel, Pill } from "./ui"

const ICON: Record<string, ComponentType<{ className?: string }>> = {
  collect: Database, perf: Activity, anomaly: Radar, plan: ListChecks, agents: Users, reco: Sparkles, verify: ShieldCheck, final: FileText,
}

function stateView(s: Stage): { label: string; tone: Tone; ring: string } {
  const st: StageState = s.state
  if (st === "failed") return { label: "Échec", tone: "bad", ring: "bg-burgundy text-white" }
  if (st === "skipped") return { label: "Non nécessaire", tone: "neutral", ring: "border-2 border-dashed border-slate-300 bg-card text-slate-400" }
  if (st === "unknown") return { label: "Non disponible", tone: "neutral", ring: "border-2 border-dashed border-slate-300 bg-card text-slate-400" }
  if (s.warn) return { label: "Terminé avec réserve", tone: "warn", ring: "bg-amber-ink text-white" }
  return { label: "Terminé", tone: "good", ring: "bg-forest-mark text-white" }
}

export function WorkflowTimeline({ view }: { view: Om5View }) {
  const stages = buildWorkflow(view)
  return (
    <Panel title="Déroulement de l'analyse" icon={<Workflow />} subtitle="Étapes réellement exécutées par l'orchestrateur pour ce rapport. Les étapes grisées n'ont pas été nécessaires.">
      <ol className="relative">
        {stages.map((s, i) => {
          const sv = stateView(s)
          const Icon = ICON[s.id]
          const last = i === stages.length - 1
          return (
            <li key={s.id} className="relative flex gap-4 pb-5 last:pb-0">
              {!last && <span aria-hidden className={cn("absolute top-10 bottom-0 left-[1.15rem] w-0.5", s.state === "done" ? "bg-forest-mark/40" : "border-l-2 border-dashed border-slate-300")} />}
              <span className={cn("relative z-10 grid size-9 shrink-0 place-items-center rounded-full", sv.ring)}><Icon className="size-4" /></span>
              <div className="flex min-w-0 flex-1 flex-wrap items-start justify-between gap-x-3 gap-y-1">
                <div className="min-w-0">
                  <p className={cn("text-sm font-semibold", s.state === "done" ? "text-ink" : "text-muted-foreground")}><span className="mr-1.5 text-xs text-muted-foreground tabular-nums">{i + 1}.</span>{s.title}</p>
                  <p className="text-xs text-muted-foreground">{s.caption}</p>
                </div>
                <Pill tone={sv.tone}>{sv.label}</Pill>
              </div>
            </li>
          )
        })}
      </ol>
    </Panel>
  )
}
