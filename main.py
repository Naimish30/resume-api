import os
from flask import Flask, request, jsonify
from werkzeug.utils import secure_filename
from pdfminer.high_level import extract_text
from pdf2image import convert_from_path
import pytesseract
import re

app = Flask(__name__)

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'pdf'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_emails_from_text(text):
    email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    emails = re.findall(email_pattern, text)
    return emails

def extract_phone_numbers_from_text(text):
    phone_number_pattern = r'\(?\+?\d{0,2}\)?[- ]?\d{3}[- ]?\d{3}[- ]?\d{4}'
    phone_numbers = re.findall(phone_number_pattern, text)
    return phone_numbers

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)

        emailid = []
        phone_numbers = []

        text = extract_text(file_path)
        email = extract_emails_from_text(text)
        phone = extract_phone_numbers_from_text(text)

        if len(email) != 0 or len(phone) != 0:
            emailid.append(email)
            phone_numbers.append(phone)
        if len(email) == 0 and len(phone) == 0:
            pages = convert_from_path(file_path, 400)
            text = ""
            for page_number, page in enumerate(pages):
                image = page
                page_text = pytesseract.image_to_string(image)
                text += f"Page {page_number + 1}\n\n" + page_text + "\n\n"
            email = extract_emails_from_text(text)
            emailid.append(email)
            phone = extract_phone_numbers_from_text(text)
            phone_numbers.append(phone)

        return jsonify({
            "email_id": emailid,
            "phone_numbers": phone_numbers
        })

    return jsonify({"error": "File not allowed"}), 400

if __name__ == '__main__':
    app.run(debug=True)
