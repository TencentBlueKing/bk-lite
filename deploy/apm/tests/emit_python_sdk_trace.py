"""使用标准 OpenTelemetry Python SDK 发出一条可验证 Trace。"""

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor


provider = TracerProvider()
provider.add_span_processor(SimpleSpanProcessor(OTLPSpanExporter()))
trace.set_tracer_provider(provider)

with trace.get_tracer("bk-lite-apm-product-contract").start_as_current_span("sdk-contract-request") as span:
    span.set_attribute("http.request.method", "GET")
    span.set_attribute("http.route", "/sdk-contract")
    trace_id = f"{span.get_span_context().trace_id:032x}"

provider.shutdown()
print(trace_id)
