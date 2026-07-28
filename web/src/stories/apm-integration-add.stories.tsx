import type { Meta, StoryObj } from '@storybook/nextjs';
import {
  IntegrationCatalog,
  IntegrationDetail,
  JavaConfigPanel,
  NodeConfigPanel,
  OtcConfigPanel,
  EbpfConfigPanel,
  K8sConfigPanel,
  PythonConfigPanel,
  DotnetConfigPanel,
  GoConfigPanel,
  OTC_TRACES_ENDPOINTS,
} from './apm-integration-pages.components';

const meta = {
  title: 'APM/Integration Pages/添加接入',
  parameters: {
    layout: 'fullscreen',
  },
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

export const IntegrationCatalogStory: Story = {
  name: '接入方式总览',
  render: () => <IntegrationCatalog />,
};

export const IntegrationDetailJava: Story = {
  name: 'Java 接入',
  render: () => <IntegrationDetail title="Java 接入" configPanel={(ep) => <JavaConfigPanel endpoint={ep} />} />,
};

export const IntegrationDetailNode: Story = {
  name: 'Node.js 接入',
  render: () => <IntegrationDetail title="Node.js 接入" configPanel={(ep) => <NodeConfigPanel endpoint={ep} />} />,
};

export const IntegrationDetailPython: Story = {
  name: 'Python 接入',
  render: () => <IntegrationDetail title="Python 接入" configPanel={(ep) => <PythonConfigPanel endpoint={ep} />} />,
};

export const IntegrationDetailDotnet: Story = {
  name: '.NET 接入',
  render: () => <IntegrationDetail title=".NET 接入" configPanel={(ep) => <DotnetConfigPanel endpoint={ep} />} />,
};

export const IntegrationDetailGo: Story = {
  name: 'Go 接入',
  render: () => <IntegrationDetail title="Go 接入" configPanel={(ep) => <GoConfigPanel endpoint={ep} />} />,
};

export const IntegrationDetailOtc: Story = {
  name: 'OTel Collector 接入',
  render: () => (
    <IntegrationDetail
      title="OTel Collector 接入"
      endpointMap={OTC_TRACES_ENDPOINTS}
      configPanel={(ep) => <OtcConfigPanel endpoint={ep} />}
    />
  ),
};

export const IntegrationDetailEbpf: Story = {
  name: 'eBPF 接入',
  render: () => <IntegrationDetail title="eBPF 自动注入(OBI)" configPanel={() => <EbpfConfigPanel />} />,
};

export const IntegrationDetailK8s: Story = {
  name: 'K8s 接入',
  render: () => <IntegrationDetail title="Kubernetes 注册注入" configPanel={() => <K8sConfigPanel />} />,
};
