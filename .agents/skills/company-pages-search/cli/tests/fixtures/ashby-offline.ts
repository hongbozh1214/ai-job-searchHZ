// Explicit response fixtures only. The preceding production-test preload denies
// every fetch; this override never falls through to the real transport.
import { readFileSync, appendFileSync } from 'node:fs'
const responses = JSON.parse(readFileSync(process.env.COMPANY_OFFLINE_ASHBY_RESPONSES!, 'utf8'))
const allowed = new Set(['cradlebio', 'adaptyv', 'basecamp-research'].map(b => `https://api.ashbyhq.com/posting-api/job-board/${b}`))
globalThis.fetch = async (input, init) => {
  const url = String(input)
  if (process.env.COMPANY_OFFLINE_ASHBY_FETCH_LOG) appendFileSync(process.env.COMPANY_OFFLINE_ASHBY_FETCH_LOG, url + '\n')
  if (!allowed.has(url) || !Object.hasOwn(responses, url)) {
    if (process.env.COMPANY_OFFLINE_ASHBY_FETCH_LOG) appendFileSync(process.env.COMPANY_OFFLINE_ASHBY_FETCH_LOG, 'OFFLINE_UNMOCKED_FETCH_DENIED\n')
    throw Error('OFFLINE_UNMOCKED_FETCH_DENIED')
  }
  if (init?.redirect !== 'manual' || init.credentials !== 'omit') throw Error('OFFLINE_UNSAFE_REQUEST_OPTIONS')
  const fixture = responses[url]
  return new Response(typeof fixture.body === 'string' ? fixture.body : JSON.stringify(fixture.body), { status: fixture.status ?? 200, headers: fixture.headers })
}
