import { useQuery } from "@tanstack/react-query"
import { Activity, Bell, Bot, Gauge, Map, MessageSquareText, PackageSearch, PhoneCall, Store } from "lucide-react"
import type { ReactNode } from "react"
import { NavLink, Outlet, useLocation } from "react-router-dom"
import { AssistantWidget } from "@/components/assistant/assistant-widget"
import { Logo, LogoMark } from "@/components/brand/logo"
import { api } from "@/lib/api"
import { setCategoryLabels } from "@/lib/categories"
import { cn } from "@/lib/utils"
import { MonthPicker } from "./month"

// Navigation par domaine métier (et non par agent technique) : ce que le responsable veut piloter.
const NAV = [
  { group: "Pilotage", items: [{ to: "/", label: "Tableau de bord", icon: Gauge }, { to: "/om5", label: "Monitoring autonome", icon: Activity }] },
  {
    group: "Vendeurs",
    items: [
      { to: "/bo3/calls", label: "À appeler cette semaine", icon: PhoneCall },
      { to: "/bo3/sellers", label: "Annuaire vendeurs", icon: Store },
      { to: "/bo3/market", label: "Carte du marché", icon: Map },
      { to: "/bo3/alerts", label: "Alertes vendeurs", icon: Bell },
    ],
  },
  { group: "Commandes & livraisons", items: [{ to: "/bo1", label: "Commandes à risque", icon: PackageSearch }] },
  { group: "Clients", items: [{ to: "/bo2", label: "Voix du client", icon: MessageSquareText }, { to: "/bo4", label: "Assistant client", icon: Bot }] },
]

function ApiStatus() {
  const location = useLocation()
  const h = useQuery({ queryKey: ["health"], queryFn: api.health, refetchInterval: (q) => (q.state.data && Object.values(q.state.data.agents).every((a) => a.state === "ready") ? 60_000 : 3_000) })
  const agents = h.data?.agents ?? {}
  const current = location.pathname.startsWith("/om5") ? "om5" : location.pathname.startsWith("/bo4") ? "bo4" : location.pathname.startsWith("/bo2") ? "bo2" : location.pathname.startsWith("/bo1") ? "bo1" : "bo3"
  const state = agents[current]?.state
  const loading = state === "loading" || state === "not_loaded" || !state
  const errored = h.isError || state === "error"
  const otherErrors = Object.entries(agents).filter(([name, value]) => name !== current && value.state === "error").map(([name]) => name.toUpperCase())
  const label = h.isError ? "API injoignable" : errored ? `${current.toUpperCase()} indisponible` : loading ? `${current.toUpperCase()} en chargement…` : otherErrors.length ? `${current.toUpperCase()} en ligne · ${otherErrors.join(", ")} indisponible` : `${current.toUpperCase()} en ligne`
  return (
    <div className="flex items-center gap-2 rounded-full border bg-card/70 px-2.5 py-1 text-xs text-muted-foreground" title={Object.entries(agents).map(([k, v]) => `${k}: ${v.state}`).join(" · ")}>
      <span className="relative flex size-2">
        {!errored && <span className={cn("absolute inline-flex size-full animate-ping rounded-full opacity-60", loading ? "bg-butter-hover" : "bg-forest-mark")} />}
        <span className={cn("relative inline-flex size-2 rounded-full", errored ? "bg-burgundy" : loading ? "bg-butter-hover" : "bg-forest-mark")} />
      </span>
      <span className="hidden md:inline">{label}</span>
    </div>
  )
}

export function AppShell() {
  const loc = useLocation()
  const meta = useQuery({ queryKey: ["meta"], queryFn: api.meta, staleTime: Infinity })
  setCategoryLabels(meta.data?.category_labels) // noms français des catégories, avant le rendu des pages
  const search = new URLSearchParams(loc.search)
  const month = search.get("month")
  const withMonth = (to: string) => (month ? `${to}?month=${month}` : to)
  return (
    <div className="flex min-h-svh text-foreground">
      <div className="brand-ribbon fixed inset-x-0 top-0 z-30 h-[3px]" aria-hidden />
      <aside className="sticky top-0 hidden h-svh w-64 shrink-0 flex-col bg-sidebar px-3 pt-6 pb-4 text-sidebar-foreground md:flex">
        <NavLink to={withMonth("/")} className="mb-8 px-2" aria-label="ShopInsight — accueil">
          <Logo tone="light" />
        </NavLink>
        <nav className="flex-1 space-y-6" aria-label="Navigation principale">
          {NAV.map((g) => (
            <div key={g.group}>
              <p className="mb-1.5 px-3 text-[10px] font-semibold tracking-[0.14em] text-sidebar-foreground/45 uppercase">{g.group}</p>
              <div className="space-y-0.5">
                {g.items.map((it) => (
                  <NavItem key={it.to} to={withMonth(it.to)} end={it.to === "/"} icon={<it.icon className="size-4" />}>
                    {it.label}
                  </NavItem>
                ))}
              </div>
            </div>
          ))}
        </nav>
        <div className="rounded-xl bg-white/[0.06] p-3 text-[11px] leading-snug text-sidebar-foreground/70 ring-1 ring-white/10">
          <p className="mb-1 font-medium text-sidebar-foreground/90">Données Olist 2016–2018</p>
          Chaque chiffre est calculé à partir des données et renvoie à sa source.
        </div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex h-14 items-center justify-between gap-3 border-b border-border/70 bg-background/75 px-4 backdrop-blur-md md:px-8">
          <div className="flex min-w-0 items-center gap-3 md:hidden">
            <LogoMark size={26} handle="#132238" />
            <nav className="flex gap-1 overflow-x-auto" aria-label="Navigation">
              {NAV.flatMap((g) => g.items).map((it) => (
                <NavLink
                  key={it.to}
                  to={withMonth(it.to)}
                  end={it.to === "/"}
                  className={({ isActive }) => cn("rounded-lg p-2 text-muted-foreground transition-colors", isActive && "bg-primary text-primary-foreground")}
                  aria-label={it.label}
                >
                  <it.icon className="size-4" />
                </NavLink>
              ))}
            </nav>
          </div>
          <div className="hidden md:block" />
          <div className="flex items-center gap-3">
            {!loc.pathname.startsWith("/bo4") && <MonthPicker />}
            <ApiStatus />
          </div>
        </header>
        <main key={loc.pathname} className="page-enter mx-auto w-full max-w-7xl min-w-0 flex-1 px-4 pt-8 pb-32 md:px-8">
          <Outlet />
        </main>
      </div>
      {!loc.pathname.startsWith("/bo4") && <AssistantWidget />}
    </div>
  )
}

function NavItem({ to, end, icon, children }: { to: string; end?: boolean; icon: ReactNode; children: ReactNode }) {
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) =>
        cn(
          "group relative flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm text-sidebar-foreground/70 transition-all duration-200 hover:translate-x-0.5 hover:bg-white/8 hover:text-sidebar-foreground",
          isActive && "bg-sidebar-accent font-semibold text-sidebar-accent-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
        )
      }
    >
      {({ isActive }) => (
        <>
          <span
            className={cn("absolute top-1/2 -left-3 h-5 w-1 -translate-y-1/2 rounded-r-full bg-sidebar-primary transition-all duration-300", isActive ? "opacity-100" : "h-0 opacity-0")}
            aria-hidden
          />
          <span className={cn("transition-colors", isActive ? "text-sidebar-accent-foreground" : "group-hover:text-sidebar-primary")}>{icon}</span>
          {children}
        </>
      )}
    </NavLink>
  )
}

export function PageHeader({ title, description, actions }: { title: string; description?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-8 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">{title}</h1>
        {description && <p className="mt-2 max-w-3xl text-sm leading-relaxed text-muted-foreground">{description}</p>}
      </div>
      {actions}
    </div>
  )
}
