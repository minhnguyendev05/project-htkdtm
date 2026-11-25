/*
 * FX → VND converter for the competitor dataset.
 *
 * Goal: never write a converted price from a guessed rate.
 *
 * Rate resolution order:
 *   1. Google Finance CNY-VND (rendered via Firecrawl, only when
 *      FIRECRAWL_API_KEY is set, because Google renders the quote in JS).
 *   2. currency-api on jsDelivr (free, no key). Measured 2026-11-22 against
 *      Google Finance: 3,864.71 vs 3,863.80 => 0.02% difference.
 *   3. open.er-api.com (independent cross-check).
 *   4. Vietcombank XML (bank transfer/buy/sell, used only as a sanity check;
 *      bank spread is 1.5-3% by design and is NOT used as the market rate).
 *
 * Integrity guards (the script exits non-zero instead of writing bad data):
 *   - primary vs cross-check must agree within MAX_SPREAD (default 1.5%).
 *   - if Google is available, its value is authoritative; a >1% disagreement
 *     with jsDelivr aborts the run.
 *
 * Usage:  node scripts/convert-to-vnd.mjs [--tolerance=0.015]
 * Env:    FIRECRAWL_API_KEY (optional, enables the Google Finance source)
 * Output: datasets/fx-rates.json
 *         datasets/competitor-prices-vnd.json
 *         datasets/competitor-prices-vnd.csv
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '..');
const SRC = path.join(root, 'src/mocks/collected-ai-dataset.json');
const OUT_DIR = path.join(root, 'datasets');

const tolArg = process.argv.find((a) => a.startsWith('--tolerance='));
const MAX_SPREAD = tolArg ? Number(tolArg.split('=')[1]) : 0.015;
const GOOGLE_TOLERANCE = 0.01;

const UA = { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)' };
const get = async (url, init = {}) => {
  const res = await fetch(url, { ...init, headers: { ...UA, ...(init.headers || {}) }, signal: AbortSignal.timeout(25000) });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res;
};

/* ---------------- sources ---------------- */

async function googleFinance(pair) {
  const key = process.env.FIRECRAWL_API_KEY;
  if (!key) return null;
  const url = `https://www.google.com/finance/quote/${pair}`;
  const res = await fetch('https://api.firecrawl.dev/v1/scrape', {
    method: 'POST',
    headers: { Authorization: `Bearer ${key}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ url, formats: ['markdown'], onlyMainContent: true }),
    signal: AbortSignal.timeout(60000),
  });
  if (!res.ok) throw new Error(`Firecrawl HTTP ${res.status}`);
  const j = await res.json();
  const md = (j.data && j.data.markdown) || '';
  // "3,863.8004" right after the pair heading. Anchored to avoid chart ticks.
  const re = new RegExp(`${pair.replace('-', '\\s*/\\s*')}[\\s\\S]{0,300}?\\n+([0-9][0-9,]*\\.[0-9]+)`);
  const m = md.match(re);
  if (!m) throw new Error('Google Finance: price not found in page');
  const value = Number(m[1].replace(/,/g, ''));
  if (!Number.isFinite(value) || value <= 0) throw new Error('Google Finance: invalid price');
  return { source: 'google-finance', value };
}

async function jsdelivr(base, quote) {
  const url = `https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/${base.toLowerCase()}.json`;
  const j = await (await get(url)).json();
  const v = j?.[base.toLowerCase()]?.[quote.toLowerCase()];
  if (!v) throw new Error('jsdelivr: pair missing');
  return { source: 'currency-api-jsdelivr', value: Number(v), date: j.date };
}

async function erApi(base, quote) {
  // open.er-api returns units of `quote` per 1 `base` (e.g. CNY→VND = 3846.15).
  const j = await (await get(`https://open.er-api.com/v6/latest/${base}`)).json();
  if (j.result !== 'success') throw new Error(`er-api: ${j['error-type'] ?? 'error'}`);
  const value = j.rates[quote];
  if (!value) throw new Error('er-api: pair missing');
  return { source: 'open.er-api.com', value, updatedAt: j.time_last_update_utc };
}

async function vietcombank(quote) {
  const xml = await (await get('https://portal.vietcombank.com.vn/Usercontrols/TVPortal.TyGia/pXML.aspx')).text();
  const row = [...xml.matchAll(/<Exrate\s+([^/]+)\/>/g)].find((m) => new RegExp(`CurrencyCode="${quote}"`).test(m[1]));
  if (!row) throw new Error('vietcombank: currency missing');
  const attr = (n) => Number((row[1].match(new RegExp(`${n}="([0-9.,]+)"`)) || [])[1]?.replace(/,/g, ''));
  return { source: 'vietcombank', buy: attr('Buy'), transfer: attr('Transfer'), sell: attr('Sell') };
}

/* ---------------- resolve one pair ---------------- */

async function resolveRate(base, quote) {
  const collected = [];
  const warnings = [];
  let google = null;
  let reference = null;

  try {
    google = await googleFinance(`${base}-${quote}`);
    if (google) collected.push(google);
  } catch (e) { warnings.push(`google: ${e.message}`); }

  try {
    const j = await jsdelivr(base, quote);
    collected.push(j);
  } catch (e) { warnings.push(`jsdelivr: ${e.message}`); }

  try {
    collected.push(await erApi(base, quote));
  } catch (e) { warnings.push(`er-api: ${e.message}`); }

  let bank = null;
  if (quote === 'VND') {
    try {
      bank = await vietcombank(base);
      collected.push({ source: 'vietcombank-transfer', value: bank.transfer });
    } catch (e) { warnings.push(`vietcombank: ${e.message}`); }
  }

  // Reference: Google when available, else jsDelivr.
  reference = google || collected.find((c) => c.source === 'currency-api-jsdelivr') || null;
  if (!reference) {
    throw new Error(`No usable reference rate for ${base}/${quote}. Sources: ${warnings.join('; ')}`);
  }

  const near = collected.filter((c) => c.source !== 'vietcombank-transfer');
  const deviations = near.map((c) => ({
    source: c.source,
    value: c.value,
    deviationPct: ((c.value - reference.value) / reference.value) * 100,
  }));

  const hardBreaches = deviations.filter(
    (d) => d.source !== reference.source && Math.abs(d.deviationPct) / 100 > MAX_SPREAD,
  );
  if (hardBreaches.length > 0) {
    throw new Error(
      `Rate sources disagree for ${base}/${quote} beyond ${(MAX_SPREAD * 100).toFixed(2)}%: ` +
        deviations.map((d) => `${d.source}=${d.value.toFixed(2)} (${d.deviationPct.toFixed(2)}%)`).join(', '),
    );
  }
  if (google) {
    const jsd = deviations.find((d) => d.source === 'currency-api-jsdelivr');
    if (jsd && Math.abs(jsd.deviationPct) / 100 > GOOGLE_TOLERANCE) {
      throw new Error(`Google vs jsDelivr disagree by ${jsd.deviationPct.toFixed(2)}% for ${base}/${quote}`);
    }
  }
  if (bank) {
    const bankDev = ((bank.transfer - reference.value) / reference.value) * 100;
    if (Math.abs(bankDev) > 5) warnings.push(`vietcombank transfer differs ${bankDev.toFixed(2)}% (bank spread?)`);
  }

  return {
    base,
    quote,
    rate: Number(reference.value.toFixed(6)),
    source: reference.source,
    checked: deviations.map((d) => ({ source: d.source, value: Number(d.value.toFixed(6)), deviationPct: Number(d.deviationPct.toFixed(4)) })),
    bank: bank ? { buy: bank.buy, transfer: bank.transfer, sell: bank.sell } : null,
    warnings,
  };
}

/* ---------------- run ---------------- */

const read = (p) => JSON.parse(fs.readFileSync(p, 'utf8').replace(/^\uFEFF/, ''));
const esc = (v) => {
  if (v == null) return '';
  const s = String(v).replace(/"/g, '""');
  return /[",\n]/.test(s) ? `"${s}"` : s;
};

const data = read(SRC);
const currencies = [...new Set(data.records.map((r) => r.currency))].filter((c) => c !== 'VND');

const rates = {};
for (const cur of currencies) rates[cur] = await resolveRate(cur, 'VND');

const now = new Date().toISOString();
const records = data.records.map((r) => {
  const rate = r.currency === 'VND' ? 1 : rates[r.currency].rate;
  const convert = (v) => (v == null ? null : Math.round(v * rate));
  return {
    ...r,
    priceVnd: convert(r.effectivePrice),
    originalPriceVnd: convert(r.listedPrice),
    fxRateVndPerUnit: r.currency === 'VND' ? 1 : rate,
    fxSource: r.currency === 'VND' ? null : rates[r.currency].source,
    fxCheckedAt: now,
  };
});

const meta = {
  ...data.meta,
  convertedTo: 'VND',
  convertedAt: now,
  fxTolerancePct: Number((MAX_SPREAD * 100).toFixed(2)),
  fx: Object.fromEntries(Object.entries(rates).map(([c, r]) => [c, { vndPerUnit: r.rate, source: r.source, checked: r.checked, bank: r.bank }])),
  total: records.length,
};

fs.mkdirSync(OUT_DIR, { recursive: true });
fs.writeFileSync(path.join(OUT_DIR, 'fx-rates.json'), JSON.stringify({ fetchedAt: now, rates }, null, 2));
fs.writeFileSync(path.join(OUT_DIR, 'competitor-prices-vnd.json'), JSON.stringify({ meta, records }, null, 2));

const cols = [
  'marketplace', 'category', 'product_id', 'title', 'seller', 'brand',
  'price', 'currency', 'price_vnd', 'original_price', 'original_price_vnd',
  'discount_percent', 'rating', 'review_count', 'sold', 'fx_rate_vnd_per_unit',
  'fx_source', 'url', 'observed_at', 'confidence',
];
const lines = [cols.join(',')];
for (const r of records) {
  lines.push([
    r.marketplaceCode, r.categoryName, r.externalProductId, r.productTitle, r.sellerName,
    r.brand, r.effectivePrice, r.currency, r.priceVnd, r.listedPrice, r.originalPriceVnd,
    r.discountPercent, r.rating, r.reviewCount, r.soldCount ?? r.soldDisplay,
    r.fxRateVndPerUnit, r.fxSource, r.url, r.observedAt, r.confidence,
  ].map(esc).join(','));
}
fs.writeFileSync(path.join(OUT_DIR, 'competitor-prices-vnd.csv'), '\uFEFF' + lines.join('\n'), 'utf8');

for (const [c, r] of Object.entries(rates)) {
  console.log(`${c}→VND ${r.rate} [${r.source}] checked:`, r.checked.map((x) => `${x.source} ${x.value} (${x.deviationPct}%)`).join('; '));
  if (r.warnings.length) console.log('  warnings:', r.warnings.join('; '));
}
console.log(`records ${records.length} → datasets/competitor-prices-vnd.{json,csv}`);