### Packetbeat HTTP Introduction

- &zwnj;**Basic Functions**&zwnj;
  - HTTP protocol parsing

  - Real-time traffic monitoring

  - Traffic statistics and visualization

  - Integration with Elasticsearch/Logstash

- &zwnj;**Key Features**&zwnj;
  - Lightweight

  - Non-intrusive monitoring

  - Rich field information

  - Performance analysis capabilities

  - Can work with other modules

  - Highly configurable


### Packetbeat HTTP Output Fields


|Group|Field Name|Description|Type|
|---|---|---|---|
|Built-in Fields|collect_type|Collection type|-|
|Built-in Fields|collector|Collector|-|
|Built-in Fields|instance_id|Instance ID|-|
|http.request|http.request.headers|HTTP request header field mapping, configurable headers to capture; same-name headers separated by commas|object|
|http.request|http.request.params|HTTP request parameters|alias (url.query)|
|http.response|http.response.status_phrase|HTTP status phrase, e.g., "Not Found"|example|
|http.response|http.response.headers|HTTP response header field mapping, configurable headers to capture; same-name headers separated by commas|object|
|http.response|http.response.code|HTTP response status code|alias (http.response.status_code)|
|http.response|http.response.phrase|HTTP response status phrase|alias (http.response.status_phrase)|
