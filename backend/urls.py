# backend/urls.py
from django.contrib import admin
from django.urls import path, re_path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve as media_serve
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

    # ── API - URLs inchangées (Phase 1→3) ─────────────────────────────────
    # IMPORTANT : ces préfixes ne changent pas pour ne pas casser l'existant.
    # La migration vers /api/ se fera en une seule fois quand le frontend
    # sera prêt à suivre.
    path('api/company/', include('apps.company.urls')),
    path('api/accounts/', include('apps.accounts.urls')),
    path('api/menu/', include('apps.menu.urls')),
    path('api/commandes/', include('apps.commandes.urls')),
    path('api/restaurant/',  include('apps.restaurant.api_urls')),
    path('api/paiements/', include('apps.paiements.urls')),
    path('api/dashboard/', include('apps.dashboard.urls')),

    # ── Vitrine publique ──────────────────────────────────────────────────
    path('api/public/', include('apps.public.api_urls')),

    # ── Prometheus ────────────────────────────────────────────────────────
    path('', include('django_prometheus.urls')),
]

# Servir les médias uploadés (photos des plats) quand ils ne sont pas sur S3.
# En dev : helper static(). En prod (DEBUG=False) : static() est un no-op, donc on
# branche django.views.static.serve sur le volume media monté (mnt Dokploy /app/media).
# Acceptable à l'échelle de l'app ; pour un fort trafic, préférer S3 (USE_S3=True) ou
# faire servir /media/ directement par le reverse-proxy.
if not settings.USE_S3:
    if settings.DEBUG:
        urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    else:
        urlpatterns += [
            re_path(
                r'^media/(?P<path>.*)$',
                media_serve,
                {'document_root': settings.MEDIA_ROOT},
            ),
        ]