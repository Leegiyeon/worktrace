import { execFileSync } from "node:child_process";
import { randomBytes, scryptSync } from "node:crypto";

if (!process.stdin.isTTY) {
  console.error("Run this command in an interactive terminal.");
  process.exit(2);
}

process.stdout.write("Password (12+ characters): ");
execFileSync("stty", ["-echo"]);
let password = "";
try {
  for await (const chunk of process.stdin) {
    password += chunk.toString();
    if (password.includes("\n")) break;
  }
} finally {
  execFileSync("stty", ["echo"]);
  process.stdout.write("\n");
}
password = password.replace(/[\r\n]+$/, "");
if (password.length < 12) {
  console.error("Password must contain at least 12 characters.");
  process.exit(2);
}

const salt = randomBytes(16).toString("hex");
const hash = scryptSync(password, salt, 64).toString("hex");
console.log(`scrypt$${salt}$${hash}`);
