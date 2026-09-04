"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { Badge, Button } from "@metiquo/ui";
import {
  Activity,
  CalendarDays,
  ChartNoAxesCombined,
  Database,
  FileChartColumnIncreasing,
  Menu,
  Settings,
  ShieldCheck,
  X,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { useState } from "react";

import { ThemeMenu } from "./theme-menu";

export type DataMode = "mock" | "real";

type NavigationItem = Readonly<{
  href: string;
  icon: LucideIcon;
  label: string;
}>;

export const navigationItems: readonly NavigationItem[] = [
  { href: "/", icon: ChartNoAxesCombined, label: "Opportunités" },
  { href: "/events", icon: CalendarDays, label: "Événements" },
  { href: "/paper-trading", icon: FileChartColumnIncreasing, label: "Paper trading" },
  { href: "/models", icon: Activity, label: "Modèles & backtests" },
  { href: "/data", icon: Database, label: "Données" },
  { href: "/admin", icon: ShieldCheck, label: "Administration" },
  { href: "/settings", icon: Settings, label: "Paramètres" },
];

type AppShellProperties = Readonly<{
  children: ReactNode;
  dataMode: DataMode;
}>;

function DataModeBadge({ dataMode }: Readonly<{ dataMode: DataMode }>) {
  return (
    <Badge
      className={
        dataMode === "mock"
          ? "border-sky-300 bg-sky-50 text-sky-800 dark:border-sky-800 dark:bg-sky-950 dark:text-sky-200"
          : "border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-100"
      }
    >
      <span aria-hidden="true" className="mr-1.5 size-1.5 rounded-full bg-current" />
      {dataMode.toUpperCase()}
    </Badge>
  );
}

function Brand() {
  return (
    <Link
      className="group flex min-h-11 items-center gap-3 rounded-lg outline-none focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-focus"
      href="/"
    >
      <span
        aria-hidden="true"
        className="grid size-9 place-items-center rounded-lg bg-accent text-sm font-black tracking-tighter text-accent-contrast shadow-sm transition-transform duration-interaction group-hover:-translate-y-0.5 motion-reduce:transition-none motion-reduce:group-hover:translate-y-0"
      >
        MQ
      </span>
      <span>
        <span className="block text-base font-bold tracking-tight text-ink-primary">Metiquo</span>
        <span className="block text-xs text-ink-secondary">Pricing intelligence</span>
      </span>
    </Link>
  );
}

function Navigation({ onNavigate }: Readonly<{ onNavigate?: () => void }>) {
  const pathname = usePathname();

  return (
    <nav aria-label="Navigation principale">
      <ul className="grid gap-1">
        {navigationItems.map((item) => {
          const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
          const Icon = item.icon;

          return (
            <li key={item.href}>
              <Link
                aria-current={active ? "page" : undefined}
                className={`flex min-h-11 items-center gap-3 rounded-lg px-3 text-sm font-medium outline-none transition-[background-color,color,transform] duration-interaction focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus motion-reduce:transition-none ${
                  active
                    ? "bg-accent-soft text-ink-primary"
                    : "text-ink-secondary hover:translate-x-0.5 hover:bg-surface-muted hover:text-ink-primary motion-reduce:hover:translate-x-0"
                }`}
                href={item.href}
                {...(onNavigate === undefined ? {} : { onClick: onNavigate })}
              >
                <Icon aria-hidden="true" className="size-4.5 shrink-0" strokeWidth={1.8} />
                <span>{item.label}</span>
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

export function AppShell({ children, dataMode }: AppShellProperties) {
  const [mobileNavigationOpen, setMobileNavigationOpen] = useState(false);

  return (
    <div className="min-h-screen bg-surface-canvas text-ink-primary">
      <a
        className="fixed left-4 top-4 z-[70] -translate-y-24 rounded-md bg-accent px-4 py-2 text-sm font-semibold text-accent-contrast shadow-panel outline-none transition-transform focus:translate-y-0 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus motion-reduce:transition-none"
        href="#main-content"
      >
        Aller au contenu
      </a>

      <aside className="fixed inset-y-0 left-0 z-30 hidden w-72 flex-col border-r border-border-subtle bg-surface-raised px-5 py-6 lg:flex">
        <Brand />
        <div className="mt-9 flex-1">
          <Navigation />
        </div>
        <div className="grid gap-4 border-t border-border-subtle pt-5">
          <div className="flex items-center justify-between gap-3">
            <DataModeBadge dataMode={dataMode} />
            <ThemeMenu />
          </div>
          <p className="text-xs leading-5 text-ink-secondary">
            Analyse et paper trading uniquement. Aucun pari réel n’est exécuté.
          </p>
        </div>
      </aside>

      <div className="lg:pl-72">
        <header className="sticky top-0 z-20 flex h-16 items-center justify-between border-b border-border-subtle bg-surface-canvas/90 px-4 backdrop-blur-md sm:px-6 lg:hidden">
          <Brand />
          <div className="flex items-center gap-1.5">
            <DataModeBadge dataMode={dataMode} />
            <ThemeMenu />
            <Dialog.Root open={mobileNavigationOpen} onOpenChange={setMobileNavigationOpen}>
              <Dialog.Trigger asChild>
                <Button aria-label="Ouvrir la navigation" size="icon" variant="ghost">
                  <Menu aria-hidden="true" className="size-5" strokeWidth={1.8} />
                </Button>
              </Dialog.Trigger>
              <Dialog.Portal>
                <Dialog.Overlay className="fixed inset-0 z-40 bg-slate-950/45 backdrop-blur-[2px] data-[state=closed]:animate-none" />
                <Dialog.Content className="fixed inset-y-0 right-0 z-50 flex w-[min(88vw,22rem)] flex-col border-l border-border-subtle bg-surface-raised p-5 text-ink-primary shadow-panel outline-none">
                  <div className="flex items-center justify-between gap-4">
                    <Dialog.Title className="text-lg font-semibold tracking-tight">
                      Navigation
                    </Dialog.Title>
                    <Dialog.Close asChild>
                      <Button aria-label="Fermer la navigation" size="icon" variant="ghost">
                        <X aria-hidden="true" className="size-5" strokeWidth={1.8} />
                      </Button>
                    </Dialog.Close>
                  </div>
                  <div className="mt-7">
                    <Navigation
                      onNavigate={() => {
                        setMobileNavigationOpen(false);
                      }}
                    />
                  </div>
                  <p className="mt-auto border-t border-border-subtle pt-5 text-xs leading-5 text-ink-secondary">
                    Analyse et paper trading uniquement. Aucun pari réel n’est exécuté.
                  </p>
                </Dialog.Content>
              </Dialog.Portal>
            </Dialog.Root>
          </div>
        </header>

        <main
          className="mx-auto min-h-screen w-full max-w-[96rem] px-4 py-8 sm:px-6 sm:py-10 lg:px-10"
          id="main-content"
          tabIndex={-1}
        >
          {children}
        </main>
      </div>
    </div>
  );
}
