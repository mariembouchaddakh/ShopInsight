import { useQuery } from "@tanstack/react-query"
import { HelpCircle, Lightbulb, MapPin } from "lucide-react"
import { Link } from "react-router-dom"
import { EmptyBlock, ErrorBlock, LoadingBlock } from "@/components/app/states"
import { api, type StateAlert } from "@/lib/api"
import { catLabel } from "@/lib/categories"
import { num, pct, shortId } from "@/lib/format"

const times = (r: number | null) => (r == null ? "" : r >= 1.95 ? `environ ${Math.round(r)} fois plus` : `${r.toLocaleString("fr-FR", { maximumFractionDigits: 1 })} fois plus`)

/** Deux barres côte à côte : le vendeur (bordeaux) et les autres vendeurs vers le même État (ardoise). */
function Compare({ a, max }: { a: StateAlert; max: number }) {
  const rows: [string, number | null, string][] = [
    ["Ce vendeur", a.rate, "bg-burgundy"],
    ["Les autres vendeurs", a.reference_rate, "bg-[#94A3B8]"],
  ]
  return (
    <div className="space-y-1.5">
      {rows.map(([l, v, c]) => (
        <div key={l} className="grid grid-cols-[8.5rem_1fr_3.5rem] items-center gap-2 text-xs">
          <span className="text-muted-foreground">{l}</span>
          <div className="h-2 rounded-full bg-muted">
            <div className={`h-2 rounded-full ${c}`} style={{ width: `${(100 * (v ?? 0)) / max}%` }} />
          </div>
          <span className="text-right font-semibold tabular-nums">{pct(v)}</span>
        </div>
      ))}
    </div>
  )
}

/** Retards anormaux d'un vendeur vers UN État de destination, regroupés par État (signal descriptif). */
export function StateAlertsTab({ month }: { month?: string }) {
  const q = useQuery({ queryKey: ["state-alerts", month], queryFn: () => api.stateAlerts(month), enabled: !!month })
  if (q.isLoading) return <LoadingBlock rows={6} />
  if (q.isError) return <ErrorBlock error={q.error} />
  const d = q.data?.result
  if (!d) return null
  const groups = new Map<string, StateAlert[]>()
  for (const a of d.alerts) groups.set(a.state_name, [...(groups.get(a.state_name) ?? []), a])
  const states = [...groups.entries()].sort((x, y) => y[1].length - x[1].length)
  const max = Math.max(0.05, ...d.alerts.map((a) => a.rate ?? 0)) * 1.05
  const worst = [...d.alerts].sort((x, y) => (y.ratio ?? 0) - (x.ratio ?? 0))[0]

  return (
    <div className="space-y-5">
      {d.alerts.length > 0 && (
        <section className="rounded-2xl border border-butter-hover bg-butter/25 p-5">
          <h3 className="mb-2.5 flex items-center gap-2 font-display text-base font-bold">
            <Lightbulb className="size-4" /> Ce qu'il faut retenir
          </h3>
          <ul className="space-y-1.5 text-sm leading-relaxed">
            <li>
              <b>{num(d.n_sellers)} vendeurs</b> livrent un État précis bien plus souvent en retard que les autres vendeurs livrant ce même État.
            </li>
            <li>
              L'État le plus concerné est <b>{states[0][0]}</b> ({states[0][1].length} vendeur{states[0][1].length > 1 ? "s" : ""}) : c'est aussi la première destination des
              commandes, d'où sa présence répétée.
            </li>
            {worst && (
              <li>
                Écart le plus marqué : le vendeur <b className="font-mono">{shortId(worst.seller_id)}</b> vers {worst.state_name} ({pct(worst.rate)} de livraisons en retard,
                contre {pct(worst.reference_rate)} pour les autres vendeurs).
              </li>
            )}
          </ul>
        </section>
      )}

      <details className="rounded-xl border bg-card p-4 text-sm">
        <summary className="flex cursor-pointer items-center gap-2 font-semibold">
          <HelpCircle className="size-4" /> Comment lire cette liste ?
        </summary>
        <div className="mt-2 space-y-1.5 leading-relaxed text-muted-foreground">
          <p>
            Les délais de livraison dépendent beaucoup de la destination. Pour être juste, chaque vendeur est comparé <b>aux autres vendeurs qui livrent le même État</b>,
            sur les 12 derniers mois (livraisons dont l'issue était connue à la fin du mois).
          </p>
          <p>
            Un même État apparaît plusieurs fois lorsque plusieurs vendeurs y livrent mal : la liste est donc regroupée par État de destination. Un vendeur n'y figure que si
            l'écart est net (au moins 15 livraisons vers cet État, écart statistiquement solide, taux au moins 1,5 fois celui des autres vendeurs).
          </p>
          <p>Ce signal aide à cibler un problème de transporteur ou de destination plutôt que le vendeur dans son ensemble ; il n'a pas encore été vérifié sur des périodes passées.</p>
        </div>
      </details>

      {d.alerts.length === 0 ? (
        <EmptyBlock>Aucun retard anormal par État ce mois-ci.</EmptyBlock>
      ) : (
        <div className="space-y-4">
          {states.map(([state, rows]) => (
            <section key={state} className="rounded-2xl border bg-card">
              <header className="flex flex-wrap items-baseline justify-between gap-2 border-b px-5 py-3">
                <h3 className="flex items-center gap-2 font-display text-base font-bold">
                  <MapPin className="size-4 text-burgundy" /> Livraisons vers {state}
                </h3>
                <p className="text-xs text-muted-foreground">
                  {rows.length} vendeur{rows.length > 1 ? "s" : ""} concerné{rows.length > 1 ? "s" : ""}
                </p>
              </header>
              <ul className="divide-y">
                {rows.map((a) => (
                  <li key={a.seller_id} className="grid gap-3 px-5 py-3.5 md:grid-cols-[minmax(0,1fr)_minmax(0,22rem)] md:items-center">
                    <div className="min-w-0 space-y-0.5">
                      <p className="text-sm">
                        <Link to={`/bo3/sellers/${a.seller_id}?month=${d.decision_month}`} className="font-mono font-semibold text-ink hover:underline">
                          Vendeur {shortId(a.seller_id)}
                        </Link>{" "}
                        <span className="text-xs text-muted-foreground">· {catLabel(a.main_category)}</span>
                      </p>
                      <p className="text-sm leading-relaxed">
                        <b className="text-burgundy">{pct(a.rate)}</b> de ses livraisons vers {state} arrivent en retard ({num(a.late)} sur {num(a.known_n)}), soit{" "}
                        <b>{times(a.ratio)}</b> que les autres vendeurs.
                      </p>
                    </div>
                    <Compare a={a} max={max} />
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}
    </div>
  )
}
