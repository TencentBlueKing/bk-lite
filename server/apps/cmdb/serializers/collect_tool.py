# -- coding: utf-8 --
# @File: collect_tool.py
# @Time: 2026/05/08
import re

from rest_framework import serializers


class SnmpCredentialSerializer(serializers.Serializer):
    version = serializers.ChoiceField(choices=["v2", "v2c", "v3"])
    community = serializers.CharField(required=False, allow_blank=True)
    username = serializers.CharField(required=False, allow_blank=True)
    level = serializers.ChoiceField(choices=["authNoPriv", "authPriv"], required=False)
    integrity = serializers.ChoiceField(choices=["sha", "md5"], required=False)
    authkey = serializers.CharField(required=False, allow_blank=True)
    privacy = serializers.ChoiceField(choices=["aes", "des"], required=False)
    privkey = serializers.CharField(required=False, allow_blank=True)

    def validate(self, data):
        version = data.get("version")
        if version in ("v2", "v2c"):
            if not data.get("community"):
                raise serializers.ValidationError("SNMP v2/v2c 需要填写 community")
        elif version == "v3":
            if not data.get("username"):
                raise serializers.ValidationError("SNMP v3 需要填写 username")
            level = data.get("level")
            if not level:
                raise serializers.ValidationError("SNMP v3 需要填写 level")
            if not data.get("integrity"):
                raise serializers.ValidationError("SNMP v3 需要填写 integrity")
            if not data.get("authkey"):
                raise serializers.ValidationError("SNMP v3 需要填写 authkey")
            if level == "authPriv":
                if not data.get("privacy"):
                    raise serializers.ValidationError("SNMP v3 authPriv 需要填写 privacy")
                if not data.get("privkey"):
                    raise serializers.ValidationError("SNMP v3 authPriv 需要填写 privkey")
        return data


class IpmiCredentialSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField()
    privilege = serializers.ChoiceField(choices=["callback", "user", "operator", "administrator"], required=False)
    cipher_suite = serializers.CharField(required=False, allow_blank=True)


class CollectToolExecuteSerializer(serializers.Serializer):
    protocol = serializers.ChoiceField(choices=["snmp", "ipmi"])
    action = serializers.ChoiceField(choices=["test_connection", "raw_collect", "get_oid", "ipmi_collect"])
    access_point_id = serializers.CharField()
    target = serializers.IPAddressField()
    port = serializers.IntegerField(min_value=1, max_value=65535)
    credential = serializers.DictField()
    oid = serializers.CharField(required=False, allow_blank=True)
    task_id = serializers.IntegerField(required=False)

    def validate(self, data):
        protocol = data.get("protocol")
        action = data.get("action")

        # Validate action matches protocol
        snmp_actions = {"test_connection", "raw_collect", "get_oid"}
        ipmi_actions = {"test_connection", "ipmi_collect"}

        if protocol == "snmp" and action not in snmp_actions:
            raise serializers.ValidationError(f"SNMP 协议不支持 action={action}")
        if protocol == "ipmi" and action not in ipmi_actions:
            raise serializers.ValidationError(f"IPMI 协议不支持 action={action}")

        # Validate OID for get_oid
        if protocol == "snmp" and action == "get_oid":
            oid = data.get("oid")
            if not oid:
                raise serializers.ValidationError("action=get_oid 时 oid 为必填项")
            if not re.match(r"^[\d.]+$", oid):
                raise serializers.ValidationError("OID 格式不正确，只允许数字和点号")

        # Validate credential
        credential = data.get("credential", {})
        if protocol == "snmp":
            cred_serializer = SnmpCredentialSerializer(data=credential)
            cred_serializer.is_valid(raise_exception=True)
        elif protocol == "ipmi":
            cred_serializer = IpmiCredentialSerializer(data=credential)
            cred_serializer.is_valid(raise_exception=True)

        return data


class CollectToolPrefillRequestSerializer(serializers.Serializer):
    task_id = serializers.IntegerField()
    protocol = serializers.ChoiceField(choices=["snmp", "ipmi"])


class CollectToolResultRequestSerializer(serializers.Serializer):
    debug_id = serializers.CharField()
