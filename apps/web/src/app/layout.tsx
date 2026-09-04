import type { Metadata } from "next";
import type { ReactNode } from "react";

import "./globals.css";
import { Providers } from "./providers";

export const metadata: Metadata = {
  description: "Pricing probabiliste League of Legends traçable et prudent.",
  title: "Metiquo",
};

type RootLayoutProperties = Readonly<{
  children: ReactNode;
}>;

export default function RootLayout({ children }: RootLayoutProperties) {
  return (
    <html lang="fr">
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
