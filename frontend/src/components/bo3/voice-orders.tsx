import { useQuery } from "@tanstack/react-query"
import { Languages, MessageSquareQuote, Package, Sparkles } from "lucide-react"
import { useState } from "react"
import { openAssistant } from "@/components/assistant/assistant-widget"
import { OrderTimeline, ReviewCard } from "@/components/evidence/evidence-drawer"
import { SourcePills } from "@/components/evidence/source-pill"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { api } from "@/lib/api"
import { num, pct } from "@/lib/format"

export interface Voice {
  available: boolean
  n_written_reviews?: number
  share_rated_1_2?: number | null
  top_negative?: { aspect: string; label: string; negative: number }[]
  top_positive?: { aspect: string; label: string; positive: number }[]
  quotes?: { review_id: string; score: number; aspect: string; excerpt: string; machine_translated: boolean; excerpt_original?: string | null }[]
}
export interface Orders {
  orders_recent: number
  orders_with_known_problem: number
  shown: { order_id: string; purchase_date: string; customer_state: string; category: string; problems: string[]; late_days: number | null; review_score: number | null; handover_delay_days: number | null }[]
}

function AspectBars({ rows, value, color }: { rows: { label: string; n: number }[]; value: string; color: string }) {
  const max = Math.max(1, ...rows.map((r) => r.n))
  return (
    <ul className="space-y-2.5">
      {rows.map((r) => (
        <li key={r.label} className="group space-y-1" title={`${r.label} : ${r.n} avis`}>
          <div className="flex justify-between gap-2 text-sm">
            <span>{r.label}</span>
            <span className="tabular-nums text-muted-foreground">
              {num(r.n)} {value}
            </span>
          </div>
          <div className="h-2 rounded-full bg-muted">
            <div className="h-2 rounded-full transition-[filter] group-hover:brightness-110" style={{ width: `${(100 * r.n) / max}%`, background: color }} />
          </div>
        </li>
      ))}
    </ul>
  )
}

/** Onglet « Voix du client & commandes » : aspects critiqués (avis BO2), extraits d'avis, commandes problématiques récentes. */
/** Extrait d'avis en français : traduction locale à la demande (l'original reste consultable). */
function TranslatedReview({ q, tr }: { q: NonNullable<Voice["quotes"]>[number]; tr?: { excerpt: string; original: string | null } }) {
  const [orig, setOrig] = useState(false)
  const fr = q.machine_translated ? q.excerpt : tr?.excerpt
  const shown = fr && !orig ? { ...q, excerpt: fr, machine_translated: true } : { ...q, excerpt: q.machine_translated ? (q.excerpt_original ?? q.excerpt) : q.excerpt, machine_translated: false }
  return (
    <div className="space-y-1">
      <ReviewCard q={shown} />
      {fr && (
        <button onClick={() => setOrig((v) => !v)} className="inline-flex items-center gap-1 px-1 text-[11px] font-medium text-muted-foreground hover:text-foreground">
          <Languages className="size-3" /> {orig ? "Voir la traduction" : "Voir l'original en portugais"}
        </button>
      )}
    </div>
  )
}

export function VoiceAndOrders({ voice, orders, ids, onOpen, seller, month }: { voice?: Voice; orders?: Orders; ids: { voice: string; orders: string }; onOpen: (id: string) => void; seller: string; month: string }) {
  const needs = (voice?.quotes ?? []).some((q) => !q.machine_translated)
  const tr = useQuery({ queryKey: ["voice-fr", seller, month], queryFn: () => api.voiceTranslations(seller, month), enabled: needs && !!month, staleTime: Infinity })
  return (
    <div className="space-y-6">
      <Card>
        <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <CardTitle className="flex items-center gap-2 text-base">
              <MessageSquareQuote className="size-4" /> Ce que disent les clients
            </CardTitle>
            <CardDescription>
              {voice?.available && voice.n_written_reviews
                ? `${num(voice.n_written_reviews)} avis écrits sur les 12 derniers mois, dont ${pct(voice.share_rated_1_2)} notés 1 ou 2 étoiles.`
                : "Pas d'avis écrit exploitable sur la période."}
            </CardDescription>
            <SourcePills ids={[ids.voice]} onOpen={onOpen} className="mt-2" />
          </div>
          <Button variant="outline" size="sm" onClick={() => openAssistant("Que disent les avis clients ?")}>
            <Sparkles className="size-3.5" /> Analyser les avis
          </Button>
        </CardHeader>
        {voice?.available && (voice.top_negative?.length ?? 0) > 0 && (
          <CardContent className="grid gap-8 lg:grid-cols-5">
            <div className="space-y-6 lg:col-span-2">
              <div className="space-y-3">
                <h3 className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">Sujets les plus critiqués</h3>
                <AspectBars rows={(voice.top_negative ?? []).map((r) => ({ label: r.label, n: r.negative }))} value="avis" color="#7357B8" />
              </div>
              {(voice.top_positive?.length ?? 0) > 0 && (
                <div className="space-y-3">
                  <h3 className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">Sujets appréciés</h3>
                  <AspectBars rows={(voice.top_positive ?? []).map((r) => ({ label: r.label, n: r.positive }))} value="avis" color="#2F8F5B" />
                </div>
              )}
            </div>
            <div className="space-y-3 lg:col-span-3">
              <h3 className="flex items-center gap-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                Extraits d'avis
                {needs && tr.isFetching && <span className="animate-pulse font-normal normal-case">· traduction en français en cours…</span>}
              </h3>
              {needs && tr.data && !tr.data.available && (voice.quotes ?? []).some((q) => !q.machine_translated && !tr.data?.translations[q.review_id]) && (
                <p className="rounded-lg border bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
                  Certains extraits restent en portugais : le module de traduction locale n'est pas installé dans l'environnement de l'API
                  (requirements-translation.txt).
                </p>
              )}
              {(voice.quotes ?? []).length ? (
                <div className="grid gap-3 md:grid-cols-2">
                  {voice.quotes!.map((q) => (
                    <TranslatedReview key={q.review_id} q={q} tr={tr.data?.translations[q.review_id]} />
                  ))}
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">Aucun extrait disponible.</p>
              )}
            </div>
          </CardContent>
        )}
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Package className="size-4" /> Commandes récentes à examiner
          </CardTitle>
          <CardDescription>
            {orders
              ? `${num(orders.orders_with_known_problem)} commandes des 90 derniers jours (sur ${num(orders.orders_recent)}) avaient déjà un problème connu à la date du bilan.`
              : "—"}
          </CardDescription>
          <SourcePills ids={[ids.orders]} onOpen={onOpen} className="mt-2" />
        </CardHeader>
        <CardContent>
          {orders?.shown.length ? (
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {orders.shown.map((o) => (
                <OrderTimeline key={o.order_id} o={o} />
              ))}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">Aucune commande problématique connue sur la période.</p>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
