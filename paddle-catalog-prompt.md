# Paddle sandbox — промпт за създаване на каталога

Предварително: сложи в `.env`:  `PADDLE_API_KEY=pdl_sdbx_...`  (Paddle sandbox → Developer tools → Authentication)

Пусни следното в сесия със зареден paddle плъгин:

---

Create my product catalog in my Paddle sandbox account.

Subscription plans (base currency EUR), no free trial (the Free plan is the trial):
- Pro — EUR 25.00/month ("2500"), EUR 250.00/year ("25000") — the annual price includes ~17% discount (2 months free vs 12×25)
- Ultra — EUR 99.00/month ("9900"), EUR 990.00/year ("99000") — same ~17% annual discount

One-time credit packs (no trial, no billing cycle — one-off prices):
- Credits 1000 — EUR 7.00 ("700")
- Credits 4000 — EUR 20.00 ("2000")
- Credits 10000 — EUR 40.00 ("4000")

Country price overrides (base is EUR, so Ireland needs no override):
- United Kingdom (GBP): Pro £21.00/mo ("2100"), £210.00/yr ("21000"); Ultra £84.00/mo ("8400"), £840.00/yr ("84000"); packs £6.00 ("600"), £17.00 ("1700"), £34.00 ("3400")
- Australia (AUD): Pro A$40.00/mo ("4000"), A$400.00/yr ("40000"); Ultra A$159.00/mo ("15900"), A$1590.00/yr ("159000"); packs A$11.00 ("1100"), A$32.00 ("3200"), A$64.00 ("6400")

Notes:
- Paddle amounts are in the lowest denomination as strings — EUR 25.00 is "2500", not "25" or "25.00".
- Create one product per plan (Pro, Ultra) with its monthly and annual prices attached, and one product per credit pack with its one-time price.
- Do NOT set trial_period on any price.
- On every price, set custom_data so my backend can map webhooks to plans: {"plan":"pro"} / {"plan":"ultra"} on subscription prices, {"credits":1000|4000|10000} on pack prices.
- When done, list every product and price you created with its Paddle ID, so I have the mapping.
