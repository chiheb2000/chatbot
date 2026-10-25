import chromadb
from chromadb.utils import embedding_functions
from pypdf import PdfReader

# Modèle qui transforme le texte en vecteurs (embeddings)
MODEL_NAME = "all-MiniLM-L6-v2"

embedding = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name=MODEL_NAME
)

# 1) Base ChromaDB enregistrée dans le dossier "chroma_db"
client = chromadb.PersistentClient(path="chroma_db")

NOM_COLLECTION = "documents"


def get_collection():
    """Une seule collection pour tous les documents."""
    return client.get_or_create_collection(
        name=NOM_COLLECTION,
        embedding_function=embedding,
    )


# 2) Lire le texte d'un fichier (PDF ou TXT)
def lire_fichier(fichier):
    if fichier.name.lower().endswith(".pdf"):
        lecteur = PdfReader(fichier)
        texte = ""
        for page in lecteur.pages:
            texte += (page.extract_text() or "") + "\n"
        return texte
    else:
        return fichier.read().decode("utf-8", errors="ignore")


# 3) Couper le texte en petits morceaux (chunks)
def decouper_texte(texte, taille=500):
    morceaux = []
    for i in range(0, len(texte), taille):
        morceau = texte[i:i + taille].strip()
        if morceau:
            morceaux.append(morceau)
    return morceaux


# 4) Ajouter un document dans ChromaDB
def ajouter_document(fichier):
    texte = lire_fichier(fichier)
    morceaux = decouper_texte(texte)
    if not morceaux:
        return 0

    collection = get_collection()
    ids = [f"{fichier.name}_{i}" for i in range(len(morceaux))]
    collection.upsert(
        ids=ids,
        documents=morceaux,
        metadatas=[{"source": fichier.name}] * len(morceaux),
    )
    return len(morceaux)


# 5) Chercher les morceaux les plus proches de la question
def chercher(question, n=3):
    collection = get_collection()
    if collection.count() == 0:
        return []
    resultats = collection.query(
        query_texts=[question],
        n_results=min(n, collection.count()),
    )
    return resultats["documents"][0]


# 6) Nombre de morceaux enregistrés
def nombre_morceaux():
    return get_collection().count()


# 7) Supprimer tous les documents
def supprimer_documents():
    try:
        client.delete_collection(name=NOM_COLLECTION)
    except Exception:
        pass  # la collection n'existe pas encore : rien à supprimer