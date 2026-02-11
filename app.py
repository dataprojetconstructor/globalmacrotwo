import streamlit as st
import pandas as pd
from fredapi import Fred
import plotly.express as px
from datetime import datetime, timedelta

# --- CONFIGURATION INITIALE ---
st.set_page_config(page_title="Global Macro Dashboard", layout="wide")

# Gestion de la clé API
if "FRED_KEY" in st.secrets:
    API_KEY = st.secrets["FRED_KEY"]
else:
    API_KEY = 'f25835309cd5c99504970cd7f417dddd' # Votre clé

try:
    fred = Fred(api_key=API_KEY)
except Exception as e:
    st.error(f"Erreur API : {e}")
    st.stop()

# --- DICTIONNAIRE DE SÉRIES RÉVISÉ (Plus robuste) ---
# J'ai utilisé des séries "Immediate Rates" (Interbancaire) qui sont mieux mises à jour
central_banks = {
    'USD (Fed)': {
        'rate': 'FEDFUNDS',             
        'cpi': 'CPIAUCSL',              
        'balance': 'WALCL'              
    },
    'EUR (ECB)': {
        'rate': 'ECBDFR',               
        'cpi': 'CP0000EZ19M086NEST',    
        'balance': 'ECBASSETSW'         
    },
    'JPY (BoJ)': {
        'rate': 'IRSTCI01JPM156N', # Taux interbancaire JPY (Plus récent)
        'cpi': 'JPNCPIALLMINMEI',       
        'balance': 'JPNASSETS'          
    },
    'GBP (BoE)': {
        'rate': 'IUDSOIA', # SONIA Rate (Très réactif)
        'cpi': 'GBRCPIALLMINMEI',       
        'balance': None                 
    },
    'CAD (BoC)': {
        'rate': 'IRSTCI01CAM156N', # Taux interbancaire CAD
        'cpi': 'CANCPIALLMINMEI',       
        'balance': 'CV11269'            
    },
    'AUD (RBA)': {
        'rate': 'IRSTCI01AUM156N', # Taux interbancaire AUD
        'cpi': 'AUSCPIALLMINMEI',       
        'balance': None
    },
    'CHF (SNB)': {
        'rate': 'IRSTCI01CHM156N', # Taux interbancaire CHF
        'cpi': 'CHECPIALLMINMEI',       
        'balance': 'CHFCENTRALBANK'     
    },
}

# --- LOGIQUE DE CALCUL ---

def calculate_z_score(series):
    if series is None or len(series) < 5: return 0
    clean = series.dropna()
    if clean.empty: return 0
    return (clean.iloc[-1] - clean.mean()) / clean.std()

@st.cache_data(ttl=3600*12)
def get_macro_data():
    data = []
    start_date = datetime.now() - timedelta(days=365*5)
    
    progress_bar = st.progress(0, text="Interrogation de la FRED...")
    
    for i, (currency, codes) in enumerate(central_banks.items()):
        row = {'Devise': currency, 'Taux (%)': 0, 'Z-Rate': 0, 'CPI (%)': 0, 'Z-CPI': 0, 
               'Bilan 6M (%)': 0, 'Z-Bilan': 0, 'Macro Score': 0, 'Status': '✅'}
        
        try:
            # 1. TAUX (Indispensable)
            try:
                rate_s = fred.get_series(codes['rate'], observation_start=start_date).ffill()
                row['Taux (%)'] = rate_s.iloc[-1]
                row['Z-Rate'] = calculate_z_score(rate_s)
            except:
                row['Status'] = '❌ Taux manquant'
                data.append(row)
                continue

            # 2. CPI (Optionnel pour le calcul)
            try:
                cpi_s = fred.get_series(codes['cpi'], observation_start=start_date).ffill()
                cpi_yoy = cpi_s.pct_change(12).dropna() * 100
                row['CPI (%)'] = cpi_yoy.iloc[-1]
                row['Z-CPI'] = calculate_z_score(cpi_yoy)
            except:
                row['Status'] = '⚠️ CPI manquant'

            # 3. BILAN (Optionnel)
            if codes['balance']:
                try:
                    bs_s = fred.get_series(codes['balance'], observation_start=start_date).ffill()
                    bs_chg = bs_s.pct_change(26).dropna() * 100 # 6 mois approx
                    row['Bilan 6M (%)'] = bs_chg.iloc[-1]
                    row['Z-Bilan'] = calculate_z_score(bs_chg)
                except:
                    pass

            # Score : Hawk (Taux+CPI) vs Dove (Bilan)
            row['Macro Score'] = (row['Z-Rate'] * 2.0) + (row['Z-CPI'] * 1.0) - (row['Z-Bilan'] * 0.5)
            data.append(row)

        except Exception as e:
            row['Status'] = f"❌ Erreur: {str(e)[:20]}"
            data.append(row)
            
        progress_bar.progress((i + 1) / len(central_banks))

    progress_bar.empty()
    return pd.DataFrame(data).sort_values(by='Macro Score', ascending=False)

# --- INTERFACE ---

st.title("🏦 Central Bank Alpha Tool")
st.info("Note : Les données hors USA peuvent avoir un délai de mise à jour (Source FRED/OCDE).")

if st.button('🔄 Forcer le rafraîchissement des données'):
    st.cache_data.clear()
    st.rerun()

df = get_macro_data()

# Affichage du tableau
st.header("1. Analyse Comparative")

def style_df(val):
    if not isinstance(val, (int, float)): return ''
    if val > 1.2: return 'background-color: #d4edda; color: #155724'
    if val < -1.2: return 'background-color: #f8d7da; color: #721c24'
    return ''

st.dataframe(
    df.style.map(style_df, subset=['Z-Rate', 'Z-CPI', 'Z-Bilan', 'Macro Score'])
    .format("{:.2f}", subset=['Taux (%)', 'Z-Rate', 'CPI (%)', 'Z-CPI', 'Bilan 6M (%)', 'Z-Bilan', 'Macro Score']),
    use_container_width=True
)

# Graphique
st.header("2. Positionnement Hawkish vs Dovish")
fig = px.scatter(df, x="Z-CPI", y="Z-Rate", text="Devise", color="Macro Score",
                 size=[20]*len(df), color_continuous_scale="RdYlGn",
                 labels={"Z-CPI": "Inflation (Z-Score)", "Z-Rate": "Taux (Z-Score)"})
fig.add_hline(y=0, line_dash="dash")
fig.add_vline(x=0, line_dash="dash")
st.plotly_chart(fig, use_container_width=True)

# Signaux
st.header("3. Signaux Forex")
col1, col2 = st.columns(2)
with col1:
    st.success(f"🔥 Plus Hawkish : {df.iloc[0]['Devise']}")
with col2:
    st.error(f"🌊 Plus Dovish : {df.iloc[-1]['Devise']}")
