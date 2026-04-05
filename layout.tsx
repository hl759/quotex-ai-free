
import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Alpha Hive Hybrid Trading Platform",
  description: "Binary signals + Binance Futures automation dashboard",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
