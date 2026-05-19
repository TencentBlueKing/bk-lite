from plugins.inputs.storage.brands.oceanstor import OceanStorBrandCollector

BRAND_REGISTRY = {
    "oceanstor": OceanStorBrandCollector,
}


def get_brand_collector(brand: str):
    return BRAND_REGISTRY.get(brand)
