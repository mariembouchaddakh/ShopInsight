// Test de bout en bout (fumée) : l'API (port 8000) et Vite (port 5173) doivent tourner.
// Utilise le navigateur Edge/Chrome installé (playwright-core, aucun téléchargement de navigateur).
// node e2e/smoke.mjs [dossier_captures]
import { chromium } from "playwright-core"
import fs from "node:fs"

const BASE = process.env.SHOPINSIGHT_UI ?? "http://localhost:5173"
const OUT = process.argv[2]
const BROWSERS = [
  "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
  "C:/Program Files/Google/Chrome/Application/chrome.exe",
  "/usr/bin/google-chrome",
  "/usr/bin/chromium",
]
const executablePath = process.env.BROWSER_PATH ?? BROWSERS.find((p) => fs.existsSync(p))
const SELLER = "2eb70248d66e0e3ef83659f71b244378"

const pages = [
  { name: "dashboard", path: "/?month=2018-06", expect: ["Tableau de bord", "Taux de référence de la marketplace", "À appeler cette semaine"] },
  { name: "sellers", path: "/bo3/sellers?month=2018-06", expect: ["Vendeurs", "vendeurs évalués", "Métier (catégorie)", "Commandes 12 mois", "2eb70248"] },
  { name: "audit", path: `/bo3/sellers/${SELLER}?month=2018-06`, expect: ["Vendeur", "Situation critique", "Expédition tardive", "Bilan & plan d'action", "Concurrence & classement", "Clients, catalogue & historique", "Voix du client & commandes", "Télécharger le Bilan PDF"] },
  { name: "alerts", path: "/bo3/alerts?month=2018-06", expect: ["Alertes vendeurs", "2eb70248"] },
  { name: "calls", path: "/bo3/calls?month=2018-06", expect: ["À appeler cette semaine", "Script d'appel", "Marquer contacté"] },
  { name: "market", path: "/bo3/market?month=2018-06", expect: ["Carte du marché", "Famille", "Ce qu'il faut retenir", "Portrait des 5 familles", "Positionnement de tous les vendeurs"] },
  { name: "bo1", path: "/bo1?month=2018-06", expect: ["BO1", "Commandes à risque"] },
  { name: "bo2", path: "/bo2?month=2018-03", expect: ["BO2", "Voix du client"] },
  { name: "om5", path: "/om5?month=2018-03", expect: ["Centre de pilotage intelligent", "Synthèse exécutive", "Centre d'alertes", "Plan d'action"] },
]
const viewports = [
  { name: "desktop", width: 1440, height: 1000 },
  { name: "mobile", width: 390, height: 844 },
]

const browser = await chromium.launch({ executablePath, headless: true })
let failures = 0
for (const vp of viewports) {
  const ctx = await browser.newContext({ viewport: { width: vp.width, height: vp.height }, deviceScaleFactor: 1 })
  const page = await ctx.newPage()
  const errors = []
  page.on("pageerror", (e) => errors.push(e.message))
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()))
  for (const p of pages) {
    await page.goto(BASE + p.path, { waitUntil: "networkidle", timeout: 120_000 })
    await page.waitForTimeout(500)
    const text = await page.locator("body").innerText()
    const missing = p.expect.filter((t) => !text.includes(t))
    // Aucun détail technique visible : fournisseur ou nom de modèle, coût, nom de détecteur statistique, contenu JSON brut.
    const leaked = ["OpenRouter", ":free", "bêta-binomial", "beta_binomial", "binomial", "coût 0", '{"'].filter((t) => text.includes(t))
    missing.push(...leaked.map((t) => `interdit: ${t}`))
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
    const ok = missing.length === 0 && overflow <= 1
    if (!ok) failures++
    console.log(`${ok ? "OK  " : "FAIL"} ${vp.name.padEnd(7)} ${p.name.padEnd(9)} débordement=${overflow}px${missing.length ? ` manquant=${JSON.stringify(missing)}` : ""}`)
    if (OUT) await page.screenshot({ path: `${OUT}/e2e_${vp.name}_${p.name}.png`, fullPage: false })
  }
  if (errors.length) {
    failures++
    console.log(`FAIL ${vp.name} erreurs console :`, errors.slice(0, 5))
  }
  await ctx.close()
}
await browser.close()
console.log(failures ? `${failures} échec(s)` : "tous les contrôles réussis")
process.exit(failures ? 1 : 0)
