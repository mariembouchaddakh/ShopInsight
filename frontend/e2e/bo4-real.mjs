// End-to-end BO4 check against the running real-data API and Vite frontend.
import { chromium } from "playwright-core"
import fs from "node:fs"

const base = process.env.SHOPINSIGHT_UI ?? "http://127.0.0.1:5173"
const browsers = ["C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe", "C:/Program Files/Google/Chrome/Application/chrome.exe"]
const executablePath = process.env.BROWSER_PATH ?? browsers.find((p) => fs.existsSync(p))
const browser = await chromium.launch({ executablePath, headless: true })
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
const errors = []
const orderId = "53cdb2fc8bc7dce0b6741e2150273451"
const suggested = ["Où en est ma commande ?", "Quand devrait-elle arriver ?", "D'autres clients ont-ils connu un retard similaire ?", "Que puis-je faire si la date promise est dépassée ?"]
page.on("pageerror", (e) => errors.push(e.message))
page.on("console", (m) => m.type() === "error" && errors.push(m.text()))
page.on("request", (r) => r.url().includes("/api/bo4/") && console.log(r.method(), r.url()))
await page.goto(`${base}/bo4`, { waitUntil: "domcontentloaded", timeout: 120_000 })
console.log("page loaded")
await page.getByLabel("Identifiant de commande").fill(orderId)
await page.getByLabel("Date de simulation historique").fill("2018-07-27")
await page.getByRole("button", { name: "Consulter" }).click()
await page.getByText("Remise au transporteur", { exact: true }).first().waitFor({ timeout: 120_000 })
let text = await page.locator("body").innerText()
if (text.includes("observed_delivered") || text.includes("perfumery") || text.includes("Delivered")) errors.push("technical or untranslated labels visible before delivery")
if (!text.includes("Parfumerie")) errors.push("translated category missing")
if (!text.includes("Médiane") || !text.includes("couverture cible 80 %")) errors.push("pre-delivery prediction missing")

async function ask(question) {
  const chip = page.getByRole("button", { name: question, exact: true })
  if (await chip.count()) await chip.click()
  else await page.getByLabel("Question client").fill(question)
  const responsePromise = page.waitForResponse((r) => r.url().endsWith("/api/bo4/ask") && r.request().method() === "POST", { timeout: 120_000 })
  await page.getByRole("button", { name: "Répondre", exact: true }).click()
  const response = await responsePromise
  const payload = await response.json()
  if (response.status() !== 200 || !payload.report?.facts?.length || !payload.evidence?.length) errors.push(`invalid assistant response for: ${question}`)
  await page.getByText(/Assistant client — commande/).waitFor({ timeout: 120_000 })
}

for (const question of suggested) await ask(question)
await ask("Le transporteur a-t-il perdu mon colis ?")

await page.getByLabel("Date de simulation historique").fill("2018-08-31")
await page.getByRole("button", { name: "Consulter" }).click()
await page.getByText("Livrée", { exact: true }).first().waitFor({ timeout: 120_000 })
await page.getByText("Livraison constatée", { exact: true }).waitFor({ timeout: 120_000 })
await ask("Où en est ma commande ?")
text = await page.locator("body").innerText()
const expected = ["BO4 · Assistant client", "BO4 en ligne", "BO1 indisponible", "Livrée", "Parfumerie", "31/08/2018", "Faits observés", "Comparaisons et expériences d'autres clients"]
const missing = expected.filter((x) => !text.includes(x))
const reply = page.getByRole("button", { name: "Répondre", exact: true })
const launcher = page.getByRole("button", { name: "Ouvrir l'assistant", exact: true })
const [replyBox, launcherBox] = await Promise.all([reply.boundingBox(), launcher.boundingBox()])
if (replyBox && launcherBox && !(replyBox.x + replyBox.width < launcherBox.x || launcherBox.x + launcherBox.width < replyBox.x || replyBox.y + replyBox.height < launcherBox.y || launcherBox.y + launcherBox.height < replyBox.y)) errors.push("floating assistant overlaps BO4 response button")
const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
await browser.close()
if (errors.length || missing.length || overflow > 1) {
  console.error({ errors, missing, overflow }); process.exit(1)
}
console.log("BO4 real-data browser workflow passed")
