import { useId } from "react"
import { cn } from "@/lib/utils"

// Identité ShopInsight : un sac de boutique (le commerce) qui porte une courbe montante (l'analyse)
// et une étincelle safran (l'« insight »). Le même sac, avec un visage, sert de mascotte à l'assistant.

const BAG = "M9.4 17h29.2a2.2 2.2 0 0 1 2.2 2l1.7 21.3a3.6 3.6 0 0 1-3.6 3.9H9.1a3.6 3.6 0 0 1-3.6-3.9L7.2 19a2.2 2.2 0 0 1 2.2-2z"
const SPARK = "M0-5.5C.5-1.8 1.8-.5 5.5 0 1.8.5.5 1.8 0 5.5-.5 1.8-1.8.5-5.5 0-1.8-.5-.5-1.8 0-5.5z"

function Gradient({ id }: { id: string }) {
  return (
    <linearGradient id={id} x1="6" y1="17" x2="42" y2="44" gradientUnits="userSpaceOnUse">
      <stop offset="0" stopColor="#F9E9A8" />
      <stop offset="1" stopColor="#EACD65" />
    </linearGradient>
  )
}

/** Marque seule (sac + courbe + étincelle). */
export function LogoMark({ size = 32, animated = false, handle = "currentColor", className }: { size?: number; animated?: boolean; handle?: string; className?: string }) {
  const id = useId().replace(/:/g, "")
  return (
    <svg viewBox="0 0 48 48" width={size} height={size} className={className} aria-hidden="true">
      <defs>
        <Gradient id={`g${id}`} />
      </defs>
      <path d="M16.5 17v-4.2a7.5 7.5 0 0 1 15 0V17" fill="none" stroke={handle} strokeWidth="3.2" strokeLinecap="round" />
      <path d={BAG} fill={`url(#g${id})`} />
      <path d="M12.5 36.5l6.8-6.3 5 3.4 9.6-9.4" fill="none" stroke="#132238" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="34.3" cy="24.1" r="2.7" fill="#8B1E3F" />
      <path d={SPARK} transform="translate(39.5 8.5)" fill="#F6E08D" className={cn(animated && "si-sparkle")} />
    </svg>
  )
}

/** Logo complet : marque + nom (« Shop » en clair ou en encre, « Insight » en dégradé de marque). */
export function Logo({ tone = "dark", size = 34, className }: { tone?: "dark" | "light"; size?: number; className?: string }) {
  return (
    <div className={cn("group flex items-center gap-2.5", className)}>
      <LogoMark size={size} animated handle={tone === "light" ? "#F8FAFC" : "#132238"} className="transition-transform duration-300 group-hover:-rotate-6" />
      <div className="leading-none">
        <p className={cn("font-display text-[19px] font-bold tracking-tight", tone === "light" ? "text-white" : "text-foreground")}>
          Shop<span className={tone === "light" ? "text-brand" : "text-ink underline decoration-butter decoration-[3px] underline-offset-2"}>Insight</span>
        </p>
        <p className={cn("mt-1 text-[10px] font-medium tracking-[0.14em] uppercase", tone === "light" ? "text-white/55" : "text-muted-foreground")}>Vendeurs · Olist</p>
      </div>
    </div>
  )
}

/** Mascotte de l'assistant : le sac de la marque avec un visage (yeux qui clignent, sourire), qui flotte doucement. */
export function Mascot({ size = 34, mood = "happy", className }: { size?: number; mood?: "happy" | "thinking"; className?: string }) {
  const id = useId().replace(/:/g, "")
  return (
    <svg viewBox="0 0 48 48" width={size} height={size} className={cn("si-bob", className)} aria-hidden="true">
      <defs>
        <linearGradient id={`m${id}`} x1="6" y1="17" x2="42" y2="44" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#FFFFFF" />
          <stop offset="1" stopColor="#F3F0E4" />
        </linearGradient>
      </defs>
      <path d="M16.5 17v-4.2a7.5 7.5 0 0 1 15 0V17" fill="none" stroke="#F6E08D" strokeWidth="3.2" strokeLinecap="round" />
      <path d={BAG} fill={`url(#m${id})`} />
      <ellipse className="si-eye" cx="18.5" cy="28" rx="2.3" ry="2.9" fill="#132238" />
      <ellipse className="si-eye" cx="29.5" cy="28" rx="2.3" ry="2.9" fill="#132238" />
      {mood === "happy" ? (
        <path d="M19.5 34.5q4.5 4 9 0" fill="none" stroke="#8B1E3F" strokeWidth="2.4" strokeLinecap="round" />
      ) : (
        <circle cx="24" cy="35.5" r="1.8" fill="#8B1E3F" />
      )}
      <circle cx="14.5" cy="33" r="2" fill="#F6E08D" />
      <circle cx="33.5" cy="33" r="2" fill="#F6E08D" />
      <path d={SPARK} transform="translate(39.5 8.5)" fill="#F6E08D" className="si-sparkle" />
    </svg>
  )
}
