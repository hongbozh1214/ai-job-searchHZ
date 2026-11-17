import { test, expect } from 'bun:test'
import { mkdtempSync, writeFileSync, readFileSync, existsSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { ashbyBoard, parseAshbyBoard, fetchAshbyList, fetchAshbyDetail } from '../src/ashby'

const id = '11111111-2222-4333-8444-555555555555'
const row = (board = 'adaptyv', extra: Record<string, unknown> = {}) => ({ title: 'Synthetic scientist', jobUrl: `https://jobs.ashbyhq.com/${board}/${id}`, isListed: true, location: 'Fixture city', descriptionHtml: '<p>Synthetic duties.</p><p>Synthetic requirements.</p>', ...extra })

test('listed identities, deduplication, publication source and unknown dates remain explicit', () => {
  const listed = row('adaptyv', { publishedAt: '2026-10-30T12:00:00Z' })
  const result = parseAshbyBoard('Fixture', 'adaptyv', { jobs: [listed, listed, row('adaptyv', { isListed: false })] })
  expect(result.jobs).toHaveLength(1); expect(result.coverage).toBe('partial')
  expect(result.jobs[0]).toMatchObject({ id, id_source: 'jobUrl', date: '2026-10-30', date_source: 'publishedAt' })
  for (const publishedAt of [undefined, 'not-a-date', '2026-02-30T00:00:00Z']) {
    expect(parseAshbyBoard('Fixture', 'adaptyv', { jobs: [row('adaptyv', { publishedAt })] }).jobs[0].date).toBeNull()
  }
})

test('missing, foreign-board or conflicting identity never becomes another job detail', async () => {
  for (const change of [{ jobUrl: undefined }, { jobUrl: 'https://jobs.ashbyhq.com/adaptyv/' }, { jobUrl: `https://jobs.ashbyhq.com/cradlebio/${id}` }, { id: 'wrong' }, { isListed: undefined }]) {
    const data = { jobs: [row('adaptyv', change)] }
    expect(parseAshbyBoard('Fixture', 'adaptyv', data).coverage).toBe('parse_failed')
    await expect(fetchAshbyDetail('Fixture', 'adaptyv', id, { gate: async () => true, fetchImpl: async () => Response.json(data) })).rejects.toThrow('ashby_detail_id_unconfirmed')
  }
  expect(parseAshbyBoard('Fixture', 'adaptyv', { jobs: [row(), row('adaptyv', { title: 'Different' })] }).reason).toBe('conflicting_job_identity')
  await expect(fetchAshbyDetail('Fixture', 'adaptyv', '../other')).rejects.toThrow('ashby_detail_id_invalid')
})

test('empty response is scoped, unlisted-only and unexpected continuation are not complete boards', () => {
  expect(parseAshbyBoard('Fixture', 'adaptyv', { jobs: [] })).toMatchObject({ coverage: 'valid_empty', scope: 'listed_jobs_in_single_response' })
  for (const body of [{}, [], { jobs: [], success: false }, { jobs: [], error: 'denied' }]) expect(parseAshbyBoard('Fixture', 'adaptyv', body).coverage).toBe('parse_failed')
  expect(parseAshbyBoard('Fixture', 'adaptyv', { jobs: [row('adaptyv', { isListed: false })] }).coverage).toBe('partial')
  expect(parseAshbyBoard('Fixture', 'adaptyv', { jobs: [], nextCursor: 'unknown' }).reason).toBe('continuation_unverified')
})

test('detail reuses one board response and missing JD fails without a second request', async () => {
  let requests = 0
  const deps = { gate: async () => true, fetchImpl: async (url: unknown) => { requests++; expect(url).toBe(ashbyBoard('adaptyv')); return Response.json({ jobs: [row()] }) } }
  const detail = await fetchAshbyDetail('Fixture', 'adaptyv', id, deps)
  expect(requests).toBe(1); expect(detail.description).toContain('Synthetic requirements')
  const list = await fetchAshbyList('Fixture', 'adaptyv', deps); expect(list.jobs[0]).not.toHaveProperty('description')
  await expect(fetchAshbyDetail('Fixture', 'adaptyv', id, { ...deps, fetchImpl: async () => Response.json({ jobs: [row('adaptyv', { descriptionHtml: '<p>&nbsp;</p>' })] }) })).rejects.toThrow('ashby_detail_description_missing')
})

test('checker false or unknown prevents fetch; errors, limits and redirects do not become empty', async () => {
  let calls = 0
  for (const gate of [async () => false, async () => { throw Error('checker failed') }]) {
    expect((await fetchAshbyList('Fixture', 'adaptyv', { gate, fetchImpl: async () => { calls++; return Response.json({ jobs: [] }) } })).coverage).toBe('unknown')
  }
  expect(calls).toBe(0)
  for (const [status, expected] of [[403, 'blocked'], [429, 'rate_limited'], [404, 'unknown'], [500, 'unknown'], [302, 'unknown']] as const) {
    calls = 0
    const result = await fetchAshbyList('Fixture', 'adaptyv', { gate: async () => true, fetchImpl: async () => { calls++; return new Response('', { status, headers: { 'retry-after': '60', location: 'https://offline.invalid/' } }) } })
    expect(result.coverage).toBe(expected); expect(calls).toBe(1)
    if (status === 429) expect(result.reason).toBe('retry_after:60')
  }
  expect((await fetchAshbyList('Fixture', 'adaptyv', { gate: async () => true, fetchImpl: async () => new Response('<html>challenge</html>') })).coverage).toBe('parse_failed')
  expect((await fetchAshbyList('Fixture', 'adaptyv', { gate: async () => true, fetchImpl: async () => { throw Error('timeout') } })).coverage).toBe('unknown')
})

async function cli(board: string, mode: 'search' | 'detail', body: unknown, robots = '1', mocked = true, registryBoard = board) {
  const dir = mkdtempSync(path.join(tmpdir(), 'ashby-data-')), registry = path.join(dir, 'registry.json'), responses = path.join(dir, 'responses.json'), log = path.join(dir, 'fetch.log')
  writeFileSync(registry, JSON.stringify([{ name: 'Selected fixture', ats: 'ashby', ats_id: registryBoard, careers_url: `https://jobs.ashbyhq.com/${board}` }]))
  writeFileSync(responses, JSON.stringify(mocked ? { [ashbyBoard(board)]: { body } } : {}))
  try {
    const child = Bun.spawn([process.execPath, 'run', '--preload', process.env.COMPANY_OFFLINE_PRELOAD!, '--preload', path.join(import.meta.dir, 'fixtures/ashby-offline.ts'), path.join(import.meta.dir, '../src/cli.ts'), mode, '--company', 'Selected fixture', ...(mode === 'detail' ? ['--id', id] : []), '--format', 'json'], {
      env: { ...process.env, COMPANY_PAGES_REGISTRY: registry, COMPANY_OFFLINE_ASHBY_RESPONSES: responses, COMPANY_OFFLINE_ASHBY_FETCH_LOG: log, COMPANY_OFFLINE_ASHBY_ROBOTS_FIXTURE: robots }, stdout: 'pipe', stderr: 'pipe',
    })
    const stdout = await new Response(child.stdout).text(), stderr = await new Response(child.stderr).text(), exit = await child.exited
    return { stdout, stderr, exit, requests: existsSync(log) ? readFileSync(log, 'utf8').trim().split('\n') : [] }
  } finally { rmSync(dir, { recursive: true, force: true }) }
}

for (const board of ['cradlebio', 'adaptyv', 'basecamp-research']) test(`${board}: real CLI children use strict checker and exact synthetic board fixture`, async () => {
  const body = { jobs: [row(board), row(board)] }
  const search = await cli(board, 'search', body), detail = await cli(board, 'detail', body)
  expect(search.exit).toBe(0); expect(search.stderr).toBe(''); expect(detail.exit).toBe(0); expect(detail.stderr).toBe('')
  const result = JSON.parse(search.stdout), job = JSON.parse(detail.stdout)
  expect(result.results).toHaveLength(1); expect(result.meta.coverage[0]).toMatchObject({ status: 'partial', scope: 'listed_jobs_in_single_response' })
  expect(result.results[0]).toMatchObject({ id, date: null, source_ats: 'ashby' }); expect(job).toMatchObject({ id, url: `https://jobs.ashbyhq.com/${board}/${id}`, date: null, description: row(board).descriptionHtml })
  expect(search.requests).toEqual([ashbyBoard(board)]); expect(detail.requests).toEqual([ashbyBoard(board)])
})

test('real CLI checker deny and default refusal do not reach the response preload', async () => {
  for (const robots of ['deny', '']) {
    const result = await cli('adaptyv', 'search', { jobs: [row()] }, robots)
    expect(result.exit).toBe(0); expect(result.requests).toHaveLength(0)
    expect(JSON.parse(result.stdout).meta.coverage[0]).toMatchObject({ status: 'unknown', reason: 'robots_permission_unconfirmed', requests: 0 })
    expect(result.stderr).toContain('ROBOTS_UNCONFIRMED')
  }
})

test('CLI identity error is explicit, and empty and malformed envelopes remain different', async () => {
  const bad = await cli('adaptyv', 'detail', { jobs: [row('cradlebio')] })
  expect(bad.exit).toBe(1); expect(bad.stderr).toContain('ashby_detail_id_unconfirmed')
  const empty = await cli('adaptyv', 'search', { jobs: [] }), malformed = await cli('adaptyv', 'search', { error: 'fixture error' })
  expect(JSON.parse(empty.stdout).meta.coverage[0].status).toBe('valid_empty')
  expect(JSON.parse(malformed.stdout).meta.coverage[0].status).toBe('parse_failed')
})


test('CLI preserves configuration errors and explicitly denies an unmocked board response', async () => {
  const invalid = await cli('adaptyv', 'search', { jobs: [] }, '1', true, 'not-a-verified-board')
  expect(invalid.requests).toHaveLength(0)
  expect(JSON.parse(invalid.stdout).meta.errors[0].error).toContain('ashby_config_error')
  const unmapped = await cli('adaptyv', 'search', { jobs: [] }, '1', false)
  expect(JSON.parse(unmapped.stdout).meta.coverage[0]).toMatchObject({ status: 'unknown', reason: 'request_failed' })
  expect(unmapped.requests).toEqual([ashbyBoard('adaptyv'), 'OFFLINE_UNMOCKED_FETCH_DENIED'])
})
