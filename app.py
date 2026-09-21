import streamlit as st
import streamlit.components.v1 as components
from pathlib import Path

from src.embeddings import get_embeddings
from src.llm import get_llm
from src.loader import load_documents
from src.rag_chain import build_rag_chain
from src.splitter import split_docs
from src.vector_store import create_vector_store


# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="AI RAG Assistant",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="collapsed"
)


# ============================================================
# CUSTOM CSS
# ============================================================

st.markdown("""
<style>

    /* -------------------------------
       GLOBAL
    --------------------------------*/

    .stApp {
        background:
            radial-gradient(
                circle at 20% 10%,
                rgba(75, 85, 200, 0.12),
                transparent 35%
            ),
            radial-gradient(
                circle at 80% 80%,
                rgba(0, 200, 180, 0.08),
                transparent 35%
            ),
            #080b12;
        color: #f5f7fb;
    }

    #MainMenu {
        visibility: hidden;
    }

    footer {
        visibility: hidden;
    }

    header {
        background: transparent !important;
    }

    /* -------------------------------
       MAIN CONTAINER
    --------------------------------*/

    .block-container {
        max-width: 1100px;
        padding-top: 3rem;
        padding-bottom: 5rem;
    }

    /* -------------------------------
       HERO
    --------------------------------*/

    .hero {
        text-align: center;
        padding: 35px 20px 20px;
    }

    .hero-badge {
        display: inline-block;
        padding: 8px 15px;
        border-radius: 30px;

        background: rgba(110, 120, 255, 0.10);
        border: 1px solid rgba(110, 120, 255, 0.25);

        color: #9da7ff;
        font-size: 13px;
        font-weight: 600;

        margin-bottom: 18px;
    }

    .hero h1 {
        font-size: clamp(38px, 6vw, 65px);
        font-weight: 800;
        letter-spacing: -2px;

        margin: 0;

        background: linear-gradient(
            90deg,
            #ffffff,
            #aeb8ff,
            #72e5d1
        );

        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }

    .hero p {
        color: #8991a3;
        font-size: 17px;
        margin-top: 15px;
    }

    /* -------------------------------
       STATUS
    --------------------------------*/

    .status-card {
        display: flex;
        align-items: center;
        gap: 12px;

        padding: 15px 18px;

        border-radius: 16px;

        background: rgba(19, 25, 38, 0.75);
        border: 1px solid rgba(255,255,255,0.07);

        margin: 20px 0 25px;
    }

    .status-dot {
        width: 10px;
        height: 10px;

        border-radius: 50%;

        background: #4ade80;

        box-shadow:
            0 0 0 5px rgba(74,222,128,0.10),
            0 0 15px rgba(74,222,128,0.65);

        animation: pulse 2s infinite;
    }

    @keyframes pulse {

        0% {
            transform: scale(1);
            opacity: 1;
        }

        50% {
            transform: scale(1.25);
            opacity: .7;
        }

        100% {
            transform: scale(1);
            opacity: 1;
        }

    }

    /* -------------------------------
       QUESTION CARD
    --------------------------------*/

    .question-label {
        color: #a8b0c2;
        font-size: 14px;
        font-weight: 600;

        margin-bottom: 8px;
    }

    /* Streamlit input */

    div[data-baseweb="input"] {
        background: #111622 !important;
        border: 1px solid #252d3e !important;

        border-radius: 16px !important;

        min-height: 55px;
    }

    div[data-baseweb="input"]:focus-within {
        border-color: #6976ff !important;

        box-shadow:
            0 0 0 3px rgba(105,118,255,.12);
    }

    div[data-baseweb="input"] input {
        color: white !important;
        font-size: 16px !important;
    }

    /* -------------------------------
       BUTTON
    --------------------------------*/

    div.stButton > button {

        border: 0;

        border-radius: 14px;

        background:
            linear-gradient(
                135deg,
                #6976ff,
                #5a63e8
            );

        color: white;

        font-weight: 700;

        padding: 12px 25px;

        transition: all .2s ease;
    }

    div.stButton > button:hover {

        transform: translateY(-2px);

        box-shadow:
            0 10px 30px rgba(105,118,255,.25);
    }

    /* -------------------------------
       RESPONSE
    --------------------------------*/

    .response-card {

        margin-top: 25px;

        padding: 25px;

        border-radius: 20px;

        background:
            linear-gradient(
                145deg,
                rgba(19,25,38,.95),
                rgba(12,16,25,.95)
            );

        border: 1px solid rgba(255,255,255,.07);

        animation: appear .35s ease;
    }

    @keyframes appear {

        from {
            opacity: 0;
            transform: translateY(10px);
        }

        to {
            opacity: 1;
            transform: translateY(0);
        }

    }

    /* -------------------------------
       FEATURE CARDS
    --------------------------------*/

    .feature-card {

        padding: 20px;

        border-radius: 18px;

        background: rgba(17,22,34,.75);

        border:
            1px solid rgba(255,255,255,.06);

        transition: .25s ease;
    }

    .feature-card:hover {

        transform: translateY(-4px);

        border-color:
            rgba(110,120,255,.3);

        background:
            rgba(25,31,46,.9);
    }

    .feature-icon {

        font-size: 25px;

        margin-bottom: 10px;
    }

    .feature-title {

        font-weight: 700;

        color: white;

        margin-bottom: 5px;
    }

    .feature-text {

        color: #7f899c;

        font-size: 13px;
        line-height: 1.5;
    }

    /* -------------------------------
       MOBILE
    --------------------------------*/

    @media(max-width: 700px) {

        .block-container {
            padding-left: 15px;
            padding-right: 15px;
        }

        .hero {
            padding-top: 20px;
        }

        .hero h1 {
            font-size: 40px;
        }

    }

</style>
""", unsafe_allow_html=True)


# ============================================================
# FLOATING DRAGGABLE BOT
# ============================================================

components.html(
"""
<!DOCTYPE html>

<html>

<head>

<style>

* {
    box-sizing: border-box;
}

body {
    margin: 0;
    background: transparent;
    overflow: hidden;
    font-family: Inter, Arial, sans-serif;
}


/* -----------------------------
   BOT
------------------------------*/

#bot {

    position: fixed;

    right: 35px;
    bottom: 35px;

    width: 90px;
    height: 90px;

    border-radius: 50%;

    cursor: grab;

    user-select: none;

    z-index: 999999;

    background:
        radial-gradient(
            circle at 30% 25%,
            #ffffff,
            #9ca6ff 25%,
            #636df4 55%,
            #343ca0
        );

    border:
        3px solid rgba(255,255,255,.35);

    box-shadow:

        0 15px 45px
        rgba(80,90,255,.35),

        0 0 0 8px
        rgba(105,118,255,.06);

    animation: floating 3s ease-in-out infinite;

    transition:
        transform .25s ease,
        box-shadow .25s ease;
}


/* -----------------------------
   BOT GLOW
------------------------------*/

#bot::before {

    content: "";

    position: absolute;

    inset: -12px;

    border-radius: 50%;

    border:
        1px solid
        rgba(110,120,255,.20);

    animation:
        botGlow 2.5s infinite;
}


@keyframes botGlow {

    0% {
        transform: scale(.9);
        opacity: .4;
    }

    50% {
        transform: scale(1.15);
        opacity: .05;
    }

    100% {
        transform: scale(.9);
        opacity: .4;
    }

}


/* -----------------------------
   FLOAT
------------------------------*/

@keyframes floating {

    0%,100% {
        transform: translateY(0);
    }

    50% {
        transform: translateY(-9px);
    }

}


/* -----------------------------
   BOT FACE
------------------------------*/

.face {

    position: absolute;

    left: 50%;
    top: 50%;

    transform:
        translate(-50%, -50%);

    width: 58px;
    height: 48px;

    border-radius: 20px;

    background:
        linear-gradient(
            145deg,
            #11162a,
            #1d2440
        );

    border:
        1px solid
        rgba(255,255,255,.18);

}


/* eyes */

.eye {

    position: absolute;

    top: 14px;

    width: 8px;
    height: 12px;

    border-radius: 50%;

    background: #8fffee;

    box-shadow:
        0 0 10px
        rgba(143,255,238,.9);

    animation:
        blink 4s infinite;
}


.eye.left {
    left: 15px;
}

.eye.right {
    right: 15px;
}


@keyframes blink {

    0%, 94%, 100% {
        transform: scaleY(1);
    }

    96% {
        transform: scaleY(.08);
    }

}


/* mouth */

.mouth {

    position: absolute;

    width: 17px;
    height: 7px;

    left: 50%;
    bottom: 9px;

    transform:
        translateX(-50%);

    border-bottom:
        2px solid #8fffee;

    border-radius: 50%;

}


/* -----------------------------
   SPEECH BUBBLE
------------------------------*/

#bubble {

    position: fixed;

    right: 135px;
    bottom: 55px;

    max-width: 230px;

    padding: 13px 17px;

    border-radius: 15px 15px 4px 15px;

    background:
        rgba(17,22,34,.96);

    color: white;

    font-size: 14px;

    line-height: 1.4;

    border:
        1px solid
        rgba(255,255,255,.10);

    box-shadow:
        0 10px 35px
        rgba(0,0,0,.35);

    opacity: 0;

    transform:
        translateY(8px)
        scale(.95);

    pointer-events: none;

    transition:
        .25s ease;

}


/* -----------------------------
   ACTIVE
------------------------------*/

#bot.active {

    cursor: grabbing;

    transform:
        scale(1.08);

    box-shadow:

        0 20px 55px
        rgba(80,90,255,.55),

        0 0 0 12px
        rgba(105,118,255,.08);
}


#bot.active + #bubble {

    opacity: 1;

    transform:
        translateY(0)
        scale(1);

}


/* -----------------------------
   DRAG HINT
------------------------------*/

#hint {

    position: fixed;

    right: 30px;
    bottom: 130px;

    color:
        rgba(255,255,255,.45);

    font-size: 11px;

    opacity: .8;

}

</style>

</head>


<body>


<div id="bot">

    <div class="face">

        <div class="eye left"></div>

        <div class="eye right"></div>

        <div class="mouth"></div>

    </div>

</div>


<div id="bubble">
    Ask me a question 👋
</div>


<div id="hint">
    Drag me anywhere
</div>


<script>

const bot =
    document.getElementById("bot");

const bubble =
    document.getElementById("bubble");

let dragging = false;

let offsetX = 0;
let offsetY = 0;

let moved = false;


/* --------------------------------
   POINTER DOWN
---------------------------------*/

bot.addEventListener(
    "pointerdown",
    function(e) {

        dragging = true;

        moved = false;

        bot.setPointerCapture(
            e.pointerId
        );

        const rect =
            bot.getBoundingClientRect();

        offsetX =
            e.clientX - rect.left;

        offsetY =
            e.clientY - rect.top;

        bot.classList.add(
            "active"
        );

        e.preventDefault();

    }
);


/* --------------------------------
   POINTER MOVE
---------------------------------*/

bot.addEventListener(
    "pointermove",
    function(e) {

        if (!dragging) return;

        moved = true;

        let x =
            e.clientX - offsetX;

        let y =
            e.clientY - offsetY;


        const maxX =
            window.innerWidth -
            bot.offsetWidth -
            10;

        const maxY =
            window.innerHeight -
            bot.offsetHeight -
            10;


        x =
            Math.max(
                10,
                Math.min(x, maxX)
            );

        y =
            Math.max(
                10,
                Math.min(y, maxY)
            );


        bot.style.left =
            x + "px";

        bot.style.top =
            y + "px";

        bot.style.right =
            "auto";

        bot.style.bottom =
            "auto";


        bubble.style.left =
            Math.max(
                10,
                x - 240
            ) + "px";

        bubble.style.top =
            Math.max(
                10,
                y + 10
            ) + "px";

        bubble.style.right =
            "auto";

        bubble.style.bottom =
            "auto";


        e.preventDefault();

    }
);


/* --------------------------------
   POINTER UP
---------------------------------*/

bot.addEventListener(
    "pointerup",
    function(e) {

        dragging = false;

        bot.classList.remove(
            "active"
        );


        if (!moved) {

            bubble.style.opacity =
                "1";

            bubble.style.transform =
                "translateY(0) scale(1)";


            bubble.innerHTML =
                "Ask me a question 👋";


            setTimeout(() => {

                bubble.style.opacity =
                    "0";

                bubble.style.transform =
                    "translateY(8px) scale(.95)";

            }, 3000);

        }

    }
);

</script>

</body>

</html>
""",
height=1,
)


# ============================================================
# HERO
# ============================================================

st.markdown(
"""
<div class="hero">

    <div class="hero-badge">
        ✦ AI POWERED • RAG ASSISTANT
    </div>

    <h1>AI Student Assistant</h1>

    <p>
        Ask questions from your documents using Retrieval-Augmented Generation.
    </p>

</div>
""",
unsafe_allow_html=True
)


# ============================================================
# STATUS
# ============================================================

st.markdown(
"""
<div class="status-card">

    <div class="status-dot"></div>

    <div>
        <strong>AI Assistant Online</strong>
        <div style="color:#778197;font-size:12px;">
            Connected to your local RAG pipeline
        </div>
    </div>

</div>
""",
unsafe_allow_html=True
)


# ============================================================
# PDF INFO
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

PDF_PATH = (
    BASE_DIR /
    "data" /
    "sample.pdf"
)


# ============================================================
# QUESTION
# ============================================================

st.markdown(
"""
<div class="question-label">
    💬 Ask your document anything
</div>
""",
unsafe_allow_html=True
)


question = st.text_input(
    "",
    placeholder="e.g. What are the main concepts explained in this document?",
    label_visibility="collapsed"
)


ask = st.button(
    "Ask AI  →",
    use_container_width=False
)


# ============================================================
# RAG PIPELINE
# ============================================================

if ask and question.strip():

    with st.spinner("Thinking..."):

        try:

            # Load PDF
            documents = load_documents(
                str(PDF_PATH)
            )

            # Split documents
            chunks = split_docs(
                documents
            )

            # Embeddings
            embeddings = get_embeddings()

            # Vector database
            vector_store = create_vector_store(
                chunks,
                embeddings
            )

            # LLM
            llm = get_llm()

            # RAG chain
            rag_chain = build_rag_chain(
                llm,
                vector_store
            )

            # Ask
            answer = rag_chain.invoke(
                question
            )


            # -------------------------
            # RESPONSE
            # -------------------------

            st.markdown(
                f"""
                <div class="response-card">

                    <div style="
                        color:#8994ff;
                        font-size:13px;
                        font-weight:700;
                        margin-bottom:12px;
                    ">
                        🤖 AI RESPONSE
                    </div>

                    <div style="
                        color:#e6e9f0;
                        font-size:16px;
                        line-height:1.8;
                    ">
                        {answer}
                    </div>

                </div>
                """,
                unsafe_allow_html=True
            )


        except Exception as e:

            st.error(
                f"Something went wrong: {str(e)}"
            )


elif ask:

    st.warning(
        "Please enter a question first."
    )


# ============================================================
# FEATURES
# ============================================================

st.markdown(
"""
<br>

<div style="
    display:grid;
    grid-template-columns:
        repeat(auto-fit,minmax(220px,1fr));
    gap:15px;
">

    <div class="feature-card">

        <div class="feature-icon">
            📚
        </div>

        <div class="feature-title">
            Document Aware
        </div>

        <div class="feature-text">
            Answers are generated using information
            retrieved directly from your PDF.
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
            Combines semantic search with an AI language
            model for contextual answers.
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
            Your current setup can run with a local
            Ollama model.
        </div>

    </div>

</div>
""",
unsafe_allow_html=True
)