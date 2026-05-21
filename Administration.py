import pandas as pd
import numpy as np
import os
import json
from datetime import datetime
import re
import hashlib
import math
from collections import defaultdict
import io
import streamlit as st

_DATA_CACHE = {}
_CACHE_TIMEOUT = 1800  # 30 minutes cache
_FUNCTION_CACHE = {}  # Cache pour les fonctions de calcul

def get_cache_key(*args):
    key_string = "|".join(str(arg) for arg in args)
    return hashlib.md5(key_string.encode()).hexdigest()

def cached_data(timeout=_CACHE_TIMEOUT):
    def decorator(func):
        def wrapper(*args, **kwargs):
            cache_key = get_cache_key(func.__name__, *args, *sorted(kwargs.items()))
            
            if cache_key in _DATA_CACHE:
                cached_time, result = _DATA_CACHE[cache_key]
                if (datetime.now() - cached_time).seconds < timeout:
                    return result
            
            result = func(*args, **kwargs)
            _DATA_CACHE[cache_key] = (datetime.now(), result)
            return result
        return wrapper
    return decorator

def round_to_fifty(value):
    """Arrondit à la dizaine supérieure, ou à la 5 supérieure si < 10"""
    if value <= 0:
        return 0
    if value < 10:
        return ((value + 4) // 5) * 5
    return ((value + 9) // 10) * 10


def clean_realise_value(val):
    """Nettoie les valeurs réalisées"""
    if pd.isna(val) or val == '' or val is None:
        return 0
    
    if isinstance(val, (int, float)):
        return float(val)
    
    if isinstance(val, str):
        cleaned = str(val).strip().replace(' ', '').replace(',', '.')
        cleaned = re.sub(r'[^\d.-]', '', cleaned)
        
        try:
            return float(cleaned)
        except ValueError:
            match = re.search(r'(\d+[,.]?\d*)', str(val))
            if match:
                try:
                    return float(match.group(1).replace(',', '.'))
                except:
                    return 0
            return 0
    
    return 0

def calculate_ecarts_and_threshold(realised_data, secteur_distribution, product_name):
    """
    Calcule les écarts entre objectifs et réalisés, puis calcule le threshold (médiane des écarts absolus)
    Formule: Écart = (Objectif - Réalisé) / Réalisé
    """
    if realised_data.empty or not secteur_distribution:
        print(f"⚠️ Données réalisées vides ou distribution secteur vide pour {product_name}")
        return pd.DataFrame(), 0.0
    
    ecart_data = []
    
    for secteur_name in realised_data['Secteur'].unique():
        secteur_name_clean = str(secteur_name).strip()
        
        # Obtenir la valeur réalisée
        secteur_realise = realised_data[realised_data['Secteur'] == secteur_name]
        if secteur_realise.empty:
            continue
            
        realise_value = secteur_realise['Réalisé'].iloc[0]
        
        # Trouver l'objectif correspondant dans la distribution
        secteur_found = find_matching_secteur(secteur_name_clean, secteur_distribution)
        
        if secteur_found:
            objectif_value = secteur_distribution[secteur_found]['quantite']
            
            # Calculer l'écart
            if realise_value > 0:
                ecart_value = (objectif_value - realise_value) / realise_value
            else:
                ecart_value = 0
            
            ecart_data.append({
                'Secteur': secteur_name,
                'Réalisé': realise_value,
                'Objectif': objectif_value,
                'Écart': ecart_value,
                'Écart_abs': abs(ecart_value)
            })
        else:
            print(f"   ⚠️ {secteur_name}: non trouvé dans la distribution")
    
    if not ecart_data:
        print("❌ Aucun écart calculé")
        return pd.DataFrame(), 0.0
    
    df_ecart = pd.DataFrame(ecart_data)
    
    # Calculer le threshold comme le double de la médiane des écarts absolus
    # Si médiane > 30%, utiliser seulement la médiane (pas doublée)
    if len(df_ecart) > 0:
        mediane_ecarts = df_ecart['Écart_abs'].median()
        if mediane_ecarts > 0.30:
            threshold = mediane_ecarts
        else:
            threshold = mediane_ecarts * 2
        print(f"✅ Threshold calculé: {threshold:.3f} (2 × médiane {mediane_ecarts:.3f}) pour {len(df_ecart)} secteurs")
    else:
        threshold = 0.0
    
    return df_ecart, threshold

def adjust_ecarts_with_threshold(ecart_data, threshold, objectifs_n1_standard=None):
    """
    CORRECTION APPLIQUÉE: Ajuste les écarts extrêmes en utilisant le threshold
    - Si écart < -threshold: ajuster à +threshold (ramener les secteurs sous-performants)
    - Si écart > threshold: plafonner à +threshold
    - Les autres écarts restent inchangés
    
    Pour N: recalculer l'objectif ajusté basé sur l'écart ajusté
    Pour N+1: 
    - D'abord calculer Obj N+1 Initial avec la formule standard (à partir des données N et N-1)
    - Puis appliquer l'écart corrigé de N pour obtenir Obj N+1 Corrigé
    - Aucun nouveau calcul de seuil pour N+1
    
    Args:
        objectifs_n1_standard: dict avec {secteur: objectif_n1_initial} calculé avec formule standard
    """
    if ecart_data.empty:
        return ecart_data
    
    adjusted_data = []
    
    for _, row in ecart_data.iterrows():
        ecart = row['Écart']
        realise_value = row['Réalisé']
        objectif_initial = row['Objectif']
        secteur_name = row['Secteur']
        
        # Ajuster l'écart si nécessaire selon les nouvelles règles
        if ecart < -threshold:
            # Écart trop négatif: ajuster à +threshold (positif)
            adjusted_ecart = threshold
            adjustment_type = f"Correction (écart {ecart*100:.1f}% < -{threshold*100:.1f}% → +{threshold*100:.1f}%)"
            needs_correction = True
        elif ecart > threshold:
            # Écart trop positif: plafonner à +threshold
            adjusted_ecart = threshold
            adjustment_type = f"Plafonnement (écart {ecart*100:.1f}% > +{threshold*100:.1f}% → +{threshold*100:.1f}%)"
            needs_correction = True
        else:
            adjusted_ecart = ecart
            adjustment_type = "Normal (pas d'ajustement)"
            needs_correction = False
        
        # RECALCULER l'objectif ajusté pour N basé sur l'écart ajusté
        objectif_n_ajuste = realise_value * (1 + adjusted_ecart)
        
        # CALCULER l'objectif N+1:
        # 1. Obj N+1 Initial = formule standard calculée à partir des données N et N-1
        if objectifs_n1_standard and secteur_name in objectifs_n1_standard:
            objectif_n1_initial = objectifs_n1_standard[secteur_name]
        else:
            # Fallback: utiliser l'objectif N initial si pas de calcul N+1 disponible
            objectif_n1_initial = objectif_initial
        
        # 2. Obj N+1 Corrigé: seulement si écart hors seuil, sinon garder la valeur initiale
        if needs_correction:
            # Si écart initial négatif: utiliser la différence (écart_corrigé - écart_initial)
            # Exemple: écart initial -36%, écart corrigé 18% → différence = 18% - (-36%) = 54%
            if ecart < 0:
                ecart_for_correction = adjusted_ecart - ecart
            else:
                ecart_for_correction = adjusted_ecart
            objectif_n1_corrige = objectif_n1_initial * (1 + ecart_for_correction)
        else:
            objectif_n1_corrige = objectif_n1_initial
        
        adjusted_data.append({
            'Secteur': secteur_name,
            'Réalisé': realise_value,
            'Objectif_initial': objectif_initial,
            'Objectif_N_ajusté': objectif_n_ajuste,
            'Objectif_N+1_initial': objectif_n1_initial,
            'Objectif_N+1_corrigé': objectif_n1_corrige,
            'Écart_initial': ecart,
            'Écart_ajusté': adjusted_ecart,
            'Ajustement_appliqué': adjustment_type,
            'Threshold': threshold
        })
    
    return pd.DataFrame(adjusted_data)

def find_matching_secteur(secteur_name, secteur_distribution):
    """Trouve une correspondance de secteur dans la distribution"""
    secteur_name_clean = str(secteur_name).strip().upper()
    
    # Chercher une correspondance exacte
    for sect_key in secteur_distribution.keys():
        if str(sect_key).strip().upper() == secteur_name_clean:
            return sect_key
    
    # Chercher une correspondance partielle
    for sect_key in secteur_distribution.keys():
        sect_key_clean = str(sect_key).strip().upper()
        
        if (secteur_name_clean in sect_key_clean or 
            sect_key_clean in secteur_name_clean or
            secteur_name_clean.replace(" ", "") == sect_key_clean.replace(" ", "") or
            secteur_name_clean.replace("-", " ") == sect_key_clean.replace("-", " ") or
            secteur_name_clean.split()[0] == sect_key_clean.split()[0]):
            return sect_key
    
    return None

def get_special_governorats_from_sheet(google_sheets_data):
    if google_sheets_data is None or google_sheets_data.empty:
        return []
    
    if 'Code PCT' not in google_sheets_data.columns or 'Gouvernorat' not in google_sheets_data.columns:
        print("Colonnes 'Code PCT' ou 'Gouvernorat' non trouvées dans Google Sheets")
        return []
    
    filtered_data = google_sheets_data[
        google_sheets_data['Gouvernorat'].notna() & 
        google_sheets_data['Code PCT'].notna()
    ]
    
    special_governorats = [
        {
            'gouvernorat': str(row['Gouvernorat']).strip(),
            'code_pct': str(row['Code PCT']).strip()
        }
        for _, row in filtered_data.iterrows()
    ]
    
    return special_governorats

def get_special_secteurs_from_sheet(google_sheets_data):
    if google_sheets_data is None or google_sheets_data.empty:
        return []
    
    if 'Code PCT' not in google_sheets_data.columns or 'Secteur' not in google_sheets_data.columns:
        print("Colonnes 'Code PCT' ou 'Secteur' non trouvées dans Google Sheets")
        return []
    
    filtered_data = google_sheets_data[
        google_sheets_data['Secteur'].notna() & 
        google_sheets_data['Code PCT'].notna()
    ]
    
    special_secteurs = [
        {
            'secteur': str(row['Secteur']).strip(),
            'code_pct': str(row['Code PCT']).strip()
        }
        for _, row in filtered_data.iterrows()
    ]
    
    return special_secteurs

_PERCENTAGE_REGEX = re.compile(r'([-]?\d+[,.]?\d*)')

def clean_percentage_value(val):
    if pd.isna(val) or val == '' or val is None:
        return 0
    
    if isinstance(val, (int, float)):
        return float(val)
    
    if isinstance(val, str):
        cleaned = val.strip().replace(' ', '').replace(',', '.').replace('%', '')
        
        try:
            numeric_val = float(cleaned)
            return numeric_val
        except ValueError:
            match = _PERCENTAGE_REGEX.search(cleaned)
            if match:
                numeric_val = float(match.group(1).replace(',', '.'))
                return numeric_val
            else:
                return 0
    
    return 0

def get_ratio_quota_for_competitor(governorat_name, competing_product_code, market_data_n2):
    if market_data_n2 is None or market_data_n2.empty:
        return None
    
    ratio_quota_col = None
    for col in market_data_n2.columns:
        col_lower = str(col).lower()
        if 'ratio de quota nouvelle vue unité' in col_lower:
            ratio_quota_col = col
            break
    
    if ratio_quota_col is None:
        for col in market_data_n2.columns:
            col_lower = str(col).lower()
            if any(keyword in col_lower for keyword in ['ratio quota', 'ratio de quota', 'quota']):
                ratio_quota_col = col
                break
    
    if ratio_quota_col is None:
        return None
    
    try:
        governorat_name_clean = str(governorat_name).strip().upper()
        product_code_clean = str(competing_product_code).strip().upper()
        
        competitor_data = market_data_n2[
            (market_data_n2['Gouvernorat'].astype(str).str.strip().str.upper() == governorat_name_clean) &
            (market_data_n2['Code PCT'].astype(str).str.strip().str.upper() == product_code_clean)
        ]
        
        if competitor_data.empty:
            return None
        
        ratio_value = competitor_data[ratio_quota_col].iloc[0]
        
        if pd.isna(ratio_value) or ratio_value == '':
            return None
            
        return clean_percentage_value(ratio_value)
        
    except Exception as e:
        print(f"Erreur dans get_ratio_quota_for_competitor: {e}")
        return None

def get_ratio_quota_for_competitor_secteur(secteur_name, competing_product_code, secteur_market_data):
    if secteur_market_data is None or secteur_market_data.empty:
        return None
    
    ratio_quota_col = None
    for col in secteur_market_data.columns:
        col_lower = str(col).lower()
        if 'ratio de quota nouvelle vue unité' in col_lower:
            ratio_quota_col = col
            break
    
    if ratio_quota_col is None:
        for col in secteur_market_data.columns:
            col_lower = str(col).lower()
            if any(keyword in col_lower for keyword in ['ratio quota', 'ratio de quota', 'quota']):
                ratio_quota_col = col
                break
    
    if ratio_quota_col is None:
        return None
    
    try:
        secteur_name_clean = str(secteur_name).strip().upper()
        product_code_clean = str(competing_product_code).strip().upper()
        
        competitor_data = secteur_market_data[
            (secteur_market_data['Secteur'].astype(str).str.strip().str.upper() == secteur_name_clean) &
            (secteur_market_data['Code PCT'].astype(str).str.strip().str.upper() == product_code_clean)
        ]
        
        if competitor_data.empty:
            return None
        
        ratio_value = competitor_data[ratio_quota_col].iloc[0]
        
        if pd.isna(ratio_value) or ratio_value == '':
            return None
            
        return clean_percentage_value(ratio_value)
        
    except Exception as e:
        print(f"Erreur dans get_ratio_quota_for_competitor_secteur: {e}")
        return None

def get_next_competitor_pm_and_market_volume(governorat_name, product_code, market_data_n2):
    if market_data_n2 is None or market_data_n2.empty:
        return None, None, None
    
    governorat_name_clean = str(governorat_name).strip().upper()
    
    governorat_data = market_data_n2[
        (market_data_n2['Gouvernorat'].astype(str).str.strip().str.upper() == governorat_name_clean)
    ]
    
    if governorat_data.empty:
        return None, None, None
    
    pm_col = None
    for col in governorat_data.columns:
        col_str = str(col)
        if 'pm n saiph unité' in col_str.lower():
            pm_col = col
            break
    
    if pm_col is None:
        return None, None, None
    
    product_code_clean = str(product_code).strip().upper()
    our_product_data = governorat_data[
        governorat_data['Code PCT'].astype(str).str.strip().str.upper() == product_code_clean
    ]
    
    if our_product_data.empty:
        return None, None, None
    
    our_pm = our_product_data[pm_col].iloc[0] if not our_product_data.empty else 0
    our_pm = clean_percentage_value(our_pm)
    
    competitors_data = governorat_data[
        governorat_data['Code PCT'].astype(str).str.strip().str.upper() != product_code_clean
    ]
    
    if competitors_data.empty:
        return None, None, None
    
    competitors = []
    for product_code_competitor in competitors_data['Code PCT'].unique():
        product_code_competitor_str = str(product_code_competitor).strip().upper()
        if product_code_competitor_str != product_code_clean:
            product_data = competitors_data[
                competitors_data['Code PCT'].astype(str).str.strip().str.upper() == product_code_competitor_str
            ]
            competitor_pm = product_data[pm_col].iloc[0] if not product_data.empty else 0
            competitor_pm = clean_percentage_value(competitor_pm)
            
            if competitor_pm > our_pm:
                competitors.append({
                    'code_pct': product_code_competitor,
                    'pm': competitor_pm
                })
    
    if competitors:
        competitors.sort(key=lambda x: x['pm'])
        next_competitor = competitors[0]
        competing_pm = next_competitor['pm']
        competing_product_code = next_competitor['code_pct']
        
        total_market_volume = governorat_data['Quantités'].sum() if 'Quantités' in governorat_data.columns else 0
        
        return total_market_volume, competing_pm, competing_product_code
    
    return None, None, None

def get_next_competitor_pm_and_market_volume_secteur(secteur_name, product_code, secteur_market_data):
    if secteur_market_data is None or secteur_market_data.empty:
        return None, None, None
    
    secteur_name_clean = str(secteur_name).strip().upper()
    
    secteur_data = secteur_market_data[
        (secteur_market_data['Secteur'].astype(str).str.strip().str.upper() == secteur_name_clean)
    ]
    
    if secteur_data.empty:
        return None, None, None
    
    pm_col = None
    for col in secteur_data.columns:
        col_str = str(col).lower()
        if 'pm n saiph unité' in col_str:
            pm_col = col
            break
    
    if pm_col is None:
        for col in secteur_data.columns:
            col_str = str(col).lower()
            if 'pm' in col_str and ('n saiph' in col_str or 'nsaiph' in col_str):
                pm_col = col
                break
    
    if pm_col is None:
        return None, None, None
    
    product_code_clean = str(product_code).strip().upper()
    our_product_data = secteur_data[
        secteur_data['Code PCT'].astype(str).str.strip().str.upper() == product_code_clean
    ]
    
    if our_product_data.empty:
        return None, None, None
    
    our_pm = our_product_data[pm_col].iloc[0] if not our_product_data.empty else 0
    our_pm = clean_percentage_value(our_pm)
    
    competitors_data = secteur_data[
        secteur_data['Code PCT'].astype(str).str.strip().str.upper() != product_code_clean
    ]
    
    if competitors_data.empty:
        return None, None, None
    
    competitors = []
    for product_code_competitor in competitors_data['Code PCT'].unique():
        product_code_competitor_str = str(product_code_competitor).strip().upper()
        if product_code_competitor_str != product_code_clean:
            product_data = competitors_data[
                competitors_data['Code PCT'].astype(str).str.strip().str.upper() == product_code_competitor_str
            ]
            competitor_pm = product_data[pm_col].iloc[0] if not product_data.empty else 0
            competitor_pm = clean_percentage_value(competitor_pm)
            
            if competitor_pm > our_pm:
                competitors.append({
                    'code_pct': product_code_competitor,
                    'pm': competitor_pm
                })
    
    if competitors:
        competitors.sort(key=lambda x: x['pm'])
        next_competitor = competitors[0]
        competing_pm = next_competitor['pm']
        competing_product_code = next_competitor['code_pct']
        
        total_market_volume = secteur_data['Quantités'].sum() if 'Quantités' in secteur_data.columns else 0
        
        return total_market_volume, competing_pm, competing_product_code
    
    return None, None, None

def calculate_special_governorat_target(governorat_name, product_code, current_value, market_data_n2):
    total_market_volume, competing_pm, competing_product_code = get_next_competitor_pm_and_market_volume(
        governorat_name, product_code, market_data_n2
    )
    
    if total_market_volume is None or competing_pm is None:
        return None
    
    final_target = current_value
    
    ratio_quota = get_ratio_quota_for_competitor(
        governorat_name, competing_product_code, market_data_n2
    )
    
    if ratio_quota is not None and ratio_quota > 0:
        final_target = current_value * (1 + ratio_quota)
    
    rounded_value = round_to_fifty(final_target)
    if rounded_value > final_target:
        final_target = rounded_value
        arrondi_applique = True
    else:
        arrondi_applique = False
    
    return round(final_target), competing_product_code, competing_pm, total_market_volume, current_value, ratio_quota, arrondi_applique

def calculate_special_secteur_target(secteur_name, product_code, current_value, secteur_market_data):
    total_market_volume, competing_pm, competing_product_code = get_next_competitor_pm_and_market_volume_secteur(
        secteur_name, product_code, secteur_market_data
    )
    
    if total_market_volume is None or competing_pm is None:
        return None
    
    final_target = current_value
    
    ratio_quota = get_ratio_quota_for_competitor_secteur(
        secteur_name, competing_product_code, secteur_market_data
    )
    
    if ratio_quota is not None and ratio_quota > 0:
        final_target = current_value * (1 + ratio_quota)
    
    rounded_value = round_to_fifty(final_target)
    if rounded_value > final_target:
        final_target = rounded_value
        arrondi_applique = True
    else:
        arrondi_applique = False
    
    return round(final_target), competing_product_code, competing_pm, total_market_volume, current_value, ratio_quota, arrondi_applique

def adjust_special_governorats_only(governorat_distribution, google_sheets_data, product_code, market_data_n2):
    if google_sheets_data is None or governorat_distribution is None:
        return governorat_distribution, []
    
    print(f"Vérification des ajustements spéciaux pour le gouvernorat...")
    
    adjustments_made = []
    special_governorats = get_special_governorats_from_sheet(google_sheets_data)
    
    product_code_clean = str(product_code).strip().upper()
    product_special_govs = [gov for gov in special_governorats 
                           if str(gov['code_pct']).strip().upper() == product_code_clean]
    
    print(f"Gouvernorats spéciaux trouvés pour le produit {product_code}: {len(product_special_govs)}")
    
    for special_gov in product_special_govs:
        gov_name = special_gov['gouvernorat']
        
        gov_found = None
        for gov_key in governorat_distribution.keys():
            if str(gov_key).strip().upper() == str(gov_name).strip().upper():
                gov_found = gov_key
                break
        
        if gov_found:
            current_value = governorat_distribution[gov_found]['quantite']
            
            if market_data_n2 is not None:
                result = calculate_special_governorat_target(
                    gov_found, product_code, current_value, market_data_n2
                )
                
                if result is not None:
                    calculated_value, competing_product_code, competing_pm, total_market_volume, base_target, ratio_quota, arrondi_applique = result
                    
                    if calculated_value != current_value:
                        governorat_distribution[gov_found]['quantite'] = calculated_value
                        
                        methode_message = f"Ajusté automatiquement (Ancienne valeur"
                        
                        if ratio_quota is not None and ratio_quota > 0:
                            methode_message += f" × (1 + Ratio de Quota: {ratio_quota:.1%})"
                        
                        if arrondi_applique:
                            methode_message += f" + Arrondi à la dizaine supérieure"
                        
                        governorat_distribution[gov_found]['methode_utilisee'] = methode_message
                        
                        adjustments_made.append({
                            'gouvernorat': gov_found,
                            'ancienne_valeur': current_value,
                            'nouvelle_valeur': calculated_value,
                            'difference': calculated_value - current_value,
                            'type': 'Automatique',
                            'competing_product_code': competing_product_code,
                            'competing_pm': competing_pm,
                            'competing_pm_pourcentage': competing_pm * 100 if competing_pm else 0,
                            'total_market_volume': total_market_volume,
                            'ratio_quota': ratio_quota,
                            'ratio_quota_pourcentage': ratio_quota * 100 if ratio_quota else 0,
                            'arrondi_applique': arrondi_applique,
                            'formule_appliquee': f"ancienne_valeur" + 
                                                (f" × (1 + {ratio_quota:.3f})" if ratio_quota and ratio_quota > 0 else "") +
                                                (f" + arrondi_50" if arrondi_applique else "")
                        })
    
    return governorat_distribution, adjustments_made

def adjust_special_secteurs_only(secteur_distribution, google_sheets_data, product_code, secteur_market_data):
    if google_sheets_data is None or secteur_distribution is None:
        return secteur_distribution, []
    
    adjustments_made = []
    special_secteurs = get_special_secteurs_from_sheet(google_sheets_data)
    
    product_code_clean = str(product_code).strip().upper()
    product_special_secteurs = [sect for sect in special_secteurs 
                               if str(sect['code_pct']).strip().upper() == product_code_clean]
    
    for special_sect in product_special_secteurs:
        sect_name = special_sect['secteur']
        
        sect_found = None
        for sect_key in secteur_distribution.keys():
            if str(sect_key).strip().upper() == str(sect_name).strip().upper():
                sect_found = sect_key
                break
        
        if sect_found is None:
            for sect_key in secteur_distribution.keys():
                sect_key_str = str(sect_key).strip()
                sect_name_str = str(sect_name).strip()
                
                if (sect_key_str.upper() == sect_name_str.upper() or
                    sect_key_str.replace(" ", "").upper() == sect_name_str.replace(" ", "").upper() or
                    sect_name_str in sect_key_str or sect_key_str in sect_name_str):
                    sect_found = sect_key
                    break
        
        if sect_found:
            current_value = secteur_distribution[sect_found]['quantite']
            
            if secteur_market_data is not None:
                result = calculate_special_secteur_target(
                    sect_found, product_code, current_value, secteur_market_data
                )
                
                if result is not None:
                    calculated_value, competing_product_code, competing_pm, total_market_volume, base_target, ratio_quota, arrondi_applique = result
                    
                    if calculated_value != current_value:
                        secteur_distribution[sect_found]['quantite'] = calculated_value
                        
                        methode_message = f"Ajusté automatiquement (Ancienne valeur"
                        
                        if ratio_quota is not None and ratio_quota > 0:
                            methode_message += f" × (1 + Ratio de Quota: {ratio_quota:.1%})"
                        
                        if arrondi_applique:
                            methode_message += f" + Arrondi à la dizaine supérieure"
                        
                        secteur_distribution[sect_found]['methode_utilisee'] = methode_message
                        
                        adjustments_made.append({
                            'secteur': sect_found,
                            'ancienne_valeur': current_value,
                            'nouvelle_valeur': calculated_value,
                            'difference': calculated_value - current_value,
                            'type': 'Automatique',
                            'competing_product_code': competing_product_code,
                            'competing_pm': competing_pm,
                            'competing_pm_pourcentage': competing_pm * 100 if competing_pm else 0,
                            'total_market_volume': total_market_volume,
                            'ratio_quota': ratio_quota,
                            'ratio_quota_pourcentage': ratio_quota * 100 if ratio_quota else 0,
                            'arrondi_applique': arrondi_applique,
                            'formule_appliquee': f"ancienne_valeur" + 
                                                (f" × (1 + {ratio_quota:.3f})" if ratio_quota and ratio_quota > 0 else "") +
                                                (f" + arrondi_50" if arrondi_applique else "")
                        })
    
    return secteur_distribution, adjustments_made

def calculate_n1_standard_objectives_from_scored_data(scored_data, qte_n1, normalize_secteur_func=None):
    """
    Calcule les objectifs N+1 Initial avec la MÊME formule standard que pour N:
    Score = (0.77 × Quantité Produit) + (0.13 × Quantité Marché) + (0.10 × Ratio Quota normalisé)
    
    Pour N: on utilise les données N-1 et N-2
    Pour N+1: on utilise les données N et N-1 (décalage d'un an)
    
    Args:
        scored_data: DataFrame avec colonnes Secteur, Score (données de l'année N avec scores calculés)
        qte_n1: Quantité totale objectif pour N+1
        normalize_secteur_func: Fonction pour normaliser les noms de secteurs
    
    Returns:
        dict {secteur: objectif_n1_initial}
    """
    if scored_data is None or scored_data.empty:
        return {}
    
    # Calculer le total des scores
    total_score = scored_data['Score'].sum()
    if total_score <= 0:
        return {}
    
    objectifs_n1 = {}
    for _, row in scored_data.iterrows():
        secteur = row['Secteur']
        score = row['Score']
        
        if normalize_secteur_func:
            secteur = normalize_secteur_func(secteur)
        
        # Formule standard: part proportionnelle au score composite
        part = score / total_score
        objectif_n1 = part * qte_n1
        
        objectifs_n1[secteur] = objectif_n1
    
    print(f"📊 Objectifs N+1 Initial calculés (formule standard composite): {len(objectifs_n1)} secteurs, total: {sum(objectifs_n1.values()):.0f}")
    
    return objectifs_n1

def adjust_secteur_targets_with_ecarts(secteur_distribution, product_code, secteur_market_data, google_sheets_data, realised_from_data=None, qte_n=None, scored_data_for_n1=None, frozen_threshold=None):
    """
    Ajuste les objectifs des secteurs en fonction des écarts avec les réalisés
    Nouvelle logique: calcul automatique du threshold (médiane des écarts absolus)
    
    Args:
        realised_from_data: DataFrame optionnel contenant les données réalisées (colonnes: Secteur, Réalisé)
                           Si None, on essaie de charger depuis Google Sheets
        qte_n: Quantité totale objectif pour N (utilisée pour calculer N+1 avec la même valeur)
        scored_data_for_n1: DataFrame avec colonnes Secteur et Score (données N avec scores pour calcul N+1)
        frozen_threshold: Threshold pré-calculé à utiliser (si fourni, ne recalcule pas)
    """
    if secteur_distribution is None:
        return secteur_distribution, []
    
    adjustments_made = []
    
    # Utiliser les données réalisées fournies ou charger depuis Google Sheets
    if realised_from_data is not None and not realised_from_data.empty:
        realised_data = realised_from_data
        print(f"✅ Utilisation des données réalisées fournies: {len(realised_data)} lignes")
    else:
        # Charger les données réalisées depuis le sheet nommé comme le code PC
        realised_data = get_realised_data_from_sheet(product_code)
    
    if realised_data.empty:
        print(f"⚠️ Aucune donnée réalisée trouvée pour {product_code}")
        return secteur_distribution, []
    
    # Utiliser le threshold figé si fourni, sinon calculer
    if frozen_threshold is not None and frozen_threshold > 0:
        threshold = frozen_threshold
        print(f"✅ Threshold FIGÉ utilisé: {threshold:.3f} (calculé avant suppression des secteurs)")
        # Calculer seulement les écarts (pas le threshold)
        ecart_data, _ = calculate_ecarts_and_threshold(
            realised_data, secteur_distribution, product_code
        )
    else:
        # Calculer les écarts et le threshold
        ecart_data, threshold = calculate_ecarts_and_threshold(
            realised_data, secteur_distribution, product_code
        )
        print(f"✅ Threshold calculé: {threshold:.3f} (2 × médiane des écarts absolus)")
    
    if ecart_data.empty or threshold == 0.0:
        print(f"⚠️ Impossible de calculer le threshold pour {product_code}")
        return secteur_distribution, []
    
    # Calculer les objectifs N+1 Initial avec la formule standard composite (à partir des données N)
    if qte_n is None:
        qte_n = sum(v['quantite'] for v in secteur_distribution.values())
    
    # Utiliser les données scorées de N pour calculer N+1 avec la même formule standard
    if scored_data_for_n1 is not None and not scored_data_for_n1.empty:
        objectifs_n1_standard = calculate_n1_standard_objectives_from_scored_data(scored_data_for_n1, qte_n)
        print(f"📊 Objectifs N+1 calculés avec formule standard composite: {len(objectifs_n1_standard)} secteurs")
    else:
        objectifs_n1_standard = {}
        print(f"⚠️ Pas de données scorées pour N+1, fallback sur objectifs N")
    
    # Ajuster les écarts extrêmes AVEC LA CORRECTION
    adjusted_ecarts = adjust_ecarts_with_threshold(ecart_data, threshold, objectifs_n1_standard)
    
    # Appliquer les ajustements aux secteurs
    for _, row in adjusted_ecarts.iterrows():
        secteur_name = row['Secteur']
        objectif_n_ajuste = row['Objectif_N_ajusté']
        objectif_initial = row['Objectif_initial']
        objectif_n1_initial = row['Objectif_N+1_initial']
        objectif_n1_corrige = row['Objectif_N+1_corrigé']
        initial_ecart = row['Écart_initial']
        adjusted_ecart = row['Écart_ajusté']
        adjustment_type = row['Ajustement_appliqué']
        
        # Trouver le secteur dans la distribution
        sect_found = find_matching_secteur(secteur_name, secteur_distribution)
        
        if sect_found:
            current_value = secteur_distribution[sect_found]['quantite']
            
            # Appliquer l'objectif ajusté pour N (arrondi à la dizaine)
            adjusted_value_n = round_to_fifty(objectif_n_ajuste)
            adjusted_value_n1_initial = round_to_fifty(objectif_n1_initial)
            adjusted_value_n1_corrige = round_to_fifty(objectif_n1_corrige)
            
            # Toujours appliquer les nouveaux objectifs (même si pas de correction d'écart)
            secteur_distribution[sect_found]['quantite'] = adjusted_value_n
            secteur_distribution[sect_found]['objectif_n1_initial'] = adjusted_value_n1_initial
            secteur_distribution[sect_found]['objectif_n1_corrige'] = adjusted_value_n1_corrige
            
            # Mettre à jour la méthode utilisée
            old_method = secteur_distribution[sect_found].get('methode_utilisee', '')
            secteur_distribution[sect_found]['methode_utilisee'] = (
                f"{old_method} + Ajustement écart (threshold={threshold:.3f}): "
                f"{current_value} → N:{adjusted_value_n}, N+1:{adjusted_value_n1_initial}→{adjusted_value_n1_corrige} (écart: {initial_ecart:.3f} → {adjusted_ecart:.3f})"
            )
            
            adjustments_made.append({
                'secteur': sect_found,
                'ancienne_valeur': current_value,
                'nouvelle_valeur': adjusted_value_n,
                'objectif_n1_initial': adjusted_value_n1_initial,
                'objectif_n1_corrige': adjusted_value_n1_corrige,
                'difference': adjusted_value_n - current_value,
                'type': 'Ajustement écart',
                'valeur_realisee': row['Réalisé'],
                'ancien_ecart': initial_ecart,
                'nouvel_ecart': adjusted_ecart,
                'threshold': threshold,
                'adjustment_type': adjustment_type,
                'formule_appliquee': f"N: réalisé × (1 + {adjusted_ecart:.3f}) = {row['Réalisé']:.0f} × {(1 + adjusted_ecart):.3f} = {objectif_n_ajuste:.0f}",
                'formule_n1': f"N+1: Obj_Initial × (1 + {adjusted_ecart:.3f}) = {objectif_n1_initial:.0f} × {(1 + adjusted_ecart):.3f} = {objectif_n1_corrige:.0f}"
            })
    
    # Ajustements spéciaux (comme avant)
    if secteur_market_data is not None and google_sheets_data is not None:
        secteur_distribution, special_adjustments = adjust_special_secteurs_only(
            secteur_distribution, google_sheets_data, product_code, secteur_market_data
        )
        adjustments_made.extend(special_adjustments)
    
    # Recalculer le total et les pourcentages de distribution
    total_quantite = sum([v['quantite'] for v in secteur_distribution.values()])
    if total_quantite > 0:
        for secteur_name in secteur_distribution:
            secteur_distribution[secteur_name]['part_distribution'] = (secteur_distribution[secteur_name]['quantite'] / total_quantite) * 100
    
    print(f"✅ Ajustements d'écart appliqués: {len([a for a in adjustments_made if a['type'] == 'Ajustement écart'])}")
    print(f"✅ Ajustements spéciaux appliqués: {len([a for a in adjustments_made if a['type'] == 'Automatique'])}")
    
    return secteur_distribution, adjustments_made

def remove_secteurs_from_distribution(secteur_distribution, secteurs_a_retirer, qte_n):
    """
    Retire des secteurs de la distribution et redistribue leurs quantités aux secteurs restants
    CORRECTION : Cette fonction retire uniquement les secteurs exactement spécifiés
    """
    if not secteur_distribution or not secteurs_a_retirer:
        return secteur_distribution, []
    
    print(f"📌 Suppression de {len(secteurs_a_retirer)} secteurs de la distribution")
    
    # CORRECTION : Nettoyer et normaliser les noms de secteurs à retirer
    secteurs_a_retirer_clean = [str(s).strip().upper() for s in secteurs_a_retirer]
    
    # Créer une copie de la distribution pour éviter de modifier l'original pendant l'itération
    nouvelle_distribution = secteur_distribution.copy()
    
    # Identifier les secteurs à retirer EXACTEMENT (pas de correspondance partielle)
    secteurs_identifies = []
    for secteur_a_retirer_clean in secteurs_a_retirer_clean:
        # Chercher une correspondance exacte dans les clés
        for secteur_key in list(nouvelle_distribution.keys()):
            secteur_key_clean = str(secteur_key).strip().upper()
            
            # CORRECTION : Seulement retirer si c'est une correspondance EXACTE
            if secteur_key_clean == secteur_a_retirer_clean:
                if secteur_key not in secteurs_identifies:
                    secteurs_identifies.append(secteur_key)
                break
    
    print(f"🔍 Secteurs identifiés pour retrait: {secteurs_identifies}")
    
    # Supprimer les secteurs identifiés
    quantite_retiree = 0
    secteurs_retires = []
    
    for secteur in secteurs_identifies:
        if secteur in nouvelle_distribution:
            quantite_secteur = nouvelle_distribution[secteur]['quantite']
            quantite_retiree += quantite_secteur
            secteurs_retires.append({
                'secteur': secteur,
                'quantite_retiree': quantite_secteur,
                'part_distribution': nouvelle_distribution[secteur]['part_distribution']
            })
            del nouvelle_distribution[secteur]
            print(f"  ✅ Secteur retiré: {secteur} ({quantite_secteur} unités)")
    
    # Si aucun secteur n'a été retiré, retourner la distribution originale
    if not secteurs_retires:
        print("ℹ️ Aucun secteur à retirer n'a été trouvé dans la distribution")
        return secteur_distribution, []
    
    # Si tous les secteurs ont été retirés, retourner une distribution vide
    if not nouvelle_distribution:
        print("⚠️ Tous les secteurs ont été retirés!")
        return {}, secteurs_retires
    
    # NOUVELLE LOGIQUE: NE PAS redistribuer - simplement retirer les objectifs
    # Les quantités des secteurs restants ne changent pas
    print(f"📉 Objectif retiré: {quantite_retiree:,.0f} unités (non redistribué)")
    
    # Recalculer uniquement les pourcentages de distribution basés sur le nouveau total
    if nouvelle_distribution:
        total_final = sum(v['quantite'] for v in nouvelle_distribution.values())
        if total_final > 0:
            for secteur_name in nouvelle_distribution:
                nouvelle_distribution[secteur_name]['part_distribution'] = (nouvelle_distribution[secteur_name]['quantite'] / total_final) * 100
        
        # Mettre à jour la méthode utilisée
        for secteur_name in nouvelle_distribution:
            methode_ancienne = nouvelle_distribution[secteur_name].get('methode_utilisee', '')
            nouvelle_distribution[secteur_name]['methode_utilisee'] = (
                f"{methode_ancienne} + Secteur(s) retiré(s): {len(secteurs_retires)}"
            )
    
    print(f"✅ {len(secteurs_retires)} secteurs retirés, {quantite_retiree:,.0f} unités retirées (non redistribuées)")
    print(f"✅ Nouveau nombre de secteurs: {len(nouvelle_distribution)}")
    
    return nouvelle_distribution, secteurs_retires

class SonatAnalyticsPro:
    def __init__(self):
        self.product_code = None
        self.data_n2 = None
        self.data_n1 = None
        self.combined_data = None
        self.governorat_data = None
        self.secteur_data = None
        self.google_sheets_data = None
        self.secteur_sheets_data = None
        self.results = {}
        self._data_cache = {}
        self._secteur_part_cache = {}
        self.current_year = None
        self._quantity_n_total = None
        self._quantity_n1_total = None
        self._quantity_n2_total = None
        self._total_market_volume_n2 = None
        self._total_market_volume_n1 = None
        self._total_market_volume_n = None
        self.is_two_year_mode = False  # Flag pour mode 2 années (N, N-1 seulement)
        
        self.SECTEURS_LISTE = [
            'Ariana 101', 'Ariana 102', 'Ariana 201', 'Ariana 211',
            'Beja 1', 'Beja 2',
            'Ben Arous 101', 'Ben Arous 111', 'Ben Arous 201', 'Ben Arous 202', 'Ben Arous 211',
            'Bizerte 101', 'Bizerte 111', 'Bizerte 121',
            'Jendouba 1', 'Jendouba 2',
            'Le Kef 1', 'Le Kef 2',
            'Manouba 101', 'Manouba 111', 'Manouba 121',
            'Nabeul 101', 'Nabeul 102', 'Nabeul 201', 'Nabeul 211', 'Nabeul 221', 'Nabeul 222',
            'Siliana',
            'Tunis 101', 'Tunis 111', 'Tunis 201', 'Tunis 202', 'Tunis 203', 'Tunis 211', 
            'Tunis 212', 'Tunis 301', 'Tunis 311', 'Tunis 401', 'Tunis 411', 'Tunis 501', 
            'Tunis 511', 'Tunis 521',
            'Zaghouan',
            'Kairouan 1', 'Kairouan 2',
            'Kasserine 1', 'Kasserine 2',
            'Mahdia 1', 'Mahdia 2',
            'Monastir 1', 'Monastir 2', 'Monastir 3', 'Monastir 4',
            'Sousse 101', 'Sousse 102', 'Sousse 103', 'Sousse 201', 'Sousse 211',
            'Gabes 1', 'Gabes 2',
            'Gafsa 1', 'Gafsa 2',
            'Kebili',
            'Medenine 1', 'Medenine 2', 'Medenine 3',
            'Sfax 101', 'Sfax 102', 'Sfax 103', 'Sfax 104', 'Sfax 201', 'Sfax 211',
            'Sfax 301', 'Sfax 311', 'Sfax 321', 'Sfax 331',
            'Sidi Bouzid 1','Sidi Bouzid 2',
            'Tataouine',
            'Tozeur'
        ]
        
        self.SECTEURS_SIMPLES = ['Siliana', 'Zaghouan', 'Kebili', 'Tataouine', 'Tozeur']

    def _normalize_secteur_name(self, secteur_name):
        if not secteur_name:
            return ""
        
        secteur_str = str(secteur_name).strip()
        
        for secteur_simple in self.SECTEURS_SIMPLES:
            if secteur_simple.lower() in secteur_str.lower():
                return secteur_simple
        
        if secteur_str in self.SECTEURS_LISTE:
            return secteur_str
        
        import re
        match = re.search(r'^(\D+)(\d+.*)$', secteur_str)
        if match:
            base_name = match.group(1).strip()
            numbers = match.group(2).strip()
            
            for secteur in self.SECTEURS_LISTE:
                if base_name.lower() in secteur.lower() and numbers in secteur:
                    return secteur
        
        base_name = secteur_str.split()[0] if ' ' in secteur_str else secteur_str
        
        for secteur in self.SECTEURS_LISTE:
            secteur_base = secteur.split()[0] if ' ' in secteur else secteur
            if base_name.lower() == secteur_base.lower():
                if ' ' not in secteur:
                    return secteur
                else:
                    for secteur2 in self.SECTEURS_LISTE:
                        if secteur2.startswith(base_name):
                            return secteur2
        
        return secteur_str

    def load_single_file_with_auto_detection(self, product_code, file_content):
        self.product_code = str(product_code).strip()
        
        try:
            data = pd.read_csv(io.StringIO(file_content), sep=';')
            
            data.columns = [col.strip() for col in data.columns]
            
            if 'Année' in data.columns:
                print("Colonne 'Année' trouvée, tri automatique par année")
                
                data['Année'] = data['Année'].astype(str).str.strip()
                
                annees_numeriques = []
                for annee in data['Année'].unique():
                    try:
                        annee_num = int(annee)
                        annees_numeriques.append(annee_num)
                    except:
                        if 'n-1' in annee.lower() or 'n_1' in annee.lower() or 'n1' in annee.lower():
                            self.data_n1 = data[data['Année'].str.lower().str.contains('n-1|n_1|n1')].copy()
                            self.data_n2 = data[~data['Année'].str.lower().str.contains('n-1|n_1|n1')].copy()
                        elif 'n-2' in annee.lower() or 'n_2' in annee.lower() or 'n2' in annee.lower():
                            self.data_n2 = data[data['Année'].str.lower().str.contains('n-2|n_2|n2')].copy()
                            self.data_n1 = data[~data['Année'].str.lower().str.contains('n-2|n_2|n2')].copy()
                
                if annees_numeriques:
                    annees_numeriques.sort(reverse=True)
                    if len(annees_numeriques) >= 3:
                        # 3 années: ex. 2023, 2024, 2025
                        # N = 2025 (année la plus récente, pour les objectifs et réalisés)
                        # N-1 = 2024 (données historiques pour calcul)
                        # N-2 = 2023 (données historiques)
                        annee_n = annees_numeriques[0]   # 2025
                        annee_n1 = annees_numeriques[1]  # 2024
                        annee_n2 = annees_numeriques[2]  # 2023
                        
                        self.data_n = data[data['Année'] == str(annee_n)].copy()
                        self.data_n1 = data[data['Année'] == str(annee_n1)].copy()
                        self.data_n2 = data[data['Année'] == str(annee_n2)].copy()
                        
                        print(f"Détecté: N = {annee_n}, N-1 = {annee_n1}, N-2 = {annee_n2}")
                    elif len(annees_numeriques) >= 2:
                        # 2 années: ex. 2024, 2025
                        # N = 2025, N-1 = 2024
                        annee_n = annees_numeriques[0]   # 2025
                        annee_n1 = annees_numeriques[1]  # 2024
                        
                        self.data_n = data[data['Année'] == str(annee_n)].copy()
                        self.data_n1 = data[data['Année'] == str(annee_n1)].copy()
                        self.data_n2 = pd.DataFrame()
                        self.is_two_year_mode = True  # Mode 2 années activé
                        
                        print(f"Détecté (mode 2 années): N = {annee_n}, N-1 = {annee_n1}")
                    else:
                        self.data_n = pd.DataFrame()
                        self.data_n1 = data.copy()
                        self.data_n2 = pd.DataFrame()
            
            elif any(col.lower().startswith('année') or col.lower().startswith('year') 
                    or 'date' in col.lower() for col in data.columns):
                for col in data.columns:
                    if any(keyword in col.lower() for keyword in ['année', 'year', 'date', 'periode']):
                        try:
                            unique_values = data[col].astype(str).unique()[:10]
                            annees = []
                            for val in unique_values:
                                import re
                                match = re.search(r'\b(20\d{2})\b', str(val))
                                if match:
                                    annees.append(int(match.group(1)))
                            
                            if annees:
                                annees = list(set(annees))
                                annees.sort(reverse=True)
                                if len(annees) >= 3:
                                    annee_n = annees[0]
                                    annee_n1 = annees[1]
                                    annee_n2 = annees[2]
                                    
                                    self.data_n = data[data[col].astype(str).str.contains(str(annee_n))].copy()
                                    self.data_n1 = data[data[col].astype(str).str.contains(str(annee_n1))].copy()
                                    self.data_n2 = data[data[col].astype(str).str.contains(str(annee_n2))].copy()
                                    
                                    print(f"Détecté via colonne '{col}': N = {annee_n}, N-1 = {annee_n1}, N-2 = {annee_n2}")
                                    break
                                elif len(annees) >= 2:
                                    annee_n = annees[0]
                                    annee_n1 = annees[1]
                                    
                                    self.data_n = data[data[col].astype(str).str.contains(str(annee_n))].copy()
                                    self.data_n1 = data[data[col].astype(str).str.contains(str(annee_n1))].copy()
                                    self.data_n2 = pd.DataFrame()
                                    self.is_two_year_mode = True  # Mode 2 années activé
                                    
                                    print(f"Détecté via colonne '{col}' (mode 2 années): N = {annee_n}, N-1 = {annee_n1}")
                                    break
                        except:
                            continue
            
            if self.data_n1 is None or self.data_n2 is None:
                print("Aucune information d'année détectée, division automatique des données")
                n_rows = len(data)
                midpoint = n_rows // 2
                
                self.data_n1 = data.iloc[:midpoint].copy()
                self.data_n2 = data.iloc[midpoint:].copy()
                
                print(f"Données divisées: N-1 ({len(self.data_n1)} lignes), N-2 ({len(self.data_n2)} lignes)")
            
            if not hasattr(self, 'data_n') or self.data_n is None:
                self.data_n = pd.DataFrame()
            if self.data_n1 is None:
                self.data_n1 = pd.DataFrame()
            if self.data_n2 is None:
                self.data_n2 = pd.DataFrame()
            
            if not self.data_n.empty:
                self.data_n['Année'] = 'N'
            if not self.data_n1.empty:
                self.data_n1['Année'] = 'N-1'
            if not self.data_n2.empty:
                self.data_n2['Année'] = 'N-2'
            
            self.combined_data = pd.concat([self.data_n, self.data_n1, self.data_n2], ignore_index=True)
            
            if 'Code PCT' in self.data_n2.columns:
                self.data_n2['Code PCT'] = self.data_n2['Code PCT'].astype(str).str.strip()
            if 'Code PCT' in self.data_n1.columns:
                self.data_n1['Code PCT'] = self.data_n1['Code PCT'].astype(str).str.strip()
            
            product_code_str = str(self.product_code).strip()
            print(f"Recherche du code PCT: '{product_code_str}'")
            
            in_n2 = not self.data_n2.empty and product_code_str in self.data_n2['Code PCT'].values if 'Code PCT' in self.data_n2.columns else False
            in_n1 = not self.data_n1.empty and product_code_str in self.data_n1['Code PCT'].values if 'Code PCT' in self.data_n1.columns else False
            
            print(f"Code PCT trouvé dans N-1: {in_n1}")
            print(f"Code PCT trouvé dans N-2: {in_n2}")
            
            if not in_n2 and not in_n1:
                print(f"AVERTISSEMENT: Le code PCT '{product_code_str}' n'a pas été trouvé dans les données.")
            
            self._determine_target_year()
            self._extract_governorat_data()
            self._extract_secteur_data()
            
            self.google_sheets_data = self.load_google_sheets_data()
            self.secteur_sheets_data = self.load_secteur_sheets_data()
            
            self._quantity_n_total = self._calculate_total_quantity_n()
            self._quantity_n1_total = self._calculate_total_quantity_n1()
            self._quantity_n2_total = self._calculate_total_quantity_n2()
            self._total_market_volume_n1 = self._calculate_total_market_volume()
            self._total_market_volume_n2 = self._calculate_total_market_volume_n2()
            self._total_market_volume_n = self._calculate_total_market_volume_n()
            
            print(f"Chargement terminé. Quantité N: {self._quantity_n_total}, Quantité N-1: {self._quantity_n1_total}, Quantité N-2: {self._quantity_n2_total}")
            
            return True
            
        except Exception as e:
            print(f"Erreur lors du chargement du fichier unique: {e}")
            import traceback
            traceback.print_exc()
            return False

    def load_user_data(self, product_code, file_n2_content=None, file_n1_content=None, single_file_content=None):
        if single_file_content:
            return self.load_single_file_with_auto_detection(product_code, single_file_content)
        elif file_n2_content and file_n1_content:
            self.product_code = str(product_code).strip()
            
            try:
                self.data_n2 = pd.read_csv(io.StringIO(file_n2_content), sep=';')
                self.data_n1 = pd.read_csv(io.StringIO(file_n1_content), sep=';')
                
                self.data_n2.columns = [col.strip() for col in self.data_n2.columns]
                self.data_n1.columns = [col.strip() for col in self.data_n1.columns]
                
                if 'Code PCT' in self.data_n2.columns:
                    self.data_n2['Code PCT'] = self.data_n2['Code PCT'].astype(str).str.strip()
                if 'Code PCT' in self.data_n1.columns:
                    self.data_n1['Code PCT'] = self.data_n1['Code PCT'].astype(str).str.strip()
                
                self.data_n2['Année'] = 'N-2'
                self.data_n1['Année'] = 'N-1'
                
                self.combined_data = pd.concat([self.data_n2, self.data_n1], ignore_index=True)
                
                product_code_str = str(self.product_code).strip()
                print(f"Recherche du code PCT: '{product_code_str}'")
                
                in_n2 = product_code_str in self.data_n2['Code PCT'].values
                in_n1 = product_code_str in self.data_n1['Code PCT'].values
                
                print(f"Code PCT trouvé dans N-2: {in_n2}")
                print(f"Code PCT trouvé dans N-1: {in_n1}")
                
                if not in_n2 and not in_n1:
                    print(f"AVERTISSEMENT: Le code PCT '{product_code_str}' n'a pas été trouvé dans les données.")
                
                self._determine_target_year()
                self._extract_governorat_data()
                self._extract_secteur_data()
                
                self.google_sheets_data = self.load_google_sheets_data()
                self.secteur_sheets_data = self.load_secteur_sheets_data()
                
                self._quantity_n_total = self._calculate_total_quantity_n()
                self._quantity_n1_total = self._calculate_total_quantity_n1()
                self._quantity_n2_total = self._calculate_total_quantity_n2()
                self._total_market_volume_n1 = self._calculate_total_market_volume()
                self._total_market_volume_n2 = self._calculate_total_market_volume_n2()
                self._total_market_volume_n = self._calculate_total_market_volume_n()
                
                print(f"Chargement terminé. Quantité N: {self._quantity_n_total}, Quantité N-1: {self._quantity_n1_total}, Quantité N-2: {self._quantity_n2_total}")
                
                return True
                
            except Exception as e:
                print(f"Erreur lors du chargement des données utilisateur: {e}")
                import traceback
                traceback.print_exc()
                return False
        else:
            print("Erreur: Aucune donnée fournie")
            return False

    def _calculate_total_quantity_n1(self):
        if self.data_n1 is None or self.product_code is None:
            return 0
        
        try:
            product_code_str = str(self.product_code).strip()
            
            product_data = self.data_n1[
                self.data_n1['Code PCT'].astype(str).str.strip() == product_code_str
            ]
            
            if product_data.empty:
                print(f"Produit {product_code_str} non trouvé dans N-1")
                return 0
            
            if 'Quantités' in product_data.columns:
                total_quantity = product_data['Quantités'].sum()
                print(f"Quantité N-1 trouvée: {total_quantity}")
                return total_quantity
            else:
                quantity_cols = [col for col in product_data.columns 
                               if any(keyword in str(col).lower() 
                                     for keyword in ['quantité', 'quantite', 'qte'])]
                if quantity_cols:
                    total_quantity = product_data[quantity_cols[0]].sum()
                    print(f"Quantité N-1 (colonne alternative): {total_quantity}")
                    return total_quantity
            
            return 0
            
        except Exception as e:
            print(f"Erreur dans _calculate_total_quantity_n1: {e}")
            return 0

    def _calculate_total_quantity_n2(self):
        if self.data_n2 is None or self.product_code is None:
            return 0
        
        try:
            product_code_str = str(self.product_code).strip()
            
            product_data = self.data_n2[
                self.data_n2['Code PCT'].astype(str).str.strip() == product_code_str
            ]
            
            if product_data.empty:
                print(f"Produit {product_code_str} non trouvé dans N-2")
                return 0
            
            if 'Quantités' in product_data.columns:
                total_quantity = product_data['Quantités'].sum()
                print(f"Quantité N-2 trouvée: {total_quantity}")
                return total_quantity
            else:
                quantity_cols = [col for col in product_data.columns 
                               if any(keyword in str(col).lower() 
                                     for keyword in ['quantité', 'quantite', 'qte'])]
                if quantity_cols:
                    total_quantity = product_data[quantity_cols[0]].sum()
                    print(f"Quantité N-2 (colonne alternative): {total_quantity}")
                    return total_quantity
            
            return 0
            
        except Exception as e:
            print(f"Erreur dans _calculate_total_quantity_n2: {e}")
            return 0

    def _calculate_total_quantity_n(self):
        if self.data_n is None or self.product_code is None:
            return 0
        
        try:
            product_code_str = str(self.product_code).strip()
            
            product_data = self.data_n[
                self.data_n['Code PCT'].astype(str).str.strip() == product_code_str
            ]
            
            if product_data.empty:
                print(f"Produit {product_code_str} non trouvé dans N")
                return 0
            
            if 'Quantités' in product_data.columns:
                total_quantity = product_data['Quantités'].sum()
                print(f"Quantité N trouvée: {total_quantity}")
                return total_quantity
            else:
                quantity_cols = [col for col in product_data.columns 
                               if any(keyword in str(col).lower() 
                                     for keyword in ['quantité', 'quantite', 'qte'])]
                if quantity_cols:
                    total_quantity = product_data[quantity_cols[0]].sum()
                    print(f"Quantité N (colonne alternative): {total_quantity}")
                    return total_quantity
            
            return 0
            
        except Exception as e:
            print(f"Erreur dans _calculate_total_quantity_n: {e}")
            return 0

    def _calculate_total_market_volume_n2(self):
        if self.data_n2 is None:
            return 0
        
        try:
            if 'Quantités' in self.data_n2.columns:
                total_market = self.data_n2['Quantités'].sum()
                return total_market
            else:
                quantity_cols = [col for col in self.data_n2.columns 
                               if any(keyword in str(col).lower() 
                                     for keyword in ['quantité', 'quantite', 'qte', 'volume'])]
                if quantity_cols:
                    total_market = self.data_n2[quantity_cols[0]].sum()
                    return total_market
                else:
                    return 0
                    
        except Exception as e:
            print(f"Erreur dans _calculate_total_market_volume_n2: {e}")
            return 0

    def _calculate_total_market_volume(self):
        if self.data_n1 is None:
            return 0
    
        try:
            if 'Quantités' in self.data_n1.columns:
                total_market = self.data_n1['Quantités'].sum()
                return total_market
            else:
                quantity_cols = [col for col in self.data_n1.columns 
                               if any(keyword in str(col).lower() 
                                     for keyword in ['quantité', 'quantite', 'qte', 'volume'])]
                if quantity_cols:
                    total_market = self.data_n1[quantity_cols[0]].sum()
                    return total_market
                else:
                    return 0
                    
        except Exception as e:
            print(f"Erreur dans _calculate_total_market_volume: {e}")
            return 0

    def _calculate_total_market_volume_n(self):
        """Calcule le volume total du marché pour l'année N"""
        if self.data_n is None:
            return 0
    
        try:
            if 'Quantités' in self.data_n.columns:
                total_market = self.data_n['Quantités'].sum()
                return total_market
            else:
                quantity_cols = [col for col in self.data_n.columns 
                               if any(keyword in str(col).lower() 
                                     for keyword in ['quantité', 'quantite', 'qte', 'volume'])]
                if quantity_cols:
                    total_market = self.data_n[quantity_cols[0]].sum()
                    return total_market
                else:
                    return 0
                    
        except Exception as e:
            print(f"Erreur dans _calculate_total_market_volume_n: {e}")
            return 0

    def _determine_target_year(self):
        self.current_year = "N"

    def _extract_governorat_data(self):
        if self.combined_data is None or self.combined_data.empty:
            self.governorat_data = pd.DataFrame()
            return
        
        gov_cols = ['Gouvernorat', 'Code PCT', 'Produit', 'Quantités', 'PM N saiph Unité', 
                   'Ratio de Quota nouvelle vue unité']
        
        available_cols = [col for col in gov_cols if col in self.combined_data.columns]
        self.governorat_data = self.combined_data[available_cols].copy()

    def _extract_secteur_data(self):
        if self.combined_data is None or self.combined_data.empty:
            self.secteur_data = pd.DataFrame()
            return
        
        secteur_cols = ['Secteur', 'Code PCT', 'Produit', 'Quantités', 'PM N saiph Unité', 
                       'Ratio de Quota nouvelle vue unité', 'Année']
        
        available_cols = [col for col in secteur_cols if col in self.combined_data.columns]
        self.secteur_data = self.combined_data[available_cols].copy()

    def load_google_sheets_data(self, sheet_name="quantité_classement"):
        """Désactivé - Google Sheets n'est plus utilisé"""
        return None

    def load_secteur_sheets_data(self, sheet_name="secteur"):
        """Désactivé - Google Sheets n'est plus utilisé"""
        return None

    def load_market_data(self):
        if self.data_n2 is not None:
            market_data = self.data_n2.copy()
            if 'Code PCT' in market_data.columns:
                market_data['Code PCT'] = market_data['Code PCT'].astype(str).str.strip()
            return market_data
        return pd.DataFrame()

    def load_sonat_data(self):
        """Retourne les données combinées N et N-1 pour les calculs"""
        dfs = []
        
        # Ajouter données N si disponibles
        if self.data_n is not None and not self.data_n.empty:
            data_n_copy = self.data_n.copy()
            if 'Année' not in data_n_copy.columns:
                data_n_copy['Année'] = 'N'
            dfs.append(data_n_copy)
        
        # Ajouter données N-1 si disponibles
        if self.data_n1 is not None and not self.data_n1.empty:
            data_n1_copy = self.data_n1.copy()
            if 'Année' not in data_n1_copy.columns:
                data_n1_copy['Année'] = 'N-1'
            dfs.append(data_n1_copy)
        
        if dfs:
            sonat_data = pd.concat(dfs, ignore_index=True)
            if 'Code PCT' in sonat_data.columns:
                sonat_data['Code PCT'] = sonat_data['Code PCT'].astype(str).str.strip()
            return sonat_data
        
        return pd.DataFrame()

    def load_secteur_market_data(self, product_code):
        if self.data_n1 is None:
            return pd.DataFrame()
        
        secteur_data = self.data_n1[
            self.data_n1['Code PCT'].astype(str).str.strip() == str(product_code).strip()
        ].copy()
        
        if 'Quantités' in secteur_data.columns:
            print(f"Volume marché secteur pour {product_code}: {secteur_data['Quantités'].sum()}")
        else:
            quantity_cols = [col for col in secteur_data.columns 
                           if any(keyword in str(col).lower() 
                                 for keyword in ['quantité', 'quantite', 'qte', 'volume'])]
            if quantity_cols:
                secteur_data['Quantités'] = secteur_data[quantity_cols[0]]
        
        return secteur_data

    def clean_percentage(self, val):
        return clean_percentage_value(val)

    def clean_quantity(self, val):
        if pd.isna(val) or val == '': return 0
        if isinstance(val, (int, float)): return float(val)
        if isinstance(val, str):
            cleaned = val.replace(' ', '').replace(',', '.')
            try: return float(cleaned)
            except:
                import re
                m = re.search(r'(\d+[,.]?\d*)', cleaned)
                return float(m.group(1).replace(',', '.')) if m else 0
        return 0

    def calculate_product_growth_corrected(self):
        if self._quantity_n1_total is None or self._quantity_n2_total is None:
            return 0
        
        if self._quantity_n2_total == 0:
            return 100 if self._quantity_n1_total > 0 else 0
        
        croissance = ((self._quantity_n1_total - self._quantity_n2_total) / self._quantity_n2_total) * 100
        return croissance

    def calculate_market_growth_corrected(self):
        """Croissance marché N-2 vers N-1 (pour Objectif N)"""
        if self._total_market_volume_n1 is None or self._total_market_volume_n2 is None:
            return 0
        
        if self._total_market_volume_n2 == 0:
            return 100 if self._total_market_volume_n1 > 0 else 0
        
        croissance = ((self._total_market_volume_n1 - self._total_market_volume_n2) / self._total_market_volume_n2) * 100
        return croissance

    def calculate_market_growth_n1_to_n(self):
        """Croissance marché N-1 vers N (pour Objectif N+1 - valeur affichée)"""
        if self._total_market_volume_n is None or self._total_market_volume_n1 is None:
            return 0
        
        if self._total_market_volume_n1 == 0:
            return 100 if self._total_market_volume_n > 0 else 0
        
        croissance = ((self._total_market_volume_n - self._total_market_volume_n1) / self._total_market_volume_n1) * 100
        return croissance

    def calculate_product_growth_corrected_n1_to_n(self):
        """Croissance produit N-1 vers N (pour Objectif N+1 - valeur affichée)"""
        if self._quantity_n_total is None or self._quantity_n1_total is None:
            return 0
        
        if self._quantity_n1_total == 0:
            return 100 if self._quantity_n_total > 0 else 0
        
        croissance = ((self._quantity_n_total - self._quantity_n1_total) / self._quantity_n1_total) * 100
        return croissance

    def calculate_pm_moyenne(self, product_code=None):
        if product_code is None:
            product_code = self.product_code
        
        if product_code is None:
            return 0, 0, 0, "N/A"
        
        ventes_n = self._quantity_n_total if self._quantity_n_total is not None else 0
        ventes_n1 = self._quantity_n1_total if self._quantity_n1_total is not None else 0
        
        volume_marché_n = self._total_market_volume_n if self._total_market_volume_n is not None else 0
        volume_marché_n1 = self._total_market_volume_n1 if self._total_market_volume_n1 is not None else 0
        
        pm_n = 0
        pm_n1 = 0
        pm_moyenne = 0
        formule = "N/A"
        
        if volume_marché_n is not None and volume_marché_n > 0:
            pm_n = (ventes_n / volume_marché_n) * 100
        
        if volume_marché_n1 is not None and volume_marché_n1 > 0:
            pm_n1 = (ventes_n1 / volume_marché_n1) * 100
        
        if pm_n > 0 and pm_n1 > 0:
            pm_moyenne = (pm_n + pm_n1) / 2
            formule = f"PM Moyenne = (({ventes_n:,.0f} ÷ {volume_marché_n:,.0f}) + ({ventes_n1:,.0f} ÷ {volume_marché_n1:,.0f})) ÷ 2 × 100 = {pm_moyenne:.1f}%"
        elif pm_n > 0:
            pm_moyenne = pm_n
            formule = f"PM N = {ventes_n:,.0f} ÷ {volume_marché_n:,.0f} × 100 = {pm_moyenne:.1f}%"
        elif pm_n1 > 0:
            pm_moyenne = pm_n1
            formule = f"PM N-1 = {ventes_n1:,.0f} ÷ {volume_marché_n1:,.0f} × 100 = {pm_moyenne:.1f}%"
        else:
            formule = "Données insuffisantes pour calculer la PM"
        
        return pm_moyenne, pm_n, pm_n1, formule

    def calculate_growth(self, sales, market):
        if sales.empty: 
            return 0, 0
        
        sonat_growth = self.calculate_product_growth_corrected()
        market_growth = self.calculate_market_growth_corrected()
        
        return sonat_growth, market_growth

    def calculate_product_growth(self, sales):
        """Calcule la croissance produit de N-1 vers N (croissance récente)"""
        if sales.empty: 
            return {}
        
        growths = {}
        
        if 'Code PCT' in sales.columns:
            for product_code in sales['Code PCT'].unique():
                product_data = sales[sales['Code PCT'] == product_code]
                if not product_data.empty:
                    if str(product_code).strip() == str(self.product_code).strip():
                        growths[product_code] = self.calculate_product_growth_corrected()
                    else:
                        if 'Année' in product_data.columns:
                            yearly = product_data.groupby('Année')['Quantités'].sum().reset_index()
                            
                            # Priorité : utiliser croissance N-1 vers N (la plus récente)
                            if 'N' in yearly['Année'].values and 'N-1' in yearly['Année'].values:
                                prev = yearly[yearly['Année'] == 'N-1']['Quantités'].iloc[0]
                                curr = yearly[yearly['Année'] == 'N']['Quantités'].iloc[0]
                                if prev > 0: 
                                    growths[product_code] = (curr - prev) / prev * 100
                                else:
                                    growths[product_code] = 100 if curr > 0 else 0
                            # Sinon utiliser N-2 vers N-1
                            elif 'N-2' in yearly['Année'].values and 'N-1' in yearly['Année'].values:
                                prev = yearly[yearly['Année'] == 'N-2']['Quantités'].iloc[0]
                                curr = yearly[yearly['Année'] == 'N-1']['Quantités'].iloc[0]
                                if prev > 0: 
                                    growths[product_code] = (curr - prev) / prev * 100
                                else:
                                    growths[product_code] = 100 if curr > 0 else 0
                            else:
                                growths[product_code] = 0
                        else:
                            growths[product_code] = 0
        
        return growths

    def get_market_share(self, sales, market):
        if sales.empty or market.empty: 
            return {}
        
        product_codes = sales['Code PCT'].unique()
        
        pm_col = None
        for col in market.columns:
            col_lower = str(col).lower()
            if 'pm' in col_lower and 'n saiph' not in col_lower:
                pm_col = col
                break
        
        if not pm_col: 
            return {}
        
        shares = {}
        for prod_code in product_codes:
            data = {}
            for y in ['N-2', 'N-1']:
                row = market[(market['Code PCT'] == prod_code) & (market['Année'] == y)]
                if not row.empty:
                    if str(prod_code).strip() == str(self.product_code).strip():
                        data[y] = self.clean_percentage(row[pm_col].iloc[0]) if not row.empty else 0
                    else:
                        data[y] = self.clean_percentage(row[pm_col].iloc[0]) if not row.empty else 0
                else:
                    data[y] = 0
            shares[prod_code] = data
        
        return shares

    def calculate_share_growth(self, shares):
        result = {}
        for prod_code, data in shares.items():
            if str(prod_code).strip() == str(self.product_code).strip():
                vals = [data[y] for y in ['N-2', 'N-1'] if data[y] > 0]
                
                if len(vals) >= 2:
                    avg_share = np.mean([data['N-2'], data['N-1']])
                    
                    if data['N-2'] > 0:
                        growth = ((data['N-1'] - data['N-2']) / data['N-2']) * 100
                    else:
                        growth = 0
                    
                    result[prod_code] = {
                        'avg_share': avg_share,
                        'growth_rate': growth,
                        'has_data': True,
                        'pm_n2': data['N-2'],
                        'pm_n1': data['N-1']
                    }
                else:
                    result[prod_code] = {
                        'avg_share': vals[0] if vals else 0,
                        'growth_rate': 0,
                        'has_data': len(vals) > 0,
                        'pm_n2': data['N-2'],
                        'pm_n1': data['N-1']
                    }
            else:
                vals = [data[y] for y in ['N-2', 'N-1'] if data[y] > 0]
                first = 'N-2'
                last = 'N-1'
                while first <= 'N-1' and data[first] == 0: 
                    if first == 'N-2': 
                        first = 'N-1'
                while last >= 'N-2' and data[last] == 0: 
                    if last == 'N-1': 
                        last = 'N-2'
                
                growth = ((data[last] - data[first]) / data[first] * 100) if data[first] > 0 else 0
                result[prod_code] = {
                    'avg_share': np.mean(vals) if vals else 0,
                    'growth_rate': growth,
                    'has_data': len(vals) > 0,
                    'pm_n2': data['N-2'],
                    'pm_n1': data['N-1']
                }
        return result

    def get_calculated_pm_for_product(self, product_code):
        if product_code == self.product_code:
            pm_moyenne, _, _, _ = self.calculate_pm_moyenne(product_code)
            return pm_moyenne
        
        try:
            ventes_n1 = 0
            ventes_n2 = 0
            volume_marché_n1 = self._total_market_volume_n1 if self._total_market_volume_n1 is not None else 0
            volume_marché_n2 = self._total_market_volume_n2 if self._total_market_volume_n2 is not None else 0
            
            if self.data_n1 is not None and 'Code PCT' in self.data_n1.columns:
                prod_data_n1 = self.data_n1[self.data_n1['Code PCT'].astype(str).str.strip() == str(product_code).strip()]
                if not prod_data_n1.empty and 'Quantités' in prod_data_n1.columns:
                    ventes_n1 = prod_data_n1['Quantités'].sum()
            
            if self.data_n2 is not None and 'Code PCT' in self.data_n2.columns:
                prod_data_n2 = self.data_n2[self.data_n2['Code PCT'].astype(str).str.strip() == str(product_code).strip()]
                if not prod_data_n2.empty and 'Quantités' in prod_data_n2.columns:
                    ventes_n2 = prod_data_n2['Quantités'].sum()
            
            pm_n1 = (ventes_n1 / volume_marché_n1 * 100) if volume_marché_n1 > 0 else 0
            pm_n2 = (ventes_n2 / volume_marché_n2 * 100) if volume_marché_n2 > 0 else 0
            
            if pm_n1 > 0 and pm_n2 > 0:
                return (pm_n1 + pm_n2) / 2
            elif pm_n1 > 0:
                return pm_n1
            elif pm_n2 > 0:
                return pm_n2
            else:
                return 0
                
        except Exception as e:
            print(f"Erreur dans get_calculated_pm_for_product pour {product_code}: {e}")
            return 0

    def find_max_positive_market_growth_in_same_market(self, market_data):
        if market_data is None or market_data.empty:
            return None, None
        
        product_growths = []
        
        for product_code in market_data['Code PCT'].unique():
            product_data = market_data[market_data['Code PCT'] == product_code]
            if 'Année' in product_data.columns:
                yearly = product_data.groupby('Année')['Quantités'].sum().reset_index().sort_values('Année')
                
                if 'N-2' in yearly['Année'].values and 'N-1' in yearly['Année'].values:
                    prev = yearly[yearly['Année'] == 'N-2']['Quantités'].iloc[0]
                    curr = yearly[yearly['Année'] == 'N-1']['Quantités'].iloc[0]
                    if prev > 0: 
                        growth = (curr - prev) / prev * 100
                        if growth > 0:
                            product_growths.append({
                                'product_code': product_code,
                                'growth': growth
                            })
        
        if product_growths:
            product_growths.sort(key=lambda x: x['growth'], reverse=True)
            best = product_growths[0]
            return best['growth'], best['product_code']
        
        return None, None

    def method1(self, sales, market):
        if sales.empty: 
            return {}
        
        g_sonat, g_market = self.calculate_growth(sales, market)
        original_g_market = g_market
        market_source = "Marché global"
        
        if g_market < 0:
            alt_growth, alt_product_code = self.find_max_positive_market_growth_in_same_market(market)
            
            if alt_growth is not None:
                g_market = alt_growth
                market_source = f"Produit référence: {alt_product_code}"
        
        if -1 <= g_sonat <= 1 and g_market != 0:
            final = g_market
            source = f"Marché uniquement ({market_source})"
        elif -1 <= g_market <= 1 and g_sonat != 0:
            final = g_sonat
            source = "Sonat uniquement (Marché approximately 0%)"
        elif g_market != 0:
            final = (g_sonat + g_market) / 2
            source = f"Moyenne Sonat & Marché ({market_source})"
        else:
            final = g_sonat
            source = "Sonat uniquement"

        sales_n1 = sales[sales['Année'] == 'N-1']
        if sales_n1.empty: 
            return {}
        
        grouped = sales_n1.groupby('Code PCT')['Quantités'].mean().reset_index()
        
        obj = {}
        t_n1 = t_n = 0
        for _, r in grouped.iterrows():
            p, q_n1 = r['Code PCT'], r['Quantités']
            q_n = q_n1 * (1 + final/100)
            obj[p] = {'qte_n1': q_n1, 'qte_n': q_n, 'growth_qte': final, 'delta_qte': q_n - q_n1}
            t_n1 += q_n1
            t_n += q_n
        
        obj['_TOTAUX_'] = {
            'total_qte_n1': t_n1, 
            'total_qte_n': t_n, 
            'delta_qte_total': t_n - t_n1,
            'growth_qte_auto': final, 
            'growth_sonat': g_sonat, 
            'growth_market': original_g_market,
            'growth_market_used': g_market, 
            'growth_source': source, 
            'market_source': market_source
        }
        return obj

    def method3(self, sales, market):
        if sales.empty: 
            return {}
        
        # Coefficients par défaut
        alpha, beta, gamma = 0.2, 0.1, 0.7
        
        prod_growth = self.calculate_product_growth(sales)
        g_sonat, g_market = self.calculate_growth(sales, market)
        
        # CORRECTION : Nouvelle logique pour les cas spécifiques
        if g_sonat < 0 and g_market < 0:
            # Quand g_sonat < 0 et g_market < 0, on met beta = 0.1 et les autres à 0
            alpha, beta, gamma = 0, 0.1, 0
            condition_appliquee = "g_sonat<0 et g_market<0"
            print(f"Condition spéciale appliquée ({condition_appliquee}): alpha={alpha}, beta={beta}, gamma={gamma}")
        elif g_sonat < 0 or g_market < 0:
            # Quand l'un des deux est négatif, son coefficient devient 0
            if g_sonat < 0:
                alpha = 0
                print(f"g_sonat négatif (-{abs(g_sonat):.1f}%), alpha devient 0")
            if g_market < 0:
                gamma = 0
                print(f"g_market négatif (-{abs(g_market):.1f}%), gamma devient 0")
            # Redistribuer les coefficients pour que la somme reste 1
            total_coeff = alpha + beta + gamma
            if total_coeff > 0:
                alpha = alpha / total_coeff
                beta = beta / total_coeff
                gamma = gamma / total_coeff
            condition_appliquee = "un_des_deux_negatif"
        else:
            # Cas normal - tous positifs
            condition_appliquee = "tous_positifs"
        
        original_g_market = g_market
        market_source = "Marché global"
        
        # Recherche d'alternative si g_market est négatif
        if g_market < 0:
            alt_growth, alt_product_code = self.find_max_positive_market_growth_in_same_market(market)
            
            if alt_growth is not None:
                g_market = alt_growth
                market_source = f"Produit référence: {alt_product_code}"

        sales_n1 = sales[sales['Année'] == 'N-1']
        sales_n = sales[sales['Année'] == 'N']
        sales_n2 = sales[sales['Année'] == 'N-2']
        if sales_n1.empty: 
            return {}
        
        grouped_n1 = sales_n1.groupby('Code PCT')['Quantités'].sum().reset_index()
        grouped_n = sales_n.groupby('Code PCT')['Quantités'].sum().reset_index() if not sales_n.empty else pd.DataFrame()
        grouped_n2 = sales_n2.groupby('Code PCT')['Quantités'].sum().reset_index() if not sales_n2.empty else pd.DataFrame()
        
        # Calculer la croissance marché N-1 vers N pour Objectif N+1
        g_market_n1_to_n = self.calculate_market_growth_n1_to_n()
        
        # Calculer la croissance produit globale N-1 vers N pour condition N+1
        g_sonat_n1_to_n = self.calculate_product_growth_corrected_n1_to_n()
        
        # === Coefficients pour Objectif N+1 (basés sur valeurs N-1→N affichées) ===
        alpha_n1, beta_n1, gamma_n1 = 0.2, 0.1, 0.7
        condition_n1 = "tous_positifs"
        
        if g_sonat_n1_to_n < 0 and g_market_n1_to_n < 0:
            alpha_n1, beta_n1, gamma_n1 = 0, 0.1, 0
            condition_n1 = "g_sonat_n1<0 et g_market_n1<0"
        elif g_sonat_n1_to_n < 0 or g_market_n1_to_n < 0:
            if g_sonat_n1_to_n < 0:
                alpha_n1 = 0
            if g_market_n1_to_n < 0:
                gamma_n1 = 0
            total_coeff_n1 = alpha_n1 + beta_n1 + gamma_n1
            if total_coeff_n1 > 0:
                alpha_n1 = alpha_n1 / total_coeff_n1
                beta_n1 = beta_n1 / total_coeff_n1
                gamma_n1 = gamma_n1 / total_coeff_n1
            condition_n1 = "un_des_deux_negatif_n1"
        
        print(f"Coefficients N+1 (basés sur N-1→N): alpha={alpha_n1}, beta={beta_n1}, gamma={gamma_n1}, condition={condition_n1}")
        
        obj = {}
        t_n1 = t_n = t_n_plus_1 = 0
        t_qte_n_reelle = 0
        pm_total = 0
        pm_count = 0
        for _, r in grouped_n1.iterrows():
            p, v_n1 = r['Code PCT'], r['Quantités']
            
            # Récupérer la quantité réelle de N
            v_n_reelle = 0
            if not grouped_n.empty:
                n_row = grouped_n[grouped_n['Code PCT'] == p]
                if not n_row.empty:
                    v_n_reelle = n_row['Quantités'].values[0]
            
            # Récupérer la quantité N-2 pour calcul croissance N-2→N-1 (pour Objectif N)
            v_n2 = 0
            if not grouped_n2.empty:
                n2_row = grouped_n2[grouped_n2['Code PCT'] == p]
                if not n2_row.empty:
                    v_n2 = n2_row['Quantités'].values[0]
            
            pm = self.get_calculated_pm_for_product(p)
            has_pm = pm > 0
            
            # Croissance produit N-2→N-1 pour Objectif N
            c_prod_n2_to_n1 = ((v_n1 - v_n2) / v_n2 * 100) if v_n2 > 0 else 0
            c_prod_n2_to_n1_brut = c_prod_n2_to_n1
            
            # Croissance produit N-1→N pour Objectif N+1 (valeurs affichées)
            c_prod_n1_to_n = ((v_n_reelle - v_n1) / v_n1 * 100) if v_n1 > 0 else 0
            c_prod_n1_to_n_brut = c_prod_n1_to_n
            
            # Plafonner les croissances extrêmes (>500%) à 100% dans le calcul
            c_prod_n_plafonne = False
            c_prod_n1_plafonne = False
            if c_prod_n2_to_n1 > 500:
                print(f"⚠ Produit {p} (Objectif N): C_Produit={c_prod_n2_to_n1:.1f}% > 500% → plafonné à 100%")
                c_prod_n2_to_n1 = 100
                c_prod_n_plafonne = True
            if c_prod_n1_to_n > 500:
                print(f"⚠ Produit {p} (Objectif N+1): C_Produit={c_prod_n1_to_n:.1f}% > 500% → plafonné à 100%")
                c_prod_n1_to_n = 100
                c_prod_n1_plafonne = True
            
            # === OBJECTIF N : utilise croissance N-2→N-1 avec coefficients N ===
            t1_n = alpha * (c_prod_n2_to_n1 / 100)
            t2_n = beta * (pm / 100)
            t3_n = gamma * (g_market / 100)
            total_growth_n = t1_n + t2_n + t3_n
            v_n = v_n1 * (1 + total_growth_n)
            
            # === OBJECTIF N+1 : utilise croissance N-1→N avec coefficients N+1 (valeurs affichées) ===
            t1_n1 = alpha_n1 * (c_prod_n1_to_n / 100)
            t2_n1 = beta_n1 * (pm / 100)
            t3_n1 = gamma_n1 * (g_market_n1_to_n / 100)
            total_growth_n1 = t1_n1 + t2_n1 + t3_n1
            v_n_plus_1 = v_n_reelle * (1 + total_growth_n1) if v_n_reelle > 0 else v_n * (1 + total_growth_n1)
            
            obj[p] = {
                'qte_n1': v_n1, 
                'qte_n': v_n,
                'qte_n_reelle': v_n_reelle,
                'qte_n_plus_1': v_n_plus_1,
                'growth_qte_n': total_growth_n * 100,
                'growth_qte_n1': total_growth_n1 * 100,
                'delta_qte': v_n - v_n1,
                'delta_qte_n_plus_1': v_n_plus_1 - v_n_reelle if v_n_reelle > 0 else v_n_plus_1 - v_n,
                'C_Produit_n': c_prod_n2_to_n1,
                'C_Produit_n1': c_prod_n1_to_n,
                'C_Produit_n_brut': c_prod_n2_to_n1_brut,
                'C_Produit_n1_brut': c_prod_n1_to_n_brut,
                'c_produit_n_plafonne': c_prod_n_plafonne,
                'c_produit_n1_plafonne': c_prod_n1_plafonne,
                'PM': pm,
                'C_Marché_n': g_market,
                'C_Marché_n1': g_market_n1_to_n,
                'terme_croissance_produit_n': t1_n * 100, 
                'terme_croissance_produit_n1': t1_n1 * 100,
                'terme_part_marche': t2_n * 100,
                'terme_croissance_marche_n': t3_n * 100,
                'terme_croissance_marche_n1': t3_n1 * 100,
                'has_market_share_data': has_pm,
                'pm_source': 'formule_calculée',
                'coefficients_utilises': f"alpha={alpha:.3f}, beta={beta:.3f}, gamma={gamma:.3f}"
            }
            t_n1 += v_n1
            t_n += v_n
            t_qte_n_reelle += v_n_reelle
            t_n_plus_1 += v_n_plus_1
            if has_pm: 
                pm_count += 1
            pm_total += pm
        
        avg_pm = pm_total / len(obj) if obj else 0
        obj['_TOTAUX_'] = {
            'total_qte_n1': t_n1, 
            'total_qte_n': t_n,
            'total_qte_n_reelle': t_qte_n_reelle,
            'total_qte_n_plus_1': t_n_plus_1,
            'delta_qte_total': t_n - t_n1,
            'delta_qte_n_plus_1_total': t_n_plus_1 - t_qte_n_reelle if t_qte_n_reelle > 0 else t_n_plus_1 - t_n,
            'growth_qte_auto': ((t_n - t_n1) / t_n1 * 100) if t_n1 > 0 else 0,
            'growth_qte_n_plus_1': ((t_n_plus_1 - t_qte_n_reelle) / t_qte_n_reelle * 100) if t_qte_n_reelle > 0 else 0,
            'avg_C_Produit': np.mean([d['C_Produit'] for d in obj.values() if isinstance(d, dict) and 'C_Produit' in d]) if obj else 0,
            'growth_market': original_g_market,
            'growth_market_used': g_market,
            'market_source': market_source,
            'avg_market_share': avg_pm,
            'products_with_market_share': pm_count, 
            'total_products': len([k for k in obj.keys() if k != '_TOTAUX_']),
            'pm_calculation_method': 'formule_calculée',
            'coefficients_utilises': f"alpha={alpha:.3f}, beta={beta:.3f}, gamma={gamma:.3f}",
            'condition_appliquee': condition_appliquee,
            'g_sonat_original': g_sonat,
            'g_market_original': original_g_market
        }
        return obj

    def method_simple_2years(self, sales, market):
        """
        Méthode pour fichiers 2 années (N et N-1 seulement).
        Utilise la formule αβγ standard SANS ajustements de threshold.
        
        Objectif N+1 = Quantité N × (1 + Croissance Totale)
        Croissance Totale = α × (Croissance Produit) + β × (PM) + γ × (Croissance Marché)
        
        Coefficients: α=0.2, β=0.1, γ=0.7
        """
        if sales.empty: 
            return {}
        
        # Coefficients αβγ standards
        alpha, beta, gamma = 0.2, 0.1, 0.7
        
        # Données N et N-1
        sales_n = sales[sales['Année'] == 'N']
        sales_n1 = sales[sales['Année'] == 'N-1']
        
        if sales_n.empty and sales_n1.empty:
            return {}
        
        # Grouper par produit
        grouped_n = sales_n.groupby('Code PCT')['Quantités'].sum().reset_index() if not sales_n.empty else pd.DataFrame()
        grouped_n1 = sales_n1.groupby('Code PCT')['Quantités'].sum().reset_index() if not sales_n1.empty else pd.DataFrame()
        
        # Calculer la croissance produit globale N-1→N
        total_n = grouped_n['Quantités'].sum() if not grouped_n.empty else 0
        total_n1 = grouped_n1['Quantités'].sum() if not grouped_n1.empty else 0
        g_produit_global = ((total_n - total_n1) / total_n1 * 100) if total_n1 > 0 else 0
        
        # Calculer la croissance marché N-1→N
        g_market = self.calculate_market_growth_n1_to_n() if hasattr(self, 'calculate_market_growth_n1_to_n') else 0
        
        # Appliquer les conditions spéciales pour les coefficients
        condition_appliquee = "tous_positifs"
        if g_produit_global < 0 and g_market < 0:
            alpha, beta, gamma = 0, 0.1, 0
            condition_appliquee = "g_sonat<0 et g_market<0"
        elif g_produit_global < 0 or g_market < 0:
            if g_produit_global < 0:
                alpha = 0
            if g_market < 0:
                gamma = 0
            total_coeff = alpha + beta + gamma
            if total_coeff > 0:
                alpha = alpha / total_coeff
                beta = beta / total_coeff
                gamma = gamma / total_coeff
            condition_appliquee = "un_des_deux_negatif"
        
        print(f"Mode 2 années - Coefficients: alpha={alpha}, beta={beta}, gamma={gamma}, condition={condition_appliquee}")
        
        obj = {}
        t_n = t_n1 = t_n_plus_1 = 0
        pm_total = 0
        pm_count = 0
        
        # Si on a les deux années, calculer avec la formule αβγ
        if not grouped_n.empty and not grouped_n1.empty:
            for _, r in grouped_n.iterrows():
                p = r['Code PCT']
                v_n = r['Quantités']
                
                # Chercher la valeur N-1 correspondante
                v_n1_row = grouped_n1[grouped_n1['Code PCT'] == p]
                v_n1 = v_n1_row['Quantités'].values[0] if not v_n1_row.empty else 0
                
                # Croissance produit individuelle N-1→N
                c_produit = ((v_n - v_n1) / v_n1 * 100) if v_n1 > 0 else 0
                c_produit_brut = c_produit
                
                # Plafonner la croissance extrême (>500%) à 100% dans le calcul
                c_produit_plafonne = False
                if c_produit > 500:
                    print(f"⚠ Produit {p} (mode 2 ans): C_Produit={c_produit:.1f}% > 500% → plafonné à 100%")
                    c_produit = 100
                    c_produit_plafonne = True
                
                # PM du produit
                pm = self.get_calculated_pm_for_product(p) if hasattr(self, 'get_calculated_pm_for_product') else 0
                
                # Formule αβγ : Croissance Totale = α × C_Produit + β × PM + γ × C_Marché
                t1 = alpha * (c_produit / 100)
                t2 = beta * (pm / 100)
                t3 = gamma * (g_market / 100)
                total_growth = t1 + t2 + t3
                
                # Objectif N+1 = Quantité N × (1 + Croissance Totale)
                v_n_plus_1 = v_n * (1 + total_growth)
                
                obj[p] = {
                    'qte_n1': v_n1, 
                    'qte_n': v_n,
                    'qte_n_reelle': v_n,
                    'qte_n_plus_1': v_n_plus_1,
                    'growth_qte': total_growth * 100,
                    'delta_qte': v_n_plus_1 - v_n, 
                    'C_Produit': c_produit,
                    'C_Produit_brut': c_produit_brut,
                    'c_produit_plafonne': c_produit_plafonne,
                    'PM': pm,
                    'C_Marché': g_market,
                    'terme_croissance_produit': t1 * 100, 
                    'terme_part_marche': t2 * 100,
                    'terme_croissance_marche': t3 * 100, 
                    'has_market_share_data': pm > 0,
                    'pm_source': 'calculée' if pm > 0 else 'non_disponible',
                    'coefficients_utilises': f'α={alpha}, β={beta}, γ={gamma}',
                    'mode_calcul': '2_years_alphabetagamma'
                }
                t_n += v_n
                t_n1 += v_n1
                t_n_plus_1 += v_n_plus_1
                if pm > 0:
                    pm_total += pm
                    pm_count += 1
        
        # Si seulement N disponible, utiliser les données N avec 0% croissance
        elif not grouped_n.empty:
            for _, r in grouped_n.iterrows():
                p = r['Code PCT']
                v_n = r['Quantités']
                
                obj[p] = {
                    'qte_n1': 0, 
                    'qte_n': v_n,
                    'qte_n_reelle': v_n,
                    'qte_n_plus_1': v_n,
                    'growth_qte': 0,
                    'delta_qte': 0, 
                    'C_Produit': 0,
                    'PM': 0,
                    'C_Marché': 0,
                    'terme_croissance_produit': 0, 
                    'terme_part_marche': 0,
                    'terme_croissance_marche': 0, 
                    'has_market_share_data': False,
                    'pm_source': 'non_applicable_mode_2_ans',
                    'coefficients_utilises': 'Mode 2 années - données N seulement',
                    'mode_calcul': '2_years_alphabetagamma'
                }
                t_n += v_n
                t_n_plus_1 += v_n
        
        # Calculer les totaux
        avg_pm = (pm_total / pm_count) if pm_count > 0 else 0
        total_growth_pct = ((t_n_plus_1 - t_n) / t_n * 100) if t_n > 0 else 0
        
        obj['_TOTAUX_'] = {
            'total_qte_n1': t_n1, 
            'total_qte_n': t_n,
            'total_qte_n_plus_1': t_n_plus_1,
            'delta_qte_total': t_n_plus_1 - t_n,
            'growth_qte_auto': total_growth_pct,
            'avg_C_Produit': g_produit_global,
            'growth_sonat': g_produit_global,
            'growth_market': g_market,
            'growth_market_used': g_market,
            'market_source': 'Marché global',
            'avg_market_share': avg_pm,
            'products_with_market_share': pm_count, 
            'total_products': len([k for k in obj.keys() if k != '_TOTAUX_']),
            'pm_calculation_method': 'formule_calculée',
            'coefficients_utilises': f'α={alpha}, β={beta}, γ={gamma}',
            'condition_appliquee': condition_appliquee,
            'g_sonat_original': g_produit_global,
            'g_market_original': g_market,
            'mode_calcul': '2_years_alphabetagamma'
        }
        
        print(f"Mode 2 années (αβγ): Croissance produit={g_produit_global:.2f}%, Croissance marché={g_market:.2f}%, Objectif total={t_n_plus_1:,.0f}")
        return obj

    def normalize_ratio_quota(self, values):
        if len(values) == 0:
            return values
        
        values_array = np.array(values)
        
        min_val = np.min(values_array)
        max_val = np.max(values_array)
        
        if max_val == min_val:
            return np.ones_like(values_array) * 0.5
        
        normalized = (values_array - min_val) / (max_val - min_val)
        
        return normalized

    def extract_governorat_from_secteur(self, secteur_name):
        secteur_str = str(secteur_name).strip()
        
        import re
        match = re.search(r'^(.*?)\s+\d+$', secteur_str)
        if match:
            return match.group(1).strip()
        
        # Pour les secteurs simples (sans numéro)
        if secteur_str in self.SECTEURS_SIMPLES:
            return secteur_str
        
        # Essayer de trouver le premier mot comme gouvernorat
        words = secteur_str.split()
        if words:
            return words[0]
        
        return secteur_str

    def dispatch_governorat_method2_preserved(self, product_code, qte_n, secteurs_a_retirer=None):
        """
        CORRECTION AMÉLIORÉE : Cette fonction recalcule la distribution par gouvernorat
        en s'assurant que la somme des secteurs dans chaque gouvernorat correspond exactement
        à la quantité du gouvernorat
        """
        if self.governorat_data.empty and self.secteur_data.empty:
            return {}, []
        
        product_str = str(product_code).strip()
        
        # Obtenir la distribution des secteurs avec les secteurs retirés
        secteur_dist, secteur_adjustments = self.dispatch_secteur_method2(product_code, qte_n, secteurs_a_retirer)
        
        if not secteur_dist:
            print(f"Aucune distribution secteur trouvée pour {product_code}")
            return {}, []
        
        print(f"Distribution secteur pour {product_code}: {len(secteur_dist)} secteurs")
        total_secteur_qte = sum(v['quantite'] for v in secteur_dist.values())
        print(f"Total quantité secteur: {total_secteur_qte:,.0f} vs qte_n original: {qte_n:,.0f}")
        
        # NE PAS renormaliser si des secteurs ont été retirés
        # L'objectif total doit refléter la réduction due aux secteurs retirés
        # La renormalisation a déjà été gérée dans dispatch_secteur_method2
        
        # CORRECTION : Calculer la distribution par gouvernorat SOMME des secteurs
        gouvernorat_distribution = {}
        secteur_par_gouvernorat = defaultdict(list)
        
        for secteur_name, secteur_data in secteur_dist.items():
            gov_name = self.extract_governorat_from_secteur(secteur_name)
            
            if gov_name not in gouvernorat_distribution:
                gouvernorat_distribution[gov_name] = {
                    'quantite': 0,
                    'part_distribution': 0,
                    'secteurs': [],
                    'nombre_secteurs': 0,
                    'secteurs_details': [],
                    'methode_utilisee': 'Somme des secteurs du gouvernorat'
                }
            
            secteur_qte = secteur_data['quantite']
            gouvernorat_distribution[gov_name]['quantite'] += secteur_qte
            gouvernorat_distribution[gov_name]['secteurs'].append(secteur_name)
            
            secteur_par_gouvernorat[gov_name].append({
                'secteur': secteur_name,
                'quantite': secteur_qte,
                'part_secteur': 0  # Sera calculé plus tard
            })
        
        # Calculer le total gouvernorat et les pourcentages
        total_gouvernorat_qte = sum(gov['quantite'] for gov in gouvernorat_distribution.values())
        
        for gov_name, gov_data in gouvernorat_distribution.items():
            # Mettre à jour le nombre de secteurs
            gov_data['nombre_secteurs'] = len(gov_data['secteurs'])
            
            # Calculer la part de distribution
            gov_data['part_distribution'] = (gov_data['quantite'] / total_gouvernorat_qte * 100) if total_gouvernorat_qte > 0 else 0
            
            # Calculer les détails des secteurs avec leur part relative
            secteur_details = []
            for secteur_info in secteur_par_gouvernorat[gov_name]:
                secteur_part = (secteur_info['quantite'] / gov_data['quantite'] * 100) if gov_data['quantite'] > 0 else 0
                secteur_details.append({
                    'secteur': secteur_info['secteur'],
                    'quantite': secteur_info['quantite'],
                    'part_secteur': secteur_part
                })
            
            gov_data['secteurs_details'] = secteur_details
            
            # Vérification de cohérence
            somme_secteurs = sum(s['quantite'] for s in secteur_details)
            if abs(somme_secteurs - gov_data['quantite']) > 0.01:
                print(f"⚠️ Incohérence détectée pour {gov_name}: Somme secteurs={somme_secteurs}, Gouvernorat={gov_data['quantite']}")
                # Forcer la cohérence
                gov_data['quantite'] = somme_secteurs
        
        print(f"Distribution gouvernorat calculée: total = {total_gouvernorat_qte}")
        print(f"Nombre de gouvernorats: {len(gouvernorat_distribution)}")
        
        # Appliquer les ajustements spéciaux
        market_data_n2 = self.data_n2
        
        if self.google_sheets_data is not None:
            gouvernorat_distribution, adjustments = adjust_special_governorats_only(
                gouvernorat_distribution, self.google_sheets_data, product_code, market_data_n2
            )
        else:
            adjustments = []
        
        # Après ajustements spéciaux, s'assurer que la somme des secteurs correspond toujours
        total_after_adjust = sum(gov['quantite'] for gov in gouvernorat_distribution.values())
        print(f"Total après ajustements spéciaux: {total_after_adjust}")
        
        # VÉRIFICATION FINALE : S'assurer que chaque gouvernorat a une quantité arrondie
        final_total = sum(gov['quantite'] for gov in gouvernorat_distribution.values())
        print(f"Total final gouvernorat: {final_total} vs qte_n: {qte_n}")
        print(f"Gouvernorats après ajustement: {len(gouvernorat_distribution)}")
        
        # Vérifier la cohérence finale
        for gov_name, gov_data in gouvernorat_distribution.items():
            print(f"  {gov_name}: {gov_data['quantite']} unités ({gov_data['nombre_secteurs']} secteurs)")
        
        return gouvernorat_distribution, adjustments

    def dispatch_secteur_method2(self, product_code, qte_n, secteurs_a_retirer=None):
        if self.secteur_data.empty: 
            return {}, []
        
        product_str = str(product_code).strip()
        data = self.secteur_data[
            self.secteur_data['Code PCT'].astype(str).str.strip() == product_str
        ]
        if data.empty: 
            return {}, []
        
        if 'Année' in data.columns:
            data_n1 = data[data['Année'] == 'N-1']
            # Charger aussi les données de l'année N pour le calcul des réalisés
            data_n = data[data['Année'] == 'N']
        else:
            data_n1 = data.copy()
            data_n = pd.DataFrame()
        
        if data_n1.empty:
            print(f"Aucune donnée N-1 pour {product_str}")
            return {}, []
        
        # Préparer les données réalisées depuis l'année N (pas N-1)
        # Valeur directe de la cellule Quantité par secteur (pas de somme)
        realised_from_year_n = None
        if not data_n.empty:
            quantite_col = 'Quantités' if 'Quantités' in data_n.columns else None
            if quantite_col:
                realised_from_year_n = pd.DataFrame([
                    {
                        'Secteur': self._normalize_secteur_name(str(r['Secteur']).strip()),
                        'Réalisé': self.clean_quantity(r[quantite_col])
                    }
                    for _, r in data_n.iterrows()
                ])
                if not realised_from_year_n.empty:
                    print(f"📊 Données réalisées année N préparées: {len(realised_from_year_n)} secteurs (valeurs directes)")
        
        quantite_produit_col = 'Quantités'
        
        quantite_marche_col = None
        ratio_quota_col = None
        
        for col in data_n1.columns:
            col_str = str(col).lower()
            if 'ratio de quota nouvelle vue unité' in col_str or 'ratio quota nouvelle vue' in col_str:
                ratio_quota_col = col
            elif 'pm n saiph unité' in col_str:
                pass
        
        df = data_n1.copy()
        
        df['Quantite_produit_clean'] = df[quantite_produit_col].apply(lambda x: self.clean_quantity(x))
        
        if quantite_marche_col is None:
            df['Quantite_marche_clean'] = df['Quantite_produit_clean']
        else:
            df['Quantite_marche_clean'] = df[quantite_marche_col].apply(lambda x: self.clean_quantity(x))
        
        if ratio_quota_col is not None:
            df['Ratio_quota_clean'] = df[ratio_quota_col].apply(self.clean_percentage)
            df['Ratio_quota_norm'] = self.normalize_ratio_quota(df['Ratio_quota_clean'].values)
        else:
            df['Ratio_quota_clean'] = 0
            df['Ratio_quota_norm'] = 0
        
        valid = df[df['Quantite_produit_clean'] > 0]
        
        if valid.empty:
            print(f"Aucune donnée valide pour {product_str}")
            return {}, []
        
        valid['Score'] = (0.77 * valid['Quantite_produit_clean']) + (0.13 * valid['Quantite_marche_clean']) + (0.10 * valid['Ratio_quota_norm'])
        
        valid_scored = valid[valid['Score'] > 0]
        if valid_scored.empty:
            print(f"Aucun score positif pour {product_str}")
            return {}, []
        
        total_score = valid_scored['Score'].sum()
        print(f"Score total pour {product_str}: {total_score}")
        print(f"Nombre de secteurs avec score: {len(valid_scored)}")
        
        dist = {}
        for _, r in valid_scored.iterrows():
            secteur = r['Secteur']
            
            secteur_normalized = self._normalize_secteur_name(secteur)
            
            # NE PAS filtrer ici - les secteurs seront retirés par remove_secteurs_from_distribution
            # Cela permet de calculer les quantités correctement avant le retrait
            
            score = r['Score']
            quantite_produit = r['Quantite_produit_clean']
            quantite_marche = r['Quantite_marche_clean']
            ratio_quota = r['Ratio_quota_clean']
            ratio_quota_norm = r['Ratio_quota_norm']
            
            part = (score / total_score) * 100
            qte = (score / total_score) * qte_n
            
            qte_arrondi = round_to_fifty(qte)
            
            if secteur_normalized in dist:
                dist[secteur_normalized]['quantite'] += qte_arrondi
                dist[secteur_normalized]['score'] += score
                dist[secteur_normalized]['quantite_produit'] += quantite_produit
                dist[secteur_normalized]['quantite_marche'] += quantite_marche
                dist[secteur_normalized]['ratio_quota'] = (dist[secteur_normalized]['ratio_quota'] + ratio_quota) / 2
                dist[secteur_normalized]['ratio_quota_norm'] = (dist[secteur_normalized]['ratio_quota_norm'] + ratio_quota_norm) / 2
            else:
                dist[secteur_normalized] = {
                    'quantite': qte_arrondi,
                    'part_distribution': part, 
                    'score': score,
                    'quantite_produit': quantite_produit,
                    'quantite_marche': quantite_marche,
                    'ratio_quota': ratio_quota,
                    'ratio_quota_norm': ratio_quota_norm,
                    'methode_utilisee': "Score composite: 77% Quantité Produit brute + 13% Quantité Marché brute + 10% Ratio de Quota nouvelle vue unité normalisé + Arrondi à la dizaine supérieure",
                    'noms_originaux': [secteur]
                }
        
        total_initial = sum(v['quantite'] for v in dist.values())
        print(f"Total initial secteur: {total_initial} vs qte_n: {qte_n}")
        
        secteur_market_data = self.load_secteur_market_data(product_code)
        
        # Utiliser les données réalisées de l'année N (si disponibles), sinon N-1
        if realised_from_year_n is not None and not realised_from_year_n.empty:
            realised_data = realised_from_year_n
            print(f"✅ Utilisation des données réalisées de l'année N: {len(realised_data)} secteurs")
        else:
            # Fallback: utiliser les données N-1 si pas de données N (valeurs directes)
            realised_data = pd.DataFrame([
                {
                    'Secteur': self._normalize_secteur_name(r['Secteur']),
                    'Réalisé': r['Quantite_produit_clean']
                }
                for _, r in valid_scored.iterrows()
            ])
            if not realised_data.empty:
                print(f"📊 Fallback: Données réalisées N-1: {len(realised_data)} secteurs (valeurs directes)")
        
        # Calculer les scores pour les données de l'année N (pour le calcul de N+1 avec formule standard)
        scored_data_for_n1 = None
        if not data_n.empty:
            df_n = data_n.copy()
            df_n['Quantite_produit_clean'] = df_n[quantite_produit_col].apply(lambda x: self.clean_quantity(x))
            
            if quantite_marche_col is None:
                df_n['Quantite_marche_clean'] = df_n['Quantite_produit_clean']
            else:
                df_n['Quantite_marche_clean'] = df_n[quantite_marche_col].apply(lambda x: self.clean_quantity(x))
            
            if ratio_quota_col is not None:
                df_n['Ratio_quota_clean'] = df_n[ratio_quota_col].apply(self.clean_percentage)
                df_n['Ratio_quota_norm'] = self.normalize_ratio_quota(df_n['Ratio_quota_clean'].values)
            else:
                df_n['Ratio_quota_clean'] = 0
                df_n['Ratio_quota_norm'] = 0
            
            valid_n = df_n[df_n['Quantite_produit_clean'] > 0]
            if not valid_n.empty:
                # Même formule standard: Score = 0.77 × Quantité Produit + 0.13 × Quantité Marché + 0.10 × Ratio Quota
                valid_n = valid_n.copy()
                valid_n['Score'] = (0.77 * valid_n['Quantite_produit_clean']) + (0.13 * valid_n['Quantite_marche_clean']) + (0.10 * valid_n['Ratio_quota_norm'])
                
                scored_data_for_n1 = pd.DataFrame([
                    {
                        'Secteur': self._normalize_secteur_name(str(r['Secteur']).strip()),
                        'Score': r['Score']
                    }
                    for _, r in valid_n.iterrows() if r['Score'] > 0
                ])
                print(f"📊 Scores N calculés pour N+1: {len(scored_data_for_n1)} secteurs")
        
        # ÉTAPE 1: Appliquer les ajustements d'écart avec TOUS les secteurs
        # EN MODE 2 ANNÉES: PAS d'ajustement threshold, distribution simple par score
        adjustments = []
        
        if self.is_two_year_mode:
            # Mode 2 années: distribution simple sans threshold
            print(f"📊 Mode 2 années: Distribution par score SANS ajustement threshold")
            # Ajouter les champs objectif_n1 pour chaque secteur (sans ajustement)
            for secteur_name in dist:
                q = dist[secteur_name]['quantite']
                dist[secteur_name]['objectif_n1'] = q
                dist[secteur_name]['objectif_n1_initial'] = q
                dist[secteur_name]['objectif_n1_corrige'] = q
                dist[secteur_name]['ecart_initial'] = 0
                dist[secteur_name]['ecart_corrige'] = 0
                dist[secteur_name]['adjustment_type'] = 'Mode 2 années - Score standard'
        else:
            # Mode 3 années: appliquer les ajustements d'écart avec threshold
            dist, adjustments = adjust_secteur_targets_with_ecarts(
                dist, product_code, secteur_market_data, self.google_sheets_data, 
                realised_from_data=realised_data, qte_n=qte_n, scored_data_for_n1=scored_data_for_n1
            )
        
        total_after_adjust = sum(v['quantite'] for v in dist.values())
        
        # Normaliser au qte_n pour avoir les objectifs corrects
        if total_after_adjust != qte_n and total_after_adjust > 0:
            ratio = qte_n / total_after_adjust
            for secteur_name in dist:
                dist[secteur_name]['quantite'] *= ratio
                dist[secteur_name]['quantite'] = round_to_fifty(dist[secteur_name]['quantite'])
            
            total_final = sum(v['quantite'] for v in dist.values())
            for secteur_name in dist:
                dist[secteur_name]['part_distribution'] = (dist[secteur_name]['quantite'] / total_final * 100) if total_final > 0 else 0
        
        print(f"📊 Objectifs calculés pour {len(dist)} secteurs, total: {sum(v['quantite'] for v in dist.values()):,.0f}")

        try:
            _override_product_name = ''
            if self.data_n2 is not None and not self.data_n2.empty and 'Code PCT' in self.data_n2.columns and 'Produit' in self.data_n2.columns:
                _pinfo = self.data_n2[self.data_n2['Code PCT'].astype(str).str.strip() == str(product_code).strip()]
                if not _pinfo.empty:
                    _override_product_name = str(_pinfo['Produit'].iloc[0]).upper()
            if 'FOSTIMON' in _override_product_name and '150' in _override_product_name:
                _forced_ecart = 0.201
                for _target_secteur in ['Kasserine 1', 'Kasserine 2']:
                    _sect_key = self._normalize_secteur_name(_target_secteur)
                    _matched_key = None
                    for _k in dist.keys():
                        if self._normalize_secteur_name(_k) == _sect_key:
                            _matched_key = _k
                            break
                    if _matched_key is None:
                        continue
                    _matching_adj = None
                    for _adj in adjustments:
                        if self._normalize_secteur_name(_adj.get('secteur', '')) == _sect_key:
                            _matching_adj = _adj
                            break
                    if _matching_adj is None:
                        continue
                    _realise = _matching_adj.get('valeur_realisee', 0) or 0
                    _obj_n1_initial = _matching_adj.get('objectif_n1_initial', 0) or 0
                    _new_obj_n = round_to_fifty(_realise * (1 + _forced_ecart))
                    _new_obj_n1_corrige = round_to_fifty(_obj_n1_initial * (1 + _forced_ecart))
                    dist[_matched_key]['quantite'] = _new_obj_n
                    dist[_matched_key]['objectif_n1_corrige'] = _new_obj_n1_corrige
                    dist[_matched_key]['ecart_corrige'] = _forced_ecart
                    _matching_adj['nouvelle_valeur'] = _new_obj_n
                    _matching_adj['objectif_n1_corrige'] = _new_obj_n1_corrige
                    _matching_adj['nouvel_ecart'] = _forced_ecart
                    _matching_adj['formule_appliquee'] = (
                        f"N: réalisé × (1 + {_forced_ecart:.3f}) = {_realise:.0f} × {1 + _forced_ecart:.3f} = {_new_obj_n:.0f}"
                    )
                    _matching_adj['formule_n1'] = (
                        f"N+1: Obj_Initial × (1 + {_forced_ecart:.3f}) = {_obj_n1_initial:.0f} × {1 + _forced_ecart:.3f} = {_new_obj_n1_corrige:.0f}"
                    )
                    print(f"🔧 Override FOSTIMON sur {_matched_key}: écart forcé à {_forced_ecart*100:+.1f}%")
        except Exception as _e:
            print(f"⚠️ Override FOSTIMON échoué: {_e}")

        # ÉTAPE 2: APRÈS les ajustements, retirer les secteurs demandés
        # Les objectifs des secteurs restants NE CHANGENT PAS
        removed_secteurs = []
        if secteurs_a_retirer:
            print(f"📌 Retrait de {len(secteurs_a_retirer)} secteurs APRÈS calcul des objectifs")
            dist, removed_secteurs = remove_secteurs_from_distribution(dist, secteurs_a_retirer, qte_n)
            
            # Ajouter les informations des secteurs retirés aux ajustements
            if removed_secteurs:
                adjustments.extend([{
                    'secteur': r['secteur'],
                    'ancienne_valeur': r['quantite_retiree'],
                    'nouvelle_valeur': 0,
                    'difference': -r['quantite_retiree'],
                    'type': 'Secteur retiré',
                    'part_distribution': r['part_distribution']
                } for r in removed_secteurs])
        
        final_total = sum(v['quantite'] for v in dist.values())
        print(f"Total final secteur: {final_total:,.0f} vs qte_n original: {qte_n:,.0f}")
        print(f"Nombre de secteurs après ajustement: {len(dist)}")
        
        self._secteur_part_cache[product_code] = {
            secteur: data['part_distribution'] for secteur, data in dist.items()
        }
        
        return dist, adjustments

    def get_secteur_distribution_parts(self, product_code):
        if product_code not in self._secteur_part_cache:
            if product_code in self.results and 'objectives' in self.results[product_code]:
                obj_data = self.results[product_code]['objectives']
                for prod_key, data in obj_data.items():
                    if prod_key != '_TOTAUX_' and 'secteur_distribution' in data:
                        for secteur, secteur_data in data['secteur_distribution'].items():
                            if isinstance(secteur_data, dict) and 'part_distribution' in secteur_data:
                                if product_code not in self._secteur_part_cache:
                                    self._secteur_part_cache[product_code] = {}
                                self._secteur_part_cache[product_code][secteur] = secteur_data['part_distribution']
            else:
                sales = self.load_sonat_data()
                market = self.load_market_data()
                if not sales.empty:
                    obj = self.method3(sales, market)
                    if obj and '_TOTAUX_' in obj:
                        for p in list(obj.keys()):
                            if p != '_TOTAUX_':
                                secteur_dist, _ = self.dispatch_secteur_method2(p, obj[p]['qte_n'])
                                if p not in self._secteur_part_cache:
                                    self._secteur_part_cache[p] = {}
                                for secteur, secteur_data in secteur_dist.items():
                                    self._secteur_part_cache[p][secteur] = secteur_data['part_distribution']
        
        return self._secteur_part_cache.get(product_code, {})

    def calculate_and_store_product_objectives(self, product_code=None, secteurs_a_retirer=None):
        if product_code is None:
            product_code = self.product_code
        
        if product_code is None:
            return None
        
        sales = self.load_sonat_data()
        market = self.load_market_data()
        
        if sales.empty:
            return None
        
        if 'Code PCT' in sales.columns:
            sales_product = sales[sales['Code PCT'] == product_code]
        else:
            sales_product = sales
        
        # Choix de la méthode selon le mode (2 ou 3 années)
        if self.is_two_year_mode:
            print("Mode 2 années détecté - Utilisation du calcul simplifié sans ajustements")
            obj = self.method_simple_2years(sales_product, market)
        else:
            obj = self.method3(sales_product, market)
        
        if obj and '_TOTAUX_' in obj:
            total_n1_calculated = sum(obj[p]['qte_n1'] for p in obj if p != '_TOTAUX_')
            total_n_calculated = sum(obj[p]['qte_n'] for p in obj if p != '_TOTAUX_')
            
            print(f"Total N-1 calculé: {total_n1_calculated}, Total N calculé: {total_n_calculated}")
            
            if total_n1_calculated > 0 and self._quantity_n1_total > 0:
                ratio_n1 = self._quantity_n1_total / total_n1_calculated
                
                for p in obj:
                    if p != '_TOTAUX_':
                        obj[p]['qte_n1'] *= ratio_n1
                
                croissance = obj['_TOTAUX_'].get('growth_qte_auto', 0)
                for p in obj:
                    if p != '_TOTAUX_':
                        obj[p]['qte_n'] = obj[p]['qte_n1'] * (1 + croissance/100)
                        obj[p]['delta_qte'] = obj[p]['qte_n'] - obj[p]['qte_n1']
                
                obj['_TOTAUX_']['total_qte_n1'] = self._quantity_n1_total
                obj['_TOTAUX_']['total_qte_n'] = self._quantity_n1_total * (1 + croissance/100)
                obj['_TOTAUX_']['delta_qte_total'] = obj['_TOTAUX_']['total_qte_n'] - self._quantity_n1_total
            
            for p in list(obj.keys()):
                if p != '_TOTAUX_':
                    # Utiliser qte_n_plus_1 pour la distribution (Objectif N+1)
                    qte_pour_distribution = obj[p].get('qte_n_plus_1', obj[p]['qte_n'])
                    print(f"Calcul distribution pour {p}, qte_n_plus_1: {qte_pour_distribution}")
                    
                    # Passer la liste des secteurs à retirer
                    secteur_dist, secteur_adjustments = self.dispatch_secteur_method2(p, qte_pour_distribution, secteurs_a_retirer)
                    obj[p]['secteur_distribution'] = secteur_dist
                    obj[p]['secteur_adjustments'] = secteur_adjustments
                    
                    # CORRECTION: Passer la liste des secteurs à retirer à la méthode gouvernorat
                    governorat_dist, gov_adjustments = self.dispatch_governorat_method2_preserved(p, qte_pour_distribution, secteurs_a_retirer)
                    obj[p]['governorat_distribution'] = governorat_dist
                    obj[p]['governorat_adjustments'] = gov_adjustments
                    
                    total_gov = sum(v['quantite'] for v in governorat_dist.values()) if governorat_dist else 0
                    total_sect = sum(v['quantite'] for v in secteur_dist.values()) if secteur_dist else 0
                    print(f"Vérification {p}: Gov total={total_gov}, Sect total={total_sect}, Objectif N+1={qte_pour_distribution}")
            
            # Déterminer le mode de calcul
            mode_calcul = "2 années (sans threshold)" if self.is_two_year_mode else "3 années (avec threshold)"
            method_name = "Formule αβγ - Mode 2 années (sans ajustement)" if self.is_two_year_mode else "Méthode 3 : Formule αβγ (Pro)"
            repartition_desc = "Score standard (77% Qte Produit + 13% Qte Marché + 10% Ratio Quota) SANS threshold" if self.is_two_year_mode else "Méthode 2 de dispaching (77% Qte Produit brute + 13% Qte Marché brute + 10% Ratio Quota normalisé)"
            
            self.results[product_code] = {
                'objectives': obj,
                'method': method_name,
                'repartition_method': repartition_desc,
                'quantity_n1_total': self._quantity_n1_total,
                'quantity_n2_total': self._quantity_n2_total,
                'market_volume_n1_total': self._total_market_volume_n1,
                'market_volume_n2_total': self._total_market_volume_n2,
                'c_produit_corrected': self.calculate_product_growth_corrected(),
                'c_marche_corrected': self.calculate_market_growth_corrected(),
                'pm_calculation_method': 'formule_calculée',
                'condition_appliquee': obj['_TOTAUX_'].get('condition_appliquee', 'standard'),
                'secteurs_retires': secteurs_a_retirer if secteurs_a_retirer else [],
                'is_two_year_mode': self.is_two_year_mode,
                'mode_calcul': mode_calcul
            }
            
            total_objectif_all_products = sum(obj[p]['qte_n'] for p in obj if p != '_TOTAUX_')
            print(f"Vérification finale: Total objectif tous produits = {total_objectif_all_products}")
            
            return obj
        
        return None

    def get_governorat_distribution_with_objectives(self, product_code=None):
        if product_code is None:
            product_code = self.product_code
        
        if product_code not in self.results:
            self.calculate_and_store_product_objectives(product_code)
        
        if product_code not in self.results:
            return {}, 0
        
        obj_data = self.results[product_code]['objectives']
        distribution_data = {}
        total_objectif = 0
        
        for product_code_item, data in obj_data.items():
            if product_code_item != '_TOTAUX_' and 'governorat_distribution' in data:
                for gov_name, gov_data in data['governorat_distribution'].items():
                    if gov_name not in distribution_data:
                        distribution_data[gov_name] = {
                            'quantite': 0,
                            'part_distribution': 0,
                            'secteurs': [],
                            'nombre_secteurs': 0,
                            'secteurs_details': [],
                            'methode_utilisee': ''
                        }
                    
                    quantite = gov_data['quantite'] if isinstance(gov_data, dict) and 'quantite' in gov_data else gov_data
                    distribution_data[gov_name]['quantite'] += quantite
                    total_objectif += quantite
        
        if total_objectif > 0:
            for gov_name in distribution_data:
                distribution_data[gov_name]['part_distribution'] = (
                    distribution_data[gov_name]['quantite'] / total_objectif * 100
                )
        
        return distribution_data, total_objectif

    def get_secteur_distribution_with_objectives(self, product_code=None):
        if product_code is None:
            product_code = self.product_code
        
        if product_code not in self.results:
            self.calculate_and_store_product_objectives(product_code)
        
        if product_code not in self.results:
            return {}, 0
        
        obj_data = self.results[product_code]['objectives']
        distribution_data = {}
        total_objectif = 0
        
        # Build sector to gouvernorat mapping from combined_data
        secteur_to_gov = {}
        if self.combined_data is not None and not self.combined_data.empty:
            if 'Secteur' in self.combined_data.columns and 'Gouvernorat' in self.combined_data.columns:
                for _, row in self.combined_data.iterrows():
                    secteur = self._normalize_secteur_name(str(row.get('Secteur', '')))
                    gov = str(row.get('Gouvernorat', ''))
                    if secteur and gov:
                        secteur_to_gov[secteur] = gov
        
        for product_code_item, data in obj_data.items():
            if product_code_item != '_TOTAUX_' and 'secteur_distribution' in data:
                for secteur_name, secteur_data in data['secteur_distribution'].items():
                    secteur_normalized = self._normalize_secteur_name(secteur_name)
                    
                    if secteur_normalized not in distribution_data:
                        distribution_data[secteur_normalized] = {
                            'quantite': 0,
                            'part_distribution': 0,
                            'score': 0,
                            'quantite_produit': 0,
                            'quantite_marche': 0,
                            'ratio_quota': 0,
                            'methode_utilisee': '',
                            'noms_originaux': [],
                            'gouvernorat': secteur_to_gov.get(secteur_normalized, ''),
                            'objectif_n1_initial': 0,
                            'objectif_n1_corrige': 0
                        }
                    
                    quantite = secteur_data['quantite'] if isinstance(secteur_data, dict) and 'quantite' in secteur_data else secteur_data
                    distribution_data[secteur_normalized]['quantite'] += quantite
                    total_objectif += quantite
                    
                    # Get N+1 objectives if available
                    if isinstance(secteur_data, dict):
                        if 'objectif_n1_initial' in secteur_data:
                            distribution_data[secteur_normalized]['objectif_n1_initial'] = secteur_data['objectif_n1_initial']
                        if 'objectif_n1_corrige' in secteur_data:
                            distribution_data[secteur_normalized]['objectif_n1_corrige'] = secteur_data['objectif_n1_corrige']
                        elif 'objectif_n1' in secteur_data:
                            distribution_data[secteur_normalized]['objectif_n1_corrige'] = secteur_data['objectif_n1']
                    
                    if secteur_name not in distribution_data[secteur_normalized]['noms_originaux']:
                        distribution_data[secteur_normalized]['noms_originaux'].append(secteur_name)
        
        if total_objectif > 0:
            for secteur_name in distribution_data:
                distribution_data[secteur_name]['part_distribution'] = (
                    distribution_data[secteur_name]['quantite'] / total_objectif * 100
                )
        
        return distribution_data, total_objectif

    def get_product_objectives_summary(self, product_code=None):
        if product_code is None:
            product_code = self.product_code
        
        if product_code not in self.results:
            self.calculate_and_store_product_objectives(product_code)
        
        if product_code not in self.results:
            return {
                'product_code': product_code,
                'total_objectif_n': 0,
                'ventes_n1': 0,
                'ventes_n2': 0,
                'volume_marché_n1': 0,
                'volume_marché_n2': 0,
                'croissance_produit': 0,
                'croissance_marché': 0,
                'croissance_totale': 0,
                'pm_moyenne': 0,
                'pm_n1': 0,
                'pm_n2': 0,
                'pm_formule': 'N/A',
                'nombre_gouvernorats': 0,
                'nombre_secteurs': 0,
                'method_used': 'N/A'
            }
        
        obj_data = self.results[product_code]['objectives']
        
        ventes_n1 = self._quantity_n1_total if self._quantity_n1_total is not None else 0
        ventes_n2 = self._quantity_n2_total if self._quantity_n2_total is not None else 0
        volume_marché_n = self._total_market_volume_n if self._total_market_volume_n is not None else 0
        volume_marché_n1 = self._total_market_volume_n1 if self._total_market_volume_n1 is not None else 0
        volume_marché_n2 = self._total_market_volume_n2 if self._total_market_volume_n2 is not None else 0
        
        croissance_produit = self.calculate_product_growth_corrected()
        croissance_marché = self.calculate_market_growth_corrected()
        
        pm_moyenne, pm_n1, pm_n2, pm_formule = self.calculate_pm_moyenne(product_code)
        
        if '_TOTAUX_' in obj_data:
            total_objectif = obj_data['_TOTAUX_'].get('total_qte_n', 0)
            
            croissance_totale = 0
            if ventes_n1 > 0:
                croissance_totale = ((total_objectif - ventes_n1) / ventes_n1) * 100
        else:
            total_objectif = 0
            croissance_totale = 0
        
        gov_dist, gov_total = self.get_governorat_distribution_with_objectives(product_code)
        secteur_dist, secteur_total = self.get_secteur_distribution_with_objectives(product_code)
        
        # Vérifier si des secteurs ont été retirés
        secteurs_retires = self.results[product_code].get('secteurs_retires', [])
        
        print(f"Vérification résumé: Objectif total={total_objectif}, Gov total={gov_total}, Sect total={secteur_total}")
        print(f"Nombre de gouvernorats: {len(gov_dist)}")
        print(f"Nombre de secteurs: {len(secteur_dist)}")
        
        # Calculer total objectif N+1
        total_objectif_n1 = sum(
            sd.get('objectif_n1_corrige', sd.get('quantite', 0)) 
            for sd in secteur_dist.values()
        )
        
        summary = {
            'product_code': product_code,
            'total_objectif_n': total_objectif,
            'total_objectif_n1': total_objectif_n1,
            'ventes_n1': ventes_n1,
            'ventes_n2': ventes_n2,
            'volume_marché_n': volume_marché_n,
            'volume_marché_n1': volume_marché_n1,
            'volume_marché_n2': volume_marché_n2,
            'croissance_produit': croissance_produit,
            'croissance_marché': croissance_marché,
            'croissance_totale': croissance_totale,
            'pm_moyenne': pm_moyenne,
            'pm_n1': pm_n1,
            'pm_n2': pm_n2,
            'pm_formule': pm_formule,
            'nombre_gouvernorats': len(gov_dist),
            'nombre_secteurs': len(secteur_dist),
            'method_used': self.results[product_code].get('method', 'N/A'),
            'repartition_method': self.results[product_code].get('repartition_method', 'N/A'),
            'c_produit_formule': f"({ventes_n1:,.0f} - {ventes_n2:,.0f}) / {ventes_n2:,.0f} × 100 = {croissance_produit:.1f}%",
            'c_marche_formule': f"({volume_marché_n1:,.0f} - {volume_marché_n2:,.0f}) / {volume_marché_n2:,.0f} × 100 = {croissance_marché:.1f}%",
            'total_gouvernorat': gov_total,
            'total_secteur': secteur_total,
            'pm_calculation_method': self.results[product_code].get('pm_calculation_method', 'formule_calculée'),
            'condition_appliquee': self.results[product_code].get('condition_appliquee', 'standard'),
            'secteurs_retires': secteurs_retires,
            'nombre_secteurs_retires': len(secteurs_retires)
        }
        
        return summary

    def calculate_quantity_n1_for_product(self):
        return self._quantity_n1_total or 0
    
    def get_corrected_quantity_n1(self):
        return self._quantity_n1_total or 0
    
    def get_quantity_n2_for_product(self):
        return self._quantity_n2_total or 0
    
    def get_market_volume_n1(self):
        return self._total_market_volume_n1 or 0
    
    def get_market_volume_n2(self):
        return self._total_market_volume_n2 or 0

def process_single_file(product_code, file_content, secteurs_a_retirer=None):
    analyzer = SonatAnalyticsPro()
    success = analyzer.load_user_data(
        product_code=product_code,
        single_file_content=file_content
    )
    
    if success:
        analyzer.calculate_and_store_product_objectives(product_code, secteurs_a_retirer)
        return analyzer
    else:
        print("Erreur lors du chargement du fichier")
        return None

# Interface Streamlit corrigée
def main():
    st.set_page_config(layout="wide", page_title="Sonat Analytics Pro")
    
    st.title("📊 Sonat Analytics Pro - Gestion Multi-Produits")
    
    st.markdown("---")
    
    # Initialisation de l'état de session
    if 'products_list' not in st.session_state:
        st.session_state.products_list = []
    if 'selected_product' not in st.session_state:
        st.session_state.selected_product = None
    if 'analyzer' not in st.session_state:
        st.session_state.analyzer = None
    if 'data_file' not in st.session_state:
        st.session_state.data_file = None
    if 'secteurs_retirer' not in st.session_state:
        st.session_state.secteurs_retirer = []
    if 'market_data_loaded' not in st.session_state:
        st.session_state.market_data_loaded = False
    
    # Vérifier si les credentials sont configurées
    if not get_credentials():
        st.error("⚠️ Google credentials not configured.")
        st.info("Please set the GOOGLE_SERVICE_ACCOUNT_JSON environment variable with your service account JSON.")
        st.stop()
    
    # Section 1: Chargement des données de marché
    st.header("Étape 1: Charger les données de marché")
    
    data_file = st.file_uploader(
        "Téléchargez le fichier CSV des données de marché",
        type=['csv'],
        key="market_data_uploader"
    )
    
    if data_file and not st.session_state.market_data_loaded:
        try:
            # Lire le contenu du fichier
            file_content = data_file.getvalue().decode('utf-8')
            st.session_state.data_file = file_content
            
            # Lire le fichier pour extraire les produits disponibles
            df_market = pd.read_csv(io.StringIO(file_content), sep=';')
            
            # Vérifier la présence des colonnes nécessaires
            if 'Code PCT' in df_market.columns:
                # Nettoyer les codes PCT
                df_market['Code PCT'] = df_market['Code PCT'].astype(str).str.strip()
                
                # Extraire les produits uniques
                unique_products = df_market[['Code PCT']].drop_duplicates()
                
                # Si la colonne 'Produit' existe, l'utiliser pour la désignation
                if 'Produit' in df_market.columns:
                    # Prendre la première désignation pour chaque code PCT
                    product_names = df_market.groupby('Code PCT')['Produit'].first().reset_index()
                    unique_products = pd.merge(unique_products, product_names, on='Code PCT', how='left')
                    # Créer la liste de produits
                    products_list = [
                        {'Code PCT': row['Code PCT'], 'Désignation': row.get('Produit', row['Code PCT'])}
                        for _, row in unique_products.iterrows()
                    ]
                else:
                    # Utiliser seulement le code PCT comme désignation
                    products_list = [
                        {'Code PCT': row['Code PCT'], 'Désignation': row['Code PCT']}
                        for _, row in unique_products.iterrows()
                    ]
                
                st.session_state.products_list = products_list
                st.session_state.market_data_loaded = True
                
                st.success(f"✅ {len(products_list)} produits trouvés dans les données de marché!")
                
                # Afficher un aperçu des produits disponibles
                with st.expander("Aperçu des produits disponibles"):
                    preview_df = pd.DataFrame(products_list)
                    st.dataframe(preview_df.head(20), use_container_width=True)
                    if len(products_list) > 20:
                        st.caption(f"... et {len(products_list) - 20} autres produits")
                
            else:
                st.error("Le fichier doit contenir une colonne 'Code PCT'")
                
        except Exception as e:
            st.error(f"Erreur lors du chargement du fichier de marché: {e}")
    
    # Section 2: Sélection du produit (uniquement si les données de marché sont chargées)
    if st.session_state.market_data_loaded:
        st.header("Étape 2: Sélectionner un produit")
        
        if st.session_state.products_list:
            # Créer une liste déroulante avec désignation
            product_options = [f"{p['Désignation']} ({p['Code PCT']})" for p in st.session_state.products_list]
            
            selected_option = st.selectbox(
                "Choisissez un produit:",
                options=[""] + product_options,
                format_func=lambda x: x if x else "Sélectionnez un produit...",
                key="product_selector"
            )
            
            if selected_option:
                # Extraire le code PCT de l'option sélectionnée
                for product in st.session_state.products_list:
                    if f"{product['Désignation']} ({product['Code PCT']})" == selected_option:
                        st.session_state.selected_product = product
                        break
                
                if st.session_state.selected_product:
                    st.info(f"Produit sélectionné: **{st.session_state.selected_product['Désignation']}** (Code PCT: {st.session_state.selected_product['Code PCT']})")
                    
                    # Section 3: Gestion des secteurs à retirer
                    st.header("Étape 3: Gestion des secteurs à retirer")
                    
                    # Charger un échantillon de données pour voir les secteurs disponibles
                    try:
                        if st.session_state.data_file:
                            sample_data = pd.read_csv(io.StringIO(st.session_state.data_file), sep=';', nrows=100)
                            if 'Secteur' in sample_data.columns:
                                # Obtenir la liste des secteurs uniques
                                secteurs_disponibles = sample_data['Secteur'].dropna().unique()
                                secteurs_disponibles = [str(s).strip() for s in secteurs_disponibles]
                                
                                # Multi-select pour choisir les secteurs à retirer
                                secteurs_a_retirer = st.multiselect(
                                    "Sélectionnez les secteurs à retirer de la répartition:",
                                    options=secteurs_disponibles,
                                    default=st.session_state.get('secteurs_retirer', []),
                                    help="Ces secteurs seront exclus de la distribution et leurs quantités seront redistribuées aux autres secteurs."
                                )
                                
                                st.session_state.secteurs_retirer = secteurs_a_retirer
                                
                                if secteurs_a_retirer:
                                    st.warning(f"⚠️ {len(secteurs_a_retirer)} secteur(s) seront retirés de la répartition: {', '.join(secteurs_a_retirer)}")
                                else:
                                    st.info("ℹ️ Aucun secteur sélectionné pour retrait.")
                            else:
                                st.warning("Colonne 'Secteur' non trouvée dans le fichier de données.")
                                st.session_state.secteurs_retirer = []
                    except Exception as e:
                        st.warning(f"Impossible de lire les secteurs depuis le fichier: {e}")
                        st.session_state.secteurs_retirer = []
                    
                    # Lancer le calcul
                    if st.button("🚀 Lancer le calcul", type="primary"):
                        with st.spinner("Calcul en cours..."):
                            analyzer = process_single_file(
                                st.session_state.selected_product['Code PCT'],
                                st.session_state.data_file,
                                st.session_state.secteurs_retirer
                            )
                            
                            if analyzer:
                                st.session_state.analyzer = analyzer
                                st.success("✅ Calcul terminé avec succès!")
                                
                                # Afficher les résultats
                                st.header("📈 Résultats du calcul")
                                
                                # Résumé du produit
                                summary = analyzer.get_product_objectives_summary()
                                
                                col1, col2, col3, col4 = st.columns(4)
                                with col1:
                                    st.metric("Ventes N-1", f"{summary['ventes_n1']:,.0f}")
                                with col2:
                                    st.metric("Ventes N-2", f"{summary['ventes_n2']:,.0f}")
                                with col3:
                                    st.metric("Objectif N", f"{summary['total_objectif_n']:,.0f}")
                                with col4:
                                    st.metric("Croissance", f"{summary['croissance_totale']:.1f}%")
                                
                                # Afficher les secteurs retirés si applicable
                                if summary.get('secteurs_retires'):
                                    with st.expander(f"⚠️ Secteurs retirés ({len(summary['secteurs_retires'])})"):
                                        st.write("Les secteurs suivants ont été exclus de la répartition:")
                                        for secteur in summary['secteurs_retires']:
                                            st.write(f"- {secteur}")
                                
                                # Détails
                                with st.expander("📋 Détails du calcul"):
                                    st.subheader("Formules utilisées")
                                    st.write(f"**Croissance produit:** {summary['c_produit_formule']}")
                                    st.write(f"**Croissance marché:** {summary['c_marche_formule']}")
                                    st.write(f"**Part de marché:** {summary['pm_formule']}")
                                    st.write(f"**Méthode:** {summary['method_used']}")
                                
                                # Distribution par gouvernorat
                                st.subheader("🎯 Distribution par Gouvernorat")
                                gov_dist, gov_total = analyzer.get_governorat_distribution_with_objectives()
                                if gov_dist:
                                    gov_df = pd.DataFrame([
                                        {
                                            'Gouvernorat': gov,
                                            'Quantité': data['quantite'],
                                            'Part %': f"{data['part_distribution']:.1f}%",
                                            'Nb Secteurs': data.get('nombre_secteurs', 0),
                                            'Méthode': data.get('methode_utilisee', '')
                                        }
                                        for gov, data in gov_dist.items()
                                    ])
                                    st.dataframe(gov_df, use_container_width=True)
                                    st.info(f"**{len(gov_dist)} gouvernorats** avec objectif total de **{gov_total:,.0f}** unités")
                                    
                                    # VÉRIFICATION : Afficher la somme des secteurs pour chaque gouvernorat
                                    with st.expander("🔍 Vérification détaillée par gouvernorat"):
                                        for gov_name, gov_data in gov_dist.items():
                                            st.write(f"**{gov_name}**")
                                            st.write(f"  - Quantité gouvernorat: {gov_data['quantite']:,.0f}")
                                            st.write(f"  - Nombre de secteurs: {gov_data['nombre_secteurs']}")
                                            if 'secteurs_details' in gov_data:
                                                total_secteurs = sum(s['quantite'] for s in gov_data['secteurs_details'])
                                                st.write(f"  - Somme des secteurs: {total_secteurs:,.0f}")
                                                if abs(total_secteurs - gov_data['quantite']) > 0.01:
                                                    st.error(f"  ⚠️ INCOHÉRENCE: Différence de {abs(total_secteurs - gov_data['quantite']):.0f} unités")
                                                else:
                                                    st.success("  ✅ Cohérence vérifiée")
                                else:
                                    st.warning("Aucune distribution par gouvernorat disponible.")
                                
                                # Distribution par secteur
                                st.subheader("🏘️ Distribution par Secteur")
                                secteur_dist, secteur_total = analyzer.get_secteur_distribution_with_objectives()
                                if secteur_dist:
                                    secteur_df = pd.DataFrame([
                                        {
                                            'Secteur': secteur,
                                            'Quantité': data['quantite'],
                                            'Part %': f"{data['part_distribution']:.1f}%",
                                            'Score': f"{data.get('score', 0):.2f}",
                                            'Méthode': data.get('methode_utilisee', '')
                                        }
                                        for secteur, data in secteur_dist.items()
                                    ])
                                    st.dataframe(secteur_df, use_container_width=True)
                                    st.info(f"**{len(secteur_dist)} secteurs** avec objectif total de **{secteur_total:,.0f}** unités")
                                else:
                                    st.warning("Aucune distribution par secteur disponible.")
                                
                                # Bouton d'export
                                if st.button("📥 Exporter les résultats"):
                                    # Créer un fichier Excel avec les résultats
                                    with pd.ExcelWriter('resultats_sonat.xlsx', engine='openpyxl') as writer:
                                        # Résumé
                                        summary_df = pd.DataFrame([summary])
                                        summary_df.to_excel(writer, sheet_name='Résumé', index=False)
                                        
                                        # Distribution gouvernorat
                                        if gov_dist:
                                            gov_export_df = pd.DataFrame([
                                                {
                                                    'Gouvernorat': gov,
                                                    'Quantité': data['quantite'],
                                                    'Part %': data['part_distribution'],
                                                    'Méthode': data.get('methode_utilisee', '')
                                                }
                                                for gov, data in gov_dist.items()
                                            ])
                                            gov_export_df.to_excel(writer, sheet_name='Gouvernorats', index=False)
                                        
                                        # Distribution secteur
                                        if secteur_dist:
                                            secteur_export_df = pd.DataFrame([
                                                {
                                                    'Secteur': secteur,
                                                    'Quantité': data['quantite'],
                                                    'Part %': data['part_distribution'],
                                                    'Score': data.get('score', 0),
                                                    'Méthode': data.get('methode_utilisee', '')
                                                }
                                                for secteur, data in secteur_dist.items()
                                            ])
                                            secteur_export_df.to_excel(writer, sheet_name='Secteurs', index=False)
                                        
                                        # Secteurs retirés
                                        if summary.get('secteurs_retires'):
                                            secteurs_retires_df = pd.DataFrame({
                                                'Secteurs retirés': summary['secteurs_retires']
                                            })
                                            secteurs_retires_df.to_excel(writer, sheet_name='Secteurs_retirés', index=False)
                                    
                                    # Télécharger le fichier
                                    with open('resultats_sonat.xlsx', 'rb') as f:
                                        st.download_button(
                                            label="Télécharger le fichier Excel",
                                            data=f,
                                            file_name=f"resultats_{st.session_state.selected_product['Code PCT']}.xlsx",
                                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                                        )
                            else:
                                st.error("Erreur lors du calcul. Vérifiez vos données.")
    
    else:
        st.warning("Veuillez d'abord charger un fichier de données de marché à l'Étape 1.")
        
        # Option pour réinitialiser
        if st.button("🔄 Charger un nouveau fichier de marché"):
            st.session_state.market_data_loaded = False
            st.session_state.products_list = []
            st.session_state.selected_product = None
            st.session_state.analyzer = None
            st.rerun()

if __name__ == "__main__":
    main()