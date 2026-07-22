import type { Meta, StoryObj } from '@storybook/nextjs';
import AuthSecretField from '@/components/auth-secret-field';
import CodeEditor from '@/components/code-editor';
import CodeSnippet from '@/components/code-snippet';
import NodeManagerCollectorPackageModal from '@/app/node-manager/components/node-manager-collector-package-modal';
import NodeManagerOperatingSystemBadge from '@/app/node-manager/components/node-manager-operating-system-badge';
import NodeManagerRuntimeStatusBadge from '@/app/node-manager/components/node-manager-runtime-status-badge';
import SectionHeader from '@/components/section-header';
import SummaryDetailLayoutShell from '@/components/summary-detail-layout-shell';
import TopSection from '@/components/top-section';
import {
  createPasswordSecretFieldProps,
  createPrivateKeySecretFieldProps,
} from '@/components/auth-secret-field/presets';
import {
  createNodeManagerAuthCredentialFieldConfig,
  createNodeManagerAuthTypeFieldConfig,
  createNodeManagerAuthTypeOptions,
} from '@/app/node-manager/presets/auth-field-configs';
import {
  LinuxOperationGuidanceSection,
  WindowsOperationGuidanceSection,
} from '@/app/node-manager/(pages)/cloudregion/node/controllerInstall/installing/operationGuidanceSections';
import type { NodeManagerCollectorPackageModalRef } from '@/app/node-manager/components/node-manager-collector-package-modal/types';
import React, { useEffect, useMemo, useRef, useState } from 'react';

const nodeManagerStoryMessages = {
  'common.inputMsg': 'Input value',
  'common.inputTip': 'Input here',
  'common.selectTip': 'Select an option',
  'node-manager.cloudregion.node.authType': 'Auth type',
  'node-manager.cloudregion.node.password': 'Password',
  'node-manager.cloudregion.node.privateKey': 'Private key',
  'node-manager.cloudregion.node.loginPassword': 'Login credential',
  'node-manager.cloudregion.node.excelLoginPassword': 'Login password',
};

const nodeManagerStoryT = (key: string) =>
  nodeManagerStoryMessages[key as keyof typeof nodeManagerStoryMessages] ?? key;

const nodeManagerOperationGuidanceSharedArgs = {
  loading: false,
  downloadLoading: false,
  copying: false,
  installerSession:
    'powershell.exe -ExecutionPolicy Bypass -File .\\install-controller.ps1 -SessionToken "bk-session-20260702"',
  installerMetadata: {
    version: '1.3.2',
    os: 'windows',
    cpu_architecture: 'x86_64',
    filename: 'bk_controller_installer.exe',
    download_url: 'https://bk-lite.example.com/downloads/bk_controller_installer.exe',
    alias_object_key: 'controller/latest/windows',
    object_key: 'controller/1.3.2/windows/bk_controller_installer.exe',
  },
  installerManifest: {
    default_version: '1.3.2',
    artifacts: {
      windows: {
        x86_64: {
          version: '1.3.2',
          os: 'windows',
          cpu_architecture: 'x86_64',
          filename: 'bk_controller_installer.exe',
          download_url: 'https://bk-lite.example.com/downloads/bk_controller_installer.exe',
          alias_object_key: 'controller/latest/windows',
          object_key: 'controller/1.3.2/windows/bk_controller_installer.exe',
        },
      },
    },
  },
  onDownload: async () => undefined,
  onCopy: () => undefined,
  onCopyDebugValue: () => undefined,
};

const NodeManagerAuthWorkflowPreview = () => {
  const [authType, setAuthType] = useState<'password' | 'private_key'>(
    'password'
  );
  const [password, setPassword] = useState('bk-lite-password');
  const [fileName, setFileName] = useState<string | undefined>(
    'controller-access.pem'
  );

  const authOptions = useMemo(
    () => createNodeManagerAuthTypeOptions(nodeManagerStoryT),
    []
  );
  const installAuthTypeField = useMemo(
    () =>
      createNodeManagerAuthTypeFieldConfig(nodeManagerStoryT, {
        defaultValue: 'password',
        placeholder: nodeManagerStoryT('common.selectTip'),
        useWidgetProps: true,
      }),
    []
  );
  const installCredentialField = useMemo(
    () =>
      createNodeManagerAuthCredentialFieldConfig(nodeManagerStoryT, {
        excelLabel: nodeManagerStoryT(
          'node-manager.cloudregion.node.excelLoginPassword'
        ),
        placeholder: nodeManagerStoryT('common.inputTip'),
        encrypted: true,
      }),
    []
  );
  const uninstallCredentialField = useMemo(
    () =>
      createNodeManagerAuthCredentialFieldConfig(nodeManagerStoryT, {
        placeholder: nodeManagerStoryT('common.inputMsg'),
      }),
    []
  );

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,0.92fr)_minmax(0,1.08fr)]">
      <div className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
        <SectionHeader spacing="flush" title="Shared auth semantics" titleClassName="text-sm font-medium" />
        <div className="flex flex-wrap gap-2">
          {authOptions.map((option) => (
            <button
              key={String(option.value)}
              type="button"
              className={`rounded-md border px-3 py-1.5 text-sm transition-colors ${
                authType === option.value
                  ? 'border-[var(--color-primary)] bg-[var(--color-bg-active)] text-[var(--color-primary)]'
                  : 'border-[var(--color-border)] bg-[var(--color-bg-1)] text-[var(--color-text-2)]'
              }`}
              onClick={() =>
                setAuthType(option.value as 'password' | 'private_key')
              }
            >
              {option.label}
            </button>
          ))}
        </div>
        <div className="text-xs text-[var(--color-text-3)]">
          One governed option set now drives controller install, uninstall, and retry-install flows.
        </div>
        <AuthSecretField
          {...(authType === 'private_key'
            ? createPrivateKeySecretFieldProps({
              fileName,
              onPrivateKeyClear: () => setFileName(undefined),
              onPrivateKeyLoaded: (_, nextFileName) =>
                setFileName(nextFileName),
            })
            : createPasswordSecretFieldProps({
              passwordValue: password,
              passwordPlaceholder: nodeManagerStoryT('common.inputTip'),
              onPasswordChange: setPassword,
            }))}
        />
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
          <SectionHeader spacing="compact" title="Remote install field contract" titleClassName="text-sm font-medium" />
          <CodeSnippet
            value={JSON.stringify(
              [installAuthTypeField, installCredentialField],
              null,
              2
            )}
            tone="inverse"
            copyable
            maxHeight={260}
          />
        </div>

        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
          <SectionHeader spacing="compact" title="Uninstall and retry contract" titleClassName="text-sm font-medium" />
          <CodeSnippet
            value={JSON.stringify(uninstallCredentialField, null, 2)}
            tone="inverse"
            copyable
            maxHeight={260}
          />
        </div>
      </div>
    </div>
  );
};

const NodeManagerCollectorPackageStoryHarness: React.FC<{
  type: 'add' | 'edit' | 'upload';
}> = ({ type }) => {
  const ref = useRef<NodeManagerCollectorPackageModalRef>(null);

  useEffect(() => {
    ref.current?.showModal({
      type,
      title:
        type === 'add'
          ? 'Add Component'
          : type === 'edit'
            ? 'Edit Component'
            : 'Upload Package',
      key: 'collector',
      appTag: 'collector',
      form: {
        id: 'disk-collector-linux',
        name: 'Disk Collector',
        original_name: 'disk-collector',
        original_introduction: 'Collect disk usage metrics from Linux nodes.',
        description: 'Collect disk usage metrics from Linux nodes.',
        service_type: 'exec',
        system: 'linux',
        os: 'linux',
        cpu_architecture: 'x86_64',
        executable_path: '/opt/bk-lite/collector',
        execute_parameters: '--foreground',
      },
    });
  }, [type]);

  return (
    <NodeManagerCollectorPackageModal
      ref={ref}
      onSuccess={() => undefined}
      addCollectorAction={async () => undefined}
      editCollectorAction={async () => undefined}
      uploadPackageAction={async () => undefined}
      getControllerListAction={async () => [
        { node_operating_system: 'linux', cpu_architecture: 'x86_64' },
        { node_operating_system: 'linux', cpu_architecture: 'arm64' },
        { node_operating_system: 'windows', cpu_architecture: 'x86_64' },
      ]}
    />
  );
};

const FamilyOverview = () => {
  return (
    <div className="space-y-6">
      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Detail workspace shell"
          titleClassName="text-sm font-semibold"
          description="Shared detail layouts keep controller and collector pages aligned around the same summary header, back navigation, and inner content frame."
        />

        <SummaryDetailLayoutShell
          topSection={(
            <TopSection
              title="Package Management"
              content="Keep controller and collector detail routes aligned around one shared summary layout contract."
            />
          )}
          summary={{
            title: 'Collector Agent',
            iconType: 'caijiqizongshu',
            layout: 'vertical',
            align: 'center',
          }}
          onBackButtonClick={() => undefined}
        >
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-6 text-sm text-[var(--color-text-2)]">
            Shared package details, install steps, or runtime diagnostics render inside this stable business shell.
          </div>
        </SummaryDetailLayoutShell>
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Node identity and runtime semantics"
          titleClassName="text-sm font-semibold"
          description="Shared badges express operating-system identity and operation status consistently across node lists, collector details, and install progress surfaces."
        />

        <div className="grid gap-4 lg:grid-cols-[minmax(0,280px)_minmax(0,1fr)]">
          <div className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="flush" title="Operating system language" titleClassName="text-sm font-medium" />
            <div className="flex flex-wrap items-center gap-3">
              <NodeManagerOperatingSystemBadge
                operatingSystem="linux"
                label="Linux"
                variant="tag"
                color="blue"
                bordered={false}
                className="flex w-fit items-center gap-1"
                iconClassName="text-[16px]"
              />
              <NodeManagerOperatingSystemBadge
                operatingSystem="windows"
                label="Windows"
                variant="tag"
                color="gold"
                bordered={false}
                className="flex w-fit items-center gap-1"
                iconClassName="text-[16px]"
              />
              <NodeManagerOperatingSystemBadge
                operatingSystem="linux"
                variant="icon"
                tooltip="System: Linux"
                className="flex items-center"
                iconStyle={{ fontSize: '24px', cursor: 'pointer' }}
              />
            </div>
          </div>

          <div className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="flush" title="Runtime and operation statuses" titleClassName="text-sm font-medium" />
            <div className="flex flex-wrap items-center gap-3">
              <NodeManagerRuntimeStatusBadge status={0} />
              <NodeManagerRuntimeStatusBadge status={1} />
              <NodeManagerRuntimeStatusBadge status={2} />
              <NodeManagerRuntimeStatusBadge status={3} />
              <NodeManagerRuntimeStatusBadge status={10} count={1} />
              <NodeManagerRuntimeStatusBadge status={12} />
              <NodeManagerRuntimeStatusBadge status={0} count={5} />
              <NodeManagerRuntimeStatusBadge status={2} count={2} />
              <NodeManagerRuntimeStatusBadge status="running" label="Running" />
              <NodeManagerRuntimeStatusBadge status="success" label="Completed" />
              <NodeManagerRuntimeStatusBadge status="timeout" label="Timeout" />
              <NodeManagerRuntimeStatusBadge status="waiting" label="Waiting Manual" />
              <NodeManagerRuntimeStatusBadge
                status="timeout"
                tone="error"
                label="Timeout (Error Tone)"
              />
            </div>
          </div>
        </div>
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Collector package workflow"
          titleClassName="text-sm font-semibold"
          description="Collector and controller package-management surfaces now share one governed package modal for add, edit, and upload flows instead of keeping the package editor buried in one sidecar page subtree."
        />

        <div className="grid gap-4 xl:grid-cols-3">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Add collector" titleClassName="text-sm font-semibold" />
            <NodeManagerCollectorPackageStoryHarness type="add" />
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Edit collector" titleClassName="text-sm font-semibold" />
            <NodeManagerCollectorPackageStoryHarness type="edit" />
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Upload package" titleClassName="text-sm font-semibold" />
            <NodeManagerCollectorPackageStoryHarness type="upload" />
          </div>
        </div>
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Authentication workflow contract"
          titleClassName="text-sm font-semibold"
          description="Controller install, uninstall, and retry flows now share one business auth preset layer on top of the framework-level secret field, keeping option labels, field configs, and secret-mode behavior aligned."
        />

        <NodeManagerAuthWorkflowPreview />
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Generated deployment surfaces"
          titleClassName="text-sm font-semibold"
          description="Node-manager generated scripts and installer sessions now use the same governed read-only snippet surface as other operator copy-and-run flows instead of keeping page-local editor treatments for static output."
        />

        <div className="grid gap-4 lg:grid-cols-2">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Deployment script" titleClassName="text-sm font-medium" />
            <CodeSnippet
              value={`python install_proxy.py \\
  --cloud-region-id 2001 \\
  --proxy-address 10.0.0.18:8080 \\
  --token bk_nm_xxx`}
              tone="inverse"
              copyable
              maxHeight={250}
            />
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Installer session" titleClassName="text-sm font-medium" />
            <CodeSnippet
              value={`powershell.exe -ExecutionPolicy Bypass -File .\\install-controller.ps1 \\
  -SessionToken "bk-session-20260701" \\
  -ControllerPackage ".\\bk-lite-controller.zip"`}
              tone="inverse"
              copyable
              maxHeight={120}
            />
          </div>
        </div>
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Controller install operation guidance"
          titleClassName="text-sm font-semibold"
          description="Windows and Linux guidance are stable branches of the same controller-install workflow, so Storybook governs them inside the node-manager family instead of splitting them into another root."
        />

        <div className="grid gap-4 xl:grid-cols-2">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Windows flow" titleClassName="text-sm font-medium" />
            <WindowsOperationGuidanceSection
              {...nodeManagerOperationGuidanceSharedArgs}
            />
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Linux flow" titleClassName="text-sm font-medium" />
            <LinuxOperationGuidanceSection
              {...nodeManagerOperationGuidanceSharedArgs}
              installerSession="curl -fsSL https://bk-lite.example.com/install-controller.sh | bash -s -- --token bk_nm_xxx"
              installerMetadata={{
                ...nodeManagerOperationGuidanceSharedArgs.installerMetadata,
                os: 'linux',
                cpu_architecture: 'x86_64',
                filename: 'bk_controller_installer.tar.gz',
                download_url:
                  'https://bk-lite.example.com/downloads/bk_controller_installer.tar.gz',
                alias_object_key: 'controller/latest/linux',
                object_key: 'controller/1.3.2/linux/bk_controller_installer.tar.gz',
              }}
            />
          </div>
        </div>
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Parameterized config editor"
          titleClassName="text-sm font-semibold"
          description="Node-manager still preserves `CodeEditor` for real configuration authoring surfaces, where operators edit template content while cross-checking variable references and helper metadata."
        />

        <div className="grid gap-4 lg:grid-cols-[400px_minmax(0,1fr)]">
          <CodeEditor
            mode="python"
            theme="monokai"
            name="node-manager-config-template-editor"
            width="100%"
            height="250px"
            value={`collector:
  endpoint: ${'{PROXY_ADDRESS}'}
  token: ${'{ACCESS_TOKEN}'}
  interval: 30`}
            headerOptions={{ copy: true, fullscreen: true }}
          />

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4 text-[13px] text-[var(--color-text-2)]">
            <SectionHeader spacing="compact" title="Variable reference help" titleClassName="text-sm font-medium" />
            <div className="space-y-2">
              <div><strong>PROXY_ADDRESS</strong>: Proxy service endpoint</div>
              <div><strong>ACCESS_TOKEN</strong>: Generated access token</div>
              <div><strong>interval</strong>: Collector execution interval in seconds</div>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
};

const meta = {
  title: 'Business/NodeManager/FamilyOverview',
  component: FamilyOverview,
  decorators: [
    (Story) => (
      <div style={{ maxWidth: 1120, padding: 24, background: 'var(--color-bg-2)' }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof FamilyOverview>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Overview: Story = {};
