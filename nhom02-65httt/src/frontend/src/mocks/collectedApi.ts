/*
 * Collected-data accessors. Kept OUT of `mocks/api.ts` so the large JSON
 * snapshots are only pulled in by the lazily-loaded collected page.
 */
import type { Paged } from '@/types/domain';
import {
  ALL_COLLECTED_PRICES,
  MULTI_COMPETITOR_META,
  type CollectedMarketplacePrice,
  type MarketplaceCode,
  type MultiCollectedMeta,
} from './collected';

const clone = <T>(v: T): T => structuredClone(v);
const wait = (ms = 320) => new Promise((r) => setTimeout(r, ms));

function paginate<T>(items: T[], page = 1, pageSize = 10): Paged<T> {
  const total = items.length;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const safePage = Math.min(Math.max(1, page), totalPages);
  const start = (safePage - 1) * pageSize;
  return {
    data: items.slice(start, start + pageSize),
    meta: { page: safePage, pageSize, total, totalPages },
  };
}

export function collectedMeta(): MultiCollectedMeta {
  return MULTI_COMPETITOR_META;
}

export interface CollectedStats {
  total: number;
  outlierCount: number;
  categoryCount: number;
  categoryNames: Record<string, string>;
  marketplaceCounts: Record<string, number>;
}

export function collectedStats(): CollectedStats {
  const categoryNames: Record<string, string> = {};
  const marketplaceCounts: Record<string, number> = {};
  for (const record of ALL_COLLECTED_PRICES) {
    categoryNames[record.categoryName] = record.categoryName;
    marketplaceCounts[record.marketplaceCode] =
      (marketplaceCounts[record.marketplaceCode] ?? 0) + 1;
  }
  return {
    total: ALL_COLLECTED_PRICES.length,
    outlierCount: ALL_COLLECTED_PRICES.filter((r) => r.isOutlier).length,
    categoryCount: Object.keys(categoryNames).length,
    categoryNames,
    marketplaceCounts,
  };
}

export async function listCollectedCompetitorPrices(params: {
  q?: string;
  marketplace?: MarketplaceCode | '';
  categoryName?: string;
  page?: number;
  pageSize?: number;
}): Promise<Paged<CollectedMarketplacePrice>> {
  await wait();
  const q = params.q?.trim().toLowerCase() ?? '';
  const items = ALL_COLLECTED_PRICES.filter((r) => {
    if (
      q &&
      !`${r.productTitle} ${r.sellerName ?? ''} ${r.externalProductId}`
        .toLowerCase()
        .includes(q)
    )
      return false;
    if (params.marketplace && r.marketplaceCode !== params.marketplace) return false;
    if (params.categoryName && r.categoryName !== params.categoryName) return false;
    return true;
  });
  return paginate(clone(items), params.page, params.pageSize ?? 10);
}