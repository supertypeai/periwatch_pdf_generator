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
            pdf.drawString((width - text2_width) / 2, height/2 + 67, text2)
            
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
        """Send PDF via email with detailed error handling"""
        try:
            logger.info(f"Attempting to send PDF email to {recipient_email}")
            
            subject = f"Your {title} Report is Ready"
            # Get file size for email message
            pdf_buffer.seek(0)
            file_size_bytes = len(pdf_buffer.read())
            file_size_mb = file_size_bytes / 1024 / 1024
            
            message = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Periwatch Report Ready</title>
</head>
<body style="margin: 0; padding: 0; font-family: 'Arial', 'Helvetica', sans-serif; background-color: #f4f4f4;">
    <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 10px; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.1);">
        
        <!-- Header -->
        <div style="background: linear-gradient(135deg, #C8A882 0%, #8B6636 100%); padding: 30px 20px; text-align: center;">
            <h1 style="color: #ffffff; margin: 0; font-size: 28px; font-weight: bold; text-shadow: 0 2px 4px rgba(0,0,0,0.3);">
                Report Ready!
            </h1>
            <p style="color: #ffffff; margin: 10px 0 0 0; font-size: 16px; opacity: 0.9;">
                Your intelligence brief has been generated
            </p>
        </div>
        
        <!-- Main Content -->
        <div style="padding: 40px 30px;">
            <p style="color: #333333; font-size: 18px; line-height: 1.6; margin: 0 0 25px 0;">
                Hello!
            </p>
            
            <p style="color: #555555; font-size: 16px; line-height: 1.6; margin: 0 0 30px 0;">
                Great news! Your requested report <strong style="color: #8B6636;">"{title}"</strong> has been generated successfully and is ready for download.
            </p>
            
            <!-- Report Details Card -->
            <div style="background-color: #f8f6f3; border-left: 4px solid #C8A882; padding: 25px; margin: 30px 0; border-radius: 8px;">
                <h3 style="color: #8B6636; margin: 0 0 20px 0; font-size: 20px; display: flex; align-items: center;">
                    📋  Report Details
                </h3>
                
                <table style="width: 100%; border-collapse: collapse;">
                    <tr>
                        <td style="padding: 8px 0; color: #666666; font-weight: bold; width: 30%;">Title:</td>
                        <td style="padding: 8px 0; color: #333333;">{title}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; color: #666666; font-weight: bold;">Generated:</td>
                        <td style="padding: 8px 0; color: #333333;">{datetime.now().strftime('%B %d, %Y at %I:%M %p')}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; color: #666666; font-weight: bold;">File Size:</td>
                        <td style="padding: 8px 0; color: #333333;">{file_size_mb:.2f} MB ({file_size_bytes:,} bytes)</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; color: #666666; font-weight: bold;">Status:</td>
                        <td style="padding: 8px 0;">
                            <span style="background-color: #d4edda; color: #155724; padding: 4px 12px; border-radius: 20px; font-size: 14px; font-weight: bold;">
                                ✅ Optimized & Ready
                            </span>
                        </td>
                    </tr>
                </table>
            </div>
            
            <p style="color: #555555; font-size: 16px; line-height: 1.6; margin: 25px 0;">
                The complete report is attached to this email. Simply click on the attachment to download and view your personalized analysis.
            </p>
        </div>
        
        <!-- Footer -->
        <div style="background-color: #2a2a2a; padding: 30px 20px; text-align: center;">
            <div style="border-bottom: 1px solid #444444; padding-bottom: 20px; margin-bottom: 20px;">
                <h3 style="color: #C8A882; margin: 0 0 10px 0; font-size: 20px;">
                    Periwatch Team
                </h3>
                <p style="color: #cccccc; margin: 0; font-size: 14px;">
                    Delivering insights that matter
                </p>
            </div>
            
            <p style="color: #999999; font-size: 12px; margin: 0 0 10px 0; line-height: 1.4;">
                This email was sent automatically by Periwatch PDF Generator.<br>
                If you have any questions, please contact our support team.
            </p>
            
            <p style="color: #666666; font-size: 11px; margin: 0;">
                © 2025 Periwatch. All rights reserved.
            </p>
        </div>
    </div>
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
            logger.info(f"Email sent successfully to {recipient_email} (PDF size: {len(pdf_data)} bytes)")
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Failed to send email to {recipient_email}: {error_msg}")
            
            if "Username and Password not accepted" in error_msg or "BadCredentials" in error_msg:
                logger.error("EMAIL ERROR: Gmail credentials rejected. Please check:")
                logger.error("1. Enable 2-Factor Authentication on Gmail")
                logger.error("2. Generate App Password (not regular password)")
                logger.error("3. Use App Password in EMAIL_HOST_PASSWORD")
                logger.error("4. Ensure EMAIL_HOST_USER matches Gmail address")
                
            elif "Connection refused" in error_msg or "timeout" in error_msg.lower():
                logger.error("EMAIL ERROR: SMTP connection failed. Please check:")
                logger.error("1. EMAIL_HOST and EMAIL_PORT settings")
                logger.error("2. Network connectivity")
                logger.error("3. Firewall/antivirus blocking SMTP")
                
            elif "authentication failed" in error_msg.lower():
                logger.error("EMAIL ERROR: SMTP authentication failed. Please check:")
                logger.error("1. EMAIL_HOST_USER and EMAIL_HOST_PASSWORD")
                logger.error("2. Email provider SMTP settings")
                
            logger.error(f"Current email settings:")
            logger.error(f"- HOST: {getattr(settings, 'EMAIL_HOST', 'Not set')}")
            logger.error(f"- PORT: {getattr(settings, 'EMAIL_PORT', 'Not set')}")
            logger.error(f"- USER: {getattr(settings, 'EMAIL_HOST_USER', 'Not set')}")
            logger.error(f"- TLS: {getattr(settings, 'EMAIL_USE_TLS', 'Not set')}")
            logger.error(f"- SSL: {getattr(settings, 'EMAIL_USE_SSL', 'Not set')}")
            logger.error(f"- FROM: {getattr(settings, 'DEFAULT_FROM_EMAIL', 'Not set')}")
            raise
    
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
