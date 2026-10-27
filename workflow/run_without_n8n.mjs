// Runs the workflow's Code nodes outside n8n, against the real endpoints, with the few
// n8n globals they use stubbed out.
//
//   node workflow/run_without_n8n.mjs workflow/Nagaralu_Gurumurthy_Likhith_MedVault_Workflow.json
//
// Why this exists: a workflow JSON is a file full of JavaScript that nobody can check by
// reading it. This executes the same code the Code nodes contain, hits the same three
// endpoints the HTTP nodes hit, and prints what the join produced - so the thing can be
// verified before it is imported, and after any edit to it.
//
// It found two real defects on its first runs. The enforcement match missed two of nine
// hospitals (a city suffix and an operator prefix), and Sutter serves its cms-hpt.txt as
// UTF-16 with a byte-order mark, which arrives decoded as "h t t p s" and matches
// nothing. Neither would have been visible from reading the JSON.
import fs from 'node:fs';

const wf = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const code = Object.fromEntries(wf.nodes.filter(n => n.type.endsWith('.code'))
                                        .map(n => [n.name, n.parameters.jsCode]));
const store = {};
const $ = name => ({
  all: () => (store[name] || []),
  first: () => (store[name] || [])[0],
});
const run = (name, src) => {
  const fn = new Function('$', '$json', '$input', `${src}`);
  return fn($, {}, {});
};

// --- Scope --------------------------------------------------------------------
store['Scope'] = run('Scope', code['Scope']);
const scope = store['Scope'][0].json;
console.log(`Scope: ${scope.hospitals.length} hospitals, ${scope.codes.length} codes`);

const UA = { 'User-Agent': 'medvault/1.0 (INFO7375 coursework; node-fetch)' };

// --- CMS enforcement, paginated the way the HTTP node is configured -----------
const ENF = 'https://data.cms.gov/data-api/v1/dataset/6a3aa708-3c9d-411a-a1a4-e046d3ade7ef/data';
let all = [], page = 0;
for (;;) {
  const r = await fetch(`${ENF}?size=5000&offset=${page * 5000}`, { headers: UA });
  const b = await r.json();
  all = all.concat(b);
  page++;
  if (b.length < 5000) break;
}
store['CMS enforcement actions'] = all.map(json => ({ json }));
console.log(`CMS enforcement actions: ${all.length}`);

// --- Medicare fee schedule ----------------------------------------------------
const pfs = await (await fetch(scope.pfsUrl, { headers: UA })).json();
store['Medicare fee schedule'] = pfs.map(json => ({ json }));
console.log(`Medicare fee schedule: ${pfs.length} rows`);

// --- discovery ----------------------------------------------------------------
store['Price-file discovery URLs'] = run('Price-file discovery URLs',
                                         code['Price-file discovery URLs']);
const fetched = [];
for (const item of store['Price-file discovery URLs']) {
  try {
    const r = await fetch(item.json.url, { headers: UA, redirect: 'follow' });
    fetched.push({ json: { body: await r.text(), statusCode: r.status,
                           headers: Object.fromEntries(r.headers) } });
  } catch (e) {
    fetched.push({ json: { error: String(e), statusCode: 0 } });
  }
}
store['Fetch cms-hpt.txt'] = fetched;
console.log(`cms-hpt.txt fetched: ${fetched.filter(f => f.json.statusCode === 200).length}/9 ok`);

// --- the join -----------------------------------------------------------------
const rows = run('Clean and join', code['Clean and join']);
console.log(`\nJOIN RETURNED ${rows.length} rows`);
const seen = {};
for (const { json } of rows) {
  seen[json.hospital_name] = [json.cms_enforcement_actions, json.cms_enforcement_match,
                              json.mrf_discovered];
}
console.log('\n actions  match                      mrf  hospital');
for (const [h, [n, m, mrf]] of Object.entries(seen))
  console.log(`${String(n).padStart(8)}  ${m.padEnd(26)} ${mrf.padEnd(4)} ${h.slice(0, 44)}`);
console.log('\nsample row:', JSON.stringify(rows[0].json, null, 1));
