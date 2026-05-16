import streamlit as st
import pandas as pd
import os
from datetime import datetime
from google import genai
from PIL import Image

# --- CONFIGURAZIONE PROMPT AI ---
SYSTEM_INSTRUCTION = """
Sei un assistente finanziario. Analizza l'immagine dello scontrino e restituisci ESCLUSIVAMENTE un codice JSON valido con questi campi:
{
  "data": "AAAA-MM-GG",
  "negozio": "Nome del negozio",
  "totale": 0.00,
  "categoria": "Scegli tra: Alimentari, Trasporti, Svago, Salute, Tecnologia, Casa, Altro"
}
Non aggiungere spiegazioni, rispondi solo con il JSON.
"""

DB_FILE = "registro_finanze.csv"
COLUMNS = ["Data", "Tipo", "Descrizione", "Importo", "Categoria", "Mese_Anno", "Ricorrente"]

# Carica o crea il database delle spese mettendo in sicurezza la struttura delle colonne
if os.path.exists(DB_FILE):
    df = pd.read_csv(DB_FILE)
    if "Mese_Anno" not in df.columns:
        df["Mese_Anno"] = df["Data"].apply(lambda x: str(x)[:7] if pd.notnull(x) else "")
    if "Ricorrente" not in df.columns:
        df["Ricorrente"] = "No"
    df = df.reindex(columns=COLUMNS)
    df["Ricorrente"] = df["Ricorrente"].fillna("No")
else:
    df = pd.DataFrame(columns=COLUMNS)

# --- INTERFACCIA GRAFICA (STREAMLIT) ---
st.set_page_config(page_title="Smart Budget AI", layout="wide")
st.title("💰 Smart Budget AI & Personal Finance")
st.subheader("Gestione finanziaria mensile con lettura automatica degli scontrini")

# Barra laterale per Inserimenti Manuali
with st.sidebar:
    st.header("✍️ Inserimento Manuale")
    tipo_transazione = st.radio("Tipo movimento:", ["Entrata", "Uscita"])
    
    descrizione = st.text_input("Descrizione (es: Stipendio, Netflix, Affitto, Regalo):")
    importo = st.number_input("Importo (€):", min_value=0.0, step=1.0)
    data_manuale = st.date_input("Data inizio:", datetime.today())
    
    if tipo_transazione == "Entrata":
        categoria_man = st.selectbox("Categoria Entrata:", ["Stipendio", "Paghetta", "Vendite/Usato", "Regali", "Altro"])
    else:
        categoria_man = st.selectbox("Categoria Uscita:", ["Casa/Affitto", "Abbonamenti", "Svago", "Tecnologia", "Trasporti", "Spesa", "Altro"])
    
    ricorrente_check = st.checkbox("🔄 Imposta come ricorrente ogni mese")
    ricorrente_val = "Sì" if ricorrente_check else "No"
    
    if st.button("Salva Inserimento"):
        if descrizione and importo > 0:
            valore = importo if tipo_transazione == "Entrata" else -importo
            str_mese_anno = data_manuale.strftime("%Y-%m")
            
            nuova_riga = pd.DataFrame([[
                data_manuale.strftime("%Y-%m-%d"), 
                "Manuale", 
                descrizione, 
                valore, 
                categoria_man, 
                str_mese_anno,
                ricorrente_val
            ]], columns=COLUMNS)
            
            df = pd.concat([df, nuova_riga], ignore_index=True)
            df.to_csv(DB_FILE, index=False)
            st.success("Dato salvato con successo!")
            st.rerun()

# Layout Principale a due colonne
col1, col2 = st.columns([1, 1])

with col1:
    st.header("📸 Carica Scontrino Automatico")
    file_scontrino = st.file_uploader("Trascina qui lo scontrino...", type=["png", "jpg", "jpeg"])
    api_key = st.text_input("Inserisci la tua API Key di AI Studio:", type="password")

    if file_scontrino and api_key:
        image = Image.open(file_scontrino)
        st.image(image, caption="Scontrino caricato", width=250)
        
        if st.button("Analizza e Salva con AI"):
            with st.spinner("Gemini sta analizzando lo scontrino..."):
                try:
                    client = genai.Client(api_key=api_key)
                    response = client.models.generate_content(
                        model='gemini-3-flash-preview',
                        contents=[image, SYSTEM_INSTRUCTION]
                    )
                    testo_json = response.text.replace("```json", "").replace("```", "").strip()
                    dati_ai = eval(testo_json)
                    
                    data_str = dati_ai["data"]
                    str_mese_anno = data_str[:7]
                    
                    nuova_riga = pd.DataFrame([[
                        data_str, 
                        "AI (Scontrino)", 
                        dati_ai["negozio"], 
                        -float(dati_ai["totale"]), 
                        dati_ai["categoria"], 
                        str_mese_anno,
                        "No"
                    ]], columns=COLUMNS)
                    
                    df = pd.concat([df, nuova_riga], ignore_index=True)
                    df.to_csv(DB_FILE, index=False)
                    st.success(f"Salvato automaticamente: {dati_ai['negozio']} di €{dati_ai['totale']}")
                    st.rerun()
                except Exception as e:
                    st.error(f"Errore durante l'analisi dell'AI: {e}")

with col2:
    st.header("📊 Resoconto Finanziario")
    if not df.empty:
        tutti_i_mesi = sorted(list(df["Mese_Anno"].dropna().unique()))
        df_espanso = df[df["Ricorrente"] == "No"].copy()
        df_ricorrenti = df[df["Ricorrente"] == "Sì"].copy()
        
        # Logica ricorrenze
        righe_ricorrenti_generate = []
        for index, row in df_ricorrenti.iterrows():
            mese_inizio = row["Mese_Anno"]
            for mese in tutti_i_mesi:
                if mese >= mese_inizio:
                    nuova_row = row.copy()
                    nuova_row["Mese_Anno"] = mese
                    nuova_row["Data"] = f"{mese}-01" 
                    righe_ricorrenti_generate.append(nuova_row)
                    
        if righe_ricorrenti_generate:
            df_visualizzazione = pd.concat([df_espanso, pd.DataFrame(righe_ricorrenti_generate)], ignore_index=True)
        else:
            df_visualizzazione = df_espanso.copy()
            
        # Saldo Totale
        saldo_totale = df_visualizzazione["Importo"].sum()
        st.metric(label="Saldo Attuale Bilancio (Inclusi Ricorrenti)", value=f"{saldo_totale:.2f} €")
        
        # Registro Completo
        st.subheader("📜 Registro Completo Transazioni")
        st.dataframe(df_visualizzazione.sort_values(by="Data", ascending=False), use_container_width=True)
        
        # --- SEZIONE GRAFICI DI ANALISI ---
        df_entrate = df_visualizzazione[df_visualizzazione["Importo"] > 0].copy()
        df_uscite = df_visualizzazione[df_visualizzazione["Importo"] < 0].copy()
        df_uscite["Importo"] = df_uscite["Importo"].abs()
        
        # 1. Grafico Uscite
        st.subheader("📉 Analisi Spese per Mese e Anno")
        if not df_uscite.empty:
            spese_mensili = df_uscite.groupby("Mese_Anno")["Importo"].sum()
            st.bar_chart(spese_mensili)
        else:
            st.info("Nessuna uscita registrata.")
            
        # 2. Grafico Entrate (Nuovo!)
        st.subheader("📈 Analisi Entrate per Mese e Anno")
        if not df_entrate.empty:
            entrate_mensili = df_entrate.groupby("Mese_Anno")["Importo"].sum()
            st.bar_chart(entrate_mensili)
        else:
            st.info("Nessuna entrata registrata.")
            
        # 3. Grafico di Confronto Totale (Nuovo!)
        st.subheader("⚖️ Bilancio Totale: Entrate vs Uscite")
        entrate_m = df_entrate.groupby("Mese_Anno")["Importo"].sum() if not df_entrate.empty else pd.Series(dtype=float)
        spese_m = df_uscite.groupby("Mese_Anno")["Importo"].sum() if not df_uscite.empty else pd.Series(dtype=float)
        
        # Combiniamo le informazioni in un'unica tabella per il grafico doppio
        tutti_i_mesi_charts = sorted(list(set(entrate_m.index).union(set(spese_m.index))))
        df_confronto = pd.DataFrame(index=tutti_i_mesi_charts)
        df_confronto["Entrate (€)"] = entrate_m
        df_confronto["Uscite (€)"] = spese_m
        df_confronto = df_confronto.fillna(0)
        
        if not df_confronto.empty:
            # Mostra le due barre affiancate per ogni mese
            st.bar_chart(df_confronto)
            
            # 4. Linea del Risparmio Netto
            df_confronto["Risparmio Netto (€)"] = df_confronto["Entrate (€)"] - df_confronto["Uscite (€)"]
            st.subheader("📈 Flusso di Cassa Netto (Risparmio Mensile)")
            st.line_chart(df_confronto["Risparmio Netto (€)"])
            
    else:
        st.info("Il registro è vuoto. Inserisci un movimento nella barra laterale o carica uno scontrino!")