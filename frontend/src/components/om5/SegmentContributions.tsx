import { Layers, MapPin } from "lucide-react"
import type { ReactNode } from "react"
import { metricLabel, segmentBars, segmentMetrics, type SegmentBar } from "./model"
import type { Om5View } from "./types"
import { Panel } from "./ui"

function Bars({ title, icon, rows }: { title: string; icon: ReactNode; rows: SegmentBar[] }) {
  return (
    <div>
      <h3 className="mb-3 flex items-center gap-1.5 text-xs font-semibold text-ink [&>svg]:size-3.5 [&>svg]:text-navy-soft">{icon}{title}</h3>
      {!rows.length ? (
        <p className="text-xs text-muted-foreground">Aucun segment au-dessus du taux global avec un effectif suffisant.</p>
      ) : (
        <ul className="space-y-3">
          {rows.map((r) => (
            <li key={r.label} title={`${r.excess} · ${r.n.toLocaleString("fr-FR")} observations`}>
              <div className="flex items-baseline justify-between gap-2 text-xs">
                <span className="truncate font-medium text-ink">{r.label}</span>
                <span className="shrink-0 tabular-nums text-muted-foreground">{r.rate} · n = {r.n.toLocaleString("fr-FR")}</span>
              </div>
              <div className="mt-1 h-2 overflow-hidden rounded-full bg-muted" role="img" aria-label={`${r.label} : ${r.excess}`}>
                <div className="h-full rounded-full bg-burgundy/80" style={{ width: `${Math.max(r.share * 100, 4)}%` }} />
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export function SegmentContributions({ view }: { view: Om5View }) {
  const metrics = segmentMetrics(view)
  if (!metrics.length) {
    return (
      <Panel title="Contributions géographiques et par catégorie" icon={<Layers />}>
        <p className="text-sm text-muted-foreground">
          {view.detected.length ? "L'API n'a fourni aucune décomposition par segment pour ce mois." : "Aucune anomalie ce mois-ci : aucune décomposition par région ou par catégorie n'a été nécessaire."}
        </p>
      </Panel>
    )
  }
  return (
    <div className="space-y-4">
      {metrics.map((id) => (
        <Panel key={id} title={`Contributions — ${metricLabel(view, id)}`} icon={<Layers />}
          subtitle="Segments dont le taux dépasse le taux global du mois, classés par nombre de commandes en excès. Contributions descriptives : elles ne démontrent aucune causalité.">
          <div className="grid gap-6 md:grid-cols-2">
            <Bars title="Régions (États)" icon={<MapPin />} rows={segmentBars(view, id, "state")} />
            <Bars title="Catégories de produits" icon={<Layers />} rows={segmentBars(view, id, "category")} />
          </div>
        </Panel>
      ))}
    </div>
  )
}
