import type { Metadata } from "next";
import { Manrope, IBM_Plex_Sans } from "next/font/google";
import "./globals.css";
import { cookies } from "next/headers";
import { Providers } from "@/components/providers";

const manrope = Manrope({ variable: "--font-manrope", subsets: ["latin", "cyrillic"], weight: ["500", "700", "800"] });
const plex = IBM_Plex_Sans({ variable: "--font-plex", subsets: ["latin", "cyrillic"], weight: ["400", "500", "600"] });

export const metadata: Metadata = {
  title: "Bizzmind",
  description: "AI analyst for business teams: upload your spreadsheets, get a live dashboard and decisions.",
  icons: { icon: "/icon.svg" },
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const jar = await cookies();
  const dark = (jar.get("theme")?.value ?? "dark") === "dark";
  const lang = jar.get("lang")?.value === "en" ? "en" : "bg";
  return (
    <html lang={lang} className={`${manrope.variable} ${plex.variable} ${dark ? "dark" : ""} h-full antialiased`} suppressHydrationWarning>
      <body className="min-h-full flex flex-col" suppressHydrationWarning>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
