import { HelpCircle } from "lucide-react"
import type { ReactNode } from "react"
import { SeverityBadge } from "@/components/app/badges"
import type { AlertItem } from "@/lib/api"
import { METRIC_SHORT, num, pct } from "@/lib/format"
import { cn } from "@/lib/utils"

// Formulations en clair des taux affichés : ce qui est mesuré, à quoi on le compare, et sur combien de commandes.
export const METRIC_PLAIN: Record<string, string> = {
  late: "de ses commandes livrées après la date annoncée",
  poor: "de ses commandes notées 1 ou 2 étoiles",
  handover: "de ses commandes remises au transporteur après la date limite",
}

/** Une alerte lisible : « 24,2 % de ses commandes livrées en retard, contre 7,9 % pour la marketplace — calculé sur 62 commandes ». */
export function AlertLine({ a, compact = false }: { a: AlertItem; compact?: boolean }) {
  const ref = a.family === "level" ? "pour l'ensemble de la marketplace" : "dans son propre passé (commandes d'il y a 3 à 12 mois)"
  return (
    <div className={cn("min-w-0 space-y-0.5", !compact && "py-0.5")}>
      <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
        <span className="font-semibold">{METRIC_SHORT[a.metric]}</span>
        <span className={cn("rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase", a.family === "level" ? "bg-burgundy-tint text-burgundy" : "bg-navy-tint text-navy-soft")}>
          {a.family === "level" ? "écart à la marketplace" : "dégradation récente"}
        </span>
        {a.severity && <SeverityBadge severity={a.severity} />}
      </p>
      <p className="text-sm leading-relaxed">
        <b className="tabular-nums text-burgundy">{pct(a.recent_rate)}</b> {METRIC_PLAIN[a.metric]}, contre <b className="tabular-nums">{pct(a.baseline)}</b> {ref}
      </p>
      <p className="text-[11px] text-muted-foreground">calculé sur {num(a.recent_known_n)} commandes des 90 derniers jours dont l'issue était connue</p>
    </div>
  )
}

/** Taux compact pour les tableaux : « 24,2 % » puis « sur 62 commandes ». */
export function RateWithBase({ rate, n, className }: { rate: number | null | undefined; n: number; className?: string }) {
  return (
    <span className={cn("inline-flex flex-col items-end leading-tight", className)} title={`Calculé sur ${n} commandes dont l'issue était connue`}>
      <span className="tabular-nums">{pct(rate)}</span>
      <span className="text-[10px] text-muted-foreground">sur {num(n)} commande{n > 1 ? "s" : ""}</span>
    </span>
  )
}

/** Panneau « Comment lire… » repliable, placé au-dessus des tableaux chiffrés. */
export function HowToRead({ title = "Comment lire ce tableau ?", items, open = false }: { title?: string; items: ReactNode[]; open?: boolean }) {
  return (
    <details open={open} className="group rounded-xl border bg-card px-4 py-3 text-sm">
      <summary className="flex cursor-pointer list-none items-center gap-2 font-semibold">
        <HelpCircle className="size-4" /> {title}
        <span className="ml-auto text-xs font-normal text-muted-foreground group-open:hidden">afficher</span>
      </summary>
      <ul className="mt-2.5 space-y-1.5 leading-relaxed text-muted-foreground">
        {items.map((t, i) => (
          <li key={i} className="flex gap-2">
            <span className="mt-2 size-1 shrink-0 rounded-full bg-muted-foreground" />
            <span>{t}</span>
          </li>
        ))}
      </ul>
    </details>
  )
}

export const RATE_HELP = [
  <>
    <b className="text-foreground">Le pourcentage</b> est la part des commandes du vendeur concernées par le problème (livraison en retard, avis 1-2 étoiles ou remise
    tardive au transporteur), sur ses achats des <b className="text-foreground">90 derniers jours</b>.
  </>,
  <>
    <b className="text-foreground">« sur N commandes »</b> indique sur combien de ses commandes ce pourcentage est calculé : seules celles dont l'issue était déjà connue à la
    fin du mois comptent. Plus N est petit, plus le pourcentage est fragile.
  </>,
  <>
    <b className="text-foreground">La référence</b> : pour une alerte « écart à la marketplace », le taux de l'ensemble des vendeurs sur 12 mois ; pour une alerte
    « dégradation récente », le propre passé du vendeur (ses commandes d'il y a 3 à 12 mois).
  </>,
  <>
    <b className="text-foreground">La priorité</b> : élevée = écart très net et déjà présent le mois précédent ; moyenne = écart net ou déjà signalé ; faible = autres alertes.
  </>,
]
