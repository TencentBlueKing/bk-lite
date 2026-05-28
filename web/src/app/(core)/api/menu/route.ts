import { NextRequest, NextResponse } from 'next/server';
import path from 'path';
import fs from 'fs/promises';
import { getInstallApps } from '../_utils/installApps';

const COMMUNITY_APP_ROOT = path.join(process.cwd(), 'src', 'app');
const ENTERPRISE_WEB_ROOT = process.env.ENTERPRISE_WEB_ROOT || '';
const ENTERPRISE_MENUS_MANIFEST_PATH = ENTERPRISE_WEB_ROOT
  ? path.join(ENTERPRISE_WEB_ROOT, 'manifests', 'menus.json')
  : '';

interface MenuPatch {
  target: string;
  children: any[];
}

const applyPatch = (items: any[], targetParts: string[], children: any[]): boolean => {
  const [head, ...rest] = targetParts;
  for (const item of items) {
    if (item.name !== head) {
      continue;
    }

    if (rest.length === 0) {
      item.children = [...(item.children || []), ...children];
      return true;
    }

    if (item.children && applyPatch(item.children, rest, children)) {
      return true;
    }
  }

  return false;
};

const applyPatches = (menuItems: any[], patches: MenuPatch[]) => {
  for (const patch of patches) {
    const applied = applyPatch(menuItems, patch.target.split('.'), patch.children);
    if (!applied) {
      console.warn(`[menu] patch target not found: ${patch.target}`);
    }
  }
};

const getDynamicMenuItems = async (locale: string) => {
  const installApps = await getInstallApps([COMMUNITY_APP_ROOT]);
  let allMenuItems: any[] = [];
  const allPatches: MenuPatch[] = [];

  for (const app of installApps) {
    const menuPath = path.join(COMMUNITY_APP_ROOT, app, 'constants', 'menu.json');

    try {
      await fs.access(menuPath);
      const menuContent = await fs.readFile(menuPath, 'utf-8');
      const menu = JSON.parse(menuContent);
      allMenuItems = allMenuItems.concat(menu[locale] || []);
      allPatches.push(...(menu[`${locale}_patches`] || []));
    } catch {
      // Silently skip if menu.json doesn't exist for this app
    }
  }

  try {
    if (!ENTERPRISE_MENUS_MANIFEST_PATH) {
      throw new Error('enterprise menus manifest path not configured');
    }
    await fs.access(ENTERPRISE_MENUS_MANIFEST_PATH);
    const enterpriseMenus = JSON.parse(await fs.readFile(ENTERPRISE_MENUS_MANIFEST_PATH, 'utf-8'));
    allMenuItems = allMenuItems.concat(enterpriseMenus[locale] || []);
    allPatches.push(...(enterpriseMenus[`${locale}_patches`] || []));
  } catch {
    // Silently skip if enterprise menus manifest doesn't exist
  }

  if (allPatches.length > 0) {
    applyPatches(allMenuItems, allPatches);
  }

  return allMenuItems;
};

const getFallbackMenuItems = async (locale: string) => {
  try {
    const localePath = path.join(process.cwd(), 'public', 'menus', `${locale}.json`);
    await fs.access(localePath);
    const menuContent = await fs.readFile(localePath, 'utf-8');
    const menus = JSON.parse(menuContent);
    return menus || [];
  } catch (err) {
    console.error(`Failed to load fallback menus for locale ${locale}:`, err);
    return [];
  }
};

export const GET = async (request: NextRequest) => {
  try {
    const { searchParams } = new URL(request.url);
    const locale = searchParams.get('locale') === 'en' ? 'en' : 'zh';

    let menuItems;

    try {
      menuItems = await getDynamicMenuItems(locale);
    } catch (error) {
      console.error('Error merging dynamic messages:', error);
    }

    if (!menuItems || menuItems.length === 0) {
      console.warn(`Fallback to public/menus for locale: ${locale}`);
      menuItems = await getFallbackMenuItems(locale);
    }

    return NextResponse.json(menuItems, { status: 200 });
  } catch (error) {
    console.error('Failed to load menus:', error);
    return NextResponse.json({ message: 'Failed to load menus', error }, { status: 500 });
  }
};

export const POST = async () => {
  return NextResponse.json({ message: 'Method Not Allowed' }, { status: 405 });
};
