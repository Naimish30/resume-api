import os
import re
from flask import Flask, request, jsonify
from werkzeug.utils import secure_filename
from pdfminer.high_level import extract_text
from pdf2image import convert_from_path
import pytesseract
import nltk
from nltk.tokenize import word_tokenize, sent_tokenize
from nltk.tag import pos_tag
from nltk.chunk import ne_chunk
from spacy.lang.en.stop_words import STOP_WORDS
import pandas as pd
from fuzzywuzzy import process

app = Flask(__name__)

UPLOAD_FOLDER = '/tmp'
ALLOWED_EXTENSIONS = {'pdf'}
DATA_FOLDER = 'data'

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

nltk.download('maxent_ne_chunker')
nltk.download('words')

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_names(text):
    names = []
    for sent in sent_tokenize(text):
        for chunk in ne_chunk(pos_tag(word_tokenize(sent))):
            if hasattr(chunk, 'label') and chunk.label() == 'PERSON':
                names.append(' '.join(c[0] for c in chunk.leaves()))
    return names

def extract_emails_from_text(text):
    email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    emails = re.findall(email_pattern, text)
    return emails

def extract_phone_numbers_from_text(text):
    phone_pattern = r'\(?\+?\d{0,2}\)?[- ]?\d{3}[- ]?\d{3}[- ]?\d{4}'
    phone_numbers = re.findall(phone_pattern, text)
    return phone_numbers

@app.route('/get', methods=['GET'])
def say_hello():
    return jsonify({"message": "HEllo"}), 200


def find_closest_name(names, email):
    email_prefix = email.split('@')[0]
    closest_name = process.extractOne(email_prefix, names)
    return closest_name[0] if closest_name else "No name found"

def find_skills_in_text(text, skills):
    cleaned_text = ' '.join(token.lower() for token in word_tokenize(text) if token.lower() not in STOP_WORDS)
    found_skills = []
    for skill in skills:
        if skill.lower() in cleaned_text:
            found_skills.append(skill)
    return found_skills

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

        text = extract_text(file_path)
        email = extract_emails_from_text(text)
        phone = extract_phone_numbers_from_text(text)
        name = extract_names(text)
        skills_path = os.path.join(DATA_FOLDER, "Tech-skills.csv")
        skills = pd.read_csv(skills_path)["skills"].apply(lambda x: x.strip().strip('"')).tolist()
        skill_set = find_skills_in_text(text, skills)

        if not email and not phone:
            pages = convert_from_path(file_path, 400)
            text = ""
            for page_number, page in enumerate(pages):
                page_text = pytesseract.image_to_string(page)
                text += f"Page {page_number + 1}\n\n" + page_text + "\n\n"
            email = extract_emails_from_text(text)
            phone = extract_phone_numbers_from_text(text)
            name = extract_names(text)
            skill_set = find_skills_in_text(text, skills)

        name = find_closest_name(name, email[0]) if email else "No email found"

        return jsonify({
            "email_id": email,
            "phone_number": phone,
            "name": name,
            "skills": skill_set
        })

    return jsonify({"error": "File not allowed"}), 400

if __name__ == '__main__':
    app.run(debug=True)
