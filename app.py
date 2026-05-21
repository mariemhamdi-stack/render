import streamlit as st
import pandas as pd
import numpy as np
import os
import gc
from datetime import datetime
import pytz
from io import BytesIO, StringIO

px = None
go = None

def _get_plotly():
    global px, go
    if px is None:
        import plotly.express as _px
        import plotly.graph_objects as _go
        px = _px
        go = _go
    return px, go

try:
    from Administration import SonatAnalyticsPro
    from Administration import clean_percentage_value
except ImportError:
    st.error("Erreur: Le fichier Administration.py est introuvable.")
    st.stop()

DELEGUE_MODULE_AVAILABLE = True
DelegueCalculator = None

def _get_delegue_calculator():
    global DelegueCalculator, DELEGUE_MODULE_AVAILABLE
    if DelegueCalculator is None:
        try:
            from delegue import DelegueCalculator as _DC
            DelegueCalculator = _DC
        except ImportError:
            DELEGUE_MODULE_AVAILABLE = False
    return DelegueCalculator

try:
    from authentification import authenticate_user, create_user, get_user_by_id, init_admin_user, get_all_users, delete_user, update_user_laboratoire, update_user_password, update_user_role, activate_user, deactivate_user, init_distance_table
    AUTH_MODULE_AVAILABLE = True
    init_admin_user()
    init_distance_table()
except ImportError as e:
    AUTH_MODULE_AVAILABLE = False

st.set_page_config(page_title="Sentinel Data Analytics | Objectifs N",
                   page_icon="📊",
                   layout="wide",
                   initial_sidebar_state="expanded")

@st.cache_data(show_spinner=False)
def get_app_css():
    return """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    * { font-family: 'Inter', sans-serif; }
    .main { background: #F8FAFC; padding: 0; }
    
    /* Light mode sidebar - style gris clair */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #f5f5f5 0%, #e8e8e8 100%) !important;
    }
    section[data-testid="stSidebar"] > div {
        background: transparent !important;
    }
    section[data-testid="stSidebar"] * {
        color: #1a1a1a !important;
    }
    section[data-testid="stSidebar"] .stCaption {
        color: #64748b !important;
    }
    section[data-testid="stSidebar"] hr {
        border-color: rgba(0, 0, 0, 0.1) !important;
    }
    section[data-testid="stSidebar"] img {
        filter: none;
    }
    
    
    /* Animations globales */
    @keyframes fadeInUp {
        from { opacity: 0; transform: translateY(20px); }
        to { opacity: 1; transform: translateY(0); }
    }
    @keyframes fadeIn {
        from { opacity: 0; }
        to { opacity: 1; }
    }
    @keyframes slideInLeft {
        from { opacity: 0; transform: translateX(-20px); }
        to { opacity: 1; transform: translateX(0); }
    }
    @keyframes pulse {
        0%, 100% { transform: scale(1); }
        50% { transform: scale(1.02); }
    }
    
    /* Animation des éléments principaux */
    .stButton > button {
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
    }
    .stButton > button:hover {
        transform: translateY(-2px) !important;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15) !important;
    }
    .stButton > button:active {
        transform: translateY(0) !important;
    }
    
    /* Animation des cartes et conteneurs */
    .stExpander {
        transition: all 0.3s ease !important;
        animation: fadeInUp 0.4s ease-out !important;
    }
    .stExpander:hover {
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08) !important;
    }
    
    /* Animation des métriques */
    [data-testid="stMetric"] {
        transition: all 0.3s ease !important;
        animation: fadeInUp 0.5s ease-out !important;
    }
    [data-testid="stMetric"]:hover {
        transform: translateY(-3px) !important;
        box-shadow: 0 6px 20px rgba(0, 0, 0, 0.1) !important;
    }
    
    /* Animation des tableaux */
    .stDataFrame, [data-testid="stDataFrame"] {
        animation: fadeIn 0.5s ease-out !important;
    }
    .stDataFrame tbody tr {
        transition: background-color 0.2s ease !important;
    }
    .stDataFrame tbody tr:hover {
        background-color: rgba(59, 130, 246, 0.05) !important;
    }
    
    /* Figer la première ligne (header) et première colonne - Streamlit GlideDataEditor */
    [data-testid="stDataFrame"] [data-testid="glide-data-grid-canvas"] {
        max-height: 500px !important;
    }
    /* Fallback pour anciennes versions et tables HTML */
    [data-testid="stDataFrame"] table thead tr th {
        position: sticky !important;
        top: 0 !important;
        z-index: 10 !important;
        background-color: #f8fafc !important;
    }
    [data-testid="stDataFrame"] table tbody tr td:first-child,
    [data-testid="stDataFrame"] table thead tr th:first-child {
        position: sticky !important;
        left: 0 !important;
        z-index: 5 !important;
        background-color: #f8fafc !important;
    }
    [data-testid="stDataFrame"] table thead tr th:first-child {
        z-index: 15 !important;
    }
    /* Style pour le nouveau dataframe Streamlit */
    .dvn-scroller {
        max-height: 500px !important;
    }
    .dvn-header {
        position: sticky !important;
        top: 0 !important;
        z-index: 10 !important;
        background-color: #f8fafc !important;
    }
    
    /* Animation des inputs */
    .stTextInput > div > div > input,
    .stNumberInput > div > div > input,
    .stSelectbox > div > div {
        transition: all 0.3s ease !important;
    }
    .stTextInput > div > div > input:focus,
    .stNumberInput > div > div > input:focus {
        box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.2) !important;
        border-color: #3B82F6 !important;
    }
    
    /* Animation des multiselect */
    .stMultiSelect > div {
        transition: all 0.3s ease !important;
    }
    .stMultiSelect > div:hover {
        border-color: #3B82F6 !important;
    }
    
    /* Animation des tabs */
    .stTabs [data-baseweb="tab"] {
        transition: all 0.3s ease !important;
    }
    .stTabs [data-baseweb="tab"]:hover {
        background-color: rgba(59, 130, 246, 0.1) !important;
    }
    
    /* Animation du header */
    .header-container {
        animation: fadeInUp 0.6s ease-out !important;
    }
    
    /* Animation des colonnes */
    [data-testid="column"] {
        animation: fadeIn 0.4s ease-out !important;
    }
    
    /* Animation des messages de succès/erreur */
    .stSuccess, .stError, .stWarning, .stInfo {
        animation: slideInLeft 0.4s ease-out !important;
    }
    
    /* Animation des spinners de chargement */
    .stSpinner > div {
        animation: pulse 1.5s infinite !important;
    }
    
    /* Animations spécifiques pour la section délégués */
    .metric-card-animate {
        animation: fadeInUp 0.5s ease-out forwards;
        opacity: 0;
    }
    .metric-card-animate:nth-child(1) { animation-delay: 0.1s; }
    .metric-card-animate:nth-child(2) { animation-delay: 0.2s; }
    .metric-card-animate:nth-child(3) { animation-delay: 0.3s; }
    
    .region-card-animate {
        animation: slideInLeft 0.4s ease-out forwards;
        opacity: 0;
        transition: all 0.3s ease;
    }
    .region-card-animate:hover {
        transform: translateX(5px);
        box-shadow: 0 4px 15px rgba(0,0,0,0.1);
    }
    
    .delegue-header-animate {
        animation: fadeIn 0.6s ease-out forwards;
    }
    
    @keyframes countUp {
        from { opacity: 0; transform: scale(0.5); }
        to { opacity: 1; transform: scale(1); }
    }
    
    .number-animate {
        animation: countUp 0.4s ease-out forwards;
    }
    
    .header-container {
        background: linear-gradient(135deg, #0F172A 0%, #1E293B 100%);
        padding: 2rem 3rem;
        border-radius: 0 0 24px 24px;
        margin: -6rem -6rem 2rem -6rem;
        color: white;
        box-shadow: 0 10px 30px rgba(15, 23, 42, 0.15);
    }
    .header-title {
        font-size: 2.6rem;
        font-weight: 700;
        margin: 0;
        letter-spacing: -0.5px;
    }
    .header-subtitle {
        font-size: 1.1rem;
        opacity: 0.9;
        margin-top: 0.5rem;
        font-weight: 500;
    }
    .metric-card {
        background: transparent;
        border-radius: 0;
        padding: 0.5rem;
        box-shadow: none;
        border: none;
        transition: none;
    }
    .metric-label {
        font-size: 0.9rem;
        color: #000000;
        font-weight: 500;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .metric-value {
        font-size: 1.8rem;
        font-weight: 700;
        color: #000000;
        margin: 0.5rem 0;
    }
    .metric-delta {
        font-size: 0.95rem;
        font-weight: 600;
    }
    .section-header {
        color: #000000;
    }
    .dark-text {
        color: #000000;
    }
    /* Style pour boutons INACTIFS de la sidebar - fond transparent + légère ombre */
    .stSidebar .stButton > button,
    section[data-testid="stSidebar"] .stButton > button {
        background: transparent !important;
        background-color: transparent !important;
        border: none !important;
        color: #0f0f0f !important;
        font-weight: 400 !important;
        text-align: left !important;
        padding: 10px 12px !important;
        border-radius: 10px !important;
        transition: all 0.2s ease !important;
        box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04) !important;
        margin: 4px 0 !important;
        font-size: 14px !important;
    }
    .stSidebar .stButton > button:hover,
    section[data-testid="stSidebar"] .stButton > button:hover {
        background-color: #f2f2f2 !important;
        border: none !important;
        box-shadow: 0 2px 6px rgba(0, 0, 0, 0.1) !important;
        transform: translateX(4px) !important;
    }
    /* Style pour bouton ACTIF - fond gris + texte gras */
    .stSidebar .stButton > button[kind="primary"],
    .stSidebar [data-testid="stBaseButton-primary"],
    section[data-testid="stSidebar"] .stButton > button[kind="primary"],
    section[data-testid="stSidebar"] [data-testid="stBaseButton-primary"] {
        background: #e5e5e5 !important;
        background-color: #e5e5e5 !important;
        font-weight: 700 !important;
        box-shadow: none !important;
    }
    .stSidebar .stButton > button[kind="primary"]:hover,
    .stSidebar [data-testid="stBaseButton-primary"]:hover,
    section[data-testid="stSidebar"] .stButton > button[kind="primary"]:hover,
    section[data-testid="stSidebar"] [data-testid="stBaseButton-primary"]:hover {
        background-color: #e0e0e0 !important;
        box-shadow: none !important;
    }
    .stSidebar .stButton > button:active,
    .stSidebar .stButton > button:focus,
    section[data-testid="stSidebar"] .stButton > button:active,
    section[data-testid="stSidebar"] .stButton > button:focus {
        background-color: #e5e5e5 !important;
        border: none !important;
        box-shadow: none !important;
    }
    .sidebar-logo {
        text-align: center;
        margin-bottom: 1.5rem;
        padding: 1rem 0;
        border-bottom: 1px solid #E2E8F0;
    }
    .sidebar-logo img {
        max-width: 80%;
        height: auto;
        max-height: 60px;
    }
    .stButton > button {
        background: linear-gradient(90deg, #3B82F6, #2563EB);
        color: white;
        font-weight: 600;
        border: none;
        border-radius: 12px;
        padding: 0.75rem 1.5rem;
        box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3);
        transition: all 0.3s ease;
        width: 100%;
    }
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 20px rgba(59, 130, 246, 0.4);
    }
    .section-header {
        font-size: 1.5rem;
        font-weight: 700;
        color: #0F172A;
        margin: 2.5rem 0 1rem 0;
        padding-bottom: 0.75rem;
        border-bottom: 2px solid #3B82F6;
        display: inline-block;
    }
    .stDataFrame {
        border-radius: 12px;
        overflow: hidden;
        box-shadow: 0 4px 12px rgba(0,0,0,0.08);
    }
    .footer {
        text-align: center;
        padding: 2rem;
        color: #94A3B8;
        font-size: 0.9rem;
        margin-top: 4rem;
        border-top: 1px solid #E2E8F0;
    }
    /* YouTube-style profile circle */
    .profile-container {
        position: fixed;
        top: 14px;
        right: 80px;
        z-index: 1000;
    }
    .profile-circle {
        width: 36px;
        height: 36px;
        border-radius: 50%;
        background: linear-gradient(135deg, #3B82F6, #2563EB);
        color: white;
        display: flex;
        align-items: center;
        justify-content: center;
        font-weight: 600;
        font-size: 14px;
        cursor: pointer;
        transition: transform 0.2s ease, box-shadow 0.2s ease;
        border: none;
    }
    .profile-circle:hover {
        transform: scale(1.05);
        box-shadow: 0 2px 8px rgba(59, 130, 246, 0.4);
    }
    .profile-dropdown {
        position: absolute;
        top: 44px;
        right: 0;
        background: white;
        border-radius: 12px;
        box-shadow: 0 4px 24px rgba(0, 0, 0, 0.15);
        min-width: 180px;
        padding: 8px 0;
        display: none;
        z-index: 1001;
    }
    .profile-dropdown.show {
        display: block;
    }
    .profile-dropdown-item {
        padding: 10px 16px;
        cursor: pointer;
        font-size: 14px;
        color: #0f0f0f;
        transition: background-color 0.2s ease;
        display: flex;
        align-items: center;
        gap: 10px;
    }
    .profile-dropdown-item:hover {
        background-color: #f2f2f2;
    }
    .profile-dropdown-item svg {
        width: 20px;
        height: 20px;
    }
    /* Style for profile popover button */
    [data-testid="stPopoverButton"] > button {
        width: 40px !important;
        height: 40px !important;
        border-radius: 50% !important;
        background: linear-gradient(135deg, #3B82F6, #2563EB) !important;
        color: white !important;
        font-weight: 600 !important;
        font-size: 14px !important;
        padding: 0 !important;
        min-width: 40px !important;
        border: none !important;
        box-shadow: 0 2px 8px rgba(59, 130, 246, 0.3) !important;
    }
    [data-testid="stPopoverButton"] > button:hover {
        transform: scale(1.05) !important;
        box-shadow: 0 4px 12px rgba(59, 130, 246, 0.4) !important;
    }
    [data-testid="stPopover"] {
        border-radius: 12px !important;
        box-shadow: 0 4px 24px rgba(0, 0, 0, 0.15) !important;
    }
    .special-governorat {
        background: linear-gradient(90deg, #FFFBEB, #FEF3C7);
        border-left: 4px solid #F59E0B;
        padding: 1rem;
        border-radius: 8px;
        margin: 0.5rem 0;
    }
    .special-secteur {
        background: linear-gradient(90deg, #F0FDF4, #DCFCE7);
        border-left: 4px solid #22C55E;
        padding: 1rem;
        border-radius: 8px;
        margin: 0.5rem 0;
    }
    .input-container {
        background: white;
        border-radius: 12px;
        padding: 1.5rem;
        box-shadow: 0 4px 15px rgba(0,0,0,0.08);
        margin-bottom: 1.5rem;
    }
    .info-box {
        background: #F0F9FF;
        border-left: 4px solid #3B82F6;
        padding: 1rem;
        border-radius: 8px;
        margin: 1rem 0;
    }
    .warning-box {
        background: #FFFBEB;
        border-left: 4px solid #F59E0B;
        padding: 1rem;
        border-radius: 8px;
        margin: 1rem 0;
    }
    .danger-box {
        background: #FEF2F2;
        border-left: 4px solid #EF4444;
        padding: 1rem;
        border-radius: 8px;
        margin: 1rem 0;
    }
    .download-buttons-container {
        display: flex;
        gap: 1rem;
        margin-top: 1rem;
        margin-bottom: 2rem;
    }
    .file-uploader {
        background: white;
        border: 2px dashed #CBD5E1;
        border-radius: 12px;
        padding: 2rem;
        text-align: center;
        margin-bottom: 1rem;
    }
    .file-uploader:hover {
        border-color: #3B82F6;
        background: #F8FAFF;
    }
    .threshold-info {
        background: linear-gradient(90deg, #FEF3C7, #FDE68A);
        border-left: 4px solid #D97706;
        padding: 1rem;
        border-radius: 8px;
        margin: 1rem 0;
    }
    .adjustment-summary {
        background: white;
        border-radius: 12px;
        padding: 1.5rem;
        box-shadow: 0 4px 12px rgba(0,0,0,0.08);
        margin: 1rem 0;
        border-left: 5px solid #8B5CF6;
    }
    .secteurs-retires-box {
        background: linear-gradient(90deg, #FEF2F2, #FEE2E2);
        border-left: 5px solid #EF4444;
        border-radius: 12px;
        padding: 1.5rem;
        box-shadow: 0 4px 15px rgba(0,0,0,0.08);
        margin-bottom: 1.5rem;
    }
    .secteur-retire-item {
        background: white;
        border-radius: 8px;
        padding: 1rem;
        margin-bottom: 0.75rem;
        border-left: 4px solid #EF4444;
        box-shadow: 0 2px 8px rgba(0,0,0,0.05);
        transition: all 0.3s ease;
    }
    .retire-metrics-grid {
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        gap: 1rem;
        margin-top: 0.5rem;
    }
    .retire-metric-label {
        font-size: 0.75rem;
        color: #64748B;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .retire-metric-value {
        font-size: 1.1rem;
        font-weight: 700;
        color: #1E293B;
        margin-top: 0.25rem;
    }
    .percentage-badge {
        background: #EF4444;
        color: white;
        padding: 0.25rem 0.75rem;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: 600;
        display: inline-block;
        margin-left: 0.5rem;
    }
    .increase-badge {
        background: #10B981;
        color: white;
        padding: 0.25rem 0.75rem;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: 600;
        display: inline-block;
        margin-left: 0.5rem;
    }
    .decrease-badge {
        background: #EF4444;
        color: white;
        padding: 0.25rem 0.75rem;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: 600;
        display: inline-block;
        margin-left: 0.5rem;
    }
    .secondary-button {
        background: #64748B;
        color: white;
        font-weight: 600;
        border: none;
        border-radius: 12px;
        padding: 0.75rem 1.5rem;
        box-shadow: 0 4px 12px rgba(100, 116, 139, 0.3);
        transition: all 0.3s ease;
        width: 100%;
    }
    .secondary-button:hover {
        background: #475569;
        transform: translateY(-2px);
        box-shadow: 0 8px 20px rgba(100, 116, 139, 0.4);
    }
    .success-box {
        background: linear-gradient(90deg, #DCFCE7, #BBF7D0);
        border-left: 4px solid #16A34A;
        padding: 1rem;
        border-radius: 8px;
        margin: 1rem 0;
    }
    .secteur-to-remove {
        background: #FEF2F2;
        border: 1px solid #FECACA;
        border-radius: 8px;
        padding: 0.75rem;
        margin: 0.5rem 0;
    }
    .secteur-remaining {
        background: #F0FDF4;
        border: 1px solid #BBF7D0;
        border-radius: 8px;
        padding: 0.75rem;
        margin: 0.5rem 0;
    }
    .delegue-details-box {
        background: white;
        border-radius: 12px;
        padding: 1.5rem;
        margin-bottom: 1rem;
        border-left: 5px solid;
        box-shadow: 0 4px 12px rgba(0,0,0,0.08);
    }
    .delegue-nord {
        border-left-color: #EF4444;
        background: linear-gradient(90deg, #FEF2F2, #FEE2E2);
    }
    .delegue-centre {
        border-left-color: #F59E0B;
        background: linear-gradient(90deg, #FFFBEB, #FEF3C7);
    }
    .delegue-sud {
        border-left-color: #10B981;
        background: linear-gradient(90deg, #F0FDF4, #DCFCE7);
    }
    .secteur-list-item {
        background: #F8FAFC;
        border-radius: 6px;
        padding: 0.5rem 0.75rem;
        margin-bottom: 0.5rem;
        display: flex;
        justify-content: space-between;
        align-items: center;
        border-left: 3px solid;
    }
    .secteur-item-highlight {
        border-left-color: #3B82F6;
    }
    .secteur-item-normal {
        border-left-color: #CBD5E1;
    }
    .secteur-objectif-value {
        font-weight: 600;
        color: #0F172A;
        font-size: 0.9rem;
    }
    .secteur-objectif-header {
        font-size: 0.75rem;
        color: #64748B;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-top: 0.25rem;
    }
    
    .download-button-wrapper {
        margin-bottom: 1rem;
    }
    .download-button-wrapper button {
        width: 100% !important;
    }
    .stDownloadButton > button {
        background: linear-gradient(90deg, #3B82F6, #2563EB) !important;
        color: white !important;
        font-weight: 600 !important;
        border: none !important;
        border-radius: 12px !important;
        padding: 0.75rem 1.5rem !important;
        box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3) !important;
        transition: all 0.3s ease !important;
        width: 100% !important;
    }
    .stDownloadButton > button:hover {
        transform: translateY(-2px) !important;
        box-shadow: 0 8px 20px rgba(59, 130, 246, 0.4) !important;
    }
</style>
"""

st.markdown(get_app_css(), unsafe_allow_html=True)


def to_excel_simple(df, columns_to_keep):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        if columns_to_keep:
            df = df[columns_to_keep]
        df.to_excel(writer, index=False, sheet_name='Données')
    processed_data = output.getvalue()
    return processed_data


def extract_year_from_data(df):
    """
    Extrait les années des données et détermine l'année N.
    Logique: N = année la plus récente dans les données
    Exemple: si données contiennent 2023, 2024, 2025 → N = 2025, N+1 = 2026
    """
    years = []

    if df is None or df.empty:
        return "N"

    # Essayer de trouver une colonne 'Année' ou similaire
    year_cols = [
        col for col in df.columns
        if any(keyword in str(col).lower()
               for keyword in ['année', 'year', 'annee', 'date', 'periode'])
    ]

    if year_cols:
        for col in year_cols:
            try:
                # Extraire les valeurs uniques de la colonne
                unique_values = df[col].astype(str).unique()[:20]

                for val in unique_values:
                    # Chercher des années 4 chiffres (ex: 2022, 2023, 2024)
                    import re
                    matches = re.findall(r'\b(20\d{2})\b', str(val))
                    if matches:
                        years.extend([int(match) for match in matches])

                    # Vérifier les formats comme 'N-1', 'N-2'
                    if any(pattern in str(val).upper()
                           for pattern in ['N-1', 'N_1', 'N1']):
                        # C'est une référence relative, on ne peut pas en extraire une année absolue
                        continue

            except Exception as e:
                continue

    # Si pas d'années trouvées, vérifier dans toutes les colonnes
    if not years:
        for col in df.columns:
            try:
                # Essayer de convertir la colonne en chaîne et chercher des années
                sample_values = df[col].astype(str).head(50)
                for val in sample_values:
                    import re
                    matches = re.findall(r'\b(20\d{2})\b', str(val))
                    if matches:
                        years.extend([int(match) for match in matches])
            except:
                continue

    # Déterminer l'année N
    if years:
        # Trouver l'année la plus récente (max) = année N
        max_year = max(years)

        # Année N = année la plus récente dans les données
        year_n = max_year

        return str(year_n)

    # Si aucune année n'est trouvée, utiliser l'année courante
    current_year = datetime.now().year
    st.warning(
        f"Aucune année détectée dans les données. Utilisation de l'année courante: {current_year}"
    )
    return str(current_year)


def read_uploaded_file(file):
    if file is None:
        return None
    
    # Utiliser le cache session_state pour éviter de relire le fichier
    file_key = f"parsed_file_{file.name}_{file.size}"
    if file_key in st.session_state:
        return st.session_state[file_key]

    try:
        file_name = file.name.lower()

        if file_name.endswith('.csv'):
            content = file.getvalue()
            encodings = ['utf-8', 'latin-1', 'iso-8859-1', 'cp1252']
            df = None

            for encoding in encodings:
                try:
                    df = pd.read_csv(BytesIO(content),
                                     sep=';',
                                     encoding=encoding)
                    if df.shape[1] > 1:
                        break
                    else:
                        df = pd.read_csv(BytesIO(content),
                                         sep=',',
                                         encoding=encoding)
                        if df.shape[1] > 1:
                            break
                        else:
                            df = pd.read_csv(BytesIO(content),
                                             sep='\t',
                                             encoding=encoding)
                        if df.shape[1] > 1:
                            break
                except:
                    continue

            if df is None:
                try:
                    df = pd.read_csv(BytesIO(content),
                                     sep=None,
                                     engine='python',
                                     encoding='utf-8')
                except:
                    st.error(
                        "Impossible de lire le fichier CSV. Vérifiez le format."
                    )
                    return None

            st.session_state[file_key] = df
            return df

        elif file_name.endswith(('.xlsx', '.xls', '.xlsm')):
            try:
                df = pd.read_excel(file,
                                   engine='openpyxl'
                                   if file_name.endswith('.xlsx') else 'xlrd')
                st.session_state[file_key] = df
                return df
            except Exception as e:
                st.error(
                    f"Erreur lors de la lecture du fichier Excel: {str(e)}")
                return None

        else:
            st.error(f"Format de fichier non supporté: {file_name}")
            st.info("Formats acceptés: CSV, XLS, XLSX")
            return None

    except Exception as e:
        st.error(f"Erreur lors de la lecture du fichier {file.name}: {str(e)}")
        return None


def display_remove_secteurs_multi_product(all_products_results):
    """Affiche l'interface de sélection des secteurs non promus pour chaque produit"""
    
    year_n = st.session_state.get('detected_year_n', 'N')
    try:
        year_n1_label = str(int(year_n) + 1)
    except (ValueError, TypeError):
        year_n1_label = "N+1"
    
    all_secteurs = set()
    secteurs_par_produit = {}
    for prod_code, prod_data in all_products_results.items():
        prod_secteur_dist = prod_data.get('secteur_dist', {})
        secteurs_produit = sorted(list(prod_secteur_dist.keys()))
        secteurs_par_produit[prod_code] = secteurs_produit
        all_secteurs.update(secteurs_produit)
    
    all_secteurs_sorted = sorted(list(all_secteurs))
    
    if not all_secteurs_sorted:
        st.warning("Aucun secteur disponible.")
        return False
    
    if all_secteurs_sorted and len(all_products_results) > 1:
        st.markdown("""
        <div style="background: linear-gradient(135deg, #FEF3C7 0%, #FDE68A 100%); padding: 1rem 1.5rem; border-radius: 12px; margin-bottom: 1rem; border: 1px solid #F59E0B;">
            <div style="font-size: 1rem; font-weight: 600; color: #92400E; margin-bottom: 0.25rem;">Retirer des secteurs pour tous les produits</div>
            <div style="font-size: 0.8rem; color: #78350F;">Les secteurs sélectionnés ici seront exclus de tous les produits en même temps</div>
        </div>
        """, unsafe_allow_html=True)
        
        default_global = st.session_state.get('secteurs_retires_global', [])
        default_global = [s for s in default_global if s in all_secteurs_sorted]
        
        secteurs_exclus_global = st.multiselect(
            "Secteurs à exclure pour tous les produits :",
            options=all_secteurs_sorted,
            default=default_global,
            key="multiselect_secteurs_global",
            help="Ces secteurs seront retirés de tous les produits analysés"
        )
        
        st.session_state.secteurs_retires_global = secteurs_exclus_global
        
        if secteurs_exclus_global:
            total_impact = {}
            for prod_code, prod_data in all_products_results.items():
                prod_secteur_dist = prod_data.get('secteur_dist', {})
                obj_exclu = sum(
                    prod_secteur_dist[s].get('objectif_n1_corrige', prod_secteur_dist[s].get('quantite', 0)) or 0
                    for s in secteurs_exclus_global if s in prod_secteur_dist
                )
                total_impact[prod_code] = obj_exclu
            
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Secteurs exclus (global)", len(secteurs_exclus_global))
            with col2:
                total_obj_exclu = sum(total_impact.values())
                st.metric("Objectif total exclu", f"{total_obj_exclu:,.0f}")
        
        st.markdown("---")
    
    st.markdown("""
    <div style="font-size: 0.9rem; font-weight: 600; color: #475569; margin-bottom: 0.5rem;">Exclusions par produit</div>
    """, unsafe_allow_html=True)
    
    global_exclus = st.session_state.get('secteurs_retires_global', [])
    
    for prod_code, prod_data in all_products_results.items():
        prod_name = prod_data.get('name', prod_code)
        prod_secteur_dist = prod_data.get('secteur_dist', {})
        
        secteurs_produit = secteurs_par_produit.get(prod_code, [])
        
        if not secteurs_produit:
            continue
        
        total_objectif = sum(
            sd.get('objectif_n1_corrige', sd.get('quantite', 0)) or 0
            for sd in prod_secteur_dist.values()
        )
        
        with st.expander(f"**{prod_name}** - Objectif {year_n1_label}: {total_objectif:,.0f}", expanded=True):
            existing_per_product = st.session_state.secteurs_retires_par_produit.get(prod_code, [])
            default_secteurs = list(set(
                [s for s in existing_per_product if s in secteurs_produit] +
                [s for s in global_exclus if s in secteurs_produit]
            ))
            
            secteurs_exclus = st.multiselect(
                f"Secteurs à exclure pour {prod_name}:",
                options=secteurs_produit,
                default=default_secteurs,
                key=f"multiselect_secteurs_{prod_code}",
                help="Ces secteurs auront leur objectif mis à zéro"
            )
            
            st.session_state.secteurs_retires_par_produit[prod_code] = secteurs_exclus
            
            if secteurs_exclus:
                objectif_exclus = sum(
                    prod_secteur_dist[s].get('objectif_n1_corrige', prod_secteur_dist[s].get('quantite', 0)) or 0
                    for s in secteurs_exclus if s in prod_secteur_dist
                )
                objectif_apres = total_objectif - objectif_exclus
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Secteurs exclus", len(secteurs_exclus))
                with col2:
                    st.metric(f"Objectif exclu", f"{objectif_exclus:,.0f}")
                with col3:
                    st.metric(f"Objectif après", f"{objectif_apres:,.0f}")
    
    st.markdown("---")
    
    has_exclusions = any(
        len(st.session_state.secteurs_retires_par_produit.get(pc, [])) > 0
        for pc in all_products_results.keys()
    ) or len(st.session_state.get('secteurs_retires_global', [])) > 0
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        if st.button("← Retour à l'analyse", use_container_width=True, key="btn_retour_multi"):
            st.session_state.show_remove_secteurs = False
            st.session_state.current_view = "Analyse par produit"
            st.rerun()
    
    with col2:
        if has_exclusions:
            if st.button("Appliquer les exclusions", type="primary", use_container_width=True, key="btn_appliquer_multi"):
                global_to_apply = st.session_state.get('secteurs_retires_global', [])
                if global_to_apply:
                    for prod_code in all_products_results:
                        existing = st.session_state.secteurs_retires_par_produit.get(prod_code, [])
                        merged = sorted(set(existing + global_to_apply))
                        st.session_state.secteurs_retires_par_produit[prod_code] = merged
                
                st.session_state.show_remove_secteurs = False
                st.session_state.cached_gov_distributions = {}
                st.session_state.cached_secteur_distributions = {}
                st.rerun()
        else:
            st.button("Appliquer les exclusions", disabled=True, use_container_width=True, key="btn_appliquer_multi_disabled")
    
    return True


def display_remove_secteurs_interface(app, product_code):
    """Affiche l'interface pour retirer des secteurs de la distribution"""
    
    # En mode multi-produits, récupérer l'instance correcte depuis all_products_results
    all_products_results = st.session_state.get('all_products_results', {})
    is_multi_product = len(all_products_results) > 1
    
    # Initialiser le dictionnaire des secteurs retirés par produit
    if 'secteurs_retires_par_produit' not in st.session_state:
        st.session_state.secteurs_retires_par_produit = {}
    if 'secteurs_retires_global' not in st.session_state:
        st.session_state.secteurs_retires_global = []
    
    st.markdown(
        '<div class="section-header">Secteurs non promus</div>',
        unsafe_allow_html=True)
    
    if is_multi_product:
        # Mode multi-produit: interface par produit
        return display_remove_secteurs_multi_product(all_products_results)
    
    # Mode mono-produit (existant)
    if not hasattr(app, 'results') or product_code not in app.results:
        st.error(f"Aucun résultat trouvé pour le produit {product_code}")
        return False

    secteur_dist, secteur_total = app.get_secteur_distribution_with_objectives(
        product_code)

    if not secteur_dist:
        st.warning("Aucune distribution secteur disponible pour ce produit.")
        return False

    # Déterminer l'année N+1 pour l'affichage
    year_n = st.session_state.get('detected_year_n', 'N')
    year_n1_label = "N+1"
    try:
        year_n_int = int(year_n)
        year_n1_label = str(year_n_int + 1)
    except (ValueError, TypeError):
        year_n1_label = "N+1"

    # Statistiques de base - utiliser objectif N+1
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Secteurs total", len(secteur_dist))
    with col2:
        # Utiliser objectif_n1_corrige au lieu de quantite (N)
        total_objectif = sum(
            sd.get('objectif_n1_corrige', sd.get('quantite', 0))
            for sd in secteur_dist.values())
        st.metric(f"Objectif total {year_n1_label}", f"{total_objectif:,.0f}")

    st.markdown("---")

    # Section de sélection des secteurs à retirer
    st.markdown("### Sélectionner les secteurs à retirer")

    # Liste des secteurs disponibles - TRIÉE PAR ORDRE ALPHABÉTIQUE
    secteurs_disponibles = sorted(list(secteur_dist.keys()))

    if not secteurs_disponibles:
        st.info("Aucun secteur disponible.")
        return False

    # Afficher les secteurs avec leurs objectifs N+1
    st.markdown(f"#### Objectifs {year_n1_label} par secteur")
    secteur_data_list = []
    for secteur_nom, secteur_data in secteur_dist.items():
        # Utiliser objectif_n1_corrige au lieu de quantite
        objectif_n1 = secteur_data.get('objectif_n1_corrige',
                                       secteur_data.get('quantite', 0))
        part_actuelle = secteur_data.get('part_distribution', 0)
        secteur_data_list.append({
            'Secteur': secteur_nom,
            f'Objectif {year_n1_label}': f"{objectif_n1:,.0f}",
            'Poid %': f"{part_actuelle:.1f}%"
        })

    df_secteurs = pd.DataFrame(secteur_data_list)
    df_secteurs = df_secteurs.sort_values('Secteur')  # Tri alphabétique
    st.dataframe(df_secteurs,
                 use_container_width=True,
                 height=300,
                 hide_index=True)

    # Interface de sélection - TRIÉE PAR ORDRE ALPHABÉTIQUE
    st.markdown("### Choisir les secteurs à retirer")

    # Récupérer les secteurs déjà sélectionnés de session_state
    default_secteurs = []
    if st.session_state.get('secteurs_a_retirer'):
        # Filtrer pour garder uniquement les secteurs qui existent encore
        default_secteurs = [
            s for s in st.session_state.secteurs_a_retirer
            if s in secteurs_disponibles
        ]

    secteurs_a_retirer = st.multiselect(
        "Sélectionnez les secteurs à retirer de la distribution:",
        options=secteurs_disponibles,
        default=default_secteurs,
        key="multiselect_secteurs_retirer",
        help=
        "Ces secteurs seront exclus de la distribution et leurs objectifs seront redistribués aux secteurs restants"
    )

    # Sauvegarder automatiquement la sélection dans session_state
    st.session_state.secteurs_selection_temp = secteurs_a_retirer

    # Calculer l'impact
    if secteurs_a_retirer:
        st.markdown("### Impact du retrait")

        # Calculer les totaux - utiliser objectif N+1
        objectif_total_initial = total_objectif
        objectif_secteurs_retires = 0

        for secteur_nom in secteurs_a_retirer:
            if secteur_nom in secteur_dist:
                # Utiliser objectif_n1_corrige au lieu de quantite
                objectif_secteurs_retires += secteur_dist[secteur_nom].get(
                    'objectif_n1_corrige',
                    secteur_dist[secteur_nom].get('quantite', 0))

        # Nombre de secteurs restants
        secteurs_restants = len(secteurs_disponibles) - len(secteurs_a_retirer)

        # Calculer l'objectif après retrait (maintenant diminue)
        if secteurs_restants > 0:
            objectif_total_apres = objectif_total_initial - objectif_secteurs_retires

            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Secteurs à retirer", len(secteurs_a_retirer))
            with col2:
                st.metric(f"Objectif {year_n1_label} à retirer",
                          f"{objectif_secteurs_retires:,.0f}")
            with col3:
                st.metric(f"Objectif {year_n1_label} après retrait",
                          f"{objectif_total_apres:,.0f}")

            # Afficher les secteurs affectés
            st.markdown("#### Secteurs à retirer")
            for secteur_nom in secteurs_a_retirer:
                if secteur_nom in secteur_dist:
                    # Utiliser objectif_n1_corrige au lieu de quantite
                    objectif_secteur = secteur_dist[secteur_nom].get(
                        'objectif_n1_corrige',
                        secteur_dist[secteur_nom].get('quantite', 0))
                    st.markdown(f"""
                    <div class="secteur-to-remove">
                        <strong>{secteur_nom}</strong>
                        <div style="color: #EF4444; font-weight: 600;">Objectif {year_n1_label}: {objectif_secteur:,.0f} → <strong>0</strong></div>
                    </div>
                    """,
                                unsafe_allow_html=True)

    # Boutons d'action
    st.markdown("---")
    col1, col3 = st.columns([1, 1])

    with col1:
        if st.button("← Retour à l'analyse", use_container_width=True):
            st.session_state.show_remove_secteurs = False
            st.session_state.current_view = "Analyse par produit"
            st.rerun()

    with col3:
        if secteurs_a_retirer:
            if st.button("Appliquer le retrait",
                         type="primary",
                         use_container_width=True):
                # Stocker la configuration
                st.session_state.secteurs_a_retirer = secteurs_a_retirer

                # Retour automatique à l'interface principale
                st.session_state.show_remove_secteurs = False

                # Relancer l'analyse avec les secteurs retirés
                with st.spinner(
                        "Recalcul de l'analyse avec les secteurs retirés..."):
                    try:
                        app = st.session_state.sonat_app

                        # Recalculer avec les secteurs retirés
                        objectives = app.calculate_and_store_product_objectives(
                            product_code,
                            secteurs_a_retirer=secteurs_a_retirer)

                        if objectives is None:
                            st.error(
                                "Erreur lors du recalcul avec les secteurs retirés."
                            )
                        else:
                            st.success("Analyse recalculée avec succès !")
                            st.session_state.analysis_done = True
                            st.session_state.cached_gov_distributions = {}
                            st.session_state.cached_secteur_distributions = {}
                            st.rerun()

                    except Exception as e:
                        st.error(f"Erreur lors du recalcul: {str(e)}")
        else:
            st.button("Appliquer le retrait",
                      disabled=True,
                      use_container_width=True)

    return True


@st.fragment
def display_pro(app, product_code):
    # En mode multi-produits, récupérer l'instance correcte depuis all_products_results
    all_products_results = st.session_state.get('all_products_results', {})
    
    if not hasattr(app, 'results') or product_code not in app.results:
        st.error(f"Aucun résultat trouvé pour le produit {product_code}")
        st.info("Veuillez d'abord exécuter l'analyse.")
        return

    # Vérifier si on doit afficher l'interface de retrait de secteurs
    if st.session_state.get('show_remove_secteurs', False):
        display_remove_secteurs_interface(app, product_code)
        return

    result = app.results[product_code]
    obj = result.get('objectives', {})

    if not obj or '_TOTAUX_' not in obj:
        st.error("Données d'objectifs non disponibles")
        return

    # Afficher le KPI somme des objectifs N+1 uniquement si plusieurs produits analysés
    if len(all_products_results) > 1:
        year_n = st.session_state.get('detected_year_n', 'N')
        try:
            year_n_int = int(year_n)
            year_n1_display = str(year_n_int + 1)
        except (ValueError, TypeError):
            year_n1_display = "N+1"
        
        # Récupérer les secteurs exclus par produit
        secteurs_retires_par_produit = st.session_state.get('secteurs_retires_par_produit', {})
        
        # Calculer la somme totale des objectifs N+1 corrigés de tous les produits (après exclusions)
        somme_objectifs_n1_tous_produits = 0
        for prod_code, prod_data in all_products_results.items():
            prod_secteur_dist = prod_data.get('secteur_dist', {})
            secteurs_exclus = secteurs_retires_par_produit.get(prod_code, [])
            somme_objectifs_n1_tous_produits += sum(
                sd.get('objectif_n1_corrige', sd.get('quantite', 0)) or 0
                for s, sd in prod_secteur_dist.items()
                if s not in secteurs_exclus
            )
        
        # Stocker dans session_state
        st.session_state.somme_objectifs_n1_tous_produits = somme_objectifs_n1_tous_produits
        
        # Afficher le KPI au milieu avec fond gris et texte noir
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.markdown(f'''
            <div style="background: #f5f5f5; 
                        padding: 1.5rem; border-radius: 12px; text-align: center; 
                        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15), 0 2px 8px rgba(0, 0, 0, 0.1);">
                <div style="color: #333333; font-size: 0.9rem; margin-bottom: 0.5rem;">
                    Somme Objectifs {year_n1_display} (Tous Produits)
                </div>
                <div style="color: #000000; font-size: 2rem; font-weight: bold;">
                    {somme_objectifs_n1_tous_produits:,.0f}
                </div>
            </div>
            ''', unsafe_allow_html=True)
        
        st.markdown("<div style='height: 1rem;'></div>", unsafe_allow_html=True)

    cache_key = f"{product_code}_gov"
    if cache_key in st.session_state.cached_gov_distributions:
        gov_dist, gov_total = st.session_state.cached_gov_distributions[cache_key]
    else:
        gov_dist, gov_total = app.get_governorat_distribution_with_objectives(product_code)
        st.session_state.cached_gov_distributions[cache_key] = (gov_dist, gov_total)
    
    cache_key_sect = f"{product_code}_sect"
    if cache_key_sect in st.session_state.cached_secteur_distributions:
        secteur_dist, secteur_total = st.session_state.cached_secteur_distributions[cache_key_sect]
    else:
        secteur_dist, secteur_total = app.get_secteur_distribution_with_objectives(product_code)
        st.session_state.cached_secteur_distributions[cache_key_sect] = (secteur_dist, secteur_total)

    total_objectif = gov_total

    totals = obj.get('_TOTAUX_', {})

    product_name = product_code
    if app.data_n2 is not None and 'Produit' in app.data_n2.columns and 'Code PCT' in app.data_n2.columns:
        produit_info = app.data_n2[app.data_n2['Code PCT'].astype(str).str.strip() == str(product_code).strip()]
        if not produit_info.empty and 'Produit' in produit_info.columns:
            _nom = str(produit_info['Produit'].iloc[0]).strip()
            if _nom:
                product_name = _nom
    if product_name == product_code and st.session_state.get('selected_product'):
        _sp = st.session_state.selected_product
        _nom_sp = (_sp.get('Désignation') or _sp.get('Produit') or '').strip()
        if _nom_sp:
            product_name = _nom_sp

    # Afficher le nom du produit seulement si un seul produit est analysé
    all_products_results = st.session_state.get('all_products_results', {})
    if len(all_products_results) <= 1:
        st.markdown(f"### Produit : **{product_name}**")

    # Afficher les secteurs retirés si applicable
    secteurs_retires = result.get('secteurs_retires', [])
    if secteurs_retires:
        st.markdown(f"""
        <div class="danger-box">
            <strong>Secteurs retirés : {len(secteurs_retires)}</strong><br>
        </div>
        """,
                    unsafe_allow_html=True)

        with st.expander("Voir les secteurs retirés"):
            for secteur in secteurs_retires:
                st.write(f"- {secteur}")

    product_data = None
    for p, d in obj.items():
        if p == product_code:
            product_data = d
            break

    if product_data is None and len(obj) > 1:
        for p, d in obj.items():
            if p != '_TOTAUX_':
                product_data = d
                st.warning(
                    f"Données non trouvées pour {product_code}, affichage de {p}"
                )
                break

    if product_data is None:
        st.error("Aucune donnée disponible pour ce produit")
        return

    ventes_n1_produit = product_data.get('qte_n1', 0) or 0
    # Utiliser la quantité N réelle (pas l'objectif calculé)
    ventes_n_produit = product_data.get('qte_n_reelle',
                                        product_data.get('qte_n', 0)) or 0
    ventes_n2_produit = product_data.get('qte_n2', 0) or 0
    pm_produit = product_data.get('PM', 0) or 0

    # Evolution N+1 = (Quantité N - Quantité N-1) / Quantité N-1
    if ventes_n1_produit > 0:
        croissance_produit_n1 = (
            (ventes_n_produit - ventes_n1_produit) / ventes_n1_produit) * 100
    else:
        croissance_produit_n1 = 0

    # Evolution Marché N+1 = (Volume Marché N - Volume Marché N-1) / Volume Marché N-1
    summary_data = app.get_product_objectives_summary(product_code)
    volume_marche_n = summary_data.get('volume_marché_n',
                                       0) if summary_data else 0
    volume_marche_n1 = summary_data.get('volume_marché_n1',
                                        0) if summary_data else 0
    if volume_marche_n1 > 0:
        croissance_marche_n1 = (
            (volume_marche_n - volume_marche_n1) / volume_marche_n1) * 100
    else:
        croissance_marche_n1 = 0

    # Calculer la somme des objectifs N+1 corrigés de tous les secteurs
    somme_objectifs_n1 = sum(
        sd.get('objectif_n1_corrige', sd.get('quantite', 0))
        for sd in secteur_dist.values())

    # Utiliser la somme des objectifs N+1 pour l'affichage
    objectif_n1_a_afficher = somme_objectifs_n1

    # Croissance = (Objectif N+1 - Quantité N) / Quantité N
    croissance_produit = 0
    if ventes_n_produit > 0:
        croissance_produit = ((objectif_n1_a_afficher - ventes_n_produit) /
                              ventes_n_produit) * 100

    summary = app.get_product_objectives_summary(product_code)
    if summary:
        pm_moyenne = summary.get('pm_moyenne', 0) or 0
    else:
        pm_moyenne = pm_produit if pm_produit <= 1 else pm_produit / 100

    pm_moyenne_pourcentage = pm_moyenne if pm_moyenne <= 1 else pm_moyenne / 100

    ventes_n_produit = float(
        ventes_n_produit) if ventes_n_produit is not None else 0.0
    pm_moyenne_pourcentage = float(
        pm_moyenne_pourcentage) if pm_moyenne_pourcentage is not None else 0.0
    croissance_produit_n1 = float(
        croissance_produit_n1) if croissance_produit_n1 is not None else 0.0
    croissance_marche_n1 = float(
        croissance_marche_n1) if croissance_marche_n1 is not None else 0.0

    # Stocker la Quantité N pour la recommendation
    st.session_state.quantite_n_produit = ventes_n_produit

    year_n = st.session_state.get('detected_year_n', 'N')
    try:
        year_n_int = int(year_n)
        year_n_label = str(year_n_int)
        year_n1_label = str(year_n_int + 1)
    except (ValueError, TypeError):
        year_n_label = "N"
        year_n1_label = "N+1"

    # Afficher les métriques seulement si un seul produit est analysé
    all_products_results = st.session_state.get('all_products_results', {})
    if len(all_products_results) <= 1:
        cols = st.columns(5)
        
        metrics = [(f"Quantité {year_n_label}", f"{ventes_n_produit:,.0f}", None),
                   (f"Objectif {year_n1_label}", f"{objectif_n1_a_afficher:,.0f}",
                    f"+{croissance_produit:.1f}%"
                    if croissance_produit > 0 else f"{croissance_produit:.1f}%"),
                   (f"Part de marché {year_n_label}", f"{pm_moyenne_pourcentage*100:.1f}%", None),
                   (f"Evolution Produit {year_n_label}",
                    f"{croissance_produit_n1:.1f}%", None),
                   (f"Evolution Marché {year_n_label}",
                    f"{croissance_marche_n1:.1f}%", None)]

        for col, (label, value, delta) in zip(cols, metrics):
            with col:
                st.markdown(f'<div class="metric-card">', unsafe_allow_html=True)
                if label:
                    st.markdown(f'<div class="metric-label">{label}</div>',
                                unsafe_allow_html=True)
                if value:
                    st.markdown(f'<div class="metric-value">{value}</div>',
                                unsafe_allow_html=True)
                if delta:
                    color = "#10B981" if croissance_produit > 0 else "#EF4444" if croissance_produit < 0 else "#64748B"
                    st.markdown(
                        f'<div class="metric-delta" style="color:{color}">{delta}</div>',
                        unsafe_allow_html=True)
                st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)

    special_gov_adjustments = []
    special_secteur_adjustments = []

    for p, d in obj.items():
        if p != '_TOTAUX_':
            if 'governorat_adjustments' in d:
                special_gov_adjustments.extend(d['governorat_adjustments'])
            if 'secteur_adjustments' in d:
                special_secteur_adjustments.extend(d['secteur_adjustments'])

    year_n = st.session_state.get('detected_year_n', 'N')
    try:
        year_n_int = int(year_n)
        year_n_label = str(year_n_int)
        year_n1_label = str(year_n_int + 1)
    except (ValueError, TypeError):
        year_n_label = "N"
        year_n1_label = "N+1"

    ecart_adjustments = []
    if special_secteur_adjustments:
        ecart_adjustments = [
            adj for adj in special_secteur_adjustments
            if adj.get('type') == 'Ajustement écart'
        ]

    user_role = st.session_state.get('user', {}).get('role', 'user')
    is_admin_user = user_role == 'admin'

    # Vérifier si on est en mode 2 années (sans threshold)
    is_two_year_mode = getattr(app, 'is_two_year_mode', False)

    if is_admin_user:
        # Afficher la section threshold UNIQUEMENT en mode 3 années
        if not is_two_year_mode:
            st.markdown(
                f'<div class="section-header">Correction des Objectifs par Secteur ({year_n_label} et {year_n1_label})</div>',
                unsafe_allow_html=True)

            # Récupérer tous les produits analysés pour afficher leurs thresholds
            all_products_results = st.session_state.get('all_products_results', {})
            
            # Vérifier si au moins un produit a des ecart_adjustments
            has_any_ecart_adjustments = ecart_adjustments or any(
                prod_data.get('ecart_adjustments', []) for prod_data in all_products_results.values()
            )
            
            if has_any_ecart_adjustments:
                
                # Construire la liste des thresholds par produit
                threshold_lines = []
                for prod_code, prod_data in all_products_results.items():
                    prod_name = prod_data.get('name', prod_code)
                    prod_ecart_adj = prod_data.get('ecart_adjustments', [])
                    if prod_ecart_adj:
                        prod_threshold = prod_ecart_adj[0].get('threshold', 0) * 100
                        threshold_lines.append(f"<span style='color: #000000;'>• <strong>{prod_name}:</strong> {prod_threshold:.1f}%</span>")
                
                # Si pas de multi-produit, utiliser le threshold actuel
                if not threshold_lines:
                    threshold = ecart_adjustments[0].get('threshold', 0)
                    threshold_pct = threshold * 100
                    threshold_lines.append(f"<span style='color: #000000;'>• <strong>Produit actuel:</strong> {threshold_pct:.1f}%</span>")
                
                thresholds_html = "<br>".join(threshold_lines)

                st.markdown(f"""
                <div class="threshold-info" style="background-color: #FFFFFF; color: #000000; padding: 1rem; border-radius: 8px; border: 1px solid #E2E8F0;">
                    <strong style="color: #000000;">Système de Correction par Threshold</strong><br>
                    <strong style="color: #000000;">Thresholds calculés (2 × médiane des écarts absolus):</strong><br>
                    {thresholds_html}
                </div>
                """,
                            unsafe_allow_html=True)

                # Construire le tableau avec colonnes multi-produits
                # D'abord, collecter tous les secteurs de TOUS les produits
                all_secteurs = set()
                for prod_code, prod_data in all_products_results.items():
                    prod_ecart_adj = prod_data.get('ecart_adjustments', [])
                    for adj in prod_ecart_adj:
                        all_secteurs.add(adj.get('secteur', ''))
                
                # Initialiser secteurs_data avec tous les secteurs
                secteurs_data = {secteur: {'Secteur': secteur} for secteur in all_secteurs}
                
                # Ajouter les colonnes pour chaque produit
                for prod_code, prod_data in all_products_results.items():
                    prod_name = prod_data.get('name', prod_code)
                    # Extraire le nom court (sans le code)
                    if '(' in prod_name:
                        short_name = prod_name.split('(')[0].strip()[:15]
                    else:
                        short_name = prod_name[:15]
                    
                    prod_ecart_adj = prod_data.get('ecart_adjustments', [])
                    prod_secteur_data = {adj.get('secteur', ''): adj for adj in prod_ecart_adj}
                    
                    for secteur in secteurs_data.keys():
                        if secteur in prod_secteur_data:
                            adj = prod_secteur_data[secteur]
                            # Quantité réelle année N
                            secteurs_data[secteur][f'{short_name} Réel {year_n_label}'] = adj.get('valeur_realisee', 0)
                            # Année N (initiale et corrigée)
                            secteurs_data[secteur][f'{short_name} {year_n_label} Init.'] = adj.get('ancienne_valeur', 0)
                            secteurs_data[secteur][f'{short_name} {year_n_label} Corr.'] = adj.get('nouvelle_valeur', 0)
                            # Année N+1 (initiale et corrigée)
                            secteurs_data[secteur][f'{short_name} {year_n1_label} Init.'] = adj.get('objectif_n1_initial', adj.get('ancienne_valeur', 0))
                            secteurs_data[secteur][f'{short_name} {year_n1_label} Corr.'] = adj.get('objectif_n1_corrige', adj.get('objectif_n1', 0))
                            secteurs_data[secteur][f'{short_name} Écart'] = f"{adj.get('nouvel_ecart', 0) * 100:+.1f}%"
                            secteurs_data[secteur][f'{short_name} Type'] = adj.get('adjustment_type', '')
                        else:
                            secteurs_data[secteur][f'{short_name} Réel {year_n_label}'] = 0
                            secteurs_data[secteur][f'{short_name} {year_n_label} Init.'] = 0
                            secteurs_data[secteur][f'{short_name} {year_n_label} Corr.'] = 0
                            secteurs_data[secteur][f'{short_name} {year_n1_label} Init.'] = 0
                            secteurs_data[secteur][f'{short_name} {year_n1_label} Corr.'] = 0
                            secteurs_data[secteur][f'{short_name} Écart'] = "N/A"
                            secteurs_data[secteur][f'{short_name} Type'] = "N/A"
                
                # Formater les données pour le dataframe
                ecart_data = []
                for secteur, data in secteurs_data.items():
                    row = {'Secteur': secteur}
                    for key, val in data.items():
                        if key == 'Secteur':
                            continue
                        if isinstance(val, (int, float)) and key not in ['Écart Init.', 'Écart Corr.']:
                            row[key] = f"{val:,.0f}"
                        elif key in ['Écart Init.', 'Écart Corr.']:
                            row[key] = f"{val:+.1f}%"
                        else:
                            row[key] = val
                    ecart_data.append(row)

                if ecart_data:
                    df_ecart = pd.DataFrame(ecart_data).sort_values('Secteur')
                    st.dataframe(df_ecart,
                                 use_container_width=True,
                                 hide_index=True)

    if special_gov_adjustments:
        st.markdown(
            '<div class="section-header">Ajustements Automatiques - Gouvernorats Spéciaux</div>',
            unsafe_allow_html=True)

        adjustment_data = []
        for adj in special_gov_adjustments:
            row_data = {
                'Gouvernorat': adj.get('gouvernorat', ''),
                'Ancienne Valeur': f"{adj.get('ancienne_valeur', 0):,.0f}",
                'Nouvelle Valeur': f"{adj.get('nouvelle_valeur', 0):,.0f}",
                'Différence': f"{adj.get('difference', 0):,.0f}",
                'Code PCT Concurrent': adj.get('competing_product_code',
                                               'N/A'),
                'PM Concurrent':
                f"{adj.get('competing_pm_pourcentage', 0):.1f}%",
                'Volume Total Marché':
                f"{adj.get('total_market_volume', 0):,.0f}"
            }

            if adj.get('ratio_quota') is not None and adj.get(
                    'ratio_quota', 0) > 0:
                row_data[
                    'Ratio Quota'] = f"{adj.get('ratio_quota_pourcentage', 0):.1f}%"
                row_data[
                    'Valeur Base'] = f"{adj.get('base_target', adj.get('ancienne_valeur', 0)):,.0f}"
            else:
                row_data['Ratio Quota'] = "N/A"
                row_data['Valeur Base'] = "N/A"

            adjustment_data.append(row_data)

        if adjustment_data:
            df_adj = pd.DataFrame(adjustment_data).sort_values('Gouvernorat')
            st.dataframe(df_adj, use_container_width=True, hide_index=True)

    if special_secteur_adjustments:
        special_only = [
            adj for adj in special_secteur_adjustments
            if adj.get('type') == 'Automatique'
        ]

        if special_only:
            st.markdown(
                '<div class="section-header">Ajustements Automatiques - Secteurs Spéciaux</div>',
                unsafe_allow_html=True)

            adjustment_data = []
            for adj in special_only:
                row_data = {
                    'Secteur': adj.get('secteur', ''),
                    'Ancienne Valeur': f"{adj.get('ancienne_valeur', 0):,.0f}",
                    'Nouvelle Valeur': f"{adj.get('nouvelle_valeur', 0):,.0f}",
                    'Différence': f"{adj.get('difference', 0):,.0f}",
                    'Type': adj.get('type', 'Automatique')
                }

                if adj.get('type') == 'Automatique':
                    row_data['Code PCT Concurrent'] = adj.get(
                        'competing_product_code', 'N/A')
                    row_data[
                        'PM Concurrent'] = f"{adj.get('competing_pm_pourcentage', 0):.1f}%"
                    row_data[
                        'Volume Total Marché'] = f"{adj.get('total_market_volume', 0):,.0f}"

                    if adj.get('ratio_quota') is not None and adj.get(
                            'ratio_quota', 0) > 0:
                        row_data[
                            'Ratio Quota'] = f"{adj.get('ratio_quota_pourcentage', 0):.1f}%"
                        row_data[
                            'Valeur Base'] = f"{adj.get('base_target', adj.get('ancienne_valeur', 0)):,.0f}"
                    else:
                        row_data['Ratio Quota'] = "N/A"
                        row_data['Valeur Base'] = "N/A"

                adjustment_data.append(row_data)

            if adjustment_data:
                df_adj_secteur = pd.DataFrame(adjustment_data).sort_values(
                    'Secteur')
                st.dataframe(df_adj_secteur,
                             use_container_width=True,
                             hide_index=True)

    st.markdown('<div class="section-header">Détail par Produit(s) Analysé(s)</div>',
                unsafe_allow_html=True)

    # Récupérer tous les produits analysés
    all_products_results = st.session_state.get('all_products_results', {})
    
    year_n = st.session_state.get('detected_year_n', 'N')
    try:
        year_n_int = int(year_n)
        year_n1_col = str(year_n_int - 1)
        year_n_col = str(year_n_int)
        year_n_plus_1_col = str(year_n_int + 1)
    except (ValueError, TypeError):
        year_n1_col = "N-1"
        year_n_col = "N"
        year_n_plus_1_col = "N+1"

    rows = []
    
    # Récupérer les secteurs exclus par produit
    secteurs_retires_par_produit = st.session_state.get('secteurs_retires_par_produit', {})
    
    # Afficher une ligne pour chaque produit analysé
    for prod_code, prod_data in all_products_results.items():
        prod_name = prod_data.get('name', prod_code)
        prod_objectives = prod_data.get('objectives', {})
        prod_secteur_dist = prod_data.get('secteur_dist', {})
        secteurs_exclus = secteurs_retires_par_produit.get(prod_code, [])
        
        # Calculer le total objectif corrigé pour ce produit (après exclusions)
        total_objectif_corrige = sum(
            sd.get('objectif_n1_corrige', sd.get('quantite', 0)) or 0
            for s, sd in prod_secteur_dist.items()
            if s not in secteurs_exclus
        )
        
        # Récupérer les données du produit principal
        if prod_code in prod_objectives:
            d = prod_objectives[prod_code]
        elif '_TOTAUX_' in prod_objectives:
            d = prod_objectives['_TOTAUX_']
        else:
            # Chercher le premier produit non-TOTAUX
            d = None
            for p, obj_data in prod_objectives.items():
                if p != '_TOTAUX_':
                    d = obj_data
                    break
        
        if d is None:
            continue
            
        # Quantités réelles
        qte_n1 = d.get('qte_n1', 0) or 0
        qte_n_reelle = d.get('qte_n_reelle', 0) or 0
        qte_n_plus_1 = total_objectif_corrige if total_objectif_corrige > 0 else (d.get('qte_n_plus_1', 0) or 0)

        # Delta = Objectif N+1 corrigé - Quantité réelle N
        delta_qte = qte_n_plus_1 - qte_n_reelle
        delta_pct = ((qte_n_plus_1 - qte_n_reelle) / qte_n_reelle * 100) if qte_n_reelle > 0 else 0

        # Métriques
        pm = d.get('PM', 0) or 0
        pm_display = pm if pm <= 1 else pm / 100

        # Croissance produit N-1→N
        c_produit_n1_to_n = ((qte_n_reelle - qte_n1) / qte_n1 * 100) if qte_n1 > 0 else 0

        # Croissance marché
        c_marche_n1_to_n = prod_data.get('market_growth', 0) or 0
        if c_marche_n1_to_n == 0:
            c_marche_n1_to_n = d.get('C_Marché', 0) or 0

        row = {
            'Code PCT': prod_code,
            'Produit': prod_name,
            f"Qté {year_n1_col}": f"{qte_n1:,.0f}",
            f"Qté {year_n_col}": f"{qte_n_reelle:,.0f}",
            f"Objectif {year_n_plus_1_col}": f"{qte_n_plus_1:,.0f}",
            'Δ': f"{delta_qte:,.0f}",
            'Δ%': f"{delta_pct:.1f}%",
            f"PM {year_n_col}": f"{pm_display*100:.2f}%",
            f"Evol. Produit {year_n_col}": f"{c_produit_n1_to_n:.1f}%",
            f"Evol. Marché {year_n_col}": f"{c_marche_n1_to_n:.1f}%"
        }
        rows.append(row)

    if rows:
        df_rows = pd.DataFrame(rows)
        if 'Produit' in df_rows.columns:
            df_rows = df_rows.sort_values('Produit')
        col_config = {}
        for col in df_rows.columns:
            col_config[col] = st.column_config.TextColumn(label=col)
        st.dataframe(df_rows, use_container_width=True, hide_index=True, column_config=col_config)
    else:
        st.info("Aucun détail de produit disponible")

    st.markdown(
        '<div class="section-header">Répartition par Gouvernorats</div>',
        unsafe_allow_html=True)

    if gov_dist:
        # Vérifier si on a plusieurs produits
        all_products_results = st.session_state.get('all_products_results', {})
        
        gov_df = None  # Initialiser pour éviter UnboundLocalError
        
        if len(all_products_results) > 1:
            # Mode multi-produits : afficher tous les produits en colonnes avec poids
            gov_data = {}
            product_totals = {}  # Pour calculer les pourcentages
            
            # Récupérer les secteurs exclus par produit
            secteurs_retires_par_produit = st.session_state.get('secteurs_retires_par_produit', {})
            
            # Récupérer l'année N+1 pour les titres de colonnes
            year_n = st.session_state.get('detected_year_n', 'N')
            try:
                year_n1_display = str(int(year_n) + 1)
            except (ValueError, TypeError):
                year_n1_display = "N+1"
            
            # Première passe : collecter les données par gouvernorat en tenant compte des exclusions
            for prod_code, prod_data in all_products_results.items():
                prod_name = prod_data.get('name', prod_code)
                prod_secteur_dist = prod_data.get('secteur_dist', {})
                secteurs_exclus = secteurs_retires_par_produit.get(prod_code, [])
                
                gov_objectifs = {}
                gov_reels_n = {}
                
                prod_ecart_adj = prod_data.get('ecart_adjustments', [])
                reels_par_secteur = {adj.get('secteur', ''): adj.get('valeur_realisee', 0) or 0 for adj in prod_ecart_adj}
                
                for secteur, sd in prod_secteur_dist.items():
                    if secteur in secteurs_exclus:
                        continue
                    gov = sd.get('gouvernorat', '')
                    if not gov:
                        continue
                    if gov not in gov_objectifs:
                        gov_objectifs[gov] = 0
                        gov_reels_n[gov] = 0
                    gov_objectifs[gov] += sd.get('objectif_n1_corrige', sd.get('quantite', 0)) or 0
                    gov_reels_n[gov] += reels_par_secteur.get(secteur, 0)
                
                product_totals[prod_name] = sum(gov_objectifs.values())
                
                col_objectif = f"Objectif {year_n1_display} de produit\n{prod_name}"
                col_evolution = f"Évolution de produit\n{prod_name}"
                
                for g, objectif in gov_objectifs.items():
                    if g not in gov_data:
                        gov_data[g] = {'Gouvernorat': g}
                    gov_data[g][col_objectif] = objectif
                    reel_n = gov_reels_n.get(g, 0)
                    if reel_n > 0:
                        gov_data[g][col_evolution] = ((objectif - reel_n) / reel_n) * 100
                    else:
                        gov_data[g][col_evolution] = 0
            
            if gov_data:
                gov_df = pd.DataFrame(list(gov_data.values()))
                gov_df = gov_df.sort_values('Gouvernorat')
                gov_df = gov_df.fillna(0)
                
                # Ajouter les colonnes de poids pour chaque produit
                for prod_code, prod_data in all_products_results.items():
                    prod_name = prod_data.get('name', prod_code)
                    col_objectif = f"Objectif {year_n1_display} de produit\n{prod_name}"
                    col_poids = f"Poids de produit\n{prod_name}"
                    total = product_totals.get(prod_name, 0)
                    if total > 0 and col_objectif in gov_df.columns:
                        gov_df[col_poids] = gov_df[col_objectif].apply(
                            lambda x: (float(x) / total * 100) if pd.notna(x) else 0
                        )
                
                ordered_cols = ['Gouvernorat']
                for prod_code, prod_data in all_products_results.items():
                    prod_name = prod_data.get('name', prod_code)
                    col_objectif = f"Objectif {year_n1_display} de produit\n{prod_name}"
                    col_poids = f"Poids de produit\n{prod_name}"
                    col_evolution = f"Évolution de produit\n{prod_name}"
                    if col_objectif in gov_df.columns:
                        ordered_cols.append(col_objectif)
                    if col_poids in gov_df.columns:
                        ordered_cols.append(col_poids)
                    if col_evolution in gov_df.columns:
                        ordered_cols.append(col_evolution)
                gov_df = gov_df[ordered_cols]
                
                gov_df_display = gov_df.copy()
                for col in gov_df_display.columns:
                    if col == 'Gouvernorat':
                        continue
                    elif 'Poids de produit' in col:
                        gov_df_display[col] = gov_df_display[col].apply(lambda x: f"{float(x):.1f}%" if pd.notna(x) else "0%")
                    elif 'Évolution de produit' in col:
                        gov_df_display[col] = gov_df_display[col].apply(lambda x: f"{float(x):.1f}%" if pd.notna(x) else "0%")
                    else:
                        gov_df_display[col] = gov_df_display[col].apply(lambda x: f"{float(x):,.0f}" if pd.notna(x) else "0")
                
                compact_col_config = {}
                for col in gov_df_display.columns:
                    if col == 'Gouvernorat':
                        compact_col_config[col] = st.column_config.TextColumn(col, width="small")
                    elif 'Poids' in col or 'Poid' in col:
                        compact_col_config[col] = st.column_config.TextColumn(col, width="small")
                    else:
                        compact_col_config[col] = st.column_config.TextColumn(col, width="small")
                st.dataframe(gov_df_display, use_container_width=True, hide_index=True, column_config=compact_col_config)
            else:
                st.warning("Aucune distribution disponible pour les produits sélectionnés.")
        else:
            gov_n1_totals = {g: 0 for g in gov_dist}
            gov_reels_n = {g: 0 for g in gov_dist}

            first_prod_code = list(all_products_results.keys())[0] if all_products_results else product_code
            first_prod_data = all_products_results.get(first_prod_code, {})
            prod_ecart_adj = first_prod_data.get('ecart_adjustments', [])
            reels_par_secteur = {adj.get('secteur', ''): adj.get('valeur_realisee', 0) or 0 for adj in prod_ecart_adj}

            secteur_to_gov_map = {}
            sonat_app_local = st.session_state.get('sonat_app')
            if sonat_app_local is not None and hasattr(sonat_app_local, 'results') and product_code in sonat_app_local.results:
                prod_results = sonat_app_local.results[product_code].get('objectives', {})
                for pc_item, pdata in prod_results.items():
                    if pc_item == '_TOTAUX_' or not isinstance(pdata, dict):
                        continue
                    gov_distrib = pdata.get('governorat_distribution', {})
                    for g_name, g_data in gov_distrib.items():
                        if isinstance(g_data, dict):
                            for s_name in g_data.get('secteurs', []):
                                secteur_to_gov_map[s_name] = g_name
                                if hasattr(sonat_app_local, '_normalize_secteur_name'):
                                    secteur_to_gov_map[sonat_app_local._normalize_secteur_name(s_name)] = g_name

            for s, sd in secteur_dist.items():
                g_field = sd.get('gouvernorat', '')
                if g_field and s not in secteur_to_gov_map:
                    secteur_to_gov_map[s] = g_field

            def _resolve_gov(_s):
                _g = secteur_to_gov_map.get(_s, '')
                if not _g and sonat_app_local is not None and hasattr(sonat_app_local, '_normalize_secteur_name'):
                    _g = secteur_to_gov_map.get(sonat_app_local._normalize_secteur_name(_s), '')
                return _g

            for s, sd in secteur_dist.items():
                g_for_s = _resolve_gov(s)
                if g_for_s and g_for_s in gov_n1_totals:
                    gov_n1_totals[g_for_s] += sd.get('objectif_n1_corrige', sd.get('quantite', 0)) or 0

            for s_name, reel in reels_par_secteur.items():
                g_for_s = _resolve_gov(s_name)
                if g_for_s and g_for_s in gov_reels_n:
                    gov_reels_n[g_for_s] += reel

            for g in list(gov_n1_totals.keys()):
                if gov_n1_totals[g] == 0:
                    gov_n1_totals[g] = gov_dist[g].get('quantite', 0) or 0

            total_gov_n1 = sum(gov_n1_totals.values())
            st.markdown(
                f"**Objectif total {year_n1_label} par gouvernorat :** {total_gov_n1:,.0f} unités"
            )

            gov_data = []
            for g, gd in gov_dist.items():
                objectif_n1 = gov_n1_totals.get(g, gd.get('quantite', 0) or 0)
                reel_n = gov_reels_n.get(g, 0)
                part = (objectif_n1 / total_gov_n1 *
                        100) if total_gov_n1 > 0 else 0
                evolution = ((objectif_n1 - reel_n) / reel_n * 100) if reel_n > 0 else 0
                gov_data.append({
                    'Gouvernorat': g,
                    f'Objectif {year_n1_label}': objectif_n1,
                    'Poid %': part,
                    'Évolution': evolution
                })

            gov_df = pd.DataFrame(gov_data)
            gov_df = gov_df.sort_values('Gouvernorat')

            gov_df_display = gov_df.copy()
            gov_df_display[f'Objectif {year_n1_label}'] = gov_df_display[
                f'Objectif {year_n1_label}'].apply(lambda x: f"{float(x):,.0f}")
            gov_df_display['Poid %'] = gov_df_display['Poid %'].apply(
                lambda x: f"{float(x):.1f}%")
            gov_df_display['Évolution'] = gov_df_display['Évolution'].apply(
                lambda x: f"{float(x):.1f}%")

            gov_df_display = gov_df_display[[
                'Gouvernorat', f'Objectif {year_n1_label}', 'Poid %', 'Évolution'
            ]]
            compact_col_config = {col: st.column_config.TextColumn(col, width="small") for col in gov_df_display.columns}
            st.dataframe(gov_df_display, use_container_width=True, hide_index=True, column_config=compact_col_config)

        # Section téléchargement seulement si gov_df est défini
        if gov_df is not None:
            st.markdown('<div class="download-buttons-container">',
                        unsafe_allow_html=True)

            # Obtenir le nom pour le fichier
            if len(all_products_results) > 1:
                product_name_for_file = "multi_produits"
            else:
                product_name_for_file = product_code
                if app.data_n2 is not None and 'Produit' in app.data_n2.columns and 'Code PCT' in app.data_n2.columns:
                    produit_info = app.data_n2[app.data_n2['Code PCT'] == product_code]
                    if not produit_info.empty and 'Produit' in produit_info.columns:
                        product_name_for_file = produit_info['Produit'].iloc[
                            0].replace(' ', '_').replace('/', '_')

            if len(all_products_results) <= 1:
                gov_export_cols = ['Gouvernorat', f'Objectif {year_n1_label}', 'Poid %']
                if 'Évolution' in gov_df.columns:
                    gov_export_cols.append('Évolution')
                gov_simple_df = gov_df[gov_export_cols].copy()
                gov_simple_df['Poid %'] = gov_simple_df['Poid %'].apply(lambda x: f"{float(x):.1f}%" if pd.notna(x) else "0%")
                if 'Évolution' in gov_simple_df.columns:
                    gov_simple_df['Évolution'] = gov_simple_df['Évolution'].apply(lambda x: f"{float(x):.1f}%" if pd.notna(x) else "0%")
                try:
                    gov_simple_df['Année'] = int(year_n1_label)
                except (ValueError, TypeError):
                    gov_simple_df['Année'] = year_n1_label
                gov_export_cols.append('Année')
                excel_gov = to_excel_simple(gov_simple_df, gov_export_cols)
            else:
                gov_export_df = gov_df.copy()
                for col in gov_export_df.columns:
                    if 'Poids de produit' in col:
                        gov_export_df[col] = gov_export_df[col].apply(lambda x: f"{float(x):.1f}%" if pd.notna(x) else "0%")
                    elif 'Évolution de produit' in col:
                        gov_export_df[col] = gov_export_df[col].apply(lambda x: f"{float(x):.1f}%" if pd.notna(x) else "0%")
                try:
                    gov_export_df['Année'] = int(year_n1_label)
                except (ValueError, TypeError):
                    gov_export_df['Année'] = year_n1_label
                excel_gov = to_excel_simple(gov_export_df, list(gov_export_df.columns))

            # Clé stable pour le mode multi-produit
            download_key = "excel_gouvernorats_multi" if len(all_products_results) > 1 else f"excel_gouvernorats_{product_code}"
            st.download_button(
                label="Télécharger la répartition par Gouvernorats",
                data=excel_gov,
                file_name=
                f"Objectif_par_gouvernorat_{product_name_for_file}_{year_n1_label}_{datetime.now().strftime('%Y%m%d')}.xlsx",
                mime=
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key=download_key)
            st.markdown('</div>', unsafe_allow_html=True)
    else:
        st.warning("Aucune distribution par gouvernorat disponible.")

    st.markdown('<div class="section-header">Répartition par Secteurs</div>',
                unsafe_allow_html=True)

    if secteur_dist:
        # Vérifier si on a plusieurs produits
        all_products_results = st.session_state.get('all_products_results', {})
        
        secteur_df = None  # Initialiser pour éviter UnboundLocalError
        
        if len(all_products_results) > 1:
            # Mode multi-produits : afficher tous les produits en colonnes avec poids
            secteur_data = {}
            product_totals = {}  # Pour calculer les pourcentages
            
            # Récupérer les secteurs exclus par produit
            secteurs_retires_par_produit = st.session_state.get('secteurs_retires_par_produit', {})
            
            year_n = st.session_state.get('detected_year_n', 'N')
            try:
                year_n1_display = str(int(year_n) + 1)
            except (ValueError, TypeError):
                year_n1_display = "N+1"
            
            # Première passe : collecter les données et calculer les totaux (avec exclusions)
            for prod_code, prod_data in all_products_results.items():
                prod_name = prod_data.get('name', prod_code)
                prod_secteur_dist = prod_data.get('secteur_dist', {})
                secteurs_exclus = secteurs_retires_par_produit.get(prod_code, [])
                
                # Calculer le total pour ce produit (après exclusions)
                product_totals[prod_name] = sum(
                    sd.get('objectif_n1_corrige', sd.get('quantite', 0)) or 0
                    for s, sd in prod_secteur_dist.items()
                    if s not in secteurs_exclus
                )
                
                # Nom de colonne avec retour à la ligne
                col_objectif = f"Objectif {year_n1_display} de produit\n{prod_name}"
                
                col_evolution = f"Évolution de produit\n{prod_name}"
                
                prod_ecart_adj = prod_data.get('ecart_adjustments', [])
                reels_par_secteur = {adj.get('secteur', ''): adj.get('valeur_realisee', 0) or 0 for adj in prod_ecart_adj}
                
                for s, sd in prod_secteur_dist.items():
                    if s in secteurs_exclus:
                        continue
                    if s not in secteur_data:
                        secteur_data[s] = {'Secteur': s}
                    obj_n1 = sd.get('objectif_n1_corrige', sd.get('quantite', 0)) or 0
                    reel_n = reels_par_secteur.get(s, 0)
                    secteur_data[s][col_objectif] = obj_n1
                    if reel_n > 0:
                        secteur_data[s][col_evolution] = ((obj_n1 - reel_n) / reel_n) * 100
                    else:
                        secteur_data[s][col_evolution] = 0
            
            if secteur_data:
                secteur_df = pd.DataFrame(list(secteur_data.values()))
                secteur_df = secteur_df.sort_values('Secteur')
                secteur_df = secteur_df.fillna(0)
                
                # Ajouter les colonnes de poids pour chaque produit
                for prod_code, prod_data in all_products_results.items():
                    prod_name = prod_data.get('name', prod_code)
                    col_objectif = f"Objectif {year_n1_display} de produit\n{prod_name}"
                    col_poids = f"Poids de produit\n{prod_name}"
                    total = product_totals.get(prod_name, 0)
                    if total > 0 and col_objectif in secteur_df.columns:
                        secteur_df[col_poids] = secteur_df[col_objectif].apply(
                            lambda x: (float(x) / total * 100) if pd.notna(x) else 0
                        )
                
                ordered_cols = ['Secteur']
                for prod_code, prod_data in all_products_results.items():
                    prod_name = prod_data.get('name', prod_code)
                    col_objectif = f"Objectif {year_n1_display} de produit\n{prod_name}"
                    col_poids = f"Poids de produit\n{prod_name}"
                    col_evolution = f"Évolution de produit\n{prod_name}"
                    if col_objectif in secteur_df.columns:
                        ordered_cols.append(col_objectif)
                    if col_poids in secteur_df.columns:
                        ordered_cols.append(col_poids)
                    if col_evolution in secteur_df.columns:
                        ordered_cols.append(col_evolution)
                secteur_df = secteur_df[ordered_cols]
                
                secteur_df_display = secteur_df.copy()
                for col in secteur_df_display.columns:
                    if col == 'Secteur':
                        continue
                    elif 'Poids de produit' in col:
                        secteur_df_display[col] = secteur_df_display[col].apply(lambda x: f"{float(x):.1f}%" if pd.notna(x) else "0%")
                    elif 'Évolution de produit' in col:
                        secteur_df_display[col] = secteur_df_display[col].apply(lambda x: f"{float(x):.1f}%" if pd.notna(x) else "0%")
                    else:
                        secteur_df_display[col] = secteur_df_display[col].apply(lambda x: f"{float(x):,.0f}" if pd.notna(x) else "0")
                
                compact_col_config = {col: st.column_config.TextColumn(col, width="small") for col in secteur_df_display.columns}
                st.dataframe(secteur_df_display, use_container_width=True, hide_index=True, column_config=compact_col_config)
            else:
                st.warning("Aucune distribution disponible pour les produits sélectionnés.")
        else:
            # Mode mono-produit (existant)
            total_n1_secteur = sum(
                sd.get('objectif_n1_corrige', sd.get('quantite', 0))
                for sd in secteur_dist.values())
            st.markdown(
                f"**Objectif total {year_n1_label} par secteur :** {total_n1_secteur:,.0f} unités"
            )

            first_prod_code = list(all_products_results.keys())[0] if all_products_results else product_code
            first_prod_data = all_products_results.get(first_prod_code, {})
            prod_ecart_adj = first_prod_data.get('ecart_adjustments', [])
            reels_par_secteur = {adj.get('secteur', ''): adj.get('valeur_realisee', 0) or 0 for adj in prod_ecart_adj}
            
            secteur_data = []
            for s, sd in secteur_dist.items():
                objectif_n1 = sd.get('objectif_n1_corrige', sd.get('quantite',
                                                                   0)) or 0
                reel_n = reels_par_secteur.get(s, 0)
                part = (objectif_n1 / total_n1_secteur *
                        100) if total_n1_secteur > 0 else 0
                evolution = ((objectif_n1 - reel_n) / reel_n * 100) if reel_n > 0 else 0
                row = {
                    'Secteur': s,
                    f'Objectif {year_n1_label}': objectif_n1,
                    'Poid %': part,
                    'Évolution': evolution
                }
                secteur_data.append(row)

            secteur_df = pd.DataFrame(secteur_data)
            secteur_df = secteur_df.sort_values('Secteur')

            secteur_df_display = secteur_df.copy()
            secteur_df_display[f'Objectif {year_n1_label}'] = secteur_df_display[
                f'Objectif {year_n1_label}'].apply(lambda x: f"{float(x):,.0f}")
            secteur_df_display['Poid %'] = secteur_df_display['Poid %'].apply(
                lambda x: f"{float(x):.1f}%")
            secteur_df_display['Évolution'] = secteur_df_display['Évolution'].apply(
                lambda x: f"{float(x):.1f}%")

            secteur_df_display = secteur_df_display[[
                'Secteur', f'Objectif {year_n1_label}', 'Poid %', 'Évolution'
            ]]
            compact_col_config = {col: st.column_config.TextColumn(col, width="small") for col in secteur_df_display.columns}
            st.dataframe(secteur_df_display,
                         use_container_width=True,
                         hide_index=True,
                         column_config=compact_col_config)

        # Section téléchargement seulement si secteur_df est défini
        if secteur_df is not None:
            st.markdown('<div class="download-buttons-container">',
                        unsafe_allow_html=True)

            # Obtenir le nom pour le fichier
            if len(all_products_results) > 1:
                product_name_for_file = "multi_produits"
            else:
                product_name_for_file = product_code
                if app.data_n2 is not None and 'Produit' in app.data_n2.columns and 'Code PCT' in app.data_n2.columns:
                    produit_info = app.data_n2[app.data_n2['Code PCT'] == product_code]
                    if not produit_info.empty and 'Produit' in produit_info.columns:
                        product_name_for_file = produit_info['Produit'].iloc[
                            0].replace(' ', '_').replace('/', '_')

            if len(all_products_results) <= 1:
                secteur_export_cols = ['Secteur', f'Objectif {year_n1_label}', 'Poid %']
                if 'Évolution' in secteur_df.columns:
                    secteur_export_cols.append('Évolution')
                secteur_simple_df = secteur_df[secteur_export_cols].copy()
                secteur_simple_df['Poid %'] = secteur_simple_df['Poid %'].apply(lambda x: f"{float(x):.1f}%" if pd.notna(x) else "0%")
                if 'Évolution' in secteur_simple_df.columns:
                    secteur_simple_df['Évolution'] = secteur_simple_df['Évolution'].apply(lambda x: f"{float(x):.1f}%" if pd.notna(x) else "0%")
                try:
                    secteur_simple_df['Année'] = int(year_n1_label)
                except (ValueError, TypeError):
                    secteur_simple_df['Année'] = year_n1_label
                secteur_export_cols.append('Année')
                excel_secteur = to_excel_simple(secteur_simple_df, secteur_export_cols)
            else:
                secteur_export_df = secteur_df.copy()
                for col in secteur_export_df.columns:
                    if 'Poids de produit' in col:
                        secteur_export_df[col] = secteur_export_df[col].apply(lambda x: f"{float(x):.1f}%" if pd.notna(x) else "0%")
                    elif 'Évolution de produit' in col:
                        secteur_export_df[col] = secteur_export_df[col].apply(lambda x: f"{float(x):.1f}%" if pd.notna(x) else "0%")
                try:
                    secteur_export_df['Année'] = int(year_n1_label)
                except (ValueError, TypeError):
                    secteur_export_df['Année'] = year_n1_label
                excel_secteur = to_excel_simple(secteur_export_df, list(secteur_export_df.columns))

            # Clé stable pour le mode multi-produit
            download_key_secteur = "excel_secteurs_multi" if len(all_products_results) > 1 else f"excel_secteurs_{product_code}"
            st.download_button(
                label="Télécharger la répartition par Secteurs",
                data=excel_secteur,
                file_name=
                f"Objectif_par_secteur_{product_name_for_file}_{year_n1_label}_{datetime.now().strftime('%Y%m%d')}.xlsx",
                mime=
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key=download_key_secteur)
            st.markdown('</div>', unsafe_allow_html=True)
    else:
        st.warning("Aucune distribution par secteur disponible.")

    st.markdown(f"""
<div class="footer">
    © {datetime.now().year} JUNO Performance by Sentinel Data 
    <a href="mailto:analytics@sentinel.dz" style="color:#3B82F6; text-decoration:none;">Contact Support</a>
</div>
""",
                unsafe_allow_html=True)


@st.cache_data(ttl=3600)
def load_map_geojson():
    """Charge le GeoJSON de la carte de Tunisie"""
    import json as _json
    map_path = os.path.join(os.path.dirname(__file__), 'map_tunisie_geojson.json')
    with open(map_path, 'r') as f:
        return _json.load(f)

GOUVERNORAT_COORDS = {
    'Tunis': {'lat': 36.8065, 'lon': 10.1815},
    'Ariana': {'lat': 36.8625, 'lon': 10.1956},
    'Ben Arous': {'lat': 36.7533, 'lon': 10.2283},
    'Manouba': {'lat': 36.8101, 'lon': 9.8871},
    'Nabeul': {'lat': 36.4513, 'lon': 10.7357},
    'Zaghouan': {'lat': 36.4029, 'lon': 10.1428},
    'Bizerte': {'lat': 37.2746, 'lon': 9.8739},
    'Beja': {'lat': 36.7256, 'lon': 9.1817},
    'Jendouba': {'lat': 36.5011, 'lon': 8.7803},
    'Le Kef': {'lat': 36.1826, 'lon': 8.7148},
    'Siliana': {'lat': 36.0850, 'lon': 9.3708},
    'Sousse': {'lat': 35.8288, 'lon': 10.6405},
    'Monastir': {'lat': 35.7643, 'lon': 10.8113},
    'Mahdia': {'lat': 35.5047, 'lon': 11.0622},
    'Sfax': {'lat': 34.7406, 'lon': 10.7603},
    'Kairouan': {'lat': 35.6781, 'lon': 10.0963},
    'Kasserine': {'lat': 35.1676, 'lon': 8.8365},
    'Sidi Bouzid': {'lat': 35.0382, 'lon': 9.4849},
    'Gabes': {'lat': 33.8815, 'lon': 10.0982},
    'Medenine': {'lat': 33.3549, 'lon': 10.5054},
    'Tataouine': {'lat': 32.9297, 'lon': 10.4518},
    'Gafsa': {'lat': 34.4250, 'lon': 8.7842},
    'Tozeur': {'lat': 33.9197, 'lon': 8.1339},
    'Kebili': {'lat': 33.7044, 'lon': 8.9690}
}

# Coordonnées réelles des secteurs (latitude/longitude moyennes)
SECTOR_COORDS = {
    'Beja 1': {'lat': 36.802049, 'lon': 9.138042},
    'Beja 2': {'lat': 36.548012, 'lon': 9.438940},
    'Bizerte 101': {'lat': 37.262721, 'lon': 9.871359},
    'Bizerte 111': {'lat': 37.174367, 'lon': 9.982116},
    'Bizerte 121': {'lat': 37.078450, 'lon': 9.543735},
    'Gabes 1': {'lat': 33.925878, 'lon': 10.053833},
    'Gabes 2': {'lat': 33.786887, 'lon': 10.037633},
    'Gafsa 1': {'lat': 34.467182, 'lon': 8.763861},
    'Gafsa 2': {'lat': 34.411631, 'lon': 8.759314},
    'Jendouba 1': {'lat': 36.484687, 'lon': 8.586597},
    'Jendouba 2': {'lat': 36.728038, 'lon': 8.776740},
    'Kairouan 1': {'lat': 35.612522, 'lon': 10.144899},
    'Kairouan 2': {'lat': 35.587540, 'lon': 9.837944},
    'Kasserine 1': {'lat': 35.006209, 'lon': 8.652424},
    'Kasserine 2': {'lat': 35.405893, 'lon': 8.824111},
    'Kebili': {'lat': 33.594307, 'lon': 8.960060},
    'Le Kef 1': {'lat': 36.168128, 'lon': 8.711020},
    'Le Kef 2': {'lat': 35.873024, 'lon': 8.665667},
    'Mahdia 1': {'lat': 35.412507, 'lon': 11.026458},
    'Mahdia 2': {'lat': 35.351876, 'lon': 10.630661},
    'Manouba 101': {'lat': 36.818663, 'lon': 10.094024},
    'Manouba 111': {'lat': 36.729476, 'lon': 9.933322},
    'Manouba 121': {'lat': 36.843866, 'lon': 9.920221},
    'Medenine 1': {'lat': 33.421633, 'lon': 10.651775},
    'Medenine 2': {'lat': 33.801480, 'lon': 10.864856},
    'Medenine 3': {'lat': 33.167116, 'lon': 11.130132},
    'Monastir 1': {'lat': 35.764554, 'lon': 10.812839},
    'Monastir 2': {'lat': 35.661842, 'lon': 10.892529},
    'Monastir 3': {'lat': 35.626302, 'lon': 10.864162},
    'Monastir 4': {'lat': 35.680597, 'lon': 10.742058},
    'Nabeul 101': {'lat': 36.476936, 'lon': 10.737049},
    'Nabeul 102': {'lat': 36.410905, 'lon': 10.631675},
    'Nabeul 201': {'lat': 36.590710, 'lon': 10.836404},
    'Nabeul 211': {'lat': 36.917726, 'lon': 11.014360},
    'Nabeul 221': {'lat': 36.597446, 'lon': 10.532472},
    'Nabeul 222': {'lat': 36.698475, 'lon': 10.605917},
    'Sidi Bouzid 1': {'lat': 35.098568, 'lon': 9.451067},
    'Sidi Bouzid 2': {'lat': 34.861211, 'lon': 9.642124},
    'Siliana': {'lat': 36.101649, 'lon': 9.339354},
    'Sousse 101': {'lat': 35.826744, 'lon': 10.632486},
    'Sousse 102': {'lat': 35.850632, 'lon': 10.617194},
    'Sousse 103': {'lat': 35.808531, 'lon': 10.618599},
    'Sousse 201': {'lat': 35.793709, 'lon': 10.522161},
    'Sousse 211': {'lat': 36.086262, 'lon': 10.413340},
    'Tataouine': {'lat': 32.911884, 'lon': 10.448622},
    'Tozeur': {'lat': 34.005451, 'lon': 8.101053},
    'Zaghouan': {'lat': 36.331960, 'lon': 10.062966}
}

def get_sector_coords(secteur_name):
    """Récupère les coordonnées d'un secteur (réelles ou approximatives)"""
    # Chercher d'abord dans les coordonnées réelles des secteurs
    if secteur_name in SECTOR_COORDS:
        return SECTOR_COORDS[secteur_name]
    
    # Sinon, utiliser les coordonnées du gouvernorat
    gouvernorat = get_gouvernorat_from_secteur(secteur_name)
    if gouvernorat in GOUVERNORAT_COORDS:
        coords = GOUVERNORAT_COORDS[gouvernorat]
        # Ajouter un léger décalage pour différencier les secteurs du même gouvernorat
        return {'lat': coords['lat'], 'lon': coords['lon']}
    
    # Coordonnées par défaut (centre de la Tunisie)
    return {'lat': 34.5, 'lon': 9.5}

def get_gouvernorat_from_secteur(secteur_name):
    """Extrait le gouvernorat du nom de secteur"""
    parts = secteur_name.split()
    if len(parts) >= 2:
        if parts[0] in ['Ben', 'Le', 'Sidi']:
            return ' '.join(parts[:2])
        return parts[0]
    return secteur_name

@st.fragment
def display_visualisations(delegue_results, delegue_calculator):
    """Affiche les visualisations: carte + graphiques d'objectifs"""
    
    st.markdown("""
    <div style="background: linear-gradient(135deg, #F8FAFC 0%, #FFFFFF 100%); padding: 1.5rem 2rem; border-radius: 16px; margin-bottom: 1.5rem; box-shadow: 0 4px 20px rgba(0,0,0,0.05); border: 1px solid #E5E5E5; text-align: center;">
        <div style="color: #64748B; font-size: 0.85rem; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 0.5rem;">Vue graphique</div>
        <div class="dark-text" style="font-size: 1.8rem; font-weight: 700;">Visualisations</div>
    </div>
    """, unsafe_allow_html=True)
    
    if not delegue_results or 'regions' not in delegue_results:
        st.warning("Veuillez d'abord calculer la répartition des délégués.")
        return
    
    all_delegates_data = []
    delegate_colors = {}
    px, go = _get_plotly()
    color_palette = px.colors.qualitative.Set3 + px.colors.qualitative.Pastel1 + px.colors.qualitative.Dark24
    color_idx = 0
    
    for region_name, region_data in delegue_results['regions'].items():
        repartition_data = region_data.get('repartition') or region_data.get('repartition_delegues', {})
        if repartition_data:
            for delegate_key, delegate_info in repartition_data.items():
                delegate_label = f"{region_name} - {delegate_key}"
                if delegate_label not in delegate_colors:
                    delegate_colors[delegate_label] = color_palette[color_idx % len(color_palette)]
                    color_idx += 1
                
                secteurs = delegate_info.get('secteurs', [])
                objectif_total = delegate_info.get('objectif_total', 0)
                
                for secteur in secteurs:
                    if isinstance(secteur, dict):
                        secteur_nom = secteur.get('nom', '')
                        secteur_objectif = secteur.get('objectif', 0)
                    else:
                        secteur_nom = secteur
                        secteur_objectif = 0
                    
                    gouvernorat = get_gouvernorat_from_secteur(secteur_nom)
                    
                    all_delegates_data.append({
                        'Région': region_name,
                        'Délégué': delegate_label,
                        'Secteur': secteur_nom,
                        'Gouvernorat': gouvernorat,
                        'Objectif': secteur_objectif,
                        'Couleur': delegate_colors[delegate_label]
                    })
    
    if not all_delegates_data:
        st.warning("Aucune donnée de répartition disponible pour les visualisations.")
        return
    
    df_viz = pd.DataFrame(all_delegates_data)
    
    st.markdown("""
    <div style="background: linear-gradient(135deg, #F8FAFC 0%, #FFFFFF 100%); padding: 1rem 1.5rem; border-radius: 12px; margin-bottom: 1rem; border: 1px solid #E2E8F0;">
        <div style="font-size: 1.2rem; font-weight: 600; color: #1E293B; margin-bottom: 0.25rem;">Carte de répartition des délégués</div>
        <div style="font-size: 0.85rem; color: #64748B;">Chaque couleur représente un délégué • Utilisez les filtres ci-dessous</div>
    </div>
    """, unsafe_allow_html=True)
    
    # Filtres
    col_filter1, col_filter2 = st.columns(2)
    
    with col_filter1:
        regions_disponibles = ['Toutes les régions'] + sorted(df_viz['Région'].unique().tolist())
        region_selectionnee = st.selectbox(
            "Filtrer par région",
            options=regions_disponibles,
            key="map_region_filter"
        )
    
    with col_filter2:
        # Filtrer les délégués selon la région sélectionnée
        if region_selectionnee == 'Toutes les régions':
            delegues_disponibles = ['Tous les délégués'] + sorted(df_viz['Délégué'].unique().tolist())
        else:
            delegues_region = df_viz[df_viz['Région'] == region_selectionnee]['Délégué'].unique().tolist()
            delegues_disponibles = ['Tous les délégués'] + sorted(delegues_region)
        
        delegue_selectionne = st.selectbox(
            "Filtrer par délégué",
            options=delegues_disponibles,
            key="map_delegue_filter"
        )
    
    # Appliquer les filtres
    df_filtered = df_viz.copy()
    
    if region_selectionnee != 'Toutes les régions':
        df_filtered = df_filtered[df_filtered['Région'] == region_selectionnee]
    
    if delegue_selectionne != 'Tous les délégués':
        df_filtered = df_filtered[df_filtered['Délégué'] == delegue_selectionne]
    
    # Afficher les stats du filtre
    nb_secteurs = len(df_filtered)
    nb_delegues = df_filtered['Délégué'].nunique()
    objectif_total = df_filtered['Objectif'].sum()
    
    st.markdown(f"""
    <div style="display: flex; gap: 1rem; margin-bottom: 1rem;">
        <div style="flex: 1; background: #F1F5F9; padding: 0.75rem; border-radius: 8px; text-align: center;">
            <div style="font-size: 1.2rem; font-weight: 700; color: #1E293B;">{nb_secteurs}</div>
            <div style="font-size: 0.75rem; color: #64748B;">Secteurs affichés</div>
        </div>
        <div style="flex: 1; background: #F1F5F9; padding: 0.75rem; border-radius: 8px; text-align: center;">
            <div style="font-size: 1.2rem; font-weight: 700; color: #1E293B;">{nb_delegues}</div>
            <div style="font-size: 0.75rem; color: #64748B;">Délégués</div>
        </div>
        <div style="flex: 1; background: #F1F5F9; padding: 0.75rem; border-radius: 8px; text-align: center;">
            <div style="font-size: 1.2rem; font-weight: 700; color: #1E293B;">{objectif_total:,.0f}</div>
            <div style="font-size: 0.75rem; color: #64748B;">Objectif total</div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    if df_filtered.empty:
        st.warning("Aucun secteur ne correspond aux filtres sélectionnés.")
        return
    
    filtered_delegate_colors = {d: delegate_colors[d] for d in df_filtered['Délégué'].unique() if d in delegate_colors}
    
    geojson_data = load_map_geojson()
    
    secteur_to_delegate = {}
    secteur_to_info = {}
    for _, row in df_filtered.iterrows():
        secteur_to_delegate[row['Secteur']] = row['Délégué']
        secteur_to_info[row['Secteur']] = {
            'Gouvernorat': row['Gouvernorat'],
            'Région': row['Région'],
            'Objectif': row['Objectif']
        }
    
    filtered_features = []
    choropleth_ids = []
    choropleth_delegates = []
    choropleth_secteurs = []
    choropleth_gouvernorats = []
    choropleth_regions = []
    choropleth_objectifs = []
    
    for feature in geojson_data['features']:
        sector_name = feature['properties'].get('name_2', '')
        if sector_name in secteur_to_delegate:
            filtered_features.append(feature)
            fid = feature['id']
            delegate = secteur_to_delegate[sector_name]
            info = secteur_to_info[sector_name]
            choropleth_ids.append(fid)
            choropleth_delegates.append(delegate)
            choropleth_secteurs.append(sector_name)
            choropleth_gouvernorats.append(info['Gouvernorat'])
            choropleth_regions.append(info['Région'])
            choropleth_objectifs.append(info['Objectif'])
    
    filtered_geojson = {'type': 'FeatureCollection', 'features': filtered_features}
    
    unique_delegates = sorted(set(choropleth_delegates))
    delegate_color_map = {d: filtered_delegate_colors.get(d, '#999999') for d in unique_delegates}
    delegate_to_idx = {d: i for i, d in enumerate(unique_delegates)}
    z_values = [delegate_to_idx[d] for d in choropleth_delegates]
    
    n = len(unique_delegates)
    color_scale = []
    if n == 1:
        c = delegate_color_map[unique_delegates[0]]
        color_scale = [[0, c], [1, c]]
    elif n > 1:
        for i, d in enumerate(unique_delegates):
            lower = i / (n - 1) if n > 1 else 0
            upper = i / (n - 1) if n > 1 else 1
            c = delegate_color_map[d]
            color_scale.append([lower, c])
    
    if not choropleth_ids:
        st.warning("Aucun secteur trouvé sur la carte pour les filtres sélectionnés.")
        return
    
    fig_map = go.Figure(go.Choroplethmapbox(
        geojson=filtered_geojson,
        locations=choropleth_ids,
        featureidkey="id",
        z=z_values,
        zmin=0,
        zmax=max(n - 1, 1),
        colorscale=color_scale if color_scale else [[0, '#999999'], [1, '#999999']],
        marker_opacity=0.65,
        marker_line_width=0.5,
        marker_line_color='white',
        showscale=False,
        text=[f"<b>{s}</b><br>Gouvernorat: {g}<br>Région: {r}<br>Objectif: {o:,.0f}<br>Délégué: {d}" 
              for s, g, r, o, d in zip(choropleth_secteurs, choropleth_gouvernorats, choropleth_regions, choropleth_objectifs, choropleth_delegates)],
        hoverinfo='text'
    ))
    
    for delegate_name in unique_delegates:
        fig_map.add_trace(go.Scattermapbox(
            lat=[None], lon=[None],
            mode='markers',
            marker=dict(size=12, color=delegate_color_map[delegate_name]),
            name=delegate_name,
            showlegend=True
        ))
    
    all_lats = []
    all_lons = []
    for feat in filtered_features:
        geom = feat['geometry']
        coords_list = []
        if geom['type'] == 'Polygon':
            coords_list = geom['coordinates'][0]
        elif geom['type'] == 'MultiPolygon':
            for poly in geom['coordinates']:
                coords_list.extend(poly[0])
        for coord in coords_list:
            all_lons.append(coord[0])
            all_lats.append(coord[1])
    
    if all_lats:
        center_lat = (min(all_lats) + max(all_lats)) / 2
        center_lon = (min(all_lons) + max(all_lons)) / 2
        lat_range = max(all_lats) - min(all_lats)
        if lat_range > 5:
            zoom_level = 5.5
        elif lat_range > 2:
            zoom_level = 7
        elif lat_range > 1:
            zoom_level = 8
        else:
            zoom_level = 9
    else:
        center_lat, center_lon, zoom_level = 34.5, 9.5, 6
    
    fig_map.update_layout(
        mapbox_style='carto-positron',
        mapbox_center={'lat': center_lat, 'lon': center_lon},
        mapbox_zoom=zoom_level,
        height=700,
        margin=dict(l=0, r=0, t=10, b=10),
        legend=dict(
            orientation='h',
            yanchor='top',
            y=-0.02,
            xanchor='center',
            x=0.5,
            font=dict(size=11, color='#334155'),
            bgcolor='rgba(255,255,255,0.9)',
            bordercolor='#E2E8F0',
            borderwidth=1
        ),
        hoverlabel=dict(
            bgcolor='white',
            font_size=12,
            font_family='Inter, sans-serif'
        )
    )
    
    st.plotly_chart(fig_map, use_container_width=True, config={
        'displayModeBar': True,
        'modeBarButtonsToInclude': ['zoomIn2d', 'zoomOut2d', 'resetScale2d'],
        'displaylogo': False
    })

def display_gestion_utilisateurs():
    """Vue de gestion des utilisateurs - admin uniquement"""
    st.markdown("""
    <div style="background: linear-gradient(135deg, #F8FAFC 0%, #FFFFFF 100%); padding: 1.5rem 2rem; border-radius: 16px; margin-bottom: 1.5rem; box-shadow: 0 4px 20px rgba(0,0,0,0.05); border: 1px solid #E5E5E5; text-align: center;">
        <h2 style="margin: 0; font-size: 1.8rem; font-weight: 700; color: #1a1a1a;">Gestion des Utilisateurs</h2>
        <p style="margin: 0.5rem 0 0 0; color: #6b7280; font-size: 1rem;">Ajouter, modifier, activer/désactiver et supprimer les utilisateurs</p>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""<style>
    div[data-testid="stColumn"] div[data-testid="stButton"] > button {
        font-size: 0.75rem !important;
        padding: 0.2rem 0.6rem !important;
        min-height: 0 !important;
        height: 1.8rem !important;
        line-height: 1 !important;
        width: auto !important;
        white-space: nowrap !important;
    }
    </style>""", unsafe_allow_html=True)

    if 'admin_action_msg' not in st.session_state:
        st.session_state.admin_action_msg = None

    if st.session_state.admin_action_msg:
        msg_type, msg_text = st.session_state.admin_action_msg
        if msg_type == 'success':
            st.success(msg_text)
        else:
            st.error(msg_text)
        st.session_state.admin_action_msg = None

    @st.dialog("Ajouter un nouvel utilisateur")
    def show_add_user_dialog():
        col1, col2 = st.columns(2)
        with col1:
            new_username = st.text_input("Nom d'utilisateur", key="dlg_new_username", placeholder="ex: jdupont")
            new_email = st.text_input("Email", key="dlg_new_email", placeholder="ex: j.dupont@labo.com")
            new_password = st.text_input("Mot de passe", key="dlg_new_password", type="password")
            new_role = st.selectbox("Rôle", ["user", "admin"], key="dlg_new_role")
        with col2:
            new_first_name = st.text_input("Prénom", key="dlg_new_firstname", placeholder="ex: Jean")
            new_last_name = st.text_input("Nom", key="dlg_new_lastname", placeholder="ex: Dupont")
            new_laboratoire = st.text_input("Laboratoire", key="dlg_new_lab", placeholder="ex: Sanofi")

        st.markdown("<div style='height: 0.5rem;'></div>", unsafe_allow_html=True)
        if st.button("Créer l'utilisateur", key="btn_dlg_create_user", type="primary", use_container_width=True):
            if not new_username or not new_email or not new_password:
                st.error("Nom d'utilisateur, email et mot de passe sont obligatoires.")
            else:
                result = create_user(
                    username=new_username,
                    email=new_email,
                    password=new_password,
                    first_name=new_first_name if new_first_name else None,
                    last_name=new_last_name if new_last_name else None,
                    role=new_role,
                    laboratoire=new_laboratoire if new_laboratoire else None
                )
                if result['success']:
                    st.session_state.admin_action_msg = ('success', f"Utilisateur '{new_username}' créé avec succès !")
                    st.rerun()
                else:
                    st.error(result['error'])

    @st.dialog("Modifier l'utilisateur")
    def show_edit_user_dialog(user_data):
        user_id = user_data['id']
        st.markdown(f"**Utilisateur :** {user_data['username']}")
        st.markdown(f"**Email :** {user_data['email']}")
        st.divider()

        current_role = user_data.get('role', 'user')
        role_options = ["user", "admin", "manager"]
        role_index = role_options.index(current_role) if current_role in role_options else 0
        new_role = st.selectbox("Rôle", role_options, index=role_index, key=f"dlg_edit_role_{user_id}")

        current_lab = user_data.get('laboratoire') or ""
        new_lab = st.text_input("Laboratoire", value=current_lab, key=f"dlg_edit_lab_{user_id}", placeholder="ex: Sanofi")

        st.divider()
        st.markdown("**Réinitialiser le mot de passe**")
        new_password = st.text_input("Nouveau mot de passe", key=f"dlg_edit_pwd_{user_id}", type="password", placeholder="Laisser vide pour ne pas changer")
        confirm_password = st.text_input("Confirmer le mot de passe", key=f"dlg_edit_pwd_confirm_{user_id}", type="password")

        st.markdown("<div style='height: 0.5rem;'></div>", unsafe_allow_html=True)
        if st.button("Enregistrer les modifications", key=f"btn_dlg_save_edit_{user_id}", type="primary", use_container_width=True):
            messages = []
            errors = []

            if new_role != current_role:
                result = update_user_role(user_id, new_role)
                if result['success']:
                    messages.append(f"Rôle modifié en '{new_role}'")
                else:
                    errors.append(result['error'])

            if new_lab != (current_lab or ""):
                result = update_user_laboratoire(user_id, new_lab if new_lab else None)
                if result['success']:
                    messages.append("Laboratoire mis à jour")
                else:
                    errors.append(result['error'])

            if new_password:
                if new_password != confirm_password:
                    st.error("Les mots de passe ne correspondent pas.")
                    return
                if len(new_password) < 4:
                    st.error("Le mot de passe doit contenir au moins 4 caractères.")
                    return
                result = update_user_password(user_id, new_password)
                if result['success']:
                    messages.append("Mot de passe réinitialisé")
                else:
                    errors.append(result['error'])

            if errors:
                st.session_state.admin_action_msg = ('error', " | ".join(errors))
            elif messages:
                st.session_state.admin_action_msg = ('success', f"{user_data['username']} : {', '.join(messages)}")
            st.rerun()

    users = get_all_users()

    if not users:
        st.info("Aucun utilisateur trouvé.")
        return

    current_user_id = st.session_state.get('user', {}).get('id')

    all_labs = sorted(set(u.get('laboratoire') or '' for u in users if u.get('laboratoire')))

    col_search, col_role, col_status, col_lab = st.columns([3, 1.5, 1.5, 2])
    with col_search:
        search_query = st.text_input("Rechercher", placeholder="Nom, email ou utilisateur...", key="admin_search_users", label_visibility="collapsed")
    with col_role:
        filter_role = st.selectbox("Rôle", ["Tous", "Admin", "User", "Manager"], key="admin_filter_role", label_visibility="collapsed")
    with col_status:
        filter_status = st.selectbox("Statut", ["Tous", "Actif", "Inactif"], key="admin_filter_status", label_visibility="collapsed")
    with col_lab:
        filter_lab = st.selectbox("Laboratoire", ["Tous"] + all_labs, key="admin_filter_lab", label_visibility="collapsed")

    filtered_users = users
    if search_query:
        q = search_query.lower()
        filtered_users = [u for u in filtered_users if
                          q in (u.get('username', '') or '').lower() or
                          q in (u.get('email', '') or '').lower() or
                          q in (u.get('first_name', '') or '').lower() or
                          q in (u.get('last_name', '') or '').lower() or
                          q in f"{(u.get('first_name', '') or '')} {(u.get('last_name', '') or '')}".lower()]
    if filter_role != "Tous":
        filtered_users = [u for u in filtered_users if u.get('role', '').lower() == filter_role.lower()]
    if filter_status != "Tous":
        is_active = filter_status == "Actif"
        filtered_users = [u for u in filtered_users if u.get('is_active', True) == is_active]
    if filter_lab != "Tous":
        filtered_users = [u for u in filtered_users if (u.get('laboratoire') or '') == filter_lab]

    col_count, col_add_btn = st.columns([4, 1])
    with col_count:
        st.markdown(f"""
        <div style="display: flex; align-items: center; gap: 0.75rem; margin: 0.5rem 0;">
            <span style="font-size: 1.1rem; font-weight: 600; color: #1a1a1a;">{len(filtered_users)} utilisateur(s)</span>
            {f'<span style="background: #EEF2FF; color: #4F46E5; padding: 2px 10px; border-radius: 12px; font-size: 0.8rem;">filtrés sur {len(users)}</span>' if len(filtered_users) != len(users) else ''}
        </div>
        """, unsafe_allow_html=True)
    with col_add_btn:
        if st.button("+ Ajouter", key="btn_open_add_user", type="primary", use_container_width=True):
            show_add_user_dialog()

    for idx, user in enumerate(filtered_users):
        is_current = user['id'] == current_user_id
        is_active = user.get('is_active', True)
        role = user.get('role', 'user')
        full_name = f"{user.get('first_name', '') or ''} {user.get('last_name', '') or ''}".strip() or "—"
        last_login = user.get('last_login')
        if last_login:
            last_login_str = last_login.strftime('%d/%m/%Y %H:%M') if hasattr(last_login, 'strftime') else str(last_login)
        else:
            last_login_str = "Jamais"
        lab = user.get('laboratoire') or "—"

        role_badge_color = "#4F46E5" if role == 'admin' else "#0891B2"
        role_badge_bg = "#EEF2FF" if role == 'admin' else "#ECFEFF"
        status_badge_color = "#16A34A" if is_active else "#DC2626"
        status_badge_bg = "#F0FDF4" if is_active else "#FEF2F2"
        status_text = "Actif" if is_active else "Inactif"
        card_border = "#E5E7EB" if is_active else "#FCA5A5"
        card_opacity = "1" if is_active else "0.75"

        st.markdown(f"""
        <div style="background: #fff; border: 1px solid {card_border}; border-radius: 12px; padding: 1rem 1.25rem; margin-bottom: 0.6rem; opacity: {card_opacity}; box-shadow: 0 1px 3px rgba(0,0,0,0.04);">
            <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.5rem;">
                <div style="display: flex; align-items: center; gap: 0.75rem; flex: 1; min-width: 200px;">
                    <div style="width: 40px; height: 40px; border-radius: 50%; background: linear-gradient(135deg, {role_badge_bg}, {'#C7D2FE' if role == 'admin' else '#A5F3FC'}); display: flex; align-items: center; justify-content: center; font-weight: 700; color: {role_badge_color}; font-size: 1rem; flex-shrink: 0;">
                        {user.get('username', '?')[0].upper()}
                    </div>
                    <div>
                        <div style="font-weight: 600; color: #111827; font-size: 0.95rem;">
                            {user.get('username', '')} {' <span style="font-size: 0.75rem; color: #6B7280;">(vous)</span>' if is_current else ''}
                        </div>
                        <div style="color: #6B7280; font-size: 0.82rem;">{full_name} &middot; {user.get('email', '')}</div>
                    </div>
                </div>
                <div style="display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap;">
                    <span style="background: {role_badge_bg}; color: {role_badge_color}; padding: 3px 10px; border-radius: 10px; font-size: 0.75rem; font-weight: 600; text-transform: uppercase;">{role}</span>
                    <span style="background: {status_badge_bg}; color: {status_badge_color}; padding: 3px 10px; border-radius: 10px; font-size: 0.75rem; font-weight: 600;">{status_text}</span>
                    <span style="color: #9CA3AF; font-size: 0.78rem;">Lab: {lab}</span>
                    <span style="color: #9CA3AF; font-size: 0.78rem;">&middot; Connexion: {last_login_str}</span>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        col_edit, col_toggle, col_delete, col_spacer = st.columns([0.7, 0.9, 0.8, 5])
        with col_edit:
            if st.button("Modifier", key=f"btn_edit_user_{user['id']}_{idx}"):
                show_edit_user_dialog(user)
        with col_toggle:
            if is_current:
                st.button("—", key=f"btn_toggle_disabled_{user['id']}_{idx}", disabled=True)
            else:
                toggle_label = "Désactiver" if is_active else "Activer"
                if st.button(toggle_label, key=f"btn_toggle_user_{user['id']}_{idx}"):
                    if is_active:
                        result = deactivate_user(user['id'])
                        if result['success']:
                            st.session_state.admin_action_msg = ('success', f"Compte '{user['username']}' désactivé.")
                        else:
                            st.session_state.admin_action_msg = ('error', result['error'])
                    else:
                        result = activate_user(user['id'])
                        if result['success']:
                            st.session_state.admin_action_msg = ('success', f"Compte '{user['username']}' activé.")
                        else:
                            st.session_state.admin_action_msg = ('error', result['error'])
                    st.rerun()
        with col_delete:
            if is_current:
                st.button("—", key=f"btn_del_disabled_{user['id']}_{idx}", disabled=True)
            else:
                if st.button("Supprimer", key=f"btn_del_user_{user['id']}_{idx}"):
                    st.session_state[f'confirm_delete_{user["id"]}'] = True
                    st.rerun()

        if st.session_state.get(f'confirm_delete_{user["id"]}', False):
            st.warning(f"Confirmer la suppression de **{user['username']}** ? Cette action est irréversible.")
            ca, cb, cc = st.columns([0.8, 0.8, 5])
            with ca:
                if st.button("Oui, supprimer", key=f"btn_confirm_del_{user['id']}_{idx}", type="primary"):
                    result = delete_user(user['id'], current_user_id=current_user_id)
                    if result['success']:
                        st.session_state.admin_action_msg = ('success', f"Utilisateur '{user['username']}' supprimé.")
                    else:
                        st.session_state.admin_action_msg = ('error', result['error'])
                    del st.session_state[f'confirm_delete_{user["id"]}']
                    st.rerun()
            with cb:
                if st.button("Annuler", key=f"btn_cancel_del_{user['id']}_{idx}"):
                    del st.session_state[f'confirm_delete_{user["id"]}']
                    st.rerun()


@st.fragment
def display_repartition_delegue_clustering(app):
    """Affiche l'interface pour la répartition des délégués avec clustering K-means"""

    if 'delegue_sub_view' not in st.session_state:
        st.session_state.delegue_sub_view = 'repartition'
    
    # Initialiser les valeurs des inputs dans session_state (avant tout changement de vue)
    if 'visites_jour_clustering' not in st.session_state:
        st.session_state.visites_jour_clustering = 10.0
    if 'produits_visite_clustering' not in st.session_state:
        st.session_state.produits_visite_clustering = 30.0
    if 'taux_conversion_clustering' not in st.session_state:
        st.session_state.taux_conversion_clustering = 100.0
    if 'jours_travail_an_clustering' not in st.session_state:
        st.session_state.jours_travail_an_clustering = 220
    if 'objectif_total_clustering' not in st.session_state:
        st.session_state.objectif_total_clustering = 0
    if 'nombre_delegues_total_clustering' not in st.session_state:
        st.session_state.nombre_delegues_total_clustering = 0

    product_code = ""
    product_name = ""
    product_display = "Non défini"
    if 'selected_product' in st.session_state and st.session_state.selected_product:
        product_code = st.session_state.selected_product.get('Code PCT', '')
        product_name = (st.session_state.selected_product.get('Désignation', '')
                        or st.session_state.selected_product.get('Produit', '')
                        or '').strip()
        if not product_name and hasattr(app, 'data_n2') and app.data_n2 is not None and not app.data_n2.empty:
            try:
                if 'Produit' in app.data_n2.columns and 'Code PCT' in app.data_n2.columns:
                    _pi = app.data_n2[app.data_n2['Code PCT'].astype(str).str.strip() == str(product_code).strip()]
                    if not _pi.empty:
                        product_name = str(_pi['Produit'].iloc[0]).strip()
            except Exception:
                pass
        product_display = product_name or product_code or "Non défini"

    # Vérifier si on est en mode multi-produit
    is_multi_product = len(st.session_state.get('selected_products', [])) > 1
    
    if is_multi_product:
        # Mode multi-produit: pas de nom de produit dans le titre
        st.markdown("""
        <div class="delegue-header-animate" style="background: linear-gradient(135deg, #F8FAFC 0%, #FFFFFF 100%); padding: 1.5rem 2rem; border-radius: 16px; margin-bottom: 1.5rem; box-shadow: 0 4px 20px rgba(0,0,0,0.05); border: 1px solid #E5E5E5; text-align: center;">
            <div style="color: #64748B; font-size: 0.85rem; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 0.5rem;">Stratégie de répartition</div>
            <div class="dark-text" style="font-size: 1.8rem; font-weight: 700; margin-bottom: 0.25rem;">Délégués Médicaux</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        # Mode mono-produit: afficher le nom du produit
        st.markdown(f"""
        <div class="delegue-header-animate" style="background: linear-gradient(135deg, #F8FAFC 0%, #FFFFFF 100%); padding: 1.5rem 2rem; border-radius: 16px; margin-bottom: 1.5rem; box-shadow: 0 4px 20px rgba(0,0,0,0.05); border: 1px solid #E5E5E5; text-align: center;">
            <div style="color: #64748B; font-size: 0.85rem; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 0.5rem;">Stratégie de répartition</div>
            <div class="dark-text" style="font-size: 1.8rem; font-weight: 700; margin-bottom: 0.25rem;">Délégués Médicaux</div>
            <div style="color: #3B82F6; font-size: 1rem;">Produit : {product_display}</div>
        </div>
        """, unsafe_allow_html=True)
    
    col_nav1, col_nav2 = st.columns(2)
    with col_nav1:
        if st.button("Répartition", 
                     use_container_width=True,
                     type="primary" if st.session_state.delegue_sub_view == 'repartition' else "secondary",
                     key="btn_sub_repartition"):
            st.session_state.delegue_sub_view = 'repartition'
            st.rerun(scope="fragment")
    with col_nav2:
        if st.button("Visualisations", 
                     use_container_width=True,
                     type="primary" if st.session_state.delegue_sub_view == 'visualisations' else "secondary",
                     key="btn_sub_visualisations"):
            st.session_state.delegue_sub_view = 'visualisations'
            st.rerun(scope="fragment")
    
    st.markdown("<div style='height: 1rem;'></div>", unsafe_allow_html=True)
    
    if st.session_state.delegue_sub_view == 'visualisations':
        delegue_results = st.session_state.get('last_delegue_results')
        if not delegue_results:
            product_code = st.session_state.selected_product.get('Code PCT', 'unknown') if st.session_state.get('selected_product') else 'unknown'
            cached = st.session_state.get('clustering_results', {}).get(product_code)
            if cached:
                delegue_results = cached.get('resultats')
                st.session_state.last_delegue_results = delegue_results
        
        if delegue_results and 'delegue_calculator' in st.session_state:
            display_visualisations(delegue_results, st.session_state.delegue_calculator)
        else:
            st.warning("Veuillez d'abord calculer la répartition des délégués dans l'onglet 'Répartition'.")
        return

    _DC = _get_delegue_calculator()
    if not DELEGUE_MODULE_AVAILABLE or _DC is None:
        st.error("Le module de répartition des délégués n'est pas disponible.")
        st.info(
            "Assurez-vous que le fichier delegue.py est dans le même répertoire."
        )
        return

    if 'delegue_calculator' not in st.session_state or st.session_state.get(
            'delegue_calculator_app_id') != id(app):
        st.session_state.delegue_calculator = _DC(app)
        st.session_state.delegue_calculator_app_id = id(app)
    delegue_calculator = st.session_state.delegue_calculator

    # Section des paramètres avec carte stylée
    st.markdown("""
    <div style="background: #FFFFFF; padding: 1.25rem 1.5rem; border-radius: 12px; margin-bottom: 1rem; border: 1px solid #E5E5E5; box-shadow: 0 2px 8px rgba(0,0,0,0.04);">
        <div style="display: flex; align-items: center; margin-bottom: 1rem;">
            <div style="width: 4px; height: 20px; background: #DC2626; border-radius: 2px; margin-right: 10px;"></div>
            <span class="dark-text" style="font-weight: 600; font-size: 1rem;">Paramètres de calcul</span>
        </div>
    </div>
    """,
                unsafe_allow_html=True)

    # Ligne 1 : 2 inputs
    col1, col2 = st.columns(2)

    with col1:
        jours_travail_an = st.number_input(
            "Nombre de jours ouvrables par an",
            min_value=0,
            max_value=365,
            step=10,
            help="Nombre de jours ouvrables par an",
            key="jours_travail_an_clustering")

    with col2:
        visites_par_jour = st.number_input(
            "Nombre de visites par jour",
            min_value=5.0,
            max_value=15.0,
            step=0.5,
            help="Nombre moyen de visites par délégué par jour (5-15)",
            key="visites_jour_clustering")

    # Ligne 2 : 2 inputs
    col3, col4 = st.columns(2)

    with col3:
        produits_par_visite = st.number_input(
            "Nombre d'unités par visite réussie",
            min_value=0.0,
            max_value=1000.0,
            step=1.0,
            help="Nombre d'unités par visite réussie (max 1000)",
            key="produits_visite_clustering")

    with col4:
        taux_conversion = st.number_input(
            "Taux de conversion",
            min_value=1.0,
            max_value=100.0,
            step=1.0,
            help="Pourcentage des visites générant une vente",
            key="taux_conversion_clustering")

    # Options avancées avec bouton Recommendation
    if 'show_recommendation' not in st.session_state:
        st.session_state.show_recommendation = False

    # Options avancées avec bouton Recommendation intégré
    col_options, col_btn = st.columns([4, 1])
    with col_options:
        st.markdown("""
        <div style="background: #FAFAFA; padding: 1rem 1.5rem; border-radius: 12px; margin: 0.5rem 0; border: 1px solid #E5E5E5; display: flex; align-items: center;">
            <div style="width: 4px; height: 20px; background: #991B1B; border-radius: 2px; margin-right: 10px;"></div>
            <span class="dark-text" style="font-weight: 600; font-size: 0.95rem;">Options avancées</span>
        </div>
        """,
                    unsafe_allow_html=True)
    with col_btn:
        st.markdown("""
        <style>
        .reco-btn-container button {
            background: #6B7280 !important;
            color: white !important;
            font-size: 0.75rem !important;
            padding: 0.4rem 0.6rem !important;
            border: none !important;
            border-radius: 6px !important;
            margin-top: 0.5rem !important;
        }
        .reco-btn-container button:hover {
            background: #4B5563 !important;
        }
        </style>
        <div class="reco-btn-container">
        """,
                    unsafe_allow_html=True)
        if st.button("Recommendation",
                     key="btn_recommendation",
                     help="Afficher les options de recommendation"):
            st.session_state.show_recommendation = not st.session_state.show_recommendation
            st.rerun(scope="fragment")
        st.markdown("</div>", unsafe_allow_html=True)

    # Colonnes pour les options - avec ou sans Délégués N-1
    if st.session_state.show_recommendation:
        col_opt1, col_opt2, col_opt3 = st.columns(3)
    else:
        col_opt1, col_opt2 = st.columns(2)
        col_opt3 = None

    with col_opt1:
        objectif_total = st.number_input(
            "Objectif total manuel",
            min_value=0,
            max_value=100000000,
            step=1000,
            help="Laissez 0 pour calcul automatique",
            key="objectif_total_clustering")

    with col_opt2:
        nombre_delegues_total = st.number_input(
            "Nombre de délégués fixe",
            min_value=0,
            max_value=100,
            step=1,
            help="Laissez 0 pour calcul automatique. Les objectifs s'ajusteront proportionnellement.",
            key="nombre_delegues_total_clustering")

    # Coefficient de mutualisation (m) par produit - dans un expander
    # Initialiser le dictionnaire des coefficients par produit
    if 'coefficients_mutualisation' not in st.session_state:
        st.session_state.coefficients_mutualisation = {}
    
    # Récupérer les produits sélectionnés
    selected_products_list = st.session_state.get('selected_products', [])
    if not selected_products_list and st.session_state.get('selected_product'):
        selected_products_list = [st.session_state.selected_product]
    
    # Initialiser le coefficient par défaut
    coefficient_mutualisation = 1.0
    
    # Afficher la section coefficient de mutualisation uniquement en mode multi-produit
    if len(selected_products_list) > 1:
        with st.expander("Coefficient de mutualisation (m)", expanded=False):
            st.markdown("""
            <div style="background: linear-gradient(135deg, #F0F9FF 0%, #E0F2FE 100%); padding: 12px 16px; border-radius: 8px; margin-bottom: 15px; border-left: 4px solid #0284C7;">
                <div style="color: #0C4A6E; font-size: 0.85rem;">
                    Ce coefficient ajuste le nombre de délégués en tenant compte qu'une même visite sert plusieurs produits.<br>
                    <strong>m = 1.0</strong> : Produit exclusif (100% de la visite)<br>
                    <strong>m = 0.5</strong> : Produit partagé (50% de la visite)<br>
                    <strong>m = 0.3</strong> : Produit mutualisé (30% de la visite)
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            # Créer un input pour chaque produit
            for product in selected_products_list:
                product_code = product.get('Code PCT', 'unknown')
                # Utiliser le nom complet du produit (Désignation)
                product_name = product.get('Désignation', product.get('DCI', product_code))
                
                col_prod, col_coef = st.columns([3, 1])
                with col_prod:
                    st.markdown(f"<div style='padding-top: 8px; font-weight: 500;'>{product_name}</div>", unsafe_allow_html=True)
                with col_coef:
                    coef_value = st.session_state.coefficients_mutualisation.get(product_code, 1.0)
                    new_coef = st.number_input(
                        f"m",
                        min_value=0.1,
                        max_value=1.0,
                        value=coef_value,
                        step=0.05,
                        key=f"coef_m_{product_code}",
                        label_visibility="collapsed"
                    )
                    st.session_state.coefficients_mutualisation[product_code] = new_coef
    
    # Recalculer le coefficient moyen après l'expander (pour le calcul)
    if selected_products_list:
        total_coef = sum(st.session_state.coefficients_mutualisation.get(p.get('Code PCT', 'unknown'), 1.0) for p in selected_products_list)
        coefficient_mutualisation = total_coef / len(selected_products_list)
    else:
        coefficient_mutualisation = 1.0

    if st.session_state.show_recommendation and col_opt3:
        with col_opt3:
            nombre_delegues_n1 = st.number_input(
                "Nombre de délégués N-1",
                min_value=0,
                max_value=100,
                value=0,
                step=1,
                help=
                "Nombre de délégués de l'année précédente pour calculer la recommendation",
                key="nombre_delegues_n1_clustering")

        # Calcul et affichage de la recommendation si N-1 est renseigné
        if nombre_delegues_n1 > 0 and visites_par_jour > 0 and jours_travail_an > 0 and taux_conversion > 0:
            # Récupérer la Quantité N selon le mode (mono ou multi-produit)
            all_products_results = st.session_state.get('all_products_results', {})
            is_multi_product = len(all_products_results) > 1
            
            if is_multi_product:
                # Mode multi-produit: somme des quantités N de tous les produits
                quantite_n = sum(
                    prod_data.get('quantite_n', 0) 
                    for prod_data in all_products_results.values()
                )
            else:
                # Mode mono-produit: quantité N du produit unique
                quantite_n = st.session_state.get('quantite_n_produit', 0)

            if quantite_n > 0:
                taux_conv_decimal = taux_conversion / 100.0
                import math
                
                if is_multi_product:
                    # Mode multi-produit: produits_par_visite = Σ(m_i × Objectif_i) / (D × visites_par_jour × jours_travail_an × taux_conversion)
                    somme_m_objectif = 0
                    for prod_code, prod_data in all_products_results.items():
                        q_n = prod_data.get('quantite_n', 0)
                        m_i = st.session_state.coefficients_mutualisation.get(prod_code, 1.0)
                        somme_m_objectif += m_i * q_n
                    
                    if somme_m_objectif > 0:
                        denominateur = nombre_delegues_n1 * visites_par_jour * jours_travail_an * taux_conv_decimal
                        unites_recommandees_brut = somme_m_objectif / denominateur
                        total_unites = math.ceil(unites_recommandees_brut)
                        
                        st.markdown(f"""
                        <div style="background: linear-gradient(135deg, #ECFDF5 0%, #D1FAE5 100%); padding: 12px 16px; border-radius: 8px; margin-top: 10px; border-left: 4px solid #10B981;">
                            <div style="font-weight: 600; color: #065F46; margin-bottom: 5px;">Recommendation calculée</div>
                            <div style="color: #047857; font-size: 0.95rem;">
                                <strong>Nombre d'unités par visite réussie recommandé :</strong> {total_unites:.0f} unités
                            </div>
                        </div>
                        """,
                                    unsafe_allow_html=True)
                else:
                    # Mode mono-produit: Unités/visite = Quantité N / (Délégués N-1 × Visites/jour × Jours travaillés × Taux conversion)
                    unites_recommandees_brut = quantite_n / (
                        nombre_delegues_n1 * visites_par_jour * jours_travail_an *
                        taux_conv_decimal)
                    unites_recommandees = math.ceil(unites_recommandees_brut)

                    st.markdown(f"""
                    <div style="background: linear-gradient(135deg, #ECFDF5 0%, #D1FAE5 100%); padding: 12px 16px; border-radius: 8px; margin-top: 10px; border-left: 4px solid #10B981;">
                        <div style="font-weight: 600; color: #065F46; margin-bottom: 5px;">Recommendation calculée</div>
                        <div style="color: #047857; font-size: 0.95rem;">
                            <strong>Nombre d'unités par visite réussie recommandé :</strong> {unites_recommandees:.0f} unités
                        </div>
                    </div>
                    """,
                                unsafe_allow_html=True)

    # Option avancée: répartition manuelle par région
    delegues_par_region = None
    with st.expander("Répartition manuelle par région", expanded=False):
        st.markdown("""
        <div style="background: linear-gradient(135deg, #FEF2F2 0%, #FFF5F5 100%); padding: 12px 16px; border-radius: 8px; margin-bottom: 15px; border-left: 4px solid #DC2626;">
            <span style="font-size: 0.9rem; color: #991B1B;">Spécifiez le nombre de délégués par région pour remplacer le calcul automatique.</span>
        </div>
        """,
                    unsafe_allow_html=True)

        col_r1, col_r2, col_r3 = st.columns(3)

        with col_r1:
            delegues_nord = st.number_input(
                "Délégués Nord",
                min_value=0,
                max_value=50,
                step=1,
                help="Nombre de délégués pour la région Nord",
                key="delegues_nord_input")

        with col_r2:
            delegues_centre = st.number_input(
                "Délégués Centre",
                min_value=0,
                max_value=50,
                step=1,
                help="Nombre de délégués pour la région Centre",
                key="delegues_centre_input")

        with col_r3:
            delegues_sud = st.number_input(
                "Délégués Sud",
                min_value=0,
                max_value=50,
                step=1,
                help="Nombre de délégués pour la région Sud",
                key="delegues_sud_input")

        # Stocker les valeurs si au moins une est renseignée
        if delegues_nord > 0 or delegues_centre > 0 or delegues_sud > 0:
            delegues_par_region = {
                'Nord': delegues_nord,
                'Centre': delegues_centre,
                'Sud': delegues_sud
            }
            total_manuel = delegues_nord + delegues_centre + delegues_sud
            st.info(
                f"Total délégués par région: **{total_manuel}** (Nord: {delegues_nord}, Centre: {delegues_centre}, Sud: {delegues_sud})"
            )

    with st.expander("Modifier les régions des secteurs", expanded=False):
        st.markdown("""
        <div style="background: linear-gradient(135deg, #EFF6FF 0%, #DBEAFE 100%); padding: 12px 16px; border-radius: 8px; margin-bottom: 15px; border-left: 4px solid #2563EB;">
            <span style="font-size: 0.9rem; color: #1E3A8A;">Réaffectez chaque secteur à la région souhaitée. Les modifications seront appliquées au prochain calcul de répartition.</span>
        </div>
        """, unsafe_allow_html=True)

        default_mapping = {}
        for _region, _secteurs in delegue_calculator.SECTEURS_PAR_REGION.items():
            for _s in _secteurs:
                default_mapping[_s] = _region

        if 'custom_secteurs_par_region_map' in st.session_state:
            for _s, _r in st.session_state.custom_secteurs_par_region_map.items():
                if _s in default_mapping:
                    default_mapping[_s] = _r

        df_secteurs_region = pd.DataFrame([
            {'Secteur': s, 'Région': r} for s, r in sorted(default_mapping.items())
        ])

        edited_df = st.data_editor(
            df_secteurs_region,
            column_config={
                'Secteur': st.column_config.TextColumn('Secteur', disabled=True, width='medium'),
                'Région': st.column_config.SelectboxColumn(
                    'Région', options=['Nord', 'Centre', 'Sud'], required=True, width='small'
                ),
            },
            hide_index=True,
            use_container_width=True,
            height=400,
            key='editor_secteurs_region',
        )

        new_map = dict(zip(edited_df['Secteur'].tolist(), edited_df['Région'].tolist()))
        counts = {'Nord': 0, 'Centre': 0, 'Sud': 0}
        for _r in new_map.values():
            if _r in counts:
                counts[_r] += 1

        col_n, col_c, col_s = st.columns(3)
        with col_n:
            st.metric("Secteurs Nord", counts['Nord'])
        with col_c:
            st.metric("Secteurs Centre", counts['Centre'])
        with col_s:
            st.metric("Secteurs Sud", counts['Sud'])

        col_save, col_reset = st.columns([1, 1])
        with col_save:
            if st.button("Appliquer les modifications", type="primary", use_container_width=True, key='btn_save_regions'):
                st.session_state.custom_secteurs_par_region_map = new_map
                if 'repartition_cache' in st.session_state:
                    st.session_state.repartition_cache = {}
                st.success("Configuration des régions enregistrée. Lancez le calcul pour l'appliquer.")
                st.rerun()
        with col_reset:
            if st.button("Réinitialiser", use_container_width=True, key='btn_reset_regions'):
                if 'custom_secteurs_par_region_map' in st.session_state:
                    del st.session_state.custom_secteurs_par_region_map
                if 'repartition_cache' in st.session_state:
                    st.session_state.repartition_cache = {}
                st.info("Configuration réinitialisée à la valeur par défaut.")
                st.rerun()

        if 'custom_secteurs_par_region_map' in st.session_state:
            st.caption("Configuration personnalisée active.")

    if 'custom_secteurs_par_region_map' in st.session_state:
        _custom_map = st.session_state.custom_secteurs_par_region_map
        _new_spr = {'Nord': [], 'Centre': [], 'Sud': []}
        for _sect, _reg in _custom_map.items():
            if _reg in _new_spr:
                _new_spr[_reg].append(_sect)
        for _reg in _new_spr:
            _new_spr[_reg].sort()
        delegue_calculator.SECTEURS_PAR_REGION = _new_spr

        _new_gov = {'Nord': set(), 'Centre': set(), 'Sud': set()}
        import re as _re
        for _reg, _secs in _new_spr.items():
            for _s in _secs:
                _m = _re.match(r'^(.+?)\s*\d+$', str(_s).strip())
                _gov = _m.group(1).strip() if _m else str(_s).strip()
                _new_gov[_reg].add(_gov)
        delegue_calculator.GOUVERNORATS_SECTEURS = {k: sorted(v) for k, v in _new_gov.items()}

    st.markdown("---")

    # Vérifier la présence de la matrice de distance
    if delegue_calculator.distance_matrix is None:
        st.warning("""
        ⚠️ **Matrice de distance non trouvée**
        

        """)

    # Afficher les secteurs retirés si disponibles
    if hasattr(app, 'results') and app.product_code in app.results:
        result = app.results[app.product_code]
        secteurs_retires = result.get('secteurs_retires', [])

        if secteurs_retires:
            st.markdown(f"""
            <div class="danger-box">
                <strong>Secteurs retirés détectés ({len(secteurs_retires)})</strong><br>
                Ces secteurs ne seront pas inclus dans la répartition des délégués.
            </div>
            """,
                        unsafe_allow_html=True)

            with st.expander("Voir les secteurs retirés"):
                for secteur in secteurs_retires:
                    st.write(f"- {secteur}")

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        calculer_clustering = st.button("CALCULER LA RÉPARTITION",
                                        type="primary",
                                        use_container_width=True,
                                        key="btn_calcul_clustering")

    # Vérifier si on a des résultats en cache pour ce produit
    product_code = st.session_state.selected_product.get(
        'Code PCT',
        'unknown') if st.session_state.get('selected_product') else 'unknown'
    cached_results = st.session_state.get('clustering_results',
                                          {}).get(product_code)

    if calculer_clustering:
        if visites_par_jour == 0:
            st.error("Le nombre de visites par jour doit être supérieur à 0")
            return

        if produits_par_visite == 0:
            st.error(
                "Le nombre de produits par visite doit être supérieur à 0")
            return

        if jours_travail_an == 0:
            st.error("Le nombre de jours de travail par an ne peut pas être 0")
            return

        objectif_total_param = None if objectif_total == 0 else objectif_total
        nombre_delegues_total_param = None if nombre_delegues_total == 0 else int(
            nombre_delegues_total)

        import hashlib, json as _json
        cache_input = {
            'product_code': product_code,
            'visites_par_jour': visites_par_jour,
            'produits_par_visite': produits_par_visite,
            'jours_travail_an': jours_travail_an,
            'objectif_total': objectif_total_param,
            'nombre_delegues_total': nombre_delegues_total_param,
            'taux_conversion': taux_conversion,
            'delegues_par_region': delegues_par_region,
            'coefficients_mutualisation': st.session_state.coefficients_mutualisation,
        }
        cache_key = hashlib.md5(_json.dumps(cache_input, sort_keys=True, default=str).encode()).hexdigest()

        if 'repartition_cache' not in st.session_state:
            st.session_state.repartition_cache = {}

        if cache_key in st.session_state.repartition_cache:
            cached = st.session_state.repartition_cache[cache_key]
            resultats = cached['resultats']
            secteurs_retires = cached['secteurs_retires']

            if 'clustering_results' not in st.session_state:
                st.session_state.clustering_results = {}
            st.session_state.clustering_results[product_code] = cached
            st.session_state.last_delegue_results = resultats
            st.session_state.delegue_sub_view = 'repartition'

            afficher_resultats_clustering(resultats, secteurs_retires)
        else:
            if objectif_total_param:
                st.info(
                    f"Utilisation de l'objectif total manuel: {objectif_total_param:,.0f} unités"
                )

            progress_bar = st.progress(0)
            status_text = st.empty()

            try:
                status_text.text("Préparation des données...")
                progress_bar.progress(10)

                secteurs_retires = []
                if hasattr(app, 'results') and app.product_code in app.results:
                    result = app.results[app.product_code]
                    secteurs_retires = result.get('secteurs_retires', [])

                delegue_calculator.secteurs_retires = secteurs_retires

                all_products_results = st.session_state.get('all_products_results', {})
                if all_products_results:
                    secteurs_retires_par_produit = st.session_state.get('secteurs_retires_par_produit', {})
                    delegue_calculator.set_multi_product_objectives(all_products_results, secteurs_retires_par_produit)
                    if len(all_products_results) > 1:
                        status_text.text("Mode multi-produits: calcul de la somme des objectifs...")

                status_text.text("Calcul de la répartition K-means...")
                progress_bar.progress(30)

                resultats = delegue_calculator.calculate_delegate_distribution_with_proximity_grouping(
                    visites_par_jour=visites_par_jour,
                    produits_par_visite=produits_par_visite,
                    jours_travail_an=jours_travail_an,
                    objectif_total=objectif_total_param,
                    nombre_delegues_total=nombre_delegues_total_param,
                    taux_conversion=taux_conversion / 100.0,
                    delegues_par_region=delegues_par_region,
                    coefficients_mutualisation=st.session_state.coefficients_mutualisation)

                progress_bar.progress(90)

                if 'erreur' in resultats:
                    st.error(f"Erreur: {resultats['erreur']}")
                    progress_bar.empty()
                    status_text.empty()
                    return

                status_text.text("Affichage des résultats...")
                progress_bar.progress(100)

                cached_entry = {
                    'resultats': resultats,
                    'secteurs_retires': secteurs_retires
                }
                st.session_state.repartition_cache[cache_key] = cached_entry

                if 'clustering_results' not in st.session_state:
                    st.session_state.clustering_results = {}
                st.session_state.clustering_results[product_code] = cached_entry
                st.session_state.last_delegue_results = resultats
                st.session_state.delegue_sub_view = 'repartition'

                progress_bar.empty()
                status_text.empty()

                afficher_resultats_clustering(resultats, secteurs_retires)
            except Exception as e:
                progress_bar.empty()
                status_text.empty()
                st.error(f"Erreur lors du calcul: {str(e)}")
    elif cached_results:
        # Afficher les résultats en cache si on navigue vers cette page
        st.session_state.last_delegue_results = cached_results['resultats']
        afficher_resultats_clustering(cached_results['resultats'],
                                      cached_results['secteurs_retires'])


def afficher_resultats_clustering(resultats, secteurs_retires=None):
    """Affiche les résultats du clustering K-means"""

    params = resultats['parametres']
    regions = resultats['regions']
    stats_globales = resultats['statistiques_globales']

    objectif_source = params.get('objectif_source', 'Calcul automatique')
    objectif_saisi = params.get('objectif_total_saisi', False)

    if objectif_saisi:
        st.markdown(f"""
        <div class="warning-box">
            <strong>Objectif manuel utilisé :</strong> L'objectif total a été saisi manuellement
        </div>
        """,
                    unsafe_allow_html=True)

    # Afficher le nom du produit analysé
    product_name = "Produit"
    product_code = ""
    if 'selected_product' in st.session_state and st.session_state.selected_product:
        product_code = st.session_state.selected_product.get('Code PCT', '')
        product_name = st.session_state.selected_product.get(
            'Désignation', '') or st.session_state.selected_product.get(
                'Produit', '')
        if product_name and product_code:
            product_display = f"{product_name} ({product_code})"
        else:
            product_display = product_name or product_code or "Non défini"
    else:
        product_display = params.get('product_code', 'Produit')

    # Calcul de l'objectif total
    total_objectif = sum(
        region_data.get('allocation_region', {}).get('objectif_total', 0)
        for region_data in regions.values())

    # Cartes de métriques principales - Toutes avec bordure grise et nombres en noir
    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown(f"""
        <div class="metric-card-animate" style="background: #FFFFFF; padding: 1.25rem; border-radius: 12px; text-align: center; box-shadow: 0 2px 10px rgba(0,0,0,0.05); border: 2px solid #E5E5E5;">
            <div style="color: #64748B; font-size: 0.85rem; margin-bottom: 0.5rem;">Délégués totaux</div>
            <div style="color: #000000; font-size: 2.2rem; font-weight: 700;">{stats_globales['total_delegues']}</div>
        </div>
        """,
                    unsafe_allow_html=True)

    with col2:
        st.markdown(f"""
        <div class="metric-card-animate" style="background: #FFFFFF; padding: 1.25rem; border-radius: 12px; text-align: center; box-shadow: 0 2px 10px rgba(0,0,0,0.05); border: 2px solid #E5E5E5;">
            <div style="color: #64748B; font-size: 0.85rem; margin-bottom: 0.5rem;">Régions</div>
            <div style="color: #000000; font-size: 2.2rem; font-weight: 700;">{stats_globales['regions_traitees']}</div>
        </div>
        """,
                    unsafe_allow_html=True)

    with col3:
        st.markdown(f"""
        <div class="metric-card-animate" style="background: #FFFFFF; padding: 1.25rem; border-radius: 12px; text-align: center; box-shadow: 0 2px 10px rgba(0,0,0,0.05); border: 2px solid #E5E5E5;">
            <div style="color: #64748B; font-size: 0.85rem; margin-bottom: 0.5rem;">Objectif total</div>
            <div style="color: #000000; font-size: 2.2rem; font-weight: 700;">{total_objectif:,.0f}</div>
        </div>
        """,
                    unsafe_allow_html=True)

    st.markdown("<div style='height: 1.5rem;'></div>", unsafe_allow_html=True)

    _extract_data_for_delegue = []
    year_n_raw = st.session_state.get('detected_year_n', 'N')
    try:
        _year_n_extract = int(year_n_raw)
        _year_n1_extract = _year_n_extract + 1
    except (ValueError, TypeError):
        _year_n_extract = 'N'
        _year_n1_extract = 'N+1'

    _delegue_counter_extract = {}
    for region_nom, region_data in regions.items():
        repartition = region_data.get('repartition_delegues', {})
        region_type = ""
        if "Nord" in region_nom:
            region_type = "nord"
        elif "Centre" in region_nom:
            region_type = "centre"
        elif "Sud" in region_nom:
            region_type = "sud"
        else:
            region_type = "region"

        if region_type not in _delegue_counter_extract:
            _delegue_counter_extract[region_type] = 1

        for delegue_key, delegue_data in repartition.items():
            delegue_name = f"délégué {region_type} {_delegue_counter_extract[region_type]}"
            _delegue_counter_extract[region_type] += 1

            secteurs = delegue_data.get('secteurs', [])
            if isinstance(secteurs, list) and len(secteurs) > 0:
                for secteur_item in secteurs:
                    if isinstance(secteur_item, dict):
                        secteur_nom = secteur_item.get('nom', '')
                        quantite = secteur_item.get('objectif', 0)
                        details_produits = secteur_item.get('details_produits', {})
                    else:
                        secteur_nom = str(secteur_item)
                        quantite = 0
                        details_produits = {}

                    _mois_names = ['Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
                                    'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre']

                    if details_produits:
                        for prod_code, prod_info in details_produits.items():
                            _obj_annuel = prod_info.get('objectif', 0)
                            _obj_mensuel = round(_obj_annuel / 12, 2) if _obj_annuel else 0
                            for _m_idx, _m_nom in enumerate(_mois_names, 1):
                                _extract_data_for_delegue.append({
                                    'Délégué': delegue_name,
                                    'Secteur': secteur_nom,
                                    'Produit': prod_info.get('name', prod_code),
                                    'Année': _year_n1_extract,
                                    'Mois': _m_nom,
                                    'N° Mois': _m_idx,
                                    'Objectif Mensuel': _obj_mensuel,
                                    'Objectif Annuel Produit': _obj_annuel,
                                    'Objectif Total Secteur': quantite,
                                })
                    else:
                        _obj_mensuel_s = round(quantite / 12, 2) if quantite else 0
                        for _m_idx, _m_nom in enumerate(_mois_names, 1):
                            _extract_data_for_delegue.append({
                                'Délégué': delegue_name,
                                'Secteur': secteur_nom,
                                'Produit': '-',
                                'Année': _year_n1_extract,
                                'Mois': _m_nom,
                                'N° Mois': _m_idx,
                                'Objectif Mensuel': _obj_mensuel_s,
                                'Objectif Annuel Produit': quantite,
                                'Objectif Total Secteur': quantite,
                            })

    if _extract_data_for_delegue:
        _df_delegue_extract = pd.DataFrame(_extract_data_for_delegue)
        _df_delegue_extract = _df_delegue_extract.sort_values(['Délégué', 'Secteur', 'Produit', 'N° Mois'])

        _product_label_extract = "multi_produits"
        if 'selected_product' in st.session_state and st.session_state.selected_product:
            _product_label_extract = st.session_state.selected_product.get('Code PCT', 'produit')

        _ordered_cols_extract = ['Délégué', 'Secteur', 'Produit', 'Année', 'Mois', 'Objectif Mensuel', 'Objectif Annuel Produit', 'Objectif Total Secteur']
        _excel_delegue_extract = to_excel_simple(_df_delegue_extract, _ordered_cols_extract)

        st.markdown("""
        <div style="display: flex; align-items: center; margin: 1rem 0 0.75rem 0;">
            <div style="width: 5px; height: 24px; background: linear-gradient(180deg, #3B82F6, #1E40AF); border-radius: 3px; margin-right: 12px;"></div>
            <span class="dark-text" style="font-size: 1.25rem; font-weight: 600;">Extraction des Données</span>
        </div>
        """, unsafe_allow_html=True)

        st.download_button(
            label="Télécharger les Données des Délégués",
            data=_excel_delegue_extract,
            file_name=f"Donnees_Delegue_{_product_label_extract}_{_year_n1_extract}_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"excel_delegue_extract_{_product_label_extract}")

    st.markdown("<div style='height: 1rem;'></div>", unsafe_allow_html=True)

    # Titre de section avec style
    st.markdown("""
    <div style="display: flex; align-items: center; margin: 1.5rem 0 1rem 0;">
        <div style="width: 5px; height: 24px; background: linear-gradient(180deg, #3B82F6, #1E40AF); border-radius: 3px; margin-right: 12px;"></div>
        <span class="dark-text" style="font-size: 1.25rem; font-weight: 600;">Détail par Région</span>
    </div>
    """,
                unsafe_allow_html=True)

    for region_nom, region_data in regions.items():
        allocation = region_data['allocation_region']
        repartition = region_data.get('repartition_delegues', {})
        statistiques = region_data.get('statistiques_region', {})

        if not repartition:
            continue

        # Couleurs par région - Palette bleu/rouge
        couleur_region = "#3B82F6"  # Bleu par défaut
        classe_region = ""
        if "Nord" in region_nom:
            classe_region = "delegue-nord"
            couleur_region = "#3B82F6"  # Bleu
        elif "Centre" in region_nom:
            classe_region = "delegue-centre"
            couleur_region = "#1E40AF"  # Bleu foncé
        elif "Sud" in region_nom:
            classe_region = "delegue-sud"
            couleur_region = "#DC2626"  # Rouge (accent)

        # Header de région stylé avec animation
        st.markdown(f"""
        <div class="region-card-animate" style="background: #FFFFFF; padding: 1rem 1.25rem; border-radius: 12px; margin: 1rem 0 0.75rem 0; border-left: 4px solid {couleur_region}; box-shadow: 0 2px 8px rgba(0,0,0,0.05);">
            <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 1rem;">
                <div>
                    <div style="font-size: 1.1rem; font-weight: 600; color: #000000;">{region_nom}</div>
                </div>
                <div style="display: flex; gap: 1.5rem;">
                    <div style="text-align: center;">
                        <div style="font-size: 0.75rem; color: #64748B; text-transform: uppercase;">Délégués</div>
                        <div class="number-animate" style="font-size: 1.4rem; font-weight: 700; color: #000000;">{statistiques.get('nombre_delegues', 0)}</div>
                    </div>
                    <div style="text-align: center;">
                        <div style="font-size: 0.75rem; color: #64748B; text-transform: uppercase;">Objectif</div>
                        <div class="number-animate" style="font-size: 1.4rem; font-weight: 700; color: #000000;">{allocation['objectif_total']:,.0f}</div>
                    </div>
                </div>
            </div>
        </div>
        """,
                    unsafe_allow_html=True)

        # Afficher les secteurs retirés pour cette région
        if secteurs_retires:
            secteurs_retires_region = []
            for secteur in secteurs_retires:
                # Vérifier si le secteur appartient à cette région
                for secteur_liste in region_data.get('allocation_region',
                                                     {}).get('secteurs', []):
                    if secteur in str(secteur_liste):
                        secteurs_retires_region.append(secteur)
                        break

            if secteurs_retires_region:
                with st.expander(
                        f"Secteurs retirés dans {region_nom} ({len(secteurs_retires_region)})"
                ):
                    for secteur in secteurs_retires_region:
                        st.write(f"- {secteur}")

        # Afficher les clusters par délégué
        for delegue_key, delegue_data in repartition.items():
            objectif_delegue = delegue_data.get('objectif_total', 0)
            objectif_cible = delegue_data.get('objectif_cible', 0)

            with st.expander(
                    f"{delegue_key} - {objectif_delegue:,.0f} unités"
            ):
                st.markdown(f"""
                <div class="delegue-details-box {classe_region}">
                    <div style="margin-bottom: 1rem;">
                        <div style="font-size: 0.9rem; color: #64748B;">Objectif délégué</div>
                        <div style="font-size: 1.5rem; font-weight: 700; color: #1E293B;">
                            {objectif_delegue:,.0f}
                        </div>
                    </div>
                    <div style="margin-top: 1rem;">
                        <div style="font-size: 0.9rem; color: #64748B; margin-bottom: 0.5rem;">Secteurs assignés:</div>
                """,
                            unsafe_allow_html=True)

                secteurs = delegue_data.get('secteurs', [])
                if isinstance(secteurs, list) and len(secteurs) > 0:
                    # Trier les secteurs par ordre alphabétique
                    if len(secteurs) > 0 and isinstance(secteurs[0], dict):
                        secteurs = sorted(secteurs,
                                          key=lambda x: x.get('nom', ''))
                    else:
                        secteurs = sorted(secteurs, key=lambda x: str(x))
                    for secteur_item in secteurs:
                        if isinstance(secteur_item, dict):
                            secteur_nom = secteur_item.get('nom', '')
                            objectif_secteur = secteur_item.get('objectif', 0)
                        else:
                            secteur_nom = str(secteur_item)
                            objectif_secteur = 0

                        # Vérifier si ce secteur est retiré
                        secteur_est_retire = False
                        if secteurs_retires:
                            for secteur_retire in secteurs_retires:
                                if secteur_retire in secteur_nom or secteur_nom in secteur_retire:
                                    secteur_est_retire = True
                                    break

                        if secteur_est_retire:
                            st.markdown(f"""
                            <div class="secteur-list-item" style="border-left-color: #EF4444; background-color: #FEF2F2;">
                                <div style="flex-grow: 1;">
                                    <div><strong>{secteur_nom}</strong> <span style="color: #EF4444; font-size: 0.8rem;">(retiré)</span></div>
                                    <div class="secteur-objectif-header">Objectif: 0</div>
                                </div>
                                <div class="secteur-objectif-value" style="color: #EF4444;">0</div>
                            </div>
                            """,
                                        unsafe_allow_html=True)
                        else:
                            couleur_objectif = "#10B981" if objectif_secteur > 0 else "#64748B"
                            
                            # Vérifier si on a des détails par produit (mode multi-produits)
                            details_produits = secteur_item.get('details_produits', {}) if isinstance(secteur_item, dict) else {}
                            
                            if details_produits and len(details_produits) > 1:
                                # Afficher avec détails par produit
                                details_html = ""
                                for prod_code, prod_info in details_produits.items():
                                    prod_name = prod_info.get('name', prod_code)
                                    prod_obj = prod_info.get('objectif', 0)
                                    if prod_obj > 0:
                                        details_html += f'<div style="font-size: 0.75rem; color: #6B7280; padding-left: 10px;">• {prod_name}: {prod_obj:,.0f}</div>'
                                
                                st.markdown(f"""
                                <div class="secteur-list-item" style="background-color: #FFFFFF; flex-direction: column; align-items: stretch;">
                                    <div style="display: flex; justify-content: space-between; align-items: center;">
                                        <div style="flex-grow: 1;">
                                            <div style="color: #000000; font-weight: 600;">{secteur_nom}</div>
                                            <div class="secteur-objectif-header" style="color: #000000;">Objectif Global</div>
                                        </div>
                                        <div class="secteur-objectif-value" style="color: {couleur_objectif};">{objectif_secteur:,.0f}</div>
                                    </div>
                                    <div style="margin-top: 5px; border-top: 1px dashed #E5E7EB; padding-top: 5px;">
                                        <div style="font-size: 0.75rem; color: #9CA3AF; margin-bottom: 3px;">Détail par produit:</div>
                                        {details_html}
                                    </div>
                                </div>
                                """,
                                            unsafe_allow_html=True)
                            else:
                                st.markdown(f"""
                                <div class="secteur-list-item" style="background-color: #FFFFFF;">
                                    <div style="flex-grow: 1;">
                                        <div style="color: #000000;">{secteur_nom}</div>
                                        <div class="secteur-objectif-header" style="color: #000000;">Objectif</div>
                                    </div>
                                    <div class="secteur-objectif-value" style="color: {couleur_objectif};">{objectif_secteur:,.0f}</div>
                                </div>
                                """,
                                            unsafe_allow_html=True)
                else:
                    st.markdown(f"""
                    <div class="warning-box">
                        Aucun secteur assigné ou format de données incorrect.
                    </div>
                    """,
                                unsafe_allow_html=True)

                st.markdown("</div></div>", unsafe_allow_html=True)



def show_landing_page():
    """Display the landing/home page before login"""
    import os
    import base64

    script_dir = os.path.dirname(os.path.abspath(__file__))
    logo_path = os.path.join(script_dir, "logo.png")

    logo_b64 = ""
    try:
        with open(logo_path, "rb") as f:
            logo_b64 = base64.b64encode(f.read()).decode()
    except:
        pass

    logo_img = f'<img src="data:image/png;base64,{logo_b64}" style="max-width: 180px; height: auto;">' if logo_b64 else ''

    st.markdown(f"""
    <style>
    header[data-testid="stHeader"] {{
        display: none !important;
        height: 0 !important;
        min-height: 0 !important;
        padding: 0 !important;
        margin: 0 !important;
    }}
    [data-testid="stToolbar"] {{
        display: none !important;
    }}
    .stDeployButton {{
        display: none !important;
    }}
    .stApp {{
        background: #f8fafc !important;
    }}
    .stApp > .main .block-container {{
        padding-top: 0 !important;
        margin-top: 0 !important;
    }}
    .stApp > .main {{
        margin-top: 0 !important;
        padding-top: 0 !important;
    }}
    section[data-testid="stMain"] {{
        padding-top: 0 !important;
    }}
    .stApp > .main > div:first-child {{
        padding-top: 0 !important;
    }}
    .landing-topnav {{
        position: sticky;
        top: 0;
        z-index: 9999;
        background: white;
        border-bottom: 1px solid #e2e8f0;
        padding: 0 40px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        height: 60px;
        margin-left: -6rem;
        margin-right: -6rem;
        margin-top: -10rem;
        padding-left: 6rem;
        padding-right: 6rem;
    }}
    .landing-topnav-brand {{
        display: flex;
        align-items: center;
        gap: 10px;
        font-size: 1.05rem;
        font-weight: 700;
        color: #0f172a;
        text-decoration: none !important;
    }}
    .landing-topnav-brand:hover {{
        text-decoration: none !important;
    }}
    .landing-topnav-brand img {{
        height: 36px;
        width: auto;
    }}
    .landing-topnav-links {{
        display: flex;
        align-items: center;
        gap: 28px;
    }}
    .landing-topnav-links a {{
        font-size: 0.88rem;
        font-weight: 500;
        color: #475569;
        text-decoration: none;
        transition: color 0.2s;
    }}
    .landing-topnav-links a:hover {{
        color: #1e3a5f;
    }}
    .landing-topnav-cta {{
        font-size: 0.85rem;
        font-weight: 600;
        color: white !important;
        background: #1e3a5f;
        padding: 8px 20px;
        border-radius: 8px;
        text-decoration: none !important;
        transition: background 0.2s;
    }}
    .landing-topnav-cta:hover {{
        background: #0f172a;
    }}
    html {{
        scroll-behavior: smooth;
    }}
    .st-key-hero_btn_container {{
        background: transparent;
        margin-top: -16px;
        padding: 15px 0 20px 0;
    }}
    .landing-hero {{
        text-align: center;
        padding: 50px 20px 30px;
        background: transparent;
        color: #1e293b;
        position: relative;
        overflow: hidden;
    }}
    .landing-hero-content {{
        position: relative;
        z-index: 1;
    }}
    .landing-hero-badge {{
        display: inline-flex;
        align-items: center;
        margin-top: 30px;
        gap: 8px;
        background: white;
        border: 1px solid #e2e8f0;
        border-radius: 20px;
        padding: 6px 18px;
        font-size: 0.72rem;
        font-weight: 600;
        color: #475569;
        letter-spacing: 1.5px;
        text-transform: uppercase;
        margin-bottom: 28px;
    }}
    .landing-hero-badge .badge-dot {{
        width: 8px;
        height: 8px;
        border-radius: 50%;
        background: #3b82f6;
    }}
    .landing-hero h1 {{
        font-size: 3.5rem;
        font-weight: 800;
        margin-bottom: 1rem;
        letter-spacing: -1px;
        color: #0f172a;
        line-height: 1.15;
        max-width: 800px;
        margin-left: auto;
        margin-right: auto;
    }}
    .landing-hero h1 .highlight {{
        color: #3b82f6;
    }}
    .landing-hero .hero-desc {{
        font-size: 1.05rem;
        max-width: 650px;
        margin: 0 auto;
        line-height: 1.7;
        font-weight: 400;
        color: #64748b;
    }}
    @keyframes fadeInUp {{
        from {{ opacity: 0; transform: translateY(30px); }}
        to {{ opacity: 1; transform: translateY(0); }}
    }}
    .landing-features-section {{
        background: linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #0f172a 100%);
        padding: 70px 40px;
        margin-left: -6rem;
        margin-right: -6rem;
        padding-left: 6rem;
        padding-right: 6rem;
    }}
    .landing-features-section h2 {{
        text-align: center;
        font-size: 2rem;
        font-weight: 700;
        color: #ffffff;
        margin-bottom: 12px;
        line-height: 1.3;
    }}
    .landing-features-section .section-sub {{
        text-align: center;
        font-size: 1rem;
        color: #94a3b8;
        margin-bottom: 40px;
    }}
    .landing-features {{
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        gap: 24px;
        max-width: 1200px;
        margin: 0 auto;
    }}
    .landing-problems {{
        background: #f8fafc;
        padding: 60px 40px;
        text-align: center;
    }}
    .landing-problems h2 {{
        font-size: 2rem;
        font-weight: 700;
        color: #1e3a5f;
        margin-bottom: 12px;
        line-height: 1.3;
        max-width: 700px;
        margin-left: auto;
        margin-right: auto;
    }}
    .landing-problems > p {{
        font-size: 1rem;
        color: #64748b;
        margin-bottom: 36px;
        max-width: 700px;
        margin-left: auto;
        margin-right: auto;
    }}
    .landing-problems-grid {{
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 20px;
        max-width: 1100px;
        margin: 0 auto;
    }}
    .landing-problem-card {{
        background: white;
        border-radius: 16px;
        padding: 28px 20px;
        text-align: left;
        box-shadow: 0 2px 12px rgba(0,0,0,0.04);
    }}
    .landing-problem-card .problem-icon {{
        width: 44px;
        height: 44px;
        border-radius: 12px;
        background: #f1f5f9;
        display: flex;
        align-items: center;
        justify-content: center;
        margin-bottom: 16px;
        font-size: 1.2rem;
        color: #475569;
    }}
    .landing-problem-card h4 {{
        font-size: 1rem;
        font-weight: 700;
        color: #1e3a5f;
        margin-bottom: 8px;
    }}
    .landing-problem-card p {{
        font-size: 0.88rem;
        color: #64748b;
        line-height: 1.5;
    }}
    .landing-feature-card {{
        background: rgba(255,255,255,0.05);
        border: 1px solid rgba(255,255,255,0.1);
        border-radius: 16px;
        padding: 32px 24px;
        text-align: left;
        transition: transform 0.4s, box-shadow 0.4s, border-color 0.4s;
        animation: fadeInUp 0.6s ease-out both;
    }}
    .landing-feature-card:nth-child(1) {{ animation-delay: 0.1s; }}
    .landing-feature-card:nth-child(2) {{ animation-delay: 0.25s; }}
    .landing-feature-card:nth-child(3) {{ animation-delay: 0.4s; }}
    .landing-feature-card:hover {{
        transform: translateY(-6px);
        box-shadow: 0 12px 40px rgba(59,130,246,0.15);
        border-color: rgba(59,130,246,0.4);
    }}
    .landing-feature-icon {{
        width: 44px;
        height: 44px;
        border-radius: 50%;
        background: rgba(59,130,246,0.15);
        border: 2px solid #3b82f6;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 1.2rem;
        margin-bottom: 18px;
    }}
    .landing-feature-card h3 {{
        font-size: 1.1rem;
        font-weight: 700;
        color: #ffffff;
        margin-bottom: 10px;
    }}
    .landing-feature-card p {{
        font-size: 0.88rem;
        color: #94a3b8;
        line-height: 1.6;
    }}
    .landing-howit {{
        background: white;
        padding: 70px 40px 50px;
    }}
    .landing-howit h2 {{
        text-align: center;
        font-size: 2rem;
        font-weight: 700;
        color: #1e3a5f;
        margin-bottom: 50px;
    }}
    .landing-howit-grid {{
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 32px;
        max-width: 1100px;
        margin: 0 auto;
        position: relative;
    }}
    .landing-howit-grid::before {{
        content: '';
        position: absolute;
        top: 32px;
        left: 12%;
        right: 12%;
        height: 2px;
        background: linear-gradient(90deg, #e2e8f0, #cbd5e1, #e2e8f0);
        z-index: 0;
    }}
    .landing-howit-step {{
        text-align: center;
        position: relative;
        z-index: 1;
        animation: fadeInUp 0.5s ease-out both;
    }}
    .landing-howit-step:nth-child(1) {{ animation-delay: 0.1s; }}
    .landing-howit-step:nth-child(2) {{ animation-delay: 0.25s; }}
    .landing-howit-step:nth-child(3) {{ animation-delay: 0.4s; }}
    .landing-howit-step:nth-child(4) {{ animation-delay: 0.55s; }}
    .landing-howit-num {{
        width: 64px;
        height: 64px;
        border-radius: 50%;
        background: white;
        border: 2px solid #e2e8f0;
        display: flex;
        align-items: center;
        justify-content: center;
        margin: 0 auto 18px;
        font-size: 1.3rem;
        font-weight: 700;
        color: #3b82f6;
        box-shadow: 0 4px 16px rgba(0,0,0,0.06);
        transition: transform 0.3s, border-color 0.3s, box-shadow 0.3s;
    }}
    .landing-howit-step:hover .landing-howit-num {{
        transform: scale(1.1);
        border-color: #3b82f6;
        box-shadow: 0 6px 24px rgba(59,130,246,0.2);
    }}
    .landing-howit-step h4 {{
        font-size: 1rem;
        font-weight: 700;
        color: #1e3a5f;
        margin-bottom: 6px;
    }}
    .landing-howit-step p {{
        font-size: 0.85rem;
        color: #64748b;
        line-height: 1.5;
        max-width: 200px;
        margin: 0 auto;
    }}
    .landing-section-title {{
        text-align: center;
        font-size: 2rem;
        font-weight: 700;
        color: #1e3a5f;
        margin-bottom: 10px;
    }}
    .landing-section-subtitle {{
        text-align: center;
        font-size: 1.05rem;
        color: #64748b;
        margin-bottom: 30px;
    }}
    .landing-impact {{
        background: #f8fafc;
        padding: 60px 40px;
    }}
    .landing-impact-container {{
        max-width: 1100px;
        margin: 0 auto;
        display: flex;
        align-items: center;
        gap: 60px;
    }}
    .landing-impact-left {{
        flex: 1;
    }}
    .landing-impact-left h2 {{
        font-size: 2rem;
        font-weight: 700;
        color: #1e3a5f;
        margin-bottom: 16px;
        line-height: 1.3;
    }}
    .landing-impact-left p {{
        font-size: 1rem;
        color: #64748b;
        line-height: 1.7;
        margin-bottom: 24px;
    }}
    .landing-impact-check {{
        display: flex;
        align-items: center;
        gap: 10px;
        margin-bottom: 12px;
    }}
    .landing-impact-check .check-icon {{
        color: #3b82f6;
        font-size: 1.1rem;
        flex-shrink: 0;
    }}
    .landing-impact-check span {{
        color: #334155;
        font-size: 0.95rem;
        font-weight: 600;
    }}
    .landing-impact-cta {{
        display: inline-block;
        margin-top: 20px;
        padding: 12px 28px;
        background: #1e3a5f;
        color: white;
        border-radius: 8px;
        font-size: 0.95rem;
        font-weight: 600;
        text-decoration: none;
        cursor: pointer;
        border: none;
    }}
    .landing-impact-right {{
        flex: 1;
        display: flex;
        justify-content: center;
    }}
    .landing-impact-card {{
        background: white;
        border-radius: 16px;
        box-shadow: 0 8px 32px rgba(0,0,0,0.08);
        padding: 28px;
        min-width: 280px;
    }}
    .landing-impact-card-header {{
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 20px;
    }}
    .landing-impact-card-header .trend-icon {{
        font-size: 1.4rem;
        color: #3b82f6;
    }}
    .landing-impact-card-header .stat {{
        text-align: right;
    }}
    .landing-impact-card-header .stat-label {{
        font-size: 0.7rem;
        color: #94a3b8;
        font-weight: 600;
        letter-spacing: 1px;
        text-transform: uppercase;
    }}
    .landing-impact-card-header .stat-value {{
        font-size: 2rem;
        font-weight: 700;
        color: #1e3a5f;
    }}
    .landing-impact-bar {{
        height: 12px;
        border-radius: 6px;
        margin-bottom: 10px;
    }}
    .landing-impact-bar-1 {{ background: linear-gradient(90deg, #60a5fa, #3b82f6); width: 90%; }}
    .landing-impact-bar-2 {{ background: linear-gradient(90deg, #38bdf8, #0ea5e9); width: 82%; }}
    .landing-impact-bar-3 {{ background: linear-gradient(90deg, #22d3ee, #06b6d4); width: 75%; }}
    .landing-impact-bar-4 {{ background: linear-gradient(90deg, #67e8f9, #22d3ee); width: 68%; }}
    .landing-impact-bar-5 {{ background: linear-gradient(90deg, #a5f3fc, #67e8f9); width: 60%; }}
    .landing-cta-section {{
        padding: 60px 40px;
    }}
    .landing-cta-box {{
        max-width: 900px;
        margin: 0 auto;
        background: linear-gradient(135deg, #2563eb 0%, #3b82f6 50%, #1d4ed8 100%);
        border-radius: 24px;
        padding: 60px 50px;
        text-align: center;
    }}
    .landing-cta-box h2 {{
        color: white;
        font-size: 2rem;
        font-weight: 700;
        margin-bottom: 16px;
        line-height: 1.3;
    }}
    .landing-cta-box p {{
        color: rgba(255,255,255,0.85);
        font-size: 1rem;
        line-height: 1.6;
        max-width: 550px;
        margin: 0 auto 30px;
    }}
    .landing-cta-box .cta-note {{
        color: rgba(255,255,255,0.6);
        font-size: 0.82rem;
        margin-top: 16px;
    }}
    .landing-footer {{
        background: #f8fafc;
        padding: 40px 40px 24px;
        border-top: 1px solid #e2e8f0;
    }}
    .landing-footer-grid {{
        display: grid;
        grid-template-columns: 2fr 1fr 1fr;
        gap: 40px;
        max-width: 1100px;
        margin: 0 auto 30px;
    }}
    .landing-footer-brand h3 {{
        font-size: 1.1rem;
        font-weight: 700;
        color: #1e3a5f;
        margin-bottom: 8px;
    }}
    .landing-footer-brand h3 span {{
        color: #3b82f6;
    }}
    .landing-footer-brand p {{
        font-size: 0.85rem;
        color: #64748b;
        line-height: 1.5;
    }}
    .landing-footer-col h4 {{
        font-size: 0.9rem;
        font-weight: 700;
        color: #334155;
        margin-bottom: 12px;
    }}
    .landing-footer-col ul {{
        list-style: none;
        padding: 0;
        margin: 0;
    }}
    .landing-footer-col ul li {{
        font-size: 0.85rem;
        color: #64748b;
        margin-bottom: 8px;
    }}
    .landing-footer-bottom {{
        text-align: center;
        padding-top: 20px;
        border-top: 1px solid #e2e8f0;
        font-size: 0.82rem;
        color: #94a3b8;
    }}
    .landing-cta-btn {{
        display: inline-block;
        background: white;
        color: #1e3a5f;
        padding: 14px 40px;
        border-radius: 30px;
        font-weight: 700;
        font-size: 1.1rem;
        text-decoration: none;
        transition: transform 0.2s, box-shadow 0.2s;
        cursor: pointer;
        border: none;
    }}
    .landing-cta-btn:hover {{
        transform: scale(1.05);
        box-shadow: 0 6px 20px rgba(0,0,0,0.2);
    }}
    </style>

    <div class="landing-topnav">
        <a href="#section-hero" class="landing-topnav-brand">
            <img src="data:image/png;base64,{logo_b64}" alt="Sentinel Data">
        </a>
        <div class="landing-topnav-links">
            <a href="#section-solution">Solution</a>
            <a href="#section-fonctionnalites">Fonctionnalités</a>
            <a href="#section-impact">Impact</a>
            <a href="#section-demo">Démo</a>
        </div>
    </div>

    <div class="landing-hero" id="section-hero">
        <div class="landing-hero-content">
            <div class="landing-hero-badge"><span class="badge-dot"></span> Next-Gen Pharma Medical Planning</div>
            <h1>Optimisation Intelligente de la <span class="highlight">Performance Médicale</span></h1>
            <p class="hero-desc">
                JUNO Performance permet aux laboratoires pharmaceutiques de transformer leurs données de ventes en objectifs médicaux précis, et d'optimiser le dimensionnement de la force de vente.
            </p>
        </div>
    </div>
    """, unsafe_allow_html=True)


    with st.container(key="hero_btn_container"):
        col_left, col_btn, col_right = st.columns([2, 1, 2])
        with col_btn:
            if st.button("Se connecter →", key="landing_go_login", type="primary", use_container_width=True):
                st.session_state.show_landing = False
                st.rerun()

    st.markdown("""
    <div class="landing-problems" id="section-solution">
        <h2>La planification médicale pharmaceutique reste encore largement manuelle</h2>
        <p>Des processus obsolètes limitent le potentiel de croissance de vos équipes terrain.</p>
        <div class="landing-problems-grid">
            <div class="landing-problem-card">
                <div class="problem-icon">◎</div>
                <h4>Objectifs manuels</h4>
                <p>Des objectifs commerciaux définis sans bases analytiques solides.</p>
            </div>
            <div class="landing-problem-card">
                <div class="problem-icon">☰</div>
                <h4>Sectorisation déséquilibrée</h4>
                <p>Des zones géographiques mal réparties créent des iniquités.</p>
            </div>
            <div class="landing-problem-card">
                <div class="problem-icon">⚙</div>
                <h4>Allocation inefficace</h4>
                <p>Un placement des délégués médicaux non optimal face au potentiel.</p>
            </div>
            <div class="landing-problem-card">
                <div class="problem-icon">✎</div>
                <h4>Décisions intuitives</h4>
                <p>Un pilotage basé sur l'intuition plutôt que sur la donnée.</p>
            </div>
        </div>
    </div>

    <div class="landing-features-section" id="section-fonctionnalites">
        <h2>Une plateforme intelligente de planification médicale</h2>
        <p class="section-sub">Notre moteur d'analyse transforme la complexité en plans d'action clairs et précis.</p>
        <div class="landing-features">
            <div class="landing-feature-card">
                <div class="landing-feature-icon">📍</div>
                <h3>Précision Géographique</h3>
                <p>Pilotez les objectifs avec précision, du niveau national jusqu'aux région, gouvernorats et secteurs.</p>
            </div>
            <div class="landing-feature-card">
                <div class="landing-feature-icon">📈</div>
                <h3>Modélisation de la Croissance</h3>
                <p>Générez automatiquement des objectifs médicaux selon votre stratégie de croissance.</p>
            </div>
            <div class="landing-feature-card">
                <div class="landing-feature-icon">⚡</div>
                <h3>Optimisation de la Force de Vente</h3>
                <p>Répartissez et redimensionnez les délégués en fonction du potentiel et de la capacité pour optimiser la couverture terrain.</p>
            </div>
        </div>
    </div>

    <div class="landing-howit">
        <h2>Comment fonctionne JUNO Performance</h2>
        <div class="landing-howit-grid">
            <div class="landing-howit-step">
                <div class="landing-howit-num">01</div>
                <h4>Import des données</h4>
                <p>Intégration de vos données de ventes historiques via fichier Excel.</p>
            </div>
            <div class="landing-howit-step">
                <div class="landing-howit-num">02</div>
                <h4>Analyse & Segmentation</h4>
                <p>Analyse géographique par région, gouvernorat et secteur.</p>
            </div>
            <div class="landing-howit-step">
                <div class="landing-howit-num">03</div>
                <h4>Paramétrage</h4>
                <p>Application de vos règles stratégiques : croissance, mutualisation, répartition.</p>
            </div>
            <div class="landing-howit-step">
                <div class="landing-howit-num">04</div>
                <h4>Optimisation</h4>
                <p>Génération automatique des objectifs et répartition optimale des délégués.</p>
            </div>
        </div>
    </div>

    <div class="landing-impact" id="section-impact">
        <div class="landing-impact-container">
            <div class="landing-impact-left">
                <h2>Impact direct sur la performance médicale</h2>
                <p>Passez d'une gestion réactive à un pilotage proactif. JUNO Performance transforme l'organisation de vos équipes terrain pour un maximum d'efficacité.</p>
                <div class="landing-impact-check">
                    <span class="check-icon">✓</span>
                    <span>Meilleure couverture du marché</span>
                </div>
                <div class="landing-impact-check">
                    <span class="check-icon">✓</span>
                    <span>Pression promotionnelle optimisée</span>
                </div>
                <div class="landing-impact-check">
                    <span class="check-icon">✓</span>
                    <span>Équilibrage de la charge des équipes</span>
                </div>
                <div class="landing-impact-check">
                    <span class="check-icon">✓</span>
                    <span>Objectifs médicaux réalistes et motivants</span>
                </div>
                <div class="landing-impact-check">
                    <span class="check-icon">✓</span>
                    <span>Décisions managériales basées sur la donnée</span>
                </div>
            </div>
            <div class="landing-impact-right">
                <div class="landing-impact-card">
                    <div style="position:relative;display:flex;align-items:flex-end;justify-content:center;gap:12px;height:160px;padding:20px 24px 16px 24px;">
                        <div style="width:28px;height:35%;background:linear-gradient(180deg,#2563eb,#60a5fa);border-radius:6px 6px 4px 4px;"></div>
                        <div style="width:28px;height:50%;background:linear-gradient(180deg,#2563eb,#60a5fa);border-radius:6px 6px 4px 4px;"></div>
                        <div style="width:28px;height:45%;background:linear-gradient(180deg,#0ea5e9,#67e8f9);border-radius:6px 6px 4px 4px;"></div>
                        <div style="width:28px;height:65%;background:linear-gradient(180deg,#2563eb,#60a5fa);border-radius:6px 6px 4px 4px;"></div>
                        <div style="width:28px;height:60%;background:linear-gradient(180deg,#2563eb,#818cf8);border-radius:6px 6px 4px 4px;"></div>
                        <div style="width:28px;height:80%;background:linear-gradient(180deg,#0ea5e9,#67e8f9);border-radius:6px 6px 4px 4px;"></div>
                        <div style="width:28px;height:92%;background:linear-gradient(180deg,#2563eb,#60a5fa);border-radius:6px 6px 4px 4px;"></div>
                        <svg style="position:absolute;top:10px;left:20px;right:20px;width:calc(100% - 40px);height:140px;" viewBox="0 0 300 140" fill="none" xmlns="http://www.w3.org/2000/svg">
                            <polyline points="10,110 55,85 100,95 145,60 190,65 235,35 280,10" stroke="#1e3a5f" stroke-width="2.5" fill="none" stroke-linecap="round" stroke-linejoin="round" stroke-dasharray="6,4" opacity="0.5"/>
                            <polygon points="280,2 290,10 280,18" fill="#1e3a5f" opacity="0.6"/>
                        </svg>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <div class="landing-cta-section" id="section-demo">
        <div class="landing-cta-box">
            <h2>Prêt à transformer vos performances ?</h2>
            <p>Planifiez une démonstration personnalisée et découvrez comment JUNO Performance peut optimiser la planification médicale de votre laboratoire dès aujourd'hui.</p>
            <div class="cta-note">Aucun engagement requis. Démo gratuite de 30 minutes.</div>
        </div>
    </div>

    <div class="landing-footer">
        <div class="landing-footer-grid">
            <div class="landing-footer-brand">
                <h3>JUNO <span>Performance</span></h3>
                <p>Plateforme SaaS de planification et d'optimisation médicale dédiée à l'industrie pharmaceutique.</p>
            </div>
            <div class="landing-footer-col">
                <h4>Produit</h4>
                <ul>
                    <li>Solution</li>
                    <li>Fonctionnalités</li>
                    <li>Impact</li>
                    <li>Démo Interactive</li>
                </ul>
            </div>
            <div class="landing-footer-col">
                <h4>Société</h4>
                <ul>
                    <li>À propos</li>
                    <li>Écosystème JUNO</li>
                    <li>Contact</li>
                    <li>Mentions légales</li>
                </ul>
            </div>
        </div>
        <div class="landing-footer-bottom">
            &copy; 2026 Sentinel Data. Tous droits réservés.
        </div>
    </div>
    """, unsafe_allow_html=True)


def show_login_page():
    """Display the login page"""

    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    header[data-testid="stHeader"] {
        display: none !important;
        height: 0 !important;
    }
    [data-testid="stToolbar"] { display: none !important; }
    .stDeployButton { display: none !important; }
    .stApp {
        background: #f8fafc !important;
        font-family: 'Inter', sans-serif !important;
    }
    </style>

    <div style="display:flex;flex-direction:column;align-items:center;margin-top:0px;text-align:center;">
        <div style="width:48px;height:48px;background:#2563eb;border-radius:50%;display:flex;align-items:center;justify-content:center;margin:0 auto 10px auto;">
            <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" style="width:24px;height:24px;">
                <rect x="4" y="14" width="3" height="6" rx="1" fill="white"/>
                <rect x="10.5" y="9" width="3" height="11" rx="1" fill="white"/>
                <rect x="17" y="4" width="3" height="16" rx="1" fill="white"/>
            </svg>
        </div>
        <div style="font-size:1.3rem;font-weight:700;font-family:'Inter',sans-serif;margin-bottom:14px;"><span style="color:#0f172a;">JUNO</span> <span style="color:#1e3a5f;font-style:italic;">Performance</span></div>
        <h3 style="color:#0f172a;font-size:1.5rem;font-weight:700;margin:0 0 6px 0;font-family:'Inter',sans-serif;">Connexion</h3>
        <p style="color:#64748b;font-size:0.9rem;margin:0 0 16px 0;">Accédez à votre espace JUNO Performance</p>
    </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 1.5, 1])

    with col2:
        with st.form("login_form"):
            username = st.text_input("Nom d'utilisateur ou Email",
                                     placeholder="Entrez votre identifiant")
            password = st.text_input("Mot de passe",
                                     type="password",
                                     placeholder="Entrez votre mot de passe")

            col_btn1, col_btn2 = st.columns(2)
            with col_btn1:
                submit = st.form_submit_button("Se connecter",
                                               use_container_width=True,
                                               type="primary")
            with col_btn2:
                register = st.form_submit_button("Créer un compte",
                                                 use_container_width=True)

            if submit:
                if username and password:
                    if AUTH_MODULE_AVAILABLE:
                        result = authenticate_user(username, password)
                        if result['success']:
                            st.session_state.authenticated = True
                            st.session_state.user = result['user']
                            st.success("Connexion réussie!")
                            st.rerun()
                        else:
                            st.error(result['error'])
                    else:
                        st.error("Module d'authentification non disponible")
                else:
                    st.warning("Veuillez remplir tous les champs")

            if register:
                st.session_state.show_register = True
                st.rerun()

    col_bl, col_back, col_br = st.columns([1, 1.5, 1])
    with col_back:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("← Retour à l'accueil", key="login_back_landing", use_container_width=True):
            st.session_state.show_landing = True
            st.rerun()


def show_register_page():
    """Display the registration page"""
    st.markdown("""
    <div class="header-container">
        <h1 class="header-title">JUNO Performance by Sentinel Data</h1>
        <p class="header-subtitle">Création de compte</p>
    </div>
    """,
                unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])

    with col2:
        st.markdown("### Créer un compte")

        with st.form("register_form"):
            first_name = st.text_input("Prénom", placeholder="Votre prénom")
            last_name = st.text_input("Nom", placeholder="Votre nom")
            email = st.text_input("Email",
                                  placeholder="votre.email@exemple.com")
            username = st.text_input("Nom d'utilisateur",
                                     placeholder="Choisissez un identifiant")
            password = st.text_input("Mot de passe",
                                     type="password",
                                     placeholder="Minimum 6 caractères")
            password_confirm = st.text_input(
                "Confirmer le mot de passe",
                type="password",
                placeholder="Confirmez votre mot de passe")

            col_btn1, col_btn2 = st.columns(2)
            with col_btn1:
                submit = st.form_submit_button("Créer le compte",
                                               use_container_width=True,
                                               type="primary")
            with col_btn2:
                back = st.form_submit_button("Retour à la connexion",
                                             use_container_width=True)

            if submit:
                if not all([
                        first_name, last_name, email, username, password,
                        password_confirm
                ]):
                    st.warning("Veuillez remplir tous les champs")
                elif password != password_confirm:
                    st.error("Les mots de passe ne correspondent pas")
                elif len(password) < 6:
                    st.error(
                        "Le mot de passe doit contenir au moins 6 caractères")
                elif '@' not in email:
                    st.error("Veuillez entrer une adresse email valide")
                else:
                    if AUTH_MODULE_AVAILABLE:
                        result = create_user(username, email, password,
                                             first_name, last_name)
                        if result['success']:
                            st.success(
                                "Compte créé avec succès! Vous pouvez maintenant vous connecter."
                            )
                            st.session_state.show_register = False
                            st.rerun()
                        else:
                            st.error(result['error'])
                    else:
                        st.error("Module d'authentification non disponible")

            if back:
                st.session_state.show_register = False
                st.rerun()


def run_streamlit_app():
    st.markdown("""
    <div class="header-container">
        <h1 class="header-title">JUNO Performance by Sentinel Data</h1>
        <p class="header-subtitle">Plateforme dédiée au calcul et au pilotage des objectifs</p>
    </div>
    """,
                unsafe_allow_html=True)

    # Initialisation des états de session
    if 'products_list' not in st.session_state:
        st.session_state.products_list = []
    if 'selected_product' not in st.session_state:
        st.session_state.selected_product = None
    if 'selected_products' not in st.session_state:
        st.session_state.selected_products = []
    if 'selected_laboratoire' not in st.session_state:
        st.session_state.selected_laboratoire = None
    if 'selected_laboratoires' not in st.session_state:
        st.session_state.selected_laboratoires = []
    if 'selected_product_options' not in st.session_state:
        st.session_state.selected_product_options = []
    if 'data_file' not in st.session_state:
        st.session_state.data_file = None
    if 'sonat_app' not in st.session_state:
        st.session_state.sonat_app = None
    if 'analysis_done' not in st.session_state:
        st.session_state.analysis_done = False
    if 'show_remove_secteurs' not in st.session_state:
        st.session_state.show_remove_secteurs = False
    if 'secteurs_a_retirer' not in st.session_state:
        st.session_state.secteurs_a_retirer = None
    if 'detected_year_n' not in st.session_state:
        st.session_state.detected_year_n = 'N'
    if 'market_data_loaded' not in st.session_state:
        st.session_state.market_data_loaded = False
    if 'current_view' not in st.session_state:
        st.session_state.current_view = "Analyse par produit"
    if 'cached_analysis_results' not in st.session_state:
        st.session_state.cached_analysis_results = {}
    if 'cached_gov_distributions' not in st.session_state:
        st.session_state.cached_gov_distributions = {}
    if 'cached_secteur_distributions' not in st.session_state:
        st.session_state.cached_secteur_distributions = {}

    # YouTube-style profile circle with dropdown (fixed position top right)
    if st.session_state.get('user'):
        user = st.session_state.user
        initials = f"{user.get('first_name', 'U')[0].upper()}{user.get('last_name', '')[0].upper() if user.get('last_name') else ''}"

        # Check for logout action
        if st.session_state.get('trigger_logout', False):
            st.session_state.authenticated = False
            st.session_state.user = None
            st.session_state.products_list = []
            st.session_state.selected_product = None
            st.session_state.analysis_done = False
            st.session_state.trigger_logout = False
            st.rerun()

        # Fixed position profile circle using HTML/CSS (hover to show dropdown)
        st.markdown(f"""
        <style>
            #profile-container {{
                position: fixed;
                top: 14px;
                right: 70px;
                z-index: 999999;
            }}
            #profile-circle {{
                width: 36px;
                height: 36px;
                border-radius: 50%;
                background: linear-gradient(135deg, #065fd4, #0a4a9e);
                color: white;
                display: flex;
                align-items: center;
                justify-content: center;
                font-weight: 600;
                font-size: 14px;
                cursor: pointer;
                user-select: none;
                box-shadow: 0 1px 3px rgba(0,0,0,0.2);
            }}
            #profile-dropdown {{
                display: none;
                position: absolute;
                top: 44px;
                right: 0;
                background: white;
                border-radius: 12px;
                box-shadow: 0 4px 24px rgba(0,0,0,0.18);
                min-width: 160px;
                padding: 8px 0;
                z-index: 999999;
            }}
            #profile-container:hover #profile-dropdown {{
                display: block;
            }}
            #logout-btn {{
                padding: 10px 16px;
                cursor: pointer;
                font-size: 14px;
                color: #0f0f0f;
                display: flex;
                align-items: center;
                gap: 10px;
                transition: background-color 0.15s ease;
            }}
            #logout-btn:hover {{
                background-color: #f2f2f2;
            }}
        </style>
        <div id="profile-container">
            <div id="profile-circle">{initials}</div>
            <div id="profile-dropdown">
                <div id="logout-btn" onclick="triggerLogout()">
                    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path><polyline points="16 17 21 12 16 7"></polyline><line x1="21" y1="12" x2="9" y2="12"></line></svg>
                    Déconnexion
                </div>
            </div>
        </div>
        <script>
            function triggerLogout() {{
                const streamlitDoc = window.parent.document;
                const buttons = streamlitDoc.querySelectorAll('button');
                buttons.forEach(btn => {{
                    if (btn.innerText.includes('Déconnexion')) btn.click();
                }});
            }}
        </script>
        """,
                    unsafe_allow_html=True)

    with st.sidebar:
        st.image("logo.png", use_container_width=True)

        st.markdown(
            '<p style="font-size: 1.1rem; font-weight: 700; color: #ffffff; margin-bottom: 5px;">Navigation</p>',
            unsafe_allow_html=True)

        # Boutons modernes pour la navigation (un en dessous de l'autre)
        is_analyse_active = st.session_state.current_view == "Analyse par produit"
        is_delegues_active = st.session_state.current_view == "Répartition des Délégués"
        is_admin_view_active = st.session_state.current_view == "Gestion des Utilisateurs"
        user_role = st.session_state.get('user', {}).get('role', 'user')

        # Style moderne et interactif pour les boutons de sidebar
        st.markdown("""
        <style>
        /* Animation d'entrée pour les boutons */
        @keyframes slideInSidebar {
            from { opacity: 0; transform: translateX(-10px); }
            to { opacity: 1; transform: translateX(0); }
        }
        @keyframes pulseGlow {
            0%, 100% { box-shadow: 0 0 0 0 rgba(59, 130, 246, 0); }
            50% { box-shadow: 0 0 0 4px rgba(59, 130, 246, 0.1); }
        }
        @keyframes ripple {
            to { transform: scale(2); opacity: 0; }
        }
        
        /* Style moderne pour TOUS les boutons Streamlit dans la sidebar - Light mode */
        section[data-testid="stSidebar"] button {
            background: linear-gradient(135deg, #ffffff 0%, #f8f9fa 100%) !important;
            border: 1px solid #e9ecef !important;
            color: #1a1a1a !important;
            font-weight: 500 !important;
            text-align: left !important;
            justify-content: flex-start !important;
            padding: 12px 16px !important;
            border-radius: 12px !important;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.04) !important;
            animation: slideInSidebar 0.4s ease-out forwards !important;
            position: relative !important;
            overflow: hidden !important;
        }
        section[data-testid="stSidebar"] .stButton > button {
            text-align: left !important;
            justify-content: flex-start !important;
        }
        section[data-testid="stSidebar"] button:hover {
            background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%) !important;
            border-color: #dee2e6 !important;
            transform: translateX(6px) scale(1.01) !important;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08) !important;
        }
        section[data-testid="stSidebar"] button:active {
            transform: translateX(3px) scale(0.99) !important;
            box-shadow: 0 1px 2px rgba(0, 0, 0, 0.06) !important;
            transition: all 0.1s ease !important;
        }
        section[data-testid="stSidebar"] button:focus {
            outline: none !important;
            box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.15) !important;
        }
        
        /* Style pour le bouton actif (primary) dans la sidebar - Light mode */
        section[data-testid="stSidebar"] button[kind="primary"],
        section[data-testid="stSidebar"] button[data-testid="stBaseButton-primary"],
        section[data-testid="stSidebar"] .stButton button[kind="primary"],
        section[data-testid="stSidebar"] [data-testid="stBaseButton-primary"] {
            background: linear-gradient(135deg, #e8f4fd 0%, #d6e9f8 100%) !important;
            border: 1px solid #b8d4ea !important;
            color: #1a5490 !important;
            font-weight: 600 !important;
            text-align: left !important;
            justify-content: flex-start !important;
            box-shadow: 0 2px 8px rgba(59, 130, 246, 0.12), inset 0 1px 0 rgba(255, 255, 255, 0.5) !important;
            animation: slideInSidebar 0.4s ease-out forwards, pulseGlow 2s ease-in-out infinite !important;
        }
        section[data-testid="stSidebar"] button[kind="primary"]:hover,
        section[data-testid="stSidebar"] button[data-testid="stBaseButton-primary"]:hover,
        section[data-testid="stSidebar"] [data-testid="stBaseButton-primary"]:hover {
            background: linear-gradient(135deg, #d6e9f8 0%, #c4ddf2 100%) !important;
            border-color: #9ec5db !important;
            box-shadow: 0 4px 16px rgba(59, 130, 246, 0.18) !important;
            transform: translateX(6px) scale(1.01) !important;
        }
        section[data-testid="stSidebar"] button[kind="primary"]:active,
        section[data-testid="stSidebar"] [data-testid="stBaseButton-primary"]:active {
            transform: translateX(3px) scale(0.99) !important;
            box-shadow: 0 1px 4px rgba(59, 130, 246, 0.1) !important;
        }
        
        /* Forcer l'alignement à gauche pour tous les boutons sidebar */
        section[data-testid="stSidebar"] .stButton button p,
        section[data-testid="stSidebar"] .stButton button span,
        section[data-testid="stSidebar"] .stButton button div {
            text-align: left !important;
            width: 100% !important;
        }
        
        /* Animation d'icône au hover */
        section[data-testid="stSidebar"] button:hover::before {
            content: '';
            position: absolute;
            left: 0;
            top: 50%;
            transform: translateY(-50%);
            width: 3px;
            height: 60%;
            background: linear-gradient(180deg, #3B82F6, #1E40AF);
            border-radius: 0 2px 2px 0;
            animation: slideInSidebar 0.2s ease-out forwards;
        }
        </style>
        """,
                    unsafe_allow_html=True)

        # Bouton Analyse par produit - toujours utiliser st.button pour alignement uniforme
        if st.button("Analyse par produit",
                     use_container_width=True,
                     key="nav_btn_analyse",
                     type="primary" if is_analyse_active else "secondary"):
            if not is_analyse_active or st.session_state.get('show_remove_secteurs', False):
                st.session_state.current_view = "Analyse par produit"
                st.session_state.show_remove_secteurs = False
                st.rerun()

        # Bouton Répartition des Délégués - toujours utiliser st.button pour alignement uniforme
        if st.button("Répartition des Délégués",
                     use_container_width=True,
                     key="nav_btn_delegues",
                     type="primary" if is_delegues_active else "secondary"):
            if not is_delegues_active or st.session_state.get('show_remove_secteurs', False):
                st.session_state.current_view = "Répartition des Délégués"
                st.session_state.show_remove_secteurs = False
                st.rerun()

        if user_role == 'admin':
            if st.button("Gestion des Utilisateurs",
                         use_container_width=True,
                         key="nav_btn_admin_users",
                         type="primary" if is_admin_view_active else "secondary"):
                if not is_admin_view_active:
                    st.session_state.current_view = "Gestion des Utilisateurs"
                    st.session_state.show_remove_secteurs = False
                    st.rerun()

        # Afficher la section "Gestion des Secteurs" quand l'analyse est lancée (visible dans toutes les vues)
        if st.session_state.analysis_done:
            st.markdown(
                '<p style="font-size: 1.1rem; font-weight: 700; color: #ffffff; margin-bottom: 10px;">Gestion des Secteurs</p>',
                unsafe_allow_html=True)

            # Bouton "Secteurs non Promus" - toujours visible, toggle la vue
            if st.button("Secteurs non Promus",
                         use_container_width=True,
                         key="btn_secteurs_non_promus"):
                st.session_state.show_remove_secteurs = not st.session_state.get(
                    'show_remove_secteurs', False)
                st.rerun()

            # Bouton "Retirer la Configuration" - visible seulement si des secteurs sont exclus
            secteurs_retires = st.session_state.get('secteurs_retires_par_produit', {})
            has_exclusions = any(len(v) > 0 for v in secteurs_retires.values())
            
            if has_exclusions:
                if st.button("Retirer la Configuration",
                             use_container_width=True,
                             key="btn_retirer_config"):
                    st.session_state.secteurs_retires_par_produit = {}
                    st.session_state.secteurs_retires_global = []
                    st.session_state.cached_gov_distributions = {}
                    st.session_state.cached_secteur_distributions = {}
                    st.success("Configuration des exclusions supprimée !")
                    st.rerun()

        st.markdown("---")

        # Bouton de déconnexion dans la sidebar
        if st.session_state.get('user'):
            if st.button(" Déconnexion",
                         use_container_width=True,
                         key="btn_logout_sidebar"):
                st.session_state.authenticated = False
                st.session_state.user = None
                st.session_state.products_list = []
                st.session_state.selected_product = None
                st.session_state.analysis_done = False
                st.session_state.sonat_app = None
                st.session_state.delegue_calculator = None
                st.session_state.current_view = "Analyse par produit"
                st.session_state.cached_gov_distributions = {}
                st.session_state.cached_secteur_distributions = {}
                st.session_state.cached_analysis_results = {}
                st.rerun()

        tz_tunis = pytz.timezone('Africa/Tunis')
        heure_tunis = datetime.now(tz_tunis)
        st.caption(f"Session : {heure_tunis.strftime('%d/%m/%Y %H:%M')}")

    # Afficher la section "Secteurs non promus" si activée (prioritaire sur les autres vues)
    if st.session_state.get('show_remove_secteurs',
                            False) and st.session_state.analysis_done:
        product_code = st.session_state.selected_product['Code PCT']
        app = st.session_state.sonat_app
        display_remove_secteurs_interface(app, product_code)
        return

    # Utiliser la vue stockée dans session_state
    if st.session_state.current_view == "Gestion des Utilisateurs":
        user_role = st.session_state.get('user', {}).get('role', 'user')
        if user_role == 'admin':
            display_gestion_utilisateurs()
        else:
            st.error("Accès réservé aux administrateurs.")
        return

    if st.session_state.current_view == "Répartition des Délégués":
        if not st.session_state.analysis_done:
            st.error("Veuillez d'abord effectuer une analyse de produit")
            st.info(
                "La répartition des délégués nécessite des données de produit chargées."
            )
            return

        if st.session_state.sonat_app:
            display_repartition_delegue_clustering(st.session_state.sonat_app)
        else:
            st.error(
                "Aucune application disponible pour la répartition des délégués."
            )
    else:
        st.markdown("## Analyse par produit")

        if st.session_state.analysis_done and st.session_state.selected_product:
            product_code = st.session_state.selected_product['Code PCT']
            app = st.session_state.sonat_app

            col_left, col_center, col_right = st.columns([1, 2, 1])
            with col_center:
                if st.button("🔄 Relancer le calcul",
                             key="btn_relancer_calcul",
                             type="primary",
                             use_container_width=True):
                    st.session_state.analysis_done = False
                    st.session_state.cached_gov_distributions = {}
                    st.session_state.cached_secteur_distributions = {}
                    st.session_state.cached_analysis_results = {}
                    st.rerun()

            if not st.session_state.get('show_remove_secteurs', False):
                st.markdown("---")

            try:
                display_pro(app, product_code)
            except Exception as e:
                st.error(f"Erreur lors de l'affichage des résultats: {str(e)}")
                st.info("Essayez de réanalyser avec de nouvelles données.")

        else:
            with st.container():
                # NOUVELLE LOGIQUE DE CHARGEMENT INVERSE
                # Étape 1: Charger le fichier de marché
                st.markdown("### 1. Charger le fichier de données de marché")

                market_data_file = st.file_uploader(
                    "Téléchargez le fichier CSV/Excel des données de marché",
                    type=['csv', 'xlsx', 'xls'],
                    key="market_file")

                if market_data_file:
                    try:
                        df_market = read_uploaded_file(market_data_file)

                        if df_market is not None:
                            # Sauvegarder les données de marché
                            st.session_state.data_file = df_market

                            # Vérifier la présence de la colonne Code PCT
                            if 'Code PCT' in df_market.columns:
                                # Extraire les produits uniques du marché
                                df_market['Code PCT'] = df_market[
                                    'Code PCT'].astype(str).str.strip()

                                # Créer la liste des produits (uniquement ceux avec des ventes non-nulles)
                                products_list = []
                                unique_codes = df_market['Code PCT'].dropna(
                                ).unique()

                                # Obtenir les produits avec ventes non-nulles sur TOUTES les années
                                df_sales = st.session_state.data_file
                                products_with_sales = set()
                                if df_sales is not None and 'Code PCT' in df_sales.columns:
                                    df_sales['Code PCT'] = df_sales[
                                        'Code PCT'].astype(str).str.strip()
                                    if 'Quantités' in df_sales.columns and 'Année' in df_sales.columns:
                                        # Grouper par produit ET année
                                        sales_by_product_year = df_sales.groupby(
                                            ['Code PCT', 'Année']
                                        )['Quantités'].sum().reset_index()

                                        all_years_sorted = sorted(
                                            [int(y) for y in sales_by_product_year['Année'].astype(str).str.strip().unique() if y.isdigit()],
                                            reverse=True
                                        )
                                        year_n_detected = all_years_sorted[0] if all_years_sorted else None
                                        year_n1_detected = all_years_sorted[1] if len(all_years_sorted) >= 2 else None
                                        
                                        for code in sales_by_product_year[
                                                'Code PCT'].unique():
                                            product_sales = sales_by_product_year[
                                                sales_by_product_year[
                                                    'Code PCT'] == code]
                                            product_years = set(product_sales['Année'].astype(str).str.strip().values)
                                            has_positive_sales = (product_sales['Quantités'] > 0).any()
                                            
                                            if year_n_detected is not None and year_n1_detected is not None:
                                                has_n = str(year_n_detected) in product_years
                                                has_n1 = str(year_n1_detected) in product_years
                                                if has_n and has_n1 and has_positive_sales:
                                                    products_with_sales.add(code)
                                                elif (product_sales['Quantités'] > 0).all():
                                                    products_with_sales.add(code)
                                            else:
                                                if has_positive_sales:
                                                    products_with_sales.add(code)
                                    elif 'Quantités' in df_sales.columns:
                                        # Fallback si pas de colonne Année
                                        sales_by_product = df_sales.groupby(
                                            'Code PCT')['Quantités'].sum()
                                        products_with_sales = set(
                                            sales_by_product[sales_by_product >
                                                             0].index)

                                marche_col = None
                                for col in df_market.columns:
                                    if col.strip().lower() in ['marché', 'marche', 'marche_name', 'market', 'classe']:
                                        marche_col = col
                                        break

                                if marche_col is not None:
                                    seen_pairs = set()
                                    for code in unique_codes:
                                        if products_with_sales and code not in products_with_sales:
                                            continue
                                        
                                        produit_info = df_market[df_market['Code PCT'] == code]
                                        if produit_info.empty:
                                            continue
                                        
                                        marches_produit = produit_info[marche_col].dropna().astype(str).str.strip().unique()
                                        if len(marches_produit) == 0:
                                            marches_produit = ['Non défini']
                                        
                                        for marche in marches_produit:
                                            if not marche:
                                                marche = 'Non défini'
                                            pair_key = (code, marche)
                                            if pair_key in seen_pairs:
                                                continue
                                            seen_pairs.add(pair_key)
                                            
                                            designation = code
                                            laboratoire = "Non défini"
                                            produit_marche_info = produit_info[produit_info[marche_col].astype(str).str.strip() == marche] if marche != 'Non défini' else produit_info
                                            row = produit_marche_info.iloc[0] if not produit_marche_info.empty else produit_info.iloc[0]
                                            
                                            if 'Produit' in df_market.columns:
                                                designation = row['Produit'] if pd.notna(row.get('Produit')) else code
                                            if 'Laboratoire' in df_market.columns:
                                                lab_val = row.get('Laboratoire')
                                                if pd.notna(lab_val) and str(lab_val).strip():
                                                    laboratoire = str(lab_val).strip()
                                            
                                            products_list.append({
                                                'Code PCT': code,
                                                'Désignation': designation,
                                                'Laboratoire': laboratoire,
                                                'Marché': marche
                                            })
                                    
                                    st.session_state.marche_column = marche_col
                                    marches_count = len(set(p['Marché'] for p in products_list if p['Marché'] != 'Non défini'))
                                    if marches_count > 1:
                                        st.success(f"{marches_count} marchés détectés dans le fichier")
                                else:
                                    for code in unique_codes:
                                        if products_with_sales and code not in products_with_sales:
                                            continue

                                        designation = code
                                        laboratoire = "Non défini"
                                        produit_info = df_market[df_market['Code PCT'] == code]
                                        
                                        if not produit_info.empty:
                                            if 'Produit' in produit_info.columns:
                                                designation = produit_info['Produit'].iloc[0]
                                            if 'Laboratoire' in produit_info.columns:
                                                lab_val = produit_info['Laboratoire'].iloc[0]
                                                if pd.notna(lab_val) and str(lab_val).strip():
                                                    laboratoire = str(lab_val).strip()

                                        products_list.append({
                                            'Code PCT': code,
                                            'Désignation': designation,
                                            'Laboratoire': laboratoire,
                                            'Marché': 'Non défini'
                                        })
                                    st.session_state.marche_column = None

                                st.session_state.products_list = products_list
                                st.session_state.market_data_loaded = True

                            else:
                                st.error(
                                    "Le fichier doit contenir une colonne 'Code PCT'"
                                )

                    except Exception as e:
                        st.error(
                            f"Erreur lors du chargement du fichier de marché: {e}"
                        )

                # Étape 2: Sélectionner laboratoire puis produits (uniquement si le marché est chargé)
                if st.session_state.market_data_loaded and st.session_state.products_list:
                    st.markdown("### 2. Sélectionner un ou plusieurs laboratoires")
                    
                    # Obtenir la liste des laboratoires uniques
                    laboratoires = sorted(set(p.get('Laboratoire', 'Non défini') for p in st.session_state.products_list))
                    
                    # Récupérer la sélection précédente
                    default_labs = st.session_state.get('selected_laboratoires', [])
                    # Garder seulement les laboratoires valides
                    default_labs = [l for l in default_labs if l in laboratoires]
                    
                    selected_labs = st.multiselect(
                        "Choisissez un ou plusieurs laboratoires:",
                        options=laboratoires,
                        default=default_labs,
                        key="lab_multiselect"
                    )
                    
                    if selected_labs:
                        st.session_state.selected_laboratoires = selected_labs
                        st.session_state.selected_laboratoire = selected_labs[0]  # Compatibilité
                        
                        # Filtrer les produits par laboratoires sélectionnés
                        filtered_products = [
                            p for p in st.session_state.products_list 
                            if p.get('Laboratoire', 'Non défini') in selected_labs
                        ]
                        
                        st.markdown("### 3. Sélectionner un ou plusieurs produits")
                        
                        has_marche_col = st.session_state.get('marche_column', None) is not None
                        product_options = []
                        for p in filtered_products:
                            if has_marche_col and p.get('Marché', 'Non défini') != 'Non défini':
                                product_options.append(f"{p['Désignation']} ({p['Code PCT']}) [{p['Marché']}]")
                            else:
                                product_options.append(f"{p['Désignation']} ({p['Code PCT']})")
                        
                        # Récupérer la sélection précédente de produits (seulement ceux valides)
                        default_prods = st.session_state.get('selected_product_options', [])
                        default_prods = [p for p in default_prods if p in product_options]
                        
                        selected_options = st.multiselect(
                            "Choisissez les produits à analyser:",
                            options=product_options,
                            default=default_prods,
                            key="products_multiselect"
                        )
                        
                        if selected_options:
                            # Sauvegarder la sélection pour persistance
                            st.session_state.selected_product_options = selected_options
                            
                            selected_products = []
                            for opt in selected_options:
                                for product in filtered_products:
                                    if has_marche_col and product.get('Marché', 'Non défini') != 'Non défini':
                                        label = f"{product['Désignation']} ({product['Code PCT']}) [{product['Marché']}]"
                                    else:
                                        label = f"{product['Désignation']} ({product['Code PCT']})"
                                    if label == opt:
                                        selected_products.append(product)
                                        break
                            
                            st.session_state.selected_products = selected_products
                            # Garder le premier produit comme produit principal pour compatibilité
                            st.session_state.selected_product = selected_products[0] if selected_products else None
                            
                            labs_text = ", ".join(selected_labs)
                            marches_in_selection = set(p.get('Marché', 'Non défini') for p in selected_products if p.get('Marché', 'Non défini') != 'Non défini')
                            if marches_in_selection:
                                marches_text = ", ".join(sorted(marches_in_selection))
                                st.info(
                                    f"**{len(selected_products)} produit(s) sélectionné(s)** des laboratoires: **{labs_text}** | Marchés: **{marches_text}**"
                                )
                            else:
                                st.info(
                                    f"**{len(selected_products)} produit(s) sélectionné(s)** des laboratoires: **{labs_text}**"
                                )

                    # Étape 4: Lancer l'analyse
                    if st.session_state.selected_product:
                        st.markdown("### 4. Lancer l'analyse")

                        col1, col2, col3 = st.columns([1, 2, 1])
                        with col2:
                            launch_analysis = st.button(
                                "LANCER L'ANALYSE COMPLÈTE",
                                type="primary",
                                use_container_width=True,
                                key="launch_analysis")

                        if launch_analysis:
                            # Traitement pour tous les produits sélectionnés
                            selected_products = st.session_state.get('selected_products', [])
                            if not selected_products:
                                selected_products = [st.session_state.selected_product]
                            
                            with st.spinner(f"Calcul en cours pour {len(selected_products)} produit(s)..."):
                                try:
                                    df = st.session_state.data_file
                                    marche_col = st.session_state.get('marche_column', None)
                                    
                                    all_products_results = {}
                                    last_app = None
                                    
                                    for product in selected_products:
                                        product_code = product['Code PCT']
                                        product_name = product.get('Désignation', product_code)
                                        product_marche = product.get('Marché', 'Non défini')
                                        
                                        if marche_col is not None and product_marche != 'Non défini':
                                            df_filtered_marche = df[df[marche_col].astype(str).str.strip() == product_marche]
                                        else:
                                            df_filtered_marche = df
                                        
                                        csv_content = df_filtered_marche.to_csv(index=False, sep=';')
                                        
                                        app = SonatAnalyticsPro()
                                        
                                        success = app.load_user_data(
                                            product_code=product_code,
                                            single_file_content=csv_content)

                                        if not success:
                                            st.warning(f"Erreur pour {product_name}")
                                            del app
                                            gc.collect()
                                            continue

                                        objectives = app.calculate_and_store_product_objectives(product_code)

                                        if objectives is not None:
                                            gov_dist, _ = app.get_governorat_distribution_with_objectives(product_code)
                                            secteur_dist, _ = app.get_secteur_distribution_with_objectives(product_code)
                                            
                                            total_objectif_n1 = sum(
                                                sd.get('objectif_n1_corrige', sd.get('quantite', 0)) or 0
                                                for sd in (secteur_dist or {}).values()
                                            )
                                            
                                            if total_objectif_n1 == 0:
                                                del app
                                                gc.collect()
                                                continue
                                            
                                            prod_secteur_adjustments = []
                                            for p, d in objectives.items():
                                                if p != '_TOTAUX_' and 'secteur_adjustments' in d:
                                                    prod_secteur_adjustments.extend(d['secteur_adjustments'])
                                            
                                            prod_ecart_adjustments = [
                                                adj for adj in prod_secteur_adjustments
                                                if adj.get('type') == 'Ajustement écart'
                                            ]
                                            
                                            product_data_for_n = objectives.get(product_code, {})
                                            quantite_n_produit = product_data_for_n.get('qte_n_reelle', 
                                                product_data_for_n.get('qte_n', 0)) or 0
                                            
                                            market_growth = 0
                                            if hasattr(app, 'calculate_market_growth_n1_to_n'):
                                                try:
                                                    market_growth = app.calculate_market_growth_n1_to_n()
                                                except Exception:
                                                    pass
                                            
                                            all_products_results[product_code] = {
                                                'name': product_name,
                                                'objectives': objectives,
                                                'gouvernorat_dist': gov_dist or {},
                                                'secteur_dist': secteur_dist or {},
                                                'ecart_adjustments': prod_ecart_adjustments,
                                                'market_growth': market_growth,
                                                'quantite_n': quantite_n_produit,
                                            }
                                            
                                            if last_app is not None and last_app is not app:
                                                for rk, rv in app.results.items():
                                                    last_app.results[rk] = rv
                                                app.data_n2 = None
                                                app.data_n1 = None
                                                app.data_n = None if hasattr(app, 'data_n') else None
                                                app.combined_data = None
                                                app.governorat_data = None
                                                app.secteur_data = None
                                                app._data_cache = {}
                                                app._secteur_part_cache = {}
                                                del app
                                                gc.collect()
                                            else:
                                                last_app = app
                                        else:
                                            del app
                                            gc.collect()

                                    if not all_products_results:
                                        st.error("Aucun objectif calculé. Vérifiez les données.")
                                        return
                                    
                                    if last_app:
                                        last_app.data_n2 = None
                                        last_app.data_n1 = None
                                        if hasattr(last_app, 'data_n'):
                                            last_app.data_n = None
                                        last_app.combined_data = None
                                        last_app.governorat_data = None
                                        last_app.secteur_data = None
                                        last_app._data_cache = {}
                                        last_app._secteur_part_cache = {}
                                    
                                    st.session_state.all_products_results = all_products_results
                                    st.session_state.sonat_app = last_app
                                    st.session_state.analysis_done = True
                                    st.session_state.cached_gov_distributions = {}
                                    st.session_state.cached_secteur_distributions = {}
                                    gc.collect()

                                    # Détecter l'année N
                                    year_n = extract_year_from_data(df)
                                    st.session_state.detected_year_n = year_n

                                    st.success(f"Analyse terminée pour {len(all_products_results)} produit(s)")
                                    st.markdown("---")

                                    col1, col2, col3 = st.columns([1, 2, 1])
                                    with col2:
                                        if st.button(
                                                "Accéder à Gestion des Secteurs",
                                                type="primary",
                                                use_container_width=True,
                                                key="btn_acces_gestion_secteurs"
                                        ):
                                            st.session_state.show_remove_secteurs = True
                                            st.rerun()

                                    st.rerun()

                                except Exception as e:
                                    st.error(f"Erreur lors de l'analyse: {str(e)}")


def main():
    """Main entry point with authentication check"""
    if 'authenticated' not in st.session_state:
        st.session_state.authenticated = False
    if 'show_register' not in st.session_state:
        st.session_state.show_register = False
    if 'user' not in st.session_state:
        st.session_state.user = None
    if 'show_landing' not in st.session_state:
        st.session_state.show_landing = True

    if not AUTH_MODULE_AVAILABLE:
        st.error(
            "Erreur système: Module d'authentification non disponible. Veuillez contacter l'administrateur."
        )
        st.stop()
        return

    if st.session_state.authenticated and st.session_state.user:
        user_id = st.session_state.user.get('id')
        if user_id:
            try:
                current_user = get_user_by_id(user_id)
                if current_user is not None and not current_user.get('is_active', False):
                    st.session_state.authenticated = False
                    st.session_state.user = None
                    st.warning(
                        "Votre session a expiré. Veuillez vous reconnecter.")
                    st.rerun()
            except Exception:
                pass

    if st.session_state.authenticated:
        run_streamlit_app()
    elif st.session_state.show_landing:
        show_landing_page()
    elif st.session_state.show_register:
        show_register_page()
    else:
        show_login_page()


if __name__ == "__main__":
    main()
