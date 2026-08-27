"use client";
/* One pricing surface: anonymous visitors get the public plan cards,
   signed-in users get the full credits & plans screen. */
import { useEffect, useState } from "react";
import { PricingClient } from "@/components/pricing-client";
import { UsageContent } from "@/components/usage-content";

export function PricingSwitch({ country }: { country?: string }) {
  const [authed, setAuthed] = useState<boolean | null>(null);
  useEffect(() => {
    fetch("/api/auth/me", { credentials: "same-origin" })
      .then((r) => setAuthed(r.ok))
      .catch(() => setAuthed(false));
  }, []);
  if (authed === null) return null;
  return authed ? <UsageContent /> : <PricingClient country={country} />;
}
