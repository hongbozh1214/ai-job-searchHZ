import { robotsCheckPyGate, UA, type NormalizedJob } from './helpers.js'

export const EURAXESS_LIST = 'https://euraxess.ec.europa.eu/jobs/search'
const ORIGIN = 'https://euraxess.ec.europa.eu', MAX = 2 * 1024 * 1024
type Deps = { fetchImpl?: typeof fetch; gate?: (url: string) => Promise<boolean> }
type Scan = { jobs: NormalizedJob[]; coverage: string; reason: string; errors: string[]; requests: number; received_count: number | null; total_jobs: number | null; total_pages?: number | null; retry_after: string | null }
const normal = (v: string) => v.replace(/\s+/g, ' ').trim()
const fail = (status: string, reason: string, requests = 0, retry_after: string | null = null): Scan => ({ jobs: [], coverage: status, reason, errors: [reason], requests, received_count: null, total_jobs: null, retry_after })
async function visibleHtml(html: string): Promise<string> {
  // A separate removal pass avoids depending on nested streaming text/end-tag
  // callback ordering to exclude script/hidden content from the parsed fields.
  return new HTMLRewriter()
    .on('script, style, noscript, nav, [hidden], [aria-hidden="true"]', { element(e) { e.remove() } })
    .on('[style]', { element(e) { if (/display\s*:\s*none|visibility\s*:\s*hidden/i.test(e.getAttribute('style') ?? '')) e.remove() } })
    .transform(new Response(html)).text()
}
export function euraxessId(url: string): string | null {
  try {
    const u = new URL(url)
    return u.origin === ORIGIN && !u.username && !u.password && !u.search && !u.hash ? /^\/jobs\/([1-9]\d{0,11})$/.exec(u.pathname)?.[1] ?? null : null
  } catch { return null }
}

// Bun's built-in HTMLRewriter: no new dependency, script execution or resources.
// These selectors/sections come from the approved EURAXESS response structure.
export async function parseEuraxessList(html: string): Promise<Scan> {
  html = await visibleHtml(html)
  const jobs: NormalizedJob[] = [], errors: string[] = [], seen = new Map<string, NormalizedJob>(), conflicts = new Set<string>()
  let current: { urls: string[]; title: string; location: string } | null = null, suppressed = 0, title = false, location = false, heading = '', total: number | null = null, count = 0
  const rw = new HTMLRewriter()
    .on('*', { element(e) {
      if (['script','style','noscript','nav'].includes(e.tagName) || e.getAttribute('hidden') !== null || e.getAttribute('aria-hidden') === 'true' || /display\s*:\s*none|visibility\s*:\s*hidden/i.test(e.getAttribute('style') ?? '')) {
        if (!['input','img','br','hr','meta','link'].includes(e.tagName)) { suppressed++; e.onEndTag(() => { suppressed-- }) }
      }
    } })
    .on('h2', { element(e) { heading = ''; e.onEndTag(() => { const n = /^Search results\s*\(([\d,\s]+)\)$/.exec(normal(heading)); if (n) total = Number(n[1].replace(/[,\s]/g, '')) }) }, text(t) { if (!suppressed) heading += t.text } })
    .on('article.ecl-content-item', { element(e) {
      current = { urls: [], title: '', location: '' }; count++
      e.onEndTag(() => {
        const c = current; current = null
        if (!c || c.urls.length !== 1 || !normal(c.title)) { errors.push('listing_identity_missing'); return }
        const url = c.urls[0], id = euraxessId(url)
        if (!id) { errors.push('listing_foreign_or_invalid_id'); return }
        const job: NormalizedJob & { portal:string; date_source:null; needs_detail:boolean } = { id, title: normal(c.title), company: '', location: normal(c.location) || null, date: null, date_source:null, url, source_ats: 'generic', portal:'euraxess', needs_detail:true }
        // No verified employer field was retained in the list fixture: do not
        // invent an employer from a metadata item's position or portal name.
        const old = seen.get(url)
        if (old && old.title !== job.title) { seen.delete(url); conflicts.add(url); errors.push('conflicting_url_identity'); return }
        if (!conflicts.has(url)) seen.set(url, job)
      })
    } })
    .on('article.ecl-content-item h3.ecl-content-block__title', { element(e) { title = true; e.onEndTag(() => { title = false }) }, text(t) { if (current && title && !suppressed) current.title += t.text } })
    .on('article.ecl-content-item h3 a[href]', { element(e) { if (!current || suppressed) return; const raw = e.getAttribute('href'); if (raw) { const u = new URL(raw, ORIGIN).href; if (!current.urls.includes(u)) current.urls.push(u) } } })
    .on('article.ecl-content-item .id-Work-Locations .ecl-text-standard', { element(e) { location = true; e.onEndTag(() => { location = false }) }, text(t) { if (current && location && !suppressed) current.location += t.text } })
  try { await rw.transform(new Response(html)).text() } catch { return fail('parse_failed', 'invalid_list_html', 1) }
  jobs.push(...seen.values())
  if (jobs.length) return { jobs, coverage: 'partial', reason: 'one_page_employer_requires_detail', errors: [...errors, 'list_employer_unverified_requires_detail'], requests: 1, received_count: count, total_jobs: total, retry_after: null }
  if (count === 0 && total === 0) return { jobs: [], coverage: 'valid_empty', reason: 'explicit_empty_this_page', errors: [], requests: 1, received_count: 0, total_jobs: 0, retry_after: null }
  return fail('parse_failed', count ? 'listing_identity_missing' : 'no_verified_list_or_explicit_empty', 1)
}

export async function parseEuraxessDetail(html: string, listed: NormalizedJob): Promise<Record<string, unknown>> {
  html = await visibleHtml(html)
  const id = euraxessId(listed.url)
  if (!id || listed.id !== id || !listed.title) throw Error('euraxess_list_identity_unconfirmed')
  let suppressed = 0, inHeading = false, heading = '', section = '', term = '', value = '', label = '', deadline: string | null = null
  const titles: string[] = [], canonicals: string[] = [], fields: Record<string,string> = {}, sections: Record<string,string> = {}
  let h1 = ''
  const rw = new HTMLRewriter()
    .on('*', { element(e) {
      if (['script','style','noscript','nav'].includes(e.tagName) || e.getAttribute('hidden') !== null || e.getAttribute('aria-hidden') === 'true' || /display\s*:\s*none|visibility\s*:\s*hidden/i.test(e.getAttribute('style') ?? '')) {
        if (!['input','img','br','hr','meta','link'].includes(e.tagName)) { suppressed++; e.onEndTag(() => { suppressed-- }) }
      }
    } })
    .on('link[rel="canonical"]', { element(e) { const u = e.getAttribute('href'); if (u && !suppressed) canonicals.push(new URL(u, ORIGIN).href) } })
    .on('h1', { element(e) { h1 = ''; e.onEndTag(() => { if (!suppressed) titles.push(normal(h1)) }) }, text(t) { if (!suppressed) h1 += t.text } })
    .on('main h2', { element(e) { inHeading = true; heading = ''; e.onEndTag(() => { section = normal(heading); sections[section] ??= ''; inHeading = false }) }, text(t) { if (!suppressed) heading += t.text } })
    .on('main', { text(t) { if (!suppressed && !inHeading && ['Offer Description','Requirements','Additional Information'].includes(section)) sections[section] = (sections[section] ?? '') + t.text } })
    .on('main p, main li, main br', { element(e) { if (!suppressed && sections[section] !== undefined) sections[section] += '\n'; e.onEndTag(() => { if (!suppressed && sections[section] !== undefined) sections[section] += '\n' }) } })
    .on('main dt', { element(e) { term = ''; e.onEndTag(() => { label = normal(term) }) }, text(t) { if (!suppressed) term += t.text } })
    .on('main dd', { element(e) { value = ''; e.onEndTag(() => { if (!suppressed && label && !fields[label]) fields[label] = normal(value) }) }, text(t) { if (!suppressed) value += t.text } })
    .on('main dd time[datetime]', { element(e) {
      if (suppressed || label !== 'Application Deadline') return
      const raw = e.getAttribute('datetime') ?? '', day = raw.slice(0,10)
      if (/^\d{4}-\d\d-\d\d$/.test(day) && Number.isFinite(Date.parse(day)) && new Date(day).toISOString().slice(0,10) === day) deadline = day
    } })
  await rw.transform(new Response(html)).text()
  // The source's explicit canonical metadata is the detail ID namespace. Title
  // agreement alone never suffices, and a list miss/404 is never closure.
  if (canonicals.length !== 1 || canonicals[0] !== listed.url || euraxessId(canonicals[0]) !== id || !titles.includes(normal(listed.title))) throw Error('euraxess_detail_identity_mismatch')
  if (!fields['Organisation/Company']) throw Error('euraxess_employer_missing')
  if (!normal(sections['Offer Description'] ?? '') || !normal(sections['Requirements'] ?? '')) throw Error('euraxess_jd_sections_missing')
  const description = ['Offer Description','Requirements','Additional Information'].filter(k => normal(sections[k] ?? '')).map(k => k+'\n'+normal(sections[k])).join('\n\n')
  return { ...listed, needs_detail: false, company: fields['Organisation/Company'], location: fields['Country'] || listed.location, description, date: null, date_source: null, deadline, id_source: 'list_url_and_detail_canonical_path', detail_coverage: 'offer_and_requirements_sections_read', coverage: 'partial', portal: 'euraxess', observed_at: new Date().toISOString() }
}

async function page(url: string, deps: Deps): Promise<{ html?: string; error?: Scan }> {
  try { if (await (deps.gate ?? (u => robotsCheckPyGate(u, undefined, undefined, true)))(url) !== true) return { error: fail('unknown','robots_permission_unconfirmed') } }
  catch { return { error: fail('unknown','robots_permission_unconfirmed') } }
  let r: Response
  try { r = await (deps.fetchImpl ?? fetch)(url,{method:'GET',headers:{'User-Agent':UA,Accept:'text/html'},redirect:'manual',credentials:'omit',signal:AbortSignal.timeout(15000)}) }
  catch { return { error: fail('unknown','request_failed',1) } }
  const discard = () => { if (r.body) void r.body.cancel().catch(() => {}) }
  if (r.url && r.url !== url) { discard(); return { error: fail('unknown','unexpected_response_url',1) } }
  if (r.status !== 200) { discard(); return { error: fail(r.status===403||r.status===401?'blocked':r.status===429?'rate_limited':'unknown',`http_${r.status}`,1,r.status===429?r.headers.get('retry-after'):null) } }
  if (!/\btext\/html\b/i.test(r.headers.get('content-type') ?? '')) { discard(); return { error: fail('parse_failed','unexpected_content_type',1) } }
  if (Number(r.headers.get('content-length')) > MAX) { discard(); return { error: fail('unknown','body_budget_exhausted',1) } }
  const reader = r.body?.getReader(); if (!reader) return { error: fail('parse_failed','missing_body',1) }
  let bytes=0, html=''; const decoder = new TextDecoder()
  try { while (true) { const v=await reader.read(); if(v.done)break; bytes+=v.value.byteLength; if(bytes>MAX){await reader.cancel();return {error:fail('unknown','body_budget_exhausted',1)}} html+=decoder.decode(v.value,{stream:true}) } html+=decoder.decode() }
  catch { return { error:fail('unknown','body_read_failed',1) } }
  if (/<title[^>]*>[^<]*(?:captcha|access denied|just a moment|forbidden)/i.test(html)) return { error:fail('blocked','challenge',1) }
  return { html }
}
export async function fetchEuraxessList(deps: Deps = {}): Promise<Scan> {
  const p=await page(EURAXESS_LIST,deps); return p.error ?? parseEuraxessList(p.html!)
}
export async function fetchEuraxessDetail(id: string, deps: Deps = {}): Promise<Record<string,unknown>> {
  if (!/^[1-9]\d{0,11}$/.test(id)) throw Error('euraxess_bad_id')
  const list=await fetchEuraxessList(deps)
  const meta = { coverage: [{ source:'euraxess', status:list.coverage, reason:list.reason, requests:list.requests, scope:'one_source_page', retry_after:list.retry_after }], errors:list.errors.map(error=>({company:'EURAXESS',error})) }
  const stop = (reason:string):never => {
    if(!meta.errors.some(e=>e.error===reason)) meta.errors.push({company:'EURAXESS',error:reason})
    throw Object.assign(Error(reason), { meta })
  }
  const selected=list.jobs.find(j=>j.id===id)
  if (!selected) stop('euraxess_identity_unconfirmed_first_page:'+list.reason)
  const p=await page(selected!.url,deps)
  if (p.error) {
    meta.coverage.push({source:'euraxess',status:p.error.coverage,reason:p.error.reason,requests:p.error.requests,scope:'one_selected_detail',retry_after:p.error.retry_after})
    meta.errors.push(...p.error.errors.map(error=>({company:'EURAXESS',error})))
    stop('euraxess_detail_unconfirmed:'+p.error.reason)
  }
  let job:Record<string,unknown>
  try { job=await parseEuraxessDetail(p.html!,selected!) }
  catch(e) {
    const reason=e instanceof Error?e.message:'euraxess_detail_parse_failed'
    meta.coverage.push({source:'euraxess',status:'parse_failed',reason,requests:1,scope:'one_selected_detail',retry_after:null})
    meta.errors.push({company:'EURAXESS',error:reason});stop(reason)
  }
  meta.coverage.push({source:'euraxess',status:'partial',reason:'offer_and_requirements_sections_read',requests:1,scope:'one_selected_detail',retry_after:null})
  return { ...job!, canonical_url:selected!.url, description_format:'text', list_coverage:list.coverage, requests:list.requests+1, meta }
}
