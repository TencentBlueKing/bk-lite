def resolve_collection_regions(selected_region, regions):
    selected_region = str(selected_region or "").strip()
    if selected_region:
        return [selected_region]

    return [
        region.get("Region")
        for region in regions
        if region.get("RegionState") == "AVAILABLE" and region.get("Region")
    ]
