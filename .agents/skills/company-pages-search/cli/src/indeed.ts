import { execFile } from "node:child_process"
import { fileURLToPath } from "node:url"
import { promisify } from "node:util"
import type { NormalizedJob } from "./helpers.js"

const PAGE_SIZE = 100
export const INDEED_COUNTRIES = ["FI", "GB", "DK", "DE", "NL", "BE", "CH", "CN"] as const
export type IndeedCountry = typeof INDEED_COUNTRIES[number]

export function isIndeedCountry(value: unknown): value is IndeedCountry {
  return INDEED_COUNTRIES.some(country => country === value)
}

const BRIDGE = fileURLToPath(new URL("./indeed_jobspy.py", import.meta.url))
const run = promisify(execFile)
type Status = "partial" | "valid_empty" | "blocked" | "rate_limited" | "parse_failed" | "unknown"
type Lead = NormalizedJob & {
  portal: "indeed"; country: IndeedCountry; date_source: "indeed_date_on_site" | null
  needs_detail: true; reported_external_url: string | null
}
type Scan = {
  jobs: Lead[]; coverage: Status; reason: string; errors: string[]; requests: number | null
  received_count: number | null; total_jobs: null; total_pages: null; retry_after: string | null
}
type RecordValue = Record<string, unknown>
const record = (value: unknown): RecordValue =>
  value !== null && typeof value === "object" && !Array.isArray(value) ? value as RecordValue : {}
const text = (value: unknown) => typeof value === "string" && value.trim() ? value.trim() : null
const fail = (coverage: Status, reason: string, requests: number | null, retry_after: string | null = null): Scan => ({
  jobs: [], coverage, reason, errors: [reason], requests,
  received_count: null, total_jobs: null, total_pages: null, retry_after,
})

function externalUrl(value: unknown): string | null {
  const raw = text(value)
  if (!raw) return null
  try {
    const url = new URL(raw)
    if (url.protocol !== "https:" || url.username || url.password ||
        url.hostname === "indeed.com" || url.hostname.endsWith(".indeed.com")) return null
    return url.href
  } catch { return null }
}

export function parseIndeedPage(value: unknown, target: IndeedCountry): Scan {
  const envelope = record(value)
  if (Array.isArray(envelope.errors) && envelope.errors.length) {
    const denied = envelope.errors.some(error => ["UNAUTHENTICATED", "UNAUTHORIZED", "FORBIDDEN", "ACCESS_DENIED"]
      .some(code => code === record(record(error).extensions).code))
    return fail(denied ? "blocked" : "unknown", denied ? "indeed_authorization_failed" : "indeed_graphql_errors", 1)
  }
  const search = record(record(envelope.data).jobSearch)
  const rows = search.results
  if (!Array.isArray(rows) || (envelope.errors !== undefined && !Array.isArray(envelope.errors))) {
    return fail("parse_failed", "invalid_job_search_response", 1)
  }
  const scan: Scan = {
    jobs: [], coverage: "partial", reason: target === "FI" ? "one_finland_list_page" : "one_country_list_page", errors: [], requests: 1,
    received_count: rows.length, total_jobs: null, total_pages: null, retry_after: null,
  }
  if (rows.length === 0) {
    if (record(search.pageInfo).nextCursor === null) return { ...scan, coverage: "valid_empty", reason: "empty_first_page" }
    return { ...scan, coverage: "unknown", reason: "empty_page_without_end_marker", errors: ["empty_page_without_end_marker"] }
  }
  if (rows.length > PAGE_SIZE) return { ...scan, coverage: "unknown", reason: "response_page_budget_exceeded", errors: ["response_page_budget_exceeded"] }
  const jobs = new Map<string, Lead>(), conflicts = new Set<string>()
  for (const [index, row] of rows.entries()) {
    const job = record(record(row).job), location = record(job.location)
    const id = text(job.key), title = text(job.title)
    if (!id || !/^[a-zA-Z0-9_-]{1,80}$/.test(id) || !title) {
      scan.errors.push(`invalid_record_identity:${index}`)
      continue
    }
    const country = text(location.countryCode)?.toUpperCase()
    if (!country) scan.errors.push(`country_unverified:${index}`)
    if (country !== target) continue
    const company = text(record(job.employer).name) ?? text(job.sourceEmployerName) ?? ""
    const prior = jobs.get(id)
    if (prior && (prior.title !== title || (prior.company && company && prior.company !== company))) {
      conflicts.add(id)
      jobs.delete(id)
      scan.errors.push(`conflicting_record_identity:${index}`)
    }
    if (prior || conflicts.has(id)) continue
    const stamp = job.dateOnIndeed
    const date = typeof stamp === "number" && Number.isSafeInteger(stamp) && stamp > 0 &&
      stamp <= 253402300799999 ? new Date(stamp).toISOString().slice(0, 10) : null
    jobs.set(id, {
      id, title, company, location: text(location.city), date, date_source: date ? "indeed_date_on_site" : null,
      url: `https://${target === "GB" ? "uk" : target.toLowerCase()}.indeed.com/viewjob?jk=${id}`,
      source_ats: "generic", portal: "indeed", country: target, needs_detail: true,
      reported_external_url: externalUrl(record(job.recruit).viewJobUrl),
    })
  }
  return { ...scan, jobs: [...jobs.values()] }
}

export async function fetchIndeedPage(query: string | undefined, country: IndeedCountry): Promise<Scan> {
  if (!isIndeedCountry(country)) return fail("unknown", "indeed_country_unsupported", 0)
  const keyword = query?.trim()
  if (!keyword || keyword.length > 100 || /[\x00-\x1f\x7f]/.test(keyword)) return fail("unknown", "indeed_keyword_required", 0)
  const key = process.env.INDEED_SHARED_API_KEY?.trim()
  if (!key || /[^\x21-\x7e]/.test(key)) return fail("unknown", "indeed_runtime_key_unavailable", 0)
  const vendor = process.env.INDEED_JOBSPY_VENDOR_DIR
  if (!vendor) return fail("unknown", "indeed_jobspy_unavailable", 0)
  let output: string
  try {
    const { stdout } = await run("python3", ["-I", "-B", BRIDGE, keyword, country], {
      timeout: 25000, killSignal: "SIGKILL", maxBuffer: 512 * 1024, encoding: "utf8",
      env: { PATH: process.env.PATH, INDEED_SHARED_API_KEY: key, INDEED_JOBSPY_VENDOR_DIR: vendor },
    })
    output = stdout
  } catch (error) {
    const { code, killed } = error as NodeJS.ErrnoException & { killed?: boolean }
    if (code === "ENOENT") return fail("unknown", "indeed_jobspy_python_unavailable", 0)
    if (code === "ERR_CHILD_PROCESS_STDIO_MAXBUFFER") return fail("parse_failed", "indeed_body_too_large", null)
    return fail("unknown", killed ? "indeed_jobspy_timeout" : "indeed_jobspy_process_failed", null)
  }
  let result: RecordValue
  try { result = record(JSON.parse(output)) }
  catch { return fail("parse_failed", "indeed_jobspy_invalid_output", null) }
  const { requests, status } = result
  if (requests !== 0 && requests !== 1) return fail("parse_failed", "indeed_jobspy_invalid_output", null)
  switch (result.error) {
    case "indeed_jobspy_unavailable":
    case "indeed_country_unsupported":
    case "indeed_jobspy_credential_mismatch":
    case "indeed_jobspy_transport_configuration":
    case "indeed_jobspy_request_budget":
    case "indeed_jobspy_timeout":
    case "indeed_transport_failure":
    case "indeed_jobspy_process_failed":
      return fail("unknown", result.error, requests)
    case "indeed_invalid_json_body":
    case "indeed_non_json_response":
    case "indeed_body_too_large":
      return fail("parse_failed", result.error, requests)
  }
  if (result.error !== undefined || requests !== 1 || typeof status !== "number" ||
      !Number.isInteger(status) || status < 100 || status > 599) {
    return fail("parse_failed", "indeed_jobspy_invalid_output", requests)
  }
  if (status === 429) {
    const retry = text(result.retry_after)
    const safeRetry = retry && /^(?:\d{1,10}|[A-Z][a-z]{2}, \d{2} [A-Z][a-z]{2} \d{4} \d{2}:\d{2}:\d{2} GMT)$/.test(retry) ? retry : null
    return fail("rate_limited", "indeed_http_429", 1, safeRetry)
  }
  if (status === 401 || status === 403) return fail("blocked", "indeed_http_" + status, 1)
  if (result.challenge === true) return fail("blocked", "indeed_challenge", 1)
  if (status !== 200) return fail("unknown", "indeed_http_" + status, 1)
  return parseIndeedPage(result.payload, country)
}
