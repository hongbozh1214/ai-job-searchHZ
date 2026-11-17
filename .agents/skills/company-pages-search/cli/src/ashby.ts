import { robotsCheckPyGate, UA, type NormalizedJob } from './helpers.js'

const BOARDS = new Set(['cradlebio', 'adaptyv', 'basecamp-research'])
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
type Deps = { fetchImpl?: typeof fetch; gate?: (url: string) => Promise<boolean> }
type Coverage = 'partial' | 'valid_empty' | 'blocked' | 'rate_limited' | 'parse_failed' | 'unknown'
type Job = NormalizedJob & { id: string; id_source: 'jobUrl'; published_raw: string | null; date_source: string | null; observed_at: string; description: string | null; description_format: 'html' | 'plain' | null }
type Scan = { jobs: Job[]; coverage: Coverage; reason: string; requests: number; scope: string }

export function ashbyBoard(board: string): string {
  if (!BOARDS.has(board)) throw new Error('ashby_config_error: board not in verified mapping')
  return `https://api.ashbyhq.com/posting-api/job-board/${board}`
}

/** Candidate public-response contract; no live schema/completeness claim. */
export function parseAshbyBoard(company: string, board: string, data: unknown): Scan {
  ashbyBoard(board)
  const result = (jobs: Job[], coverage: Coverage, reason: string): Scan => ({ jobs, coverage, reason, requests: 1, scope: 'listed_jobs_in_single_response' })
  const body = data as Record<string, unknown> | null
  if (!body || !Array.isArray(body.jobs) || body.success === false || body.error || (body.errors && (!Array.isArray(body.errors) || body.errors.length))) return result([], 'parse_failed', 'invalid_board_response')
  const jobs: Job[] = [], seen = new Map<string, string>()
  let invalid = false
  for (const value of body.jobs) {
    if (!value || typeof value !== 'object') { invalid = true; continue }
    const row = value as Record<string, unknown>
    // Do not infer publication/listing permission from a URL or a missing flag.
    if (row.isListed === false) continue
    if (row.isListed !== true || typeof row.title !== 'string' || !row.title.trim() || typeof row.jobUrl !== 'string') { invalid = true; continue }
    let url: URL
    try { url = new URL(row.jobUrl) } catch { invalid = true; continue }
    const parts = url.pathname.split('/').filter(Boolean), id = parts[1]
    if (url.protocol !== 'https:' || url.host !== 'jobs.ashbyhq.com' || url.username || url.password || url.search || url.hash || parts.length !== 2 || parts[0] !== board || !UUID.test(id) || ![`/${board}/${id}`, `/${board}/${id}/`].includes(url.pathname) || (row.id !== undefined && row.id !== id)) { invalid = true; continue }
    const canonical = `${url.origin}/${board}/${id}`
    const fingerprint = JSON.stringify(row)
    if (seen.has(id)) {
      if (seen.get(id) !== fingerprint) return result([], 'parse_failed', 'conflicting_job_identity')
      continue
    }
    seen.set(id, fingerprint)
    const raw = typeof row.publishedAt === 'string' ? row.publishedAt : null
    const dated = raw !== null && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(raw) && Number.isFinite(Date.parse(raw)) && new Date(raw.slice(0,10)).toISOString().slice(0,10) === raw.slice(0,10)
    const hasText = (s: unknown): s is string => typeof s === 'string' && !!s.replace(/<[^>]*>/g, '').replace(/&nbsp;|&#160;|\s/g, '')
    const html = hasText(row.descriptionHtml), plain = hasText(row.descriptionPlain)
    jobs.push({ id, id_source: 'jobUrl', company, title: row.title.trim(), location: typeof row.location === 'string' ? row.location : null, url: canonical, date: dated ? raw.slice(0,10) : null, date_source: dated ? 'publishedAt' : null, published_raw: raw, observed_at: new Date().toISOString(), source_ats: 'ashby', description: html ? row.descriptionHtml as string : plain ? row.descriptionPlain as string : null, description_format: html ? 'html' : plain ? 'plain' : null })
  }
  if (invalid) return result(jobs, jobs.length ? 'partial' : 'parse_failed', 'invalid_listing_identity_or_fields')
  if ('nextCursor' in body || 'nextPage' in body || body.hasMore === true) return result(jobs, 'partial', 'continuation_unverified')
  if (!body.jobs.length) return result([], 'valid_empty', 'empty_response_only_not_board_completeness')
  return result(jobs, 'partial', jobs.length ? 'board_completeness_unverified' : 'no_listed_jobs_in_response')
}

async function readBoard(company: string, board: string, deps: Deps): Promise<Scan> {
  const url = ashbyBoard(board)
  const fail = (coverage: Coverage, reason: string, requests: number): Scan => ({ jobs: [], coverage, reason, requests, scope: 'listed_jobs_in_single_response' })
  try {
    if (await (deps.gate ?? (u => robotsCheckPyGate(u, undefined, undefined, true)))(url) !== true) return fail('unknown', 'robots_permission_unconfirmed', 0)
  } catch { return fail('unknown', 'robots_permission_unconfirmed', 0) }
  let response: Response
  try { response = await (deps.fetchImpl ?? fetch)(url, { headers: { 'User-Agent': UA, Accept: 'application/json' }, redirect: 'manual', credentials: 'omit', signal: AbortSignal.timeout(15000) }) }
  catch { return fail('unknown', 'request_failed', 1) }
  if (response.status >= 300 && response.status < 400) return fail('unknown', 'redirect_unconfirmed', 1)
  if (response.url && response.url !== url) return fail('unknown', 'response_url_unconfirmed', 1)
  if (response.status === 401 || response.status === 403) return fail('blocked', `http_${response.status}`, 1)
  if (response.status === 429) return fail('rate_limited', `retry_after:${response.headers.get('retry-after') ?? 'unknown'}`, 1)
  if (response.status !== 200) return fail('unknown', `http_${response.status}`, 1)
  try { return parseAshbyBoard(company, board, await response.json()) }
  catch { return fail('parse_failed', 'invalid_json_or_response', 1) }
}

export async function fetchAshbyList(company: string, board: string, deps: Deps = {}) {
  const scan = await readBoard(company, board, deps)
  // Do not emit every JD in a list response. Detail uses the same board decoder.
  return { ...scan, jobs: scan.jobs.map(({ description, description_format, ...job }) => job) }
}

export async function fetchAshbyDetail(company: string, board: string, id: string, deps: Deps = {}) {
  if (!UUID.test(id)) throw new Error('ashby_detail_id_invalid')
  const scan = await readBoard(company, board, deps), job = scan.jobs.find(j => j.id === id)
  if (!job) throw new Error(`ashby_detail_id_unconfirmed [${scan.coverage}:${scan.reason}]`)
  if (!job.description) throw new Error('ashby_detail_description_missing')
  return { ...job, detail_coverage: 'response_description_present', coverage: { status: scan.coverage, reason: scan.reason, scope: scan.scope, requests: scan.requests } }
}
