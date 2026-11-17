import { fetchVttDetail, VTT_BOARD } from './vtt.js'
import { robotsCheckPyGate, UA, type NormalizedJob } from './helpers.js'

type Deps = { fetchImpl?: typeof fetch; gate?: (url: string) => Promise<boolean> }
type Status = 'partial' | 'valid_empty' | 'blocked' | 'rate_limited' | 'parse_failed' | 'unknown'
export type SourceJob = NormalizedJob & { portal: 'work-in-finland'; date_source: null; observed_at: string }
export type SourceScan = { jobs: SourceJob[]; coverage: Status; reason: string; requests: number; errors: string[]; received_count: number | null; total_jobs: number | null; total_pages: number | null; retry_after: string | null }
export const MAX_SOURCE_BYTES = 131072

export function workInFinlandUrl(query?: string): string {
  if (query !== undefined && (!query.trim() || query.length > 256)) throw Error('invalid_source_query')
  const url = new URL('https://www.workinfinland.com/api/jobs/')
  url.search = new URLSearchParams({ limit: '6', page: '1', ...(query ? { query: query.trim().toLowerCase() } : {}) }).toString()
  return url.href
}

function vttId(job: Pick<SourceJob,'company'|'url'>):string | null {
  const u=new URL(job.url)
  return job.company.toLowerCase()==='vtt' && u.origin==='https://ats.talentadore.com' && !u.username && !u.password && !u.search && !u.hash
    ? /^\/apply\/[^/]+\/([A-Za-z0-9]+)\/?$/.exec(u.pathname)?.[1] ?? null : null
}

// Jobly编号与TalentAdore编号使用不同命名空间，只接已留证的VTT英文职位路径。
function joblyIdentity(job:Pick<SourceJob,'company'|'url'>) {
  try {
    const u=new URL(job.url),m=/^\/en\/job\/([a-z0-9][a-z0-9-]{0,399}-([1-9]\d{0,11}))$/.exec(u.pathname)
    return job.company.toLowerCase()==='vtt' && u.origin==='https://www.jobly.fi' && !u.username && !u.password && !u.search && !u.hash && m
      ? {id:m[2],canonical:'https://www.jobly.fi/tyopaikka/'+m[1]} : null
  } catch { return null }
}

export async function parseJoblyVttDetail(html:string,listed:SourceJob):Promise<Record<string,unknown>> {
  const identity=joblyIdentity(listed),normal=(s:string)=>s.replace(/\s+/g,' ').trim().toLowerCase()
  if(!identity || listed.id!=='jobly:'+identity.id)throw Error('jobly_listing_identity_unconfirmed')
  const canonicals:string[]=[],posts:any[]=[];let script='',invalid=false
  const add=(x:any)=>{if(!x||typeof x!=='object')return;if(x['@type']==='JobPosting'||Array.isArray(x['@type'])&&x['@type'].includes('JobPosting'))posts.push(x);if(Array.isArray(x['@graph']))x['@graph'].forEach(add)}
  await new HTMLRewriter()
    .on('link[rel~="canonical"]',{element(e){const href=e.getAttribute('href');if(href)canonicals.push(new URL(href,listed.url).href)}})
    .on('script[type="application/ld+json"]',{element(e){script='';e.onEndTag(()=>{try{const v=JSON.parse(script);(Array.isArray(v)?v:[v]).forEach(add)}catch{invalid=true}})},text(t){script+=t.text}})
    .transform(new Response(html)).text()
  if(invalid || posts.length!==1)throw Error('jobly_structured_identity_unconfirmed')
  const post=posts[0],identifier=typeof post.identifier==='object'&&post.identifier!==null?post.identifier.value:post.identifier
  if(canonicals.length!==1 || canonicals[0]!==identity.canonical || typeof post.title!=='string' || normal(post.title)!==normal(listed.title) || typeof post.hiringOrganization?.name!=='string' || normal(post.hiringOrganization.name)!=='vtt')throw Error('jobly_detail_identity_mismatch')
  // 来源未提供identifier/url时由同编号canonical、卡片标题/雇主独立绑定；若字段存在则不得冲突。
  if(post.identifier!=null && String(identifier)!==identity.id || post.url!=null && post.url!==listed.url && post.url!==identity.canonical)throw Error('jobly_structured_identity_mismatch')
  if(typeof post.description!=='string')throw Error('jobly_description_missing')
  const visible=post.description.replace(/<(script|style)\b[^>]*>[\s\S]*?<\/\1>/gi,' ').replace(/<[^>]*>/g,' ').replace(/&nbsp;|&#160;/gi,' ').trim()
  if(!visible || !/responsibilit|your role|main tasks|tehtäv/i.test(visible) || !/requirements|qualifications|we expect|looking for|edellyt|vaatim/i.test(visible))throw Error('jobly_description_sections_unconfirmed')
  return {...listed,id:'jobly:'+identity.id,source_job_id:identity.id,id_namespace:'jobly',id_source:'wif_url_and_jobly_canonical_path',source_url:listed.url,url:identity.canonical,canonical_url:identity.canonical,description:post.description,description_format:'html',detail_source:'jobly',detail_coverage:'structured_description_with_duties_and_requirements',independent_full_JD_completeness:'unverified',date:null,date_source:null,needs_detail:false,observed_at:new Date().toISOString()}
}

async function fetchJoblyVttDetail(job:SourceJob,deps:Deps) {
  const fail=(status:Status,reason:string,requests:number,retry_after:string|null=null):{job:Record<string,unknown>|null;status:Status;reason:string;requests:number;retry_after:string|null}=>({job:null,status,reason,requests,retry_after})
  try{if(await (deps.gate??(u=>robotsCheckPyGate(u,undefined,undefined,true)))(job.url)!==true)return fail('unknown','robots_permission_unconfirmed',0)}catch{return fail('unknown','robots_permission_unconfirmed',0)}
  let r:Response
  try{r=await (deps.fetchImpl??fetch)(job.url,{method:'GET',headers:{'User-Agent':UA,Accept:'text/html'},redirect:'manual',credentials:'omit',signal:AbortSignal.timeout(15000)})}catch{return fail('unknown','request_failed',1)}
  const discard=()=>{void r.body?.cancel().catch(()=>{})}
  if(r.status!==200){discard();return fail(r.status===401||r.status===403?'blocked':r.status===429?'rate_limited':'unknown','http_'+r.status,1,r.status===429?r.headers.get('retry-after'):null)}
  if(r.url && r.url!==job.url){discard();return fail('unknown','response_url_unconfirmed',1)}
  if(!/\btext\/html\b/i.test(r.headers.get('content-type')??'')){discard();return fail('parse_failed','unexpected_content_type',1)}
  if(Number(r.headers.get('content-length'))>2097152){discard();return fail('unknown','body_budget_exhausted',1)}
  const reader=r.body?.getReader();if(!reader)return fail('parse_failed','missing_body',1)
  let html='',bytes=0;const decoder=new TextDecoder()
  try{while(true){const v=await reader.read();if(v.done)break;bytes+=v.value.byteLength;if(bytes>2097152){await reader.cancel();return fail('unknown','body_budget_exhausted',1)}html+=decoder.decode(v.value,{stream:true})}html+=decoder.decode()}catch{return fail('unknown','body_read_failed',1)}
  if(/<title[^>]*>[^<]*(captcha|access denied|just a moment|forbidden)/i.test(html))return fail('blocked','challenge',1)
  try{return {job:await parseJoblyVttDetail(html,job),status:'partial' as Status,reason:'jobly_structured_description_read',requests:1,retry_after:null}}catch(e){return fail('parse_failed',e instanceof Error?e.message:'jobly_parse_failed',1)}
}

export function parseWorkInFinland(data: unknown): SourceScan {
  const scan: SourceScan = { jobs: [], coverage: 'parse_failed', reason: 'invalid_list_schema', requests: 1, errors: [], received_count: null, total_jobs: null, total_pages: null, retry_after: null }
  const fail = (reason: string): SourceScan => ({ ...scan, coverage: 'parse_failed', reason, errors: [reason] })
  const body = data as Record<string, unknown> | null
  if (!body || !Array.isArray(body.jobs) || body.success === false || body.error || (body.errors && (!Array.isArray(body.errors) || body.errors.length)) || !Number.isInteger(body.totalJobs) || !Number.isInteger(body.totalPages) || (body.totalJobs as number) < 0 || (body.totalPages as number) < 0) return fail('invalid_list_schema')
  scan.received_count = body.jobs.length; scan.total_jobs = body.totalJobs as number; scan.total_pages = body.totalPages as number
  if (!body.jobs.length) {
    if (scan.total_jobs === 0 && scan.total_pages <= 1) return { ...scan, coverage: 'valid_empty', reason: 'empty_this_query_page_only' }
    return { ...scan, coverage: 'unknown', reason: 'empty_page_nonzero_or_inconsistent_total', errors: ['inconsistent_page_counts'] }
  }
  if (body.jobs.length > 6 || scan.total_jobs < body.jobs.length || scan.total_pages < 1) return fail('inconsistent_page_counts')
  const byUrl = new Map<string, SourceJob>(), rejected = new Set<string>()
  for (const [index, value] of body.jobs.entries()) {
    const row = value as Record<string, unknown> | null, employer = row?.employer as Record<string, unknown> | null
    if (!row || !employer || typeof row.title !== 'string' || !row.title.trim() || typeof employer.name !== 'string' || !employer.name.trim() || typeof row.externalUrl !== 'string') { scan.errors.push(`invalid_record_identity:${index}`); continue }
    let url: URL
    try { url = new URL(row.externalUrl) } catch { scan.errors.push(`invalid_posting_url:${index}`); continue }
    if (!row.externalUrl.startsWith('https://') || row.externalUrl !== row.externalUrl.trim() || /[\s\x00-\x1f]/.test(row.externalUrl) || url.protocol !== 'https:' || !url.hostname || url.username || url.password) { scan.errors.push(`invalid_posting_url:${index}`); continue }
    const job: SourceJob = { title: row.title.trim(), company: employer.name.trim(), location: typeof employer.city === 'string' && employer.city.trim() ? employer.city.trim() : null, url: row.externalUrl, date: null, date_source: null, observed_at: new Date().toISOString(), source_ats: 'generic', portal: 'work-in-finland' }
    const jobly=joblyIdentity(job)
    const id=vttId(job) ?? (jobly?'jobly:'+jobly.id:null)
    if(id) job.id=id // 来源URL派生的候选ID；仍须按对应分支核验详情身份。
    const old = byUrl.get(job.url)
    if (rejected.has(job.url)) continue
    if (old && [old.company, old.title, old.location].join('\0') !== [job.company, job.title, job.location].join('\0')) {
      byUrl.delete(job.url); rejected.add(job.url); scan.errors.push(`conflicting_url_identity:${index}`); continue
    }
    if (!old) byUrl.set(job.url, job)
  }
  scan.jobs = [...byUrl.values()]
  return { ...scan, coverage: scan.jobs.length ? 'partial' : 'parse_failed', reason: scan.errors.length ? 'invalid_listing_identity_or_fields' : 'single_page_only' }
}

/** One fixed-origin page, strict real checker, no redirect/retry/fallback or JD read. */
export async function fetchWorkInFinland(query?: string, deps: Deps = {}): Promise<SourceScan> {
  const url = workInFinlandUrl(query)
  const fail = (coverage: Status, reason: string, requests: number, retry_after: string | null = null): SourceScan => ({ jobs: [], coverage, reason, requests, errors: [reason], received_count: null, total_jobs: null, total_pages: null, retry_after })
  try { if (await (deps.gate ?? (u => robotsCheckPyGate(u, undefined, undefined, true)))(url) !== true) return fail('unknown', 'robots_permission_unconfirmed', 0) }
  catch { return fail('unknown', 'robots_permission_unconfirmed', 0) }
  let response: Response
  try { response = await (deps.fetchImpl ?? fetch)(url, { method: 'GET', headers: { 'User-Agent': UA, Accept: 'application/json' }, redirect: 'manual', credentials: 'omit', signal: AbortSignal.timeout(15000) }) }
  catch { return fail('unknown', 'request_failed', 1) }
  const discard = () => { void response.body?.cancel().catch(() => {}) }
  if (response.status >= 300 && response.status < 400) { discard(); return fail('unknown', 'redirect_unconfirmed', 1) }
  if (response.url && response.url !== url) { discard(); return fail('unknown', 'response_url_unconfirmed', 1) }
  if (response.status === 401 || response.status === 403) { discard(); return fail('blocked', `http_${response.status}`, 1) }
  if (response.status === 429) { discard(); return fail('rate_limited', 'http_429', 1, response.headers.get('retry-after')) }
  if (response.status !== 200) { discard(); return fail('unknown', `http_${response.status}`, 1) }
  if (!/\bapplication\/(?:[\w.-]+\+)?json\b/i.test(response.headers.get('content-type') ?? '')) { discard(); return fail('parse_failed', 'unexpected_content_type', 1) }
  if (Number(response.headers.get('content-length')) > MAX_SOURCE_BYTES) { discard(); return fail('unknown', 'body_budget_exhausted', 1) }
  const reader = response.body?.getReader()
  if (!reader) return fail('parse_failed', 'missing_body', 1)
  let bytes = 0, text = ''; const decoder = new TextDecoder()
  try {
    while (true) {
      const { done, value } = await reader.read(); if (done) break
      bytes += value.byteLength
      if (bytes > MAX_SOURCE_BYTES) { await reader.cancel(); return fail('unknown', 'body_budget_exhausted', 1) }
      text += decoder.decode(value, { stream: true })
    }
    text += decoder.decode()
  } catch { return fail('unknown', 'body_read_failed', 1) }
  try { return parseWorkInFinland(JSON.parse(text)) } catch { return fail('parse_failed', 'invalid_json', 1) }
}

/** 仅VTT：直链核对官方board；Jobly独立核对同编号canonical。 */
export async function fetchWorkInFinlandDetail(id:string, query?:string, deps:Deps = {}) {
  if (!/^(?:[A-Za-z0-9]+|jobly:[1-9]\d{0,11})$/.test(id)) throw Error('wif_bad_vtt_id')
  const scan=await fetchWorkInFinland(query,deps)
  const meta={coverage:[{source:'work-in-finland',status:scan.coverage,reason:scan.reason,requests:scan.requests as number | null,retry_after:scan.retry_after}],errors:scan.errors.map(error=>({company:'Work in Finland',error}))}
  const stop=(reason:string):never=>{meta.errors.push({company:'Work in Finland',error:reason});throw Object.assign(Error(reason),{meta})}
  const isJobly=id.startsWith('jobly:')
  const matches=scan.jobs.filter(j=>isJobly ? j.id===id && joblyIdentity(j)!==null : vttId(j)===id)
  if(matches.length!==1)stop(isJobly?'wif_jobly_identity_unconfirmed_first_page':'wif_vtt_identity_unconfirmed_first_page')
  const selected=matches[0]
  if(isJobly){
    const detail=await fetchJoblyVttDetail(selected,deps)
    meta.coverage.push({source:'jobly',status:detail.status,reason:detail.reason,requests:detail.requests,retry_after:detail.retry_after})
    if(!detail.job)stop('wif_jobly_detail_unconfirmed:'+detail.reason)
    return {...detail.job,list_coverage:scan.coverage,meta}
  }
  let job:Awaited<ReturnType<typeof fetchVttDetail>>
  try { job=await fetchVttDetail('VTT',VTT_BOARD,id,deps) }
  catch(e){
    const reason=e instanceof Error?e.message:'wif_vtt_detail_unconfirmed'
    const status=/_http_(401|403)$/.test(reason)?'blocked':/_http_429$/.test(reason)?'rate_limited':/identity|description_missing|parse_failed/.test(reason)?'parse_failed':'unknown'
    meta.coverage.push({source:'vtt',status,reason,requests:null,retry_after:null});stop(reason)
  }
  if(job!.url!==selected.url || job!.title.trim().replace(/\s+/g,' ').toLowerCase()!==selected.title.trim().replace(/\s+/g,' ').toLowerCase())stop('wif_vtt_source_identity_mismatch')
  meta.coverage.push({source:'vtt',status:'partial',reason:'matched_official_board_and_detail',requests:null as number | null,retry_after:null})
  return {...job!,portal:'work-in-finland',canonical_url:job!.url,needs_detail:false,date:null,date_source:null,observed_at:new Date().toISOString(),list_coverage:scan.coverage,meta}
}
