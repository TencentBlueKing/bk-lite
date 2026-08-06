import { apiGet } from '@/api/request';
import { fetchWebJson } from '@/api/web';
import {
  MODULE_CONFIG,
  type AvailabilityFacts,
  type BusinessClient,
  type MenuNode,
} from './model';

interface ApiEnvelope<T> {
  result: boolean;
  data: T;
  message?: string;
}

interface ClientItem {
  name: string;
}

interface CustomMenuResponse {
  is_build_in: boolean;
  menus: MenuNode[];
}

const BUSINESS_CLIENTS = Array.from(
  new Set(Object.values(MODULE_CONFIG).map(({ client }) => client)),
) as BusinessClient[];

function unwrap<T>(response: ApiEnvelope<T>, fallbackMessage: string): T {
  if (!response?.result) throw new Error(response?.message || fallbackMessage);
  return response.data;
}

async function loadCustomMenus(client: BusinessClient) {
  try {
    const response = await apiGet<ApiEnvelope<CustomMenuResponse>>(
      '/system_mgmt/custom_menu_group/get_menus/',
      { app: client },
    );
    const data = unwrap(response, `Failed to load custom menus for ${client}`);
    return {
      isBuiltIn: data.is_build_in,
      menus: Array.isArray(data.menus) ? data.menus : [],
    };
  } catch {
    // Web 对无启用自定义菜单（404）或读取失败均回退静态菜单。
    return undefined;
  }
}

export async function loadAvailabilityFacts(locale: string): Promise<AvailabilityFacts> {
  const [clientResponse, staticMenus, perClientFacts] = await Promise.all([
    apiGet<ApiEnvelope<ClientItem[]>>('/core/api/get_client/'),
    fetchWebJson<MenuNode[]>(`/api/menu?locale=${encodeURIComponent(locale)}`),
    Promise.all(BUSINESS_CLIENTS.map(async (client) => {
      const [menuResponse, customMenus] = await Promise.all([
        apiGet<ApiEnvelope<MenuNode[]>>('/core/api/get_user_menus/', { name: client }),
        loadCustomMenus(client),
      ]);
      return {
        client,
        userMenus: unwrap(menuResponse, `Failed to load user menus for ${client}`),
        customMenus,
      };
    })),
  ]);

  if (!Array.isArray(staticMenus) || staticMenus.length === 0) {
    throw new Error('Static Web menus are unavailable');
  }

  return {
    licensedClients: unwrap(clientResponse, 'Failed to load licensed clients')
      .map((client) => client.name),
    staticMenus,
    userMenusByClient: Object.fromEntries(
      perClientFacts.map(({ client, userMenus }) => [client, userMenus]),
    ),
    customMenusByClient: Object.fromEntries(
      perClientFacts
        .filter(({ customMenus }) => customMenus !== undefined)
        .map(({ client, customMenus }) => [client, customMenus]),
    ),
  };
}
