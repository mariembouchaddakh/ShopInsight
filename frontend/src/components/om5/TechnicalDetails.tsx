import { Wrench } from "lucide-react"
import { cn } from "@/lib/utils"
import type { Om5Trace, Om5View } from "./types"
import { Disclosure } from "./ui"

type Row = Om5Trace & { args?: Record<string, unknown> }
const yn = (b: boolean) => (b ? "oui" : "non")

function KV({ k, v }: { k: string; v: string }) {
  return <div className="min-w-0 rounded-lg bg-card px-3 py-2 ring-1 ring-foreground/8"><dt className="text-[11px] text-muted-foreground">{k}</dt><dd className="mt-0.5 font-mono text-[11.5px] break-words text-ink">{v}</dd></div>
}

function TraceTable({ rows, title }: { rows: Row[]; title: string }) {
  if (!rows.length) return null
  return (
    <div>
      <p className="mb-1.5 font-semibold text-ink">{title}</p>
      <div className="overflow-x-auto rounded-lg ring-1 ring-foreground/10">
        <table className="w-full min-w-[34rem] border-collapse text-left text-[11.5px]">
          <thead className="bg-muted text-muted-foreground"><tr><th className="px-3 py-1.5 font-medium">Nom</th><th className="px-3 py-1.5 font-medium">Statut</th><th className="px-3 py-1.5 text-right font-medium">Durée</th><th className="px-3 py-1.5 font-medium">Paramètres / raison</th></tr></thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={`${r.tool}-${i}`} className="border-t border-border/70 align-top">
                <td className="px-3 py-1.5 font-mono">{r.tool}</td>
                <td className={cn("px-3 py-1.5 font-mono", r.status === "error" && "font-semibold text-burgundy")}>{r.status}</td>
                <td className="px-3 py-1.5 text-right font-mono tabular-nums">{r.duration_ms != null ? `${r.duration_ms.toLocaleString("fr-FR")} ms` : "—"}</td>
                <td className="px-3 py-1.5 font-mono break-all text-muted-foreground">{r.error ? <span className="text-burgundy">{r.error}</span> : r.reason ?? (r.args ? JSON.stringify(r.args) : "—")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export function TechnicalDetails({ view }: { view: Om5View }) {
  const m = view.meta
  const trace = m.tool_trace as Row[]
  const nodes = trace.filter((t) => t.kind === "node")
  const tools = trace.filter((t) => t.kind === "tool")
  const other = trace.filter((t) => t.kind !== "node" && t.kind !== "tool")
  const problems = [...(m.validation_errors ?? []), ...(((m as unknown as { validation_problems?: string[] }).validation_problems) ?? [])]
  const errors = trace.filter((t) => t.status === "error" || t.error)
  return (
    <Disclosure summary={<span className="inline-flex items-center gap-2 text-sm"><Wrench className="size-4" /> Détails techniques et traçabilité</span>} className="bg-card">
      <div className="space-y-5 text-xs">
        <dl className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          <KV k="Moteur d'orchestration" v={m.graph_engine} />
          <KV k="Budget d'appels analytiques" v={`${m.calls_used} / ${m.call_budget}`} />
          <KV k="Mode de génération" v={m.generation_mode} />
          <KV k="Fournisseur LLM" v={m.llm_provider ?? "—"} />
          <KV k="Modèle" v={m.llm_model ?? "—"} />
          <KV k="Latence LLM" v={m.llm_latency_ms != null ? `${Math.round(m.llm_latency_ms).toLocaleString("fr-FR")} ms` : "—"} />
          <KV k="Statut de validation" v={m.validation_status} />
          <KV k="Citations valides" v={yn(m.evidence_valid)} />
          <KV k="Nouvelles tentatives (retries)" v={String(m.graph_retries)} />
          <KV k="Repli déterministe activé" v={yn(m.fallback_used)} />
          <KV k="Raison du repli" v={m.fallback_reason ?? "—"} />
          <KV k="Rapport partiel" v={yn(m.partial)} />
        </dl>

        {(problems.length > 0 || errors.length > 0) && (
          <div className="rounded-lg bg-burgundy-tint p-3 text-burgundy">
            <p className="font-semibold">Erreurs et avertissements d'exécution</p>
            <ul className="mt-1 list-disc space-y-0.5 pl-4">
              {problems.map((p, i) => <li key={`p-${i}`}>{p}</li>)}
              {errors.map((e, i) => <li key={`e-${i}`}><span className="font-mono">{e.tool}</span> : {e.error ?? e.status}</li>)}
            </ul>
          </div>
        )}

        <TraceTable rows={nodes} title="Nœuds du graphe LangGraph" />
        <TraceTable rows={tools} title="Appels d'outils" />
        <TraceTable rows={other} title="Autres étapes" />

        <div>
          <p className="mb-1.5 font-semibold text-ink">Identifiants de preuves ({view.evidence.length})</p>
          <ul className="max-h-56 space-y-0.5 overflow-auto rounded-lg bg-card p-3 font-mono text-[11px] text-muted-foreground ring-1 ring-foreground/10">
            {view.evidence.map((e) => <li key={e.id} className="break-all"><span className="text-ink">{e.id}</span> · {e.kind}</li>)}
          </ul>
        </div>
      </div>
    </Disclosure>
  )
}
