// 占位文件:由 web/scripts/prepare-enterprise.mjs 在企业版模式下重写为 EE 端
// enterpriseBrands(20 条 storage BRANDS)。社区模式下不重写,空数组生效。
// CE 端 getPluginBrandIcon/getBrandLabel 不直接 import 该文件(通过 window 读取),
// 本文件存在仅为显式声明类型与对 prepare-enterprise.mjs 提供覆盖目标。
// 加此注释避免误以为冗余。

export const enterpriseBrands: Array<{ match: RegExp; label: string; icon?: string }> = []