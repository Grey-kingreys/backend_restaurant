from django.urls import path
from .views import DashboardView

app_name = 'dashboard'

urlpatterns = [
    path('stats/', DashboardView.as_view(), name='stats'),
]
