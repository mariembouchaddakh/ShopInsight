// Noms français des catégories de produits : fournis par l'API (/api/bo3/meta, source unique côté serveur),
// enregistrés au rendu de l'enveloppe de l'application. Repli lisible tant que la liste n'est pas chargée.
let LABELS: Record<string, string> = {}
const FALLBACK_LABELS: Record<string, string> = { perfumery: "Parfumerie" }

export function setCategoryLabels(m: Record<string, string> | undefined) {
  if (m) LABELS = m
}

export function catLabel(slug: string | null | undefined): string {
  if (!slug) return "—"
  return LABELS[slug] ?? FALLBACK_LABELS[slug] ?? slug.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase())
}
