import type {
  GroupOrderPayload,
  Model,
  ModelGroup,
  ModelGroupPayload,
  ModelVendor,
  ModelVendorPayload,
} from '../../../src/app/opspilot/types/provider';

const vendors: ModelVendor[] = [
  {
    id: 1,
    name: 'OpenAI Production',
    vendor_type: 'openai',
    protocol_type: 'openai',
    api_base: 'https://api.openai.com/v1',
    enabled: true,
    team: [1],
    team_name: ['Default'],
    model_count: 8,
    description: 'Primary LLM provider for production assistants.',
    permissions: ['View', 'Setting', 'Delete'],
  },
];

const models: Model[] = [
  {
    id: 1,
    name: 'gpt-4o',
    enabled: true,
    is_build_in: false,
    model_type_name: 'Chat',
    icon: 'GPT',
    permissions: ['View', 'Setting', 'Delete'],
  },
];

const groups: ModelGroup[] = [
  {
    id: 1,
    name: 'general',
    display_name: 'General Models',
    count: 3,
    is_build_in: true,
  },
];

export const useProviderApi = () => {
  const fetchModels = async () => models;
  const fetchModelsByVendor = async () => models;
  const fetchModelDetail = async () => models[0];
  const addProvider = async (_type: string, payload: Record<string, unknown>) => ({ ...models[0], ...payload });
  const updateProvider = async (_type: string, id: number, payload: Record<string, unknown>) => ({ ...models[0], id, ...payload });
  const patchProvider = async (_type: string, id: number, payload: Record<string, unknown>) => ({ ...models[0], id, ...payload });
  const deleteProvider = async () => {};

  const fetchVendors = async () => vendors;
  const fetchVendorDetail = async (id: number) => vendors.find((vendor) => vendor.id === id) || vendors[0];
  const createVendor = async (payload: ModelVendorPayload) => ({ ...vendors[0], ...payload, id: vendors.length + 1 });
  const updateVendor = async (id: number, payload: Partial<ModelVendorPayload>) => ({ ...vendors[0], id, ...payload });
  const patchVendor = async (id: number, payload: Partial<ModelVendorPayload>) => ({ ...vendors[0], id, ...payload });
  const deleteVendor = async () => {};
  const testVendorConnection = async () => ({ success: true });

  const fetchModelGroups = async () => groups;
  const createModelGroup = async (_type: string, payload: ModelGroupPayload) => ({ ...groups[0], ...payload, id: groups.length + 1 });
  const updateModelGroup = async (_type: string, groupId: string, payload: Partial<ModelGroupPayload>) => ({
    ...groups[0],
    ...payload,
    id: Number(groupId) || groups[0].id,
  });
  const deleteModelGroup = async () => {};
  const updateGroupOrder = async (_type: string, payload: GroupOrderPayload) => ({ ...groups[0], ...payload });

  return {
    fetchModels,
    fetchModelsByVendor,
    fetchModelDetail,
    addProvider,
    updateProvider,
    patchProvider,
    deleteProvider,
    fetchVendors,
    fetchVendorDetail,
    createVendor,
    updateVendor,
    patchVendor,
    deleteVendor,
    testVendorConnection,
    fetchModelGroups,
    createModelGroup,
    updateModelGroup,
    deleteModelGroup,
    updateGroupOrder,
  };
};
