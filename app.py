import streamlit as st
import pandas as pd
from fredapi import Fred
import plotly.express as px
from datetime import datetime, timedelta
import os
import time

# --- CONFIGURATION INITIALE ---
st.set_page_config(page_title="Central Bank Alpha Tool", layout="wide")

# --- GESTION SÉCURISÉE DE LA CLÉ API ---
if "FRED_KEY" in st.secrets:
    API_KEY = st.secrets["FRED_KEY"]
else:
    # Clé de secours (Veillez à ne pas la pousser sur un repo public)
    API_KEY = 'f25835309cd5c99504970cd7f417dddd'

try:
    fred = Fred(api_key=API_KEY)
except Exception as e:
    st.error(f"Erreur de connexion à la FRED : {e}")
    st.stop()

# --- DEFINITION DES INDICES (Codes Robustes) ---
central_banks = {
    'USD (Fed)': {'rate': 'FEDFUNDS', 'cpi': 'CPIAUCSL', 'balance': 'WALCL'},
    'EUR (ECB)': {'rate': 'ECBDFR', 'cpi': 'CP0000EZ19M086NEST', 'balance': 'ECBASSETSW'},
    'JPY (BoJ)': {'rate': 'IRSTCI01JPM156N', 'cpi': 'JPNCPIALLMINMEI', 'balance': 'JPNASSETS'},
    'GBP (BoE)': {'rate': 'IUDSOIA', 'cpi': 'GBRCPIALLMINMEI', 'balance': None}, 
    'CAD (BoC)': {'rate': 'IRSTCI01CAM156N', 'cpi': 'CANCPIALLMINMEI', 'balance': 'CV11269'},
    'AUD (RBA)': {'rate': 'IRSTCI01AUM156N', 'cpi': 'AUSCPIALLMINMEI', 'balance': None},
    'CHF (SNB)': {'rate': 'IRSTCI01CHM156N', 'cpi': 'CHECPIALLMINMEI', 'balance': 'CHFCENTRALBANK'},
}

# --- MOTEUR DE CALCUL (BACKEND) ---

def calculate_z_score(series):
    """Calcule le Z-Score de manière robuste"""
    if series is None or len(series) < 10: return 0
    clean_s = series.dropna()
    if clean_s.empty: return 0
    mean = clean_s.mean()
    std = clean_s.std()
    return (clean_s.iloc[-1] - mean) / std if std != 0 else 0

@st.cache_data(ttl=86400) # Cache de 24h
def get_macro_data():
    """Télécharge et traite les données"""
    data = []
    start_date = datetime.now() - timedelta(days=365*5)
    
    progress_bar = st.progress(0, text="Interrogation de la FRED...")
    
    for i, (currency, codes) in enumerate(central_banks.items()):
        row = {
            'Devise': currency, 'Taux (%)': 0, 'Z-Rate': 0, 
            'CPI (%)': 0, 'Z-CPI': 0, 'Bilan 6M (%)': 0, 
            'Z-Bilan': 0, 'Macro Score': 0
        }
        
        try:
            # 1. TAUX
            s_rate = fred.get_series(codes['rate'], observation_start=start_date).ffill()
            if not s_rate.empty:
                row['Taux (%)'] = s_rate.iloc[-1]
                row['Z-Rate'] = calculate_z_score(s_rate)

            # 2. INFLATION (YoY)
            s_cpi = fred.get_series(codes['cpi'], observation_start=start_date).ffill()
            if not s_cpi.empty:
                cpi_yoy = s_cpi.pct_change(12).dropna() * 100
                row['CPI (%)'] = cpi_yoy.iloc[-1]
                row['Z-CPI'] = calculate_z_score(cpi_yoy)

            # 3. BILAN
            if codes['balance']:
                try:
                    s_bs = fred.get_series(codes['balance'], observation_start=start_date).ffill()
                    bs_chg = s_bs.pct_change(26).dropna() * 100
                    row['Bilan 6M (%)'] = bs_chg.iloc[-1]
                    row['Z-Bilan'] = calculate_z_score(bs_chg)
                except:
                    pass

            # 4. SCORE FINAL
            row['Macro Score'] = (row['Z-Rate'] * 2.0) + (row['Z-CPI'] * 1.0) - (row['Z-Bilan'] * 0.5)
            data.append(row)

        except Exception as e:
            st.warning(f"Problème avec {currency} : Données indisponibles.")
            continue
            
        progress_bar.progress((i + 1) / len(central_banks))

    progress_bar.empty()
    return pd.DataFrame(data).sort_values(by='Macro Score', ascending=False)

# --- FRONTEND (INTERFACE) ---

st.title("🏦 Central Bank Policy Tracker")
st.markdown("Analyse quantitative des banques centrales : **Hawkish** (Vert) vs **Dovish** (Rouge).")

# Barre latérale pour actions
with st.sidebar:
    st.header("Paramètres")
    if st.button('🔄 Rafraîchir les données'):
        st.cache_data.clear()
        st.rerun()
    st.write("Source : FRED (St. Louis Fed)")

df = get_macro_data()

# SECTION 1 : TABLEAU DE BORD
st.header("1. Comparaison Macro")

if not df.empty:
    def style_val(val):
        if not isinstance(val, (int, float)): return ''
        if val > 1.2: return 'background-color: #d4edda; color: #155724' # Vert
        if val < -1.2: return 'background-color: #f8d7da; color: #721c24' # Rouge
        return ''

    st.dataframe(
        df.style.map(style_val, subset=['Z-Rate', 'Z-CPI', 'Z-Bilan', 'Macro Score'])
        .format("{:.2f}", subset=['Taux (%)', 'Z-Rate', 'CPI (%)', 'Z-CPI', 'Bilan 6M (%)', 'Z-Bilan', 'Macro Score']),
        use_container_width=True
    )

    # SECTION 2 : VISUALISATION
    st.divider()
    col_chart, col_sig = st.columns([2, 1])

    with col_chart:
        st.subheader("Visualisation du Cycle")
        fig = px.scatter(
            df, x="Z-CPI", y="Z-Rate", text="Devise", 
            size=[20]*len(df), color="Macro Score",
            color_continuous_scale="RdYlGn",
            labels={"Z-CPI": "Inflation (Z-Score)", "Z-Rate": "Taux (Z-Score)"},
            height=500
        )
        fig.add_hline(y=0, line_dash="dash", line_color="grey")
        fig.add_vline(x=0, line_dash="dash", line_color="grey")
        st.plotly_chart(fig, use_container_width=True)

    with col_sig:
        st.subheader("Signaux Forex")
        top_hawk = df.iloc[0]
        top_dove = df.iloc[-1]
        
        st.metric("Top HAWK (Long)", top_hawk['Devise'], f"Score: {top_hawk['Macro Score']:.2f}")
        st.metric("Top DOVE (Short)", top_dove['Devise'], f"Score: {top_dove['Macro Score']:.2f}", delta_color="inverse")
        
        spread = top_hawk['Macro Score'] - top_dove['Macro Score']
        st.info(f"**Paire suggérée :** {top_hawk['Devise'][:3]}/{top_dove['Devise'][:3]}\n\n**Force du spread :** {spread:.2f}")

    # SECTION 3 : LOGIQUE DE DIVERGENCE
    st.divider()
    st.subheader("3. Opportunités de Divergence (>2.0)")
    trades = []
    for i, row_l in df.iterrows():
        for j, row_s in df.iterrows():
            diff = row_l['Macro Score'] - row_s['Macro Score']
            if diff > 2.0:
                trades.append({
                    'Achat': row_l['Devise'],
                    'Vente': row_s['Devise'],
                    'Divergence': round(diff, 2),
                    'Statut': '🔥 Signal Fort'
                })
    
    if trades:
        st.table(pd.DataFrame(trades))
    else:
        st.write("Aucune divergence extrême détectée.")

else:
    st.error("Échec du chargement des données. Vérifiez votre connexion ou votre clé API.")
