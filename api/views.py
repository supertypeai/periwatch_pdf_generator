from rest_framework.views import APIView
from django.http import HttpResponse
from .pdf_generator import generate_pdf  # Adjust import path accordingly

class PDFReportAPIView(APIView):
    def get(self, request):
        title_text = request.GET.get('title', 'Periwatch Report')
        email_text = request.GET.get('email', 'human@supertype.ai')

        pdf_buffer = generate_pdf(title_text, email_text)

        response = HttpResponse(pdf_buffer, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{title_text}.pdf"'
        return response
