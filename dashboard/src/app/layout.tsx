import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "MaaS Dashboard",
  description: "Memory as a Service — Observability Dashboard",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen">{children}</body>
    </html>
  );
}