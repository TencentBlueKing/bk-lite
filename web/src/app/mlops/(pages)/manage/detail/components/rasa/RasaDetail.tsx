import {
  Button,
  message,
  Popconfirm,
  Input
} from "antd";
import { PlusOutlined } from "@ant-design/icons";
import CustomTable from "@/components/custom-table";
import RasaModal from "./rasaModal";
import { useSearchParams } from "next/navigation";
import { useTranslation } from "@/utils/i18n";
import { useEffect, useMemo, useRef, useState } from "react";
import { ColumnItem } from "@/types";
import { ModalRef, TableData } from "@/app/mlops/types";
import useMlopsManageApi from "@/app/mlops/api/manage";
import ExampleContent from "./components/exampleContent";
const { Search } = Input;

const RasaDetail = () => {
  const { t } = useTranslation();
  const searchParams = useSearchParams();
  const modalRef = useRef<ModalRef>(null);
  const {
    getRasaIntentFileList,
    deleteRasaIntentFile,
    getRasaResponseFileList,
    deleteRasaResponseFile,
    getRasaRuleFileList,
    deleteRasaRuleFile,
    getRasaStoryFileList,
    deleteRasaStoryFile,
    getRasaEntityList,
    deleteRasaEntityFile,
    getRasaSlotList,
    deleteRasaSlotFile,
    getRasaFormList,
    deleteRasaFormFile,
    getRasaActionList,
    deleteRasaActionFile
  } = useMlopsManageApi();
  const [loading, setLoading] = useState<boolean>(false);
  const [tableData, setTableData] = useState<TableData[]>([]);
  const treeList = ['intent', 'response', 'story'];

  const btnsElements = (record: any) => (<>
    <Button type="link" className="mr-2" onClick={() => handleEdit(record)}>{t(`common.edit`)}</Button>
    <Popconfirm
      title={t(`common.delConfirm`)}
      description={t(`common.delConfirmCxt`)}
      okText={t('common.confirm')}
      cancelText={t('common.cancel')}
      onConfirm={() => handleDel(record.id)}
    >
      <Button type="link" danger>{t(`common.delete`)}</Button>
    </Popconfirm>
  </>);

  const columnsMap: Record<string, ColumnItem[]> = {
    'rule': [
      {
        title: t(`datasets.ruleName`),
        dataIndex: 'name',
        key: 'name'
      },
      {
        title: t(`datasets.intentNum`),
        dataIndex: 'intent_count',
        key: 'intent_count'
      },
      {
        title: t(`datasets.responseNum`),
        dataIndex: 'response_count',
        key: 'response_count'
      },
      {
        title: t(`datasets.formNum`),
        dataIndex: 'form_count',
        key: 'form_count'
      },
      {
        title: t(`common.action`),
        dataIndex: 'action',
        key: 'action',
        width: 180,
        render: (_, record) => btnsElements(record)
      }
    ],
    'entity': [
      {
        title: t(`datasets.entityName`),
        key: 'name',
        dataIndex: 'name'
      },
      {
        title: t(`common.type`),
        key: 'entity_type',
        dataIndex: 'entity_type'
      },
      {
        title: t(`datasets.exampleNum`),
        key: 'example_count',
        dataIndex: 'example_count',
        render: (_, record) => (
          <p className="truncate w-full">{record.example_count || '--'}</p>
        )
      },
      {
        title: t(`common.action`),
        key: 'action',
        dataIndex: 'action',
        width: 180,
        render: (_, record) => btnsElements(record)
      }
    ],
    slot: [
      {
        title: t(`datasets.slotName`),
        key: 'name',
        dataIndex: 'name'
      },
      {
        title: t(`common.type`),
        key: 'slot_type',
        dataIndex: 'slot_type'
      },
      {
        title: t(`common.action`),
        key: 'action',
        dataIndex: 'action',
        width: 180,
        render: (_, record) => btnsElements(record)
      }
    ],
    form: [
      {
        title: t(`datasets.formName`),
        key: 'name',
        dataIndex: 'name'
      },
      {
        title: t(`datasets.slotNum`),
        key: 'slot_count',
        dataIndex: 'slot_count'
      },
      {
        title: t(`common.action`),
        key: 'action',
        dataIndex: 'action',
        width: 180,
        render: (_, record) => btnsElements(record)
      }
    ],
    action: [
      {
        title: t(`common.name`),
        key: 'name',
        dataIndex: 'name'
      },
      {
        title: t(`common.action`),
        key: 'action',
        dataIndex: 'action',
        width: 180,
        render: (_, record) => btnsElements(record)
      }
    ]
  };

  const getFileMap: Record<string, any> = {
    'intent': getRasaIntentFileList,
    'response': getRasaResponseFileList,
    'rule': getRasaRuleFileList,
    'story': getRasaStoryFileList,
    'entity': getRasaEntityList,
    'slot': getRasaSlotList,
    'form': getRasaFormList,
    'action': getRasaActionList
  };

  const delFileMap: Record<string, any> = {
    'intent': deleteRasaIntentFile,
    'response': deleteRasaResponseFile,
    'rule': deleteRasaRuleFile,
    'story': deleteRasaStoryFile,
    'entity': deleteRasaEntityFile,
    'slot': deleteRasaSlotFile,
    'form': deleteRasaFormFile,
    'action': deleteRasaActionFile
  };

  const {
    folder_id,
    menu,
    // folder_name,
    // description,
    // activeTap
  } = useMemo(() => ({
    folder_id: searchParams.get('folder_id'),
    folder_name: searchParams.get('folder_name') || '',
    description: searchParams.get('description') || '',
    activeTap: searchParams.get('activeTap') || '',
    menu: searchParams.get('menu') || 'intent',
  }), [searchParams]);

  useEffect(() => {
    if (menu) {
      getTableData();
    }
  }, [menu]);

  const getTableData = async (search: string = '') => {
    setLoading(true);
    try {
      const data = await getFileMap[menu]({ name: search, dataset: folder_id });
      if (menu === 'story') {
        const _data = data?.map((item: any) => ({ ...item, icon: 'chakanshuji' }));
        setTableData(_data);
      } else {
        setTableData(data);
      }
    } catch (e) {
      console.log(e);
      message.error(t(`common.fetchFailed`));
      setTableData([]);
    } finally {
      setLoading(false);
    }
  };

  const onSearch = (value: string) => {
    getTableData(value);
  };

  const handleAdd = () => {
    modalRef.current?.showModal({ type: 'add', title: `add${menu}`, form: { dataset: folder_id } })
  };

  const handleEdit = (record: any) => {
    modalRef.current?.showModal({ type: 'edit', title: `edit${menu}`, form: { ...record } })
  };

  const handleDel = async (id: number) => {
    try {
      await delFileMap[menu](id);
      message.success(t(`common.delSuccess`));
    } catch (e) {
      console.log(e);
      message.error(t(`common.delFailed`));
    } finally {
      getTableData();
    }
  };

  return (<>
    <div className="w-full h-full relative">{
      treeList.includes(menu) ? (
        <>
          <ExampleContent
            dataset={folder_id || ''}
            menu={menu}
            loading={loading}
            data={tableData}
            handleAdd={handleAdd}
            handleDel={handleDel}
            handleEdit={handleEdit}
            onSuccess={getTableData}
          />
        </>
      ) : (<>
        <div className="flex justify-end">
          <Search
            className="w-[240px] mr-1.5"
            placeholder={t('common.search')}
            enterButton
            onSearch={onSearch}
            style={{ fontSize: 15 }}
          />
          <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>
            {t(`common.add`)}
          </Button>
        </div>
        <CustomTable rowKey="id" loading={loading} columns={columnsMap[menu]} dataSource={tableData} />
      </>)
    }</div>
    <RasaModal ref={modalRef} selectKey={menu} folder_id={folder_id as string} onSuccess={() => getTableData()} />
  </>)
};

export default RasaDetail;