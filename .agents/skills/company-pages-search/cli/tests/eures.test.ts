import { test, expect } from 'bun:test'
import { readFileSync, writeFileSync, existsSync, mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { EURES_SEARCH, euresBody, parseEuresList, fetchEuresList, euresDetailUrl, parseEuresDetail, fetchEuresDetail, euresBaOriginal, parseEuresBaOriginal } from '../src/eures.js'
import { ROBOTS_CHECK_PY, UA } from '../src/helpers.js'
const fixture = JSON.parse(readFileSync(new URL('fixtures/eures-list-synthetic.json', import.meta.url), 'utf8'))
const detailFixture = JSON.parse(readFileSync(new URL('fixtures/eures-detail-synthetic.json', import.meta.url), 'utf8'))
const detailID = 'fixture-detail-1', detailURL = euresDetailUrl(detailID)
const detailError = (stderr: string) => JSON.parse(stderr.trim().split('\n').at(-1)!)
const baURL = 'https://www.arbeitsagentur.de/jobsuche/jobdetail/synthetic-reference'
const baHTML = readFileSync(new URL('fixtures/eures-ba-synthetic.html', import.meta.url), 'utf8')
const baPost = JSON.parse(/<script type="application\/ld\+json">([\s\S]*?)<\/script>/.exec(baHTML)![1])
function baAPI() { const d=structuredClone(detailFixture);d.jvProfiles.de.title+=' (Synthetic classification)';(d.jvProfiles.de as any).applicationInstructions=['Source: https://other-source.invalid/posting ; '+baURL];return d }
const baFixtures = () => ({[detailURL]:{data:baAPI()},[baURL]:{raw:baHTML}})
const response = (data:unknown,status=200,headers={}) => new Response(JSON.stringify(data),{status,headers:{'content-type':'application/json',...headers}})

test('provisional list preserves exact IDs/suffixes, dedup and unknown metadata; never claims a canonical page/JD',()=>{
  const s=parseEuresList(fixture)
  expect(s.jobs.map(j=>j.id)).toEqual(['fixture-job','fixture-job-1','fixture-job-2']);expect(s.coverage).toBe('partial');expect(s.received_count).toBe(4)
  for(const j of s.jobs){expect(j).toMatchObject({company:'',location:null,date:null,date_source:null,canonical_url:null,url_kind:'unverified_api_detail_reference',needs_detail:true,portal:'eures'});expect(j).not.toHaveProperty('description');expect(j.url).toContain('/public/jv/id/'+j.id+'?');expect(Number.isFinite(Date.parse(j.observed_at))).toBe(true)}
  expect(s.errors).toContain('provisional_leads_require_employer_canonical_link_and_JD_verification')
  const conflict=parseEuresList({numberRecords:3,jvs:[{id:'same',title:'A'},{id:'same',title:'B'},{id:'same',title:'A'}]})
  expect(conflict.jobs).toEqual([]);expect(conflict.coverage).toBe('parse_failed')
  const encoded=parseEuresList({numberRecords:1,jvs:[{id:'namespace:001/02',title:'A'}]});expect(encoded.jobs[0].id).toBe('namespace:001/02');expect(encoded.jobs[0].url).toContain('namespace%3A001%2F02')
})
test('explicit empty differs from malformed/error/invalid identity and nonempty zero totals; one-page cap enforced',()=>{
  expect(parseEuresList({numberRecords:0,jvs:[]}).coverage).toBe('valid_empty')
  expect(parseEuresList({numberRecords:3,jvs:[]}).coverage).toBe('unknown')
  for(const x of [null,{},[],{numberRecords:'0',jvs:[]},{numberRecords:0,jvs:[],error:'denied'},{numberRecords:0,jvs:[],success:false},{numberRecords:0,jvs:[],errors:['oops']},{numberRecords:1,jvs:[{id:'a'}]},{numberRecords:1,jvs:[{id:123,title:'A'}]},{numberRecords:1,jvs:[{id:'..',title:'A'}]}])expect(parseEuresList(x).coverage).toBe('parse_failed')
  const inconsistent=parseEuresList({numberRecords:0,jvs:[{id:'a',title:'A'}]});expect(inconsistent.jobs).toHaveLength(1);expect(inconsistent.coverage).toBe('partial');expect(inconsistent.errors).toContain('nonempty_rows_inconsistent_declared_total')
  expect(parseEuresList({numberRecords:20,jvs:Array.from({length:11},(_,i)=>({id:String(i),title:'A'}))}).coverage).toBe('unknown')
})
test('checker denied/unknown/missing never issues protected POST; minimal accepted body remains fixed',async()=>{
  let calls=0
  for(const gate of [async()=>false,async()=>undefined as any,async()=>{throw Error('missing checker')}]){
    const s=await fetchEuresList({gate,fetchImpl:(async()=>{calls++;return response(fixture)}) as typeof fetch});expect(s.requests).toBe(0);expect(s.coverage).toBe('unknown')
  }
  expect(calls).toBe(0)
  const checker=Bun.spawn(['python3','-B',ROBOTS_CHECK_PY,EURES_SEARCH+'-extra','--strict','--user-agent',UA.split('/')[0]],{env:{...process.env,COMPANY_OFFLINE_EURES_ROBOTS_FIXTURE:'1'},stdout:'pipe',stderr:'pipe'})
  expect(await new Response(checker.stdout).text()).toContain('DISALLOWED');expect(await checker.exited).toBe(1)
  const {sessionId,...body}=euresBody();expect(sessionId).toMatch(/^[a-z0-9]+$/);expect(body).toEqual({page:1,resultsPerPage:10,sortSearch:'BEST_MATCH',keywords:[],minNumberPost:null,requestLanguage:'en'})
})
test('evidenced EVERYWHERE keyword is forwarded literally; invalid criteria fail before checker or POST',async()=>{
  expect(euresBody('  protein  ').keywords).toEqual([{keyword:'protein',specificSearchCode:'EVERYWHERE'}])
  expect(euresBody('protein engineer').keywords[0].keyword).toBe('protein engineer') // serialization only; no claim about live phrase semantics
  let calls=0
  for(const query of ['', '  ', 'protein\nassay', 'a'.repeat(201), 123 as any]){
    expect(()=>euresBody(query)).toThrow('invalid_eures_keyword')
    const scan=await fetchEuresList({gate:async()=>{calls++;return true},fetchImpl:(async()=>{calls++;return response(fixture)}) as typeof fetch},query)
    expect(scan).toMatchObject({coverage:'unknown',requests:0,errors:['invalid_eures_keyword']})
  }
  expect(calls).toBe(0)
})
test('one POST only, real transport options, 403/404/429/5xx/redirect stop and Retry-After retained',async()=>{
  for(const [status,coverage] of [[403,'blocked'],[404,'unknown'],[429,'rate_limited'],[503,'unknown'],[302,'unknown']] as const){
    let calls=0
    const s=await fetchEuresList({gate:async(u)=>{expect(u).toBe(EURES_SEARCH);return true},fetchImpl:(async(u,init)=>{calls++;expect(String(u)).toBe(EURES_SEARCH);expect(init).toMatchObject({method:'POST',redirect:'manual',credentials:'omit'});expect(init?.signal).toBeDefined();return response({},status,{'retry-after':'120',location:'https://outside.example'})}) as typeof fetch})
    expect(calls).toBe(1);expect(s.coverage).toBe(coverage);expect(s.jobs).toEqual([]);expect(s.requests).toBe(1);if(status===429)expect(s.retry_after).toBe('120')
  }
})
test('timeout, media/JSON/body/read/response-URL failures cannot become valid empty',async()=>{
  const changed=response(fixture);Object.defineProperty(changed,'url',{value:'https://outside.example'})
  const broken=new Response(new ReadableStream({start(c){c.error(Error('read failure'))}}),{headers:{'content-type':'application/json'}})
  for(const r of [changed,broken,new Response('{',{headers:{'content-type':'application/json'}}),new Response('<title>Challenge</title>',{headers:{'content-type':'text/html'}}),new Response('é'.repeat(1048577),{headers:{'content-type':'application/json'}}),response({},200,{'content-length':String(3*1024*1024)})]){
    const s=await fetchEuresList({gate:async()=>true,fetchImpl:(async()=>r) as typeof fetch});expect(s.jobs).toEqual([]);expect(s.coverage).not.toBe('valid_empty');expect(s.errors.length).toBeGreaterThan(0)
  }
  expect((await fetchEuresList({gate:async()=>true,fetchImpl:(async()=>{throw Error('timeout')}) as typeof fetch})).coverage).toBe('unknown')
})

async function cli(args:string[],opts:{mode?:string;fixtures?:Record<string,unknown>;cwd?:'project'|'temporary'}={}){
  const dir=mkdtempSync(path.join(tmpdir(),'eures-data-')),data=path.join(dir,'responses.json'),log=path.join(dir,'fetch.log'),curl=path.join(dir,'curl.log')
  writeFileSync(data,JSON.stringify(opts.fixtures ?? {[EURES_SEARCH]:{data:fixture}}))
  try{
    const proc=Bun.spawn([process.execPath,'run','--preload',process.env.COMPANY_OFFLINE_PRELOAD!,'--preload',path.join(import.meta.dir,'fixtures/eures-offline.ts'),path.join(import.meta.dir,'../src/cli.ts'),...args],{cwd:opts.cwd==='temporary'?dir:path.resolve(import.meta.dir,'../../../../..'),env:{...process.env,COMPANY_PAGES_REGISTRY:path.join(dir,'MISSING.json'),COMPANY_OFFLINE_EURES_RESPONSES:data,COMPANY_OFFLINE_EURES_FETCH_LOG:log,COMPANY_OFFLINE_CURL_LOG:curl,COMPANY_OFFLINE_EURES_ROBOTS_FIXTURE:opts.mode??'1'},stdout:'pipe',stderr:'pipe'})
    const stdout=await new Response(proc.stdout).text(),stderr=await new Response(proc.stderr).text(),exit=await proc.exited
    return{stdout,stderr,exit,requests:existsSync(log)?readFileSync(log,'utf8').trim().split('\n').map(x=>JSON.parse(x)):[],checkerCalls:existsSync(curl)?readFileSync(curl,'utf8').trim().split('\n').length:0}
  }finally{rmSync(dir,{recursive:true,force:true})}
}
test('real CLI child with explicit deny preload and real strict checker supports missing registry and different cwd',async()=>{
  for(const cwd of ['project','temporary'] as const){
    const r=await cli(['search','--source','eures'],{cwd}),s=JSON.parse(r.stdout)
    expect(r.exit).toBe(0);expect(r.checkerCalls).toBe(1);expect(r.requests).toHaveLength(1);expect(r.requests[0]).toMatchObject({url:EURES_SEARCH,method:'POST',body:{page:1,resultsPerPage:10,keywords:[]}})
    expect(s.results.map((j:any)=>j.id)).toEqual(['fixture-job','fixture-job-1','fixture-job-2']);expect(s.meta.coverage[0]).toMatchObject({source:'eures',status:'partial',requests:1,received_count:4});expect(s.meta.errors.length).toBeGreaterThan(0)
  }
  const filtered=await cli(['search','--source','eures','--query','protein','--limit','1'],{fixtures:{[EURES_SEARCH]:{data:fixture,expectedKeyword:'protein'}}});expect(JSON.parse(filtered.stdout).results).toHaveLength(1);expect(filtered.requests[0].body.keywords).toEqual([{keyword:'protein',specificSearchCode:'EVERYWHERE'}])
  const zero=JSON.parse((await cli(['search','--source','eures','--location','not in this page'])).stdout);expect(zero.results).toEqual([]);expect(zero.meta.coverage[0].status).toBe('partial');expect(zero.meta.errors.length).toBeGreaterThan(0)
  for(const format of ['plain','table']){const r=await cli(['search','--source','eures','--format',format]);expect(r.exit).toBe(0);expect(JSON.parse(r.stderr).coverage[0].status).toBe('partial')}
})
test('CLI server keyword preserves description-only matches, query scope, partial/errors and query-specific empty',async()=>{
  const data={numberRecords:25,jvs:[{id:'description-match-1',title:'Cell analyst',description:'Synthetic protein assay description.'}]}
  const fixtures={[EURES_SEARCH]:{data,expectedKeyword:'protein'}}
  const r=await cli(['search','--source','eures','--query','  protein  '],{fixtures,cwd:'temporary'}),s=JSON.parse(r.stdout)
  expect(r.exit).toBe(0);expect(r.checkerCalls).toBe(1);expect(r.requests).toHaveLength(1)
  expect(r.requests[0].body).toMatchObject({page:1,resultsPerPage:10,keywords:[{keyword:'protein',specificSearchCode:'EVERYWHERE'}]});expect(r.requests[0].body).not.toHaveProperty('locationCodes')
  expect(s.results).toHaveLength(1);expect(s.results[0]).toMatchObject({id:'description-match-1',title:'Cell analyst',date:null,canonical_url:null,needs_detail:true})
  expect(s.meta.coverage[0]).toMatchObject({status:'partial',query_scope:'server_everywhere',country_scope:'unfiltered',reason:'one_server_keyword_page_provisional_leads',requests:1});expect(s.meta.errors.length).toBeGreaterThan(0)
  const empty=JSON.parse((await cli(['search','--source','eures','--query','protein'],{fixtures:{[EURES_SEARCH]:{data:{numberRecords:0,jvs:[]},expectedKeyword:'protein'}}})).stdout)
  expect(empty.results).toEqual([]);expect(empty.meta.coverage[0]).toMatchObject({status:'valid_empty',query_scope:'server_everywhere',reason:'explicit_empty_this_query_page_only'})
  for(const mode of ['deny','']){
    const denied=await cli(['search','--source','eures','--query','protein'],{mode,fixtures});expect(denied.requests).toEqual([]);expect(JSON.parse(denied.stdout).meta.coverage[0]).toMatchObject({status:'unknown',query_scope:'server_everywhere',requests:0})
  }
  const unmatched=await cli(['search','--source','eures','--query','different term'],{fixtures});expect(JSON.parse(unmatched.stdout).meta.coverage[0].status).toBe('unknown');expect(unmatched.requests).toHaveLength(1)
})
test('CLI refusal/unknown has no POST; empty/error/unmocked stay distinct and preserve source errors/Retry-After',async()=>{
  for(const mode of ['deny','']){const r=await cli(['search','--source','eures'],{mode}),s=JSON.parse(r.stdout);expect(r.requests).toEqual([]);expect(r.checkerCalls).toBe(1);expect(s.meta.coverage[0].status).toBe('unknown');expect(s.meta.errors).toHaveLength(1)}
  for(const [f,status] of [[{data:{jvs:[],numberRecords:0}},'valid_empty'],[{data:{error:'oops',jvs:[],numberRecords:0}},'parse_failed'],[{raw:'{'},'parse_failed'],[{status:429,data:{},headers:{'retry-after':'120'}},'rate_limited']] as const){
    const r=await cli(['search','--source','eures'],{fixtures:{[EURES_SEARCH]:f}}),s=JSON.parse(r.stdout);expect(r.requests).toHaveLength(1);expect(s.meta.coverage[0].status).toBe(status);if(status==='rate_limited'){expect(s.meta.coverage[0].retry_after).toBe('120');expect(s.meta.errors).toHaveLength(1)}
  }
  const absent=await cli(['search','--source','eures'],{fixtures:{}});expect(absent.requests[0].fixture).toBe(false);expect(JSON.parse(absent.stdout).meta.coverage[0].status).toBe('unknown')
})
test('unsupported detail/list and company combinations stop before registry, checker or fetch',async()=>{
  for(const args of [['detail','--source','work-in-finland','--id','fixture-job'],['detail','--source','eures','--company','Fixture','--id',detailID],['list','--source','eures'],['search','--source','eures','--company','Fixture']]){
    const r=await cli(args);expect(r.exit).toBe(1);expect(r.checkerCalls).toBe(0);expect(r.requests).toEqual([]);expect(r.stderr).toContain('BAD_ARG');expect(r.stderr).not.toContain('NO_REGISTRY')
  }
})
test('observed detail structure preserves exact ID and complete provided field, without claiming full JD or canonical',()=>{
  const d=structuredClone(detailFixture);d.jvProfiles.de.description+='\n'+('Synthetic paragraph. '.repeat(500))
  const job=parseEuresDetail(d,{id:detailID,title:d.jvProfiles.de.title})
  expect(job).toMatchObject({id:detailID,title:d.jvProfiles.de.title,company:'Synthetic employer',language:'de',location:'Fixture city, XX',description:d.jvProfiles.de.description,date:null,date_source:null,needs_detail:true,canonical_url:null,JD_completeness:'unverified',body_coverage:'provided_description_field_read',title_crosscheck:'matched'})
  expect(job.url).toBe(detailURL);expect(JSON.stringify(job)).not.toContain('DO_NOT_EMIT');expect(JSON.stringify(job)).not.toContain('employer.invalid')
  expect(euresDetailUrl('fixture-detail-1-2')).not.toBe(detailURL)
  expect(euresDetailUrl('namespace:a/b')).toContain('namespace%3Aa%2Fb')
})
test('detail identity, title, profile, employer or body gaps fail closed; no silent language/body substitution',()=>{
  for(const edit of [(d:any)=>{delete d.id},(d:any)=>{d.id+='-2'},(d:any)=>{delete d.jvProfiles.de.title},(d:any)=>{d.jvProfiles.de.description=' '},(d:any)=>{delete d.jvProfiles.de.employer.name},(d:any)=>{d.errors={message:'blocked'}},(d:any)=>{d.errorMessage='blocked'},(d:any)=>{delete d.preferredLanguage;d.jvProfiles.en=d.jvProfiles.de}]){
    const d=structuredClone(detailFixture);edit(d);expect(()=>parseEuresDetail(d,{id:detailID})).toThrow()
  }
  expect(()=>parseEuresDetail(detailFixture,{id:detailID,title:'Wrong listing title'})).toThrow('eures_detail_title_unconfirmed')
  for(const id of ['', '..', 'a\nb', '\ud800'])expect(()=>euresDetailUrl(id)).toThrow()
})
test('detail GET is separately gated and bounded; refusal/unknown makes zero requests; failures never imply closure',async()=>{
  let calls=0
  for(const gate of [async()=>false,async()=>undefined as any,async()=>{throw Error('missing checker')}] ){
    const r=await fetchEuresDetail(detailID,{gate,fetchImpl:(async()=>{calls++;return response(detailFixture)}) as typeof fetch});expect(r.job).toBeNull();expect(r.scan).toMatchObject({coverage:'unknown',requests:0})
  }
  expect(calls).toBe(0)
  for(const [status,expected] of [[403,'blocked'],[404,'unknown'],[429,'rate_limited'],[503,'unknown'],[302,'unknown']] as const){
    let requests=0
    const r=await fetchEuresDetail(detailID,{gate:async u=>{expect(u).toBe(detailURL);return true},fetchImpl:(async(u,init)=>{requests++;expect(String(u)).toBe(detailURL);expect(init).toMatchObject({method:'GET',redirect:'manual',credentials:'omit'});expect(init?.body).toBeUndefined();return response({},status,{'retry-after':'90'})}) as typeof fetch})
    expect(requests).toBe(1);expect(r.job).toBeNull();expect(r.scan.coverage).toBe(expected);if(status===429)expect(r.scan.retry_after).toBe('90')
  }
})
test('real detail CLI child preserves warnings/partial and never scans list; exact robots fixture is isolated',async()=>{
  const fixtures={[detailURL]:{data:detailFixture}}, args=['detail','--source','eures','--id',detailID]
  const r=await cli(args,{mode:'detail',fixtures,cwd:'temporary'}),job=JSON.parse(r.stdout)
  expect(r.exit).toBe(0);expect(r.requests).toHaveLength(1);expect(r.checkerCalls).toBe(1);expect(r.requests[0]).toMatchObject({url:detailURL,method:'GET',body:null})
  expect(job).toMatchObject({id:detailID,description:detailFixture.jvProfiles.de.description,date:null,needs_detail:true,canonical_url:null,JD_completeness:'unverified',title_crosscheck:'not_performed'})
  expect(job.meta.coverage[0]).toMatchObject({source:'eures',status:'partial',requests:1,scope:'one_selected_detail'});expect(job.meta.errors[0].error).toBe('canonical_and_full_JD_unverified')
  const plain=await cli([...args,'--format','plain'],{mode:'detail',fixtures});expect(plain.exit).toBe(0);expect(plain.stdout).toContain(detailFixture.jvProfiles.de.description);expect(JSON.parse(plain.stderr).coverage[0].status).toBe('partial')
  for(const mode of ['1','deny','']){const denied=await cli(args,{mode,fixtures});expect(denied.exit).toBe(1);expect(denied.requests).toEqual([]);expect(detailError(denied.stderr).meta.coverage[0]).toMatchObject({status:'unknown',requests:0})}
  for(const [data,status] of [[{...detailFixture,id:'wrong'},'parse_failed'],[{},'parse_failed']] as const){const bad=await cli(args,{mode:'detail',fixtures:{[detailURL]:{data}}});expect(bad.exit).toBe(1);expect(detailError(bad.stderr).meta.coverage[0].status).toBe(status)}
  const limited=await cli(args,{mode:'detail',fixtures:{[detailURL]:{status:429,data:{},headers:{'retry-after':'90'}}}});expect(detailError(limited.stderr).meta.coverage[0]).toMatchObject({status:'rate_limited',retry_after:'90'})
  const unmocked=await cli(args,{mode:'detail',fixtures:{}});expect(unmocked.exit).toBe(1);expect(detailError(unmocked.stderr).meta.coverage[0].status).toBe('unknown')
})
test('original link is supplied, exact-reference and fixed-host only; no URL construction or unrelated origin fetching',()=>{
  expect(euresBaOriginal(baAPI(),'de')).toEqual({url:baURL,reference:'synthetic-reference'})
  expect(euresBaOriginal(detailFixture,'de')).toBeNull()
  for(const link of ['https://attacker.invalid/jobsuche/jobdetail/synthetic-reference',baURL+'?token=x',baURL+'#apply','https://user@www.arbeitsagentur.de/jobsuche/jobdetail/synthetic-reference','http://www.arbeitsagentur.de/jobsuche/jobdetail/synthetic-reference']){
    const data=baAPI();(data.jvProfiles.de as any).applicationInstructions=[link];expect(euresBaOriginal(data,'de')).toBeNull()
  }
  const bad=baAPI();(bad.jvProfiles.de as any).applicationInstructions=[baURL+'-2'];expect(()=>euresBaOriginal(bad,'de')).toThrow('eures_original_reference_mismatch')
})
test('original JobPosting is the sole JD fact source; identity is independent and raw feed provenance/meaningful hyphens survive',async()=>{
  const source=baAPI(),apiJob=parseEuresDetail(source,{id:detailID}),original={url:baURL,reference:'synthetic-reference'}
  const job=await parseEuresBaOriginal(baHTML,original,apiJob)
  expect(job).toMatchObject({id:detailID,title:baPost.title,description:baPost.description,source_title:source.jvProfiles.de.title,source_description:source.jvProfiles.de.description,source_api_url:detailURL,canonical_url:baURL,url:baURL,needs_detail:false,JD_completeness:'canonical_JobPosting_description_read',canonical_title_relation:'canonical_title_plus_feed_classification',date:null,date_source:null})
  expect(job.description).toContain('-20 C');expect(job.description).toContain('3-5');expect(job.description).not.toContain('Synthetische Stellenbeschreibung');expect(job.description).not.toContain('Unrelated page navigation')
  const html=(post:any,canonical=baURL)=>`<link rel="canonical" href="${canonical}"><script type="application/ld+json">${JSON.stringify(post)}</script>`
  for(const edit of [(p:any)=>{p.identifier.value+='-2'},(p:any)=>{p.url+='-2'},(p:any)=>{p.title='Different role'},(p:any)=>{p.hiringOrganization.name='Different employer'},(p:any)=>{p.description='<h2>Ihre Aufgaben</h2><p>Synthetic duties only.</p>'},(p:any)=>{delete p.description}]){
    const post=structuredClone(baPost);edit(post);await expect(parseEuresBaOriginal(html(post),original,apiJob)).rejects.toThrow()
  }
  await expect(parseEuresBaOriginal(html(baPost,baURL+'-2'),original,apiJob)).rejects.toThrow('eures_original_identity_ambiguous')
  await expect(parseEuresBaOriginal(html(baPost,''),original,apiJob)).rejects.toThrow('eures_original_identity_ambiguous')
  await expect(parseEuresBaOriginal(html(baPost)+html(baPost),original,apiJob)).rejects.toThrow('eures_original_identity_ambiguous')
  await expect(parseEuresBaOriginal('<link rel="canonical" href="'+baURL+'"><script type="application/ld+json">{</script>',original,apiJob)).rejects.toThrow()
})
test('original-page guard is a separate permission and stops before its GET; both responses share the fixed request/byte budget',async()=>{
  for(const permission of [false,undefined,'throw'] as const){
    const events:string[]=[]
    const r=await fetchEuresDetail(detailID,{gate:async u=>{events.push('gate:'+u);if(u===detailURL)return true;if(permission==='throw')throw Error('checker unavailable');return permission as any},fetchImpl:(async u=>{events.push('fetch:'+String(u));return response(baAPI())}) as typeof fetch})
    expect(events).toEqual(['gate:'+detailURL,'fetch:'+detailURL,'gate:'+baURL]);expect(r.job).toBeNull();expect(r.scan).toMatchObject({coverage:'unknown',requests:1})
  }
  for(const [status,expected] of [[403,'blocked'],[404,'unknown'],[429,'rate_limited'],[503,'unknown'],[302,'unknown']] as const){
    const urls:string[]=[]
    const r=await fetchEuresDetail(detailID,{gate:async()=>true,fetchImpl:(async(u,init)=>{urls.push(String(u));expect(init).toMatchObject({method:'GET',redirect:'manual',credentials:'omit'});return String(u)===detailURL?response(baAPI()):new Response('',{status,headers:{'content-type':'text/html','retry-after':'80'}})}) as typeof fetch})
    expect(urls).toEqual([detailURL,baURL]);expect(r.job).toBeNull();expect(r.scan).toMatchObject({coverage:expected,requests:2});if(status===429)expect(r.scan.retry_after).toBe('80')
  }
})
test('real CLI original reader emits source-only JD/partial and exact provenance; denial/unknown/parse failure has no downgrade',async()=>{
  const args=['detail','--source','eures','--id',detailID], fixtures=baFixtures()
  const r=await cli(args,{mode:'original',fixtures,cwd:'temporary'}),job=JSON.parse(r.stdout)
  expect(r.exit).toBe(0);expect(r.requests.map((q:any)=>q.url)).toEqual([detailURL,baURL]);expect(r.requests.every((q:any)=>q.method==='GET')).toBe(true);expect(r.checkerCalls).toBe(2)
  expect(job).toMatchObject({description:baPost.description,title:baPost.title,source_description:detailFixture.jvProfiles.de.description,canonical_url:baURL,needs_detail:false,date:null});expect(job.meta.coverage[0]).toMatchObject({status:'partial',requests:2});expect(job.meta.errors).toEqual([])
  const plain=await cli([...args,'--format','plain'],{mode:'original',fixtures});expect(plain.exit).toBe(0);expect(plain.stdout).toContain(baPost.description);expect(plain.stdout).not.toContain(detailFixture.jvProfiles.de.description);expect(JSON.parse(plain.stderr).coverage[0].requests).toBe(2)
  for(const mode of ['original-deny','original-unknown']){const denied=await cli(args,{mode,fixtures});expect(denied.exit).toBe(1);expect(denied.checkerCalls).toBe(2);expect(denied.requests.map((q:any)=>q.url)).toEqual([detailURL]);expect(detailError(denied.stderr).meta.coverage[0]).toMatchObject({status:'unknown',requests:1})}
  for(const page of [{status:429,raw:'',headers:{'retry-after':'80'}},{raw:'<title>Access denied</title>'},{raw:'<html>No JobPosting</html>'}]){
    const bad=await cli(args,{mode:'original',fixtures:{...fixtures,[baURL]:page}});expect(bad.exit).toBe(1);expect(bad.requests).toHaveLength(2);expect(bad.stdout).toBe('');expect(detailError(bad.stderr).meta.coverage[0].status).not.toBe('valid_empty')
  }
})
test('isolated downstream lookup consumes synthetic detail identity without altering null dates or state; rule blocks ingestion',async()=>{
  const r=await cli(['detail','--source','eures','--id',detailID],{mode:'detail',fixtures:{[detailURL]:{data:detailFixture}}}),job=JSON.parse(r.stdout)
  expect(r.exit).toBe(0);expect(job.needs_detail).toBe(true);expect(job.meta.coverage[0].status).toBe('partial')
  // Skills may live outside the project; reuse the production checker locator.
  const root=path.resolve(path.dirname(ROBOTS_CHECK_PY),'..'),rule=readFileSync(path.join(root,'.claude/skills/job-scraper/SKILL.md'),'utf8').split('#### 1g.')[1].split('### Step 2:')[0]
  expect(rule).toContain('Do not write these leads into Step 4/state');expect(rule).toContain('JD_completeness')
  const original=await cli(['detail','--source','eures','--id',detailID],{mode:'original',fixtures:baFixtures()}),canonical=JSON.parse(original.stdout);expect(original.exit).toBe(0);expect(canonical.needs_detail).toBe(false)
  for(const [sample,expectedErrors] of [[job,1],[canonical,0]] as const){
    const dir=mkdtempSync(path.join(tmpdir(),'eures-state-data-')),state=path.join(dir,'state.json'),tracker=path.join(dir,'tracker.csv'),input=path.join(dir,'input.json')
    const saved=JSON.stringify({seen:{fixture:{...sample,posted_date:null,market:'europe',status:'scraped'}}})
    writeFileSync(state,saved);writeFileSync(tracker,'Company,Role\n');writeFileSync(input,JSON.stringify([sample,sample]))
    try{
      const p=Bun.spawn(['python3','-B',path.join(root,'tools/scrape_state.py'),'lookup','--state',state,'--tracker',tracker,'--input',input],{env:process.env,stdout:'pipe',stderr:'pipe'})
      const out=await new Response(p.stdout).text(),err=await new Response(p.stderr).text();expect(await p.exited).toBe(0);expect(err).toBe('');expect(JSON.parse(out).map((v:any)=>v.decision)).toEqual(['seen_url','seen_url'])
      expect(readFileSync(state,'utf8')).toBe(saved);expect(sample.date).toBeNull();expect(sample.meta.errors).toHaveLength(expectedErrors)
    }finally{rmSync(dir,{recursive:true,force:true})}
  }
})

test('acceptance decoder resolves HTML entities exactly once and preserves meaningful punctuation/numbers',async()=>{
  const decoder=path.join(path.dirname(path.dirname(ROBOTS_CHECK_PY)),'tools/company-cli-offline/decode-html-text.py')
  const p=Bun.spawn(['python3','-B',decoder],{env:process.env,stdin:'pipe',stdout:'pipe',stderr:'pipe'})
  p.stdin.write('R&amp;D&nbsp;X-ray -20 C; 3&#45;5 &amp;amp; &#x1F9EC; &unknown;');p.stdin.end()
  const out=await new Response(p.stdout).text(),err=await new Response(p.stderr).text()
  expect(await p.exited).toBe(0);expect(err).toBe('');expect(JSON.parse(out)).toBe('R&D X-ray -20 C; 3-5 &amp; 🧬 &unknown;')
})
test('acceptance text containment fixes the entity false-negative but still rejects missing text and changed hyphens',async()=>{
  const decoder=path.join(path.dirname(path.dirname(ROBOTS_CHECK_PY)),'tools/company-cli-offline/decode-html-text.py')
  async function decode(text:string){const p=Bun.spawn(['python3','-B',decoder],{env:process.env,stdin:'pipe',stdout:'pipe',stderr:'pipe'});p.stdin.write(text);p.stdin.end();const out=await new Response(p.stdout).text();expect(await new Response(p.stderr).text()).toBe('');expect(await p.exited).toBe(0);return JSON.parse(out) as string}
  const body='Synthetic R&D X-ray checks at -20 C, 3-5 years.',page='Header Synthetic R&amp;D&nbsp;X-ray checks at -20 C, 3-5 years. Footer'
  expect(page.includes(body)).toBe(false)
  expect((await decode(page)).includes(await decode(body))).toBe(true)
  for(const bad of [page.replace('X-ray','Xray'),page.replace('3-5','35'),page.replace('checks at ',''),page.replace('-20','20')])expect((await decode(bad)).includes(await decode(body))).toBe(false)
})
