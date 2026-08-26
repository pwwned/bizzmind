# Paddle — go-live промпт (пази се за след sandbox теста)

Предусловия преди да се пусне:
1. Sandbox интеграцията е минала end-to-end тест (checkout → плащане → webhook → /welcome).
2. Има купен реален домейн (vercel.app поддомейн НЕ минава website approval за live).
3. Публични /terms, /privacy, /refund, /contact страници.
4. Live акаунтът е създаден и MCP-тата са закачени:
   claude mcp add --transport http paddle-sandbox https://sandbox-mcp.paddle.com/mcp --header "Authorization: Bearer $PADDLE_API_KEY"
   claude mcp add --transport http paddle-live https://mcp.paddle.com/mcp   # OAuth в браузъра при първа употреба

---

Take my tested sandbox integration live. Do this once it has passed sandbox testing. Work through three parts in order.

Heads-up: migrating points my code at live, but I can't take live payments until verification passes and my domains are approved. Don't deploy the live build to real customers until part 3 is done — verify locally or in staging first.

I have two MCP servers:
- `paddle-sandbox` — my sandbox account (source)
- `paddle-live` — my live account (destination)

## 1. Migrate my data and config to live
1. Recreate my catalog in live: read products, prices, and discounts from sandbox and create equivalents in live with the `paddle-live` MCP. Skip test/junk items. Capture the old-new ID mapping.
2. Find and replace every sandbox price ID and discount ID in my codebase with the matching live IDs — pricing page (web/src/lib/tiers.ts), checkout, upgrade/downgrade logic, subscription lifecycle code.
3. Create new live client-side tokens (prefixed `live_`) and update my env vars.
4. Create new live notification destinations and update the signing secret used by my webhook handler.
5. Switch all environment references from sandbox to live: NEXT_PUBLIC_PADDLE_ENV=production (frontend fails loudly otherwise), and PADDLE_API_KEY -> live key server-side.
6. For Paddle Retain, add `pwCustomer` to `Paddle.Initialize()`, passing the signed-in customer's Paddle customer ID — e.g. `pwCustomer: { id: 'ctm_...' }`. It must be the Paddle customer ID, not my internal ID or the customer's email.

Prompt me to create a live API key and update my env vars; add domains to Paddle for website approval; and to update my default payment link to my live checkout page under Checkout > Checkout settings — for live it must be a real, approved domain, not localhost.

For webhook security, fetch Paddle's current live IPs from https://api.paddle.com/ips (the addresses are in `data.ipv4_cidrs`, as /32 CIDRs), allowlist them on my webhook server, and reject deliveries from any other source. Don't hard-code the list — the endpoint is the source of truth and can change.

## 2. Check I'm ready to go live
Audit my app and report what's ready vs. missing:
- Live, publicly accessible Terms & Conditions, Privacy Policy, and Refund/Cancellation Policy. List the URLs; flag any that 404 or redirect.
- A clear description of what my product does.
- Contact details reachable from the homepage in two clicks or fewer.
- Pricing on the site matches my live Paddle catalog. List discrepancies.
- Every domain where I run Paddle Checkout resolves, serves the real product, and is approved for live under Checkout > Website approval.

## 3. Tell me to proceed to live
Once the above looks good, tell me to switch to vendors.paddle.com to follow the steps there — verification and a real payment.
