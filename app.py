import streamlit as st
import pandas as pd
from fredapi import Fred
import plotly.express as px
from datetime import datetime, timedelta

# --- CONFIGURATION INITIALE ---
st.set_page_config(page_title="Global Macro Dashboard", layout="wide")

# --- GESTION DE LA CLÉ API SÉCURISÉE ---
if "FRED_KEY" in st.secrets:
    API_KEY = st.secrets["FRED_KEY"]
else:
    # Clé de secours pour vos tests locaux
    API_KEY = 'f25835309cd5c99504970cd7f417dddd'

# Initialisation de l'objet FRED
try:
    fred = Fred(api_key=API_KEY)
except Exception as e:
    st.error(f"Erreur de connexion API : {e}")
    st.stop()

# --- DEFINITION DES INDICES ---
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
        'rate': 'INTDSRJPM193N',        
        'cpi': 'JPNCPIALLMINMEI',       
        'balance': 'JPNASSETS'          
    },
    'GBP (BoE)': {
        'rate': 'IUDSOIA',              
        'cpi': 'GBRCPIALLMINMEI',       
        'balance': None                 
    },
    'CAD (BoC)': {
        'rate': 'INTDSRCAM193N',        
        'cpi': 'CANCPIALLMINMEI',       
        'balance': 'CV11269'            
    },
    'AUD (RBA)': {
        'rate': 'INTDSRAUM193N',        
        'cpi': 'AUSCPIALLMINMEI',       
        'balance': None
    },
    'CHF (SNB)': {
        'rate': 'INTDSRCHM193N',        
        'cpi': 'CHECPIALLMINMEI',       
        'balance': 'CHFCENTRALBANK'     
    },
}

# --- FONCTIONS DE CALCUL (BACKEND) ---

def calculate_z_score(series):
    """Calcule le Z-Score (écart à la moyenne en écarts-types)"""
    if series is None or len(series) < 10: 
        return 0
    clean_series = series.dropna()
    if clean_series.empty:
        return 0
    mean = clean_series.mean()
    std = clean_series.std()
    if std == 0: 
        return 0
    return (clean_series.iloc[-1] - mean) / std

@st.cache_data(ttl=3600*24)
def get_macro_data():
    """Télécharge et traite les données macro-économiques"""
    data = []
    start_date = datetime.now() - timedelta(days=365*5) # 5 ans d'historique
    
    progress_bar = st.progress(0, text="Connexion aux serveurs de la FED...")
    total = len(central_banks)

    for i, (currency, codes) in enumerate(central_banks.items()):
        try:
            # 1. TAUX DIRECTEUR
            rate_s = fred.get_series(codes['rate'], observation_start=start_date).ffill()
            if rate_s.empty: continue
            cur_rate = rate_s.iloc[-1]
            z_rate = calculate_z_score(rate_s)

            # 2. INFLATION (CPI)
            cpi_s = fred.get_series(codes['cpi'], observation_start=start_date).ffill()
            # Calcul de la variation annuelle (YoY)
            cpi_yoy = cpi_s.pct_change(12).dropna() * 100
            cur_cpi = cpi_yoy.iloc[-1] if not cpi_yoy.empty else 0
            z_cpi = calculate_z_score(cpi_yoy)

            # 3. BILAN (Balance Sheet)
            cur_bs_chg = 0
            z_bs = 0
            if codes['balance']:
                try:
                    bs_s = fred.get_series(codes['balance'], observation_start=start_date).ffill()
                    # Variation sur env. 6 mois (26 semaines ou 6 mois)
                    # On utilise un décalage relatif à la longueur de la série
                    shift = 26 if len(bs_s) > 100 else 6 
                    bs_chg = bs_s.pct_change(shift).dropna() * 100
                    cur_bs_chg = bs_chg.iloc[-1]
                    z_bs = calculate_z_score(bs_chg)
                except:
                    pass

            # 4. ALGORITHME DE SCORING (Hawk vs Dove)
            # Poids : Taux (x2), Inflation (x1), Bilan (-0.5 car expansion = Dovish)
            score = (z_rate * 2.0) + (z_cpi * 1.0) - (z_bs * 0.5)

            data.append({
                'Devise': currency,
                'Taux (%)': round(cur_rate, 2),
                'Z-Rate': z_rate,
                'CPI (%)': round(cur_cpi, 2),
                'Z-CPI': z_cpi,
                'Bilan 6M (%)': round(cur_bs_chg, 2),
                'Z-Bilan': z_bs,
                'Macro Score': score
            })

        except Exception as e:
            st.warning(f"Données incomplètes pour {currency}")
            continue
        
        progress_bar.progress((i + 1) / total, text=f"Chargement : {currency}")

    progress_bar.empty()
    df = pd.DataFrame(data)
    return df.sort_values(by='Macro Score', ascending=False)

# --- INTERFACE (FRONTEND) ---

st.title("🏦 Central Bank Alpha Tool")
st.markdown(f"**Status:** Live | **Source:** FRED/FMI | **Dernier Refresh:** {datetime.now().strftime('%H:%M')}")

# Chargement des données
with st.spinner('Analyse des cycles monétaires en cours...'):
    df = get_macro_data()

if not df.empty:
    # SECTION 1 : TABLEAU DE BORD
    st.header("1. Tableau de Bord Macro")
    
    col1, col2 = st.columns([3, 1])

    with col1:
        # Fonction de style corrigée pour Pandas 2.x
        def highlight_scores(val):
            if not isinstance(val, (int, float)): return ''
            if val > 1.2: return 'background-color: #d4edda; color: #155724; font-weight: bold' # Vert
            if val < -1.2: return 'background-color: #f8d7da; color: #721c24; font-weight: bold' # Rouge
            return ''

        # Affichage du DataFrame avec formatage
        st.dataframe(
            df.style.map(highlight_scores, subset=['Z-Rate', 'Z-CPI', 'Z-Bilan', 'Macro Score'])
            .format("{:.2f}", subset=['Z-Rate', 'Z-CPI', 'Z-Bilan', 'Macro Score']),
            use_container_width=True,
            height=350
        )

    with col2:
        best = df.iloc[0]
        worst = df.iloc[-1]
        
        st.success(f"🔥 **HAWKISH** (Long)\n\n**{best['Devise']}**")
        st.error(f"🌊 **DOVISH** (Short)\n\n**{worst['Devise']}**")
        
        spread = best['Macro Score'] - worst['Macro Score']
        st.metric("Potentiel de Divergence", f"{spread:.2f}")

    # SECTION 2 : VISUALISATION
    st.divider()
    st.header("2. Analyse des Cycles (Z-Score Map)")
    
    col_chart1, col_chart2 = st.columns([2, 1])

    with col_chart1:
        fig = px.scatter(
            df, x="Z-CPI", y="Z-Rate", text="Devise", 
            size=[20]*len(df), color="Macro Score",
            color_continuous_scale="RdYlGn",
            labels={"Z-CPI": "Inflation (Z-Score)", "Z-Rate": "Taux (Z-Score)"},
            title="Divergence : Taux vs Inflation"
        )
        fig.add_hline(y=0, line_dash="dash", line_color="grey")
        fig.add_vline(x=0, line_dash="dash", line_color="grey")
        fig.update_traces(textposition='top center')
        st.plotly_chart(fig, use_container_width=True)

    with col_chart2:
        st.info("""
        **Comment interpréter ?**
        - **Haut-Droite** : La banque centrale est agressive (Taux hauts) pour contrer une inflation forte. Devise généralement forte.
        - **Bas-Droite** : "Behind the curve". Inflation forte mais taux bas. Risque de dévaluation.
        - **Bas-Gauche** : Politique expansionniste. Taux bas et peu d'inflation. Devise de financement (Carry).
        """)

    # SECTION 3 : OPPORTUNITÉS FOREX
    st.divider()
    st.header("3. Signaux de Divergence")

    trades = []
    for i, row_l in df.iterrows():
        for j, row_s in df.iterrows():
            spread = row_l['Macro Score'] - row_s['Macro Score']
            if spread > 2.0: # Seuil de divergence forte
                pair = f"{row_l['Devise'][:3]}/{row_s['Devise'][:3]}"
                trades.append({
                    'Paire': pair,
                    'Action': 'ACHAT (Long)',
                    'Force du Signal': round(spread, 2),
                    'Logique': "Divergence Politique Monétaire"
                })

    if trades:
        df_trades = pd.DataFrame(trades).sort_values(by='Force du Signal', ascending=False)
        st.table(df_trades.head(5))
    else:
        st.write("Pas de divergence majeure détectée pour le moment.")

else:
    st.error("Impossible de charger les données. Vérifiez votre clé API FRED.")
