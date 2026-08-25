import type { Metadata } from "next";
import { Manrope, IBM_Plex_Sans } from "next/font/google";
import "./globals.css";
import { Providers } from "@/components/providers";

const manrope = Manrope({ variable: "--font-manrope", subsets: ["latin", "cyrillic"], weight: ["500", "700", "800"] });
const plex = IBM_Plex_Sans({ variable: "--font-plex", subsets: ["latin", "cyrillic"], weight: ["400", "500", "600"] });

export const metadata: Metadata = {
  title: "Bizzmind",
  description: "AI analyst for business teams: upload your spreadsheets, get a live dashboard and decisions.",
  icons: { icon: "/icon.svg" },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="bg" className={`${manrope.variable} ${plex.variable} dark h-full antialiased`} suppressHydrationWarning>
      <body className="min-h-full flex flex-col">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
