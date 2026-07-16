"use client";

import { QueryClientProvider } from "@tanstack/react-query";
import { useLayoutEffect, useState } from "react";
import { Toaster } from "sonner";

import { createQueryClient } from "../lib/query";
import { applyThemeClass, resolveInitialTheme } from "../lib/theme";

/** Re-apply cookie theme after React hydrates <html className> (font vars only). */
function ThemeHydrator() {
  useLayoutEffect(() => {
    applyThemeClass(resolveInitialTheme());
  }, []);
  return null;
}

export default function Providers({ children }: { children: React.ReactNode }) {
  const [client] = useState(() => createQueryClient());

  return (
    <QueryClientProvider client={client}>
      <ThemeHydrator />
      {children}
      <Toaster
        position="top-right"
        closeButton
        toastOptions={{
          className: "font-sans",
          duration: 5000,
        }}
      />
    </QueryClientProvider>
  );
}
