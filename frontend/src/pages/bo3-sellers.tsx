import { keepPreviousData, useQuery } from "@tanstack/react-query"
import { RotateCcw, Search, X } from "lucide-react"
import { useState } from "react"
import { Link, useNavigate } from "react-router-dom"
import { Pill, SeverityBadge } from "@/components/app/badges"
import { useDecisionMonth } from "@/components/app/month"
import { PageHeader } from "@/components/app/shell"
import { EmptyBlock, ErrorBlock, LoadingBlock } from "@/components/app/states"
import { CountUp } from "@/components/brand/count-up"
import { HowToRead, RATE_HELP, RateWithBase } from "@/components/app/explain"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { api, type OverviewFilters, type SellerMetric, type Severity } from "@/lib/api"
import { METRICS, METRIC_SHORT, monthLabel, num, shortId } from "@/lib/format"
import { catLabel } from "@/lib/categories"
import { stateName } from "@/lib/geo"

function MetricCell({ m }: { m: SellerMetric | undefined }) {
  if (!m || m.known_n_90d === 0) return <span className="text-muted-foreground">—</span>
  return (
    <div className="flex flex-col items-end gap-1">
      <span className="tabular-nums">
        <RateWithBase rate={m.rate_90d} n={m.known_n_90d} />
      </span>
      <div className="flex gap-1">
        {m.alert_level && <SeverityBadge severity={m.severity} />}
        {m.alert_trend && <Pill tone="blue">en dégradation</Pill>}
        {m.strength && <Pill tone="green">point fort</Pill>}
      </div>
    </div>
  )
}

/** Liste déroulante native (accessible, compacte) pour la barre de filtres. */
function FilterSelect({ label, value, onChange, options }: { label: string; value: string; onChange: (v: string) => void; options: [string, string][] }) {
  return (
    <label className="flex min-w-0 flex-col gap-1 text-[11px] font-medium text-muted-foreground">
      {label}
      <select
        className="h-8 w-full min-w-0 rounded-md border border-input bg-background px-2 text-xs text-foreground"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        aria-label={label}
      >
        <option value="">Tous</option>
        {options.map(([v, l]) => (
          <option key={v} value={v}>
            {l}
          </option>
        ))}
      </select>
    </label>
  )
}

function Chip({ label, onClear }: { label: string; onClear: () => void }) {
  return (
    <span className="inline-flex h-6 items-center gap-1 rounded-full border bg-muted/60 pr-1 pl-2.5 text-xs">
      {label}
      <button onClick={onClear} className="rounded-full p-0.5 hover:bg-background" aria-label={`Retirer le filtre ${label}`}>
        <X className="size-3" />
      </button>
    </span>
  )
}

type Filters = Required<Pick<OverviewFilters, "seller_state" | "region" | "main_category" | "segment">> & {
  alert_status: "" | NonNullable<OverviewFilters["alert_status"]>
  severity: "" | Severity
  trend: "" | NonNullable<OverviewFilters["trend"]>
}
const FILTER_LABEL: Record<keyof Filters, string> = {
  seller_state: "Zone",
  region: "Région",
  main_category: "Métier",
  segment: "Segment",
  alert_status: "Alerte",
  severity: "Priorité",
  trend: "Tendance",
}
const EMPTY: Filters = { seller_state: "", region: "", main_category: "", segment: "", alert_status: "", severity: "", trend: "" }

export function SellersPage() {
  const [month] = useDecisionMonth()
  const [q, setQ] = useState("")
  const [f, setF] = useState<Filters>(EMPTY)
  const [limit, setLimit] = useState(100)
  const nav = useNavigate()
  const set = (k: keyof Filters) => (v: string) => {
    setF((x) => ({ ...x, [k]: v }))
    setLimit(100)
  }
  const ov = useQuery({
    queryKey: ["overview", month, q, f, limit],
    queryFn: () =>
      api.overview({
        month,
        q: q || undefined,
        limit,
        seller_state: f.seller_state || undefined,
        region: f.region || undefined,
        main_category: f.main_category || undefined,
        segment: f.segment || undefined,
        alert_status: f.alert_status || undefined,
        severity: f.severity || undefined,
        trend: f.trend || undefined,
      }),
    enabled: !!month,
    placeholderData: keepPreviousData,
  })
  const d = ov.data?.result
  const s = d?.summary
  const active = q !== "" || Object.values(f).some(Boolean)
  const opts = (xs: string[] | undefined): [string, string][] => (xs ?? []).map((x) => [x, x])
  const stateOpts = (xs: string[] | undefined): [string, string][] => (xs ?? []).map((x): [string, string] => [x, stateName(x)]).sort((a, b) => a[1].localeCompare(b[1], "fr"))

  return (
    <div>
      <PageHeader
        title="Vendeurs"
        description={
          <>
            Vendeurs actifs (au moins 5 commandes sur 12 mois) à fin {month ? monthLabel(month) : "…"} : taux des 90 derniers jours, alertes et priorités.
            Cliquez sur un vendeur pour ouvrir son bilan.
          </>
        }
      />

      {s && d && (
        <p className="mb-4 flex flex-wrap items-baseline gap-x-2 text-sm text-muted-foreground">
          <span className="font-display text-2xl font-bold text-foreground">
            <CountUp value={s.n_evaluated} format={(v) => num(Math.round(v))} />
          </span>
          vendeurs évalués ce mois-ci, dont <b className="text-forest">{num(s.n_with_strength)}</b> avec au moins un point fort sur 12 mois. Les alertes et leur priorité
          sont détaillées sur la page{" "}
          <Link to={`/bo3/alerts?month=${month ?? ""}`} className="font-semibold text-ink underline underline-offset-2">
            Alertes vendeurs
          </Link>
          .
        </p>
      )}

      <div className="sticky top-12 z-[5] mb-5 space-y-3 rounded-2xl border bg-background/95 p-3 shadow-sm backdrop-blur">
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 xl:grid-cols-[2fr_repeat(7,minmax(0,1fr))]">
          <label className="col-span-2 flex min-w-0 flex-col gap-1 text-[11px] font-medium text-muted-foreground sm:col-span-4 xl:col-span-1">
            Recherche
            <span className="relative">
              <Search className="absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={q}
                onChange={(e) => {
                  setQ(e.target.value)
                  setLimit(100)
                }}
                placeholder="Identifiant ou catégorie…"
                className="h-8 pl-8 text-xs"
                aria-label="Rechercher un vendeur"
              />
            </span>
          </label>
          <FilterSelect label="Zone (État)" value={f.seller_state} onChange={set("seller_state")} options={stateOpts(d?.facets.seller_state)} />
          <FilterSelect label="Région" value={f.region} onChange={set("region")} options={opts(d?.facets.segment_region)} />
          <FilterSelect label="Métier (catégorie)" value={f.main_category} onChange={set("main_category")} options={(d?.facets.main_category ?? []).map((x) => [x, catLabel(x)] as [string, string]).sort((a, b) => a[1].localeCompare(b[1], "fr"))} />
          <FilterSelect label="Segment" value={f.segment} onChange={set("segment")} options={opts(d?.facets.segment_volume)} />
          <FilterSelect
            label="Alerte"
            value={f.alert_status}
            onChange={set("alert_status")}
            options={[
              ["any", "En alerte"],
              ["level", "Écart à la marketplace"],
              ["trend", "Dégradation récente"],
              ["none", "Sans alerte"],
            ]}
          />
          <FilterSelect
            label="Priorité"
            value={f.severity}
            onChange={set("severity")}
            options={[
              ["élevée", "élevée"],
              ["moyenne", "moyenne"],
              ["faible", "faible"],
            ]}
          />
          <FilterSelect
            label="Tendance"
            value={f.trend}
            onChange={set("trend")}
            options={[
              ["degradation", "En dégradation"],
              ["stable", "Stable"],
            ]}
          />
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          {q && <Chip label={`« ${q} »`} onClear={() => setQ("")} />}
          {(Object.keys(f) as (keyof Filters)[])
            .filter((k) => f[k])
            .map((k) => (
              <Chip key={k} label={`${FILTER_LABEL[k]} : ${k === "main_category" ? catLabel(f[k]) : f[k]}`} onClear={() => set(k)("")} />
            ))}
          {active && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setF(EMPTY)
                setQ("")
              }}
            >
              <RotateCcw className="size-3.5" /> Tout effacer
            </Button>
          )}
          {d && (
            <span className="ml-auto text-xs text-muted-foreground">
              {num(d.n_matching)} vendeur{d.n_matching > 1 ? "s" : ""} sur {num(d.n_sellers)}
              {d.n_returned < d.n_matching ? ` · ${num(d.n_returned)} affichés` : ""}
            </span>
          )}
        </div>
      </div>

      <div className="mb-4">
        <HowToRead
          items={[
            ...RATE_HELP.slice(0, 2),
            <>
              <b className="text-foreground">Les badges</b> sous un taux : priorité de l'alerte (élevée, moyenne, faible), « en dégradation » si le vendeur fait moins bien
              que son propre passé, « point fort » s'il fait nettement mieux que la marketplace sur 12 mois.
            </>,
          ]}
        />
      </div>
      {ov.isError && <ErrorBlock error={ov.error} />}
      {ov.isLoading && <LoadingBlock rows={10} />}
      {d && d.sellers.length === 0 && <EmptyBlock>Aucun vendeur ne correspond à ces filtres.</EmptyBlock>}
      {d && d.sellers.length > 0 && (
        <div className="overflow-x-auto rounded-lg border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Vendeur</TableHead>
                <TableHead className="text-right">Commandes 12 mois</TableHead>
                <TableHead>Zone · segment</TableHead>
                {METRICS.map((k) => (
                  <TableHead key={k} className="text-right">
                    {METRIC_SHORT[k]}
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody className={ov.isFetching ? "opacity-60" : undefined}>
              {d.sellers.map((r) => (
                <TableRow
                  key={r.seller_id}
                  className="cursor-pointer transition-colors hover:bg-primary/[0.04]"
                  onClick={() => nav(`/bo3/sellers/${r.seller_id}?month=${month}`)}
                  tabIndex={0}
                  onKeyDown={(e) => e.key === "Enter" && nav(`/bo3/sellers/${r.seller_id}?month=${month}`)}
                >
                  <TableCell>
                    <div className="font-mono text-xs">{shortId(r.seller_id)}</div>
                    <div className="text-xs text-muted-foreground">{catLabel(r.main_category)}</div>
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{num(r.orders_12m)}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {stateName(r.seller_state)}
                    {r.segment_volume ? ` · ${r.segment_volume}` : ""}
                    {r.segment_region ? ` · ${r.segment_region}` : ""}
                  </TableCell>
                  {METRICS.map((k) => (
                    <TableCell key={k} className="text-right">
                      <MetricCell m={r.metrics[k]} />
                    </TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
      {d && d.n_returned < d.n_matching && (
        <div className="mt-4 flex justify-center">
          <Button variant="outline" size="sm" onClick={() => setLimit((l) => l + 200)}>
            Afficher plus
          </Button>
        </div>
      )}
    </div>
  )
}
