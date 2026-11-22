import { useMutation, useQuery } from "@tanstack/react-query"
import { ArrowUp, Globe2, Store, X } from "lucide-react"
import { Mascot } from "@/components/brand/logo"
import { useEffect, useMemo, useRef, useState } from "react"
import { matchPath, useLocation } from "react-router-dom"
import { useDecisionMonth } from "@/components/app/month"
import { aiErrorMessage, ProseItem, QuestionList } from "@/components/bo3/ai-items"
import { EvidenceDrawer } from "@/components/evidence/evidence-drawer"
import { Button } from "@/components/ui/button"
import { api, type AiChatAnswer, type AiItem, type AiQuestion, type Evidence } from "@/lib/api"
import { monthLabel, num } from "@/lib/format"
import { cn } from "@/lib/utils"

/** Ouvre l'assistant depuis n'importe quelle page, avec éventuellement une question à envoyer. */
export function openAssistant(question?: string) {
  window.dispatchEvent(new CustomEvent("shopinsight:assistant", { detail: { question } }))
}

export function useAiStatus() {
  return useQuery({ queryKey: ["ai-status"], queryFn: api.aiStatus, staleTime: 5 * 60_000 })
}

/** Créneau utilisé en interne (jamais affiché) : le modèle principal « a », sauf s'il n'est pas vérifié gratuit.
 * Le serveur bascule de toute façon sur les modèles gratuits de repli si le principal est limité. */
export function useAiSlot(): "a" | "b" {
  const st = useAiStatus().data
  return st && !st.models.a.free_verified && st.models.b.free_verified ? "b" : "a"
}

type Turn = { role: "user"; content: string } | { role: "assistant"; items: AiItem[]; questions: AiQuestion[]; follow: string[]; evidence: Evidence[]; notice?: string }

const SELLER_CHIPS = ["Pourquoi ce vendeur baisse-t-il ?", "Que disent les avis clients ?", "Comment rattraper ses concurrents ?"]
const MARKET_CHIPS = ["Quels vendeurs nécessitent une action urgente ce mois-ci ?", "Quelles catégories ont le plus de retards ?", "Quelles catégories concentrent le plus de vendeurs en alerte ?"]

function Avatar({ mood = "happy" }: { mood?: "happy" | "thinking" }) {
  return (
    <span className="brand-gradient flex size-8 shrink-0 items-center justify-center rounded-full shadow-sm ring-2 ring-background">
      <Mascot size={22} mood={mood} />
    </span>
  )
}

function TypingDots() {
  return (
    <div className="pop-in flex items-end gap-2" role="status">
      <Avatar mood="thinking" />
      <div className="flex items-center gap-2 rounded-2xl rounded-bl-md border bg-card px-3.5 py-2.5 text-sm text-muted-foreground">
        <span className="flex gap-1">
          {[0, 1, 2].map((i) => (
            <span key={i} className="size-1.5 animate-bounce rounded-full bg-primary/70" style={{ animationDelay: `${i * 120}ms` }} />
          ))}
        </span>
        Je croise les indicateurs, les avis et les commandes…
      </div>
    </div>
  )
}

const TEASER_KEY = "shopinsight.assistant.teaser"
function teaserSeen(): boolean {
  try {
    return sessionStorage.getItem(TEASER_KEY) === "1"
  } catch {
    return false
  }
}
function markTeaserSeen() {
  try {
    sessionStorage.setItem(TEASER_KEY, "1")
  } catch {
    /* stockage indisponible : la bulle réapparaîtra, sans gravité */
  }
}

/** Assistant flottant, présent sur toutes les pages : contexte « vendeur » sur une fiche d'audit (toutes ses sources sont jointes),
 * contexte « marketplace » ailleurs (alertes prioritaires et catégories du mois). Réponses contrôlées contre les sources. */
export function AssistantWidget() {
  const loc = useLocation()
  const match = matchPath("/bo3/sellers/:sellerId", loc.pathname)
  const seller = match?.params.sellerId
  const [month] = useDecisionMonth()
  const status = useAiStatus()
  const slot = useAiSlot()
  const [open, setOpen] = useState(false)
  const [unread, setUnread] = useState(0)
  const [convs, setConvs] = useState<Record<string, Turn[]>>({})
  const [input, setInput] = useState("")
  const [openId, setOpenId] = useState<string | null>(null)
  const key = seller ? `seller:${seller}:${month}` : `market:${month}`
  const turns = convs[key] ?? []
  const endRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  // Contexte joint automatiquement : audit complet du vendeur (même cache que la page) ou synthèse marketplace du mois.
  const audit = useQuery({ queryKey: ["audit", seller, month], queryFn: () => api.audit(seller!, month), enabled: !!seller && !!month })
  const brief = useQuery({ queryKey: ["brief", month], queryFn: () => api.brief(month), enabled: !seller && !!month && open })
  const alerts = ((audit.data?.report.meta as { alerts?: unknown[] } | undefined)?.alerts ?? []).length

  const chat = useMutation({
    mutationFn: ({ q, k }: { q: string; k: string }) => {
      const history = (convs[k] ?? []).map((t) => (t.role === "user" ? { role: t.role, content: t.content } : { role: t.role, content: t.items.map((i) => i.texte).join(" ") }))
      const body = { month, model: slot, question: q, history }
      return k.startsWith("seller:") ? api.aiChat(seller!, body) : api.marketChat(body)
    },
    onMutate: ({ q, k }) => setConvs((c) => ({ ...c, [k]: [...(c[k] ?? []), { role: "user", content: q }] })),
    onSuccess: (d: AiChatAnswer, { k }) => {
      setConvs((c) => ({
        ...c,
        [k]: [...(c[k] ?? []), { role: "assistant", items: d.items, questions: d.questions ?? [], follow: d.follow_up, evidence: d.evidence ?? [], notice: d.mode === "sans_ia" ? d.notice : undefined }],
      }))
      if (!open) setUnread((u) => u + 1)
    },
  })

  const send = (q: string) => {
    const t = q.trim()
    if (t.length < 3 || chat.isPending || !month) return
    chat.mutate({ q: t, k: key })
    setInput("")
  }

  useEffect(() => {
    const h = (e: Event) => {
      setOpen(true)
      setUnread(0)
      const q = (e as CustomEvent<{ question?: string }>).detail?.question
      if (q) setTimeout(() => send(q), 0)
    }
    window.addEventListener("shopinsight:assistant", h)
    return () => window.removeEventListener("shopinsight:assistant", h)
  })
  useEffect(() => {
    // Accolades indispensables : scrollIntoView renvoie une promesse dans les navigateurs récents, que React prendrait pour une fonction de nettoyage.
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" })
  }, [turns.length, chat.isPending, open])

  const evidence = useMemo(() => {
    const m = new Map<string, Evidence>()
    for (const e of audit.data?.evidence ?? []) m.set(e.id, e)
    for (const t of turns) if (t.role === "assistant") for (const e of t.evidence) m.set(e.id, e)
    return [...m.values()]
  }, [audit.data, turns])

  const usable = status.data?.usable
  const chips = seller ? SELLER_CHIPS : MARKET_CHIPS
  const lastFollow = [...turns].reverse().find((t) => t.role === "assistant") as Extract<Turn, { role: "assistant" }> | undefined
  const b = brief.data?.result
  const hint = seller && alerts > 0 && turns.length === 0
  const [teaser, setTeaser] = useState(false)
  // Bulle d'accroche : une fois par session, quelques secondes après l'arrivée, adaptée à la page ; disparaît seule.
  useEffect(() => {
    if (open || teaserSeen() || usable === false) return
    const show = setTimeout(() => setTeaser(true), 3500)
    const hide = setTimeout(() => {
      setTeaser(false)
      markTeaserSeen()
    }, 14000)
    return () => {
      clearTimeout(show)
      clearTimeout(hide)
    }
  }, [open, usable])
  const toggle = () => {
    setOpen((o) => !o)
    setUnread(0)
    setTeaser(false)
    markTeaserSeen()
  }

  return (
    <>
      {open && (
        <section
          className="pop-in fixed right-4 bottom-24 z-40 flex h-[min(680px,calc(100svh-8rem))] w-[min(440px,calc(100vw-2rem))] origin-bottom-right flex-col overflow-hidden rounded-3xl border bg-popover text-popover-foreground shadow-[0_30px_80px_-20px_rgb(19_34_56/45%)] sm:right-6"
          aria-label="Assistant ShopInsight"
        >
          <header className="brand-gradient relative flex items-start justify-between gap-3 px-4 py-4 text-white">
            <div className="flex min-w-0 items-center gap-3">
              <span className="flex size-11 shrink-0 items-center justify-center rounded-2xl bg-butter/15 ring-1 ring-butter/40 backdrop-blur">
                <Mascot size={32} mood={chat.isPending ? "thinking" : "happy"} />
              </span>
              <div className="min-w-0">
              <p className="font-display text-base leading-tight font-bold">Assistant ShopInsight</p>
              <p className="mt-0.5 flex items-center gap-1.5 truncate text-xs text-white/85">
                {seller ? <Store className="size-3 shrink-0" /> : <Globe2 className="size-3 shrink-0" />}
                {seller
                  ? `Vendeur ${seller.slice(0, 8)} · ${month ? monthLabel(month) : ""}${audit.data ? ` · ${audit.data.evidence.length} sources jointes` : " · chargement des sources…"}`
                  : `Marketplace · ${month ? monthLabel(month) : ""}${b ? ` · ${num(b.overview.summary.n_with_any_alert)} vendeurs en alerte` : ""}`}
              </p>
              </div>
            </div>
            <Button variant="ghost" size="icon-sm" className="text-white hover:bg-white/20 hover:text-white" onClick={() => setOpen(false)} aria-label="Fermer l'assistant">
              <X className="size-4" />
            </Button>
          </header>

          <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-4 py-4">
            {status.data && !usable ? (
              <p className="rounded-xl border border-dashed p-4 text-sm text-muted-foreground">
                L'assistant n'est pas disponible pour le moment. Les tableaux de bord, les alertes et les audits restent complets.
              </p>
            ) : (
              <>
                {turns.length === 0 && (
                  <div className="pop-in space-y-3 rounded-2xl border border-primary/15 bg-gradient-to-br from-primary/[0.07] to-transparent p-4 text-sm leading-relaxed">
                    <p className="font-display text-base font-semibold">Bonjour 👋</p>
                    <p className="text-muted-foreground">
                      {seller
                        ? "Je connais la performance de ce vendeur, ses alertes, son historique, ses concurrents directs, les avis de ses clients et ses commandes récentes. Que voulez-vous comprendre ?"
                        : "Je vous aide à prioriser le mois : vendeurs à traiter en urgence, catégories les plus touchées, tendances de la marketplace."}
                    </p>
                  </div>
                )}
                {turns.map((t, i) =>
                  t.role === "user" ? (
                    <div key={i} className="pop-in ml-auto w-fit max-w-[85%] rounded-2xl rounded-br-md bg-primary px-3.5 py-2 text-sm text-primary-foreground shadow-sm">
                      {t.content}
                    </div>
                  ) : (
                    <div key={i} className="pop-in space-y-3">
                      {t.notice && (
                        <p className="ml-10 rounded-lg bg-amber-tint px-2.5 py-1.5 text-[11px] leading-snug text-amber-ink">{t.notice}</p>
                      )}
                      {t.items.length ? (
                        <div className="flex items-start gap-2">
                          <Avatar />
                          <div className="min-w-0 flex-1 space-y-3 rounded-2xl rounded-tl-md border bg-card p-3.5 shadow-sm">
                            {t.items.map((it, j) => (
                              <ProseItem key={j} it={it} onOpen={setOpenId} />
                            ))}
                          </div>
                        </div>
                      ) : (
                        <p className="rounded-2xl border bg-card p-3.5 text-sm text-muted-foreground">
                          Je n'ai pas trouvé d'élément suffisamment étayé par les données pour répondre. Pouvez-vous reformuler ou préciser la question ?
                        </p>
                      )}
                      {t.questions.length > 0 && (
                        <div className="space-y-2">
                          <p className="text-xs font-medium text-muted-foreground">Pour aller plus loin, pouvez-vous me préciser :</p>
                          <QuestionList
                            questions={t.questions}
                            onOpen={setOpenId}
                            onPick={(q) => {
                              setInput(`À propos de « ${q} » : `)
                              inputRef.current?.focus()
                            }}
                          />
                        </div>
                      )}
                    </div>
                  ),
                )}
                {chat.isPending && <TypingDots />}
                {chat.isError && <p className="rounded-xl border border-destructive/30 bg-destructive/5 p-3 text-sm">{aiErrorMessage(chat.error)}</p>}
                <div ref={endRef} />
              </>
            )}
          </div>

          {usable !== false && (
            <footer className="space-y-2 border-t px-3 py-3">
              <div className="flex gap-1.5 overflow-x-auto pb-1">
                {(lastFollow?.follow.length ? lastFollow.follow : chips).map((q) => (
                  <button
                    key={q}
                    onClick={() => send(q)}
                    disabled={chat.isPending}
                    className="shrink-0 rounded-full border bg-background px-3 py-1 text-xs transition hover:bg-muted disabled:opacity-50"
                  >
                    {q}
                  </button>
                ))}
              </div>
              <form
                className="flex items-end gap-2"
                onSubmit={(e) => {
                  e.preventDefault()
                  send(input)
                }}
              >
                <textarea
                  ref={inputRef}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault()
                      send(input)
                    }
                  }}
                  rows={1}
                  maxLength={600}
                  placeholder={seller ? "Posez une question sur ce vendeur…" : "Posez une question sur la marketplace…"}
                  aria-label="Votre question"
                  className="max-h-28 min-h-9 flex-1 resize-none rounded-xl border border-input bg-background px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
                />
                <Button type="submit" size="icon" className="rounded-xl" disabled={chat.isPending || input.trim().length < 3} aria-label="Envoyer">
                  <ArrowUp className="size-4" />
                </Button>
              </form>
            </footer>
          )}
        </section>
      )}

      {teaser && !open && (
        <div className="pop-in fixed right-4 bottom-24 z-40 w-[min(300px,calc(100vw-2rem))] origin-bottom-right sm:right-6" role="status">
          <div className="relative rounded-2xl rounded-br-md border bg-popover p-3.5 pr-8 text-sm leading-relaxed shadow-xl">
            <button
              onClick={() => {
                setTeaser(false)
                markTeaserSeen()
              }}
              className="absolute top-2 right-2 rounded-full p-1 text-muted-foreground hover:bg-muted"
              aria-label="Masquer"
            >
              <X className="size-3" />
            </button>
            <p className="font-display font-semibold">Besoin d'un coup de main ?</p>
            <p className="mt-0.5 text-muted-foreground">
              {seller
                ? alerts > 0
                  ? "Ce vendeur est en alerte : je peux vous expliquer pourquoi, en croisant ses commandes et ses avis."
                  : "Je connais ses avis clients, ses concurrents et son historique. Posez-moi une question !"
                : "Je peux vous dire quels vendeurs traiter en priorité ce mois-ci."}
            </p>
            <button onClick={toggle} className="mt-2 text-xs font-semibold text-ink underline decoration-butter-hover decoration-2 underline-offset-2 hover:decoration-ink">
              Discuter avec l'assistant →
            </button>
          </div>
        </div>
      )}

      <button
        onClick={toggle}
        className={cn(
          "si-launcher group fixed right-4 bottom-6 z-40 flex h-14 items-center rounded-full text-white transition-all duration-500 ease-[cubic-bezier(0.2,0.8,0.2,1)] sm:right-6",
          open ? "w-14 justify-center bg-[var(--brand-ink)]" : "brand-gradient w-14 justify-start pl-[11px] hover:w-[11.5rem] hover:-translate-y-0.5",
        )}
        aria-label={open ? "Fermer l'assistant" : "Ouvrir l'assistant"}
      >
        {open ? (
          <X className="size-5 transition-transform duration-500 group-hover:rotate-90" />
        ) : (
          <>
            <Mascot size={34} className="shrink-0 drop-shadow-sm" />
            <span className="ml-2 overflow-hidden text-sm font-semibold whitespace-nowrap opacity-0 transition-opacity duration-300 group-hover:opacity-100">
              Une question ?
            </span>
          </>
        )}
        {!open && (unread > 0 || hint) && (
          <span className="si-badge absolute -top-1 -right-1 flex size-5 items-center justify-center rounded-full bg-burgundy text-[10px] font-bold text-white ring-2 ring-background">
            {unread > 0 ? unread : "!"}
          </span>
        )}
      </button>
      <EvidenceDrawer evidence={evidence} openId={openId} onClose={() => setOpenId(null)} />
    </>
  )
}
