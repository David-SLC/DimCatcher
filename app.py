import streamlit as st
import fitz  # PyMuPDF
import pytesseract
from PIL import Image
import io
import re
import pandas as pd
import os
from fpdf import FPDF

# --- Core Functions ---

def parse_dimensions(text_snippet):
    match = re.search(r'(?i)DW[T|I]\s*:?\s*([\d\.,]+)', text_snippet)
    if not match:
        return None 

    raw_dims = match.group(1)
    normalized = raw_dims.replace('.', ',')
    parts = [p.strip() for p in normalized.split(',') if p.strip()]
    
    if len(parts) == 3:
        return parts 
        
    final_parts = []
    total_digits = sum(len(p) for p in parts)
    
    if len(parts) == 2:
        for part in parts:
            if len(part) == 4:
                final_parts.extend([part[:2], part[2:]])
            elif len(part) == 2 and total_digits == 3:
                final_parts.extend([part[0], part[1]])
            else:
                final_parts.append(part)
                
    elif len(parts) == 1:
        s = parts[0]
        if len(s) == 6:
            final_parts.extend([s[:2], s[2:4], s[4:]])
        elif len(s) == 3:
            final_parts.extend([s[0], s[1], s[2]])
        else:
            final_parts.append(s)
            
    else:
        final_parts = parts

    return final_parts if len(final_parts) == 3 else None

def process_page(page_num, file_bytes):
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    page = doc[page_num]
    text = page.get_text("text")
    
    if len(text.strip()) < 50:
        pix = page.get_pixmap(dpi=150)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        text = pytesseract.image_to_string(img)

    text_clean = re.sub(r'\s+', ' ', text)
    doc.close()

    if re.search(r'Packing\s+Slip', text_clean, re.IGNORECASE):
        return {"status": "skipped_slip", "page": page_num + 1}

    fedex_match = re.search(r'(?:DIMMED|DIM|DIMS)\s*[:]?\s*(\d+)\s*[xX]\s*(\d+)\s*[xX]\s*(\d+)', text_clean, re.IGNORECASE)
    if fedex_match:
        return {"status": "found", "dim": f"{fedex_match.group(1)}x{fedex_match.group(2)}x{fedex_match.group(3)}", "page": page_num + 1}

    ups_dims = parse_dimensions(text_clean)
    if ups_dims:
        return {"status": "found", "dim": f"{ups_dims[0]}x{ups_dims[1]}x{ups_dims[2]}", "page": page_num + 1}

    express_match = re.search(r'ACTWGT\s*[:]?\s*1\.00\s*LB', text_clean, re.IGNORECASE)
    if express_match:
        return {"status": "found", "dim": "FedEx Express Package", "page": page_num + 1}

    return {"status": "not_found", "page": page_num + 1}

def calculate_volume(dim_string):
    if dim_string == "FedEx Express Package":
        return -1  
    try:
        l, w, h = dim_string.split('x')
        return int(l) * int(w) * int(h)
    except:
        return 0  

def create_pdf_report(df):
    pdf = FPDF()
    pdf.add_page()
    
    # Title
    pdf.set_font("helvetica", "B", 16)
    pdf.cell(0, 10, "DimCatcher - Daily Box Tally", align="C", new_x="LMARGIN", new_y="NEXT")
    
    # Subtitle
    pdf.set_font("helvetica", "", 12)
    pdf.cell(0, 10, "Ranked by Volume (Largest to Smallest)", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(10)
    
    # Table Header
    pdf.set_font("helvetica", "B", 12)
    pdf.cell(95, 10, "Dimensions (LxWxH)", border=1, align="C")
    pdf.cell(95, 10, "Total Quantity", border=1, align="C", new_x="LMARGIN", new_y="NEXT")
    
    # Table Data
    pdf.set_font("helvetica", "", 12)
    for index, row in df.iterrows():
        pdf.cell(95, 10, str(row['Dimensions (LxWxH)']), border=1, align="C")
        pdf.cell(95, 10, str(row['Total Quantity']), border=1, align="C", new_x="LMARGIN", new_y="NEXT")
        
    return bytes(pdf.output())

# --- Streamlit UI ---

st.set_page_config(page_title="DimCatcher", page_icon="📦")

st.title("📦 DimCatcher")
st.write("Upload your daily ShipStation labels below to extract and tally your box dimensions.")

# Drag and Drop Uploader
uploaded_file = st.file_uploader("Upload PDF file", type=["pdf"])

if uploaded_file is not None:
    file_bytes = uploaded_file.read()
    
    try:
        with st.spinner("Initializing scanner..."):
            initial_doc = fitz.open(stream=file_bytes, filetype="pdf")
            num_pages = len(initial_doc)
            initial_doc.close()
            
        # Setup Progress Bar
        progress_bar = st.progress(0, text="Starting scan...")
        
        dimensions_tally = {}
        pages_found = 0
        pages_skipped = 0
        results = []
        
        # Single-threaded processing to respect free-tier CPU limits
        for p in range(num_pages):
            res = process_page(p, file_bytes)
            results.append(res)
            
            # Update progress bar in real-time
            completed = p + 1
            percentage = int((completed / num_pages) * 100)
            progress_bar.progress(completed / num_pages, text=f"Scanning labels... {percentage}% ({completed}/{num_pages} pages)")
                
        # Process Results
        for res in results:
            if res['status'] == 'not_found' or res['status'] == 'skipped_slip':
                pages_skipped += 1
            elif res['status'] == 'found':
                pages_found += 1
                dim = res['dim']
                dimensions_tally[dim] = dimensions_tally.get(dim, 0) + 1
                
        # Final Output Validation
        if dimensions_tally:
            progress_bar.empty() 
            st.success(f"Success! Processed {pages_found} labels. ({pages_skipped} pages skipped)")
            
            df = pd.DataFrame(list(dimensions_tally.items()), columns=['Dimensions (LxWxH)', 'Total Quantity'])
            df['Volume'] = df['Dimensions (LxWxH)'].apply(calculate_volume)
            df = df.sort_values(by='Volume', ascending=False)
            df = df.drop(columns=['Volume'])
            
            # Generate PDF byte output
            pdf_bytes = create_pdf_report(df)
            
            st.download_button(
                label="📄 Download Box Tally (PDF)",
                data=pdf_bytes,
                file_name="DimCatcher_Box_Tally.pdf",
                mime="application/pdf"
            )
        else:
            progress_bar.empty()
            st.error("Uh oh! No dimensions were found in this document.")

    except Exception as e:
        st.error("An error occurred while processing the file. Please ensure it is a valid PDF and try again.")
        with st.expander("Show error details"):
            st.write(e)
