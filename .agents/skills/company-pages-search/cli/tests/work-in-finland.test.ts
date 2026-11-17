import { verifyDetailState } from './fixtures/verified-detail-state.js'
import { test, expect } from 'bun:test'
import { mkdtempSync, writeFileSync, readFileSync, existsSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { parseJoblyVttDetail, fetchWorkInFinlandDetail, fetchWorkInFinland, parseWorkInFinland, workInFinlandUrl, MAX_SOURCE_BYTES } from '../src/work-in-finland.js'
const url = workInFinlandUrl()
const row = (link='https://jobs.example.test/role?jobId=1') => ({ title: 'Synthetic scientist', employer: { name: 'Fixture Ltd', city: 'Espoo' }, externalUrl: link, expireDate: '2099-01-01', description: 'not a list output field' })
const body = (jobs: unknown[]=[row()]) => ({ jobs, totalJobs: jobs.length ? 1081 : 0, totalPages: jobs.length ? 181 : 0 })

test('source query is fixed-origin/one-page; cards retain query, dates unknown, duplicate URL only', () => {
  expect(workInFinlandUrl('Protein & Enzyme')).toBe(url+'&query=protein+%26+enzyme')
  const scan=parseWorkInFinland(body([row(),row(),row('https://jobs.example.test/role?jobId=2')]))
  expect(scan.coverage).toBe('partial'); expect(scan.jobs).toHaveLength(2)
  expect(scan.jobs[0]).toMatchObject({ company:'Fixture Ltd',date:null,date_source:null,portal:'work-in-finland',url:row().externalUrl })
  expect(scan.jobs[0]).not.toHaveProperty('id'); expect(scan.jobs[0]).not.toHaveProperty('description'); expect(scan.jobs[0]).not.toHaveProperty('expireDate')
})
test('valid empty, contradictory counts, malformed fields and conflicting identities differ', () => {
  expect(parseWorkInFinland(body([])).coverage).toBe('valid_empty')
  expect(parseWorkInFinland({jobs:[],totalJobs:1,totalPages:1}).coverage).toBe('unknown')
  for(const value of [null,{error:'bad',jobs:[],totalJobs:0,totalPages:0},{jobs:'wrong',totalJobs:0,totalPages:0},{jobs:[],totalJobs:true,totalPages:0},body([{title:'missing employer'}]),body([{...row(),externalUrl:'https://user:pass@example.test/1'}])]) expect(parseWorkInFinland(value).coverage).toBe('parse_failed')
  const mixed=parseWorkInFinland(body([row(),{title:'missing employer'}]));expect(mixed.jobs).toHaveLength(1);expect(mixed.errors).toHaveLength(1);expect(mixed.coverage).toBe('partial')
  const conflict=parseWorkInFinland(body([row(),{...row(),title:'Other identity'}]));expect(conflict.jobs).toEqual([]);expect(conflict.coverage).toBe('parse_failed')
})
test('checker refusal, unknown and failure never send a protected fetch', async () => {
  let requests=0
  const fetchImpl=(async()=>{requests++;return Response.json(body())}) as typeof fetch
  for(const gate of [async()=>false,async()=>undefined as any,async()=>{throw Error('checker failed')}]) {
    const scan=await fetchWorkInFinland(undefined,{gate,fetchImpl});expect(scan.coverage).toBe('unknown');expect(scan.requests).toBe(0)
  }
  expect(requests).toBe(0)
})
test('strict transport: no retry/redirect, 403/404/429/5xx and timeout retain errors', async () => {
  for(const [status,coverage] of [[302,'unknown'],[403,'blocked'],[404,'unknown'],[429,'rate_limited'],[503,'unknown']] as const) {
    let requests=0
    const scan=await fetchWorkInFinland(undefined,{gate:async()=>true,fetchImpl:(async(u,init)=>{requests++;expect(String(u)).toBe(url);expect(init).toMatchObject({method:'GET',redirect:'manual',credentials:'omit'});return new Response('',{status,headers:{'retry-after':'120',location:'https://other.example.test'}})}) as typeof fetch})
    expect(scan.coverage).toBe(coverage);expect(scan.errors.length).toBeGreaterThan(0);expect(requests).toBe(1)
    if(status===429)expect(scan.retry_after).toBe('120')
  }
  const timed=await fetchWorkInFinland(undefined,{gate:async()=>true,fetchImpl:(async()=>{throw Error('timeout')}) as typeof fetch});expect(timed.coverage).toBe('unknown');expect(timed.requests).toBe(1)
})
test('bounded streaming and malformed/HTML response cannot become empty success', async () => {
  for(const [response,reason] of [[new Response('x'.repeat(MAX_SOURCE_BYTES+1),{headers:{'content-type':'application/json'}}),'body_budget_exhausted'],[new Response('é'.repeat(MAX_SOURCE_BYTES/2+1),{headers:{'content-type':'application/json'}}),'body_budget_exhausted'],[new Response('{',{headers:{'content-type':'application/json'}}),'invalid_json'],[new Response('<title>challenge</title>',{headers:{'content-type':'text/html'}}),'unexpected_content_type']] as const) {
    const scan=await fetchWorkInFinland(undefined,{gate:async()=>true,fetchImpl:(async()=>response) as typeof fetch});expect(scan.reason).toBe(reason);expect(scan.jobs).toEqual([]);expect(scan.coverage).not.toBe('valid_empty')
  }
})
async function cli(args:string[],mode='1',responses:Record<string,unknown>={[url]:{body:body()}},joblyMode='1') {
  const dir=mkdtempSync(path.join(tmpdir(),'wif-data-')), f=path.join(dir,'responses.json'), log=path.join(dir,'fetch.log'), curl=path.join(dir,'curl.log')
  writeFileSync(f,JSON.stringify(responses))
  try {
    const p=Bun.spawn([process.execPath,'run','--preload',process.env.COMPANY_OFFLINE_PRELOAD!,'--preload',path.join(import.meta.dir,'fixtures/work-in-finland-offline.ts'),path.join(import.meta.dir,'../src/cli.ts'),...args],{env:{...process.env,COMPANY_PAGES_REGISTRY:path.join(dir,'MISSING.json'),COMPANY_OFFLINE_WIF_RESPONSES:f,COMPANY_OFFLINE_WIF_FETCH_LOG:log,COMPANY_OFFLINE_CURL_LOG:curl,COMPANY_OFFLINE_WIF_ROBOTS_FIXTURE:mode,COMPANY_OFFLINE_ROBOTS_FIXTURE:'1',COMPANY_OFFLINE_JOBLY_ROBOTS_FIXTURE:joblyMode},stdout:'pipe',stderr:'pipe'})
    const stdout=await new Response(p.stdout).text(),stderr=await new Response(p.stderr).text(),exit=await p.exited
    return {stdout,stderr,exit,requests:existsSync(log)?readFileSync(log,'utf8').trim().split('\n').map(s=>JSON.parse(s)):[],checkerCalls:existsSync(curl)?readFileSync(curl,'utf8').trim().split('\n').length:0}
  } finally {rmSync(dir,{recursive:true,force:true})}
}
test('normal CLI source branch works without registry; server query and emitted limit retain partial/errors', async () => {
  const queried=workInFinlandUrl('Protein engineer')
  const r=await cli(['search','--source','work-in-finland','--query','Protein engineer','--limit','1'], '1', {[queried]:{body:body([row(),row('https://jobs.example.test/2'),{title:'bad'}])}}), data=JSON.parse(r.stdout)
  expect(r.exit).toBe(0);expect(r.checkerCalls).toBe(1);expect(r.requests.map(r=>r.url)).toEqual([queried]);expect(data.results).toHaveLength(1)
  expect(new URL(r.requests[0].url).searchParams.get('query')).toBe('protein engineer')
  expect(data.results[0].date).toBeNull();expect(data.results[0]).not.toHaveProperty('id');expect(data.results[0].url).toBe(row().externalUrl)
  expect(data.meta.coverage[0]).toMatchObject({source:'work-in-finland',status:'partial',received_count:3,total_jobs:1081,total_pages:181,requests:1});expect(data.meta.errors).toHaveLength(1)
  const filtered=await cli(['search','--source','work-in-finland','--location','Nowhere']), zero=JSON.parse(filtered.stdout)
  expect(zero.results).toEqual([]);expect(zero.meta.coverage[0].status).toBe('partial');expect(zero.meta.coverage[0].received_count).toBe(1)
})
test('CLI real checker denial/unknown, valid empty and errors preserve business semantics', async () => {
  for(const mode of ['deny','']) {
    const r=await cli(['search','--source','work-in-finland'],mode),data=JSON.parse(r.stdout);expect(r.exit).toBe(0);expect(r.checkerCalls).toBe(1);expect(r.requests).toEqual([]);expect(data.meta.coverage[0].status).toBe('unknown');expect(data.meta.errors).toHaveLength(1)
  }
  const empty=JSON.parse((await cli(['search','--source','work-in-finland'],'1',{[url]:{body:body([])}})).stdout);expect(empty.results).toEqual([]);expect(empty.meta.coverage[0].status).toBe('valid_empty');expect(empty.meta.errors).toEqual([])
  const limited=JSON.parse((await cli(['search','--source','work-in-finland'],'1',{[url]:{status:429,headers:{'retry-after':'120'},body:{error:'limited'}}})).stdout);expect(limited.meta.coverage[0]).toMatchObject({status:'rate_limited',retry_after:'120'});expect(limited.meta.errors).toHaveLength(1)
})
test('unsupported/conflicting source flags never read registry or send requests', async () => {
  for(const args of [['search','--source','unknown'],['search','--source','work-in-finland','--company','Fixture'],['search','--source']]) {
    const r=await cli(args);expect(r.exit).toBe(1);expect(r.stderr).toContain('BAD_ARG');expect(r.stderr).not.toContain('NO_REGISTRY');expect(r.requests).toEqual([]);expect(r.checkerCalls).toBe(0)
  }
})

const vf=JSON.parse(readFileSync(path.join(import.meta.dir,'fixtures/vtt-detail-sanitized.json'),'utf8'))
const vb='https://www.vttresearch.com/en/careers/come-and-build-future-vtt'
function vttResponses():Record<string,any>{return {
 [url]:{body:body([{...row(vf.job.url),title:vf.job.title,employer:{name:'VTT',city:'Espoo'}}])},
 [vb]:{raw:`<table><tr><td>${vf.job.title}</td><td><a href="${vf.job.url}">Details</a></td></tr></table>`,headers:{'content-type':'text/html'}},
 [vf.job.url]:{raw:`<script type="application/ld+json">${JSON.stringify(vf.jobPosting)}</script>`,headers:{'content-type':'text/html'}}}}
test('WIF CLI reuses official VTT detail route with exact identity and preserved body, no registry',async()=>{
 const r=await cli(['detail','--source','work-in-finland','--id',vf.job.id],'1',vttResponses()),j=JSON.parse(r.stdout)
 expect(r.exit).toBe(0);expect(r.checkerCalls).toBe(3);expect(r.requests.map(x=>x.url)).toEqual([url,vb,vf.job.url])
 expect(j).toMatchObject({id:vf.job.id,company:'VTT',url:vf.job.url,canonical_url:vf.job.url,date:null,date_source:null,needs_detail:false,list_coverage:'partial'})
 expect(j.description).toBe(vf.jobPosting.description);verifyDetailState(j,'finland');expect(j.meta.coverage.map((x:any)=>x.status)).toEqual(['partial','partial']);expect(j.meta.coverage[1].requests).toBeNull()
 const g=vttResponses();g[workInFinlandUrl('protein')]=g[url];delete g[url]
 expect((await cli(['detail','--source','work-in-finland','--query','protein','--id',vf.job.id],'1',g)).exit).toBe(0)
})
test('WIF rejects unsupported employer, changed identity, absent body and denied checker without fallback',async()=>{
 for(const mode of ['deny','']){
  const r=await cli(['detail','--source','work-in-finland','--id',vf.job.id],mode,vttResponses());expect(r.exit).toBe(1);expect(r.requests).toEqual([]);expect(JSON.parse(r.stderr.trim().split("\n").at(-1)!).meta.coverage[0].status).toBe('unknown')
 }
 for(const change of ['employer','title','url','body','id','detail-denied']){
  const f=vttResponses()
  if(change==='employer')f[url].body.jobs[0].employer.name='Other Employer'
  if(change==='title')f[url].body.jobs[0].title='Different position'
  if(change==='url')f[url].body.jobs[0].externalUrl+='?other=1'
  if(change==='body'||change==='id')f[vf.job.url].raw=`<script type="application/ld+json">${JSON.stringify({...vf.jobPosting,...(change==='body'?{description:''}:{identifier:'WrongID'})})}</script>`
  if(change==='detail-denied')f[vf.job.url]={raw:'',status:403}
  const r=await cli(['detail','--source','work-in-finland','--id',vf.job.id],'1',f)
  expect(r.exit).toBe(1);expect(r.stdout).toBe('');expect(JSON.parse(r.stderr.trim().split("\n").at(-1)!).meta.errors.length).toBeGreaterThan(0)
  if(['employer','url'].includes(change))expect(r.requests).toHaveLength(1)
 }
})

test('WIF derives only supported URL ID and detail checker refusal sends no detail request',async()=>{
 const f=vttResponses(),scan=parseWorkInFinland(f[url].body)
 expect(scan.jobs[0].id).toBe(vf.job.id)
 const requests:string[]=[]
 await expect(fetchWorkInFinlandDetail(vf.job.id,undefined,{gate:async u=>u!==vf.job.url,fetchImpl:(async u=>{const key=String(u);requests.push(key);return new Response(f[key].raw??JSON.stringify(f[key].body),{headers:{'content-type':key===url?'application/json':'text/html'}})}) as typeof fetch})).rejects.toThrow('vtt_detail_robots_unconfirmed')
 expect(requests).toEqual([url,vb])
})

const ju='https://www.jobly.fi/en/job/synthetic-scientist-900001',jc='https://www.jobly.fi/tyopaikka/synthetic-scientist-900001'
const jh=readFileSync(path.join(import.meta.dir,'fixtures/jobly-vtt-sanitized.html'),'utf8')
const jd='<h2>Responsibilities</h2><p>Synthetic protein research duties.</p><h2>Requirements</h2><p>Synthetic research qualifications.</p>'
function jf():Record<string,any>{return {[url]:{body:body([{...row(ju),employer:{name:'VTT',city:'Espoo'}}])},[ju]:{raw:jh,headers:{'content-type':'text/html'}}}}
test('Jobly独立ID、语言canonical和原链接保留，其他雇主或外链不派生ID',async()=>{
 const j=parseWorkInFinland(jf()[url].body).jobs[0];expect(j).toMatchObject({id:'jobly:900001',url:ju,date:null})
 const d=await parseJoblyVttDetail(jh,j);expect(d).toMatchObject({id:'jobly:900001',source_job_id:'900001',id_namespace:'jobly',source_url:ju,url:jc,canonical_url:jc,date:null,needs_detail:false,detail_source:'jobly'});expect(d.description).toBe(jd)
 for(const link of [ju+'?track=unknown',ju+'#section',ju.replace('www.jobly.fi','evil.example'),jc])expect(parseWorkInFinland(body([{...row(link),employer:{name:'VTT'}}])).jobs[0].id).toBeUndefined()
 expect(parseWorkInFinland(body([{...row(ju),employer:{name:'Other'}}])).jobs[0].id).toBeUndefined()
})
test('Jobly错ID/canonical/雇主/标题、缺正文和歧义结构均失败',async()=>{
 const j=parseWorkInFinland(jf()[url].body).jobs[0]
 for(const h of [jh.replace('tyopaikka/synthetic-scientist-900001','tyopaikka/synthetic-scientist-900002'),jh.replace('tyopaikka/synthetic-scientist','tyopaikka/other-slug'),jh.replace('https://www.jobly.fi/tyopaikka','https://evil.example/tyopaikka'),jh.replace('"name":"VTT"','"name":"Other"'),jh.replace('"title":"Synthetic scientist"','"title":"Wrong role"'),jh.replace(jd,''),jh.replace('Requirements</h2>','Other section</h2>').replace('qualifications','skills'),jh.replace('"@type":"JobPosting"','"@type":"JobPosting","identifier":"900002"'),jh.replace('"@type":"JobPosting"','"@type":"JobPosting","url":"https://evil.example/job"'),jh.replace('</head>','<link rel="canonical" href="'+jc+'"></head>'),jh.replace('"@type":"JobPosting"','"@type":"Other"')])await expect(parseJoblyVttDetail(h,j)).rejects.toThrow()
 await expect(parseJoblyVttDetail(jh,{...j,id:'900001'})).rejects.toThrow()
})
test('真实CLI子进程WIF→Jobly仅两请求，保留元数据并消费临时去重状态',async()=>{
 const s=await cli(['search','--source','work-in-finland'],'1',jf());expect(JSON.parse(s.stdout).results[0].id).toBe('jobly:900001')
 const r=await cli(['detail','--source','work-in-finland','--id','jobly:900001'],'1',jf()),j=JSON.parse(r.stdout)
 expect(r.exit).toBe(0);expect(r.checkerCalls).toBe(2);expect(r.requests.map(x=>x.url)).toEqual([url,ju]);expect(j.description).toBe(jd);expect(j.source_url).toBe(ju);expect(j.canonical_url).toBe(jc)
 expect(j.meta.coverage.map((x:any)=>[x.source,x.status,x.requests])).toEqual([['work-in-finland','partial',1],['jobly','partial',1]]);expect(j.independent_full_JD_completeness).toBe('unverified');verifyDetailState(j,'finland')
 const query='research scientist',f=jf();f[workInFinlandUrl(query)]=f[url];delete f[url];expect((await cli(['detail','--source','work-in-finland','--id','jobly:900001','--query',query],'1',f)).exit).toBe(0)
 const plain=await cli(['detail','--source','work-in-finland','--id','jobly:900001','--format','plain'],'1',jf());expect(plain.stdout).toContain(jd);expect(JSON.parse(plain.stderr).meta.coverage[1].source).toBe('jobly')
})
test('真实Jobly checker拒绝或未知不发送详情请求，未模拟请求无网络回退',async()=>{
 for(const mode of ['deny','']){const r=await cli(['detail','--source','work-in-finland','--id','jobly:900001'],'1',jf(),mode);expect(r.exit).toBe(1);expect(r.checkerCalls).toBe(2);expect(r.requests.map(x=>x.url)).toEqual([url]);expect(JSON.parse(r.stderr.trim().split('\n').at(-1)!).meta.coverage[1]).toMatchObject({source:'jobly',status:'unknown',requests:0})}
 const f=jf();delete f[ju];const r=await cli(['detail','--source','work-in-finland','--id','jobly:900001'],'1',f);expect(r.exit).toBe(1);expect(r.requests[1].fixture).toBe(false);expect(r.stderr).toContain('request_failed')
})
test('Jobly限流、访问错误和解析失败保留partial/errors，不重试或当作关闭',async()=>{
 for(const [status,coverage] of [[403,'blocked'],[404,'unknown'],[429,'rate_limited'],[503,'unknown'],[302,'unknown']] as const){
  const f=jf();f[ju]={raw:'',status,headers:{'content-type':'text/html','retry-after':'120',location:'https://evil.example'}}
  const r=await cli(['detail','--source','work-in-finland','--id','jobly:900001'],'1',f),e=JSON.parse(r.stderr.trim().split('\n').at(-1)!);expect(r.exit).toBe(1);expect(r.requests.map(x=>x.url)).toEqual([url,ju]);expect(e.meta.coverage[0].status).toBe('partial');expect(e.meta.coverage[1].status).toBe(coverage);expect(e.meta.errors.length).toBeGreaterThan(0);if(status===429)expect(e.meta.coverage[1].retry_after).toBe('120')
 }
 for(const response of [{raw:'{}',headers:{'content-type':'application/json'}},{raw:'<title>Just a moment</title>',headers:{'content-type':'text/html'}},{raw:'',headers:{'content-type':'text/html','content-length':'2097153'}},{raw:jh.replace('tyopaikka/synthetic-scientist-900001','tyopaikka/other-900001'),headers:{'content-type':'text/html'}}]){const f=jf();f[ju]=response;const r=await cli(['detail','--source','work-in-finland','--id','jobly:900001'],'1',f);expect(r.exit).toBe(1);expect(r.stdout).toBe('');expect(JSON.parse(r.stderr.trim().split('\n').at(-1)!).meta.coverage[1].status).not.toBe('valid_empty')}
})
test('Jobly命名空间不可混用；歧义ID和无效ID在详情请求前拒绝',async()=>{
 for(const id of ['jobly:0','jobly:01','jobly:900001x','jobly:900001#']){const r=await cli(['detail','--source','work-in-finland','--id',id],'1',jf());expect(r.exit).toBe(1);expect(r.requests).toEqual([]);expect(r.checkerCalls).toBe(0)}
 const f=jf();f[url].body.jobs.push({...row(ju.replace('synthetic-scientist','other-slug')),employer:{name:'VTT'}});const r=await cli(['detail','--source','work-in-finland','--id','jobly:900001'],'1',f);expect(r.exit).toBe(1);expect(r.requests.map(x=>x.url)).toEqual([url])
})
