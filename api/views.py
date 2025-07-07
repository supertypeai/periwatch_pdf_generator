from rest_framework.views import APIView
from django.http import HttpResponse
from .pdf_generator import generate_pdf  # Adjust import path accordingly
import jwt
import datetime
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings
import os
from dotenv import load_dotenv
load_dotenv()

class SupertypeTokenView(APIView):
    def post(self, request):
        email = request.data.get('email')
        password = request.data.get('password')

        if not email or not password:
            return Response({'detail': 'Email and password required'}, status=status.HTTP_400_BAD_REQUEST)

        if not email.endswith('@supertype.ai'):
            return Response({'detail': 'Unauthorized email domain'}, status=status.HTTP_401_UNAUTHORIZED)

        if password != os.environ.get('PASSWORD'):
            return Response({'detail': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)

        payload = {
            'email': email,
            'exp': datetime.datetime.utcnow() + datetime.timedelta(seconds=settings.JWT_EXP_DELTA_SECONDS)
        }
        token = jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)

        return Response({'token': token})


class PDFReportAPIView(APIView):
    def get(self, request):
        auth_header = request.headers.get('Authorization', '')
        token = auth_header.replace('Bearer ', '')
        
        if token !=  os.environ.get('PASSWORD'):
            return Response({'detail': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)

        title_text = request.GET.get('title', 'Periwatch Report')
        email_text = request.GET.get('email', 'human@supertype.ai')
        ticker = request.GET.get('ticker', '')
        company = request.GET.get('company', '')
        if company:
            company = company.strip()

        pdf_buffer = generate_pdf(title_text, email_text, ticker, company)

        response = HttpResponse(pdf_buffer, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{title_text}.pdf"'
        return response
