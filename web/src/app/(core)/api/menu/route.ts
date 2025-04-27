import { NextRequest, NextResponse } from 'next/server';
import path from 'path';
import fs from 'fs/promises';

const INSTALL_APPS = (process.env.NEXTAPI_INSTALL_APP || 'example').split(',').map(app => app.trim());

const getDynamicMenuItems = async (locale: string) => {
  const dirPath = path.join(process.cwd(), 'src', 'app');

  let allMenuItems: any[] = [];

  for (const app of INSTALL_APPS) {
    const menuPath = path.join(dirPath, app, 'constants', 'menu.json');

    try {
      await fs.access(menuPath);
      const menuContent = await fs.readFile(menuPath, 'utf-8');
      const menu = JSON.parse(menuContent);
      allMenuItems = allMenuItems.concat(menu[locale] || []);
    } catch (err) {
      console.error(`Failed to load menu for ${app}:`, err);
    }
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
