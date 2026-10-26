import hashlib
import hmac
import os
import re
import sqlite3
import streamlit as st

DB = "chat.db"
ITERATIONS = 200_000


# ---------- BASE DE DONNÉES ----------
def _requete(sql, params=(), fetch=False):
    conn = sqlite3.connect(DB)
    cur = conn.execute(sql, params)
    resultat = cur.fetchall() if fetch else cur.lastrowid
    conn.commit()
    conn.close()
    return resultat


def init_users():
    _requete("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nom TEXT UNIQUE NOT NULL COLLATE NOCASE,
        mot_de_passe TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")


# ---------- MOT DE PASSE (jamais stocké en clair) ----------
def _hasher(mdp):
    sel = os.urandom(16)
    h = hashlib.pbkdf2_hmac("sha256", mdp.encode("utf-8"), sel, ITERATIONS)
    return f"{sel.hex()}${h.hex()}"

def _mdp_correct(mdp, stocke):
    sel_hex, h_hex = stocke.split("$")
    h = hashlib.pbkdf2_hmac(
        "sha256", mdp.encode("utf-8"), bytes.fromhex(sel_hex), ITERATIONS
    )
    return hmac.compare_digest(h.hex(), h_hex)


# ---------- INSCRIPTION / CONNEXION ----------
def inscrire(nom, mdp, confirmation):
    nom = nom.strip()
    if len(nom) < 3:
        return None, "Le nom doit contenir au moins 3 caractères."
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", nom):
        return None, "Le nom ne peut contenir que lettres, chiffres, _ . -"
    if len(mdp) < 6:
        return None, "Le mot de passe doit contenir au moins 6 caractères."
    if mdp != confirmation:
        return None, "Les mots de passe ne correspondent pas."
    try:
        user_id = _requete(
            "INSERT INTO users (nom, mot_de_passe) VALUES (?, ?)",
            (nom, _hasher(mdp)),
        )
    except sqlite3.IntegrityError:
        return None, "Ce nom d'utilisateur existe déjà."
    return {"id": user_id, "nom": nom}, None


def connecter(nom, mdp):
    lignes = _requete(
        "SELECT id, nom, mot_de_passe FROM users WHERE nom = ?",
        (nom.strip(),),
        fetch=True,
    )
    if lignes and _mdp_correct(mdp, lignes[0][2]):
        return {"id": lignes[0][0], "nom": lignes[0][1]}
    return None


def deconnecter():
    st.session_state.pop("user", None)
    st.session_state.conv_id = None


# ---------- PAGE LOGIN / REGISTER ----------
def exiger_connexion():
    """Retourne l'utilisateur connecté, sinon affiche login/register et stoppe la page."""
    if "user" in st.session_state:
        return st.session_state.user

    st.title("🐉 Mon chatbot")
    tab_login, tab_register = st.tabs(["🔑 Connexion", "📝 Inscription"])

    with tab_login:
        with st.form("form_login"):
            nom = st.text_input("Nom d'utilisateur")
            mdp = st.text_input("Mot de passe", type="password")
            ok = st.form_submit_button("Se connecter", use_container_width=True)
        if ok:
            user = connecter(nom, mdp)
            if user:
                st.session_state.user = user
                st.rerun()
            else:
                st.error("Nom d'utilisateur ou mot de passe incorrect.")

    with tab_register:
        with st.form("form_register"):
            nom = st.text_input("Choisis un nom d'utilisateur")
            mdp = st.text_input("Mot de passe (6 caractères min.)", type="password")
            conf = st.text_input("Confirme le mot de passe", type="password")
            ok = st.form_submit_button("Créer mon compte", use_container_width=True)
        if ok:
            user, erreur = inscrire(nom, mdp, conf)
            if erreur:
                st.error(erreur)
            else:
                st.session_state.user = user
                st.rerun()

    st.stop()
