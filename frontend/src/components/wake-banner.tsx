"use client";

import { AnimatePresence, motion } from "framer-motion";
import { Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
import { wakeServer } from "@/lib/api";

/**
 * The API runs on a free tier that sleeps when idle and takes ~30-60s to wake.
 * Ping it as soon as the page loads, and only explain the wait if it is slow.
 */
export function useServerReady() {
  const [ready, setReady] = useState(false);
  const [slow, setSlow] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    const slowTimer = setTimeout(() => setSlow(true), 2500);
    let attempts = 0;
    const poll = async () => {
      while (!controller.signal.aborted && attempts < 40) {
        attempts += 1;
        if (await wakeServer(controller.signal)) {
          setReady(true);
          clearTimeout(slowTimer);
          return;
        }
        await new Promise((r) => setTimeout(r, 3000));
      }
    };
    poll();
    return () => {
      controller.abort();
      clearTimeout(slowTimer);
    };
  }, []);

  return { ready, slow: slow && !ready };
}

export function WakeBanner({ show }: { show: boolean }) {
  return (
    <AnimatePresence>
      {show && (
        <motion.div
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -8 }}
          role="status"
          className="flex items-center gap-2 rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink"
        >
          <Loader2 className="size-4 animate-spin text-muted" aria-hidden />
          Getting things ready. This can take up to a minute on your first visit.
        </motion.div>
      )}
    </AnimatePresence>
  );
}
