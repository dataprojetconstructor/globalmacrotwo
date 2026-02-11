import streamlit as st
import pandas as pd
import pandas_datareader.data as web
import yfinance as yf
import plotly.graph_objects as go
from datetime import datetime, timedelta

# Configuration de la page
st.set_page_config(page_title="GlobaMacro Pro - Central Bank Monitor", layout="wide")

# --- TITRE ET STYLE ---
st.title("🌐 GlobaMacro Pro : Surveillance des Banques Centrales")
st.markdown("""
    Cette application fournit une analyse en temps réel des politiques monétaires mondiales. 
    Les données sont extraites directement de la **FRED (St. Louis Fed)** et de **Yahoo Finance**.
""")

# --- CONFIGURATION DES TICKERS (CORRIGÉS) ---
# Correction des IDs FRED pour éviter les erreurs "Series not exist"
SERIES_MAP = {
    "États-Unis (FED)": {"rate": "FEDFUNDS", "cpi": "CPIAUCSL"},
    "Zone Euro (BCE)": {"rate": "ECBASHW", "cpi": "CP0000EZ19M086NEST"},
    "Royaume-Uni (BoE)": {"rate": "IUDSOIA", "cpi": "GBRCPIALLMINMEI"},
    "Canada (BoC)": {"rate": "INTDSRCAM193N", "cpi": "CPALTT01CAM659N"},
    "Australie (RBA)": {"rate": "IR3TIB01AUM156N", "cpi": "CPALTT01AUM659N"},
    "Suisse (BNS)": {"rate": "INTDSRCHM193N", "cpi": "CPALTT01CHM659N"},
    "Japon (BoJ)": {"rate": "INTDSRJPM193N", "cpi": "CPALTT01JPM659N"}
}

# --- FONCTIONS DE RÉCUPÉRATION SÉCURISÉES ---
@st.cache_data(ttl=3600)  # Cache d'une heure pour la performance
def get_macro_data(series_id, source="fred"):
    try:
        start = datetime.now() - timedelta(days=5*365)
        if source == "fred":
            data = web.DataReader(series_id, 'fred', start)
            if data.empty:
                return None, "Données vides"
            return data, "OK"
    except Exception as e:
        return None, str(e)

# --- BARRE LATÉRALE (AUDIT & CONTRÔLE) ---
st.sidebar.header("🛡️ Intégrité des Données")
status_list = []

# --- CHARGEMENT ET CALCULS ---
combined_data = pd.DataFrame()
real_rates_data = pd.DataFrame()

with st.spinner('Extraction des données réelles en cours...'):
    for country, ids in SERIES_MAP.items():
        # Récupération du taux directeur
        df_rate, msg_rate = get_macro_data(ids["rate"])
        # Récupération de l'inflation (pour le calcul du taux réel)
        df_cpi, msg_cpi = get_macro_data(ids["cpi"])
        
        status_list.append({"Pays": country, "Status Taux": msg_rate, "Status Inflation": msg_cpi})
        
        if df_rate is not None:
            combined_data[country] = df_rate.iloc[:, 0]
            
            # Calcul du taux réel (Taux Nominal - Inflation) 
            # Note: Calcul simplifié pour la démo
            if df_cpi is not None:
                # On aligne les données par date
                cpi_pct = df_cpi.pct_change(periods=12).iloc[:, 0] * 100
                real_rates_data[country] = df_rate.iloc[:, 0] - cpi_pct

# --- AFFICHAGE DE LA SÉCURITÉ ---
with st.sidebar.expander("Vérifier les sources (Log technique)"):
    st.table(pd.DataFrame(status_list))

# --- LAYOUT PRINCIPAL : 2 COLONNES ---
col1, col2 = st.columns(2)

with col1:
    st.subheader("📈 Taux Directeurs Nominaux")
    if not combined_data.empty:
        fig = go.Figure()
        for col in combined_data.columns:
            fig.add_trace(go.Scatter(x=combined_data.index, y=combined_data[col], name=col))
        fig.update_layout(hovermode="x unified", yaxis_title="Taux (%)", template="plotly_dark")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.error("Aucune donnée de taux disponible.")

with col2:
    st.subheader("📉 Taux Réels (Ajustés de l'inflation)")
    st.info("Un taux réel négatif indique une politique très accommodante.")
    if not real_rates_data.empty:
        fig_real = go.Figure()
        for col in real_rates_data.columns:
            fig_real.add_trace(go.Scatter(x=real_rates_data.index, y=real_rates_data[col], name=col))
        fig_real.add_hline(y=0, line_dash="dash", line_color="white")
        fig_real.update_layout(hovermode="x unified", yaxis_title="Taux Réel (%)", template="plotly_dark")
        st.plotly_chart(fig_real, use_container_width=True)

# --- NOUVELLE VISUALISATION : MATRICE DE COMPARAISON ---
st.divider()
st.subheader("📊 Résumé de la Situation Actuelle")

last_rates = combined_data.ffill().iloc[-1]
last_real = real_rates_data.ffill().iloc[-1]

summary_df = pd.DataFrame({
    "Taux Actuel (%)": last_rates,
    "Taux Réel (%)": last_real,
    "Dernière Mise à jour": [combined_data.index[-1].strftime('%d-%m-%Y')] * len(last_rates)
})

st.dataframe(summary_df.style.background_gradient(cmap='RdYlGn', subset=['Taux Réel (%)']), use_container_width=True)

# --- SECTION ÉDUCATIVE ---
with st.expander("💡 Pourquoi ces données sont-elles importantes ?"):
    st.write("""
        1. **Taux Nominaux** : C'est le prix de l'argent fixé par la banque centrale. S'il monte, le crédit devient cher.
        2. **Taux Réels** : Si l'inflation est à 10% et le taux à 5%, le taux réel est de -5%. C'est une mesure de la 'pression' réelle sur l'économie.
        3. **Sécurité** : Les données FRED sont les données officielles utilisées par les économistes du monde entier.
    """)
