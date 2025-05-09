import * as vscode from 'vscode';
const fetch: typeof globalThis.fetch = globalThis.fetch;
import * as inspector from 'inspector';

PLACEHOLDER_IMPORT

const dummyUrl = 'http://127.0.0.1:8080';
const airflowCfg = vscode.workspace.getConfiguration('airflow');

const covSession = new inspector.Session();
  covSession.connect();
  covSession.post('Profiler.enable');
  covSession.post('Profiler.startPreciseCoverage', {
    callCount: true,
    detailed : true,
  }
);

for (const key of ['url', 'baseUrl']) {
  if (!airflowCfg.get(key)) {
    airflowCfg.update(key, dummyUrl, true);
  }
}
for (const key of ['username', 'password']) {
  if (!airflowCfg.get(key)) {
    airflowCfg.update(key, 'fuzzer', true);
  }
}

(globalThis as any).fetch = async () => ({
  ok: true,
  status: 200,
  json: async () => ({}),
  text: async () => '',
});



const HOST = '127.0.0.1';
const PORT = 5000;
const BASE = `http://${HOST}:${PORT}`;

console.log('Harness booted, BASE =', BASE);
console.log('Airflow URL in settings =', airflowCfg.get('url') || airflowCfg.get('baseUrl'));

interface FuzzCase {
  funcName: string;
  args: any[];
  coverage: Record<string, string[]>;
  error?: string;
}

function diffCoverage(
  before: Map<string, number>,
  raw: any[]
): Record<string, string[]> {
  const newlyHit: Record<string, string[]> = {};
  for (const s of raw) {
    if (!s.url.includes('/ext-fuzz-')) continue;
    for (const fn of s.functions) {
      for (const r of fn.ranges) {
        if (r.count === 0) continue;
        const key = `${s.url}::${fn.functionName}`;
        const prev = before.get(key) || 0;
        if (r.count > prev) {
          (newlyHit[s.url] ??= []).push(fn.functionName || '<anon>');
        }
        // update running tally
        before.set(key, r.count);
      }
    }
  }
  return newlyHit;
}

async function waitForServerReady(): Promise<void> {
  for (let i = 0; i < 10; i++) {
    try {
      const r = await fetch(`${BASE}/ping`, { method: 'GET' });
      if (r.ok) return;
    } catch { }
    await new Promise(r => setTimeout(r, 500));
  }
  throw new Error('HTTP server never became ready');
}

export async function fetchFuzzCases(): Promise<FuzzCase[]> {
  try {
    const res = await fetch(`${BASE}/tests`);
    if (!res.ok) {
      console.error('GET /tests ->', res.status, res.statusText);
      return [];
    }
    const data = await res.json();
    console.log('Fetched queue size', Array.isArray(data) ? data.length : 0);
    return Array.isArray(data) ? data as FuzzCase[] : [];
  } catch (err) {
    console.error('Fetch to /tests failed:', err);
    return [];
  }
}

async function sendReport(
  clean: FuzzCase[], 
  errors: FuzzCase[], 
  crash: FuzzCase | null, 
  coverage: Record<string, { total: number; hit: number }>
) {
  await fetch(`${BASE}/report`, {
    method : 'POST',
    headers: { 'Content-Type': 'application/json' },
    body   : JSON.stringify({ clean, errors, crash, coverage }),
  });
}

const resolveFn = (name: string): Function | undefined => {
  const walk = (obj: any, path: string) =>
    path.split('.').reduce((o, k) => (o ? o[k] : undefined), obj);
  
  const parts = name.split('.');
  let fn = walk(targetModule, name) ?? walk((targetModule as any).default, name);
  if (typeof fn === 'function') return fn;            // found static export

  /* ---------- new: handle instance methods ---------- */
  if (parts.length >= 2) {
    const [className, ...methodPath] = parts;
    const ctor =
      (targetModule as any)[className] ??
      (targetModule as any).default?.[className];

    if (typeof ctor === 'function') {
      // try static first
      fn = walk(ctor, methodPath.join('.'));
      if (typeof fn === 'function') return fn;

      // fall back to prototype → bind to fresh instance
      fn = walk(ctor.prototype, methodPath.join('.'));
      if (typeof fn === 'function') {
        const instance = new ctor();
        return fn.bind(instance);
      }
    }
  }
  /* --------------------------------------------------- */

  return undefined;                                   // still not found
};

async function runFuzzerHarness() {
  await waitForServerReady();
  const cases = await fetchFuzzCases();

  const clean:  FuzzCase[] = [];
  let   crash:  FuzzCase | null = null;
  const errors: FuzzCase[] = [];

  console.log('Available exports:', Object.keys(targetModule));
  const hitCounts = new Map<string, number>();

  for (const { funcName, args } of cases) {
  /* snapshot BEFORE the call */
  const before = new Map(hitCounts);

  try {
    const fn = resolveFn(funcName);
    if (typeof fn !== 'function')
      throw new Error(`No such function: ${funcName}`);

    const out = fn(...args);
    if (out instanceof Promise) await out;

    /* snapshot AFTER and compute delta */
    const raw = await new Promise<any[]>((res, rej) =>
      covSession.post('Profiler.takePreciseCoverage',
        (e, r) => (e ? rej(e) : res(r.result)))
    );
    const covDelta = diffCoverage(before, raw);

    clean.push({ funcName, args, coverage: covDelta });

  } catch (e) {
    const raw = await new Promise<any[]>((res, rej) =>
      covSession.post('Profiler.takePreciseCoverage',
        (er, r) => (er ? rej(er) : res(r.result)))
    );
    const covDelta = diffCoverage(before, raw);

    errors.push({
      funcName,
      args,
      coverage: covDelta,
      error: e instanceof Error ? e.stack ?? e.message : String(e),
    });
  }
}

  function takeCoverage(): Promise<any[]> {
    return new Promise((resolve, reject) => {
      covSession.post('Profiler.takePreciseCoverage', (err, res) => {
        if (err) reject(err);
        else     resolve(res.result);
      });
    });
  }
  
  const rawCov = await takeCoverage();
  covSession.post('Profiler.stopPreciseCoverage');
  covSession.disconnect();
  
  const summary: Record<string, { total: number; hit: number }> = {};
  for (const s of rawCov) {
    if (!s.url.includes('/ext-fuzz-')) continue;
    let hit = 0;
    for (const fn of s.functions) {
      if (fn.ranges.some((r: { count: number }) => r.count > 0)) hit += 1;
    }
    summary[s.url] = { total: s.functions.length, hit };
  }
  
  await sendReport(clean, errors, crash, summary);
}

runFuzzerHarness();
