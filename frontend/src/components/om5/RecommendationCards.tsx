import { ClipboardCheck, Clock, Eye, MapPin, Target, TrendingUp, Users } from "lucide-react"
import type { ReactNode } from "react"
import { cn } from "@/lib/utils"
import { buildRecommendations, evidenceLabel, LEVEL_LABEL, type Rec, type Tone } from "./model"
import type { Om5View } from "./types"
import { TONE } from "./tone"
import { Disclosure, Notice, Panel, Pill } from "./ui"

const LEVEL_TONE: Record<NonNullable<Rec["level"]>, Tone> = { haute: "bad", moyenne: "warn", basse: "info" }

function Fact({ icon, label, children }: { icon: ReactNode; label: string; children: ReactNode }) {
  return (
    <div className="flex min-w-0 gap-2">
      <span className="mt-0.5 text-navy-soft [&>svg]:size-3.5">{icon}</span>
      <div className="min-w-0"><dt className="text-[11px] text-muted-foreground">{label}</dt><dd className="text-xs font-medium text-ink">{children}</dd></div>
    </div>
  )
}

function RecCard({ rec, view, rank }: { rec: Rec; view: Om5View; rank?: number }) {
  const tone: Tone = rec.preventive ? "info" : rec.level ? LEVEL_TONE[rec.level] : "neutral"
  return (
    <article className="lift flex flex-col gap-3 rounded-2xl bg-card p-5 shadow-[0_1px_2px_rgb(19_34_56/6%)] ring-1 ring-foreground/10">
      <header className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          {rank != null && <span className="grid size-7 shrink-0 place-items-center rounded-full bg-navy text-xs font-bold text-butter">{rank}</span>}
          <h3 className="font-display text-[0.95rem] leading-snug font-semibold text-ink">{rec.title}</h3>
        </div>
        {rec.preventive
          ? <Pill tone="info" icon={<Eye />}>Suivi préventif</Pill>
          : rec.level && <Pill tone={tone}>{LEVEL_LABEL[rec.level]}</Pill>}
      </header>

      {!rec.preventive && (
        <div>
          <div className="mb-1 flex items-baseline justify-between text-[11px] text-muted-foreground">
            <span>Score de priorité (déterministe)</span>
            <span className={cn("font-display text-sm font-bold tabular-nums", TONE[tone].text)}>{Math.round(rec.score)}<span className="text-[11px] font-medium text-muted-foreground"> / 100</span></span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-muted" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(rec.score)} aria-label={`Score de priorité : ${Math.round(rec.score)} sur 100`}>
            <div className={cn("h-full rounded-full", TONE[tone].bar)} style={{ width: `${Math.min(Math.max(rec.score, 0), 100)}%` }} />
          </div>
        </div>
      )}

      <p className="text-[0.8125rem] leading-relaxed text-ink/90">{rec.description}</p>
      <p className="rounded-lg bg-muted/50 p-2.5 text-xs leading-relaxed text-muted-foreground"><span className="font-semibold text-ink/80">Pourquoi : </span>{rec.justification}</p>

      <dl className="grid grid-cols-2 gap-3">
        {rec.team && <Fact icon={<Users />} label="Équipe responsable">{rec.team}</Fact>}
        {rec.timeframe && <Fact icon={<Clock />} label="Échéance suggérée">{rec.timeframe}</Fact>}
        {rec.benefit && <div className="col-span-2"><Fact icon={<TrendingUp />} label="Bénéfice attendu">{rec.benefit}</Fact></div>}
      </dl>

      {(rec.related || rec.segment) && (
        <div className="flex flex-wrap gap-1.5">
          {rec.related && <Pill tone="neutral" icon={<Target />}>{rec.related}</Pill>}
          {rec.segment && <Pill tone="neutral" icon={<MapPin />}>{rec.segment}</Pill>}
        </div>
      )}

      {rec.evidenceIds.length > 0 && (
        <Disclosure summary={`Preuves (${rec.evidenceIds.length})`} className="mt-auto">
          <ul className="space-y-1.5">
            {rec.evidenceIds.map((id) => <li key={id}><span className="text-ink">{evidenceLabel(view, id)}</span><br /><code className="break-all text-[10.5px] text-muted-foreground">{id}</code></li>)}
          </ul>
        </Disclosure>
      )}
    </article>
  )
}

export function RecommendationCards({ view, limit, compact }: { view: Om5View; limit?: number; compact?: boolean }) {
  const all = buildRecommendations(view)
  const action = all.filter((r) => !r.preventive)
  const preventive = all.filter((r) => r.preventive)
  const shownAction = limit ? action.slice(0, limit) : action
  const grid = compact ? "grid gap-4 md:grid-cols-2 xl:grid-cols-3" : "grid gap-4 xl:grid-cols-2"

  if (!all.length) {
    return (
      <Panel title="Plan d'action recommandé" icon={<ClipboardCheck />}>
        <Notice tone="info" icon={<Eye />} title="Aucune action spécifique à proposer">Maintenir la surveillance mensuelle standard des indicateurs.</Notice>
      </Panel>
    )
  }
  return (
    <div className="space-y-5">
      {shownAction.length > 0 && (
        <Panel title="Plan d'action recommandé" icon={<ClipboardCheck />}
          subtitle="Classées par score de priorité déterministe (amplitude, confiance, volume). Ces recommandations sont des aides à la décision : aucune action n'est exécutée automatiquement.">
          <div className={grid}>{shownAction.map((r, i) => <RecCard key={r.key} rec={r} view={view} rank={i + 1} />)}</div>
          {limit && action.length > limit && <p className="mt-3 text-xs text-muted-foreground">{action.length - limit} autre{action.length - limit > 1 ? "s" : ""} action{action.length - limit > 1 ? "s" : ""} dans l'onglet « Plan d'action ».</p>}
        </Panel>
      )}
      {preventive.length > 0 && (
        <Panel title="Surveillance préventive" icon={<Eye />}
          subtitle="Aucune dégradation à traiter : ces suggestions entretiennent la vigilance et ne portent pas de score de priorité.">
          <div className={grid}>{preventive.map((r) => <RecCard key={r.key} rec={r} view={view} />)}</div>
        </Panel>
      )}
    </div>
  )
}
