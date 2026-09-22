import { join } from "path";

const CLI_PATH = join(import.meta.dir, "../src/cli.ts");
const EXAMPLE_REGISTRY = join(import.meta.dir, "../../company_pages.example.json");

export interface CLIResult {
  stdout: string;
  stderr: string;
  exitCode: number;
}

export async function runCLI(
  args: string[],
  env: Record<string, string> = {},
): Promise<CLIResult> {
  const proc = Bun.spawn(["bun", "run", CLI_PATH, ...args], {
    stdout: "pipe",
    stderr: "pipe",
    env: { ...process.env, ...env },
  });

  const [stdout, stderr, exitCode] = await Promise.all([
    new Response(proc.stdout).text(),
    new Response(proc.stderr).text(),
    proc.exited,
  ]);

  return { stdout: stdout.trim(), stderr: stderr.trim(), exitCode };
}

/** Opt into the committed fixture explicitly; production never falls back to it. */
export function runExampleCLI(args: string[]): Promise<CLIResult> {
  return runCLI(args, { COMPANY_PAGES_REGISTRY: EXAMPLE_REGISTRY });
}

export function parseJSON<T = unknown>(result: CLIResult): T {
  if (result.exitCode !== 0) {
    throw new Error(
      `CLI exited with code ${result.exitCode}. stderr: ${result.stderr}`
    );
  }
  try {
    return JSON.parse(result.stdout) as T;
  } catch {
    throw new Error(
      `Failed to parse JSON. stdout: ${result.stdout}\nstderr: ${result.stderr}`
    );
  }
}

/** Build a Response-shaped stub without touching the network. */
export function stubResponse(
  status: number,
  body = "",
  statusText = ""
): Response {
  return new Response(status === 204 || status === 304 ? null : body, {
    status,
    statusText,
  });
}

/**
 * A fetch stub that returns the given responses in order and records the
 * options each call received, so tests can assert on the headers actually sent.
 */
export function recordingFetch(responses: Response[]): {
  impl: typeof fetch;
  calls: { url: string; headers: Record<string, string> }[];
} {
  const calls: { url: string; headers: Record<string, string> }[] = [];
  let i = 0;
  const impl = (async (input: string | URL | Request, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input.toString();
    const headers = (init?.headers ?? {}) as Record<string, string>;
    calls.push({ url, headers });
    const r = responses[Math.min(i, responses.length - 1)];
    i++;
    return r;
  }) as unknown as typeof fetch;
  return { impl, calls };
}
