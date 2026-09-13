import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (path) => readFileSync(new URL(`../${path}`, import.meta.url), "utf8");

const layout = read("app/layout.tsx");
const overflowStyles = read("app/ui-overflow-fixes.css");
const verificationPage = read("app/verifications/page.tsx");

test("responsive overflow hardening is loaded globally", () => {
  assert.match(layout, /ui-overflow-fixes\.css/);
  assert.match(overflowStyles, /overflow-x:\s*clip/);
  assert.match(overflowStyles, /\.app-nav[\s\S]*?overflow-x:\s*auto/);
  assert.match(overflowStyles, /button,[\s\S]*?white-space:\s*normal/);
  assert.match(overflowStyles, /\.dense-list-row,[\s\S]*?grid-template-columns:\s*minmax\(0,\s*1fr\)/);
});

test("goals milestone rows reflow before they can overlap", () => {
  assert.match(overflowStyles, /\.project-page \.dense-list > article > \.dense-list-row/);
  assert.match(overflowStyles, /@media \(max-width:\s*900px\)/);
  assert.match(overflowStyles, /@media \(max-width:\s*640px\)/);
});

test("verification center marks shrink-safe responsive surfaces", () => {
  assert.match(verificationPage, /verification-page/);
  assert.match(verificationPage, /verification-project-panel/);
  assert.match(verificationPage, /verification-card/);
  assert.match(verificationPage, /verification-review/);
  assert.match(verificationPage, /verification-actions/);
  assert.match(overflowStyles, /\.verification-card/);
  assert.match(overflowStyles, /\.verification-actions/);
});
