import type { Metadata } from "next";
import { Fraunces, Geist, Geist_Mono } from "next/font/google";

import Providers from "./providers";
import "./globals.css";

const geistSans = Geist({
  subsets: ["latin"],
  variable: "--font-geist-sans",
  display: "swap",
});

const geistMono = Geist_Mono({
  subsets: ["latin"],
  variable: "--font-geist-mono",
  display: "swap",
});

const fraunces = Fraunces({
  subsets: ["latin"],
  variable: "--font-fraunces",
  display: "swap",
});

export const metadata: Metadata = {
  title: "TeamScout",
  description: "Recruiting intelligence — resume→jobs→team and library→best-resume.",
};

/** Inline script: apply theme class before paint via cookie (no browser storage APIs). */
const themeInitScript = `
(function(){
  try {
    var m = document.cookie.match(/(?:^|; )teamscout-theme=(dark|light)/);
    var t = m ? m[1] : (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
    var r = document.documentElement;
    r.classList.remove('dark', 'light');
    r.classList.add(t);
    r.dataset.theme = t;
  } catch (e) {
    var r2 = document.documentElement;
    r2.classList.remove('dark', 'light');
    r2.classList.add('light');
  }
})();
`;

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      // Font vars only — light/dark class is applied by themeInitScript (cookie)
      // before paint. Hardcoding "light" here re-hydrates over dark cookie.
      className={`${geistSans.variable} ${geistMono.variable} ${fraunces.variable}`}
      suppressHydrationWarning
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
      </head>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
