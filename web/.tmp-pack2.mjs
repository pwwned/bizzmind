import { chromium } from "playwright";
const SS = "/private/tmp/claude-501/-Users-georgesotirov-Repos-Analytics-Project/146b78f1-1524-416e-8698-064197dbe4c9/scratchpad";
const b = await chromium.launch();
const pg = await b.newPage({ viewport: { width: 1440, height: 900 } });
await pg.goto("http://localhost:3000/login");
await pg.evaluate(() => { document.cookie = "lang=bg;path=/"; });
await pg.goto("http://localhost:3000/app");
if (await pg.locator('input[type=email]').count()) {
  await pg.fill('input[type=email]', "george@inceptiq.ai");
  await pg.fill('input[type=password]', "Queral1119!@#");
  await pg.click('button[type=submit]');
  await pg.waitForURL("**/app", { timeout: 20000 });
}
await pg.goto("http://localhost:3000/usage");
await pg.waitForSelector("text=КУПИ КРЕДИТИ", { timeout: 20000 });
await pg.locator("button", { hasText: "€20" }).click();
const fl = pg.frameLocator('iframe[name="paddle_frame"], iframe[src*="paddle"]');
// make sure the Card tab is selected before filling
await fl.locator("text=Card").first().click().catch(() => {});
await pg.waitForTimeout(1000);
await fl.locator('input[autocomplete="cc-name"], input[id*="name" i]').first().fill("Test Buyer");
await fl.locator('input[autocomplete="cc-number"], input[placeholder*="XXXX"]').first().fill("4242424242424242");
await fl.locator('input[autocomplete="cc-exp"], input[placeholder*="MM"]').first().fill("12/30");
await fl.locator('input[autocomplete="cc-csc"], input[placeholder*="CVV" i]').first().fill("100");
await pg.waitForTimeout(800);
const btn = fl.locator('button[type="submit"]').last();
for (let attempt = 1; attempt <= 3; attempt++) {
  await btn.click({ force: true });
  let retry = false;
  for (let i = 0; i < 10; i++) {
    await pg.waitForTimeout(3000);
    const t = ((await fl.locator("body").textContent().catch(() => "")) ?? "").replace(/\s+/g, " ");
    if (/try again/i.test(t)) { retry = true; break; }
    if (/success|thank|complete/i.test(t)) { console.log("PAID:", t.slice(0, 100)); attempt = 99; break; }
  }
  if (!retry) break;
  console.log("tax recalc — clicking again");
}
await pg.waitForTimeout(8000);
await pg.screenshot({ path: SS + "/33-pack-paid.png" });
await b.close();
