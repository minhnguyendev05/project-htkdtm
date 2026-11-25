/*
 * Unified competitor dataset — REAL data for UI + AI train/test.
 *
 * Sources (all fetched via API, no scraping bypass):
 * - Tiki VN (ReefAPI tiki v1 search)
 * - AliExpress (ReefAPI aliexpress v1 search, ship-to VN, VND)
 * - 1688 CN wholesale (ReefAPI 1688 v1 category/offers + search, CNY)
 * - TikTok Shop VN (ReefAPI tiktok-shop v1 category_products)
 * - Shopee VN (Magpie scraping v1 shopee get_pc)
 *
 * Rules: listed vs effective price kept separate; discountPercent comes from
 * the marketplace; 1688 is wholesale CNY and must not be compared to VND retail.
 * Regenerate with the build script; this file only exposes the snapshot.
 */
import ai from './collected-ai-dataset.json';

export type MarketplaceCode =
  | 'TIKTOK_SHOP'
  | 'TIKI'
  | 'SHOPEE'
  | '1688'
  | 'ALIEXPRESS'
  | 'LAZADA';

export interface CollectedMarketplacePrice {
  id: string;
  marketplaceCode: MarketplaceCode;
  categoryName: string;
  externalProductId: string;
  productTitle: string;
  url: string | null;
  /** Original marketplace URL when `url` is nulled (e.g. region-locked). */
  sourceUrl?: string | null;
  urlStatus?: 'ok' | 'region_locked';
  fallbackUrl?: string | null;
  sellerName: string | null;
  brand: string | null;
  listedPrice: number | null;
  effectivePrice: number;
  currency: 'VND' | 'CNY';
  discountPercent: number | null;
  rating: number | null;
  reviewCount: number;
  soldCount: number | null;
  soldDisplay?: string | null;
  unit?: string | null;
  moq?: number | null;
  promo?: string | null;
  skuCount: number | null;
  isOutlier: boolean;
  isAd?: boolean;
  observedAt: string;
  sourceType: 'API';
  sourceName: string;
  confidence: number;
}

export interface MultiCollectedMeta {
  collectedAt: string;
  market: string;
  marketplaces: Record<string, number>;
  categories: Record<string, number>;
  total: number;
  withDiscount: number;
  withSold: number;
  source: string;
  note: string;
}

export const MULTI_COMPETITOR_META = ai.meta as MultiCollectedMeta;

export const ALL_COLLECTED_PRICES = ai.records as CollectedMarketplacePrice[];

export const MARKETPLACE_LABELS: Record<MarketplaceCode, string> = {
  TIKTOK_SHOP: 'TikTok Shop',
  TIKI: 'Tiki',
  SHOPEE: 'Shopee',
  '1688': '1688',
  ALIEXPRESS: 'AliExpress',
  LAZADA: 'Lazada',
};