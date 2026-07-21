import path from 'path';
import fs from 'fs-extra';

const EXCLUDED_DIRECTORIES = ['(core)', 'no-permission'];
const COMMUNITY_APP_ROOT = path.resolve(process.cwd(), 'src/app');
const ENTERPRISE_WEB_LINK = path.resolve(process.cwd(), 'enterprise');
const ENTERPRISE_WEB_ROOT = fs.existsSync(ENTERPRISE_WEB_LINK) ? fs.realpathSync(ENTERPRISE_WEB_LINK) : ENTERPRISE_WEB_LINK;
const COMMUNITY_APP_ROOTS = [COMMUNITY_APP_ROOT];
const ENTERPRISE_APP_ROOT = path.join(ENTERPRISE_WEB_ROOT, 'src/app');
const ENTERPRISE_MENUS_MANIFEST_PATH = path.join(ENTERPRISE_WEB_ROOT, 'manifests', 'menus.json');
const ENTERPRISE_PUBLIC_ROOT = path.join(ENTERPRISE_WEB_ROOT, 'public');

const getAppDirectories = async (rootPath) => {
  if (!(await fs.pathExists(rootPath))) {
    return [];
  }
  return fs.readdir(rootPath, { withFileTypes: true });
};

const buildAppPath = (rootPath, appName, targetDir) => path.join(rootPath, appName, targetDir);

const applyPatch = (items, targetParts, children) => {
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

const applyPatches = (menuItems, patches) => {
  for (const patch of patches) {
    if (!applyPatch(menuItems, patch.target.split('.'), patch.children)) {
      console.warn(`[menu] patch target not found: ${patch.target}`);
    }
  }
};

const mergeMessages = (target, source) => {
  for (const key in source) {
    if (source[key] instanceof Object && key in target) {
      Object.assign(source[key], mergeMessages(target[key], source[key]));
    }
  }
  Object.assign(target || {}, source);
  return target;
};

const flattenMessages = (nestedMessages, prefix = '') => {
  return Object.keys(nestedMessages).reduce((messages, key) => {
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

const combineLocales = async () => {
  const publicLocalesDir = path.resolve(process.cwd(), 'public/locales');

  const baseLocales = {
    en: await fs.readJSON(path.join(process.cwd(), 'src/locales/en.json')),
    zh: await fs.readJSON(path.join(process.cwd(), 'src/locales/zh.json')),
  };

  const mergedMessages = {
    en: flattenMessages(baseLocales.en),
    zh: flattenMessages(baseLocales.zh),
  };

  for (const rootPath of [COMMUNITY_APP_ROOT, ENTERPRISE_APP_ROOT]) {
    const apps = await getAppDirectories(rootPath);
    for (const app of apps) {
      if (app.isDirectory() && !EXCLUDED_DIRECTORIES.includes(app.name)) {
        const appLocalesDir = buildAppPath(rootPath, app.name, 'locales');
        for (const locale of ['en', 'zh']) {
          try {
            const filePath = path.join(appLocalesDir, `${locale}.json`);
            if (await fs.pathExists(filePath)) {
              const messages = flattenMessages(await fs.readJSON(filePath));
              mergedMessages[locale] = mergeMessages(mergedMessages[locale], messages);
            }
          } catch (error) {
            console.error(`Error loading locale for ${app.name}:`, error);
          }
        }
      }
    }
  }

  await fs.ensureDir(publicLocalesDir);

  await fs.writeJSON(path.join(publicLocalesDir, 'en.json'), mergedMessages.en, { spaces: 2 });
  await fs.writeJSON(path.join(publicLocalesDir, 'zh.json'), mergedMessages.zh, { spaces: 2 });

  console.log('Locales combined successfully to public/locales directory');
};

const combineMenus = async () => {
  const publicMenusDir = path.resolve(process.cwd(), 'public/menus');
  let allMenusEn = [];
  let allMenusZh = [];
  const allMenuPatchesEn = [];
  const allMenuPatchesZh = [];
  for (const rootPath of COMMUNITY_APP_ROOTS) {
    const directories = await getAppDirectories(rootPath);
    for (const dirent of directories) {
      if (dirent.isDirectory() && !EXCLUDED_DIRECTORIES.includes(dirent.name)) {
        try {
          const menuPath = buildAppPath(rootPath, dirent.name, 'constants/menu.json');
          if (await fs.pathExists(menuPath)) {
            const menu = await fs.readJSON(menuPath);
            allMenusEn = allMenusEn.concat(menu.en || []);
            allMenusZh = allMenusZh.concat(menu.zh || []);
            allMenuPatchesEn.push(...(menu.en_patches || []));
            allMenuPatchesZh.push(...(menu.zh_patches || []));
          }
        } catch (err) {
          console.error(`Failed to load menu for ${dirent.name}:`, err);
        }
      }
    }
  }
  if (await fs.pathExists(ENTERPRISE_MENUS_MANIFEST_PATH)) {
    const enterpriseMenus = await fs.readJSON(ENTERPRISE_MENUS_MANIFEST_PATH);
    allMenusEn = allMenusEn.concat(enterpriseMenus.en || []);
    allMenusZh = allMenusZh.concat(enterpriseMenus.zh || []);
    allMenuPatchesEn.push(...(enterpriseMenus.en_patches || []));
    allMenuPatchesZh.push(...(enterpriseMenus.zh_patches || []));
  }
  if (allMenuPatchesEn.length > 0) {
    applyPatches(allMenusEn, allMenuPatchesEn);
  }
  if (allMenuPatchesZh.length > 0) {
    applyPatches(allMenusZh, allMenuPatchesZh);
  }
  await fs.ensureDir(publicMenusDir);
  await fs.writeJSON(path.join(publicMenusDir, 'en.json'), allMenusEn, { spaces: 2 });
  await fs.writeJSON(path.join(publicMenusDir, 'zh.json'), allMenusZh, { spaces: 2 });
  console.log('Menus combined successfully to public/menus directory');
};

const copyPublicDirectories = ({
  communityAppRoots = COMMUNITY_APP_ROOTS,
  enterpriseAppRoot = ENTERPRISE_APP_ROOT,
  enterprisePublicRoot = ENTERPRISE_PUBLIC_ROOT,
  destinationRoot = path.resolve(process.cwd(), 'public', 'app'),
} = {}) => {
  const mainDestinationPath = destinationRoot;
  fs.emptyDirSync(mainDestinationPath);
  fs.ensureFileSync(path.join(mainDestinationPath, '.gitkeep'));

  [...communityAppRoots, enterpriseAppRoot].forEach(rootPath => {
    if (!fs.existsSync(rootPath)) {
      return;
    }

    const apps = fs.readdirSync(rootPath).filter(file =>
      fs.lstatSync(path.join(rootPath, file)).isDirectory() && !EXCLUDED_DIRECTORIES.includes(file)
    );

    apps.forEach(app => {
      const sourcePath = path.join(rootPath, app, 'public');
      const destinationPath = path.join(mainDestinationPath);

      if (fs.existsSync(sourcePath)) {
        try {
          fs.ensureDirSync(destinationPath);
          fs.copySync(sourcePath, destinationPath, {
            dereference: true,
            overwrite: true,
            filter: itemPath => path.basename(itemPath) !== '.DS_Store',
          });
          console.log(`Copied contents of ${sourcePath} to ${destinationPath}`);
        } catch (err) {
          console.error(`Failed to copy contents of ${sourcePath} to ${destinationPath}:`, err);
        }
      } else {
        console.log(`No public directory found for ${app}`);
      }
    });
  });

  if (fs.existsSync(enterprisePublicRoot)) {
    try {
      fs.copySync(enterprisePublicRoot, mainDestinationPath, {
        dereference: true,
        overwrite: true,
        filter: itemPath => path.basename(itemPath) !== '.DS_Store',
      });
      console.log(`Copied contents of ${enterprisePublicRoot} to ${mainDestinationPath}`);
    } catch (err) {
      console.error(`Failed to copy contents of ${enterprisePublicRoot} to ${mainDestinationPath}:`, err);
    }
  }
};

export { mergeMessages, flattenMessages, combineLocales, combineMenus, copyPublicDirectories };
