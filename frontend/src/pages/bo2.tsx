import { useQuery } from "@tanstack/react-query"
import { BadgeCheck, Bell, MessageSquareText, ThumbsDown } from "lucide-react"
import { useState } from "react"
import { Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, ResponsiveContainer, Tooltip as RTooltip, XAxis, YAxis } from "recharts"
import { useDecisionMonth } from "@/components/app/month"
import { ReportView } from "@/components/app/report-view"
import { PageHeader } from "@/components/app/shell"
import { ErrorBlock, LoadingBlock } from "@/components/app/states"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { api } from "@/lib/api"
import { catLabel, categoryOptions } from "@/lib/categories"
import { CHART, monthLabel, num, pct } from "@/lib/format"
import { UF_NAMES, stateName } from "@/lib/geo"

const tick = { fontSize: 11, fill: CHART.tick }
// 4 séries maximum, couleurs de la charte (validées daltonisme dans lib/format)
const TREND_COLORS = ["#2F6BB0", "#A8325A", "#B08418", "#2F8F5B"]
const NEG = "#A8325A"
const POS = "#2F8F5B"

function Kpi({ icon: Icon, label, value, hint }: { icon: typeof Bell; label: string; value: string; hint: string }) {
  return (
    <Card size="sm" className="lift">
      <CardHeader>
        <CardDescription className="flex items-center gap-2">
          <Icon className="size-3.5" /> {label}
        </CardDescription>
        <CardTitle>
          <span className="font-display text-3xl font-bold tracking-tight">{value}</span>
        </CardTitle>
      </CardHeader>
      <CardContent className="text-xs text-muted-foreground">{hint}</CardContent>
    </Card>
  )
}

/** BO2 : voix du client. Graphiques (aspects, comparaison à la référence, évolution) puis rapport détaillé de l'agent avec extraits d'avis. */
export function Bo2Page() {
  const [month] = useDecisionMonth()
  const [state, setState] = useState("")
  const [category, setCategory] = useState("")
  const [applied, setApplied] = useState<{ state?: string; category?: string }>({})
  const ov = useQuery({ queryKey: ["bo2-overview", month, applied], queryFn: () => api.bo2Overview({ month, ...applied }), enabled: !!month })
  const rep = useQuery({ queryKey: ["bo2", month, applied], queryFn: () => api.bo2Report({ month, ...applied }), enabled: !!month })
  const d = ov.data
  const filtered = !!(applied.state || applied.category)
  const scope = [applied.state ? stateName(applied.state) : null, applied.category ? catLabel(applied.category) : null].filter(Boolean).join(" · ")

  // aspects affichés dans l'évolution : les 4 plus critiqués ce mois-ci (hors satisfaction globale)
  const topAspects = d
    ? [...d.aspects].filter((a) => a.aspect !== "satisfaction_globale").sort((x, y) => (y.negative_share ?? 0) - (x.negative_share ?? 0)).slice(0, 4).map((a) => a.aspect)
    : []
  const profile = d ? [...d.aspects].sort((x, y) => y.negative + y.positive - (x.negative + x.positive)).map((a) => ({ ...a, negative_neg: -a.negative })) : []
  const f1 = d?.validation

  return (
    <div className="space-y-5">
      <PageHeader
        title="Voix du client"
        description="L'agent BO2 lit les avis écrits (en portugais, avec leur traduction automatique), repère les aspects critiqués ou appréciés et signale les plaintes qui augmentent anormalement par rapport aux 12 mois précédents."
      />
      <form
        className="flex flex-wrap items-center gap-2"
        onSubmit={(e) => {
          e.preventDefault()
          setApplied({ state: state || undefined, category: category.trim() || undefined })
        }}
      >
        <span className="text-sm text-muted-foreground">Mois d'achat {month ? monthLabel(month) : "…"}</span>
        <select value={state} onChange={(e) => setState(e.target.value)} className="h-9 w-52 rounded-md border border-input bg-background px-2 text-sm" aria-label="État du client">
          <option value="">Tous les États</option>
          {Object.entries(UF_NAMES)
            .sort((x, y) => x[1].localeCompare(y[1], "fr"))
            .map(([uf, name]) => (
              <option key={uf} value={uf}>
                {name}
              </option>
            ))}
        </select>
        <select value={category} onChange={(e) => setCategory(e.target.value)} className="h-9 w-64 rounded-md border border-input bg-background px-2 text-sm" aria-label="Catégorie de produit">
          <option value="">Toutes les catégories</option>
          {categoryOptions().map(([slug, name]) => (
            <option key={slug} value={slug}>
              {name}
            </option>
          ))}
        </select>
        <Button type="submit" variant="outline">
          Appliquer
        </Button>
      </form>

      {ov.isLoading && <LoadingBlock rows={8} />}
      {ov.isError && <ErrorBlock error={ov.error} />}
      {d && (
        <>
          <div className="stagger grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Kpi icon={MessageSquareText} label="Avis écrits" value={num(d.n_reviews)} hint={`commandes de ${monthLabel(d.month)}${scope ? ` · ${scope}` : ""}`} />
            <Kpi icon={ThumbsDown} label="Notés 1 ou 2 étoiles" value={pct(d.share_rated_1_2)} hint="parmi les avis écrits (les mécontents écrivent plus souvent)" />
            <Kpi
              icon={Bell}
              label="Plaintes en hausse"
              value={String(d.alerts.length)}
              hint={d.alerts.length ? d.alerts.join(" · ") : "aucune hausse anormale par rapport aux 12 mois précédents"}
            />
            <Kpi
              icon={BadgeCheck}
              label="Fiabilité de la détection"
              value={f1 ? `F1 ${f1.macro_f1_detection.toLocaleString("fr-FR")}` : "—"}
              hint={f1 ? `moyenne des 9 aspects, mesurée sur 500 avis annotés (provisoire) ; objectif ${f1.target_f1.toLocaleString("fr-FR")}` : "pas encore évaluée"}
            />
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle className="text-sm">Ce mois-ci comparé aux 12 mois précédents</CardTitle>
                <CardDescription>Part des avis écrits qui critiquent chaque aspect (toute la marketplace). En bordeaux : hausse jugée anormale par le test statistique.</CardDescription>
              </CardHeader>
              <CardContent className="h-72">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={d.vs_baseline} layout="vertical" margin={{ left: 10, right: 8 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke={CHART.grid} horizontal={false} />
                    <XAxis type="number" tick={tick} tickFormatter={(v) => `${Math.round(v * 100)} %`} />
                    <YAxis type="category" dataKey="label" tick={tick} width={175} interval={0} />
                    <RTooltip formatter={(v) => pct(v as number)} contentStyle={{ fontSize: 12 }} />
                    <Legend wrapperStyle={{ fontSize: 11 }} />
                    <Bar dataKey="baseline_rate" name="référence (médiane 12 mois)" fill={CHART.reference} isAnimationActive={false} radius={[0, 4, 4, 0]} />
                    <Bar dataKey="rate" name={monthLabel(d.month)} isAnimationActive={false} radius={[0, 4, 4, 0]} fill="#2F6BB0">
                      {d.vs_baseline.map((r) => (
                        <Cell key={r.aspect} fill={r.alert ? CHART.alert : "#2F6BB0"} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle className="text-sm">Évolution des principales critiques</CardTitle>
                <CardDescription>Part des avis écrits qui critiquent l'aspect, mois par mois{filtered ? ` (${scope})` : ""}.</CardDescription>
              </CardHeader>
              <CardContent className="h-72">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={d.trend} margin={{ left: -10, right: 8 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke={CHART.grid} vertical={false} />
                    <XAxis dataKey="month" tick={tick} tickFormatter={(m) => String(m).slice(2)} />
                    <YAxis tick={tick} tickFormatter={(v) => `${Math.round(v * 100)} %`} width={48} />
                    <RTooltip formatter={(v) => pct(v as number)} labelFormatter={(m) => monthLabel(String(m))} contentStyle={{ fontSize: 12 }} />
                    <Legend wrapperStyle={{ fontSize: 11 }} />
                    {topAspects.map((a, i) => (
                      <Line key={a} type="linear" dataKey={a} name={d.labels[a]} stroke={TREND_COLORS[i]} strokeWidth={2} dot={{ r: 2 }} isAnimationActive={false} />
                    ))}
                  </LineChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader>
              <CardTitle className="text-sm">De quoi parlent les clients</CardTitle>
              <CardDescription>Nombre d'avis qui critiquent (à gauche) ou apprécient (à droite) chaque aspect ce mois-ci, avec la fiabilité mesurée de la détection.</CardDescription>
            </CardHeader>
            <CardContent className="grid gap-4 lg:grid-cols-[1fr_260px]">
              <div className="h-80">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={profile} layout="vertical" stackOffset="sign" margin={{ left: 10, right: 8 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke={CHART.grid} horizontal={false} />
                    <XAxis type="number" tick={tick} tickFormatter={(v) => num(Math.abs(v))} />
                    <YAxis type="category" dataKey="label" tick={tick} width={175} interval={0} />
                    <RTooltip formatter={(v, n) => [num(Math.abs(v as number)), n]} contentStyle={{ fontSize: 12 }} />
                    <Legend wrapperStyle={{ fontSize: 11 }} />
                    <Bar dataKey="negative_neg" name="critiques" stackId="s" fill={NEG} isAnimationActive={false} />
                    <Bar dataKey="positive" name="appréciations" stackId="s" fill={POS} isAnimationActive={false} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <div className="rounded-xl border p-3 text-sm">
                <p className="mb-2 font-semibold">F1 de détection par aspect</p>
                {f1 ? (
                  <ul className="space-y-1.5">
                    {profile.map((a) => {
                      const v = f1.per_aspect[a.aspect]?.f1_detection
                      return (
                        <li key={a.aspect} className="flex items-center justify-between gap-2">
                          <span className="truncate text-muted-foreground">{a.label}</span>
                          <span className={v !== undefined && v >= f1.target_f1 ? "font-semibold text-forest-mark tabular-nums" : "tabular-nums"}>{v?.toLocaleString("fr-FR", { minimumFractionDigits: 2 }) ?? "—"}</span>
                        </li>
                      )
                    })}
                  </ul>
                ) : (
                  <p className="text-muted-foreground">Pas encore évaluée.</p>
                )}
                {f1 && (
                  <p className="mt-3 text-xs leading-snug text-muted-foreground">
                    Référence : 500 avis annotés à l'aveugle par un LLM ; accord avec deux annotatrices humaines κ ≈ {f1.human_check.kappa_llm_vs_annotator_b.toLocaleString("fr-FR")} sur {f1.human_check.n_reviews} avis (entre humaines : {f1.human_check.kappa_between_humans.toLocaleString("fr-FR")}). Résultat provisoire.
                  </p>
                )}
              </div>
            </CardContent>
          </Card>
        </>
      )}

      <section className="space-y-3 pt-2">
        <h2 className="text-lg font-semibold">Rapport détaillé de l'agent</h2>
        <p className="text-sm text-muted-foreground">Synthèse, chiffres sourcés et extraits d'avis ; chaque extrait indique sa langue (traduction automatique ou portugais original).</p>
        {rep.isLoading && <LoadingBlock rows={6} />}
        {rep.isError && <ErrorBlock error={rep.error} />}
        {rep.data && <ReportView report={rep.data.report} evidence={rep.data.evidence} showTitle={false} />}
      </section>
    </div>
  )
}
