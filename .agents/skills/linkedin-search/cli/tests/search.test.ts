import { afterEach, describe, expect, test } from "bun:test";
import { runSearch } from "../src/commands/search";

const originalFetch = globalThis.fetch;
const originalStdoutWrite = process.stdout.write;
const originalStderrWrite = process.stderr.write;

function searchCard(id: string, title: string): string {
  return `<li>
    <div data-entity-urn="urn:li:jobPosting:${id}">
      <a class="base-card__full-link" href="https://www.linkedin.com/jobs/view/${id}"></a>
      <h3 class="base-search-card__title">${title}</h3>
    </div>
  </li>`;
}

afterEach(() => {
  globalThis.fetch = originalFetch;
  process.stdout.write = originalStdoutWrite;
  process.stderr.write = originalStderrWrite;
});

describe("runSearch", () => {
  test("single-request keeps first-page results partial and dates unknown", async () => {
    let stdout = "";
    process.stdout.write = ((chunk: string) => { stdout += chunk; return true; }) as typeof process.stdout.write;
    globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
      expect(new URL(String(input)).searchParams.get("location")).toBe("Finland");
      expect(init?.redirect).toBe("manual");
      return new Response(searchCard("123456", "Scientist"));
    }) as typeof fetch;
    expect(await runSearch({ location: "Finland", query: "protein", jobage: 14, page: 1, format: "json", singleRequest: true })).toBe(0);
    const data = JSON.parse(stdout);
    expect(data.meta.coverage[0].status).toBe("partial");
    expect(data.results[0]).toMatchObject({ id: "123456", date: null });
  });

  test("single-request stops on denial, rate limit, redirect, or unknown HTML", async () => {
    for (const status of [403, 429, 302, 200]) {
      let requests = 0;
      let stderr = "";
      process.stderr.write = ((chunk: string) => { stderr += chunk; return true; }) as typeof process.stderr.write;
      globalThis.fetch = (async () => {
        requests++;
        return new Response("<html>Sign in</html>", {
          status,
          headers: status === 429 ? { "Retry-After": "60" } : {},
        });
      }) as typeof fetch;
      expect(await runSearch({ location: "Finland", jobage: 14, page: 1, format: "json", singleRequest: true })).toBe(1);
      expect(requests).toBe(1);
      if (status === 429) expect(stderr).toContain("Retry-After: 60");
      if (status === 200) expect(JSON.parse(stderr).code).toBe("LIST_UNCONFIRMED");
    }
  });

  test("--limit 0 emits zero results", async () => {
    globalThis.fetch = (async () => new Response(searchCard("123456", "Engineer"))) as typeof fetch;

    let stdout = "";
    process.stdout.write = ((chunk: string | Uint8Array) => {
      stdout += chunk.toString();
      return true;
    }) as typeof process.stdout.write;

    const code = await runSearch({
      location: "Copenhagen, Denmark",
      jobage: 9999,
      page: 1,
      limit: 0,
      format: "json",
    });

    expect(code).toBe(0);
    expect(JSON.parse(stdout).results).toHaveLength(0);
  });

  test("--jobage-minutes 30 constructs f_TPR=r1800 in the request URL", async () => {
    let capturedUrl = "";
    globalThis.fetch = (async (input: RequestInfo | URL) => {
      capturedUrl = typeof input === "string" ? input : input.toString();
      return new Response("");
    }) as typeof fetch;

    const code = await runSearch({
      location: "Remote",
      jobage: 9999,
      jobageMinutes: 30,
      page: 1,
      format: "json",
    });

    expect(code).toBe(0);
    expect(capturedUrl).toContain("f_TPR=r1800");
  });
});
