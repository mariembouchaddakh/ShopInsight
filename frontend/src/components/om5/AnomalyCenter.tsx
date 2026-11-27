import { ArrowRight, MapPin, ShieldAlert, ShieldCheck, Tag } from "lucide-react"
import { cn } from "@/lib/utils"
import { evidenceLabel, readAnomaly, segmentBars, type Tone } from "./model"
import type { Om5AnomalyRow, Om5View } from "./types"
import { TONE } from "./tone"
import { Disclosure, Notice, Panel, Pill } from "./ui"

export function NoAnomalyState({ view }: { view: Om5View }) {
  return (
    <Notice tone="good" icon={<ShieldCheck />} title="Aucune dégradation statistiquement significative détectée">
      <p>
        {view.anomalies.length} indicateurs ont été comparés à leur historique : aucun écart anormal ce mois-ci. La surveillance préventive reste active sur l'ensemble des indicateurs.
      </p>
      <p className="mt-1.5">L'absence d'anomalie statistique ne garantit pas l'absence de risque métier : elle indique seulement qu'aucun écart inhabituel n'apparaît dans les données analysées.</p>
    </Notice>
  )
}

function Stat({ label, value, strong }: { label: string; value: string; strong?: boolean }) {
  return (
    <div className="min-w-0">
      <dt className="text-[11px] text-muted-foreground">{label}</dt>
      <dd className={cn("mt-0.5 truncate font-display tabular-nums", strong ? "text-lg font-bold text-ink" : "text-base font-semibold text-ink/85")}>{value}</dd>
    </div>
  )
}

function AnomalyCard({ a, view }: { a: Om5AnomalyRow; view: Om5View }) {
  const r = readAnomaly(a)
  const tone: Tone = a.severity === "high" ? "bad" : "warn"
  const states = segmentBars(view, a.metric_id, "state").slice(0, 3)
  const cats = segmentBars(view, a.metric_id, "category").slice(0, 2)
  return (
    <article className={cn("rounded-xl border-l-4 bg-card p-4 ring-1 ring-foreground/10", a.severity === "high" ? "border-l-burgundy" : "border-l-amber-ink")}>
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="flex items-center gap-2 font-display text-[0.95rem] font-semibold text-ink"><ShieldAlert className={cn("size-4", TONE[tone].text)} /> {a.label}</h3>
        <Pill tone={tone}>Sévérité {r.severity.toLowerCase()}</Pill>
      </header>
      <dl className="mt-3 grid grid-cols-3 gap-3 rounded-lg bg-muted/50 p-3">
        <Stat label="Valeur actuelle" value={r.current} strong />
        <Stat label="Référence historique" value={r.baseline} />
        <Stat label="Variation" value={r.delta} />
      </dl>
      <p className="mt-3 text-[0.8125rem] leading-relaxed text-ink/90">{r.interpretation}</p>
      {(states.length > 0 || cats.length > 0) && (
        <div className="mt-3 flex flex-wrap items-center gap-1.5 text-xs">
          <span className="text-muted-foreground">Segments les plus exposés :</span>
          {states.map((s) => <Pill key={`s-${s.label}`} tone="info" icon={<MapPin />}>{s.label}</Pill>)}
          {cats.map((s) => <Pill key={`c-${s.label}`} tone="neutral" icon={<Tag />}>{s.label}</Pill>)}
        </div>
      )}
      <Disclosure summary="Détails de l'investigation" className="mt-3">
        <dl className="grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-4">
          <Stat label="Observations" value={a.sample_size.toLocaleString("fr-FR")} />
          <Stat label="Méthode statistique" value={a.method} />
          <Stat label="Score robuste (z)" value={a.robust_z == null ? "—" : a.robust_z.toLocaleString("fr-FR", { maximumFractionDigits: 2 })} />
          <Stat label="q-value (Benjamini-Hochberg)" value={a.q_value == null ? "—" : a.q_value.toExponential(2)} />
          {a.p_value != null && <Stat label="p-value" value={a.p_value.toExponential(2)} />}
        </dl>
        <p className="mt-3 text-muted-foreground">Preuve : {evidenceLabel(view, a.evidence_id)} · <code className="break-all">{a.evidence_id}</code></p>
      </Disclosure>
    </article>
  )
}

export function AnomalyCenter({ view, limit, onSeeAll }: { view: Om5View; limit?: number; onSeeAll?: () => void }) {
  const list = [...view.detected].sort((a, b) => Number(b.severity === "high") - Number(a.severity === "high"))
  const shown = limit ? list.slice(0, limit) : list
  return (
    <Panel title="Centre d'alertes" icon={<ShieldAlert />} subtitle="Dégradations statistiquement significatives face à l'historique ; un signal à investiguer, jamais une sanction automatique."
      actions={list.length > 0 && <Pill tone={list.some((a) => a.severity === "high") ? "bad" : "warn"}>{list.length} alerte{list.length > 1 ? "s" : ""}</Pill>}>
      {!list.length ? <NoAnomalyState view={view} /> : (
        <div className="space-y-3">
          {shown.map((a) => <AnomalyCard key={a.metric_id} a={a} view={view} />)}
          {limit && list.length > limit && onSeeAll && (
            <button type="button" onClick={onSeeAll} className="flex items-center gap-1 text-xs font-medium text-navy-soft hover:underline">
              Voir les {list.length} alertes <ArrowRight className="size-3.5" />
            </button>
          )}
        </div>
      )}
    </Panel>
  )
}
