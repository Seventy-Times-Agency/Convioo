import type { Metadata, Viewport } from "next";
import { Manrope } from "next/font/google";
import "./globals.css";
import { LocaleProvider } from "@/lib/i18n";
import { ThemeProvider, THEME_BOOT_SCRIPT } from "@/components/ThemeProvider";
import { KeyboardShortcuts } from "@/components/KeyboardShortcuts";
import { Toaster } from "sonner";

const manrope = Manrope({
  subsets: ["latin", "cyrillic"],
  variable: "--font-manrope",
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
    { media: "(prefers-color-scheme: dark)", color: "#14120E" },
  ],
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ru" className={manrope.variable}>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOT_SCRIPT }} />
      </head>
      <body>
        <ThemeProvider>
          <LocaleProvider>
            {children}
            <KeyboardShortcuts />
            <Toaster richColors position="top-right" />
          </LocaleProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
