import os
import base64
import sqlite3
import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI

import auth
import rag

DB = "chat.db"
MODELES = ["openai/gpt-oss-120b", "qwen/qwen3.8-27b"]
MODELE_VISION = "qwen/qwen3.8-27b"          # seul modèle qui lit les images
MODELE_WHISPER = "whisper-large-v3-turbo"   # voix → texte


# ---------- BASE DE DONNÉES ----------
def sql(requete, params=(), fetch=False):
    conn = sqlite3.connect(DB)
    cur = conn.execute(requete, params)
    resultat = cur.fetchall() if fetch else cur.lastrowid
    conn.commit()
    conn.close()
    return resultat


def init_db():
    sql("""CREATE TABLE IF NOT EXISTS conversations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        titre TEXT NOT NULL,
        user_id INTEGER)""")
    sql("""CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        conversation_id INTEGER NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL)""")
    # anciennes bases : ajouter user_id si absent
    if "user_id" not in [c[1] for c in sql("PRAGMA table_info(conversations)", fetch=True)]:
        sql("ALTER TABLE conversations ADD COLUMN user_id INTEGER")


def lister_conversations(user_id):
    return sql("SELECT id, titre FROM conversations WHERE user_id = ? ORDER BY id DESC",
               (user_id,), fetch=True)


def charger_messages(conv_id):
    lignes = sql("SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY id",
                 (conv_id,), fetch=True)
    return [{"role": r, "content": c} for r, c in lignes]


def ajouter_message(conv_id, role, content):
    sql("INSERT INTO messages (conversation_id, role, content) VALUES (?, ?, ?)",
        (conv_id, role, content))


def supprimer_conversation(conv_id, user_id):
    sql("""DELETE FROM messages WHERE conversation_id IN
           (SELECT id FROM conversations WHERE id = ? AND user_id = ?)""", (conv_id, user_id))
    sql("DELETE FROM conversations WHERE id = ? AND user_id = ?", (conv_id, user_id))


# ---------- OUTILS ----------
def image_en_base64(fichier):
    donnees = base64.b64encode(fichier.getvalue()).decode("utf-8")
    return f"data:{fichier.type};base64,{donnees}"


def transcrire(audio):
    resultat = client.audio.transcriptions.create(
        file=(audio.name or "voix.wav", audio.getvalue()),
        model=MODELE_WHISPER,
        language="fr",
        response_format="text",
    )
    return (resultat if isinstance(resultat, str) else resultat.text).strip()


# ---------- DÉMARRAGE ----------
st.set_page_config(page_title="chatbot", page_icon="🐉")
load_dotenv()
client = OpenAI(api_key=os.getenv("GROQ_API_KEY"), base_url="https://api.groq.com/openai/v1")

init_db()
auth.init_users()

st.session_state.setdefault("conv_id", None)
st.session_state.setdefault("reset", 0)   # change la clé des uploaders pour les vider

utilisateur = auth.exiger_connexion()     # affiche login/register sinon
st.title("🐉 Mon chatbot")


# ---------- SIDEBAR ----------
with st.sidebar:
    st.caption(f"👤 {utilisateur['nom']}")
    if st.button("🚪 Se déconnecter", use_container_width=True):
        auth.deconnecter()
        st.rerun()

    # 💬 Historique
    st.header("💬 Historique")
    if st.button("➕ Nouvelle conversation", use_container_width=True):
        st.session_state.conv_id = None
        st.rerun()

    for conv_id, titre in lister_conversations(utilisateur["id"]):
        col1, col2 = st.columns([4, 1])
        if col1.button(titre, key=f"open_{conv_id}", use_container_width=True,
                       type="primary" if conv_id == st.session_state.conv_id else "secondary"):
            st.session_state.conv_id = conv_id
            st.rerun()
        if col2.button("🗑️", key=f"del_{conv_id}"):
            supprimer_conversation(conv_id, utilisateur["id"])
            if conv_id == st.session_state.conv_id:
                st.session_state.conv_id = None
            st.rerun()

    st.divider()

    # Options rangées dans des menus repliables
    with st.expander("⚙️ Paramètres"):
        modele = st.selectbox("Modèle", MODELES)
        temperature = st.slider("Créativité", 0.0, 1.0, 0.7, 0.1)
        consigne = st.text_area("Consigne du bot",
                                value="Tu es un assistant sympa qui répond en français.")

    with st.expander("🖼️ Image"):
        image = st.file_uploader("Importer une image", type=["png", "jpg", "jpeg", "webp"],
                                 key=f"img_{st.session_state.reset}")
        if image:
            st.image(image, use_container_width=True)

    with st.expander("🎙️ Voix"):
        audio = st.audio_input("Parle, puis arrête l'enregistrement",
                               key=f"audio_{st.session_state.reset}")

    with st.expander("📚 Documents (RAG)"):
        utiliser_rag = st.toggle("Utiliser mes documents", value=True)
        fichiers = st.file_uploader("Ajouter des fichiers", type=["pdf", "txt"],
                                    accept_multiple_files=True)
        if st.button("📥 Indexer", use_container_width=True) and fichiers:
            with st.spinner("Indexation..."):
                for f in fichiers:
                    st.success(f"{f.name} : {rag.ajouter_document(f)} morceaux")
        st.caption(f"Morceaux en base : {rag.nombre_morceaux()}")
        if st.button("🧹 Vider", use_container_width=True):
            rag.supprimer_documents()
            st.rerun()


# ---------- HISTORIQUE DE LA CONVERSATION ----------
if st.session_state.conv_id:
    for m in charger_messages(st.session_state.conv_id):
        with st.chat_message(m["role"]):
            st.write(m["content"])


# ---------- SAISIE ----------
question = st.chat_input("Écris ta question ici...")
if not question and audio:                       # pas de texte → on utilise la voix
    with st.spinner("Transcription..."):
        question = transcrire(audio)

if question:
    # nouvelle conversation si besoin
    nouvelle = st.session_state.conv_id is None
    if nouvelle:
        titre = question[:30] + ("..." if len(question) > 30 else "")
        st.session_state.conv_id = sql(
            "INSERT INTO conversations (titre, user_id) VALUES (?, ?)",
            (titre, utilisateur["id"]))
    conv_id = st.session_state.conv_id

    with st.chat_message("user"):
        if image:
            st.image(image, width=250)
        st.write(question)

    ajouter_message(conv_id, "user",
                    f"📎 [image : {image.name}]\n{question}" if image else question)

    # contexte RAG
    morceaux = rag.chercher(question) if utiliser_rag else []
    consigne_finale = consigne
    if morceaux:
        consigne_finale += ("\n\nUtilise le CONTEXTE ci-dessous pour répondre. "
                            "Si la réponse ne s'y trouve pas, dis que tu ne sais pas.\n\n"
                            "CONTEXTE :\n" + "\n\n---\n\n".join(morceaux))

    # messages envoyés au modèle (le dernier contient l'image si jointe)
    messages = charger_messages(conv_id)
    modele_utilise = modele
    if image:
        modele_utilise = MODELE_VISION
        messages[-1] = {"role": "user", "content": [
            {"type": "text", "text": question},
            {"type": "image_url", "image_url": {"url": image_en_base64(image)}},
        ]}

    with st.chat_message("assistant"):
        with st.spinner("Je réfléchis..."):
            reponse = client.chat.completions.create(
                model=modele_utilise,
                temperature=temperature,
                messages=[{"role": "system", "content": consigne_finale}, *messages],
            ).choices[0].message.content
        st.write(reponse)

        if morceaux:
            with st.expander("📄 Sources utilisées"):
                for texte in morceaux:
                    st.write(texte[:300] + "...")

    ajouter_message(conv_id, "assistant", reponse)

    # vider image / micro et rafraîchir la liste
    if image or audio:
        st.session_state.reset += 1
    if nouvelle or image or audio:
        st.rerun()