// Exact synthetic transport replay, layered explicitly after default-deny preload.
import { readFileSync, appendFileSync } from 'node:fs'
const fixtures=JSON.parse(readFileSync(process.env.COMPANY_OFFLINE_EURAXESS_RESPONSES!,'utf8'))
globalThis.fetch=async(input,init)=>{
  const url=String(input), present=Object.hasOwn(fixtures,url)
  appendFileSync(process.env.COMPANY_OFFLINE_EURAXESS_FETCH_LOG!,JSON.stringify({url,fixture:present})+'\n')
  if(!present)throw Error('OFFLINE_UNMOCKED_FETCH_DENIED')
  if(init?.method!=='GET'||init.redirect!=='manual'||init.credentials!=='omit'||!init.signal)throw Error('OFFLINE_UNSAFE_OPTIONS')
  const f=fixtures[url]
  return new Response(f.body,{status:f.status??200,headers:{'content-type':'text/html',...f.headers}})
}
