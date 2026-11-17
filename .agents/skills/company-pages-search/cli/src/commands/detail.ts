import { fetchWorkInFinlandDetail } from '../work-in-finland.js'
import { fetchAshbyDetail } from "../ashby.js"
import { fetchVttDetail, isVttBoard } from "../vtt.js"
import { fetchWorkdayDetail } from "../workday.js"
import { fetchEuraxessDetail } from "../euraxess.js"
import { fetchEuresDetail } from "../eures.js"
import { loadRegistry, writeCaughtError, writeError } from "../helpers.js"
import { fetchGreenhouseDetail, fetchLeverDetail, fetchSmartRecruitersDetail, fetchOracleDetail } from "../ats.js"

export interface DetailOpts {
  company?: string
  source?: "euraxess" | "eures" | "work-in-finland"
  query?: string
  id: string
  format: "json" | "plain"
}

export async function runDetail(opts: DetailOpts, workdayDeps: Parameters<typeof fetchWorkdayDetail>[3] = {}): Promise<number> {
  try {
    if (opts.source) {
      if (opts.source === "eures" && !opts.company) {
        const { job, scan } = await fetchEuresDetail(opts.id, workdayDeps)
        const meta = { coverage: [{ source: 'eures', status: scan.coverage, reason: scan.reason, requests: scan.requests, retry_after: scan.retry_after, scope: 'one_selected_detail' }], errors: scan.errors.map(error => ({ company: 'EURES', error })) }
        if (!job) { process.stderr.write(JSON.stringify({ error: 'EURES detail unconfirmed', code: 'EURES_DETAIL_UNCONFIRMED', meta }) + '\n'); return 1 }
        if (opts.format === 'plain') {
          process.stdout.write(`${job.title}\n${job.company} · ${job.location ?? '—'}\n\n${job.description}\n\nURL: ${job.url}\n`)
          process.stderr.write(JSON.stringify(meta) + '\n')
        } else process.stdout.write(JSON.stringify({ ...job, meta }, null, 2) + '\n')
        return 0
      }
      if (opts.company || !['euraxess','work-in-finland'].includes(opts.source)) throw Error("invalid_source_detail")
      const job = opts.source === 'work-in-finland'
        ? await fetchWorkInFinlandDetail(opts.id,opts.query,workdayDeps)
        : await fetchEuraxessDetail(opts.id, workdayDeps)
      if (opts.format === 'plain') process.stderr.write(JSON.stringify({meta:job.meta})+'\n')
      process.stdout.write(opts.format === "plain" ? `${job.title}\n${job.company} · ${job.location ?? "—"}\n\n${job.description}\n\nURL: ${job.url}\n` : JSON.stringify(job, null, 2) + "\n")
      return 0
    }
    if (!opts.company) { writeError("detail requires --company", "NO_ARGS"); return 1 }
    const registry = await loadRegistry()
    const entry = registry.find((e) => e.name.toLowerCase() === opts.company!.toLowerCase())
    if (!entry) {
      writeError(`No registry entry named "${opts.company}"`, "COMPANY_NOT_FOUND")
      return 1
    }
    if (entry.ats === "generic" && !isVttBoard(entry.careers_url)) {
      writeError(
        `"${entry.name}" is ats=generic — there is no detail API. WebFetch the job URL directly.`,
        "NO_DETAIL_API",
      )
      return 1
    }

    let job: Record<string, unknown> | null = null
    if (entry.ats === "generic" && isVttBoard(entry.careers_url)) job = await fetchVttDetail(entry.name, entry.careers_url, opts.id, workdayDeps)
    else if (entry.ats === "ashby") job = await fetchAshbyDetail(entry.name, entry.ats_id, opts.id, workdayDeps)
    else if (entry.ats === "workday") job = await fetchWorkdayDetail(entry.name, entry.careers_url, opts.id, workdayDeps)
    else if (entry.ats === "greenhouse") job = await fetchGreenhouseDetail(entry.ats_id, opts.id)
    else if (entry.ats === "lever") job = await fetchLeverDetail(entry.ats_id, opts.id)
    else if (entry.ats === "smartrecruiters") job = await fetchSmartRecruitersDetail(entry.ats_id, opts.id)
    else if (entry.ats === "oracle") job = await fetchOracleDetail(entry.ats_id, opts.id)

    if (!job) {
      writeError("Job not found", "NOT_FOUND")
      return 1
    }
    job.company = entry.name

    if (opts.format === "plain") {
      const lines = [
        String(job.title ?? "(untitled)"),
        `${entry.name} · ${job.location ?? "—"}`,
        "",
        String(job.description ?? "(no description)"),
        "",
        `URL: ${job.url ?? "—"}`,
      ]
      process.stdout.write(lines.join("\n") + "\n")
    } else {
      process.stdout.write(JSON.stringify(job, null, 2) + "\n")
    }
    return 0
  } catch (e) {
    if (opts.source && e instanceof Error && 'meta' in e) process.stderr.write(JSON.stringify({error:e.message,code:'DETAIL_FAILED',meta:e.meta})+'\n')
    else writeCaughtError(e, "DETAIL_FAILED")
    return 1
  }
}
