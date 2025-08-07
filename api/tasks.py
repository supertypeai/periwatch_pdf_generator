import os
import time
import threading
from datetime import datetime
from django.core.mail import send_mail, EmailMessage
from django.conf import settings
from .pdf_generator import generate_pdf
import logging
from io import BytesIO
import fitz  # PyMuPDF for compression
from PIL import Image
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Attachment, FileContent, FileName, FileType, Disposition
import base64

logger = logging.getLogger(__name__)

class PDFGenerationTask:
    def __init__(self):
        self.active_tasks = {}
    
    def compress_pdf_buffer(self, pdf_buffer, image_quality=90):
        """
        Compress PDF buffer using PyMuPDF with image quality optimization.
        Returns compressed PDF buffer.
        """
        try:
            logger.info(f"Starting PDF compression with quality {image_quality}%")
            
            # Read original PDF from buffer
            pdf_buffer.seek(0)
            original_data = pdf_buffer.read()
            original_size = len(original_data)
            
            # Open PDF with PyMuPDF
            doc = fitz.open(stream=original_data, filetype="pdf")
            
            # Create new document for compressed version
            new_doc = fitz.open()
            
            total_pages = len(doc)
            logger.info(f"Compressing {total_pages} pages...")
            
            for page_num in range(total_pages):
                page = doc[page_num]
                
                # Create high-quality pixmap
                zoom = 1.9  # Good balance between quality and size
                mat = fitz.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=mat)
                
                # Convert to PIL Image for compression
                img_data = pix.tobytes("png")
                pil_image = Image.open(BytesIO(img_data))
                
                # Handle different image modes
                if pil_image.mode in ('RGBA', 'LA', 'P'):
                    rgb_image = Image.new('RGB', pil_image.size, (255, 255, 255))
                    if pil_image.mode == 'RGBA':
                        rgb_image.paste(pil_image, mask=pil_image.split()[-1])
                    else:
                        rgb_image.paste(pil_image)
                    pil_image = rgb_image
                
                # Compress image
                img_buffer = BytesIO()
                pil_image.save(img_buffer,
                            format='JPEG',
                            quality=image_quality,
                            optimize=True,
                            progressive=True)
                img_buffer.seek(0)
                
                # Create new page and insert compressed image
                new_page = new_doc.new_page(width=page.rect.width, height=page.rect.height)
                new_page.insert_image(page.rect, stream=img_buffer.read())
            
            # Save compressed PDF to buffer
            compressed_buffer = BytesIO()
            compressed_data = new_doc.tobytes(
                garbage=4,      # Remove unused objects
                deflate=True,   # Compress streams
                clean=True      # Clean up structure
            )
            compressed_buffer.write(compressed_data)
            compressed_buffer.seek(0)
            
            # Clean up
            new_doc.close()
            doc.close()
            
            # Log compression results
            compressed_size = len(compressed_data)
            compression_ratio = ((original_size - compressed_size) / original_size) * 100
            
            logger.info(f"PDF compression completed:")
            logger.info(f"  Original size: {original_size:,} bytes ({original_size/1024/1024:.2f} MB)")
            logger.info(f"  Compressed size: {compressed_size:,} bytes ({compressed_size/1024/1024:.2f} MB)")
            logger.info(f"  Space saved: {original_size - compressed_size:,} bytes ({(original_size - compressed_size)/1024/1024:.2f} MB)")
            logger.info(f"  Compression ratio: {compression_ratio:.1f}%")
            
            return compressed_buffer
            
        except Exception as e:
            logger.error(f"PDF compression failed: {str(e)}")
            logger.warning("Returning original PDF without compression")
            pdf_buffer.seek(0)
            return pdf_buffer
        
    def generate_pdf_with_timeout(self, task_id, title_text, email_text, ticker, company, 
                                  timeout_seconds=30, recipient_email=None):
        """
        Generate PDF with timeout. Returns partial PDF if timeout, continues in background.
        """
        start_time = time.time()
        
        self.active_tasks[task_id] = {
            'status': 'running',
            'start_time': start_time,
            'title_text': title_text,
            'email_text': email_text,
            'ticker': ticker,
            'company': company,
            'recipient_email': recipient_email or email_text
        }
        
        # Container for the result
        result_container = {'pdf_buffer': None, 'completed': False, 'error': None}
        
        def generate_pdf_worker():
            try:
                logger.info(f"Starting PDF generation for task {task_id}")
                pdf_buffer = generate_pdf(title_text, email_text, ticker, company)
                result_container['pdf_buffer'] = pdf_buffer
                result_container['completed'] = True
                logger.info(f"PDF generation completed for task {task_id}")
            except Exception as e:
                result_container['error'] = str(e)
                logger.error(f"PDF generation failed for task {task_id}: {str(e)}")
        
        # Start PDF generation in a separate thread
        worker_thread = threading.Thread(target=generate_pdf_worker)
        worker_thread.daemon = True
        worker_thread.start()
        
        # Wait for timeout or completion
        elapsed_time = 0
        while elapsed_time < timeout_seconds and not result_container['completed'] and not result_container['error']:
            time.sleep(0.5)
            elapsed_time = time.time() - start_time
        
        if result_container['completed']:
            # PDF completed within timeout - compress before returning
            self.active_tasks[task_id]['status'] = 'completed'
            logger.info(f"Task {task_id} completed within timeout, compressing PDF...")
            
            # Compress the completed PDF
            compressed_pdf = self.compress_pdf_buffer(result_container['pdf_buffer'], image_quality=90)
            
            logger.info(f"Task {task_id} compression completed")
            return compressed_pdf, 'completed'
            
        elif result_container['error']:
            # PDF generation failed
            self.active_tasks[task_id]['status'] = 'failed'
            self.active_tasks[task_id]['error'] = result_container['error']
            logger.error(f"Task {task_id} failed: {result_container['error']}")
            return None, 'failed'
        else:
            # Timeout reached, return partial PDF and continue in background
            self.active_tasks[task_id]['status'] = 'processing_background'
            logger.info(f"Task {task_id} timed out, generating partial PDF and continuing in background")
            
            # Generate partial PDF (cover page only)
            partial_pdf = self._generate_partial_pdf(title_text, email_text, ticker, company)
            
            # Compress partial PDF before returning
            if partial_pdf:
                logger.info(f"Compressing partial PDF for task {task_id}")
                partial_pdf = self.compress_pdf_buffer(partial_pdf, image_quality=90)
            
            # Continue full generation in background
            self._continue_in_background(task_id, worker_thread, result_container)
            return partial_pdf, 'partial'
    
    def _generate_partial_pdf(self, title_text, email_text, ticker, company):
        """Generate a partial PDF with cover page and processing info"""
        try:
            from reportlab.pdfgen import canvas
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont
            from reportlab.lib import colors
            from io import BytesIO
            import os
            from .pdf_generator import ASSET_PATH, cover_text_generator
            
            logger.info(f"Generating partial PDF for {title_text}")
            
            buffer = BytesIO()
            width, height = 595, 842
            
            try:
                pdfmetrics.registerFont(TTFont('Inter', os.path.join(ASSET_PATH, "font/Inter-Regular.ttf")))
                pdfmetrics.registerFont(TTFont('Inter-Bold', os.path.join(ASSET_PATH, "font/Inter-Bold.ttf")))
            except Exception as font_error:
                logger.warning(f"Font registration failed: {font_error}. Using default fonts.")
            
            pdf = canvas.Canvas(buffer, pagesize=(width, height))
            
            # Cover Page
            try:
                cover_image_path = os.path.join(ASSET_PATH, 'cover.png')
                if os.path.exists(cover_image_path):
                    pdf.drawImage(cover_image_path, 0, 0, width, height)
                    
                    if company != '':
                        cover_text_generator(pdf, height, ticker, email_text, title_text, company)
                    else:
                        cover_text_generator(pdf, height, ticker, email_text, title_text, '')
                else:
                    logger.warning(f"Cover image not found: {cover_image_path}")
                    pdf.setFillColor(colors.HexColor("#8B6636"))
                    pdf.rect(0, 0, width, height, fill=1)
                    pdf.setFont('Inter-Bold', 40)
                    pdf.setFillColor(colors.white)
                    pdf.drawString(64, height-200, "Intelligence Brief")
                    
            except Exception as cover_error:
                logger.error(f"Cover page generation failed: {cover_error}")
                pdf.setFillColor(colors.white)
                pdf.rect(0, 0, width, height, fill=1)
                pdf.setFont('Inter-Bold', 40)
                pdf.setFillColor(colors.black)  
                title_width = pdf.stringWidth(title_text, 'Inter-Bold', 40)
                pdf.drawString((width - title_width) / 2, height/2, title_text)
            pdf.showPage()
            
            # Processing page
            pdf.drawImage(os.path.join(ASSET_PATH,'company_blank.png'), 0, 0, width, height)
            try:
                title_font = 'Inter-Bold'
                body_font = 'Inter'
                pdf.setFont(title_font, 32)
            except:
                title_font = 'Inter-Bold'
                body_font = 'Inter'
            
            pdf.setFont(title_font, 36)
            pdf.setFillColor(colors.HexColor("#C8A882"))
            text1 = "Processing Your Report"
            text1_width = pdf.stringWidth(text1, title_font, 36)
            pdf.drawString((width - text1_width) / 2, height/2 + 157, text1)
            
            # Dots
            pdf.setFillColor(colors.HexColor("#C8A882"))
            dot_y = height/2 + 117
            dot_spacing = 15
            start_x = (width - (2 * dot_spacing)) / 2
            for i in range(3):
                pdf.circle(start_x + (i * dot_spacing), dot_y, 4, fill=1)

            pdf.setFont(body_font, 18)
            pdf.setFillColor(colors.HexColor("#E5E5E5"))
            text2 = "Please wait while we generate your complete report"
            text2_width = pdf.stringWidth(text2, body_font, 18)
            pdf.drawString((width - text2_width) / 2, height/2 + 55, text2)
            
            # Info box
            box_width = 450
            box_height = 60
            box_x = (width - box_width) / 2
            box_y = height/2 - 40
            pdf.setFillColor(colors.HexColor("#2A2A2A"))
            pdf.setStrokeColor(colors.HexColor("#C8A882"))
            pdf.setLineWidth(2)
            pdf.roundRect(box_x, box_y, box_width, box_height, 10, fill=1, stroke=1)
            
            # Info text
            pdf.setFont(body_font, 14)
            pdf.setFillColor(colors.white)
            text3 = "The complete version will be sent to your email shortly."
            text3_width = pdf.stringWidth(text3, body_font, 14)
            pdf.drawString((width - text3_width) / 2, height/2 - 13, text3)
            
            # Email info
            pdf.setFont(title_font, 16)
            pdf.setFillColor(colors.HexColor("#C8A882"))
            text4 = f"📧 {email_text}"
            text4_width = pdf.stringWidth(text4, title_font, 16)
            pdf.drawString((width - text4_width) / 2, height/2 - 80, text4)
            
            # Progress indicator
            progress_width = 350
            progress_height = 10
            progress_x = (width - progress_width) / 2
            progress_y = height/2 - 120
            pdf.setFillColor(colors.HexColor("#404040")) # bar background
            pdf.roundRect(progress_x, progress_y, progress_width, progress_height, 5, fill=1)
            pdf.setFillColor(colors.HexColor("#C8A882")) # bar fill
            pdf.roundRect(progress_x, progress_y, progress_width * 0.3, progress_height, 5, fill=1)
            
            # Progress text
            pdf.setFont(body_font, 12)
            pdf.setFillColor(colors.HexColor("#CCCCCC"))
            progress_text = "Generating complete analysis..."
            progress_text_width = pdf.stringWidth(progress_text, body_font, 12)
            pdf.drawString((width - progress_text_width) / 2, progress_y - 25, progress_text)
            
            # Additional info
            pdf.setFont(body_font, 11)
            pdf.setFillColor(colors.HexColor("#B0B0B0"))
            text5 = "This partial PDF contains the cover page. The complete analysis is being prepared."
            text5_width = pdf.stringWidth(text5, body_font, 11)
            pdf.drawString((width - text5_width) / 2, height/2 - 170, text5)
            
            # Footer
            footer_y = 100
            pdf.setStrokeColor(colors.HexColor("#8B6636")) # Footer separator line
            pdf.setLineWidth(1)
            pdf.line(80, footer_y, width-80, footer_y)
            pdf.setFont(body_font, 12) # Footer text
            pdf.setFillColor(colors.HexColor("#C8A882"))
            text6 = "Powered by Periwatch"
            text6_width = pdf.stringWidth(text6, body_font, 12)
            pdf.drawString((width - text6_width) / 2, 60, text6)
            
            # Add timestamp
            pdf.setFont(body_font, 10)
            pdf.setFillColor(colors.HexColor("#999999"))
            timestamp = f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            timestamp_width = pdf.stringWidth(timestamp, body_font, 10)
            pdf.drawString((width - timestamp_width) / 2, 40, timestamp)
            pdf.showPage()
            
            # Page 1
            pdf.drawImage(os.path.join(ASSET_PATH,'goliath.png'), 0, 0, width, height)
            pdf.showPage()

            # Page 2
            pdf.drawImage(os.path.join(ASSET_PATH,'vincent.png'), 0, 0, width, height)
            pdf.showPage()

            # CTA
            pdf.drawImage(os.path.join(ASSET_PATH,'cta.png'), 0, 0, width, height)
            pdf.showPage()

            pdf.save()
            buffer.seek(0)
            
            logger.info(f"Partial PDF generated successfully for {title_text}")
            return buffer
            
        except Exception as e:
            logger.error(f"Failed to generate partial PDF: {str(e)}")
            logger.exception("Detailed error for partial PDF generation:")
            
            try:
                from reportlab.pdfgen import canvas
                from io import BytesIO
                
                buffer = BytesIO()
                pdf = canvas.Canvas(buffer, pagesize=(595, 842))
                
                # Simple fallback page
                pdf.setFont('Inter-Bold', 24)
                pdf.drawString(100, 600, "Processing Report...")
                pdf.setFont('Inter', 14)
                pdf.drawString(100, 550, f"Title: {title_text}")
                pdf.drawString(100, 530, f"Email: {email_text}")
                pdf.drawString(100, 500, "Complete version will be sent via email.")
                
                pdf.save()
                buffer.seek(0)
                logger.info("Fallback partial PDF created")
                return buffer
                
            except Exception as fallback_error:
                logger.error(f"Even fallback PDF generation failed: {fallback_error}")
                return None
    
    def _continue_in_background(self, task_id, worker_thread, result_container):
        """Continue PDF generation in background and send email when complete"""
        def background_worker():
            try:
                # Wait for the original worker thread to complete
                worker_thread.join()
                
                if result_container['completed'] and result_container['pdf_buffer']:
                    # Compress full PDF before sending email
                    task_info = self.active_tasks.get(task_id, {})
                    logger.info(f"Compressing full PDF for task {task_id} before email")
                    
                    compressed_pdf = self.compress_pdf_buffer(result_container['pdf_buffer'], image_quality=90)
                    
                    # Send email with compressed complete PDF
                    self._send_pdf_email(
                        task_info.get('recipient_email'),
                        task_info.get('title_text', 'Periwatch Report'),
                        compressed_pdf
                    )
                    self.active_tasks[task_id]['status'] = 'completed_and_sent'
                    logger.info(f"Task {task_id} completed and email sent")
                elif result_container['error']:
                    self.active_tasks[task_id]['status'] = 'failed'
                    self.active_tasks[task_id]['error'] = result_container['error']
                    logger.error(f"Background task {task_id} failed: {result_container['error']}")
                    
            except Exception as e:
                logger.error(f"Background worker failed for task {task_id}: {str(e)}")
                self.active_tasks[task_id]['status'] = 'failed'
                self.active_tasks[task_id]['error'] = str(e)
        
        background_thread = threading.Thread(target=background_worker)
        background_thread.daemon = True
        background_thread.start()
    
    def _send_pdf_email(self, recipient_email, title, pdf_buffer):
        """Send PDF via email using SendGrid API with detailed error handling"""
        try:
            logger.info(f"Attempting to send PDF email to {recipient_email} using SendGrid")
            if not hasattr(settings, 'SENDGRID_API_KEY') or not settings.SENDGRID_API_KEY:
                raise ValueError("SENDGRID_API_KEY not found in settings. Please set it in your environment variables.")
            subject = f"Your {title} Report is Ready"
            pdf_buffer.seek(0)
            pdf_data = pdf_buffer.read()
            pdf_base64 = base64.b64encode(pdf_data).decode('utf-8')
            html_message = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Periwatch Report Ready</title>
    <style>
        @import url('data:font/woff2;base64,/* Inter font will be embedded */');
        
        /* Responsive Email Styles */
        @media screen and (max-width: 640px) {{
            .email-container {{
                width: 100% !important;
                max-width: none !important;
                margin: 0 !important;
                border-radius: 0 !important;
            }}
            .email-header {{
                padding: 25px 15px !important;
            }}
            .email-header h1 {{
                font-size: 24px !important;
            }}
            .email-header p {{
                font-size: 14px !important;
            }}
            .email-content {{
                padding: 30px 15px !important;
            }}
            .email-content p {{
                font-size: 15px !important;
            }}
            .report-card {{
                padding: 20px 15px !important;
                margin: 20px 0 !important;
            }}
            .report-card h3 {{
                font-size: 18px !important;
            }}
            .report-table td {{
                padding: 8px 0 !important;
                font-size: 14px !important;
                display: block !important;
                width: 100% !important;
            }}
            .report-table .label {{
                font-weight: 600 !important;
                margin-bottom: 5px !important;
            }}
            .report-table .value {{
                margin-bottom: 15px !important;
                padding-left: 0 !important;
            }}
            .status-badge {{
                font-size: 12px !important;
                padding: 3px 10px !important;
            }}
            .email-footer {{
                padding: 25px 15px !important;
            }}
            .email-footer h3 {{
                font-size: 18px !important;
            }}
            .email-footer p {{
                font-size: 11px !important;
            }}
            .cta-button {{
                padding: 15px 20px !important;
                font-size: 14px !important;
            }}
        }}
        
        @media screen and (max-width: 480px) {{
            .email-header h1 {{
                font-size: 22px !important;
            }}
            .email-content p {{
                font-size: 14px !important;
            }}
            .report-card h3 {{
                font-size: 16px !important;
            }}
        }}
        
        /* Font fallbacks */
        .inter-font {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
        }}
        
        .inter-bold {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            font-weight: 700;
        }}
    </style>
</head>
<body style="margin: 0; padding: 0; font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif; background-color: #f4f4f4; -webkit-text-size-adjust: 100%; -ms-text-size-adjust: 100%; min-height: 100vh;">
    <table role="presentation" style="width: 100%; margin: 0; padding: 0; background-color: #f4f4f4; min-height: 100vh;" cellpadding="0" cellspacing="0" border="0">
        <tr>
            <td align="center" style="padding: 0;">
                <div class="email-container inter-font" style="max-width: 1000px; width: 100%; margin: 0 auto; background-color: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 8px 24px rgba(0,0,0,0.12);">
                    
                    <!-- Header -->
                    <div class="email-header" style="background: linear-gradient(135deg, #C8A882 0%, #8B6636 100%); padding: 30px 25px; text-align: center;">
                        <h1 class="inter-bold" style="color: #ffffff; margin: 0; font-size: 28px; font-weight: 700; text-shadow: 0 2px 4px rgba(0,0,0,0.3); line-height: 1.2;">
                            Report Ready!
                        </h1>
                        <p class="inter-font" style="color: #ffffff; margin: 12px 0 0 0; font-size: 16px; opacity: 0.95; line-height: 1.4; font-weight: 400;">
                            Your intelligence brief has been generated
                        </p>
                    </div>
                    
                    <!-- Main Content -->
                    <div class="email-content" style="padding: 35px 30px; text-align: left;">
                        <p class="inter-font" style="color: #333333; font-size: 17px; line-height: 1.6; margin: 0 0 20px 0; font-weight: 400;">
                            Hello!
                        </p>
                        
                        <p class="inter-font" style="color: #555555; font-size: 16px; line-height: 1.6; margin: 0 0 28px 0; font-weight: 400;">
                            Great news! Your requested report <strong class="inter-bold" style="color: #8B6636; font-weight: 600;">"{title}"</strong> has been generated successfully and is ready for download.
                        </p>
                        
                        <!-- Report Details Card -->
                        <div class="report-card" style="background-color: #f8f6f3; border-left: 4px solid #C8A882; padding: 25px; margin: 28px 0; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.06);">
                            <h3 class="inter-bold" style="color: #8B6636; margin: 0 0 20px 0; font-size: 20px; line-height: 1.3; font-weight: 600;">
                                📋  Report Details
                            </h3>
                            
                            <table class="report-table" style="width: 100%; border-collapse: collapse;">
                                <tr>
                                    <td class="label inter-font" style="padding: 10px 0; color: #666666; font-weight: 600; width: 35%; vertical-align: top; font-size: 15px;">Title:</td>
                                    <td class="value inter-font" style="padding: 10px 0; color: #333333; word-break: break-word; font-size: 15px; font-weight: 400;">{title}</td>
                                </tr>
                                <tr>
                                    <td class="label inter-font" style="padding: 10px 0; color: #666666; font-weight: 600; vertical-align: top; font-size: 15px;">Generated:</td>
                                    <td class="value inter-font" style="padding: 10px 0; color: #333333; font-size: 15px; font-weight: 400;">{datetime.now().strftime('%B %d, %Y at %I:%M %p')}</td>
                                </tr>
                                <tr>
                                    <td class="label inter-font" style="padding: 10px 0; color: #666666; font-weight: 600; vertical-align: top; font-size: 15px;">Status:</td>
                                    <td class="value" style="padding: 10px 0;">
                                        <span class="status-badge inter-font" style="background-color: #d4edda; color: #155724; padding: 6px 15px; border-radius: 25px; font-size: 14px; font-weight: 600; display: inline-block;">
                                            ✅ Optimized & Ready
                                        </span>
                                    </td>
                                </tr>
                            </table>
                        </div>
                        
                        <p class="inter-font" style="color: #555555; font-size: 17px; line-height: 1.6; margin: 30px 0; font-weight: 400;">
                            The complete report is attached to this email. Simply click on the attachment to download and view your personalized analysis.
                        </p>
                    </div>
                    
                    <!-- Footer -->
                    <div class="email-footer" style="background-color: #2a2a2a; padding: 35px 30px; text-align: center;">
                        <div style="border-bottom: 1px solid #444444; padding-bottom: 25px; margin-bottom: 25px;">
                            <h3 class="inter-bold" style="color: #C8A882; margin: 0 0 12px 0; font-size: 22px; line-height: 1.3; font-weight: 600;">
                                Periwatch Team
                            </h3>
                            <p class="inter-font" style="color: #cccccc; margin: 0; font-size: 15px; line-height: 1.4; font-weight: 400;">
                                Delivering insights that matter
                            </p>
                        </div>
                        
                        <p class="inter-font" style="color: #999999; font-size: 13px; margin: 0 0 12px 0; line-height: 1.5; font-weight: 400;">
                            This email was sent automatically by Periwatch PDF Generator.<br>
                            If you have any questions, please contact our support team.
                        </p>
                        
                        <p class="inter-font" style="color: #666666; font-size: 12px; margin: 0; line-height: 1.4; font-weight: 400;">
                            © 2025 Periwatch. All rights reserved.
                        </p>
                    </div>
                </div>
            </td>
        </tr>
    </table>
    
    <!-- Fallback for Outlook -->
    <!--[if mso]>
    <style>
        .email-container {{ width: 1000px !important; }}
        .email-header h1 {{ font-size: 28px !important; }}
        .email-content {{ padding: 35px 30px !important; }}
        .inter-font, .inter-bold {{ font-family: Arial, sans-serif !important; }}
    </style>
    <![endif]-->
</body>
</html>
            """
            
            message = Mail(
                from_email=settings.DEFAULT_FROM_EMAIL,
                to_emails=recipient_email,
                subject=subject,
                html_content=html_message
            )
            attachment = Attachment(
                FileContent(pdf_base64),
                FileName(f'{title}.pdf'),
                FileType('application/pdf'),
                Disposition('attachment')
            )
            message.attachment = attachment
            sg = SendGridAPIClient(settings.SENDGRID_API_KEY)
            response = sg.send(message)
            logger.info(f"Email sent successfully via SendGrid to {recipient_email}")
            logger.info(f"SendGrid response: {response.status_code}")
            if response.status_code != 202:
                logger.error(f"SendGrid returned status code: {response.status_code}")
                logger.error(f"Response body: {response.body}")
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Failed to send email via SendGrid to {recipient_email}: {error_msg}")
            if "api_key" in error_msg.lower() or "unauthorized" in error_msg.lower():
                logger.error("SENDGRID ERROR: API key issue. Please check:")
                logger.error("1. SENDGRID_API_KEY is set in environment variables")
                logger.error("2. API key is valid and not expired")
                logger.error("3. API key has 'Mail Send' permissions")
            elif "rate limit" in error_msg.lower():
                logger.error("SENDGRID ERROR: Rate limit exceeded. Please:")
                logger.error("1. Check your SendGrid plan limits")
                logger.error("2. Implement rate limiting in your application")
                logger.error("3. Consider upgrading your SendGrid plan")
            elif "invalid email" in error_msg.lower() or "malformed" in error_msg.lower():
                logger.error("SENDGRID ERROR: Email format issue. Please check:")
                logger.error(f"1. Recipient email format: {recipient_email}")
                logger.error(f"2. From email format: {settings.DEFAULT_FROM_EMAIL}")
                logger.error("3. Email addresses are properly formatted")
            elif "domain" in error_msg.lower():
                logger.error("SENDGRID ERROR: Domain verification issue. Please:")
                logger.error("1. Verify your sending domain in SendGrid dashboard")
                logger.error("2. Check DNS records are properly configured")
                logger.error("3. Ensure FROM email uses verified domain")
            logger.error("Current SendGrid settings:")
            logger.error(f"- API Key configured: {'Yes' if hasattr(settings, 'SENDGRID_API_KEY') and settings.SENDGRID_API_KEY else 'No'}")
            logger.error(f"- FROM email: {getattr(settings, 'DEFAULT_FROM_EMAIL', 'Not set')}")
            logger.error(f"- TO email: {recipient_email}")
            logger.info("Attempting fallback to Django email system...")
            try:
                self._send_pdf_email_django_fallback(recipient_email, title, pdf_buffer)
                logger.info("Successfully sent email using Django fallback")
            except Exception as fallback_error:
                logger.error(f"Django email fallback also failed: {fallback_error}")
                raise e  # Raise the original SendGrid error
    
    def _send_pdf_email_django_fallback(self, recipient_email, title, pdf_buffer):
        """Fallback method using Django's built-in email system"""
        logger.info(f"Using Django email fallback for {recipient_email}")
        
        subject = f"Your {title} Report is Ready"
        
        # Get file size for email message
        pdf_buffer.seek(0)
        pdf_data = pdf_buffer.read()
        
        message = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Periwatch Report Ready</title>
    <style>
        @import url('data:font/woff2;base64,/* Inter font will be embedded */');
        
        /* Responsive Email Styles */
        @media screen and (max-width: 640px) {{
            .email-container {{
                width: 100% !important;
                max-width: none !important;
                margin: 0 !important;
                border-radius: 0 !important;
            }}
            .email-header {{
                padding: 25px 15px !important;
            }}
            .email-header h1 {{
                font-size: 24px !important;
            }}
            .email-header p {{
                font-size: 14px !important;
            }}
            .email-content {{
                padding: 30px 15px !important;
            }}
            .email-content p {{
                font-size: 15px !important;
            }}
            .report-card {{
                padding: 20px 15px !important;
                margin: 20px 0 !important;
            }}
            .report-card h3 {{
                font-size: 18px !important;
            }}
            .report-table td {{
                padding: 8px 0 !important;
                font-size: 14px !important;
                display: block !important;
                width: 100% !important;
            }}
            .report-table .label {{
                font-weight: 600 !important;
                margin-bottom: 5px !important;
            }}
            .report-table .value {{
                margin-bottom: 15px !important;
                padding-left: 0 !important;
            }}
            .status-badge {{
                font-size: 12px !important;
                padding: 3px 10px !important;
            }}
            .email-footer {{
                padding: 25px 15px !important;
            }}
            .email-footer h3 {{
                font-size: 18px !important;
            }}
            .email-footer p {{
                font-size: 11px !important;
            }}
            .cta-button {{
                padding: 15px 20px !important;
                font-size: 14px !important;
            }}
        }}
        
        @media screen and (max-width: 480px) {{
            .email-header h1 {{
                font-size: 22px !important;
            }}
            .email-content p {{
                font-size: 14px !important;
            }}
            .report-card h3 {{
                font-size: 16px !important;
            }}
        }}
        
        /* Font fallbacks */
        .inter-font {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
        }}
        
        .inter-bold {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            font-weight: 700;
        }}
    </style>
</head>
<body style="margin: 0; padding: 0; font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif; background-color: #f4f4f4; -webkit-text-size-adjust: 100%; -ms-text-size-adjust: 100%; min-height: 100vh;">
    <table role="presentation" style="width: 100%; margin: 0; padding: 0; background-color: #f4f4f4; min-height: 100vh;" cellpadding="0" cellspacing="0" border="0">
        <tr>
            <td align="center" style="padding: 0;">
                <div class="email-container inter-font" style="max-width: 1000px; width: 100%; margin: 0 auto; background-color: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 8px 24px rgba(0,0,0,0.12);">
                    
                    <!-- Header -->
                    <div class="email-header" style="background: linear-gradient(135deg, #C8A882 0%, #8B6636 100%); padding: 30px 25px; text-align: center;">
                        <h1 class="inter-bold" style="color: #ffffff; margin: 0; font-size: 28px; font-weight: 700; text-shadow: 0 2px 4px rgba(0,0,0,0.3); line-height: 1.2;">
                            Report Ready!
                        </h1>
                        <p class="inter-font" style="color: #ffffff; margin: 12px 0 0 0; font-size: 16px; opacity: 0.95; line-height: 1.4; font-weight: 400;">
                            Your intelligence brief has been generated
                        </p>
                    </div>
                    
                    <!-- Main Content -->
                    <div class="email-content" style="padding: 35px 30px; text-align: left;">
                        <p class="inter-font" style="color: #333333; font-size: 17px; line-height: 1.6; margin: 0 0 20px 0; font-weight: 400;">
                            Hello!
                        </p>
                        
                        <p class="inter-font" style="color: #555555; font-size: 16px; line-height: 1.6; margin: 0 0 28px 0; font-weight: 400;">
                            Great news! Your requested report <strong class="inter-bold" style="color: #8B6636; font-weight: 600;">"{title}"</strong> has been generated successfully and is ready for download.
                        </p>
                        
                        <!-- Report Details Card -->
                        <div class="report-card" style="background-color: #f8f6f3; border-left: 4px solid #C8A882; padding: 25px; margin: 28px 0; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.06);">
                            <h3 class="inter-bold" style="color: #8B6636; margin: 0 0 20px 0; font-size: 20px; line-height: 1.3; font-weight: 600;">
                                📋  Report Details
                            </h3>
                            
                            <table class="report-table" style="width: 100%; border-collapse: collapse;">
                                <tr>
                                    <td class="label inter-font" style="padding: 8px 0; color: #666666; font-weight: 600; width: 35%; vertical-align: top; font-size: 14px;">Title:</td>
                                    <td class="value inter-font" style="padding: 8px 0; color: #333333; word-break: break-word; font-size: 14px; font-weight: 400;">{title}</td>
                                </tr>
                                <tr>
                                    <td class="label inter-font" style="padding: 8px 0; color: #666666; font-weight: 600; vertical-align: top; font-size: 14px;">Generated:</td>
                                    <td class="value inter-font" style="padding: 8px 0; color: #333333; font-size: 14px; font-weight: 400;">{datetime.now().strftime('%B %d, %Y at %I:%M %p')}</td>
                                </tr>
                                <tr>
                                    <td class="label inter-font" style="padding: 8px 0; color: #666666; font-weight: 600; vertical-align: top; font-size: 14px;">Status:</td>
                                    <td class="value" style="padding: 8px 0;">
                                        <span class="status-badge inter-font" style="background-color: #d4edda; color: #155724; padding: 5px 12px; border-radius: 25px; font-size: 13px; font-weight: 600; display: inline-block;">
                                            ✅ Optimized & Ready
                                        </span>
                                    </td>
                                </tr>
                            </table>
                        </div>
                        
                        <p class="inter-font" style="color: #555555; font-size: 16px; line-height: 1.6; margin: 25px 0; font-weight: 400;">
                            The complete report is attached to this email. Simply click on the attachment to download and view your personalized analysis.
                        </p>
                    </div>
                    
                    <!-- Footer -->
                    <div class="email-footer" style="background-color: #2a2a2a; padding: 30px 25px; text-align: center;">
                        <div style="border-bottom: 1px solid #444444; padding-bottom: 20px; margin-bottom: 20px;">
                            <h3 class="inter-bold" style="color: #C8A882; margin: 0 0 10px 0; font-size: 20px; line-height: 1.3; font-weight: 600;">
                                Periwatch Team
                            </h3>
                            <p class="inter-font" style="color: #cccccc; margin: 0; font-size: 14px; line-height: 1.4; font-weight: 400;">
                                Delivering insights that matter
                            </p>
                        </div>
                        
                        <p class="inter-font" style="color: #999999; font-size: 12px; margin: 0 0 10px 0; line-height: 1.5; font-weight: 400;">
                            This email was sent automatically by Periwatch PDF Generator.<br>
                            If you have any questions, please contact our support team.
                        </p>
                        
                        <p class="inter-font" style="color: #666666; font-size: 11px; margin: 0; line-height: 1.4; font-weight: 400;">
                            © 2025 Periwatch. All rights reserved.
                        </p>
                    </div>
                </div>
            </td>
        </tr>
    </table>
    
    <!-- Fallback for Outlook -->
    <!--[if mso]>
    <style>
        .email-container {{ width: 1000px !important; }}
        .email-header h1 {{ font-size: 28px !important; }}
        .email-content {{ padding: 35px 30px !important; }}
        .inter-font, .inter-bold {{ font-family: Arial, sans-serif !important; }}
    </style>
    <![endif]-->
</body>
</html>
        """
        
        email = EmailMessage(
            subject=subject,
            body=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[recipient_email]
        )
        email.content_subtype = "html"  # Set email to HTML format
        
        # Attach PDF
        pdf_buffer.seek(0)
        pdf_data = pdf_buffer.read()
        email.attach(f'{title}.pdf', pdf_data, 'application/pdf')

        email.send()
        logger.info(f"Fallback email sent successfully to {recipient_email} (PDF size: {len(pdf_data)} bytes)")
    
    def get_task_status(self, task_id):
        """Get status of a specific task"""
        return self.active_tasks.get(task_id, {'status': 'not_found'})
    
    def cleanup_old_tasks(self, hours=24):
        """Remove old task records"""
        current_time = time.time()
        tasks_to_remove = []
        
        for task_id, task_info in self.active_tasks.items():
            if current_time - task_info.get('start_time', 0) > hours * 3600:
                tasks_to_remove.append(task_id)
        
        for task_id in tasks_to_remove:
            del self.active_tasks[task_id]
        
        logger.info(f"Cleaned up {len(tasks_to_remove)} old tasks")

pdf_task_manager = PDFGenerationTask()
