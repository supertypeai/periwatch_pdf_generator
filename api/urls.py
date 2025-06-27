from django.urls import path
from .views import PDFReportAPIView

urlpatterns = [
    path('generate-pdf/', PDFReportAPIView.as_view(), name='generate-pdf'),
]
