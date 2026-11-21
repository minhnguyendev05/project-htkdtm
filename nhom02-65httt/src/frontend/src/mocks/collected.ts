/*
 * Collected competitor price data — REAL TikTok Shop VN data.
 *
 * Source: ReefAPI tiktok-shop v1 `category_products` (market=vn), fetched in a
 * single batch of 6 leaf categories x 50 products (~299 records).
 * This is planned seed data for the MVP ("dữ liệu dự kiến"). It is NOT mapped
 * to internal SKUs yet — treat marketplaceCode + externalProductId as the key.
 *
 * Rules honoured (see SPEC.md / BUSINESS_RULES.md):
 * - listedPrice and effectivePrice are kept separate; a promotional price is
 *   never used as the listed price.
 * - Records with effectivePrice <= 1000 VND are bait listings and flagged
 *   isOutlier = true (do not use as a primary signal, BR-005).
 * - sourceType = API, confidence = 0.9 (structured product-page data).
 *
 * Regenerate: POST /tiktok-shop/v1/category_products {category_id, market:"vn",
 * max_results:50} per category, then normalize into this JSON.
 */
import raw from './collected-tiktok-vn.json';

export interface CollectedCompetitorPrice {
  id: string;
  marketplaceCode: 'TIKTOK_SHOP';
  categoryId: string;
  categoryName: string;
  externalProductId: string;
  productTitle: string;
  url: string;
  sellerId: string;
  sellerName: string;
  brand: string | null;
  listedPrice: number | null;
  effectivePrice: number;
  currency: 'VND';
  discountPercent: number | null;
  isPromotional: boolean;
  rating: number | null;
  reviewCount: number;
  soldCount: number;
  skuCount: number;
  isOutlier: boolean;
  observedAt: string;
  sourceType: 'API';
  sourceName: string;
  confidence: number;
}

export interface CollectedMeta {
  marketplaceCode: string;
  market: string;
  collectedAt: string;
  source: string;
  categoryCounts: Record<string, number>;
  total: number;
  note: string;
}

export const COLLECTED_COMPETITOR_META = raw.meta as CollectedMeta;

export const COLLECTED_COMPETITOR_PRICES =
  raw.records as CollectedCompetitorPrice[];

/** Records safe to use as a pricing signal (fresh, not bait). */
export function usableCollectedPrices(): CollectedCompetitorPrice[] {
  return COLLECTED_COMPETITOR_PRICES.filter((r) => !r.isOutlier && r.effectivePrice > 0);
}