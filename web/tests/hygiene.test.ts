import { test } from "node:test"
import assert from "node:assert/strict"
import { readFileSync, readdirSync, statSync } from "node:fs"
import { join } from "node:path"

const ROOT = new URL("..", import.meta.url).pathname
const SOURCE_DIRS = ["app", "components", "lib"]
const BANNED_DEPS = ["cn", "@vercel/analytics"]

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const p = join(dir, name)
    if (statSync(p).isDirectory()) return sourceFiles(p)
    return /\.(ts|tsx)$/.test(name) ? [p] : []
  })
}

test("no source file imports the npm package 'cn'", () => {
  const offenders = SOURCE_DIRS.flatMap((d) => sourceFiles(join(ROOT, d))).filter((f) =>
    /from\s+["']cn["']/.test(readFileSync(f, "utf8")),
  )
  assert.deepEqual(offenders, [])
})

test("banned packages are not dependencies", () => {
  const pkg = JSON.parse(readFileSync(join(ROOT, "package.json"), "utf8"))
  const deps = { ...pkg.dependencies, ...pkg.devDependencies }
  assert.deepEqual(BANNED_DEPS.filter((d) => d in deps), [])
})
