# apps/telemetry.py
"""
Initialisation OpenTelemetry pour Restaurant Manager Pro.
Appelé depuis backend/wsgi.py et backend/asgi.py AVANT le chargement Django.
"""
import os
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.django import DjangoInstrumentor
from opentelemetry.instrumentation.psycopg import PsycopgInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor


def setup_tracing():
    """
    Configure le TracerProvider et instrumente Django, PostgreSQL, Redis, Requests.
    Ne fait rien si OTEL_EXPORTER_OTLP_ENDPOINT n'est pas défini.
    """
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint:
        return  # Pas de tracing si l'endpoint n'est pas configuré

    resource = Resource.create({
        SERVICE_NAME: os.getenv("OTEL_SERVICE_NAME", "restaurant-backend"),
        SERVICE_VERSION: "2.0.0",
        "deployment.environment": "development" if os.getenv("DEBUG", "False").lower() == "true" else "production",
    })

    provider = TracerProvider(resource=resource)

    # Exporter OTLP HTTP → Tempo
    otlp_exporter = OTLPSpanExporter(
        endpoint=f"{endpoint.rstrip('/')}/v1/traces",
    )
    provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
    trace.set_tracer_provider(provider)

    # Instrumentation automatique
    DjangoInstrumentor().instrument()
    PsycopgInstrumentor().instrument()
    RedisInstrumentor().instrument()
    RequestsInstrumentor().instrument()