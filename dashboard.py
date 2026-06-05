"""
dashboard.py
------------
Tableau de bord de suivi des paris tennis ATP+WTA.
Lancement : streamlit run dashboard.py

Architecture en 5 onglets :
  1. Aujourd'hui  : paris du jour, bankroll, streak
  2. Performance  : KPIs, courbes, évolution mensuelle
  3. Analyse      : breakdowns par surface/circuit/bookmaker/value
  4. Modèle       : calibration des probabilités, distributions
  5. Logs         : journal complet filtrable
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import os
from datetime import datetime, timedelta
from config_public import BANKROLL_INITIALE, DRAWDOWN_MAX

DOSSIER_SCRIPT = os.path.dirname(os.path.abspath(__file__))
JOURNAL_PATH = os.path.join(DOSSIER_SCRIPT, 'journal_paris.csv')

# Configuration globale de la page
st.set_page_config(
    page_title="Tennis Betting Dashboard",
    page_icon="🎾",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ============================================================
# AUTHENTIFICATION PAR MOT DE PASSE
# ============================================================

def check_password():
    """Affiche un écran de connexion et vérifie le mot de passe."""
    
    def password_entered():
        """Vérifie le mot de passe quand l'utilisateur appuie sur Entrée."""
        if st.session_state["password"] == st.secrets["password"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # Ne pas garder le mot de passe en mémoire
        else:
            st.session_state["password_correct"] = False

    # Si déjà authentifié, accès direct
    if st.session_state.get("password_correct", False):
        return True

    # Affichage de l'écran de connexion
    st.markdown(
        """
        <div style='text-align: center; padding: 50px 20px;'>
            <h1>🎾 Tennis Betting Dashboard</h1>
            <p style='color: #6B7280; font-size: 1.1rem;'>
                Accès privé — veuillez entrer le mot de passe
            </p>
        </div>
        """,
        unsafe_allow_html=True
    )
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.text_input(
            "Mot de passe",
            type="password",
            on_change=password_entered,
            key="password",
            placeholder="Entrez le mot de passe"
        )
        
        if "password_correct" in st.session_state and not st.session_state["password_correct"]:
            st.error("❌ Mot de passe incorrect")
        
        st.caption(
            "🔒 Ce dashboard est un outil personnel partagé en privé. "
            "Si vous n'avez pas le mot de passe, contactez le propriétaire."
        )
    
    return False


# Vérification du mot de passe — bloque l'accès si non authentifié
if not check_password():
    st.stop()
# ============================================================
# CUSTOM CSS - Polishing visuel niveau pro
# ============================================================
st.markdown("""
<style>
    /* Réduire l'espace en haut */
    .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
        max-width: 1400px;
    }

    /* Titres plus élégants */
    h1, h2, h3 {
        color: #1F2937;
        font-weight: 600;
    }

    /* Onglets plus visibles */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 45px;
        padding: 0px 24px;
        background-color: #F3F4F6;
        border-radius: 8px 8px 0 0;
        font-weight: 500;
    }
    .stTabs [aria-selected="true"] {
        background-color: #1F2937;
        color: white;
    }

    /* Cartes metric plus lisibles */
    [data-testid="stMetricValue"] {
        font-size: 1.8rem;
        font-weight: 700;
    }
    [data-testid="stMetricLabel"] {
        font-size: 0.85rem;
        color: #6B7280;
        font-weight: 500;
    }
    [data-testid="stMetricDelta"] {
        font-size: 0.9rem;
    }

    /* Boutons plus pro */
    .stButton button {
        border-radius: 6px;
        font-weight: 500;
    }
    .stDownloadButton button {
        background-color: #1F2937;
        color: white;
        border-radius: 6px;
        font-weight: 500;
    }

    /* Selectbox plus lisible */
    .stSelectbox label {
        font-weight: 500;
        color: #374151;
    }

    /* Footer discret */
    .stCaption {
        color: #9CA3AF;
    }

    /* Espace entre les sections */
    hr {
        margin-top: 1.5rem;
        margin-bottom: 1.5rem;
    }
</style>
""", unsafe_allow_html=True)

# ============================================================
# CHARGEMENT ET PRÉPARATION DES DONNÉES
# ============================================================

@st.cache_data(ttl=60)
def charger_journal():
    """Charge le journal et prépare les colonnes numériques."""
    if not os.path.exists(JOURNAL_PATH):
        return None
    df = pd.read_csv(JOURNAL_PATH)
    if df.empty:
        return df

    # Conversions numériques
    df['Cote_num'] = pd.to_numeric(df['Cote'], errors='coerce')
    df['Mise_num'] = pd.to_numeric(
        df['Mise_pct'].astype(str).str.replace('%', '').str.strip(),
        errors='coerce'
    )
    df['Value_num'] = pd.to_numeric(df['Value'], errors='coerce')
    df['Proba_num'] = pd.to_numeric(
        df['Proba_IA'].astype(str).str.replace('%', '').str.strip(),
        errors='coerce'
    ) / 100
    df['Date_parsed'] = pd.to_datetime(df['Date'], errors='coerce')

    # Compatibilité ascendante : si Circuit/Mode absents (ancien format)
    if 'Circuit' not in df.columns:
        df['Circuit'] = 'ATP'
    if 'Mode' not in df.columns:
        df['Mode'] = 'PARI_REEL'

    return df


def calculer_bankroll_curve(df_joues, bankroll_initiale=None):
    """Calcule l'évolution de la bankroll pari après pari."""
    if bankroll_initiale is None:
        bankroll_initiale = BANKROLL_INITIALE
    capital = [bankroll_initiale]
    dates = [df_joues['Date_parsed'].min() if len(df_joues) > 0 else datetime.today()]

    for _, r in df_joues.iterrows():
        mise_euros = capital[-1] * r['Mise_num'] / 100
        if r['Resultat'] == 'GAGNE':
            nouvelle_bk = capital[-1] + mise_euros * (r['Cote_num'] - 1)
        else:
            nouvelle_bk = capital[-1] - mise_euros
        capital.append(nouvelle_bk)
        dates.append(r['Date_parsed'])
    return dates, capital


def calculer_kpis(df_joues, bankroll_initiale=None):
    """Calcule l'ensemble des KPIs à partir d'un DataFrame de paris résolus."""
    if bankroll_initiale is None:
        bankroll_initiale = BANKROLL_INITIALE

    if len(df_joues) == 0:
        return {
            'gagnes': 0, 'perdus': 0, 'joues': 0,
            'winrate': 0, 'bankroll': bankroll_initiale,
            'profit': 0, 'roi_mise': 0, 'roi_bankroll': 0,
            'pic_bankroll': bankroll_initiale, 'drawdown': 0,
            'capital_curve': [bankroll_initiale]
        }

    gagnes = len(df_joues[df_joues['Resultat'] == 'GAGNE'])
    perdus = len(df_joues[df_joues['Resultat'] == 'PERDU'])
    joues = gagnes + perdus
    winrate = (gagnes / joues * 100) if joues > 0 else 0

    _, capital_curve = calculer_bankroll_curve(df_joues, bankroll_initiale)
    bankroll = capital_curve[-1]
    pic_bankroll = max(capital_curve)
    profit = bankroll - bankroll_initiale
    mises_totales = df_joues.apply(
        lambda r: bankroll_initiale * r['Mise_num'] / 100, axis=1
    ).sum()
    roi_mise = (profit / mises_totales * 100) if mises_totales > 0 else 0
    roi_bankroll = (profit / bankroll_initiale * 100)
    drawdown = ((pic_bankroll - bankroll) / pic_bankroll * 100) if pic_bankroll > 0 else 0

    return {
        'gagnes': gagnes, 'perdus': perdus, 'joues': joues,
        'winrate': winrate, 'bankroll': bankroll,
        'profit': profit, 'roi_mise': roi_mise, 'roi_bankroll': roi_bankroll,
        'pic_bankroll': pic_bankroll, 'drawdown': drawdown,
        'capital_curve': capital_curve
    }


# ============================================================
# HEADER GLOBAL
# ============================================================

st.title("🎾 Tennis Betting Dashboard")
col_h1, col_h2, col_h3 = st.columns([2, 2, 1])
with col_h1:
    st.caption(f"📅 Dernière actualisation : {datetime.now().strftime('%d/%m/%Y %H:%M')}")
with col_h2:
    st.caption(f"💰 Bankroll initiale : {BANKROLL_INITIALE:.2f} €")

df = charger_journal()

if df is None:
    st.error(f"❌ Journal introuvable : {JOURNAL_PATH}")
    st.stop()

if df.empty:
    st.info("ℹ️ Aucun pari dans le journal pour le moment. Lancez l'orchestrateur pour générer des prédictions.")
    st.stop()

with col_h3:
    st.metric("Total paris", len(df))


# ============================================================
# NAVIGATION EN ONGLETS
# ============================================================

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📅 Aujourd'hui",
    "📊 Performance",
    "🔍 Analyse",
    "🧠 Modèle",
    "📋 Logs"
])


# ============================================================
# ONGLET 1 — AUJOURD'HUI
# ============================================================

with tab1:
    # --- BANDEAU SUPÉRIEUR : 3 KPIs principaux ---
    df_joues_global = df[df['Resultat'].isin(['GAGNE', 'PERDU'])].copy()
    df_joues_global = df_joues_global.sort_values('Date_parsed')

    kpis_global = calculer_kpis(df_joues_global)

    # Calcul du streak en cours
    if len(df_joues_global) > 0:
        derniers_resultats = df_joues_global['Resultat'].tail(20).tolist()
        derniers_resultats.reverse()  # du plus récent au plus ancien
        dernier_resultat = derniers_resultats[0]
        streak = 0
        for r in derniers_resultats:
            if r == dernier_resultat:
                streak += 1
            else:
                break
        streak_label = f"+{streak} gagnés ✅" if dernier_resultat == 'GAGNE' else f"-{streak} perdus ❌"
    else:
        streak = 0
        streak_label = "Aucun pari résolu"

    col_kpi1, col_kpi2, col_kpi3 = st.columns(3)
    col_kpi1.metric(
        "💰 Bankroll actuelle",
        f"{kpis_global['bankroll']:,.2f} €",
        f"{kpis_global['profit']:+.2f} €"
    )
    col_kpi2.metric(
        "📈 ROI bankroll",
        f"{kpis_global['roi_bankroll']:+.2f}%",
        f"sur {kpis_global['joues']} paris"
    )
    col_kpi3.metric(
        "🔥 Série en cours",
        streak_label
    )

    st.markdown("---")

    # --- PARIS EN ATTENTE : ATP / WTA en colonnes ---
    # Uniquement les PARI_REEL (mise réelle d'argent)
    df_attente = df[
        (df['Resultat'] == 'EN_ATTENTE') & 
        (df['Mode'] == 'PARI_REEL')
    ].copy()

    st.markdown("## 📅 Paris en attente")

    if len(df_attente) == 0:
        st.info("ℹ️ Aucun pari en attente actuellement.")
    else:
        # Total des mises engagées (uniquement PARI_REEL, pas OBSERVATION)
        df_attente_reels = df_attente[df_attente['Mode'] == 'PARI_REEL'].copy()
        mises_engagees = df_attente_reels.apply(
            lambda r: kpis_global['bankroll'] * r['Mise_num'] / 100, axis=1
        ).sum() if len(df_attente_reels) > 0 else 0

        col_info1, col_info2 = st.columns(2)
        col_info1.metric("Paris réels", len(df_attente))
        col_info2.metric("💵 Mises engagées", f"{mises_engagees:,.2f} €")

        # Séparation ATP / WTA
        col_atp, col_wta = st.columns(2)

        with col_atp:
            st.markdown("### 🎾 ATP")
            df_attente_atp = df_attente[df_attente['Circuit'] == 'ATP']
            if len(df_attente_atp) == 0:
                st.caption("Aucun pari ATP en attente.")
            else:
                for _, r in df_attente_atp.iterrows():
                    badge = "🟢 RÉEL" if r['Mode'] == 'PARI_REEL' else "⚪ OBS"
                    with st.container():
                        st.markdown(
                            f"**{r['Joueur_parie']}** vs {r['Adversaire']}  \n"
                            f"📍 {r['Tournoi']} ({r['Surface']}) — Round {r.get('Round', '?')}  \n"
                            f"🎯 Proba IA : **{r['Proba_IA']}** | 🎲 Cote {r['Cote']} @ {r['Bookmaker']}  \n"
                            f"💵 Mise : **{r['Mise_pct']}** | Edge : {r['Value']}  \n"
                            f"{badge}"
                        )
                        st.markdown("")

        with col_wta:
            st.markdown("### 🎾 WTA")
            df_attente_wta = df_attente[df_attente['Circuit'] == 'WTA']
            if len(df_attente_wta) == 0:
                st.caption("Aucun pari WTA en attente.")
            else:
                for _, r in df_attente_wta.iterrows():
                    badge = "🟢 RÉEL" if r['Mode'] == 'PARI_REEL' else "⚪ OBS"
                    with st.container():
                        st.markdown(
                            f"**{r['Joueur_parie']}** vs {r['Adversaire']}  \n"
                            f"📍 {r['Tournoi']} ({r['Surface']}) — Round {r.get('Round', '?')}  \n"
                            f"🎯 Proba IA : **{r['Proba_IA']}** | 🎲 Cote {r['Cote']} @ {r['Bookmaker']}  \n"
                            f"💵 Mise : **{r['Mise_pct']}** | Edge : {r['Value']}  \n"
                            f"{badge}"
                        )
                        st.markdown("")

    st.markdown("---")

    # --- AVIS DU JOUR : OBSERVATIONS + AVIS LIBRES (tout ce qui n'est pas pari réel) ---
    df_avis = df[
        (df['Resultat'] == 'EN_ATTENTE') & 
        (df['Mode'].isin(['OBSERVATION', 'AVIS_LIBRE']))
    ].copy()

    st.markdown("## 🔮 Mes avis du jour")
    st.caption(
        "Tous les matchs analysés par l'IA. "
        "Aucune mise réelle, juste mon pronostic du favori avec sa probabilité. "
        "Utile pour suivre les matchs qui n'ont pas passé mes filtres de pari."
    )

    if len(df_avis) == 0:
        st.info("ℹ️ Aucun avis du jour pour le moment.")
    else:
        col_avis_atp, col_avis_wta = st.columns(2)

        with col_avis_atp:
            st.markdown("### 🎾 ATP")
            df_avis_atp = df_avis[df_avis['Circuit'] == 'ATP']
            if len(df_avis_atp) == 0:
                st.caption("Aucun avis ATP.")
            else:
                for _, r in df_avis_atp.iterrows():
                    # Couleur selon la confiance (proba)
                    proba = r['Proba_num']
                    if proba >= 0.70:
                        emoji_conf = "🟢"
                        niveau = "Forte confiance"
                    elif proba >= 0.60:
                        emoji_conf = "🟡"
                        niveau = "Confiance modérée"
                    else:
                        emoji_conf = "⚪"
                        niveau = "Confiance limitée"
                    
                    type_avis = "⚪ Observation (filtre WTA)" if r['Mode'] == 'OBSERVATION' else "🔮 Avis libre"
                    st.markdown(
                        f"{emoji_conf} **{r['Joueur_parie']}** vs {r['Adversaire']}  \n"
                        f"📍 {r['Tournoi']} ({r['Surface']}) — Round {r.get('Round', '?')}  \n"
                        f"🎯 Proba IA : **{r['Proba_IA']}** ({niveau})  \n"
                        f"💰 Cote disponible : {r['Cote']} @ {r['Bookmaker']}  \n"
                        f"{type_avis}"
                    )
                    st.markdown("")

        with col_avis_wta:
            st.markdown("### 🎾 WTA")
            df_avis_wta = df_avis[df_avis['Circuit'] == 'WTA']
            if len(df_avis_wta) == 0:
                st.caption("Aucun avis WTA.")
            else:
                for _, r in df_avis_wta.iterrows():
                    proba = r['Proba_num']
                    if proba >= 0.70:
                        emoji_conf = "🟢"
                        niveau = "Forte confiance"
                    elif proba >= 0.60:
                        emoji_conf = "🟡"
                        niveau = "Confiance modérée"
                    else:
                        emoji_conf = "⚪"
                        niveau = "Confiance limitée"
                    
                    type_avis = "⚪ Observation (filtre WTA)" if r['Mode'] == 'OBSERVATION' else "🔮 Avis libre"
                    st.markdown(
                        f"{emoji_conf} **{r['Joueur_parie']}** vs {r['Adversaire']}  \n"
                        f"📍 {r['Tournoi']} ({r['Surface']}) — Round {r.get('Round', '?')}  \n"
                        f"🎯 Proba IA : **{r['Proba_IA']}** ({niveau})  \n"
                        f"💰 Cote disponible : {r['Cote']} @ {r['Bookmaker']}  \n"
                        f"{type_avis}"
                    )
                    st.markdown("")

    st.markdown("---")

    # --- RÉSULTATS RÉCENTS : 5 derniers paris résolus ---
    st.markdown("## 📜 Résultats récents")

    df_recents = df_joues_global.sort_values('Date_parsed', ascending=False).head(5)
    if len(df_recents) == 0:
        st.info("Aucun pari résolu pour le moment.")
    else:
        for _, r in df_recents.iterrows():
            icone = "✅" if r['Resultat'] == 'GAGNE' else "❌"
            gain_perte = (
                f"+{r['Mise_num'] * (r['Cote_num'] - 1):.2f}% bankroll"
                if r['Resultat'] == 'GAGNE'
                else f"-{r['Mise_num']:.2f}% bankroll"
            )
            circuit_badge = "🎾 ATP" if r['Circuit'] == 'ATP' else "🎾 WTA"
            mode_badge = "🟢 RÉEL" if r['Mode'] == 'PARI_REEL' else "⚪ OBS"
            st.markdown(
                f"{icone} **{r['Joueur_parie']}** vs {r['Adversaire']} — "
                f"{r['Tournoi']} ({r['Surface']}) | "
                f"Cote {r['Cote']} | {gain_perte} | {circuit_badge} | {mode_badge}"
            )


# ============================================================
# ONGLET 2 — PERFORMANCE
# ============================================================

with tab2:
    # --- FILTRES EN HAUT ---
    col_f1, col_f2 = st.columns([1, 1])
    with col_f1:
        periode = st.selectbox(
            "📅 Période",
            ["Tout", "7 derniers jours", "30 derniers jours", "90 derniers jours"],
            index=0,
            key="periode_perf"
        )
    with col_f2:
        inclure_observation = st.checkbox(
            "Inclure les paris en mode OBSERVATION dans les stats",
            value=False,
            help="Si coché, les paris WTA Clay/Grass (observation) seront inclus dans le calcul"
        )

    # --- FILTRAGE DES DONNÉES ---
    df_joues_perf = df[df['Resultat'].isin(['GAGNE', 'PERDU'])].copy()

    # Filtrage par mode
    if not inclure_observation:
        df_joues_perf = df_joues_perf[df_joues_perf['Mode'] == 'PARI_REEL']

    # Filtrage par période
    if periode != "Tout" and len(df_joues_perf) > 0:
        jours = {"7 derniers jours": 7, "30 derniers jours": 30, "90 derniers jours": 90}[periode]
        date_limite = datetime.today() - timedelta(days=jours)
        df_joues_perf = df_joues_perf[df_joues_perf['Date_parsed'] >= date_limite]

    if len(df_joues_perf) == 0:
        st.info(f"Aucun pari résolu sur la période sélectionnée ({periode}).")
    else:
        # --- SÉPARATION ATP / WTA ---
        df_atp = df_joues_perf[df_joues_perf['Circuit'] == 'ATP'].sort_values('Date_parsed')
        df_wta = df_joues_perf[df_joues_perf['Circuit'] == 'WTA'].sort_values('Date_parsed')
        df_total = df_joues_perf.sort_values('Date_parsed')

        kpis_atp = calculer_kpis(df_atp)
        kpis_wta = calculer_kpis(df_wta)
        kpis_tot = calculer_kpis(df_total)

        # --- BANDEAU TOTAL ---
        st.markdown("### 🌐 Total")
        col_t1, col_t2, col_t3, col_t4 = st.columns(4)
        col_t1.metric("Bankroll", f"{kpis_tot['bankroll']:,.2f} €", f"{kpis_tot['profit']:+.2f} €")
        col_t2.metric("Winrate", f"{kpis_tot['winrate']:.1f}%",
                     f"{kpis_tot['gagnes']}G / {kpis_tot['perdus']}P")
        col_t3.metric("ROI bankroll", f"{kpis_tot['roi_bankroll']:+.2f}%")
        col_t4.metric("Drawdown",
                     f"-{kpis_tot['drawdown']:.1f}%",
                     "⚠️" if kpis_tot['drawdown'] >= DRAWDOWN_MAX * 100 else "OK")

        st.markdown("---")

        # --- COMPARATIF ATP / WTA EN 2 COLONNES ---
        col_atp_perf, col_wta_perf = st.columns(2)

        with col_atp_perf:
            st.markdown("### 🎾 ATP")
            if kpis_atp['joues'] == 0:
                st.caption("Aucun pari ATP sur cette période.")
            else:
                col_a1, col_a2 = st.columns(2)
                col_a1.metric("Paris", kpis_atp['joues'])
                col_a2.metric("Winrate", f"{kpis_atp['winrate']:.1f}%")
                col_a3, col_a4 = st.columns(2)
                col_a3.metric("ROI", f"{kpis_atp['roi_bankroll']:+.2f}%")
                col_a4.metric("Profit", f"{kpis_atp['profit']:+.2f} €")

        with col_wta_perf:
            st.markdown("### 🎾 WTA")
            if kpis_wta['joues'] == 0:
                st.caption("Aucun pari WTA sur cette période.")
            else:
                col_w1, col_w2 = st.columns(2)
                col_w1.metric("Paris", kpis_wta['joues'])
                col_w2.metric("Winrate", f"{kpis_wta['winrate']:.1f}%")
                col_w3, col_w4 = st.columns(2)
                col_w3.metric("ROI", f"{kpis_wta['roi_bankroll']:+.2f}%")
                col_w4.metric("Profit", f"{kpis_wta['profit']:+.2f} €")

        st.markdown("---")

        # --- COURBES DE BANKROLL (3 courbes sur un graphe) ---
        st.markdown("### 💰 Évolution de la bankroll")

        fig_bk = go.Figure()

        # Courbe Totale
        if len(df_total) > 0:
            fig_bk.add_trace(go.Scatter(
                x=list(range(len(kpis_tot['capital_curve']))),
                y=kpis_tot['capital_curve'],
                mode='lines',
                line=dict(color='#2C3E50', width=3),
                name=f"Total ({kpis_tot['roi_bankroll']:+.1f}%)"
            ))

        # Courbe ATP
        if len(df_atp) > 0:
            fig_bk.add_trace(go.Scatter(
                x=list(range(len(kpis_atp['capital_curve']))),
                y=kpis_atp['capital_curve'],
                mode='lines',
                line=dict(color='#3498DB', width=2, dash='dot'),
                name=f"ATP seul ({kpis_atp['roi_bankroll']:+.1f}%)"
            ))

        # Courbe WTA
        if len(df_wta) > 0:
            fig_bk.add_trace(go.Scatter(
                x=list(range(len(kpis_wta['capital_curve']))),
                y=kpis_wta['capital_curve'],
                mode='lines',
                line=dict(color='#E74C3C', width=2, dash='dot'),
                name=f"WTA seul ({kpis_wta['roi_bankroll']:+.1f}%)"
            ))

        fig_bk.add_hline(
            y=BANKROLL_INITIALE, line_dash="dash", line_color="gray",
            annotation_text=f"Capital initial ({BANKROLL_INITIALE:.0f} €)"
        )
        fig_bk.update_layout(
            xaxis_title="Numéro de pari",
            yaxis_title="Bankroll (€)",
            height=400,
            hovermode='x unified',
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        st.plotly_chart(fig_bk, use_container_width=True)

        # --- ÉVOLUTION MENSUELLE ---
        st.markdown("### 📅 ROI mensuel")

        df_total['Mois'] = df_total['Date_parsed'].dt.to_period('M').astype(str)

        roi_mensuel = []
        for mois in sorted(df_total['Mois'].unique()):
            grp = df_total[df_total['Mois'] == mois]
            for circuit in ['ATP', 'WTA']:
                sub = grp[grp['Circuit'] == circuit]
                if len(sub) == 0:
                    continue
                gains = sub.apply(
                    lambda r: r['Mise_num'] * (r['Cote_num'] - 1) if r['Resultat'] == 'GAGNE'
                              else -r['Mise_num'], axis=1
                ).sum()
                mises = sub['Mise_num'].sum()
                roi_pct = (gains / mises * 100) if mises > 0 else 0
                roi_mensuel.append({
                    'Mois': mois,
                    'Circuit': circuit,
                    'Paris': len(sub),
                    'ROI': roi_pct
                })

        if roi_mensuel:
            df_roi_mensuel = pd.DataFrame(roi_mensuel)
            fig_mois = px.bar(
                df_roi_mensuel,
                x='Mois', y='ROI',
                color='Circuit',
                color_discrete_map={'ATP': '#3498DB', 'WTA': '#E74C3C'},
                barmode='group',
                title=None,
                text='Paris'
            )
            fig_mois.update_traces(texttemplate='%{text} paris', textposition='outside')
            fig_mois.update_layout(
                height=350,
                yaxis_title="ROI (%)",
                xaxis_title="Mois",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            fig_mois.add_hline(y=0, line_dash="dot", line_color="gray")
            st.plotly_chart(fig_mois, use_container_width=True)
        else:
            st.info("Pas encore assez de données pour l'évolution mensuelle.")


# ============================================================
# ONGLET 3 — ANALYSE
# ============================================================

with tab3:
    # --- FILTRES EN HAUT ---
    col_fa1, col_fa2, col_fa3 = st.columns(3)
    with col_fa1:
        filtre_circuit = st.selectbox(
            "🎾 Circuit",
            ["Tous", "ATP seulement", "WTA seulement"],
            key="filtre_circuit_analyse"
        )
    with col_fa2:
        filtre_mode = st.selectbox(
            "💰 Mode",
            ["Paris réels seulement", "Observations seulement", "Tous"],
            key="filtre_mode_analyse"
        )
    with col_fa3:
        filtre_periode = st.selectbox(
            "📅 Période",
            ["Tout", "30 derniers jours", "90 derniers jours", "Année en cours"],
            key="filtre_periode_analyse"
        )

    # --- APPLICATION DES FILTRES ---
    df_analyse = df[df['Resultat'].isin(['GAGNE', 'PERDU'])].copy()

    if filtre_circuit == "ATP seulement":
        df_analyse = df_analyse[df_analyse['Circuit'] == 'ATP']
    elif filtre_circuit == "WTA seulement":
        df_analyse = df_analyse[df_analyse['Circuit'] == 'WTA']

    if filtre_mode == "Paris réels seulement":
        df_analyse = df_analyse[df_analyse['Mode'] == 'PARI_REEL']
    elif filtre_mode == "Observations seulement":
        df_analyse = df_analyse[df_analyse['Mode'] == 'OBSERVATION']

    if filtre_periode != "Tout" and len(df_analyse) > 0:
        if filtre_periode == "30 derniers jours":
            date_lim = datetime.today() - timedelta(days=30)
        elif filtre_periode == "90 derniers jours":
            date_lim = datetime.today() - timedelta(days=90)
        elif filtre_periode == "Année en cours":
            date_lim = datetime(datetime.today().year, 1, 1)
        df_analyse = df_analyse[df_analyse['Date_parsed'] >= date_lim]

    # --- AFFICHAGE DU RÉSUMÉ DE FILTRAGE ---
    st.caption(f"📌 **{len(df_analyse)} paris** correspondent aux filtres actuels")
    st.markdown("---")

    if len(df_analyse) == 0:
        st.info("Aucun pari ne correspond aux filtres sélectionnés.")
    else:
        # Fonction utilitaire pour calculer ROI sur un sous-ensemble
        def stats_groupe(grp):
            if len(grp) == 0:
                return None
            gagnes = len(grp[grp['Resultat'] == 'GAGNE'])
            perdus = len(grp[grp['Resultat'] == 'PERDU'])
            joues = gagnes + perdus
            winrate = (gagnes / joues * 100) if joues > 0 else 0
            gains = grp.apply(
                lambda r: r['Mise_num'] * (r['Cote_num'] - 1) if r['Resultat'] == 'GAGNE'
                          else -r['Mise_num'], axis=1
            ).sum()
            mises = grp['Mise_num'].sum()
            roi_pct = (gains / mises * 100) if mises > 0 else 0
            return {
                'Paris': joues,
                'Winrate_pct': winrate,
                'ROI_pct': roi_pct,
                'Gains_pct': gains
            }

        # ============================================================
        # ROI PAR SURFACE
        # ============================================================
        st.markdown("### 🏟️ ROI par surface")

        stats_surf = []
        for surf in sorted(df_analyse['Surface'].dropna().unique()):
            grp = df_analyse[df_analyse['Surface'] == surf]
            s = stats_groupe(grp)
            if s:
                stats_surf.append({
                    'Surface': surf,
                    'Paris': s['Paris'],
                    'Winrate': f"{s['Winrate_pct']:.1f}%",
                    'ROI': s['ROI_pct']
                })

        if stats_surf:
            df_stats_surf = pd.DataFrame(stats_surf)
            col_sa, col_sb = st.columns([1, 2])
            with col_sa:
                st.dataframe(
                    df_stats_surf.assign(
                        ROI=df_stats_surf['ROI'].apply(lambda x: f"{x:+.2f}%")
                    ),
                    hide_index=True, use_container_width=True
                )
            with col_sb:
                couleurs_surf = {'Clay': '#D2691E', 'Hard': '#4682B4', 'Grass': '#228B22'}
                fig_surf = px.bar(
                    df_stats_surf,
                    x='Surface', y='ROI',
                    color='Surface',
                    color_discrete_map=couleurs_surf,
                    text=df_stats_surf['ROI'].apply(lambda x: f"{x:+.1f}%")
                )
                fig_surf.update_traces(textposition='outside')
                fig_surf.update_layout(height=300, showlegend=False, yaxis_title="ROI (%)")
                fig_surf.add_hline(y=0, line_dash="dot", line_color="gray")
                st.plotly_chart(fig_surf, use_container_width=True)

        st.markdown("---")

        # ============================================================
        # ROI PAR BOOKMAKER
        # ============================================================
        st.markdown("### 🏦 ROI par bookmaker")

        stats_book = []
        for book in sorted(df_analyse['Bookmaker'].dropna().unique()):
            grp = df_analyse[df_analyse['Bookmaker'] == book]
            s = stats_groupe(grp)
            if s:
                stats_book.append({
                    'Bookmaker': book,
                    'Paris': s['Paris'],
                    'Winrate': f"{s['Winrate_pct']:.1f}%",
                    'ROI': s['ROI_pct']
                })

        if stats_book:
            df_stats_book = pd.DataFrame(stats_book)
            col_ba, col_bb = st.columns([1, 2])
            with col_ba:
                st.dataframe(
                    df_stats_book.assign(
                        ROI=df_stats_book['ROI'].apply(lambda x: f"{x:+.2f}%")
                    ),
                    hide_index=True, use_container_width=True
                )
            with col_bb:
                couleurs_book = {
                    'Betclic': '#E63946', 'Winamax': '#F1C40F',
                    'Unibet': '#2ECC71', '?': '#95A5A6'
                }
                fig_book = px.bar(
                    df_stats_book,
                    x='Bookmaker', y='ROI',
                    color='Bookmaker',
                    color_discrete_map=couleurs_book,
                    text=df_stats_book['ROI'].apply(lambda x: f"{x:+.1f}%")
                )
                fig_book.update_traces(textposition='outside')
                fig_book.update_layout(height=300, showlegend=False, yaxis_title="ROI (%)")
                fig_book.add_hline(y=0, line_dash="dot", line_color="gray")
                st.plotly_chart(fig_book, use_container_width=True)

        st.markdown("---")

        # ============================================================
        # ROI PAR TRANCHE DE VALUE_EDGE
        # ============================================================
        st.markdown("### 🎯 ROI par tranche de value_edge")
        st.caption("Identifie les paris piégeux (edge trop élevé = souvent suspect)")

        def bin_value(v):
            v = abs(v)
            if v < 0.10:
                return "< 0.10"
            elif v < 0.15:
                return "0.10–0.15"
            elif v < 0.20:
                return "0.15–0.20"
            elif v < 0.30:
                return "0.20–0.30"
            else:
                return "0.30+"

        df_analyse_copy = df_analyse.copy()
        df_analyse_copy['Value_bin'] = df_analyse_copy['Value_num'].apply(bin_value)
        ordre_bins = ["< 0.10", "0.10–0.15", "0.15–0.20", "0.20–0.30", "0.30+"]

        stats_value = []
        for bin_name in ordre_bins:
            grp = df_analyse_copy[df_analyse_copy['Value_bin'] == bin_name]
            s = stats_groupe(grp)
            if s:
                stats_value.append({
                    'Tranche': bin_name,
                    'Paris': s['Paris'],
                    'Winrate': f"{s['Winrate_pct']:.1f}%",
                    'ROI': s['ROI_pct']
                })

        if stats_value:
            df_stats_value = pd.DataFrame(stats_value)
            col_va, col_vb = st.columns([1, 2])
            with col_va:
                st.dataframe(
                    df_stats_value.assign(
                        ROI=df_stats_value['ROI'].apply(lambda x: f"{x:+.2f}%")
                    ),
                    hide_index=True, use_container_width=True
                )
            with col_vb:
                fig_val = px.bar(
                    df_stats_value, x='Tranche', y='ROI',
                    color='ROI', color_continuous_scale='RdYlGn',
                    color_continuous_midpoint=0,
                    text=df_stats_value['ROI'].apply(lambda x: f"{x:+.1f}%")
                )
                fig_val.update_traces(textposition='outside')
                fig_val.update_layout(height=300, showlegend=False, yaxis_title="ROI (%)")
                fig_val.add_hline(y=0, line_dash="dot", line_color="gray")
                st.plotly_chart(fig_val, use_container_width=True)

        st.markdown("---")

        # ============================================================
        # ROI PAR ROUND
        # ============================================================
        st.markdown("### 🥇 ROI par round")
        st.caption("Indique si certains tours du tournoi sont mieux prédits que d'autres")

        ordre_rounds = ['Q1', 'Q2', 'Q3', 'R128', 'R64', 'R32', 'R16', 'QF', 'SF', 'F']

        stats_round = []
        for round_name in ordre_rounds:
            grp = df_analyse[df_analyse['Round'] == round_name]
            s = stats_groupe(grp)
            if s:
                stats_round.append({
                    'Round': round_name,
                    'Paris': s['Paris'],
                    'Winrate': f"{s['Winrate_pct']:.1f}%",
                    'ROI': s['ROI_pct']
                })

        if stats_round:
            df_stats_round = pd.DataFrame(stats_round)
            col_ra, col_rb = st.columns([1, 2])
            with col_ra:
                st.dataframe(
                    df_stats_round.assign(
                        ROI=df_stats_round['ROI'].apply(lambda x: f"{x:+.2f}%")
                    ),
                    hide_index=True, use_container_width=True
                )
            with col_rb:
                fig_round = px.bar(
                    df_stats_round, x='Round', y='ROI',
                    color='ROI', color_continuous_scale='RdYlGn',
                    color_continuous_midpoint=0,
                    text=df_stats_round['ROI'].apply(lambda x: f"{x:+.1f}%")
                )
                fig_round.update_traces(textposition='outside')
                fig_round.update_layout(
                    height=300, showlegend=False, yaxis_title="ROI (%)",
                    xaxis={'categoryorder': 'array', 'categoryarray': ordre_rounds}
                )
                fig_round.add_hline(y=0, line_dash="dot", line_color="gray")
                st.plotly_chart(fig_round, use_container_width=True)
        else:
            st.info("Pas assez de données par round.")

        st.markdown("---")

        # ============================================================
        # TOP 10 TOURNOIS LES PLUS RENTABLES
        # ============================================================
        st.markdown("### 🏆 Top tournois (≥ 3 paris)")
        st.caption("Tournois où vous obtenez le meilleur ROI (minimum 3 paris pour être significatif)")

        stats_tournois = []
        for tournoi in df_analyse['Tournoi'].dropna().unique():
            grp = df_analyse[df_analyse['Tournoi'] == tournoi]
            s = stats_groupe(grp)
            if s and s['Paris'] >= 3:  # filtre minimum
                stats_tournois.append({
                    'Tournoi': tournoi,
                    'Paris': s['Paris'],
                    'Winrate': f"{s['Winrate_pct']:.1f}%",
                    'ROI': s['ROI_pct'],
                    'ROI_str': f"{s['ROI_pct']:+.2f}%"
                })

        if stats_tournois:
            df_stats_tournois = pd.DataFrame(stats_tournois).sort_values('ROI', ascending=False)
            col_tt1, col_tt2 = st.columns(2)

            with col_tt1:
                st.markdown("**🥇 Top 5 tournois les plus rentables**")
                top5 = df_stats_tournois.head(5)[['Tournoi', 'Paris', 'Winrate', 'ROI_str']]
                top5.columns = ['Tournoi', 'Paris', 'Winrate', 'ROI']
                st.dataframe(top5, hide_index=True, use_container_width=True)

            with col_tt2:
                st.markdown("**🥉 Bottom 5 tournois les moins rentables**")
                bottom5 = df_stats_tournois.tail(5).sort_values('ROI')[['Tournoi', 'Paris', 'Winrate', 'ROI_str']]
                bottom5.columns = ['Tournoi', 'Paris', 'Winrate', 'ROI']
                st.dataframe(bottom5, hide_index=True, use_container_width=True)
        else:
            st.info("Pas encore assez de paris par tournoi (minimum 3) pour faire un classement significatif.")


# ============================================================
# ONGLET 4 — MODÈLE
# ============================================================

with tab4:
    st.markdown(
        "Cet onglet évalue la **qualité prédictive du modèle ML**. "
        "Un modèle bien calibré dit 70% quand ça arrive vraiment 70% du temps."
    )

    # --- FILTRES EN HAUT ---
    col_fm1, col_fm2 = st.columns(2)
    with col_fm1:
        circuit_modele = st.selectbox(
            "🎾 Circuit",
            ["Total", "ATP seulement", "WTA seulement"],
            key="circuit_modele"
        )
    with col_fm2:
        mode_modele = st.selectbox(
            "💰 Mode",
            ["Paris réels seulement", "Tous (réels + observations)"],
            key="mode_modele"
        )

    # Filtrage
    df_modele = df[df['Resultat'].isin(['GAGNE', 'PERDU'])].copy()

    if circuit_modele == "ATP seulement":
        df_modele = df_modele[df_modele['Circuit'] == 'ATP']
    elif circuit_modele == "WTA seulement":
        df_modele = df_modele[df_modele['Circuit'] == 'WTA']

    if mode_modele == "Paris réels seulement":
        df_modele = df_modele[df_modele['Mode'] == 'PARI_REEL']

    st.caption(f"📌 **{len(df_modele)} paris** analysés")
    st.markdown("---")

    if len(df_modele) < 10:
        st.info(
            "⚠️ Au moins 10 paris résolus sont nécessaires pour évaluer le modèle. "
            "Continuez à laisser tourner le système pour accumuler des données."
        )
    else:
        # ============================================================
        # COURBE DE CALIBRATION
        # ============================================================
        st.markdown("### 📐 Calibration des probabilités")
        st.caption(
            "Si la ligne bleue est proche de la ligne diagonale (idéale), "
            "votre modèle est bien calibré."
        )

        # Définir les bins de probabilité (par tranches de 5%)
        bins_proba = [0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95, 1.00]
        bin_labels = ['45-50%', '50-55%', '55-60%', '60-65%', '65-70%',
                      '70-75%', '75-80%', '80-85%', '85-90%', '90-95%', '95%+']

        df_modele_copy = df_modele.copy()
        df_modele_copy['Proba_bin'] = pd.cut(df_modele_copy['Proba_num'], bins=bins_proba, labels=bin_labels)

        calibration_data = []
        for bin_label in bin_labels:
            grp = df_modele_copy[df_modele_copy['Proba_bin'] == bin_label]
            if len(grp) > 0:
                proba_moyenne = grp['Proba_num'].mean()
                taux_reel = (grp['Resultat'] == 'GAGNE').mean()
                calibration_data.append({
                    'Tranche': bin_label,
                    'Proba_predite': proba_moyenne,
                    'Taux_reel': taux_reel,
                    'Paris': len(grp)
                })

        if calibration_data:
            df_calib = pd.DataFrame(calibration_data)

            fig_calib = go.Figure()
            # Diagonale idéale
            fig_calib.add_trace(go.Scatter(
                x=[0.45, 1.0], y=[0.45, 1.0],
                mode='lines',
                line=dict(color='gray', dash='dash', width=2),
                name='Calibration parfaite'
            ))
            # Courbe réelle
            fig_calib.add_trace(go.Scatter(
                x=df_calib['Proba_predite'],
                y=df_calib['Taux_reel'],
                mode='lines+markers',
                line=dict(color='#3498DB', width=3),
                marker=dict(size=df_calib['Paris'] * 2 + 5, sizemode='diameter'),
                name='Votre modèle',
                text=df_calib['Paris'].astype(str) + ' paris',
                hovertemplate='Proba prédite: %{x:.2f}<br>Taux réel: %{y:.2f}<br>%{text}<extra></extra>'
            ))

            fig_calib.update_layout(
                xaxis=dict(title="Probabilité prédite par l'IA", range=[0.4, 1.0]),
                yaxis=dict(title="Taux réel de victoire", range=[0.0, 1.0]),
                height=450,
                hovermode='closest',
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            st.plotly_chart(fig_calib, use_container_width=True)

            # Interprétation automatique
            st.markdown("**🔍 Interprétation :**")
            if len(df_calib) >= 3:
                ecarts = (df_calib['Taux_reel'] - df_calib['Proba_predite']).abs()
                ecart_moyen = ecarts.mean()
                if ecart_moyen < 0.05:
                    st.success(f"✅ Excellente calibration (écart moyen : {ecart_moyen:.1%})")
                elif ecart_moyen < 0.10:
                    st.info(f"🟢 Bonne calibration (écart moyen : {ecart_moyen:.1%})")
                elif ecart_moyen < 0.15:
                    st.warning(f"🟡 Calibration moyenne (écart moyen : {ecart_moyen:.1%})")
                else:
                    st.error(f"🔴 Calibration faible (écart moyen : {ecart_moyen:.1%}) — modèle à surveiller")

        st.markdown("---")

        # ============================================================
        # BRIER SCORE
        # ============================================================
        st.markdown("### 📊 Score de qualité prédictive")

        # Brier Score = mean((proba_predite - resultat_reel)^2)
        df_modele_copy['Resultat_binaire'] = (df_modele_copy['Resultat'] == 'GAGNE').astype(int)
        brier_score = ((df_modele_copy['Proba_num'] - df_modele_copy['Resultat_binaire']) ** 2).mean()

        col_bs1, col_bs2, col_bs3 = st.columns(3)
        col_bs1.metric("Brier Score", f"{brier_score:.4f}")

        # Interprétation
        if brier_score < 0.20:
            interpretation = "🟢 Excellent"
            couleur = "green"
        elif brier_score < 0.22:
            interpretation = "🟢 Bon"
            couleur = "green"
        elif brier_score < 0.24:
            interpretation = "🟡 Moyen"
            couleur = "orange"
        elif brier_score < 0.25:
            interpretation = "🟠 Faible"
            couleur = "orange"
        else:
            interpretation = "🔴 Pile-ou-face"
            couleur = "red"

        col_bs2.metric("Qualité", interpretation)
        col_bs3.caption(
            "Échelle : 0 = parfait, 0.25 = pile-ou-face. "
            "Un modèle pro fait < 0.22."
        )

        st.markdown("---")

        # ============================================================
        # DISTRIBUTION DES PROBABILITÉS PRÉDITES
        # ============================================================
        st.markdown("### 📈 Distribution des probabilités prédites")
        st.caption("Permet de voir dans quelle zone de probabilité votre modèle se positionne.")

        fig_distrib = px.histogram(
            df_modele,
            x='Proba_num',
            nbins=20,
            color_discrete_sequence=['#3498DB'],
            labels={'Proba_num': 'Probabilité prédite', 'count': 'Nombre de paris'}
        )
        fig_distrib.update_layout(
            height=300,
            xaxis_title="Probabilité prédite",
            yaxis_title="Nombre de paris",
            showlegend=False
        )
        st.plotly_chart(fig_distrib, use_container_width=True)

        st.markdown("---")

        # ============================================================
        # DISTRIBUTION DES VALUE_EDGE
        # ============================================================
        st.markdown("### 🎯 Distribution des value_edge")
        st.caption(
            "La value_edge mesure l'écart entre votre proba IA et la proba implicite "
            "de la cote bookmaker. Plus c'est élevé, plus le pari est censé être 'value'."
        )

        fig_edge = px.histogram(
            df_modele,
            x='Value_num',
            nbins=20,
            color_discrete_sequence=['#E67E22'],
            labels={'Value_num': 'Value Edge', 'count': 'Nombre de paris'}
        )
        fig_edge.update_layout(
            height=300,
            xaxis_title="Value Edge",
            yaxis_title="Nombre de paris",
            showlegend=False
        )
        st.plotly_chart(fig_edge, use_container_width=True)

        st.markdown("---")

        # ============================================================
        # PERFORMANCE PAR NIVEAU DE CONFIANCE
        # ============================================================
        st.markdown("### 🎯 Performance par niveau de confiance IA")
        st.caption("Vérifie si les paris à haute confiance sont effectivement plus rentables.")

        df_modele_copy['Conf_bin'] = pd.cut(
            df_modele_copy['Proba_num'],
            bins=[0.45, 0.55, 0.65, 0.75, 0.85, 1.0],
            labels=['45-55% (faible)', '55-65% (modérée)', '65-75% (bonne)',
                    '75-85% (forte)', '85%+ (très forte)']
        )

        stats_conf = []
        for conf_label in df_modele_copy['Conf_bin'].cat.categories:
            grp = df_modele_copy[df_modele_copy['Conf_bin'] == conf_label]
            if len(grp) > 0:
                gagnes = len(grp[grp['Resultat'] == 'GAGNE'])
                winrate = gagnes / len(grp) * 100
                gains = grp.apply(
                    lambda r: r['Mise_num'] * (r['Cote_num'] - 1) if r['Resultat'] == 'GAGNE'
                              else -r['Mise_num'], axis=1
                ).sum()
                mises = grp['Mise_num'].sum()
                roi = (gains / mises * 100) if mises > 0 else 0
                stats_conf.append({
                    'Confiance IA': conf_label,
                    'Paris': len(grp),
                    'Winrate': f"{winrate:.1f}%",
                    'ROI': f"{roi:+.2f}%"
                })

        if stats_conf:
            st.dataframe(pd.DataFrame(stats_conf), hide_index=True, use_container_width=True)
        else:
            st.info("Pas encore assez de données pour cette analyse.")


# ============================================================
# ONGLET 5 — LOGS
# ============================================================

with tab5:
    st.markdown("Vue complète du journal des paris, avec filtres et téléchargement CSV.")

    # --- FILTRES MULTIPLES ---
    col_l1, col_l2, col_l3, col_l4 = st.columns(4)

    with col_l1:
        filtre_circuit_log = st.selectbox(
            "Circuit",
            ["Tous"] + sorted(df['Circuit'].dropna().unique().tolist()),
            key="filtre_circuit_log"
        )
    with col_l2:
        filtre_mode_log = st.selectbox(
            "Mode",
            ["Tous"] + sorted(df['Mode'].dropna().unique().tolist()),
            key="filtre_mode_log"
        )
    with col_l3:
        filtre_resultat_log = st.selectbox(
            "Résultat",
            ["Tous", "EN_ATTENTE", "GAGNE", "PERDU"],
            key="filtre_resultat_log"
        )
    with col_l4:
        filtre_surface_log = st.selectbox(
            "Surface",
            ["Toutes"] + sorted(df['Surface'].dropna().unique().tolist()),
            key="filtre_surface_log"
        )

    # --- RECHERCHE TEXTUELLE ---
    recherche = st.text_input(
        "🔎 Recherche (joueur ou tournoi)",
        placeholder="Ex: Sinner, Roland-Garros, Sabalenka...",
        key="recherche_log"
    )

    # --- APPLICATION DES FILTRES ---
    df_logs = df.copy()

    if filtre_circuit_log != "Tous":
        df_logs = df_logs[df_logs['Circuit'] == filtre_circuit_log]
    if filtre_mode_log != "Tous":
        df_logs = df_logs[df_logs['Mode'] == filtre_mode_log]
    if filtre_resultat_log != "Tous":
        df_logs = df_logs[df_logs['Resultat'] == filtre_resultat_log]
    if filtre_surface_log != "Toutes":
        df_logs = df_logs[df_logs['Surface'] == filtre_surface_log]

    if recherche:
        recherche_low = recherche.lower()
        mask = (
            df_logs['Joueur_parie'].str.lower().str.contains(recherche_low, na=False) |
            df_logs['Adversaire'].str.lower().str.contains(recherche_low, na=False) |
            df_logs['Tournoi'].str.lower().str.contains(recherche_low, na=False)
        )
        df_logs = df_logs[mask]

    # --- COMPTEUR ET TÉLÉCHARGEMENT ---
    col_count, col_dl = st.columns([2, 1])
    with col_count:
        st.caption(f"📌 **{len(df_logs)} pari(s)** correspondent aux filtres")
    with col_dl:
        if len(df_logs) > 0:
            csv = df_logs.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Télécharger CSV",
                data=csv,
                file_name=f"journal_filtre_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime='text/csv'
            )

    st.markdown("---")

    # --- AFFICHAGE DU JOURNAL FILTRÉ ---
    if len(df_logs) == 0:
        st.info("Aucun pari ne correspond aux filtres sélectionnés.")
    else:
        # Sélection des colonnes à afficher (sans les colonnes techniques)
        colonnes_affichage = [
            'Date', 'Joueur_parie', 'Adversaire', 'Tournoi',
            'Circuit', 'Surface', 'Round', 'Cote', 'Bookmaker',
            'Proba_IA', 'Value', 'Mise_pct', 'Mode', 'Resultat'
        ]
        # Garde uniquement les colonnes existantes
        colonnes_affichage = [c for c in colonnes_affichage if c in df_logs.columns]

        # Tri par date décroissante (plus récent en premier)
        df_logs_aff = df_logs.sort_values('Date_parsed', ascending=False)[colonnes_affichage]

        st.dataframe(
            df_logs_aff,
            use_container_width=True,
            hide_index=True,
            height=600
        )

        # --- STATISTIQUES SUR LA SÉLECTION ---
        st.markdown("---")
        st.markdown("### 📊 Statistiques sur la sélection")

        df_logs_joues = df_logs[df_logs['Resultat'].isin(['GAGNE', 'PERDU'])]
        if len(df_logs_joues) > 0:
            gagnes = len(df_logs_joues[df_logs_joues['Resultat'] == 'GAGNE'])
            perdus = len(df_logs_joues[df_logs_joues['Resultat'] == 'PERDU'])
            winrate = (gagnes / (gagnes + perdus) * 100) if (gagnes + perdus) > 0 else 0
            gains = df_logs_joues.apply(
                lambda r: r['Mise_num'] * (r['Cote_num'] - 1) if r['Resultat'] == 'GAGNE'
                          else -r['Mise_num'], axis=1
            ).sum()
            mises = df_logs_joues['Mise_num'].sum()
            roi = (gains / mises * 100) if mises > 0 else 0

            col_s1, col_s2, col_s3, col_s4 = st.columns(4)
            col_s1.metric("Paris résolus", len(df_logs_joues))
            col_s2.metric("Winrate", f"{winrate:.1f}%")
            col_s3.metric("ROI", f"{roi:+.2f}%")
            col_s4.metric("En attente", len(df_logs[df_logs['Resultat'] == 'EN_ATTENTE']))
        else:
            st.caption("Aucun pari résolu dans cette sélection.")


# ============================================================
# FOOTER
# ============================================================

st.markdown("---")
st.caption(
    f"🎾 Tennis Betting Dashboard v2.0 | "
    f"Source : {os.path.basename(JOURNAL_PATH)} | "
    f"Total paris : {len(df)} ({len(df[df['Resultat'].isin(['GAGNE', 'PERDU'])])} résolus)"
)