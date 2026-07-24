import { cp, mkdir } from "node:fs/promises";
import { existsSync } from "node:fs";

if (existsSync("data")) {
  await mkdir("dist/data", { recursive: true });
  await cp("data", "dist/data", { recursive: true });
}
