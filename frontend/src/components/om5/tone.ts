import type { Tone } from "./model"

/** Styles de ton (texte ≥ 4,5:1 sur fond teinté) — vert / orange / rouge réservés à un sens métier réel. */
export const TONE: Record<Tone, { chip: string; dot: string; text: string; bar: string }> = {
  good: { chip: "bg-forest-mark/10 text-forest ring-forest-mark/25", dot: "bg-forest-mark", text: "text-forest", bar: "bg-forest-mark" },
  warn: { chip: "bg-amber-tint text-amber-ink ring-amber-ink/25", dot: "bg-amber-ink", text: "text-amber-ink", bar: "bg-amber-ink" },
  bad: { chip: "bg-burgundy-tint text-burgundy ring-burgundy/25", dot: "bg-burgundy", text: "text-burgundy", bar: "bg-burgundy" },
  neutral: { chip: "bg-muted text-muted-foreground ring-border", dot: "bg-slate-400", text: "text-muted-foreground", bar: "bg-slate-400" },
  info: { chip: "bg-navy-tint text-navy-soft ring-navy-soft/20", dot: "bg-navy-soft", text: "text-navy-soft", bar: "bg-navy-soft" },
}
