"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "next-themes";
import type { ReactNode } from "react";
import { useState } from "react";

import { BackendReadError } from "../lib/backend";

type ProvidersProperties = Readonly<{
  children: ReactNode;
  nonce?: string;
}>;

export function Providers({ children, nonce }: ProvidersProperties) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            networkMode: "always",
            refetchOnReconnect: true,
            refetchOnWindowFocus: false,
            retry: (failures, error) =>
              failures < 1 &&
              !(
                error instanceof BackendReadError &&
                [400, 401, 403, 404, 410].includes(error.status)
              ),
            staleTime: 30_000,
          },
          mutations: { networkMode: "always", retry: false },
        },
      }),
  );

  return (
    <ThemeProvider
      {...(nonce ? { nonce } : {})}
      attribute="data-theme"
      defaultTheme="system"
      disableTransitionOnChange
      enableColorScheme
      enableSystem
      storageKey="metiquo-theme"
    >
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    </ThemeProvider>
  );
}
