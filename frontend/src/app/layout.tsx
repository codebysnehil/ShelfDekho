import type { Metadata } from "next";
import { Geist_Mono, IBM_Plex_Sans, IBM_Plex_Serif } from "next/font/google";
import { THEME_SCRIPT } from "@/lib/theme";
import { Providers } from "./providers";
import "./globals.css";

const ui = IBM_Plex_Sans({
  variable: "--font-ui",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
});
// The product's voice: titles, the figure that answers a screen, and the analyst's written answer.
const voice = IBM_Plex_Serif({
  variable: "--font-voice-face",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
});
// Monospace is used for real code only (the analyst's SQL).
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "ShelfIQ: know what runs out before it does",
  description:
    "ShelfIQ tells a grocery chain what sold, what will sell and what to reorder today, in every store, before the shelf is empty.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${ui.variable} ${voice.variable} ${geistMono.variable} h-full antialiased`}
      suppressHydrationWarning
    >
      <body className="min-h-full font-sans">
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
