// Runs under plain Node (type stripping): `npm test` in web/.
import { test } from "node:test";
import assert from "node:assert/strict";
import { seriesPalette, hueWords, themeScore, type GammaTheme } from "../src/lib/deck-theme.ts";

const SOPHARMA = ["#023B59", "#00A5DE", "#8A959C", "#C7D8E2", "#C4DB9B", "#81B177", "#C7D8D8"];
const FALLBACK = ["#6f8f1f", "#b5d33d", "#56703a"];

test("brand palette drops washed-out tints and twins, then darkens survivors", () => {
  const pal = seriesPalette(SOPHARMA, FALLBACK);
  assert.deepEqual(pal.slice(0, 4), ["#023B59", "#00A5DE", "#8A959C", "#C4DB9B"]);
  assert.equal(pal.length, 8);                                   // 4 kept + 4 darker
  assert.ok(!pal.includes("#C7D8E2") && !pal.includes("#C7D8D8")); // too close to white
  assert.ok(!pal.includes("#81B177"));                           // twin of #8A959C
  assert.ok(new Set(pal).size === pal.length, "no colour repeats");
});

test("a brand with too few usable colours keeps the product palette", () => {
  assert.deepEqual(seriesPalette(["#ffffff", "#fefefe"], FALLBACK), FALLBACK);
  assert.deepEqual(seriesPalette(undefined, FALLBACK), FALLBACK);
  assert.deepEqual(seriesPalette(["#023B59", "not-a-colour", "#00A5DE"], FALLBACK), FALLBACK);
});

test("hue words follow the brand's dominant channel", () => {
  assert.match("navy", hueWords("#023b59"));
  assert.match("sky", hueWords("#00a5de"));
  assert.match("olive", hueWords("#6f8f1f"));
  assert.match("burgundy", hueWords("#7a1020"));
  assert.match("gray", hueWords("#888888"));
  assert.doesNotMatch("anything", hueWords("nope"));
});

const theme = (name: string, color: string[], tone: string[] = [], type?: string): GammaTheme =>
  ({ id: name, name, colorKeywords: color, toneKeywords: tone, type });

test("a navy brand ranks a corporate navy theme above a generic light one", () => {
  const icebreaker = theme("Icebreaker", ["light", "blue", "white", "navy"], ["cool", "clean"]);
  const basic = theme("Basic Light", ["light", "blue", "white", "black", "b&w"]);
  const party = theme("Confetti", ["pink", "neon"], ["playful", "fun"]);
  assert.ok(themeScore(icebreaker, "#023b59") > themeScore(basic, "#023b59"));
  assert.ok(themeScore(party, "#023b59") < 0);
});

test("our own custom themes get no bonus on a client's deck", () => {
  const ours = theme("IncentivAI", [], [], "custom");
  const stock = theme("Commons", ["light", "green"], ["professional", "clean"]);
  assert.equal(themeScore(ours, "#6f8f1f"), 0);
  assert.ok(themeScore(stock, "#6f8f1f") > themeScore(ours, "#6f8f1f"));
});
