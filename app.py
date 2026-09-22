# This has the added functionality of RAG and and Guardrails

import streamlit as st
import google.generativeai as genai
import json
import numpy as np

# ==========================================
# 1. SETUP & API KEY
# ==========================================
API_KEY = st.secrets["GEMINI_API_KEY"]
genai.configure(api_key=API_KEY)

model = genai.GenerativeModel('gemini-3.5-flash')
embedding_model = 'models/gemini-embedding-001'

# ==========================================
# 2. THE SCREEN DICTIONARY
# ==========================================
SCREEN_DICTIONARY = {
    "home_screen": "https://github.com/hsuyaalasnab/MS_Visual_Assistant/blob/main/photo_1.png?raw=true",
    "file_menu_screen": "https://github.com/hsuyaalasnab/MS_Visual_Assistant/blob/main/photo_2.png?raw=true"
}

# ==========================================
# 3. THE KNOWLEDGE BASE (Simulated Vector DB)
# ==========================================
KNOWLEDGE_BASE = [
    {
        "intent_description": "How to save a file as a new document or save as.",
        "ui_map": """
            Screen 1 (home_screen):
            - File Menu: '1%', y: '9%'
            Screen 2 (file_menu_screen):
            - Save As Button: x: '3%', y: '32%'
        """
    },
    {
        "intent_description": "How to export data to a CSV file.",
        "ui_map": """
            Screen 1 (home_screen):
            - File Menu: x: '1%', y: '9%'
            Screen 2 (file_menu_screen):
            - Export CSV Button: x: '3%', y: '40%'
        """
    }
]

def get_embedding(text):
    result = genai.embed_content(model=embedding_model, content=text, task_type="retrieval_document")
    return result['embedding']


SYSTEM_PROMPT = """
You are an expert UI navigation assistant. Your job is to guide users step-by-step through a web application.
Your ONLY source of truth is the [RETRIEVED CONTEXT] provided below. 

GUARDRAILS:
1. If the user's question cannot be answered using the [RETRIEVED CONTEXT], reply that you can only assist with documented application features and return an empty "actions" list. Do not hallucinate steps.
2. You must output ONLY a valid, raw JSON object. Do not include markdown blocks (like ```json), comments, or any conversational text outside the JSON structure.

INSTRUCTIONS FOR ACTIONS:
Translate the retrieved workflow into a sequential list of actions. For EVERY step in the workflow, provide a brief instruction, the exact x and y coordinates, and the exact screen_id provided in the context.

JSON OUTPUT FORMAT:
{
  "reply": "Here is how you do it. First, click File. Then, click Save As.",
  "actions": [
    {
      "text": "Click the File menu.",
      "x": "1%",
      "y": "9%",
      "screen_id": "home_screen"
    },
    {
      "text": "Click the Save As button.",
      "x": "3%",
      "y": "32%",
      "screen_id": "file_menu_screen"
    }
  ]
}

[RETRIEVED CONTEXT]:
"""

# ==========================================
# 5. STREAMLIT APP LAYOUT & LOGIC
# ==========================================
st.set_page_config(layout="wide")
st.title("Bernanrd")

col1, col2 = st.columns([3, 2])

if "messages" not in st.session_state:
    st.session_state.messages = []
if "animation_data" not in st.session_state:
    st.session_state.animation_data = "[]"

with col2:
    st.subheader("Chat")
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if prompt := st.chat_input("Ask 'How to export?' or 'How do I save as?'"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Searching Knowledge Base & Thinking..."):
                try:
                    # --- RAG RETRIEVAL STEP ---
                    user_embedding = get_embedding(prompt)
                    
                    best_match = None
                    highest_similarity = 0
                    
                    for item in KNOWLEDGE_BASE:
                        item_embedding = get_embedding(item["intent_description"])
                        similarity = np.dot(user_embedding, item_embedding) / (np.linalg.norm(user_embedding) * np.linalg.norm(item_embedding))
                        
                        if similarity > highest_similarity:
                            highest_similarity = similarity
                            best_match = item
                    
                    # --- GUARDRAIL CHECK ---
                    if highest_similarity < 0.65:
                        retrieved_context = "NO RELEVANT CONTEXT FOUND."
                    else:
                        retrieved_context = best_match["ui_map"]

                    # --- GENERATION STEP ---
                    final_prompt = SYSTEM_PROMPT + retrieved_context + "\n\nUser Question: " + prompt
                    
                    # Force JSON output via generation_config
                    response = model.generate_content(
                        final_prompt,
                        generation_config=genai.GenerationConfig(
                            response_mime_type="application/json"
                        )
                    )
                    
                    ai_payload = json.loads(response.text)
                    
                    st.markdown(ai_payload["reply"])
                    st.session_state.messages.append({"role": "assistant", "content": ai_payload["reply"]})
                    
                    # --- MAPPING THE URLS (Backend Dictionary Lookup) ---
                    actions = ai_payload.get("actions", [])
                    for action in actions:
                        screen_id = action.get("screen_id")
                        action["image"] = SCREEN_DICTIONARY.get(screen_id, "") 
                    
                    st.session_state.animation_data = json.dumps(actions)

                except Exception as e:
                    st.error(f"Error processing request. Details: {e}")

with col1:
    st.subheader("Application View")
    
    # ==========================================
    # 6. FRONTEND ANIMATION COMPONENT
    # ==========================================
    html_code = f"""
    <div id="app-screen" style="
        position: relative; width: 100%; aspect-ratio: 850 / 458;
        background-color: #ecf0f1; 
        background-image: url('https://github.com/hsuyaalasnab/MS_Visual_Assistant/blob/main/photo_1.png?raw=true');
        background-size: 100% 100%; background-position: center;
        border-radius: 8px; border: 2px solid #bdc3c7; overflow: hidden;
        transition: background-image 0.3s ease-in-out;
    ">
        <div id="virtual-cursor" style="
            position: absolute; width: 24px; height: 24px;
            background: rgba(231, 76, 60, 0.8); border: 2px solid #e74c3c; border-radius: 50%;
            pointer-events: none; z-index: 100;
            transition: left 1s ease-in-out, top 1s ease-in-out, transform 0.2s;
            left: -50px; top: -50px;
        "></div>
    </div>

    <script>
        const steps = {st.session_state.animation_data};
        const screen = document.getElementById('app-screen');
        const cursor = document.getElementById('virtual-cursor');
        const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

        async function runAnimation() {{
            if (!steps || steps.length === 0) {{
                screen.style.backgroundImage = "url('https://via.placeholder.com/800x450/e74c3c/ffffff?text=Action+Not+Supported')";
                return;
            }}

            for (const step of steps) {{
                if (step.image) screen.style.backgroundImage = `url('${{step.image}}')`;
                await sleep(600);
                
                cursor.style.left = step.x;
                cursor.style.top = step.y;
                await sleep(1000);
                
                cursor.style.transform = 'scale(0.5)';
                await sleep(200);
                cursor.style.transform = 'scale(1)';
                await sleep(800);
            }}
            
            await sleep(1000);
            cursor.style.left = '-50px'; 
            cursor.style.top = '-50px';
            screen.style.backgroundImage = "url('https://via.placeholder.com/800x450/ecf0f1/333333?text=Workflow+Complete')";
        }}

        runAnimation();
    </script>
    """
    
    st.components.v1.html(html_code, height=500)