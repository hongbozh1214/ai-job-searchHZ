// Workday list normalization and bounded pagination. Transport must be supplied
// by a policy-checked caller; this module does not issue network requests.
export type Coverage = 'complete' | 'valid_empty' | 'partial' | 'blocked' | 'rate_limited' | 'parse_failed' | 'unknown'
export type WorkdayJob = { id: string; company: string; title: string; location: string | null; url: string; posted_raw: string | null; date: null; date_source: null; observed_at: string; external_path: string }
export type WorkdayPage = { total: number; jobPostings: unknown[] }
export type PageResponse = { status: number; data?: unknown; retryAfter?: string | null; reason?: string }
export type WorkdayScan = { jobs: WorkdayJob[]; coverage: Coverage; reason: string | null; requests: number; initial_total: number | null }

export async function collectWorkdayPages(options: {
  company: string; boardUrl: string; pageSize?: number; maxPages?: number;
  getPage: (offset: number, limit: number) => Promise<PageResponse>; now?: () => Date
}): Promise<WorkdayScan> {
  const limit = options.pageSize ?? 20, budget = options.maxPages ?? 5
  if (!Number.isInteger(limit) || limit < 1 || limit > 20 || !Number.isInteger(budget) || budget < 1 || budget > 20) throw new Error('invalid request budget')
  const board = new URL(options.boardUrl)
  if (board.protocol !== 'https:' || !board.hostname.endsWith('.myworkdayjobs.com') || board.username || board.password || board.search || board.hash) throw new Error('invalid board URL')
  const base = board.href.replace(/\/$/, '')
  const jobs: WorkdayJob[] = [], ids = new Map<string, string>(), pages = new Set<string>()
  let initialTotal: number | null = null, requests = 0
  const finish = (coverage: Coverage, reason: string | null): WorkdayScan => ({ jobs, coverage, reason, requests, initial_total: initialTotal })
  for (let page = 0; page < budget; page++) {
    let result: PageResponse
    try { requests++; result = await options.getPage(page * limit, limit) } catch { return finish(jobs.length ? 'partial' : 'unknown', 'request_failed') }
    if (result.status === 403 || result.status === 401) return finish(jobs.length ? 'partial' : 'blocked', `http_${result.status}`)
    if (result.status === 429) return finish(jobs.length ? 'partial' : 'rate_limited', `retry_after:${result.retryAfter ?? 'unknown'}`)
    if (result.status !== 200) return finish(jobs.length ? 'partial' : 'unknown', result.reason ?? `http_${result.status}`)
    const data = result.data as Partial<WorkdayPage> | null
    if (!data || !Array.isArray(data.jobPostings) || typeof data.total !== 'number' || !Number.isFinite(data.total) || data.total < 0) return finish(jobs.length ? 'partial' : 'parse_failed', 'invalid_page')
    if (page === 0) initialTotal = data.total
    if (data.jobPostings.length > limit) return finish(jobs.length ? 'partial' : 'parse_failed', 'oversized_page')
    if (data.jobPostings.length === 0) {
      if (page === 0 && initialTotal === 0) return finish('valid_empty', null)
      if (initialTotal !== null && jobs.length < initialTotal) return finish('partial', 'empty_before_initial_total')
      return finish('complete', null)
    }
    const fingerprint = JSON.stringify(data.jobPostings)
    if (pages.has(fingerprint)) return finish('partial', 'repeated_page')
    pages.add(fingerprint)
    let malformed = false
    for (const value of data.jobPostings) {
      const item = value as Record<string, unknown> | null
      if (!item || typeof item.title !== 'string' || !item.title.trim() || typeof item.externalPath !== 'string' || !/^\/job\/(?!\/)[^?#\s]+$/.test(item.externalPath) || /%2f|%5c|%2e|\\|\.\./i.test(item.externalPath)) { malformed = true; continue }
      const fields = Array.isArray(item.bulletFields) ? item.bulletFields : []
      const id = fields.find(x => typeof x === 'string' && /^(JR|R)\d+$/i.test(x))
      if (typeof id !== 'string' || !new RegExp('_' + id + '(?:-\\d+)?$').test(item.externalPath)) { malformed = true; continue }
      const rawId = item.externalPath.match(/_((?:JR|R)\d+(?:-\d+)?)$/i)?.[1]
      if (!rawId) { malformed = true; continue }
      const existingPath = ids.get(rawId)
      if (existingPath !== undefined) {
        if (existingPath !== item.externalPath) malformed = true
        continue
      }
      ids.set(rawId, item.externalPath)
      jobs.push({id: rawId, company: options.company, title: item.title, location: typeof item.locationsText === 'string' ? item.locationsText : null, url: base + item.externalPath, posted_raw: typeof item.postedOn === 'string' ? item.postedOn : null, date: null, date_source: null, observed_at: (options.now ?? (() => new Date()))().toISOString(), external_path: item.externalPath})
    }
    if (malformed) return finish('partial', 'invalid_listing')
    // Later totals can be zero with a full page; only page zero is evidence.
    if (data.jobPostings.length < limit) return finish(initialTotal !== null && jobs.length < initialTotal ? 'partial' : 'complete', initialTotal !== null && jobs.length < initialTotal ? 'short_before_initial_total' : null)
  }
  return finish('partial', 'page_budget_exhausted')
}

/** Detail must match the exact list path and requisition before it can be joined. */
export function parseWorkdayDetail(job: WorkdayJob, payload: unknown) {
  const root = payload as {jobPostingInfo?: Record<string, unknown>} | null
  const info = root?.jobPostingInfo
  if (!info || typeof info.jobReqId !== 'string' || typeof info.externalUrl !== 'string') throw new Error('detail_identity_missing')
  const req = job.id.replace(/-\d+$/, '')
  let detailUrl: URL
  try { detailUrl = new URL(info.externalUrl) } catch { throw new Error('detail_identity_invalid') }
  const expected = new URL(job.url)
  if (info.jobReqId !== req || detailUrl.origin !== expected.origin || !detailUrl.pathname.endsWith(job.external_path)) throw new Error('detail_identity_mismatch')
  if (typeof info.jobDescription !== 'string' || !info.jobDescription.trim()) throw new Error('detail_jd_missing')
  return { ...job, description: info.jobDescription, description_format: 'html', detail_coverage: 'jobDescription_present', detail_posted_raw: typeof info.postedOn === 'string' ? info.postedOn : null, start_date_raw: typeof info.startDate === 'string' ? info.startDate : null, end_date_raw: typeof info.endDate === 'string' ? info.endDate : null }
}

import { robotsCheckPyGate, UA } from './helpers.js'
const VERIFIED_BOARDS: Record<string, {tenant: string; site: string}> = {
  'iff.wd5.myworkdayjobs.com': {tenant:'iff',site:'IFF_Careers'},
  'novonesis.wd103.myworkdayjobs.com': {tenant:'novonesis',site:'Novonesis_Careers'},
}
export function workdayBoard(url: string) {
  const u = new URL(url); const config = VERIFIED_BOARDS[u.hostname]
  if (u.protocol !== 'https:' || u.port || u.username || u.password || u.search || u.hash || !config || !new RegExp(`^/(?:en-US/)?${config.site}/?$`).test(u.pathname)) throw new Error('workday_config_error')
  return { origin:u.origin, ...config, board:`${u.origin}/en-US/${config.site}`, api:`${u.origin}/wday/cxs/${config.tenant}/${config.site}` }
}
type RequestDeps = { fetchImpl?: typeof fetch; gate?: (url:string)=>Promise<boolean> }
export async function guardedWorkdayRequest(url: string, init: RequestInit, deps: RequestDeps = {}): Promise<PageResponse> {
  const gate=deps.gate ?? ((target: string) => robotsCheckPyGate(target, undefined, undefined, true)), fetcher=deps.fetchImpl ?? fetch
  let current=url
  for(let hop=0;hop<=3;hop++) {
    try { if ((await gate(current)) !== true) return {status:0, reason:'robots_permission_unconfirmed'} }
    catch { return {status:0, reason:'robots_permission_unconfirmed'} }
    let response:Response
    try { response=await fetcher(current,{...init,headers:{'User-Agent':UA,'Content-Type':'application/json'},redirect:'manual',credentials:'omit',signal:AbortSignal.timeout(15000)}) } catch {return {status:0, reason:'request_failed'}}
    if (response.status>=300 && response.status<400) {
      const location=response.headers.get('location');if(!location)return {status:0}
      let next: URL
      try { next=new URL(location,current) } catch { return {status:0, reason:'invalid_redirect'} }
      if(next.protocol!=='https:' || next.origin!==new URL(url).origin)return {status:0, reason:'redirect_origin_unconfirmed'}
      current=next.href;continue
    }
    if(response.status===429)return {status:429,retryAfter:response.headers.get('retry-after')}
    if(response.status!==200)return {status:response.status}
    try{return {status:200,data:await response.json()}}catch{return {status:200,data:null}}
  }
  return {status:0}
}
export async function fetchWorkdayList(company: string, boardUrl: string, deps: RequestDeps = {}, maxPages=5) {
  const b=workdayBoard(boardUrl)
  return collectWorkdayPages({company,boardUrl:b.board,maxPages,getPage:(offset,limit)=>guardedWorkdayRequest(b.api+'/jobs',{method:'POST',body:JSON.stringify({appliedFacets:{},limit,offset,searchText:''})},deps)})
}
export async function fetchWorkdayDetail(company: string, boardUrl: string, id: string, deps: RequestDeps = {}) {
  const b=workdayBoard(boardUrl), scan=await fetchWorkdayList(company,boardUrl,deps)
  const job=scan.jobs.find(j=>j.id===id)
  if(!job)throw new Error(`detail_id_unconfirmed [${scan.coverage}]`)
  if(/%2f|%5c|%2e|\\|\.\./i.test(job.external_path))throw new Error('detail_path_invalid')
  const result=await guardedWorkdayRequest(b.api+job.external_path,{method:'GET'},deps)
  if(result.status!==200)throw new Error(`detail_unavailable_${result.reason ?? `http_${result.status}`}${result.status === 429 ? `_retry_after_${result.retryAfter ?? 'unknown'}` : ''}`)
  return parseWorkdayDetail(job,result.data)
}
