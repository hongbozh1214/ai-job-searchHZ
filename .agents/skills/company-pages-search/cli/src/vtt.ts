import { robotsCheckPyGate, UA, type NormalizedJob } from './helpers.js'

const LIST = 'https://www.vttresearch.com/en/careers/come-and-build-future-vtt'
export { LIST as VTT_BOARD }
type Deps = { fetchImpl?: typeof fetch; gate?: (url: string) => Promise<boolean> }

export function isVttBoard(url: string): boolean {
  try { const u = new URL(url); return u.protocol === 'https:' && u.host === 'www.vttresearch.com' && u.pathname.replace(/\/$/, '') === '/en/careers/come-and-build-future-vtt' && !u.username && !u.password && !u.search && !u.hash } catch { return false }
}

function text(html: string): string {
  return html.replace(/<[^>]*>/g, ' ').replace(/&amp;/gi, '&').replace(/&nbsp;|&#160;/gi, ' ').replace(/&#(\d+);/g, (_, n) => String.fromCodePoint(Number(n) <= 0x10ffff ? Number(n) : 0xfffd)).replace(/\s+/g, ' ').trim()
}

/** The official VTT table links each position directly to a TalentAdore posting. */
export function parseVttList(html: string, company: string): NormalizedJob[] {
  const jobs: NormalizedJob[] = [], seen = new Map<string,string>()
  for (const row of html.match(/<tr\b[^>]*>[\s\S]*?<\/tr\s*>/gi) ?? []) {
    const cells = [...row.matchAll(/<td\b[^>]*>([\s\S]*?)<\/td\s*>/gi)]
    if (!cells.length) continue
    const links = [...row.matchAll(/<a\b[^>]*\bhref\s*=\s*["']([^"']+)["'][^>]*>/gi)]
    for (const link of links) {
      let url: URL
      try { url = new URL(link[1].replace(/&amp;/g, '&'), LIST) } catch { continue }
      const match = url.pathname.match(/^\/apply\/[^/]+\/([A-Za-z0-9]+)\/?$/)
      if (url.protocol !== 'https:' || url.host !== 'ats.talentadore.com' || url.username || url.password || url.search || url.hash || !match) continue
      const title = text(cells[0][1]), id = match[1]
      if (!title || title.length > 300) continue
      const canonical = url.origin + url.pathname.replace(/\/$/, '')
      if (seen.has(id)) { if (seen.get(id) !== canonical) throw new Error('vtt_conflicting_id'); continue }
      seen.set(id,canonical)
      jobs.push({ id, company, title, location:null, url:canonical, date:null, source_ats:'generic' })
    }
  }
  return jobs
}

export async function fetchVttList(company: string, url: string, deps: Deps = {}) {
  if (!isVttBoard(url)) throw new Error('vtt_config_error')
  const gate = deps.gate ?? ((target: string) => robotsCheckPyGate(target, undefined, undefined, true))
  const fetcher = deps.fetchImpl ?? fetch
  let current = LIST
  for (let hop=0; hop<=3; hop++) {
    try { if (await gate(current) !== true) return { jobs:[], coverage:'unknown', reason:'robots_permission_unconfirmed', requests:hop } }
    catch { return { jobs:[], coverage:'unknown', reason:'robots_permission_unconfirmed', requests:hop } }
    let response: Response
    try { response=await fetcher(current,{headers:{'User-Agent':UA},redirect:'manual',credentials:'omit',signal:AbortSignal.timeout(15000)}) }
    catch { return { jobs:[], coverage:'unknown', reason:'request_failed', requests:hop+1 } }
    if (response.status >= 300 && response.status < 400) {
      const loc=response.headers.get('location'); let next: URL
      try { if (!loc) throw Error(); next=new URL(loc,current) } catch { return { jobs:[], coverage:'unknown', reason:'invalid_redirect', requests:hop+1 } }
      if (!isVttBoard(next.href)) return { jobs:[], coverage:'unknown', reason:'redirect_unconfirmed', requests:hop+1 }
      current=next.href; continue
    }
    if (response.status === 403 || response.status === 401) return { jobs:[], coverage:'blocked', reason:`http_${response.status}`, requests:hop+1 }
    if (response.status === 429) return { jobs:[], coverage:'rate_limited', reason:`retry_after:${response.headers.get('retry-after') ?? 'unknown'}`, requests:hop+1 }
    if (response.status !== 200) return { jobs:[], coverage:'unknown', reason:`http_${response.status}`, requests:hop+1 }
    try {
      const jobs=parseVttList(await response.text(),company)
      if (!jobs.length) return { jobs, coverage:'parse_failed', reason:'no_recognized_job_rows', requests:hop+1 }
      return { jobs, coverage:'partial', reason:'pagination_and_detail_unverified', requests:hop+1 }
    } catch { return { jobs:[], coverage:'parse_failed', reason:'invalid_list', requests:hop+1 } }
  }
  return { jobs:[], coverage:'unknown', reason:'redirect_budget_exhausted', requests:4 }
}

/** Accept a detail only when structured data independently identifies the same listing. */
export function parseVttDetail(job: NormalizedJob, html: string, finalUrl: string) {
  if (!job.id || finalUrl !== job.url) throw new Error('vtt_detail_identity_mismatch')
  const scripts = [...html.matchAll(/<script\b(?=[^>]*\btype\s*=\s*["']application\/ld\+json["'])[^>]*>([\s\S]*?)<\/script\s*>/gi)]
  const objects: any[] = []
  for (const script of scripts) {
    try { const x = JSON.parse(script[1]); const items = Array.isArray(x) ? x : [x]; for (const item of items) { objects.push(item); if (Array.isArray(item?.['@graph'])) objects.push(...item['@graph']) } }
    catch { throw new Error('vtt_detail_parse_failed') }
  }
  const posts = objects.filter(x => x && (x['@type'] === 'JobPosting' || Array.isArray(x['@type']) && x['@type'].includes('JobPosting')))
  if (posts.length !== 1) throw new Error('vtt_detail_identity_missing')
  const post = posts[0], identifier = typeof post.identifier === 'string' ? post.identifier : post.identifier?.value
  if (identifier !== job.id || post.url !== job.url || typeof post.title !== 'string' || text(post.title).toLowerCase() !== job.title.trim().toLowerCase()) throw new Error('vtt_detail_identity_mismatch')
  if (typeof post.description !== 'string' || !text(post.description)) throw new Error('vtt_detail_description_missing')
  return { ...job, description:post.description, description_format:'html', detail_coverage:'structured_description_present' }
}

export async function fetchVttDetail(company: string, board: string, id: string, deps: Deps = {}) {
  const scan = await fetchVttList(company,board,deps), job = scan.jobs.find(j => j.id === id)
  if (!job) throw new Error(`vtt_detail_id_unconfirmed [${scan.coverage}]`)
  const gate = deps.gate ?? ((target: string) => robotsCheckPyGate(target, undefined, undefined, true))
  try { if (await gate(job.url) !== true) throw new Error('vtt_detail_robots_unconfirmed') } catch { throw new Error('vtt_detail_robots_unconfirmed') }
  let response: Response
  try { response=await (deps.fetchImpl ?? fetch)(job.url,{headers:{'User-Agent':UA},redirect:'manual',credentials:'omit',signal:AbortSignal.timeout(15000)}) }
  catch { throw new Error('vtt_detail_request_failed') }
  if (response.status !== 200) throw new Error(`vtt_detail_unavailable_http_${response.status}`)
  return parseVttDetail(job,await response.text(),job.url)
}
