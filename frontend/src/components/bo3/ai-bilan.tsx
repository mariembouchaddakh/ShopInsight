import type { UseMutationResult } from "@tanstack/react-query"
import { ChevronDown, Compass, HelpCircle, ListChecks, RefreshCw, Sparkles, Stethoscope } from "lucide-react"
import { useState, type ReactNode } from "react"
import { openAssistant, useAiStatus } from "@/components/assistant/assistant-widget"
import { Skeleton } from "@/components/ui/skeleton"
import { Button } from "@/components/ui/button"
import type { AiAnalysis, AiItem } from "@/lib/api"
import { cn } from "@/lib/utils"
import { ActionCard, aiErrorMessage, ProseList, QuestionList } from "./ai-items"

export type AnalysisMutation = UseMutationResult<AiAnalysis, Error, void>

function Block({ icon, step, title, subtitle, children, className }: { icon: ReactNode; step: string; title: string; subtitle?: string; children: ReactNode; className?: string }) {
  return (
    <section className={cn("min-w-0 space-y-4 rounded-2xl border bg-card p-5", className)}>
      <header className="flex items-start gap-3">
        <span className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-ink">{icon}</span>
        <div>
          <p className="text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">{step}</p>
          <h3 className="text-base font-semibold">{title}</h3>
          {subtitle && <p className="text-xs text-muted-foreground">{subtitle}</p>}
        </div>
      </header>
      {children}
    </section>
  )
}

const empty = (xs?: AiItem[]) => !xs || xs.length === 0

/** Onglet « Bilan & Plan d'action » : synthèse toujours visible, puis analyse stratégique à la demande
 * (diagnostic croisé, positionnement, plan de remontée, questions d'investigation). Seuls les éléments contrôlés contre les sources sont affichés. */
export function BilanPanel({
  alerted,
  analysis,
  onOpen,
  children,
}: {
  alerted: boolean
  analysis: AnalysisMutation
  onOpen: (id: string) => void
  children?: ReactNode
}) {
  const status = useAiStatus()
  const [more, setMore] = useState(false)
  const a = analysis.data
  const sec = a?.sections ?? {}
  const usable = status.data?.usable
  const diag = [...(sec.diagnostic ?? []), ...(sec.hypotheses ?? [])]

  return (
    <div className="space-y-6">
      <section className="relative overflow-hidden rounded-2xl border bg-gradient-to-br from-primary/10 via-background to-background p-6">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
          <div className="max-w-3xl space-y-3">
            <p className="flex items-center gap-2 text-xs font-semibold tracking-wide text-ink uppercase">
              <Sparkles className="size-3.5" /> {alerted ? "Bilan & plan de remontée" : "Bilan de suivi"}
            </p>
            {a?.resume && <p className="text-base leading-relaxed [overflow-wrap:anywhere]">{a.resume}</p>}
            {!a && !analysis.isPending && (
              <p className="text-sm text-muted-foreground">
                L'analyse stratégique croise la performance du vendeur, son historique, ses concurrents directs, les avis de ses clients et ses commandes
                récentes pour proposer un diagnostic et un plan d'action.
              </p>
            )}
          </div>
          {usable && (
            <div className="flex shrink-0 flex-wrap gap-2">
              <Button onClick={() => analysis.mutate()} disabled={analysis.isPending} size="lg">
                {a ? <RefreshCw className="size-4" /> : <Sparkles className="size-4" />}
                {analysis.isPending ? "Préparation…" : a ? "Actualiser l'analyse" : "Générer l'analyse stratégique"}
              </Button>
              <Button variant="outline" size="lg" onClick={() => openAssistant()}>
                Poser une question
              </Button>
            </div>
          )}
        </div>
        {status.data && !usable && (
          <p className="mt-4 text-sm text-muted-foreground">L'analyse stratégique est momentanément indisponible ; le bilan chiffré ci-dessous reste complet.</p>
        )}
      </section>

      {children}

      {analysis.isPending && (
        <div className="space-y-3" role="status" aria-label="Préparation de la synthèse">
          <p className="text-sm text-muted-foreground">Préparation de la synthèse : croisement des indicateurs, des avis clients et des commandes…</p>
          <div className="grid gap-4 lg:grid-cols-2">
            {[0, 1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-44 rounded-2xl" />
            ))}
          </div>
        </div>
      )}
      {analysis.isError && <p className="rounded-xl border border-destructive/30 bg-destructive/5 p-4 text-sm">{aiErrorMessage(analysis.error)}</p>}

      {a && !analysis.isPending && (
        <>
          <div className="grid gap-5 lg:grid-cols-2">
            <Block icon={<Stethoscope className="size-4" />} step="1 · Diagnostic croisé" title="Que se passe-t-il ?" subtitle="Opérations, historique et avis clients mis en regard">
              {diag.length ? <ProseList items={diag} onOpen={onOpen} /> : <p className="text-sm text-muted-foreground">Aucun élément de diagnostic suffisamment étayé.</p>}
            </Block>
            <Block icon={<Compass className="size-4" />} step="2 · Positionnement concurrentiel" title="Où se situe-t-il ?" subtitle="Dans sa catégorie et face à ses concurrents directs">
              {empty(sec.positionnement ?? sec.comparaison) ? (
                <p className="text-sm text-muted-foreground">Pas de comparaison disponible.</p>
              ) : (
                <ProseList items={(sec.positionnement ?? sec.comparaison)!} onOpen={onOpen} />
              )}
            </Block>
            <Block icon={<ListChecks className="size-4" />} step="3 · Plan de remontée" title="Comment rejoindre les meilleurs ?" subtitle="Pistes à valider avec le vendeur" className="lg:col-span-2">
              {a.actions.length ? (
                <ul className="grid gap-3 md:grid-cols-2">
                  {a.actions.map((ac, i) => (
                    <ActionCard key={i} ac={ac} onOpen={onOpen} />
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-muted-foreground">Aucune piste suffisamment étayée.</p>
              )}
            </Block>
            {(a.questions?.length ?? 0) > 0 && (
              <Block icon={<HelpCircle className="size-4" />} step="4 · Questions d'investigation" title="Ce qu'il reste à vérifier" subtitle="Les données de la plateforme ne permettent pas de trancher seules" className="lg:col-span-2">
                <QuestionList questions={a.questions ?? []} onOpen={onOpen} onPick={(q) => openAssistant(`À propos de « ${q} » : quelles données du vendeur aident à y répondre ?`)} />
              </Block>
            )}
          </div>

          {[sec.situation, sec.faiblesses, sec.points_forts, sec.inconnues].some((x) => !empty(x)) && (
            <div className="rounded-2xl border">
              <button className="flex w-full items-center justify-between px-5 py-3 text-sm font-medium" onClick={() => setMore((v) => !v)} aria-expanded={more}>
                Compléments : situation, faiblesses, points forts, limites
                <ChevronDown className={cn("size-4 transition", more && "rotate-180")} />
              </button>
              {more && (
                <div className="grid gap-6 border-t p-5 lg:grid-cols-2">
                  {(
                    [
                      ["Situation", sec.situation],
                      ["Faiblesses récurrentes", sec.faiblesses],
                      ["Points forts", sec.points_forts],
                      ["À confirmer", sec.inconnues],
                    ] as const
                  ).map(([t, xs]) =>
                    empty(xs) ? null : (
                      <div key={t} className="space-y-2">
                        <h4 className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">{t}</h4>
                        <ProseList items={xs!} onOpen={onOpen} />
                      </div>
                    ),
                  )}
                </div>
              )}
            </div>
          )}
          {a.stats.items_rejected > 0 && (
            <p className="text-xs text-muted-foreground">
              {a.stats.items_rejected} élément{a.stats.items_rejected > 1 ? "s" : ""} non publié{a.stats.items_rejected > 1 ? "s" : ""} faute de source suffisante.
            </p>
          )}
        </>
      )}
    </div>
  )
}
