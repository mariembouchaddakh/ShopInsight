import { ChevronDown } from "lucide-react"
import type { ReactNode } from "react"
import { cn } from "@/lib/utils"
import type { Tone } from "./model"
import { TONE } from "./tone"

export function Pill({ tone = "neutral", icon, children, className }: { tone?: Tone; icon?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ring-1 ring-inset [&>svg]:size-3.5", TONE[tone].chip, className)}>
      {icon}
      {children}
    </span>
  )
}

/** Carte de section : titre + sous-titre + contenu. */
export function Panel({ title, subtitle, icon, actions, children, className }: { title?: ReactNode; subtitle?: ReactNode; icon?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={cn("rounded-2xl bg-card p-5 shadow-[0_1px_2px_rgb(19_34_56/6%)] ring-1 ring-foreground/10", className)}>
      {(title || actions) && (
        <header className="mb-4 flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            {title && (
              <h2 className="flex items-center gap-2 font-display text-base font-semibold tracking-tight text-ink [&>svg]:size-4.5 [&>svg]:text-navy-soft">
                {icon}
                {title}
              </h2>
            )}
            {subtitle && <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{subtitle}</p>}
          </div>
          {actions}
        </header>
      )}
      {children}
    </section>
  )
}

/** Panneau repliable (détails). Natif <details> : accessible au clavier, sans état à gérer. */
export function Disclosure({ summary, children, className, defaultOpen }: { summary: ReactNode; children: ReactNode; className?: string; defaultOpen?: boolean }) {
  return (
    <details open={defaultOpen} className={cn("group/disc rounded-lg border border-border/70 bg-muted/30", className)}>
      <summary className="flex cursor-pointer list-none items-center justify-between gap-2 rounded-lg px-3 py-2 text-xs font-medium text-navy-soft outline-none marker:hidden hover:bg-muted/60 focus-visible:ring-2 focus-visible:ring-ring/50 [&::-webkit-details-marker]:hidden">
        <span>{summary}</span>
        <ChevronDown className="size-3.5 transition-transform group-open/disc:rotate-180" />
      </summary>
      <div className="border-t border-border/70 px-3 py-3 text-xs">{children}</div>
    </details>
  )
}

export function Notice({ tone = "info", icon, title, children }: { tone?: Tone; icon?: ReactNode; title: ReactNode; children?: ReactNode }) {
  return (
    <div role={tone === "bad" ? "alert" : "status"} className={cn("flex gap-3 rounded-xl p-4 ring-1 ring-inset", TONE[tone].chip)}>
      {icon && <span className="mt-0.5 shrink-0 [&>svg]:size-4.5">{icon}</span>}
      <div className="min-w-0 text-sm">
        <p className="font-semibold">{title}</p>
        {children && <div className="mt-1 text-[0.8rem] leading-relaxed opacity-90">{children}</div>}
      </div>
    </div>
  )
}
