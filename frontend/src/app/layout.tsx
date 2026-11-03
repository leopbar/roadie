import type { Metadata } from "next";
import { Fraunces, JetBrains_Mono, Manrope } from "next/font/google";
import "./globals.css";

const fraunces = Fraunces({ subsets: ["latin"], variable: "--font-fraunces" });
const manrope = Manrope({ subsets: ["latin"], variable: "--font-manrope" });
const jetbrains = JetBrains_Mono({ subsets: ["latin"], variable: "--font-jetbrains" });

export const metadata: Metadata = {
  title: "Roadie · Empório da Música",
  description: "Console de atendimento do Tom, o atendente virtual da Empório da Música.",
  icons: { icon: "/icon.svg" },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR" className={`${fraunces.variable} ${manrope.variable} ${jetbrains.variable}`}>
      <body className="min-h-full">{children}</body>
    </html>
  );
}
