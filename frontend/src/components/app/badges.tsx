import type { Severity } from "@/lib/api"
import { SEVERITY_STYLE } from "@/lib/format"
import { cn } from "@/lib/utils"

export function SeverityBadge({ severity, className }: { severity: Severity | null | undefined; className?: string }) {
  if (!severity) return null
  return (
    <span className={cn("inline-flex h-5 items-center rounded-full border px-2 text-[11px] font-medium", SEVERITY_STYLE[severity], className)}>
      {severity}
    </span>
  )
}

export function Pill({ children, tone = "muted", className }: { children: React.ReactNode; tone?: "muted" | "green" | "blue" | "red"; className?: string }) {
  const tones = {
    muted: "bg-muted text-muted-foreground border-transparent",
    green: "bg-sage text-forest border-forest/25",
    blue: "bg-navy-tint text-navy-soft border-navy-soft/25",
    red: "bg-burgundy-tint text-burgundy border-burgundy/30",
  }
  return <span className={cn("inline-flex h-5 items-center rounded-full border px-2 text-[11px] font-medium", tones[tone], className)}>{children}</span>
}

/** Étiquette de nature de contenu : distingue faits vérifiés, estimations, hypothèses et limites. */
export function KindTag({ kind }: { kind: "fact" | "estimate" | "similar" | "action" | "caveat" }) {
  const map = {
    fact: ["Fait", "bg-sage text-forest"],
    estimate: ["Estimation", "bg-navy-tint text-navy-soft"],
    similar: ["Comparaison", "bg-plum-tint text-plum"],
    action: ["Hypothèse à valider", "bg-amber-tint text-amber-ink"],
    caveat: ["Limite", "bg-muted text-muted-foreground"],
  } as const
  const [label, cls] = map[kind]
  return <span className={cn("rounded px-1.5 py-0.5 text-[10px] font-medium tracking-wide uppercase", cls)}>{label}</span>
}
