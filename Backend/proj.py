from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
import re
from langdetect import detect, LangDetectException
import os
import google.generativeai as genai
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Retrieve the API key from the environment variable
api_key = os.getenv('GENAI_API_KEY')

if not api_key:
    raise ValueError("API key for GenAI is missing. Please set it in the environment variables.")

# Configure GenAI with the retrieved API key
genai.configure(api_key=api_key)

def fetch_tnc_and_links(url):
    try:
        response = requests.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        # Extract text
        tnc_text = soup.get_text(separator='\n', strip=True)

        # Extract hyperlinks and their text
        links = []
        for link in soup.find_all('a', href=True):
            link_text = link.get_text(strip=True)
            links.append((link_text, link['href']))

        return tnc_text.strip(), links
    except requests.exceptions.RequestException as e:
        return f"Error fetching T&C: {e}", []

def fetch_link_content(url):
    try:
        response = requests.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        return soup.get_text(separator='\n', strip=True)
    except requests.exceptions.RequestException as e:
        return f"Error fetching content from link: {e}"

def clean_text(text):
    text = text.encode("ascii", "ignore").decode()
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'http\S+', '', text)
    text = re.sub(r'\[.*?\]', '', text)
    text = re.sub(r'\(.*?\)', '', text)
    text = re.sub(r'[^a-zA-Z0-9\s]', '', text)
    return text.strip()

def is_english(text):
    try:
        return detect(text) == 'en'
    except LangDetectException:
        return False

def combine_content(tnc_text, link_contents):
    combined_content = tnc_text
    for link_text, content in link_contents.items():
        if not content.startswith("Error fetching content from link:") and is_english(content):
            combined_content += f"\n\n### {link_text}\n{content}"
    combined_content = combined_content.replace('\n', ' ')
    return clean_text(combined_content)

def summarize_with_gemini(text):
    model = genai.GenerativeModel('gemini-1.5-flash', generation_config=genai.GenerationConfig(temperature=0.5))
    response = model.generate_content(f"""Summarize the privacy policy provided in triple quotes. 
    Summarize it in simple and clear language for a general audience.
    The summary should focus on the key points that a common man would need to understand, such as:

    What personal information is collected.
    How the information is used.
    How the information is shared.
    User rights regarding their data.

    Ensure the summary is concise, easy to read, and avoids technical jargon. 

    privacy policy: '''{text}'''""")
    return response.text

@app.route('/summarize-url', methods=['POST'])
def summarize_url():
    data = request.json
    url = data['url']
    
    # Fetch and combine content from URL and its links
    tnc, links = fetch_tnc_and_links(url)
    link_contents = {link[0]: fetch_link_content(link[1]) for link in links}
    combined_content = combine_content(tnc, link_contents)

    # Summarize the combined content using Gemini
    combined_summary = summarize_with_gemini(combined_content)
    
    return jsonify({"summary": combined_summary})

if __name__ == '__main__':
    app.run(debug=True)
