import { useQuery } from "@tanstack/react-query"
import { useState } from "react"
import { Link } from "react-router-dom"
import { Pill, SeverityBadge } from "@/components/app/badges"
import { useDecisionMonth } from "@/components/app/month"
import { PageHeader } from "@/components/app/shell"
import { EmptyBlock, ErrorBlock, LoadingBlock } from "@/components/app/states"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { api, type MetricKey } from "@/lib/api"
import { FAMILY_LABEL, METRICS, METRIC_SHORT, STATUS_LABEL, monthLabel, num, pct, shortId } from "@/lib/format"
import { catLabel } from "@/lib/categories"
import { StateAlertsTab } from "@/components/bo3/state-alerts"
import { AlertLine, HowToRead, RATE_HELP, RateWithBase } from "@/components/app/explain"

const selectCls = "h-8 rounded-md border border-input bg-background px-2 text-sm shadow-xs"

export function AlertsPage() {
  const [month] = useDecisionMonth()
  const [metric, setMetric] = useState<MetricKey | "">("")
  const [status, setStatus] = useState("")
  const [family, setFamily] = useState("")
  const list = useQuery({ queryKey: ["alerts", month, metric], queryFn: () => api.alerts({ month, metric: metric || undefined, top_k: 200 }), enabled: !!month })
  const hist = useQuery({
    queryKey: ["alert-history", month, metric, status, family],
    queryFn: () => api.alertHistory({ until: month, metric: metric || undefined, status: status || undefined, family: family || undefined, limit: 300 }),
    enabled: !!month,
  })

  return (
    <div>
      <PageHeader
        title="Alertes vendeurs"
        description={
          <>
            Décision fin {month ? monthLabel(month) : "…"}. Priorité élevée : écart très marqué et déjà présent le mois précédent ; moyenne : écart marqué ou déjà signalé ; faible : autres alertes. Une alerte signale un écart
            statistique à investiguer, pas une faute du vendeur.
          </>
        }
        actions={
          <select className={selectCls} value={metric} onChange={(e) => setMetric(e.target.value as MetricKey | "")} aria-label="Indicateur">
            <option value="">Tous les indicateurs</option>
            {METRICS.map((k) => (
              <option key={k} value={k}>
                {METRIC_SHORT[k]}
              </option>
            ))}
          </select>
        }
      />
      <Tabs defaultValue="current" className="min-w-0">
        <TabsList>
          <TabsTrigger value="current">Alertes du mois</TabsTrigger>
          <TabsTrigger value="history">Historique</TabsTrigger>
          <TabsTrigger value="states">Retards par État</TabsTrigger>
        </TabsList>
        <TabsContent value="current" className="mt-4 min-w-0">
          {list.isLoading && <LoadingBlock rows={8} />}
          {list.isError && <ErrorBlock error={list.error} />}
          {list.data && (
            <>
              <p className="mb-3 text-sm leading-relaxed text-muted-foreground">
                {num(list.data.result.n_alerted_sellers)} vendeurs en alerte ({num(list.data.result.n_alerts)} alertes), selon leur priorité la plus haute :{" "}
                {(["élevée", "moyenne", "faible"] as const).map((k) => (
                  <span key={k} className="mx-0.5 inline-flex items-center gap-1 align-middle">
                    <SeverityBadge severity={k} /> {num(list.data.result.listing.filter((x) => x.top_severity === k).length)}
                  </span>
                ))}
                {list.data.result.listing.some((x) => !x.top_severity) && (
                  <> · dégradation récente seule : {num(list.data.result.listing.filter((x) => !x.top_severity).length)}</>
                )}
                <br />
                Vendeurs évaluables (assez de commandes pour être jugés) :{" "}
                {Object.entries(list.data.result.eligible_sellers)
                  .map(([k, v]) => `${METRIC_SHORT[k as MetricKey].toLowerCase()} ${num(v)}`)
                  .join(" · ")}
              </p>
              <div className="mb-3">
                <HowToRead items={RATE_HELP} open />
              </div>
              {list.data.result.listing.length === 0 ? (
                <EmptyBlock>Aucun vendeur en alerte pour ce mois et cet indicateur.</EmptyBlock>
              ) : (
                <div className="overflow-x-auto rounded-lg border">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Vendeur</TableHead>
                        <TableHead>Priorité</TableHead>
                        <TableHead>Problèmes détectés : ce vendeur, comparé à la référence</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {list.data.result.listing.map((s) => (
                        <TableRow key={s.seller_id}>
                          <TableCell>
                            <Link to={`/bo3/sellers/${s.seller_id}?month=${month}`} className="font-mono text-xs underline-offset-2 hover:underline">
                              {shortId(s.seller_id)}
                            </Link>
                            <div className="text-xs text-muted-foreground">{catLabel(s.main_category)}</div>
                          </TableCell>
                          <TableCell>
                            <SeverityBadge severity={s.top_severity} />
                          </TableCell>
                          <TableCell>
                            <ul className="divide-y">
                              {s.alerts.map((a, i) => (
                                <li key={i} className="py-1.5 first:pt-0 last:pb-0">
                                  <AlertLine a={a} />
                                </li>
                              ))}
                            </ul>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}
            </>
          )}
        </TabsContent>
        <TabsContent value="history" className="mt-4 min-w-0 space-y-3">
          <div className="flex flex-wrap gap-2">
            <select className={selectCls} value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Statut">
              <option value="">Tous les statuts</option>
              <option value="new">nouvelle</option>
              <option value="ongoing">en cours</option>
              <option value="resolved">résolue</option>
            </select>
            <select className={selectCls} value={family} onChange={(e) => setFamily(e.target.value)} aria-label="Famille">
              <option value="">Niveau et tendance</option>
              <option value="level">écart à la marketplace</option>
              <option value="trend">tendance</option>
            </select>
            {hist.data && <span className="self-center text-xs text-muted-foreground">{num(hist.data.result.n_rows)} lignes jusqu'à {month}</span>}
          </div>
          {hist.isLoading && <LoadingBlock rows={8} />}
          {hist.isError && <ErrorBlock error={hist.error} />}
          {hist.data && (
            <div className="overflow-x-auto rounded-lg border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Mois</TableHead>
                    <TableHead>Vendeur</TableHead>
                    <TableHead>Indicateur</TableHead>
                    <TableHead>Famille</TableHead>
                    <TableHead>Statut</TableHead>
                    <TableHead>Sévérité</TableHead>
                    <TableHead className="text-right">Taux du vendeur (90 j)</TableHead>
                    <TableHead className="text-right">Comparé à (référence)</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {hist.data.result.rows.map((r, i) => (
                    <TableRow key={i}>
                      <TableCell className="tabular-nums">{r.month}</TableCell>
                      <TableCell>
                        <Link to={`/bo3/sellers/${r.seller_id}?month=${r.month}`} className="font-mono text-xs hover:underline">
                          {shortId(r.seller_id)}
                        </Link>
                      </TableCell>
                      <TableCell>{METRIC_SHORT[r.metric]}</TableCell>
                      <TableCell>{FAMILY_LABEL[r.family]}</TableCell>
                      <TableCell>
                        <Pill tone={r.status === "resolved" ? "green" : r.status === "new" ? "red" : "muted"}>{STATUS_LABEL[r.status]}</Pill>
                      </TableCell>
                      <TableCell>
                        <SeverityBadge severity={r.severity} />
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        <RateWithBase rate={r.recent_rate} n={r.recent_known_n} />
                      </TableCell>
                      <TableCell className="text-right tabular-nums">{pct(r.baseline)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </TabsContent>
        <TabsContent value="states" className="mt-4 min-w-0">
          <StateAlertsTab month={month} />
        </TabsContent>
      </Tabs>
    </div>
  )
}
