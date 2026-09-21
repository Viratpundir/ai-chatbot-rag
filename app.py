import streamlit as st
from pathlib import Path
import streamlit.components.v1 as components


# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="AI Student Assistant",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="collapsed"
)


# ============================================================
# IMPORT YOUR RAG COMPONENTS
# ============================================================

from src.embeddings import get_embeddings
from src.llm import get_llm
from src.loader import load_documents
from src.rag_chain import build_rag_chain
from src.splitter import split_docs
from src.vector_store import create_vector_store


# ============================================================
# GLOBAL CSS
# ============================================================

st.markdown("""
<style>

#MainMenu {
    visibility: hidden;
}

footer {
    visibility: hidden;
}

header {
    background: transparent !important;
}

.stApp {
    background:
        radial-gradient(
            circle at 10% 10%,
            rgba(99,102,241,0.15),
            transparent 30%
        ),
        radial-gradient(
            circle at 90% 90%,
            rgba(20,184,166,0.10),
            transparent 30%
        ),
        #070a12;
}

.block-container {
    max-width: 1050px;
    padding-top: 40px;
    padding-bottom: 100px;
}


/* =========================================================
   HERO
========================================================= */

.hero-container {
    text-align: center;
    padding: 45px 20px 35px;
}

.hero-badge {
    display: inline-block;

    padding: 8px 16px;

    border-radius: 30px;

    background: rgba(99,102,241,0.12);

    border: 1px solid rgba(129,140,248,0.25);

    color: #a5b4fc;

    font-size: 13px;

    font-weight: 600;

    letter-spacing: 0.5px;

    margin-bottom: 20px;
}

.hero-title {
    font-size: 58px;

    font-weight: 800;

    letter-spacing: -2.5px;

    margin: 0;

    background:
        linear-gradient(
            90deg,
            #ffffff,
            #a5b4fc,
            #5eead4
        );

    -webkit-background-clip: text;

    -webkit-text-fill-color: transparent;
}

.hero-subtitle {
    color: #8993a7;

    font-size: 17px;

    margin-top: 16px;
}


/* =========================================================
   STATUS
========================================================= */

.status-container {

    display: flex;

    align-items: center;

    gap: 13px;

    padding: 17px 20px;

    background:
        rgba(17,24,39,0.75);

    border:
        1px solid rgba(255,255,255,0.07);

    border-radius: 18px;

    margin-bottom: 28px;
}

.status-dot {

    width: 11px;

    height: 11px;

    border-radius: 50%;

    background: #4ade80;

    box-shadow:
        0 0 0 5px rgba(74,222,128,0.08),
        0 0 18px rgba(74,222,128,0.7);

    animation: pulse 2s infinite;
}

@keyframes pulse {

    0%,100% {
        transform: scale(1);
    }

    50% {
        transform: scale(1.3);
    }

}

.status-title {

    color: #f3f4f6;

    font-weight: 700;

    font-size: 15px;
}

.status-subtitle {

    color: #778197;

    font-size: 12px;

    margin-top: 3px;
}


/* =========================================================
   QUESTION
========================================================= */

.question-title {

    color: #d7dce7;

    font-size: 14px;

    font-weight: 600;

    margin-bottom: 8px;
}

div[data-baseweb="input"] {

    background: #111622 !important;

    border:
        1px solid #252d3e !important;

    border-radius: 16px !important;

    min-height: 55px;
}

div[data-baseweb="input"]:focus-within {

    border-color: #6366f1 !important;

    box-shadow:
        0 0 0 3px rgba(99,102,241,0.12);
}

div[data-baseweb="input"] input {

    color: #f8fafc !important;

    font-size: 16px !important;
}


/* =========================================================
   BUTTON
========================================================= */

.stButton > button {

    border: none !important;

    border-radius: 13px !important;

    padding: 11px 25px !important;

    background:
        linear-gradient(
            135deg,
            #6366f1,
            #4f46e5
        ) !important;

    color: white !important;

    font-weight: 700 !important;

    transition: all 0.25s ease !important;
}

.stButton > button:hover {

    transform: translateY(-2px);

    box-shadow:
        0 10px 30px rgba(99,102,241,0.3);
}


/* =========================================================
   RESPONSE
========================================================= */

.response-card {

    margin-top: 30px;

    padding: 25px;

    border-radius: 20px;

    background:
        linear-gradient(
            145deg,
            rgba(18,24,38,0.95),
            rgba(10,14,23,0.95)
        );

    border:
        1px solid rgba(255,255,255,0.07);

    animation:
        responseAppear 0.4s ease;
}

@keyframes responseAppear {

    from {
        opacity: 0;
        transform: translateY(12px);
    }

    to {
        opacity: 1;
        transform: translateY(0);
    }

}

.response-label {

    color: #a5b4fc;

    font-size: 12px;

    font-weight: 700;

    letter-spacing: 0.7px;

    margin-bottom: 12px;
}

.response-text {

    color: #e5e7eb;

    font-size: 16px;

    line-height: 1.8;
}


/* =========================================================
   FEATURE CARDS
========================================================= */

.features {

    display: grid;

    grid-template-columns:
        repeat(3, 1fr);

    gap: 15px;

    margin-top: 35px;
}

.feature-card {

    padding: 22px;

    border-radius: 18px;

    background:
        rgba(17,24,39,0.7);

    border:
        1px solid rgba(255,255,255,0.06);

    transition: all 0.25s ease;
}

.feature-card:hover {

    transform: translateY(-5px);

    border-color:
        rgba(99,102,241,0.35);

    background:
        rgba(23,30,48,0.9);
}

.feature-icon {

    font-size: 27px;

    margin-bottom: 12px;
}

.feature-title {

    color: white;

    font-weight: 700;

    font-size: 15px;

    margin-bottom: 7px;
}

.feature-text {

    color: #7d8799;

    font-size: 13px;

    line-height: 1.6;
}


@media(max-width: 700px) {

    .hero-title {
        font-size: 40px;
    }

    .features {
        grid-template-columns: 1fr;
    }

}

</style>
""", unsafe_allow_html=True)


# ============================================================
# HERO
# ============================================================

st.markdown("""
<div class="hero-container">

    <div class="hero-badge">
        ✦ AI POWERED • RAG ASSISTANT
    </div>

    <h1 class="hero-title">
        AI Student Assistant
    </h1>

    <p class="hero-subtitle">
        Ask questions from your documents using Retrieval-Augmented Generation.
    </p>

</div>
""", unsafe_allow_html=True)


# ============================================================
# STATUS
# ============================================================

st.markdown("""
<div class="status-container">

    <div class="status-dot"></div>

    <div>

        <div class="status-title">
            AI Assistant Online
        </div>

        <div class="status-subtitle">
            Connected to your local RAG pipeline
        </div>

    </div>

</div>
""", unsafe_allow_html=True)


# ============================================================
# QUESTION
# ============================================================

st.markdown("""
<div class="question-title">
    💬 Ask your document anything
</div>
""", unsafe_allow_html=True)


question = st.text_input(
    "question",
    placeholder="e.g. What are the main concepts explained in this document?",
    label_visibility="collapsed"
)


ask = st.button("Ask AI →")


# ============================================================
# RAG
# ============================================================

if ask:

    if not question.strip():

        st.warning("Please enter a question first.")

    else:

        with st.spinner("🤖 Thinking..."):

            try:

                BASE_DIR = Path(__file__).resolve().parent

                PDF_PATH = (
                    BASE_DIR /
                    "data" /
                    "sample.pdf"
                )

                documents = load_documents(
                    str(PDF_PATH)
                )

                chunks = split_docs(
                    documents
                )

                embeddings = get_embeddings()

                vector_store = create_vector_store(
                    chunks,
                    embeddings
                )

                llm = get_llm()

                rag_chain = build_rag_chain(
                    llm,
                    vector_store
                )

                answer = rag_chain.invoke(
                    question
                )

                st.markdown(
                    f"""
                    <div class="response-card">

                        <div class="response-label">
                            🤖 AI RESPONSE
                        </div>

                        <div class="response-text">
                            {answer}
                        </div>

                    </div>
                    """,
                    unsafe_allow_html=True
                )

            except Exception as e:

                st.error(
                    f"Error: {str(e)}"
                )


# ============================================================
# FEATURES
# ============================================================

st.markdown("""
<div class="features">

    <div class="feature-card">

        <div class="feature-icon">
            📚
        </div>

        <div class="feature-title">
            Document Aware
        </div>

        <div class="feature-text">
            Answers are generated from information
            retrieved directly from your documents.
        </div>

    </div>


    <div class="feature-card">

        <div class="feature-icon">
            🧠
        </div>

        <div class="feature-title">
            RAG Powered
        </div>

        <div class="feature-text">
            Combines semantic search with an AI
            language model for contextual answers.
        </div>

    </div>


    <div class="feature-card">

        <div class="feature-icon">
            ⚡
        </div>

        <div class="feature-title">
            Local AI
        </div>

        <div class="feature-text">
            Runs with your local Ollama-based AI
            setup for private document interaction.
        </div>

    </div>

</div>
""", unsafe_allow_html=True)


# ============================================================
# FLOATING AI BOT
# ============================================================

components.html("""

<style>

#ai-bot {

    position: fixed;

    right: 30px;

    bottom: 30px;

    width: 82px;

    height: 82px;

    border-radius: 50%;

    background:
        radial-gradient(
            circle at 30% 25%,
            #ffffff,
            #a5b4fc 25%,
            #6366f1 60%,
            #312e81
        );

    border:
        3px solid rgba(255,255,255,0.3);

    box-shadow:
        0 15px 45px rgba(79,70,229,0.45);

    cursor: grab;

    z-index: 99999;

    animation:
        botFloat 3s ease-in-out infinite;

    user-select: none;

}

@keyframes botFloat {

    0%,100% {
        transform: translateY(0);
    }

    50% {
        transform: translateY(-8px);
    }

}

.bot-face {

    position: absolute;

    width: 54px;

    height: 45px;

    left: 50%;

    top: 50%;

    transform:
        translate(-50%, -50%);

    border-radius: 18px;

    background:
        linear-gradient(
            145deg,
            #111827,
            #1e293b
        );

    border:
        1px solid rgba(255,255,255,0.2);

}

.bot-eye {

    position: absolute;

    top: 13px;

    width: 8px;

    height: 11px;

    border-radius: 50%;

    background: #67e8f9;

    box-shadow:
        0 0 10px #67e8f9;

    animation:
        blink 4s infinite;

}

.bot-eye.left {
    left: 14px;
}

.bot-eye.right {
    right: 14px;
}

@keyframes blink {

    0%,95%,100% {
        transform: scaleY(1);
    }

    97% {
        transform: scaleY(0.1);
    }

}

.bot-mouth {

    position: absolute;

    bottom: 9px;

    left: 50%;

    width: 16px;

    height: 7px;

    transform:
        translateX(-50%);

    border-bottom:
        2px solid #67e8f9;

    border-radius: 50%;

}

#bot-message {

    position: fixed;

    right: 125px;

    bottom: 55px;

    max-width: 220px;

    padding: 13px 17px;

    border-radius:
        16px 16px 4px 16px;

    background:
        rgba(17,24,39,0.97);

    color: white;

    border:
        1px solid rgba(255,255,255,0.1);

    font-family:
        Arial, sans-serif;

    font-size: 14px;

    box-shadow:
        0 12px 35px rgba(0,0,0,0.35);

    opacity: 0;

    transform:
        translateY(10px);

    transition:
        all .25s ease;

    pointer-events: none;

}

#bot-message.show {

    opacity: 1;

    transform:
        translateY(0);

}

</style>


<div id="ai-bot">

    <div class="bot-face">

        <div class="bot-eye left"></div>

        <div class="bot-eye right"></div>

        <div class="bot-mouth"></div>

    </div>

</div>


<div id="bot-message">
    Ask me a question 👋
</div>


<script>

const bot =
    document.getElementById("ai-bot");

const message =
    document.getElementById("bot-message");

let dragging = false;

let startX = 0;

let startY = 0;

let moved = false;


bot.addEventListener(
    "pointerdown",
    function(event) {

        dragging = true;

        moved = false;

        const rect =
            bot.getBoundingClientRect();

        startX =
            event.clientX - rect.left;

        startY =
            event.clientY - rect.top;

        bot.setPointerCapture(
            event.pointerId
        );

        bot.style.animation =
            "none";

    }
);


bot.addEventListener(
    "pointermove",
    function(event) {

        if (!dragging) {
            return;
        }

        moved = true;

        let x =
            event.clientX - startX;

        let y =
            event.clientY - startY;

        const maxX =
            window.innerWidth -
            bot.offsetWidth;

        const maxY =
            window.innerHeight -
            bot.offsetHeight;

        x =
            Math.max(
                5,
                Math.min(x, maxX - 5)
            );

        y =
            Math.max(
                5,
                Math.min(y, maxY - 5)
            );

        bot.style.left =
            x + "px";

        bot.style.top =
            y + "px";

        bot.style.right =
            "auto";

        bot.style.bottom =
            "auto";

    }
);


bot.addEventListener(
    "pointerup",
    function() {

        dragging = false;

        bot.style.animation =
            "botFloat 3s ease-in-out infinite";

        if (!moved) {

            message.classList.add(
                "show"
            );

            setTimeout(
                function() {

                    message.classList.remove(
                        "show"
                    );

                },
                3000
            );

        }

    }
);

</script>

""", height=1)