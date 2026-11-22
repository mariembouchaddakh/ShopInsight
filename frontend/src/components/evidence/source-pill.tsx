import { sourceMeta, TONE_CLASS } from "@/lib/evidence"
import { cn } from "@/lib/utils"

/** Pastille de source lisible (icône + libellé) ; un clic ouvre la fiche de la preuve. L'identifiant technique reste en infobulle. */
export function SourcePill({ id, onOpen, className }: { id: string; onOpen: (id: string) => void; className?: string }) {
  const m = sourceMeta(id)
  const Icon = m.icon
  return (
    <button
      type="button"
      onClick={() => onOpen(id)}
      title="Voir la source"
      className={cn(
        "inline-flex h-6 max-w-full items-center gap-1 rounded-full border px-2 text-[11px] font-medium transition hover:brightness-95 hover:ring-1 hover:ring-current/20",
        TONE_CLASS[m.tone],
        className,
      )}
    >
      <Icon className="size-3 shrink-0" aria-hidden />
      <span className="truncate">{m.label}</span>
    </button>
  )
}

export function SourcePills({ ids, onOpen, className }: { ids: string[]; onOpen: (id: string) => void; className?: string }) {
  const uniq = [...new Set(ids)]
  if (!uniq.length) return null
  return (
    <div className={cn("flex flex-wrap gap-1", className)}>
      {uniq.map((id) => (
        <SourcePill key={id} id={id} onOpen={onOpen} />
      ))}
    </div>
  )
}
