import { Empty } from 'antd';

import { useTranslation } from '@/utils/i18n';

/** 整盘被模块许可 omit 后的查看态空态。不提供「去编辑」主按钮。 */
const ModuleLicenseCanvasEmpty = () => {
  const { t } = useTranslation();

  return (
    <div
      className="flex h-full min-h-[320px] w-full flex-col items-center justify-center px-6 py-16"
      data-module-license-canvas-empty="true"
    >
      <Empty
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description={(
          <div className="flex max-w-md flex-col items-center gap-1">
            <span className="text-(--color-text-1)">
              {t('dashboard.moduleLicenseCanvasEmpty')}
            </span>
            <span className="text-xs text-(--color-text-3)">
              {t('dashboard.moduleLicenseCanvasEmptyHint')}
            </span>
          </div>
        )}
      />
    </div>
  );
};

export default ModuleLicenseCanvasEmpty;
