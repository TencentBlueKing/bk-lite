'use client';

import { useCallback } from 'react';
import { readListPages } from './list-pages';
import type { TriggerOptions } from '../rule/triggers/trigger-config';
import type { TriggerOptionsQuery } from '../rule/triggers/trigger-option-pages';
import type { PortalLayout } from '../portal/workbench-types';
import type { HandoverCandidate, HandoverDraft, HandoverRecord, PortalData, SurveySubmission, TicketCenterFilters, TicketExportCatalog, TicketExportRecord } from '../types';
import useApiClient from '@/utils/request';

export interface TicketTriggerLogPage {
  count: number;
  items: {
    id: number;
    trigger_name: string;
    event: string;
    action: string;
    position: number | null;
    status: 'success' | 'failed' | 'pending' | 'legacy';
    message: string;
    created_at: string;
  }[];
}

// Next.js 代理使用无尾斜杠入口，代理转发 Django 时统一补斜杠。
// 仅规范本模块路径，查询串和外部地址保持原样。
export const itsmRequestPath = (url: string) => url.startsWith('/itsm/') ? url.replace(/^([^?#]*)\/(?=[?#]|$)/, '$1') : url;

export function useItsmApi() {
  const client = useApiClient();
  const { isLoading } = client;
  const get = useCallback<typeof client.get>((url, config) => client.get(itsmRequestPath(url), config), [client.get]);
  const post = useCallback<typeof client.post>((url, body, config) => client.post(itsmRequestPath(url), body, config), [client.post]);
  const put = useCallback<typeof client.put>((url, body, config) => client.put(itsmRequestPath(url), body, config), [client.put]);
  const del = useCallback<typeof client.del>((url, config) => client.del(itsmRequestPath(url), config), [client.del]);

  const fetchField = useCallback((body: Record<string, unknown>) => post('/itsm/api/fields/fetch/', body), [post]);
  const bindFieldGateway = useCallback((body: Record<string, unknown>) => post('/itsm/api/fields/gateway/', body), [post]);
  const fieldCatalog = useCallback(() => get('/itsm/api/fields/catalog/'), [get]);

  const listIntegrations = useCallback((summary = false) => get('/itsm/api/integrations/', { params: summary ? { summary: '1' } : {} }), [get]);
  const integrationCatalog = useCallback(() => get('/itsm/api/integrations/catalog/'), [get]);
  const getIntegration = useCallback((id: number, filters?: Record<string, string>) => get(`/itsm/api/integrations/${id}/${filters ? `?${new URLSearchParams(filters)}` : ''}`), [get]);
  const saveIntegration = useCallback((body: Record<string, unknown>, id?: number) => id ? put(`/itsm/api/integrations/${id}/`, body) : post('/itsm/api/integrations/', body), [post, put]);
  const testIntegration = useCallback((id: number, inputs: Record<string, unknown>) => post(`/itsm/api/integrations/${id}/test/`, { inputs }), [post]);
  const retryDelivery = useCallback((id: number, delivery: number) => post(`/itsm/api/integrations/${id}/deliveries/${delivery}/retry/`), [post]);
  const reconcileDelivery = useCallback((id: number, delivery: number, attempts: number, received: boolean) =>
    post(`/itsm/api/integrations/${id}/deliveries/${delivery}/reconcile/`, { attempts, received }), [post]);

  const searchTicketTags = useCallback((q: string) => get('/itsm/api/tickets/filter_tags/', { params: { q } }), [get]);
  const centerSettings = useCallback(() => get('/itsm/api/tickets/center_settings/'), [get]);
  const saveTicketColumns = useCallback((columns: string[] | null) => put('/itsm/api/tickets/center_settings/', { columns }), [put]);
  const saveTicketGroup = useCallback((name: string, filters: TicketCenterFilters) => post('/itsm/api/tickets/center_settings/', { name, filters }), [post]);
  const deleteTicketGroup = useCallback((id: number) => del('/itsm/api/tickets/center_settings/', { data: { id } }), [del]);
  const batchOptions = useCallback((ids: number[]) => post('/itsm/api/tickets/batch_options/', { ids }), [post]);
  const batchTickets = useCallback((ids: number[], action: string, opinion: string) => post('/itsm/api/tickets/batch_operate/', { ids, action, opinion }), [post]);

  const listForms = useCallback(async () => {
    const items: { id: number; name: string; key: string }[] = [];
    let count = 0;
    for (let page = 1; ; page++) {
      const result = await get('/itsm/api/forms/', { params: { page, page_size: 100 } }) as { count: number; items: typeof items };
      items.push(...result.items); count = result.count;
      if (!result.items.length || items.length >= count) break;
    }
    return { items, count };
  }, [get]);
  const createForm = useCallback(
    (body: { name: string; key: string }) => post('/itsm/api/forms/', body),
    [post],
  );
  const getForm = useCallback((id: number) => get(`/itsm/api/forms/${id}/`), [get]);
  const saveForm = useCallback((id: number, schema: unknown) => put(`/itsm/api/forms/${id}/`, { schema }), [put]);
  const publishForm = useCallback(
    (id: number, schema: unknown) => post(`/itsm/api/forms/${id}/publish/`, { schema }),
    [post],
  );
  const listWorkflows = useCallback(() => readListPages(page => get('/itsm/api/workflows', { params: { page, page_size: 100 } })), [get]);
  const createWorkflow = useCallback(
    (body: { name: string; key: string; form_id?: number }) => post('/itsm/api/workflows/', body),
    [post],
  );
  const getDesign = useCallback((id: number) => get(`/itsm/api/workflows/${id}/design/`), [get]);
  const saveDesign = useCallback(
    (id: number, design: unknown) => put(`/itsm/api/workflows/${id}/design/`, design),
    [put],
  );
  const publishWorkflow = useCallback(
    (id: number) => post(`/itsm/api/workflows/${id}/publish/`),
    [post],
  );
  const listTickets = useCallback((query?: Partial<TicketCenterFilters> & { page?: number; page_size?: number; relation_for?: number; fields?: string }) => {
    const { form_filters, ...filters } = query || {};
    const params = Object.fromEntries(Object.entries(filters).filter(([, value]) => value));
    if (form_filters?.length) params.form_filters = JSON.stringify(form_filters);
    return get('/itsm/api/tickets/', Object.keys(params).length ? { params } : undefined);
  }, [get]);
  const ticketFilterWorkflows = useCallback((q: string) => get('/itsm/api/tickets/filter_fields/', { params: { q } }), [get]);
  const ticketFilterFields = useCallback((workflowId: string) => get('/itsm/api/tickets/filter_fields/', { params: { workflow_id: workflowId } }), [get]);
  const exportTickets = useCallback(
    (filters: TicketCenterFilters, formColumns: string[], ids?: number[], fields?: { columns: string[]; form_workflow_id?: string }) =>
      post<TicketExportRecord>('/itsm/api/tickets/export/tasks/', { filters, form_columns: formColumns, ids, ...fields }),
    [post],
  );
  const ticketExportFields = useCallback((params: { workflow_id?: string; q?: string }) =>
    get<TicketExportCatalog>('/itsm/api/tickets/export/fields/', { params }), [get]);
  const listTicketExports = useCallback((page: number, pageSize: number) => get<{ count: number; items: TicketExportRecord[] }>(
    '/itsm/api/tickets/export/tasks/', { params: { page, page_size: pageSize } },
  ), [get]);
  const downloadTicketExport = useCallback((id: number) => get<Blob>(`/itsm/api/tickets/export/tasks/${id}/download/`, { responseType: 'blob' }), [get]);
  const retryTicketExport = useCallback((id: number) => post<TicketExportRecord>(`/itsm/api/tickets/export/tasks/${id}/retry/`), [post]);
  const listResources = useCallback((kind: string) => readListPages(page => get(`/itsm/api/resources/${kind}/`, { params: { page, page_size: 100 } })), [get]);
  const getTriggerOptions = useCallback(({ page, selected }: TriggerOptionsQuery) => get<TriggerOptions>('/itsm/api/triggers/options/', {
    params: { page, ...(selected && { selected: JSON.stringify(selected) }) },
  }), [get]);
  const previewPrintTemplate = useCallback(() =>
    post<{ html: string }>('/itsm/api/print-templates/preview/', {}, { suppressErrorNotification: true }), [post]);
  const getTicketPrint = useCallback((id: number) =>
    get<{ html: string }>(`/itsm/api/tickets/${id}/print/`, { suppressErrorNotification: true }), [get]);
  const listHandovers = useCallback(async () => await listResources('handovers') as unknown as {
    items: HandoverRecord[];
    can_add?: boolean;
    can_retry?: boolean;
  }, [listResources]);
  const searchHandoverCandidates = useCallback((fromUser: string, q: string, page: number) => get<{
    items: HandoverCandidate[];
    count: number;
  }>('/itsm/api/handovers/candidates/', { params: { from_user: fromUser, q, page } }), [get]);
  const createHandover = useCallback((body: HandoverDraft) => post<HandoverRecord>('/itsm/api/resources/handovers/', body), [post]);
  const retryHandover = useCallback((id: number) => post<HandoverRecord>(`/itsm/api/handovers/${id}/retry/`), [post]);
  const createResource = useCallback((kind: string, body: Record<string, unknown>) => post(`/itsm/api/resources/${kind}/`, body), [post]);
  const updateResource = useCallback(
    (kind: string, id: number, body: Record<string, unknown>) => put(`/itsm/api/resources/${kind}/${id}/`, body),
    [put],
  );
  const deleteResource = useCallback((kind: string, id: number) => del(`/itsm/api/resources/${kind}/${id}/`), [del]);
  const createTicket = useCallback(
    (body: { workflow_version_id: number; form_data: Record<string, unknown>; service_id?: number; creation_key?: string }) => post('/itsm/api/tickets/', body),
    [post],
  );
  const operateTicket = useCallback(
    (id: number, body: { task_id?: number; action: string; opinion?: string; target?: string; return_node_id?: string; form_data?: Record<string, unknown> }) => post(`/itsm/api/tickets/${id}/operate/`, body),
    [post],
  );
  const ticketLogs = useCallback((id: number) => get(`/itsm/api/tickets/${id}/logs/`), [get]);
  const listTicketWorkflows = useCallback(() => get('/itsm/api/tickets/workflows/'), [get]);
  const ticketForm = useCallback((versionId: number, serviceId?: number) => get(`/itsm/api/tickets/form/${versionId}/`, { params: serviceId ? { service_id: serviceId } : {} }), [get]);
  const getTicket = useCallback((id: number, taskId?: number) => get(`/itsm/api/tickets/${id}/`, { params: { task_id: taskId }, suppressErrorNotification: true }), [get]);
  const getTicketTriggerLogs = useCallback((id: number, page: number, pageSize: number) => get<TicketTriggerLogPage>(
    `/itsm/api/tickets/${id}/trigger-logs/`, { params: { page, page_size: pageSize }, suppressErrorNotification: true },
  ), [get]);
  const retryAutoNode = useCallback((ticketId: number, executionId: number) => post(`/itsm/api/tickets/${ticketId}/auto/${executionId}/retry/`), [post]);
  const listScheduleRuns = useCallback((page: number, scheduleId?: number) => get('/itsm/api/schedules/runs/', { params: { page, schedule_id: scheduleId } }), [get]);
  const submitSurvey = useCallback(
    (id: number, body: SurveySubmission) => post(`/itsm/api/tickets/${id}/survey/`, body),
    [post],
  );
  const portal = useCallback((serviceId?: number) => get<PortalData>(`/itsm/api/services/portal/?${serviceId ? `service_id=${serviceId}` : 'summary=1'}`), [get]);
  const directoryPage = useCallback((query: Record<string, string>) => get<{items: PortalData['services']; total: number; page: number}>(`/itsm/api/services/portal/?directory=1&${new URLSearchParams(query)}`), [get]);
  const portalLayout = useCallback(() => get('/itsm/api/services/layout/'), [get]);
  const savePortalLayout = useCallback((value: PortalLayout) => put('/itsm/api/services/layout/', value), [put]);
  const portalDashboard = useCallback(() => get('/itsm/api/services/dashboard/'), [get]);
  const loadDrafts = useCallback(() => get('/itsm/api/services/drafts/'), [get]);
  const saveDraft = useCallback((body: { service_id: number; form_data?: Record<string, unknown>; clear?: boolean }) => post('/itsm/api/services/drafts/', body), [post]);
  const listCatalogs = useCallback(() => get('/itsm/api/catalogs/'), [get]);
  const createCatalog = useCallback((body: { id?: number; name: string; parent_id?: number | null }) => post('/itsm/api/catalogs/', body), [post]);
  const deleteCatalog = useCallback((id: number) => del(`/itsm/api/catalogs/?id=${id}`), [del]);
  const listServices = useCallback(() => get('/itsm/api/services/'), [get]);
  const createService = useCallback(
    (body: { id?: number; name?: string; catalog_id?: number | null; workflow_id?: number; description?: string; is_hot?: boolean; is_enabled?: boolean; visibility?: string; visible_users?: string[]; visible_groups?: number[] }) => post('/itsm/api/services/', body),
    [post],
  );
  const deleteService = useCallback((id: number) => del(`/itsm/api/services/?id=${id}`), [del]);
  const toggleFavorite = useCallback((id: number) => post<{ favorite: boolean; service?: PortalData['services'][number] }>(`/itsm/api/services/${id}/favorite/`), [post]);
  const useService = useCallback((id: number) => post(`/itsm/api/services/${id}/use/`), [post]);
  const searchUsers = useCallback(
    (q: string, page = 1) => get('/itsm/api/users/search/', { params: { q, page, page_size: 10 } }),
    [get],
  );
  const searchTransferCandidates = useCallback(
    (ticketId: number, taskId: number, q: string, page = 1) => get(
      `/itsm/api/tickets/${ticketId}/tasks/${taskId}/transfer-candidates/`, { params: { q, page } },
    ),
    [get],
  );
  const listStatuses = useCallback(() => get('/itsm/api/statuses/'), [get]);
  const listStatusAdmin = useCallback(() => get('/itsm/api/statuses/admin/'), [get]);
  const postStatus = useCallback((body: { id?: number; key?: string; name: string; color?: string; description?: string }) => post('/itsm/api/statuses/admin/', body), [post]);
  const listSla = useCallback(() => get('/itsm/api/sla/'), [get]);
  const saveSla = useCallback((body: { policy_id?: number; category?: string; is_enabled?: boolean; kind?: string; name?: string; id?: number; work_days?: number[]; work_start?: string; work_end?: string; timezone?: string; target?: string; minutes?: number; calendar_id?: number; workflow_id?: number; warning_minutes?: number; escalation_users?: string[] }) => post('/itsm/api/sla/', body), [post]);
  const listViewTemplates = useCallback((formId?: number) => get('/itsm/api/view_templates/', formId ? { params: { form_id: formId } } : undefined), [get]);
  const createViewTemplate = useCallback((body: { form_id: number; name: string; layout?: { fields?: string[] }; match_rules?: { status?: string } }) => post('/itsm/api/view_templates/', body), [post]);
  const exportWorkflow = useCallback((id: number) => get(`/itsm/api/workflows/${id}/export/`), [get]);
  const importWorkflow = useCallback((bundle: Record<string, unknown>) => post('/itsm/api/workflows/import/', bundle), [post]);
  const testVariable = useCallback((body: { workflow_id: number; key: string; form_data?: Record<string, unknown> }) => post('/itsm/api/workflow_variables/test/', body), [post]);
  const listVariables = useCallback((workflowId: number) => get('/itsm/api/workflow_variables/', { params: { workflow_id: workflowId } }), [get]);
  const listDataTables = useCallback(() => get('/itsm/api/data_tables/'), [get]);
  const createDataTable = useCallback((body: { name: string; key: string; fields?: Array<{ key: string; type?: string }> }) => post('/itsm/api/data_tables/', body), [post]);
  const exportDataTable = useCallback((id: number) => get(`/itsm/api/data_tables/${id}/export/`), [get]);
  const importDataTable = useCallback((contentBase64: string, filename: string) => post('/itsm/api/data_tables/import/', { content_base64: contentBase64, filename }), [post]);
  const getDataTable = useCallback((id: number) => get(`/itsm/api/data_tables/${id}/`), [get]);
  const saveDataTable = useCallback((id: number, body: Record<string, unknown>) => put(`/itsm/api/data_tables/${id}/`, body), [put]);
  const saveDataRow = useCallback((id: number, data: Record<string, unknown>, rowId?: number) => rowId ? put(`/itsm/api/data_tables/${id}/rows/${rowId}/`, { data }) : post(`/itsm/api/data_tables/${id}/rows/`, { data }), [post, put]);
  const deleteDataRows = useCallback((id: number, ids: number[]) => post(`/itsm/api/data_tables/${id}/rows/delete/`, { ids }), [post]);
  const listDataRows = useCallback((id: number, page = 1, pageSize = 20) => get(`/itsm/api/data_tables/${id}/rows/?page=${page}&page_size=${pageSize}`), [get]);
  const listWorkflowVersions = useCallback((id: number) => get(`/itsm/api/workflows/${id}/versions/`), [get]);
  const enableWorkflowVersion = useCallback((workflowId: number, versionId: number) => post(`/itsm/api/workflows/${workflowId}/versions/${versionId}/enable/`, {}), [post]);
  const listComments = useCallback((id: number) => get(`/itsm/api/tickets/${id}/comments/`), [get]);
  const addComment = useCallback((id: number, content: string, parent_id?: number, attachment_ids?: number[]) => post(`/itsm/api/tickets/${id}/comments/`, { content, parent_id, attachment_ids }), [post]);
  const listAttachments = useCallback((id: number) => get(`/itsm/api/tickets/${id}/attachments/`), [get]);
  const addAttachment = useCallback(
    (id: number, body: { receipt: string }) => post(`/itsm/api/tickets/${id}/attachments/`, body),
    [post],
  );
  const downloadAttachment = useCallback((id: number, fileId: number) => get(`/itsm/api/tickets/${id}/attachments/${fileId}/`), [get]);
  const deleteAttachment = useCallback((id: number, fileId: number) => del(`/itsm/api/tickets/${id}/attachments/${fileId}/`), [del]);
  const listFollowers = useCallback((id: number) => get(`/itsm/api/tickets/${id}/followers/`), [get]);
  const toggleFollow = useCallback((id: number, following: boolean) => post(`/itsm/api/tickets/${id}/followers/`, { following }), [post]);
  const listTags = useCallback((id: number) => get(`/itsm/api/tickets/${id}/tags/`), [get]);
  const addTag = useCallback((id: number, name: string, color?: string) => post(`/itsm/api/tickets/${id}/tags/`, { name, color }), [post]);
  const removeTag = useCallback((id: number, tagId: number) => del(`/itsm/api/tickets/${id}/tags/`, { data: { id: tagId } }), [del]);
  const removeRelation = useCallback((id: number, relationId: number) => del(`/itsm/api/tickets/${id}/relations/`, { data: { id: relationId } }), [del]);
  const listRelations = useCallback((id: number) => get(`/itsm/api/tickets/${id}/relations/`), [get]);
  const addRelation = useCallback(
    (id: number, relatedId: number) => post(`/itsm/api/tickets/${id}/relations/`, { related_id: relatedId }),
    [post],
  );
  const listDictionaries = useCallback(() => readListPages(page => get('/itsm/api/dictionaries/', { params: { page, page_size: 100 } })), [get]);
  const createDictionary = useCallback((body: { id?: number; key?: string; name: string }) => post('/itsm/api/dictionaries/', body), [post]);
  const listDictionaryItems = useCallback((id: number) => get(`/itsm/api/dictionaries/${id}/items/`), [get]);
  const createDictionaryItem = useCallback(
    (id: number, body: { id?: number; key: string; label: string; order?: number; is_enabled?: boolean }) => post(`/itsm/api/dictionaries/${id}/items/`, body),
    [post],
  );
  const deleteDictionaryItem = useCallback(
    (id: number, itemId: number) => del(`/itsm/api/dictionaries/${id}/items/?id=${itemId}`),
    [del],
  );
  const exportDictionaries = useCallback(() => get('/itsm/api/dictionaries/export/'), [get]);
  const importDictionaries = useCallback((rows: unknown[]) => post('/itsm/api/dictionaries/import/', rows), [post]);
  const listStages = useCallback(() => get('/itsm/api/stages/'), [get]);
  const createStage = useCallback(
    (body: { workflow_id: number; key: string; name: string }) => post('/itsm/api/stages/', body),
    [post],
  );
  const deleteStage = useCallback((id: number) => del(`/itsm/api/stages/?id=${id}`), [del]);
  const deleteStatus = useCallback((id: number) => del(`/itsm/api/statuses/admin/?id=${id}`), [del]);
  const listTransitions = useCallback(() => get('/itsm/api/statuses/transitions/'), [get]);
  const createTransition = useCallback(
    (body: { from_id: number; to_id: number; name?: string }) => post('/itsm/api/statuses/transitions/', body),
    [post],
  );
  const deleteTransition = useCallback((id: number) => del(`/itsm/api/statuses/transitions/?id=${id}`), [del]);
  const listHandlerGroups = useCallback(() => get('/itsm/api/handler_groups/'), [get]);
  const listWorkflowHandlerGroupOptions = useCallback(
    async () => await readListPages(page => get('/itsm/api/workflows/handler-group-options/', {
      params: { page, page_size: 100 },
    })) as { items: { id: number; name: string }[] },
    [get],
  );
  const createHandlerGroup = useCallback(
    (body: { id?: number; name: string; members: string[]; leaders: string[] }) => post('/itsm/api/handler_groups/', body),
    [post],
  );
  const deleteHandlerGroup = useCallback((id: number) => del(`/itsm/api/handler_groups/?id=${id}`), [del]);
  const listNotifyTemplates = useCallback(() => get('/itsm/api/notify_templates/'), [get]);
  const saveNotifyTemplate = useCallback(
    (body: { id?: number; event: string; channel_type?: 'site' | 'im'; title_tpl: string; content_tpl: string }) => post('/itsm/api/notify_templates/', body),
    [post],
  );
  const deleteNotifyTemplate = useCallback((id: number) => del(`/itsm/api/notify_templates/?id=${id}`), [del]);
  const getBasicSettings = useCallback(() => get('/itsm/api/settings/basic/'), [get]);
  const saveBasicSettings = useCallback(
    (body: { product_name: string; tab_title: string; attachment_types: string; show_process_log: boolean; user_display: string }) => post('/itsm/api/settings/basic/', body),
    [post],
  );
  const presignAttachment = useCallback((filename: string, ticket_id?: number, fieldContext?: { field: string; task_id?: number }) => post('/itsm/api/attachments/presign/', { filename, ticket_id, ...fieldContext }), [post]);

  return {
    ready: !isLoading,
    fetchField, fieldCatalog, bindFieldGateway, listIntegrations, integrationCatalog, getIntegration, saveIntegration, testIntegration, retryDelivery, reconcileDelivery,
    searchTicketTags, centerSettings, saveTicketColumns, saveTicketGroup, deleteTicketGroup, batchTickets, batchOptions,
    listForms,
    createForm,
    getForm,
    saveForm,
    publishForm,
    listWorkflows,
    createWorkflow,
    getDesign,
    saveDesign,
    publishWorkflow,
    listTickets, ticketFilterWorkflows, ticketFilterFields, exportTickets, ticketExportFields, listTicketExports, downloadTicketExport, retryTicketExport,
    listResources, getTriggerOptions,
    previewPrintTemplate,
    getTicketPrint,
    createResource,
    updateResource,
    deleteResource,
    createTicket,
    operateTicket,
    ticketLogs,
    getTicket,
    getTicketTriggerLogs,
    retryAutoNode,
    listScheduleRuns,
    ticketForm,
    listTicketWorkflows,
    submitSurvey,
    directoryPage, portal,
    portalLayout,
    savePortalLayout,
    portalDashboard,
    loadDrafts,
    saveDraft,
    listCatalogs,
    createCatalog,
    deleteCatalog,
    listServices,
    createService,
    deleteService,
    toggleFavorite,
    useService,
    searchUsers,
    listHandovers,
    searchHandoverCandidates,
    createHandover,
    retryHandover,
    searchTransferCandidates,
    listStatuses,
    listStatusAdmin,
    postStatus,
    listSla,
    saveSla,
    listViewTemplates,
    createViewTemplate,
    exportWorkflow,
    importWorkflow,
    testVariable,
    listVariables,
    listDataTables,
    createDataTable,
    exportDataTable,
    importDataTable,
    deleteDataRows,
    listDataRows, getDataTable, saveDataTable, saveDataRow,
    listWorkflowVersions,
    enableWorkflowVersion,
    listComments,
    addComment,
    listAttachments,
    addAttachment,
    downloadAttachment,
    deleteAttachment,
    listFollowers,
    toggleFollow,
    listTags,
    addTag,
    removeTag,
    removeRelation,
    listRelations,
    addRelation,
    listDictionaries,
    createDictionary,
    listDictionaryItems,
    createDictionaryItem,
    deleteDictionaryItem,
    exportDictionaries,
    importDictionaries,
    listStages,
    createStage,
    deleteStage,
    deleteStatus,
    listTransitions,
    createTransition,
    deleteTransition,
    listHandlerGroups,
    listWorkflowHandlerGroupOptions,
    createHandlerGroup,
    deleteHandlerGroup,
    listNotifyTemplates,
    saveNotifyTemplate,
    deleteNotifyTemplate,
    getBasicSettings,
    saveBasicSettings,
    presignAttachment,
    remove: del,
  };
}
