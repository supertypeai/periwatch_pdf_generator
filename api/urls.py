from django.urls import path
from .views import PDFReportAPIView,SupertypeTokenView
from rest_framework.authtoken.views import obtain_auth_token

urlpatterns = [
    path('generate-pdf/', PDFReportAPIView.as_view(), name='generate-pdf'),
    path('token/', SupertypeTokenView.as_view(), name='api_token_auth'),
]
