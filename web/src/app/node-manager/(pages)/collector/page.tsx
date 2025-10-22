'use client';
import React, { useEffect, useState, useRef, useCallback } from 'react';
import { Menu, Input, Space, Select, Button, message, Modal } from 'antd';
import useApiClient from '@/utils/request';
import useApiCollector from '@/app/node-manager/api/collector';
import EntityList from '@/components/entity-list/index';
import { useRouter } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import type { CardItem } from '@/app/node-manager/types';
import CollectorModal from '@/app/node-manager/components/sidecar/collectorModal';
import { ModalRef } from '@/app/node-manager/types';
import PermissionWrapper from '@/components/permission';
import { COLLECTOR_LABEL } from '@/app/node-manager/constants/collector';
import { useCollectorMenuItem } from '@/app/node-manager/hooks/collector';
import { Option } from '@/types';
const { Search } = Input;
const { confirm } = Modal;

const Collector = () => {
  const router = useRouter();
  const { t } = useTranslation();
  const { isLoading } = useApiClient();
  const { getCollectorlist, deleteCollector } = useApiCollector();
  const menuItem = useCollectorMenuItem();
  const modalRef = useRef<ModalRef>(null);
  const [collectorCards, setCollectorCards] = useState<CardItem[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [search, setSearch] = useState<string>('');
  const [options, setOptions] = useState<Option[]>([]);
  const [loading, setLoading] = useState<boolean>(false);

  useEffect(() => {
    if (!isLoading) {
      fetchCollectorlist(search, selected);
    }
  }, [isLoading]);

  const navigateToCollectorDetail = (item: CardItem) => {
    router.push(`
      /node-manager/collector/detail?id=${item.id}&name=${item.name}&introduction=${item.description}&system=${item.tagList[0]}&icon=${item.icon}`);
  };

  const filterBySelected = (data: any[], selected: string[]) => {
    if (!selected?.length) return data;
    const selectedSet = new Set(selected);
    return data.filter((item) =>
      item.tagList.some((tag: string) => selectedSet.has(tag))
    );
  };

  const getCollectorLabelKey = (value: string) => {
    for (const key in COLLECTOR_LABEL) {
      if (COLLECTOR_LABEL[key].includes(value)) {
        return key;
      }
    }
  };

  const handleResult = (res: any, selected?: string[]) => {
    const optionSet = new Set<string>();
    const _options: Option[] = [];
    const filter = res.filter((item: any) => !item.controller_default_run);
    let tempdata = filter.map((item: any) => {
      const system = item.node_operating_system || item.os;
      const tagList = [system];
      const label = getCollectorLabelKey(item.name);
      if (label) tagList.push(label);
      if (system && !optionSet.has(system)) {
        optionSet.add(system);
        _options.push({ value: system, label: system });
      }
      return {
        id: item.id,
        name: item.name,
        service_type: item.service_type,
        executable_path: item.executable_path,
        execute_parameters: item.execute_parameters,
        description: item.introduction || '--',
        icon: item.icon || 'caijiqizongshu',
        tagList,
      };
    });
    tempdata = filterBySelected(tempdata, selected || []);
    setCollectorCards(tempdata);
    setOptions(_options);
  };

  const fetchCollectorlist = async (search?: string, selected?: string[]) => {
    const params = { name: search };
    try {
      setLoading(true);
      const res = await getCollectorlist(params);
      handleResult(res, selected);
    } catch (error) {
      console.log(error);
    } finally {
      setLoading(false);
    }
  };

  const openModal = (config: any) => {
    modalRef.current?.showModal({
      title: config?.title,
      type: config?.type,
      form: config?.form,
      key: config?.key,
    });
  };

  const handleSubmit = (type?: string) => {
    if (type === 'upload') return;
    fetchCollectorlist();
  };

  const handleDelete = (id: string) => {
    confirm({
      title: t(`common.delete`),
      content: t(`node-manager.packetManage.deleteInfo`),
      okText: t('common.confirm'),
      cancelText: t('common.cancel'),
      centered: true,
      onOk() {
        return new Promise(async (resolve) => {
          try {
            await deleteCollector({ id });
            message.success(t('common.successfullyDeleted'));
            fetchCollectorlist();
          } finally {
            return resolve(true);
          }
        });
      },
    });
  };

  const menuActions = useCallback(
    (data: any) => {
      return (
        <Menu onClick={(e) => e.domEvent.preventDefault()}>
          {menuItem.map((item) => {
            return (
              <Menu.Item
                key={item.key}
                className="!p-0"
                onClick={() =>
                  openModal({ ...item.config, form: data, key: 'collector' })
                }
              >
                <PermissionWrapper
                  requiredPermissions={[item.role]}
                  className="!block"
                >
                  <Button type="text" className="w-full">
                    {item.title}
                  </Button>
                </PermissionWrapper>
              </Menu.Item>
            );
          })}
          <Menu.Item className="!p-0" onClick={() => handleDelete(data.id)}>
            <PermissionWrapper
              requiredPermissions={['Delete']}
              className="!block"
            >
              <Button type="text" className="w-full">
                {t(`common.delete`)}
              </Button>
            </PermissionWrapper>
          </Menu.Item>
        </Menu>
      );
    },
    [menuItem]
  );

  const changeFilter = (selected: string[]) => {
    fetchCollectorlist(search, selected);
    setSelected(selected);
  };

  const ifOpenAddModal = () => {
    return {
      openModal: () =>
        openModal({
          title: t('node-manager.collector.addCollector'),
          type: 'add',
          form: {},
        }),
    };
  };

  const onSearch = (search: string) => {
    setSearch(search);
    fetchCollectorlist(search, selected);
  };

  return (
    <div className="h-[calc(100vh-88px)] w-full">
      {/* 卡片的渲染 */}
      <EntityList
        data={collectorCards}
        loading={loading}
        menuActions={(value) => menuActions(value)}
        filter={false}
        search={false}
        operateSection={
          <Space.Compact>
            <Select
              size="middle"
              allowClear={true}
              placeholder={`${t('common.select')}...`}
              mode="multiple"
              maxTagCount="responsive"
              className="w-[170px]"
              options={options}
              value={selected}
              onChange={changeFilter}
            />
            <Search
              size="middle"
              allowClear
              enterButton
              placeholder={`${t('common.search')}...`}
              className="w-60"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              onSearch={onSearch}
            />
          </Space.Compact>
        }
        {...ifOpenAddModal()}
        onCardClick={(item: CardItem) => navigateToCollectorDetail(item)}
      ></EntityList>
      <CollectorModal ref={modalRef} onSuccess={handleSubmit} />
    </div>
  );
};

export default Collector;
