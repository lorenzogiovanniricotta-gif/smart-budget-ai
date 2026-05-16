import streamlit as st
import pandas as pd
import os
from datetime import datetime, timedelta
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
            
    st.write("---")
    st.header("🗑️ Gestione Errori")
    if st.button("❌ Cancella Ultimo Inserimento"):
        if not df.empty:
            df = df.drop(df.index[-1])
            df.to_csv(DB_FILE, index=False)
            st.warning("Ultima transazione eliminata!")
            st.rerun()
        else:
            st.info("Il registro è già vuoto.")

# Layout Principale a due colonne
col1, col2 = st.columns([1, 1])

with col1:
    st.header("📸 Carica Scontrino Automatico")
    file_scontrino = st.file_uploader("Trascina qui lo scontrino...", type=["png", "jpg", "jpeg"])
    
    api_key = st.secrets["GEMINI_API_KEY"]

    if file_scontrino and api_key:
        image = Image.open(file_scontrino)
        st.image(image, caption="Scontrino caricato", width=250)
        
        if st.button("Analizza e Salva con AI"):
            with st.spinner("Gemini sta analizzando lo scontrino..."):
                try:
                    client = genai.Client(api_key=api_key)
                    response = client.models.generate_content(
                        model='gemini-2.5-flash',
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
        # Generiamo la lista dei mesi includendo anche i prossimi 6 mesi nel futuro
        oggi = datetime.today()
        mesi_futuri = [(oggi + timedelta(days=30 * i)).strftime("%Y-%m") for i in range(7)]
        
        mesi_storici = list(df["Mese_Anno"].dropna().unique())
        tutti_i_mesi = sorted(list(set(mesi_storici + mesi_futuri)))
        
        df_espanso = df[df["Ricorrente"] == "No"].copy()
        df_ricorrenti = df[df["Ricorrente"] == "Sì"].copy()
        
        # Logica di proiezione nel futuro per le ricorrenze
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
            
        # Saldo Totale (calcolato solo fino al mese corrente per non falsare il portafoglio attuale)
        mese_corrente_str = oggi.strftime("%Y-%m")
        saldo_attuale = df_visualizzazione[df_visualizzazione["Mese_Anno"] <= mese_corrente_str]["Importo"].sum()
        st.metric(label="Saldo Attuale Reale (Fino a questo mese)", value=f"{saldo_attuale:.2f} €")
        
        # Registro Completo (Mostra solo i dati reali inseriti, ordinati per data)
        st.subheader("📜 Registro Transazioni Inserite")
        st.dataframe(df.sort_values(by="Data", ascending=False), use_container_width=True)
        
        # --- SEZIONE GRAFICI DI PREVISIONE FUTURA ---
        st.markdown("### 🔮 Previsioni e Analisi Futura (Prossimi 6 Mesi)")
        
        df_entrate = df_visualizzazione[df_visualizzazione["Importo"] > 0].copy()
        df_uscite = df_visualizzazione[df_visualizzazione["Importo"] < 0].copy()
        df_uscite["Importo"] = df_uscite["Importo"].abs()
        
        # 1. Grafico Uscite (Storico + Futuro)
        st.subheader("📉 Analisi Spese per Mese (Incluso Futuro)")
        if not df_uscite.empty:
            spese_mensili = df_uscite.groupby("Mese_Anno")["Importo"].sum().reindex(tutti_i_mesi, fill_value=0)
            st.bar_chart(spese_mens
