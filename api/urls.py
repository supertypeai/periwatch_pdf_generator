from django.urls import path
from .views import PDFReportAPIView, SupertypeTokenView, PDFTaskStatusView, PDFCleanupView
from rest_framework.authtoken.views import obtain_auth_token

urlpatterns = [
    path('generate-pdf/', PDFReportAPIView.as_view(), name='generate-pdf'),
    path('token/', SupertypeTokenView.as_view(), name='api_token_auth'),
    path('task-status/<str:task_id>/', PDFTaskStatusView.as_view(), name='pdf-task-status'),
    path('cleanup-tasks/', PDFCleanupView.as_view(), name='pdf-cleanup-tasks'),
]
