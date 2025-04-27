"use client";
import React, { useState, useEffect } from "react";
import { useSearchParams } from "next/navigation";
import { Input, message, Button, Spin, Popconfirm } from "antd";
import { ColumnsType } from "antd/es/table";
import { useTranslation } from "@/utils/i18n";
import CustomTable from "@/components/custom-table";
import ChannelModal from "@/app/system-manager/components/channel/channelModal";
import { ChannelType } from "@/app/system-manager/types/channel";
import { useChannelApi } from "@/app/system-manager/api/channel";

const { Search } = Input;

const ChannelSettingsPage: React.FC = () => {
  const { t } = useTranslation();
  const searchParams = useSearchParams();

  const channelType: ChannelType = (searchParams?.get("id") || "email") as ChannelType;

  const [allTableData, setAllTableData] = useState<Array<{ key: string; name: string; description: string }>>([]);
  const [tableData, setTableData] = useState<
    Array<{ key: string; name: string; description: string }>
  >([]);
  const [searchValue, setSearchValue] = useState<string>("");
  const [currentPage, setCurrentPage] = useState<number>(1);
  const [pageSize, setPageSize] = useState<number>(10);
  const [loading, setLoading] = useState<boolean>(true);

  const [isModalVisible, setIsModalVisible] = useState<boolean>(false);
  const [modalType, setModalType] = useState<"add" | "edit">("add");
  const [channelId, setChannelId] = useState<string | null>(null);

  const { getChannelData, deleteChannel } = useChannelApi();

  const columns: ColumnsType<{ key: string; name: string; description: string }> = [
    {
      title: t("system.channel.table.name"),
      dataIndex: "name",
      width: 200,
    },
    {
      title: t("system.channel.table.description"),
      dataIndex: "description",
      width: 300,
    },
    {
      title: t("common.actions"),
      dataIndex: "key",
      width: 160,
      fixed: "right",
      render: (key: string) => (
        <>
          <Button type="link" className="mr-[8px]" onClick={() => openChannelModal("edit", key)}>
            {t("common.edit")}
          </Button>
          <Popconfirm
            title={t("common.delConfirm")}
            okText={t("common.confirm")}
            cancelText={t("common.cancel")}
            onConfirm={() => handleDeleteChannel(key)}
          >
            <Button type="link">{t("common.delete")}</Button>
          </Popconfirm>
        </>
      ),
    },
  ];

  const fetchChannels = async () => {
    setLoading(true);
    try {
      const data = await getChannelData({
        channel_type: channelType,
      });
      const channels = data.map((item: { id: string; name: string; description: string }) => ({
        key: item.id,
        name: item.name,
        description: item.description,
      }));
      setAllTableData(channels);
      setTableData(getPaginatedData(filterData(channels)));
    } catch {
      message.error(t("common.fetchFailed"));
    } finally {
      setLoading(false);
    }
  };

  const filterData = (data: Array<{ key: string; name: string; description: string }>) => {
    const lowerCaseSearch = searchValue.toLowerCase();
    return data.filter(
      (item) =>
        item.name.toLowerCase().includes(lowerCaseSearch) ||
        item.description.toLowerCase().includes(lowerCaseSearch)
    );
  };

  const getPaginatedData = (data: Array<{ key: string; name: string; description: string }>) => {
    const startIndex = (currentPage - 1) * pageSize;
    return data.slice(startIndex, startIndex + pageSize);
  };

  useEffect(() => {
    fetchChannels();
  }, [channelType]);

  useEffect(() => {
    const filteredData = filterData(allTableData);
    setTableData(getPaginatedData(filteredData));
  }, [searchValue, currentPage, pageSize, allTableData]);

  const handleDeleteChannel = async (key: string) => {
    try {
      await deleteChannel({ id: key });
      const updatedData = allTableData.filter((item) => item.key !== key);
      setAllTableData(updatedData);
      setTableData(getPaginatedData(filterData(updatedData)));
      message.success(t("common.delSuccess"));
    } catch {
      message.error(t("common.delFailed"));
    }
  };

  const openChannelModal = (type: "add" | "edit", id: string | null = null) => {
    setIsModalVisible(true);
    setModalType(type);
    if (type === "edit" && id) {
      setChannelId(id);
    } else {
      setChannelId(null);
    }
  };

  const onSuccessChannelModal = () => {
    fetchChannels();
  };

  const handleSearchChange = (value: string) => {
    setSearchValue(value);
    setCurrentPage(1);
  };

  const handlePaginationChange = (page: number, pageSize: number) => {
    setCurrentPage(page);
    setPageSize(pageSize);
  };

  return (
    <div>
      <div className="w-full mb-4 flex justify-end">
        <Search
          allowClear
          enterButton
          className="w-60 mr-2"
          placeholder={`${t("common.search")}...`}
          onSearch={handleSearchChange}
        />
        <Button type="primary" className="mr-2" onClick={() => openChannelModal("add")}>
          + {t("common.add")}
        </Button>
        <ChannelModal
          visible={isModalVisible}
          onClose={() => setIsModalVisible(false)}
          type={modalType}
          channelId={channelId}
          onSuccess={onSuccessChannelModal}
        />
      </div>
      <Spin spinning={loading}>
        <CustomTable
          scroll={{ y: "calc(100vh - 365px)" }}
          pagination={{
            pageSize,
            current: currentPage,
            total: filterData(allTableData).length,
            showSizeChanger: true,
            onChange: handlePaginationChange,
          }}
          columns={columns}
          dataSource={tableData}
        />
      </Spin>
    </div>
  );
};

export default ChannelSettingsPage;
