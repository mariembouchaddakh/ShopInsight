import { Download, FileSpreadsheet, FileText, Info } from "lucide-react"
import { buttonVariants } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { evidenceLabel, health, monthLong, provenance, verification } from "./model"
import type { Om5View } from "./types"
import { Disclosure, Panel, Pill } from "./ui"

export function ReportPanel({ view, base }: { view: Om5View; base: string }) {
  const h = health(view)
  const prov = provenance(view)
  const ver = verification(view)
  const links = [
    { href: `/api/om5/report.pdf?${base}`, label: "Rapport PDF", icon: <FileText />, primary: true },
    { href: `/api/om5/kpis.csv?${base}`, label: "Indicateurs (CSV)", icon: <FileSpreadsheet />, primary: false },
    { href: `/api/om5/evidence.csv?${base}`, label: "Preuves (CSV)", icon: <FileSpreadsheet />, primary: false },
  ]
  return (
    <div className="space-y-4">
      <Panel title="Rapport mensuel" icon={<FileText />} subtitle={<span className="capitalize">{monthLong(view.month)} · mode {view.mode === "as_of" ? "à date" : "rétrospectif"}</span>}
        actions={<div className="flex flex-wrap gap-2"><Pill tone={h.tone}>{h.label}</Pill><Pill tone={prov.llm ? "info" : "warn"}>{prov.label}</Pill><Pill tone={ver.verified ? "good" : "warn"}>{ver.label}</Pill></div>}>
        <h3 className="font-display text-lg font-semibold text-ink">{view.title}</h3>
        <p className="mt-2 max-w-4xl text-sm leading-7 text-ink/90">{view.narrative}</p>

        <div className="mt-5 flex flex-wrap gap-2.5">
          {links.map((l) => (
            <a key={l.href} href={l.href} className={cn(buttonVariants({ variant: l.primary ? "default" : "outline", size: "lg" }), "h-9 px-3.5")}>
              {l.icon}<Download className="hidden" />{l.label}
            </a>
          ))}
        </div>
        <p className="mt-2 text-[11px] text-muted-foreground">Les exports reprennent les valeurs du rapport affiché ; aucune nouvelle analyse n'est lancée depuis cet onglet.</p>
      </Panel>

      {view.caveats.length > 0 && (
        <Panel title="Limites de l'analyse" icon={<Info />}>
          <ul className="list-disc space-y-1 pl-5 text-[0.8125rem] leading-relaxed text-muted-foreground">{view.caveats.map((c, i) => <li key={i}>{c}</li>)}</ul>
        </Panel>
      )}

      {view.facts.length > 0 && (
        <Disclosure summary="Faits chiffrés du rapport et preuves associées" className="bg-card">
          <ul className="space-y-2">
            {view.facts.map((f, i) => (
              <li key={i}>
                <p className="text-ink">{f.text}</p>
                <p className="text-[11px] text-muted-foreground">{f.evidence.map((id) => evidenceLabel(view, id)).join(" · ")}</p>
              </li>
            ))}
          </ul>
        </Disclosure>
      )}
    </div>
  )
}
