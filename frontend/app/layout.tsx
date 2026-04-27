import type { Metadata, Viewport } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { LocaleProvider } from "@/lib/i18n";
import { ThemeProvider, THEME_BOOT_SCRIPT } from "@/components/ThemeProvider";
import { KeyboardShortcuts } from "@/components/KeyboardShortcuts";

const inter = Inter({
  subsets: ["latin", "cyrillic"],
  variable: "--font-inter",
  display: "swap",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin", "cyrillic"],
  variable: "--font-jetbrains",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Convioo — 50 AI-scored B2B prospects in 90 seconds",
  description:
    "Describe your target niche and region. Convioo pulls matches from Google Places, enriches every site and review, and hands you an AI-scored list with a custom pitch per lead.",
  manifest: "/manifest.webmanifest",
  appleWebApp: {
    capable: true,
    title: "Convioo",
    statusBarStyle: "black-translucent",
  },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#FAFAF7" },
    { media: "(prefers-color-scheme: dark)", color: "#0F0F11" },
  ],
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ru" className={`${inter.variable} ${jetbrainsMono.variable}`}>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOT_SCRIPT }} />
      </head>
      <body>
        <ThemeProvider>
          <LocaleProvider>
            {children}
            <KeyboardShortcuts />
          </LocaleProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
