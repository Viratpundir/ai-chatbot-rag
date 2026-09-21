import streamlit as st
import streamlit.components.v1 as components
from pathlib import Path


# ============================================================
# PAGE CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="AI Student Assistant",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="collapsed"
)


# ============================================================
# YOUR EXISTING RAG IMPORTS
# ============================================================

from src.embeddings import get_embeddings
from src.llm import get_llm
from src.loader import load_documents
from src.rag_chain import build_rag_chain
from src.splitter import split_docs
from src.vector_store import create_vector_store


# ============================================================
# GLOBAL STREAMLIT CSS
# ============================================================

st.markdown(
    """
    <style>

    /* ========================================================
       REMOVE STREAMLIT DEFAULT UI
    ======================================================== */

    #MainMenu {
        visibility: hidden;
    }

    footer {
        visibility: hidden;
    }

    header {
        background: transparent !important;
    }

    [data-testid="stHeader"] {
        background: transparent !important;
    }


    /* ========================================================
       MAIN BACKGROUND
    ======================================================== */

    .stApp {

        background:
            radial-gradient(
                circle at 10% 10%,
                rgba(99, 102, 241, 0.16),
                transparent 32%
            ),

            radial-gradient(
                circle at 90% 85%,
                rgba(20, 184, 166, 0.10),
                transparent 30%
            ),

            linear-gradient(
                135deg,
                #060810 0%,
                #090d18 50%,
                #05070d 100%
            );

        color: #f8fafc;

    }


    /* ========================================================
       MAIN CONTENT WIDTH
    ======================================================== */

    .block-container {

        max-width: 1100px;

        padding-top: 35px;
        padding-bottom: 100px;

    }


    /* ========================================================
       HERO
    ======================================================== */

    .hero-container {

        text-align: center;

        padding:
            45px
            20px
            35px;

    }


    .hero-badge {

        display: inline-block;

        padding:
            8px
            16px;

        border-radius: 30px;

        background:
            rgba(99, 102, 241, 0.10);

        border:
            1px solid
            rgba(129, 140, 248, 0.25);

        color:
            #a5b4fc;

        font-size:
            13px;

        font-weight:
            700;

        letter-spacing:
            0.6px;

        margin-bottom:
            20px;

        box-shadow:
            0 0 25px
            rgba(99,102,241,0.08);

    }


    .hero-title {

        margin:
            0;

        font-size:
            clamp(42px, 6vw, 68px);

        line-height:
            1.05;

        font-weight:
            850;

        letter-spacing:
            -3px;

        background:
            linear-gradient(
                90deg,
                #ffffff 0%,
                #c7d2fe 45%,
                #5eead4 100%
            );

        -webkit-background-clip:
            text;

        -webkit-text-fill-color:
            transparent;

    }


    .hero-subtitle {

        max-width:
            700px;

        margin:
            18px auto 0;

        color:
            #8993a7;

        font-size:
            17px;

        line-height:
            1.7;

    }


    /* ========================================================
       STATUS CARD
    ======================================================== */

    .status-container {

        display:
            flex;

        align-items:
            center;

        gap:
            14px;

        padding:
            18px
            20px;

        margin-bottom:
            30px;

        border-radius:
            18px;

        background:
            linear-gradient(
                135deg,
                rgba(17,24,39,0.90),
                rgba(12,18,30,0.78)
            );

        border:
            1px solid
            rgba(255,255,255,0.07);

        box-shadow:
            0 15px 40px
            rgba(0,0,0,0.15);

    }


    .status-dot {

        flex-shrink:
            0;

        width:
            11px;

        height:
            11px;

        border-radius:
            50%;

        background:
            #4ade80;

        box-shadow:
            0 0 0 5px
            rgba(74,222,128,0.08),

            0 0 18px
            rgba(74,222,128,0.75);

        animation:
            statusPulse 2s
            infinite;

    }


    @keyframes statusPulse {

        0% {
            transform:
                scale(1);

            opacity:
                1;
        }

        50% {
            transform:
                scale(1.35);

            opacity:
                0.65;
        }

        100% {
            transform:
                scale(1);

            opacity:
                1;
        }

    }


    .status-title {

        color:
            #f8fafc;

        font-size:
            15px;

        font-weight:
            700;

    }


    .status-subtitle {

        color:
            #778197;

        font-size:
            12px;

        margin-top:
            4px;

    }


    /* ========================================================
       QUESTION AREA
    ======================================================== */

    .question-title {

        color:
            #d7dce7;

        font-size:
            14px;

        font-weight:
            700;

        margin-bottom:
            8px;

    }


    div[data-baseweb="input"] {

        background:
            #111622 !important;

        border:
            1px solid
            #252d3e !important;

        border-radius:
            16px !important;

        min-height:
            56px;

        transition:
            all 0.25s ease;

    }


    div[data-baseweb="input"]:focus-within {

        border-color:
            #6366f1 !important;

        box-shadow:
            0 0 0 3px
            rgba(99,102,241,0.13);

    }


    div[data-baseweb="input"] input {

        color:
            #f8fafc !important;

        font-size:
            16px !important;

    }


    div[data-baseweb="input"] input::placeholder {

        color:
            #697386 !important;

    }


    /* ========================================================
       ASK BUTTON
    ======================================================== */

    .stButton > button {

        margin-top:
            10px;

        border:
            none !important;

        border-radius:
            13px !important;

        padding:
            11px 26px !important;

        background:
            linear-gradient(
                135deg,
                #6366f1,
                #4f46e5
            ) !important;

        color:
            white !important;

        font-size:
            14px !important;

        font-weight:
            700 !important;

        transition:
            all 0.25s ease !important;

    }


    .stButton > button:hover {

        transform:
            translateY(-2px);

        box-shadow:
            0 12px 30px
            rgba(99,102,241,0.35);

    }


    /* ========================================================
       RESPONSE CARD
    ======================================================== */

    .response-card {

        margin-top:
            30px;

        padding:
            25px;

        border-radius:
            20px;

        background:
            linear-gradient(
                145deg,
                rgba(18,24,38,0.96),
                rgba(9,13,23,0.96)
            );

        border:
            1px solid
            rgba(255,255,255,0.07);

        box-shadow:
            0 20px 50px
            rgba(0,0,0,0.18);

        animation:
            responseAppear
            0.45s
            ease;

    }


    @keyframes responseAppear {

        from {

            opacity:
                0;

            transform:
                translateY(15px);

        }

        to {

            opacity:
                1;

            transform:
                translateY(0);

        }

    }


    .response-label {

        color:
            #a5b4fc;

        font-size:
            12px;

        font-weight:
            800;

        letter-spacing:
            0.8px;

        margin-bottom:
            13px;

    }


    .response-text {

        color:
            #e5e7eb;

        font-size:
            16px;

        line-height:
            1.8;

    }


    /* ========================================================
       FEATURE CARDS
    ======================================================== */

    .features {

        display:
            grid;

        grid-template-columns:
            repeat(3, 1fr);

        gap:
            16px;

        margin-top:
            38px;

    }


    .feature-card {

        padding:
            24px;

        border-radius:
            19px;

        background:
            rgba(17,24,39,0.68);

        border:
            1px solid
            rgba(255,255,255,0.06);

        transition:
            all 0.3s ease;

    }


    .feature-card:hover {

        transform:
            translateY(-6px);

        border-color:
            rgba(99,102,241,0.32);

        background:
            rgba(23,30,48,0.90);

        box-shadow:
            0 15px 40px
            rgba(0,0,0,0.20);

    }


    .feature-icon {

        font-size:
            28px;

        margin-bottom:
            12px;

    }


    .feature-title {

        color:
            #ffffff;

        font-size:
            15px;

        font-weight:
            750;

        margin-bottom:
            7px;

    }


    .feature-text {

        color:
            #7d8799;

        font-size:
            13px;

        line-height:
            1.65;

    }


    /* ========================================================
       MOBILE
    ======================================================== */

    @media (max-width: 700px) {

        .block-container {

            padding-left:
                15px;

            padding-right:
                15px;

        }

        .hero-title {

            font-size:
                42px;

            letter-spacing:
                -2px;

        }

        .features {

            grid-template-columns:
                1fr;

        }

    }

    </style>
    """,
    unsafe_allow_html=True
)


# ============================================================
# HERO SECTION
# ============================================================

st.html(
    """
    <div class="hero-container">

        <div class="hero-badge">
            ✦ AI POWERED • RAG ASSISTANT
        </div>

        <h1 class="hero-title">
            AI Student Assistant
        </h1>

        <p class="hero-subtitle">
            Your intelligent document assistant powered by
            Retrieval-Augmented Generation.
        </p>

    </div>
    """
)


# ============================================================
# STATUS SECTION
# ============================================================

st.html(
    """
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
    """
)


# ============================================================
# QUESTION SECTION
# ============================================================

st.html(
    """
    <div class="question-title">
        💬 Ask your document anything
    </div>
    """
)


question = st.text_input(
    "question",
    placeholder="e.g. What are the main concepts explained in this document?",
    label_visibility="collapsed"
)


ask = st.button(
    "Ask AI →"
)


# ============================================================
# RAG PIPELINE
# ============================================================

if ask:

    if not question.strip():

        st.warning(
            "Please enter a question first."
        )

    else:

        with st.spinner("🤖 Thinking..."):

            try:

                # ------------------------------------------------
                # PDF PATH
                # ------------------------------------------------

                BASE_DIR = Path(
                    __file__
                ).resolve().parent

                PDF_PATH = (
                    BASE_DIR /
                    "data" /
                    "sample.pdf"
                )


                # ------------------------------------------------
                # LOAD DOCUMENT
                # ------------------------------------------------

                documents = load_documents(
                    str(PDF_PATH)
                )


                # ------------------------------------------------
                # SPLIT DOCUMENT
                # ------------------------------------------------

                chunks = split_docs(
                    documents
                )


                # ------------------------------------------------
                # CREATE EMBEDDINGS
                # ------------------------------------------------

                embeddings = get_embeddings()


                # ------------------------------------------------
                # CREATE VECTOR STORE
                # ------------------------------------------------

                vector_store = create_vector_store(
                    chunks,
                    embeddings
                )


                # ------------------------------------------------
                # LOAD LLM
                # ------------------------------------------------

                llm = get_llm()


                # ------------------------------------------------
                # BUILD RAG CHAIN
                # ------------------------------------------------

                rag_chain = build_rag_chain(
                    llm,
                    vector_store
                )


                # ------------------------------------------------
                # ASK QUESTION
                # ------------------------------------------------

                answer = rag_chain.invoke(
                    question
                )


                # ------------------------------------------------
                # DISPLAY RESPONSE
                # ------------------------------------------------

                st.html(
                    f"""
                    <div class="response-card">

                        <div class="response-label">
                            🤖 AI RESPONSE
                        </div>

                        <div class="response-text">
                            {answer}
                        </div>

                    </div>
                    """
                )


            except Exception as e:

                st.error(
                    f"Something went wrong: {str(e)}"
                )


# ============================================================
# FEATURE CARDS
# ============================================================

st.html(
    """
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
    """
)


# ============================================================
# FLOATING ROBOT
# ============================================================

components.html(
    """
    <!DOCTYPE html>

    <html>

    <head>

    <style>

    html,
    body {

        margin: 0;
        padding: 0;

        width: 100%;
        height: 100%;

        background: transparent;

        overflow: hidden;

    }


    /* ========================================================
       ROBOT
    ======================================================== */

    #ai-bot {

        position: absolute;

        right: 35px;

        bottom: 35px;

        width: 90px;

        height: 90px;

        border-radius: 50%;

        cursor: grab;

        user-select: none;

        background:
            radial-gradient(
                circle at 30% 25%,
                #ffffff 0%,
                #c7d2fe 20%,
                #818cf8 42%,
                #6366f1 65%,
                #312e81 100%
            );

        border:
            3px solid
            rgba(255,255,255,0.35);

        box-shadow:
            0 15px 45px
            rgba(99,102,241,0.50),

            0 0 30px
            rgba(99,102,241,0.20);

        z-index:
            999;

        animation:
            botFloat
            3s
            ease-in-out
            infinite;

        transition:
            box-shadow
            0.25s ease;

    }


    #ai-bot:hover {

        box-shadow:
            0 20px 55px
            rgba(99,102,241,0.65),

            0 0 45px
            rgba(99,102,241,0.25);

    }


    @keyframes botFloat {

        0% {

            transform:
                translateY(0px);

        }

        50% {

            transform:
                translateY(-10px);

        }

        100% {

            transform:
                translateY(0px);

        }

    }


    /* ========================================================
       OUTER PULSE
    ======================================================== */

    #ai-bot::before {

        content: "";

        position: absolute;

        inset:
            -12px;

        border-radius:
            50%;

        border:
            2px solid
            rgba(129,140,248,0.20);

        animation:
            botRing
            2.5s
            infinite;

    }


    @keyframes botRing {

        0% {

            transform:
                scale(0.90);

            opacity:
                0.80;

        }

        100% {

            transform:
                scale(1.25);

            opacity:
                0;

        }

    }


    /* ========================================================
       BOT FACE
    ======================================================== */

    .bot-face {

        position:
            absolute;

        width:
            58px;

        height:
            48px;

        left:
            50%;

        top:
            50%;

        transform:
            translate(-50%, -50%);

        border-radius:
            19px;

        background:
            linear-gradient(
                145deg,
                #111827,
                #1e293b
            );

        border:
            1px solid
            rgba(255,255,255,0.20);

    }


    /* ========================================================
       EYES
    ======================================================== */

    .bot-eye {

        position:
            absolute;

        top:
            14px;

        width:
            8px;

        height:
            12px;

        border-radius:
            50%;

        background:
            #67e8f9;

        box-shadow:
            0 0 12px
            #67e8f9;

        animation:
            botBlink
            4s
            infinite;

    }


    .bot-eye.left {

        left:
            15px;

    }


    .bot-eye.right {

        right:
            15px;

    }


    @keyframes botBlink {

        0%,
        94%,
        100% {

            transform:
                scaleY(1);

        }

        96% {

            transform:
                scaleY(0.08);

        }

    }


    /* ========================================================
       MOUTH
    ======================================================== */

    .bot-mouth {

        position:
            absolute;

        bottom:
            9px;

        left:
            50%;

        width:
            18px;

        height:
            7px;

        transform:
            translateX(-50%);

        border-bottom:
            2px solid
            #67e8f9;

        border-radius:
            50%;

    }


    /* ========================================================
       SPEECH BUBBLE
    ======================================================== */

    #bot-message {

        position:
            absolute;

        right:
            140px;

        bottom:
            55px;

        max-width:
            230px;

        padding:
            14px 18px;

        border-radius:
            17px
            17px
            5px
            17px;

        background:
            rgba(15,23,42,0.97);

        color:
            #ffffff;

        font-family:
            Arial,
            sans-serif;

        font-size:
            14px;

        line-height:
            1.4;

        border:
            1px solid
            rgba(255,255,255,0.10);

        box-shadow:
            0 12px 35px
            rgba(0,0,0,0.40);

        opacity:
            0;

        transform:
            translateY(10px)
            scale(0.95);

        transition:
            all
            0.25s
            ease;

        pointer-events:
            none;

    }


    #bot-message.show {

        opacity:
            1;

        transform:
            translateY(0)
            scale(1);

    }


    /* ========================================================
       DRAG LABEL
    ======================================================== */

    #drag-label {

        position:
            absolute;

        right:
            25px;

        bottom:
            10px;

        color:
            rgba(255,255,255,0.35);

        font-family:
            Arial,
            sans-serif;

        font-size:
            11px;

    }

    </style>

    </head>


    <body>


    <!-- =====================================================
         ROBOT
    ====================================================== -->

    <div id="ai-bot">

        <div class="bot-face">

            <div class="bot-eye left"></div>

            <div class="bot-eye right"></div>

            <div class="bot-mouth"></div>

        </div>

    </div>


    <!-- =====================================================
         SPEECH
    ====================================================== -->

    <div id="bot-message">
        Ask me a question 👋
    </div>


    <div id="drag-label">
        Drag me
    </div>


    <!-- =====================================================
         JAVASCRIPT
    ====================================================== -->

    <script>

    const bot =
        document.getElementById(
            "ai-bot"
        );

    const message =
        document.getElementById(
            "bot-message"
        );


    let dragging =
        false;

    let moved =
        false;

    let offsetX =
        0;

    let offsetY =
        0;


    /* ======================================================
       START DRAG
    ====================================================== */

    bot.addEventListener(
        "pointerdown",
        function(event) {

            dragging =
                true;

            moved =
                false;

            const rect =
                bot.getBoundingClientRect();


            offsetX =
                event.clientX -
                rect.left;


            offsetY =
                event.clientY -
                rect.top;


            bot.setPointerCapture(
                event.pointerId
            );


            bot.style.cursor =
                "grabbing";


            bot.style.animation =
                "none";


            event.preventDefault();

        }
    );


    /* ======================================================
       DRAG
    ====================================================== */

    bot.addEventListener(
        "pointermove",
        function(event) {

            if (!dragging) {

                return;

            }


            moved =
                true;


            let x =
                event.clientX -
                offsetX;


            let y =
                event.clientY -
                offsetY;


            const maxX =
                window.innerWidth -
                bot.offsetWidth;


            const maxY =
                window.innerHeight -
                bot.offsetHeight;


            x =
                Math.max(
                    5,
                    Math.min(
                        x,
                        maxX - 5
                    )
                );


            y =
                Math.max(
                    5,
                    Math.min(
                        y,
                        maxY - 5
                    )
                );


            bot.style.left =
                x + "px";


            bot.style.top =
                y + "px";


            bot.style.right =
                "auto";


            bot.style.bottom =
                "auto";


            /* ----------------------------------------------
               MOVE MESSAGE WITH BOT
            ----------------------------------------------- */

            message.style.left =
                Math.max(
                    10,
                    x - 245
                ) + "px";


            message.style.top =
                Math.max(
                    10,
                    y + 5
                ) + "px";


            message.style.right =
                "auto";


            message.style.bottom =
                "auto";

        }
    );


    /* ======================================================
       STOP DRAG / CLICK
    ====================================================== */

    bot.addEventListener(
        "pointerup",
        function(event) {

            dragging =
                false;


            bot.style.cursor =
                "grab";


            bot.style.animation =
                "botFloat 3s ease-in-out infinite";


            /* ----------------------------------------------
               CLICK
            ----------------------------------------------- */

            if (!moved) {

                message.innerHTML =
                    "Ask me a question 👋";


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


    /* ======================================================
       CANCEL DRAG
    ====================================================== */

    bot.addEventListener(
        "pointercancel",
        function() {

            dragging =
                false;

            bot.style.cursor =
                "grab";

            bot.style.animation =
                "botFloat 3s ease-in-out infinite";

        }
    );

    </script>

    </body>

    </html>
    """,
    height=600,
)