import {test,expect} from 'bun:test'
import {parseVttList,fetchVttList} from '../src/vtt'
import {mkdtempSync,writeFileSync,rmSync} from 'node:fs'
import {tmpdir} from 'node:os'
import path from 'node:path'
const board='https://www.vttresearch.com/en/careers/come-and-build-future-vtt'
const row=(name:string,id:string)=>`<tr><td>${name}</td><td>Until 1 November</td><td><a href="https://ats.talentadore.com/apply/fixture-role/${id}">See more</a></td></tr>`
const fixture=`<table>${row('Research Scientist','abc123')}${row('Research Scientist','abc123')}${row('Engineer','def456')}</table>`
test('VTT rows retain titles and stable posting IDs and deduplicate',()=>{
 const jobs=parseVttList(fixture,'VTT');expect(jobs.map(j=>j.id)).toEqual(['abc123','def456']);expect(jobs[0].title).toBe('Research Scientist');expect(jobs[0].url).toBe('https://ats.talentadore.com/apply/fixture-role/abc123')
})
test('same ID with conflicting paths fails instead of silently merging',()=>{
 expect(()=>parseVttList(row('A','abc123')+row('A','abc123').replace('fixture-role','another-role'),'VTT')).toThrow('vtt_conflicting_id')
})
test('checker refusal prevents the protected request; 429 and malformed lists stay explicit',async()=>{
 let calls=0;const denied=await fetchVttList('VTT',board,{gate:async()=>false,fetchImpl:async()=>{calls++;return new Response(fixture)}});expect(calls).toBe(0);expect(denied.reason).toBe('robots_permission_unconfirmed')
 const rate=await fetchVttList('VTT',board,{gate:async()=>true,fetchImpl:async()=>new Response('',{status:429,headers:{'retry-after':'60'}})});expect(rate.coverage).toBe('rate_limited');expect(rate.reason).toBe('retry_after:60')
 const bad=await fetchVttList('VTT',board,{gate:async()=>true,fetchImpl:async()=>new Response('<html>unrelated</html>')});expect(bad.coverage).toBe('parse_failed')
})
test('redirect beyond approved VTT board never makes another request',async()=>{
 let calls=0;const r=await fetchVttList('VTT',board,{gate:async()=>true,fetchImpl:async()=>{calls++;return new Response('',{status:302,headers:{location:'https://example.invalid/'}})}});expect(calls).toBe(1);expect(r.reason).toBe('redirect_unconfirmed')
})
test('existing CLI search calls VTT reader with isolated registry and emits partial coverage',async()=>{
 const {runSearch}=await import('../src/commands/search');const dir=mkdtempSync(path.join(tmpdir(),'vtt-cli-'));const file=path.join(dir,'registry.json');const old=process.env.COMPANY_PAGES_REGISTRY;const stdout=process.stdout.write;let output='',calls=0
 writeFileSync(file,JSON.stringify([{name:'VTT fixture',ats:'generic',ats_id:'',careers_url:board}]));process.env.COMPANY_PAGES_REGISTRY=file
 try {process.stdout.write=((chunk:any)=>{output+=String(chunk);return true}) as typeof process.stdout.write
 const code=await runSearch({company:'VTT fixture',format:'json'},{gate:async()=>true,fetchImpl:async()=>{calls++;return new Response(fixture)}});const result=JSON.parse(output)
 expect(code).toBe(0);expect(calls).toBe(1);expect(result.results.map((j:any)=>j.id)).toEqual(['abc123','def456']);expect(result.meta.coverage[0].status).toBe('partial')
 }finally{process.stdout.write=stdout;if(old===undefined)delete process.env.COMPANY_PAGES_REGISTRY;else process.env.COMPANY_PAGES_REGISTRY=old;rmSync(dir,{recursive:true,force:true})}
})
test('CLI process reads the synthetic VTT listing through the real strict checker',async()=>{
 const dir=mkdtempSync(path.join(tmpdir(),'vtt-cli-process-'));const registry=path.join(dir,'registry.json');const mock=path.join(dir,'offline.js')
 writeFileSync(registry,JSON.stringify([{name:'VTT fixture',ats:'generic',ats_id:'',careers_url:board}]))
 writeFileSync(mock,`globalThis.fetch=async (url)=>{if(String(url)!==${JSON.stringify(board)})throw new Error('unexpected network');return new Response(${JSON.stringify(fixture)})}`)
 try {
  const child=Bun.spawn([process.execPath,'run','--preload',process.env.COMPANY_OFFLINE_PRELOAD!, '--preload',mock,path.join(import.meta.dir,'../src/cli.ts'),'search','--company','VTT fixture','--format','json'],{env:{...process.env,COMPANY_OFFLINE_ROBOTS_FIXTURE:'1',COMPANY_PAGES_REGISTRY:registry},stdout:'pipe',stderr:'pipe'})
  const stdout=await new Response(child.stdout).text();const stderr=await new Response(child.stderr).text();const code=await child.exited
  expect(stderr).toBe('');expect(code).toBe(0);const result=JSON.parse(stdout);expect(result.results.map((j:any)=>j.id)).toEqual(['abc123','def456']);expect(result.meta.coverage[0].status).toBe('partial')
 }finally{rmSync(dir,{recursive:true,force:true})}
})

test('detail verifies stable ID, URL, title and nonempty structured description',async()=>{
 const {parseVttDetail}=await import('../src/vtt');const job=parseVttList(fixture,'VTT')[0]
 const detail=(changes:Record<string,unknown>={})=>`<script type="application/ld+json">${JSON.stringify({'@type':'JobPosting',identifier:{value:job.id},url:job.url,title:job.title,description:'<p>Synthetic complete description.</p>',...changes})}</script>`
 expect(parseVttDetail(job,detail(),job.url).description).toContain('Synthetic complete description')
 expect(()=>parseVttDetail(job,detail({identifier:{value:'other'}}),job.url)).toThrow('vtt_detail_identity_mismatch')
 expect(()=>parseVttDetail(job,detail({url:'https://ats.talentadore.com/apply/other/abc123'}),job.url)).toThrow('vtt_detail_identity_mismatch')
 expect(()=>parseVttDetail(job,detail({description:''}),job.url)).toThrow('vtt_detail_description_missing')
 expect(()=>parseVttDetail(job,detail(),'https://ats.talentadore.com/apply/redirect/abc123')).toThrow('vtt_detail_identity_mismatch')
})
test('detail refusal prevents detail request after a permitted listing',async()=>{
 const {fetchVttDetail}=await import('../src/vtt');const requests:string[]=[],checks:string[]=[]
 await expect(fetchVttDetail('VTT',board,'abc123',{gate:async u=>{checks.push(u);return checks.length===1},fetchImpl:async u=>{requests.push(String(u));return new Response(fixture)}})).rejects.toThrow('vtt_detail_robots_unconfirmed')
 expect(checks).toHaveLength(2);expect(requests).toEqual([board])
})
test('CLI detail subprocess reads only matching fixture and returns description',async()=>{
 const dir=mkdtempSync(path.join(tmpdir(),'vtt-detail-process-'));const registry=path.join(dir,'registry.json'),mock=path.join(dir,'offline.js');const real=await Bun.file(path.join(import.meta.dir,'fixtures/vtt-detail-sanitized.json')).json();const job=real.job
 const listing=`<table><tr><td>${job.title}</td><td><a href="${job.url}">See more</a></td></tr></table>`
 const payload=`<script type="application/ld+json">${JSON.stringify(real.jobPosting)}</script>`
 writeFileSync(registry,JSON.stringify([{name:'VTT fixture',ats:'generic',ats_id:'',careers_url:board}]))
 writeFileSync(mock,`globalThis.fetch=async (url)=>{if(String(url)===${JSON.stringify(board)})return new Response(${JSON.stringify(listing)});if(String(url)===${JSON.stringify(job.url)})return new Response(${JSON.stringify(payload)});throw new Error('unexpected network')}`)
 try {const child=Bun.spawn([process.execPath,'run','--preload',process.env.COMPANY_OFFLINE_PRELOAD!, '--preload',mock,path.join(import.meta.dir,'../src/cli.ts'),'detail','--company','VTT fixture','--id',job.id,'--format','json'],{env:{...process.env,COMPANY_OFFLINE_ROBOTS_FIXTURE:'1',COMPANY_PAGES_REGISTRY:registry},stdout:'pipe',stderr:'pipe'})
 const stdout=await new Response(child.stdout).text(),stderr=await new Response(child.stderr).text(),code=await child.exited
 expect(stderr).toBe('');expect(code).toBe(0);const result=JSON.parse(stdout);expect(result.id).toBe(job.id);expect(result.url).toBe(job.url);expect(result.description).toBe(real.jobPosting.description);expect(result.detail_coverage).toBe('structured_description_present')
 }finally{rmSync(dir,{recursive:true,force:true})}
})

test('sanitized real TalentAdore structure preserves ID, URL and description sections',async()=>{
 const {parseVttDetail}=await import('../src/vtt');const f=await Bun.file(path.join(import.meta.dir,'fixtures/vtt-detail-sanitized.json')).json()
 const html=`<div id="job-description">${f.jobPosting.description}</div><script type="application/ld+json">${JSON.stringify(f.jobPosting)}</script>`
 const result=parseVttDetail(f.job,html,f.job.url)
 expect(result.id).toBe(f.jobPosting.identifier.value);expect(result.url).toBe(f.jobPosting.url);expect(result.description).toContain('Who we are looking for');expect(result.description).toContain('In this role')
 expect(()=>parseVttDetail(f.job,html.replace(f.job.id,'different-id'),f.job.url)).toThrow('vtt_detail_identity_mismatch')
})
