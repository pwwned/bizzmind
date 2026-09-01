/* Brand-aware choices for a client deck: which brand colours may carry data
   series, and which of Gamma's themes fits the brand. Pure functions — no
   React, no DOM — so they are unit-tested under plain Node. */

export interface GammaTheme { id: string; name: string; type?: string; colorKeywords?: string[]; toneKeywords?: string[] }

/* A brand book's palette is not a series palette: it carries pale neutrals meant
   for backgrounds and near-identical tints that become the same colour once they
   sit next to each other in a legend. Keep only what reads apart — from the white
   slide and from each other — then darken each survivor so a chart with more
   series than brand colours still never repeats one. */
export function seriesPalette(brand: string[] | undefined, fallback: string[]): string[] {
  const rgb = (h: string) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
  const gap = (a: number[], b: number[]) => Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);
  const kept: string[] = [];
  for (const c of brand ?? []) {
    if (!/^#[0-9a-f]{6}$/i.test(c)) continue;
    const v = rgb(c);
    if (gap(v, [255, 255, 255]) < 90) continue;              // washes out on a white slide
    if (kept.some((k) => gap(rgb(k), v) < 60)) continue;      // twin of one already kept
    kept.push(c);
  }
  if (kept.length < 3) return fallback;
  const darker = kept.map((c) => "#" + rgb(c).map((n) =>
    Math.round(n * 0.55).toString(16).padStart(2, "0")).join(""));
  return [...kept, ...darker];
}

/* Which colour words describe this brand's own family. */
export function hueWords(hex: string): RegExp {
  if (!/^#[0-9a-f]{6}$/i.test(hex)) return /$^/;
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
  const max = Math.max(r, g, b);
  if (max - Math.min(r, g, b) < 30) return /gray|grey|black|white|mono|b&w/;
  if (b === max) return max < 110 ? /navy|deep blue|dark blue/ : /blue|azure|sky|teal/;
  if (g === max) return /green|olive|emerald|forest|sage/;
  return g > b ? /orange|amber|gold|earth/ : /red|crimson|burgundy|maroon/;
}

export function themeScore(th: GammaTheme, brandPrimary: string) {
  const kw = [...(th.colorKeywords ?? []), ...(th.toneKeywords ?? [])].map((k) => k.toLowerCase());
  const has = (re: RegExp) => kw.some((k) => re.test(k));
  // Deliberately no bonus for `type === "custom"`: the custom themes live in OUR
  // Gamma workspace, so preferring one would stamp our identity on the client's
  // deck — the opposite of what a white-label deliverable should do.
  let score = 0;
  if (has(hueWords(brandPrimary.toLowerCase()))) score += 5;   // the brand's own colour family
  if (has(/corporate|professional|business|formal|editorial/)) score += 3;
  if (has(/clean|minimal|refined|serious/)) score += 2;
  if (has(/light|white/)) score += 1;                          // business decks get printed
  if (has(/playful|fun|retro|neon|grunge|hand|comic|whimsical|bold/)) score -= 4;
  return score;
}
