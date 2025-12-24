import streamlit as st
import PyPDF2
import speech_recognition as sr
import tempfile
import base64
import os
from gtts import gTTS
from audio_recorder_streamlit import audio_recorder
from openai import OpenAI
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet

# -----------------------------------
# 1. CONFIG & API SETUP
# -----------------------------------
# On Streamlit Cloud, st.secrets handles the API key automatically
try:
    client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
except Exception:
    st.error("OpenAI API Key not found. Please add it to Streamlit Secrets.")

st.set_page_config(page_title="AI Interview Pro", layout="centered")

# -----------------------------------
# 2. SESSION STATE (Memory)
# -----------------------------------
# This prevents the app from "forgetting" your progress when the screen refreshes
if "question" not in st.session_state: st.session_state.question = None
if "transcript" not in st.session_state: st.session_state.transcript = None
if "result" not in st.session_state: st.session_state.result = None

# -----------------------------------
# 3. UTILITY FUNCTIONS
# -----------------------------------
def speak(text):
    """Converts text to speech and plays it in the browser."""
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
    """Checks for common interview filler words."""
    fillers = ["uh", "um", "er", "ah", "you know", "like"]
    found = {}
    lower_text = text.lower()
    for f in fillers:
        count = lower_text.count(f)
        if count > 0:
            found[f] = count
    return found, sum(found.values())

def generate_pdf(score_text, filler_count, feedback):
    """Creates a downloadable PDF report."""
    path = "Interview_Report.pdf"
    doc = SimpleDocTemplate(path, pagesize=letter)
    styles = getSampleStyleSheet()
    elements = []

    elements.append(Paragraph("AI Interview Analysis Report", styles["Title"]))
    elements.append(Spacer(1, 12))

    # Summary Table
    data = [
        ["Metric", "Result"],
        ["Final Score", score_text],
        ["Filler Words Count", str(filler_count)]
    ]
    table = Table(data, colWidths=[150, 300])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    
    elements.append(table)
    elements.append(Spacer(1, 24))
    elements.append(Paragraph("Detailed AI Feedback:", styles["Heading2"]))
    elements.append(Paragraph(feedback, styles["Normal"]))
    
    doc.build(elements)
    return path

# -----------------------------------
# 4. APP UI
# -----------------------------------
st.title("🎤 AI Interview Pro")
st.caption("Upload your resume and practice with AI-generated behavioral questions.")

# Custom CSS for the Results Cards
st.markdown("""
<style>
    .metric-card {
        background-color: #1e293b;
        padding: 20px;
        border-radius: 10px;
        text-align: center;
        color: white;
    }
</style>
""", unsafe_allow_html=True)

# Step 1: Resume Upload
resume = st.file_uploader("📄 Upload Resume (PDF)", type="pdf")
resume_text = ""

if resume:
    reader = PyPDF2.PdfReader(resume)
    resume_text = " ".join([p.extract_text() for p in reader.pages if p.extract_text()])
    st.success("Resume loaded! Ready to start.")

# Step 2: Start Interview
if st.button("▶ Start Interview") and resume_text:
    with st.spinner("AI is reading your resume..."):
        prompt = f"Ask one tough behavioral interview question based on this resume:\n{resume_text[:2000]}"
        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )
        st.session_state.question = res.choices[0].message.content
        st.session_state.transcript = None # Clear previous answer
        speak(st.session_state.question)

# Step 3: Question and Microphone
if st.session_state.question:
    st.info(f"**Question:** {st.session_state.question}")
    
    st.write("### 🎤 Record Your Answer")
    # This widget handles the browser microphone
    audio_data = audio_recorder(text="Click to speak", pause_threshold=2.0)

    if audio_data:
        with st.spinner("Transcribing..."):
            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
                f.write(audio_data)
                r = sr.Recognizer()
                with sr.AudioFile(f.name) as source:
                    audio_recorded = r.record(source)
                    try:
                        st.session_state.transcript = r.recognize_google(audio_recorded)
                        st.success("Answer Captured!")
                        st.write(f"**Your Answer:** {st.session_state.transcript}")
                    except:
                        st.error("Could not understand audio. Please try speaking louder.")

# Step 4: Evaluate
if st.session_state.transcript and st.button("🛑 Stop & Evaluate"):
    with st.spinner("AI is analyzing your response..."):
        fillers, total_fillers = detect_fillers(st.session_state.transcript)
        
        eval_prompt = f"""
        Question: {st.session_state.question}
        Answer: {st.session_state.transcript}
        Filler words detected: {fillers}
        
        Please provide:
        1. A score out of 10.
        2. Constructive feedback on clarity and content.
        3. An improved version of this answer.
        """
        
        eval_res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": eval_prompt}]
        )
        st.session_state.result = eval_res.choices[0].message.content
        
        # Display Results
        st.markdown("---")
        st.subheader("📊 Performance Summary")
        c1, c2 = st.columns(2)
        with c1:
            st.markdown(f'<div class="metric-card"><h2>{total_fillers}</h2>Filler Words</div>', unsafe_allow_html=True)
        with c2:
            st.markdown(f'<div class="metric-card"><h2>GPT-Powered</h2>Analysis Ready</div>', unsafe_allow_html=True)
            
        st.markdown("### 🧠 Detailed Feedback")
        st.write(st.session_state.result)
        
        # PDF Generation
        pdf_path = generate_pdf("See Feedback Below", total_fillers, st.session_state.result)
        with open(pdf_path, "rb") as f:
            st.download_button("📥 Download Report", f, file_name="Interview_Analysis.pdf")
