import { headers } from "next/headers";
import { PricingSwitch } from "@/components/pricing-switch";

/* Country comes from the edge header; when absent we pass nothing and
   Paddle.PricePreview() auto-detects from the visitor's IP. */
export default async function PricingPage() {
  const h = await headers();
  const country = h.get("x-vercel-ip-country") ?? undefined;
  return <PricingSwitch country={country} />;
}
