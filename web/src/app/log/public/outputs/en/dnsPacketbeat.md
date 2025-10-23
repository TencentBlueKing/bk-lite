### Packetbeat DNS Introduction

- &zwnj;**Basic Functions**&zwnj;
  - DNS protocol parsing

  - Query and response correlation

  - Structured output

  - Data output and analysis


- &zwnj;**Key Features**&zwnj;
  - Non-intrusive monitoring

  - Real-time capability

  - Suitable for security scenarios

  - Performance analysis capabilities

  - Configurable filtering and sampling

  - Integration with observability ecosystem

### Packetbeat DNS Output Fields


|Group|Field Name|Description|Type|
|--------|------|------|--------|
|Built-in Fields|collect_type|Collection type|-|
|Built-in Fields|collector|Collector|-|
|Built-in Fields|instance_id|Instance ID|-|
|dns.flags|dns.flags.authoritative|Specifies whether the response server is the authoritative server for the domain|boolean|
|dns.flags|dns.flags.recursion_available|Specifies whether the name server supports recursive queries|boolean|
|dns.flags|dns.flags.recursion_desired|Specifies whether the client requires the server to perform recursive queries (recursion optional)|boolean|
|dns.flags|dns.flags.authentic_data|Specifies that the recursive server considers the response to be authentic|boolean|
|dns.flags|dns.flags.checking_disabled|Specifies whether the client has disabled signature verification for queries by the server|boolean|
|dns.flags|dns.flags.truncated_response|Specifies that the response only returns the first 512 bytes|boolean|
|dns.question|dns.question.etld_plus_one|Effective top-level domain plus one label, e.g., "amazon.co.uk"|example|
|dns.answers|dns.answers_count|Number of resource records contained in the dns.answers field|long|
|dns.authorities|dns.authorities|Array containing dictionaries for each authority section|object|
|dns.authorities|dns.authorities_count|Number of resource records contained in the dns.authorities field|long|
|dns.authorities|dns.authorities.name|Domain name corresponding to this resource record|example|
|dns.authorities|dns.authorities.type|Type of this resource record|example|
|dns.authorities|dns.authorities.class|Class of this resource record|example|
|dns.additionals|dns.additionals|Array containing dictionaries for each additional section|object|
|dns.additionals|dns.additionals_count|Number of resource records contained in the dns.additionals field|long|
|dns.additionals|dns.additionals.name|Domain name corresponding to this resource record|example|
|dns.additionals|dns.additionals.type|Type of this resource record|example|
|dns.additionals|dns.additionals.class|Class of this resource record|example|
|dns.additionals|dns.additionals.ttl|Time interval (seconds) this resource record can be cached, 0 means no caching|long|
|dns.additionals|dns.additionals.data|Data describing this resource, specific meaning depends on type and class| |
|dns.opt|dns.opt.version|EDNS version|example|
|dns.opt|dns.opt.do|Whether DNSSEC is used|boolean|
|dns.opt|dns.opt.ext_rcode|Extended response code field|example|
|dns.opt|dns.opt.udp_size|UDP payload size of the requester (bytes)|long|