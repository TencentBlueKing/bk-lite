import { ModalRef } from "@/app/lab/types";
import { forwardRef, useImperativeHandle, useState, memo } from "react";
import {
  Form,
  Input,
  Select,
  InputNumber,
  Button,
  message,
  Card,
  Row,
  Col,
  Divider,
  Tooltip
} from "antd";
import { PlusOutlined, MinusCircleOutlined, QuestionCircleOutlined } from "@ant-design/icons";
import OperateModal from "@/components/operate-modal";
import useLabManage from "@/app/lab/api/mirror";
import { useTranslation } from "@/utils/i18n";

const { TextArea } = Input;
const { Option } = Select;

interface LabImageProps {
  activeTap: ("ide" | "infra");
  onSuccess?: () => void;
}

interface LabImageFormData {
  id?: number | string;
  name: string;
  version: string;
  image_type: 'ide' | 'infra';
  description?: string;
  image: string;
  default_port: number;
  default_env: Record<string, string>;
  default_command: string[];
  default_args: string[];
  expose_ports: number[];
  volume_mounts: Array<{
    container_path: string;
    host_path?: string;
    read_only?: boolean;
  }>;
}

const LabImageModal = forwardRef<ModalRef, LabImageProps>(({ activeTap, onSuccess }, ref) => {
  const { t } = useTranslation();
  const { addImage, updateImage } = useLabManage();
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [editData, setEditData] = useState<LabImageFormData | null>(null);
  const [form] = Form.useForm();

  useImperativeHandle(ref, () => ({
    showModal: (config: any) => {
      const data = config?.form as LabImageFormData;
      setEditData(data || null);
      setOpen(true);

      // 直接计算表单值,不依赖 useMemo (因为状态更新是异步的)
      if (data) {
        const formValues = {
          ...data,
          default_env_pairs: Object.entries(data.default_env || {}).map(([key, value]) => ({ key, value })),
          default_command_pairs: (data.default_command || []).map((cmd: string) => ({ command: cmd })),
          default_args_pairs: (data.default_args || []).map((arg: string) => ({ arg: arg })),
          expose_ports_pairs: (data.expose_ports || []).map((port: number) => ({ port: port })),
          volume_mount_pairs: (data.volume_mounts || []).map((mount: any) => ({
            container_path: mount.container_path,
            host_path: mount.host_path,
            read_only: mount.read_only
          }))
        };
        // 延迟表单赋值,让Modal先渲染
        requestAnimationFrame(() => {
          form.setFieldsValue(formValues);
        });
      } else {
        // 新建模式
        requestAnimationFrame(() => {
          form.resetFields();
          form.setFieldsValue({
            default_port: 8888,
            image_type: activeTap
          });
        });
      }
    }
  }));

  const handleSubmit = async () => {
    try {
      setLoading(true);
      const values = await form.validateFields();
      console.log(values);
      // return;

      // 处理环境变量格式
      const default_env: Record<string, string> = {};
      if (values.default_env_pairs) {
        values.default_env_pairs.forEach((pair: { key: string; value: string }) => {
          if (pair.key && pair.value) {
            default_env[pair.key] = pair.value;
          }
        });
      }

      // 处理启动命令格式
      const default_command: string[] = [];
      if (values.default_command_pairs) {
        values.default_command_pairs.forEach((pair: { command: string }) => {
          if (pair.command) {
            default_command.push(pair.command);
          }
        });
      }

      // 处理启动参数格式
      const default_args: string[] = [];
      if (values.default_args_pairs) {
        values.default_args_pairs.forEach((pair: { arg: string }) => {
          if (pair.arg) {
            default_args.push(pair.arg);
          }
        });
      }

      // 处理暴露端口格式
      const expose_ports: number[] = [];
      if (values.expose_ports_pairs) {
        values.expose_ports_pairs.forEach((pair: { port: number }) => {
          if (pair.port) {
            expose_ports.push(Number(pair.port));
          }
        });
      }

      // 处理卷挂载格式
      const volume_mounts = values.volume_mount_pairs || [];

      const formData: LabImageFormData = {
        name: values.name,
        version: values.version,
        image_type: editData?.image_type || activeTap,
        description: values.description,
        image: values.image || "null",
        default_port: values.default_port,
        default_env,
        default_command,
        default_args,
        expose_ports,
        volume_mounts
      };

      console.log(formData);

      if (editData) {
        // 编辑模式
        await updateImage(editData?.id as string, formData);
        message.success(t(`lab.manage.imageUpdatedSuccess`));
      } else {
        // 新建模式
        await addImage(formData);
        message.success(t(`lab.manage.imageCreatedSuccess`));
      }

      setOpen(false);
      form.resetFields();
      setEditData(null);
      onSuccess?.();

    } catch (error) {
      console.error(t(`common.valFailed`), error);
    } finally {
      setLoading(false);
    }
  };

  const handleCancel = () => {
    setOpen(false);
    form.resetFields();
    setEditData(null);
  };

  return (
    <OperateModal
      title={editData ? t(`lab.manage.editImage`) : t(`lab.manage.updateImage`)}
      open={open}
      onCancel={handleCancel}
      // width={800}
      footer={[
        <Button key="cancel" onClick={handleCancel}>
          取消
        </Button>,
        <Button key="submit" type="primary" loading={loading} onClick={handleSubmit}>
          确认
        </Button>
      ]}
      destroyOnClose
    >
      <Form
        form={form}
        layout="vertical"
        initialValues={{
          default_port: 8888,
          image_type: 'ide'
        }}
      >
        <Row gutter={16}>
          <Col span={12}>
            <Form.Item
              name="name"
              label={t(`lab.manage.imageName`)}
              rules={[
                { required: true, message: t(`lab.manage.nameMsg`) },
                { max: 100, message: t(`lab.manage.nameCharMsg`) }
              ]}
            >
              <Input placeholder={t(`lab.manage.nameMsg`)} />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item
              name="version"
              label={t(`lab.manage.imageVersion`)}
              rules={[
                { required: true, message: t(`lab.manage.versionMsg`) },
                { max: 50, message: t(`lab.manage.versionCharMsg`) }
              ]}
            >
              <Input placeholder={t(`lab.manage.versionExample`)} />
            </Form.Item>
          </Col>
        </Row>

        {/* <Row gutter={16}>
          <Col span={12}>
            <Form.Item
              name="image_type"
              label={t(`lab.manage.imageType`)}
              rules={[{ required: true, message: t(`lab.manage.imageType`) }]}
            >
              <Select placeholder={t(`lab.manage.imageType`)}>
                <Option value="ide">{t(`lab.manage.ide`)}</Option>
                <Option value="infra">{t(`lab.manage.infra`)}</Option>
              </Select>
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item
              name="default_port"
              label={t(`lab.manage.defaultPort`)}
              rules={[{ required: true, message: t(`lab.manage.portMsg`) }]}
            >
              <InputNumber
                min={1}
                max={65535}
                placeholder="8888"
                style={{ width: '100%' }}
              />
            </Form.Item>
          </Col>
        </Row> */}

        {/* <Form.Item
          name="image"
          label={t(`lab.manage.imageUrl`)}
          // rules={[
          //   { required: true, message: t(`lab.manage.urlMsg`) },
          //   { max: 200, message: t(`lab.manage.urlCharMsg`) }
          // ]}
        >
          <Input placeholder={t(`lab.manage.urlExample`)} />
        </Form.Item> */}

        <Form.Item
          name="description"
          label={t(`lab.manage.description`)}
        >
          <TextArea
            rows={3}
            placeholder={t(`lab.manage.descriptionMsg`)}
            maxLength={500}
            showCount
          />
        </Form.Item>

        <Divider orientation="left" orientationMargin={0}>{t(`lab.manage.config`)}</Divider>

        {/* 默认环境变量 */}
        <Card title={t(`lab.manage.configVar`)} size="small" style={{ marginBottom: 16 }}>
          <EnvVariablesSection t={t} />
        </Card>

        {/* 启动命令 */}
        <Card
          title={
            <span>
              {t(`lab.manage.defaultCommand`)}
              <Tooltip title={t(`lab.manage.commandContent`)}>
                <QuestionCircleOutlined style={{ marginLeft: 6, color: '#8c8c8c', fontSize: '14px' }} />
              </Tooltip>
            </span>
          }
          size="small"
          style={{ marginBottom: 16 }}
        >
          <CommandSection t={t} />
        </Card>

        {/* 启动参数 */}
        <Card
          title={
            <span>
              {t(`lab.manage.defaultParams`)}
              <Tooltip title={t(`lab.manage.paramsContent`)}>
                <QuestionCircleOutlined style={{ marginLeft: 6, color: '#8c8c8c', fontSize: '14px' }} />
              </Tooltip>
            </span>
          }
          size="small"
          style={{ marginBottom: 16 }}
        >
          <ArgsSection t={t} />
        </Card>

        {/* 暴露端口 */}
        <Card
          title={
            <span>
              {t(`lab.manage.exposePort`)}
              <Tooltip title={t(`lab.manage.portContent`)}>
                <QuestionCircleOutlined style={{ marginLeft: 6, color: '#8c8c8c', fontSize: '14px' }} />
              </Tooltip>
            </span>
          }
          size="small"
          style={{ marginBottom: 16 }}
        >
          <PortsSection t={t} />
        </Card>

        {/* 卷挂载配置 */}
        <Card title={t(`lab.manage.volumeContent`)} size="small" className="mb-2">
          <VolumesSection t={t} />
        </Card>
      </Form>
    </OperateModal>
  );
});

// 使用 memo 优化各个表单区块组件
const EnvVariablesSection = memo(({ t }: { t: any }) => (
  <Form.List name="default_env_pairs">
    {(fields, { add, remove }) => (
      <>
        {fields.map(({ key, name, ...restField }) => (
          <div key={key} style={{ display: 'flex', gap: '8px', marginBottom: '8px', alignItems: 'flex-start' }}>
            <Form.Item
              style={{ flex: '0 0 40%', marginBottom: 0 }}
              name={[name, 'key']}
              rules={[{ required: true, message: t(`lab.manage.varNameMsg`) }]}
              {...restField}
            >
              <Input placeholder={t(`lab.manage.varName`)} />
            </Form.Item>
            <Form.Item
              style={{ flex: '1', marginBottom: 0 }}
              name={[name, 'value']}
              rules={[{ required: true, message: t(`lab.manage.varValueMsg`) }]}
              {...restField}
            >
              <Input placeholder={t(`lab.manage.varValue`)} />
            </Form.Item>
            <MinusCircleOutlined
              style={{ fontSize: '14px', marginTop: '9px', cursor: 'pointer' }}
              onClick={() => remove(name)}
            />
          </div>
        ))}
        <Button
          type="dashed"
          onClick={() => add()}
          block
          icon={<PlusOutlined />}
          style={{ marginTop: '8px' }}
        >
          {t(`lab.manage.addConfigVar`)}
        </Button>
      </>
    )}
  </Form.List>
));
EnvVariablesSection.displayName = 'EnvVariablesSection';

const CommandSection = memo(({ t }: { t: any }) => (
  <Form.List name="default_command_pairs">
    {(fields, { add, remove }) => (
      <>
        {fields.map(({ key, name, ...restField }) => (
          <div key={key} style={{ display: 'flex', gap: '8px', marginBottom: '8px', alignItems: 'flex-start' }}>
            <Form.Item
              style={{ flex: '1', marginBottom: 0 }}
              name={[name, 'command']}
              rules={[{ required: true, message: t(`lab.manage.commandMsg`) }]}
              {...restField}
            >
              <Input placeholder={t(`lab.manage.commandExample`)} />
            </Form.Item>
            <MinusCircleOutlined
              style={{ fontSize: '14px', marginTop: '9px', cursor: 'pointer' }}
              onClick={() => remove(name)}
            />
          </div>
        ))}
        <Button
          type="dashed"
          onClick={() => add()}
          block
          icon={<PlusOutlined />}
          size="small"
          style={{ marginTop: '8px' }}
        >
          {t(`lab.manage.addCommand`)}
        </Button>
      </>
    )}
  </Form.List>
));
CommandSection.displayName = 'CommandSection';

const ArgsSection = memo(({ t }: { t: any }) => (
  <Form.List name="default_args_pairs">
    {(fields, { add, remove }) => (
      <>
        {fields.map(({ key, name, ...restField }) => (
          <div key={key} style={{ display: 'flex', gap: '8px', marginBottom: '8px', alignItems: 'flex-start' }}>
            <Form.Item
              style={{ flex: '1', marginBottom: 0 }}
              name={[name, 'arg']}
              rules={[{ required: true, message: t(`lab.manage.paramsMsg`) }]}
              {...restField}
            >
              <Input placeholder={t(`lab.manage.paramsExample`)} />
            </Form.Item>
            <MinusCircleOutlined
              style={{ fontSize: '14px', marginTop: '9px', cursor: 'pointer' }}
              onClick={() => remove(name)}
            />
          </div>
        ))}
        <Button
          type="dashed"
          onClick={() => add()}
          block
          icon={<PlusOutlined />}
          size="small"
          style={{ marginTop: '8px' }}
        >
          {t(`lab.manage.addParams`)}
        </Button>
      </>
    )}
  </Form.List>
));
ArgsSection.displayName = 'ArgsSection';

const PortsSection = memo(({ t }: { t: any }) => (
  <Form.List name="expose_ports_pairs">
    {(fields, { add, remove }) => (
      <>
        {fields.map(({ key, name, ...restField }) => (
          <div key={key} style={{ display: 'flex', gap: '8px', marginBottom: '8px', alignItems: 'flex-start' }}>
            <Form.Item
              style={{ flex: '1', marginBottom: 0 }}
              name={[name, 'port']}
              rules={[
                { required: true, message: t(`lab.manage.portMsg`) },
                { pattern: /^[1-9]\d{0,4}$/, message: t(`lab.manage.portCharMsg`) }
              ]}
              {...restField}
            >
              <InputNumber
                placeholder={t(`lab.manage.portExample`)}
                min={1}
                max={65535}
                style={{ width: '100%' }}
              />
            </Form.Item>
            <MinusCircleOutlined
              style={{ fontSize: '14px', marginTop: '9px', cursor: 'pointer' }}
              onClick={() => remove(name)}
            />
          </div>
        ))}
        <Button
          type="dashed"
          onClick={() => add()}
          block
          icon={<PlusOutlined />}
          style={{ marginTop: '8px' }}
        >
          {t(`lab.manage.addPort`)}
        </Button>
      </>
    )}
  </Form.List>
));
PortsSection.displayName = 'PortsSection';

const VolumesSection = memo(({ t }: { t: any }) => (
  <Form.List name="volume_mount_pairs">
    {(fields, { add, remove }) => (
      <>
        {fields.map(({ key, name, ...restField }) => (
          <div key={key} style={{ display: 'flex', gap: '8px', marginBottom: '8px', alignItems: 'flex-start' }}>
            <Form.Item
              style={{ flex: '1', marginBottom: 0 }}
              name={[name, 'container_path']}
              rules={[{ required: true, message: t(`lab.manage.containterPath`) }]}
              {...restField}
            >
              <Input placeholder={t(`lab.manage.containterMsg`)} />
            </Form.Item>
            <Form.Item
              style={{ flex: '1', marginBottom: 0 }}
              name={[name, 'host_path']}
              {...restField}
            >
              <Input placeholder={t(`lab.manage.hostPathMsg`)} />
            </Form.Item>
            <Form.Item
              style={{ flex: '0 0 120px', marginBottom: 0 }}
              name={[name, 'read_only']}
              {...restField}
            >
              <Select placeholder="读写权限" style={{ width: '100%' }}>
                <Option value={false}>{t(`lab.manage.write`)}</Option>
                <Option value={true}>{t(`lab.manage.read`)}</Option>
              </Select>
            </Form.Item>
            <MinusCircleOutlined
              style={{ fontSize: '14px', marginTop: '9px', cursor: 'pointer' }}
              onClick={() => remove(name)}
            />
          </div>
        ))}
        <Button
          type="dashed"
          onClick={() => add()}
          block
          icon={<PlusOutlined />}
          style={{ marginTop: '8px' }}
        >
          {t(`lab.manage.addVolume`)}
        </Button>
      </>
    )}
  </Form.List>
));
VolumesSection.displayName = 'VolumesSection';

LabImageModal.displayName = 'LabImageModal';
export default LabImageModal;