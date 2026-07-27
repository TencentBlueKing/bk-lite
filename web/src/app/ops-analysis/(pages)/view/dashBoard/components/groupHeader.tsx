import React from 'react';
import {
  CaretDownFilled,
  CaretRightFilled,
  HolderOutlined,
} from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import MoreActionsDropdown from '@/components/more-actions-dropdown';
import type { MoreActionsDropdownItem } from '@/components/more-actions-dropdown';
import type { DashboardGroupLayoutItem } from '@/app/ops-analysis/types/dashBoard';

interface GroupHeaderProps {
  item: DashboardGroupLayoutItem;
  collapsed: boolean;
  isEditMode: boolean;
  onAddView: () => void;
  onToggle: () => void;
  onRename: () => void;
  onRemoveGroup: () => void;
  onDeleteGroup: () => void;
}

const GroupHeader: React.FC<GroupHeaderProps> = ({
  item,
  collapsed,
  isEditMode,
  onAddView,
  onToggle,
  onRename,
  onRemoveGroup,
  onDeleteGroup,
}) => {
  const { t } = useTranslation();
  const menuItems: MoreActionsDropdownItem[] = [
    { key: 'add-view', label: t('dashboard.addView'), onClick: onAddView },
    { key: 'rename', label: t('dashboard.editGroup'), onClick: onRename },
    { key: 'remove', label: t('dashboard.unGroup'), onClick: onRemoveGroup },
    { key: 'delete', label: t('dashboard.deleteEntireGroup'), onClick: onDeleteGroup, danger: true },
  ];

  return (
    <div
      className={`flex min-h-9.5 items-center justify-between gap-2 px-3 py-1.5 ${
        isEditMode ? 'cursor-grab active:cursor-grabbing' : ''
      }`}
    >
      {isEditMode ? (
        <div className="flex min-w-0 items-center gap-2 text-(--color-text-1)">
          <span className="flex items-center text-[12px] text-(--color-text-3)">
            <HolderOutlined />
          </span>
          <button
            type="button"
            onClick={onToggle}
            className="no-drag flex cursor-pointer items-center text-[10px] text-(--color-text-2)"
            aria-label={collapsed ? t('common.expand') : t('common.collapse')}
          >
            {collapsed ? <CaretRightFilled /> : <CaretDownFilled />}
          </button>
          <div className="min-w-0 flex items-baseline gap-2">
            <span className="truncate text-[14px] font-medium leading-5">
              {item.name}
            </span>
          </div>
        </div>
      ) : (
        <button
          type="button"
          onClick={onToggle}
          className="no-drag flex min-w-0 cursor-pointer items-center gap-2 text-(--color-text-1)"
        >
          <span className="cursor-pointer text-[10px] text-(--color-text-2)">
            {collapsed ? <CaretRightFilled /> : <CaretDownFilled />}
          </span>
          <div className="min-w-0 flex items-baseline gap-2">
            <span className="truncate text-[14px] font-medium leading-5">
              {item.name}
            </span>
          </div>
        </button>
      )}

      {isEditMode && (
        <MoreActionsDropdown
          items={menuItems}
          stopPropagation
          buttonClassName="no-drag h-7 w-7 rounded-full! text-(--color-text-2)!"
        />
      )}
    </div>
  );
};

export default GroupHeader;
