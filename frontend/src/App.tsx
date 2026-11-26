import { lazy, Suspense } from "react"
import { Navigate, Route, Routes } from "react-router-dom"
import { AppShell } from "@/components/app/shell"
import { LoadingBlock } from "@/components/app/states"

// Chargement à la demande : la bibliothèque de graphiques n'est téléchargée que par les pages qui l'utilisent.
const DashboardPage = lazy(() => import("@/pages/dashboard").then((m) => ({ default: m.DashboardPage })))
const SellersPage = lazy(() => import("@/pages/bo3-sellers").then((m) => ({ default: m.SellersPage })))
const SellerAuditPage = lazy(() => import("@/pages/bo3-seller").then((m) => ({ default: m.SellerAuditPage })))
const CallsPage = lazy(() => import("@/pages/bo3-calls").then((m) => ({ default: m.CallsPage })))
const MarketPage = lazy(() => import("@/pages/bo3-market").then((m) => ({ default: m.MarketPage })))
const AlertsPage = lazy(() => import("@/pages/bo3-alerts").then((m) => ({ default: m.AlertsPage })))
const Bo1Page = lazy(() => import("@/pages/bo1").then((m) => ({ default: m.Bo1Page })))
const Bo2Page = lazy(() => import("@/pages/bo2").then((m) => ({ default: m.Bo2Page })))
const Bo4Page = lazy(() => import("@/pages/bo4").then((m) => ({ default: m.Bo4Page })))
const Om5Page = lazy(() => import("@/pages/om5").then((m) => ({ default: m.Om5Page })))

const page = (el: React.ReactNode) => <Suspense fallback={<LoadingBlock rows={6} />}>{el}</Suspense>

export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={page(<DashboardPage />)} />
        <Route path="bo3/sellers" element={page(<SellersPage />)} />
        <Route path="bo3/sellers/:sellerId" element={page(<SellerAuditPage />)} />
        <Route path="bo3/alerts" element={page(<AlertsPage />)} />
        <Route path="bo3/market" element={page(<MarketPage />)} />
        <Route path="bo3/calls" element={page(<CallsPage />)} />
        <Route path="bo1" element={page(<Bo1Page />)} />
        <Route path="bo2" element={page(<Bo2Page />)} />
        <Route path="bo4" element={page(<Bo4Page />)} />
        <Route path="om5" element={page(<Om5Page />)} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
