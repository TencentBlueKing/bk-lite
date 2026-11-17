"""BK-Lite 随代码发版的 Grok 模式库。定义只用 Rust regex 与 Python re 的公共子集。"""

from dataclasses import dataclass

from apps.log.utils.locale_text import log_text

_MONTH = "January|February|March|April|May|June|July|August|September|October|November|December|" "Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec"
_DAY = "Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday|Mon|Tue|Wed|Thu|Fri|Sat|Sun"
_LOGLEVEL = (
    r"\b(?:EMERGENCY|ALERT|CRITICAL|WARNING|ERROR|NOTICE|INFO|INF|DEBUG|DBG|TRACE|TRC|FATAL|SEVERE|WARN|WRN|CRIT|ERR|"
    r"Emergency|Alert|Critical|Warning|Error|Notice|Info|Inf|Debug|Dbg|Trace|Trc|Fatal|Severe|Warn|Wrn|Crit|Err|"
    r"emergency|alert|critical|warning|error|notice|info|inf|debug|dbg|trace|trc|fatal|severe|warn|wrn|crit|err)\b"
)
_IPV4 = r"\b(?:(?:25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9][0-9]|[0-9])\.){3}" r"(?:25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9][0-9]|[0-9])\b"
_IPV6 = (
    r"(?:(?:[0-9A-Fa-f]{1,4}:){7}[0-9A-Fa-f]{1,4}"
    r"|(?:[0-9A-Fa-f]{1,4}:){1,2}(?::[0-9A-Fa-f]{1,4}){1,5}"
    r"|(?:[0-9A-Fa-f]{1,4}:){1,3}(?::[0-9A-Fa-f]{1,4}){1,4}"
    r"|(?:[0-9A-Fa-f]{1,4}:){1,4}(?::[0-9A-Fa-f]{1,4}){1,3}"
    r"|(?:[0-9A-Fa-f]{1,4}:){1,5}(?::[0-9A-Fa-f]{1,4}){1,2}"
    r"|(?:[0-9A-Fa-f]{1,4}:){1,6}:[0-9A-Fa-f]{1,4}"
    r"|[0-9A-Fa-f]{1,4}:(?:(?::[0-9A-Fa-f]{1,4}){1,6})"
    r"|:(?:(?::[0-9A-Fa-f]{1,4}){1,7}|:)"
    r"|(?:[0-9A-Fa-f]{1,4}:){1,7}:)"
)
_HOSTNAME = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*"
_COMMON_EXAMPLE = '127.0.0.1 - frank [10/Oct/2000:13:55:36 -0700] "GET /apache_pb.gif HTTP/1.0" 200 2326'
_COMBINED_EXAMPLE = _COMMON_EXAMPLE + ' "http://www.example.com/start.html" "Mozilla/4.08 [en] (Win98; I ;Nav)"'
_COMMON_OUTPUTS = (
    "source.address",
    "user.name",
    "log_time",
    "http.request.method",
    "url.original",
    "http.version",
    "http.response.status_code",
    "http.response.body.bytes",
)
_COMMON_VALUES = (
    ("source.address", "127.0.0.1"),
    ("user.name", "frank"),
    ("log_time", "10/Oct/2000:13:55:36 -0700"),
    ("http.request.method", "GET"),
    ("url.original", "/apache_pb.gif"),
    ("http.version", "1.0"),
    ("http.response.status_code", "200"),
    ("http.response.body.bytes", "2326"),
)
_SYSLOG_OUTPUTS = ("log_time", "host.hostname", "process.name", "process.pid")
_SYSLOG_VALUES = (
    ("log_time", "Nov 16 15:04:05"),
    ("host.hostname", "web-01"),
    ("process.name", "sshd"),
    ("process.pid", "1234"),
)


@dataclass(frozen=True)
class GrokPattern:
    name: str
    category: str
    definition: str
    example: str
    composite: bool = False
    outputs: tuple[str, ...] = ()
    example_outputs: tuple[tuple[str, str], ...] = ()


GROK_CATEGORIES = ("common", "number", "network", "path", "datetime", "level", "composite")

GROK_PATTERNS: tuple[GrokPattern, ...] = (
    GrokPattern("WORD", "common", r"[A-Za-z0-9_]+", "GET"),
    GrokPattern("NOTSPACE", "common", r"\S+", "a/b"),
    GrokPattern("SPACE", "common", r"\s*", " "),
    GrokPattern("DATA", "common", r".*?", "sample text"),
    GrokPattern("GREEDYDATA", "common", r".*", "sample text"),
    GrokPattern("QUOTEDSTRING", "common", r"""(?:"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')""", '"hello"'),
    GrokPattern(
        "UUID", "common", r"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}", "550e8400-e29b-41d4-a716-446655440000"
    ),
    GrokPattern("USERNAME", "common", r"[A-Za-z0-9._-]+", "alice"),
    GrokPattern("EMAILADDRESS", "common", r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "alice@example.com"),
    GrokPattern("INT", "number", r"[+-]?[0-9]+", "-12"),
    GrokPattern("POSINT", "number", r"[1-9][0-9]*", "8080"),
    GrokPattern("NONNEGINT", "number", r"[0-9]+", "0"),
    GrokPattern("NUMBER", "number", r"[+-]?(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+)", "3.14"),
    GrokPattern("BASE16NUM", "number", r"[+-]?(?:0[xX])?[0-9A-Fa-f]+", "0x1F"),
    GrokPattern("IPV4", "network", _IPV4, "192.168.1.10"),
    GrokPattern("IPV6", "network", _IPV6, "2001:db8::1"),
    GrokPattern("IP", "network", r"%{IPV6}|%{IPV4}", "192.168.1.10"),
    GrokPattern("HOSTNAME", "network", _HOSTNAME, "web-01"),
    GrokPattern("IPORHOST", "network", r"%{IP}|%{HOSTNAME}", "web-01"),
    GrokPattern("HOSTPORT", "network", r"%{IPORHOST}:%{POSINT}", "web-01:514"),
    GrokPattern("MAC", "network", r"(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}|(?:[0-9A-Fa-f]{4}\.){2}[0-9A-Fa-f]{4}", "00:1A:2B:3C:4D:5E"),
    GrokPattern("UNIXPATH", "path", r"/(?:[A-Za-z0-9._~@%+-]+/)*[A-Za-z0-9._~@%+-]*", "/var/log/messages"),
    GrokPattern("WINPATH", "path", r'[A-Za-z]:\\(?:[^\\/:*?"<>|\r\n]+\\)*[^\\/:*?"<>|\r\n]*', r"C:\Windows\System32"),
    GrokPattern("PATH", "path", r"%{WINPATH}|%{UNIXPATH}", "/var/log/messages"),
    GrokPattern("URIPROTO", "path", r"[A-Za-z][A-Za-z0-9+.-]*", "https"),
    GrokPattern("URIHOST", "path", r"%{IPORHOST}(?::%{POSINT})?", "example.com:8080"),
    GrokPattern("URIPATH", "path", r"/(?:[A-Za-z0-9._~!$&'()*+,;=:@%/-])*", "/search"),
    GrokPattern("URIPARAM", "path", r"\?(?:[A-Za-z0-9._~!$&'()*+,;=:@%/-])*", "?q=1"),
    GrokPattern("URIPATHPARAM", "path", r"%{URIPATH}(?:%{URIPARAM})?", "/search?q=1"),
    GrokPattern("URI", "path", r"%{URIPROTO}://%{URIHOST}(?:%{URIPATHPARAM})?", "https://example.com/search?q=1"),
    GrokPattern("YEAR", "datetime", r"[0-9]{4}", "2026"),
    GrokPattern("MONTH", "datetime", _MONTH, "Oct"),
    GrokPattern("MONTHNUM", "datetime", r"(?:1[0-2]|0[1-9]|[1-9])", "11"),
    GrokPattern("MONTHDAY", "datetime", r"(?:3[01]|[12][0-9]|0[1-9]|[1-9])", "16"),
    GrokPattern("DAY", "datetime", _DAY, "Mon"),
    GrokPattern("HOUR", "datetime", r"(?:2[0-3]|[01][0-9]|[0-9])", "15"),
    GrokPattern("MINUTE", "datetime", r"[0-5][0-9]", "04"),
    GrokPattern("SECOND", "datetime", r"(?:[0-5][0-9]|60)", "05"),
    GrokPattern("TIME", "datetime", r"%{HOUR}:%{MINUTE}(?::%{SECOND})?", "15:04:05"),
    GrokPattern("DATE", "datetime", r"%{YEAR}-%{MONTHNUM}-%{MONTHDAY}", "2026-11-16"),
    GrokPattern("DATESTAMP", "datetime", r"%{DATE}[- ]%{TIME}", "2026-11-16 15:04:05"),
    GrokPattern(
        "TIMESTAMP_ISO8601",
        "datetime",
        r"%{YEAR}-%{MONTHNUM}-%{MONTHDAY}[T ]%{HOUR}:%{MINUTE}(?::%{SECOND}(?:\.[0-9]{1,9})?)?(?:Z|[+-]%{HOUR}:?%{MINUTE})?",
        "2026-11-16T15:04:05.123+08:00",
    ),
    GrokPattern("HTTPDATE", "datetime", r"%{MONTHDAY}/%{MONTH}/%{YEAR}:%{TIME} %{INT}", "10/Oct/2000:13:55:36 -0700"),
    GrokPattern("SYSLOGTIMESTAMP", "datetime", r"%{MONTH} +%{MONTHDAY} %{TIME}", "Nov 16 15:04:05"),
    GrokPattern("LOGLEVEL", "level", _LOGLEVEL, "ERROR"),
    GrokPattern("PROG", "level", r"[A-Za-z0-9][A-Za-z0-9_./-]*", "sshd"),
    GrokPattern("SYSLOGHOST", "level", r"%{IPORHOST}", "web-01"),
    GrokPattern(
        "COMMONAPACHELOG",
        "composite",
        r"%{IPORHOST:source.address} %{NOTSPACE} %{NOTSPACE:user.name} \[%{HTTPDATE:log_time}\] "
        r'"%{WORD:http.request.method} %{NOTSPACE:url.original} HTTP/%{NUMBER:http.version}" '
        r"%{NUMBER:http.response.status_code} (?:%{NUMBER:http.response.body.bytes}|-)",
        _COMMON_EXAMPLE,
        True,
        _COMMON_OUTPUTS,
        _COMMON_VALUES,
    ),
    GrokPattern(
        "COMBINEDAPACHELOG",
        "composite",
        r'%{COMMONAPACHELOG} "%{DATA:http.request.referrer}" "%{DATA:user_agent.original}"',
        _COMBINED_EXAMPLE,
        True,
        _COMMON_OUTPUTS + ("http.request.referrer", "user_agent.original"),
        _COMMON_VALUES
        + (("http.request.referrer", "http://www.example.com/start.html"), ("user_agent.original", "Mozilla/4.08 [en] (Win98; I ;Nav)")),
    ),
    GrokPattern(
        "SYSLOGBASE",
        "composite",
        r"%{SYSLOGTIMESTAMP:log_time} %{SYSLOGHOST:host.hostname} %{PROG:process.name}(?:\[%{POSINT:process.pid}\])?:",
        "Nov 16 15:04:05 web-01 sshd[1234]: Failed password for root",
        True,
        _SYSLOG_OUTPUTS,
        _SYSLOG_VALUES,
    ),
)

GROK_PATTERNS_BY_NAME = {pattern.name: pattern for pattern in GROK_PATTERNS}


def grok_catalog(locale) -> list[dict]:
    return [
        {
            "name": pattern.name,
            "category": pattern.category,
            "description": log_text(locale, f"grok_pattern.{pattern.name}.description"),
            "example": pattern.example,
            "composite": pattern.composite,
            "outputs": list(pattern.outputs),
        }
        for pattern in GROK_PATTERNS
    ]
