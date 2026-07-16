import type { Meta, StoryObj } from '@storybook/react';
import { Button, Form, Input, Segmented, Tag } from 'antd';
import CompactEmptyState from '@/components/compact-empty-state';
import ContentDrawer from '@/components/content-drawer';
import ContentFormDrawer from '@/components/content-form-drawer';
import IntegrationAccessComplete from '@/components/integration-access-complete';
import K8sCollectorInstall from '@/components/k8s-collector-install';
import {
  createCmdbK8sAccessCompletePreset,
  createMonitorFlowAccessCompletePreset,
} from '@/components/integration-access-complete/presets';
import OperateDrawer from '@/components/operate-drawer';
import OperateFormDrawer from '@/components/operate-form-drawer';
import OperateFormModal from '@/components/operate-form-modal';
import OperateModal from '@/components/operate-modal';
import ModalActionFooter from '@/components/modal-action-footer';
import PageHeaderShell from '@/components/page-header-shell';
import SectionHeader from '@/components/section-header';
import SelectionPreviewLayout from '@/components/selection-preview-layout';
import Spin from '@/components/spin';
import { createK8sStoryT } from './k8s-story.fixtures';

const t = createK8sStoryT();

const FamilyOverview = () => {
  const [modalForm] = Form.useForm();
  const [drawerForm] = Form.useForm();
  const [contentDrawerForm] = Form.useForm();

  return (
    <div className="space-y-6">
      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader spacing="flush" title="Empty and status feedback" titleClassName="text-sm font-semibold" />
        <div className="grid gap-4 xl:grid-cols-3">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <div className="space-y-3">
              <CompactEmptyState
                description="Shared empty-state feedback keeps low-data and precondition surfaces visually aligned before business-specific actions appear."
                className="py-10"
              />
              <CompactEmptyState
                description="Fill in query criteria to preview the latest records here."
                className="py-8"
              />
              <CompactEmptyState
                description="Select a source item to inspect its detail panel."
                className="py-8"
              />
              <CompactEmptyState
                description="No records are available for the current table view."
                className="py-6"
              />
            </div>
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <IntegrationAccessComplete
              title="Setup completed"
              description="Shared completion feedback keeps multi-step flows aligned once the final action succeeds."
              subDescription="Teams can route to the next business workflow without rebuilding the terminal success state."
              actions={[
                {
                  key: 'primary',
                  label: 'View details',
                  type: 'primary',
                  onClick: () => undefined,
                },
                {
                  key: 'secondary',
                  label: 'Add another',
                  onClick: () => undefined,
                },
              ]}
            />
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <div className="space-y-4">
              <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-6">
                <div className="mb-3 text-xs text-[var(--color-text-3)]">Standalone page loading</div>
                <div className="flex min-h-[120px] items-center justify-center">
                  <Spin />
                </div>
              </div>
              <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-6">
                <div className="mb-3 text-xs text-[var(--color-text-3)]">Inline shell loading</div>
                <div className="rounded-lg bg-[var(--color-fill-1)] p-6">
                  <Spin />
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="grid gap-4 xl:grid-cols-2">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <IntegrationAccessComplete
              {...createCmdbK8sAccessCompletePreset(t, {
                onPrimaryAction: () => undefined,
                onSecondaryAction: () => undefined,
              })}
            />
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <IntegrationAccessComplete
              {...createMonitorFlowAccessCompletePreset(t, {
                onPrimaryAction: () => undefined,
                onSecondaryAction: () => undefined,
                onTertiaryAction: () => undefined,
              })}
            />
          </div>
        </div>
      </section>

      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Install and verification shell"
          titleClassName="text-sm font-semibold"
          description="K8s onboarding reuses one install-command and verify-status feedback shell. Business presets stay in K8s workflow stories, while the outer command, verify, success, and failure contract is governed here."
        />
        <div className="grid gap-4 xl:grid-cols-2">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <K8sCollectorInstall
              title="Install collector"
              installDescription="Run the command below in a cluster context with kubectl access."
              verifyTitle="Verify status"
              verifyButtonText="Verify"
              verifyWaitingDescription="After the rollout completes, trigger verification to confirm reporting."
              installCommand={`kubectl apply -f https://example.com/bk-lite/collector.yaml
kubectl rollout status deployment/bk-lite-collector -n bk-lite`}
              prevButtonText="Previous"
              successMessage="Collector connected"
              successDescription="Reporting has started and the setup wizard will continue automatically."
              failedMessage="Verification failed"
              failedDescription={(
                <>
                  Review the deployment status, then open
                  <Button type="link" className="px-1" onClick={() => undefined}>
                    Common issues
                  </Button>
                  for troubleshooting steps.
                </>
              )}
              commonIssuesText="Common issues"
              isVerifying={false}
              verificationStatus="waiting"
              onVerify={() => undefined}
              onPrev={() => undefined}
              onOpenCommonIssues={() => undefined}
            />
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <K8sCollectorInstall
              title="Install collector"
              installDescription="Generate a short-lived install command before moving to verification."
              verifyTitle="Verify status"
              verifyButtonText="Verify"
              verifyWaitingDescription="Verification stays disabled until a command is generated."
              installCommand=""
              prevButtonText="Previous"
              successMessage="Collector connected"
              successDescription="Reporting has started and the setup wizard will continue automatically."
              failedMessage="Verification failed"
              failedDescription="Generate the command, deploy it, and retry verification."
              installActions={(
                <div className="flex gap-2">
                  <Button type="primary">Generate Install Command</Button>
                </div>
              )}
              verifyDisabled
              isVerifying={false}
              verificationStatus="idle"
              onVerify={() => undefined}
              onPrev={() => undefined}
            />
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <K8sCollectorInstall
              title="Install collector"
              installDescription="Run the command below in a cluster context with kubectl access."
              verifyTitle="Verify status"
              verifyButtonText="Verify"
              verifyWaitingDescription="After the rollout completes, trigger verification to confirm reporting."
              installCommand={`kubectl apply -f https://example.com/bk-lite/collector.yaml
kubectl rollout status deployment/bk-lite-collector -n bk-lite`}
              prevButtonText="Previous"
              successMessage="Collector connected"
              successDescription="Reporting has started and the setup wizard will continue automatically."
              failedMessage="Verification failed"
              failedDescription="Collector has not reported yet. Check connectivity and retry."
              isVerifying={false}
              verificationStatus="success"
              onVerify={() => undefined}
              onPrev={() => undefined}
            />
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <K8sCollectorInstall
              title="Install collector"
              installDescription="Run the command below in a cluster context with kubectl access."
              verifyTitle="Verify status"
              verifyButtonText="Verify"
              verifyWaitingDescription="After the rollout completes, trigger verification to confirm reporting."
              installCommand={`kubectl apply -f https://example.com/bk-lite/collector.yaml
kubectl rollout status deployment/bk-lite-collector -n bk-lite`}
              prevButtonText="Previous"
              successMessage="Collector connected"
              successDescription="Reporting has started and the setup wizard will continue automatically."
              failedMessage="Verification failed"
              failedDescription={(
                <>
                  Review the deployment status, then open
                  <Button type="link" className="px-1" onClick={() => undefined}>
                    Common issues
                  </Button>
                  for troubleshooting steps.
                </>
              )}
              commonIssuesText="Common issues"
              isVerifying={false}
              verificationStatus="failed"
              onVerify={() => undefined}
              onPrev={() => undefined}
              onOpenCommonIssues={() => undefined}
            />
          </div>
        </div>
      </section>

      <div className="grid gap-6 xl:grid-cols-2">
        <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
          <SectionHeader spacing="flush" title="Modal shells" titleClassName="text-sm font-semibold" />
          <div className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-3">
              <OperateModal
                title="Base modal shell"
                subTitle="Legacy-compatible"
                open
                footer={null}
              >
                <div className="rounded-md bg-[var(--color-fill-1)] p-3 text-sm text-[var(--color-text-2)]">
                  The raw modal shell remains available for edge cases that own custom footer contracts.
                </div>
              </OperateModal>
            </div>

            <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-3">
              <OperateModal
                title="Header extra and legacy open alias"
                subTitle="Compatible with callers still migrating from visible"
                headerExtra={<Button size="small">Preview</Button>}
                footer={<div className="text-xs text-[var(--color-text-3)]">Custom footer content</div>}
                centered
                visible
              >
                <div className="rounded-md bg-[var(--color-fill-1)] p-3 text-sm text-[var(--color-text-2)]">
                  Base modal callers can keep header actions and the legacy visible alias without forking the shell.
                </div>
              </OperateModal>
            </div>

            <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-3">
              <OperateFormModal
                title="Governed modal shell"
                subTitle="Shared confirm/cancel footer"
                open
                confirmText="Confirm"
                cancelText="Cancel"
                onConfirm={() => modalForm.submit()}
                onCancel={() => undefined}
                extra={<span className="text-xs text-[var(--color-text-3)]">Draft changes</span>}
                secondaryActions={<Button>Validate</Button>}
                primaryFirst={false}
              >
                <Form form={modalForm} layout="vertical">
                  <Form.Item label="Name" name="name">
                    <Input placeholder="Rule name" />
                  </Form.Item>
                </Form>
              </OperateFormModal>
            </div>

            <div className="grid gap-4 xl:grid-cols-2">
              <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-3">
                <OperateFormModal
                  width={480}
                  title="Restart collector"
                  subTitle="Destructive confirm branch"
                  open
                  confirmText="Restart"
                  cancelText="Cancel"
                  onConfirm={() => undefined}
                  onCancel={() => undefined}
                  primaryFirst={false}
                  confirmPopconfirm={{
                    title: 'Restart collector',
                    description: 'The restart action will interrupt collection briefly before the agent comes back online.',
                    okText: 'Confirm',
                    cancelText: 'Back',
                  }}
                >
                  <div className="text-sm text-[var(--color-text-2)]">
                    Safety-check flows stay inside the governed modal shell instead of opening a separate feedback root.
                  </div>
                </OperateFormModal>
              </div>

              <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-3">
                <OperateFormModal
                  width={420}
                  title="Add tag"
                  open
                  confirmText="Save"
                  cancelText="Cancel"
                  onConfirm={() => undefined}
                  onCancel={() => undefined}
                >
                  <div className="space-y-4">
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <div className="mb-1 text-sm text-[var(--color-text-2)]">Key</div>
                        <Input placeholder="environment" />
                      </div>
                      <div>
                        <div className="mb-1 text-sm text-[var(--color-text-2)]">Value</div>
                        <Input placeholder="production" />
                      </div>
                    </div>
                    <div className="text-xs text-[var(--color-text-3)]">
                      Compact field-entry variants are still the same modal-action contract.
                    </div>
                  </div>
                </OperateFormModal>
              </div>
            </div>

            <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-3">
              <OperateFormModal
                width={860}
                title="Select instances"
                open
                confirmText="Confirm"
                cancelText="Cancel"
                confirmDisabled={false}
                primaryFirst={false}
                onConfirm={() => undefined}
                onCancel={() => undefined}
              >
                <SelectionPreviewLayout
                  primaryWidth={520}
                  primary={(
                    <div className="space-y-3">
                      <Input placeholder="Search instances" />
                      <div className="rounded border border-[var(--color-border-1)] p-3">
                        Table/list content goes here
                      </div>
                    </div>
                  )}
                  items={[
                    { key: '1', label: 'web-01' },
                    { key: '2', label: 'web-02' },
                  ]}
                  onClear={() => undefined}
                  onRemove={() => undefined}
                />
              </OperateFormModal>
            </div>

            <div className="grid gap-4 xl:grid-cols-2">
              <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-3">
                <OperateFormModal
                  width={720}
                  title="Import configuration"
                  open
                  hideFooter
                >
                  <div className="space-y-4">
                    <div className="flex items-center gap-3 text-sm">
                      <div className="rounded-full bg-[var(--color-primary)] px-3 py-1 text-white">1 Upload</div>
                      <div className="rounded-full border border-[var(--color-border-1)] px-3 py-1">2 Validate</div>
                      <div className="rounded-full border border-[var(--color-border-1)] px-3 py-1">3 Result</div>
                    </div>
                    <div className="rounded-lg border border-dashed border-[var(--color-border-1)] p-8 text-center text-sm text-[var(--color-text-2)]">
                      Multi-step workflows can own their action row inside the body while still using the shared shell.
                    </div>
                  </div>
                </OperateFormModal>
              </div>

              <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-3">
                <OperateFormModal
                  width="80vw"
                  title="Topology graph"
                  open
                  hideFooter
                >
                  <div className="h-[520px] bg-[var(--color-fill-1)] p-4">
                    <div className="flex h-full items-center justify-center rounded-lg border border-dashed border-[var(--color-border-1)] text-sm text-[var(--color-text-2)]">
                      Read-only wide viewers stay on the governed modal shell instead of falling back to raw antd modals.
                    </div>
                  </div>
                </OperateFormModal>
              </div>
            </div>
          </div>
        </section>

        <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
          <SectionHeader spacing="flush" title="Drawer shells" titleClassName="text-sm font-semibold" />
          <div className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-3">
              <ContentDrawer
                title="Base content drawer"
                open
                width={520}
                onClose={() => undefined}
                extra={<Button size="small">Copy</Button>}
                footer={<Button>Close</Button>}
                maskClosable={false}
              >
                <div className="space-y-3">
                  <div className="rounded-md bg-[var(--color-fill-1)] p-3 text-sm text-[var(--color-text-2)]">
                    The raw content drawer remains available for read-only preview and detail flows that do not need governed submit actions.
                  </div>
                  <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-bg-2)] p-3 text-xs text-[var(--color-text-3)]">
                    It also keeps the header-extra, custom-footer, and locked-mask branches on the shared shell.
                  </div>
                </div>
              </ContentDrawer>
            </div>

            <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-3">
              <OperateDrawer
                title="Base drawer shell"
                subTitle="Legacy-compatible"
                open
                width={420}
                footer={<Button>Close</Button>}
              >
                <div className="rounded-md bg-[var(--color-fill-1)] p-3 text-sm text-[var(--color-text-2)]">
                  The raw drawer shell stays available when the footer or header needs a fully custom contract.
                </div>
              </OperateDrawer>
            </div>

            <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-3">
              <OperateDrawer
                title="Header extra and legacy open alias"
                subTitle="Visible callers still map to the shared drawer"
                visible
                width={560}
                headerExtra={(
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-xs text-[var(--color-text-3)]">Last updated 2 minutes ago</span>
                    <Button size="small">Preview</Button>
                  </div>
                )}
                footer={<Button>Close</Button>}
              >
                <div className="grid gap-3">
                  <div className="h-10 rounded-md bg-[var(--color-fill-1)]" />
                  <div className="h-10 rounded-md bg-[var(--color-fill-1)]" />
                  <div className="h-24 rounded-md bg-[var(--color-fill-1)]" />
                </div>
              </OperateDrawer>
            </div>

            <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-3">
              <OperateFormDrawer
                title="Governed drawer shell"
                subTitle="Shared confirm/cancel footer"
                open
                width={420}
                confirmText="Save"
                cancelText="Cancel"
                onConfirm={() => drawerForm.submit()}
                onCancel={() => undefined}
                secondaryActions={<Button>Preview</Button>}
              >
                <Form form={drawerForm} layout="vertical">
                  <Form.Item label="Namespace" name="namespace">
                    <Input placeholder="Namespace" />
                  </Form.Item>
                </Form>
              </OperateFormDrawer>
            </div>

            <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-3">
              <ContentFormDrawer
                title="Governed content drawer"
                open
                width={420}
                onClose={() => undefined}
                confirmText={undefined}
                cancelText="Close"
                onCancel={() => undefined}
                primaryFirst={false}
                secondaryActions={<Button danger>Delete</Button>}
                extra={(
                  <span className="text-xs text-[var(--color-text-3)]">
                    Read-only detail with governed actions.
                  </span>
                )}
              >
                <Form form={contentDrawerForm} layout="vertical">
                  <Form.Item label="Question" name="question">
                    <Input placeholder="How do we route shared drawer actions?" />
                  </Form.Item>
                </Form>
              </ContentFormDrawer>
            </div>

            <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-3">
              <OperateFormDrawer
                title="Selection workflow drawer"
                subTitle="Cancel-only and preview layout variants"
                open
                width={760}
                cancelText="Close"
                onCancel={() => undefined}
              >
                <SelectionPreviewLayout
                  primaryWidth={500}
                  listHeight="360px"
                  primary={(
                    <div className="space-y-3">
                      <Input placeholder="Search assets" />
                      <div className="rounded border border-[var(--color-border-1)] p-3">
                        Asset list or tree content goes here
                      </div>
                    </div>
                  )}
                  items={[
                    { key: '1', label: 'cluster-a / web-01' },
                    { key: '2', label: 'cluster-b / web-02' },
                  ]}
                  onClear={() => undefined}
                  onRemove={() => undefined}
                />
              </OperateFormDrawer>
            </div>

            <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-3">
              <OperateFormDrawer
                title="Guidance"
                subTitle="Read-only drawer shell"
                open
                width={620}
                hideFooter
              >
                <div className="space-y-3">
                  <div className="rounded border border-[var(--color-border-1)] p-3">
                    Use this variant when the drawer is informational and intentionally has no action row.
                  </div>
                  <div className="rounded border border-[var(--color-border-1)] p-3">
                    Operational guidance, troubleshooting notes, and detail browsing flows should stay on the governed shell.
                  </div>
                </div>
              </OperateFormDrawer>
            </div>

            <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-3">
              <ContentFormDrawer
                title="API guide"
                open
                width={720}
                onClose={() => undefined}
                hideFooter
                headerExtra={<Segmented options={['Usage', 'Response']} size="small" />}
              >
                <div className="space-y-3">
                  <div className="rounded border border-[var(--color-border-1)] p-4">
                    Use this variant when a content drawer is read-only and should not expose an action row.
                  </div>
                  <div className="rounded border border-[var(--color-border-1)] p-4">
                    Endpoint examples, file previews, and detail browsing flows can stay on the governed content drawer shell.
                  </div>
                </div>
              </ContentFormDrawer>
            </div>

            <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-3">
              <ContentFormDrawer
                title="Preview selected chunks"
                open
                width={960}
                onClose={() => undefined}
                confirmText="Confirm (2)"
                cancelText="Cancel"
                onConfirm={() => undefined}
                onCancel={() => undefined}
                primaryFirst={false}
              >
                <SelectionPreviewLayout
                  className="h-[420px] gap-4"
                  primaryWidth={260}
                  previewTitle="Selected documents (2)"
                  showClearWhenEmpty={false}
                  primaryClassName="rounded-lg border border-[var(--color-border-1)] p-4"
                  previewClassName="rounded-lg border border-[var(--color-border-1)] p-4"
                  items={[
                    { key: '1', label: 'Handbook.pdf' },
                    { key: '2', label: 'FAQ.md' },
                  ]}
                  onClear={() => undefined}
                  onRemove={() => undefined}
                  primary={(
                    <div className="space-y-2">
                      <div className="rounded-lg border border-blue-200 bg-blue-50/50 p-3">
                        Handbook.pdf
                      </div>
                      <div className="rounded-lg border border-[var(--color-border-1)] p-3">
                        FAQ.md
                      </div>
                    </div>
                  )}
                  footer={(
                    <div className="space-y-3">
                      <PageHeaderShell
                        as="h3"
                        className="pt-3"
                        title="Chunk preview"
                        titleClassName="m-0 text-sm font-medium text-[var(--color-text-1)]"
                        headerRowClassName="flex items-center justify-between gap-3"
                        actions={<Input.Search placeholder="Search chunk content" className="w-[220px]" />}
                      />
                      <div className="space-y-3">
                        <div className="rounded border border-[var(--color-border-1)] p-3">
                          Chunk preview content goes here.
                        </div>
                        <div className="rounded border border-[var(--color-border-1)] p-3">
                          Another selected chunk preview.
                        </div>
                      </div>
                    </div>
                  )}
                />
              </ContentFormDrawer>
            </div>

            <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-3">
              <ContentDrawer
                title="Loading and empty state"
                open
                width={420}
                onClose={() => undefined}
                loading
                content=""
              />
            </div>
          </div>
        </section>
      </div>

      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader spacing="flush" title="Shared action footer contract" titleClassName="text-sm font-semibold" />
        <div className="grid gap-4 xl:grid-cols-2">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <ModalActionFooter
              confirmText="Confirm"
              cancelText="Cancel"
              onConfirm={() => undefined}
              onCancel={() => undefined}
              extra={(
                <div className="flex flex-wrap items-center gap-2">
                  <Tag color="processing">2 files pending</Tag>
                  <Button size="small">Download template</Button>
                </div>
              )}
              secondaryActions={<Button>Test connection</Button>}
              primaryFirst={false}
            />
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <ModalActionFooter
              confirmText="Restart collector"
              cancelText="Cancel"
              onConfirm={() => undefined}
              onCancel={() => undefined}
              confirmLoading
              cancelDisabled
              secondaryActionsPosition="afterConfirm"
              secondaryActions={<Button>Save Only</Button>}
              confirmPopconfirm={{
                title: 'Restart collector',
                description: 'This action restarts the selected collector on the target nodes.',
                okText: 'Confirm',
                cancelText: 'Back',
              }}
            />
          </div>
        </div>
      </section>
    </div>
  );
};

const meta = {
  title: 'Framework/Feedback/FamilyOverview',
  component: FamilyOverview,
  decorators: [
    (Story) => (
      <div style={{ maxWidth: 1240, padding: 24, background: 'var(--color-bg-2)' }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof FamilyOverview>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Overview: Story = {};
