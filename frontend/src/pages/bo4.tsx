import { useEffect, useRef, useState } from "react"
import { Bot, Send, RotateCcw } from "lucide-react"
import { Button } from "@/components/ui/button"

type Turn = { role: "user" | "assistant"; content: string }
const welcome = "Bonjour ! Indiquez votre numéro de commande et la date historique à laquelle vous souhaitez consulter son suivi. Comment puis-je vous aider ?"
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
  return <section className="mx-auto flex h-[calc(100svh-9rem)] min-h-[28rem] max-w-3xl flex-col overflow-hidden rounded-2xl border bg-card shadow-sm">
    <header className="flex items-center justify-between border-b p-4"><div className="flex items-center gap-3"><Bot className="size-6"/><div><h1 className="font-display text-lg font-semibold">Votre assistant commande</h1><p className="text-xs text-muted-foreground">Un suivi clair, à votre écoute</p></div></div><Button variant="ghost" aria-label="Nouvelle conversation" disabled={busy} onClick={() => { session.current = crypto.randomUUID(); setTurns([]); setDraft(""); setFailed(null); setLimited(false) }}><RotateCcw className="size-4"/><span className="hidden sm:inline">Nouvelle conversation</span></Button></header>
    {limited && <p className="border-b bg-amber-tint px-4 py-2 text-xs text-amber-ink">Service temporairement limité : les informations de commande restent disponibles.</p>}
    <div ref={scroll} role="log" aria-live="polite" className="flex-1 space-y-4 overflow-y-auto p-4 sm:p-6">
      <p className="max-w-[90%] rounded-2xl rounded-tl-sm bg-muted p-4 text-sm leading-relaxed">{welcome}</p>
      {turns.map((turn, i) => <div key={i} className={`flex ${turn.role === "user" ? "justify-end" : "justify-start"}`}><p className={`max-w-[90%] whitespace-pre-wrap rounded-2xl px-4 py-3 text-sm leading-relaxed ${turn.role === "user" ? "rounded-tr-sm bg-navy text-white" : "rounded-tl-sm bg-muted"}`}>{turn.content}</p></div>)}
      {busy && <p className="animate-pulse text-sm text-muted-foreground" role="status">L’assistant prépare sa réponse…</p>}
      {failed && <div role="alert" className="text-sm text-burgundy">La connexion a échoué. <Button variant="outline" onClick={() => send(failed, true)}>Réessayer</Button></div>}
    </div>
    {!turns.length && <div className="flex flex-wrap gap-2 px-4"><Button variant="outline" onClick={() => send("Comment retrouver ma commande ?")}>Retrouver ma commande</Button><Button variant="outline" onClick={() => send("Quand vais-je recevoir ma commande ?")}>Comprendre mon délai</Button></div>}
    <form className="p-4" onSubmit={event => { event.preventDefault(); void send(draft) }}><div className="flex items-end gap-2 rounded-xl border p-2 focus-within:ring-2 focus-within:ring-ring/20"><textarea aria-label="Votre message" placeholder="Écrivez votre message…" rows={2} maxLength={2000} className="min-w-0 flex-1 resize-none bg-transparent p-2 text-sm outline-none" value={draft} onChange={event => setDraft(event.target.value)} onKeyDown={event => { if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); void send(draft) } }}/><Button aria-label="Envoyer" type="submit" size="icon" disabled={busy || !draft.trim()}><Send className="size-4"/></Button></div></form>
  </section>
}
