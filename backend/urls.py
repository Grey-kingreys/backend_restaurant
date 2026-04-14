# backend/urls.py
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)

urlpatterns = [
    path('admin/', admin.site.urls),

    # ── Swagger / OpenAPI ─────────────────────────────────────────────────
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),

    # ── API — URLs inchangées (Phase 1→3) ─────────────────────────────────
    # IMPORTANT : ces préfixes ne changent pas pour ne pas casser l'existant.
    # La migration vers /api/v1/ se fera en une seule fois quand le frontend
    # sera prêt à suivre.
    path('api/company/', include('apps.company.urls')),
    path('api/accounts/', include('apps.accounts.urls')),

    # ── Phase 4 — Menu & Plats ────────────────────────────────────────────
    # Nouvelles routes seulement.
    path('api/menu/', include('apps.menu.urls')),

    # ── Prometheus ────────────────────────────────────────────────────────
    path('', include('django_prometheus.urls')),
]

# Servir les media en développement (USE_S3=False uniquement)
if settings.DEBUG and not settings.USE_S3:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)