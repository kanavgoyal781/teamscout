"use client";

import { QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { Toaster } from "sonner";

import { createQueryClient } from "../lib/query";

export default function Providers({ children }: { children: React.ReactNode }) {
  const [client] = useState(() => createQueryClient());

  return (
    <QueryClientProvider client={client}>
      {children}
      <Toaster
        position="top-right"
        closeButton
        richColors
        toastOptions={{
          className: "font-sans",
          duration: 5000,
        }}
      />
    </QueryClientProvider>
  );
}
