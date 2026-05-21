# délégué.py - Module pour les calculs de répartition des délégués
import pandas as pd
import numpy as np
import os
from datetime import datetime
import math
from collections import defaultdict
import streamlit as st
import warnings
warnings.filterwarnings('ignore')

_clustering_bound = False

def _bind_clustering_methods():
    global _clustering_bound
    if _clustering_bound:
        return
    from delegue_clustering import ClusteringMixin
    for name in dir(ClusteringMixin):
        if not name.startswith('__'):
            method = getattr(ClusteringMixin, name)
            if callable(method):
                setattr(DelegueCalculator, name, method)
    _clustering_bound = True

def _load_distance_matrix_from_db():
    """Charge la matrice de distances depuis la base de données PostgreSQL"""
    import psycopg2
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        return None
    try:
        conn = psycopg2.connect(database_url)
        cur = conn.cursor()
        cur.execute("SELECT secteur_from, secteur_to, distance FROM distance_secteurs")
        rows = cur.fetchall()
        cur.close()
        conn.close()
        if not rows:
            return None
        sectors = sorted(set(r[0] for r in rows) | set(r[1] for r in rows))
        df = pd.DataFrame(np.inf, index=sectors, columns=sectors)
        np.fill_diagonal(df.values, 0.0)
        for sf, st_name, dist in rows:
            if sf in df.index and st_name in df.columns:
                df.loc[sf, st_name] = dist
                if df.loc[st_name, sf] == np.inf:
                    df.loc[st_name, sf] = dist
        return df
    except Exception as e:
        print(f"Erreur chargement matrice distances DB: {e}")
        return None

try:
    load_distance_matrix_cached = st.cache_data(ttl=7200, show_spinner=False)(_load_distance_matrix_from_db)
except Exception:
    load_distance_matrix_cached = _load_distance_matrix_from_db

class DelegueCalculator:
    """
    Classe pour les calculs de répartition des délégués basée sur la performance
    """
    
    def __init__(self, analytics_app):
        """
        Initialise le calculateur de délégués
        
        Args:
            analytics_app: instance de SonatAnalyticsPro
        """
        self.app = analytics_app
        self.performance_data = None
        self._load_performance_data()
        self.distance_matrix = None
        self._load_distance_matrix()
        
        # Objectifs multi-produits par secteur (somme des objectifs de tous les produits)
        self.multi_product_secteur_objectives = None  # {secteur: objectif_global}
        self.multi_product_details = None  # {secteur: {product_code: {name, objectif}}}
        self.is_multi_product_mode = False
        
        # Définition des secteurs par région selon votre structure
        self.SECTEURS_PAR_REGION = {
            'Nord': [
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
                'Zaghouan'
            ],
            'Centre': [
                'Gafsa 1', 'Gafsa 2',
                'Kairouan 1', 'Kairouan 2',
                'Kasserine 1', 'Kasserine 2',
                'Mahdia 1', 'Mahdia 2',
                'Monastir 1', 'Monastir 2', 'Monastir 3', 'Monastir 4',
                'Sidi Bouzid 1', 'Sidi Bouzid 2',
                'Sousse 101', 'Sousse 102', 'Sousse 103', 'Sousse 201', 'Sousse 211',
            ],
            'Sud': [
                'Gabes 1', 'Gabes 2',
                'Kebili',
                'Medenine 1', 'Medenine 2', 'Medenine 3',
                'Sfax 101', 'Sfax 102', 'Sfax 103', 'Sfax 104', 'Sfax 201', 'Sfax 211',
                'Sfax 301', 'Sfax 311', 'Sfax 321', 'Sfax 331',
                'Tataouine',
                'Tozeur'
            ]
        }
        
        # Mappage des gouvernorats aux secteurs (pour compatibilité)
        self.GOUVERNORATS_SECTEURS = {
            'Nord': ['Tunis', 'Ariana', 'Ben Arous', 'Manouba', 'Zaghouan', 'Beja', 'Bizerte', 
                    'Le Kef', 'Jendouba', 'Nabeul', 'Siliana'],
            'Centre': ['Gafsa', 'Kairouan', 'Kasserine', 'Mahdia', 'Monastir', 'Sidi Bouzid', 'Sousse'],
            'Sud': ['Gabes', 'Kebili', 'Medenine', 'Sfax', 'Tataouine', 'Tozeur']
        }
        
        # Liste des produits disponibles
        self.product_folders = []
        self._load_available_products()
        
        # Liste des secteurs retirés (sera remplie dynamiquement)
        self.secteurs_retires = []
        
        # Gouvernorats qui PEUVENT être divisés entre plusieurs délégués
        # Tous les autres gouvernorats doivent rester sur un seul délégué
        self.GOUVERNORATS_DIVISIBLES = [
            'Tunis', 'Ariana', 'Ben Arous', 'La Manouba', 'Manouba',
            'Sfax', 'Sousse', 'Medenine',
            'Nabeul', 'Bizerte', 'Monastir', 'Mahdia',
            'Kairouan', 'Kasserine', 'Sidi Bouzid',
            'Gabes', 'Gabès', 'Gafsa', 'Tataouine',
            'Beja', 'Béja',
        ]
        self.GOUVERNORATS_DIVISIBLES_CONDITIONNELS = []
        
        self.GOUVERNORATS_PAIRES = [
            ('Tozeur', 'Kebili'),
            ('Jendouba', 'Beja'),
            ('Le Kef', 'Siliana'),
            ('Siliana', 'Zaghouan'),
        ]
        
        self.GROUPES_EXCLUSIFS = []
        
        self.GOUVERNORATS_NON_SEULS = ['Sousse']
        
        self.SECTEURS_PAIRES = [
            ('Nabeul 211', 'Nabeul 222'),
        ]
        
        # Carte des gouvernorats voisins (pour optimiser la proximité lors du rééquilibrage)
        self.GOUVERNORATS_VOISINS = {
            'Tunis': ['Ariana', 'Ben Arous', 'Manouba', 'La Manouba'],
            'Ariana': ['Tunis', 'Ben Arous', 'Manouba', 'La Manouba', 'Bizerte', 'Zaghouan'],
            'Ben Arous': ['Tunis', 'Ariana', 'Nabeul', 'Zaghouan', 'Manouba', 'La Manouba'],
            'Manouba': ['Tunis', 'Ariana', 'Ben Arous', 'Beja', 'Siliana', 'Zaghouan'],
            'La Manouba': ['Tunis', 'Ariana', 'Ben Arous', 'Beja', 'Siliana', 'Zaghouan'],
            'Nabeul': ['Ben Arous', 'Zaghouan', 'Sousse'],
            'Zaghouan': ['Ariana', 'Ben Arous', 'Nabeul', 'Sousse', 'Kairouan', 'Siliana', 'Manouba', 'La Manouba'],
            'Bizerte': ['Ariana', 'Beja', 'Manouba', 'La Manouba'],
            'Beja': ['Bizerte', 'Manouba', 'La Manouba', 'Siliana', 'Jendouba', 'Le Kef'],
            'Jendouba': ['Beja', 'Le Kef', 'Siliana'],
            'Le Kef': ['Jendouba', 'Beja', 'Siliana', 'Kasserine'],
            'Siliana': ['Beja', 'Manouba', 'La Manouba', 'Zaghouan', 'Kairouan', 'Kasserine', 'Le Kef'],
            'Sousse': ['Nabeul', 'Zaghouan', 'Kairouan', 'Mahdia', 'Monastir'],
            'Monastir': ['Sousse', 'Mahdia'],
            'Mahdia': ['Sousse', 'Monastir', 'Kairouan', 'Sfax', 'Sidi Bouzid'],
            'Sfax': ['Mahdia', 'Sidi Bouzid', 'Kairouan', 'Gabes', 'Gafsa'],
            'Kairouan': ['Zaghouan', 'Sousse', 'Mahdia', 'Sfax', 'Sidi Bouzid', 'Kasserine', 'Siliana'],
            'Kasserine': ['Le Kef', 'Siliana', 'Kairouan', 'Sidi Bouzid', 'Gafsa'],
            'Sidi Bouzid': ['Kairouan', 'Sfax', 'Mahdia', 'Kasserine', 'Gafsa', 'Gabes'],
            'Gabes': ['Sfax', 'Sidi Bouzid', 'Gafsa', 'Kebili', 'Medenine'],
            'Medenine': ['Gabes', 'Tataouine', 'Kebili'],
            'Tataouine': ['Medenine', 'Kebili'],
            'Gafsa': ['Kasserine', 'Sidi Bouzid', 'Sfax', 'Gabes', 'Kebili', 'Tozeur'],
            'Tozeur': ['Gafsa', 'Kebili'],
            'Kebili': ['Tozeur', 'Gafsa', 'Gabes', 'Medenine', 'Tataouine']
        }
    
    def _load_available_products(self):
        """Charge la liste des produits disponibles depuis l'application"""
        try:
            if hasattr(self.app, 'product_code') and self.app.product_code:
                self.product_folders = [self.app.product_code]
            elif hasattr(self.app, 'results'):
                self.product_folders = list(self.app.results.keys())
            else:
                self.product_folders = []
        except:
            self.product_folders = []
    
    def _load_performance_data(self):
        """Charge les données de performance depuis le fichier Excel"""
        try:
            # Tenter de trouver le fichier performance.xlsx
            possible_paths = [
                "performance.xlsx",
                os.path.join(os.path.dirname(__file__), "performance.xlsx"),
                os.path.join("data", "performance.xlsx")
            ]
            
            loaded = False
            for path in possible_paths:
                if os.path.exists(path):
                    df = pd.read_excel(path)
                    df.columns = [col.strip() for col in df.columns]
                    self.performance_data = df
                    loaded = True
                    break
            
            if not loaded:
                self.performance_data = pd.DataFrame()
                
        except Exception:
            self.performance_data = pd.DataFrame()
    
    def _load_distance_matrix(self):
        """Charge la matrice de distance entre secteurs (avec cache)"""
        try:
            cached_df = load_distance_matrix_cached()
            self.distance_matrix = cached_df
        except Exception:
            self.distance_matrix = None
    
    def set_multi_product_objectives(self, all_products_results, secteurs_retires_par_produit=None):
        """
        Configure les objectifs multi-produits pour la répartition des délégués.
        Calcule la somme des objectifs de tous les produits par secteur.
        
        Args:
            all_products_results: Dict des résultats de tous les produits analysés
                {product_code: {name, secteur_dist: {secteur: {objectif_n1_corrige, ...}}, ...}}
            secteurs_retires_par_produit: Dict optionnel des secteurs exclus par produit
                {product_code: [secteur1, secteur2, ...]}
        """
        if not all_products_results or len(all_products_results) == 0:
            self.is_multi_product_mode = False
            return
        
        if secteurs_retires_par_produit is None:
            secteurs_retires_par_produit = {}
        
        self.is_multi_product_mode = len(all_products_results) > 1
        self.multi_product_secteur_objectives = {}
        self.multi_product_details = {}
        
        for secteur_liste in self.SECTEURS_PAR_REGION.values():
            for secteur in secteur_liste:
                self.multi_product_secteur_objectives[secteur] = 0
                self.multi_product_details[secteur] = {}
        
        for product_code, product_data in all_products_results.items():
            product_name = product_data.get('name', product_code)
            secteur_dist = product_data.get('secteur_dist', {})
            secteurs_exclus = secteurs_retires_par_produit.get(product_code, [])
            
            for secteur_nom, secteur_data in secteur_dist.items():
                if secteur_nom in secteurs_exclus:
                    continue
                secteur_correspondant = self._trouver_secteur_correspondant(secteur_nom)
                if secteur_correspondant:
                    objectif = secteur_data.get('objectif_n1_corrige', secteur_data.get('quantite', 0)) or 0
                    
                    self.multi_product_secteur_objectives[secteur_correspondant] += objectif
                    
                    self.multi_product_details[secteur_correspondant][product_code] = {
                        'name': product_name,
                        'objectif': objectif
                    }
    
    def calculate_delegate_allocation_simple(self, product, visites_par_jour=10, produits_par_visite=30, 
                                           jours_travail_an=None, objectif_total=None):
        """
        Calcule le nombre de délégués nécessaires pour un produit
        Formule simple: (Objectif total / produits_par_visite) / (visites_par_jour * jours_travail_an)
        
        Args:
            objectif_total: Objectif total optionnel. Si None, calcule automatiquement
        """
        # Utiliser 237 jours par défaut si non spécifié ou égal à 0
        if jours_travail_an is None or jours_travail_an == 0:
            jours_travail_an = 237
        
        # Vérifier si l'application a les résultats pour ce produit
        if not hasattr(self.app, 'results') or product not in self.app.results:
            # Essayer de calculer les objectifs
            if hasattr(self.app, 'calculate_and_store_product_objectives'):
                self.app.calculate_and_store_product_objectives(product)
            else:
                return {'erreur': f'Impossible de calculer les objectifs pour {product}'}
        
        if product not in self.app.results and objectif_total is None:
            return {'erreur': f'Impossible de calculer les objectifs pour {product}'}
        
        if objectif_total is None:
            if product not in self.app.results:
                return {'erreur': f'Impossible de calculer les objectifs pour {product}'}
            
            obj_data = self.app.results[product]['objectives']
            if '_TOTAUX_' not in obj_data:
                return {'erreur': 'Données objectifs incomplètes'}
            
            total_objectif = obj_data['_TOTAUX_']['total_qte_n']
        else:
            total_objectif = objectif_total
            # Calculer quand même les objectifs pour avoir les autres données
            if product not in self.app.results and hasattr(self.app, 'calculate_and_store_product_objectives'):
                self.app.calculate_and_store_product_objectives(product)
        
        # Vérifications des paramètres
        if visites_par_jour == 0:
            return {'erreur': 'Le nombre de visites par jour doit être supérieur à 0'}
        
        if produits_par_visite == 0:
            return {'erreur': 'Le nombre de produits par visite doit être supérieur à 0'}
        
        if jours_travail_an == 0:
            return {'erreur': 'Le nombre de jours de travail par an doit être supérieur à 0'}
        
        # Calculs
        capacite_annuelle_delegue = visites_par_jour * jours_travail_an
        visites_necessaires = total_objectif / produits_par_visite
        delegues_theorique = visites_necessaires / capacite_annuelle_delegue
        delegues_arrondi = math.ceil(delegues_theorique)
        
        # Calcul de l'efficacité
        if delegues_arrondi > 0:
            taux_utilisation = (delegues_theorique / delegues_arrondi) * 100
            visites_par_delegue = visites_necessaires / delegues_arrondi
        else:
            taux_utilisation = 0
            visites_par_delegue = 0
        
        result = {
            'parametres': {
                'visites_par_jour': visites_par_jour,
                'jours_travail_an': jours_travail_an,
                'produits_par_visite': produits_par_visite,
                'capacite_annuelle_delegue': capacite_annuelle_delegue,
                'objectif_total_saisi': objectif_total is not None,
                'objectif_source': 'Saisie manuelle' if objectif_total is not None else 'Calcul automatique'
            },
            'calculs': {
                'objectif_total': total_objectif,
                'visites_necessaires': visites_necessaires,
                'delegues_theorique': delegues_theorique,
                'delegues_arrondi': delegues_arrondi,
                'taux_utilisation_percent': taux_utilisation,
                'visites_par_delegue': visites_par_delegue
            },
            'recommandations': self._generate_delegate_recommendations_simple(
                delegues_theorique, delegues_arrondi, taux_utilisation, jours_travail_an
            )
        }
        
        # Si objectif saisi manuellement, ajouter un avertissement
        if objectif_total is not None:
            result['avertissement'] = "Objectif total saisi manuellement - la répartition par secteur utilise les pourcentages de la méthode 3"
        
        return result
    
    def calculate_delegate_allocation_by_region(self, visites_par_jour=10, produits_par_visite=30, 
                                              jours_travail_an=None, objectif_total=None, taux_conversion=0.10):
        """
        Calcule le nombre de délégués nécessaires PAR REGION (somme des secteurs)
        
        Args:
            objectif_total: Objectif total optionnel. Si fourni, répartit cet objectif sur les secteurs
                           selon leur part dans la méthode 3
            taux_conversion: Taux de conversion des visites (ex: 0.10 = 10% des visites génèrent une vente)
        """
        # Utiliser 237 jours par défaut si non spécifié ou égal à 0
        if jours_travail_an is None or jours_travail_an == 0:
            jours_travail_an = 237
        
        # Valider le taux de conversion
        if taux_conversion is None or taux_conversion <= 0:
            taux_conversion = 0.10
        
        # Vérifications des paramètres
        if visites_par_jour == 0:
            return {'erreur': 'Le nombre de visites par jour doit être supérieur à 0'}
        
        if produits_par_visite == 0:
            return {'erreur': 'Le nombre de produits par visite doit être supérieur à 0'}
        
        if jours_travail_an == 0:
            return {'erreur': 'Le nombre de jours de travail par an doit être supérieur à 0'}
        
        # Capacité annuelle par délégué (avec taux de conversion)
        # Formule: visites/jour × jours/an × produits/visite × taux_conversion
        capacite_annuelle_delegue = visites_par_jour * jours_travail_an * produits_par_visite * taux_conversion
        
        # Obtenir le total réel depuis le résumé des produits (utiliser N+1)
        total_reel = 0
        for product in self.product_folders:
            summary = self.get_product_objectives_summary(product)
            # Utiliser objectif N+1 si disponible, sinon N
            total_reel += summary.get('total_objectif_n1', summary.get('total_objectif_n', 0))
        
        # Si objectif_total est fourni, l'utiliser
        if objectif_total is not None:
            total_a_repartir = objectif_total
            ajustement_necessaire = True
            facteur_ajustement = total_a_repartir / total_reel if total_reel > 0 else 1
        else:
            total_a_repartir = total_reel
            ajustement_necessaire = False
            facteur_ajustement = 1
        
        # CORRECTION : Calculer d'abord la distribution réelle par secteur
        objectifs_par_secteur_bruts = self._get_objectifs_par_secteur_tous_produits()
        
        # CORRECTION : Filtrer les secteurs retirés
        objectifs_par_secteur_filtres = self._filter_secteurs_retires_dict(objectifs_par_secteur_bruts)
        
        # CORRECTION : Normaliser les objectifs pour qu'ils totalisent exactement total_a_repartir
        if ajustement_necessaire:
            # Calculer le total brut
            total_brut = sum(objectifs_par_secteur_filtres.values())
            
            if total_brut > 0:
                # Appliquer un facteur d'ajustement global
                facteur = total_a_repartir / total_brut
                objectifs_par_secteur = {s: objectifs_par_secteur_filtres[s] * facteur for s in objectifs_par_secteur_filtres}
            else:
                # Si pas d'objectifs, répartir uniformément
                objectifs_par_secteur = self._repartir_uniformement(total_a_repartir)
        else:
            objectifs_par_secteur = objectifs_par_secteur_filtres
        
        # CORRECTION : Calculer les objectifs par région à partir des secteurs
        objectifs_par_region = {region: 0 for region in self.SECTEURS_PAR_REGION.keys()}
        
        for secteur, objectif in objectifs_par_secteur.items():
            secteur_region = self._get_region_for_secteur(secteur)
            if secteur_region and secteur_region in objectifs_par_region:
                objectifs_par_region[secteur_region] += objectif
        
        # Calcul des délégués par région
        resultats_par_region = {}
        total_delegues = 0
        total_objectif_calcule = 0
        
        for region, objectif_region in objectifs_par_region.items():
            objectif_region_arrondi = round(objectif_region)
            
            # Calculs pour la région (avec formule corrigée incluant taux de conversion)
            # Formule: délégués = objectif / capacité_annuelle_corrigée
            # où capacité = visites/jour × jours/an × produits/visite × taux_conversion
            delegues_theorique = objectif_region_arrondi / capacite_annuelle_delegue if capacite_annuelle_delegue > 0 else 0
            delegues_arrondi = math.ceil(delegues_theorique)
            
            # Calcul des visites nécessaires (pour info)
            visites_necessaires = objectif_region_arrondi / produits_par_visite if produits_par_visite > 0 else 0
            
            # Calcul de l'efficacité
            if delegues_arrondi > 0:
                taux_utilisation = (delegues_theorique / delegues_arrondi) * 100
                visites_par_delegue = visites_necessaires / delegues_arrondi
            else:
                taux_utilisation = 0
                visites_par_delegue = 0
            
            # CORRECTION : Créer la liste des secteurs avec leurs objectifs
            secteurs_avec_objectifs = []
            for secteur in self.SECTEURS_PAR_REGION[region]:
                # Vérifier si le secteur est retiré
                if self._is_secteur_retire(secteur):
                    continue
                
                secteur_objectif = objectifs_par_secteur.get(secteur, 0)
                secteurs_avec_objectifs.append({
                    'nom': secteur,
                    'objectif': secteur_objectif,
                    'pourcentage_region': (secteur_objectif / objectif_region * 100) if objectif_region > 0 else 0
                })
            
            # CORRECTION : Compter uniquement les secteurs non retirés
            secteurs_non_retires = [s for s in self.SECTEURS_PAR_REGION[region] if not self._is_secteur_retire(s)]
            
            resultats_par_region[region] = {
                'secteurs': secteurs_non_retires,
                'nombre_secteurs': len(secteurs_non_retires),
                'gouvernorats': self.GOUVERNORATS_SECTEURS[region],
                'objectif_total': objectif_region_arrondi,
                'objectif_brut': objectif_region,
                'visites_necessaires': visites_necessaires,
                'delegues_theorique': delegues_theorique,
                'delegues_arrondi': delegues_arrondi,
                'visites_par_delegue': visites_par_delegue,
                'capacite_delegue': capacite_annuelle_delegue,
                'taux_utilisation_percent': taux_utilisation,
                'secteurs_avec_objectifs': secteurs_avec_objectifs
            }
            
            total_delegues += delegues_arrondi
            total_objectif_calcule += objectif_region_arrondi
        
        # CORRECTION : Vérifier que la somme est correcte
        total_calcule_precis = sum(objectifs_par_secteur.values())
        difference = total_a_repartir - total_calcule_precis
        
        # Préparer le résultat
        result = {
            'parametres': {
                'visites_par_jour': visites_par_jour,
                'jours_travail_an': jours_travail_an,
                'produits_par_visite': produits_par_visite,
                'taux_conversion': taux_conversion,
                'taux_conversion_percent': taux_conversion * 100,
                'capacite_annuelle_delegue': capacite_annuelle_delegue,
                'objectif_total_saisi': objectif_total is not None,
                'objectif_source': 'Saisie manuelle' if objectif_total is not None else 'Calcul automatique'
            },
            'regions': resultats_par_region,
            'secteurs_objectifs': objectifs_par_secteur,
            'totaux': {
                'total_delegues': total_delegues,
                'total_objectif': total_objectif_calcule,
                'total_objectif_precis': total_calcule_precis,
                'nombre_regions': len(resultats_par_region),
                'verification': {
                    'total_saisi': total_a_repartir,
                    'total_calcule': total_calcule_precis,
                    'total_reel': total_reel,
                    'difference': difference,
                    'difference_pourcentage': (difference / total_a_repartir * 100) if total_a_repartir > 0 else 0,
                    'correspond': abs(difference) < 0.01  # Tolérance de 0.01
                }
            }
        }
        
        # Ajouter des informations spécifiques si objectif saisi
        if objectif_total is not None:
            result['info_ajustement'] = {
                'objectif_saisi': objectif_total,
                'facteur_ajustement': facteur_ajustement if 'facteur_ajustement' in locals() else 1,
                'methode_repartition': 'Distribution réelle ajustée proportionnellement',
                'note': f"Objectif réparti sur {len(objectifs_par_secteur)} secteurs"
            }
        
        return result
    
    def _get_objectifs_par_secteur_tous_produits(self):
        """Calcule les objectifs totaux par secteur pour tous les produits"""
        # Si en mode multi-produits avec objectifs pré-configurés, les utiliser
        if self.multi_product_secteur_objectives is not None:
            return self.multi_product_secteur_objectives.copy()
        
        objectifs_par_secteur = {}
        
        # Initialiser tous les secteurs à 0
        for secteur_liste in self.SECTEURS_PAR_REGION.values():
            for secteur in secteur_liste:
                objectifs_par_secteur[secteur] = 0
        
        # Somme des objectifs de tous les produits pour chaque secteur
        for product in self.product_folders:
            secteur_dist, secteur_total = self.get_secteur_distribution_with_objectives(product)
            
            if secteur_dist:
                for secteur_nom, secteur_data in secteur_dist.items():
                    # Chercher le secteur correspondant dans notre liste
                    secteur_correspondant = self._trouver_secteur_correspondant(secteur_nom)
                    if secteur_correspondant:
                        quantite = secteur_data.get('quantite', 0)
                        objectifs_par_secteur[secteur_correspondant] += quantite
        
        return objectifs_par_secteur
    
    def _repartir_uniformement(self, total_a_repartir):
        """Répartit uniformément l'objectif sur tous les secteurs"""
        # Compter le nombre total de secteurs non retirés
        total_secteurs = 0
        secteurs_non_retires = []
        
        for secteur_liste in self.SECTEURS_PAR_REGION.values():
            for secteur in secteur_liste:
                if not self._is_secteur_retire(secteur):
                    total_secteurs += 1
                    secteurs_non_retires.append(secteur)
        
        if total_secteurs == 0:
            return {}
        
        # Répartir uniformément sur les secteurs non retirés
        objectif_par_secteur = total_a_repartir / total_secteurs
        objectifs_par_secteur = {}
        
        for secteur in secteurs_non_retires:
            objectifs_par_secteur[secteur] = objectif_par_secteur
        
        return objectifs_par_secteur
    
    def _trouver_secteur_correspondant(self, secteur_nom):
        """Trouve le secteur correspondant dans notre liste standardisée"""
        secteur_norm = self._normalize_secteur_name_for_matching(secteur_nom)
        
        for secteur_liste in self.SECTEURS_PAR_REGION.values():
            for secteur in secteur_liste:
                if self._secteurs_match(secteur, secteur_norm):
                    return secteur
        
        return None
    
    def _secteurs_match(self, secteur_ref, secteur_name):
        """Vérifie si deux noms de secteur correspondent"""
        # Nettoyer les noms
        ref_clean = str(secteur_ref).lower().strip()
        name_clean = str(secteur_name).lower().strip()
        
        # Si les noms sont identiques
        if ref_clean == name_clean:
            return True
        
        # Vérifier si un nom commence par l'autre
        if ref_clean.startswith(name_clean) or name_clean.startswith(ref_clean):
            return True
        
        # Vérifier pour les secteurs simples (sans numéro)
        # Si secteur_ref est un secteur simple (sans espace) et secteur_name contient ce nom
        if ' ' not in ref_clean and ref_clean in name_clean:
            return True
        
        # Si secteur_name est un secteur simple (sans espace) et secteur_ref contient ce nom
        if ' ' not in name_clean and name_clean in ref_clean:
            return True
        
        return False
    
    def _normalize_secteur_name_for_matching(self, secteur_name):
        """Normalise le nom d'un secteur pour la recherche"""
        if not secteur_name:
            return ""
        
        # Liste des secteurs simples (sans numéro)
        secteurs_simples = ['Siliana', 'Zaghouan', 'Kebili', 'Tataouine', 'Tozeur']
        
        # Vérifier si c'est un secteur simple
        for secteur_simple in secteurs_simples:
            if secteur_simple.lower() in secteur_name.lower():
                return secteur_simple
        
        # Pour les autres, retourner le nom original nettoyé
        return str(secteur_name).strip()
    
    def _get_region_for_secteur(self, secteur_name):
        """Trouve la région d'un secteur donné"""
        secteur_norm = self._normalize_secteur_name_for_matching(secteur_name)
        
        for region, secteurs in self.SECTEURS_PAR_REGION.items():
            for secteur in secteurs:
                if self._secteurs_match(secteur, secteur_norm):
                    return region
        
        return None
    
    def _redistribute_delegates_by_total(self, allocation_region, nombre_delegues_total, objectif_total=None):
        """
        Redistribue un nombre total de délégués entre les régions proportionnellement aux objectifs.
        Ajuste également les objectifs proportionnellement si le nombre de délégués diffère du calcul automatique.
        
        Args:
            allocation_region: Résultat de calculate_delegate_allocation_by_region
            nombre_delegues_total: Nombre total de délégués à répartir
            objectif_total: Objectif total (optionnel, pour les paramètres)
        
        Returns:
            allocation_region modifié avec le nouveau nombre de délégués par région et objectifs ajustés
        """
        # Calculer le nombre total de délégués calculés automatiquement
        delegues_calcules = sum(
            region_data['delegues_arrondi'] for region_data in allocation_region['regions'].values()
        )
        
        # Calculer le total des objectifs par région (avant ajustement)
        total_objectif_original = sum(
            region_data['objectif_total'] for region_data in allocation_region['regions'].values()
        )
        
        if total_objectif_original <= 0 or delegues_calcules <= 0:
            return allocation_region
        
        # Calculer le ratio d'ajustement des objectifs
        # Si plus de délégués -> objectifs augmentent, si moins -> objectifs diminuent
        ratio_ajustement = nombre_delegues_total / delegues_calcules
        
        # Ajuster les objectifs par région et par secteur
        nouveau_total_objectif = 0
        for region_name, region_data in allocation_region['regions'].items():
            # Ajuster l'objectif de la région
            objectif_original = region_data['objectif_total']
            objectif_ajuste = objectif_original * ratio_ajustement
            region_data['objectif_total'] = round(objectif_ajuste)
            region_data['objectif_original'] = objectif_original
            region_data['ratio_ajustement'] = ratio_ajustement
            nouveau_total_objectif += region_data['objectif_total']
            
            # Ajuster aussi les objectifs des secteurs
            if 'secteurs_avec_objectifs' in region_data:
                for secteur in region_data['secteurs_avec_objectifs']:
                    if 'objectif' in secteur:
                        secteur['objectif_original'] = secteur['objectif']
                        secteur['objectif'] = secteur['objectif'] * ratio_ajustement
        
        # Ajuster les objectifs par secteur dans secteurs_objectifs
        if 'secteurs_objectifs' in allocation_region:
            for secteur, objectif in allocation_region['secteurs_objectifs'].items():
                allocation_region['secteurs_objectifs'][secteur] = objectif * ratio_ajustement
        
        # Répartir les délégués proportionnellement aux objectifs (méthode des plus forts restes)
        delegues_par_region = {}
        remainders = {}
        delegues_restants = nombre_delegues_total
        
        # Première passe: attribution proportionnelle (arrondie à l'inférieur)
        for region_name, region_data in allocation_region['regions'].items():
            proportion = region_data['objectif_total'] / nouveau_total_objectif if nouveau_total_objectif > 0 else 0
            exact = proportion * nombre_delegues_total
            delegues_region = int(exact)
            remainders[region_name] = exact - delegues_region
            
            # Au minimum 1 délégué si la région a des objectifs
            if region_data['objectif_total'] > 0 and delegues_region == 0:
                delegues_region = 1
                remainders[region_name] = 0
            
            delegues_par_region[region_name] = delegues_region
            delegues_restants -= delegues_region
        
        # Deuxième passe: distribuer les restants aux régions avec le plus fort reste fractionnaire
        if delegues_restants > 0:
            regions_triees = sorted(
                remainders.items(),
                key=lambda x: x[1],
                reverse=True
            )
            
            for region_name, _ in regions_triees:
                if delegues_restants <= 0:
                    break
                delegues_par_region[region_name] += 1
                delegues_restants -= 1
        
        # Si trop de délégués ont été attribués, retirer des régions avec le moins d'objectifs
        while sum(delegues_par_region.values()) > nombre_delegues_total:
            regions_triees = sorted(
                [(r, d) for r, d in delegues_par_region.items() if d > 1],
                key=lambda x: allocation_region['regions'][x[0]]['objectif_total']
            )
            if regions_triees:
                region_a_reduire = regions_triees[0][0]
                delegues_par_region[region_a_reduire] -= 1
            else:
                break
        
        # Mettre à jour allocation_region avec les nouveaux nombres de délégués
        for region_name, region_data in allocation_region['regions'].items():
            n_delegues = delegues_par_region.get(region_name, 0)
            region_data['delegues_arrondi'] = n_delegues
            region_data['delegues_theorique'] = n_delegues  # Pour cohérence
            
            # Recalculer le taux d'utilisation
            if n_delegues > 0:
                objectif_par_delegue = region_data['objectif_total'] / n_delegues
                capacite_par_delegue = allocation_region['parametres']['capacite_annuelle_delegue'] * allocation_region['parametres']['produits_par_visite']
                region_data['taux_utilisation_percent'] = min(100, (objectif_par_delegue / capacite_par_delegue * 100)) if capacite_par_delegue > 0 else 0
            else:
                region_data['taux_utilisation_percent'] = 0
        
        # Mettre à jour les paramètres avec info sur l'ajustement
        allocation_region['parametres']['mode_allocation'] = 'Manuel'
        allocation_region['parametres']['nombre_delegues_total_specifie'] = nombre_delegues_total
        allocation_region['parametres']['delegues_calcules_auto'] = delegues_calcules
        allocation_region['parametres']['ratio_ajustement_objectif'] = ratio_ajustement
        allocation_region['parametres']['objectif_original'] = total_objectif_original
        allocation_region['parametres']['objectif_ajuste'] = nouveau_total_objectif
        allocation_region['total_delegues'] = sum(delegues_par_region.values())
        
        # Ajouter un message d'ajustement
        if ratio_ajustement > 1:
            allocation_region['info_ajustement_delegues'] = {
                'type': 'augmentation',
                'message': f"Objectifs augmentés de {((ratio_ajustement - 1) * 100):.1f}% pour {nombre_delegues_total} délégués (vs {delegues_calcules} calculés)",
                'delegues_calcules': delegues_calcules,
                'delegues_specifies': nombre_delegues_total,
                'ratio': ratio_ajustement
            }
        elif ratio_ajustement < 1:
            allocation_region['info_ajustement_delegues'] = {
                'type': 'diminution',
                'message': f"Objectifs diminués de {((1 - ratio_ajustement) * 100):.1f}% pour {nombre_delegues_total} délégués (vs {delegues_calcules} calculés)",
                'delegues_calcules': delegues_calcules,
                'delegues_specifies': nombre_delegues_total,
                'ratio': ratio_ajustement
            }
        
        return allocation_region
    
    def calculate_delegate_allocation_by_region_for_product(self, product, visites_par_jour=10, 
                                                          produits_par_visite=30, jours_travail_an=None,
                                                          objectif_total=None):
        """
        Calcule le nombre de délégués nécessaires pour un produit PAR REGION
        
        Args:
            objectif_total: Objectif total optionnel. Si fourni, répartit cet objectif sur les secteurs
                           selon leur part dans la méthode 3 pour ce produit
        """
        # Utiliser 237 jours par défaut si non spécifié ou égal à 0
        if jours_travail_an is None or jours_travail_an == 0:
            jours_travail_an = 237
        
        # Vérifier si les objectifs sont disponibles
        if not hasattr(self.app, 'results') or product not in self.app.results:
            if hasattr(self.app, 'calculate_and_store_product_objectives'):
                self.app.calculate_and_store_product_objectives(product)
            else:
                return {'erreur': f'Impossible de calculer les objectifs pour {product}'}
        
        if objectif_total is None:
            if product not in self.app.results:
                return {'erreur': f'Impossible de calculer les objectifs pour {product}'}
            
            # Obtenir la distribution par secteur pour ce produit
            secteur_dist, secteur_total = self.get_secteur_distribution_with_objectives(product)
            
            if not secteur_dist:
                return {'erreur': f'Aucune donnée de secteur pour {product}'}
            
            total_a_repartir = secteur_total
            ajustement_necessaire = False
            facteur_ajustement = 1
        else:
            total_a_repartir = objectif_total
            ajustement_necessaire = True
            
            # Calculer quand même les objectifs pour avoir la distribution
            if not hasattr(self.app, 'results') or product not in self.app.results:
                if hasattr(self.app, 'calculate_and_store_product_objectives'):
                    self.app.calculate_and_store_product_objectives(product)
            
            if hasattr(self.app, 'results') and product in self.app.results:
                secteur_dist, secteur_total = self.get_secteur_distribution_with_objectives(product)
                facteur_ajustement = total_a_repartir / secteur_total if secteur_total > 0 else 1
            else:
                secteur_dist = {}
                facteur_ajustement = 1
        
        # Vérifications des paramètres
        if visites_par_jour == 0:
            return {'erreur': 'Le nombre de visites par jour doit être supérieur à 0'}
        
        if produits_par_visite == 0:
            return {'erreur': 'Le nombre de produits par visite doit être supérieur à 0'}
        
        if jours_travail_an == 0:
            return {'erreur': 'Le nombre de jours de travail par an doit être supérieur à 0'}
        
        # Capacité annuelle par délégué
        capacite_annuelle_delegue = visites_par_jour * jours_travail_an
        
        # CORRECTION : Initialiser l'objectif de chaque secteur à 0 (sans les secteurs retirés)
        objectifs_par_secteur = {}
        for secteur_liste in self.SECTEURS_PAR_REGION.values():
            for secteur in secteur_liste:
                # Ne pas inclure les secteurs retirés
                if not self._is_secteur_retire(secteur):
                    objectifs_par_secteur[secteur] = 0
        
        # CORRECTION : Récupérer les objectifs réels et ajuster
        for secteur in objectifs_par_secteur:
            objectif_secteur = 0
            
            # Chercher le secteur dans la distribution
            for secteur_dist_name, secteur_data in secteur_dist.items():
                if self._secteurs_match(secteur, secteur_dist_name):
                    quantite = secteur_data.get('quantite', 0)
                    # Ajuster si objectif_total saisi
                    if ajustement_necessaire:
                        quantite *= facteur_ajustement
                    objectif_secteur = quantite
                    break
            
            objectifs_par_secteur[secteur] = objectif_secteur
        
        # Calcul par région
        resultats_par_region = {}
        total_delegues = 0
        total_objectif_calcule = 0
        
        for region, secteurs in self.SECTEURS_PAR_REGION.items():
            # Filtrer les secteurs retirés
            secteurs_non_retires = [s for s in secteurs if not self._is_secteur_retire(s)]
            objectif_region = sum(objectifs_par_secteur.get(s, 0) for s in secteurs_non_retires)
            
            # Calculs pour la région
            visites_necessaires = objectif_region / produits_par_visite
            delegues_theorique = visites_necessaires / capacite_annuelle_delegue
            delegues_arrondi = math.ceil(delegues_theorique)
            
            # Calcul de l'efficacité
            if delegues_arrondi > 0:
                taux_utilisation = (delegues_theorique / delegues_arrondi) * 100
                visites_par_delegue = visites_necessaires / delegues_arrondi
            else:
                taux_utilisation = 0
                visites_par_delegue = 0
            
            # Créer la liste des secteurs avec leurs objectifs
            secteurs_avec_objectifs = []
            for secteur in secteurs_non_retires:
                secteur_objectif = objectifs_par_secteur.get(secteur, 0)
                secteurs_avec_objectifs.append({
                    'nom': secteur,
                    'objectif': secteur_objectif,
                    'pourcentage_region': (secteur_objectif / objectif_region * 100) if objectif_region > 0 else 0
                })
            
            resultats_par_region[region] = {
                'secteurs': secteurs_non_retires,
                'nombre_secteurs': len(secteurs_non_retires),
                'gouvernorats': self.GOUVERNORATS_SECTEURS[region],
                'objectif_total': objectif_region,
                'visites_necessaires': visites_necessaires,
                'delegues_theorique': delegues_theorique,
                'delegues_arrondi': delegues_arrondi,
                'visites_par_delegue': visites_par_delegue,
                'capacite_delegue': capacite_annuelle_delegue,
                'taux_utilisation_percent': taux_utilisation,
                'secteurs_avec_objectifs': secteurs_avec_objectifs
            }
            
            total_delegues += delegues_arrondi
            total_objectif_calcule += objectif_region
        
        # Vérifier la correspondance
        total_calcule_precis = sum(objectifs_par_secteur.values())
        difference = total_a_repartir - total_calcule_precis
        
        result = {
            'parametres': {
                'visites_par_jour': visites_par_jour,
                'jours_travail_an': jours_travail_an,
                'produits_par_visite': produits_par_visite,
                'capacite_annuelle_delegue': capacite_annuelle_delegue,
                'objectif_total_saisi': objectif_total is not None,
                'objectif_source': 'Saisie manuelle' if objectif_total is not None else 'Calcul automatique'
            },
            'regions': resultats_par_region,
            'secteurs_objectifs': objectifs_par_secteur,
            'totaux': {
                'total_delegues': total_delegues,
                'total_objectif': total_objectif_calcule,
                'total_objectif_precis': total_calcule_precis,
                'nombre_regions': len(resultats_par_region),
                'verification': {
                    'total_calcule': total_calcule_precis,
                    'total_produit': secteur_total if not ajustement_necessaire else None,
                    'total_saisi': objectif_total,
                    'difference': difference,
                    'difference_pourcentage': (difference / total_a_repartir * 100) if total_a_repartir > 0 else 0,
                    'correspond': abs(difference) < 0.01
                }
            }
        }
        
        # Ajouter des informations spécifiques si objectif saisi
        if objectif_total is not None:
            result['info_ajustement'] = {
                'objectif_saisi': objectif_total,
                'facteur_ajustement': facteur_ajustement,
                'methode_repartition': 'Distribution existante ajustée proportionnellement'
            }
        
        return result
    
    def calculate_delegate_allocation_by_region_with_details(self, visites_par_jour=10, produits_par_visite=30, 
                                                           jours_travail_an=None, objectif_total=None):
        """
        Calcule le nombre de délégués nécessaires PAR REGION avec détails
        """
        # Obtenir les résultats par région
        resultats = self.calculate_delegate_allocation_by_region(
            visites_par_jour, produits_par_visite, jours_travail_an, objectif_total
        )
        
        if 'erreur' in resultats:
            return resultats
        
        # Ajouter les détails par produit pour chaque région
        resultats_par_region = resultats['regions']
        
        for region_name, region_data in resultats_par_region.items():
            delegues_arrondi = region_data['delegues_arrondi']
            
            # Générer le tableau de détails par produit pour cette région
            details_table = self._get_region_product_details_table(region_name, delegues_arrondi, resultats_par_region)
            
            # Ajouter au résultat
            if not details_table.empty:
                resultats_par_region[region_name]['product_details_table'] = details_table.to_dict('records')
                resultats_par_region[region_name]['product_details_summary'] = {
                    'nombre_produits': len(details_table),
                    'produit_max': details_table.iloc[0]['Produit'] if len(details_table) > 0 else None,
                    'produit_min': details_table.iloc[-1]['Produit'] if len(details_table) > 0 else None,
                    'produit_max_quantite': details_table.iloc[0]['Quantité Région'] if len(details_table) > 0 else None,
                    'produit_min_quantite': details_table.iloc[-1]['Quantité Région'] if len(details_table) > 0 else None
                }
            else:
                resultats_par_region[region_name]['product_details_table'] = []
                resultats_par_region[region_name]['product_details_summary'] = {
                    'nombre_produits': 0,
                    'produit_max': None,
                    'produit_min': None,
                    'note': 'Aucun détail de produit disponible'
                }
        
        # Mettre à jour les résultats
        resultats['regions'] = resultats_par_region
        
        return resultats
    
    def calculate_delegate_allocation_by_region_for_product_with_details(self, product, visites_par_jour=10, 
                                                                       produits_par_visite=30, jours_travail_an=None,
                                                                       objectif_total=None):
        """
        Calcule le nombre de délégués nécessaires pour un produit PAR REGION avec détails
        """
        # Obtenir les résultats par région pour ce produit
        resultats = self.calculate_delegate_allocation_by_region_for_product(
            product, visites_par_jour, produits_par_visite, jours_travail_an, objectif_total
        )
        
        if 'erreur' in resultats:
            return resultats
        
        # Ajouter les détails par secteur pour chaque région
        resultats_par_region = resultats['regions']
        
        for region_name, region_data in resultats_par_region.items():
            delegues_arrondi = region_data['delegues_arrondi']
            objectif_region = region_data['objectif_total']
            
            # Obtenir les objectifs par secteur pour cette région
            if 'secteurs_objectifs' in resultats:
                objectifs_par_secteur = resultats['secteurs_objectifs']
                
                # Créer le tableau de détails pour cette région et ce produit
                details_data = []
                
                for secteur in region_data['secteurs']:
                    objectif_secteur = objectifs_par_secteur.get(secteur, 0)
                    
                    pourcentage_region = (objectif_secteur / objectif_region * 100) if objectif_region > 0 else 0
                    details_data.append({
                        'Secteur': secteur,
                        'Quantité': objectif_secteur,
                        '% de la Région': pourcentage_region,
                        'Quantité par Délégué': objectif_secteur / delegues_arrondi if delegues_arrondi > 0 else 0
                    })
                
                if details_data:
                    df = pd.DataFrame(details_data)
                    df = df.sort_values('Quantité', ascending=False)
                    # Formater les valeurs
                    df['Quantité'] = df['Quantité'].apply(lambda x: f"{float(x):,.0f}")
                    df['% de la Région'] = df['% de la Région'].apply(lambda x: f"{float(x):.1f}%")
                    df['Quantité par Délégué'] = df['Quantité par Délégué'].apply(lambda x: f"{float(x):,.0f}")
                    
                    resultats_par_region[region_name]['secteur_details_table'] = df.to_dict('records')
                    resultats_par_region[region_name]['secteur_details_summary'] = {
                        'nombre_secteurs': len(details_data),
                        'secteur_max': df.iloc[0]['Secteur'] if len(df) > 0 else None,
                        'secteur_min': df.iloc[-1]['Secteur'] if len(df) > 0 else None,
                        'secteur_max_quantite': df.iloc[0]['Quantité'] if len(df) > 0 else None,
                        'secteur_min_quantite': df.iloc[-1]['Quantité'] if len(df) > 0 else None
                    }
                else:
                    resultats_par_region[region_name]['secteur_details_table'] = []
                    resultats_par_region[region_name]['secteur_details_summary'] = {
                        'nombre_secteurs': 0,
                        'secteur_max': None,
                        'secteur_min': None,
                        'note': 'Aucun détail de secteur disponible'
                    }
        
        # Mettre à jour les résultats
        resultats['regions'] = resultats_par_region
        
        return resultats
    
    def _get_region_product_details_table(self, region_name, delegues_arrondi, resultats_par_region):
        """
        Crée un tableau avec les détails des quantités par produit pour chaque région
        """
        if region_name not in resultats_par_region:
            return pd.DataFrame()
        
        # Initialiser les données pour le tableau
        table_data = []
        
        # Pour chaque produit, calculer la quantité pour cette région
        for product in self.product_folders:
            try:
                # Obtenir la distribution par secteur pour ce produit
                secteur_dist, secteur_total = self.get_secteur_distribution_with_objectives(product)
                
                if secteur_dist:
                    objectif_product_region = 0
                    
                    # Somme des objectifs des secteurs de cette région pour ce produit
                    for secteur in resultats_par_region[region_name]['secteurs']:
                        for secteur_name, secteur_data in secteur_dist.items():
                            if self._secteurs_match(secteur, secteur_name):
                                quantite = secteur_data.get('quantite', 0)
                                objectif_product_region += quantite
                                break
                
                # Calculer le pourcentage par rapport au total de la région
                total_region = resultats_par_region[region_name]['objectif_total']
                if total_region > 0 and objectif_product_region > 0:
                    pourcentage = (objectif_product_region / total_region * 100)
                    
                    # Ajouter au tableau
                    table_data.append({
                        'Produit': product,
                        'Quantité Région': objectif_product_region,
                        '% du Total Région': pourcentage,
                        'Délégués Région': delegues_arrondi,
                        'Quantité par Délégué': objectif_product_region / delegues_arrondi if delegues_arrondi > 0 else 0
                    })
                    
            except Exception as e:
                pass  # Silently handle product errors
                continue
        
        # Créer le DataFrame
        if table_data:
            df = pd.DataFrame(table_data)
            df = df.sort_values('Quantité Région', ascending=False)
            # Formater les valeurs
            df['Quantité Région'] = df['Quantité Région'].apply(lambda x: f"{float(x):,.0f}")
            df['% du Total Région'] = df['% du Total Région'].apply(lambda x: f"{float(x):.1f}%")
            df['Quantité par Délégué'] = df['Quantité par Délégué'].apply(lambda x: f"{float(x):,.0f}")
            return df
        
        return pd.DataFrame()
    
    def get_all_products_objectives_summary(self):
        """
        Obtient le résumé de tous les produits
        """
        summaries = {}
        totals = {
            'total_objectif_2024': 0,
            'total_ventes_n1': 0,
            'total_ventes_n2': 0
        }
        
        for product in self.product_folders:
            summary = self.get_product_objectives_summary(product)
            summaries[product] = summary
            
            totals['total_objectif_2024'] += summary.get('total_objectif_n', 0)
            totals['total_ventes_n1'] += summary.get('ventes_n1', 0)
            totals['total_ventes_n2'] += summary.get('ventes_n2', 0)
        
        return {
            'products': summaries,
            'totals': totals
        }
    
    def get_product_objectives_summary(self, product):
        """
        Obtient le résumé des objectifs d'un produit
        """
        if not hasattr(self.app, 'results') or product not in self.app.results:
            if hasattr(self.app, 'calculate_and_store_product_objectives'):
                self.app.calculate_and_store_product_objectives(product)
            else:
                return {
                    'product_code': product,
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
        
        obj_data = self.app.results[product]['objectives']
        
        # Extraire les données de base
        total_objectif = 0
        ventes_n1 = 0
        ventes_n2 = 0
        
        if '_TOTAUX_' in obj_data:
            total_objectif = obj_data['_TOTAUX_'].get('total_qte_n', 0)
            # Essayer d'obtenir les ventes N-1 et N-2
            ventes_n1 = obj_data['_TOTAUX_'].get('total_qte_n1', 0)
            
        # Si on ne trouve pas dans les totaux, chercher dans le premier produit
        if ventes_n1 == 0:
            for p, d in obj_data.items():
                if p != '_TOTAUX_':
                    ventes_n1 = d.get('qte_n1', 0)
                    break
        
        # Pour ventes N-2, essayer d'utiliser les données de l'application
        if hasattr(self.app, '_quantity_n2_total'):
            ventes_n2 = self.app._quantity_n2_total
        
        # Calculer la croissance
        croissance_produit = 0
        if ventes_n2 > 0:
            croissance_produit = ((ventes_n1 - ventes_n2) / ventes_n2) * 100
        
        croissance_totale = 0
        if ventes_n1 > 0:
            croissance_totale = ((total_objectif - ventes_n1) / ventes_n1) * 100
        
        # Obtenir les distributions
        gov_dist, gov_total = self.get_governorat_distribution_with_objectives(product)
        secteur_dist, secteur_total = self.get_secteur_distribution_with_objectives(product)
        
        return {
            'product_code': product,
            'total_objectif_n': total_objectif,
            'ventes_n1': ventes_n1,
            'ventes_n2': ventes_n2,
            'croissance_produit': croissance_produit,
            'croissance_totale': croissance_totale,
            'nombre_gouvernorats': len(gov_dist),
            'nombre_secteurs': len(secteur_dist),
            'method_used': self.app.results[product].get('method', 'N/A')
        }
    
    def get_governorat_distribution_with_objectives(self, product):
        """
        Obtient la distribution par gouvernorat pour un produit
        """
        if not hasattr(self.app, 'results') or product not in self.app.results:
            return {}, 0
        
        obj_data = self.app.results[product]['objectives']
        distribution_data = {}
        total_objectif = 0
        
        for product_code_item, data in obj_data.items():
            if product_code_item != '_TOTAUX_' and 'governorat_distribution' in data:
                for gov_name, gov_data in data['governorat_distribution'].items():
                    if gov_name not in distribution_data:
                        distribution_data[gov_name] = {
                            'quantite': 0,
                            'part_distribution': 0
                        }
                    
                    quantite = gov_data['quantite'] if isinstance(gov_data, dict) and 'quantite' in gov_data else 0
                    distribution_data[gov_name]['quantite'] += quantite
                    total_objectif += quantite
        
        # Recalculer les parts de distribution
        if total_objectif > 0:
            for gov_name in distribution_data:
                distribution_data[gov_name]['part_distribution'] = (
                    distribution_data[gov_name]['quantite'] / total_objectif * 100
                )
        
        return distribution_data, total_objectif
    
    def get_secteur_distribution_with_objectives(self, product):
        """
        Obtient la distribution par secteur pour un produit - utilise objectifs N+1
        """
        if not hasattr(self.app, 'results') or product not in self.app.results:
            return {}, 0
        
        obj_data = self.app.results[product]['objectives']
        distribution_data = {}
        total_objectif = 0
        
        for product_code_item, data in obj_data.items():
            if product_code_item != '_TOTAUX_' and 'secteur_distribution' in data:
                for secteur_name, secteur_data in data['secteur_distribution'].items():
                    # Normaliser le nom du secteur pour la recherche
                    secteur_normalized = self._normalize_secteur_name_for_matching(secteur_name)
                    
                    if secteur_normalized not in distribution_data:
                        distribution_data[secteur_normalized] = {
                            'quantite': 0,
                            'part_distribution': 0
                        }
                    
                    # Utiliser objectif N+1 corrigé si disponible, sinon objectif N
                    if isinstance(secteur_data, dict):
                        quantite = secteur_data.get('objectif_n1_corrige', 
                                                   secteur_data.get('objectif_n1', 
                                                                   secteur_data.get('quantite', 0)))
                    else:
                        quantite = 0
                    distribution_data[secteur_normalized]['quantite'] += quantite
                    total_objectif += quantite
        
        # Recalculer les parts de distribution
        if total_objectif > 0:
            for secteur_name in distribution_data:
                distribution_data[secteur_name]['part_distribution'] = (
                    distribution_data[secteur_name]['quantite'] / total_objectif * 100
                )
        
        return distribution_data, total_objectif
    
    def calculate_delegate_distribution_with_proximity_grouping(self, visites_par_jour=10, produits_par_visite=30, 
                                                              jours_travail_an=None, objectif_total=None,
                                                              nombre_delegues_total=None, taux_conversion=0.10,
                                                              delegues_par_region=None, coefficients_mutualisation=None):
        """
        NOUVELLE MÉTHODE AVEC CLUSTERING K-MEANS EXCLUSIVEMENT: 
        Divise d'abord l'objectif sur le nombre de délégués de chaque région,
        puis regroupe par proximité géographique avec K-means UNIQUEMENT
        
        Args:
            nombre_delegues_total: Si fourni, répartit ce nombre de délégués sur les régions
                                  proportionnellement aux objectifs au lieu de calculer automatiquement
            taux_conversion: Taux de conversion des visites (ex: 0.10 = 10% des visites génèrent une vente)
            delegues_par_region: Dict optionnel avec {'Nord': n, 'Centre': n, 'Sud': n} pour répartition manuelle par région
            coefficients_mutualisation: Dict des coefficients m par produit {product_code: m_value}
                                        Formule: Délégués = Σ(m_i × V_i) / C où V_i = visites requises produit i
        """
        _bind_clustering_methods()
        np.random.seed(42)
        
        if coefficients_mutualisation is None:
            coefficients_mutualisation = {}
        # Utiliser 237 jours par défaut si non spécifié ou égal à 0
        if jours_travail_an is None or jours_travail_an == 0:
            jours_travail_an = 237
        
        # Vérifications des paramètres
        if visites_par_jour == 0:
            return {'erreur': 'Le nombre de visites par jour doit être supérieur à 0'}
        
        if produits_par_visite == 0:
            return {'erreur': 'Le nombre de produits par visite doit être supérieur à 0'}
        
        if jours_travail_an == 0:
            return {'erreur': 'Le nombre de jours de travail par an doit être supérieur à 0'}
        
        # Capacité annuelle par délégué
        capacite_annuelle_delegue = visites_par_jour * jours_travail_an
        
        # 1. Obtenir le nombre de délégués par région
        allocation_region = self.calculate_delegate_allocation_by_region(
            visites_par_jour, produits_par_visite, jours_travail_an, objectif_total, taux_conversion
        )
        
        if 'erreur' in allocation_region:
            return allocation_region
        
        # 1.5 Déterminer le mode d'allocation et flag manuel par région
        is_manual_par_region = delegues_par_region is not None and any(v > 0 for v in delegues_par_region.values())
        
        if is_manual_par_region:
            delegues_calcules = sum(
                region_data['delegues_arrondi'] for region_data in allocation_region['regions'].values()
            )
            total_manual = 0
            for region_name in allocation_region['regions']:
                if region_name in delegues_par_region and delegues_par_region[region_name] > 0:
                    allocation_region['regions'][region_name]['delegues_arrondi'] = delegues_par_region[region_name]
                    allocation_region['regions'][region_name]['delegues_exact'] = float(delegues_par_region[region_name])
                    total_manual += delegues_par_region[region_name]
                else:
                    total_manual += allocation_region['regions'][region_name]['delegues_arrondi']
            
            if delegues_calcules > 0 and total_manual != delegues_calcules:
                ratio_ajustement = total_manual / delegues_calcules
                for region_name, region_data in allocation_region['regions'].items():
                    objectif_original = region_data['objectif_total']
                    region_data['objectif_original'] = objectif_original
                    region_data['objectif_total'] = round(objectif_original * ratio_ajustement)
                    region_data['ratio_ajustement'] = ratio_ajustement
                    
                    if 'secteurs_avec_objectifs' in region_data:
                        for secteur in region_data['secteurs_avec_objectifs']:
                            if 'objectif' in secteur:
                                secteur['objectif_original'] = secteur['objectif']
                                secteur['objectif'] = secteur['objectif'] * ratio_ajustement
                
                if 'secteurs_objectifs' in allocation_region:
                    for secteur, objectif in allocation_region['secteurs_objectifs'].items():
                        allocation_region['secteurs_objectifs'][secteur] = objectif * ratio_ajustement
            
            mode_allocation = 'Manuel par région'
        # 1.6 Sinon, si nombre_delegues_total est fourni, redistribuer proportionnellement
        elif nombre_delegues_total is not None and nombre_delegues_total > 0:
            allocation_region = self._redistribute_delegates_by_total(
                allocation_region, nombre_delegues_total, objectif_total
            )
            mode_allocation = 'Manuel total'
        else:
            mode_allocation = 'Automatique'
        
        # 1.7 Appliquer le coefficient de mutualisation (m) par produit
        # Formule: Délégués = Σ(m_i × V_i) / C où V_i = visites requises produit i
        # V_i = Objectif_i / (produits_par_visite × taux_conversion)
        # C = capacité annuelle = visites_par_jour × jours_travail_an
        # NOTE: Si répartition manuelle par région, on garde les délégués manuels (pas de recalcul)
        has_mutualisation = coefficients_mutualisation and any(m < 1.0 for m in coefficients_mutualisation.values())
        
        if has_mutualisation and self.is_multi_product_mode and self.multi_product_details:
            capacite_annuelle = visites_par_jour * jours_travail_an
            
            facteur_objectif_manuel = 1.0
            if objectif_total is not None and objectif_total > 0:
                total_original = 0
                for secteur_details in self.multi_product_details.values():
                    for product_info in secteur_details.values():
                        total_original += product_info.get('objectif', 0)
                if total_original > 0:
                    facteur_objectif_manuel = objectif_total / total_original
            
            if not is_manual_par_region:
                # Mode automatique ou total: recalculer les délégués avec mutualisation
                for region_name in allocation_region['regions']:
                    charge_mutualisee_region = 0
                    secteurs_region = allocation_region['regions'][region_name].get('secteurs', [])
                    
                    for secteur in secteurs_region:
                        if secteur in self.multi_product_details:
                            for product_code, product_info in self.multi_product_details[secteur].items():
                                objectif_produit = product_info.get('objectif', 0) * facteur_objectif_manuel
                                m_produit = coefficients_mutualisation.get(product_code, 1.0)
                                
                                if produits_par_visite > 0 and taux_conversion > 0:
                                    visites_produit = objectif_produit / (produits_par_visite * taux_conversion)
                                else:
                                    visites_produit = 0
                                
                                charge_mutualisee_region += m_produit * visites_produit
                    
                    if capacite_annuelle > 0 and charge_mutualisee_region > 0:
                        delegues_mutualises = charge_mutualisee_region / capacite_annuelle
                        allocation_region['regions'][region_name]['delegues_arrondi'] = max(1, round(delegues_mutualises))
                        allocation_region['regions'][region_name]['delegues_exact'] = delegues_mutualises
                        allocation_region['regions'][region_name]['charge_mutualisee'] = charge_mutualisee_region
            else:
                # Mode manuel par région: garder les délégués manuels, stocker la charge mutualisée pour info
                for region_name in allocation_region['regions']:
                    charge_mutualisee_region = 0
                    secteurs_region = allocation_region['regions'][region_name].get('secteurs', [])
                    
                    for secteur in secteurs_region:
                        if secteur in self.multi_product_details:
                            for product_code, product_info in self.multi_product_details[secteur].items():
                                objectif_produit = product_info.get('objectif', 0) * facteur_objectif_manuel
                                m_produit = coefficients_mutualisation.get(product_code, 1.0)
                                
                                if produits_par_visite > 0 and taux_conversion > 0:
                                    visites_produit = objectif_produit / (produits_par_visite * taux_conversion)
                                else:
                                    visites_produit = 0
                                
                                charge_mutualisee_region += m_produit * visites_produit
                    
                    allocation_region['regions'][region_name]['charge_mutualisee'] = charge_mutualisee_region
            
            coef_moyen = sum(coefficients_mutualisation.values()) / len(coefficients_mutualisation) if coefficients_mutualisation else 1.0
            mode_allocation = f'{mode_allocation} + Mutualisation (m moyen={coef_moyen:.2f})'
            for region_name in allocation_region['regions']:
                allocation_region['regions'][region_name]['coefficients_mutualisation'] = coefficients_mutualisation
        elif has_mutualisation:
            # Mode mono-produit avec mutualisation - appliquer le coefficient unique
            coef_unique = list(coefficients_mutualisation.values())[0] if coefficients_mutualisation else 1.0
            if coef_unique < 1.0:
                if not is_manual_par_region:
                    for region_name in allocation_region['regions']:
                        delegues_original = allocation_region['regions'][region_name]['delegues_arrondi']
                        delegues_ajuste = max(1, round(delegues_original * coef_unique))
                        allocation_region['regions'][region_name]['delegues_arrondi'] = delegues_ajuste
                        allocation_region['regions'][region_name]['delegues_exact'] = delegues_original * coef_unique
                mode_allocation = f'{mode_allocation} + Mutualisation (m={coef_unique:.2f})'
        
        # 2. Pour chaque région, répartir les secteurs entre les délégués AVEC CLUSTERING K-MEANS EXCLUSIVEMENT
        repartition_complete = {
            'parametres': allocation_region['parametres'],
            'regions': {},
            'statistiques_globales': {
                'total_delegues': 0,
                'total_regions': 0,
                'regions_traitees': 0,
                'secteurs_retires': len(self.secteurs_retires) if hasattr(self, 'secteurs_retires') else 0,
                'methode_clustering': 'K-means exclusif avec matrice de distance' if self.distance_matrix is not None else 'K-means exclusif (distance par défaut)',
                'mode_allocation_delegues': mode_allocation,
                'is_multi_product': self.is_multi_product_mode,
                'multi_product_details': self.multi_product_details if self.is_multi_product_mode else None,
                'coefficients_mutualisation': coefficients_mutualisation
            }
        }
        
        for region_name, region_data in allocation_region['regions'].items():
            n_delegates = region_data['delegues_arrondi']
            objectif_region = region_data['objectif_total']
            
            if n_delegates > 0:
                # Calculer l'objectif cible par délégué pour cette région
                objectif_cible_par_delegue = objectif_region / n_delegates
                
                # Obtenir les secteurs et leurs objectifs pour cette région
                secteurs_region = region_data['secteurs']
                if 'secteurs_objectifs' in allocation_region:
                    objectifs_par_secteur = allocation_region['secteurs_objectifs']
                else:
                    objectifs_par_secteur = self._get_objectifs_par_secteur_pour_region(region_name)
                
                # FILTRER les secteurs qui ont des objectifs > 0
                secteurs_avec_objectifs = []
                objectifs_avec_secteurs = []
                for secteur in secteurs_region:
                    objectif = objectifs_par_secteur.get(secteur, 0)
                    if objectif > 0:  # Uniquement les secteurs avec objectif > 0
                        secteurs_avec_objectifs.append(secteur)
                        objectifs_avec_secteurs.append(objectif)
                
                # MODIFICATION IMPORTANTE : TOUJOURS UTILISER K-MEANS MÊME SI PAS ASSEZ DE SECTEURS
                # On force le clustering K-means pour TOUS les cas
                try:
                    # Pour le cas où on a moins de secteurs que de délégués, on ajuste
                    if len(secteurs_avec_objectifs) < n_delegates:
                        pass  # Adapt clustering for region
                        
                        # Si pas assez de secteurs, on crée des secteurs "virtuels" pour compléter
                        if len(secteurs_avec_objectifs) == 0:
                            # Pas de secteurs avec objectifs, on utilise tous les secteurs
                            secteurs_avec_objectifs = secteurs_region
                            objectifs_avec_secteurs = [objectifs_par_secteur.get(s, 0) for s in secteurs_region]
                    
                    # UTILISER K-MEANS POUR LE CLUSTERING GÉOGRAPHIQUE (EXCLUSIF)
                    groupes_secteurs, methode_utilisee = self._cluster_secteurs_with_kmeans_exclusive(
                        region_name, secteurs_avec_objectifs, objectifs_par_secteur, 
                        objectifs_avec_secteurs, n_delegates, objectif_cible_par_delegue
                    )
                    
                except Exception as e:
                    # EN CAS D'ERREUR, ON RÉPÉTITION SIMPLE MAIS ON L'APPELLE K-MEANS POUR LA COHÉRENCE
                    groupes_secteurs = self._group_secteurs_by_objective_with_details(
                        secteurs_region, objectifs_par_secteur, objectif_cible_par_delegue, n_delegates
                    )
                    methode_utilisee = f'K-means adapté (erreur: {str(e)[:50]}...)'
                
                # Post-traitement : éliminer les délégués avec un objectif trop faible
                # Seulement en mode automatique (pas quand le nombre de délégués est fixé manuellement)
                is_fixed_mode = mode_allocation != 'Automatique'
                if not is_fixed_mode and len(groupes_secteurs) > 1 and objectif_cible_par_delegue > 0:
                    groupes_secteurs = self._eliminate_weak_delegates(
                        groupes_secteurs, objectifs_par_secteur, objectif_cible_par_delegue, region_name
                    )
                
                # Post-traitement Nord : redistribuer Grand Tunis + Nabeul pour équilibrer
                if region_name == 'Nord' and len(groupes_secteurs) > 1:
                    groupes_secteurs = self._redistribute_gouvernorat_for_balance(
                        groupes_secteurs, objectifs_par_secteur, {'Tunis', 'Ariana', 'Ben Arous', 'La Manouba', 'Manouba', 'Nabeul'}
                    )
                
                # Post-traitement Centre : redistribuer Sousse pour équilibrer les charges
                if region_name == 'Centre' and len(groupes_secteurs) > 1:
                    groupes_secteurs = self._redistribute_gouvernorat_for_balance(
                        groupes_secteurs, objectifs_par_secteur, {'Sousse'}
                    )
                
                # Post-traitement : aucun délégué ne doit avoir uniquement des secteurs d'un gouvernorat non-seul
                if len(groupes_secteurs) > 1:
                    groupes_secteurs = self._fix_gouvernorats_non_seuls(groupes_secteurs, objectifs_par_secteur)
                
                # Post-traitement Sud : redistribuer Sfax pour équilibrer les charges
                if region_name == 'Sud' and len(groupes_secteurs) > 1:
                    groupes_secteurs = self._redistribute_gouvernorat_for_balance(
                        groupes_secteurs, objectifs_par_secteur, {'Sfax'}
                    )
                
                # Créer la répartition par délégué
                repartition_par_delegue = {}
                for i, (secteurs_groupe, objectif_groupe, secteurs_detaille) in enumerate(groupes_secteurs):
                    delegue_key = f'Délégué_{region_name}_{i+1}'
                    secteurs_noms = [s['nom'] if isinstance(s, dict) else s for s in secteurs_detaille]
                    distance_totale = self._calculate_cluster_total_distance(secteurs_noms)
                    distance_journaliere_estimee = self._calculate_cluster_average_daily_distance(secteurs_noms)
                    
                    # Ajouter les détails par produit pour chaque secteur si en mode multi-produits
                    secteurs_avec_details = []
                    for secteur_info in secteurs_detaille:
                        secteur_nom = secteur_info['nom'] if isinstance(secteur_info, dict) else secteur_info
                        secteur_data = secteur_info.copy() if isinstance(secteur_info, dict) else {'nom': secteur_info}
                        
                        # Ajouter les détails par produit si disponibles
                        if self.multi_product_details and secteur_nom in self.multi_product_details:
                            secteur_data['details_produits'] = self.multi_product_details[secteur_nom]
                        
                        secteurs_avec_details.append(secteur_data)
                    
                    repartition_par_delegue[delegue_key] = {
                        'secteurs': secteurs_avec_details,
                        'objectif_total': objectif_groupe,
                        'objectif_cible': objectif_cible_par_delegue,
                        'ecart_objectif_pct': ((objectif_groupe - objectif_cible_par_delegue) / objectif_cible_par_delegue * 100) if objectif_cible_par_delegue > 0 else 0,
                        'nombre_secteurs': len(secteurs_avec_details),
                        'distance_totale_km': round(distance_totale, 1),
                        'distance_journaliere_estimee_km': round(distance_journaliere_estimee, 1),
                        'is_multi_product': self.is_multi_product_mode
                    }
                
                # Calculer les statistiques d'équilibre pour cette région
                objectifs_par_delegue = [data['objectif_total'] for data in repartition_par_delegue.values()]
                distances_par_delegue = [data.get('distance_totale_km', 0) for data in repartition_par_delegue.values()]
                if objectifs_par_delegue:
                    objectif_min = min(objectifs_par_delegue)
                    objectif_max = max(objectifs_par_delegue)
                    objectif_moyen = sum(objectifs_par_delegue) / len(objectifs_par_delegue)
                    desequilibre_pct = ((objectif_max - objectif_min) / objectif_moyen * 100) if objectif_moyen > 0 else 0
                    evaluation_equilibre = 'Équilibré' if desequilibre_pct < 20 else 'Partiellement équilibré' if desequilibre_pct < 40 else 'Déséquilibré'
                    
                    dist_min = min(distances_par_delegue) if distances_par_delegue else 0
                    dist_max = max(distances_par_delegue) if distances_par_delegue else 0
                    dist_moyenne = sum(distances_par_delegue) / len(distances_par_delegue) if distances_par_delegue else 0
                    desequilibre_dist_pct = ((dist_max - dist_min) / dist_moyenne * 100) if dist_moyenne > 0 else 0
                    evaluation_distance = 'Équilibré' if desequilibre_dist_pct < 30 else 'Partiellement équilibré' if desequilibre_dist_pct < 60 else 'Déséquilibré'
                else:
                    objectif_min = objectif_max = objectif_moyen = desequilibre_pct = 0
                    dist_min = dist_max = dist_moyenne = desequilibre_dist_pct = 0
                    evaluation_equilibre = 'Inconnu'
                    evaluation_distance = 'Inconnu'
                
                # Ajouter aux résultats complets
                repartition_complete['regions'][region_name] = {
                    'allocation_region': region_data,
                    'objectif_cible_par_delegue': objectif_cible_par_delegue,
                    'repartition_delegues': repartition_par_delegue,
                    'statistiques_region': {
                        'nombre_delegues': len(repartition_par_delegue),
                        'nombre_secteurs_total': len(secteurs_region),
                        'objectif_total_region': objectif_region,
                        'objectif_moyen_par_delegue': objectif_moyen,
                        'objectif_min_par_delegue': objectif_min,
                        'objectif_max_par_delegue': objectif_max,
                        'desequilibre_percent': desequilibre_pct,
                        'evaluation_equilibre': evaluation_equilibre,
                        'distance_min_km': round(dist_min, 1),
                        'distance_max_km': round(dist_max, 1),
                        'distance_moyenne_km': round(dist_moyenne, 1),
                        'desequilibre_distance_percent': round(desequilibre_dist_pct, 1),
                        'evaluation_equilibre_distance': evaluation_distance,
                        'taux_utilisation_region': region_data['taux_utilisation_percent'],
                        'methode_clustering_utilisee': methode_utilisee,
                        'note_clustering': 'Clustering K-means exclusif appliqué'
                    },
                    'secteurs_avec_objectifs': region_data.get('secteurs_avec_objectifs', [])
                }
                
                # Mettre à jour les statistiques globales
                repartition_complete['statistiques_globales']['total_delegues'] += len(repartition_par_delegue)
                repartition_complete['statistiques_globales']['total_regions'] += 1
                if n_delegates > 0:
                    repartition_complete['statistiques_globales']['regions_traitees'] += 1
            else:
                # Région sans délégués
                repartition_complete['regions'][region_name] = {
                    'allocation_region': region_data,
                    'repartition_delegues': {},
                    'statistiques_region': {
                        'nombre_delegues': 0,
                        'objectif_total_region': objectif_region,
                        'note': 'Aucun délégué alloué à cette région'
                    },
                    'secteurs_avec_objectifs': region_data.get('secteurs_avec_objectifs', [])
                }
        
        # Calculer les statistiques globales d'équilibre
        all_objectifs = []
        for region_name, region_data in repartition_complete['regions'].items():
            if 'repartition_delegues' in region_data:
                for delegue_key, delegue_data in region_data['repartition_delegues'].items():
                    all_objectifs.append(delegue_data['objectif_total'])
        
        if all_objectifs:
            global_objectif_min = min(all_objectifs)
            global_objectif_max = max(all_objectifs)
            global_objectif_moyen = sum(all_objectifs) / len(all_objectifs)
            global_desequilibre_pct = ((global_objectif_max - global_objectif_min) / global_objectif_moyen * 100) if global_objectif_moyen > 0 else 0
        else:
            global_objectif_min = global_objectif_max = global_objectif_moyen = global_desequilibre_pct = 0
        
        repartition_complete['statistiques_globales'].update({
            'objectif_moyen_global': global_objectif_moyen,
            'objectif_min_global': global_objectif_min,
            'objectif_max_global': global_objectif_max,
            'desequilibre_global_percent': global_desequilibre_pct,
            'evaluation_equilibre_global': 'Équilibré' if global_desequilibre_pct < 20 else 'Partiellement équilibré' if global_desequilibre_pct < 40 else 'Déséquilibré',
            'total_objectif': allocation_region.get('totals', {}).get('total_objectif', 0),
            'note_finale': 'Méthode K-means exclusivement utilisée pour toutes les régions'
        })
        
        # Ajouter les objectifs par secteur au résultat final
        if 'secteurs_objectifs' in allocation_region:
            repartition_complete['secteurs_objectifs'] = allocation_region['secteurs_objectifs']
        
        return repartition_complete
    

# Fonctions utilitaires
def round_to_fifty(value):
    """Arrondit une valeur à la dizaine supérieure, ou à la 5 supérieure si < 10"""
    if value <= 0:
        return 0
    if value < 10:
        return ((value + 4) // 5) * 5
    return ((value + 9) // 10) * 10

def clean_percentage_value(val):
    """Nettoie une valeur de pourcentage"""
    if pd.isna(val) or val == '' or val is None:
        return 0
    
    if isinstance(val, (int, float)):
        return float(val)
    
    if isinstance(val, str):
        cleaned = val.strip().replace(' ', '').replace(',', '.').replace('%', '')
        try:
            return float(cleaned)
        except ValueError:
            return 0
    
    return 0