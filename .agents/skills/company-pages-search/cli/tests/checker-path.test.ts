import { test, expect, afterAll } from "bun:test"
import { mkdtempSync, mkdirSync, writeFileSync, symlinkSync, rmSync, realpathSync, copyFileSync, existsSync, readFileSync } from "node:fs"
import { tmpdir } from "node:os"
import path from "node:path"
import { pathToFileURL } from "node:url"
import { resolveRobotsChecker, robotsCheckPyGate, htmlFetch, curlFallback, ROBOTS_CHECK_PY } from "../src/helpers"

const childBun = () => [process.execPath, "--preload", process.env.COMPANY_OFFLINE_PRELOAD!]

const temp = realpathSync(mkdtempSync(path.join(tmpdir(), "checker-path-")))
afterAll(() => rmSync(temp, { recursive: true, force: true }))
const workspace = path.join(temp, "workspace")
const project = path.join(workspace, "ai-job-search")
mkdirSync(path.join(project, "tools"), { recursive: true })
writeFileSync(path.join(project, "company_pages.json"), "[]")
writeFileSync(path.join(project, "tools", "robots_check.py"), "import sys; sys.exit(0)\n")
symlinkSync("ai-job-search/company_pages.json", path.join(workspace, "company_pages.json"))

test("standalone layout preserves original checker", () => {
  expect(resolveRobotsChecker(project, "company_pages.json", project)).toBe(path.join(project, "tools/robots_check.py"))
})
test("workspace registry link locates project checker from both working directories", () => {
  for (const cwd of [workspace, project]) {
    expect(resolveRobotsChecker(workspace, path.join(workspace, "company_pages.json"), cwd)).toBe(path.join(project, "tools/robots_check.py"))
  }
})
test("nested project skill link locates the checker without a registry", () => {
  const root = path.join(temp, "skills-linked-workspace")
  const nested = path.join(root, "ai-job-search")
  mkdirSync(path.join(root, ".agents"), { recursive: true })
  mkdirSync(nested)
  symlinkSync("../.agents", path.join(nested, ".agents"))
  for (const cwd of [root, nested]) {
    expect(resolveRobotsChecker(root, path.join(temp, "unrelated-registry.json"), cwd)).toBe(path.join(nested, "tools/robots_check.py"))
  }
})
test("default gate executes the selected synthetic project checker from both cwd values", () => {
  const source = path.join(workspace, ".agents/skills/company-pages-search/cli/src")
  mkdirSync(source, { recursive: true })
  const helper = path.join(source, "helpers.ts")
  copyFileSync(path.join(import.meta.dir, "../src/helpers.ts"), helper)
  const env = { ...process.env }; delete env.COMPANY_PAGES_REGISTRY
  const code = `import {ROBOTS_CHECK_PY,robotsCheckPyGate} from ${JSON.stringify(pathToFileURL(helper).href)}; console.log(JSON.stringify({path:ROBOTS_CHECK_PY,allowed:await robotsCheckPyGate('https://example.invalid/jobs')}))`
  for (const cwd of [workspace, project]) {
    const result = Bun.spawnSync([...childBun(), "--eval", code], { cwd, env, stdout: "pipe", stderr: "pipe" })
    expect(result.exitCode).toBe(0)
    expect(JSON.parse(result.stdout.toString())).toEqual({ path: path.join(project, "tools/robots_check.py"), allowed: true })
  }
})
test("existing explicit registry override finds exact direct project without the compatibility link", () => {
  rmSync(path.join(workspace, "company_pages.json"))
  try {
    expect(resolveRobotsChecker(workspace, path.join(project, "company_pages.json"), workspace)).toBe(path.join(project, "tools/robots_check.py"))
  } finally {
    symlinkSync("ai-job-search/company_pages.json", path.join(workspace, "company_pages.json"))
  }
})
test("external or missing data registry cannot displace the stable project checker", () => {
  const external = path.join(temp, "external.json")
  writeFileSync(external, "[]")
  for (const registry of [external, path.join(temp, "absent.json")]) {
    expect(resolveRobotsChecker(workspace, registry, project)).toBe(path.join(project, "tools/robots_check.py"))
  }
  const root = path.join(temp, "no-stable-link")
  mkdirSync(root)
  expect(resolveRobotsChecker(root, external, project)).toBe(path.join(root, "tools/robots_check.py"))
})
test("an external child symlink cannot select an external checker", () => {
  const root = path.join(temp, "escape-root")
  const outside = path.join(temp, "outside")
  mkdirSync(root); mkdirSync(outside)
  writeFileSync(path.join(outside, "company_pages.json"), "[]")
  symlinkSync(outside, path.join(root, "ai-job-search"))
  expect(resolveRobotsChecker(root, path.join(root, "ai-job-search/company_pages.json"))).toBe(path.join(root, "tools/robots_check.py"))
})
test("default checker link outside the project cannot execute", () => {
  const root = path.join(temp, "unsafe-root")
  const source = path.join(root, ".agents/skills/company-pages-search/cli/src")
  mkdirSync(source, { recursive: true }); mkdirSync(path.join(root, "tools"))
  const marker = path.join(temp, "external-executed")
  const external = path.join(temp, "external-checker.py")
  writeFileSync(external, `open(${JSON.stringify(marker)}, 'w').write('bad')\n`)
  symlinkSync(external, path.join(root, "tools/robots_check.py"))
  const helper = path.join(source, "helpers.ts")
  copyFileSync(path.join(import.meta.dir, "../src/helpers.ts"), helper)
  const env = { ...process.env }; delete env.COMPANY_PAGES_REGISTRY
  const code = `import {robotsCheckPyGate} from ${JSON.stringify(pathToFileURL(helper).href)}; console.log(JSON.stringify(await robotsCheckPyGate('https://example.invalid/jobs')))`
  const result = Bun.spawnSync([...childBun(), "--eval", code], { cwd: root, env, stdout: "pipe", stderr: "pipe" })
  expect(result.exitCode).toBe(0)
  expect(result.stdout.toString().trim()).toBe("false")
  expect(existsSync(marker)).toBe(false)
})
test("redirect to a denied or unknown target sends no request to that target", async () => {
  const bin = path.join(temp, "mock-bin"); mkdirSync(bin)
  const log = path.join(temp, "mock-requests")
  const curl = path.join(bin, "curl")
  writeFileSync(curl, '#!/bin/sh\nfor arg do last="$arg"; done\nprintf "%s\\n" "$last" >> "$CHECKER_TEST_LOG"\nprintf "\\n__CPS_STATUS__302\\n__CPS_LOCATION__https://target.invalid/jobs"\n', { mode: 0o755 })
  const previousPath = process.env.PATH, previousLog = process.env.CHECKER_TEST_LOG
  process.env.PATH = bin + path.delimiter + previousPath
  process.env.CHECKER_TEST_LOG = log
  try {
    for (const verdict of ["denied", "unknown"]) {
      writeFileSync(log, "")
      const checker = path.join(temp, `redirect-${verdict}.py`)
      writeFileSync(checker, `import sys; sys.exit(${verdict === "denied" ? 1 : 2})\n`)
      const seen: string[] = []
      const result = await curlFallback("https://first.invalid/jobs", async (url) => {
        seen.push(url)
        return url === "https://first.invalid/jobs" ? true : robotsCheckPyGate(url, checker)
      })
      expect(result).toBe("")
      expect(seen).toEqual(["https://first.invalid/jobs", "https://target.invalid/jobs"])
      expect((await Bun.file(log).text()).trim().split("\n")).toEqual(["https://first.invalid/jobs"])
    }
  } finally {
    process.env.PATH = previousPath
    if (previousLog === undefined) delete process.env.CHECKER_TEST_LOG
    else process.env.CHECKER_TEST_LOG = previousLog
  }
})

for (const [name, body, expected] of [
  ["allow", "import sys; sys.exit(0)\n", true],
  ["deny", "import sys; sys.exit(1)\n", false],
  ["unknown", "import sys; sys.exit(2)\n", false],
  ["failure", "raise RuntimeError('fixture')\n", false],
  ["missing", null, false],
] as const) {
  test(`${name} checker controls protected follow-up requests`, async () => {
    const script = path.join(temp, `${name}.py`)
    if (body !== null) writeFileSync(script, body)
    let calls = 0
    const gate = (url: string) => robotsCheckPyGate(url, script)
    const request = htmlFetch("https://example.invalid/jobs", {
      fetchImpl: async () => new Response("", { status: 403 }),
      gate,
      curl: async () => { calls++; return "synthetic body" },
    })
    if (expected) expect(await request).toBe("synthetic body")
    else await expect(request).rejects.toThrow("robots_unconfirmed")
    expect(calls).toBe(expected ? 1 : 0)
  })
}

test('nested CLI child keeps real checker with temporary registry and fails closed on refusal or missing file', () => {
  const root=path.join(temp,'isolated-nested'), project=path.join(root,'ai-job-search'), source=path.join(root,'.agents/skills/company-pages-search/cli/src')
  mkdirSync(source,{recursive:true});mkdirSync(path.join(project,'tools'),{recursive:true})
  writeFileSync(path.join(project,'company_pages.json'),'[]');symlinkSync('ai-job-search/company_pages.json',path.join(root,'company_pages.json'))
  const helper=path.join(source,'helpers.ts'),checker=path.join(project,'tools/robots_check.py'),registry=path.join(temp,'isolated-registry.json'),log=path.join(temp,'real-checker-curl.log')
  copyFileSync(path.join(import.meta.dir,'../src/helpers.ts'),helper);copyFileSync(ROBOTS_CHECK_PY,checker)
  writeFileSync(registry,JSON.stringify([{name:'synthetic fixture',ats:'generic',ats_id:'',careers_url:'https://offline.invalid'}]))
  const env={...process.env,COMPANY_PAGES_REGISTRY:registry,COMPANY_OFFLINE_CURL_LOG:log};delete env.COMPANY_OFFLINE_ROBOTS_FIXTURE
  const code=`import {ROBOTS_CHECK_PY,robotsCheckPyGate,loadRegistry} from ${JSON.stringify(pathToFileURL(helper).href)};let calls=0;const allowed=await robotsCheckPyGate('https://offline.invalid/job',undefined,undefined,true);if(allowed)calls++;console.log(JSON.stringify({path:ROBOTS_CHECK_PY,allowed,calls,names:(await loadRegistry()).map(x=>x.name),preload:process.env.COMPANY_OFFLINE_PRELOAD}));`
  for(const cwd of [root,project]) {
    const result=Bun.spawnSync([...childBun(),'--eval',code],{cwd,env,stdout:'pipe',stderr:'pipe'})
    expect(result.exitCode).toBe(0);const value=JSON.parse(result.stdout.toString())
    expect(value).toEqual({path:checker,allowed:false,calls:0,names:['synthetic fixture'],preload:process.env.COMPANY_OFFLINE_PRELOAD})
    expect(result.stderr.toString()).toContain('ROBOTS_UNCONFIRMED');expect(result.stderr.toString()).not.toContain('ROBOTS_CHECKER_MISSING')
  }
  expect(Bun.file(log).size).toBeGreaterThan(0)
  const beforeLog=readFileSync(log,'utf8');rmSync(checker)
  const missing=Bun.spawnSync([...childBun(),'--eval',code],{cwd:project,env,stdout:'pipe',stderr:'pipe'})
  expect(missing.exitCode).toBe(0);expect(JSON.parse(missing.stdout.toString()).calls).toBe(0);expect(missing.stderr.toString()).toContain('ROBOTS_CHECKER_MISSING');expect(readFileSync(log,'utf8')).toBe(beforeLog)
})
