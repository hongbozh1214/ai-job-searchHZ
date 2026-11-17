// Exact opt-in synthetic request replay; the default preload still denies all fetch.
import { readFileSync, appendFileSync } from 'node:fs'
const fixtures = JSON.parse(readFileSync(process.env.COMPANY_OFFLINE_WIF_RESPONSES!, 'utf8'))
globalThis.fetch = async (input, init) => {
  const url = String(input), method = init?.method ?? 'GET', present = Object.hasOwn(fixtures, url)
  appendFileSync(process.env.COMPANY_OFFLINE_WIF_FETCH_LOG!, JSON.stringify({ url, method, fixture: present }) + '\n')
  if (!present) throw Error('OFFLINE_UNMOCKED_FETCH_DENIED')
  if (method !== 'GET' || init?.redirect !== 'manual' || init.credentials !== 'omit' || !init.signal) throw Error('OFFLINE_UNSAFE_REQUEST_OPTIONS')
  const f = fixtures[url]
  return new Response(f.raw ?? JSON.stringify(f.body), { status: f.status ?? 200, headers: { 'content-type': 'application/json', ...f.headers } })
}
