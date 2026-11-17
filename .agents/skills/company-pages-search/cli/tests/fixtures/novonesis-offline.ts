// Exact synthetic response replay only; never falls through to real fetch.
import { readFileSync, appendFileSync } from 'node:fs'

const responses = JSON.parse(readFileSync(process.env.COMPANY_OFFLINE_NOVONESIS_RESPONSES!, 'utf8'))
const api = 'https://novonesis.wd103.myworkdayjobs.com/wday/cxs/novonesis/Novonesis_Careers'
const detail = api + '/job/Fixture-City/Synthetic-scientist_R77001-1'

globalThis.fetch = async (input, init) => {
  const url = String(input), method = init?.method ?? 'GET'
  let key = ''
  if (url === api + '/jobs' && method === 'POST') {
    const body = JSON.parse(String(init?.body))
    if (body.limit === 20 && [0, 20].includes(body.offset) && body.searchText === '' && JSON.stringify(body.appliedFacets) === '{}') {
      key = `POST ${url} offset=${body.offset}`
    }
  } else if (url === detail && method === 'GET') key = `GET ${url}`
  const permitted = !!key && Object.hasOwn(responses, key)
  appendFileSync(process.env.COMPANY_OFFLINE_NOVONESIS_FETCH_LOG!, JSON.stringify({ url, method, key, fixture: permitted }) + '\n')
  if (!permitted) throw Error('OFFLINE_UNMOCKED_FETCH_DENIED')
  if (init?.redirect !== 'manual' || init.credentials !== 'omit') throw Error('OFFLINE_UNSAFE_REQUEST_OPTIONS')
  const fixture = responses[key]
  return Response.json(fixture.body, { status: fixture.status ?? 200, headers: fixture.headers })
}
