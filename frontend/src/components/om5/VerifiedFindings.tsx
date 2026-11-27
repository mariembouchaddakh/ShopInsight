import { BadgeCheck } from "lucide-react"
import { evidenceLabel } from "./model"
import type { Om5View } from "./types"
import { Disclosure, Panel, Pill } from "./ui"

const SECTION: Record<string, string> = {
  health: "Santé globale", kpi: "Indicateurs", comparison: "Comparaison historique", anomaly: "Anomalies",
  statistics: "Statistiques", segments: "Segments", agents: "Agents spécialisés",
}

interface Insight { section: string; text: string; evidence_ids: string[] }

/** Constats rédigés dans le rapport, chacun rattaché aux preuves qui le fondent. */
export function VerifiedFindings({ view }: { view: Om5View }) {
  const insights = ((view.meta.generated_content?.insights ?? []) as Insight[]).filter((i) => i.text)
  if (!insights.length) return null
  return (
    <Panel title="Constats appuyés par des preuves" icon={<BadgeCheck />} subtitle="Chaque constat est rattaché aux données qui le fondent (dépliez pour consulter les références).">
      <ul className="grid gap-3 lg:grid-cols-2">
        {insights.map((i, idx) => (
          <li key={idx} className="flex flex-col gap-2 rounded-xl bg-muted/40 p-4">
            <Pill tone="info" className="w-fit">{SECTION[i.section] ?? i.section}</Pill>
            <p className="text-[0.8125rem] leading-relaxed text-ink/90">{i.text}</p>
            {i.evidence_ids?.length > 0 && (
              <Disclosure summary={`Références (${i.evidence_ids.length})`} className="mt-auto bg-card">
                <ul className="space-y-1">{i.evidence_ids.map((id) => <li key={id}>{evidenceLabel(view, id)}<br /><code className="break-all text-[10.5px] text-muted-foreground">{id}</code></li>)}</ul>
              </Disclosure>
            )}
          </li>
        ))}
      </ul>
    </Panel>
  )
}
