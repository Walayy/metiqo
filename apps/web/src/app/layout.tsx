import type { Metadata } from "next";
import type { ReactNode } from "react";

import "@fontsource-variable/inter";

import { AppShell, type DataMode } from "../components/app-shell";
import "./globals.css";
import { Providers } from "./providers";
import { OwnerAccess } from "../components/owner-access";

export const metadata: Metadata = {
  description: "Pricing probabiliste League of Legends traçable et prudent.",
  title: "Metiquo",
};

type RootLayoutProperties = Readonly<{
  children: ReactNode;
}>;

export default function RootLayout({ children }: RootLayoutProperties) {
  const configuredMode = process.env.APP_DATA_MODE ?? "mock";
  if (configuredMode !== "mock" && configuredMode !== "real") {
    throw new Error("APP_DATA_MODE must be either mock or real");
  }

  return (
    <html lang="fr" suppressHydrationWarning>
      <body>
        <Providers>
          <AppShell dataMode={configuredMode satisfies DataMode}>
            <OwnerAccess>{children}</OwnerAccess>
          </AppShell>
        </Providers>
      </body>
    </html>
  );
}
