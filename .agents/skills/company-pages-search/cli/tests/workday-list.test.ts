import { test, expect } from 'bun:test'
import { collectWorkdayPages, parseWorkdayDetail } from '../src/workday'
import path from 'node:path'
const fixtures = process.env.WORKDAY_FIXTURES!
for (const company of ['iff','novonesis']) {
  test(`${company}: second page total zero with twenty jobs is not empty or terminal`, async () => {
    const first = await Bun.file(path.join(fixtures, `${company}-1.json`)).json()
    const second = await Bun.file(path.join(fixtures, `${company}-2.json`)).json()
    const offsets: number[] = []
    const result = await collectWorkdayPages({company, boardUrl:`https://${company}.wd5.myworkdayjobs.com/en-US/Test`, maxPages: 3,
      getPage: async (offset) => { offsets.push(offset); return {status:200, data:offset===0?first:offset===20?second:{total:0,jobPostings:[]}} }})
    expect(offsets).toEqual([0,20,40]); expect(result.jobs.length).toBe(40); expect(result.initial_total).toBe(first.total); expect(result.coverage).toBe('partial'); expect(result.reason).toBe('empty_before_initial_total')
  })
}
test('empty is valid only for empty first page and zero total', async () => {
 const r = await collectWorkdayPages({company:'Example',boardUrl:'https://example.wd5.myworkdayjobs.com/Test',getPage:async()=>({status:200,data:{total:0,jobPostings:[]}})})
 expect(r.coverage).toBe('valid_empty')
})
test('duplicate page and request budget produce partial coverage', async () => {
 const first=await Bun.file(path.join(fixtures,'iff-1.json')).json()
 const r=await collectWorkdayPages({company:'Example',boardUrl:'https://example.wd5.myworkdayjobs.com/Test',getPage:async()=>({status:200,data:first})})
 expect(r.coverage).toBe('partial');expect(r.reason).toBe('repeated_page');expect(r.jobs.length).toBe(20)
 const b=await collectWorkdayPages({company:'Example',boardUrl:'https://example.wd5.myworkdayjobs.com/Test',maxPages:1,getPage:async()=>({status:200,data:first})})
 expect(b.reason).toBe('page_budget_exhausted')
})
test('403, 429 and malformed payload cannot become empty lists', async () => {
 for(const [status,data,expected] of [[403,null,'blocked'],[429,null,'rate_limited'],[200,{},'parse_failed']] as const) {
 const r=await collectWorkdayPages({company:'Example',boardUrl:'https://example.wd5.myworkdayjobs.com/Test',getPage:async()=>({status,data})});expect(r.coverage).toBe(expected)
 }
})
test('suffix variants preserve distinct raw identities and URLs', async () => {
 const entries = ['R123-1','R123-2'].map(id => ({title:'Example', externalPath:'/job/City/Role_'+id, bulletFields:['R123']}))
 const r=await collectWorkdayPages({company:'Example',boardUrl:'https://example.wd5.myworkdayjobs.com/Test',getPage:async()=>({status:200,data:{total:2,jobPostings:entries}})})
 expect(r.jobs.map(j=>j.id)).toEqual(['R123-1','R123-2']);expect(r.jobs[0].url).not.toBe(r.jobs[1].url)
})

for (const [company,host,board] of [['iff','iff.wd5.myworkdayjobs.com','IFF_Careers'],['novonesis','novonesis.wd103.myworkdayjobs.com','Novonesis_Careers']]) {
 test(`${company} detail matches list identity and rejects missing or mismatched data`, async () => {
  const page=await Bun.file(path.join(fixtures,`${company}-1.json`)).json(); const payload=await Bun.file(path.join(fixtures,`${company}-detail.json`)).json()
  const scan=await collectWorkdayPages({company,boardUrl:`https://${host}/en-US/${board}`,maxPages:1,getPage:async()=>({status:200,data:page})})
  const job=scan.jobs[0];const detail=parseWorkdayDetail(job,payload);expect(detail.description.length).toBeGreaterThan(0);expect(detail.id).toBe(job.id)
  expect(()=>parseWorkdayDetail(job,{jobPostingInfo:{...payload.jobPostingInfo,jobReqId:'R999999'}})).toThrow('detail_identity_mismatch')
  expect(()=>parseWorkdayDetail(job,{jobPostingInfo:{...payload.jobPostingInfo,jobDescription:''}})).toThrow('detail_jd_missing')
 })
}
test('guard denies redirects before any request to target', async () => {
 const {guardedWorkdayRequest}=await import('../src/workday')
 const calls:string[]=[];const checks:string[]=[]
 const response=await guardedWorkdayRequest('https://iff.wd5.myworkdayjobs.com/wday/cxs/iff/IFF_Careers/jobs',{method:'POST'}, {gate:async u=>{checks.push(u);return checks.length===1},fetchImpl:async (u)=>{calls.push(String(u));return new Response('',{status:302,headers:{location:'/forbidden'}})}})
 expect(response.status).toBe(0);expect(response.reason).toBe('robots_permission_unconfirmed');expect(checks.length).toBe(2);expect(calls.length).toBe(1)
})
test('CLI search propagates pagination budget and unique results from fixture transport', async () => {
 const {runSearch}=await import('../src/commands/search');const {mkdtempSync,writeFileSync,rmSync}=await import('node:fs');const {tmpdir}=await import('node:os')
 const dir=mkdtempSync(path.join(tmpdir(),'workday-cli-')),registry=path.join(dir,'company_pages.json');const prev=process.env.COMPANY_PAGES_REGISTRY;const original=process.stdout.write;let output='';let count=0
 const page=await Bun.file(path.join(fixtures,'iff-1.json')).json();writeFileSync(registry,JSON.stringify([{name:'Fixture',ats:'workday',ats_id:'',careers_url:'https://iff.wd5.myworkdayjobs.com/IFF_Careers'}]));process.env.COMPANY_PAGES_REGISTRY=registry
 try { process.stdout.write=((chunk:any)=>{output+=String(chunk);return true}) as typeof process.stdout.write
 const code=await runSearch({company:'Fixture',format:'json'},{gate:async()=>true,fetchImpl:async()=>{count++;return new Response(JSON.stringify(page),{status:200,headers:{'Content-Type':'application/json'}})}})
 const x=JSON.parse(output);expect(code).toBe(0);expect(count).toBe(2);expect(x.results.length).toBe(20);expect(x.meta.coverage[0].status).toBe('partial');expect(x.meta.coverage[0].reason).toBe('repeated_page')
 } finally {process.stdout.write=original;if(prev===undefined)delete process.env.COMPANY_PAGES_REGISTRY;else process.env.COMPANY_PAGES_REGISTRY=prev;rmSync(dir,{recursive:true,force:true})}
})


test('unknown guard, errors and malformed paths never produce protected requests', async () => {
 const {guardedWorkdayRequest}=await import('../src/workday');let calls=0
 for (const gate of [async()=>false, async()=>{throw new Error('checker failed')}]) {
  const r=await guardedWorkdayRequest('https://iff.wd5.myworkdayjobs.com/wday/cxs/iff/IFF_Careers/jobs',{method:'POST'},{gate,fetchImpl:async()=>{calls++;return new Response('{}')}})
  expect(r.reason).toBe('robots_permission_unconfirmed')
 }
 expect(calls).toBe(0)
 const r=await collectWorkdayPages({company:'X',boardUrl:'https://x.wd5.myworkdayjobs.com/Test',getPage:async()=>({status:200,data:{total:1,jobPostings:[{title:'X',externalPath:'/job/%2e%2e/X_R123',bulletFields:['R123']}]}})})
 expect(r.coverage).toBe('partial');expect(r.jobs).toHaveLength(0)
})
test('empty contradiction, 404, 500 and timeout stay unconfirmed', async () => {
 const base={company:'X',boardUrl:'https://x.wd5.myworkdayjobs.com/Test'}
 const empty=await collectWorkdayPages({...base,getPage:async()=>({status:200,data:{total:2,jobPostings:[]}})})
 expect(empty.coverage).toBe('partial');expect(empty.reason).toBe('empty_before_initial_total')
 for(const status of [404,500]) expect((await collectWorkdayPages({...base,getPage:async()=>({status})})).coverage).toBe('unknown')
 expect((await collectWorkdayPages({...base,getPage:async()=>{throw new Error('timeout')}})).coverage).toBe('unknown')
})
test('CLI enforces five page budget and propagates partial coverage', async () => {
 const {runSearch}=await import('../src/commands/search');const {mkdtempSync,writeFileSync,rmSync}=await import('node:fs');const {tmpdir}=await import('node:os')
 const dir=mkdtempSync(path.join(tmpdir(),'workday-budget-')),registry=path.join(dir,'registry.json');const prev=process.env.COMPANY_PAGES_REGISTRY;const original=process.stdout.write;let output='';let count=0
 writeFileSync(registry,JSON.stringify([{name:'Fixture',ats:'workday',ats_id:'',careers_url:'https://iff.wd5.myworkdayjobs.com/IFF_Careers'}]));process.env.COMPANY_PAGES_REGISTRY=registry
 try {process.stdout.write=((chunk:any)=>{output+=String(chunk);return true}) as typeof process.stdout.write
 const code=await runSearch({company:'Fixture',format:'json'},{gate:async()=>true,fetchImpl:async(_u,init)=>{count++;const offset=JSON.parse(String(init?.body)).offset;const entries=Array.from({length:20},(_,i)=>({title:'Role',externalPath:`/job/City/Role_R${offset+i+1}`,bulletFields:[`R${offset+i+1}`]}));return new Response(JSON.stringify({total:1000,jobPostings:entries}))}})
 const x=JSON.parse(output);expect(code).toBe(0);expect(count).toBe(5);expect(x.results).toHaveLength(100);expect(x.meta.coverage[0].reason).toBe('page_budget_exhausted')
 }finally{process.stdout.write=original;if(prev===undefined)delete process.env.COMPANY_PAGES_REGISTRY;else process.env.COMPANY_PAGES_REGISTRY=prev;rmSync(dir,{recursive:true,force:true})}
})
test('CLI detail joins only matching fixture and gates list and detail separately', async () => {
 const {runDetail}=await import('../src/commands/detail');const {mkdtempSync,writeFileSync,rmSync}=await import('node:fs');const {tmpdir}=await import('node:os')
 const dir=mkdtempSync(path.join(tmpdir(),'workday-detail-')),registry=path.join(dir,'registry.json');const prev=process.env.COMPANY_PAGES_REGISTRY;const original=process.stdout.write;let output='';const checks:string[]=[]
 const page=await Bun.file(path.join(fixtures,'iff-1.json')).json();const payload=await Bun.file(path.join(fixtures,'iff-detail.json')).json();const raw=page.jobPostings[0].externalPath.match(/_((?:JR|R)\d+(?:-\d+)?)$/i)[1]
 writeFileSync(registry,JSON.stringify([{name:'Fixture',ats:'workday',ats_id:'',careers_url:'https://iff.wd5.myworkdayjobs.com/IFF_Careers'}]));process.env.COMPANY_PAGES_REGISTRY=registry
 try {process.stdout.write=((chunk:any)=>{output+=String(chunk);return true}) as typeof process.stdout.write
 const code=await runDetail({company:'Fixture',id:raw,format:'json'},{gate:async u=>{checks.push(u);return true},fetchImpl:async(_u,init)=>new Response(JSON.stringify(init?.method==='GET'?payload:{total:1,jobPostings:[page.jobPostings[0]]}))})
 expect(code).toBe(0);const result=JSON.parse(output);expect(result.id).toBe(raw);expect(result.description.length).toBeGreaterThan(0);expect(checks).toHaveLength(2);expect(checks[0]).toEndWith('/jobs');expect(checks[1]).toEndWith(page.jobPostings[0].externalPath)
 }finally{process.stdout.write=original;if(prev===undefined)delete process.env.COMPANY_PAGES_REGISTRY;else process.env.COMPANY_PAGES_REGISTRY=prev;rmSync(dir,{recursive:true,force:true})}
})
test('conflicting paths for a duplicate id remain partial', async () => {
 const rows=['One','Two'].map(city=>({title:'Role',externalPath:`/job/${city}/Role_R123`,bulletFields:['R123']}))
 const r=await collectWorkdayPages({company:'X',boardUrl:'https://x.wd5.myworkdayjobs.com/Test',getPage:async()=>({status:200,data:{total:2,jobPostings:rows}})})
 expect(r.jobs).toHaveLength(1);expect(r.coverage).toBe('partial');expect(r.reason).toBe('invalid_listing')
})
test('a detail identity mismatch is reported by the CLI', async () => {
 const {runDetail}=await import('../src/commands/detail');const {mkdtempSync,writeFileSync,rmSync}=await import('node:fs');const {tmpdir}=await import('node:os')
 const dir=mkdtempSync(path.join(tmpdir(),'workday-detail-fail-')),registry=path.join(dir,'registry.json');const prev=process.env.COMPANY_PAGES_REGISTRY;const original=process.stderr.write;let output=''
 const page=await Bun.file(path.join(fixtures,'iff-1.json')).json();const payload=await Bun.file(path.join(fixtures,'iff-detail.json')).json();const raw=page.jobPostings[0].externalPath.match(/_((?:JR|R)\d+(?:-\d+)?)$/i)[1]
 writeFileSync(registry,JSON.stringify([{name:'Fixture',ats:'workday',ats_id:'',careers_url:'https://iff.wd5.myworkdayjobs.com/IFF_Careers'}]));process.env.COMPANY_PAGES_REGISTRY=registry
 try {process.stderr.write=((chunk:any)=>{output+=String(chunk);return true}) as typeof process.stderr.write
 const code=await runDetail({company:'Fixture',id:raw,format:'json'},{gate:async()=>true,fetchImpl:async(_u,init)=>new Response(JSON.stringify(init?.method==='GET'?{jobPostingInfo:{...payload.jobPostingInfo,jobReqId:'R999999'}}:{total:1,jobPostings:[page.jobPostings[0]]}))})
 expect(code).toBe(1);expect(output).toContain('detail_identity_mismatch')
 }finally{process.stderr.write=original;if(prev===undefined)delete process.env.COMPANY_PAGES_REGISTRY;else process.env.COMPANY_PAGES_REGISTRY=prev;rmSync(dir,{recursive:true,force:true})}
})
test('CLI 429 stops immediately and reports Retry-After', async () => {
 const {runSearch}=await import('../src/commands/search');const {mkdtempSync,writeFileSync,rmSync}=await import('node:fs');const {tmpdir}=await import('node:os')
 const dir=mkdtempSync(path.join(tmpdir(),'workday-429-')),registry=path.join(dir,'registry.json');const prev=process.env.COMPANY_PAGES_REGISTRY;const original=process.stdout.write;let output='';let calls=0
 writeFileSync(registry,JSON.stringify([{name:'Fixture',ats:'workday',ats_id:'',careers_url:'https://iff.wd5.myworkdayjobs.com/IFF_Careers'}]));process.env.COMPANY_PAGES_REGISTRY=registry
 try {process.stdout.write=((chunk:any)=>{output+=String(chunk);return true}) as typeof process.stdout.write
 await runSearch({company:'Fixture',format:'json'},{gate:async()=>true,fetchImpl:async()=>{calls++;return new Response('',{status:429,headers:{'Retry-After':'120'}})}})
 const x=JSON.parse(output);expect(calls).toBe(1);expect(x.meta.coverage[0].status).toBe('rate_limited');expect(x.meta.coverage[0].reason).toBe('retry_after:120');expect(x.results).toHaveLength(0)
 }finally{process.stdout.write=original;if(prev===undefined)delete process.env.COMPANY_PAGES_REGISTRY;else process.env.COMPANY_PAGES_REGISTRY=prev;rmSync(dir,{recursive:true,force:true})}
})
test('multi-location text and unknown dates are preserved without invention', async () => {
 const r=await collectWorkdayPages({company:'X',boardUrl:'https://x.wd5.myworkdayjobs.com/Test',getPage:async()=>({status:200,data:{total:1,jobPostings:[{title:'Role',externalPath:'/job/City/Role_R123',bulletFields:['R123'],locationsText:'2 Locations'}]}})})
 expect(r.jobs[0].location).toBe('2 Locations');expect(r.jobs[0].date).toBeNull();expect(r.jobs[0].posted_raw).toBeNull();expect(r.jobs[0].date_source).toBeNull()
})
test('default Workday gate invokes real checker in strict mode and denies protected requests', async () => {
 const {guardedWorkdayRequest}=await import('../src/workday');const {mkdtempSync,writeFileSync,rmSync}=await import('node:fs');const {tmpdir}=await import('node:os')
 const dir=mkdtempSync(path.join(tmpdir(),'workday-real-checker-'));const oldPath=process.env.PATH;let calls=0
 const argumentsPath=path.join(dir,'curl-args')
 writeFileSync(path.join(dir,'curl'), `#!/bin/sh\nprintf '%s\\n' "$@" > "${argumentsPath}"\nprintf 'denied\\n403'\n`,{mode:0o755});process.env.PATH=dir+path.delimiter+(oldPath ?? '')
 try {
  const r=await guardedWorkdayRequest('https://iff.wd5.myworkdayjobs.com/wday/cxs/iff/IFF_Careers/jobs',{method:'POST'},{fetchImpl:async()=>{calls++;return new Response('{}')}})
  expect(r.status).toBe(0);expect(r.reason).toBe('robots_permission_unconfirmed');expect(calls).toBe(0)
  const args=(await Bun.file(argumentsPath).text()).trim().split('\n');expect(args).not.toContain('-L');expect(args).not.toContain('--max-redirs');expect(args[args.indexOf('-A')+1]).toBe('company-pages-search-skill')
 } finally {if(oldPath===undefined)delete process.env.PATH;else process.env.PATH=oldPath;rmSync(dir,{recursive:true,force:true})}
})
