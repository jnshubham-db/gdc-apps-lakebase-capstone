import { Activity, LayoutDashboard, Radio, Users } from "lucide-react";
import { NavLink, Outlet } from "react-router-dom";

import GenieWidget from "./GenieWidget";

import { cn } from "@/lib/utils";

const NAV = [
  { to: "/", label: "Customers", icon: Users, end: true },
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard, soon: true },
  { to: "/reports", label: "Reports", icon: Activity, soon: true },
];

// The signed-in rep. On the deployed app this comes from the OBO proxy
// (X-Forwarded-Email); locally we show the dev identity placeholder.
const USER_EMAIL =
  (typeof window !== "undefined" && window.__ACME_USER__) || "rep@acme-retail.example";

declare global {
  interface Window {
    __ACME_USER__?: string;
  }
}

function Wings() {
  return (
    <svg width="26" height="14" viewBox="0 0 26 14" className="text-green" aria-hidden>
      <path
        d="M13 7 L2 4 L2 6 L11 7 L2 8 L2 10 Z M13 7 L24 4 L24 6 L15 7 L24 8 L24 10 Z"
        fill="currentColor"
        opacity="0.9"
      />
      <circle cx="13" cy="7" r="2.4" fill="none" stroke="currentColor" strokeWidth="1.2" />
    </svg>
  );
}

export function AppShell() {
  return (
    <div className="relative z-10 flex min-h-screen">
      {/* Left instrument rail */}
      <aside className="fixed inset-y-0 left-0 hidden w-56 flex-col border-r border-bezel bg-face/60 backdrop-blur-sm md:flex">
        <div className="flex items-center gap-2.5 border-b border-bezel px-5 py-5">
          <Wings />
          <div className="leading-none">
            <div className="font-display text-base font-bold uppercase tracking-[0.16em] text-lum">
              Acme Ops
            </div>
            <div className="placard !text-[9px] mt-0.5">customer flight deck</div>
          </div>
        </div>

        <nav className="flex flex-1 flex-col gap-1 p-3">
          {NAV.map(({ to, label, icon: Icon, end, soon }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                cn(
                  "group flex items-center gap-3 rounded-sm border px-3 py-2.5 font-display text-sm uppercase tracking-[0.12em] transition-all",
                  isActive
                    ? "border-green/50 bg-green/10 text-green shadow-glow"
                    : "border-transparent text-muted hover:border-bezel hover:bg-face hover:text-lum",
                )
              }
            >
              <Icon className="h-4 w-4" strokeWidth={1.75} />
              <span>{label}</span>
              {soon && <span className="placard ml-auto !text-[8px] opacity-60">soon</span>}
            </NavLink>
          ))}
        </nav>

        <div className="border-t border-bezel px-5 py-4">
          <div className="placard !text-[9px]">signed in</div>
          <div className="mt-1 truncate font-mono text-xs text-lum/90" title={USER_EMAIL}>
            {USER_EMAIL}
          </div>
        </div>
      </aside>

      {/* Main column */}
      <div className="flex flex-1 flex-col md:pl-56">
        <header className="sticky top-0 z-20 flex h-14 items-center justify-between border-b border-bezel bg-panel/80 px-4 backdrop-blur-md md:px-8">
          <div className="flex items-center gap-2 md:hidden">
            <Wings />
            <span className="font-display text-sm font-bold uppercase tracking-[0.16em]">
              Acme Ops
            </span>
          </div>
          <div className="hidden items-center gap-2 md:flex">
            <Radio className="h-3.5 w-3.5 text-green" strokeWidth={2} />
            <span className="placard">fevm-test-jg · lakebase live</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="hidden font-mono text-xs text-muted sm:inline">{USER_EMAIL}</span>
            <span className="grid h-8 w-8 place-items-center rounded-full border border-green/40 bg-green/10 font-display text-xs font-bold text-green">
              {USER_EMAIL.slice(0, 2).toUpperCase()}
            </span>
          </div>
        </header>

        <main className="flex-1 px-4 py-6 md:px-8 md:py-8">
          <Outlet />
        </main>
      </div>
      <GenieWidget />
    </div>
  );
}
