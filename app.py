from flask import Flask, render_template
from flask.globals import request
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.platypus import Table, TableStyle
from reportlab.lib import colors
from io import BytesIO
from PIL import Image
import psycopg2
import datetime
import os
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.auth.transport.requests import Request

app = Flask(__name__)

# Database parameters
db_params = {
    "host": "postgresql-152351-0.cloudclusters.net",
    "port": "19991",
    "database": "finflash",
    "user": "suresh",
    "password": "s1u2r3e4"
}

# Google Drive API parameters
SCOPES = ['https://www.googleapis.com/auth/drive.file']
TOKEN_PATH = 'token.json'
CREDENTIALS_PATH = "C:/Users/91725/Downloads/client_secret_759948599227-piupe13ali6726leibrgiqjs9u8i2646.apps.googleusercontent.com.json"
FOLDER_ID = '1p_FBCcBMdYjhPNMl2z182zTrfmc9khr3'  # Replace with your Google Drive folder ID

# Function to authenticate with Google Drive
def authenticate_drive():
    creds = None

    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES, redirect_uri='http://localhost:61818')
            creds = flow.run_local_server(port=61818)

        with open(TOKEN_PATH, 'w') as token:
            token.write(creds.to_json())

    return creds

# Function to upload a file to Google Drive
def upload_to_drive(service, file_path, folder_id=None):
    file_name = os.path.basename(file_path)
    media_body = MediaFileUpload(file_path, resumable=True)

    file_metadata = {
        'name': file_name,
        'parents': [folder_id] if folder_id else [],
        'mimeType': 'application/pdf'  # Specify the MIME type
    }

    request = service.files().create(
        body=file_metadata,
        media_body=media_body
    )

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"Uploaded {int(status.progress() * 100)}%")

    print(f"Upload complete: {response}")

# Function to add a digital signature to the PDF and upload to Google Drive
def add_digital_signature_and_upload(date_part, data, drive_service):
    # Create a BytesIO buffer to save the PDF content
    pdf_buffer = BytesIO()

    # Create a PDF document
    pdf = canvas.Canvas(pdf_buffer, pagesize=letter)

    # Set the PDF title
    pdf.setTitle(f"Data for Date: {date_part}")

    # Load the signature image
    signature_image_path = r"C:\Users\91725\OneDrive\Desktop\signature.jpg"  # Replace with the path to your signature image
    signature_image = Image.open(signature_image_path)

    # Resize the image if needed
    signature_image = signature_image.resize((100, 50))

    # Set up the table structure
    table_data = [["Product", "Reason", "Activity", "Trade", "Instrument", "Expiry", "id", "TimeStamp_str"]]
    for row in data:
        table_data.append([str(cell) for cell in row])

    # Set the specific width for the TimeStamp_str column
    col_widths = [62] * 7 + [80]  # Adjust the width of the TimeStamp_str column as needed

    # Draw the table with some space from the right and bottom edges
    table = Table(table_data, colWidths=col_widths, rowHeights=[30] + [15] * len(data))
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]))

    pdf.drawInlineImage(signature_image, pdf._pagesize[0] - 120, 20)

    table.wrapOn(pdf, pdf._pagesize[0] - 220, pdf._pagesize[1] - 100)
    table.drawOn(pdf, 60, 200)  # Adjusted coordinates

    pdf.setFont("Helvetica", 8)
    pdf.drawRightString(pdf._pagesize[0] - 120, 10, f"{date_part}")

    # Add heading at the top
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawCentredString(pdf._pagesize[0] / 2, pdf._pagesize[1] - 20, f"Research Data for {date_part}")

    # Save the PDF to a buffer
    pdf_buffer.seek(0)

    pdf_filename = f"Data_{date_part}.pdf"
    with open(pdf_filename, "wb") as pdf_file:
        pdf_file.write(pdf_buffer.read())

    # Upload the generated PDF to Google Drive
    upload_to_drive(drive_service, pdf_filename, FOLDER_ID)

    return pdf_filename

# Flask route for generating PDFs and uploading to Google Drive
@app.route('/generate_pdfs', methods=['GET'])
def generate_pdfs():
    # Authenticate with Google Drive
    drive_creds = authenticate_drive()
    drive_service = build('drive', 'v3', credentials=drive_creds)

    # Connect to the PostgreSQL server
    conn = psycopg2.connect(**db_params)

    # Create a cursor
    cursor = conn.cursor()

    # Sample query to fetch data
    query = "SELECT * FROM research"
    cursor.execute(query)

    # Fetch all rows
    data = cursor.fetchall()

    # Extract and group the date parts
    date_part_groups = {}
    for row in data:
        timestamp_str = row[-1]  # Assuming the timestamp_str is the last column
        # Convert timestamp string to datetime object
        timestamp_dt = datetime.datetime.strptime(timestamp_str, "%d-%b-%Y %H:%M")
        # Extract the date part
        date_part = timestamp_dt.date()

        # Add the row to the corresponding date part group
        if date_part not in date_part_groups:
            date_part_groups[date_part] = []
        date_part_groups[date_part].append(row)

    # Create PDFs for each date_part
    generated_pdfs = []
    for date_part, group in date_part_groups.items():
        # Add digital signature and table to the PDF
        pdf_filename = add_digital_signature_and_upload(date_part, group, drive_service)
        generated_pdfs.append(pdf_filename)

    # Close the cursor and connection
    cursor.close()
    conn.close()

    return render_template('index.html', generated_pdfs=generated_pdfs)

if __name__ == '__main__':
    app.run(debug=True)
