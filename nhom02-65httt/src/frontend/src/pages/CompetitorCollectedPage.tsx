import { useState } from 'react';
import { Database, Search, TriangleAlert } from 'lucide-react';
import {
  Card,
  CardBody,
  ErrorState,
  Input,
  KpiCard,
  LoadingState,
  PageHeader,
  Select,
  StatusPill,
} from '@/components/ui/primitives';
import { DataTable, Pagination, type Column } from '@/components/ui/DataTable';
import { Modal } from '@/components/ui/Modal';
import { useAsync } from '@/hooks/useAsync';
import { useDebouncedValue } from '@/hooks/useDebouncedValue';
import {
  collectedMeta,
  collectedStats,
  listCollectedCompetitorPrices,
} from '@/mocks/collectedApi';
import { dateTime, moneyCurrency, percent, quantity } from '@/lib/format';
import {
  MARKETPLACE_LABELS,
  type CollectedMarketplacePrice,
  type MarketplaceCode,
} from '@/mocks/collected';

const MARKETPLACE_OPTIONS: MarketplaceCode[] = [
  'TIKTOK_SHOP',
  'TIKI',
  'SHOPEE',
  '1688',
  'ALIEXPRESS',
  'LAZADA',
];

export function CompetitorCollectedPage() {
  const meta = collectedMeta();
  const stats = collectedStats();
  const categoryNames = Object.keys(stats.categoryNames).sort();

  const [term, setTerm] = useState('');
  const [marketplace, setMarketplace] = useState<MarketplaceCode | ''>('');
  const [categoryName, setCategoryName] = useState('');
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<CollectedMarketplacePrice | null>(null);
  const [copied, setCopied] = useState(false);
  const q = useDebouncedValue(term);

  const { data, loading, error, reload } = useAsync(
    () =>
      listCollectedCompetitorPrices({
        q,
        marketplace,
        categoryName: categoryName || undefined,
        page,
        pageSize: 12,
      }),
    [q, marketplace, categoryName, page],
  );

  const columns: Column<CollectedMarketplacePrice>[] = [
    {
      key: 'market',
      header: 'Sàn',
      render: (r) => (
        <StatusPill tone={r.marketplaceCode === '1688' ? 'warning' : 'neutral'}>
          {MARKETPLACE_LABELS[r.marketplaceCode]}
        </StatusPill>
      ),
    },
    {
      key: 'title',
      header: 'Sản phẩm',
      render: (r) => (
        <div className="min-w-0 max-w-md">
          <button
            type="button"
            onClick={() => setSelected(r)}
            className="block w-full truncate text-left font-medium text-ink hover:text-primary hover:underline"
            title="Xem chi tiết sản phẩm"
          >
            {r.productTitle}
          </button>
          <p className="font-mono text-[11px] text-muted">{r.externalProductId}</p>
        </div>
      ),
    },
    {
      key: 'seller',
      header: 'Shop / NCC',
      render: (r) => <span className="text-muted">{r.sellerName ?? '—'}</span>,
    },
    {
      key: 'category',
      header: 'Danh mục',
      render: (r) => <span className="text-xs text-muted">{r.categoryName}</span>,
    },
    {
      key: 'listed',
      header: 'Giá gốc',
      align: 'right',
      render: (r) => (
        <span className="tnum text-muted">{moneyCurrency(r.listedPrice, r.currency)}</span>
      ),
    },
    {
      key: 'effective',
      header: 'Giá bán',
      align: 'right',
      sortable: true,
      sortValue: (r) => r.effectivePrice,
      render: (r) => (
        <span className={`tnum font-medium ${r.isOutlier ? 'text-danger' : 'text-ink'}`}>
          {moneyCurrency(r.effectivePrice, r.currency)}
        </span>
      ),
    },
    {
      key: 'discount',
      header: 'Giảm',
      align: 'right',
      render: (r) => (
        <span className="tnum text-muted">
          {r.discountPercent == null ? '—' : percent(r.discountPercent / 100, 0)}
        </span>
      ),
    },
    {
      key: 'sold',
      header: 'Đã bán',
      align: 'right',
      sortable: true,
      sortValue: (r) => r.soldCount ?? 0,
      render: (r) => (
        <span className="tnum">
          {r.soldDisplay ?? (r.soldCount == null ? '—' : quantity(r.soldCount))}
        </span>
      ),
    },
    {
      key: 'flag',
      header: 'Cờ',
      render: (r) =>
        r.isOutlier ? (
          <StatusPill tone="danger">Bait/Outlier</StatusPill>
        ) : r.isAd ? (
          <StatusPill tone="warning">Quảng cáo</StatusPill>
        ) : r.discountPercent ? (
          <StatusPill tone="info">Khuyến mãi</StatusPill>
        ) : (
          <span className="text-xs text-muted">—</span>
        ),
    },
  ];

  return (
    <>
      <PageHeader
        title="Dữ liệu đối thủ thu thập"
        description="Ảnh chụp (snapshot) dữ liệu công khai đa sàn qua API, không phải realtime. Chưa map sang SKU nội bộ."
        actions={
          <>
            <StatusPill tone="neutral">SNAPSHOT</StatusPill>
            <StatusPill tone="success">
              <Database className="size-3" aria-hidden="true" />
              API · {Object.keys(stats.marketplaceCounts).length} sàn
            </StatusPill>
          </>
        }
      />

      <div className="mb-4 grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard
          label="Bản ghi"
          value={quantity(stats.total)}
          hint={`Thu thập ${dateTime(meta.collectedAt)}`}
        />
        <KpiCard
          label="Sàn"
          value={quantity(Object.keys(stats.marketplaceCounts).length)}
          hint={Object.entries(stats.marketplaceCounts)
            .map(([k, v]) => `${MARKETPLACE_LABELS[k as MarketplaceCode] ?? k}: ${v}`)
            .join(' · ')}
        />
        <KpiCard
          label="Bản ghi outlier"
          value={quantity(stats.outlierCount)}
          tone="warning"
          hint="Giá VND ≤ 1.000 ₫ (bait) không dùng làm tín hiệu"
          icon={<TriangleAlert className="size-4" />}
        />
        <KpiCard label="Nguồn" value="ReefAPI + Magpie" hint="Tiki · AliExpress · 1688 · TikTok · Shopee" />
      </div>

      <Card>
        <div className="flex flex-col gap-3 border-b border-border p-4 lg:flex-row lg:items-center">
          <div className="relative flex-1">
            <Search
              className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted"
              aria-hidden="true"
            />
            <Input
              value={term}
              onChange={(e) => {
                setTerm(e.target.value);
                setPage(1);
              }}
              placeholder="Tìm tên sản phẩm, shop, product id..."
              aria-label="Tìm dữ liệu thu thập"
              className="pl-8"
            />
          </div>
          <Select
            value={marketplace}
            onChange={(e) => {
              setMarketplace(e.target.value as MarketplaceCode | '');
              setPage(1);
            }}
            aria-label="Lọc theo sàn"
            className="lg:w-44"
          >
            <option value="">Tất cả sàn</option>
            {MARKETPLACE_OPTIONS.filter((code) => stats.marketplaceCounts[code]).map(
              (code) => (
                <option key={code} value={code}>
                  {MARKETPLACE_LABELS[code]} ({stats.marketplaceCounts[code]})
                </option>
              ),
            )}
          </Select>
          <Select
            value={categoryName}
            onChange={(e) => {
              setCategoryName(e.target.value);
              setPage(1);
            }}
            aria-label="Lọc theo danh mục"
            className="lg:w-56"
          >
            <option value="">Tất cả danh mục</option>
            {categoryNames.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </Select>
        </div>

        {loading && !data ? (
          <LoadingState />
        ) : error || !data ? (
          <ErrorState message={error ?? 'Không tải được dữ liệu.'} onRetry={reload} />
        ) : (
          <>
            <DataTable
              columns={columns}
              rows={data.data}
              rowKey={(r) => r.id}
              caption="Dữ liệu giá đối thủ thu thập đa sàn"
              emptyMessage="Không có bản ghi phù hợp."
            />
            <Pagination
              page={data.meta.page}
              totalPages={data.meta.totalPages}
              total={data.meta.total}
              onPage={setPage}
            />
          </>
        )}
      </Card>

      <CardBody className="mt-3 rounded-[var(--radius-card)] border border-border bg-surface-subtle text-xs text-muted">
        {meta.note} Nguồn: {meta.source}. Giá khuyến mãi và giá gốc tách riêng; 1688 là giá sỉ CNY,
        không so trực tiếp với giá bán lẻ VND.
      </CardBody>

      <Modal
        open={selected !== null}
        title={selected?.productTitle ?? ''}
        description={selected ? `${MARKETPLACE_LABELS[selected.marketplaceCode]} · ${selected.externalProductId}` : undefined}
        onClose={() => setSelected(null)}
        footer={
          selected ? (
            selected.urlStatus === 'region_locked' ? (
              <>
                {selected.fallbackUrl ? (
                  <a
                    href={selected.fallbackUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex h-8 items-center rounded-[var(--radius-control)] bg-primary px-3 text-xs font-medium text-white hover:bg-primary-hover"
                  >
                    Tìm trên TikTok
                  </a>
                ) : null}
                {selected.url ? (
                  <button
                    type="button"
                    onClick={async () => {
                      try {
                        await navigator.clipboard.writeText(selected.url as string);
                        setCopied(true);
                        window.setTimeout(() => setCopied(false), 1500);
                      } catch {
                        setCopied(false);
                      }
                    }}
                    className="inline-flex h-8 items-center rounded-[var(--radius-control)] border border-border bg-surface px-3 text-xs font-medium text-ink hover:bg-surface-subtle"
                  >
                    {copied ? 'Đã sao chép' : 'Sao chép link gốc'}
                  </button>
                ) : null}
              </>
            ) : (
              <>
                {selected.fallbackUrl ? (
                  <a
                    href={selected.fallbackUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex h-8 items-center rounded-[var(--radius-control)] border border-border bg-surface px-3 text-xs font-medium text-ink hover:bg-surface-subtle"
                  >
                    Tìm trên TikTok
                  </a>
                ) : null}
                {selected.url ? (
                  <a
                    href={selected.url}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex h-8 items-center rounded-[var(--radius-control)] bg-primary px-3 text-xs font-medium text-white hover:bg-primary-hover"
                  >
                    Mở link gốc
                  </a>
                ) : null}
              </>
            )
          ) : null
        }
      >
        {selected ? (
          <div className="space-y-3 text-sm">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <p className="text-xs text-muted">Giá bán</p>
                <p className="tnum font-semibold">{moneyCurrency(selected.effectivePrice, selected.currency)}</p>
              </div>
              <div>
                <p className="text-xs text-muted">Giá gốc</p>
                <p className="tnum">{moneyCurrency(selected.listedPrice, selected.currency)}</p>
              </div>
              <div>
                <p className="text-xs text-muted">Giảm giá</p>
                <p className="tnum">
                  {selected.discountPercent == null ? '—' : percent(selected.discountPercent / 100, 1)}
                </p>
              </div>
              <div>
                <p className="text-xs text-muted">Đánh giá</p>
                <p className="tnum">{selected.rating == null ? '—' : selected.rating}</p>
              </div>
              <div>
                <p className="text-xs text-muted">Đã bán</p>
                <p className="tnum">
                  {selected.soldDisplay ??
                    (selected.soldCount == null ? '—' : quantity(selected.soldCount))}
                </p>
              </div>
              <div>
                <p className="text-xs text-muted">Danh mục</p>
                <p className="text-xs">{selected.categoryName}</p>
              </div>
            </div>
            <div className="rounded-[var(--radius-control)] border border-border bg-surface-subtle p-3 text-xs">
              <p className="text-muted">Shop / NCC</p>
              <p className="font-medium text-ink">{selected.sellerName ?? '—'}</p>
              {selected.brand ? <p className="mt-1 text-muted">Brand: {selected.brand}</p> : null}
            </div>
            {selected.urlStatus === 'region_locked' ? (
              <p className="rounded-[var(--radius-control)] border border-warning/30 bg-warning/5 px-3 py-2 text-xs text-ink">
                TikTok chỉ mở link gốc trong app hoặc khi truy cập từ VN. Trên desktop dùng
                “Tìm trên TikTok”.
              </p>
            ) : null}
            {selected.url ? (
              <p className="break-all text-[11px] text-muted">{selected.url}</p>
            ) : null}
          </div>
        ) : null}
      </Modal>
    </>
  );
}