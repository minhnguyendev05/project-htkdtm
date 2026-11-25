/*
 * Merge Magpie Shopee search-items JSON captures into the unified dataset.
 * Rich fields: price, strikethrough (original), discount, sold, rating.
 *
 * Usage: node scripts/merge-magpie-shopee-search.mjs <dir-with-json> [more dirs...]
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '..');
const DATASET = path.join(root, 'src/mocks/collected-ai-dataset.json');
const CSV = path.join(root, 'datasets/competitor-prices-vnd.csv');

const dirs = process.argv.slice(2).filter((a) => fs.existsSync(a));
if (dirs.length === 0) {
  console.error('usage: node scripts/merge-magpie-shopee-search.mjs <dir> [...]');
  process.exit(1);
}

const read = (p) => JSON.parse(fs.readFileSync(p, 'utf8').replace(/^\uFEFF/, ''));
const esc = (v) => {
  if (v == null) return '';
  const s = String(v).replace(/"/g, '""');
  return /[",\n]/.test(s) ? `"${s}"` : s;
};
const money = (v) => (v == null ? null : Number(v) / 100000);

function keywordOf(pageUrl) {
  try {
    const u = new URL(pageUrl);
    const k = u.searchParams.get('keyword');
    return k ? `Shopee · ${k}` : 'Shopee';
  } catch {
    return 'Shopee';
  }
}

const data = read(DATASET);
const seen = new Set(data.records.map((r) => r.marketplaceCode + ':' + r.externalProductId));
const observedAt = new Date().toISOString();
let added = 0;

for (const dir of dirs) {
  for (const file of fs.readdirSync(dir).filter((f) => /\.(json|bin)$/i.test(f))) {
    let j;
    try {
      j = read(path.join(dir, file));
    } catch {
      continue;
    }
    const items = j?.search_items?.items;
    if (!Array.isArray(items)) continue;
    const categoryName = keywordOf(j.page_url);
    for (const it of items) {
      const asset = it.item_card_displayed_asset || {};
      const dp = asset.display_price || {};
      const price = money(dp.price);
      if (!it.itemid || price == null) continue;
      const key = 'SHOPEE:' + it.itemid;
      if (seen.has(key)) continue;
      seen.add(key);
      const dd = it.item_data || {};
      const soldInfo = dd.item_card_display_sold_count || {};
      const rating = dd.item_rating || {};
      const discount = dd.item_card_display_price?.discount;
      data.records.push({
        id: 'cp-shopee-' + it.itemid,
        marketplaceCode: 'SHOPEE',
        categoryName,
        externalProductId: String(it.itemid),
        productTitle: asset.name || it.display_name || '(không tên)',
        url: `https://shopee.vn/product/${it.shopid}/${it.itemid}`,
        sellerName: it.shopid ? 'shop ' + it.shopid : null,
        brand: dd.global_brand?.display_name || null,
        listedPrice: money(dp.strikethrough_price),
        effectivePrice: price,
        currency: 'VND',
        discountPercent: discount == null ? null : Number(discount),
        rating: rating.rating_star == null ? null : Number(Number(rating.rating_star).toFixed(2)),
        reviewCount: Array.isArray(rating.rating_count)
          ? rating.rating_count.reduce((a, b) => a + (Number(b) || 0), 0)
          : 0,
        soldCount: soldInfo.historical_sold_count == null ? null : Number(soldInfo.historical_sold_count),
        soldDisplay: soldInfo.historical_sold_count_text || null,
        skuCount: null,
        isOutlier: !(price > 1000),
        isAd: Boolean(it.display_ad_tag),
        observedAt,
        sourceType: 'API',
        sourceName: 'Magpie Shopee search-items',
        confidence: 0.9,
      });
      added++;
    }
  }
}

const byMarketplace = {};
const byCategory = {};
for (const r of data.records) {
  byMarketplace[r.marketplaceCode] = (byMarketplace[r.marketplaceCode] || 0) + 1;
  byCategory[r.categoryName] = (byCategory[r.categoryName] || 0) + 1;
}
data.meta.marketplaces = byMarketplace;
data.meta.categories = byCategory;
data.meta.total = data.records.length;
data.meta.withDiscount = data.records.filter((r) => r.discountPercent != null).length;
data.meta.withSold = data.records.filter((r) => (r.soldCount ?? 0) > 0).length;

fs.writeFileSync(DATASET, JSON.stringify(data, null, 2), 'utf8');
console.log(`added ${added} shopee rows; total ${data.records.length}; ${JSON.stringify(byMarketplace)}; withSold ${data.meta.withSold}`);