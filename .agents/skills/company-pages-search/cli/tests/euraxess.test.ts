import { verifyDetailState } from './fixtures/verified-detail-state.js'
import { test, expect } from 'bun:test'
import { readFileSync, writeFileSync, existsSync, mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { EURAXESS_LIST, euraxessId, parseEuraxessList, parseEuraxessDetail, fetchEuraxessList, fetchEuraxessDetail } from '../src/euraxess.js'
const list=readFileSync(new URL('fixtures/euraxess-list-sanitized.html',import.meta.url),'utf8')
const detail=readFileSync(new URL('fixtures/euraxess-detail-sanitized.html',import.meta.url),'utf8')
const url='https://euraxess.ec.europa.eu/jobs/800001'
const body=(text:string,status=200,headers={})=>new Response(text,{status,headers:{'content-type':'text/html',...headers}})

test('sanitized real list structure preserves numeric URL identity, unknown employer/date and partial',async()=>{
  const scan=await parseEuraxessList(list)
  expect(scan.jobs).toHaveLength(1);expect(scan.coverage).toBe('partial')
  expect(scan.jobs[0]).toMatchObject({id:'800001',url,title:'Synthetic researcher',company:'',date:null,date_source:null,needs_detail:true})
  expect(scan.errors).toContain('list_employer_unverified_requires_detail')
  const card=list.match(/<article[\s\S]*<\/article>/)![0]
  const duplicate=await parseEuraxessList(list.replace('</body>',card+'</body>'))
  expect(duplicate.jobs).toHaveLength(1)
  const conflict=await parseEuraxessList(list.replace('</body>',card.replace('Synthetic researcher','Other identity')+'</body>'))
  expect(conflict.jobs).toHaveLength(0);expect(conflict.coverage).toBe('parse_failed')
  for(const u of ['https://evil.example/jobs/800001',url+'?other=1',url+'#fragment','https://user:pass@euraxess.ec.europa.eu/jobs/800001'])expect(euraxessId(u)).toBeNull()
})
test('only explicit empty is empty; shell or missing title/ID remains failed/unverified',async()=>{
  expect((await parseEuraxessList('<h2>Search results (0)</h2>')).coverage).toBe('valid_empty')
  for(const h of ['<title>Search</title>','<h2>Search results (20)</h2>',list.replace('/jobs/800001','/jobs/search'),list.replace('Synthetic researcher','')])expect((await parseEuraxessList(h)).coverage).toBe('parse_failed')
})
test('detail uses list ID + explicit canonical + title; preserves description/requirements and unknown publication',async()=>{
  const selected=(await parseEuraxessList(list)).jobs[0], job=await parseEuraxessDetail(detail,selected)
  expect(job).toMatchObject({id:'800001',url,company:'Fixture University',date:null,date_source:null,needs_detail:false,deadline:'2026-11-16',coverage:'partial',id_source:'list_url_and_detail_canonical_path'})
  for(const label of ['Offer Description','Requirements','Additional Information'])expect(String(job.description)).toContain(label)
  expect(String(job.description)).toContain('Synthetic responsibilities and requirements.')
  const hidden=detail.replace('<div class="ecl">','<div class="ecl"><script>EVIL_MARKER</script><div hidden>EVIL_MARKER</div>')
  expect(String((await parseEuraxessDetail(hidden,selected)).description)).not.toContain('EVIL_MARKER')
  for(const h of [detail.replace('href="'+url+'"','href="https://euraxess.ec.europa.eu/jobs/800002"'),detail.replace('<h1>Synthetic researcher</h1>','<h1>Wrong title</h1>'),detail.replace('Organisation/Company','Unknown metadata'),detail.replace('>Offer Description</h2>','>Other section</h2>'),detail.replace('>Requirements</h2>','>Other section</h2>')])await expect(parseEuraxessDetail(h,selected)).rejects.toThrow()
})
test('checker deny, unknown and failure never reach the protected request',async()=>{
  let calls=0
  for(const gate of [async()=>false,async()=>undefined as any,async()=>{throw Error('missing checker')}]){
    const scan=await fetchEuraxessList({gate,fetchImpl:(async()=>{calls++;return body(list)}) as typeof fetch})
    expect(scan.coverage).toBe('unknown');expect(scan.requests).toBe(0)
  }
  expect(calls).toBe(0)
})
test('transport stops 403/404/429/5xx/redirect without retry and retains Retry-After',async()=>{
  for(const [status,coverage] of [[403,'blocked'],[404,'unknown'],[429,'rate_limited'],[503,'unknown'],[302,'unknown']] as const){
    let calls=0
    const scan=await fetchEuraxessList({gate:async()=>true,fetchImpl:(async(u,init)=>{calls++;expect(String(u)).toBe(EURAXESS_LIST);expect(init).toMatchObject({method:'GET',redirect:'manual',credentials:'omit'});return body('',status,{'retry-after':'120',location:'https://other.example'})}) as typeof fetch})
    expect(calls).toBe(1);expect(scan.coverage).toBe(coverage);expect(scan.jobs).toEqual([])
    if(status===429)expect(scan.retry_after).toBe('120')
  }
})
test('timeout, body budget, wrong media and challenge are never valid empty',async()=>{
  for(const response of [body('é'.repeat(1048577)),body('<title>Access Denied</title>'),body('{}',200,{'content-type':'application/json'})]){
    const s=await fetchEuraxessList({gate:async()=>true,fetchImpl:(async()=>response) as typeof fetch});expect(s.jobs).toEqual([]);expect(s.coverage).not.toBe('valid_empty')
  }
  expect((await fetchEuraxessList({gate:async()=>true,fetchImpl:(async()=>{throw Error('timeout')}) as typeof fetch})).coverage).toBe('unknown')
  let details=0
  await expect(fetchEuraxessDetail('800002',{gate:async()=>true,fetchImpl:(async()=>{details++;return body(list)}) as typeof fetch})).rejects.toThrow('identity_unconfirmed_first_page')
  expect(details).toBe(1)
})
async function cli(args:string[],mode='1',fixtures:Record<string,unknown>={[EURAXESS_LIST]:{body:list},[url]:{body:detail}}){
  const dir=mkdtempSync(path.join(tmpdir(),'euraxess-data-')),f=path.join(dir,'fixtures.json'),log=path.join(dir,'fetch.log'),curl=path.join(dir,'curl.log')
  writeFileSync(f,JSON.stringify(fixtures))
  try{
    const p=Bun.spawn([process.execPath,'run','--preload',process.env.COMPANY_OFFLINE_PRELOAD!,'--preload',path.join(import.meta.dir,'fixtures/euraxess-offline.ts'),path.join(import.meta.dir,'../src/cli.ts'),...args],{env:{...process.env,COMPANY_PAGES_REGISTRY:path.join(dir,'MISSING.json'),COMPANY_OFFLINE_EURAXESS_RESPONSES:f,COMPANY_OFFLINE_EURAXESS_FETCH_LOG:log,COMPANY_OFFLINE_CURL_LOG:curl,COMPANY_OFFLINE_EURAXESS_ROBOTS_FIXTURE:mode},stdout:'pipe',stderr:'pipe'})
    const stdout=await new Response(p.stdout).text(),stderr=await new Response(p.stderr).text(),exit=await p.exited
    return{stdout,stderr,exit,requests:existsSync(log)?readFileSync(log,'utf8').trim().split('\n').map(x=>JSON.parse(x)):[],checkerCalls:existsSync(curl)?readFileSync(curl,'utf8').trim().split('\n').length:0}
  }finally{rmSync(dir,{recursive:true,force:true})}
}
test('existing CLI source search/detail replay with real strict checker and missing registry',async()=>{
  const s=await cli(['search','--source','euraxess','--query','Synthetic researcher','--limit','1']),scan=JSON.parse(s.stdout)
  expect(s.exit).toBe(0);expect(s.checkerCalls).toBe(1);expect(s.requests.map(r=>r.url)).toEqual([EURAXESS_LIST]);expect(scan.results[0].id).toBe('800001')
  expect(scan.meta.coverage[0]).toMatchObject({source:'euraxess',status:'partial',requests:1});expect(scan.meta.errors.length).toBeGreaterThan(0)
  const d=await cli(['detail','--source','euraxess','--id','800001']),job=JSON.parse(d.stdout)
  expect(d.exit).toBe(0);expect(d.checkerCalls).toBe(2);expect(d.requests.map(r=>r.url)).toEqual([EURAXESS_LIST,url]);expect(job).toMatchObject({id:'800001',company:'Fixture University',date:null,needs_detail:false,requests:2,coverage:'partial'})
  expect(job.description).toContain('Requirements')
})
test('CLI refusal, first-page ID miss and output filtering preserve unknown/partial; invalid source combinations stay offline',async()=>{
  for(const mode of ['deny','']){
    const r=await cli(['search','--source','euraxess'],mode),s=JSON.parse(r.stdout);expect(r.requests).toEqual([]);expect(s.meta.coverage[0].status).toBe('unknown');expect(s.meta.errors).toHaveLength(1)
  }
  const zero=JSON.parse((await cli(['search','--source','euraxess','--limit','0'])).stdout);expect(zero.results).toEqual([]);expect(zero.meta.coverage[0].status).toBe('partial');expect(zero.meta.errors.length).toBeGreaterThan(0)
  const miss=await cli(['detail','--source','euraxess','--id','800002']);expect(miss.exit).toBe(1);expect(miss.requests).toHaveLength(1);expect(miss.stderr).toContain('identity_unconfirmed')
  for(const args of [['detail','--source','euraxess','--id','x'],['search','--source','euraxess','--company','Fixture'],['list','--source','euraxess']]){
    const r=await cli(args);expect(r.exit).toBe(1);expect(r.requests).toEqual([]);expect(r.stderr).not.toContain('NO_REGISTRY')
  }
})

test('EURAXESS CLI detail retains sections, canonical, per-stage coverage/errors and safe failures',async()=>{
 const d=await cli(['detail','--source','euraxess','--id','800001']),j=JSON.parse(d.stdout)
 expect(j.canonical_url).toBe(url);verifyDetailState(j,'europe');expect(j.meta.coverage.map((x:any)=>x.status)).toEqual(['partial','partial']);expect(j.meta.errors).toContainEqual({company:'EURAXESS',error:'list_employer_unverified_requires_detail'});expect(j.date).toBeNull();expect(j.description_format).toBe('text')
 for(const section of ['Offer Description','Requirements','Additional Information'])expect(j.description).toContain(section)
 for(const [modified,status] of [[detail.replace('/jobs/800001','/jobs/800002'),200],[detail.replace('>Requirements</h2>','>Other</h2>'),200],['',429]] as const){
  const r=await cli(['detail','--source','euraxess','--id','800001'],'1',{[EURAXESS_LIST]:{body:list},[url]:{body:modified,status,headers:{'retry-after':'120'}}})
  expect(r.exit).toBe(1);expect(r.stdout).toBe('');const e=JSON.parse(r.stderr.trim().split("\n").at(-1)!);expect(e.meta.coverage[0].status).toBe('partial');expect(e.meta.coverage[1].status).toBe(status===429?'rate_limited':'parse_failed');expect(e.meta.errors.length).toBeGreaterThan(0)
  if(status===429)expect(e.meta.coverage[1].retry_after).toBe('120')
 }
 const deny=await cli(['detail','--source','euraxess','--id','800001'],'deny');expect(deny.requests).toEqual([]);expect(JSON.parse(deny.stderr.trim().split("\n").at(-1)!).meta.coverage[0].status).toBe('unknown')
})
