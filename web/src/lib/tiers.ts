/* Paddle price mapping — the ONLY place to edit when the catalog changes.
   Fill the ids from the Paddle catalog output (pri_...). Free has no prices. */

export interface Tier {
  key: "free" | "pro" | "ultra";
  priceId: { month: string; year: string } | null;
}

export const TIERS: Tier[] = [
  { key: "free", priceId: null },
  { key: "pro", priceId: { month: "pri_01m0ypmaj7gejthhejwz3xp007", year: "pri_01m0ypmat13ejyjjaybs7skbw9" } },
  { key: "ultra", priceId: { month: "pri_01m0ypmb7repkv0p3cdhcxebad", year: "pri_01m0ypmbesr5ye6500ddp89sa3" } },
];

/* One-time credit packs (usage page, by credits amount). */
export const PACK_PRICE_IDS: Record<number, string> = {
  1000: "pri_01m0ypmbwa6kam1zhhvmwtm5hc",
  4000: "pri_01m0ypmc9a6dz56frqj8zbx87k",
  10000: "pri_01m0ypmcqvy68jfqtdbzgxbg15",
};

export const paddleConfigured = () =>
  TIERS.some((t) => t.priceId?.month) && !!process.env.NEXT_PUBLIC_PADDLE_CLIENT_TOKEN;
