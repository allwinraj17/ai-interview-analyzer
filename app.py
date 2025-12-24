import streamlit as st
import PyPDF2
import speech_recognition as sr
import tempfile
import base64
import os
import io
from gtts import gTTS
from audio_recorder_streamlit import audio_recorder
from openai import OpenAI
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from pydub import AudioSegment  # Added for audio conversion

# -----------------------------------
# 1. CONFIG & API SETUP
# -----------------------------------
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

st.set_page_config(page_title="AI Interview Pro", layout="centered")

# -----------------------------------
# 2. SESSION STATE
# -----------------------------------
for k in ["question", "transcript", "result"]:
    if k not in st.session_state:
        st.session_state[k] = None

# -----------------------------------
# 3. UTILITY FUNCTIONS
# -----------------------------------
def speak(text):
    tts = gTTS(text=text, lang='en')
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
        tts.save(f.name)
        with open(f.name, "rb") as audio_file:
            audio_bytes = audio_file.read()
        audio_base64 = base64.b64encode(audio_bytes).decode()
        st.markdown(
            f'<audio autoplay src="data:audio/mp3;base64,{audio_base64}"></audio>',
            unsafe_allow_html=True
        )

def detect_fillers(text):
    fillers = ["uh", "um", "er", "ah", "you know", "like"]
    found = {}
    lower_text = text.lower()
    for f in fillers:
        count = lower_text.count(f)
        if count > 0:
            found[f] = count
    return found, sum(found.values())

def generate_pdf(score_text, filler_count, feedback):
    path = "Interview_Report.pdf"
    doc = SimpleDocTemplate(path, pagesize=letter)
    styles = getSampleStyleSheet()
    elements = []
    elements.append(Paragraph("AI Interview Analysis Report", styles["Title"]))
    elements.append(Spacer(1, 12))
    data = [["Metric", "Result"], ["Performance Score", score_text], ["Filler Words Used", str(filler_count)]]
    table = Table(data, colWidths=[150, 300])
    table.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), colors.lightblue), ('GRID', (0, 0), (-1, -1), 1, colors.black)]))
    elements.append(table)
    elements.append(Spacer(1, 24))
    elements.append(Paragraph(feedback, styles["Normal"]))
    doc.build(elements)
    return path

# -----------------------------------
# 4. APP UI
# -----------------------------------
st.title("🎤 AI Interview Pro")

resume = st.file_uploader("📄 Upload Resume (PDF)", type="pdf")
resume_text = ""

if resume:
    reader = PyPDF2.PdfReader(resume)
    resume_text = " ".join([p.extract_text() for p in reader.pages if p.extract_text()])
    st.success("Resume loaded successfully!")

if st.button("▶ Start Interview") and resume_text:
    with st.spinner("AI is generating a question..."):
        prompt = f"Ask one professional interview question based on this resume:\n{resume_text[:2000]}"
        res = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}])
        st.session_state.question = res.choices[0].message.content
        st.session_state.transcript = None
        st.session_state.result = None
        speak(st.session_state.question)

if st.session_state.question:
    st.info(f"**Question:** {st.session_state.question}")
    
    st.write("### 🎤 Record Your Answer")
    audio_bytes = audio_recorder(text="Click to start speaking", pause_threshold=2.5)

    if audio_bytes:
        with st.spinner("Converting and transcribing audio..."):
            try:
                # CONVERSION LOGIC: Convert whatever the browser sends into a WAV file
                audio_file = io.BytesIO(audio_bytes)
                audio_segment = AudioSegment.from_file(audio_file)
                
                with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
                    audio_segment.export(f.name, format="wav")
                    
                    r = sr.Recognizer()
                    with sr.AudioFile(f.name) as source:
                        audio_recorded = r.record(source)
                        st.session_state.transcript = r.recognize_google(audio_recorded)
                        st.success("Answer Captured!")
                        st.write(f"**Your Answer:** {st.session_state.transcript}")
            except Exception as e:
                st.error(f"Transcription failed: Please ensure your mic is working and speak clearly.")

# Evaluation
if st.session_state.transcript and st.button("🛑 Stop & Evaluate"):
    with st.spinner("Analyzing performance..."):
        fillers, total_fillers = detect_fillers(st.session_state.transcript)
        eval_prompt = f"Question: {st.session_state.question}\nAnswer: {st.session_state.transcript}\nDetect filler words and score 1-10 with feedback."
        eval_res = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": eval_prompt}])
        st.session_state.result = eval_res.choices[0].message.content
        
        st.markdown("---")
        st.subheader("📊 AI Feedback")
        st.write(st.session_state.result)
        
        pdf_path = generate_pdf("AI Evaluated", total_fillers, st.session_state.result)
        with open(pdf_path, "rb") as f:
            st.download_button("📥 Download Interview Report", f, file_name="Report.pdf")
