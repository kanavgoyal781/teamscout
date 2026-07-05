import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "TeamScout",
  description: "Recruiting intelligence with an honesty layer for external services.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}