import { useQuery } from "@tanstack/react-query"
import { Check, ChevronDown, ClipboardCopy, Mail, MapPin, PhoneCall, Store } from "lucide-react"
import { useEffect, useState } from "react"
import { Link } from "react-router-dom"
import { SeverityBadge } from "@/components/app/badges"
import { useDecisionMonth } from "@/components/app/month"
import { PageHeader } from "@/components/app/shell"
import { EmptyBlock, ErrorBlock, LoadingBlock } from "@/components/app/states"
import { Button } from "@/components/ui/button"
import { api, type CallSeller } from "@/lib/api"
import { METRIC_SHORT, monthLabel, num, shortId } from "@/lib/format"
import { stateName } from "@/lib/geo"
import { cn } from "@/lib/utils"

// Suivi « contacté » : commodité propre à ce navigateur (aucune donnée métier), lue et écrite sans jamais bloquer la page.
const KEY = (month: string) => `shopinsight.calls.${month}`
function loadDone(month: string): string[] {
  try {
    return JSON.parse(localStorage.getItem(KEY(month)) ?? "[]")
  } catch {
    return []
  }
}
function saveDone(month: string, ids: string[]) {
  try {
    localStorage.setItem(KEY(month), JSON.stringify(ids))
  } catch {
    /* stockage indisponible : le suivi n'est simplement pas conservé */
  }
}

function copy(text: string) {
  navigator.clipboard?.writeText(text).catch(() => undefined)
}

function CallCard({ s, month, done, onToggle }: { s: CallSeller; month: string; done: boolean; onToggle: () => void }) {
  const [open, setOpen] = useState<"email" | "script" | null>(null)
  const [copied, setCopied] = useState(false)
  const mailto = `mailto:?subject=${encodeURIComponent(s.email.subject)}&body=${encodeURIComponent(s.email.body)}`
  return (
    <li className={cn("lift rounded-2xl border bg-card p-5 transition-opacity", done && "opacity-60")}>
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="flex min-w-0 gap-4">
          <span className={cn("flex size-10 shrink-0 items-center justify-center rounded-full font-display text-lg font-bold", done ? "bg-sage text-forest" : "bg-butter text-ink")}>
            {done ? <Check className="size-5" /> : s.rank}
          </span>
          <div className="min-w-0 space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <Link to={`/bo3/sellers/${s.seller_id}?month=${month}`} className="font-mono text-base font-semibold text-ink hover:underline">
                Vendeur {shortId(s.seller_id)}
              </Link>
              {s.top_severity ? <SeverityBadge severity={s.top_severity} /> : <span className="rounded-full bg-navy-tint px-2 py-0.5 text-[11px] font-medium text-navy-soft">signal par État</span>}
              {s.months_alerted_before > 0 && (
                <span className="rounded-full bg-burgundy-tint px-2 py-0.5 text-[11px] font-medium text-burgundy">
                  {s.months_alerted_before === 3 ? "en alerte depuis 3 mois" : `déjà en alerte ${s.months_alerted_before} mois sur 3`}
                </span>
              )}
            </div>
            <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
              <span className="inline-flex items-center gap-1">
                <Store className="size-3.5" /> {s.category_label}
              </span>
              <span className="inline-flex items-center gap-1">
                <MapPin className="size-3.5" /> {stateName(s.seller_state)}
              </span>
              {s.orders_12m != null && <span>{num(s.orders_12m)} commandes sur 12 mois</span>}
              <span>sujet principal : {METRIC_SHORT[s.main_metric].toLowerCase()}</span>
            </p>
            <ul className="space-y-1 text-sm leading-relaxed">
              {s.reasons.map((r) => (
                <li key={r} className="flex gap-2">
                  <span className="mt-2 size-1.5 shrink-0 rounded-full bg-burgundy" />
                  {r}
                </li>
              ))}
            </ul>
          </div>
        </div>
        <div className="flex shrink-0 flex-wrap gap-2 lg:flex-col lg:items-stretch">
          <Button onClick={() => setOpen(open === "script" ? null : "script")}>
            <PhoneCall className="size-4" /> Script d'appel
          </Button>
          <Button variant="outline" onClick={() => setOpen(open === "email" ? null : "email")}>
            <Mail className="size-4" /> E-mail
          </Button>
          <Button variant="outline" onClick={onToggle} aria-pressed={done}>
            <Check className="size-4" /> {done ? "Contacté" : "Marquer contacté"}
          </Button>
        </div>
      </div>

      {open === "script" && (
        <ol className="pop-in mt-5 space-y-3 border-t pt-5">
          {s.call_script.map((st, i) => (
            <li key={st.step} className="flex gap-3">
              <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-navy-tint text-xs font-semibold text-navy-soft">{i + 1}</span>
              <div>
                <p className="text-sm font-semibold">{st.step}</p>
                <p className="text-sm leading-relaxed text-muted-foreground">{st.text}</p>
              </div>
            </li>
          ))}
        </ol>
      )}
      {open === "email" && (
        <div className="pop-in mt-5 space-y-3 border-t pt-5">
          <p className="text-sm">
            <span className="text-muted-foreground">Objet : </span>
            <b>{s.email.subject}</b>
          </p>
          <pre className="rounded-xl bg-muted/60 p-4 font-sans text-sm leading-relaxed whitespace-pre-wrap">{s.email.body}</pre>
          <div className="flex flex-wrap gap-2">
            <a href={mailto}>
              <Button>
                <Mail className="size-4" /> Ouvrir dans la messagerie
              </Button>
            </a>
            <Button
              variant="outline"
              onClick={() => {
                copy(`${s.email.subject}\n\n${s.email.body}`)
                setCopied(true)
                setTimeout(() => setCopied(false), 1800)
              }}
            >
              <ClipboardCopy className="size-4" /> {copied ? "Copié !" : "Copier"}
            </Button>
          </div>
          <p className="text-[11px] text-muted-foreground">Les coordonnées des vendeurs ne figurent pas dans les données : ajoutez le destinataire dans votre messagerie.</p>
        </div>
      )}
    </li>
  )
}

/** Vendeurs à appeler cette semaine : liste priorisée (règle fixe), motifs chiffrés, e-mail et script d'appel prêts à l'emploi. */
export function CallsPage() {
  const [month] = useDecisionMonth()
  const q = useQuery({ queryKey: ["call-list", month], queryFn: () => api.callList(month), enabled: !!month })
  const d = q.data?.result
  const [done, setDone] = useState<string[]>([])
  const [rule, setRule] = useState(false)
  useEffect(() => {
    if (month) setDone(loadDone(month))
  }, [month])
  const toggle = (id: string) => {
    if (!month) return
    const next = done.includes(id) ? done.filter((x) => x !== id) : [...done, id]
    setDone(next)
    saveDone(month, next)
  }
  const n = d?.sellers.length ?? 0
  const k = d ? d.sellers.filter((s) => done.includes(s.seller_id)).length : 0

  return (
    <div className="space-y-6">
      <PageHeader
        title="À appeler cette semaine"
        description={
          <>
            Les vendeurs à contacter en priorité selon le bilan de fin {month ? monthLabel(month) : "…"} : pour chacun, le motif chiffré, un script d'appel et un e-mail
            prêts à l'emploi. Les chiffres viennent des alertes, des avis clients et des retards par État.
          </>
        }
      />
      {q.isLoading && <LoadingBlock rows={8} />}
      {q.isError && <ErrorBlock error={q.error} />}
      {d && n === 0 && <EmptyBlock>Aucun vendeur à contacter ce mois-ci.</EmptyBlock>}
      {d && n > 0 && (
        <>
          <div className="flex flex-col gap-3 rounded-2xl border bg-card p-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold">
                {k} sur {n} vendeurs contactés
              </p>
              <div className="mt-2 h-2 rounded-full bg-muted">
                <div className="h-2 rounded-full bg-forest-mark transition-all duration-500" style={{ width: `${(100 * k) / n}%` }} />
              </div>
            </div>
            <button onClick={() => setRule((v) => !v)} className="inline-flex items-center gap-1 text-xs font-medium text-muted-foreground hover:text-foreground">
              Comment la liste est-elle ordonnée ? <ChevronDown className={cn("size-3 transition", rule && "rotate-180")} />
            </button>
          </div>
          {rule && <p className="pop-in rounded-xl bg-navy-tint px-4 py-3 text-sm text-navy-soft">Ordre : {d.priority_rule}.</p>}
          <ul className="stagger space-y-3">
            {d.sellers.map((s) => (
              <CallCard key={s.seller_id} s={s} month={d.decision_month} done={done.includes(s.seller_id)} onToggle={() => toggle(s.seller_id)} />
            ))}
          </ul>
        </>
      )}
    </div>
  )
}
