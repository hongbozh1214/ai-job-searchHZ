import { fetchAshbyList } from "../ashby.js"
import { loadRegistry, matchesFilters, applyLocationsFilter, writeCaughtError, writeError, type NormalizedJob, type RegistryEntry } from "../helpers.js"
import { fetchWorkdayList } from "../workday.js"
import { fetchWorkInFinland } from "../work-in-finland.js"
import { fetchEuraxessList } from "../euraxess.js"
import { fetchEuresList } from "../eures.js"
import { fetchVttList, isVttBoard } from "../vtt.js"
import { fetchGreenhouse, fetchLever, fetchSmartRecruiters, fetchOracle, fetchGeneric } from "../ats.js"

export interface SearchOpts {
  source?: "work-in-finland" | "euraxess" | "eures"
  company?: string
  query?: string
  location?: string
  limit?: number
  format: "json" | "table" | "plain"
}

async function fetchEntry(entry: RegistryEntry, workdayDeps: Parameters<typeof fetchWorkdayList>[2] = {}): Promise<{ jobs: NormalizedJob[]; coverage?: unknown }> {
  switch (entry.ats) {
    case "greenhouse":
      return { jobs: await fetchGreenhouse(entry) }
    case "lever":
      return { jobs: await fetchLever(entry) }
    case "smartrecruiters":
      return { jobs: await fetchSmartRecruiters(entry) }
    case "oracle":
      return { jobs: await fetchOracle(entry) }
    case "ashby": {
      const scan = await fetchAshbyList(entry.name, entry.ats_id, workdayDeps)
      return { jobs: applyLocationsFilter(scan.jobs, entry), coverage: {company: entry.name, status: scan.coverage, reason: scan.reason, requests: scan.requests, scope: scan.scope} }
    }
    case "workday": {
      const scan = await fetchWorkdayList(entry.name, entry.careers_url, workdayDeps)
      return { jobs: applyLocationsFilter(scan.jobs.map(j => ({ ...j, source_ats: "workday" as const })), entry), coverage: {company: entry.name, status: scan.coverage, reason: scan.reason, requests: scan.requests} }
    }
    case "generic": {
      if (!isVttBoard(entry.careers_url)) return { jobs: await fetchGeneric(entry) }
      const scan = await fetchVttList(entry.name, entry.careers_url, workdayDeps)
      return { jobs: applyLocationsFilter(scan.jobs, entry), coverage: {company: entry.name, status: scan.coverage, reason: scan.reason, requests: scan.requests} }
    }
    default:
      // A typo'd ats used to fall through to the generic scraper, which returns
      // nothing for a JS portal — so "greenhose" read as "no openings" forever.
      throw new Error(
        `"${entry.name}" declares unknown ats "${entry.ats}" - expected greenhouse, lever, smartrecruiters, oracle, workday, ashby or generic [config_error]`,
      )
  }
}

function renderTable(jobs: NormalizedJob[]): string {
  if (jobs.length === 0) return "No results."
  const rows = jobs.map((j) => {
    const company = (j.company || "").slice(0, 22).padEnd(22)
    const title = (j.title || "").slice(0, 42).padEnd(42)
    const loc = (j.location || "—").slice(0, 20).padEnd(20)
    const ats = j.source_ats.padEnd(15)
    return `${company} ${title} ${loc} ${ats}`
  })
  const header =
    "COMPANY".padEnd(22) + " " + "TITLE".padEnd(42) + " " + "LOCATION".padEnd(20) + " ATS"
  return [header, "-".repeat(header.length), ...rows].join("\n")
}

export async function runSearch(opts: SearchOpts, workdayDeps: Parameters<typeof fetchWorkdayList>[2] = {}): Promise<number> {
  try {
    if (opts.source !== undefined && (!["work-in-finland", "euraxess", "eures"].includes(opts.source) || opts.company)) throw Error("source search requires a supported --source without --company")
    // Explicit source selection never loads or widens the personal registry.
    const sourceScan = opts.source === "eures" ? await fetchEuresList(workdayDeps, opts.query) : opts.source === "euraxess" ? await fetchEuraxessList(workdayDeps) : opts.source ? await fetchWorkInFinland(opts.query, workdayDeps) : null
    const registry = opts.source ? [] : await loadRegistry()
    const entries = opts.company
      ? registry.filter((e) => e.name.toLowerCase() === opts.company!.toLowerCase())
      : registry

    if (opts.company && entries.length === 0) {
      writeError(`No registry entry named "${opts.company}"`, "COMPANY_NOT_FOUND")
      return 1
    }

    const results = await Promise.allSettled(entries.map((e) => fetchEntry(e, workdayDeps)))
    let jobs: NormalizedJob[] = []
    const errors: { company: string; error: string }[] = []
    const coverage: unknown[] = []
    if (sourceScan) {
      jobs.push(...sourceScan.jobs)
      const sourceName = opts.source === "eures" ? "EURES" : opts.source === "euraxess" ? "EURAXESS" : "Work in Finland"
      errors.push(...sourceScan.errors.map(error => ({ company: sourceName, error })))
      coverage.push({ company: sourceName, source: opts.source, status: sourceScan.coverage, reason: sourceScan.reason, requests: sourceScan.requests, scope: "one_source_page", received_count: sourceScan.received_count, total_jobs: sourceScan.total_jobs, total_pages: sourceScan.total_pages ?? null, retry_after: sourceScan.retry_after, ...(opts.source === "eures" ? { query_scope: opts.query === undefined ? "unfiltered" : "server_everywhere", country_scope: "unfiltered" } : {}) })
    }
    results.forEach((r, i) => {
      if (r.status === "fulfilled") {
        jobs.push(...r.value.jobs)
        if (r.value.coverage) coverage.push(r.value.coverage)
      } else {
        errors.push({ company: entries[i].name, error: r.reason instanceof Error ? r.reason.message : String(r.reason) })
      }
    })

    // Server queries may match the description, not the title. Do not discard
    // those records with the registry branch's literal title filter.
    jobs = jobs.filter((j) => matchesFilters(j, opts.source === "work-in-finland" || opts.source === "eures" ? undefined : opts.query, opts.location))
    if (opts.limit !== undefined && opts.limit >= 0) jobs = jobs.slice(0, opts.limit)

    if (opts.format === "table") {
      process.stdout.write(renderTable(jobs) + "\n")
      if (errors.length || coverage.length) process.stderr.write(JSON.stringify({ warnings: errors, coverage }) + "\n")
    } else if (opts.format === "plain") {
      process.stdout.write(
        jobs
          .map((j) => `${j.title}\n  ${j.company} · ${j.location || "—"} · ${j.source_ats}\n  ${j.url}`)
          .join("\n\n") + "\n",
      )
      if (errors.length || coverage.length) process.stderr.write(JSON.stringify({ warnings: errors, coverage }) + "\n")
    } else {
      process.stdout.write(
        JSON.stringify({ meta: { count: jobs.length, errors, ...(coverage.length ? {coverage} : {}) }, results: jobs }, null, 2) + "\n",
      )
    }
    return 0
  } catch (e) {
    writeCaughtError(e, "SEARCH_FAILED")
    return 1
  }
}
