import streamlit as st
import openai
import firebase_admin
from firebase_admin import credentials, firestore
import json

# --- 1. SETUP & CONFIGURATION ---
st.set_page_config(page_title="Apex Shade | Sales Apex", page_icon="🌤️", layout="wide")

# Initialize OpenAI
try:
    openai.api_key = st.secrets["OPENAI_API_KEY"]
except:
    st.error("⚠️ OpenAI API Key missing. Please add it to Secrets.")
    st.stop()

# Initialize Firebase (Database)
# We check if it's already initialized to prevent errors on app rerun
if not firebase_admin._apps:
# Create the credentials dictionary manually from Secrets
    key_dict = {
        "type": "service_account",
        "project_id": st.secrets["firebase"]["project_id"],
        "private_key_id": st.secrets["firebase"]["private_key_id"],
        "private_key": st.secrets["firebase"]["private_key"],
        "client_email": st.secrets["firebase"]["client_email"],
        "client_id": st.secrets["firebase"]["client_id"],
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_x509_cert_url": st.secrets["firebase"]["client_x509_cert_url"]
    }
    
    cred = credentials.Certificate(key_dict)
    firebase_admin.initialize_app(cred)

db = firestore.client()

# --- 2. HELPER FUNCTIONS ---

def save_to_db(guru, scenario, objection, script, analysis):
    """Saves a new interaction to Firestore as 'pending'."""
    doc_ref = db.collection("interactions").document()
    doc_ref.set({
        "guru": guru,
        "scenario": scenario,
        "objection": objection,
        "script": script,
        "analysis": analysis,
        "status": "pending",  # <--- Waiting for your review
        "timestamp": firestore.SERVER_TIMESTAMP
    })

def get_approved_knowledge():
    """Fetches approved scripts to make the AI smarter (RAG)."""
    docs = db.collection("interactions").where("status", "==", "approved").stream()
    knowledge_base = ""
    for doc in docs:
        data = doc.to_dict()
        knowledge_base += f"--- PAST SUCCESSFUL SCENARIO ---\nObjection: {data['objection']}\nSuccessful Script: {data['script']}\n"
    return knowledge_base

# --- 3. SIDEBAR (ADMIN LOGIN) ---
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2965/2965335.png", width=50)
    st.markdown("### 🛡️ Admin Portal")
    admin_password = st.text_input("Admin Password", type="password")
    
    is_admin = False
    if admin_password == st.secrets["ADMIN_PASSWORD"]:
        is_admin = True
        st.success("Admin Access Granted")

# --- 4. MAIN APP LOGIC ---

# TABS for different views
tab1, tab2, tab3 = st.tabs(["🌤️ Sales Simulator", "📚 Training Library", "🔒 Admin Review"])

# === TAB 1: THE SALES SIMULATOR (What Reps See) ===
with tab1:
    st.title("Apex Shade | Sales Simulator")
    st.caption("Select a mentor, input the objection, and get an instant script.")

    col1, col2 = st.columns([1, 1])
    with col1:
        guru_options = {
            "Zig Ziglar": "Moral, optimistic, 'transfer of feeling'.",
            "Chris Voss": "Tactical empathy, labeling, 'How' questions.",
            "Grant Cardone": "10X aggression, price is a myth, close hard.",
            "David Sandler": "Disarming, reverse psychology, 'dummy curve'."
        }
        selected_guru = st.selectbox("Choose Mentor:", list(guru_options.keys()))
        st.caption(guru_options[selected_guru])
    
    with col2:
        scenario_type = st.selectbox("Scenario:", ["Price Shock", "Spousal Stall", "Competitor", "Technical", "Ghosting"])

    user_input = st.text_area("Customer Objection:", height=100, placeholder="e.g. 'I need to talk to my wife first.'")

    if st.button("Generate & Record", type="primary"):
        if not user_input:
            st.warning("Please enter an objection.")
        else:
            with st.spinner("Consulting mentors & checking database..."):
                
                # Retrieve past approved wisdom to inject into the prompt
                past_wisdom = get_approved_knowledge()

                system_prompt = f"""
                You are a high-ticket sales trainer for Retractable Awnings.
                ACT AS: {selected_guru}
                
                YOUR KNOWLEDGE BASE (Past Approved Scripts):
                {past_wisdom}
                
                INSTRUCTIONS:
                1. Use the style of {selected_guru}.
                2. If a similar scenario exists in the KNOWLEDGE BASE, adapt that successful script.
                3. Provide a VERBATIM script.
                """

                response = openai.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"Objection: {user_input}"}
                    ]
                )
                
                full_response = response.choices[0].message.content
                
                # Split response for cleaner UI (Assume AI follows roughly Script / Analysis format)
                st.markdown("### 🗣️ Recommended Script")
                st.write(full_response)
                
                # Save to Database automatically
                save_to_db(selected_guru, scenario_type, user_input, full_response, "AI Generated")
                st.toast("Saved to Admin Review Queue!", icon="✅")

# === TAB 2: TRAINING LIBRARY (Read-Only for Reps) ===
with tab2:
    st.header("📚 The Playbook")
    st.markdown("A collection of approved, winning scripts from the field.")
    
    # Fetch only approved docs
    docs = db.collection("interactions").where("status", "==", "approved").stream()
    
    for doc in docs:
        data = doc.to_dict()
        with st.expander(f"Scenario: {data['scenario']} ({data['guru']})"):
            st.markdown(f"**Objection:** {data['objection']}")
            st.markdown(f"**Script:** {data['script']}")

# === TAB 3: ADMIN REVIEW (Hidden unless logged in) ===
with tab3:
    if is_admin:
        st.header("🔒 Admin Review Queue")
        st.write("Review 'Pending' interactions. Approve them to add them to the AI's brain.")
        
        # Fetch pending docs
        pending_docs = db.collection("interactions").where("status", "==", "pending").stream()
        
        found_pending = False
        for doc in pending_docs:
            found_pending = True
            data = doc.to_dict()
            
            st.markdown("---")
            c1, c2, c3 = st.columns([3, 1, 1])
            with c1:
                st.subheader(f"Type: {data['scenario']}")
                st.write(f"**Objection:** {data['objection']}")
                st.info(f"**AI Script:** {data['script']}")
            with c2:
                if st.button("✅ Approve", key=f"app_{doc.id}"):
                    db.collection("interactions").document(doc.id).update({"status": "approved"})
                    st.rerun()
            with c3:
                if st.button("❌ Delete", key=f"del_{doc.id}"):
                    db.collection("interactions").document(doc.id).delete()
                    st.rerun()
        
        if not found_pending:
            st.success("No pending items to review!")
    else:
        st.warning("Please enter the Admin Password in the sidebar to view this tab.")
