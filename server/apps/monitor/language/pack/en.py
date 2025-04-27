MONITOR_OBJECT_TYPE = {
    "OS": "OS",
    "Web": "Web",
    "Middleware": "Middleware",
    "Database": "Database",
    "K8S": "K8S",
    "Network Device": "Network Device",
    "Hardware Device": "Hardware Device",
    "Container Management": "Container Management",
    "Other": "Other",
    "VMware": "VMware"
}

MONITOR_OBJECT = {
    "Host": "Host",
    "Website": "Website",
    "Ping": "Ping",
    "RabbitMQ": "RabbitMQ",
    "Nginx": "Nginx",
    "Apache": "Apache",
    "ClickHouse": "ClickHouse",
    "Consul": "Consul",
    "Tomcat": "Tomcat",
    "Zookeeper": "Zookeeper",
    "ActiveMQ": "ActiveMQ",
    "ElasticSearch": "ElasticSearch",
    "MongoDB": "MongoDB",
    "Mysql": "Mysql",
    "Postgres": "Postgres",
    "Redis": "Redis",
    "Switch": "Switch",
    "Router": "Router",
    "Loadbalance": "Loadbalance",
    "Firewall": "Firewall",
    "Detection Device": "Detection Device",
    "Bastion Host": "Bastion Host",
    "Scanning Device": "Scanning Device",
    "Storage": "Storage",
    "Hardware Server": "Hardware Server",
    "Docker": "Docker",
    "Docker Container": "Docker Container",
    "Cluster": "Cluster",
    "Pod": "Pod",
    "Node": "Node",
    "SNMP Trap": "SNMP Trap",
    "vCenter": "vCenter",
    "ESXI": "ESXI",
    "VM": "VM",
    "DataStorage": "DataStorage"
}

MONITOR_OBJECT_PLUGIN = {
    "Host": {
        "name": "Host",
        "desc": "The host monitoring plugin is used to collect and analyze the performance data of the host, including CPU, memory, disk, and network usage."
    },
    "Website": {
        "name": "Website Monitoring",
        "desc": "The website monitoring plugin is used to periodically check the availability and performance of HTTP/HTTPS connections."
    },
    "Ping": {
        "name": "Ping",
        "desc": "Ping is used to check the connectivity and response time of a target host or network device by sending ICMP Echo requests."
    },
    "K8S": {
        "name": "K8S",
        "desc": "The K8S monitoring plugin is used to monitor the status and health of Kubernetes clusters, including performance metrics of nodes, containers, and pods."
    },
    "Switch SNMP General": {
        "name": "Switch General (SNMP)",
        "desc": "The SNMP General plugin is used to monitor and manage the status of switches via SNMP. Administrators can obtain key information about the device, such as interface traffic, error statistics, and status information, to optimize network performance and improve management efficiency."
    },
    "Router SNMP General": {
        "name": "Router General (SNMP)",
        "desc": "The SNMP General plugin is used to monitor and manage the status of routers via SNMP. Administrators can obtain key information about the device, such as interface traffic, error statistics, and status information, to optimize network performance and improve management efficiency."
    },
    "Loadbalance SNMP General": {
        "name": "Load Balancer General (SNMP)",
        "desc": "The SNMP General plugin is used to monitor and manage the status of load balancers via SNMP. Administrators can obtain key information about the device, such as interface traffic, error statistics, and status information, to optimize network performance and improve management efficiency."
    },
    "Firewall SNMP General": {
        "name": "Firewall General (SNMP)",
        "desc": "The SNMP General plugin is used to monitor and manage the status of firewalls via SNMP. Administrators can obtain key information about the device, such as interface traffic, error statistics, and status information, to optimize network performance and improve management efficiency."
    },
    "Detection Device SNMP General": {
        "name": "Detection Device General (SNMP)",
        "desc": "The SNMP General plugin is used to monitor and manage the status of detection devices via SNMP. Administrators can obtain key information about the device, such as interface traffic, error statistics, and status information, to optimize network performance and improve management efficiency."
    },
    "Bastion Host SNMP General": {
        "name": "Bastion Host General (SNMP)",
        "desc": "The SNMP General plugin is used to monitor and manage the status of bastion hosts via SNMP. Administrators can obtain key information about the device, such as interface traffic, error statistics, and status information, to optimize network performance and improve management efficiency."
    },
    "Scanning Device SNMP General": {
        "name": "Scanning Device General (SNMP)",
        "desc": "The SNMP General plugin is used to monitor and manage the status of scanning devices via SNMP. Administrators can obtain key information about the device, such as interface traffic, error statistics, and status information, to optimize network performance and improve management efficiency."
    },
    "Storage SNMP General": {
        "name": "Storage Device General (SNMP)",
        "desc": "The SNMP General plugin is used to monitor and manage the status of storage devices via SNMP. Administrators can obtain key information about the device, such as interface traffic, error statistics, and status information, to optimize network performance and improve management efficiency."
    },
    "Storage IPMI": {
        "name": "Storage Device General (IPMI)",
        "desc": "The IPMI monitoring plugin communicates with hardware to provide real-time monitoring of system health status, hardware sensor data, and power management."
    },
    "Hardware Server SNMP General": {
        "name": "Hardware Server General (SNMP)",
        "desc": "The SNMP General plugin is used to monitor and manage the status of hardware servers via SNMP. Administrators can obtain key information about the device, such as interface traffic, error statistics, and status information, to optimize network performance and improve management efficiency."
    },
    "Hardware Server IPMI": {
        "name": "Hardware Server General (IPMI)",
        "desc": "The IPMI monitoring plugin communicates with hardware to provide real-time monitoring of system health status, hardware sensor data, and power management."
    },
    "SNMP Trap": {
        "name": "SNMP Trap",
        "desc": "The SNMP Trap monitoring plugin is used to receive and process alarms or status notifications (Trap messages) actively pushed by network devices, enabling real-time monitoring and fault alerts."
    },
    "Zookeeper": {
        "name": "Zookeeper",
        "desc": "By collecting runtime performance data and stability metrics of Zookeeper, such as uptime, average latency, and read-write ratios, users can monitor the cluster status in real-time and optimize performance."
    },
    "Apache": {
        "name": "Apache",
        "desc": "Real-time collection of Apache runtime data, resource utilization, request processing efficiency, and bandwidth statistics, helping users optimize performance, diagnose issues, and achieve efficient operations management."
    },
    "ClickHouse": {
        "name": "ClickHouse",
        "desc": "Collect runtime metrics of ClickHouse instances, such as memory, disk, query events, etc., for performance monitoring, resource tracking, and fault diagnosis, ensuring stable database operation."
    },
    "RabbitMQ": {
        "name": "RabbitMQ",
        "desc": "Used for monitoring RabbitMQ's runtime status, resource usage, message flow, and queue health."
    },
    "ActiveMQ": {
        "name": "ActiveMQ",
        "desc": "Used for collecting ActiveMQ topic-related metrics, enabling real-time monitoring of consumer count, enqueue/dequeue rates, and topic message backlog to ensure stable message queue operation."
    },
    "Nginx": {
        "name": "Nginx",
        "desc": "By collecting metrics such as Nginx requests, connection status, and processing efficiency, this helps monitor and optimize the website's performance and stability."
    },
    "Tomcat": {
        "name": "Tomcat",
        "desc": "Collects key performance metrics of Tomcat connectors and JVM memory to monitor server resource usage, request processing efficiency, and errors, optimizing system performance."
    },  
    "Consul": {
        "name": "Consul",
        "desc": "Used for real-time monitoring of Consul service health, collecting status check results, analyzing passing, warning, and critical metrics to help users promptly identify issues and ensure service availability."
    },
    "ElasticSearch": {
        "name": "ElasticSearch",
        "desc": "By collecting Elasticsearch file system metrics, HTTP requests, IO statistics, document statistics, query cache, and circuit breaker metrics, this plugin helps users monitor the health and performance of their cluster."
    },
    "MongoDB": {
        "name": "MongoDB",
        "desc": "By collecting metrics on MongoDB read and write activities, command execution, connection counts, latency, memory usage, and network traffic, this helps optimize performance and ensure efficient and stable database operations."
    },
    "Mysql": {
        "name": "Mysql",
        "desc": "Used to collect and monitor key metrics for MySQL database health and performance."
    },
    "Postgres": {
        "name": "Postgres",
        "desc": "Collecting PostgreSQL's session management, transaction metrics, and I/O performance data helps monitor resource usage, access behavior, operational efficiency, and identify potential issues within the database."
    },
    "Redis": {
        "name": "Redis",
        "desc": "Used to collect key indicators of Redis performance and resource utilization, helping improve system efficiency and stability."
    },
    "Docker": {
        "name": "Docker",
        "desc": "Used for collecting and analyzing the status, resource usage (CPU, memory, network, IO), and performance metrics of Docker containers, helping to identify anomalies and optimize container operational efficiency."
    },
    "vCenter": {
        "name": "vCenter",
        "desc": "vCenter is VMware's virtualization hub for monitoring resources (CPU/memory/storage/network), analyzing performance, and optimizing configurations. It helps identify VM/host anomalies and improves environment efficiency."
    }
}

MONITOR_OBJECT_METRIC_GROUP = {
    "Host": {
        "CPU": "CPU",
        "System": "System", 
        "Disk IO": "Disk IO", 
        "DISK": "Disk",
        "Process": "Process",
        "MEMORY": "Memory",
        "Net": "Net",
    },
    "Website": {
        "HTTP": "HTTP",
    },
    "Ping": {
        "Ping": "Ping",
    },
    "Cluster": {
        "Counts": "Counts",
        "Utilization": "Utilization",
    },
    "Pod": {
        "Status": "Status",
        "CPU": "CPU",
        "Memory": "Memory",
        "Disk": "Disk",
        "Network": "Network",
    },
    "Node": {
        "Status": "Status",
        "CPU": "CPU",
        "Memory": "Memory",
        "Disk": "Disk",
        "Net": "Net",
        "Load": "Load",
    },
    "Switch": {
        "Base": "Base",
        "Status": "Status",
        "Bandwidth": "Bandwidth",
        "Packet Error": "Packet Error",
        "Packet Loss": "Packet Loss",
        "Packet": "Packet",
        "Traffic": "Traffic",
    },
    "Router": {
        "Base": "Base",
        "Status": "Status",
        "Bandwidth": "Bandwidth",
        "Packet Error": "Packet Error",
        "Packet Loss": "Packet Loss",
        "Packet": "Packet",
        "Traffic": "Traffic",
    },
    "Loadbalance": {
        "Base": "Base",
        "Status": "Status",
        "Bandwidth": "Bandwidth",
        "Packet Error": "Packet Error",
        "Packet Loss": "Packet Loss",
        "Packet": "Packet",
        "Traffic": "Traffic",
    },
    "Firewall": {
        "Base": "Base",
        "Status": "Status",
        "Bandwidth": "Bandwidth",
        "Packet Error": "Packet Error",
        "Packet Loss": "Packet Loss",
        "Packet": "Packet",
        "Traffic": "Traffic",
    },
    "Detection Device": {
        "Base": "Base",
        "Status": "Status",
        "Bandwidth": "Bandwidth",
        "Packet Error": "Packet Error",
        "Packet Loss": "Packet Loss",
        "Packet": "Packet",
        "Traffic": "Traffic",
    },
    "Bastion Host": {
        "Base": "Base",
        "Status": "Status",
        "Bandwidth": "Bandwidth",
        "Packet Error": "Packet Error",
        "Packet Loss": "Packet Loss",
        "Packet": "Packet",
        "Traffic": "Traffic",
    },
    "Scanning Device": {
        "Base": "Base",
        "Status": "Status",
        "Bandwidth": "Bandwidth",
        "Packet Error": "Packet Error",
        "Packet Loss": "Packet Loss",
        "Packet": "Packet",
        "Traffic": "Traffic",
    },
    "Storage": {
        "Base": "Base",
        "Status": "Status",
        "Bandwidth": "Bandwidth",
        "Packet Error": "Packet Error",
        "Packet Loss": "Packet Loss",
        "Packet": "Packet",
        "Traffic": "Traffic",
         "Power": "Power", 
        "Environment": "Environment",       
    },
    "Hardware Server": {
        "Base": "Base",
        "Status": "Status",
        "Bandwidth": "Bandwidth",
        "Packet Error": "Packet Error",
        "Packet Loss": "Packet Loss",
        "Packet": "Packet",
        "Traffic": "Traffic",
        "Power": "Power", 
        "Environment": "Environment",            
    },
    "SNMP Trap": {   
    },
    "Zookeeper": {
        "Uptime": "Uptime",
        "Performance": "Performance",
        "Connection": "Connection",
        "Znode": "Znode",
        "Traffic": "Traffic",
    },
    "Apache": {
        "Uptime": "Uptime",
        "Work": "Work",
        "Request": "Request",
        "CPU": "CPU",
        "Duration": "Duration",
    },
    "ClickHouse": {
        "Uptime": "Uptime",
        "Memory": "Memory",
        "Disk": "Disk",
        "Query": "Query",
        "Part": "Part",
        "Load": "Load",
    },
    "RabbitMQ": {
        "Exchange": "Exchange",
        "Node": "Node",
        "Message": "Message",
    },
    "ActiveMQ": {
        "Topic": "Topic",
    },
    "Nginx": {
        "Request": "Request",
        "Connection": "Connection",
        "Efficiency": "Efficiency",
    },
    "Tomcat": {
        "Request": "Request",
        "Net": "Net",
        "Threads": "Threads",
        "Error": "Error",
        "JMX ": "JMX ",
    },
    "Consul": {
        "Check": "Check",
    },
    "ElasticSearch": {
        "Disk": "Disk",
        "HTTP": "HTTP",
        "IO": "IO",
        "Indices": "Indices",
        "Cache": "Cache",
        "Circuit Breakers": "Circuit Breakers",
    },
    "MongoDB": {
        "Active Operations": "Active Operations",
        "Commands": "Commands",
        "Connections": "Connections",
        "Latency": "Latency",
        "Memory": "Memory",
        "Traffic": "Traffic",
        "Storage": "Storage",
    },
    "Mysql": {
        "Connection": "Connection",
        "Error": "Error",
        "Cache": "Cache",
        "Traffic": "Traffic",
        "Command": "Command",
        "Session": "Session",
    },
    "Postgres": {
        "Performance": "Performance",
        "Cache": "Cache",
        "Memory": "Memory",
        "Transaction": "Transaction",
        "Session": "Session",
    },
    "Redis": {
        "Performance": "Performance",
        "Cache": "Cache",
        "Memory": "Memory",
        "Clients": "Clients",
        "CPU": "CPU",
        "Replication": "Replication",
        "Disk": "Disk",
        "Connectivity": "Connectivity",
    },
    "Docker": {
        "Docker Count": "Docker Count",
    },
    "Docker Container": {
        "Memory": "Memory",
        "CPU": "CPU",
        "Net": "Net",
        "Status": "Status",
        "IO": "IO",
    },
    "vCenter": {
        "Quantity": "Quantity",
    },
    "ESXI": {
        "Memory": "Memory",
        "CPU": "CPU",
        "Disk": "Disk",
        "Network": "Network",
    },
    "DataStorage": {
        "Default": "Default",
    },
    "VM": {
        "Memory": "Memory",
        "CPU": "CPU",
        "Disk": "Disk",
        "Network": "Network",
        "Power": "Power",
    }
}

MONITOR_OBJECT_METRIC = {
    "Host":{
    "cpu_summary.usage": {
        "name": "CPU Usage Rate",
        "desc": "Displays the CPU usage rate to indicate the system's load. It is derived by subtracting the idle from total. This metric is crucial for monitoring system performance."
    },
    "cpu_summary.idle": {
        "name": "CPU Idle Rate",
        "desc": "Displays the CPU idle rate, representing the amount of unused CPU resources in the system. It helps to know if the system is under high load. This metric is crucial for analyzing system performance and efficiency."
    },
    "cpu_summary.iowait": {
        "name": "Percentage of Time Waiting for IO",
        "desc": "Displays the percentage of CPU time spent waiting for IO operations, indicating the impact of disk or network performance on the system. Reducing wait time helps improve system performance. This metric is very useful for analyzing system bottlenecks."
    },
    "cpu_summary.system": {
        "name": "System Usage Rate",
        "desc": "Displays the system usage rate, showing the CPU resources consumed by kernel processes. Analyzing this value helps optimize system kernel performance and stability."
    },
    "cpu_summary.user": {
        "name": "User Usage Rate",
        "desc": "Displays the percentage of CPU resources used by user processes, helping understand the performance of applications and services. This metric is helpful in understanding the CPU consumption of specific applications."
    },
    "load1": {
        "name": "1 Minute Average Load",
        "desc": "Displays the average system load over the last 1 minute, providing a snapshot of short-term system activity. This metric helps monitor system performance in real-time."
    },
    "load5": {
        "name": "5 Minute Average Load",
        "desc": "Displays the average system load over the last 5 minutes, reflecting the medium-term load on the system. This medium-term metric helps identify sustained and intermittent high load situations."
    },
    "load15": {
        "name": "15 Minute Average Load",
        "desc": "Displays the average system load over the last 15 minutes, providing long-term load observation to understand the overall performance trend of the system."
    },
    "diskio_writes": {
        "name": "Disk I/O Write Rate",
        "desc": "Counts the number of data write operations to the disk in the specified time interval."
    },
    "diskio_write_bytes": {
        "name": "Disk I/O Write Bytes Rate",
        "desc": "Counts the number of bytes written to the disk in the specified time interval, represented in megabytes (MB)."
    },
    "diskio_write_time": {
        "name": "Disk I/O Write Time Rate",
        "desc": "Counts the time taken to write data to the disk in the specified time interval, represented in seconds (s)."
    },
    "diskio_reads": {
        "name": "Disk I/O Read Rate",
        "desc": "Counts the number of data read operations from the disk in the specified time interval."
    },
    "diskio_read_bytes": {
        "name": "Disk I/O Read Bytes Rate",
        "desc": "Counts the number of bytes read from the disk in the specified time interval, represented in megabytes (MB)."
    },
    "diskio_read_time": {
        "name": "Disk I/O Read Time Rate",
        "desc": "Counts the time taken to read data from the disk in the specified time interval, represented in seconds (s)."
    },
    "disk.is_use": {
        "name": "Disk Usage Rate",
        "desc": "Displays the percentage of disk space used, helping understand the utilization of disk resources. This metric is important for preventing disk overflow."
    },
    "disk.used": {
        "name": "Disk Used Size",
        "desc": "Displays the actual used disk space (in GB), used to determine disk capacity usage. This metric is helpful for monitoring disk space usage."
    },
    "env.procs": {
        "name": "Total Number of Processes",
        "desc": "Displays the total number of processes running on the system, helping understand the load distribution. This metric is important for monitoring the overall operation of the system."
    },
    "env.proc_running_current": {
        "name": "Number of Running Processes",
        "desc": "Displays the number of processes currently running, used to assess the concurrency. This metric is valuable for real-time monitoring of system load."
    },
    "env.procs_blocked_current": {
        "name": "Number of IO Blocked Processes",
        "desc": "Displays the number of processes currently blocked by IO operations. Analyzing this value helps optimize the system and reduce bottlenecks. This metric is helpful for identifying IO bottlenecks."
    },
    "mem.total": {
        "name": "Total Physical Memory Size",
        "desc": "Displays the total physical memory of the system (in GB), providing an overview of system resource configuration. This metric is important for understanding the base configuration of system resources."
    },
    "mem.free": {
        "name": "Free Physical Memory Amount",
        "desc": "Displays the amount of free physical memory currently available (in GB), helping understand the available resources. This metric is crucial for keeping track of memory resource usage."
    },
    "mem.cached": {
        "name": "Cache Memory Size",
        "desc": "Displays the amount of memory used for caching (in GB), used to improve system performance. This metric is important for understanding memory caching strategies."
    },
    "mem.buffer": {
        "name": "Buffer Memory Size",
        "desc": "Displays the amount of memory used for buffering (in GB), ensuring stable data transfer. This metric is crucial for performance optimization strategies."
    },
    "mem.usable": {
        "name": "Available Memory for Applications",
        "desc": "Displays the memory available for applications (in GB), ensuring smooth application operation. This metric is important for maintaining application performance and stability."
    },
    "mem.pct_usable": {
        "name": "Available Memory Percentage for Applications",
        "desc": "Displays the percentage of memory available, helping determine if there is sufficient memory to support applications. This metric is useful for monitoring memory pressure and capacity planning strategies."
    },
    "mem.used": {
        "name": "Memory Used by Applications",
        "desc": "Displays the memory used by applications (in GB), analyzing this value helps optimize application memory usage. This metric is crucial for monitoring application resource consumption."
    },
    "mem.pct_used": {
        "name": "Application Memory Usage Percentage",
        "desc": "Displays the percentage of memory used by applications, understanding memory usage distribution. This metric is valuable for optimizing memory usage."
    },
    "mem.psc_used": {
        "name": "Used Physical Memory Amount",
        "desc": "Displays the total amount of physical memory used by the system (in GB), helping understand the overall distribution of memory resources. This metric is crucial for gaining a comprehensive understanding of system memory usage."
    },
    "mem.shared": {
        "name": "Shared Memory Usage",
        "desc": "Displays the usage of shared memory (in GB), used for data sharing between processes. This metric helps optimize system memory allocation strategies."
    },
    "net.speed_packets_recv": {
        "name": "Incoming Packets on NIC",
        "desc": "Displays the number of data packets received by the network interface per unit of time, used to evaluate network reception performance. This metric is crucial for monitoring network traffic."
    },
    "net.speed_packets_sent": {
        "name": "Outgoing Packets on NIC",
        "desc": "Displays the number of data packets sent by the network interface per unit of time, used to evaluate network transmission performance. This metric is crucial for monitoring network traffic."
    },
    "net.speed_recv": {
        "name": "Incoming Bytes on NIC",
        "desc": "Displays the number of bytes received by the network interface per unit of time (in MB), used to evaluate network bandwidth utilization. This metric is important for monitoring network bandwidth."
    },
    "net.speed_sent": {
        "name": "Outgoing Bytes on NIC",
        "desc": "Displays the number of bytes sent by the network interface per unit of time (in MB), used to evaluate network bandwidth utilization. This metric is crucial for monitoring network bandwidth."
    },
    "net.errors_in": {
        "name": "NIC Error Packets",
        "desc": "Displays the number of error packets received by the network interface, used to detect network issues. This metric is helpful for identifying network faults and abnormal traffic."
    },
    "net.errors_out": {
        "name": "NIC Error Packets",
        "desc": "Displays the number of error packets sent by the network interface, helping understand network transmission errors. This metric is helpful for identifying network faults and abnormal traffic."
    },
    "net.dropped_in": {
        "name": "NIC Dropped Packets",
        "desc": "Displays the number of dropped packets received by the network interface, indicating network congestion. This metric is crucial for monitoring network reliability."
    },
    "net.dropped_out": {
        "name": "NIC Dropped Packets",
        "desc": "Displays the number of dropped packets sent by the network interface, indicating network transmission congestion. This metric is crucial for monitoring network reliability."
    }
},
    "Website": {
    "http_success.rate": {
        "name": "Success Rate",
        "desc": "Measures the success rate of multiple nodes probing targets (the percentage of successful responses out of the total number of requests)."
    },
    "http_duration": {
        "name": "Response Time",
        "desc": "This metric represents the total time taken from initiating an HTTP request to receiving the HTTP response. It is used to assess the performance of web services, especially when handling user requests. An extended duration may indicate lower backend processing efficiency or network latency, which can adversely affect the user experience. It is crucial for enhancing system responsiveness and optimizing performance."
    },
    "http_code": {
        "name": "HTTP Code",
        "desc": "This metric represents the HTTP response status code for an HTTP request. It captures the value of the HTTP response status codes, such as 200 (OK), 404 (Not Found), 500 (Internal Server Error), etc. These status codes are vital for monitoring the health and performance of web applications, assisting in identifying potential issues."
    },
    "http_content.length": {
        "name": "HTTP Content Length",
        "desc": "This metric indicates the length of the HTTP response content in bytes. Larger content lengths can result in extended data transfer times and consume more bandwidth. Monitoring this metric is crucial for optimizing website performance or analyzing bandwidth usage. Understanding the size of the response content can assist developers in making optimizations."
    }
},
    "Ping":{
    "ping_ttl": {
        "name": "Average TTL",
        "desc": "Represents the average 'hop count' (or time) allowed for ping packets from the source device to the target. This metric helps identify if packets take an abnormal number of hops or if there are route anomalies. Higher TTL values indicate longer paths."
    },
    "ping_response_time": {
        "name": "Average Response Time",
        "desc": "Represents the average ping response time of the target device over a period. This metric helps evaluate latency between the source and target device. Lower average response time indicates good network performance."
    },
    "ping_packet_transmission_rate": {
        "name": "Packet Transmission Rate",
        "desc": "Represents the percentage of successfully received packets out of the total packets transmitted. This metric measures network quality and transmission reliability. Low packet loss indicates stable and reliable connectivity."
    },
    "ping_packet_loss_rate": {
        "name": "Packet Loss Rate",
        "desc": "Represents the percentage of packets lost during ping requests. This metric helps identify unstable network connections or transmission problems. Lower loss rates indicate more stable connectivity."
    },
    "ping_error_response_code": {
        "name": "Ping State",
        "desc": "Represents the resulting code after a ping operation. A code of 0 indicates success, while non-zero values indicate potential issues with the network or host. This metric helps quickly detect network connectivity errors."
    }
},
    "Cluster": {
        "cluster_pod_count": {
            "name": "Pod Count",
            "desc": "It is used to count the total number of Pods currently present in the Kubernetes cluster. This metric returns the count of Pods running in the cluster, including those across all namespaces."
        },
        "cluster_node_count": {
            "name": "Node Count",
            "desc": "It is used to count the total number of nodes currently available in the Kubernetes cluster. This metric returns the number of nodes in the cluster, helping users understand the scale and resources of the cluster."
        },
        "cluster_cpu_utilization": {
            "name": "CPU Utilization",
            "desc": "Represents the current CPU utilization of the cluster, typically expressed as a percentage."
        },
        "cluster_memory_utilization": {
            "name": "Memory Utilization",
            "desc": "Shows the current memory utilization of the cluster, expressed as a percentage."
        }
    },
    "Pod": {
        "pod_status": {
            "name": "Pod Status",
            "desc": "Retrieves the current status of the Pod, such as Running, Stopped, etc."
        },
        "pod_restart_count": {
            "name": "Restart Count",
            "desc": "Monitors the restart counts of containers in the Pod to assess stability and frequency of issues."
        },
        "pod_cpu_utilization": {
            "name": "CPU Utilization",
            "desc": "Calculates the CPU utilization of a Pod, reflecting the difference between container CPU limits and requests."
        },
        "pod_memory_utilization": {
            "name": "Memory Utilization",
            "desc": "Calculates the memory utilization of the Pod as a ratio of memory limits to requests."
        },
        "pod_io_writes": {
            "name": "I/O Write Rate",
            "desc": "This metric represents the number of I/O write operations performed by a specific Pod over a specified time period. The write count can help analyze the write demands of the application on the storage system."
        },
        "pod_io_read": {
            "name": "I/O Read Rate",
            "desc": "This metric represents the number of I/O read operations performed by a specific Pod over a specified time period. The read count can help analyze the read demands of the application on the storage system."
        },
        "pod_network_in": {
            "name": "Network In",
            "desc": "Monitors the inbound network traffic of a Pod, calculated based on the number of containers and IPs."
        },
        "pod_network_out": {
            "name": "Network Out",
            "desc": "Monitors the outbound network traffic of a Pod, calculated based on the number of containers and IPs."
        }
    },
    "Node": {
  "node_status_condition": {
    "name": "Node Status",
    "desc": "Node Status indicates the current operational state of the node, such as 'Running' or 'Stopped.' It helps administrators monitor and manage nodes within the Kubernetes cluster."
  },
  "node_cpu_utilization": {
    "name": "CPU Utilization",
    "desc": "CPU Utilization indicates the current usage level of the node's CPU relative to its total available CPU resources. Monitoring this metric helps identify CPU bottlenecks and optimize resource allocation."
  },
  "node_memory_usage": {
    "name": "Application Memory Usage",
    "desc": "Application Memory Usage represents the total amount of memory utilized by applications running on the node. This metric helps understand the memory demands of applications and their impact on system performance."
  },
  "node_memory_utilization": {
    "name": "Application Memory Utilization Rate",
    "desc": "Application Memory Utilization Rate is the ratio of memory used by the application to its configured memory limits. By monitoring this metric, users can determine if adjustments to memory limits are needed."
  },
  "node_io_read": {
    "name": "Disk Write Rate",
    "desc": "Disk Write Rate indicates the rate of write operations performed by the node over a specified period. This metric is crucial for monitoring the disk write performance of applications."
  },
  "node_io_write": {
    "name": "Disk Read Rate",
    "desc": "Disk Read Rate indicates the rate of read operations performed by the node over a specified period. This metric helps assess the data reading performance of applications and storage load."
  },
  "node_network_receive": {
    "name": "Incoming Bytes on NIC",
    "desc": "Network In refers to the volume of data traffic received through the network interface. Monitoring this metric helps analyze if network bandwidth is sufficient and the overall network performance."
  },
  "node_network_transmit": {
    "name": "Outgoing Bytes on NIC",
    "desc": "Network Out refers to the volume of data traffic sent through the network interface. This metric helps understand the node's network egress demands and potential bottlenecks."
  },
  "node_cpu_load1": {
    "name": "1 Minute Average Load",
    "desc": "1 Minute Average Load indicates the average load on the system over the last minute. This metric helps provide a real-time understanding of the system’s load level."
  },
  "node_cpu_load5": {
    "name": "5 Minute Average Load",
    "desc": "5 Minute Average Load indicates the average load on the system over the last 5 minutes. This metric helps identify load trends and their impact on system performance."
  },
  "node_cpu_load15": {
    "name": "15 Minute Average Load",
    "desc": "15 Minute Average Load indicates the average load on the system over the last 15 minutes. Monitoring this metric helps administrators understand the long-term load state of the system."
  }
    },
    "Switch": {
  "sysUpTime": {
    "name": "System Uptime",
    "desc": "This metric indicates the uptime of the device since the last restart, measured in days. By monitoring the uptime, network administrators can understand the stability and reliability of the device and identify potential reboot or failure issues."
  },
  "ifAdminStatus": {
    "name": "Interface Admin Status",
    "desc": "This metric indicates the administrative status of the network switch interface. It serves to indicate whether the interface is enabled (up) or disabled (down) by an administrator, along with other states such as testing or not present. This information is vital for network management and troubleshooting."
  },
  "ifOperStatus": {
    "name": "Interface Oper Status",
    "desc": "This metric reflects the actual operational status of the network switch interface, indicating whether the interface is operational. Unlike the administrative status, the operational status shows whether the interface can successfully receive and send traffic, which is crucial for monitoring network health."
  },
  "ifHighSpeed": {
    "name": "Interface Bandwidth",
    "desc": "This metric indicates the maximum data transmission speed supported by the network interface, usually measured in KB per second. Understanding the maximum speed of the interface helps administrators optimize traffic and utilize network resources effectively."
  },
  "ifInErrors": {
    "name": "Incoming Errors Rate (per second)",
    "desc": "This metric calculates the average rate of incoming error packets over the past 5 minutes, measured in packets per second. Monitoring incoming errors allows administrators to detect potential issues, such as physical connection faults or configuration errors, in a timely manner."
  },
  "ifOutErrors": {
    "name": "Outgoing Errors Rate (per second)",
    "desc": "This metric calculates the average rate of outgoing error packets over the past 5 minutes, measured in packets per second. Monitoring outgoing errors is essential for identifying transmission issues and ensuring data integrity."
  },
  "ifInDiscards": {
    "name": "Incoming Discards Rate (per second)",
    "desc": "This metric represents the average rate of incoming discarded packets over the past 5 minutes, measured in packets per second. Packet discards may indicate network congestion or resource shortages, and monitoring this metric can help administrators optimize network performance."
  },
  "ifOutDiscards": {
    "name": "Outgoing Discards Rate (per second)",
    "desc": "This metric calculates the average rate of outgoing discarded packets over the past 5 minutes, measured in packets per second. Monitoring outgoing discards can help identify network transmission issues and misconfigurations."
  },
  "ifInUcastPkts": {
    "name": "Incoming Unicast Packets Rate (per second)",
    "desc": "This metric indicates the average rate of incoming unicast packets over the past 5 minutes, measured in packets per second. Monitoring unicast packets is crucial for assessing interface utilization and traffic load."
  },
  "ifOutUcastPkts": {
    "name": "Outgoing Unicast Packets Rate (per second)",
    "desc": "This metric calculates the average rate of outgoing unicast packets over the past 5 minutes, measured in packets per second. By monitoring the number of unicast packets, administrators can assess the transmission performance of the interface and the usage of traffic."
  },
  "ifInOctets": {
    "name": "Interface Incoming Traffic Rate (per second)",
    "desc": "This metric indicates the average rate of bytes received over the past 5 minutes, converted to megabytes (MB). Monitoring byte traffic helps evaluate the load on the interface and bandwidth usage."
  },
  "ifOutOctets": {
    "name": "Interface Outgoing Traffic Rate (per second)",
    "desc": "This metric calculates the average rate of bytes sent over the past 5 minutes, measured in megabytes (MB). Monitoring outgoing traffic is crucial for ensuring data transmission quality and optimizing network performance."
  },
  "iftotalInOctets": {
    "name": "Device Total Incoming Traffic (per second)",
    "desc": "This metric indicates the average rate of total bytes received by the entire device over the past 5 minutes, measured in megabytes per second (MB/s). By summing the incoming byte counts from multiple interfaces, this metric helps administrators obtain an overview of the device's incoming traffic, supporting overall traffic monitoring and capacity planning."
  },
  "iftotalOutOctets": {
    "name": "Device Total Outgoing Traffic (per second)",
    "desc": "This metric represents the average rate of total bytes sent by the entire device over the past 5 minutes, measured in megabytes per second (MB/s). By summing the outgoing byte counts from multiple interfaces, this metric allows administrators to comprehensively assess the sending performance of the entire system, enabling more effective traffic management and optimization."
  }
},
    "Router": {
  "sysUpTime": {
    "name": "System Uptime",
    "desc": "This metric indicates the uptime of the device since the last restart, measured in days. By monitoring the uptime, network administrators can understand the stability and reliability of the device and identify potential reboot or failure issues."
  },
  "ifAdminStatus": {
    "name": "Interface Admin Status",
    "desc": "This metric indicates the administrative status of the network switch interface. It serves to indicate whether the interface is enabled (up) or disabled (down) by an administrator, along with other states such as testing or not present. This information is vital for network management and troubleshooting."
  },
  "ifOperStatus": {
    "name": "Interface Oper Status",
    "desc": "This metric reflects the actual operational status of the network switch interface, indicating whether the interface is operational. Unlike the administrative status, the operational status shows whether the interface can successfully receive and send traffic, which is crucial for monitoring network health."
  },
  "ifHighSpeed": {
    "name": "Interface Bandwidth",
    "desc": "This metric indicates the maximum data transmission speed supported by the network interface, usually measured in KB per second. Understanding the maximum speed of the interface helps administrators optimize traffic and utilize network resources effectively."
  },
  "ifInErrors": {
    "name": "Incoming Errors Rate (per second)",
    "desc": "This metric calculates the average rate of incoming error packets over the past 5 minutes, measured in packets per second. Monitoring incoming errors allows administrators to detect potential issues, such as physical connection faults or configuration errors, in a timely manner."
  },
  "ifOutErrors": {
    "name": "Outgoing Errors Rate (per second)",
    "desc": "This metric calculates the average rate of outgoing error packets over the past 5 minutes, measured in packets per second. Monitoring outgoing errors is essential for identifying transmission issues and ensuring data integrity."
  },
  "ifInDiscards": {
    "name": "Incoming Discards Rate (per second)",
    "desc": "This metric represents the average rate of incoming discarded packets over the past 5 minutes, measured in packets per second. Packet discards may indicate network congestion or resource shortages, and monitoring this metric can help administrators optimize network performance."
  },
  "ifOutDiscards": {
    "name": "Outgoing Discards Rate (per second)",
    "desc": "This metric calculates the average rate of outgoing discarded packets over the past 5 minutes, measured in packets per second. Monitoring outgoing discards can help identify network transmission issues and misconfigurations."
  },
  "ifInUcastPkts": {
    "name": "Incoming Unicast Packets Rate (per second)",
    "desc": "This metric indicates the average rate of incoming unicast packets over the past 5 minutes, measured in packets per second. Monitoring unicast packets is crucial for assessing interface utilization and traffic load."
  },
  "ifOutUcastPkts": {
    "name": "Outgoing Unicast Packets Rate (per second)",
    "desc": "This metric calculates the average rate of outgoing unicast packets over the past 5 minutes, measured in packets per second. By monitoring the number of unicast packets, administrators can assess the transmission performance of the interface and the usage of traffic."
  },
  "ifInOctets": {
    "name": "Interface Incoming Traffic Rate (per second)",
    "desc": "This metric indicates the average rate of bytes received over the past 5 minutes, converted to megabytes (MB). Monitoring byte traffic helps evaluate the load on the interface and bandwidth usage."
  },
  "ifOutOctets": {
    "name": "Interface Outgoing Traffic Rate (per second)",
    "desc": "This metric calculates the average rate of bytes sent over the past 5 minutes, measured in megabytes (MB). Monitoring outgoing traffic is crucial for ensuring data transmission quality and optimizing network performance."
  },
  "iftotalInOctets": {
    "name": "Device Total Incoming Traffic (per second)",
    "desc": "This metric indicates the average rate of total bytes received by the entire device over the past 5 minutes, measured in megabytes per second (MB/s). By summing the incoming byte counts from multiple interfaces, this metric helps administrators obtain an overview of the device's incoming traffic, supporting overall traffic monitoring and capacity planning."
  },
  "iftotalOutOctets": {
    "name": "Device Total Outgoing Traffic (per second)",
    "desc": "This metric represents the average rate of total bytes sent by the entire device over the past 5 minutes, measured in megabytes per second (MB/s). By summing the outgoing byte counts from multiple interfaces, this metric allows administrators to comprehensively assess the sending performance of the entire system, enabling more effective traffic management and optimization."
  }
},
    "Loadbalance": {
  "sysUpTime": {
    "name": "System Uptime",
    "desc": "This metric indicates the uptime of the device since the last restart, measured in days. By monitoring the uptime, network administrators can understand the stability and reliability of the device and identify potential reboot or failure issues."
  },
  "ifAdminStatus": {
    "name": "Interface Admin Status",
    "desc": "This metric indicates the administrative status of the network switch interface. It serves to indicate whether the interface is enabled (up) or disabled (down) by an administrator, along with other states such as testing or not present. This information is vital for network management and troubleshooting."
  },
  "ifOperStatus": {
    "name": "Interface Oper Status",
    "desc": "This metric reflects the actual operational status of the network switch interface, indicating whether the interface is operational. Unlike the administrative status, the operational status shows whether the interface can successfully receive and send traffic, which is crucial for monitoring network health."
  },
  "ifHighSpeed": {
    "name": "Interface Bandwidth",
    "desc": "This metric indicates the maximum data transmission speed supported by the network interface, usually measured in KB per second. Understanding the maximum speed of the interface helps administrators optimize traffic and utilize network resources effectively."
  },
  "ifInErrors": {
    "name": "Incoming Errors Rate (per second)",
    "desc": "This metric calculates the average rate of incoming error packets over the past 5 minutes, measured in packets per second. Monitoring incoming errors allows administrators to detect potential issues, such as physical connection faults or configuration errors, in a timely manner."
  },
  "ifOutErrors": {
    "name": "Outgoing Errors Rate (per second)",
    "desc": "This metric calculates the average rate of outgoing error packets over the past 5 minutes, measured in packets per second. Monitoring outgoing errors is essential for identifying transmission issues and ensuring data integrity."
  },
  "ifInDiscards": {
    "name": "Incoming Discards Rate (per second)",
    "desc": "This metric represents the average rate of incoming discarded packets over the past 5 minutes, measured in packets per second. Packet discards may indicate network congestion or resource shortages, and monitoring this metric can help administrators optimize network performance."
  },
  "ifOutDiscards": {
    "name": "Outgoing Discards Rate (per second)",
    "desc": "This metric calculates the average rate of outgoing discarded packets over the past 5 minutes, measured in packets per second. Monitoring outgoing discards can help identify network transmission issues and misconfigurations."
  },
  "ifInUcastPkts": {
    "name": "Incoming Unicast Packets Rate (per second)",
    "desc": "This metric indicates the average rate of incoming unicast packets over the past 5 minutes, measured in packets per second. Monitoring unicast packets is crucial for assessing interface utilization and traffic load."
  },
  "ifOutUcastPkts": {
    "name": "Outgoing Unicast Packets Rate (per second)",
    "desc": "This metric calculates the average rate of outgoing unicast packets over the past 5 minutes, measured in packets per second. By monitoring the number of unicast packets, administrators can assess the transmission performance of the interface and the usage of traffic."
  },
  "ifInOctets": {
    "name": "Interface Incoming Traffic Rate (per second)",
    "desc": "This metric indicates the average rate of bytes received over the past 5 minutes, converted to megabytes (MB). Monitoring byte traffic helps evaluate the load on the interface and bandwidth usage."
  },
  "ifOutOctets": {
    "name": "Interface Outgoing Traffic Rate (per second)",
    "desc": "This metric calculates the average rate of bytes sent over the past 5 minutes, measured in megabytes (MB). Monitoring outgoing traffic is crucial for ensuring data transmission quality and optimizing network performance."
  },
  "iftotalInOctets": {
    "name": "Device Total Incoming Traffic (per second)",
    "desc": "This metric indicates the average rate of total bytes received by the entire device over the past 5 minutes, measured in megabytes per second (MB/s). By summing the incoming byte counts from multiple interfaces, this metric helps administrators obtain an overview of the device's incoming traffic, supporting overall traffic monitoring and capacity planning."
  },
  "iftotalOutOctets": {
    "name": "Device Total Outgoing Traffic (per second)",
    "desc": "This metric represents the average rate of total bytes sent by the entire device over the past 5 minutes, measured in megabytes per second (MB/s). By summing the outgoing byte counts from multiple interfaces, this metric allows administrators to comprehensively assess the sending performance of the entire system, enabling more effective traffic management and optimization."
  }
},
    "Firewall": {
  "sysUpTime": {
    "name": "System Uptime",
    "desc": "This metric indicates the uptime of the device since the last restart, measured in days. By monitoring the uptime, network administrators can understand the stability and reliability of the device and identify potential reboot or failure issues."
  },
  "ifAdminStatus": {
    "name": "Interface Admin Status",
    "desc": "This metric indicates the administrative status of the network switch interface. It serves to indicate whether the interface is enabled (up) or disabled (down) by an administrator, along with other states such as testing or not present. This information is vital for network management and troubleshooting."
  },
  "ifOperStatus": {
    "name": "Interface Oper Status",
    "desc": "This metric reflects the actual operational status of the network switch interface, indicating whether the interface is operational. Unlike the administrative status, the operational status shows whether the interface can successfully receive and send traffic, which is crucial for monitoring network health."
  },
  "ifHighSpeed": {
    "name": "Interface Bandwidth",
    "desc": "This metric indicates the maximum data transmission speed supported by the network interface, usually measured in KB per second. Understanding the maximum speed of the interface helps administrators optimize traffic and utilize network resources effectively."
  },
  "ifInErrors": {
    "name": "Incoming Errors Rate (per second)",
    "desc": "This metric calculates the average rate of incoming error packets over the past 5 minutes, measured in packets per second. Monitoring incoming errors allows administrators to detect potential issues, such as physical connection faults or configuration errors, in a timely manner."
  },
  "ifOutErrors": {
    "name": "Outgoing Errors Rate (per second)",
    "desc": "This metric calculates the average rate of outgoing error packets over the past 5 minutes, measured in packets per second. Monitoring outgoing errors is essential for identifying transmission issues and ensuring data integrity."
  },
  "ifInDiscards": {
    "name": "Incoming Discards Rate (per second)",
    "desc": "This metric represents the average rate of incoming discarded packets over the past 5 minutes, measured in packets per second. Packet discards may indicate network congestion or resource shortages, and monitoring this metric can help administrators optimize network performance."
  },
  "ifOutDiscards": {
    "name": "Outgoing Discards Rate (per second)",
    "desc": "This metric calculates the average rate of outgoing discarded packets over the past 5 minutes, measured in packets per second. Monitoring outgoing discards can help identify network transmission issues and misconfigurations."
  },
  "ifInUcastPkts": {
    "name": "Incoming Unicast Packets Rate (per second)",
    "desc": "This metric indicates the average rate of incoming unicast packets over the past 5 minutes, measured in packets per second. Monitoring unicast packets is crucial for assessing interface utilization and traffic load."
  },
  "ifOutUcastPkts": {
    "name": "Outgoing Unicast Packets Rate (per second)",
    "desc": "This metric calculates the average rate of outgoing unicast packets over the past 5 minutes, measured in packets per second. By monitoring the number of unicast packets, administrators can assess the transmission performance of the interface and the usage of traffic."
  },
  "ifInOctets": {
    "name": "Interface Incoming Traffic Rate (per second)",
    "desc": "This metric indicates the average rate of bytes received over the past 5 minutes, converted to megabytes (MB). Monitoring byte traffic helps evaluate the load on the interface and bandwidth usage."
  },
  "ifOutOctets": {
    "name": "Interface Outgoing Traffic Rate (per second)",
    "desc": "This metric calculates the average rate of bytes sent over the past 5 minutes, measured in megabytes (MB). Monitoring outgoing traffic is crucial for ensuring data transmission quality and optimizing network performance."
  },
  "iftotalInOctets": {
    "name": "Device Total Incoming Traffic (per second)",
    "desc": "This metric indicates the average rate of total bytes received by the entire device over the past 5 minutes, measured in megabytes per second (MB/s). By summing the incoming byte counts from multiple interfaces, this metric helps administrators obtain an overview of the device's incoming traffic, supporting overall traffic monitoring and capacity planning."
  },
  "iftotalOutOctets": {
    "name": "Device Total Outgoing Traffic (per second)",
    "desc": "This metric represents the average rate of total bytes sent by the entire device over the past 5 minutes, measured in megabytes per second (MB/s). By summing the outgoing byte counts from multiple interfaces, this metric allows administrators to comprehensively assess the sending performance of the entire system, enabling more effective traffic management and optimization."
  }
},
    "Detection Device": {
  "sysUpTime": {
    "name": "System Uptime",
    "desc": "This metric indicates the uptime of the device since the last restart, measured in days. By monitoring the uptime, network administrators can understand the stability and reliability of the device and identify potential reboot or failure issues."
  },
  "ifAdminStatus": {
    "name": "Interface Admin Status",
    "desc": "This metric indicates the administrative status of the network switch interface. It serves to indicate whether the interface is enabled (up) or disabled (down) by an administrator, along with other states such as testing or not present. This information is vital for network management and troubleshooting."
  },
  "ifOperStatus": {
    "name": "Interface Oper Status",
    "desc": "This metric reflects the actual operational status of the network switch interface, indicating whether the interface is operational. Unlike the administrative status, the operational status shows whether the interface can successfully receive and send traffic, which is crucial for monitoring network health."
  },
  "ifHighSpeed": {
    "name": "Interface Bandwidth",
    "desc": "This metric indicates the maximum data transmission speed supported by the network interface, usually measured in KB per second. Understanding the maximum speed of the interface helps administrators optimize traffic and utilize network resources effectively."
  },
  "ifInErrors": {
    "name": "Incoming Errors Rate (per second)",
    "desc": "This metric calculates the average rate of incoming error packets over the past 5 minutes, measured in packets per second. Monitoring incoming errors allows administrators to detect potential issues, such as physical connection faults or configuration errors, in a timely manner."
  },
  "ifOutErrors": {
    "name": "Outgoing Errors Rate (per second)",
    "desc": "This metric calculates the average rate of outgoing error packets over the past 5 minutes, measured in packets per second. Monitoring outgoing errors is essential for identifying transmission issues and ensuring data integrity."
  },
  "ifInDiscards": {
    "name": "Incoming Discards Rate (per second)",
    "desc": "This metric represents the average rate of incoming discarded packets over the past 5 minutes, measured in packets per second. Packet discards may indicate network congestion or resource shortages, and monitoring this metric can help administrators optimize network performance."
  },
  "ifOutDiscards": {
    "name": "Outgoing Discards Rate (per second)",
    "desc": "This metric calculates the average rate of outgoing discarded packets over the past 5 minutes, measured in packets per second. Monitoring outgoing discards can help identify network transmission issues and misconfigurations."
  },
  "ifInUcastPkts": {
    "name": "Incoming Unicast Packets Rate (per second)",
    "desc": "This metric indicates the average rate of incoming unicast packets over the past 5 minutes, measured in packets per second. Monitoring unicast packets is crucial for assessing interface utilization and traffic load."
  },
  "ifOutUcastPkts": {
    "name": "Outgoing Unicast Packets Rate (per second)",
    "desc": "This metric calculates the average rate of outgoing unicast packets over the past 5 minutes, measured in packets per second. By monitoring the number of unicast packets, administrators can assess the transmission performance of the interface and the usage of traffic."
  },
  "ifInOctets": {
    "name": "Interface Incoming Traffic Rate (per second)",
    "desc": "This metric indicates the average rate of bytes received over the past 5 minutes, converted to megabytes (MB). Monitoring byte traffic helps evaluate the load on the interface and bandwidth usage."
  },
  "ifOutOctets": {
    "name": "Interface Outgoing Traffic Rate (per second)",
    "desc": "This metric calculates the average rate of bytes sent over the past 5 minutes, measured in megabytes (MB). Monitoring outgoing traffic is crucial for ensuring data transmission quality and optimizing network performance."
  },
  "iftotalInOctets": {
    "name": "Device Total Incoming Traffic (per second)",
    "desc": "This metric indicates the average rate of total bytes received by the entire device over the past 5 minutes, measured in megabytes per second (MB/s). By summing the incoming byte counts from multiple interfaces, this metric helps administrators obtain an overview of the device's incoming traffic, supporting overall traffic monitoring and capacity planning."
  },
  "iftotalOutOctets": {
    "name": "Device Total Outgoing Traffic (per second)",
    "desc": "This metric represents the average rate of total bytes sent by the entire device over the past 5 minutes, measured in megabytes per second (MB/s). By summing the outgoing byte counts from multiple interfaces, this metric allows administrators to comprehensively assess the sending performance of the entire system, enabling more effective traffic management and optimization."
  }
},
    "Bastion Host": {
  "sysUpTime": {
    "name": "System Uptime",
    "desc": "This metric indicates the uptime of the device since the last restart, measured in days. By monitoring the uptime, network administrators can understand the stability and reliability of the device and identify potential reboot or failure issues."
  },
  "ifAdminStatus": {
    "name": "Interface Admin Status",
    "desc": "This metric indicates the administrative status of the network switch interface. It serves to indicate whether the interface is enabled (up) or disabled (down) by an administrator, along with other states such as testing or not present. This information is vital for network management and troubleshooting."
  },
  "ifOperStatus": {
    "name": "Interface Oper Status",
    "desc": "This metric reflects the actual operational status of the network switch interface, indicating whether the interface is operational. Unlike the administrative status, the operational status shows whether the interface can successfully receive and send traffic, which is crucial for monitoring network health."
  },
  "ifHighSpeed": {
    "name": "Interface Bandwidth",
    "desc": "This metric indicates the maximum data transmission speed supported by the network interface, usually measured in KB per second. Understanding the maximum speed of the interface helps administrators optimize traffic and utilize network resources effectively."
  },
  "ifInErrors": {
    "name": "Incoming Errors Rate (per second)",
    "desc": "This metric calculates the average rate of incoming error packets over the past 5 minutes, measured in packets per second. Monitoring incoming errors allows administrators to detect potential issues, such as physical connection faults or configuration errors, in a timely manner."
  },
  "ifOutErrors": {
    "name": "Outgoing Errors Rate (per second)",
    "desc": "This metric calculates the average rate of outgoing error packets over the past 5 minutes, measured in packets per second. Monitoring outgoing errors is essential for identifying transmission issues and ensuring data integrity."
  },
  "ifInDiscards": {
    "name": "Incoming Discards Rate (per second)",
    "desc": "This metric represents the average rate of incoming discarded packets over the past 5 minutes, measured in packets per second. Packet discards may indicate network congestion or resource shortages, and monitoring this metric can help administrators optimize network performance."
  },
  "ifOutDiscards": {
    "name": "Outgoing Discards Rate (per second)",
    "desc": "This metric calculates the average rate of outgoing discarded packets over the past 5 minutes, measured in packets per second. Monitoring outgoing discards can help identify network transmission issues and misconfigurations."
  },
  "ifInUcastPkts": {
    "name": "Incoming Unicast Packets Rate (per second)",
    "desc": "This metric indicates the average rate of incoming unicast packets over the past 5 minutes, measured in packets per second. Monitoring unicast packets is crucial for assessing interface utilization and traffic load."
  },
  "ifOutUcastPkts": {
    "name": "Outgoing Unicast Packets Rate (per second)",
    "desc": "This metric calculates the average rate of outgoing unicast packets over the past 5 minutes, measured in packets per second. By monitoring the number of unicast packets, administrators can assess the transmission performance of the interface and the usage of traffic."
  },
  "ifInOctets": {
    "name": "Interface Incoming Traffic Rate (per second)",
    "desc": "This metric indicates the average rate of bytes received over the past 5 minutes, converted to megabytes (MB). Monitoring byte traffic helps evaluate the load on the interface and bandwidth usage."
  },
  "ifOutOctets": {
    "name": "Interface Outgoing Traffic Rate (per second)",
    "desc": "This metric calculates the average rate of bytes sent over the past 5 minutes, measured in megabytes (MB). Monitoring outgoing traffic is crucial for ensuring data transmission quality and optimizing network performance."
  },
  "iftotalInOctets": {
    "name": "Device Total Incoming Traffic (per second)",
    "desc": "This metric indicates the average rate of total bytes received by the entire device over the past 5 minutes, measured in megabytes per second (MB/s). By summing the incoming byte counts from multiple interfaces, this metric helps administrators obtain an overview of the device's incoming traffic, supporting overall traffic monitoring and capacity planning."
  },
  "iftotalOutOctets": {
    "name": "Device Total Outgoing Traffic (per second)",
    "desc": "This metric represents the average rate of total bytes sent by the entire device over the past 5 minutes, measured in megabytes per second (MB/s). By summing the outgoing byte counts from multiple interfaces, this metric allows administrators to comprehensively assess the sending performance of the entire system, enabling more effective traffic management and optimization."
  }
},
    "Scanning Device": {
  "sysUpTime": {
    "name": "System Uptime",
    "desc": "This metric indicates the uptime of the device since the last restart, measured in days. By monitoring the uptime, network administrators can understand the stability and reliability of the device and identify potential reboot or failure issues."
  },
  "ifAdminStatus": {
    "name": "Interface Admin Status",
    "desc": "This metric indicates the administrative status of the network switch interface. It serves to indicate whether the interface is enabled (up) or disabled (down) by an administrator, along with other states such as testing or not present. This information is vital for network management and troubleshooting."
  },
  "ifOperStatus": {
    "name": "Interface Oper Status",
    "desc": "This metric reflects the actual operational status of the network switch interface, indicating whether the interface is operational. Unlike the administrative status, the operational status shows whether the interface can successfully receive and send traffic, which is crucial for monitoring network health."
  },
  "ifHighSpeed": {
    "name": "Interface Bandwidth",
    "desc": "This metric indicates the maximum data transmission speed supported by the network interface, usually measured in KB per second. Understanding the maximum speed of the interface helps administrators optimize traffic and utilize network resources effectively."
  },
  "ifInErrors": {
    "name": "Incoming Errors Rate (per second)",
    "desc": "This metric calculates the average rate of incoming error packets over the past 5 minutes, measured in packets per second. Monitoring incoming errors allows administrators to detect potential issues, such as physical connection faults or configuration errors, in a timely manner."
  },
  "ifOutErrors": {
    "name": "Outgoing Errors Rate (per second)",
    "desc": "This metric calculates the average rate of outgoing error packets over the past 5 minutes, measured in packets per second. Monitoring outgoing errors is essential for identifying transmission issues and ensuring data integrity."
  },
  "ifInDiscards": {
    "name": "Incoming Discards Rate (per second)",
    "desc": "This metric represents the average rate of incoming discarded packets over the past 5 minutes, measured in packets per second. Packet discards may indicate network congestion or resource shortages, and monitoring this metric can help administrators optimize network performance."
  },
  "ifOutDiscards": {
    "name": "Outgoing Discards Rate (per second)",
    "desc": "This metric calculates the average rate of outgoing discarded packets over the past 5 minutes, measured in packets per second. Monitoring outgoing discards can help identify network transmission issues and misconfigurations."
  },
  "ifInUcastPkts": {
    "name": "Incoming Unicast Packets Rate (per second)",
    "desc": "This metric indicates the average rate of incoming unicast packets over the past 5 minutes, measured in packets per second. Monitoring unicast packets is crucial for assessing interface utilization and traffic load."
  },
  "ifOutUcastPkts": {
    "name": "Outgoing Unicast Packets Rate (per second)",
    "desc": "This metric calculates the average rate of outgoing unicast packets over the past 5 minutes, measured in packets per second. By monitoring the number of unicast packets, administrators can assess the transmission performance of the interface and the usage of traffic."
  },
  "ifInOctets": {
    "name": "Interface Incoming Traffic Rate (per second)",
    "desc": "This metric indicates the average rate of bytes received over the past 5 minutes, converted to megabytes (MB). Monitoring byte traffic helps evaluate the load on the interface and bandwidth usage."
  },
  "ifOutOctets": {
    "name": "Interface Outgoing Traffic Rate (per second)",
    "desc": "This metric calculates the average rate of bytes sent over the past 5 minutes, measured in megabytes (MB). Monitoring outgoing traffic is crucial for ensuring data transmission quality and optimizing network performance."
  },
  "iftotalInOctets": {
    "name": "Device Total Incoming Traffic (per second)",
    "desc": "This metric indicates the average rate of total bytes received by the entire device over the past 5 minutes, measured in megabytes per second (MB/s). By summing the incoming byte counts from multiple interfaces, this metric helps administrators obtain an overview of the device's incoming traffic, supporting overall traffic monitoring and capacity planning."
  },
  "iftotalOutOctets": {
    "name": "Device Total Outgoing Traffic (per second)",
    "desc": "This metric represents the average rate of total bytes sent by the entire device over the past 5 minutes, measured in megabytes per second (MB/s). By summing the outgoing byte counts from multiple interfaces, this metric allows administrators to comprehensively assess the sending performance of the entire system, enabling more effective traffic management and optimization."
  }
},
    "Storage": {
    "sysUpTime": {
    "name": "System Uptime",
    "desc": "This metric indicates the uptime of the device since the last restart, measured in days. By monitoring the uptime, network administrators can understand the stability and reliability of the device and identify potential reboot or failure issues."
  },
  "ifAdminStatus": {
    "name": "Interface Admin Status",
    "desc": "This metric indicates the administrative status of the network switch interface. It serves to indicate whether the interface is enabled (up) or disabled (down) by an administrator, along with other states such as testing or not present. This information is vital for network management and troubleshooting."
  },
  "ifOperStatus": {
    "name": "Interface Oper Status",
    "desc": "This metric reflects the actual operational status of the network switch interface, indicating whether the interface is operational. Unlike the administrative status, the operational status shows whether the interface can successfully receive and send traffic, which is crucial for monitoring network health."
  },
  "ifHighSpeed": {
    "name": "Interface Bandwidth",
    "desc": "This metric indicates the maximum data transmission speed supported by the network interface, usually measured in KB per second. Understanding the maximum speed of the interface helps administrators optimize traffic and utilize network resources effectively."
  },
  "ifInErrors": {
    "name": "Incoming Errors Rate (per second)",
    "desc": "This metric calculates the average rate of incoming error packets over the past 5 minutes, measured in packets per second. Monitoring incoming errors allows administrators to detect potential issues, such as physical connection faults or configuration errors, in a timely manner."
  },
  "ifOutErrors": {
    "name": "Outgoing Errors Rate (per second)",
    "desc": "This metric calculates the average rate of outgoing error packets over the past 5 minutes, measured in packets per second. Monitoring outgoing errors is essential for identifying transmission issues and ensuring data integrity."
  },
  "ifInDiscards": {
    "name": "Incoming Discards Rate (per second)",
    "desc": "This metric represents the average rate of incoming discarded packets over the past 5 minutes, measured in packets per second. Packet discards may indicate network congestion or resource shortages, and monitoring this metric can help administrators optimize network performance."
  },
  "ifOutDiscards": {
    "name": "Outgoing Discards Rate (per second)",
    "desc": "This metric calculates the average rate of outgoing discarded packets over the past 5 minutes, measured in packets per second. Monitoring outgoing discards can help identify network transmission issues and misconfigurations."
  },
  "ifInUcastPkts": {
    "name": "Incoming Unicast Packets Rate (per second)",
    "desc": "This metric indicates the average rate of incoming unicast packets over the past 5 minutes, measured in packets per second. Monitoring unicast packets is crucial for assessing interface utilization and traffic load."
  },
  "ifOutUcastPkts": {
    "name": "Outgoing Unicast Packets Rate (per second)",
    "desc": "This metric calculates the average rate of outgoing unicast packets over the past 5 minutes, measured in packets per second. By monitoring the number of unicast packets, administrators can assess the transmission performance of the interface and the usage of traffic."
  },
  "ifInOctets": {
    "name": "Interface Incoming Traffic Rate (per second)",
    "desc": "This metric indicates the average rate of bytes received over the past 5 minutes, converted to megabytes (MB). Monitoring byte traffic helps evaluate the load on the interface and bandwidth usage."
  },
  "ifOutOctets": {
    "name": "Interface Outgoing Traffic Rate (per second)",
    "desc": "This metric calculates the average rate of bytes sent over the past 5 minutes, measured in megabytes (MB). Monitoring outgoing traffic is crucial for ensuring data transmission quality and optimizing network performance."
  },
  "iftotalInOctets": {
    "name": "Device Total Incoming Traffic (per second)",
    "desc": "This metric indicates the average rate of total bytes received by the entire device over the past 5 minutes, measured in megabytes per second (MB/s). By summing the incoming byte counts from multiple interfaces, this metric helps administrators obtain an overview of the device's incoming traffic, supporting overall traffic monitoring and capacity planning."
  },
  "iftotalOutOctets": {
    "name": "Device Total Outgoing Traffic (per second)",
    "desc": "This metric represents the average rate of total bytes sent by the entire device over the past 5 minutes, measured in megabytes per second (MB/s). By summing the outgoing byte counts from multiple interfaces, this metric allows administrators to comprehensively assess the sending performance of the entire system, enabling more effective traffic management and optimization."
  },"ipmi_chassis_power_state": {
        "name": "Power State",
        "desc": "The power state indicator is used to monitor if the device is powered on. Its value can indicate whether the power is on or off. It is mainly used for remote management and monitoring of the device's power state."
    },
    "ipmi_power_watts": {
        "name": "Power",
        "desc": "The power indicator is measured in watts and reflects the current power consumption of the device. This indicator helps evaluate the device's energy efficiency and power consumption trends. It facilitates the implementation of energy-saving policies and resource optimization."
    },
    "ipmi_voltage_volts": {
        "name": "Voltage",
        "desc": "The voltage indicator measured in volts monitors the voltage levels of different power rails within the device. Stable voltage supply is crucial for the reliability of the device. This indicator helps quickly identify electrical issues, ensuring normal operation."
    },
    "ipmi_fan_speed_rpm": {
        "name": "Fan Speed",
        "desc": "The fan speed indicator is measured in rotations per minute (rpm) and monitors the fan's operation status within the device. Efficient fan operation is key to maintaining device temperature. It helps prevent overheating and ensures the device's stable long-term operation."
    },
    "ipmi_temperature_celsius": {
        "name": "Temperature",
        "desc": "The temperature indicator measured in degrees Celsius monitors the internal temperature of the device. Monitoring temperature prevents heat accumulation and avoids device overheating. It is crucial for maintaining system stability and longevity."
    }
    },
    "Hardware Server": {
 "sysUpTime": {
    "name": "System Uptime",
    "desc": "This metric indicates the uptime of the device since the last restart, measured in days. By monitoring the uptime, network administrators can understand the stability and reliability of the device and identify potential reboot or failure issues."
  },
  "ifAdminStatus": {
    "name": "Interface Admin Status",
    "desc": "This metric indicates the administrative status of the network switch interface. It serves to indicate whether the interface is enabled (up) or disabled (down) by an administrator, along with other states such as testing or not present. This information is vital for network management and troubleshooting."
  },
  "ifOperStatus": {
    "name": "Interface Oper Status",
    "desc": "This metric reflects the actual operational status of the network switch interface, indicating whether the interface is operational. Unlike the administrative status, the operational status shows whether the interface can successfully receive and send traffic, which is crucial for monitoring network health."
  },
  "ifHighSpeed": {
    "name": "Interface Bandwidth",
    "desc": "This metric indicates the maximum data transmission speed supported by the network interface, usually measured in KB per second. Understanding the maximum speed of the interface helps administrators optimize traffic and utilize network resources effectively."
  },
  "ifInErrors": {
    "name": "Incoming Errors Rate (per second)",
    "desc": "This metric calculates the average rate of incoming error packets over the past 5 minutes, measured in packets per second. Monitoring incoming errors allows administrators to detect potential issues, such as physical connection faults or configuration errors, in a timely manner."
  },
  "ifOutErrors": {
    "name": "Outgoing Errors Rate (per second)",
    "desc": "This metric calculates the average rate of outgoing error packets over the past 5 minutes, measured in packets per second. Monitoring outgoing errors is essential for identifying transmission issues and ensuring data integrity."
  },
  "ifInDiscards": {
    "name": "Incoming Discards Rate (per second)",
    "desc": "This metric represents the average rate of incoming discarded packets over the past 5 minutes, measured in packets per second. Packet discards may indicate network congestion or resource shortages, and monitoring this metric can help administrators optimize network performance."
  },
  "ifOutDiscards": {
    "name": "Outgoing Discards Rate (per second)",
    "desc": "This metric calculates the average rate of outgoing discarded packets over the past 5 minutes, measured in packets per second. Monitoring outgoing discards can help identify network transmission issues and misconfigurations."
  },
  "ifInUcastPkts": {
    "name": "Incoming Unicast Packets Rate (per second)",
    "desc": "This metric indicates the average rate of incoming unicast packets over the past 5 minutes, measured in packets per second. Monitoring unicast packets is crucial for assessing interface utilization and traffic load."
  },
  "ifOutUcastPkts": {
    "name": "Outgoing Unicast Packets Rate (per second)",
    "desc": "This metric calculates the average rate of outgoing unicast packets over the past 5 minutes, measured in packets per second. By monitoring the number of unicast packets, administrators can assess the transmission performance of the interface and the usage of traffic."
  },
  "ifInOctets": {
    "name": "Interface Incoming Traffic Rate (per second)",
    "desc": "This metric indicates the average rate of bytes received over the past 5 minutes, converted to megabytes (MB). Monitoring byte traffic helps evaluate the load on the interface and bandwidth usage."
  },
  "ifOutOctets": {
    "name": "Interface Outgoing Traffic Rate (per second)",
    "desc": "This metric calculates the average rate of bytes sent over the past 5 minutes, measured in megabytes (MB). Monitoring outgoing traffic is crucial for ensuring data transmission quality and optimizing network performance."
  },
  "iftotalInOctets": {
    "name": "Device Total Incoming Traffic (per second)",
    "desc": "This metric indicates the average rate of total bytes received by the entire device over the past 5 minutes, measured in megabytes per second (MB/s). By summing the incoming byte counts from multiple interfaces, this metric helps administrators obtain an overview of the device's incoming traffic, supporting overall traffic monitoring and capacity planning."
  },
  "iftotalOutOctets": {
    "name": "Device Total Outgoing Traffic (per second)",
    "desc": "This metric represents the average rate of total bytes sent by the entire device over the past 5 minutes, measured in megabytes per second (MB/s). By summing the outgoing byte counts from multiple interfaces, this metric allows administrators to comprehensively assess the sending performance of the entire system, enabling more effective traffic management and optimization."
  },"ipmi_chassis_power_state": {
        "name": "Power State",
        "desc": "The power state indicator is used to monitor if the device is powered on. Its value can indicate whether the power is on or off. It is mainly used for remote management and monitoring of the device's power state."
    },
    "ipmi_power_watts": {
        "name": "Power",
        "desc": "The power indicator is measured in watts and reflects the current power consumption of the device. This indicator helps evaluate the device's energy efficiency and power consumption trends. It facilitates the implementation of energy-saving policies and resource optimization."
    },
    "ipmi_voltage_volts": {
        "name": "Voltage",
        "desc": "The voltage indicator measured in volts monitors the voltage levels of different power rails within the device. Stable voltage supply is crucial for the reliability of the device. This indicator helps quickly identify electrical issues, ensuring normal operation."
    },
    "ipmi_fan_speed_rpm": {
        "name": "Fan Speed",
        "desc": "The fan speed indicator is measured in rotations per minute (rpm) and monitors the fan's operation status within the device. Efficient fan operation is key to maintaining device temperature. It helps prevent overheating and ensures the device's stable long-term operation."
    },
    "ipmi_temperature_celsius": {
        "name": "Temperature",
        "desc": "The temperature indicator measured in degrees Celsius monitors the internal temperature of the device. Monitoring temperature prevents heat accumulation and avoids device overheating. It is crucial for maintaining system stability and longevity."
    }
},
    "SNMP Trap": {                     
    },
    "Zookeeper": {
    "zookeeper_uptime": {
        "name": "Uptime",
        "desc": "This metric shows the uptime of the Zookeeper service, helping to monitor if the system is running normally."
    },
    "zookeeper_avg_latency": {
        "name": "Average Latency",
        "desc": "This metric represents the average latency of Zookeeper processing requests, used to monitor system response capability."
    },
    "zookeeper_read_write_ratio": {
        "name": "Read/Write Ratio",
        "desc": "This metric represents the ratio of commits to snapshots in Zookeeper, helping to assess the read/write load distribution."
    },
    "zookeeper_snapshot_to_commit_ratio": {
        "name": "Snapshot to Commit Ratio",
        "desc": "This metric represents the ratio of snapshot generation frequency to commit request frequency in Zookeeper, helping to monitor the relationship between persistence operations and transaction commits."
    },
    "zookeeper_connection_drop_count": {
        "name": "Connection Drop Count",
        "desc": "This metric represents the number of connection drops in Zookeeper, used to monitor connection stability."
    },
    "zookeeper_connection_rejected": {
        "name": "Connection Rejected",
        "desc": "This metric represents the number of rejected connections in Zookeeper, helping to monitor if connections are being correctly handled."
    },
    "zookeeper_znode_count": {
        "name": "Znode Count",
        "desc": "This metric represents the number of znodes in Zookeeper, helping to monitor changes in Zookeeper's data size."
    },
    "zookeeper_packets_received": {
        "name": "Packets Received",
        "desc": "This metric shows the number of packets received by Zookeeper, helping to monitor the network traffic."
    }
},
"Apache": {
    "apache_uptime": {
        "name": "Uptime",
        "desc": "This metric represents the uptime of the Apache server since it was started, used to monitor the server's health."
    },
    "apache_busy_workers": {
        "name": "Busy Workers",
        "desc": "This metric represents the number of busy worker processes in the Apache server, used to assess the server's load."
    },
    "apache_idle_workers": {
        "name": "Idle Workers",
        "desc": "This metric represents the number of idle worker processes in the Apache server, reflecting the server's resource utilization."
    },
    "apache_req_per_sec": {
        "name": "Requests per Second",
        "desc": "This metric represents the number of requests handled by Apache per second, used to monitor the server's request processing capability."
    },
    "apache_bytes_per_sec": {
        "name": "Bytes per Second",
        "desc": "This metric represents the number of bytes transferred by Apache per second, reflecting the network traffic."
    },
    "apache_total_accesses": {
        "name": "Total Accesses",
        "desc": "This metric represents the total number of accesses to the Apache server since startup, reflecting the overall request volume."
    },
    "apache_total_duration": {
        "name": "Total Duration",
        "desc": "This metric represents the total request processing duration since the Apache server started, used to assess the server's processing load."
    },
    "apache_cpu_system": {
        "name": "System CPU Usage",
        "desc": "This metric represents the CPU usage at the system level for Apache server."
    },
    "apache_cpu_user": {
        "name": "User CPU Usage",
        "desc": "This metric represents the CPU usage at the user process level for Apache server."
    },
    "apache_cpu_load": {
        "name": "CPU Load",
        "desc": "This metric represents the CPU load of the Apache server, reflecting the overall load of the system."
    },
    "apache_duration_per_req": {
        "name": "Duration per Request",
        "desc": "This metric represents the average duration per request, helping to evaluate the efficiency of request handling by the server."
    }
},
"ClickHouse": {
    "clickhouse_asynchronous_metrics_uptime": {
        "name": "Uptime",
        "desc": "Represents the uptime of the ClickHouse system."
    },
    "clickhouse_metrics_memory_tracking": {
        "name": "Memory Tracking",
        "desc": "Indicates the current memory usage by the ClickHouse process."
    },
    "clickhouse_asynchronous_metrics_os_memory_available": {
        "name": "Available Memory",
        "desc": "Indicates the total physical memory available for processes."
    },
    "clickhouse_asynchronous_metrics_disk_used_default": {
        "name": "Disk Usage (Default)",
        "desc": "Represents the amount of disk space currently used on the default disk."
    },
    "clickhouse_asynchronous_metrics_disk_total_default": {
        "name": "Total Disk Capacity (Default)",
        "desc": "Displays the total capacity of the default disk."
    },
    "clickhouse_events_query": {
        "name": "Query Rate",
        "desc": "Displays the number of queries processed per second by ClickHouse."
    },
    "clickhouse_events_inserted_rows": {
        "name": "Inserted Rows Rate",
        "desc": "Represents the rate of rows inserted during the last 5 minutes."
    },
    "clickhouse_events_select_query": {
        "name": "Select Query Rate",
        "desc": "Represents the rate of SELECT queries processed during the last 5 minutes."
    },
    "clickhouse_events_compressed_read_buffer_bytes": {
        "name": "Compressed Data Read Rate",
        "desc": "Displays the rate of compressed data read by ClickHouse system, indicating IO performance."
    },
    "clickhouse_metrics_parts_active": {
        "name": "Active Parts Count",
        "desc": "Displays the number of active parts in the MergeTree tables."
    },
    "clickhouse_metrics_parts_outdated": {
        "name": "Outdated Parts Count",
        "desc": "Shows the count of outdated parts in the MergeTree tables."
    },
    "clickhouse_asynchronous_metrics_load_average1": {
        "name": "Load Average (1m)",
        "desc": "Indicates the average system load over the last 1 minute."
    }
},
"RabbitMQ": {
    "rabbitmq_exchange_publish_in_rate": {
        "name": "Exchange Publish In Rate",
        "desc": "This metric shows the rate of messages published to the RabbitMQ exchange per second. It helps identify bottlenecks in message inflow."
    },
    "rabbitmq_exchange_publish_out_rate": {
        "name": "Exchange Publish Out Rate",
        "desc": "This metric shows the rate of messages published out of the RabbitMQ exchange per second. It helps identify issues in message outflow."
    },
    "rabbitmq_node_disk_free": {
        "name": "Disk Space Free",
        "desc": "This metric indicates the free disk space on the RabbitMQ node, in bytes. Low disk space can lead to performance degradation or failures."
    },
    "rabbitmq_node_fd_used": {
        "name": "File Descriptors Used",
        "desc": "This metric shows the number of file descriptors used by the RabbitMQ node. Excessive use may prevent the system from handling additional connections."
    },
    "rabbitmq_node_mem_used": {
        "name": "Memory Used",
        "desc": "This metric indicates the memory usage on the RabbitMQ node. High memory usage may lead to performance issues or node crashes."
    },
    "rabbitmq_node_run_queue": {
        "name": "Run Queue",
        "desc": "This metric shows the number of queues currently being handled by the RabbitMQ node. A high number may indicate system pressure and need for optimization."
    },
    "rabbitmq_node_uptime": {
        "name": "Uptime",
        "desc": "This metric indicates the uptime of the RabbitMQ node, in seconds. Nodes running for extended periods may require a restart to free resources and perform maintenance."
    },
    "rabbitmq_fd_usage_ratio": {
        "name": "File Descriptor Usage Ratio",
        "desc": "This metric shows the ratio of used file descriptors to the total number of file descriptors on the RabbitMQ node."
    },
    "rabbitmq_overview_messages_ready": {
        "name": "Messages Ready",
        "desc": "This metric indicates the number of messages ready for processing. A high number of ready messages may indicate consumer lag or slow processing speed."
    },
    "rabbitmq_overview_messages_unacked": {
        "name": "Unacknowledged Messages",
        "desc": "This metric represents the number of unacknowledged messages. A high number of unacknowledged messages may indicate slow consumer processing or backlog."
    },
    "rabbitmq_queue_message_backlog_ratio": {
        "name": "Queue Message Backlog Ratio",
        "desc": "This metric shows the ratio of ready messages to acked messages in the queue, helping to identify message backlog in the system."
    },
    "rabbitmq_unacked_message_ratio": {
        "name": "Unacked Message Ratio",
        "desc": "This metric shows the ratio of unacknowledged messages to the total messages in the queue, helping to identify slow consumers."
    }
},
"ActiveMQ": {
    "activemq_topic_consumer_count": {
        "name": "Consumer Count",
        "desc": "This metric represents the number of consumers per topic, used to monitor if consumers are evenly distributed."
    },
    "activemq_topic_dequeue_rate": {
        "name": "Dequeue Rate",
        "desc": "This metric shows the rate at which messages are consumed from the topic, indicating the consumption rate per second."
    },
    "activemq_topic_enqueue_rate": {
        "name": "Enqueue Rate",
        "desc": "This metric shows the rate at which messages are enqueued to the topic, indicating the incoming message rate per second."
    },
    "activemq_topic_size": {
        "name": "Topic Size",
        "desc": "This metric shows the number of unconsumed messages in the topic, helping to identify potential message backlog."
    }
},
"Nginx": {
    "nginx_requests": {
        "name": "Requests Rate",
        "desc": "Indicates the number of HTTP requests per second processed over the last 5 minutes, reflecting server load."
    },
    "nginx_accepts": {
        "name": "Accepted Connections Rate",
        "desc": "Indicates the number of client connections successfully established per second over the last 5 minutes, used to monitor connection activity."
    },
    "nginx_handled": {
        "name": "Handled Connections Rate",
        "desc": "Indicates the number of connected sessions successfully handled per second over the last 5 minutes, monitoring connection handling capacity."
    },
    "nginx_active": {
        "name": "Active Connections",
        "desc": "The number of active connections currently including those in reading, writing, and waiting states."
    },
    "nginx_waiting": {
        "name": "Waiting Connections",
        "desc": "The current number of idle connections waiting to be processed, reflecting the waiting connection queue."
    },
    "nginx_reading": {
        "name": "Reading Connections",
        "desc": "The number of connections currently reading client requests (header or body), used to monitor load in the reading stage."
    },
    "nginx_writing": {
        "name": "Writing Connections",
        "desc": "The number of connections currently writing response data to clients, used to monitor performance in the response stage."
    },
    "nginx_connect_rate": {
        "name": "Connection Handling Success Rate",
        "desc": "The percentage of handled connections out of total accepted connections over the last 5 minutes, used to analyze connection handling stability."
    },
    "nginx_request_handling_efficiency": {
        "name": "Requests per Handled Connection",
        "desc": "Indicates the average number of requests per handled connection, indirectly reflecting Nginx's efficiency and load level."
    }
},
"Tomcat": {
    "tomcat_connector_request_count": {
        "name": "Request Count",
        "desc": "This metric represents the total number of requests processed per second on average by the Tomcat connector in the past 5 minutes, and is used to monitor the request load."
    },
    "tomcat_connector_processing_time": {
        "name": "Processing Time",
        "desc": "This metric is used to measure the average per - second change in the time taken by the Tomcat connector to process requests over the past 5 minutes. It can reflect the efficiency of the server in processing requests."
    },
    "tomcat_connector_max_time": {
        "name": "Max Processing Time",
        "desc": "This metric indicates the maximum time taken to process a single request in Tomcat, reflecting the performance of the slowest request."
    },
    "tomcat_connector_bytes_received": {
        "name": "Bytes Received",
        "desc": "It represents the number of bytes of data received per second on average by the Tomcat connector in the past 5 minutes. It can be used to monitor the network traffic load of the Tomcat server."
    },
    "tomcat_connector_bytes_sent": {
        "name": "Bytes Sent",
        "desc": "This metric represents the average number of bytes sent per second by the Tomcat connector in the past 5 minutes, and it is used to monitor traffic and response load."
    },
    "tomcat_connector_current_thread_count": {
        "name": "Current Thread Count",
        "desc": "This metric shows the current number of threads used by the Tomcat connector, used to monitor concurrency capabilities."
    },
    "tomcat_connector_current_threads_busy": {
        "name": "Busy Thread Count",
        "desc": "This metric indicates the number of busy threads in the Tomcat connector, used to monitor concurrent processing."
    },
    "tomcat_connector_max_threads": {
        "name": "Max Thread Count",
        "desc": "This metric indicates the maximum number of threads for the Tomcat connector, used to monitor Tomcat's concurrency capabilities."
    },
    "tomcat_connector_error_count": {
        "name": "Error Count",
        "desc": "This metric represents the average number of errors per second that occur when the Tomcat connector processes requests in the past 5 minutes, and it is used to monitor the error rate."
    },
    "tomcat_jvm_memory_free": {
        "name": "JMX Free Memory",
        "desc": "This metric shows the free memory in Tomcat JVM, used to monitor memory usage."
    },
    "tomcat_jvm_memory_max": {
        "name": "JMX Max Memory",
        "desc": "This metric indicates the maximum memory available to Tomcat JVM, used to monitor memory limits."
    },
    "tomcat_jvm_memorypool_used": {
        "name": "JMX Used Memory Pool",
        "desc": "This metric shows the amount of memory used in the Tomcat JVM memory pool, used to monitor memory pool usage."
    }
},
"Consul": {
    "consul_health_checks_status": {
        "name": "Health Check Status",
        "desc": "This metric represents the status of the health check in Consul, where 0=passing, 1=warning, 2=critical."
    },
    "consul_health_checks_passing": {
        "name": "Passing Health Checks",
        "desc": "This metric indicates the number of passing health checks, used to monitor the health status of services."
    },
    "consul_health_checks_warning": {
        "name": "Warning Health Checks",
        "desc": "This metric shows the number of health checks in warning status, used to monitor potential issues."
    },
    "consul_health_checks_critical": {
        "name": "Critical Health Checks",
        "desc": "This metric shows the number of health checks in critical status, used to monitor critical failures."
    }
},
"ElasticSearch": {
    "elasticsearch_fs_total_available_in_bytes": {
        "name": "Total Available Disk Space",
        "desc": "Indicates total available disk space, converted to GB."
    },
    "elasticsearch_fs_total_free_in_bytes": {
        "name": "Total Free Disk Space",
        "desc": "Represents unallocated available disk space."
    },
    "elasticsearch_http_current_open": {
        "name": "Current Open HTTP Connections",
        "desc": "Tracks the number of currently open HTTP connections."
    },
    "elasticsearch_http_total_opened": {
        "name": "New HTTP Connections in 5m",
        "desc": "Number of new HTTP connections opened in 5 minutes."
    },
    "elasticsearch_fs_io_stats_total_write_kilobytes": {
        "name": "Disk Write Throughput",
        "desc": "Monitors disk write throughput (MB/s)."
    },
    "elasticsearch_fs_io_stats_total_read_kilobytes": {
        "name": "Disk Read Throughput",
        "desc": "Tracks disk read throughput (MB/s)."
    },
    "elasticsearch_indices_docs_count": {
        "name": "Total Document Count",
        "desc": "Total number of document entries in Elasticsearch."
    },
    "elasticsearch_indices_docs_deleted": {
        "name": "Total Deleted Document Count",
        "desc": "Total number of deleted documents in Elasticsearch."
    },
    "elasticsearch_indices_query_cache_cache_count": {
        "name": "Query Cache Count",
        "desc": "Tracks the number of query cache entries."
    },
    "elasticsearch_breakers_parent_tripped": {
        "name": "Parent Circuit Breaker Tripped",
        "desc": "Parent circuit breaker trips in 5 minutes."
    },
    "elasticsearch_breakers_fielddata_tripped": {
        "name": "Field Data Circuit Breaker Tripped",
        "desc": "Field data circuit breaker trips in 5 minutes."
    }
},
"MongoDB": {
    "mongodb_active_reads": {
        "name": "Active Reads",
        "desc": "The number of active read operations currently being executed, used to monitor database load."
    },
    "mongodb_active_writes": {
        "name": "Active Writes",
        "desc": "The number of active write operations currently being executed, used to monitor write pressure."
    },
    "mongodb_commands": {
        "name": "Commands Per Second",
        "desc": "The number of database operations per second, reflecting database load."
    },
    "mongodb_connections_current": {
        "name": "Current Connections",
        "desc": "The number of active client connections to the database."
    },
    "mongodb_latency_commands": {
        "name": "Command Latency",
        "desc": "The average latency of database commands, used to assess database performance."
    },
    "mongodb_resident_megabytes": {
        "name": "Resident Memory Usage",
        "desc": "The amount of physical memory used by MongoDB, reflecting resource usage."
    },
    "mongodb_net_in_bytes": {
        "name": "Incoming Traffic",
        "desc": "The amount of incoming data received per second, used to monitor network traffic."
    },
    "mongodb_net_out_bytes": {
        "name": "Outgoing Traffic",
        "desc": "The amount of outgoing data sent per second, used to monitor network traffic."
    },
    "mongodb_total_docs_scanned": {
        "name": "Documents Scanned",
        "desc": "The number of documents scanned per second during queries, used to assess query performance."
    }
},
"Mysql": {
    "mysql_aborted_clients": {
        "name": "Aborted Clients",
        "desc": "This metric represents the number of connections aborted due to client errors. Monitoring this metric can help identify connection reliability issues."
    },
    "mysql_aborted_connects": {
        "name": "Aborted Connects",
        "desc": "This metric represents the number of connection attempts aborted due to connection issues. High values may indicate configuration issues or server overload."
    },
    "mysql_access_denied_errors": {
        "name": "Access Denied Errors",
        "desc": "This metric represents the number of access denials due to insufficient privileges or authentication failures. Monitoring this metric helps in identifying and resolving permission issues."
    },
    "mysql_aria_pagecache_blocks_unused": {
        "name": "Aria Pagecache Blocks Unused",
        "desc": "This metric indicates the number of unused page cache blocks in the Aria storage engine. Monitoring this metric helps optimize cache allocation."
    },
    "mysql_aria_pagecache_blocks_used": {
        "name": "Aria Pagecache Blocks Used",
        "desc": "This metric indicates the number of used page cache blocks in the Aria storage engine. Monitoring this metric helps assess the effective utilization of the cache."
    },
    "mysql_bytes_received": {
        "name": "Bytes Received",
        "desc": "This metric indicates the number of bytes received by the MySQL server. Monitoring this metric helps understand the network traffic load."
    },
    "mysql_bytes_sent": {
        "name": "Bytes Sent",
        "desc": "This metric indicates the number of bytes sent by the MySQL server. Monitoring this metric helps understand the network traffic load."
    },
    "mysql_com_select": {
        "name": "Select Commands",
        "desc": "This metric represents the number of Select queries executed. Monitoring this metric helps understand the frequency of read operations and system load."
    },
    "mysql_com_insert": {
        "name": "Insert Commands",
        "desc": "This metric represents the number of Insert commands executed. Monitoring this metric helps understand the frequency of write operations and system load."
    },
    "mysql_com_update": {
        "name": "Update Commands",
        "desc": "This metric represents the number of Update commands executed. Monitoring this metric helps understand the frequency of update operations and system load."
    },
    "mysql_com_delete": {
        "name": "Delete Commands",
        "desc": "This metric represents the number of Delete commands executed. Monitoring this metric helps understand the frequency of delete operations and system load."
    },
    "mysql_connections_total": {
        "name": "Total Connections Created",
        "desc": "This metric represents the total number of connections created since the server started. Monitoring the total connections helps understand connection patterns and load."
    }
},
"Postgres": {
    "postgresql_active_time": {
        "name": "Active Time",
        "desc": "This metric indicates the total active time of PostgreSQL, reflecting the duration of database activity."
    },
    "postgresql_blk_read_time": {
        "name": "Block Read Time",
        "desc": "This metric indicates the total time spent by PostgreSQL reading blocks from the disk."
    },
    "postgresql_blk_write_time": {
        "name": "Block Write Time",
        "desc": "This metric indicates the total time spent by PostgreSQL writing blocks to the disk."
    },
    "postgresql_blks_hit": {
        "name": "Block Cache Hits",
        "desc": "This metric indicates the number of times PostgreSQL queries hit the cache, reflecting cache efficiency."
    },
    "postgresql_blks_read": {
        "name": "Block Reads",
        "desc": "This metric indicates the number of blocks read by PostgreSQL from the disk."
    },
    "postgresql_buffers_alloc": {
        "name": "Buffers Allocated",
        "desc": "This metric indicates the number of buffer blocks allocated by PostgreSQL to monitor memory usage."
    },
    "postgresql_buffers_checkpoint": {
        "name": "Checkpoint Buffers",
        "desc": "This metric indicates the number of buffer blocks written during checkpoints in PostgreSQL."
    },
    "postgresql_xact_commit": {
        "name": "Transaction Commits",
        "desc": "This metric indicates the total number of transactions committed by PostgreSQL, reflecting the workload of the database."
    },
    "postgresql_xact_rollback": {
        "name": "Transaction Rollbacks",
        "desc": "This metric indicates the total number of transaction rollbacks performed by PostgreSQL."
    },
    "postgresql_sessions": {
        "name": "Total Sessions",
        "desc": "This metric indicates the total number of sessions created by PostgreSQL, reflecting database connection activity."
    },
    "postgresql_sessions_abandoned": {
        "name": "Abandoned Sessions",
        "desc": "This metric indicates the count of sessions abandoned due to prolonged inactivity."
    },
    "postgresql_sessions_killed": {
        "name": "Killed Sessions",
        "desc": "This metric indicates the total number of sessions terminated by an administrator or system."
    }
},
"Redis": {
    "redis_used_memory": {
        "name": "Used Memory",
        "desc": "This metric indicates the memory used by the Redis allocator."
    },
    "redis_mem_fragmentation_ratio": {
        "name": "Memory Fragmentation",
        "desc": "This metric indicates the memory fragmentation ratio of the Redis allocator."
    },
    "redis_instantaneous_ops_per_sec": {
        "name": "Operations per Second",
        "desc": "This metric indicates the number of commands processed per second by Redis."
    },
    "redis_keyspace_hits": {
        "name": "Keyspace Hits",
        "desc": "This metric indicates the number of cache hits."
    },
    "redis_keyspace_misses": {
        "name": "Keyspace Misses",
        "desc": "This metric indicates the number of cache misses."
    },
    "redis_clients": {
        "name": "Connected Clients",
        "desc": "This metric indicates the number of active client connections."
    },
    "redis_used_cpu_sys": {
        "name": "CPU Used (System)",
        "desc": "This metric indicates the total system CPU time consumed by the Redis process."
    },
    "redis_evicted_keys": {
        "name": "Evicted Keys",
        "desc": "This metric indicates the number of keys evicted due to memory constraints."
    },
    "redis_connected_slaves": {
        "name": "Connected Slaves",
        "desc": "This metric indicates the number of replicas connected to the master node."
    },
    "redis_rdb_last_save_time_elapsed": {
        "name": "Last Save Elapsed Time",
        "desc": "This metric indicates the time elapsed since the last successful RDB save operation."
    },
    "redis_rejected_connections": {
        "name": "Rejected Connections",
        "desc": "This metric indicates the number of connections rejected due to server overload or policy limits."
    }
},
"Docker": {
    "docker_n_containers": {
        "name": "Containers Count",
        "desc": "This metric indicates the total number of containers on the Docker host, reflecting the host's load."
    },
    "docker_n_containers_running": {
        "name": "Running Containers",
        "desc": "This metric indicates the number of containers running on the Docker host, reflecting the host's load."
    },
    "docker_n_containers_stopped": {
        "name": "Stopped Containers",
        "desc": "This metric indicates the number of stopped containers on the Docker host, helping to understand container status."
    },
},
"Docker Container": {
    "docker_container_status": {
        "name": "Status",
        "desc": "This metric indicates the state of the container, where 0 means the container is normal."
    },
    "docker_container_status_restart_count": {
        "name": "Restart Count",
        "desc": "This metric indicates the number of container restarts, helping monitor if the container is frequently restarting."
    },
    "docker_container_cpu_usage_percent": {
        "name": "CPU Usage Percent",
        "desc": "This metric indicates the percentage of CPU usage of the container, monitoring the CPU load of the container."
    },
    "docker_container_mem_usage_percent": {
        "name": "Memory Usage Percent",
        "desc": "This metric indicates the percentage of memory usage of the container, monitoring the memory load of the container."
    },
    "docker_container_blkio_io_service_bytes_recursive_total": {
        "name": "Total Block I/O Bytes",
        "desc": "This metric indicates the total block I/O bytes of the container, reflecting the disk I/O load of the container."
    },
    "docker_container_net_rx_bytes": {
        "name": "Received Network Bytes",
        "desc": "This metric indicates the number of network bytes received by the container, in MiB, used to monitor the network traffic of the container."
    },
    "docker_container_net_tx_bytes": {
        "name": "Transmitted Network Bytes",
        "desc": "This metric indicates the number of network bytes sent by the container, in MiB, used to monitor the network traffic of the container."
    }
},
"vCenter": {
        "vmware_esxi_count": {
            "name": "Number of ESXi",
            "desc": "This metric counts the number of ESXi hosts in the VMware environment, helping administrators understand the current physical host resources."
        },
        "vmware_datastore_count": {
            "name": "Number of Datastores",
            "desc": "This metric counts the number of datastores in the VMware environment, facilitating the monitoring of storage resource allocation and usage."
        },
        "vmware_vm_count": {
            "name": "Number of VM",
            "desc": "This metric counts the number of virtual machines in the VMware environment, used to assess the utilization of virtualization resources."
        }
    },
"ESXI": {
   "esxi_cpu_usage_average_gauge": {
        "name": "CPU usage",
        "desc": "It represents the CPU utilization rate of the system or application program, measured in percent (%), which is a key indicator for measuring CPU load and performance."
    },
    "esxi_cpu_usagemhz_average_gauge": {
        "name": "CPU utilization rate",
        "desc": "It represents the CPU usage, measured in megahertz (MHz), and reflects the actual operating frequency of the CPU."
    },
    "esxi_mem_usage_average_gauge": {
        "name": "Memory utilization rate",
        "desc": "The memory utilization rate indicates the usage situation of the memory, measured in percent (%), and is used to evaluate the memory load of the system or application program."
    },
    "esxi_mem_consumed_average_gauge": {
        "name": "Active memory",
        "desc": "The active memory represents the actual amount of memory used by the system or application program, measured in megabytes (MB), and is a key indicator of memory consumption."
    },
    "esxi_disk_read_average_gauge": {
        "name": "Disk read rate",
        "desc": "The disk read rate represents the amount of data read from the disk per second, measured in megabytes per second (MB/s), and is an important indicator for measuring the disk read performance."
    },
    "esxi_disk_write_average_gauge": {
        "name": "Disk write rate",
        "desc": "The disk write rate represents the amount of data written to the disk per second, measured in megabytes per second (MB/s), and is an important indicator for measuring the disk write performance."
    },
    "esxi_disk_numberRead_summation_gauge": {
        "name": "Disk read I/O",
        "desc": "Represents the number of disk read operations completed per second, measured in IOPS (operations per second), which is an important metric for measuring the frequency of disk read requests. Higher values indicate more frequent read requests."
    },
    "esxi_disk_numberWrite_summation_gauge": {
        "name": "Disk write I/O",
        "desc": "Represents the number of disk write operations completed per second, measured in IOPS (operations per second), which is an important metric for measuring the frequency of disk write requests. Higher values indicate more frequent write requests."
    },
    "esxi_net_bytesRx_average_gauge": {
        "name": "Network receive rate",
        "desc": "The network receive rate represents the amount of data received per second, measured in kilobytes per second (KB/s), and is an important criterion for measuring network traffic."
    },
    "esxi_net_bytesTx_average_gauge": {
        "name": "Network transmit rate",
        "desc": "The network transmit rate represents the amount of data sent out per second, measured in kilobytes per second (KB/s), and is an important criterion for measuring network traffic."
    }
},
"DataStorage": {
    "data_storage_disk_used_average": {
        "name": "Disk utilization rate",
        "desc": "The disk utilization rate indicates the usage situation of disk space and is an indicator for measuring the utilization rate of disk storage."
    },
    "data_storage_disk_free_average": {
        "name": "Disk remaining capacity",
        "desc": "The remaining disk space represents the amount of unused space in the disk and is a key indicator for evaluating the disk capacity."
    },
    "data_storage_base.store_accessible": {
        "name": "Storage connection status",
        "desc": "The storage connection status indicates the connectability of the storage device and is an indicator for evaluating the health status of the storage system."
    }
},
"VM": {
     "vm_cpu_usage_average_gauge": {
        "name": "CPU utilization rate",
        "desc": "It represents the CPU utilization rate of the system within a specific time period, usually expressed as a percentage. This indicator helps to understand the CPU load situation, so as to carry out performance optimization and capacity planning."
    },
    "vm_cpu_usagemhz_average_gauge": {
        "name": "CPU usage",
        "desc": "It represents the CPU usage of the system within a specific time period, usually measured in MHz. This indicator is used to measure the actual operating frequency of the CPU and helps to analyze the consumption of CPU resources."
    },
    "vm_mem_usage_average_gauge": {
        "name": "Memory utilization rate",
        "desc": "It represents the memory utilization rate of the system within a specific time period, usually expressed as a percentage. This indicator helps to understand the memory load situation, which is helpful for optimizing memory usage and conducting capacity planning."
    },
    "vm_mem_consumed_average_gauge": {
        "name": "Active memory",
        "desc": "It represents the active memory of the system within a specific time period, usually measured in MB or GB. This indicator is used to measure the actual memory resources consumed by the system and helps to analyze the memory usage situation."
    },
    "vm_disk_io_usage_gauge": {
        "name": "Disk I/O Usage",
        "desc": "Indicates the I/O usage of the VM's disk, i.e., the busyness of the disk over a period of time. Higher values indicate higher disk load."
    },
    "vm_disk_read_average_gauge": {
        "name": "Disk Read Throughput",
        "desc": "Represents the average read throughput of the VM's disk over a period of time. Higher values indicate better read performance."
    },
    "vm_disk_used_average_gauge": {
        "name": "Disk Usage",
        "desc": "Represents the average usage of the VM's disk, i.e., the proportion of disk space used. Higher values indicate tighter disk space."
    },
    "vm_disk_numberRead_summation_gauge": {
        "name": "Disk read I/O",
        "desc": "Represents the number of disk read operations completed per second, an important metric for measuring the frequency of disk read requests. Higher values indicate more frequent read requests."
    },
    "vm_disk_numberWrite_summation_gauge": {
        "name": "Disk write I/O",
        "desc": "Represents the number of disk write operations completed per second, an important metric for measuring the frequency of disk write requests."
    },
    "vm_disk_write_average_gauge": {
        "name": "Disk Write Throughput",
        "desc": "Represents the average write throughput of the VM's disk over a period of time. Higher values indicate better write performance."
    },
    "vm_net_bytesRx_average_gauge": {
        "name": "Network receive rate",
        "desc": "It represents the network receive rate of the system within a specific time period, usually measured in MB/s or GB/s. This indicator is used to measure the network receiving performance and helps to analyze network traffic and bandwidth usage."
    },
    "vm_net_bytesTx_average_gauge": {
        "name": "Network transmit rate",
        "desc": "It represents the network transmit rate of the system within a specific time period, usually measured in MB/s or GB/s. This indicator is used to measure the network transmitting performance and helps to analyze network traffic and bandwidth usage."
    },
    "vm_power_state_gauge": {
        "name": "Power state",
        "desc": "It indicates the current power status of a virtual machine (VM). This metric helps administrators monitor whether a VM is powered on or off. This metric is essential for tracking VM availability, optimizing resource allocation, and automating workflows in VMware environments."
    }
}
}

LANGUAGE_DICT = {
    "MONITOR_OBJECT_TYPE": MONITOR_OBJECT_TYPE,
    "MONITOR_OBJECT": MONITOR_OBJECT,
    "MONITOR_OBJECT_PLUGIN": MONITOR_OBJECT_PLUGIN,
    "MONITOR_OBJECT_METRIC_GROUP": MONITOR_OBJECT_METRIC_GROUP,
    "MONITOR_OBJECT_METRIC": MONITOR_OBJECT_METRIC,
}
