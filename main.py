from pdfminer.high_level import extract_text
from spacy.matcher import Matcher
import re
import os
import spacy
import pytesseract
from pdf2image import convert_from_path
import pandas as pd
from flask import Flask, request, jsonify
from werkzeug.utils import secure_filename
from spacy.lang.en.stop_words import STOP_WORDS
from fuzzywuzzy import fuzz

try:
    nlp = spacy.load('en_core_web_sm')
except OSError:
    os.system("python -m spacy download en_core_web_sm")
    nlp = spacy.load('en_core_web_sm')

app = Flask(__name__)

UPLOAD_FOLDER = '/tmp'
ALLOWED_EXTENSIONS = {'pdf'}
DATA_FOLDER = 'data'

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_names(text):
    matcher = Matcher(nlp.vocab)
    pattern = [{'POS': 'PROPN'}, {'POS': 'PROPN'}]
    matcher.add("NAME", [pattern])
    doc = nlp(text)
    matches = matcher(doc)
    matched_names = [doc[start:end].text for match_id, start, end in matches]
    return matched_names

def extract_emails_from_text(text):
    email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    emails = re.findall(email_pattern, text)
    return emails

def extract_phone_numbers_from_text(text):
    phone_pattern = r'\(?\+?\d{0,2}\)?[- ]?\d{3}[- ]?\d{3}[- ]?\d{4}'
    phone_numbers = re.findall(phone_pattern, text)
    return phone_numbers

@app.route('/get',methods=['GET'])
def say_hello():
    return jsonify({"message":"HEllo"}),200

def find_closest_name(names, email):
    email_prefix = email.split('@')[0].lower()
    names_lower = [name.lower() for name in names]
    similarities = [fuzz.token_set_ratio(email_prefix, name) for name in names_lower]
    max_similarity_index = similarities.index(max(similarities))
    return names[max_similarity_index] if max(similarities) > 30 else names[0]

def find_skills_in_text(text, skills):
    doc = nlp(text.replace('\r', ''))
    cleaned_text = ' '.join(token.text.lower() for token in doc if token.text.lower() not in STOP_WORDS)
    found_skills = []

    for skill in skills:
        skill_lower = skill.lower()
        if skill_lower in cleaned_text:
            r_index = cleaned_text.find(skill_lower)
            if len(skill_lower) == 1:
                if cleaned_text[r_index-1:r_index+2] == f" {skill_lower} ":
                    found_skills.append(skill)
            else:
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
