import { NextRequest, NextResponse } from 'next/server';
import path from 'path';
import fs from 'fs/promises';

const INSTALL_APPS = (process.env.NEXTAPI_INSTALL_APP || 'example').split(',').map(app => app.trim());

interface NestedMessages {
  [key: string]: string | NestedMessages;
}

const flattenMessages = (nestedMessages: NestedMessages, prefix = ''): { [key: string]: string } => {
  return Object.keys(nestedMessages).reduce((messages: { [key: string]: string }, key: string) => {
    const value = nestedMessages[key];
    const prefixedKey = prefix ? `${prefix}.${key}` : key;

    if (typeof value === 'string') {
      messages[prefixedKey] = value;
    } else {
      Object.assign(messages, flattenMessages(value, prefixedKey));
    }

    return messages;
  }, {});
};

const deepMerge = (target: any, source: any) => {
  for (const key in source) {
    if (source[key] instanceof Object && key in target) {
      Object.assign(source[key], deepMerge(target[key], source[key]));
    }
  }
  Object.assign(target || {}, source);
  return target;
};

const getMergedMessages = async () => {
  const localesDir = path.resolve(process.cwd(), 'src', 'app');

  const baseEnMessages = JSON.parse(await fs.readFile(path.resolve(process.cwd(), 'src', 'locales', 'en.json'), 'utf8'));
  const baseZhMessages = JSON.parse(await fs.readFile(path.resolve(process.cwd(), 'src', 'locales', 'zh.json'), 'utf8'));

  const baseMessages = {
    en: flattenMessages(baseEnMessages),
    zh: flattenMessages(baseZhMessages)
  };

  type Locale = 'en' | 'zh';

  const mergedMessages: { [key in Locale]: any } = {
    en: { ...baseMessages.en },
    zh: { ...baseMessages.zh },
  };

  // 遍历所有配置的安装应用
  for (const app of INSTALL_APPS) {
    const appLocalesDir = path.join(localesDir, app, 'locales');

    for (const locale of ['en', 'zh']) {
      try {
        const filePath = path.join(appLocalesDir, `${locale}.json`);
        await fs.access(filePath);

        const messages = flattenMessages(JSON.parse(await fs.readFile(filePath, 'utf8')));
        mergedMessages[locale as Locale] = deepMerge(mergedMessages[locale as Locale], messages);
      } catch (error) {
        console.error(`Error loading locale for ${app}:`, error);
      }
    }
  }

  return mergedMessages;
};

const getFallbackLocale = async (locale: string): Promise<any> => {
  try {
    const localePath = path.resolve(process.cwd(), 'public', 'locales', `${locale}.json`);
    const fallbackMessages = JSON.parse(await fs.readFile(localePath, 'utf8'));
    return flattenMessages(fallbackMessages);
  } catch (error) {
    console.error(`Failed to load fallback locale (${locale}) from public/locales:`, error);
    return null;
  }
};

export const GET = async (request: NextRequest) => {
  try {
    const { searchParams } = new URL(request.url);
    const locale = searchParams.get('locale') === 'en' ? 'en' : 'zh';
    let mergedMessages;

    try {
      mergedMessages = await getMergedMessages();
    } catch (error) {
      console.error('Error merging dynamic messages:', error);
    }

    if (!mergedMessages || !mergedMessages[locale]) {
      console.warn(`Falling back to public/locales for locale: ${locale}`);
      const fallbackMessages = await getFallbackLocale(locale);
      if (!fallbackMessages) {
        throw new Error(`Failed to load fallback locale: ${locale}`);
      }
      return NextResponse.json(fallbackMessages, { status: 200 });
    }

    return NextResponse.json(mergedMessages[locale], { status: 200 });
  } catch (error) {
    console.error('Failed to load locales:', error);
    return NextResponse.json({ message: 'Failed to load locales', error }, { status: 500 });
  }
};

export const POST = async () => {
  return NextResponse.json({ message: 'Method Not Allowed' }, { status: 405 });
};
