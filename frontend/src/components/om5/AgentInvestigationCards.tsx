import { CircleAlert, CircleCheck, CircleDashed, CircleX, MessagesSquare, Store, Truck } from "lucide-react"
import type { ComponentType } from "react"
import { cn } from "@/lib/utils"
import { AGENT_META, AGENT_STATE_LABEL, agentStatus, evidenceLabel, readAgent, type AgentKey, type AgentState, type Tone } from "./model"
import type { Om5View } from "./types"
import { Disclosure, Panel, Pill } from "./ui"

const ICON: Record<AgentKey, ComponentType<{ className?: string }>> = { bo1: Truck, bo2: MessagesSquare, bo3: Store }
const STATE_TONE: Record<AgentState, Tone> = { done: "good", not_needed: "neutral", unavailable: "warn", failed: "bad" }
const STATE_ICON: Record<AgentState, ComponentType<{ className?: string }>> = { done: CircleCheck, not_needed: CircleDashed, unavailable: CircleAlert, failed: CircleX }

function AgentCard({ view, k }: { view: Om5View; k: AgentKey }) {
  const meta = AGENT_META[k]
  const st = agentStatus(view, k)
  const reading = readAgent(k, view.agents[k]?.result)
  const Icon = ICON[k]
  const SIcon = STATE_ICON[st.state]
  const evId = view.agents[k]?.evidence_id
  const hasDetails = reading.extra.length || reading.actions.length || reading.caveats.length || reading.sellers.length || evId

  return (
    <article className={cn("flex flex-col rounded-2xl bg-card p-5 ring-1 ring-foreground/10", st.state === "done" ? "shadow-[0_1px_2px_rgb(19_34_56/6%)]" : "bg-muted/30")}>
      <header className="flex items-start gap-3">
        <span className={cn("grid size-11 shrink-0 place-items-center rounded-xl", st.state === "done" ? "bg-navy text-butter" : "bg-muted text-muted-foreground")}><Icon className="size-5" /></span>
        <div className="min-w-0 flex-1">
          <p className="text-[11px] font-semibold tracking-wide text-muted-foreground">{meta.code}</p>
          <h3 className="font-display text-base font-semibold leading-tight text-ink">{meta.title}</h3>
        </div>
      </header>
      <div className="mt-3"><Pill tone={STATE_TONE[st.state]} icon={<SIcon />}>{AGENT_STATE_LABEL[st.state]}</Pill></div>
      <p className="mt-3 text-xs leading-relaxed text-muted-foreground"><span className="font-medium text-ink/80">Objectif :</span> {meta.objective}</p>
      {st.trigger && st.state !== "not_needed" && <p className="mt-1 text-xs text-muted-foreground"><span className="font-medium text-ink/80">Déclenchement :</span> {st.trigger}</p>}

      <div className="mt-4 flex-1 space-y-3">
        {st.state === "not_needed" && (
          <p className="rounded-lg bg-card/70 p-3 text-[0.8125rem] leading-relaxed text-muted-foreground">
            {view.detected.length
              ? "Cet agent n'a pas été sollicité : les anomalies de ce mois ne relevaient pas de son périmètre."
              : "Aucune anomalie détectée : aucune investigation complémentaire n'a été nécessaire."}
          </p>
        )}
        {st.state === "unavailable" && <p className="rounded-lg bg-amber-tint p-3 text-[0.8125rem] text-amber-ink">L'agent a été appelé mais n'a renvoyé aucun résultat exploitable pour ce mois.</p>}
        {st.state === "failed" && <p role="alert" className="rounded-lg bg-burgundy-tint p-3 text-[0.8125rem] text-burgundy">L'investigation a échoué ; les conclusions de ce rapport ne s'appuient pas sur cet agent.</p>}

        {st.state === "done" && (
          <>
            {reading.summary && <p className="text-[0.8125rem] leading-relaxed text-ink/90">{reading.summary}</p>}
            {reading.indicators.length > 0 && (
              <dl className="grid grid-cols-2 gap-2">
                {reading.indicators.map((i) => (
                  <div key={i.label} className="rounded-lg bg-navy-tint/60 px-3 py-2">
                    <dt className="text-[11px] text-muted-foreground">{i.label}</dt>
                    <dd className="font-display text-lg font-bold tabular-nums text-ink">{i.value}</dd>
                  </div>
                ))}
              </dl>
            )}
            {reading.findings.length > 0 && (
              <ul className="space-y-1.5 text-[0.8125rem] leading-relaxed text-ink/90">
                {reading.findings.map((f, i) => <li key={i} className="flex gap-2"><span aria-hidden className="mt-2 size-1.5 shrink-0 rounded-full bg-butter-hover ring-1 ring-navy/20" />{f}</li>)}
              </ul>
            )}
          </>
        )}
      </div>

      {(hasDetails || st.error) && st.state !== "not_needed" && (
        <Disclosure summary="Détails de l'investigation" className="mt-4">
          <div className="space-y-3">
            {st.error && <p className="text-burgundy">Erreur : {st.error}</p>}
            {reading.extra.length > 0 && <ul className="list-disc space-y-1 pl-4">{reading.extra.map((t, i) => <li key={i}>{t}</li>)}</ul>}
            {reading.actions.length > 0 && <div><p className="mb-1 font-semibold text-ink">Actions suggérées par l'agent</p><ul className="list-disc space-y-1 pl-4">{reading.actions.map((t, i) => <li key={i}>{t}</li>)}</ul></div>}
            {reading.sellers.length > 0 && (
              <div>
                <p className="mb-1 font-semibold text-ink">Vendeurs les plus concernés</p>
                <ul className="space-y-1">{reading.sellers.map((s) => <li key={s.id} className="flex justify-between gap-2"><span>Vendeur {s.id.slice(0, 8)}… · {s.category}</span><span className="text-muted-foreground">{s.alerts} alertes · {s.severity}</span></li>)}</ul>
              </div>
            )}
            {reading.caveats.length > 0 && <p className="text-muted-foreground">{reading.caveats.join(" ")}</p>}
            {evId && <p className="text-muted-foreground">Preuve : {evidenceLabel(view, evId)} · <code className="break-all">{evId}</code></p>}
          </div>
        </Disclosure>
      )}
    </article>
  )
}

export function AgentInvestigationCards({ view }: { view: Om5View }) {
  const keys: AgentKey[] = ["bo1", "bo2", "bo3"]
  const done = keys.filter((k) => agentStatus(view, k).state === "done").length
  return (
    <Panel title="Investigations spécialisées" subtitle={done ? `${done} agent${done > 1 ? "s" : ""} spécialisé${done > 1 ? "s" : ""} ont collaboré à cette analyse.` : "Les agents spécialisés ne sont sollicités que lorsqu'une anomalie le justifie."}>
      <div className="grid gap-4 lg:grid-cols-3">{keys.map((k) => <AgentCard key={k} view={view} k={k} />)}</div>
    </Panel>
  )
}
