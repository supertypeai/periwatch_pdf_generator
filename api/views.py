from rest_framework.views import APIView
from django.http import HttpResponse, JsonResponse
from .pdf_generator import generate_pdf  # Adjust import path accordingly
from .tasks import pdf_task_manager
import jwt
import datetime
import uuid
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings
import os
import logging
from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger(__name__)

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
        timeout_seconds = int(request.GET.get('timeout', 30))  # Default 30 seconds
        
        if company:
            company = company.strip()
            company = ' '.join([w.capitalize() for w in company.split()])

        # Generate unique task ID
        task_id = str(uuid.uuid4())
        
        try:
            # Generate PDF with timeout
            pdf_buffer, status_result = pdf_task_manager.generate_pdf_with_timeout(
                task_id=task_id,
                title_text=title_text,
                email_text=email_text,
                ticker=ticker,
                company=company,
                timeout_seconds=timeout_seconds,
                recipient_email=email_text
            )
            
            if status_result == 'completed':
                # PDF completed within timeout
                response = HttpResponse(pdf_buffer, content_type='application/pdf')
                response['Content-Disposition'] = f'attachment; filename="{title_text}.pdf"'
                response['X-PDF-Status'] = 'completed'
                response['X-Task-ID'] = task_id
                return response
                
            elif status_result == 'partial':
                # PDF partially generated, continuing in background
                if pdf_buffer is not None:
                    response = HttpResponse(pdf_buffer, content_type='application/pdf')
                    response['Content-Disposition'] = f'attachment; filename="{title_text}_partial.pdf"'
                    response['X-PDF-Status'] = 'partial'
                    response['X-Task-ID'] = task_id
                    response['X-Message'] = f'Complete version will be sent to {email_text}'
                    return response
                else:
                    # Partial PDF generation failed, but background process continues
                    return Response({
                        'detail': 'PDF generation in progress',
                        'message': f'Report generation is taking longer than expected. Complete version will be sent to {email_text}',
                        'task_id': task_id,
                        'status': 'processing_background'
                    }, status=status.HTTP_202_ACCEPTED)
                
            else:  # failed
                return Response({
                    'detail': 'PDF generation failed',
                    'task_id': task_id,
                    'error': pdf_task_manager.get_task_status(task_id).get('error', 'Unknown error')
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                
        except Exception as e:
            logger.error(f"PDF generation error: {str(e)}")
            return Response({
                'detail': 'PDF generation failed',
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class PDFTaskStatusView(APIView):
    """Endpoint to check PDF generation task status"""
    
    def get(self, request, task_id):
        auth_header = request.headers.get('Authorization', '')
        token = auth_header.replace('Bearer ', '')
        
        if token != os.environ.get('PASSWORD'):
            return Response({'detail': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)
        
        task_status = pdf_task_manager.get_task_status(task_id)
        
        if task_status['status'] == 'not_found':
            return Response({'detail': 'Task not found'}, status=status.HTTP_404_NOT_FOUND)
        
        return Response({
            'task_id': task_id,
            'status': task_status['status'],
            'start_time': task_status.get('start_time'),
            'error': task_status.get('error'),
            'recipient_email': task_status.get('recipient_email')
        })


class PDFCleanupView(APIView):
    """Endpoint to cleanup old tasks (admin only)"""
    
    def post(self, request):
        auth_header = request.headers.get('Authorization', '')
        token = auth_header.replace('Bearer ', '')
        
        if token != os.environ.get('PASSWORD'):
            return Response({'detail': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)
        
        hours = int(request.data.get('hours', 24))
        pdf_task_manager.cleanup_old_tasks(hours)
        
        return Response({'message': f'Cleaned up tasks older than {hours} hours'})
