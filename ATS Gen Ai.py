import streamlit as st
from pypdf import PdfReader
import google.generativeai as genai
from langchain_core.messages import HumanMessage
from langchain.memory import ConversationBufferMemory
from langchain.chains import ConversationChain
from langchain_google_genai import ChatGoogleGenerativeAI
from docx2pdf import convert
import zipfile
import os
import pythoncom
import tempfile
import shutil
import hashlib

# Configure the Google Gemini API
gemini_api = "AIzaSyC-e6OumSIdNjvpoGxhDHUVmZvE-CKqdsg"
genai.configure(api_key=gemini_api)

@st.cache_data
def process_zip(zip_file):
    # Generate a unique identifier for this zip file
    file_hash = hashlib.md5(zip_file.getvalue()).hexdigest()
    
    # Check if we've already processed this file
    if file_hash in st.session_state:
        return st.session_state[file_hash]
    
    with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as temp_zip:
        temp_zip.write(zip_file.getvalue())
        temp_zip_path = temp_zip.name

    try:
        pdf_texts = extract_and_convert(temp_zip_path)
        
        # Store the processed data in session state
        st.session_state[file_hash] = pdf_texts
        
        return pdf_texts
    finally:
        os.unlink(temp_zip_path)

def extract_and_convert(zip_file_path):
    temp_dir = tempfile.mkdtemp()
    pdf_texts = []
    
    try:
        with zipfile.ZipFile(zip_file_path, 'r') as zip_ref:
            zip_ref.extractall(temp_dir)
        
        pythoncom.CoInitialize()
        
        try:
            for root, dirs, files in os.walk(temp_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    if file.lower().endswith(".docx"):
                        pdf_path = os.path.splitext(file_path)[0] + ".pdf"
                        try:
                            convert(file_path, pdf_path)
                            os.remove(file_path)
                        except Exception as e:
                            st.warning(f"Error converting {file}: {str(e)}")
                    elif file.lower().endswith(".pdf"):
                        pdf_path = file_path
                    else:
                        continue
                    
                    text = read_pdf(pdf_path)
                    if text:
                        pdf_texts.append(text)
        finally:
            pythoncom.CoUninitialize()
    
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    return pdf_texts

def read_pdf(pdf_path):
    try:
        reader = PdfReader(pdf_path)
        text = ""
        for page in reader.pages:
            text += page.extract_text()
        return text
    except Exception as e:
        st.warning(f"Error reading PDF {pdf_path}: {str(e)}")
        return ""

def summarize(pdf_texts, keywords):
    prompt = f"""
    You are an experienced HR Manager tasked with reviewing multiple resumes. 
    Your goal is to identify candidates whose resumes mention the following skills or keywords: {keywords}

    For each matching resume, please provide the following:

    Name of the Person: Extract the full name of the candidate.
    Contact Details: Extract the email, phone number, and any social media links (e.g., LinkedIn, GitHub) provided.
    Matched Skills: List the skills from the provided keywords that are found in the resume.
    Summary: Provide a brief summary of the candidate's technical expertise, focusing on the matched skills.

    Only include candidates who have at least one matching skill or keyword in their resume.
    If no candidates match the criteria, state that no matching candidates were found.

    NOTE: Provide a neatly formatted response.
    """
    
    combined_pdf_content = "\n".join(pdf_texts)
    full_prompt = prompt + "\n\nResume Content:\n" + combined_pdf_content
    
    message = HumanMessage(content=full_prompt)
    llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash", api_key=gemini_api)
    response = llm.invoke([message])
    return response.content

st.set_page_config(page_title="ATS Resume Tracker", page_icon="📄", layout="wide")
st.title("ATS Resume Tracker")

if "memory" not in st.session_state:
    st.session_state.memory = ConversationBufferMemory()

if "messages" not in st.session_state:
    st.session_state.messages = []

zip_file = st.sidebar.file_uploader("Upload the ZIP file", help="Upload ZIP file", type="zip")

if zip_file:
    pdf_texts = process_zip(zip_file)
    st.success(f"Processed {len(pdf_texts)} resumes from the ZIP file.")

keywords = st.text_area("Enter keywords or skills to search for:", help="Separate multiple keywords with commas (e.g., C++, Java, BIM)")

if st.button("Analyze Resumes"):
    if zip_file and keywords:
        with st.spinner("Analyzing resumes and matching keywords... Please wait"):
            summary = summarize(pdf_texts, keywords)
            st.session_state.messages.append({"role": "assistant", "content": summary})
    else:
        st.warning("Please upload a ZIP file and enter keywords before analyzing.")

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("Ask a question about the resumes"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash", api_key=gemini_api)
    chain = ConversationChain(llm=llm, memory=st.session_state.memory)
    response = chain.run(prompt)

    with st.chat_message("assistant"):
        st.markdown(response)
    st.session_state.messages.append({"role": "assistant", "content": response})
