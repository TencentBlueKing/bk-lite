import React from 'react';
import { Button, Dropdown, Modal, Tooltip } from 'antd';
import type { MenuProps } from 'antd';
import { MoreOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import usePermissions from '@/hooks/usePermissions';

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
  const { hasPermission } = usePermissions();
  const label = ariaLabel ?? t('common.more');
  const [open, setOpen] = React.useState(false);

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

  const menuItems: MenuProps['items'] = items.map((item) => {
    const requiredPermissions = item.permission
      ? Array.isArray(item.permission)
        ? item.permission
        : [item.permission]
      : null;
    const hasItemPermission = requiredPermissions
      ? hasPermission(requiredPermissions)
      : true;
    const disabled = Boolean(item.disabled) || !hasItemPermission;

    return {
      key: item.key,
      label: hasItemPermission ? item.label : (
        <Tooltip title={t('common.noAuth')}>
          <span>{item.label}</span>
        </Tooltip>
      ),
      disabled,
      danger: item.danger,
      icon: item.icon,
      onClick: (info) => {
        if (disabled) return;
        info.domEvent.stopPropagation();
        setOpen(false);
        runItem(item);
      },
    };
  });

  return (
    <Dropdown
      menu={{ items: menuItems }}
      trigger={trigger}
      placement={placement}
      overlayClassName={overlayClassName}
      open={open}
      onOpenChange={setOpen}
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
