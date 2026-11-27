import { useEffect, useRef, useState } from "react"
import { Bot, CalendarClock, MessageCircleQuestion, PackageSearch, RotateCcw, Send, ShieldCheck, Users } from "lucide-react"
import { Button } from "@/components/ui/button"

type Turn = { role: "user" | "assistant"; content: string }
const welcome = "Bonjour ! Indiquez votre numéro de commande et la date historique à laquelle vous souhaitez consulter son suivi. Comment puis-je vous aider ?"
// Commandes réelles du jeu Olist, pour essayer l'assistant sans chercher un identifiant
const EXAMPLES = [
  { label: "Commande vers le Maranhão, avril 2018", hint: "livrée 5 jours après la date promise", q: "Ma commande 891f571079436f35901706c6abe82ab0 au 20 avril 2018" },
  { label: "Commande vers le Ceará, juillet 2018", hint: "livrée en avance", q: "Ma commande f824b4829cd5241bb5e90df926d9434f au 20 juillet 2018" },
]
const FOLLOW_UPS = ["Quand arrivera ma commande ?", "Est-ce que d'autres clients ont eu du retard ?", "Pourquoi ce délai ?"]
const CAN_DO = [
  { icon: PackageSearch, text: "Dire où en est une commande à une date donnée" },
  { icon: CalendarClock, text: "Estimer une fenêtre de livraison réaliste" },
  { icon: Users, text: "Montrer ce qu'ont vécu des clients comparables" },
  { icon: ShieldCheck, text: "Ne rien inventer : pas de cause, pas de promesse de remboursement" },
]
export function Bo4Page() {
  const [turns, setTurns] = useState<Turn[]>([])
  const [draft, setDraft] = useState("")
  const [busy, setBusy] = useState(false)
  const [failed, setFailed] = useState<string | null>(null)
  const [limited, setLimited] = useState(false)
  const session = useRef(crypto.randomUUID())
  const lock = useRef(false)
  const scroll = useRef<HTMLDivElement>(null)
  useEffect(() => { scroll.current?.scrollTo({ top: scroll.current.scrollHeight, behavior: "smooth" }) }, [turns, busy, failed])
  async function send(text: string, retry = false) {
    const question = text.trim()
    if (!question || lock.current) return
    lock.current = true; setBusy(true); setDraft(""); setFailed(null)
    if (!retry) setTurns(old => [...old, { role: "user", content: question }])
    try {
      const response = await fetch("/api/bo4/conversation", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ session_id: session.current, question }) })
      if (!response.ok) throw new Error("request failed")
      const result = await response.json()
      setLimited(result.limited === true)
      setTurns(old => [...old, { role: "assistant", content: result.answer }])
    } catch { setFailed(question) }
    finally { lock.current = false; setBusy(false) }
  }
  const hasOrder = turns.some((x) => x.role === "user" && /[0-9a-f]{32}/i.test(x.content))
  return <div className="mx-auto grid max-w-6xl gap-5 lg:grid-cols-[minmax(0,1fr)_300px]">
  <section className="flex h-[calc(100svh-9rem)] min-h-[28rem] flex-col overflow-hidden rounded-2xl border bg-card shadow-sm">
    <header className="flex items-center justify-between border-b p-4"><div className="flex items-center gap-3"><span className="flex size-9 items-center justify-center rounded-xl bg-butter text-ink"><Bot className="size-5"/></span><div><h1 className="font-display text-lg font-semibold">Votre assistant commande</h1><p className="text-xs text-muted-foreground">Agent BO4 · suivi, délai estimé, expériences d'autres clients</p></div></div><Button variant="ghost" aria-label="Nouvelle conversation" disabled={busy} onClick={() => { session.current = crypto.randomUUID(); setTurns([]); setDraft(""); setFailed(null); setLimited(false) }}><RotateCcw className="size-4"/><span className="hidden sm:inline">Nouvelle conversation</span></Button></header>
    {limited && <p className="border-b bg-amber-tint px-4 py-2 text-xs text-amber-ink">Mode sans LLM : réponses construites directement à partir des données de commande.</p>}
    <div ref={scroll} role="log" aria-live="polite" className="flex-1 space-y-4 overflow-y-auto p-4 sm:p-6">
      <p className="max-w-[90%] rounded-2xl rounded-tl-sm bg-muted p-4 text-sm leading-relaxed">{welcome}</p>
      {!turns.length && <div className="space-y-2 pl-1">
        <p className="text-xs font-semibold text-muted-foreground">Pas de numéro sous la main ? Essayez avec une commande réelle :</p>
        {EXAMPLES.map(e => <button key={e.q} type="button" onClick={() => send(e.q)} className="lift flex w-full max-w-md items-center gap-3 rounded-xl border bg-background px-3 py-2.5 text-left text-sm hover:border-primary">
          <PackageSearch className="size-4 shrink-0 text-muted-foreground"/><span className="min-w-0"><span className="block font-medium">{e.label}</span><span className="block text-xs text-muted-foreground">{e.hint}</span></span></button>)}
      </div>}
      {turns.map((turn, i) => <div key={i} className={`flex ${turn.role === "user" ? "justify-end" : "justify-start"}`}><p className={`max-w-[90%] whitespace-pre-wrap rounded-2xl px-4 py-3 text-sm leading-relaxed ${turn.role === "user" ? "rounded-tr-sm bg-navy text-white" : "rounded-tl-sm bg-muted"}`}>{turn.content}</p></div>)}
      {busy && <p className="flex items-center gap-2 text-sm text-muted-foreground" role="status"><span className="flex gap-1"><span className="size-1.5 animate-bounce rounded-full bg-muted-foreground [animation-delay:-0.3s]"/><span className="size-1.5 animate-bounce rounded-full bg-muted-foreground [animation-delay:-0.15s]"/><span className="size-1.5 animate-bounce rounded-full bg-muted-foreground"/></span>L’assistant consulte les données…</p>}
      {failed && <div role="alert" className="text-sm text-burgundy">La connexion a échoué. <Button variant="outline" onClick={() => send(failed, true)}>Réessayer</Button></div>}
    </div>
    {hasOrder && !busy && <div className="flex flex-wrap gap-2 px-4">{FOLLOW_UPS.map(q => <Button key={q} variant="outline" size="sm" onClick={() => send(q)}><MessageCircleQuestion className="size-3.5"/>{q}</Button>)}</div>}
    <form className="p-4" onSubmit={event => { event.preventDefault(); void send(draft) }}><div className="flex items-end gap-2 rounded-xl border p-2 focus-within:ring-2 focus-within:ring-ring/20"><textarea aria-label="Votre message" placeholder={hasOrder ? "Posez une autre question sur cette commande…" : "Ex. : Ma commande 891f571079436f35901706c6abe82ab0 au 20 avril 2018"} rows={2} maxLength={2000} className="min-w-0 flex-1 resize-none bg-transparent p-2 text-sm outline-none" value={draft} onChange={event => setDraft(event.target.value)} onKeyDown={event => { if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); void send(draft) } }}/><Button aria-label="Envoyer" type="submit" size="icon" disabled={busy || !draft.trim()}><Send className="size-4"/></Button></div><p className="mt-1.5 px-1 text-[11px] text-muted-foreground">Entrée pour envoyer · Maj+Entrée pour aller à la ligne</p></form>
  </section>
  <aside className="hidden space-y-4 lg:block">
    <div className="rounded-2xl border bg-card p-4">
      <p className="mb-3 text-sm font-semibold">Ce que l'assistant sait faire</p>
      <ul className="space-y-3">{CAN_DO.map(({ icon: Icon, text }) => <li key={text} className="flex gap-2.5 text-sm"><Icon className="mt-0.5 size-4 shrink-0 text-muted-foreground"/><span>{text}</span></li>)}</ul>
    </div>
    <div className="rounded-2xl border bg-card p-4 text-sm">
      <p className="mb-1 font-semibold">Pourquoi une date ?</p>
      <p className="text-muted-foreground">Les données Olist s'arrêtent en 2018. On « se place » à une date passée pour voir ce que le client aurait su ce jour-là, sans rien connaître de la suite.</p>
    </div>
  </aside>
  </div>
}
