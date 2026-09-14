import { writeFile } from "node:fs/promises";
import sharp from "sharp";

const source = new URL("../public/brand/worktrace-mark.svg", import.meta.url);
const sizes = [16, 32, 48];
const frames = await Promise.all(sizes.map(size => sharp(source.pathname).resize(size, size).png().toBuffer()));
const header = Buffer.alloc(6 + frames.length * 16);
header.writeUInt16LE(1, 2);
header.writeUInt16LE(frames.length, 4);
let offset = header.length;
// Each ICO directory entry points to one PNG frame of the canonical SVG mark.
frames.forEach((frame, index) => {
  const entry = 6 + index * 16;
  header[entry] = sizes[index];
  header[entry + 1] = sizes[index];
  header.writeUInt16LE(1, entry + 4);
  header.writeUInt16LE(32, entry + 6);
  header.writeUInt32LE(frame.length, entry + 8);
  header.writeUInt32LE(offset, entry + 12);
  offset += frame.length;
});
await writeFile(new URL("../public/favicon.ico", import.meta.url), Buffer.concat([header, ...frames]));
await sharp(source.pathname).resize(180, 180).png().toFile(new URL("../public/apple-touch-icon.png", import.meta.url).pathname);
console.log("Generated favicon.ico (16/32/48px) and apple-touch-icon.png (180px).");
