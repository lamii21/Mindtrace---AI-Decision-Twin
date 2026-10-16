import type { Metadata } from "next";
import localFont from "next/font/local";
import { Fraunces } from "next/font/google";
import "./globals.css";
import { AppProviders } from "@/lib/providers";

const geistSans = localFont({
  src: "./fonts/GeistVF.woff",
  variable: "--font-sans",
  weight: "100 900",
});
const geistMono = localFont({
  src: "./fonts/GeistMonoVF.woff",
  variable: "--font-mono",
  weight: "100 900",
});
const fraunces = Fraunces({
  subsets: ["latin"],
  variable: "--font-display",
  weight: ["400", "500", "600"],
  style: ["normal", "italic"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "MINDTRACE — An auditable AI decision twin",
  description:
    "Every decision has a hidden structure. MINDTRACE simulates how you weigh trade-offs — with computed confidence, visible uncertainty, and a full evidence trace.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body
        className={`${geistSans.variable} ${geistMono.variable} ${fraunces.variable} bg-obsidian-950 font-sans antialiased`}
      >
        <AppProviders>{children}</AppProviders>
      </body>
    </html>
  );
}
