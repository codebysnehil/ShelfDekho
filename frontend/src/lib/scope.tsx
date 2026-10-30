"use client";

import { useQuery } from "@tanstack/react-query";
import { createContext, type ReactNode, useContext, useState } from "react";
import { api, type Store } from "./api";

type Scope = {
  storeId: string;
  setStoreId: (id: string) => void;
  stores: Store[];
  store: Store | undefined;
};

const ScopeContext = createContext<Scope | null>(null);

/** The store the whole app is looking at. Set once in the shell, followed by every screen. */
export function ScopeProvider({ children }: { children: ReactNode }) {
  const [storeId, setStoreId] = useState("");
  const { data: stores = [] } = useQuery({
    queryKey: ["stores"],
    queryFn: () => api<Store[]>("/api/meta/stores"),
  });
  const store = stores.find((s) => String(s.id) === storeId);
  return (
    <ScopeContext.Provider value={{ storeId, setStoreId, stores, store }}>
      {children}
    </ScopeContext.Provider>
  );
}

export function useScope(): Scope {
  const scope = useContext(ScopeContext);
  if (!scope) throw new Error("useScope must be used inside ScopeProvider");
  return scope;
}
