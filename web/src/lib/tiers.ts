/* Paddle price mapping — the ONLY place to edit when the catalog changes.
   Fill the ids from the Paddle catalog output (pri_...). Free has no prices. */

export interface Tier {
  key: "free" | "pro" | "ultra";
  priceId: { month: string; year: string } | null;
}

export const TIERS: Tier[] = [
  { key: "free", priceId: null },
  { key: "pro", priceId: { month: "", year: "" } },     // pri_... месечно / годишно
  { key: "ultra", priceId: { month: "", year: "" } },   // pri_... месечно / годишно
];

/* One-time credit packs (usage page, by credits amount). */
export const PACK_PRICE_IDS: Record<number, string> = {
  1000: "",   // pri_...
  4000: "",   // pri_...
  10000: "",  // pri_...
};

export const paddleConfigured = () =>
  TIERS.some((t) => t.priceId?.month) && !!process.env.NEXT_PUBLIC_PADDLE_CLIENT_TOKEN;
