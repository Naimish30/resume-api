import re
import os
import pytesseract
from pdf2image import convert_from_path
import pandas as pd
from flask import Flask, request, jsonify
from werkzeug.utils import secure_filename
from fuzzywuzzy import fuzz
from pdfminer.high_level import extract_text
from datetime import datetime


app = Flask(__name__)

UPLOAD_FOLDER = '/tmp'
ALLOWED_EXTENSIONS = {'pdf'}
DATA_FOLDER = 'data'

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_names(text):
    matcher = get_matcher()
    nlp=load_spacy_model()
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
    nlp = load_spacy_model()
    doc = nlp(text.replace('\r', ''))
    cleaned_text = ' '.join(token.text.lower() for token in doc if token.text.lower() not in get_stop_words())
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

def extract_resume_headings_and_content(pdf_text, resume_headings):
    found_headings = {}
    pattern = '|'.join([f'^({heading})' for heading in resume_headings])

    # Match at the start of a line
    matches = list(re.finditer(pattern, pdf_text, re.MULTILINE | re.IGNORECASE))

    matches.append(re.search(r'$', pdf_text))

    for i, match in enumerate(matches[:-1]):
        heading = match.group(0)
        start = match.end()
        end = matches[i + 1].start()
        content = pdf_text[start:end].strip()
        found_headings[heading] = content

    return found_headings


def extract_dates_from_sections(resume_sections):
    internship_keywords = ['internship', 'internships', 'roles & responsibility', 'training', 'training experience', "intern"]
    experience_keywords = ['experience', 'industrial experience', 'work experience', 'employment history', 'jobs']
    fellowship_keywords = ['fellowship', 'fellowships']

    date_patterns = [
        r'\b\d{4}\s*-\s*\d{4}\b',  # YYYY-YYYY
        r'\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{4}\s*[–-]\s*(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{4}\b',
        r'\b\d{1,2}/\d{4}\s*to\s*\d{1,2}/\d{4}\b',  # MM/YYYY to MM/YYYY
        r'\b\d{1,2}/\d{4}\s*-\s*\d{1,2}/\d{4}\b',  # MM/YYYY - MM/YYYY
        r'\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)/\d{4}\s*to\s*(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)/\d{4}\b',
        # MMM/YYYY to MMM/YYYY
        r'\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)/\d{4}\s*to\s*(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}\b',
        # MMM/YYYY to MMM YYYY
        r'\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{4}\s*to\s*present\b',
        # MMM YYYY to Present
        r'\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{4}\s*[–-]\s*present\b',
        r'\b\d{4}\s*to\s*present\b',  # YYYY to Present
        r'\b\d{1,2}/\d{4}\s*-\s*present\b',  # MM/YYYY - Present
        r'\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{4}\b',
        # MMM YYYY
        r'\b\d{4}\b',  # YYYY
        r'\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{4}\s*–\s*(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}\b'
        # MMM YYYY – MMM YYYY
    ]

    internship_dates = []
    experience_dates = []
    fellowship_dates = []

    current_year = str(datetime.now().year)

    for section_heading, section_content in resume_sections.items():
        if any(keyword in section_heading.lower() for keyword in internship_keywords):
            for pattern in date_patterns:
                dates = re.findall(pattern, section_content, re.IGNORECASE)
                internship_dates.extend(dates)
        elif any(keyword in section_heading.lower() for keyword in experience_keywords):
            for pattern in date_patterns:
                dates = re.findall(pattern, section_content, re.IGNORECASE)
                experience_dates.extend(dates)
        elif any(keyword in section_heading.lower() for keyword in fellowship_keywords):
            for pattern in date_patterns:
                dates = re.findall(pattern, section_content, re.IGNORECASE)
                fellowship_dates.extend(dates)

    # Handle 'Present' dates by replacing with the current year
    internship_dates = [date.replace('present', current_year).replace('Present', current_year) for date in internship_dates]
    experience_dates = [date.replace('present', current_year).replace('Present', current_year) for date in experience_dates]
    fellowship_dates = [date.replace('present', current_year).replace('Present', current_year) for date in fellowship_dates]

    # Filter out single years
    internship_dates = [date for date in internship_dates if not re.match(r'^\d{4}$', date)]
    experience_dates = [date for date in experience_dates if not re.match(r'^\d{4}$', date)]
    fellowship_dates = [date for date in fellowship_dates if not re.match(r'^\d{4}$', date)]

    return {
        "internship_dates": internship_dates,
        "experience_dates": experience_dates,
        "fellowship_dates": fellowship_dates
    }


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
        email_list = extract_emails_from_text(text)
        phone_list = extract_phone_numbers_from_text(text)
        name = extract_names(text)
        skills_path = os.path.join(DATA_FOLDER, "Tech-skills.csv")
        skills = pd.read_csv(skills_path)["skills"].apply(lambda x: x.strip().strip('"')).tolist()
        skill_set = find_skills_in_text(text, skills)

        if not email_list and not phone_list:
            pages = convert_from_path(file_path, 400)
            text = ""
            for page_number, page in enumerate(pages):
                page_text = pytesseract.image_to_string(page)
                text += f"Page {page_number + 1}\n\n" + page_text + "\n\n"
            email_list = extract_emails_from_text(text)
            phone_list = extract_phone_numbers_from_text(text)
            name = extract_names(text)
            skill_set = find_skills_in_text(text, skills)

        email = email_list[0] if email_list else "No email found"
        phone = phone_list[0] if phone_list else "No phone number found"
        name = find_closest_name(name, email) if email != "No email found" else "No email found"

        # Extracting resume headings and content
        resume_headings = [
            "PROJECT INFORMATION",
            "Contact Information",
            "TRAINING EXPERIENCE"
            "Objective",
            "Summary",
            "Executive Profile",
            "Professional Profile",
            "Personal Profile",
            "Overview",
            "Qualifications",
            "Summary of Qualifications",
            "Experience",
            "Professional Experience",
            "Work Experience",
            "Employment History",
            "Work Background",
            "Jobs",
            "Education",
            "Academic Profile",
            "Degrees and Certifications",
            "Certifications",
            "Licenses and Certifications",
            "Professional Certifications",
            "Skills",
            "Key Skills",
            "Technical Skills",
            "Core Competencies",
            "Skills & Interests",
            "Interests",
            "Hobbies",
            "Accomplishments",
            "Achievements",
            "Awards and Honors",
            "Recognitions",
            "Projects",
            "Professional Projects",
            "Academic Projects",
            "Publications",
            "Publication",
            "Research Papers",
            "Articles",
            "Books",
            "Professional Affiliations",
            "Memberships",
            "Associations",
            "Volunteer Experience",
            "Community Service",
            "Volunteering",
            "Languages",
            "Language Proficiency",
            "Languages Spoken",
            "References",
            "Professional References",
            "References Available Upon Request",
            "Co-Curricular Activities",
            "Other Activities",
            "Workshops",
            "Trainings",
            "Internships",
            "Internship",
            "Position of Responsibility",
            "INDUSTRIAL EXPERIENCE",
            "DECLARATION",
            "others",
            "Roles & Responsibility",
            "Personal Details",
            "Fellowship",
            "Training",
            "Intern"
        ]
        resume_sections = extract_resume_headings_and_content(text, resume_headings)

        # Extracting dates from resume sections
        dates_info = extract_dates_from_sections(resume_sections)
        internship_dates = dates_info["internship_dates"]
        experience_dates = dates_info["experience_dates"]
        fellowship_dates = dates_info["fellowship_dates"]

        return jsonify({
            "email_id": email,
            "phone_number": phone,
            "name": name,
            "skills": skill_set,
            "internship_dates": internship_dates,
            "experience_dates": experience_dates,
            "fellowship_dates": fellowship_dates
        })

    return jsonify({"error": "File not allowed"}), 400



def get_matcher():
    import spacy
    from spacy.matcher import Matcher
    try:
        nlp = spacy.load('en_core_web_sm')
    except OSError:
        os.system("python -m spacy download en_core_web_sm")
        nlp = spacy.load('en_core_web_sm')
    matcher = Matcher(nlp.vocab)
    pattern = [{'POS': 'PROPN'}, {'POS': 'PROPN'}]
    matcher.add("NAME", [pattern])
    return matcher

def get_stop_words():
    from spacy.lang.en.stop_words import STOP_WORDS
    return STOP_WORDS
def load_spacy_model():
    import spacy
    try:
        nlp = spacy.load('en_core_web_sm')
    except OSError:
        os.system("python -m spacy download en_core_web_sm")
        nlp = spacy.load('en_core_web_sm')
    return nlp

if __name__ == '__main__':
    app.run(debug=True)
