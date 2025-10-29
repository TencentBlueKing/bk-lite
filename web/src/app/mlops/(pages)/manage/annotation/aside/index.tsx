'use client';
import React, { useMemo, useState } from 'react';
import { useTranslation } from '@/utils/i18n';
import {
  useSearchParams,
  useRouter
} from 'next/navigation';
import { Spin, Modal, Menu, Button } from 'antd';
import Icon from '@/components/icon';
import { ArrowLeftOutlined, MenuUnfoldOutlined, MenuFoldOutlined } from '@ant-design/icons';
import {
  AsideProps
} from '@/app/mlops/types/manage'
import sideMenuStyle from './index.module.scss';
import { MenuItemType } from 'antd/es/menu/interface';
const { confirm } = Modal;

const Aside = ({
  menuItems,
  loading,
  isChange,
  onChange,
  changeFlag }: AsideProps) => {
  const { t } = useTranslation();
  const searchParams = useSearchParams();
  const file_id = searchParams.get('id') || '';
  const folder_id = searchParams.get('folder_id') || '';
  const folder_name = searchParams.get('folder_name') || '';
  const description = searchParams.get('description');
  const activeTap = searchParams.get('activeTap');
  const router = useRouter();
  const [collapsed, setCollapsed] = useState(false);

  const selectKey = useMemo(() => {
    return [file_id];
  }, [searchParams])

  const toggleCollapsed = () => {
    setCollapsed(!collapsed);
  };

  const buildUrlWithParams = (id: number) => {
    return `?id=${id}&folder_id=${folder_id}&folder_name=${folder_name}&description=${description}&activeTap=${activeTap}`;
  };

  const renderMenuItems: () => MenuItemType[] = () => {
    return menuItems.map((item: any) => {
      return {
        key: item.id?.toString(),
        label: item.name,
        title: item.name,
        icon: <Icon type={'yingpan'} className="!text-xl pr-1.5" />
      }
    })
  };

  const goBack = (e: any) => {
    e.preventDefault();
    if (isChange) {
      return confirm({
        title: t('datasets.leave'),
        content: t('datasets.leaveContent'),
        okText: t('common.confirm'),
        cancelText: t('common.cancel'),
        centered: true,
        onOk() {
          return new Promise(async (resolve) => {
            resolve(true);
            onChange(false);
            router.replace(`/mlops/manage/detail?folder_id=${folder_id}&folder_name=${folder_name}&description=${description}&activeTap=${activeTap}`);
          })
        }
      })
    }

    router.replace(`/mlops/manage/detail?folder_id=${folder_id}&folder_name=${folder_name}&description=${description}&activeTap=${activeTap}`);
  };

  const showConfirm = (id: number) => {
    confirm({
      title: t('datasets.leave'),
      content: t('datasets.leaveContent'),
      okText: t('common.confirm'),
      cancelText: t('common.cancel'),
      centered: true,
      onOk() {
        return new Promise(async (resolve) => {
          resolve(true);
          onChange(false);
          changeFlag(true);
          router.push(buildUrlWithParams(id));
        })
      }
    })
  };

  const onMenuItemClick = async (item: any) => {
    if (isChange) {
      return showConfirm(item.id)
    }
    changeFlag(true);
    router.push(buildUrlWithParams(item.id));
  };

  // 动态计算容器宽度和样式
  const asideStyle: React.CSSProperties = {
    width: collapsed ? '80px' : '200px',
    transition: 'width 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
    overflow: 'hidden'
  };

  const navStyle: React.CSSProperties = {
    transition: 'width 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
    overflow: 'hidden'
  };

  const menuStyle: React.CSSProperties = {
    width: collapsed ? 80 : 190,
    maxWidth: collapsed ? 80 : 190,
    transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
    overflow: 'hidden',
    backgroundColor: 'transparent',
    border: 0
  };

  return (
    <>
      <aside
        className={`relative mr-4 flex flex-shrink-0 flex-col h-full ${sideMenuStyle.sideMenu} font-sans rounded-md`}
        style={asideStyle}
      >
        <div className='flex flex-row relative justify-center items-center h-16 overflow-hidden'>
          <button
            className="absolute z-10 top-4 left-3 flex items-center content-center py-2 px-4 rounded-md text-sm font-medium text-gray-600 cursor-pointer hover:text-blue-600"
            onClick={goBack}
            style={{
              transition: 'all 0.2s ease',
              zIndex: 20
            }}
          >
            <ArrowLeftOutlined className="mr-2" />
          </button>
          {!collapsed && <span>文件列表</span> }
        </div>
        <nav
          className={`flex-1 relative rounded-md ${sideMenuStyle.nav}`}
          style={navStyle}
        >
          {loading ? (
            <div className="min-h-[300px] flex items-center justify-center">
              <Spin spinning={loading}></Spin>
            </div>
          ) : (
            <>
              <Menu
                items={renderMenuItems()}
                inlineCollapsed={collapsed}
                selectedKeys={selectKey}
                style={menuStyle}
                mode='inline'
                onClick={({ key, domEvent }) => {
                  domEvent.preventDefault();
                  const item = menuItems.find((item: any) => item.id.toString() === key);
                  if (item && item.id.toString() !== file_id) {
                    onMenuItemClick(item);
                  }
                }}
              />
              <Button
                color="default" variant="link"
                onClick={toggleCollapsed}
                style={{
                  marginBottom: 16,
                  transition: 'all 0.3s ease',
                  width: collapsed ? '40px' : 'auto',
                }}
                className='absolute left-3 bottom-2'
              >
                {collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
              </Button>
            </>
          )}
        </nav>
      </aside>
    </>
  )
};

export default Aside;