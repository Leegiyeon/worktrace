import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";
import test from "node:test";
import ts from "typescript";

const read = path => readFileSync(new URL(`../${path}`, import.meta.url));

test("header and login use the same mark with stable dimensions and favicon metadata", () => {
  for (const path of ["app/components/AppLogo.tsx", "app/login/page.tsx"]) {
    const source = read(path).toString();
    assert.match(source, /src="\/brand\/worktrace-mark.svg"/);
    assert.match(source, /width=\{\d+\} height=\{\d+\} alt=""/);
  }
  const metadata = read("app/layout.tsx").toString();
  for (const asset of ["/brand/worktrace-mark.svg", "/favicon.ico", "/apple-touch-icon.png"]) assert.ok(metadata.includes(asset));
});

test("generated ICO contains real 16 32 and 48px PNG frames and Apple icon is 180px", () => {
  const ico = read("public/favicon.ico");
  assert.equal(ico.readUInt16LE(0), 0);
  assert.equal(ico.readUInt16LE(2), 1);
  assert.equal(ico.readUInt16LE(4), 3);
  for (const [index, size] of [16,32,48].entries()) {
    const entry = 6 + index * 16, offset = ico.readUInt32LE(entry + 12), length = ico.readUInt32LE(entry + 8);
    assert.equal(ico[entry], size);
    assert.ok(offset + length <= ico.length);
    assert.equal(ico.subarray(offset+1, offset+4).toString(), "PNG");
    assert.equal(ico.readUInt32BE(offset+16), size);
    assert.equal(ico.readUInt32BE(offset+20), size);
  }
  const apple = read("public/apple-touch-icon.png");
  assert.equal(apple.readUInt32BE(16), 180);
  assert.equal(apple.readUInt32BE(20), 180);
});

test("production serves only explicit public brand assets without unlocking pages or APIs", async () => {
  const compiled = ts.transpileModule(read("proxy.ts").toString(), {compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText;
  const exports = {};
  runInNewContext(compiled, {exports, process:{env:{NODE_ENV:"production"}}, URL,
    require:()=>({NextResponse:{next:()=>({status:200}),json:(_, init)=>init,redirect:()=>({status:307})}})});
  for (const path of ["/brand/worktrace-mark.svg", "/apple-touch-icon.png", "/favicon.ico", "/projects", "/api/projects", "/brand/private"]) {
    const request = {nextUrl:{pathname:path},url:`https://worktrace.cloud${path}`,cookies:{get:()=>undefined}};
    const response = await exports.proxy(request);
    assert.equal(response.status, path==="/api/projects"?401:path==="/projects"||path==="/brand/private"?307:200);
  }
});
