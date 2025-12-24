import streamlit as st
import PyPDF2
import speech_recognition as sr
import tempfile
import base64
from gtts import gTTS
from audio_recorder_streamlit import audio_recorder
from dotenv import load_dotenv
from openai import OpenAI
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet

# -----------------------------------
# CONFIG
# -----------------------------------
load_dotenv()
client = OpenAI()

st.set_page_config("AI Interview Pro", layout="centered")

# -----------------------------------
# SESSION STATE
# -----------------------------------
for k in ["question", "transcript", "result"]:
    if k not in st.session_state:
        st.session_state[k] = None

# -----------------------------------
# UTIL FUNCTIONS
# -----------------------------------
def speak(text):
    tts = gTTS(text=text)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
        tts.save(f.name)
        audio = base64.b64encode(open(f.name, "rb").read()).decode()
        st.markdown(
            f'<audio autoplay src="data:audio/mp3;base64,{audio}"></audio>',
            unsafe_allow_html=True
        )

def detect_fillers(text):
    fillers = ["uh", "um", "er", "ah", "you know", "like", "hmm"]
    found = {}
    lower = text.lower()

    for f in fillers:
        count = lower.count(f)
        if count > 0:
            found[f] = count

    return found, sum(found.values())

def generate_pdf(score, fillers, feedback):
    doc = SimpleDocTemplate("Interview_Report.pdf", pagesize=letter)
    styles = getSampleStyleSheet()
    elements = []

    elements.append(Paragraph("AI Interview Feedback Report", styles["Title"]))
    elements.append(Spacer(1, 20))

    table = Table([
        ["Metric", "Value"],
        ["Final Score", score],
        ["Filler Words Used", str(fillers)]
    ])

    table.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), 1, colors.black),
        ("BACKGROUND", (0,0), (-1,0), colors.lightblue)
    ]))

    elements.append(table)
    elements.append(Spacer(1, 20))
    elements.append(Paragraph("AI Feedback:", styles["Heading2"]))
    elements.append(Paragraph(feedback, styles["Normal"]))

    doc.build(elements)

# -----------------------------------
# UI STYLES
# -----------------------------------
st.markdown("""
<style>
.card {
    background-color:#0f172a;
    padding:20px;
    border-radius:15px;
    color:white;
    margin-bottom:15px;
}
.big {
    font-size:28px;
    font-weight:bold;
}
</style>
""", unsafe_allow_html=True)

# -----------------------------------
# APP UI
# -----------------------------------
st.title("🎤 AI Interview Pro")
st.caption("Voice-based interview • Smart scoring • Filler detection")

# -----------------------------------
# RESUME UPLOAD
# -----------------------------------
resume = st.file_uploader("📄 Upload Resume (PDF)", type="pdf")
if resume:
    reader = PyPDF2.PdfReader(resume)
    resume_text = " ".join([p.extract_text() for p in reader.pages])
    st.success("Resume loaded successfully")

# -----------------------------------
# START INTERVIEW
# -----------------------------------
if st.button("▶ Start Interview") and resume:
    q_prompt = f"Ask one professional interview question based on this resume:\n{resume_text[:2000]}"
    res = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": q_prompt}]
    )
    st.session_state.question = res.choices[0].message.content
    speak(st.session_state.question)

# -----------------------------------
# QUESTION DISPLAY
# -----------------------------------
if st.session_state.question:
    st.markdown("### 🧠 Interview Question")
    st.info(st.session_state.question)

    st.markdown("### 🎤 Answer using Mic")
    audio = audio_recorder("Speak your answer", pause_threshold=2.0)

    if audio:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
            f.write(audio)
            r = sr.Recognizer()
            with sr.AudioFile(f.name) as src:
                audio_data = r.record(src)
                try:
                    st.session_state.transcript = r.recognize_google(audio_data)
                    st.success("Answer recorded successfully")
                    st.write("📝 **Your Answer:**")
                    st.write(st.session_state.transcript)
                except:
                    st.error("Speech recognition failed")

# -----------------------------------
# STOP & EVALUATE
# -----------------------------------
if st.session_state.transcript and st.button("🛑 Stop & Evaluate"):
    fillers, filler_count = detect_fillers(st.session_state.transcript)

    eval_prompt = f"""
Interview Question: {st.session_state.question}
Candidate Answer: {st.session_state.transcript}

Filler words used: {fillers}

Generate an ideal answer, compare both, penalize filler words, and give a final score out of 10 with explanation.
"""

    res = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": eval_prompt}]
    )

    st.session_state.result = res.choices[0].message.content

    # -----------------------------------
    # RESULTS
    # -----------------------------------
    st.markdown("## 📊 Interview Result")

    col1, col2 = st.columns(2)

    col1.markdown(f"""
    <div class="card">
        <div class="big">{filler_count}</div>
        Filler Words Used
    </div>
    """, unsafe_allow_html=True)

    col2.markdown(f"""
    <div class="card">
        <div class="big">Score / 10</div>
        Based on content & clarity
    </div>
    """, unsafe_allow_html=True)

    st.markdown("### 🧠 AI Feedback")
    st.write(st.session_state.result)

    generate_pdf("Out of 10", filler_count, st.session_state.result)
    with open("Interview_Report.pdf", "rb") as f:
        st.download_button("📄 Download PDF Report", f)
