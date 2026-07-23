DIGITS = "0123456789"

def _normalize_name(value):
    result = value.strip().lower()
    for separator in [" ", "-", "/", "."]:
        result = result.replace(separator, "_")
    while "__" in result:
        result = result.replace("__", "_")
    return result.strip("_")

def _extract_index(value, prefixes):
    for prefix in prefixes:
        if not value.startswith(prefix):
            continue
        remainder = value[len(prefix):].lstrip("_")
        number = ""
        for character in remainder:
            if character not in DIGITS:
                break
            number += character
        if number:
            return number
    return ""

def _suffix_after_index(value, prefix):
    if not value.startswith(prefix):
        return ""
    remainder = value[len(prefix):].lstrip("_")
    offset = 0
    for character in remainder:
        if character not in DIGITS:
            break
        offset += 1
    return remainder[offset:].lstrip("_")

def _copy_tags(metric, raw_name):
    tags = {}
    for key, value in metric.tags.items():
        if key != "name" and key != "unit":
            tags[key] = value
    tags["raw_name"] = raw_name
    tags["profile"] = "generic"
    return tags

def _new_metric(metric, measurement, field, value, tags):
    normalized = Metric(measurement)
    for key, tag_value in tags.items():
        normalized.tags[key] = tag_value
    normalized.fields[field] = value
    normalized.time = metric.time
    return normalized

def _new_fields_metric(metric, measurement, fields, tags):
    normalized = Metric(measurement)
    for key, tag_value in tags.items():
        normalized.tags[key] = tag_value
    for key, field_value in fields.items():
        normalized.fields[key] = field_value
    normalized.time = metric.time
    return normalized

def _unknown_state_fields(metric):
    fields = {"status": 0 if metric.fields.get("status", 1) == 0 else -1, "state": -1}
    if "value" in metric.fields:
        fields["raw_state_code"] = metric.fields["value"]
    return fields

def _component_status_fields(metric):
    fields = {"status": metric.fields.get("status", -1), "state": -1}
    if "value" in metric.fields:
        fields["raw_state_code"] = metric.fields["value"]
    return fields

def _direction(name):
    if "pin" in name or "p_in" in name or "vin" in name or "v_in" in name or "ac_in" in name or "input" in name:
        return "input"
    if "pout" in name or "p_out" in name or "vout" in name or "v_out" in name or "dc_out" in name or "output" in name:
        return "output"
    return ""

def _temperature_sensor_id(name):
    if "inlet" in name:
        return "inlet"
    if "exhaust" in name or "outlet" in name:
        return "exhaust"
    if "heatsink" in name or "_hs_" in "_" + name + "_":
        return "heatsink"
    if "ambient" in name or "_amb_" in "_" + name + "_":
        return "ambient"
    return "temperature"

def _cpu_channel_slot(name):
    cpu_index = _extract_index(name, ["cpu"])
    suffix = _suffix_after_index(name, "cpu")
    slot_part = suffix.split("_")[0] if suffix else ""
    if cpu_index and len(slot_part) == 2 and slot_part[0] in "abcdefgh" and slot_part[1] in DIGITS:
        return "CPU" + cpu_index + "_" + slot_part.upper()
    if cpu_index and suffix.startswith("dimm_"):
        side = suffix[len("dimm_"):].split("_")[0]
        if side:
            return "CPU" + cpu_index + "_" + side.upper()
    return ""

def apply(metric):
    raw_name = metric.tags.get("name", "")
    name = _normalize_name(raw_name)
    unit = metric.tags.get("unit", "").strip().lower()
    psu_index = _extract_index(name, ["psu", "power_supply"])
    is_psu = name.startswith("psu") or name.startswith("power_supply")

    if is_psu and "value" in metric.fields:
        tags = _copy_tags(metric, raw_name)
        tags["component_id"] = "psu_" + psu_index if psu_index else "psu"
        if unit == "degrees_c":
            tags["sensor_id"] = _temperature_sensor_id(name)
            return [metric, _new_metric(metric, "ipmi_psu_temperature", "celsius", metric.fields["value"], tags)]
        if unit == "watts":
            direction = _direction(name)
            if direction:
                tags["direction"] = direction
            return [metric, _new_metric(metric, "ipmi_psu_power", "watts", metric.fields["value"], tags)]
        if unit == "volts":
            direction = _direction(name)
            if direction:
                tags["direction"] = direction
            return [metric, _new_metric(metric, "ipmi_psu_voltage", "volts", metric.fields["value"], tags)]
        if unit == "rpm" and "fan" in name:
            tags["sensor_id"] = "fan"
            return [metric, _new_metric(metric, "ipmi_psu_fan_speed", "rpm", metric.fields["value"], tags)]

    # PSU 主状态必须是部件本身或显式 Status，避免温度、功率等误入状态指标。
    is_psu_status = psu_index and (name.endswith("_status") or name in ["psu_" + psu_index, "power_supply_" + psu_index])
    if is_psu_status and "status" in metric.fields:
        tags = _copy_tags(metric, raw_name)
        tags["component_id"] = "psu_" + psu_index
        normalized = _new_fields_metric(metric, "ipmi_psu", _component_status_fields(metric), tags)
        return [metric, normalized]

    # CPU 名称中的内存通道（如 CPU0_A1）优先归入 DIMM，避免误算成 CPU 温度。
    channel_slot = _cpu_channel_slot(name)
    if channel_slot:
        tags = _copy_tags(metric, raw_name)
        normalized_slot = channel_slot.lower()
        tags["component_id"] = "dimm_" + normalized_slot
        tags["slot"] = channel_slot
        if unit == "degrees_c" and "value" in metric.fields:
            return [metric, _new_metric(metric, "ipmi_memory_temperature", "celsius", metric.fields["value"], tags)]
        if name.endswith("_status") and "status" in metric.fields:
            return [metric, _new_fields_metric(metric, "ipmi_memory", _component_status_fields(metric), tags)]

    dimm_index = _extract_index(name, ["dimm"])
    if dimm_index:
        tags = _copy_tags(metric, raw_name)
        tags["component_id"] = "dimm_" + dimm_index
        tags["slot"] = dimm_index
        dimm_suffix = _suffix_after_index(name, "dimm")
        if unit == "degrees_c" and "value" in metric.fields and "temp" in dimm_suffix:
            return [metric, _new_metric(metric, "ipmi_memory_temperature", "celsius", metric.fields["value"], tags)]
        if not dimm_suffix and "status" in metric.fields:
            return [metric, _new_fields_metric(metric, "ipmi_memory", _component_status_fields(metric), tags)]

    if name in ["mem_power", "memory_power"] and unit == "watts" and "value" in metric.fields:
        tags = _copy_tags(metric, raw_name)
        tags["component_id"] = "memory"
        return [metric, _new_metric(metric, "ipmi_memory_power", "watts", metric.fields["value"], tags)]

    cpu_rail_index = _extract_index(name, ["p"])
    if cpu_rail_index and name.endswith("_cpu") and unit == "volts" and "value" in metric.fields:
        tags = _copy_tags(metric, raw_name)
        tags["component_id"] = "cpu_" + cpu_rail_index
        tags["sensor_id"] = _suffix_after_index(name, "p").replace("_cpu", "")
        return [metric, _new_metric(metric, "ipmi_cpu_voltage", "volts", metric.fields["value"], tags)]

    cpu_index = _extract_index(name, ["cpu"])
    cpu_suffix = _suffix_after_index(name, "cpu")
    is_cpu = name.startswith("cpu")
    if is_cpu:
        tags = _copy_tags(metric, raw_name)
        tags["component_id"] = "cpu_" + cpu_index if cpu_index else "cpu"
        if cpu_index and cpu_suffix == "status" and "status" in metric.fields:
            return [metric, _new_fields_metric(metric, "ipmi_cpu", _component_status_fields(metric), tags)]
        if unit == "degrees_c" and "value" in metric.fields and (cpu_suffix == "temp" or cpu_suffix == "vr_temp"):
            tags["sensor_id"] = "vr" if cpu_suffix == "vr_temp" else "temperature"
            return [metric, _new_metric(metric, "ipmi_cpu_temperature", "celsius", metric.fields["value"], tags)]
        if unit == "watts" and "value" in metric.fields and ("power" in name or "pwr" in name):
            return [metric, _new_metric(metric, "ipmi_cpu_power", "watts", metric.fields["value"], tags)]
        if unit == "volts" and "value" in metric.fields:
            tags["sensor_id"] = cpu_suffix if cpu_suffix else "voltage"
            return [metric, _new_metric(metric, "ipmi_cpu_voltage", "volts", metric.fields["value"], tags)]
        if unit == "percent" and "value" in metric.fields and "utilization" in name:
            return [metric, _new_metric(metric, "ipmi_cpu_utilization", "percent", metric.fields["value"], tags)]

    drive_index = _extract_index(name, ["bp_disk", "bpdisk", "drive", "disk", "hdd"])
    if drive_index:
        drive_prefix = "bpdisk" if name.startswith("bpdisk") else "bp_disk" if name.startswith("bp_disk") else "drive" if name.startswith("drive") else "disk" if name.startswith("disk") else "hdd"
        drive_suffix = _suffix_after_index(name, drive_prefix)
        if not drive_suffix or drive_suffix == "status":
            tags = _copy_tags(metric, raw_name)
            tags["component_id"] = "drive_" + drive_index
            tags["slot"] = drive_index
            return [metric, _new_fields_metric(metric, "ipmi_disk", _unknown_state_fields(metric), tags)]

    if "hdd_power" in name and unit == "watts" and "value" in metric.fields:
        location = "front" if name.startswith("front_") else "rear" if name.startswith("rear_") else ""
        tags = _copy_tags(metric, raw_name)
        tags["component_id"] = "disk_" + location if location else "disk"
        if location:
            tags["location"] = location
        return [metric, _new_metric(metric, "ipmi_disk_power", "watts", metric.fields["value"], tags)]

    raid_index = _extract_index(name, ["raid_card", "raid"])
    if name.startswith("raid"):
        tags = _copy_tags(metric, raw_name)
        tags["component_id"] = "raid_" + raid_index if raid_index else "raid"
        if "bbu" in name or "battery" in name:
            tags["battery_id"] = "bbu" if "bbu" in name else "battery"
            if unit == "degrees_c" and "value" in metric.fields:
                return [metric, _new_metric(metric, "ipmi_raid_battery_temperature", "celsius", metric.fields["value"], tags)]
        if unit == "degrees_c" and "value" in metric.fields:
            return [metric, _new_metric(metric, "ipmi_raid_temperature", "celsius", metric.fields["value"], tags)]
        if name.startswith("raid_card") and "status" in metric.fields:
            return [metric, _new_fields_metric(metric, "ipmi_raid", _unknown_state_fields(metric), tags)]

    if name == "fan_power" and unit == "watts" and "value" in metric.fields:
        tags = _copy_tags(metric, raw_name)
        tags["component_id"] = "fan"
        return [metric, _new_metric(metric, "ipmi_fan_power", "watts", metric.fields["value"], tags)]

    fan_index = _extract_index(name, ["fan"])
    if fan_index:
        tags = _copy_tags(metric, raw_name)
        tags["component_id"] = "fan_" + fan_index
        if unit == "rpm" and "value" in metric.fields:
            tags["sensor_id"] = "front" if "front" in name else "rear" if "rear" in name else "fan"
            return [metric, _new_metric(metric, "ipmi_fan_component_speed", "rpm", metric.fields["value"], tags)]
        if ("present" in name or "status" in name) and "status" in metric.fields:
            return [metric, _new_fields_metric(metric, "ipmi_fan", _unknown_state_fields(metric), tags)]

    if "value" in metric.fields:
        tags = _copy_tags(metric, raw_name)
        tags["component_id"] = "chassis"
        if unit == "degrees_c" and ("inlet" in name or "exhaust" in name or "outlet" in name or "ambient" in name):
            tags["location"] = "inlet" if "inlet" in name else "exhaust" if ("exhaust" in name or "outlet" in name) else "ambient"
            return [metric, _new_metric(metric, "ipmi_chassis_temperature", "celsius", metric.fields["value"], tags)]
        if unit == "cfm" and ("air_flow" in name or "airflow" in name):
            return [metric, _new_metric(metric, "ipmi_chassis_airflow", "cfm", metric.fields["value"], tags)]
        if unit == "watts" and (name.startswith("system_power") or name.startswith("sys_power")):
            return [metric, _new_metric(metric, "ipmi_chassis_power", "watts", metric.fields["value"], tags)]

    return metric
