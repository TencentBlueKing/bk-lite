import { prepareEnterpriseRoutes } from './prepare-enterprise.mjs';
import {
  combineLocales,
  combineMenus,
  copyPublicDirectories,
} from '../src/utils/dynamicsMerged.mjs';

export async function prepareBuildAssets() {
  await prepareEnterpriseRoutes();
  await combineLocales();
  await combineMenus();
  copyPublicDirectories();
}
