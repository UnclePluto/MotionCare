import { copyFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const repoRoot = join(__dirname, "..", "..");
const src = join(repoRoot, "specs", "patient-rehab-system", "crf", "registry.v1.json");
const dest = join(__dirname, "..", "src", "crf", "registry.v1.json");
mkdirSync(dirname(dest), { recursive: true });
copyFileSync(src, dest);
console.log("synced", dest);
