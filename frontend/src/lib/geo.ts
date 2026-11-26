// États brésiliens : nom complet et grande région (affichage lisible au lieu des sigles).
export const UF_NAMES: Record<string, string> = {
  AC: "Acre", AL: "Alagoas", AP: "Amapá", AM: "Amazonas", BA: "Bahia", CE: "Ceará", DF: "District fédéral", ES: "Espírito Santo",
  GO: "Goiás", MA: "Maranhão", MT: "Mato Grosso", MS: "Mato Grosso do Sul", MG: "Minas Gerais", PA: "Pará", PB: "Paraíba",
  PR: "Paraná", PE: "Pernambouc", PI: "Piauí", RJ: "Rio de Janeiro", RN: "Rio Grande do Norte", RS: "Rio Grande do Sul",
  RO: "Rondônia", RR: "Roraima", SC: "Santa Catarina", SP: "São Paulo", SE: "Sergipe", TO: "Tocantins",
}

export function stateName(uf: string | null | undefined): string {
  if (!uf) return "—"
  return UF_NAMES[uf] ?? uf
}

const UF_TOKEN = new RegExp(String.raw`(?<![\p{L}\p{N}_:/-])(${Object.keys(UF_NAMES).join("|")})(?![\p{L}\p{N}_:/-])`, "gu")

/** Texte libre (rapports BO1/BO2, non modifiables) : chaque sigle d'État isolé (« → MA », « Client MG ») devient son nom complet. */
export function expandStates(text: string): string {
  return text.replace(UF_TOKEN, (uf) => UF_NAMES[uf] ?? uf)
}

/** Projection équirectangulaire corrigée (cos de la latitude moyenne du Brésil) vers un repère SVG. */
export const BRAZIL = { lng: [-74, -34] as const, lat: [-34, 5.5] as const, k: 10, cos: Math.cos((-14 * Math.PI) / 180) }
export function project(lng: number, lat: number): [number, number] {
  return [(lng - BRAZIL.lng[0]) * BRAZIL.cos * BRAZIL.k, (BRAZIL.lat[1] - lat) * BRAZIL.k]
}
export const MAP_W = (BRAZIL.lng[1] - BRAZIL.lng[0]) * BRAZIL.cos * BRAZIL.k
export const MAP_H = (BRAZIL.lat[1] - BRAZIL.lat[0]) * BRAZIL.k
