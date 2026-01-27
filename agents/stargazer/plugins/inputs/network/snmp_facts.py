# -- coding: utf-8 --
# @File: snmp_facts.py
# @Time: 2025/3/20 17:30
# @Author: windyzhao

import socket
from pysnmp.entity.rfc3413.oneliner import cmdgen
from pysnmp.hlapi import usmHMACSHAAuthProtocol, usmHMACMD5AuthProtocol, usmAesCfb128Protocol, usmDESPrivProtocol
from sanic.log import logger

class DefineOid:
    """
    定义常用的 SNMP OID，用于采集设备的系统信息、接口信息和 IP 信息。
    """

    def __init__(self, dotprefix=False):
        dp = "." if dotprefix else ""
        # 系统信息 OIDs
        self.sysDescr = dp + "1.3.6.1.2.1.1.1.0"
        self.sysObjectId = dp + "1.3.6.1.2.1.1.2.0"
        # self.sysUpTime = dp + "1.3.6.1.2.1.1.3.0"
        self.sysContact = dp + "1.3.6.1.2.1.1.4.0"
        self.sysName = dp + "1.3.6.1.2.1.1.5.0"
        self.sysLocation = dp + "1.3.6.1.2.1.1.6.0"

        # 接口信息 OIDs
        self.ifIndex = dp + "1.3.6.1.2.1.2.2.1.1"
        self.ifDescr = dp + "1.3.6.1.2.1.2.2.1.2"
        self.ifMtu = dp + "1.3.6.1.2.1.2.2.1.4"
        self.ifSpeed = dp + "1.3.6.1.2.1.2.2.1.5"
        self.ifPhysAddress = dp + "1.3.6.1.2.1.2.2.1.6"
        self.ifAdminStatus = dp + "1.3.6.1.2.1.2.2.1.7"
        self.ifOperStatus = dp + "1.3.6.1.2.1.2.2.1.8"
        self.ifAlias = dp + "1.3.6.1.2.1.31.1.1.1.18"


class SnmpFacts:
    """
    SNMP 数据采集类，支持 SNMP v2 和 v3 协议。
    """

    def __init__(self, kwargs):
        # 初始化参数
        self.kwargs = kwargs
        self.host = kwargs.get('host')
        self.version = kwargs.get('version')
        self.community = kwargs.get('community')
        self.username = kwargs.get('username')
        self.level = kwargs.get('level')
        self.integrity = kwargs.get('integrity')
        self.privacy = kwargs.get('privacy')
        self.authkey = kwargs.get('authkey')
        self.privkey = kwargs.get('privkey')
        self.timeout = int(kwargs.get('timeout', 1))
        self.retries = int(kwargs.get('retries', 1))
        self.snmp_port = int(kwargs.get('snmp_port', 161))  # 默认 SNMP 端口为 161
        self.topo = kwargs.get('topo', False)

        # 校验参数
        self._validate_params()

    def _validate_params(self):
        """
        校验传入的参数是否合法。
        """
        if not self.host:
            raise ValueError("Host is required.")
        try:
            socket.gethostbyname(self.host)
        except socket.error:
            raise ValueError("Invalid host or IP address.")
        if self.version not in ['v2', 'v2c', 'v3']:
            raise ValueError("Invalid SNMP version. Must be 'v2', 'v2c', or 'v3'.")
        if self.version in ['v2', 'v2c'] and not self.community:
            raise ValueError("Community is required for SNMP version 2.")
        if self.version == 'v3':
            if not self.username:
                raise ValueError("Username is required for SNMP version 3.")
            if self.level == "authPriv" and not self.privacy:
                raise ValueError("Privacy algorithm is required for authPriv level.")
            if len(self.authkey) < 8 or len(self.privkey) < 8:
                raise ValueError("authkey and privkey must be at least 8 characters long.")
        if not (1 <= self.snmp_port <= 65535):
            raise ValueError("Invalid SNMP port. Must be between 1 and 65535.")

    def _get_snmp_auth(self):
        """
        根据 SNMP 版本和认证参数生成认证对象。
        """
        if self.version in ['v2', 'v2c']:
            return cmdgen.CommunityData(self.community)
        elif self.level == "authNoPriv":
            return cmdgen.UsmUserData(self.username, authKey=self.authkey, authProtocol=self._get_integrity_proto())
        else:
            return cmdgen.UsmUserData(
                self.username,
                authKey=self.authkey,
                privKey=self.privkey,
                authProtocol=self._get_integrity_proto(),
                privProtocol=self._get_privacy_proto()
            )

    def _get_integrity_proto(self):
        """
        获取 SNMP v3 的认证协议。
        """
        if self.integrity == "sha":
            return usmHMACSHAAuthProtocol
        elif self.integrity == "md5":
            return usmHMACMD5AuthProtocol
        return None

    def _get_privacy_proto(self):
        """
        获取 SNMP v3 的隐私协议。
        """
        if self.privacy == "aes":
            return usmAesCfb128Protocol
        elif self.privacy == "des":
            return usmDESPrivProtocol
        return None

    def collect(self):
        """
        采集 SNMP 数据，包括系统信息、接口信息和 IP 信息。
        """
        cmdGen = cmdgen.CommandGenerator()
        transport_opts = {'timeout': self.timeout, 'retries': self.retries}
        snmp_auth = self._get_snmp_auth()

        # 定义 OID
        p = DefineOid(dotprefix=True)
        v = DefineOid(dotprefix=False)

        # 初始化结果字典
        results = {
            'system': {},
            'interfaces': []  # 确保 interfaces 是一个列表
        }

        # 采集系统信息
        try:
            errorIndication, errorStatus, errorIndex, varBinds = cmdGen.getCmd(
                snmp_auth,
                cmdgen.UdpTransportTarget((self.host, self.snmp_port), **transport_opts),
                cmdgen.MibVariable(p.sysDescr),
                cmdgen.MibVariable(p.sysObjectId),
                # cmdgen.MibVariable(p.sysUpTime),
                cmdgen.MibVariable(p.sysContact),
                cmdgen.MibVariable(p.sysName),
                cmdgen.MibVariable(p.sysLocation),
                lookupMib=False
            )
            if errorIndication:
                raise RuntimeError(f"SNMP getCmd failed: {errorIndication}")

            for oid, val in varBinds:
                current_oid = oid.prettyPrint()
                current_val = val.prettyPrint()
                if current_oid == v.sysDescr:
                    try:
                        current_val = val._value.decode()
                    except Exception:
                        current_val = str(current_val)
                    results['system']['sysdescr'] = current_val
                elif current_oid == v.sysObjectId:
                    results['system']['sysobjectid'] = current_val
                # elif current_oid == v.sysUpTime:
                #     results['system']['sysuptime'] = current_val
                elif current_oid == v.sysContact:
                    results['system']['syscontact'] = current_val
                elif current_oid == v.sysName:
                    results['system']['sysname'] = current_val
                elif current_oid == v.sysLocation:
                    results['system']['syslocation'] = current_val

            results['system']['ip_addr'] = self.host
            results['system']['port'] = self.snmp_port
        except Exception as e:
            raise RuntimeError(f"Error during SNMP system information collection: {str(e)}")

        # 采集接口和 IP 信息
        try:
            errorIndication, errorStatus, errorIndex, varTable = cmdGen.nextCmd(
                snmp_auth,
                cmdgen.UdpTransportTarget((self.host, self.snmp_port), **transport_opts),
                cmdgen.MibVariable(p.ifIndex),
                cmdgen.MibVariable(p.ifDescr),
                cmdgen.MibVariable(p.ifMtu),
                cmdgen.MibVariable(p.ifSpeed),
                cmdgen.MibVariable(p.ifPhysAddress),
                cmdgen.MibVariable(p.ifAdminStatus),
                cmdgen.MibVariable(p.ifOperStatus),
                cmdgen.MibVariable(p.ifAlias),
                lookupMib=False
            )
            if errorIndication:
                raise RuntimeError(f"SNMP nextCmd failed: {errorIndication}")

            for varBinds in varTable:
                interface = {}
                for oid, val in varBinds:
                    current_oid = oid.prettyPrint()
                    current_val = val.prettyPrint()
                    if current_oid.startswith(v.ifIndex):
                        interface['index'] = current_val
                    elif current_oid.startswith(v.ifDescr):
                        interface['description'] = current_val
                    elif current_oid.startswith(v.ifMtu):
                        interface['mtu'] = current_val
                    elif current_oid.startswith(v.ifSpeed):
                        interface['speed'] = current_val
                    elif current_oid.startswith(v.ifPhysAddress):
                        interface['mac_address'] = current_val
                    elif current_oid.startswith(v.ifAdminStatus):
                        interface['admin_status'] = current_val
                    elif current_oid.startswith(v.ifOperStatus):
                        interface['oper_status'] = current_val
                    elif current_oid.startswith(v.ifAlias):
                        interface['alias'] = current_val
                if interface:
                    results['interfaces'].append(interface)
        except Exception as e:
            raise RuntimeError(f"Error during SNMP interface information collection: {str(e)}")

        return results

    def list_all_resources(self):
        """
        将采集到的 SNMP 数据转换为标准格式。
        """
        try:
            snmp_data = self.collect()
            system_data = snmp_data.get('system', {})
            interfaces_data = snmp_data.get('interfaces', [])
            model_data = {
                "network_system": [system_data],
                "network_interfaces": interfaces_data
            }
            inst_data = {"result": model_data, "success": True}
        except Exception as err:
            import traceback
            logger.error(f"snmp_facts collect error! {traceback.format_exc()}")
            inst_data = {"result": {"cmdb_collect_error": str(err)}, "success": False}
        
        return inst_data
