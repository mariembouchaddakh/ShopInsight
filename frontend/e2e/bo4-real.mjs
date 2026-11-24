// End-to-end BO4 check against the running real-data API and Vite frontend.
import { chromium } from "playwright-core"
import fs from "node:fs"

const base = process.env.SHOPINSIGHT_UI ?? "http://127.0.0.1:5173"
const browsers = ["C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe", "C:/Program Files/Google/Chrome/Application/chrome.exe"]
const executablePath = process.env.BROWSER_PATH ?? browsers.find((p) => fs.existsSync(p))
const browser = await chromium.launch({ executablePath, headless: true })
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
const errors = []
page.on("pageerror", (e) => errors.push(e.message))
page.on("console", (m) => m.type() === "error" && errors.push(m.text()))
page.on("request", (r) => r.url().includes("/api/bo4/") && console.log(r.method(), r.url()))
await page.goto(`${base}/bo4`, { waitUntil: "domcontentloaded", timeout: 120_000 })
console.log("page loaded")
await page.getByLabel("Identifiant de commande").fill("d9612f4021d391b5430703c339d62b26")
await page.getByLabel("Date de simulation historique").fill("2018-04-05")
await page.getByRole("button", { name: "Consulter" }).click()
console.log("order submitted")
await page.getByText("Statut vérifié").waitFor({ timeout: 120_000 })
console.log("context rendered")
await page.getByRole("button", { name: "Quand devrait-elle arriver ?" }).click()
console.log("question selected")
await page.getByRole("button", { name: "Répondre" }).click()
console.log("question submitted")
await page.waitForTimeout(3_000)
if (errors.length) console.log("browser errors", errors)
await page.getByText(/Assistant client — commande/).waitFor({ timeout: 120_000 })
console.log("answer rendered")
const text = await page.locator("body").innerText()
const expected = ["BO4 · Assistant client", "approved", "Estimation de livraison", "Commandes historiques comparables", "Faits observés", "Comparaisons et expériences d'autres clients"]
const missing = expected.filter((x) => !text.includes(x))
const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
await browser.close()
if (errors.length || missing.length || overflow > 1) {
  console.error({ errors, missing, overflow }); process.exit(1)
}
console.log("BO4 real-data browser workflow passed")
