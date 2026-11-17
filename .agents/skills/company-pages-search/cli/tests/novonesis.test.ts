import { test, expect } from 'bun:test'
import { mkdtempSync, writeFileSync, readFileSync, existsSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'

// Synthetic IDs/text only. Real CLI + default strict Python checker, no gate seam.
const host = 'https://novonesis.wd103.myworkdayjobs.com'
const board = host + '/en-US/Novonesis_Careers'
const api = host + '/wday/cxs/novonesis/Novonesis_Careers'
const rawId = 'R77001-1', externalPath = '/job/Fixture-City/Synthetic-scientist_' + rawId
const description = '<h2>Responsibilities</h2><p>Synthetic fixture duties.</p><h2>Requirements</h2><p>Synthetic fixture requirements.</p>'
const firstKey = `POST ${api}/jobs offset=0`, secondKey = `POST ${api}/jobs offset=20`, detailKey = `GET ${api}${externalPath}`
const posting = (id: string) => ({ title: 'Synthetic scientist', externalPath: '/job/Fixture-City/Synthetic-scientist_' + id, bulletFields: [id.replace(/-\d+$/, '')], locationsText: 'Fixture City' })
const firstRows = [posting(rawId), posting('R77001-2'), ...Array.from({ length: 18 }, (_, i) => posting('R' + (77002 + i)))]
const responses = () => ({
  [firstKey]: { body: { total: 100, jobPostings: firstRows } },
  [secondKey]: { body: { total: 0, jobPostings: [firstRows[0], posting('R77020')] } },
  [detailKey]: { body: { jobPostingInfo: { jobReqId: 'R77001', externalUrl: board + externalPath, jobDescription: description } } },
})

async function cli(mode: 'search' | 'detail', robots = '1', data: Record<string, unknown> = responses(), query?: string) {
  const dir = mkdtempSync(path.join(tmpdir(), 'novonesis-data-'))
  const registry = path.join(dir, 'registry.json'), body = path.join(dir, 'responses.json'), fetchLog = path.join(dir, 'fetch.log'), curlLog = path.join(dir, 'curl.log')
  writeFileSync(registry, JSON.stringify([{ name: 'Novonesis', ats: 'workday', ats_id: '', careers_url: host + '/Novonesis_Careers' }]))
  writeFileSync(body, JSON.stringify(data))
  try {
    const child = Bun.spawn([process.execPath, 'run', '--preload', process.env.COMPANY_OFFLINE_PRELOAD!, '--preload', path.join(import.meta.dir, 'fixtures/novonesis-offline.ts'), path.join(import.meta.dir, '../src/cli.ts'), mode, '--company', 'Novonesis', ...(mode === 'detail' ? ['--id', rawId] : []), ...(query === undefined ? [] : ['--query', query]), '--format', 'json'], {
      env: { ...process.env, COMPANY_PAGES_REGISTRY: registry, COMPANY_OFFLINE_NOVONESIS_RESPONSES: body, COMPANY_OFFLINE_NOVONESIS_FETCH_LOG: fetchLog, COMPANY_OFFLINE_CURL_LOG: curlLog, COMPANY_OFFLINE_NOVONESIS_ROBOTS_FIXTURE: robots }, stdout: 'pipe', stderr: 'pipe',
    })
    const stdout = await new Response(child.stdout).text(), stderr = await new Response(child.stderr).text(), exit = await child.exited
    return { stdout, stderr, exit, requests: existsSync(fetchLog) ? readFileSync(fetchLog, 'utf8').trim().split('\n').map(s => JSON.parse(s)) : [], checkerCalls: existsSync(curlLog) ? readFileSync(curlLog, 'utf8').trim().split('\n').length : 0 }
  } finally { rmSync(dir, { recursive: true, force: true }) }
}

test('Novonesis CLI search: two pages, total=0 nonempty, dedup and unknown dates survive', async () => {
  const r = await cli('search'), data = JSON.parse(r.stdout)
  expect(r.exit).toBe(0); expect(r.stderr).toBe('')
  expect(r.requests.map(x => x.key)).toEqual([firstKey, secondKey]); expect(r.checkerCalls).toBe(2)
  expect(data.results).toHaveLength(21); expect(new Set(data.results.map((x: any) => x.id)).size).toBe(21)
  expect(data.results.slice(0, 2).map((x: any) => x.id)).toEqual(['R77001-1', 'R77001-2'])
  expect(data.results[0].url).not.toBe(data.results[1].url)
  expect(data.results.every((x: any) => x.company === 'Novonesis' && x.date === null && x.date_source === null)).toBe(true)
  expect(data.meta.coverage[0]).toMatchObject({ company: 'Novonesis', status: 'partial', reason: 'short_before_initial_total', requests: 2 })
  expect(data.meta.errors).toEqual([])
})

test('Novonesis CLI detail: real checker gates both list pages and exact same-ID JD', async () => {
  const r = await cli('detail'), data = JSON.parse(r.stdout)
  expect(r.exit).toBe(0); expect(r.stderr).toBe(''); expect(r.checkerCalls).toBe(3)
  expect(r.requests.map(x => x.key)).toEqual([firstKey, secondKey, detailKey])
  expect(data).toMatchObject({ id: rawId, company: 'Novonesis', title: 'Synthetic scientist', url: board + externalPath, date: null, description, detail_coverage: 'jobDescription_present' })
})

test('CLI plain multi-word title filter is literal; quotes and OR cannot silently broaden it', async () => {
  for (const [query, count] of [['synthetic scientist', 21], ['"synthetic scientist"', 0], ['synthetic OR scientist', 0], ['site:example.test synthetic', 0]] as const) {
    const r = await cli('search', '1', responses(), query), data = JSON.parse(r.stdout)
    expect(r.exit).toBe(0); expect(r.checkerCalls).toBe(2)
    expect(r.requests.map(x => x.key)).toEqual([firstKey, secondKey])
    expect(data.results).toHaveLength(count)
    expect(data.meta.coverage[0]).toMatchObject({ status:'partial', reason:'short_before_initial_total' })
    expect(data.meta.errors).toEqual([])
    expect(data.results.every((x: any) => x.date === null && x.date_source === null)).toBe(true)
  }
})

test('curl fixture is opt-in and exact; IFF and URL variants remain denied', async () => {
  const stub = path.join(path.dirname(process.env.COMPANY_OFFLINE_PRELOAD!), 'curl')
  for (const [url, mode, expected] of [[host + '/robots.txt', '', 97], ['https://iff.wd5.myworkdayjobs.com/robots.txt', '1', 97], [host + '/robots.txt?other=1', '1', 97], [host + '/robots.txt', '1', 0]] as const) {
    const p = Bun.spawn([stub, url], { env: { ...process.env, COMPANY_OFFLINE_NOVONESIS_ROBOTS_FIXTURE: mode }, stdout: 'pipe', stderr: 'pipe' })
    const stdout = await new Response(p.stdout).text(), stderr = await new Response(p.stderr).text()
    expect(await p.exited).toBe(expected)
    if (expected === 97) expect(stderr).toContain('OFFLINE_CURL_DENIED')
    else expect(stdout).toContain('Allow: /')
  }
})

test('real checker denial and unknown never reach the response preload', async () => {
  for (const mode of ['deny', '']) {
    const r = await cli('search', mode), data = JSON.parse(r.stdout)
    expect(r.exit).toBe(0); expect(r.checkerCalls).toBe(1); expect(r.requests).toEqual([])
    expect(data.results).toEqual([]); expect(data.meta.coverage[0]).toMatchObject({ status: 'unknown', reason: 'robots_permission_unconfirmed' })
    expect(r.stderr).toContain('ROBOTS_UNCONFIRMED')
  }
})

test('unmocked list, mismatched detail identity and missing JD fail explicitly', async () => {
  const missing = responses(); delete (missing as Record<string, unknown>)[firstKey]
  const denied = await cli('search', '1', missing)
  expect(JSON.parse(denied.stdout).meta.coverage[0]).toMatchObject({ status: 'unknown', reason: 'request_failed' })
  expect(denied.requests).toHaveLength(1); expect(denied.requests[0].fixture).toBe(false)
  for (const [info, error] of [[{ jobReqId: 'R99999', jobDescription: description }, 'detail_identity_mismatch'], [{ jobReqId: 'R77001', jobDescription: '' }, 'detail_jd_missing']] as const) {
    const data = responses(); data[detailKey] = { body: { jobPostingInfo: { externalUrl: board + externalPath, ...info } } }
    const r = await cli('detail', '1', data)
    expect(r.exit).toBe(1); expect(r.stdout).toBe(''); expect(r.stderr).toContain(error)
    expect(r.requests).toHaveLength(3); expect(r.checkerCalls).toBe(3)
  }
})
