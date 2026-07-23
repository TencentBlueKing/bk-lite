import React from 'react';
import { Button, Dropdown, Modal } from 'antd';
import { MoreOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import PermissionWrapper from '@/components/permission';

export interface MoreActionsDropdownItem {
  key: string;
  label: React.ReactNode;
  onClick?: (e?: React.MouseEvent) => unknown;
  permission?: string | string[];
  disabled?: boolean;
  danger?: boolean;
  icon?: React.ReactNode;
  confirm?: {
    title: React.ReactNode;
    content?: React.ReactNode;
    okText?: React.ReactNode;
    cancelText?: React.ReactNode;
  };
}

export interface MoreActionsDropdownProps {
  items: MoreActionsDropdownItem[];
  ariaLabel?: string;
  placement?: 'bottomRight' | 'bottomLeft' | 'bottom' | 'topRight' | 'topLeft' | 'top';
  trigger?: ('click' | 'hover' | 'contextMenu')[];
  stopPropagation?: boolean;
  buttonSize?: 'small' | 'middle' | 'large';
  buttonType?: 'text' | 'link' | 'default';
  buttonClassName?: string;
  overlayClassName?: string;
  iconStyle?: React.CSSProperties;
}

const MoreActionsDropdown: React.FC<MoreActionsDropdownProps> = ({
  items,
  ariaLabel,
  placement = 'bottomRight',
  trigger = ['click'],
  stopPropagation = false,
  buttonSize = 'small',
  buttonType = 'text',
  buttonClassName,
  overlayClassName,
  iconStyle,
}) => {
  const { t } = useTranslation();
  const label = ariaLabel ?? t('common.more');

  const runItem = (item: MoreActionsDropdownItem) => {
    if (item.disabled) return;
    if (item.confirm) {
      Modal.confirm({
        title: item.confirm.title,
        content: item.confirm.content,
        okText: item.confirm.okText ?? t('common.confirm'),
        cancelText: item.confirm.cancelText ?? t('common.cancel'),
        centered: true,
        onOk: () => Promise.resolve(item.onClick?.()),
      });
      return;
    }
    Promise.resolve(item.onClick?.()).catch(() => undefined);
  };

  return (
    <Dropdown
      menu={{
        items: items.map((item) => {
          const requiredPermissions = item.permission
            ? Array.isArray(item.permission)
              ? item.permission
              : [item.permission]
            : null;
          const buttonNode = (
            <Button
              type="text"
              size="small"
              danger={item.danger}
              disabled={item.disabled}
              icon={item.icon}
              className="w-full text-left"
              onClick={(e) => {
                e.stopPropagation();
                runItem(item);
              }}
            >
              {item.label}
            </Button>
          );
          return {
            key: item.key,
            label: requiredPermissions ? (
              <PermissionWrapper requiredPermissions={requiredPermissions}>
                {buttonNode}
              </PermissionWrapper>
            ) : (
              buttonNode
            ),
          };
        }),
      }}
      trigger={trigger}
      placement={placement}
      overlayClassName={overlayClassName}
    >
      <Button
        type={buttonType}
        size={buttonSize}
        aria-label={label}
        icon={<MoreOutlined aria-hidden="true" style={iconStyle} />}
        className={buttonClassName}
        onClick={(e) => {
          if (stopPropagation) e.stopPropagation();
        }}
      />
    </Dropdown>
  );
};

export default MoreActionsDropdown;