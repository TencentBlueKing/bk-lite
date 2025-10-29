import React from 'react';
import { Menu, Dropdown } from 'antd';
import { useTranslation } from '@/utils/i18n';
import type { ContextMenuProps } from '@/app/ops-analysis/types/topology';
import {
  VerticalAlignTopOutlined,
  VerticalAlignBottomOutlined,
  UpOutlined,
  DownOutlined,
  LinkOutlined,
  ArrowRightOutlined,
  SwapOutlined,
  SettingOutlined,
  DeleteOutlined,
  EditOutlined,
  CopyOutlined,
} from '@ant-design/icons';

const ContextMenu: React.FC<ContextMenuProps> = ({
  visible,
  position,
  isEditMode = false,
  targetType = 'node',
  onMenuClick,
}) => {
  const { t } = useTranslation();

  const getEdgeEditMenu = () => (
    <Menu onClick={onMenuClick}>
      <Menu.Item key="configure" icon={<SettingOutlined />}>
        {t('topology.configureEdge')}
      </Menu.Item>
      <Menu.Item key="delete" icon={<DeleteOutlined />}>
        {t('topology.delete')}
      </Menu.Item>
    </Menu>
  );

  const getNodeEditMenu = () => (
    <Menu onClick={onMenuClick}>
      <Menu.Item key="edit" icon={<EditOutlined />}>
        {t('topology.editNode')}
      </Menu.Item>
      <Menu.Item key="copy" icon={<CopyOutlined />}>
        {t('topology.copyNode')}
      </Menu.Item>
      <Menu.Item key="delete" icon={<DeleteOutlined />}>
        {t('topology.delete')}
      </Menu.Item>
      <Menu.Item key="bringToFront" icon={<VerticalAlignTopOutlined />}>
        {t('topology.bringToFront')}
      </Menu.Item>
      <Menu.Item key="bringToBack" icon={<VerticalAlignBottomOutlined />}>
        {t('topology.bringToBack')}
      </Menu.Item>
      <Menu.Item key="bringForward" icon={<UpOutlined />}>
        {t('topology.bringForward')}
      </Menu.Item>
      <Menu.Item key="sendBackward" icon={<DownOutlined />}>
        {t('topology.sendBackward')}
      </Menu.Item>
      <Menu.Divider />
      <Menu.Item key="none" icon={<LinkOutlined />}>
        {t('topology.noArrowConnection')}
      </Menu.Item>
      <Menu.Item key="single" icon={<ArrowRightOutlined />}>
        {t('topology.singleArrowConnection')}
      </Menu.Item>
      <Menu.Item key="double" icon={<SwapOutlined />}>
        {t('topology.doubleArrowConnection')}
      </Menu.Item>
      <Menu.Divider />
    </Menu>
  );

  const getViewMenu = () => (
    <Menu onClick={onMenuClick}>
      <Menu.Item key="viewAlarms">{t('topology.viewAlarmList')}</Menu.Item>
      <Menu.Item key="viewMonitor">
        {t('topology.viewMonitorDetails')}
      </Menu.Item>
    </Menu>
  );

  const getMenu = () => {
    if (!isEditMode) {
      return getViewMenu();
    }
    
    if (targetType === 'edge') {
      return getEdgeEditMenu();
    }
    
    return getNodeEditMenu();
  };

  if (!visible) return null;
  
  return (
    <Dropdown
      overlay={getMenu()}
      open={visible}
      getPopupContainer={() => document.body}
    >
      <div
        style={{
          position: 'fixed',
          left: position.x,
          top: position.y,
          width: 1,
          height: 1,
        }}
      />
    </Dropdown>
  );
};

export default ContextMenu;
