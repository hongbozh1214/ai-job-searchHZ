// Explicit synthetic replay after the existing deny preload. Never live fallback.
import { readFileSync, appendFileSync } from 'node:fs'
import { EURES_SEARCH, euresDetailUrl } from '../../src/eures.js'
const fixtures = JSON.parse(readFileSync(process.env.COMPANY_OFFLINE_EURES_RESPONSES!, 'utf8'))
globalThis.fetch = async (input, init) => {
  const url = String(input), detail = url === euresDetailUrl('fixture-detail-1'), original = url === 'https://www.arbeitsagentur.de/jobsuche/jobdetail/synthetic-reference', present = (url === EURES_SEARCH || detail || original) && Object.hasOwn(fixtures, url)
  const body = typeof init?.body === 'string' ? JSON.parse(init.body) : null
  appendFileSync(process.env.COMPANY_OFFLINE_EURES_FETCH_LOG!, JSON.stringify({ url, fixture: present, method: init?.method, body }) + '\n')
  if (!present) throw Error('OFFLINE_UNMOCKED_FETCH_DENIED')
  const f = fixtures[url]
  if (detail || original) {
    const headers = new Headers(init?.headers)
    if (init?.method !== 'GET' || init.body !== undefined || init.redirect !== 'manual' || init.credentials !== 'omit' || !init.signal || headers.has('Authorization') || headers.has('Cookie')) throw Error('OFFLINE_UNSAFE_DETAIL_OPTIONS')
    return new Response(f.raw ?? JSON.stringify(f.data), { status: f.status ?? 200, headers: { 'content-type':original ? 'text/html' : 'application/json', ...f.headers } })
  }
  // Each test explicitly declares its expected server query; never derive the
  // expected body from the implementation or accept arbitrary live criteria.
  const keywords = f.expectedKeyword === undefined ? [] : [{keyword:f.expectedKeyword,specificSearchCode:'EVERYWHERE'}]
  const { sessionId, ...criteria } = body ?? {}
  if (init?.method !== 'POST' || init.redirect !== 'manual' || init.credentials !== 'omit' || !init.signal || typeof sessionId !== 'string' || !/^[a-z0-9]+$/.test(sessionId) || JSON.stringify(criteria) !== JSON.stringify({page:1,resultsPerPage:10,sortSearch:'BEST_MATCH',keywords,minNumberPost:null,requestLanguage:'en'})) throw Error('OFFLINE_UNSAFE_OPTIONS')
  const headers = new Headers(init.headers)
  if (headers.has('Authorization') || headers.has('Cookie') || headers.get('Content-Type') !== 'application/json') throw Error('OFFLINE_UNSAFE_HEADERS')
  return new Response(f.raw ?? JSON.stringify(f.data), {status: f.status ?? 200, headers: {'content-type':'application/json', ...f.headers}})
}
