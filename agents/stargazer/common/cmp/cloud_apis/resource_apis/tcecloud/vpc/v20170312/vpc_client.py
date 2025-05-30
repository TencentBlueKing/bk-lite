# -*- coding: utf8 -*-
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import json

from common.cmp.cloud_apis.resource_apis.tcecloud.common.abstract_client import AbstractClient
from common.cmp.cloud_apis.resource_apis.tcecloud.common.exception.tce_cloud_sdk_exception import TceCloudSDKException
from common.cmp.cloud_apis.resource_apis.tcecloud.vpc.v20170312 import models


class VpcClient(AbstractClient):
    _apiVersion = "2017-03-12"
    _endpoint = "vpc.api3.{{conf.main_domain}}"

    def AcceptAttachCcnInstances(self, request):
        """本接口（AcceptAttachCcnInstances）用于跨账号关联实例时，云联网所有者接受并同意关联操作。

        :param request: 调用AcceptAttachCcnInstances所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.AcceptAttachCcnInstancesRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.AcceptAttachCcnInstancesResponse`

        """
        try:
            params = request._serialize()
            body = self.call("AcceptAttachCcnInstances", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.AcceptAttachCcnInstancesResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def AddBandwidthPackageResources(self, request):
        """接口用于添加带宽包资源，包括弹性公网IP和负载均衡等

        :param request: 调用AddBandwidthPackageResources所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.AddBandwidthPackageResourcesRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.AddBandwidthPackageResourcesResponse`

        """
        try:
            params = request._serialize()
            body = self.call("AddBandwidthPackageResources", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.AddBandwidthPackageResourcesResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def AddIp6Rules(self, request):
        """1. 该接口用于在转换实例下添加IPV6转换规则。
        2. 支持在同一个转换实例下批量添加转换规则，一个账户在一个地域最多50个。
        3. 一个完整的转换规则包括vip6:vport6:protocol:vip:vport，其中vip6:vport6:protocol必须是唯一。

        :param request: 调用AddIp6Rules所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.AddIp6RulesRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.AddIp6RulesResponse`

        """
        try:
            params = request._serialize()
            body = self.call("AddIp6Rules", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.AddIp6RulesResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def AdjustPublicAddress(self, request):
        """更换公网IP

        :param request: 调用AdjustPublicAddress所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.AdjustPublicAddressRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.AdjustPublicAddressResponse`

        """
        try:
            params = request._serialize()
            body = self.call("AdjustPublicAddress", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.AdjustPublicAddressResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def AllocateAddresses(self, request):
        """本接口 (AllocateAddresses) 用于申请一个或多个弹性公网IP（简称 EIP）。
        * EIP 是专为动态云计算设计的静态 IP 地址。借助 EIP，您可以快速将 EIP 重新映射到您的另一个实例上，从而屏蔽实例故障。
        * 您的 EIP 与Tce账户相关联，而不是与某个实例相关联。在您选择显式释放该地址，或欠费超过24小时之前，它会一直与您的Tce账户保持关联。
        * 一个Tce账户在每个地域能申请的 EIP 最大配额有所限制，可参见 EIP 产品简介，上述配额可通过 DescribeAddressQuota 接口获取。

        :param request: 调用AllocateAddresses所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.AllocateAddressesRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.AllocateAddressesResponse`

        """
        try:
            params = request._serialize()
            body = self.call("AllocateAddresses", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.AllocateAddressesResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def AllocateIp6AddressesBandwidth(self, request):
        """该接口用于给IPv6地址初次分配公网带宽

        :param request: 调用AllocateIp6AddressesBandwidth所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.AllocateIp6AddressesBandwidthRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.AllocateIp6AddressesBandwidthResponse`

        """
        try:
            params = request._serialize()
            body = self.call("AllocateIp6AddressesBandwidth", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.AllocateIp6AddressesBandwidthResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def AssignIpv6Addresses(self, request):
        """本接口（AssignIpv6Addresses）用于弹性网卡申请`IPv6`地址。<br />
        本接口是异步完成，如需查询异步任务执行结果，请使用本接口返回的`RequestId`轮询`QueryTask`接口。
        * 一个弹性网卡支持绑定的IP地址是有限制的，更多资源限制信息详见弹性网卡使用限制。
        * 可以指定`IPv6`地址申请，地址类型不能为主`IP`，`IPv6`地址暂时只支持作为辅助`IP`。
        * 地址必须要在弹性网卡所在子网内，而且不能被占用。
        * 在弹性网卡上申请一个到多个辅助`IPv6`地址，接口会在弹性网卡所在子网段内返回指定数量的辅助`IPv6`地址。

        :param request: 调用AssignIpv6Addresses所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.AssignIpv6AddressesRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.AssignIpv6AddressesResponse`

        """
        try:
            params = request._serialize()
            body = self.call("AssignIpv6Addresses", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.AssignIpv6AddressesResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def AssignIpv6CidrBlock(self, request):
        """本接口（AssignIpv6CidrBlock）用于分配IPv6网段。
        * 使用本接口前，您需要已有VPC实例，如果没有可通过接口CreateVpc创建。
        * 每个VPC只能申请一个IPv6网段

        :param request: 调用AssignIpv6CidrBlock所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.AssignIpv6CidrBlockRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.AssignIpv6CidrBlockResponse`

        """
        try:
            params = request._serialize()
            body = self.call("AssignIpv6CidrBlock", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.AssignIpv6CidrBlockResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def AssignIpv6SubnetCidrBlock(self, request):
        """本接口（AssignIpv6SubnetCidrBlock）用于分配IPv6子网段。
        * 给子网分配 `IPv6` 网段，要求子网所属 `VPC` 已获得 `IPv6` 网段。如果尚未分配，请先通过接口 `AssignIpv6CidrBlock` 给子网所属 `VPC` 分配一个 `IPv6` 网段。否则无法分配 `IPv6` 子网段。
        * 每个子网只能分配一个IPv6网段。

        :param request: 调用AssignIpv6SubnetCidrBlock所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.AssignIpv6SubnetCidrBlockRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.AssignIpv6SubnetCidrBlockResponse`

        """
        try:
            params = request._serialize()
            body = self.call("AssignIpv6SubnetCidrBlock", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.AssignIpv6SubnetCidrBlockResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def AssignPrivateIpAddresses(self, request):
        """本接口（AssignPrivateIpAddresses）用于弹性网卡申请内网 IP。
        * 一个弹性网卡支持绑定的IP地址是有限制的，更多资源限制信息详见弹性网卡使用限制。
        * 可以指定内网IP地址申请，内网IP地址类型不能为主IP，主IP已存在，不能修改，内网IP必须要弹性网卡所在子网内，而且不能被占用。
        * 在弹性网卡上申请一个到多个辅助内网IP，接口会在弹性网卡所在子网网段内返回指定数量的辅助内网IP。

        :param request: 调用AssignPrivateIpAddresses所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.AssignPrivateIpAddressesRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.AssignPrivateIpAddressesResponse`

        """
        try:
            params = request._serialize()
            body = self.call("AssignPrivateIpAddresses", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.AssignPrivateIpAddressesResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def AssociateAddress(self, request):
        """本接口 (AssociateAddress) 用于将弹性公网IP（简称 EIP）绑定到实例或弹性网卡的指定内网 IP 上。
        * 将 EIP 绑定到实例（CVM）上，其本质是将 EIP 绑定到实例上主网卡的主内网 IP 上。
        * 将 EIP 绑定到主网卡的主内网IP上，绑定过程会把其上绑定的普通公网 IP 自动解绑并释放。
        * 将 EIP 绑定到指定网卡的内网 IP上（非主网卡的主内网IP），则必须先解绑该 EIP，才能再绑定新的。
        * 将 EIP 绑定到NAT网关，请使用接口EipBindNatGateway
        * EIP 如果欠费或被封堵，则不能被绑定。
        * 只有状态为 UNBIND 的 EIP 才能够被绑定。

        :param request: 调用AssociateAddress所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.AssociateAddressRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.AssociateAddressResponse`

        """
        try:
            params = request._serialize()
            body = self.call("AssociateAddress", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.AssociateAddressResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def AssociateNatGatewayAddress(self, request):
        """本接口(AssociateNatGatewayAddress)用于NAT网关绑定弹性IP（EIP）。

        :param request: 调用AssociateNatGatewayAddress所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.AssociateNatGatewayAddressRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.AssociateNatGatewayAddressResponse`

        """
        try:
            params = request._serialize()
            body = self.call("AssociateNatGatewayAddress", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.AssociateNatGatewayAddressResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def AssociateNetworkAclSubnets(self, request):
        """本接口（AssociateNetworkAclSubnets）用于网络ACL关联vpc下的子网。

        :param request: 调用AssociateNetworkAclSubnets所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.AssociateNetworkAclSubnetsRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.AssociateNetworkAclSubnetsResponse`

        """
        try:
            params = request._serialize()
            body = self.call("AssociateNetworkAclSubnets", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.AssociateNetworkAclSubnetsResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def AssociateNetworkInterfaceSecurityGroups(self, request):
        """本接口（AssociateNetworkInterfaceSecurityGroups）用于弹性网卡绑定安全组（SecurityGroup）。

        :param request: 调用AssociateNetworkInterfaceSecurityGroups所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.AssociateNetworkInterfaceSecurityGroupsRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.AssociateNetworkInterfaceSecurityGroupsResponse`

        """
        try:
            params = request._serialize()
            body = self.call("AssociateNetworkInterfaceSecurityGroups", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.AssociateNetworkInterfaceSecurityGroupsResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def AttachCcnInstances(self, request):
        """本接口（AttachCcnInstances）用于将网络实例加载到云联网实例中，网络实例包括VPC和专线网关。<br />
        每个云联网能够关联的网络实例个数是有限的，详请参考产品文档。如果需要扩充请联系在线客服。

        :param request: 调用AttachCcnInstances所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.AttachCcnInstancesRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.AttachCcnInstancesResponse`

        """
        try:
            params = request._serialize()
            body = self.call("AttachCcnInstances", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.AttachCcnInstancesResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def AttachClassicLinkVpc(self, request):
        """本接口(AttachClassicLinkVpc)用于创建私有网络和基础网络设备互通。
        * 私有网络和基础网络设备必须在同一个地域。
        * 私有网络和基础网络的区别详见vpc产品文档-私有网络与基础网络。

        :param request: 调用AttachClassicLinkVpc所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.AttachClassicLinkVpcRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.AttachClassicLinkVpcResponse`

        """
        try:
            params = request._serialize()
            body = self.call("AttachClassicLinkVpc", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.AttachClassicLinkVpcResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def AttachNetworkInterface(self, request):
        """本接口（AttachNetworkInterface）用于弹性网卡绑定云主机。
        * 一个云主机可以绑定多个弹性网卡，但只能绑定一个主网卡。更多限制信息详见弹性网卡使用限制。
        * 一个弹性网卡只能同时绑定一个云主机。
        * 只有运行中或者已关机状态的云主机才能绑定弹性网卡，查看云主机状态详见Tce主机信息。
        * 弹性网卡绑定的云主机必须是私有网络的，而且云主机所在可用区必须和弹性网卡子网的可用区相同。

        :param request: 调用AttachNetworkInterface所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.AttachNetworkInterfaceRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.AttachNetworkInterfaceResponse`

        """
        try:
            params = request._serialize()
            body = self.call("AttachNetworkInterface", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.AttachNetworkInterfaceResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def BandwidthLimitForCcnAlarmOnly(self, request):
        """云联网查看带宽上限监控告警接入专用

        :param request: 调用BandwidthLimitForCcnAlarmOnly所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.BandwidthLimitForCcnAlarmOnlyRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.BandwidthLimitForCcnAlarmOnlyResponse`

        """
        try:
            params = request._serialize()
            body = self.call("BandwidthLimitForCcnAlarmOnly", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.BandwidthLimitForCcnAlarmOnlyResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def CheckAssistantCidr(self, request):
        """本接口(CheckAssistantCidr)用于检查辅助CIDR是否与存量路由、对等连接（对端VPC的CIDR）等资源存在冲突。如果存在重叠，则返回重叠的资源。（接口灰度中，如需使用请提工单。）
        * 检测辅助CIDR是否与当前VPC的主CIDR和辅助CIDR存在重叠。
        * 检测辅助CIDR是否与当前VPC的路由的目的端存在重叠。
        * 检测辅助CIDR是否与当前VPC的对等连接，对端VPC下的主CIDR或辅助CIDR存在重叠。

        :param request: 调用CheckAssistantCidr所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.CheckAssistantCidrRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.CheckAssistantCidrResponse`

        """
        try:
            params = request._serialize()
            body = self.call("CheckAssistantCidr", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.CheckAssistantCidrResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def CheckBandwidthPackage(self, request):
        """检查账户带宽包属性。

        :param request: 调用CheckBandwidthPackage所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.CheckBandwidthPackageRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.CheckBandwidthPackageResponse`

        """
        try:
            params = request._serialize()
            body = self.call("CheckBandwidthPackage", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.CheckBandwidthPackageResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def CheckDefaultSubnet(self, request):
        """本接口（CheckDefaultSubnet）用于预判是否可建默认子网。

        :param request: 调用CheckDefaultSubnet所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.CheckDefaultSubnetRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.CheckDefaultSubnetResponse`

        """
        try:
            params = request._serialize()
            body = self.call("CheckDefaultSubnet", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.CheckDefaultSubnetResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def CheckGatewayFlowMonitor(self, request):
        """本接口（CheckGatewayFlowMonitor）用于查询网关是否启用流量监控。

        :param request: 调用CheckGatewayFlowMonitor所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.CheckGatewayFlowMonitorRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.CheckGatewayFlowMonitorResponse`

        """
        try:
            params = request._serialize()
            body = self.call("CheckGatewayFlowMonitor", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.CheckGatewayFlowMonitorResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def CheckNetDetectState(self, request):
        """本接口(CheckNetDetectState)用于验证网络探测。

        :param request: 调用CheckNetDetectState所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.CheckNetDetectStateRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.CheckNetDetectStateResponse`

        """
        try:
            params = request._serialize()
            body = self.call("CheckNetDetectState", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.CheckNetDetectStateResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def CheckSameCity(self, request):
        """本接口（CheckSameCity）用于用于检查指定的两个Region是否为同城。
        * 参数取值参考地域列表。

        :param request: 调用CheckSameCity所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.CheckSameCityRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.CheckSameCityResponse`

        """
        try:
            params = request._serialize()
            body = self.call("CheckSameCity", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.CheckSameCityResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def CheckSecurityGroupPolicies(self, request):
        """本接口（CheckSecurityGroupPolicies）用于查询安全组策略中常用端口的放开策略。

        :param request: 调用CheckSecurityGroupPolicies所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.CheckSecurityGroupPoliciesRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.CheckSecurityGroupPoliciesResponse`

        """
        try:
            params = request._serialize()
            body = self.call("CheckSecurityGroupPolicies", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.CheckSecurityGroupPoliciesResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def CloneSecurityGroup(self, request):
        """本接口（CloneSecurityGroup）用于根据存量的安全组，克隆创建出同样规则配置的安全组。仅克隆安全组及其规则信息，不会克隆安全组标签信息。

        :param request: 调用CloneSecurityGroup所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.CloneSecurityGroupRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.CloneSecurityGroupResponse`

        """
        try:
            params = request._serialize()
            body = self.call("CloneSecurityGroup", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.CloneSecurityGroupResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def CreateAddressTemplate(self, request):
        """本接口（CreateAddressTemplate）用于创建IP地址模版

        :param request: 调用CreateAddressTemplate所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.CreateAddressTemplateRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.CreateAddressTemplateResponse`

        """
        try:
            params = request._serialize()
            body = self.call("CreateAddressTemplate", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.CreateAddressTemplateResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def CreateAddressTemplateGroup(self, request):
        """本接口（CreateAddressTemplateGroup）用于创建IP地址模版集合

        :param request: 调用CreateAddressTemplateGroup所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.CreateAddressTemplateGroupRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.CreateAddressTemplateGroupResponse`

        """
        try:
            params = request._serialize()
            body = self.call("CreateAddressTemplateGroup", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.CreateAddressTemplateGroupResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def CreateAndAttachNetworkInterface(self, request):
        """本接口（CreateAndAttachNetworkInterface）用于创建弹性网卡并绑定云主机。
        * 创建弹性网卡时可以指定内网IP，并且可以指定一个主IP，指定的内网IP必须在弹性网卡所在子网内，而且不能被占用。
        * 创建弹性网卡时可以指定需要申请的内网IP数量，系统会随机生成内网IP地址。
        * 一个弹性网卡支持绑定的IP地址是有限制的，更多资源限制信息详见弹性网卡使用限制。
        * 创建弹性网卡同时可以绑定已有安全组。
        * 创建弹性网卡同时可以绑定标签, 应答里的标签列表代表添加成功的标签。

        :param request: 调用CreateAndAttachNetworkInterface所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.CreateAndAttachNetworkInterfaceRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.CreateAndAttachNetworkInterfaceResponse`

        """
        try:
            params = request._serialize()
            body = self.call("CreateAndAttachNetworkInterface", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.CreateAndAttachNetworkInterfaceResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def CreateAssistantCidr(self, request):
        """本接口(CreateAssistantCidr)用于批量创建辅助CIDR。（接口灰度中，如需使用请提工单。）

        :param request: 调用CreateAssistantCidr所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.CreateAssistantCidrRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.CreateAssistantCidrResponse`

        """
        try:
            params = request._serialize()
            body = self.call("CreateAssistantCidr", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.CreateAssistantCidrResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def CreateBandwidthPackage(self, request):
        """接口支持创建设备带宽包和IP带宽包

        :param request: 调用CreateBandwidthPackage所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.CreateBandwidthPackageRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.CreateBandwidthPackageResponse`

        """
        try:
            params = request._serialize()
            body = self.call("CreateBandwidthPackage", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.CreateBandwidthPackageResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def CreateCcn(self, request):
        """本接口（CreateCcn）用于创建云联网（CCN）。<br />
        * 创建云联网同时可以绑定标签, 应答里的标签列表代表添加成功的标签。
        每个账号能创建的云联网实例个数是有限的，详请参考产品文档。如果需要扩充请联系在线客服。

        :param request: 调用CreateCcn所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.CreateCcnRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.CreateCcnResponse`

        """
        try:
            params = request._serialize()
            body = self.call("CreateCcn", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.CreateCcnResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def CreateCcnBandwidth(self, request):
        """本接口（CreateCcnBandwidth）用于创建预付费模式下云联网实例的地域间带宽

        :param request: 调用CreateCcnBandwidth所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.CreateCcnBandwidthRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.CreateCcnBandwidthResponse`

        """
        try:
            params = request._serialize()
            body = self.call("CreateCcnBandwidth", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.CreateCcnBandwidthResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def CreateCustomerGateway(self, request):
        """本接口（CreateCustomerGateway）用于创建对端网关。

        :param request: 调用CreateCustomerGateway所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.CreateCustomerGatewayRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.CreateCustomerGatewayResponse`

        """
        try:
            params = request._serialize()
            body = self.call("CreateCustomerGateway", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.CreateCustomerGatewayResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def CreateDefaultSecurityGroup(self, request):
        """本接口（CreateDefaultSecurityGroup）用于创建（如果项目下未存在默认安全组，则创建；已存在则获取。）默认安全组（SecurityGroup）。
        * 每个账户下每个地域的每个项目的安全组数量限制。
        * 新建的安全组的入站和出站规则默认都是全部拒绝，在创建后通常您需要再调用CreateSecurityGroupPolicies将安全组的规则设置为需要的规则。
        * 创建安全组同时可以绑定标签, 应答里的标签列表代表添加成功的标签。

        :param request: 调用CreateDefaultSecurityGroup所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.CreateDefaultSecurityGroupRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.CreateDefaultSecurityGroupResponse`

        """
        try:
            params = request._serialize()
            body = self.call("CreateDefaultSecurityGroup", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.CreateDefaultSecurityGroupResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def CreateDefaultVpc(self, request):
        """本接口（CreateDefaultVpc）用于创建默认私有网络(VPC）。

        默认VPC适用于快速入门和启动公共实例，您可以像使用任何其他VPC一样使用默认VPC。如果您想创建标准VPC，即指定VPC名称、VPC网段、子网网段、子网可用区，请使用常规创建VPC接口（CreateVpc）

        正常情况，本接口并不一定生产默认VPC，而是根据用户账号的网络属性（DescribeAccountAttributes）来决定的
        * 支持基础网络、VPC，返回VpcId为0
        * 只支持VPC，返回默认VPC信息

        您也可以通过 Force 参数，强制返回默认VPC

        :param request: 调用CreateDefaultVpc所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.CreateDefaultVpcRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.CreateDefaultVpcResponse`

        """
        try:
            params = request._serialize()
            body = self.call("CreateDefaultVpc", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.CreateDefaultVpcResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def CreateDirectConnectGateway(self, request):
        """本接口（CreateDirectConnectGateway）用于创建专线网关。

        :param request: 调用CreateDirectConnectGateway所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.CreateDirectConnectGatewayRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.CreateDirectConnectGatewayResponse`

        """
        try:
            params = request._serialize()
            body = self.call("CreateDirectConnectGateway", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.CreateDirectConnectGatewayResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def CreateDirectConnectGatewayCcnRoutes(self, request):
        """本接口（CreateDirectConnectGatewayCcnRoutes）用于创建专线网关的云联网路由（IDC网段）

        :param request: 调用CreateDirectConnectGatewayCcnRoutes所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.CreateDirectConnectGatewayCcnRoutesRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.CreateDirectConnectGatewayCcnRoutesResponse`

        """
        try:
            params = request._serialize()
            body = self.call("CreateDirectConnectGatewayCcnRoutes", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.CreateDirectConnectGatewayCcnRoutesResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def CreateFlowLog(self, request):
        """本接口（CreateFlowLog）用于创建流日志

        :param request: 调用CreateFlowLog所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.CreateFlowLogRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.CreateFlowLogResponse`

        """
        try:
            params = request._serialize()
            body = self.call("CreateFlowLog", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.CreateFlowLogResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def CreateHaVip(self, request):
        """本接口（CreateHaVip）用于创建高可用虚拟IP（HAVIP）

        :param request: 调用CreateHaVip所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.CreateHaVipRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.CreateHaVipResponse`

        """
        try:
            params = request._serialize()
            body = self.call("CreateHaVip", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.CreateHaVipResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def CreateIp6Translators(self, request):
        """1. 该接口用于创建IPV6转换IPV4实例，支持批量
        2. 同一个账户在一个地域最多允许创建10个转换实例

        :param request: 调用CreateIp6Translators所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.CreateIp6TranslatorsRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.CreateIp6TranslatorsResponse`

        """
        try:
            params = request._serialize()
            body = self.call("CreateIp6Translators", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.CreateIp6TranslatorsResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def CreateLocalDestinationIpPortTranslationNatRule(self, request):
        """创建专线网关本端目的IP端口转换

        :param request: 调用CreateLocalDestinationIpPortTranslationNatRule所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.CreateLocalDestinationIpPortTranslationNatRuleRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.CreateLocalDestinationIpPortTranslationNatRuleResponse`

        """
        try:
            params = request._serialize()
            body = self.call("CreateLocalDestinationIpPortTranslationNatRule", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.CreateLocalDestinationIpPortTranslationNatRuleResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def CreateLocalIpTranslationAclRule(self, request):
        """创建专线网关本端IP转换ACL规则

        :param request: 调用CreateLocalIpTranslationAclRule所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.CreateLocalIpTranslationAclRuleRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.CreateLocalIpTranslationAclRuleResponse`

        """
        try:
            params = request._serialize()
            body = self.call("CreateLocalIpTranslationAclRule", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.CreateLocalIpTranslationAclRuleResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def CreateLocalIpTranslationNatRule(self, request):
        """创建专线网关本端IP转换

        :param request: 调用CreateLocalIpTranslationNatRule所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.CreateLocalIpTranslationNatRuleRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.CreateLocalIpTranslationNatRuleResponse`

        """
        try:
            params = request._serialize()
            body = self.call("CreateLocalIpTranslationNatRule", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.CreateLocalIpTranslationNatRuleResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def CreateLocalSourceIpPortTranslationAclRule(self, request):
        """创建专线网关本端源IP端口转换ACL规则

        :param request: 调用CreateLocalSourceIpPortTranslationAclRule所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.CreateLocalSourceIpPortTranslationAclRuleRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.CreateLocalSourceIpPortTranslationAclRuleResponse`

        """
        try:
            params = request._serialize()
            body = self.call("CreateLocalSourceIpPortTranslationAclRule", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.CreateLocalSourceIpPortTranslationAclRuleResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def CreateLocalSourceIpPortTranslationNatRule(self, request):
        """创建专线网关本端源IP端口转换

        :param request: 调用CreateLocalSourceIpPortTranslationNatRule所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.CreateLocalSourceIpPortTranslationNatRuleRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.CreateLocalSourceIpPortTranslationNatRuleResponse`

        """
        try:
            params = request._serialize()
            body = self.call("CreateLocalSourceIpPortTranslationNatRule", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.CreateLocalSourceIpPortTranslationNatRuleResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def CreateNatGateway(self, request):
        """本接口(CreateNatGateway)用于创建NAT网关。

        :param request: 调用CreateNatGateway所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.CreateNatGatewayRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.CreateNatGatewayResponse`

        """
        try:
            params = request._serialize()
            body = self.call("CreateNatGateway", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.CreateNatGatewayResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def CreateNatGatewayDestinationIpPortTranslationNatRule(self, request):
        """本接口(CreateNatGatewayDestinationIpPortTranslationNatRule)用于创建NAT网关端口转发规则。

        :param request: 调用CreateNatGatewayDestinationIpPortTranslationNatRule所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.CreateNatGatewayDestinationIpPortTranslationNatRuleRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.CreateNatGatewayDestinationIpPortTranslationNatRuleResponse`

        """
        try:
            params = request._serialize()
            body = self.call("CreateNatGatewayDestinationIpPortTranslationNatRule", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.CreateNatGatewayDestinationIpPortTranslationNatRuleResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def CreateNetDetect(self, request):
        """本接口(CreateNetDetect)用于创建网络探测。

        :param request: 调用CreateNetDetect所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.CreateNetDetectRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.CreateNetDetectResponse`

        """
        try:
            params = request._serialize()
            body = self.call("CreateNetDetect", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.CreateNetDetectResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def CreateNetworkAcl(self, request):
        """本接口（CreateNetworkAcl）用于创建新的网络ACL。
        * 新建的网络ACL的入站和出站规则默认都是全部拒绝，在创建后通常您需要再调用ModifyNetworkAclEntries将网络ACL的规则设置为需要的规则。

        :param request: 调用CreateNetworkAcl所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.CreateNetworkAclRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.CreateNetworkAclResponse`

        """
        try:
            params = request._serialize()
            body = self.call("CreateNetworkAcl", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.CreateNetworkAclResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def CreateNetworkInterface(self, request):
        """本接口（CreateNetworkInterface）用于创建弹性网卡。
        * 创建弹性网卡时可以指定内网IP，并且可以指定一个主IP，指定的内网IP必须在弹性网卡所在子网内，而且不能被占用。
        * 创建弹性网卡时可以指定需要申请的内网IP数量，系统会随机生成内网IP地址。
        * 一个弹性网卡支持绑定的IP地址是有限制的，更多资源限制信息详见弹性网卡使用限制。
        * 创建弹性网卡同时可以绑定已有安全组。
        * 创建弹性网卡同时可以绑定标签, 应答里的标签列表代表添加成功的标签。

        :param request: 调用CreateNetworkInterface所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.CreateNetworkInterfaceRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.CreateNetworkInterfaceResponse`

        """
        try:
            params = request._serialize()
            body = self.call("CreateNetworkInterface", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.CreateNetworkInterfaceResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def CreateNetworkInterfaceEx(self, request):
        """本接口（CreateNetworkInterfaceEx）用于创建跨租户的弹性网卡。
        * ReservedAddress=0时，从保留网段（169.254.128/17）分配一个未使用的IP。
        * 创建弹性网卡时可以指定内网IP（ReservedAddress=0且指定了用户SubnetId时，才可使用），并且可以指定一个主IP，指定的内网IP必须在弹性网卡所在子网内，而且不能被占用。
        * 不允许网卡VPC和云服务器在同一个VPC内，调用接口创建跨租户的弹性网卡；

        :param request: 调用CreateNetworkInterfaceEx所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.CreateNetworkInterfaceExRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.CreateNetworkInterfaceExResponse`

        """
        try:
            params = request._serialize()
            body = self.call("CreateNetworkInterfaceEx", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.CreateNetworkInterfaceExResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def CreatePeerIpTranslationNatRule(self, request):
        """创建专线网关对端IP转换

        :param request: 调用CreatePeerIpTranslationNatRule所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.CreatePeerIpTranslationNatRuleRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.CreatePeerIpTranslationNatRuleResponse`

        """
        try:
            params = request._serialize()
            body = self.call("CreatePeerIpTranslationNatRule", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.CreatePeerIpTranslationNatRuleResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def CreateRouteTable(self, request):
        """本接口(CreateRouteTable)用于创建路由表。
        * 创建了VPC后，系统会创建一个默认路由表，所有新建的子网都会关联到默认路由表。默认情况下您可以直接使用默认路由表来管理您的路由策略。当您的路由策略较多时，您可以调用创建路由表接口创建更多路由表管理您的路由策略。
        * 创建路由表同时可以绑定标签, 应答里的标签列表代表添加成功的标签。

        :param request: 调用CreateRouteTable所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.CreateRouteTableRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.CreateRouteTableResponse`

        """
        try:
            params = request._serialize()
            body = self.call("CreateRouteTable", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.CreateRouteTableResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def CreateRoutes(self, request):
        """本接口(CreateRoutes)用于创建路由策略。
        * 向指定路由表批量新增路由策略。

        :param request: 调用CreateRoutes所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.CreateRoutesRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.CreateRoutesResponse`

        """
        try:
            params = request._serialize()
            body = self.call("CreateRoutes", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.CreateRoutesResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def CreateSecurityGroup(self, request):
        """本接口（CreateSecurityGroup）用于创建新的安全组（SecurityGroup）。
        * 每个账户下每个地域的每个项目的安全组数量限制。
        * 新建的安全组的入站和出站规则默认都是全部拒绝，在创建后通常您需要再调用CreateSecurityGroupPolicies将安全组的规则设置为需要的规则。
        * 创建安全组同时可以绑定标签, 应答里的标签列表代表添加成功的标签。

        :param request: 调用CreateSecurityGroup所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.CreateSecurityGroupRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.CreateSecurityGroupResponse`

        """
        try:
            params = request._serialize()
            body = self.call("CreateSecurityGroup", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.CreateSecurityGroupResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def CreateSecurityGroupPolicies(self, request):
        """本接口（CreateSecurityGroupPolicies）用于创建安全组规则（SecurityGroupPolicy）。

        * Version安全组规则版本号，用户每次更新安全规则版本会自动加1，防止您更新的路由规则已过期，不填不考虑冲突。
        * Protocol字段支持输入TCP, UDP, ICMP, ICMPV6, GRE, ALL。
        * CidrBlock字段允许输入符合cidr格式标准的任意字符串。(展开)在基础网络中，如果CidrBlock包含您的账户内的云服务器之外的设备在Tce的内网IP，并不代表此规则允许您访问这些设备，租户之间网络隔离规则优先于安全组中的内网规则。
        * Ipv6CidrBlock字段允许输入符合IPv6 cidr格式标准的任意字符串。(展开)在基础网络中，如果Ipv6CidrBlock包含您的账户内的云服务器之外的设备在Tce的内网IPv6，并不代表此规则允许您访问这些设备，租户之间网络隔离规则优先于安全组中的内网规则。
        * SecurityGroupId字段允许输入与待修改的安全组位于相同项目中的安全组ID，包括这个安全组ID本身，代表安全组下所有云服务器的内网IP。使用这个字段时，这条规则用来匹配网络报文的过程中会随着被使用的这个ID所关联的云服务器变化而变化，不需要重新修改。
        * Port字段允许输入一个单独端口号，或者用减号分隔的两个端口号代表端口范围，例如80或8000-8010。只有当Protocol字段是TCP或UDP时，Port字段才被接受，即Protocol字段不是TCP或UDP时，Protocol和Port排他关系，不允许同时输入，否则会接口报错。
        * Action字段只允许输入ACCEPT或DROP。
        * CidrBlock, Ipv6CidrBlock, SecurityGroupId, AddressTemplate四者是排他关系，不允许同时输入，Protocol + Port和ServiceTemplate二者是排他关系，不允许同时输入。
        * 一次请求中只能创建单个方向的规则, 如果需要指定索引（PolicyIndex）参数, 多条规则的索引必须一致。

        :param request: 调用CreateSecurityGroupPolicies所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.CreateSecurityGroupPoliciesRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.CreateSecurityGroupPoliciesResponse`

        """
        try:
            params = request._serialize()
            body = self.call("CreateSecurityGroupPolicies", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.CreateSecurityGroupPoliciesResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def CreateSecurityGroupWithPolicies(self, request):
        """本接口（CreateSecurityGroupWithPolicies）用于创建新的安全组（SecurityGroup），并且可以同时添加安全组规则（SecurityGroupPolicy）。
        * 每个账户下每个地域的每个项目的安全组数量限制。
        * 新建的安全组的入站和出站规则默认都是全部拒绝，在创建后通常您需要再调用CreateSecurityGroupPolicies将安全组的规则设置为需要的规则。

        安全组规则说明：
        * Version安全组规则版本号，用户每次更新安全规则版本会自动加1，防止您更新的路由规则已过期，不填不考虑冲突。
        * Protocol字段支持输入TCP, UDP, ICMP, ICMPV6, GRE, ALL。
        * CidrBlock字段允许输入符合cidr格式标准的任意字符串。(展开)在基础网络中，如果CidrBlock包含您的账户内的云服务器之外的设备在Tce的内网IP，并不代表此规则允许您访问这些设备，租户之间网络隔离规则优先于安全组中的内网规则。
        * Ipv6CidrBlock字段允许输入符合IPv6 cidr格式标准的任意字符串。(展开)在基础网络中，如果Ipv6CidrBlock包含您的账户内的云服务器之外的设备在Tce的内网IPv6，并不代表此规则允许您访问这些设备，租户之间网络隔离规则优先于安全组中的内网规则。
        * SecurityGroupId字段允许输入与待修改的安全组位于相同项目中的安全组ID，包括这个安全组ID本身，代表安全组下所有云服务器的内网IP。使用这个字段时，这条规则用来匹配网络报文的过程中会随着被使用的这个ID所关联的云服务器变化而变化，不需要重新修改。
        * Port字段允许输入一个单独端口号，或者用减号分隔的两个端口号代表端口范围，例如80或8000-8010。只有当Protocol字段是TCP或UDP时，Port字段才被接受，即Protocol字段不是TCP或UDP时，Protocol和Port排他关系，不允许同时输入，否则会接口报错。
        * Action字段只允许输入ACCEPT或DROP。
        * CidrBlock, Ipv6CidrBlock, SecurityGroupId, AddressTemplate四者是排他关系，不允许同时输入，Protocol + Port和ServiceTemplate二者是排他关系，不允许同时输入。
        * 一次请求中只能创建单个方向的规则, 如果需要指定索引（PolicyIndex）参数, 多条规则的索引必须一致。

        :param request: 调用CreateSecurityGroupWithPolicies所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.CreateSecurityGroupWithPoliciesRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.CreateSecurityGroupWithPoliciesResponse`

        """
        try:
            params = request._serialize()
            body = self.call("CreateSecurityGroupWithPolicies", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.CreateSecurityGroupWithPoliciesResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def CreateServiceTemplate(self, request):
        """本接口（CreateServiceTemplate）用于创建协议端口模板

        :param request: 调用CreateServiceTemplate所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.CreateServiceTemplateRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.CreateServiceTemplateResponse`

        """
        try:
            params = request._serialize()
            body = self.call("CreateServiceTemplate", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.CreateServiceTemplateResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def CreateServiceTemplateGroup(self, request):
        """本接口（CreateServiceTemplateGroup）用于创建协议端口模板集合

        :param request: 调用CreateServiceTemplateGroup所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.CreateServiceTemplateGroupRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.CreateServiceTemplateGroupResponse`

        """
        try:
            params = request._serialize()
            body = self.call("CreateServiceTemplateGroup", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.CreateServiceTemplateGroupResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def CreateSubnet(self, request):
        """本接口(CreateSubnet)用于创建子网。
        * 创建子网前必须创建好 VPC。
        * 子网创建成功后，子网网段不能修改。子网网段必须在VPC网段内，可以和VPC网段相同（VPC有且只有一个子网时），建议子网网段在VPC网段内，预留网段给其他子网使用。
        * 您可以创建的最小网段子网掩码为28（有16个IP地址），最大网段子网掩码为16（65,536个IP地址）。
        * 同一个VPC内，多个子网的网段不能重叠。
        * 子网创建后会自动关联到默认路由表。
        * 创建子网同时可以绑定标签, 应答里的标签列表代表添加成功的标签。

        :param request: 调用CreateSubnet所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.CreateSubnetRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.CreateSubnetResponse`

        """
        try:
            params = request._serialize()
            body = self.call("CreateSubnet", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.CreateSubnetResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def CreateSubnets(self, request):
        """本接口(CreateSubnets)用于批量创建子网。
        * 创建子网前必须创建好 VPC。
        * 子网创建成功后，子网网段不能修改。子网网段必须在VPC网段内，可以和VPC网段相同（VPC有且只有一个子网时），建议子网网段在VPC网段内，预留网段给其他子网使用。
        * 您可以创建的最小网段子网掩码为28（有16个IP地址），最大网段子网掩码为16（65,536个IP地址）。
        * 同一个VPC内，多个子网的网段不能重叠。
        * 子网创建后会自动关联到默认路由表。
        * 创建子网同时可以绑定标签, 应答里的标签列表代表添加成功的标签。

        :param request: 调用CreateSubnets所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.CreateSubnetsRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.CreateSubnetsResponse`

        """
        try:
            params = request._serialize()
            body = self.call("CreateSubnets", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.CreateSubnetsResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def CreateTrafficMirror(self, request):
        """本接口（CreateTrafficMirror）用于创建流量镜像实例。

        :param request: 调用CreateTrafficMirror所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.CreateTrafficMirrorRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.CreateTrafficMirrorResponse`

        """
        try:
            params = request._serialize()
            body = self.call("CreateTrafficMirror", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.CreateTrafficMirrorResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def CreateTrafficPackages(self, request):
        """创建共享流量包

        :param request: 调用CreateTrafficPackages所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.CreateTrafficPackagesRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.CreateTrafficPackagesResponse`

        """
        try:
            params = request._serialize()
            body = self.call("CreateTrafficPackages", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.CreateTrafficPackagesResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def CreateVpc(self, request):
        """本接口(CreateVpc)用于创建私有网络(VPC)。
        * 用户可以创建的最小网段子网掩码为28（有16个IP地址），最大网段子网掩码为16（65,536个IP地址）,如果规划VPC网段请参见VPC网段规划说明。
        * 同一个地域能创建的VPC资源个数也是有限制的，详见 VPC使用限制,如果需要扩充请联系在线客服。
        * 创建VPC同时可以绑定标签, 应答里的标签列表代表添加成功的标签。

        :param request: 调用CreateVpc所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.CreateVpcRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.CreateVpcResponse`

        """
        try:
            params = request._serialize()
            body = self.call("CreateVpc", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.CreateVpcResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def CreateVpnConnection(self, request):
        """本接口（CreateVpnConnection）用于创建VPN通道。

        :param request: 调用CreateVpnConnection所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.CreateVpnConnectionRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.CreateVpnConnectionResponse`

        """
        try:
            params = request._serialize()
            body = self.call("CreateVpnConnection", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.CreateVpnConnectionResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def CreateVpnGateway(self, request):
        """本接口（CreateVpnGateway）用于创建VPN网关。

        :param request: 调用CreateVpnGateway所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.CreateVpnGatewayRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.CreateVpnGatewayResponse`

        """
        try:
            params = request._serialize()
            body = self.call("CreateVpnGateway", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.CreateVpnGatewayResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DeleteAddressTemplate(self, request):
        """本接口（DeleteAddressTemplate）用于删除IP地址模板

        :param request: 调用DeleteAddressTemplate所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DeleteAddressTemplateRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DeleteAddressTemplateResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DeleteAddressTemplate", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DeleteAddressTemplateResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DeleteAddressTemplateGroup(self, request):
        """本接口（DeleteAddressTemplateGroup）用于删除IP地址模板集合

        :param request: 调用DeleteAddressTemplateGroup所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DeleteAddressTemplateGroupRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DeleteAddressTemplateGroupResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DeleteAddressTemplateGroup", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DeleteAddressTemplateGroupResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DeleteAssistantCidr(self, request):
        """本接口(DeleteAssistantCidr)用于删除辅助CIDR。（接口灰度中，如需使用请提工单。）

        :param request: 调用DeleteAssistantCidr所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DeleteAssistantCidrRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DeleteAssistantCidrResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DeleteAssistantCidr", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DeleteAssistantCidrResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DeleteBandwidthPackage(self, request):
        """接口支持删除共享带宽包，包括设备带宽包和IP带宽包

        :param request: 调用DeleteBandwidthPackage所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DeleteBandwidthPackageRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DeleteBandwidthPackageResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DeleteBandwidthPackage", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DeleteBandwidthPackageResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DeleteCcn(self, request):
        """本接口（DeleteCcn）用于删除云联网。
        * 删除后，云联网关联的所有实例间路由将被删除，网络将会中断，请务必确认
        * 删除云联网是不可逆的操作，请谨慎处理。

        :param request: 调用DeleteCcn所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DeleteCcnRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DeleteCcnResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DeleteCcn", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DeleteCcnResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DeleteCcnRegionBandwidthLimits(self, request):
        """本接口（DeleteCcnRegionBandwidthLimits）用于删除云联网实例的限速规则。

        :param request: 调用DeleteCcnRegionBandwidthLimits所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DeleteCcnRegionBandwidthLimitsRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DeleteCcnRegionBandwidthLimitsResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DeleteCcnRegionBandwidthLimits", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DeleteCcnRegionBandwidthLimitsResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DeleteCustomerGateway(self, request):
        """本接口（DeleteCustomerGateway）用于删除对端网关。

        :param request: 调用DeleteCustomerGateway所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DeleteCustomerGatewayRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DeleteCustomerGatewayResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DeleteCustomerGateway", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DeleteCustomerGatewayResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DeleteDirectConnectGateway(self, request):
        """本接口（DeleteDirectConnectGateway）用于删除专线网关。
        <li>如果是 NAT 网关，删除专线网关后，NAT 规则以及 ACL 策略都被清理了。</li>
        <li>删除专线网关后，系统会删除路由表中跟该专线网关相关的路由策略。</li>
        本接口是异步完成，如需查询异步任务执行结果，请使用本接口返回的`RequestId`轮询`QueryTask`接口

        :param request: 调用DeleteDirectConnectGateway所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DeleteDirectConnectGatewayRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DeleteDirectConnectGatewayResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DeleteDirectConnectGateway", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DeleteDirectConnectGatewayResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DeleteDirectConnectGatewayCcnRoutes(self, request):
        """本接口（DeleteDirectConnectGatewayCcnRoutes）用于删除专线网关的云联网路由（IDC网段）

        :param request: 调用DeleteDirectConnectGatewayCcnRoutes所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DeleteDirectConnectGatewayCcnRoutesRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DeleteDirectConnectGatewayCcnRoutesResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DeleteDirectConnectGatewayCcnRoutes", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DeleteDirectConnectGatewayCcnRoutesResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DeleteFlowLog(self, request):
        """本接口（DeleteFlowLog）用于删除流日志

        :param request: 调用DeleteFlowLog所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DeleteFlowLogRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DeleteFlowLogResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DeleteFlowLog", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DeleteFlowLogResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DeleteHaVip(self, request):
        """本接口（DeleteHaVip）用于删除高可用虚拟IP（HAVIP）<br />
        本接口是异步完成，如需查询异步任务执行结果，请使用本接口返回的`RequestId`轮询`QueryTask`接口

        :param request: 调用DeleteHaVip所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DeleteHaVipRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DeleteHaVipResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DeleteHaVip", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DeleteHaVipResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DeleteInstanceNetworkInterface(self, request):
        """本接口（DeleteInstanceNetworkInterface）用于删除云主机例弹性网卡。
        * 本接口在CVM云主机销毁时调用。

        :param request: 调用DeleteInstanceNetworkInterface所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DeleteInstanceNetworkInterfaceRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DeleteInstanceNetworkInterfaceResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DeleteInstanceNetworkInterface", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DeleteInstanceNetworkInterfaceResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DeleteIp6Translators(self, request):
        """1. 该接口用于释放IPV6转换实例，支持批量。
        2.  如果IPV6转换实例建立有转换规则，会一并删除。

        :param request: 调用DeleteIp6Translators所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DeleteIp6TranslatorsRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DeleteIp6TranslatorsResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DeleteIp6Translators", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DeleteIp6TranslatorsResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DeleteLocalDestinationIpPortTranslationNatRule(self, request):
        """删除专线网关本端目的IP端口转换

        :param request: 调用DeleteLocalDestinationIpPortTranslationNatRule所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DeleteLocalDestinationIpPortTranslationNatRuleRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DeleteLocalDestinationIpPortTranslationNatRuleResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DeleteLocalDestinationIpPortTranslationNatRule", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DeleteLocalDestinationIpPortTranslationNatRuleResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DeleteLocalIpTranslationAclRule(self, request):
        """删除专线网关本端IP转换ACL规则

        :param request: 调用DeleteLocalIpTranslationAclRule所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DeleteLocalIpTranslationAclRuleRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DeleteLocalIpTranslationAclRuleResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DeleteLocalIpTranslationAclRule", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DeleteLocalIpTranslationAclRuleResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DeleteLocalIpTranslationNatRule(self, request):
        """删除专线网关本端IP转换

        :param request: 调用DeleteLocalIpTranslationNatRule所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DeleteLocalIpTranslationNatRuleRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DeleteLocalIpTranslationNatRuleResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DeleteLocalIpTranslationNatRule", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DeleteLocalIpTranslationNatRuleResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DeleteLocalSourceIpPortTranslationAclRule(self, request):
        """删除专线网关本端源IP端口转换ACL规则

        :param request: 调用DeleteLocalSourceIpPortTranslationAclRule所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DeleteLocalSourceIpPortTranslationAclRuleRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DeleteLocalSourceIpPortTranslationAclRuleResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DeleteLocalSourceIpPortTranslationAclRule", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DeleteLocalSourceIpPortTranslationAclRuleResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DeleteLocalSourceIpPortTranslationNatRule(self, request):
        """删除专线网关本端源IP端口转换

        :param request: 调用DeleteLocalSourceIpPortTranslationNatRule所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DeleteLocalSourceIpPortTranslationNatRuleRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DeleteLocalSourceIpPortTranslationNatRuleResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DeleteLocalSourceIpPortTranslationNatRule", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DeleteLocalSourceIpPortTranslationNatRuleResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DeleteNatGateway(self, request):
        """本接口（DeleteNatGateway）用于删除NAT网关。
        删除 NAT 网关后，系统会自动删除路由表中包含此 NAT 网关的路由项，同时也会解绑弹性公网IP（EIP）。

        :param request: 调用DeleteNatGateway所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DeleteNatGatewayRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DeleteNatGatewayResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DeleteNatGateway", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DeleteNatGatewayResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DeleteNatGatewayDestinationIpPortTranslationNatRule(self, request):
        """本接口（DeleteNatGatewayDestinationIpPortTranslationNatRule）用于删除NAT网关端口转发规则。

        :param request: 调用DeleteNatGatewayDestinationIpPortTranslationNatRule所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DeleteNatGatewayDestinationIpPortTranslationNatRuleRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DeleteNatGatewayDestinationIpPortTranslationNatRuleResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DeleteNatGatewayDestinationIpPortTranslationNatRule", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DeleteNatGatewayDestinationIpPortTranslationNatRuleResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DeleteNetDetect(self, request):
        """本接口(DeleteNetDetect)用于删除网络探测实例。

        :param request: 调用DeleteNetDetect所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DeleteNetDetectRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DeleteNetDetectResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DeleteNetDetect", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DeleteNetDetectResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DeleteNetworkAcl(self, request):
        """本接口（DeleteNetworkAcl）用于删除网络ACL。

        :param request: 调用DeleteNetworkAcl所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DeleteNetworkAclRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DeleteNetworkAclResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DeleteNetworkAcl", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DeleteNetworkAclResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DeleteNetworkInterface(self, request):
        """本接口（DeleteNetworkInterface）用于删除弹性网卡。
        * 弹性网卡上绑定了云服务器时，不能被删除。
        * 删除指定弹性网卡，弹性网卡必须先和子机解绑才能删除。删除之后弹性网卡上所有内网IP都将被退还。

        :param request: 调用DeleteNetworkInterface所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DeleteNetworkInterfaceRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DeleteNetworkInterfaceResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DeleteNetworkInterface", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DeleteNetworkInterfaceResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DeleteNetworkInterfaceEx(self, request):
        """本接口（DeleteNetworkInterfaceEx）用于删除跨租户弹性网卡。

        :param request: 调用DeleteNetworkInterfaceEx所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DeleteNetworkInterfaceExRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DeleteNetworkInterfaceExResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DeleteNetworkInterfaceEx", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DeleteNetworkInterfaceExResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DeletePeerIpTranslationNatRule(self, request):
        """删除专线网关对端IP转换

        :param request: 调用DeletePeerIpTranslationNatRule所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DeletePeerIpTranslationNatRuleRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DeletePeerIpTranslationNatRuleResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DeletePeerIpTranslationNatRule", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DeletePeerIpTranslationNatRuleResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DeleteRouteTable(self, request):
        """删除路由表

        :param request: 调用DeleteRouteTable所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DeleteRouteTableRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DeleteRouteTableResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DeleteRouteTable", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DeleteRouteTableResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DeleteRoutes(self, request):
        """本接口(DeleteRoutes)用于对某个路由表批量删除路由策略（Route）。

        :param request: 调用DeleteRoutes所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DeleteRoutesRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DeleteRoutesResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DeleteRoutes", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DeleteRoutesResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DeleteSecurityGroup(self, request):
        """本接口（DeleteSecurityGroup）用于删除安全组（SecurityGroup）。
        * 只有当前账号下的安全组允许被删除。
        * 安全组实例ID如果在其他安全组的规则中被引用，则无法直接删除。这种情况下，需要先进行规则修改，再删除安全组。
        * 删除的安全组无法再找回，请谨慎调用。

        :param request: 调用DeleteSecurityGroup所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DeleteSecurityGroupRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DeleteSecurityGroupResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DeleteSecurityGroup", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DeleteSecurityGroupResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DeleteSecurityGroupPolicies(self, request):
        """本接口（DeleteSecurityGroupPolicies）用于用于删除安全组规则（SecurityGroupPolicy）。
        * SecurityGroupPolicySet.Version 用于指定要操作的安全组的版本。传入 Version 版本号若不等于当前安全组的最新版本，将返回失败；若不传 Version 则直接删除指定PolicyIndex的规则。

        :param request: 调用DeleteSecurityGroupPolicies所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DeleteSecurityGroupPoliciesRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DeleteSecurityGroupPoliciesResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DeleteSecurityGroupPolicies", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DeleteSecurityGroupPoliciesResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DeleteServiceTemplate(self, request):
        """本接口（DeleteServiceTemplate）用于删除协议端口模板

        :param request: 调用DeleteServiceTemplate所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DeleteServiceTemplateRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DeleteServiceTemplateResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DeleteServiceTemplate", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DeleteServiceTemplateResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DeleteServiceTemplateGroup(self, request):
        """本接口（DeleteServiceTemplateGroup）用于删除协议端口模板集合

        :param request: 调用DeleteServiceTemplateGroup所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DeleteServiceTemplateGroupRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DeleteServiceTemplateGroupResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DeleteServiceTemplateGroup", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DeleteServiceTemplateGroupResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DeleteSubnet(self, request):
        """本接口（DeleteSubnet）用于用于删除子网(Subnet)。
        * 删除子网前，请清理该子网下所有资源，包括云服务器、负载均衡、云数据、noSql、弹性网卡等资源。

        :param request: 调用DeleteSubnet所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DeleteSubnetRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DeleteSubnetResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DeleteSubnet", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DeleteSubnetResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DeleteTrafficMirror(self, request):
        """本接口（DeleteTrafficMirror）用于删除流量镜像实例。

        :param request: 调用DeleteTrafficMirror所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DeleteTrafficMirrorRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DeleteTrafficMirrorResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DeleteTrafficMirror", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DeleteTrafficMirrorResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DeleteTrafficPackages(self, request):
        """删除共享带宽包（仅非活动状态的流量包可删除）。

        :param request: 调用DeleteTrafficPackages所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DeleteTrafficPackagesRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DeleteTrafficPackagesResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DeleteTrafficPackages", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DeleteTrafficPackagesResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DeleteVpc(self, request):
        """本接口（DeleteVpc）用于删除私有网络。
        * 删除前请确保 VPC 内已经没有相关资源，例如云服务器、云数据库、NoSQL、VPN网关、专线网关、负载均衡、对等连接、与之互通的基础网络设备等。
        * 删除私有网络是不可逆的操作，请谨慎处理。

        :param request: 调用DeleteVpc所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DeleteVpcRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DeleteVpcResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DeleteVpc", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DeleteVpcResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DeleteVpnConnection(self, request):
        """本接口(DeleteVpnConnection)用于删除VPN通道。

        :param request: 调用DeleteVpnConnection所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DeleteVpnConnectionRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DeleteVpnConnectionResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DeleteVpnConnection", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DeleteVpnConnectionResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DeleteVpnGateway(self, request):
        """本接口（DeleteVpnGateway）用于删除VPN网关。目前只支持删除运行中的按量计费的IPSEC网关实例。

        :param request: 调用DeleteVpnGateway所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DeleteVpnGatewayRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DeleteVpnGatewayResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DeleteVpnGateway", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DeleteVpnGatewayResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeAccountAttributes(self, request):
        """本接口（DescribeAccountAttributes）用于查询用户账号私有属性。

        :param request: 调用DescribeAccountAttributes所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeAccountAttributesRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeAccountAttributesResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeAccountAttributes", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeAccountAttributesResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeAddressActionQuota(self, request):
        """该接口用于查询上移账户EIP操作配额

        :param request: 调用DescribeAddressActionQuota所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeAddressActionQuotaRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeAddressActionQuotaResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeAddressActionQuota", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeAddressActionQuotaResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeAddressAssociationQuota(self, request):
        """查询弹性公网IP（EIP）绑定配额

        :param request: 调用DescribeAddressAssociationQuota所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeAddressAssociationQuotaRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeAddressAssociationQuotaResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeAddressAssociationQuota", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeAddressAssociationQuotaResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeAddressAvailability(self, request):
        """查询弹性公网IP（EIP）库存状态

        :param request: 调用DescribeAddressAvailability所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeAddressAvailabilityRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeAddressAvailabilityResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeAddressAvailability", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeAddressAvailabilityResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeAddressBandwidthConfigs(self, request):
        """无

        :param request: 调用DescribeAddressBandwidthConfigs所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeAddressBandwidthConfigsRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeAddressBandwidthConfigsResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeAddressBandwidthConfigs", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeAddressBandwidthConfigsResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeAddressChangeQuota(self, request):
        """查询更换公网IP配额

        :param request: 调用DescribeAddressChangeQuota所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeAddressChangeQuotaRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeAddressChangeQuotaResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeAddressChangeQuota", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeAddressChangeQuotaResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeAddressQuota(self, request):
        """本接口 (DescribeAddressQuota) 用于查询您账户的弹性公网IP（简称 EIP）在当前地域的配额信息。配额详情可参见 EIP 产品简介。

        :param request: 调用DescribeAddressQuota所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeAddressQuotaRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeAddressQuotaResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeAddressQuota", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeAddressQuotaResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeAddressSet(self, request):
        """该接口支持查询弹性公网IP集群上的IP状态

        :param request: 调用DescribeAddressSet所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeAddressSetRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeAddressSetResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeAddressSet", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeAddressSetResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeAddressTemplateGroupInstances(self, request):
        """本接口（DescribeAddressTemplateGroupInstances）用于查询参数模板IP地址组口关联的实例列表。本接口不会返回查询的结果，需要根据返回的RequestId调用DescribeVpcTaskResult接口获取结果。

        :param request: 调用DescribeAddressTemplateGroupInstances所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeAddressTemplateGroupInstancesRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeAddressTemplateGroupInstancesResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeAddressTemplateGroupInstances", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeAddressTemplateGroupInstancesResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeAddressTemplateGroups(self, request):
        """本接口（DescribeAddressTemplateGroups）用于查询IP地址模板集合

        :param request: 调用DescribeAddressTemplateGroups所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeAddressTemplateGroupsRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeAddressTemplateGroupsResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeAddressTemplateGroups", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeAddressTemplateGroupsResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeAddressTemplateInstances(self, request):
        """本接口（DescribeAddressTemplateInstances）用于查询参数模板IP地址关联的实例列表。本接口不会返回查询的结果，需要根据返回的RequestId调用DescribeVpcTaskResult接口获取结果。

        :param request: 调用DescribeAddressTemplateInstances所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeAddressTemplateInstancesRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeAddressTemplateInstancesResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeAddressTemplateInstances", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeAddressTemplateInstancesResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeAddressTemplates(self, request):
        """本接口（DescribeAddressTemplates）用于查询IP地址模板

        :param request: 调用DescribeAddressTemplates所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeAddressTemplatesRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeAddressTemplatesResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeAddressTemplates", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeAddressTemplatesResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeAddresses(self, request):
        """本接口 (DescribeAddresses) 用于查询一个或多个弹性公网IP（简称 EIP）的详细信息。
        * 如果参数为空，返回当前用户一定数量（Limit所指定的数量，默认为20）的 EIP。

        :param request: 调用DescribeAddresses所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeAddressesRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeAddressesResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeAddresses", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeAddressesResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeAddressesHistory(self, request):
        """该接口用于查询账户以往使用过但是当前已释放的eip记录

        :param request: 调用DescribeAddressesHistory所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeAddressesHistoryRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeAddressesHistoryResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeAddressesHistory", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeAddressesHistoryResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeAnycastRegion(self, request):
        """本接口(DescribeAnycastRegion)用于查询当前支持AnycastEIP的地域信息.

        :param request: 调用DescribeAnycastRegion所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeAnycastRegionRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeAnycastRegionResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeAnycastRegion", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeAnycastRegionResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeAssistantCidr(self, request):
        """本接口（DescribeAssistantCidr）用于查询辅助CIDR列表。（接口灰度中，如需使用请提工单。）

        :param request: 调用DescribeAssistantCidr所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeAssistantCidrRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeAssistantCidrResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeAssistantCidr", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeAssistantCidrResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeAvailableZone(self, request):
        """获取EIP可用区列表信息

        :param request: 调用DescribeAvailableZone所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeAvailableZoneRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeAvailableZoneResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeAvailableZone", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeAvailableZoneResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeBandwidthAttribute(self, request):
        """该接口用于查询转化的带宽属性。

        :param request: 调用DescribeBandwidthAttribute所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeBandwidthAttributeRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeBandwidthAttributeResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeBandwidthAttribute", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeBandwidthAttributeResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeBandwidthPackageQuota(self, request):
        """接口用于查询账户在当前地域的带宽包上限数量以及使用数量

        :param request: 调用DescribeBandwidthPackageQuota所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeBandwidthPackageQuotaRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeBandwidthPackageQuotaResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeBandwidthPackageQuota", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeBandwidthPackageQuotaResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeBandwidthPackageResources(self, request):
        """本接口 (DescribeBandwidthPackageResources) 用于根据共享带宽包唯一ID查询共享带宽包内的资源列表，支持按条件过滤查询结果和分页查询。

        :param request: 调用DescribeBandwidthPackageResources所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeBandwidthPackageResourcesRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeBandwidthPackageResourcesResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeBandwidthPackageResources", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeBandwidthPackageResourcesResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeBandwidthPackages(self, request):
        """接口用于查询带宽包详细信息，包括带宽包唯一标识ID，类型，计费模式，名称，资源信息等

        :param request: 调用DescribeBandwidthPackages所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeBandwidthPackagesRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeBandwidthPackagesResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeBandwidthPackages", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeBandwidthPackagesResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeCcnAttachedInstances(self, request):
        """本接口（DescribeCcnAttachedInstances）用于查询云联网实例下已关联的网络实例。

        :param request: 调用DescribeCcnAttachedInstances所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeCcnAttachedInstancesRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeCcnAttachedInstancesResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeCcnAttachedInstances", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeCcnAttachedInstancesResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeCcnLimits(self, request):
        """本接口（DescribeCcnLimits）用于查询云联网配额。

        :param request: 调用DescribeCcnLimits所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeCcnLimitsRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeCcnLimitsResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeCcnLimits", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeCcnLimitsResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeCcnRegionBandwidthLimits(self, request):
        """本接口（DescribeCcnRegionBandwidthLimits）用于查询云联网各地域出带宽上限，该接口只返回已关联网络实例包含的地域

        :param request: 调用DescribeCcnRegionBandwidthLimits所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeCcnRegionBandwidthLimitsRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeCcnRegionBandwidthLimitsResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeCcnRegionBandwidthLimits", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeCcnRegionBandwidthLimitsResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeCcnRoutes(self, request):
        """本接口（DescribeCcnRoutes）用于查询已加入云联网（CCN）的路由

        :param request: 调用DescribeCcnRoutes所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeCcnRoutesRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeCcnRoutesResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeCcnRoutes", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeCcnRoutesResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeCcns(self, request):
        """本接口（DescribeCcns）用于查询云联网（CCN）列表。

        :param request: 调用DescribeCcns所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeCcnsRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeCcnsResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeCcns", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeCcnsResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeClassicLinkInstances(self, request):
        """本接口(DescribeClassicLinkInstances)用于查询私有网络和基础网络设备互通列表。

        :param request: 调用DescribeClassicLinkInstances所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeClassicLinkInstancesRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeClassicLinkInstancesResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeClassicLinkInstances", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeClassicLinkInstancesResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeCustomerGatewayVendors(self, request):
        """本接口（DescribeCustomerGatewayVendors）用于查询可支持的对端网关厂商信息。

        :param request: 调用DescribeCustomerGatewayVendors所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeCustomerGatewayVendorsRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeCustomerGatewayVendorsResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeCustomerGatewayVendors", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeCustomerGatewayVendorsResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeCustomerGateways(self, request):
        """本接口（DescribeCustomerGateways）用于查询对端网关列表。

        :param request: 调用DescribeCustomerGateways所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeCustomerGatewaysRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeCustomerGatewaysResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeCustomerGateways", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeCustomerGatewaysResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeDirectConnectGatewayCcnRoutes(self, request):
        """本接口（DescribeDirectConnectGatewayCcnRoutes）用于查询专线网关的云联网路由（IDC网段）

        :param request: 调用DescribeDirectConnectGatewayCcnRoutes所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeDirectConnectGatewayCcnRoutesRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeDirectConnectGatewayCcnRoutesResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeDirectConnectGatewayCcnRoutes", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeDirectConnectGatewayCcnRoutesResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeDirectConnectGateways(self, request):
        """本接口（DescribeDirectConnectGateways）用于查询专线网关。

        :param request: 调用DescribeDirectConnectGateways所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeDirectConnectGatewaysRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeDirectConnectGatewaysResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeDirectConnectGateways", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeDirectConnectGatewaysResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeDownloadSpecificTrafficPackageUsedDetails(self, request):
        """本接口(DescribeDownloadSpecificTrafficPackageUsedDetails)用于查询指定共享流量包的用量明细生成历史

        :param request: 调用DescribeDownloadSpecificTrafficPackageUsedDetails所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeDownloadSpecificTrafficPackageUsedDetailsRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeDownloadSpecificTrafficPackageUsedDetailsResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeDownloadSpecificTrafficPackageUsedDetails", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeDownloadSpecificTrafficPackageUsedDetailsResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeDownloadSpecificTrafficPackageUsedDetailsQuota(self, request):
        """本接口(DescribeDownloadSpecificTrafficPackageUsedDetailsQuota)用户查询指定共享流量包在当前时间的明细文件生成配额.

        :param request: 调用DescribeDownloadSpecificTrafficPackageUsedDetailsQuota所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeDownloadSpecificTrafficPackageUsedDetailsQuotaRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeDownloadSpecificTrafficPackageUsedDetailsQuotaResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeDownloadSpecificTrafficPackageUsedDetailsQuota", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeDownloadSpecificTrafficPackageUsedDetailsQuotaResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeEIPIspInfo(self, request):
        """本接口（DescribeEIPIspInfo）用于查询EIP运营商信息

        :param request: 调用DescribeEIPIspInfo所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeEIPIspInfoRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeEIPIspInfoResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeEIPIspInfo", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeEIPIspInfoResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeEipStatistics(self, request):
        """该接口用于查询各地域EIP数量统计信息，包括全地域EIP总数，和各地域的地域名称及其EIP总数等。

        :param request: 调用DescribeEipStatistics所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeEipStatisticsRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeEipStatisticsResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeEipStatistics", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeEipStatisticsResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeFlowLog(self, request):
        """本接口（DescribeFlowLog）用于查询流日志实例信息

        :param request: 调用DescribeFlowLog所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeFlowLogRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeFlowLogResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeFlowLog", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeFlowLogResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeFlowLogs(self, request):
        """本接口（DescribeFlowLogs）用于查询获取流日志集合

        :param request: 调用DescribeFlowLogs所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeFlowLogsRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeFlowLogsResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeFlowLogs", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeFlowLogsResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeGatewayFlowMonitorDetail(self, request):
        """本接口（DescribeGatewayFlowMonitorDetail）用于查询网关流量监控明细。
        * 只支持单个网关实例查询。即入参 `VpnId` `DirectConnectGatewayId` `PeeringConnectionId` `NatId` 最多只支持传一个，且必须传一个。
        * 如果网关有流量，但调用本接口没有返回数据，请在控制台对应网关详情页确认是否开启网关流量监控。

        :param request: 调用DescribeGatewayFlowMonitorDetail所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeGatewayFlowMonitorDetailRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeGatewayFlowMonitorDetailResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeGatewayFlowMonitorDetail", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeGatewayFlowMonitorDetailResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeGatewayFlowQos(self, request):
        """本接口（DescribeGatewayFlowQos）用于查询网关来访IP流控带宽。

        :param request: 调用DescribeGatewayFlowQos所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeGatewayFlowQosRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeGatewayFlowQosResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeGatewayFlowQos", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeGatewayFlowQosResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeHaVips(self, request):
        """本接口（DescribeHaVips）用于查询高可用虚拟IP（HAVIP）列表。

        :param request: 调用DescribeHaVips所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeHaVipsRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeHaVipsResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeHaVips", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeHaVipsResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeIp6Addresses(self, request):
        """该接口用于查询IPV6地址信息

        :param request: 调用DescribeIp6Addresses所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeIp6AddressesRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeIp6AddressesResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeIp6Addresses", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeIp6AddressesResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeIp6IdcInfo(self, request):
        """查询IPV6创建时的IDC信息

        :param request: 调用DescribeIp6IdcInfo所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeIp6IdcInfoRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeIp6IdcInfoResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeIp6IdcInfo", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeIp6IdcInfoResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeIp6TranslatorQuota(self, request):
        """查询账户在指定地域IPV6转换实例和规则的配额

        :param request: 调用DescribeIp6TranslatorQuota所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeIp6TranslatorQuotaRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeIp6TranslatorQuotaResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeIp6TranslatorQuota", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeIp6TranslatorQuotaResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeIp6Translators(self, request):
        """1. 该接口用于查询账户下的IPV6转换实例及其绑定的转换规则信息
        2. 支持过滤查询

        :param request: 调用DescribeIp6Translators所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeIp6TranslatorsRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeIp6TranslatorsResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeIp6Translators", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeIp6TranslatorsResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeIpLocation(self, request):
        """该接口仅面向腾讯内部用户账号，用于查询IP地址信息，包括地理位置信息和网络信息。

        :param request: 调用DescribeIpLocation所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeIpLocationRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeIpLocationResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeIpLocation", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeIpLocationResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeIpLocationDownloadLink(self, request):
        """该接口仅面向腾讯内部用户账号，用于获取ip地址库下载链接

        :param request: 调用DescribeIpLocationDownloadLink所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeIpLocationDownloadLinkRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeIpLocationDownloadLinkResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeIpLocationDownloadLink", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeIpLocationDownloadLinkResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeIpOnline(self, request):
        """【废弃，采用DescribeIpLocation替代】查询IP地址信息，包括地理位置信息和网络信息

        :param request: 调用DescribeIpOnline所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeIpOnlineRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeIpOnlineResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeIpOnline", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeIpOnlineResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeLocalDestinationIpPortTranslationNatRules(self, request):
        """查询专线网关本端目的IP端口转换

        :param request: 调用DescribeLocalDestinationIpPortTranslationNatRules所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeLocalDestinationIpPortTranslationNatRulesRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeLocalDestinationIpPortTranslationNatRulesResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeLocalDestinationIpPortTranslationNatRules", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeLocalDestinationIpPortTranslationNatRulesResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeLocalIpTranslationAclRules(self, request):
        """查询专线网关本端IP转换ACL规则

        :param request: 调用DescribeLocalIpTranslationAclRules所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeLocalIpTranslationAclRulesRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeLocalIpTranslationAclRulesResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeLocalIpTranslationAclRules", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeLocalIpTranslationAclRulesResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeLocalIpTranslationNatRules(self, request):
        """查询专线网关本端IP转换

        :param request: 调用DescribeLocalIpTranslationNatRules所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeLocalIpTranslationNatRulesRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeLocalIpTranslationNatRulesResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeLocalIpTranslationNatRules", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeLocalIpTranslationNatRulesResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeLocalSourceIpPortTranslationAclRules(self, request):
        """查询专线网关本端源IP端口转换ACL规则

        :param request: 调用DescribeLocalSourceIpPortTranslationAclRules所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeLocalSourceIpPortTranslationAclRulesRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeLocalSourceIpPortTranslationAclRulesResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeLocalSourceIpPortTranslationAclRules", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeLocalSourceIpPortTranslationAclRulesResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeLocalSourceIpPortTranslationNatRules(self, request):
        """查询专线网关本端源IP端口转换

        :param request: 调用DescribeLocalSourceIpPortTranslationNatRules所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeLocalSourceIpPortTranslationNatRulesRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeLocalSourceIpPortTranslationNatRulesResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeLocalSourceIpPortTranslationNatRules", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeLocalSourceIpPortTranslationNatRulesResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeNatGatewayDestinationIpPortTranslationNatRules(self, request):
        """本接口（DescribeNatGatewayDestinationIpPortTranslationNatRules）用于查询NAT网关端口转发规则对象数组。

        :param request: 调用DescribeNatGatewayDestinationIpPortTranslationNatRules所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeNatGatewayDestinationIpPortTranslationNatRulesRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeNatGatewayDestinationIpPortTranslationNatRulesResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeNatGatewayDestinationIpPortTranslationNatRules", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeNatGatewayDestinationIpPortTranslationNatRulesResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeNatGatewayQuota(self, request):
        """本接口（DescribeNatGatewayQuota）用于查询 NAT 网关配额。

        :param request: 调用DescribeNatGatewayQuota所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeNatGatewayQuotaRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeNatGatewayQuotaResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeNatGatewayQuota", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeNatGatewayQuotaResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeNatGateways(self, request):
        """本接口（DescribeNatGateways）用于查询 NAT 网关。

        :param request: 调用DescribeNatGateways所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeNatGatewaysRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeNatGatewaysResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeNatGateways", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeNatGatewaysResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeNetDetectStates(self, request):
        """本接口(DescribeNetDetectStates)用于查询网络探测验证结果列表。

        :param request: 调用DescribeNetDetectStates所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeNetDetectStatesRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeNetDetectStatesResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeNetDetectStates", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeNetDetectStatesResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeNetDetects(self, request):
        """本接口（DescribeNetDetects）用于查询网络探测列表。

        :param request: 调用DescribeNetDetects所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeNetDetectsRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeNetDetectsResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeNetDetects", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeNetDetectsResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeNetworkAcls(self, request):
        """本接口（DescribeNetworkAcls）用于查询网络ACL列表。

        :param request: 调用DescribeNetworkAcls所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeNetworkAclsRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeNetworkAclsResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeNetworkAcls", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeNetworkAclsResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeNetworkInterfaceExtendIps(self, request):
        """获取弹性网卡的扩展ip

        :param request: 调用DescribeNetworkInterfaceExtendIps所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeNetworkInterfaceExtendIpsRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeNetworkInterfaceExtendIpsResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeNetworkInterfaceExtendIps", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeNetworkInterfaceExtendIpsResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeNetworkInterfaceLimit(self, request):
        """本接口（DescribeNetworkInterfaceLimit）根据CVM实例ID或弹性网卡ID查询弹性网卡配额，返回该CVM实例或弹性网卡能绑定的弹性网卡配额，以及弹性网卡可以分配的IP配额

        :param request: 调用DescribeNetworkInterfaceLimit所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeNetworkInterfaceLimitRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeNetworkInterfaceLimitResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeNetworkInterfaceLimit", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeNetworkInterfaceLimitResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeNetworkInterfaces(self, request):
        """本接口（DescribeNetworkInterfaces）用于查询弹性网卡列表。

        :param request: 调用DescribeNetworkInterfaces所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeNetworkInterfacesRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeNetworkInterfacesResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeNetworkInterfaces", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeNetworkInterfacesResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeNetworkInterfacesExtra(self, request):
        """本接口（DescribeNetworkInterfacesExtra）用于查询弹性网卡列表（IP维度），支持根据内网IP模糊查询。

        :param request: 调用DescribeNetworkInterfacesExtra所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeNetworkInterfacesExtraRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeNetworkInterfacesExtraResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeNetworkInterfacesExtra", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeNetworkInterfacesExtraResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeNmsCidrs(self, request):
        """查询非标网段

        :param request: 调用DescribeNmsCidrs所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeNmsCidrsRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeNmsCidrsResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeNmsCidrs", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeNmsCidrsResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribePeerIpTranslationNatRules(self, request):
        """查询专线网关对端IP转换

        :param request: 调用DescribePeerIpTranslationNatRules所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribePeerIpTranslationNatRulesRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribePeerIpTranslationNatRulesResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribePeerIpTranslationNatRules", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribePeerIpTranslationNatRulesResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeRegions(self, request):
        """本接口（DescribeRegions）用于查询Tce地域（大区）列表，本接口没有入参，固定返回已开服的所有大区列表。

        :param request: 调用DescribeRegions所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeRegionsRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeRegionsResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeRegions", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeRegionsResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeRouteConflicts(self, request):
        """本接口（DescribeRouteConflicts）用于查询自定义路由策略与云联网路由策略冲突列表

        :param request: 调用DescribeRouteConflicts所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeRouteConflictsRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeRouteConflictsResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeRouteConflicts", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeRouteConflictsResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeRouteTables(self, request):
        """本接口（DescribeRouteTables）用于查询路由表。

        :param request: 调用DescribeRouteTables所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeRouteTablesRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeRouteTablesResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeRouteTables", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeRouteTablesResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeRoutes(self, request):
        """本接口（DescribeRoutes）用于查询路由列表。

        :param request: 调用DescribeRoutes所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeRoutesRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeRoutesResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeRoutes", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeRoutesResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeSecurityGroupAssociationStatistics(self, request):
        """本接口（DescribeSecurityGroupAssociationStatistics）用于查询安全组关联的实例统计。

        :param request: 调用DescribeSecurityGroupAssociationStatistics所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeSecurityGroupAssociationStatisticsRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeSecurityGroupAssociationStatisticsResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeSecurityGroupAssociationStatistics", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeSecurityGroupAssociationStatisticsResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeSecurityGroupLimits(self, request):
        """本接口(DescribeSecurityGroupLimits)用于查询用户安全组配额。

        :param request: 调用DescribeSecurityGroupLimits所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeSecurityGroupLimitsRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeSecurityGroupLimitsResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeSecurityGroupLimits", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeSecurityGroupLimitsResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeSecurityGroupPolicies(self, request):
        """本接口（DescribeSecurityGroupPolicies）用于查询安全组规则。

        :param request: 调用DescribeSecurityGroupPolicies所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeSecurityGroupPoliciesRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeSecurityGroupPoliciesResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeSecurityGroupPolicies", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeSecurityGroupPoliciesResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeSecurityGroupPolicyTemplates(self, request):
        """本接口（DescribeSecurityGroupPolicyTemplates）用于查询安全组规则模板列表。

        :param request: 调用DescribeSecurityGroupPolicyTemplates所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeSecurityGroupPolicyTemplatesRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeSecurityGroupPolicyTemplatesResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeSecurityGroupPolicyTemplates", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeSecurityGroupPolicyTemplatesResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeSecurityGroupReferences(self, request):
        """本接口（DescribeSecurityGroupReferences）用于查询安全组被引用信息。

        :param request: 调用DescribeSecurityGroupReferences所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeSecurityGroupReferencesRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeSecurityGroupReferencesResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeSecurityGroupReferences", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeSecurityGroupReferencesResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeSecurityGroups(self, request):
        """本接口（DescribeSecurityGroups）用于查询安全组。

        :param request: 调用DescribeSecurityGroups所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeSecurityGroupsRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeSecurityGroupsResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeSecurityGroups", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeSecurityGroupsResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeServiceTemplateGroupInstances(self, request):
        """本接口（DescribeServiceTemplateGroupInstances）用于查询参数模板协议端口组关联的实例列表。本接口不会返回查询的结果，需要根据返回的RequestId调用DescribeVpcTaskResult接口获取结果。

        :param request: 调用DescribeServiceTemplateGroupInstances所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeServiceTemplateGroupInstancesRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeServiceTemplateGroupInstancesResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeServiceTemplateGroupInstances", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeServiceTemplateGroupInstancesResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeServiceTemplateGroups(self, request):
        """本接口（DescribeServiceTemplateGroups）用于查询协议端口模板集合

        :param request: 调用DescribeServiceTemplateGroups所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeServiceTemplateGroupsRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeServiceTemplateGroupsResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeServiceTemplateGroups", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeServiceTemplateGroupsResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeServiceTemplateInstances(self, request):
        """本接口（DescribeServiceTemplateInstances）用于查询参数模板协议端口关联的实例列表。本接口不会返回查询的结果，需要根据返回的RequestId调用DescribeVpcTaskResult接口获取结果。

        :param request: 调用DescribeServiceTemplateInstances所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeServiceTemplateInstancesRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeServiceTemplateInstancesResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeServiceTemplateInstances", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeServiceTemplateInstancesResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeServiceTemplates(self, request):
        """本接口（DescribeServiceTemplates）用于查询协议端口模板

        :param request: 调用DescribeServiceTemplates所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeServiceTemplatesRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeServiceTemplatesResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeServiceTemplates", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeServiceTemplatesResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeSingleIspRegion(self, request):
        """查询可用区对应的EIP运营商信息，包括CMCC/CTCC/CUCC

        :param request: 调用DescribeSingleIspRegion所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeSingleIspRegionRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeSingleIspRegionResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeSingleIspRegion", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeSingleIspRegionResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeSpecificTrafficPackageResourcesUsedStatistics(self, request):
        """本接口(DescribeSpecificTrafficPackageResourcesUsedStatistics)用于查询指定共享流量包内的资源在某一时间区间内的抵扣量信息

        :param request: 调用DescribeSpecificTrafficPackageResourcesUsedStatistics所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeSpecificTrafficPackageResourcesUsedStatisticsRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeSpecificTrafficPackageResourcesUsedStatisticsResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeSpecificTrafficPackageResourcesUsedStatistics", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeSpecificTrafficPackageResourcesUsedStatisticsResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeSpecificTrafficPackageUsedDetails(self, request):
        """本接口 (DescribeSpecificTrafficPackageUsedDetails) 用于查询指定 共享流量包 的用量明细。

        :param request: 调用DescribeSpecificTrafficPackageUsedDetails所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeSpecificTrafficPackageUsedDetailsRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeSpecificTrafficPackageUsedDetailsResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeSpecificTrafficPackageUsedDetails", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeSpecificTrafficPackageUsedDetailsResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeSubnetIds(self, request):
        """本接口（DescribeSubnetIds）用于查询子网数字ID。

        :param request: 调用DescribeSubnetIds所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeSubnetIdsRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeSubnetIdsResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeSubnetIds", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeSubnetIdsResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeSubnets(self, request):
        """本接口（DescribeSubnets）用于查询子网列表。

        :param request: 调用DescribeSubnets所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeSubnetsRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeSubnetsResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeSubnets", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeSubnetsResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeTaskResult(self, request):
        """查询EIP异步任务执行结果

        :param request: 调用DescribeTaskResult所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeTaskResultRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeTaskResultResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeTaskResult", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeTaskResultResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeTemplateLimits(self, request):
        """本接口（DescribeTemplateLimits）用于查询参数模板配额列表。

        :param request: 调用DescribeTemplateLimits所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeTemplateLimitsRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeTemplateLimitsResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeTemplateLimits", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeTemplateLimitsResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeTrafficMirrors(self, request):
        """本接口（DescribeTrafficMirrors）用于查询流量镜像实例信息。

        :param request: 调用DescribeTrafficMirrors所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeTrafficMirrorsRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeTrafficMirrorsResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeTrafficMirrors", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeTrafficMirrorsResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeTrafficPackageQuota(self, request):
        """接口用于查询账户在当前地域的共享流量包上限数量以及使用数量

        :param request: 调用DescribeTrafficPackageQuota所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeTrafficPackageQuotaRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeTrafficPackageQuotaResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeTrafficPackageQuota", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeTrafficPackageQuotaResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeTrafficPackageStatistics(self, request):
        """接口用于查询各地域共享流量包数量统计信息，包括全地域共享流量包总数、各地域的地域名称及其共享流量包总数等。

        :param request: 调用DescribeTrafficPackageStatistics所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeTrafficPackageStatisticsRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeTrafficPackageStatisticsResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeTrafficPackageStatistics", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeTrafficPackageStatisticsResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeTrafficPackages(self, request):
        """接口用于查询共享流量包详细信息，包括共享流量包唯一标识ID，名称，流量使用信息等

        :param request: 调用DescribeTrafficPackages所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeTrafficPackagesRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeTrafficPackagesResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeTrafficPackages", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeTrafficPackagesResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeVpcExtendCidrs(self, request):
        """查询vpc扩展CIDR段

        :param request: 调用DescribeVpcExtendCidrs所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeVpcExtendCidrsRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeVpcExtendCidrsResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeVpcExtendCidrs", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeVpcExtendCidrsResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeVpcGateways(self, request):
        """本接口（DescribeVpcGateways）用于查询VPC下的网关列表。

        :param request: 调用DescribeVpcGateways所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeVpcGatewaysRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeVpcGatewaysResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeVpcGateways", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeVpcGatewaysResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeVpcGlobalExtendCidrs(self, request):
        """获取VPC全局扩展CIDR列表

        :param request: 调用DescribeVpcGlobalExtendCidrs所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeVpcGlobalExtendCidrsRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeVpcGlobalExtendCidrsResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeVpcGlobalExtendCidrs", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeVpcGlobalExtendCidrsResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeVpcIds(self, request):
        """本接口（DescribeVpcIds）用于查询VPC数字ID。

        :param request: 调用DescribeVpcIds所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeVpcIdsRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeVpcIdsResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeVpcIds", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeVpcIdsResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeVpcInstances(self, request):
        """本接口（DescribeVpcInstances）用于查询VPC下的云主机实例列表。

        :param request: 调用DescribeVpcInstances所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeVpcInstancesRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeVpcInstancesResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeVpcInstances", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeVpcInstancesResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeVpcIpv6Addresses(self, request):
        """本接口（DescribeVpcIpv6Addresses）用于查询 `VPC` `IPv6` 信息。
        只能查询已使用的`IPv6`信息，当查询未使用的IP时，本接口不会报错，但不会出现在返回结果里。

        :param request: 调用DescribeVpcIpv6Addresses所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeVpcIpv6AddressesRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeVpcIpv6AddressesResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeVpcIpv6Addresses", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeVpcIpv6AddressesResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeVpcLimits(self, request):
        """获取私有网络配额，部分私有网络的配额有地域属性。
        LimitTypes取值范围：
        * appid-max-vpcs （每个开发商每个地域可创建的VPC数）
        * vpc-max-subnets（每个VPC可创建的子网数）
        * vpc-max-route-tables（每个VPC可创建的路由表数）
        * route-table-max-policies（每个路由表可添加的策略数）
        * vpc-max-vpn-gateways（每个VPC可创建的VPN网关数）
        * appid-max-custom-gateways（每个开发商可创建的对端网关数）
        * appid-max-vpn-connections（每个开发商可创建的VPN通道数）
        * custom-gateway-max-vpn-connections（每个对端网关可创建的VPN通道数）
        * vpn-gateway-max-custom-gateways（每个VPNGW可以创建的通道数）
        * vpc-max-network-acls（每个VPC可创建的网络ACL数）
        * network-acl-max-inbound-policies（每个网络ACL可添加的入站规则数）
        * network-acl-max-outbound-policies（每个网络ACL可添加的出站规则数）
        * vpc-max-vpcpeers（每个VPC可创建的对等连接数）
        * vpc-max-available-vpcpeers（每个VPC可创建的有效对等连接数）
        * vpc-max-basic-network-interconnections（每个VPC可创建的基础网络云主机与VPC互通数）
        * direct-connection-max-snats（每个专线网关可创建的SNAT数）
        * direct-connection-max-dnats（每个专线网关可创建的DNAT数）
        * direct-connection-max-snapts（每个专线网关可创建的SNAPT数）
        * direct-connection-max-dnapts（每个专线网关可创建的DNAPT数）
        * vpc-max-nat-gateways（每个VPC可创建的NAT网关数）
        * nat-gateway-max-eips（每个NAT可以购买的外网IP数量）
        * vpc-max-enis（每个VPC可创建弹性网卡数）
        * vpc-max-havips（每个VPC可创建HAVIP数）
        * eni-max-private-ips（每个ENI可以绑定的内网IP数（ENI未绑定子机））
        * nat-gateway-max-dnapts（每个NAT网关可创建的DNAPT数）
        * vpc-max-ipv6s（每个VPC可分配的IPv6地址数）
        * eni-max-ipv6s（每个ENI可分配的IPv6地址数）
        * vpc-max-assistant_cidrs（每个VPC可分配的辅助CIDR数）

        :param request: 调用DescribeVpcLimits所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeVpcLimitsRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeVpcLimitsResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeVpcLimits", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeVpcLimitsResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeVpcPrivateIpAddresses(self, request):
        """本接口（DescribeVpcPrivateIpAddresses）用于查询VPC内网IP信息。<br />
        只能查询已使用的IP信息，当查询未使用的IP时，本接口不会报错，但不会出现在返回结果里。

        :param request: 调用DescribeVpcPrivateIpAddresses所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeVpcPrivateIpAddressesRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeVpcPrivateIpAddressesResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeVpcPrivateIpAddresses", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeVpcPrivateIpAddressesResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeVpcResourceDashboard(self, request):
        """本接口(DescribeVpcResourceDashboard)用于查看VPC资源信息。

        :param request: 调用DescribeVpcResourceDashboard所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeVpcResourceDashboardRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeVpcResourceDashboardResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeVpcResourceDashboard", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeVpcResourceDashboardResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeVpcTaskResult(self, request):
        """本接口（DescribeVpcTaskResult）用于查询VPC任务执行结果。

        :param request: 调用DescribeVpcTaskResult所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeVpcTaskResultRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeVpcTaskResultResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeVpcTaskResult", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeVpcTaskResultResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeVpcs(self, request):
        """本接口（DescribeVpcs）用于查询私有网络列表。

        :param request: 调用DescribeVpcs所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeVpcsRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeVpcsResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeVpcs", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeVpcsResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeVpnConnections(self, request):
        """本接口（DescribeVpnConnections）查询VPN通道列表。

        :param request: 调用DescribeVpnConnections所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeVpnConnectionsRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeVpnConnectionsResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeVpnConnections", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeVpnConnectionsResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeVpnGatewayCcnRoutes(self, request):
        """本接口（DescribeVpnGatewayCcnRoutes）用于查询VPN网关云联网路由

        :param request: 调用DescribeVpnGatewayCcnRoutes所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeVpnGatewayCcnRoutesRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeVpnGatewayCcnRoutesResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeVpnGatewayCcnRoutes", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeVpnGatewayCcnRoutesResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeVpnGatewayQuota(self, request):
        """查询VPN网关配额

        :param request: 调用DescribeVpnGatewayQuota所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeVpnGatewayQuotaRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeVpnGatewayQuotaResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeVpnGatewayQuota", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeVpnGatewayQuotaResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DescribeVpnGateways(self, request):
        """本接口（DescribeVpnGateways）用于查询VPN网关列表。

        :param request: 调用DescribeVpnGateways所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DescribeVpnGatewaysRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DescribeVpnGatewaysResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DescribeVpnGateways", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DescribeVpnGatewaysResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DetachCcnInstances(self, request):
        """本接口（DetachCcnInstances）用于从云联网实例中解关联指定的网络实例。<br />
        解关联网络实例后，相应的路由策略会一并删除。

        :param request: 调用DetachCcnInstances所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DetachCcnInstancesRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DetachCcnInstancesResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DetachCcnInstances", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DetachCcnInstancesResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DetachClassicLinkVpc(self, request):
        """本接口(DetachClassicLinkVpc)用于删除私有网络和基础网络设备互通。

        :param request: 调用DetachClassicLinkVpc所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DetachClassicLinkVpcRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DetachClassicLinkVpcResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DetachClassicLinkVpc", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DetachClassicLinkVpcResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DetachNetworkInterface(self, request):
        """本接口（DetachNetworkInterface）用于弹性网卡解绑云主机。

        :param request: 调用DetachNetworkInterface所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DetachNetworkInterfaceRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DetachNetworkInterfaceResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DetachNetworkInterface", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DetachNetworkInterfaceResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DisableCcnRoutes(self, request):
        """本接口（DisableCcnRoutes）用于禁用已经启用的云联网（CCN）路由

        :param request: 调用DisableCcnRoutes所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DisableCcnRoutesRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DisableCcnRoutesResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DisableCcnRoutes", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DisableCcnRoutesResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DisableGatewayFlowMonitor(self, request):
        """本接口（DisableGatewayFlowMonitor）用于关闭网关流量监控。

        :param request: 调用DisableGatewayFlowMonitor所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DisableGatewayFlowMonitorRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DisableGatewayFlowMonitorResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DisableGatewayFlowMonitor", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DisableGatewayFlowMonitorResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DisableRoutes(self, request):
        """本接口（DisableRoutes）用于禁用已启用的子网路由

        :param request: 调用DisableRoutes所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DisableRoutesRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DisableRoutesResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DisableRoutes", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DisableRoutesResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DisassociateAddress(self, request):
        """本接口 (DisassociateAddress) 用于解绑弹性公网IP（简称 EIP）。
        * 支持CVM实例，弹性网卡上的EIP解绑
        * 不支持NAT上的EIP解绑。NAT上的EIP解绑请参考EipUnBindNatGateway
        * 只有状态为 BIND 和 BIND_ENI 的 EIP 才能进行解绑定操作。
        * EIP 如果被封堵，则不能进行解绑定操作。

        :param request: 调用DisassociateAddress所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DisassociateAddressRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DisassociateAddressResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DisassociateAddress", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DisassociateAddressResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DisassociateNatGatewayAddress(self, request):
        """本接口（DisassociateNatGatewayAddress）用于NAT网关解绑弹性IP。

        :param request: 调用DisassociateNatGatewayAddress所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DisassociateNatGatewayAddressRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DisassociateNatGatewayAddressResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DisassociateNatGatewayAddress", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DisassociateNatGatewayAddressResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DisassociateNetworkAclSubnets(self, request):
        """本接口（DisassociateNetworkAclSubnets）用于网络ACL解关联vpc下的子网。

        :param request: 调用DisassociateNetworkAclSubnets所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DisassociateNetworkAclSubnetsRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DisassociateNetworkAclSubnetsResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DisassociateNetworkAclSubnets", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DisassociateNetworkAclSubnetsResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DisassociateNetworkInterfaceSecurityGroups(self, request):
        """本接口（DisassociateNetworkInterfaceSecurityGroups）用于弹性网卡解绑安全组。支持弹性网卡完全解绑安全组。

        :param request: 调用DisassociateNetworkInterfaceSecurityGroups所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DisassociateNetworkInterfaceSecurityGroupsRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DisassociateNetworkInterfaceSecurityGroupsResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DisassociateNetworkInterfaceSecurityGroups", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DisassociateNetworkInterfaceSecurityGroupsResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DownloadCustomerGatewayConfiguration(self, request):
        """本接口(DownloadCustomerGatewayConfiguration)用于下载VPN通道配置。

        :param request: 调用DownloadCustomerGatewayConfiguration所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DownloadCustomerGatewayConfigurationRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DownloadCustomerGatewayConfigurationResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DownloadCustomerGatewayConfiguration", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DownloadCustomerGatewayConfigurationResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def DownloadSpecificTrafficPackageUsedDetails(self, request):
        """本接口(DownloadSpecificTrafficPackageUsedDetails)用于生成指定流量包的用量明细文件.

        :param request: 调用DownloadSpecificTrafficPackageUsedDetails所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.DownloadSpecificTrafficPackageUsedDetailsRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.DownloadSpecificTrafficPackageUsedDetailsResponse`

        """
        try:
            params = request._serialize()
            body = self.call("DownloadSpecificTrafficPackageUsedDetails", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.DownloadSpecificTrafficPackageUsedDetailsResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def EnableCcnRoutes(self, request):
        """本接口（EnableCcnRoutes）用于启用已经加入云联网（CCN）的路由。<br />
        本接口会校验启用后，是否与已有路由冲突，如果冲突，则无法启用，失败处理。路由冲突时，需要先禁用与之冲突的路由，才能启用该路由。

        :param request: 调用EnableCcnRoutes所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.EnableCcnRoutesRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.EnableCcnRoutesResponse`

        """
        try:
            params = request._serialize()
            body = self.call("EnableCcnRoutes", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.EnableCcnRoutesResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def EnableGatewayFlowMonitor(self, request):
        """本接口（EnableGatewayFlowMonitor）用于开启网关流量监控。

        :param request: 调用EnableGatewayFlowMonitor所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.EnableGatewayFlowMonitorRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.EnableGatewayFlowMonitorResponse`

        """
        try:
            params = request._serialize()
            body = self.call("EnableGatewayFlowMonitor", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.EnableGatewayFlowMonitorResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def EnableRoutes(self, request):
        """本接口（EnableRoutes）用于启用已禁用的子网路由。<br />
        本接口会校验启用后，是否与已有路由冲突，如果冲突，则无法启用，失败处理。路由冲突时，需要先禁用与之冲突的路由，才能启用该路由。

        :param request: 调用EnableRoutes所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.EnableRoutesRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.EnableRoutesResponse`

        """
        try:
            params = request._serialize()
            body = self.call("EnableRoutes", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.EnableRoutesResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def FlushHaVip(self, request):
        """本接口（FlushHaVip）用于刷新HAVIP配置。

        :param request: 调用FlushHaVip所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.FlushHaVipRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.FlushHaVipResponse`

        """
        try:
            params = request._serialize()
            body = self.call("FlushHaVip", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.FlushHaVipResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def GetCcnRegionBandwidthLimits(self, request):
        """本接口（GetCcnRegionBandwidthLimits）用于查询云联网相关地域带宽信息，该接口只返回已关联网络实例包含的地域

        :param request: 调用GetCcnRegionBandwidthLimits所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.GetCcnRegionBandwidthLimitsRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.GetCcnRegionBandwidthLimitsResponse`

        """
        try:
            params = request._serialize()
            body = self.call("GetCcnRegionBandwidthLimits", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.GetCcnRegionBandwidthLimitsResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def GetCreateCcnBandwidthDeal(self, request):
        """获取创建云联网带宽的商品信息

        :param request: 调用GetCreateCcnBandwidthDeal所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.GetCreateCcnBandwidthDealRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.GetCreateCcnBandwidthDealResponse`

        """
        try:
            params = request._serialize()
            body = self.call("GetCreateCcnBandwidthDeal", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.GetCreateCcnBandwidthDealResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def GetDealStatusByName(self, request):
        """本接口（GetDealStatusByName）用于查询云联网预付费订单的状态信息

        :param request: 调用GetDealStatusByName所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.GetDealStatusByNameRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.GetDealStatusByNameResponse`

        """
        try:
            params = request._serialize()
            body = self.call("GetDealStatusByName", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.GetDealStatusByNameResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def GetRenewCcnBandwidthDeal(self, request):
        """本接口用于获取续费云联网带宽订单信息。

        :param request: 调用GetRenewCcnBandwidthDeal所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.GetRenewCcnBandwidthDealRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.GetRenewCcnBandwidthDealResponse`

        """
        try:
            params = request._serialize()
            body = self.call("GetRenewCcnBandwidthDeal", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.GetRenewCcnBandwidthDealResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def GetUpdateCcnBandwidthDeal(self, request):
        """本接口用于获取变更云联网带宽的商品信息

        :param request: 调用GetUpdateCcnBandwidthDeal所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.GetUpdateCcnBandwidthDealRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.GetUpdateCcnBandwidthDealResponse`

        """
        try:
            params = request._serialize()
            body = self.call("GetUpdateCcnBandwidthDeal", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.GetUpdateCcnBandwidthDealResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def HaVipAssociateAddressIp(self, request):
        """本接口（HaVipAssociateAddressIp）用于高可用虚拟IP（HAVIP）绑定弹性公网IP（EIP）<br />
        本接口是异步完成，如需查询异步任务执行结果，请使用本接口返回的`RequestId`轮询`QueryTask`接口

        :param request: 调用HaVipAssociateAddressIp所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.HaVipAssociateAddressIpRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.HaVipAssociateAddressIpResponse`

        """
        try:
            params = request._serialize()
            body = self.call("HaVipAssociateAddressIp", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.HaVipAssociateAddressIpResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def HaVipDisassociateAddressIp(self, request):
        """本接口（HaVipDisassociateAddressIp）用于将高可用虚拟IP（HAVIP）已绑定的弹性公网IP（EIP）解除绑定<br />
        本接口是异步完成，如需查询异步任务执行结果，请使用本接口返回的`RequestId`轮询`QueryTask`接口

        :param request: 调用HaVipDisassociateAddressIp所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.HaVipDisassociateAddressIpRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.HaVipDisassociateAddressIpResponse`

        """
        try:
            params = request._serialize()
            body = self.call("HaVipDisassociateAddressIp", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.HaVipDisassociateAddressIpResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def InquiryPriceAllocateAddresses(self, request):
        """无

        :param request: 调用InquiryPriceAllocateAddresses所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.InquiryPriceAllocateAddressesRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.InquiryPriceAllocateAddressesResponse`

        """
        try:
            params = request._serialize()
            body = self.call("InquiryPriceAllocateAddresses", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.InquiryPriceAllocateAddressesResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def InquiryPriceAllocateIp6AddressesBandwidth(self, request):
        """该接口用于查询IPV6地址分配公网带宽价格

        :param request: 调用InquiryPriceAllocateIp6AddressesBandwidth所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.InquiryPriceAllocateIp6AddressesBandwidthRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.InquiryPriceAllocateIp6AddressesBandwidthResponse`

        """
        try:
            params = request._serialize()
            body = self.call("InquiryPriceAllocateIp6AddressesBandwidth", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.InquiryPriceAllocateIp6AddressesBandwidthResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def InquiryPriceCreateBandwidthPackage(self, request):
        """无

        :param request: 调用InquiryPriceCreateBandwidthPackage所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.InquiryPriceCreateBandwidthPackageRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.InquiryPriceCreateBandwidthPackageResponse`

        """
        try:
            params = request._serialize()
            body = self.call("InquiryPriceCreateBandwidthPackage", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.InquiryPriceCreateBandwidthPackageResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def InquiryPriceCreateCcnBandwidth(self, request):
        """本接口（InquiryPriceCreateCcnBandwidth）用于创建预付费云联网实例地域间带宽时的询价

        :param request: 调用InquiryPriceCreateCcnBandwidth所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.InquiryPriceCreateCcnBandwidthRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.InquiryPriceCreateCcnBandwidthResponse`

        """
        try:
            params = request._serialize()
            body = self.call("InquiryPriceCreateCcnBandwidth", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.InquiryPriceCreateCcnBandwidthResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def InquiryPriceCreateTrafficPackages(self, request):
        """无

        :param request: 调用InquiryPriceCreateTrafficPackages所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.InquiryPriceCreateTrafficPackagesRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.InquiryPriceCreateTrafficPackagesResponse`

        """
        try:
            params = request._serialize()
            body = self.call("InquiryPriceCreateTrafficPackages", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.InquiryPriceCreateTrafficPackagesResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def InquiryPriceCreateVpnGateway(self, request):
        """本接口（InquiryPriceCreateVpnGateway）用于创建VPN网关询价。

        :param request: 调用InquiryPriceCreateVpnGateway所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.InquiryPriceCreateVpnGatewayRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.InquiryPriceCreateVpnGatewayResponse`

        """
        try:
            params = request._serialize()
            body = self.call("InquiryPriceCreateVpnGateway", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.InquiryPriceCreateVpnGatewayResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def InquiryPriceModifyAddressInternetChargeType(self, request):
        """该接口用于调整上移账户弹性公网IP网络计费模式的差价查询
        * 支持BANDWIDTH_PREPAID_BY_MONTH和TRAFFIC_POSTPAID_BY_HOUR两种网络计费模式相互调整时的差价查询

        :param request: 调用InquiryPriceModifyAddressInternetChargeType所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.InquiryPriceModifyAddressInternetChargeTypeRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.InquiryPriceModifyAddressInternetChargeTypeResponse`

        """
        try:
            params = request._serialize()
            body = self.call("InquiryPriceModifyAddressInternetChargeType", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.InquiryPriceModifyAddressInternetChargeTypeResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def InquiryPriceModifyAddressesBandwidth(self, request):
        """修改带宽询价

        :param request: 调用InquiryPriceModifyAddressesBandwidth所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.InquiryPriceModifyAddressesBandwidthRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.InquiryPriceModifyAddressesBandwidthResponse`

        """
        try:
            params = request._serialize()
            body = self.call("InquiryPriceModifyAddressesBandwidth", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.InquiryPriceModifyAddressesBandwidthResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def InquiryPriceModifyBandwidthPackageBandwidth(self, request):
        """无

        :param request: 调用InquiryPriceModifyBandwidthPackageBandwidth所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.InquiryPriceModifyBandwidthPackageBandwidthRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.InquiryPriceModifyBandwidthPackageBandwidthResponse`

        """
        try:
            params = request._serialize()
            body = self.call("InquiryPriceModifyBandwidthPackageBandwidth", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.InquiryPriceModifyBandwidthPackageBandwidthResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def InquiryPriceModifyIp6AddressesBandwidth(self, request):
        """该接口用于查询修改IPV6带宽的价格

        :param request: 调用InquiryPriceModifyIp6AddressesBandwidth所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.InquiryPriceModifyIp6AddressesBandwidthRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.InquiryPriceModifyIp6AddressesBandwidthResponse`

        """
        try:
            params = request._serialize()
            body = self.call("InquiryPriceModifyIp6AddressesBandwidth", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.InquiryPriceModifyIp6AddressesBandwidthResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def InquiryPriceNatGateway(self, request):
        """本接口（InquiryPriceNatGateway）用于Nat网关的询价。

        :param request: 调用InquiryPriceNatGateway所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.InquiryPriceNatGatewayRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.InquiryPriceNatGatewayResponse`

        """
        try:
            params = request._serialize()
            body = self.call("InquiryPriceNatGateway", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.InquiryPriceNatGatewayResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def InquiryPricePublicIp6Addresses(self, request):
        """该接口用于查询IPV6地址访问internet的价格

        :param request: 调用InquiryPricePublicIp6Addresses所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.InquiryPricePublicIp6AddressesRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.InquiryPricePublicIp6AddressesResponse`

        """
        try:
            params = request._serialize()
            body = self.call("InquiryPricePublicIp6Addresses", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.InquiryPricePublicIp6AddressesResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def InquiryPriceRenewAddresses(self, request):
        """无

        :param request: 调用InquiryPriceRenewAddresses所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.InquiryPriceRenewAddressesRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.InquiryPriceRenewAddressesResponse`

        """
        try:
            params = request._serialize()
            body = self.call("InquiryPriceRenewAddresses", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.InquiryPriceRenewAddressesResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def InquiryPriceRenewBandwidthPackage(self, request):
        """无

        :param request: 调用InquiryPriceRenewBandwidthPackage所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.InquiryPriceRenewBandwidthPackageRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.InquiryPriceRenewBandwidthPackageResponse`

        """
        try:
            params = request._serialize()
            body = self.call("InquiryPriceRenewBandwidthPackage", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.InquiryPriceRenewBandwidthPackageResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def InquiryPriceRenewCcnBandwidth(self, request):
        """本接口（InquiryPriceRenewCcnBandwidth）用于续费云联网实例地域间带宽时的询价

        :param request: 调用InquiryPriceRenewCcnBandwidth所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.InquiryPriceRenewCcnBandwidthRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.InquiryPriceRenewCcnBandwidthResponse`

        """
        try:
            params = request._serialize()
            body = self.call("InquiryPriceRenewCcnBandwidth", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.InquiryPriceRenewCcnBandwidthResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def InquiryPriceRenewVpnGateway(self, request):
        """本接口（InquiryPriceRenewVpnGateway）用于续费VPN网关询价。目前仅支持IPSEC类型网关的询价。

        :param request: 调用InquiryPriceRenewVpnGateway所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.InquiryPriceRenewVpnGatewayRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.InquiryPriceRenewVpnGatewayResponse`

        """
        try:
            params = request._serialize()
            body = self.call("InquiryPriceRenewVpnGateway", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.InquiryPriceRenewVpnGatewayResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def InquiryPriceResetVpnGatewayInternetMaxBandwidth(self, request):
        """本接口（InquiryPriceResetVpnGatewayInternetMaxBandwidth）调整VPN网关带宽上限询价。

        :param request: 调用InquiryPriceResetVpnGatewayInternetMaxBandwidth所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.InquiryPriceResetVpnGatewayInternetMaxBandwidthRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.InquiryPriceResetVpnGatewayInternetMaxBandwidthResponse`

        """
        try:
            params = request._serialize()
            body = self.call("InquiryPriceResetVpnGatewayInternetMaxBandwidth", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.InquiryPriceResetVpnGatewayInternetMaxBandwidthResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def InquiryPriceUpdateCcnBandwidth(self, request):
        """本接口（InquiryPriceUpdateCcnBandwidth）用于修改预付费云联网实例地域间带宽时的询价

        :param request: 调用InquiryPriceUpdateCcnBandwidth所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.InquiryPriceUpdateCcnBandwidthRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.InquiryPriceUpdateCcnBandwidthResponse`

        """
        try:
            params = request._serialize()
            body = self.call("InquiryPriceUpdateCcnBandwidth", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.InquiryPriceUpdateCcnBandwidthResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def InquiryPriceVacancyAddresses(self, request):
        """闲置EIP询价

        :param request: 调用InquiryPriceVacancyAddresses所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.InquiryPriceVacancyAddressesRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.InquiryPriceVacancyAddressesResponse`

        """
        try:
            params = request._serialize()
            body = self.call("InquiryPriceVacancyAddresses", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.InquiryPriceVacancyAddressesResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def MigrateAddresses(self, request):
        """本接口 (MigrateAddresses) 用于跨账号迁移一个或多个弹性公网IP（简称 EIP），且仅限于未绑定任何资源的后付费EIP

        :param request: 调用MigrateAddresses所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.MigrateAddressesRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.MigrateAddressesResponse`

        """
        try:
            params = request._serialize()
            body = self.call("MigrateAddresses", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.MigrateAddressesResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def MigrateNetworkInterface(self, request):
        """本接口（MigrateNetworkInterface）用于弹性网卡迁移。

        :param request: 调用MigrateNetworkInterface所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.MigrateNetworkInterfaceRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.MigrateNetworkInterfaceResponse`

        """
        try:
            params = request._serialize()
            body = self.call("MigrateNetworkInterface", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.MigrateNetworkInterfaceResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def MigratePrivateIpAddress(self, request):
        """本接口（MigratePrivateIpAddress）用于弹性网卡内网IP迁移。

        * 该接口用于将一个内网IP从一个弹性网卡上迁移到另外一个弹性网卡，主IP地址不支持迁移。
        * 迁移前后的弹性网卡必须在同一个子网内。

        :param request: 调用MigratePrivateIpAddress所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.MigratePrivateIpAddressRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.MigratePrivateIpAddressResponse`

        """
        try:
            params = request._serialize()
            body = self.call("MigratePrivateIpAddress", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.MigratePrivateIpAddressResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def ModifyAddressAttribute(self, request):
        """本接口 (ModifyAddressAttribute) 用于修改弹性公网IP（简称 EIP）的名称。

        :param request: 调用ModifyAddressAttribute所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.ModifyAddressAttributeRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.ModifyAddressAttributeResponse`

        """
        try:
            params = request._serialize()
            body = self.call("ModifyAddressAttribute", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.ModifyAddressAttributeResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def ModifyAddressInternetChargeType(self, request):
        """该接口用于调整具有带宽属性弹性公网IP的网络计费模式
        * 支持BANDWIDTH_PREPAID_BY_MONTH和TRAFFIC_POSTPAID_BY_HOUR两种网络计费模式之间的切换。
        * 每个弹性公网IP支持调整两次，次数超出则无法调整。

        :param request: 调用ModifyAddressInternetChargeType所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.ModifyAddressInternetChargeTypeRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.ModifyAddressInternetChargeTypeResponse`

        """
        try:
            params = request._serialize()
            body = self.call("ModifyAddressInternetChargeType", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.ModifyAddressInternetChargeTypeResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def ModifyAddressTemplateAttribute(self, request):
        """本接口（ModifyAddressTemplateAttribute）用于修改IP地址模板

        :param request: 调用ModifyAddressTemplateAttribute所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.ModifyAddressTemplateAttributeRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.ModifyAddressTemplateAttributeResponse`

        """
        try:
            params = request._serialize()
            body = self.call("ModifyAddressTemplateAttribute", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.ModifyAddressTemplateAttributeResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def ModifyAddressTemplateGroupAttribute(self, request):
        """本接口（ModifyAddressTemplateGroupAttribute）用于修改IP地址模板集合

        :param request: 调用ModifyAddressTemplateGroupAttribute所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.ModifyAddressTemplateGroupAttributeRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.ModifyAddressTemplateGroupAttributeResponse`

        """
        try:
            params = request._serialize()
            body = self.call("ModifyAddressTemplateGroupAttribute", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.ModifyAddressTemplateGroupAttributeResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def ModifyAddressesAttribute(self, request):
        """本接口 (ModifyAddressAttribute) 用于批量修改弹性公网IP（简称 EIP）的属性。

        :param request: 调用ModifyAddressesAttribute所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.ModifyAddressesAttributeRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.ModifyAddressesAttributeResponse`

        """
        try:
            params = request._serialize()
            body = self.call("ModifyAddressesAttribute", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.ModifyAddressesAttributeResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def ModifyAddressesBandwidth(self, request):
        """本接口（ModifyAddressesBandwidth）用于调整弹性公网IP(简称EIP)带宽，包括后付费EIP, 预付费EIP和带宽包EIP

        :param request: 调用ModifyAddressesBandwidth所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.ModifyAddressesBandwidthRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.ModifyAddressesBandwidthResponse`

        """
        try:
            params = request._serialize()
            body = self.call("ModifyAddressesBandwidth", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.ModifyAddressesBandwidthResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def ModifyAssistantCidr(self, request):
        """本接口(ModifyAssistantCidr)用于批量修改辅助CIDR，支持新增和删除。（接口灰度中，如需使用请提工单。）

        :param request: 调用ModifyAssistantCidr所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.ModifyAssistantCidrRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.ModifyAssistantCidrResponse`

        """
        try:
            params = request._serialize()
            body = self.call("ModifyAssistantCidr", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.ModifyAssistantCidrResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def ModifyBandwidthPackageAttribute(self, request):
        """接口用于修改带宽包属性，包括带宽包名字等

        :param request: 调用ModifyBandwidthPackageAttribute所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.ModifyBandwidthPackageAttributeRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.ModifyBandwidthPackageAttributeResponse`

        """
        try:
            params = request._serialize()
            body = self.call("ModifyBandwidthPackageAttribute", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.ModifyBandwidthPackageAttributeResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def ModifyBandwidthPackageBandwidth(self, request):
        """接口用于调整共享带宽包(BWP)带宽

        :param request: 调用ModifyBandwidthPackageBandwidth所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.ModifyBandwidthPackageBandwidthRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.ModifyBandwidthPackageBandwidthResponse`

        """
        try:
            params = request._serialize()
            body = self.call("ModifyBandwidthPackageBandwidth", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.ModifyBandwidthPackageBandwidthResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def ModifyCcnAttribute(self, request):
        """本接口（ModifyCcnAttribute）用于修改云联网（CCN）的相关属性。

        :param request: 调用ModifyCcnAttribute所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.ModifyCcnAttributeRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.ModifyCcnAttributeResponse`

        """
        try:
            params = request._serialize()
            body = self.call("ModifyCcnAttribute", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.ModifyCcnAttributeResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def ModifyCcnRegionBandwidthLimitsType(self, request):
        """本接口（ModifyCcnRegionBandwidthLimitsType）用于修改后付费云联网实例修改带宽限速策略。

        :param request: 调用ModifyCcnRegionBandwidthLimitsType所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.ModifyCcnRegionBandwidthLimitsTypeRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.ModifyCcnRegionBandwidthLimitsTypeResponse`

        """
        try:
            params = request._serialize()
            body = self.call("ModifyCcnRegionBandwidthLimitsType", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.ModifyCcnRegionBandwidthLimitsTypeResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def ModifyCustomerGatewayAttribute(self, request):
        """本接口（ModifyCustomerGatewayAttribute）用于修改对端网关信息。

        :param request: 调用ModifyCustomerGatewayAttribute所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.ModifyCustomerGatewayAttributeRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.ModifyCustomerGatewayAttributeResponse`

        """
        try:
            params = request._serialize()
            body = self.call("ModifyCustomerGatewayAttribute", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.ModifyCustomerGatewayAttributeResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def ModifyDirectConnectGatewayAttribute(self, request):
        """本接口（ModifyDirectConnectGatewayAttribute）用于修改专线网关属性

        :param request: 调用ModifyDirectConnectGatewayAttribute所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.ModifyDirectConnectGatewayAttributeRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.ModifyDirectConnectGatewayAttributeResponse`

        """
        try:
            params = request._serialize()
            body = self.call("ModifyDirectConnectGatewayAttribute", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.ModifyDirectConnectGatewayAttributeResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def ModifyFlowLogAttribute(self, request):
        """本接口（ModifyFlowLogAttribute）用于修改流日志属性

        :param request: 调用ModifyFlowLogAttribute所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.ModifyFlowLogAttributeRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.ModifyFlowLogAttributeResponse`

        """
        try:
            params = request._serialize()
            body = self.call("ModifyFlowLogAttribute", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.ModifyFlowLogAttributeResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def ModifyGatewayFlowQos(self, request):
        """本接口（ModifyGatewayFlowQos）用于调整网关流控带宽。

        :param request: 调用ModifyGatewayFlowQos所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.ModifyGatewayFlowQosRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.ModifyGatewayFlowQosResponse`

        """
        try:
            params = request._serialize()
            body = self.call("ModifyGatewayFlowQos", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.ModifyGatewayFlowQosResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def ModifyHaVipAttribute(self, request):
        """本接口（ModifyHaVipAttribute）用于修改高可用虚拟IP（HAVIP）属性

        :param request: 调用ModifyHaVipAttribute所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.ModifyHaVipAttributeRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.ModifyHaVipAttributeResponse`

        """
        try:
            params = request._serialize()
            body = self.call("ModifyHaVipAttribute", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.ModifyHaVipAttributeResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def ModifyIp6AddressesBandwidth(self, request):
        """该接口用于修改IPV6地址访问internet的带宽

        :param request: 调用ModifyIp6AddressesBandwidth所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.ModifyIp6AddressesBandwidthRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.ModifyIp6AddressesBandwidthResponse`

        """
        try:
            params = request._serialize()
            body = self.call("ModifyIp6AddressesBandwidth", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.ModifyIp6AddressesBandwidthResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def ModifyIp6Rule(self, request):
        """该接口用于修改IPV6转换规则，当前仅支持修改转换规则名称，IPV4地址和IPV4端口号

        :param request: 调用ModifyIp6Rule所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.ModifyIp6RuleRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.ModifyIp6RuleResponse`

        """
        try:
            params = request._serialize()
            body = self.call("ModifyIp6Rule", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.ModifyIp6RuleResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def ModifyIp6Translator(self, request):
        """该接口用于修改IP6转换实例属性，当前仅支持修改实例名称。

        :param request: 调用ModifyIp6Translator所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.ModifyIp6TranslatorRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.ModifyIp6TranslatorResponse`

        """
        try:
            params = request._serialize()
            body = self.call("ModifyIp6Translator", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.ModifyIp6TranslatorResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def ModifyIpv6AddressesAttribute(self, request):
        """本接口（ModifyIpv6AddressesAttribute）用于修改弹性网卡内网IPv6地址属性。

        :param request: 调用ModifyIpv6AddressesAttribute所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.ModifyIpv6AddressesAttributeRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.ModifyIpv6AddressesAttributeResponse`

        """
        try:
            params = request._serialize()
            body = self.call("ModifyIpv6AddressesAttribute", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.ModifyIpv6AddressesAttributeResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def ModifyLocalDestinationIpPortTranslationNatRule(self, request):
        """修改专线网关本端目的IP端口转换

        :param request: 调用ModifyLocalDestinationIpPortTranslationNatRule所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.ModifyLocalDestinationIpPortTranslationNatRuleRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.ModifyLocalDestinationIpPortTranslationNatRuleResponse`

        """
        try:
            params = request._serialize()
            body = self.call("ModifyLocalDestinationIpPortTranslationNatRule", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.ModifyLocalDestinationIpPortTranslationNatRuleResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def ModifyLocalIpTranslationAclRule(self, request):
        """修改专线网关本端IP转换ACL规则

        :param request: 调用ModifyLocalIpTranslationAclRule所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.ModifyLocalIpTranslationAclRuleRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.ModifyLocalIpTranslationAclRuleResponse`

        """
        try:
            params = request._serialize()
            body = self.call("ModifyLocalIpTranslationAclRule", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.ModifyLocalIpTranslationAclRuleResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def ModifyLocalIpTranslationNatRule(self, request):
        """修改专线网关本端IP转换

        :param request: 调用ModifyLocalIpTranslationNatRule所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.ModifyLocalIpTranslationNatRuleRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.ModifyLocalIpTranslationNatRuleResponse`

        """
        try:
            params = request._serialize()
            body = self.call("ModifyLocalIpTranslationNatRule", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.ModifyLocalIpTranslationNatRuleResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def ModifyLocalSourceIpPortTranslationAclRule(self, request):
        """修改专线网关本端源IP端口转换ACL规则

        :param request: 调用ModifyLocalSourceIpPortTranslationAclRule所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.ModifyLocalSourceIpPortTranslationAclRuleRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.ModifyLocalSourceIpPortTranslationAclRuleResponse`

        """
        try:
            params = request._serialize()
            body = self.call("ModifyLocalSourceIpPortTranslationAclRule", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.ModifyLocalSourceIpPortTranslationAclRuleResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def ModifyLocalSourceIpPortTranslationNatRule(self, request):
        """修改专线网关本端源IP端口转换

        :param request: 调用ModifyLocalSourceIpPortTranslationNatRule所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.ModifyLocalSourceIpPortTranslationNatRuleRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.ModifyLocalSourceIpPortTranslationNatRuleResponse`

        """
        try:
            params = request._serialize()
            body = self.call("ModifyLocalSourceIpPortTranslationNatRule", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.ModifyLocalSourceIpPortTranslationNatRuleResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def ModifyNatGatewayAttribute(self, request):
        """本接口（ModifyNatGatewayAttribute）用于修改NAT网关的属性。

        :param request: 调用ModifyNatGatewayAttribute所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.ModifyNatGatewayAttributeRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.ModifyNatGatewayAttributeResponse`

        """
        try:
            params = request._serialize()
            body = self.call("ModifyNatGatewayAttribute", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.ModifyNatGatewayAttributeResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def ModifyNatGatewayDestinationIpPortTranslationNatRule(self, request):
        """本接口（ModifyNatGatewayDestinationIpPortTranslationNatRule）用于修改NAT网关端口转发规则。

        :param request: 调用ModifyNatGatewayDestinationIpPortTranslationNatRule所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.ModifyNatGatewayDestinationIpPortTranslationNatRuleRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.ModifyNatGatewayDestinationIpPortTranslationNatRuleResponse`

        """
        try:
            params = request._serialize()
            body = self.call("ModifyNatGatewayDestinationIpPortTranslationNatRule", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.ModifyNatGatewayDestinationIpPortTranslationNatRuleResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def ModifyNetDetect(self, request):
        """本接口(ModifyNetDetect)用于修改网络探测参数。

        :param request: 调用ModifyNetDetect所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.ModifyNetDetectRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.ModifyNetDetectResponse`

        """
        try:
            params = request._serialize()
            body = self.call("ModifyNetDetect", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.ModifyNetDetectResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def ModifyNetworkAclAttribute(self, request):
        """本接口（ModifyNetworkAclAttribute）用于修改网络ACL属性。

        :param request: 调用ModifyNetworkAclAttribute所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.ModifyNetworkAclAttributeRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.ModifyNetworkAclAttributeResponse`

        """
        try:
            params = request._serialize()
            body = self.call("ModifyNetworkAclAttribute", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.ModifyNetworkAclAttributeResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def ModifyNetworkAclEntries(self, request):
        """本接口（ModifyNetworkAclEntries）用于修改（包括添加和删除）网络ACL的入站规则和出站规则。

        :param request: 调用ModifyNetworkAclEntries所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.ModifyNetworkAclEntriesRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.ModifyNetworkAclEntriesResponse`

        """
        try:
            params = request._serialize()
            body = self.call("ModifyNetworkAclEntries", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.ModifyNetworkAclEntriesResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def ModifyNetworkInterfaceAttribute(self, request):
        """本接口（ModifyNetworkInterfaceAttribute）用于修改弹性网卡属性。

        :param request: 调用ModifyNetworkInterfaceAttribute所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.ModifyNetworkInterfaceAttributeRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.ModifyNetworkInterfaceAttributeResponse`

        """
        try:
            params = request._serialize()
            body = self.call("ModifyNetworkInterfaceAttribute", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.ModifyNetworkInterfaceAttributeResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def ModifyNetworkInterfaceExtendIp(self, request):
        """修改弹性网卡扩展ip

        :param request: 调用ModifyNetworkInterfaceExtendIp所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.ModifyNetworkInterfaceExtendIpRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.ModifyNetworkInterfaceExtendIpResponse`

        """
        try:
            params = request._serialize()
            body = self.call("ModifyNetworkInterfaceExtendIp", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.ModifyNetworkInterfaceExtendIpResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def ModifyPeerIpTranslationNatRule(self, request):
        """修改专线网关对端IP转换

        :param request: 调用ModifyPeerIpTranslationNatRule所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.ModifyPeerIpTranslationNatRuleRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.ModifyPeerIpTranslationNatRuleResponse`

        """
        try:
            params = request._serialize()
            body = self.call("ModifyPeerIpTranslationNatRule", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.ModifyPeerIpTranslationNatRuleResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def ModifyPrivateIpAddressesAttribute(self, request):
        """本接口（ModifyPrivateIpAddressesAttribute）用于修改弹性网卡内网IP属性。

        :param request: 调用ModifyPrivateIpAddressesAttribute所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.ModifyPrivateIpAddressesAttributeRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.ModifyPrivateIpAddressesAttributeResponse`

        """
        try:
            params = request._serialize()
            body = self.call("ModifyPrivateIpAddressesAttribute", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.ModifyPrivateIpAddressesAttributeResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def ModifyRouteTableAttribute(self, request):
        """本接口（ModifyRouteTableAttribute）用于修改路由表（RouteTable）属性。

        :param request: 调用ModifyRouteTableAttribute所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.ModifyRouteTableAttributeRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.ModifyRouteTableAttributeResponse`

        """
        try:
            params = request._serialize()
            body = self.call("ModifyRouteTableAttribute", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.ModifyRouteTableAttributeResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def ModifySecurityGroupAttribute(self, request):
        """本接口（ModifySecurityGroupAttribute）用于修改安全组（SecurityGroupPolicy）属性。

        :param request: 调用ModifySecurityGroupAttribute所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.ModifySecurityGroupAttributeRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.ModifySecurityGroupAttributeResponse`

        """
        try:
            params = request._serialize()
            body = self.call("ModifySecurityGroupAttribute", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.ModifySecurityGroupAttributeResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def ModifySecurityGroupPolicies(self, request):
        """本接口（ModifySecurityGroupPolicies）用于重置安全组出站和入站规则（SecurityGroupPolicy）。

        * 接口是先删除当前所有的出入站规则，然后再添加 Egress 和 Ingress 规则，不支持自定义索引 PolicyIndex 。
        * 如果指定 SecurityGroupPolicySet.Version 为0, 表示清空所有规则，并忽略Egress和Ingress。
        * Protocol字段支持输入TCP, UDP, ICMP, ICMPV6, GRE, ALL。
        * CidrBlock字段允许输入符合cidr格式标准的任意字符串。(展开)在基础网络中，如果CidrBlock包含您的账户内的云服务器之外的设备在Tce的内网IP，并不代表此规则允许您访问这些设备，租户之间网络隔离规则优先于安全组中的内网规则。
        * Ipv6CidrBlock字段允许输入符合IPv6 cidr格式标准的任意字符串。(展开)在基础网络中，如果Ipv6CidrBlock包含您的账户内的云服务器之外的设备在Tce的内网IPv6，并不代表此规则允许您访问这些设备，租户之间网络隔离规则优先于安全组中的内网规则。
        * SecurityGroupId字段允许输入与待修改的安全组位于相同项目中的安全组ID，包括这个安全组ID本身，代表安全组下所有云服务器的内网IP。使用这个字段时，这条规则用来匹配网络报文的过程中会随着被使用的这个ID所关联的云服务器变化而变化，不需要重新修改。
        * Port字段允许输入一个单独端口号，或者用减号分隔的两个端口号代表端口范围，例如80或8000-8010。只有当Protocol字段是TCP或UDP时，Port字段才被接受。
        * Action字段只允许输入ACCEPT或DROP。
        * CidrBlock, Ipv6CidrBlock, SecurityGroupId, AddressTemplate四者是排他关系，不允许同时输入，Protocol + Port和ServiceTemplate二者是排他关系，不允许同时输入。

        :param request: 调用ModifySecurityGroupPolicies所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.ModifySecurityGroupPoliciesRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.ModifySecurityGroupPoliciesResponse`

        """
        try:
            params = request._serialize()
            body = self.call("ModifySecurityGroupPolicies", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.ModifySecurityGroupPoliciesResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def ModifyServiceTemplateAttribute(self, request):
        """本接口（ModifyServiceTemplateAttribute）用于修改协议端口模板

        :param request: 调用ModifyServiceTemplateAttribute所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.ModifyServiceTemplateAttributeRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.ModifyServiceTemplateAttributeResponse`

        """
        try:
            params = request._serialize()
            body = self.call("ModifyServiceTemplateAttribute", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.ModifyServiceTemplateAttributeResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def ModifyServiceTemplateGroupAttribute(self, request):
        """本接口（ModifyServiceTemplateGroupAttribute）用于修改协议端口模板集合。

        :param request: 调用ModifyServiceTemplateGroupAttribute所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.ModifyServiceTemplateGroupAttributeRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.ModifyServiceTemplateGroupAttributeResponse`

        """
        try:
            params = request._serialize()
            body = self.call("ModifyServiceTemplateGroupAttribute", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.ModifyServiceTemplateGroupAttributeResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def ModifySubnetAttribute(self, request):
        """本接口（ModifySubnetAttribute）用于修改子网属性。

        :param request: 调用ModifySubnetAttribute所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.ModifySubnetAttributeRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.ModifySubnetAttributeResponse`

        """
        try:
            params = request._serialize()
            body = self.call("ModifySubnetAttribute", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.ModifySubnetAttributeResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def ModifyTrafficMirrorAttribute(self, request):
        """本接口（ModifyTrafficMirrorAttribute）用于修改流量镜像实例属性。
        注意：只支持修改名字和描述信息

        :param request: 调用ModifyTrafficMirrorAttribute所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.ModifyTrafficMirrorAttributeRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.ModifyTrafficMirrorAttributeResponse`

        """
        try:
            params = request._serialize()
            body = self.call("ModifyTrafficMirrorAttribute", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.ModifyTrafficMirrorAttributeResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def ModifyTrafficPackageAttribute(self, request):
        """接口用于修改共享流量包属性，包括共享流量包名称等

        :param request: 调用ModifyTrafficPackageAttribute所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.ModifyTrafficPackageAttributeRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.ModifyTrafficPackageAttributeResponse`

        """
        try:
            params = request._serialize()
            body = self.call("ModifyTrafficPackageAttribute", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.ModifyTrafficPackageAttributeResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def ModifyVpcAttribute(self, request):
        """本接口（ModifyVpcAttribute）用于修改私有网络（VPC）的相关属性。

        :param request: 调用ModifyVpcAttribute所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.ModifyVpcAttributeRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.ModifyVpcAttributeResponse`

        """
        try:
            params = request._serialize()
            body = self.call("ModifyVpcAttribute", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.ModifyVpcAttributeResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def ModifyVpcExtendCidr(self, request):
        """修改VPC扩展CIDR属性

        :param request: 调用ModifyVpcExtendCidr所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.ModifyVpcExtendCidrRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.ModifyVpcExtendCidrResponse`

        """
        try:
            params = request._serialize()
            body = self.call("ModifyVpcExtendCidr", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.ModifyVpcExtendCidrResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def ModifyVpnConnectionAttribute(self, request):
        """本接口（ModifyVpnConnectionAttribute）用于修改VPN通道。

        :param request: 调用ModifyVpnConnectionAttribute所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.ModifyVpnConnectionAttributeRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.ModifyVpnConnectionAttributeResponse`

        """
        try:
            params = request._serialize()
            body = self.call("ModifyVpnConnectionAttribute", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.ModifyVpnConnectionAttributeResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def ModifyVpnGatewayAttribute(self, request):
        """本接口（ModifyVpnGatewayAttribute）用于修改VPN网关属性。

        :param request: 调用ModifyVpnGatewayAttribute所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.ModifyVpnGatewayAttributeRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.ModifyVpnGatewayAttributeResponse`

        """
        try:
            params = request._serialize()
            body = self.call("ModifyVpnGatewayAttribute", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.ModifyVpnGatewayAttributeResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def ModifyVpnGatewayCcnRoutes(self, request):
        """本接口（ModifyVpnGatewayCcnRoutes）用于修改VPN网关云联网路由

        :param request: 调用ModifyVpnGatewayCcnRoutes所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.ModifyVpnGatewayCcnRoutesRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.ModifyVpnGatewayCcnRoutesResponse`

        """
        try:
            params = request._serialize()
            body = self.call("ModifyVpnGatewayCcnRoutes", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.ModifyVpnGatewayCcnRoutesResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def PrivateIp6Addresses(self, request):
        """该接口用于取消IPV6地址访问internet的能力

        :param request: 调用PrivateIp6Addresses所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.PrivateIp6AddressesRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.PrivateIp6AddressesResponse`

        """
        try:
            params = request._serialize()
            body = self.call("PrivateIp6Addresses", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.PrivateIp6AddressesResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def PublicIp6Addresses(self, request):
        """该接口用于给指定的ipv6地址开通internet访问能力。

        :param request: 调用PublicIp6Addresses所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.PublicIp6AddressesRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.PublicIp6AddressesResponse`

        """
        try:
            params = request._serialize()
            body = self.call("PublicIp6Addresses", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.PublicIp6AddressesResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def QueryTask(self, request):
        """查询异步任务执行结果

        :param request: 调用QueryTask所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.QueryTaskRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.QueryTaskResponse`

        """
        try:
            params = request._serialize()
            body = self.call("QueryTask", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.QueryTaskResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def RejectAttachCcnInstances(self, request):
        """本接口（RejectAttachCcnInstances）用于跨账号关联实例时，云联网所有者拒绝关联操作。

        :param request: 调用RejectAttachCcnInstances所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.RejectAttachCcnInstancesRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.RejectAttachCcnInstancesResponse`

        """
        try:
            params = request._serialize()
            body = self.call("RejectAttachCcnInstances", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.RejectAttachCcnInstancesResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def ReleaseAddresses(self, request):
        """本接口 (ReleaseAddresses) 用于释放一个或多个弹性公网IP（简称 EIP）。
        * 该操作不可逆，释放后 EIP 关联的 IP 地址将不再属于您的名下。
        * 只有状态为 UNBIND 的 EIP 才能进行释放操作。

        :param request: 调用ReleaseAddresses所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.ReleaseAddressesRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.ReleaseAddressesResponse`

        """
        try:
            params = request._serialize()
            body = self.call("ReleaseAddresses", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.ReleaseAddressesResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def ReleaseIp6AddressesBandwidth(self, request):
        """该接口用于给弹性公网IPv6地址释放带宽。

        :param request: 调用ReleaseIp6AddressesBandwidth所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.ReleaseIp6AddressesBandwidthRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.ReleaseIp6AddressesBandwidthResponse`

        """
        try:
            params = request._serialize()
            body = self.call("ReleaseIp6AddressesBandwidth", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.ReleaseIp6AddressesBandwidthResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def RemoveBandwidthPackageResources(self, request):
        """接口用于删除带宽包资源，包括弹性公网IP和负载均衡等

        :param request: 调用RemoveBandwidthPackageResources所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.RemoveBandwidthPackageResourcesRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.RemoveBandwidthPackageResourcesResponse`

        """
        try:
            params = request._serialize()
            body = self.call("RemoveBandwidthPackageResources", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.RemoveBandwidthPackageResourcesResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def RemoveIp6Rules(self, request):
        """1. 该接口用于删除IPV6转换规则
        2. 支持批量删除同一个转换实例下的多个转换规则

        :param request: 调用RemoveIp6Rules所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.RemoveIp6RulesRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.RemoveIp6RulesResponse`

        """
        try:
            params = request._serialize()
            body = self.call("RemoveIp6Rules", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.RemoveIp6RulesResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def RenewAddresses(self, request):
        """该接口用于续费包月带宽计费模式的弹性公网IP

        :param request: 调用RenewAddresses所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.RenewAddressesRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.RenewAddressesResponse`

        """
        try:
            params = request._serialize()
            body = self.call("RenewAddresses", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.RenewAddressesResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def RenewCcnBandwidth(self, request):
        """本接口（CreateCcnBandwidth）用于续费预付费模式下云联网实例的地域间带宽

        :param request: 调用RenewCcnBandwidth所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.RenewCcnBandwidthRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.RenewCcnBandwidthResponse`

        """
        try:
            params = request._serialize()
            body = self.call("RenewCcnBandwidth", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.RenewCcnBandwidthResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def RenewVpnGateway(self, request):
        """本接口（RenewVpnGateway）用于预付费（包年包月）VPN网关续费。目前只支持IPSEC网关。

        :param request: 调用RenewVpnGateway所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.RenewVpnGatewayRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.RenewVpnGatewayResponse`

        """
        try:
            params = request._serialize()
            body = self.call("RenewVpnGateway", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.RenewVpnGatewayResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def ReplaceDirectConnectGatewayCcnRoutes(self, request):
        """本接口（ReplaceDirectConnectGatewayCcnRoutes）根据路由ID（RouteId）修改指定的路由（Route），支持批量修改。

        :param request: 调用ReplaceDirectConnectGatewayCcnRoutes所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.ReplaceDirectConnectGatewayCcnRoutesRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.ReplaceDirectConnectGatewayCcnRoutesResponse`

        """
        try:
            params = request._serialize()
            body = self.call("ReplaceDirectConnectGatewayCcnRoutes", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.ReplaceDirectConnectGatewayCcnRoutesResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def ReplaceRouteTableAssociation(self, request):
        """本接口（ReplaceRouteTableAssociation)用于修改子网（Subnet）关联的路由表（RouteTable）。
        * 一个子网只能关联一个路由表。

        :param request: 调用ReplaceRouteTableAssociation所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.ReplaceRouteTableAssociationRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.ReplaceRouteTableAssociationResponse`

        """
        try:
            params = request._serialize()
            body = self.call("ReplaceRouteTableAssociation", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.ReplaceRouteTableAssociationResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def ReplaceRoutes(self, request):
        """本接口（ReplaceRoutes）根据路由策略ID（RouteId）修改指定的路由策略（Route），支持批量修改。

        :param request: 调用ReplaceRoutes所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.ReplaceRoutesRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.ReplaceRoutesResponse`

        """
        try:
            params = request._serialize()
            body = self.call("ReplaceRoutes", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.ReplaceRoutesResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def ReplaceSecurityGroupPolicy(self, request):
        """本接口（ReplaceSecurityGroupPolicy）用于替换单条安全组规则（SecurityGroupPolicy）。
        单个请求中只能替换单个方向的一条规则, 必须要指定索引（PolicyIndex）。

        :param request: 调用ReplaceSecurityGroupPolicy所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.ReplaceSecurityGroupPolicyRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.ReplaceSecurityGroupPolicyResponse`

        """
        try:
            params = request._serialize()
            body = self.call("ReplaceSecurityGroupPolicy", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.ReplaceSecurityGroupPolicyResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def ResetAttachCcnInstances(self, request):
        """本接口（ResetAttachCcnInstances）用于跨账号关联实例申请过期时，重新申请关联操作。

        :param request: 调用ResetAttachCcnInstances所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.ResetAttachCcnInstancesRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.ResetAttachCcnInstancesResponse`

        """
        try:
            params = request._serialize()
            body = self.call("ResetAttachCcnInstances", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.ResetAttachCcnInstancesResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def ResetNatGatewayConnection(self, request):
        """本接口（ResetNatGatewayConnection）用来NAT网关并发连接上限。

        :param request: 调用ResetNatGatewayConnection所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.ResetNatGatewayConnectionRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.ResetNatGatewayConnectionResponse`

        """
        try:
            params = request._serialize()
            body = self.call("ResetNatGatewayConnection", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.ResetNatGatewayConnectionResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def ResetRoutes(self, request):
        """本接口（ResetRoutes）用于对某个路由表名称和所有路由策略（Route）进行重新设置。<br />
        注意: 调用本接口是先删除当前路由表中所有路由策略, 再保存新提交的路由策略内容, 会引起网络中断。

        :param request: 调用ResetRoutes所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.ResetRoutesRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.ResetRoutesResponse`

        """
        try:
            params = request._serialize()
            body = self.call("ResetRoutes", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.ResetRoutesResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def ResetTrafficMirrorFilter(self, request):
        """本接口（ResetTrafficMirrorFilter）用于更新流量镜像实例过滤规则。
        注意：每一个流量镜像实例，不能同时支持按nat网关和五元组两种规则过滤

        :param request: 调用ResetTrafficMirrorFilter所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.ResetTrafficMirrorFilterRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.ResetTrafficMirrorFilterResponse`

        """
        try:
            params = request._serialize()
            body = self.call("ResetTrafficMirrorFilter", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.ResetTrafficMirrorFilterResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def ResetTrafficMirrorSrcs(self, request):
        """本接口（ResetTrafficMirrorSrcs）用于重置流量镜像实例采集对象。

        :param request: 调用ResetTrafficMirrorSrcs所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.ResetTrafficMirrorSrcsRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.ResetTrafficMirrorSrcsResponse`

        """
        try:
            params = request._serialize()
            body = self.call("ResetTrafficMirrorSrcs", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.ResetTrafficMirrorSrcsResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def ResetTrafficMirrorTarget(self, request):
        """本接口（ResetTrafficMirrorTarget）用于更新流量镜像实例的接收目的信息。

        :param request: 调用ResetTrafficMirrorTarget所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.ResetTrafficMirrorTargetRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.ResetTrafficMirrorTargetResponse`

        """
        try:
            params = request._serialize()
            body = self.call("ResetTrafficMirrorTarget", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.ResetTrafficMirrorTargetResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def ResetVpnConnection(self, request):
        """本接口(ResetVpnConnection)用于重置VPN通道。

        :param request: 调用ResetVpnConnection所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.ResetVpnConnectionRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.ResetVpnConnectionResponse`

        """
        try:
            params = request._serialize()
            body = self.call("ResetVpnConnection", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.ResetVpnConnectionResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def ResetVpnGatewayInternetMaxBandwidth(self, request):
        """本接口（ResetVpnGatewayInternetMaxBandwidth）调整VPN网关带宽上限。目前支持升级配置，如果是包年包月VPN网关需要在有效期内。

        :param request: 调用ResetVpnGatewayInternetMaxBandwidth所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.ResetVpnGatewayInternetMaxBandwidthRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.ResetVpnGatewayInternetMaxBandwidthResponse`

        """
        try:
            params = request._serialize()
            body = self.call("ResetVpnGatewayInternetMaxBandwidth", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.ResetVpnGatewayInternetMaxBandwidthResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def ReturnNormalAddresses(self, request):
        """无

        :param request: 调用ReturnNormalAddresses所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.ReturnNormalAddressesRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.ReturnNormalAddressesResponse`

        """
        try:
            params = request._serialize()
            body = self.call("ReturnNormalAddresses", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.ReturnNormalAddressesResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def SetCcnBandwidthRenewFlag(self, request):
        """本接口（SetCcnBandwidthRenewFlag）用于设置预付费云联网实例地域间限速的自动续费标记

        :param request: 调用SetCcnBandwidthRenewFlag所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.SetCcnBandwidthRenewFlagRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.SetCcnBandwidthRenewFlagResponse`

        """
        try:
            params = request._serialize()
            body = self.call("SetCcnBandwidthRenewFlag", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.SetCcnBandwidthRenewFlagResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def SetCcnRegionBandwidthLimits(self, request):
        """本接口（SetCcnRegionBandwidthLimits）用于设置云联网（CCN）各地域出带宽上限，该接口只能设置已关联网络实例包含的地域的出带宽上限

        :param request: 调用SetCcnRegionBandwidthLimits所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.SetCcnRegionBandwidthLimitsRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.SetCcnRegionBandwidthLimitsResponse`

        """
        try:
            params = request._serialize()
            body = self.call("SetCcnRegionBandwidthLimits", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.SetCcnRegionBandwidthLimitsResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def SetVpnGatewaysRenewFlag(self, request):
        """设置VPNGW续费标记

        :param request: 调用SetVpnGatewaysRenewFlag所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.SetVpnGatewaysRenewFlagRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.SetVpnGatewaysRenewFlagResponse`

        """
        try:
            params = request._serialize()
            body = self.call("SetVpnGatewaysRenewFlag", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.SetVpnGatewaysRenewFlagResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def StartTrafficMirror(self, request):
        """本接口（StartTrafficMirror）用于开启流量镜像实例。

        :param request: 调用StartTrafficMirror所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.StartTrafficMirrorRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.StartTrafficMirrorResponse`

        """
        try:
            params = request._serialize()
            body = self.call("StartTrafficMirror", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.StartTrafficMirrorResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def StopTrafficMirror(self, request):
        """本接口（StopTrafficMirror）用于关闭流量镜像实例。

        :param request: 调用StopTrafficMirror所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.StopTrafficMirrorRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.StopTrafficMirrorResponse`

        """
        try:
            params = request._serialize()
            body = self.call("StopTrafficMirror", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.StopTrafficMirrorResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def TransformAddress(self, request):
        """本接口 (TransformAddress) 用于将实例的普通公网 IP 转换为弹性公网IP（简称 EIP）。
        * 平台对用户每地域每日解绑 EIP 重新分配普通公网 IP 次数有所限制（可参见 EIP 产品简介）。上述配额可通过 DescribeAddressQuota 接口获取。

        :param request: 调用TransformAddress所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.TransformAddressRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.TransformAddressResponse`

        """
        try:
            params = request._serialize()
            body = self.call("TransformAddress", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.TransformAddressResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def UnassignIpv6Addresses(self, request):
        """本接口（UnassignIpv6Addresses）用于释放弹性网卡`IPv6`地址。<br />
        本接口是异步完成，如需查询异步任务执行结果，请使用本接口返回的`RequestId`轮询`QueryTask`接口。

        :param request: 调用UnassignIpv6Addresses所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.UnassignIpv6AddressesRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.UnassignIpv6AddressesResponse`

        """
        try:
            params = request._serialize()
            body = self.call("UnassignIpv6Addresses", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.UnassignIpv6AddressesResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def UnassignIpv6CidrBlock(self, request):
        """本接口（UnassignIpv6CidrBlock）用于释放IPv6网段。<br />
        网段如果还有IP占用且未回收，则网段无法释放。

        :param request: 调用UnassignIpv6CidrBlock所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.UnassignIpv6CidrBlockRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.UnassignIpv6CidrBlockResponse`

        """
        try:
            params = request._serialize()
            body = self.call("UnassignIpv6CidrBlock", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.UnassignIpv6CidrBlockResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def UnassignIpv6SubnetCidrBlock(self, request):
        """本接口（UnassignIpv6SubnetCidrBlock）用于释放IPv6子网段。<br />
        子网段如果还有IP占用且未回收，则子网段无法释放。

        :param request: 调用UnassignIpv6SubnetCidrBlock所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.UnassignIpv6SubnetCidrBlockRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.UnassignIpv6SubnetCidrBlockResponse`

        """
        try:
            params = request._serialize()
            body = self.call("UnassignIpv6SubnetCidrBlock", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.UnassignIpv6SubnetCidrBlockResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def UnassignPrivateIpAddresses(self, request):
        """本接口（UnassignPrivateIpAddresses）用于弹性网卡退还内网 IP。
        * 退还弹性网卡上的辅助内网IP，接口自动解关联弹性公网 IP。不能退还弹性网卡的主内网IP。

        :param request: 调用UnassignPrivateIpAddresses所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.UnassignPrivateIpAddressesRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.UnassignPrivateIpAddressesResponse`

        """
        try:
            params = request._serialize()
            body = self.call("UnassignPrivateIpAddresses", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.UnassignPrivateIpAddressesResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def UpdateCcnBandwidth(self, request):
        """本接口（UpdateCcnBandwidth）用于变更预付费模式下云联网实例的地域间带宽

        :param request: 调用UpdateCcnBandwidth所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.UpdateCcnBandwidthRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.UpdateCcnBandwidthResponse`

        """
        try:
            params = request._serialize()
            body = self.call("UpdateCcnBandwidth", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.UpdateCcnBandwidthResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def UpdateTrafficMirrorAllFilter(self, request):
        """本接口（UpdateTrafficMirrorAllFilter）用于更新流量镜像实例的过滤规则或者采集对象。

        :param request: 调用UpdateTrafficMirrorAllFilter所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.UpdateTrafficMirrorAllFilterRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.UpdateTrafficMirrorAllFilterResponse`

        """
        try:
            params = request._serialize()
            body = self.call("UpdateTrafficMirrorAllFilter", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.UpdateTrafficMirrorAllFilterResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)

    def UpdateTrafficMirrorDirection(self, request):
        """本接口（UpdateTrafficMirrorDirection）用于更新流量镜像实例的采集方向。

        :param request: 调用UpdateTrafficMirrorDirection所需参数的结构体。
        :type request: :class:`tcecloud.vpc.v20170312.models.UpdateTrafficMirrorDirectionRequest`
        :rtype: :class:`tcecloud.vpc.v20170312.models.UpdateTrafficMirrorDirectionResponse`

        """
        try:
            params = request._serialize()
            body = self.call("UpdateTrafficMirrorDirection", params)
            response = json.loads(body)
            if "Error" not in response["Response"]:
                model = models.UpdateTrafficMirrorDirectionResponse()
                model._deserialize(response["Response"])
                return model
            else:
                code = response["Response"]["Error"]["Code"]
                message = response["Response"]["Error"]["Message"]
                reqid = response["Response"]["RequestId"]
                raise TceCloudSDKException(code, message, reqid)
        except Exception as e:
            if isinstance(e, TceCloudSDKException):
                raise
            else:
                raise TceCloudSDKException(e.message, e.message)
