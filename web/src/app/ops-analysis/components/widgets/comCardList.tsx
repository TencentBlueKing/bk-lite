import React, { useEffect } from 'react';
import { Alert } from 'antd';
import ChartSurface from '@/components/chart-surface';
import type { ValueConfig } from '@/app/ops-analysis/types/dashBoard';
import {
  DEFAULT_CARD_LIST_MAX_ITEMS,
  parseCardListItems,
} from '@/app/ops-analysis/utils/cardList';
import { useTranslation } from '@/utils/i18n';
import { CardListAccent } from './cardListAccent';
import { buildScreenContentTokenStyle } from '@/app/ops-analysis/utils/screenWidgetTokens';

interface ComCardListProps {
  rawData: unknown;
  loading?: boolean;
  config?: ValueConfig;
  onReady?: (ready: boolean) => void;
}

const ComCardList: React.FC<ComCardListProps> = ({
  rawData,
  loading = false,
  config,
  onReady,
}) => {
  const { t } = useTranslation();
  const screenContentStyle = buildScreenContentTokenStyle(config?.chartThemeMode);
  const cardListConfig = config?.cardList;
  const parsed = parseCardListItems(rawData, {
    ...cardListConfig,
    titleField: cardListConfig?.titleField || '',
  });
  const layout = cardListConfig?.layout === 'grid' ? 'grid' : 'list';
  const hasData = parsed.status === 'ready' && parsed.items.length > 0;
  const leadingStyle = cardListConfig?.leading?.style;
  const badgeStyle = cardListConfig?.badgeStyle;

  useEffect(() => {
    if (!loading) {
      onReady?.(hasData);
    }
  }, [hasData, loading, onReady]);

  return (
    <div className="h-full min-h-0 w-full" style={screenContentStyle}>
      <ChartSurface
        loading={loading}
        hasData={hasData}
        containerClassName="flex h-full min-h-0 w-full flex-col p-3"
        loadingClassName="flex h-full w-full items-center justify-center"
        emptyClassName="flex h-full w-full items-center justify-center"
      >
      {parsed.truncated ? (
        <Alert
          type="warning"
          showIcon
          className="mb-2"
          message={`${t('dashboard.cardListOverflowWarning')} (${parsed.total}/${DEFAULT_CARD_LIST_MAX_ITEMS})`}
        />
      ) : null}
      <div className="min-h-0 flex-1 overflow-y-auto pr-1">
        <div
          data-layout={layout}
          className={
            layout === 'grid'
              ? 'grid grid-cols-[repeat(auto-fill,minmax(240px,1fr))] gap-2'
              : 'flex flex-col gap-2'
          }
        >
          {parsed.items.map((item, index) => (
            <article
              key={`${item.primary}-${index}`}
              className="flex min-w-0 items-center gap-3 rounded-md border border-(--color-border-2) bg-(--color-bg) px-3 py-2"
            >
              {item.leading ? (
                <CardListAccent
                  text={item.leading}
                  style={leadingStyle}
                  kind="leading"
                />
              ) : null}
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm font-medium text-(--color-text-1)">
                  {item.primary}
                </div>
                {item.secondary ? (
                  <div className="mt-0.5 line-clamp-2 text-xs text-(--color-text-2)">
                    {item.secondary}
                  </div>
                ) : null}
              </div>
              {item.badge || item.trailingPrimary || item.trailingSecondary ? (
                <div className="flex min-w-0 shrink-0 flex-col items-end gap-1">
                  {item.badge ? (
                    <CardListAccent
                      text={item.badge}
                      style={badgeStyle}
                      kind="badge"
                    />
                  ) : null}
                  {item.trailingPrimary ? (
                    <span className="max-w-full truncate text-xs font-medium text-(--color-text-1)">
                      {item.trailingPrimary}
                    </span>
                  ) : null}
                  {item.trailingSecondary ? (
                    <span className="max-w-full truncate text-xs text-(--color-text-3)">
                      {item.trailingSecondary}
                    </span>
                  ) : null}
                </div>
              ) : null}
            </article>
          ))}
        </div>
      </div>
      </ChartSurface>
    </div>
  );
};

export default ComCardList;
