import { HelpCircle, Target } from "lucide-react"
import { SourcePills } from "@/components/evidence/source-pill"
import { ApiError, type AiAction, type AiItem, type AiKind, type AiQuestion } from "@/lib/api"
import { cn } from "@/lib/utils"

// Nature d'un élément, signalée discrètement en tête de phrase (les constats n'ont pas d'étiquette).
const LEAD: Record<AiKind, [string, string] | null> = {
  fait: null,
  hypothese: ["Lecture possible", "text-amber-ink"],
  inconnu: ["À confirmer", "text-muted-foreground"],
  piste: ["Piste", "text-navy-soft"],
}
export const PRIORITY: Record<string, string> = {
  haute: "bg-burgundy-tint text-burgundy",
  moyenne: "bg-amber-tint text-amber-ink",
  basse: "bg-muted text-muted-foreground",
}
export const LEVER_LABEL: Record<string, string> = {
  operationnel: "Opérations",
  catalogue_prix: "Catalogue et prix",
  delai_promis: "Délai annoncé",
  experience_client: "Expérience client",
}

/** Paragraphe d'analyse : texte en prose, nature discrète en tête, sources lisibles à la suite. */
export function ProseItem({ it, onOpen, className }: { it: AiItem; onOpen: (id: string) => void; className?: string }) {
  const lead = LEAD[it.type]
  return (
    <div className={cn("space-y-1.5", className)}>
      <p className="text-sm leading-relaxed [overflow-wrap:anywhere]">
        {lead && <span className={cn("mr-1.5 text-[11px] font-semibold tracking-wide uppercase", lead[1])}>{lead[0]} ·</span>}
        {it.texte}
      </p>
      <SourcePills ids={it.preuves} onOpen={onOpen} />
    </div>
  )
}

export function ProseList({ items, onOpen }: { items: AiItem[]; onOpen: (id: string) => void }) {
  return (
    <div className="space-y-3">
      {items.map((it, i) => (
        <ProseItem key={i} it={it} onOpen={onOpen} />
      ))}
    </div>
  )
}

export function ActionCard({ ac, onOpen }: { ac: AiAction; onOpen: (id: string) => void }) {
  return (
    <li className="space-y-2 rounded-xl border bg-card p-4">
      <div className="flex flex-wrap items-center gap-1.5">
        <span className={cn("rounded-full px-2 py-0.5 text-[10px] font-semibold tracking-wide uppercase", PRIORITY[ac.priorite])}>priorité {ac.priorite}</span>
        {ac.levier && <span className="rounded-full bg-navy-tint px-2 py-0.5 text-[10px] font-semibold tracking-wide text-navy-soft uppercase">{LEVER_LABEL[ac.levier]}</span>}
      </div>
      <p className="text-sm leading-relaxed font-medium [overflow-wrap:anywhere]">{ac.action}</p>
      <div className="space-y-1 text-xs text-muted-foreground [overflow-wrap:anywhere]">
        {ac.faiblesse && <p>Point de départ : {ac.faiblesse}</p>}
        {ac.cible && (
          <p className="inline-flex items-center gap-1 text-foreground">
            <Target className="size-3" /> Objectif : {ac.cible}
          </p>
        )}
        {ac.impact && <p>Effet attendu : {ac.impact}</p>}
      </div>
      <SourcePills ids={ac.preuves} onOpen={onOpen} />
    </li>
  )
}

/** Questions d'investigation adressées à l'utilisateur (ce que les données ne permettent pas de trancher). */
export function QuestionList({ questions, onOpen, onPick }: { questions: AiQuestion[]; onOpen: (id: string) => void; onPick?: (q: string) => void }) {
  if (!questions.length) return null
  return (
    <ul className="space-y-2">
      {questions.map((q, i) => (
        <li key={i} className="flex gap-2.5 rounded-xl border border-dashed p-3">
          <HelpCircle className="mt-0.5 size-4 shrink-0 text-plum" />
          <div className="min-w-0 space-y-1.5">
            <p className="text-sm leading-relaxed [overflow-wrap:anywhere]">{q.texte}</p>
            <div className="flex flex-wrap items-center gap-1">
              <SourcePills ids={q.preuves} onOpen={onOpen} />
              {onPick && (
                <button className="text-[11px] font-medium text-plum hover:underline" onClick={() => onPick(q.texte)}>
                  Répondre à l'assistant
                </button>
              )}
            </div>
          </div>
        </li>
      ))}
    </ul>
  )
}

/** Message d'erreur produit (sans détail technique) pour l'analyse et l'assistant. */
export function aiErrorMessage(error: unknown): string {
  const s = error instanceof ApiError ? error.status : undefined
  if (s === 429 && error instanceof Error && error.message.includes("quota_exhausted"))
    return "Le quota quotidien de l'assistant est atteint ; il sera rétabli demain. Les tableaux de bord et l'audit restent complets."
  if (s === 429) return "L'assistant est très sollicité en ce moment : réessayez dans une minute."
  if (s === 404) return "Ce vendeur n'a pas de données pour ce mois."
  if (s === 503 || s === 409 || s === 502) return "L'analyse stratégique est momentanément indisponible. Les tableaux de bord et l'audit restent complets."
  return "La réponse n'a pas pu être préparée. Vérifiez la connexion à l'API puis réessayez."
}
