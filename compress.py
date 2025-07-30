import fitz  # PyMuPDF
import sys
import os
from PIL import Image
import io

def compress_pdf_simple(input_path, output_path, image_quality=40):
    """
    Simple and effective PDF compression by converting pages to compressed images.
    This method works reliably with all PyMuPDF versions.
    """
    print(f"Compressing PDF: {input_path}")
    
    # Open the input PDF
    doc = fitz.open(input_path)
    
    # Create a new document
    new_doc = fitz.open()
    
    total_pages = len(doc)
    print(f"Total pages: {total_pages}")
    
    for page_num in range(total_pages):
        page = doc[page_num]
        
        print(f"Processing page {page_num + 1}/{total_pages}...")
        
        # Convert page to high-resolution image
        # Use zoom factor for better quality (1.5x is good balance between quality and size)
        zoom = 1.9
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)
        
        # Convert to PIL Image
        img_data = pix.tobytes("png")
        pil_image = Image.open(io.BytesIO(img_data))
        
        # Convert to RGB if necessary (removes alpha channel)
        if pil_image.mode in ('RGBA', 'LA', 'P'):
            # Create white background
            rgb_image = Image.new('RGB', pil_image.size, (255, 255, 255))
            if pil_image.mode == 'RGBA':
                rgb_image.paste(pil_image, mask=pil_image.split()[-1])  # Use alpha channel as mask
            else:
                rgb_image.paste(pil_image)
            pil_image = rgb_image
        
        # Compress the image
        img_buffer = io.BytesIO()
        pil_image.save(img_buffer, 
                      format='JPEG', 
                      quality=image_quality,
                      optimize=True,
                      progressive=True)
        img_buffer.seek(0)
        
        # Create new page with same dimensions as original
        new_page = new_doc.new_page(width=page.rect.width, height=page.rect.height)
        
        # Insert the compressed image
        new_page.insert_image(page.rect, stream=img_buffer.read())
        
        print(f"  Original page size: {len(pix.tobytes('png')):,} bytes")
        print(f"  Compressed size: {len(img_buffer.getvalue()):,} bytes")
    
    # Save the compressed PDF
    print("Saving compressed PDF...")
    new_doc.save(output_path, 
                 garbage=4,      # Remove unused objects
                 deflate=True,   # Compress streams  
                 clean=True      # Clean up structure
    )
    
    # Close documents
    new_doc.close()
    doc.close()
    
    # Show compression results
    original_size = os.path.getsize(input_path)
    compressed_size = os.path.getsize(output_path)
    compression_ratio = ((original_size - compressed_size) / original_size) * 100
    
    print(f"\n{'='*50}")
    print(f"COMPRESSION RESULTS")
    print(f"{'='*50}")
    print(f"Original file: {input_path}")
    print(f"Compressed file: {output_path}")
    print(f"Original size: {original_size:,} bytes ({original_size/1024/1024:.2f} MB)")
    print(f"Compressed size: {compressed_size:,} bytes ({compressed_size/1024/1024:.2f} MB)")
    print(f"Space saved: {original_size - compressed_size:,} bytes ({(original_size - compressed_size)/1024/1024:.2f} MB)")
    print(f"Compression ratio: {compression_ratio:.1f}%")
    print(f"{'='*50}")

def compress_with_different_qualities(input_path, base_output_name):
    qualities = [20, 30, 50, 70]
    
    for quality in qualities:
        output_path = f"{base_output_name}_q{quality}.pdf"
        print(f"\n--- Creating version with quality {quality}% ---")
        compress_pdf_simple(input_path, output_path, quality)

if __name__ == "__main__":
    input_pdf = "kpk.pdf"
    
    if not os.path.exists(input_pdf):
        print(f"Error: File '{input_pdf}' not found!")
        print("Please make sure the PDF file exists in the current directory.")
        sys.exit(1)
    
    # Single compression with medium quality
    print("Creating compressed version with medium quality...")
    compress_pdf_simple(input_pdf, "kpk_compressed6.pdf", image_quality=90)
