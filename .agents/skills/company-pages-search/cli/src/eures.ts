import { robotsCheckPyGate, UA, type NormalizedJob } from './helpers.js'

export const EURES_SEARCH = 'https://europa.eu/eures/api/jv-searchengine/public/jv-search/search'
const DETAIL = 'https://europa.eu/eures/api/jv-searchengine/public/jv/id/'
const MAX_BYTES = 2 * 1024 * 1024
type Deps = { fetchImpl?: typeof fetch; gate?: (url: string) => Promise<boolean> }
type Status = 'partial' | 'valid_empty' | 'blocked' | 'rate_limited' | 'parse_failed' | 'unknown'
type Lead = NormalizedJob & { portal: 'eures'; canonical_url: null; url_kind: 'unverified_api_detail_reference'; needs_detail: true; date_source: null; observed_at: string }
type Scan = { jobs: Lead[]; coverage: Status; reason: string; errors: string[]; requests: number; received_count: number | null; total_jobs: number | null; total_pages: null; retry_after: string | null }
const fail = (coverage: Status, reason: string, requests: number, retry_after: string | null = null): Scan => ({ jobs: [], coverage, reason, errors: [reason], requests, received_count: null, total_jobs: null, total_pages: null, retry_after })

/** EVERYWHERE is bound to the official keyword enum and a bounded real POST.
 * Country codes remain unconfirmed; location/limit are only output filters. */
export function euresBody(query?: string) {
  if (query !== undefined && (typeof query !== 'string' || !query.trim() || query.trim().length > 200 || /[\x00-\x1f\x7f]/.test(query))) throw Error('invalid_eures_keyword')
  return { page: 1, resultsPerPage: 10, sortSearch: 'BEST_MATCH', keywords: query === undefined ? [] : [{ keyword: query.trim(), specificSearchCode: 'EVERYWHERE' }], minNumberPost: null, requestLanguage: 'en', sessionId: Math.random().toString(36).substring(2) + Math.random().toString(36).substring(2) }
}

export function parseEuresList(value: unknown): Scan {
  const body = value as Record<string, unknown> | null
  if (!body || Array.isArray(body) || typeof body !== 'object' || !Array.isArray(body.jvs) || !Number.isSafeInteger(body.numberRecords) || (body.numberRecords as number) < 0 || body.success === false || body.error || body.errorMessage || body.errorType || (body.errors && (!Array.isArray(body.errors) || body.errors.length))) return fail('parse_failed', 'invalid_list_envelope', 1)
  const scan: Scan = { jobs: [], coverage: 'partial', reason: 'one_unfiltered_page_provisional_leads', errors: [], requests: 1, received_count: body.jvs.length, total_jobs: body.numberRecords as number, total_pages: null, retry_after: null }
  if (!body.jvs.length) return scan.total_jobs === 0
    ? { ...scan, coverage: 'valid_empty', reason: 'explicit_empty_this_query_page_only' }
    : { ...scan, coverage: 'unknown', reason: 'empty_page_with_nonzero_total', errors: ['inconsistent_page_counts'] }
  if (body.jvs.length > 10) return { ...scan, coverage: 'unknown', reason: 'response_page_budget_exceeded', errors: ['response_page_budget_exceeded'] }
  const jobs = new Map<string, Lead>(), conflicts = new Set<string>(), observed_at = new Date().toISOString()
  for (const [index, value] of body.jvs.entries()) {
    const row = value as Record<string, unknown> | null
    if (!row || typeof row.id !== 'string' || !row.id || row.id.length > 512 || /[\s\x00-\x1f\x7f]/.test(row.id) || ['.', '..'].includes(row.id) || typeof row.title !== 'string' || !row.title.trim()) { scan.errors.push(`invalid_record_identity:${index}`); continue }
    let url: string
    try { url = DETAIL + encodeURIComponent(row.id) + '?requestLang=en&preferredLang=en' }
    catch { scan.errors.push(`invalid_record_identity:${index}`); continue }
    const title = row.title.trim(), prior = jobs.get(row.id)
    if (prior && prior.title !== title) { jobs.delete(row.id); conflicts.add(row.id); scan.errors.push(`conflicting_id_identity:${index}`); continue }
    if (conflicts.has(row.id)) continue
    // Employer/location/date/body types and their provenance were not retained
    // in the real probe. Do not infer them from a synthetic fixture or portal name.
    jobs.set(row.id, { id: row.id, title, company: '', location: null, date: null, date_source: null, url, url_kind: 'unverified_api_detail_reference', canonical_url: null, needs_detail: true, observed_at, source_ats: 'generic', portal: 'eures' })
  }
  scan.jobs = [...jobs.values()]
  if (!scan.jobs.length) return { ...scan, coverage: 'parse_failed', reason: 'no_valid_id_title', errors: [...scan.errors, 'no_valid_id_title'] }
  scan.errors.push('provisional_leads_require_employer_canonical_link_and_JD_verification')
  if (scan.total_jobs! < body.jvs.length) scan.errors.push('nonempty_rows_inconsistent_declared_total')
  return scan
}

/** Module-local transport for observed API routes and the explicitly selected
 * BA page; every request independently uses the real strict checker. */
async function requestEures(url: string, deps: Deps, criteria?: ReturnType<typeof euresBody>, html = false): Promise<{ data?: unknown; html?: string; error?: Scan }> {
  const error = (coverage: Status, reason: string, requests: number, retry_after: string | null = null) => ({ error: fail(coverage, reason, requests, retry_after) })
  try { if (await (deps.gate ?? (u => robotsCheckPyGate(u, undefined, undefined, true)))(url) !== true) return error('unknown', 'robots_permission_unconfirmed', 0) }
  catch { return error('unknown', 'robots_permission_unconfirmed', 0) }
  let response: Response
  try { response = await (deps.fetchImpl ?? fetch)(url, { method: criteria ? 'POST' : 'GET', headers: { 'User-Agent': UA, Accept: html ? 'text/html' : 'application/json', ...(criteria ? { 'Content-Type': 'application/json' } : {}) }, ...(criteria ? { body: JSON.stringify(criteria) } : {}), credentials: 'omit', redirect: 'manual', signal: AbortSignal.timeout(15000) }) }
  catch { return error('unknown', 'request_failed', 1) }
  const discard = () => { void response.body?.cancel().catch(() => {}) }
  if (response.url && response.url !== url) { discard(); return error('unknown', 'unexpected_response_url', 1) }
  if (response.status !== 200) { discard(); return error(response.status === 401 || response.status === 403 ? 'blocked' : response.status === 429 ? 'rate_limited' : 'unknown', `http_${response.status}`, 1, response.status === 429 ? response.headers.get('retry-after') : null) }
  if (!(html ? /\btext\/html\b/i : /\bapplication\/(?:[\w.-]+\+)?json\b/i).test(response.headers.get('content-type') ?? '')) { discard(); return error('parse_failed', 'unexpected_content_type', 1) }
  if (Number(response.headers.get('content-length')) > MAX_BYTES) { discard(); return error('unknown', 'body_budget_exhausted', 1) }
  const reader = response.body?.getReader()
  if (!reader) return error('parse_failed', 'missing_body', 1)
  let bytes = 0, text = ''; const decoder = new TextDecoder()
  try {
    while (true) {
      const { done, value } = await reader.read(); if (done) break
      bytes += value.byteLength
      if (bytes > MAX_BYTES) { await reader.cancel(); return error('unknown', 'body_budget_exhausted', 1) }
      text += decoder.decode(value, { stream: true })
    }
    text += decoder.decode()
  } catch { return error('unknown', 'body_read_failed', 1) }
  if (html) return /<title[^>]*>[^<]*(?:captcha|access denied|just a moment|forbidden)/i.test(text) ? error('blocked', 'challenge', 1) : { html: text }
  try { return { data: JSON.parse(text) } } catch { return error('parse_failed', 'invalid_json', 1) }
}

export async function fetchEuresList(deps: Deps = {}, query?: string): Promise<Scan> {
  let criteria: ReturnType<typeof euresBody>
  try { criteria = euresBody(query) } catch { return fail('unknown', 'invalid_eures_keyword', 0) }
  const response = await requestEures(EURES_SEARCH, deps, criteria)
  if (response.error) return response.error
  const scan = parseEuresList(response.data)
  return query !== undefined && scan.coverage === 'partial' ? { ...scan, reason: 'one_server_keyword_page_provisional_leads' } : scan
}

export function euresDetailUrl(id: string): string {
  if (typeof id !== 'string' || !id || id.length > 512 || /[\s\x00-\x1f\x7f]/.test(id) || ['.', '..'].includes(id)) throw Error('invalid_eures_id')
  return DETAIL + encodeURIComponent(id) + '?requestLang=en&preferredLang=en'
}

/** Preserve the complete provided field, without claiming it is a complete JD.
 * Raw response ID is mandatory; API URL/title agreement cannot replace it. */
export function parseEuresDetail(value: unknown, selected: { id: string; title?: string }): Record<string, unknown> {
  const url = euresDetailUrl(selected.id), data = value as Record<string, any> | null
  if (!data || typeof data !== 'object' || Array.isArray(data) || data.id !== selected.id || data.error || data.errorMessage || data.errorType || (data.errors && (!Array.isArray(data.errors) || data.errors.length)) || data.success === false) throw Error('eures_detail_identity_or_envelope_unconfirmed')
  const profiles = data.jvProfiles
  if (!profiles || typeof profiles !== 'object' || Array.isArray(profiles)) throw Error('eures_detail_profile_missing')
  const languages = Object.keys(profiles), language = languages.includes(data.preferredLanguage) ? data.preferredLanguage : languages.length === 1 ? languages[0] : null
  if (!language) throw Error('eures_detail_profile_ambiguous')
  const profile = profiles[language]
  if (!profile || typeof profile.title !== 'string' || !profile.title.trim() || (selected.title !== undefined && profile.title.trim() !== selected.title.trim())) throw Error('eures_detail_title_unconfirmed')
  if (typeof profile.description !== 'string' || !profile.description.trim()) throw Error('eures_detail_body_missing')
  if (typeof profile.employer?.name !== 'string' || !profile.employer.name.trim()) throw Error('eures_detail_employer_missing')
  const locations = Array.isArray(profile.locations) ? profile.locations.map((v: any) => [v?.cityName, v?.countryCode].filter(s => typeof s === 'string' && s.trim()).join(', ')).filter(Boolean) : []
  return { id: selected.id, title: profile.title.trim(), company: profile.employer.name.trim(), location: [...new Set(locations)].join('; ') || null, description: profile.description, language, url, source_ats: 'generic', portal: 'eures', date: null, date_source: null, canonical_url: null, url_kind: 'official_api_detail', needs_detail: true, body_coverage: 'provided_description_field_read', JD_completeness: 'unverified', identity: 'response_id_matches_requested_raw_ID', title_crosscheck: selected.title === undefined ? 'not_performed' : 'matched', source_title: profile.title, source_description: profile.description, source_id: selected.id, source_api_url: url, observed_at: new Date().toISOString() }
}

/** Only select an explicitly supplied BA posting whose path binds the exact
 * reference. The expected path is a validator, never a constructed fallback. */
export function euresBaOriginal(value: unknown, language: string): { url: string; reference: string } | null {
  const data = value as any, reference = data?.reference, instructions = data?.jvProfiles?.[language]?.applicationInstructions
  if (typeof reference !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9_.-]{0,199}$/.test(reference) || !Array.isArray(instructions)) return null
  const found = new Set<string>()
  for (const instruction of instructions) {
    if (typeof instruction !== 'string') continue
    for (const literal of instruction.replace(/&amp;/g, '&').match(/https?:\/\/[^\s<>"']+/g) ?? []) {
      let u: URL
      try { u = new URL(literal.replace(/[.,);\]]+$/g, '')) } catch { continue }
      if (u.protocol !== 'https:' || u.hostname !== 'www.arbeitsagentur.de' || u.port || u.username || u.password || u.search || u.hash) continue
      if (!u.pathname.startsWith('/jobsuche/jobdetail/')) continue
      if (u.pathname !== '/jobsuche/jobdetail/' + encodeURIComponent(reference)) throw Error('eures_original_reference_mismatch')
      found.add(u.href)
    }
  }
  if (found.size > 1) throw Error('eures_original_link_ambiguous')
  return found.size ? { url: [...found][0], reference } : null
}

/** The original page owns title/description. Do not splice it with the feed
 * description or delete ordinary hyphens to force cross-source equality. */
export async function parseEuresBaOriginal(html: string, original: { url: string; reference: string }, apiJob: Record<string, any>) {
  const canonical: string[] = [], objects: any[] = []; let script = ''
  await new HTMLRewriter()
    .on('link[rel~="canonical"]', { element(e) { const href = e.getAttribute('href'); try { canonical.push(href?.trim() ? new URL(href, original.url).href : 'invalid') } catch { canonical.push('invalid') } } })
    .on('script[type="application/ld+json"]', { element(e) {
      script = ''; e.onEndTag(() => {
        let data: any
        try { data = JSON.parse(script) } catch { throw Error('eures_original_jsonld_parse_failed') }
        for (const item of Array.isArray(data) ? data : [data]) { objects.push(item); if (Array.isArray(item?.['@graph'])) objects.push(...item['@graph']) }
      })
    }, text(t) { script += t.text } })
    .transform(new Response(html)).text()
  const posts = objects.filter(x => x && (x['@type'] === 'JobPosting' || Array.isArray(x['@type']) && x['@type'].includes('JobPosting')))
  if (canonical.length !== 1 || canonical[0] !== original.url || posts.length !== 1) throw Error('eures_original_identity_ambiguous')
  const post = posts[0], identifier = typeof post.identifier === 'string' ? post.identifier : post.identifier?.value
  if (identifier !== original.reference || post.url !== original.url) throw Error('eures_original_identity_mismatch')
  const normal = (s: string) => s.replace(/\s+/g, ' ').trim()
  if (typeof post.title !== 'string' || !normal(post.title)) throw Error('eures_original_title_missing')
  const title = normal(post.title), discovery = normal(apiJob.title)
  const suffix = discovery.startsWith(title) ? discovery.slice(title.length) : ''
  // This observed publisher relation is corroborative, never a replacement
  // for exact response ID + exact external reference + canonical + post.url.
  const titleRelation = discovery === title ? 'equal' : /^ \([^()\r\n]{1,120}\)$/.test(suffix) ? 'canonical_title_plus_feed_classification' : null
  if (!titleRelation) throw Error('eures_original_title_unconfirmed')
  if (typeof post.hiringOrganization?.name !== 'string' || normal(post.hiringOrganization.name).toLowerCase() !== normal(apiJob.company).toLowerCase()) throw Error('eures_original_employer_unconfirmed')
  if (typeof post.description !== 'string' || !post.description.trim()) throw Error('eures_original_body_missing')
  let visible = ''
  await new HTMLRewriter().on('script,style,noscript', { element(e) { e.remove() } }).onDocument({ text(t) { visible += t.text } }).transform(new Response(post.description)).text()
  if (!/\b(?:aufgaben|tätigkeiten|responsibilities|duties)\b/i.test(visible) || !/\b(?:anforderungen|ihr\s+profil|dein\s+profil|qualifikationen|requirements|qualifications)\b/i.test(visible)) throw Error('eures_original_JD_sections_unconfirmed')
  return { ...apiJob, title, company: post.hiringOrganization.name.trim(), description: post.description, url: original.url, canonical_url: original.url, url_kind: 'canonical_source_posting', needs_detail: false, JD_completeness: 'canonical_JobPosting_description_read', body_coverage: 'original_JobPosting_description_read', identity: 'EURES_response_id_and_BA_reference_canonical_JobPosting', canonical_title_relation: titleRelation, source_id: apiJob.id, source_title: apiJob.source_title ?? apiJob.title, source_description: apiJob.source_description ?? apiJob.description, source_api_url: apiJob.url, source_reference: original.reference }
}

/** At most one API GET and one explicitly supplied BA GET. Each is separately
 * gated; no implicit list, retries, redirects or alternative source requests. */
export async function fetchEuresDetail(id: string, deps: Deps = {}) {
  let url: string
  try { url = euresDetailUrl(id) } catch { return { job: null, scan: fail('unknown', 'invalid_eures_id', 0) } }
  const response = await requestEures(url, deps)
  if (response.error) return { job: null, scan: response.error }
  try {
    const apiJob = parseEuresDetail(response.data, { id }), original = euresBaOriginal(response.data, apiJob.language as string)
    if (!original) return { job: apiJob, scan: { ...fail('partial', 'description_read_canonical_and_full_JD_unverified', 1), errors: ['canonical_and_full_JD_unverified'] } }
    const page = await requestEures(original.url, deps, undefined, true)
    if (page.error) return { job: null, scan: { ...page.error, requests: 1 + page.error.requests, reason: 'original_page:' + page.error.reason } }
    try { return { job: await parseEuresBaOriginal(page.html!, original, apiJob), scan: { ...fail('partial', 'one_original_JobPosting_description_read', 2), errors: [] } } }
    catch (e) { return { job: null, scan: fail('parse_failed', e instanceof Error ? e.message : 'original_parse_failed', 2) } }
  } catch (e) { return { job: null, scan: fail('parse_failed', e instanceof Error ? e.message : 'detail_parse_failed', 1) } }
}
