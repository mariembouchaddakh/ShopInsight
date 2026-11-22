import { useMemo, useState } from "react"
import { EvidenceDrawer } from "@/components/evidence/evidence-drawer"
import { SourcePills } from "@/components/evidence/source-pill"
import type { Evidence, Line, Report } from "@/lib/api"
import { KindTag } from "./badges"
import { expandStates } from "@/lib/geo"

function Block({ title, kind, lines, onOpen }: { title: string; kind: "fact" | "estimate" | "similar" | "action"; lines: Line[]; onOpen: (id: string) => void }) {
  if (!lines.length) return null
  return (
    <section className="space-y-2">
      <div className="flex items-center gap-2">
        <h3 className="text-sm font-semibold">{title}</h3>
        <KindTag kind={kind} />
      </div>
      <ul className="divide-y rounded-lg border">
        {lines.map((l, i) => (
          <li key={i} className="space-y-1.5 px-3 py-2.5 text-sm leading-relaxed">
            <p className={l.text.startsWith("ALERTE") ? "font-medium [overflow-wrap:anywhere]" : "[overflow-wrap:anywhere]"}>{expandStates(l.text)}</p>
            <SourcePills ids={l.evidence} onOpen={onOpen} />
          </li>
        ))}
      </ul>
    </section>
  )
}

const DEFAULT_TITLES = {
  facts: "Faits observés (données)",
  estimates: "Estimations",
  similar: "Comparaisons et expériences d'autres clients",
  actions: "Actions suggérées",
}

/** Rendu fidèle d'un rapport d'agent (contrat Report.to_dict()), avec preuves consultables. */
export function ReportView({ report, evidence, showTitle = true, showNarrative = true }: { report: Report; evidence: Evidence[]; showTitle?: boolean; showNarrative?: boolean }) {
  const [open, setOpen] = useState<string | null>(null)
  const t = useMemo(() => ({ ...DEFAULT_TITLES, ...(report.section_titles ?? {}) }), [report.section_titles])
  return (
    <div className="space-y-6">
      {showTitle && <h2 className="text-base font-semibold [overflow-wrap:anywhere]">{expandStates(report.title)}</h2>}
      {showNarrative && report.narrative && (
        <div className="rounded-lg border bg-muted/30 p-4 text-sm leading-relaxed">
          <p className="mb-1 text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
            Synthèse
          </p>
          {expandStates(report.narrative)}
        </div>
      )}
      <Block title={t.facts} kind="fact" lines={report.facts} onOpen={setOpen} />
      <Block title={t.estimates} kind="estimate" lines={report.estimates} onOpen={setOpen} />
      <Block title={t.similar} kind="similar" lines={report.similar_experiences} onOpen={setOpen} />
      <Block title={t.actions} kind="action" lines={report.actions} onOpen={setOpen} />
      {report.caveats.length > 0 && (
        <section className="space-y-2">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold">Limites</h3>
            <KindTag kind="caveat" />
          </div>
          <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
            {report.caveats.map((c, i) => (
              <li key={i} className="[overflow-wrap:anywhere]">{c}</li>
            ))}
          </ul>
        </section>
      )}
      <EvidenceDrawer evidence={evidence} openId={open} onClose={() => setOpen(null)} />
    </div>
  )
}
