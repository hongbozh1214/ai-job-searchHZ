import './preload.ts'
import { mkdtempSync, readFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { resolve, join, delimiter } from 'node:path'
import { fileURLToPath } from 'node:url'
const dir=fileURLToPath(new URL('.',import.meta.url)), root=resolve(dir,'../..'), cli=join(root,'.agents/skills/company-pages-search/cli')
const preload=join(dir,'preload.ts'), bun=process.execPath
const markerDir=mkdtempSync(join(tmpdir(),'company-offline-')), marker=join(markerDir,'curl.log')
const env={...process.env,COMPANY_OFFLINE_CURL_LOG:marker,PATH:dir+delimiter+(process.env.PATH ?? ''),COMPANY_OFFLINE_PRELOAD:preload}
delete env.COMPANY_OFFLINE_ROBOTS_FIXTURE
delete env.COMPANY_OFFLINE_ASHBY_ROBOTS_FIXTURE
delete env.COMPANY_OFFLINE_NOVONESIS_ROBOTS_FIXTURE
delete env.COMPANY_OFFLINE_JOBLY_ROBOTS_FIXTURE
delete env.COMPANY_OFFLINE_WIF_ROBOTS_FIXTURE
delete env.COMPANY_OFFLINE_EURAXESS_ROBOTS_FIXTURE
delete env.COMPANY_OFFLINE_EURES_ROBOTS_FIXTURE
const suite = process.argv[2] ?? 'vtt'
// All suites run the same default-deny selfchecks before any fixture is enabled.
if (!['vtt', 'ashby', 'novonesis', 'work-in-finland', 'euraxess', 'eures'].includes(suite) || process.argv.length > 3) throw Error('Only vtt, ashby, novonesis, work-in-finland, euraxess or eures offline suites are allowed')
async function run(label:string,args:string[],expect:string, expectedExit:number) {
 const proc=Bun.spawn(args,{env,cwd:cli,stdout:'pipe',stderr:'pipe'})
 const out=await new Response(proc.stdout).text(),err=await new Response(proc.stderr).text(),code=await proc.exited
 if(code!==expectedExit || !(out+err).includes(expect)) throw Error(`${label}: failed to prove rejection (exit ${code})`)
 console.log(`${label}: PASS`)
}
await run('main fetch',[bun,'--preload',preload,'--eval',"try { await fetch('https://offline.invalid'); process.exit(2) } catch(e) { console.log(e.message) }"],'OFFLINE_UNMOCKED_FETCH_DENIED',0)
const registry=join(markerDir,'registry.json')
await Bun.write(registry,JSON.stringify([{name:'offline fixture',ats:'generic',ats_id:'',careers_url:'https://offline.invalid/careers'}]))
const child=Bun.spawn([bun,'run','--preload',preload,join(cli,'src/cli.ts'),'search','--company','offline fixture','--format','json'],{env:{...env,COMPANY_PAGES_REGISTRY:registry},cwd:cli,stdout:'pipe',stderr:'pipe'})
const childOut=await new Response(child.stdout).text(), childErr=await new Response(child.stderr).text(), childExit=await child.exited
if(childExit!==0 || !(childOut+childErr).includes('OFFLINE_UNMOCKED_FETCH_DENIED')) throw Error('CLI child: denial unconfirmed')
console.log('CLI child fetch: PASS')
await run('checker curl',[join(dir,'curl'),'https://offline.invalid/robots.txt'],'OFFLINE_CURL_DENIED',97)
// Verify the real checker invokes the deny stub, without relying on DNS.
const check=Bun.spawn(['python3','-B',join(root,'tools/robots_check.py'),'https://offline.invalid/job','--strict'],{env,cwd:cli,stdout:'pipe',stderr:'pipe'})
const output=await new Response(check.stdout).text(),err=await new Response(check.stderr).text(),exit=await check.exited
if(exit!==1 || !output.includes('UNCONFIRMED') || readFileSync(marker,'utf8').split('stub_invoked').length-1 !== 2) throw Error(`checker refused test failed: ${exit} ${err}`)
console.log('real checker: PASS (unconfirmed, deny stub)')
// This suite reviews workflow rules and runs only the existing Python state CLI
// against synthetic temporary data. No collector, requests or JD replay runs.
// Python is not sandboxed by the Bun preload; its reviewed call chain has no
// network I/O, and still inherits the curl deny stub. This is not system isolation.
const checks=suite==='work-in-finland'
 ? [{args:[bun,'test','--preload',preload,'tests/work-in-finland.test.ts'],cwd:cli},
    {args:['python3','-B','-m','unittest','discover','-s','tests','-p','test_work_in_finland_contract.py'],cwd:root}]
 : [{args:[bun,'test','--preload',preload,`tests/${suite}.test.ts`],cwd:cli}]
for(const check of checks) {
 const t=Bun.spawn(check.args,{env,cwd:check.cwd,stdout:'inherit',stderr:'inherit'}), rc=await t.exited
 if(rc!==0){rmSync(markerDir,{recursive:true,force:true});process.exit(rc)}
}
rmSync(markerDir,{recursive:true,force:true})
