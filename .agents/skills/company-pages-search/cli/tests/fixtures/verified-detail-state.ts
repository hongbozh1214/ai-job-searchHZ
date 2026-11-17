// Test-only downstream consumption of actual fixture CLI output; no production state.
import { expect } from 'bun:test'
import { ROBOTS_CHECK_PY } from '../../src/helpers.js'
import { mkdtempSync,writeFileSync,readFileSync,rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'
export function verifyDetailState(job:any,market:'europe'|'finland') {
 const dir=mkdtempSync(path.join(tmpdir(),'verified-detail-data-')),state=path.join(dir,'seen.json'),tracker=path.join(dir,'tracker.csv'),input=path.join(dir,'input.json')
 const meta=JSON.stringify(job.meta)
 try {
  expect(job.needs_detail).toBe(false);expect(job.canonical_url).toBe(job.url);expect(job.company.length).toBeGreaterThan(0);expect(job.description.length).toBeGreaterThan(0)
  writeFileSync(state,'{"seen":{}}');writeFileSync(tracker,'company,role,source\n')
  writeFileSync(input,JSON.stringify([{market,status:'new',source:'cli',portal:job.portal,title:job.title,company:job.company,url:job.url,posted_date:job.date,deadline:job.deadline??null}]))
  const script=path.join(path.dirname(ROBOTS_CHECK_PY),'scrape_state.py')
  const call=(cmd:string)=>{const r=Bun.spawnSync(['python3','-B',script,cmd,'--state',state,'--tracker',tracker,'--input',input]);expect(r.exitCode).toBe(0);return JSON.parse(r.stdout.toString())}
  expect(call('lookup')[0].decision).toBe('new');expect(call('add').added).toHaveLength(1);const before=readFileSync(state,'utf8');expect(call('lookup')[0].decision).toBe('seen_url');expect(readFileSync(state,'utf8')).toBe(before)
  const saved:any=Object.values(JSON.parse(before).seen)[0];expect(saved.posted_date).toBeNull();expect(saved.deadline).toBe(job.deadline??null);expect(saved.market).toBe(market);expect(saved.url).toBe(job.canonical_url);expect(JSON.stringify(job.meta)).toBe(meta)
 } finally {rmSync(dir,{recursive:true,force:true})}
}
