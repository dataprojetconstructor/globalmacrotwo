import streamlit as st
import pandas as pd
from fredapi import Fred
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import time

# --- CONFIGURATION INITIALE ---
st.set_page_config(page_title="Global Macro Dashboard", layout="wide")

# --- GESTION DE LA CLÉ API SÉCURISÉE ---
# Essaye de récupérer la clé depuis les "Secrets" de Streamlit Cloud
# Sinon, utilise la clé par défaut (pour vos tests locaux)
if "FRED_KEY" in st.secrets:
    API_KEY = st.secrets["FRED_KEY"]
else:
    # ⚠️ Clé de secours (A ne pas partager si possible)
    API_KEY = 'f25835309cd5c99504970cd7f417dddd'

# Initialisation de l'objet FRED
try:
    fred = Fred(api_key=API_KEY)
except Exception as e:
    st.error(f"Erreur de connexion API : {e}")
    st.stop()

# --- DEFINITION DES INDICES (CODES CORRIGÉS) ---
# J'ai remplacé les codes défaillants par les séries du FMI (plus stables)
central_banks = {
    'USD (Fed)': {
        'rate': 'FEDFUNDS',             # Federal Funds Effective Rate
        'cpi': 'CPIAUCSL',              # CPI Urban Consumers
        'balance': 'WALCL'              # Total Assets
    },
    'EUR (ECB)': {
        'rate': 'ECBDFR',               # ECB Deposit Facility Rate
        'cpi': 'CP0000EZ19M086NEST',    # HICP Euro Area
        'balance': 'ECBASSETSW'         # Central Bank Assets for Euro Area
    },
    'JPY (BoJ)': {
        'rate': 'INTDSRJPM193N',        # FMI: Central Bank Policy Rate Japan (Plus stable)
        'cpi': 'JPNCPIALLMINMEI',       # OECD: CPI Japan
        'balance': 'JPNASSETS'          # BoJ Total Assets
    },
    'GBP (BoE)': {
        'rate': 'IUDSOIA',              # SONIA Rate (Proxy fiable)
        'cpi': 'GBRCPIALLMINMEI',       # OECD: CPI UK
        'balance': None                 # Bilan non dispo sur FRED
    },
    'CAD (BoC)': {
        'rate': 'INTDSRCAM193N',        # FMI: Central Bank Policy Rate Canada (CORRIGÉ)
        'cpi': 'CANCPIALLMINMEI',       # OECD: CPI Canada
        'balance': 'CV11269'            # Central Bank Assets Canada
    },
    'AUD (RBA)': {
        'rate': 'INTDSRAUM193N',        # FMI: Central Bank Policy Rate Australia (CORRIGÉ)
        'cpi': 'AUSCPIALLMINMEI',       # OECD: CPI Australia
        'balance': None
    },
    'CHF (SNB)': {
        'rate': 'INTDSRCHM193N',        # FMI: Central Bank Policy Rate Switzerland (CORRIGÉ)
        'cpi': 'CHECPIALLMINMEI',       # OECD: CPI Switzerland
        'balance': 'CHFCENTRALBANK'     # SNB Balance Sheet
    },
}

# --- MOTEUR DE CALCUL (BACKEND) ---

@st.cache_data(ttl=24*3600) # Cache les données pendant 24h pour éviter les erreurs de requêtes
def get_macro_data():
    """Télécharge les données fraîches depuis FRED"""
    data = []
    # On prend 5 ans d'historique pour établir la "norme"
    start_date = datetime.now() - timedelta(days=365*5)
    
    # Barre de progression pour l'interface
    progress_text = "Connexion à la FED en cours..."
    my_bar = st.progress(0, text=progress_text)
    
    total = len(central_banks)
    count = 0

    for currency, codes in central_banks.items():
        try:
            # 1. TAUX DIRECTEUR
            rate_s = fred.get_series(codes['rate'], observation_start=start_date)
            # Remplissage des valeurs manquantes (Forward Fill) pour éviter les erreurs si la donnée date d'hier
            rate_s = rate_s.fillna(method='ffill')
            
            if rate_s.empty:
                raise ValueError(f"Série Taux vide pour {currency}")
                
            cur_rate = rate_s.iloc[-1]
            z_rate = calculate_z_score(rate_s)

            # 2. INFLATION (CPI)
            cpi_s = fred.get_series(codes['cpi'], observation_start=start_date)
            cpi_s = cpi_s.fillna(method='ffill')
            
            # Conversion en YoY % (Variation Annuelle)
            cpi_yoy = cpi_s.pct_change(12).dropna() * 100
            
            if cpi_yoy.empty:
                cur_cpi = 0
                z_cpi = 0
            else:
                cur_cpi = cpi_yoy.iloc[-1]
                z_cpi = calculate_z_score(cpi_yoy)

            # 3. BILAN (Balance Sheet)
            cur_bs_chg = 0
            z_bs = 0
            
            if codes['balance']:
                try:
                    bs_s = fred.get_series(codes['balance'], observation_start=start_date)
                    bs_s = bs_s.fillna(method='ffill')
                    # Variation sur 6 mois
                    bs_chg = bs_s.pct_change(26).dropna() * 100
                    if not bs_chg.empty:
                        cur_bs_chg = bs_chg.iloc[-1]
                        z_bs = calculate_z_score(bs_chg)
                except:
                    # Si le bilan plante, on continue sans lui (pas bloquant)
                    cur_bs_chg = 0
                    z_bs = 0

            # 4. SCORE MACRO GLOBAL
            # Formule : (Z-Rate * 2) + (Z-CPI * 1) - (Z-Balance * 0.5)
            score = (z_rate * 2.0) + (z_cpi * 1.0) - (z_bs * 0.5)

            data.append({
                'Devise': currency,
                'Taux (%)': round(cur_rate, 2),
                'Z-Rate': round(z_rate, 2),
                'CPI (%)': round(cur_cpi, 2),
                'Z-CPI': round(z_cpi, 2),
                'Bilan 6M (%)': round(cur_bs_chg, 2),
                'Z-Bilan': round(z_bs, 2),
                'Macro Score': round(score, 2),
                'Date MAJ': datetime.now().strftime("%Y-%m-%d")
            })

        except Exception as e:
            # On affiche l'erreur dans la console mais on ne plante pas l'app
            print(f"⚠️ Erreur pour {currency}: {e}")
            # On ajoute une ligne vide pour ne pas casser le tableau
            data.append({
                'Devise': currency + " (Donnée manquante)",
                'Taux (%)': 0, 'Z-Rate': 0,
                'CPI (%)': 0, 'Z-CPI': 0,
                'Bilan 6M (%)': 0, 'Z-Bilan': 0,
                'Macro Score': -999, # Score très bas pour le mettre à la fin
                'Date MAJ': 'Erreur'
            })
        
        count += 1
        my_bar.progress(count / total, text=f"Téléchargement : {currency}")

    my_bar.empty()
    return pd.DataFrame(data).sort_values(by='Macro Score', ascending=False)

def calculate_z_score(series):
    """Calcule le Z-Score (écart-type)"""
    if len(series) < 12: return 0
    mean = series.mean()
    std = series.std()
    if std == 0: return 0
    return (series.iloc[-1] - mean) / std

# --- FRONTEND (INTERFACE) ---

st.title("🏦 Central Bank Alpha Tool")
st.markdown(f"**Status:** En ligne | **Source:** FRED & FMI | **Dernier refresh:** {datetime.now().strftime('%H:%M')}")

# Chargement des données
df = get_macro_data()

# Filtrer les erreurs éventuelles
df_clean = df[df['Macro Score'] != -999]

# SECTION 1 : VUE D'ENSEMBLE
st.header("1. Tableau de Bord Macro")

col1, col2 = st.columns([3, 1])

with col1:
    def style_dataframe(val):
        color = 'black'
        if isinstance(val, (int, float)):
            if val > 1.5: color = '#27ae60' # Vert foncé
            elif val > 0.5: color = '#2ecc71' # Vert
            elif val < -1.5: color = '#c0392b' # Rouge foncé
            elif val < -0.5: color = '#e74c3c' # Rouge
        return f'color: {color}; font-weight: bold'

    st.dataframe(df_clean.style.applymap(style_dataframe, subset=['Z-Rate', 'Z-CPI', 'Z-Bilan', 'Macro Score'])
                 .format("{:.2f}", subset=['Taux (%)', 'Z-Rate', 'CPI (%)', 'Z-CPI', 'Bilan 6M (%)', 'Z-Bilan', 'Macro Score']),
                 use_container_width=True, height=400)

with col2:
    st.subheader("Signaux Forts")
    if not df_clean.empty:
        best = df_clean.iloc[0]
        worst = df_clean.iloc[-1]
        
        st.success(f"**LONG (Achat)**\n\n# {best['Devise']}")
        st.metric("Score Hawk", best['Macro Score'])
        
        st.error(f"**SHORT (Vente)**\n\n# {worst['Devise']}")
        st.metric("Score Dove", worst['Macro Score'])
        
        spread = best['Macro Score'] - worst['Macro Score']
        st.info(f"⚡ Spread Max: {round(spread, 2)}")

# SECTION 2 : ANALYSE VISUELLE
st.divider()
st.header("2. Analyse des Cycles (Z-Score Map)")

col_chart1, col_chart2 = st.columns([2, 1])

with col_chart1:
    fig = px.scatter(df_clean, x="Z-CPI", y="Z-Rate", text="Devise", 
                     size="Taux (%)", color="Macro Score",
                     color_continuous_scale="RdYlGn",
                     title="Positionnement Cyclique : Taux vs Inflation (Z-Scores)",
                     labels={"Z-CPI": "Inflation (Z-Score)", "Z-Rate": "Taux Directeur (Z-Score)"})
    
    fig.add_hline(y=0, line_dash="dash", line_color="grey")
    fig.add_vline(x=0, line_dash="dash", line_color="grey")
    fig.update_traces(textposition='top center', marker=dict(size=25, line=dict(width=2, color='DarkSlateGrey')))
    
    st.plotly_chart(fig, use_container_width=True)

with col_chart2:
    st.markdown("""
    **Guide de lecture :**
    
    *   🟢 **Zone Hawkish (Haut-Droite)** : Taux élevés & Inflation élevée. La banque combat l'inflation. Devise forte.
    *   🟠 **Zone de Risque (Bas-Droite)** : Inflation élevée mais Taux bas. La banque est en retard ("Behind the curve"). Devise faible.
    *   🔴 **Zone Dovish (Bas-Gauche)** : Taux bas & Inflation basse. Économie au ralenti.
    """)

# SECTION 3 : GÉNÉRATEUR DE PAIRES
st.divider()
st.header("3. Opportunités Forex (Algo)")

trade_ideas = []
# On compare chaque paire possible
for i, row_long in df_clean.iterrows():
    for j, row_short in df_clean.iterrows():
        if row_long['Devise'] != row_short['Devise']:
            spread = row_long['Macro Score'] - row_short['Macro Score']
            
            # Filtre : On ne garde que les écarts significatifs (> 1.5)
            if spread > 1.5:
                pair = f"{row_long['Devise'][:3]}/{row_short['Devise'][:3]}"
                
                # Raisonnement automatique
                reason = "Divergence Politique Globale"
                if row_long['Z-Rate'] > 1.0 and row_short['Z-Rate'] < 0:
                    reason = "Différentiel de Taux (Carry Trade)"
                elif row_long['Z-CPI'] > 1.5 and row_short['Z-CPI'] < 0.5:
                    reason = "Réaction à l'Inflation"
                
                trade_ideas.append({
                    'Paire': pair,
                    'Action': 'ACHAT',
                    'Score Spread': round(spread, 2),
                    'Logique': reason
                })

df_trades = pd.DataFrame(trade_ideas).sort_values(by='Score Spread', ascending=False)

if not df_trades.empty:
    st.table(df_trades.head(7))
else:
    st.write("Aucune divergence majeure détectée aujourd'hui.")
