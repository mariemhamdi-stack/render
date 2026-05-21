import gc
import pandas as pd
import numpy as np

_KMeans = None
_StandardScaler = None

def _get_kmeans():
    global _KMeans
    if _KMeans is None:
        from sklearn.cluster import KMeans as _K
        _KMeans = _K
    return _KMeans

def _get_standard_scaler():
    global _StandardScaler
    if _StandardScaler is None:
        from sklearn.preprocessing import StandardScaler as _SS
        _StandardScaler = _SS
    return _StandardScaler


class ClusteringMixin:
    def _cluster_secteurs_with_kmeans_exclusive(self, region_name, secteurs, objectifs_par_secteur,
                                               objectifs_list, n_clusters, objectif_cible_par_delegue):
        """
        Algorithme de répartition en 2 phases:
        Phase 1 (priorité absolue) : Équilibre des objectifs entre délégués — aucune contrainte géographique.
        Phase 2 : Minimisation des distances — sous contrainte d'écart d'objectif ≤ 5% de la moyenne.
        KMeans (n_init=50, random_state=42) fournit le clustering géographique initial.
        """
        secteurs = sorted(secteurs)
        objectifs_list = [objectifs_par_secteur.get(s, 0) for s in secteurs]
        n_clusters_adapted = min(n_clusters, len(secteurs))

        if n_clusters_adapted <= 1:
            groupes = [(
                secteurs,
                sum(objectifs_list),
                [{'nom': s, 'objectif': objectifs_par_secteur.get(s, 0)} for s in secteurs]
            )]
            return groupes, f"1 cluster ({len(secteurs)} secteurs)"

        try:
            # ── CLUSTERING INITIAL: KMeans sur les distances géographiques ──────────
            distance_features = self._prepare_distance_features_exclusive(secteurs, region_name)
            kmeans = _get_kmeans()(
                n_clusters=n_clusters_adapted,
                init='k-means++',
                n_init=50,
                max_iter=300,
                tol=1e-4,
                random_state=42,
                algorithm='lloyd'
            )
            cluster_labels = kmeans.fit_predict(distance_features)
            del kmeans, distance_features
            gc.collect()

            delegate_secteurs = [[] for _ in range(n_clusters_adapted)]
            for secteur, label in zip(secteurs, cluster_labels):
                delegate_secteurs[label].append(secteur)
            del cluster_labels

            delegate_secteurs = [d for d in delegate_secteurs if d]
            n_actual = len(delegate_secteurs)
            delegate_objectives = [
                sum(objectifs_par_secteur.get(s, 0) for s in d) for d in delegate_secteurs
            ]

            # ── PHASE 1: Équilibre des objectifs (aucune contrainte géographique) ───
            for _ in range(5000):
                max_obj = max(delegate_objectives)
                min_obj = min(delegate_objectives)
                obj_mean = sum(delegate_objectives) / n_actual if n_actual > 0 else 1
                ecart_pct = ((max_obj - min_obj) / obj_mean * 100) if obj_mean > 0 else 0

                if ecart_pct < 2:
                    break

                src_idx = delegate_objectives.index(max_obj)
                tgt_idx = delegate_objectives.index(min_obj)
                gap = max_obj - min_obj
                ideal = gap / 2.0

                best_secteur = None
                best_dist = float('inf')

                for s in sorted(delegate_secteurs[src_idx]):
                    obj = objectifs_par_secteur.get(s, 0)
                    new_gap = abs(
                        (delegate_objectives[src_idx] - obj) - (delegate_objectives[tgt_idx] + obj)
                    )
                    if new_gap >= gap:
                        continue
                    d = abs(obj - ideal)
                    if d < best_dist:
                        best_dist = d
                        best_secteur = s

                if best_secteur is None:
                    break

                delegate_secteurs[src_idx].remove(best_secteur)
                delegate_secteurs[tgt_idx].append(best_secteur)
                obj_moved = objectifs_par_secteur.get(best_secteur, 0)
                delegate_objectives[src_idx] -= obj_moved
                delegate_objectives[tgt_idx] += obj_moved

            # ── PHASE 2: Optimisation des distances (écart objectif ≤ 5%) ───────────
            obj_mean = sum(delegate_objectives) / n_actual if n_actual > 0 else 0
            max_deviation = obj_mean * 0.05

            passes = 0
            while passes < 50:
                passes += 1
                km_distances = [
                    self._calculate_cluster_average_daily_distance(d) for d in delegate_secteurs
                ]

                swap_done = False
                for i in range(n_actual):
                    if swap_done:
                        break
                    for j in range(i + 1, n_actual):
                        if swap_done:
                            break
                        for s_i in list(delegate_secteurs[i]):
                            if swap_done:
                                break
                            for s_j in list(delegate_secteurs[j]):
                                obj_i = objectifs_par_secteur.get(s_i, 0)
                                obj_j = objectifs_par_secteur.get(s_j, 0)
                                new_obj_i = delegate_objectives[i] - obj_i + obj_j
                                new_obj_j = delegate_objectives[j] - obj_j + obj_i

                                if abs(new_obj_i - obj_mean) > max_deviation * 2:
                                    continue
                                if abs(new_obj_j - obj_mean) > max_deviation * 2:
                                    continue

                                new_sects_i = [s for s in delegate_secteurs[i] if s != s_i] + [s_j]
                                new_sects_j = [s for s in delegate_secteurs[j] if s != s_j] + [s_i]
                                new_km_i = self._calculate_cluster_average_daily_distance(new_sects_i)
                                new_km_j = self._calculate_cluster_average_daily_distance(new_sects_j)

                                if new_km_i + new_km_j < km_distances[i] + km_distances[j] - 0.1:
                                    delegate_secteurs[i] = new_sects_i
                                    delegate_secteurs[j] = new_sects_j
                                    delegate_objectives[i] = new_obj_i
                                    delegate_objectives[j] = new_obj_j
                                    swap_done = True
                                    break

                if not swap_done:
                    break

            # ── RÉSULTAT FINAL ────────────────────────────────────────────────────────
            groupes_secteurs = []
            for sects, obj in zip(delegate_secteurs, delegate_objectives):
                if sects:
                    secteurs_detaille = [
                        {'nom': s, 'objectif': objectifs_par_secteur.get(s, 0)} for s in sorted(sects)
                    ]
                    groupes_secteurs.append((sects, obj, secteurs_detaille))

            groupes_secteurs.sort(key=lambda x: x[1], reverse=True)
            return groupes_secteurs, f"2 phases (k={n_clusters_adapted}): objectifs équilibrés + distances optimisées"

        except Exception as e:
            groupes_secteurs = self._group_secteurs_simple_fallback(
                secteurs, objectifs_par_secteur, objectifs_list, n_clusters_adapted
            )
            return groupes_secteurs, f"Fallback (erreur: {str(e)[:50]}...)"
    
    def _prepare_distance_features_exclusive(self, secteurs, region_name):
        """
        Prépare les caractéristiques de distance pour le clustering K-means exclusif
        """
        # Créer une matrice des distances
        n_secteurs = len(secteurs)
        
        if self.distance_matrix is not None:
            distance_matrix = np.zeros((n_secteurs, n_secteurs))
            
            for i, secteur_i in enumerate(secteurs):
                for j, secteur_j in enumerate(secteurs):
                    if i == j:
                        distance_matrix[i, j] = 0
                    else:
                        # Chercher la distance dans la matrice
                        try:
                            # Essayer différentes variations du nom
                            distances = []
                            
                            # Format original
                            if secteur_i in self.distance_matrix.index and secteur_j in self.distance_matrix.columns:
                                dist = self.distance_matrix.loc[secteur_i, secteur_j]
                                if not pd.isna(dist):
                                    distances.append(dist)
                            
                            # Essayer sans espace
                            secteur_i_simple = secteur_i.replace(' ', '')
                            secteur_j_simple = secteur_j.replace(' ', '')
                            if secteur_i_simple in self.distance_matrix.index and secteur_j_simple in self.distance_matrix.columns:
                                dist = self.distance_matrix.loc[secteur_i_simple, secteur_j_simple]
                                if not pd.isna(dist):
                                    distances.append(dist)
                            
                            # Prendre la distance moyenne si plusieurs valeurs trouvées
                            if distances:
                                distance_matrix[i, j] = sum(distances) / len(distances)
                            else:
                                # Distance par défaut basée sur la région
                                distance_matrix[i, j] = self._get_default_distance(region_name)
                                
                        except Exception:
                            distance_matrix[i, j] = self._get_default_distance(region_name)
        else:
            # Pas de matrice de distance, utiliser des distances par défaut
            distance_matrix = np.full((n_secteurs, n_secteurs), self._get_default_distance(region_name))
            np.fill_diagonal(distance_matrix, 0)
        
        if n_secteurs > 1:
            try:
                scaler = _get_standard_scaler()()
                distance_features = scaler.fit_transform(distance_matrix)
                del scaler, distance_matrix
                return distance_features
            except:
                return distance_matrix
        else:
            return distance_matrix
    
    def _get_default_distance(self, region_name):
        """Retourne une distance par défaut basée sur la région"""
        default_distances = {
            'Nord': 50,   # km par défaut pour le Nord
            'Centre': 75, # km par défaut pour le Centre
            'Sud': 100    # km par défaut pour le Sud
        }
        return default_distances.get(region_name, 100)
    
    def _get_gouvernorat_from_secteur(self, secteur_name):
        """Extrait le nom du gouvernorat à partir du nom du secteur"""
        import re
        # Supprimer les chiffres et espaces à la fin pour obtenir le gouvernorat
        # Exemples: "Gafsa 1" -> "Gafsa", "Tunis 101" -> "Tunis", "Ben Arous 111" -> "Ben Arous"
        secteur_clean = str(secteur_name).strip()
        
        # Essayer de matcher le pattern "Nom Gouvernorat + Chiffres"
        # Ce pattern capture tout avant le dernier bloc de chiffres
        match = re.match(r'^(.+?)\s*\d+$', secteur_clean)
        if match:
            return match.group(1).strip()
        
        # Fallback: capturer tout ce qui n'est pas un chiffre au début
        match = re.match(r'^([A-Za-zÀ-ÿ\s]+)', secteur_clean)
        if match:
            return match.group(1).strip()
        
        return secteur_clean
    
    def _get_gouvernorat_secteurs_count(self, secteurs_list):
        """Compte le nombre de secteurs par gouvernorat dans une liste"""
        gouvernorat_counts = {}
        for secteur in secteurs_list:
            gouv = self._get_gouvernorat_from_secteur(secteur)
            gouvernorat_counts[gouv] = gouvernorat_counts.get(gouv, 0) + 1
        return gouvernorat_counts
    
    def _should_keep_secteur_with_gouvernorat(self, secteur, cluster_secteurs, all_secteurs, allow_conditional=False):
        """
        Vérifie si un secteur appartient à un gouvernorat qui ne doit PAS être divisé.
        Seuls les gouvernorats dans GOUVERNORATS_DIVISIBLES peuvent être séparés.
        Si allow_conditional=True, les gouvernorats conditionnellement divisibles le sont aussi.
        """
        gouv = self._get_gouvernorat_from_secteur(secteur)
        
        gouv_lower = gouv.lower().strip()
        for divisible_gov in self.GOUVERNORATS_DIVISIBLES:
            if divisible_gov.lower() in gouv_lower or gouv_lower in divisible_gov.lower():
                return False
        
        if allow_conditional:
            for divisible_gov in self.GOUVERNORATS_DIVISIBLES_CONDITIONNELS:
                if divisible_gov.lower() in gouv_lower or gouv_lower in divisible_gov.lower():
                    return False
        
        return True
    
    def _eliminate_weak_delegates(self, groupes_secteurs, objectifs_par_secteur, objectif_cible, region_name):
        """
        Élimine les délégués dont l'objectif est trop faible (< 50% de la moyenne).
        Redistribue leurs secteurs aux délégués les plus proches géographiquement
        qui ont le moins de charge, en respectant les contraintes de non-divisibilité.
        """
        if len(groupes_secteurs) <= 1:
            return groupes_secteurs
        
        changed = True
        while changed and len(groupes_secteurs) > 1:
            changed = False
            objectif_moyen = sum(g[1] for g in groupes_secteurs) / len(groupes_secteurs)
            seuil_elimination = objectif_moyen * 0.50
            
            idx_min = min(range(len(groupes_secteurs)), key=lambda i: groupes_secteurs[i][1])
            groupe_min = groupes_secteurs[idx_min]
            
            if groupe_min[1] >= seuil_elimination:
                break
            
            secteurs_a_redistribuer = []
            for s_info in groupe_min[2]:
                s_nom = s_info['nom'] if isinstance(s_info, dict) else s_info
                secteurs_a_redistribuer.append(s_nom)
            
            remaining = [g for i, g in enumerate(groupes_secteurs) if i != idx_min]
            
            gouv_groups = {}
            for s in secteurs_a_redistribuer:
                gouv = self._get_gouvernorat_from_secteur(s)
                if gouv not in gouv_groups:
                    gouv_groups[gouv] = []
                gouv_groups[gouv].append(s)
            
            units_to_place = []
            for gouv, sects in gouv_groups.items():
                if self._is_gouvernorat_divisible(gouv):
                    for s in sects:
                        units_to_place.append([s])
                else:
                    units_to_place.append(sects)
            
            units_to_place.sort(key=lambda u: sum(objectifs_par_secteur.get(s, 0) for s in u))
            
            for unit in units_to_place:
                obj_unit = sum(objectifs_par_secteur.get(s, 0) for s in unit)
                gouv_unit = self._get_gouvernorat_from_secteur(unit[0])
                
                best_idx = None
                best_score = float('inf')
                
                for idx, (grp_secteurs, grp_obj, grp_details) in enumerate(remaining):
                    grp_secteurs_noms = [s['nom'] if isinstance(s, dict) else s for s in grp_details]
                    
                    if self._would_violate_exclusive_groups(gouv_unit, grp_secteurs_noms):
                        continue
                    
                    is_neighbor = self._is_move_allowed_by_proximity(gouv_unit, grp_secteurs_noms)
                    
                    new_obj = grp_obj + obj_unit
                    ecart = abs(new_obj - objectif_moyen)
                    
                    score = ecart
                    if not is_neighbor:
                        score += 1e9
                    
                    if score < best_score or (score == best_score and best_idx is not None and idx < best_idx):
                        best_score = score
                        best_idx = idx
                
                if best_idx is not None:
                    old_secteurs, old_obj, old_details = remaining[best_idx]
                    new_secteurs = list(old_secteurs)
                    new_obj = old_obj + obj_unit
                    new_details = list(old_details)
                    for s in unit:
                        new_secteurs.append(s)
                        new_details.append({'nom': s, 'objectif': objectifs_par_secteur.get(s, 0)})
                    remaining[best_idx] = (new_secteurs, new_obj, new_details)
            
            groupes_secteurs = remaining
            changed = True
        
        return groupes_secteurs
    
    def _redistribute_gouvernorat_for_balance(self, groupes_secteurs, objectifs_par_secteur, gouvs_to_redistribute):
        """
        Retire tous les secteurs des gouvernorats spécifiés de chaque délégué,
        puis les redistribue un par un au délégué avec le moins d'objectif,
        pour équilibrer la charge globale.
        Garantit qu'aucun délégué n'a UNIQUEMENT des secteurs de ces gouvernorats.
        """
        extracted_secteurs = []
        new_groupes = []
        for secteurs_list, objectif_total, details in groupes_secteurs:
            kept_secteurs = []
            kept_details = []
            kept_obj = 0
            for d in details:
                s_nom = d['nom'] if isinstance(d, dict) else d
                gouv = self._get_gouvernorat_from_secteur(s_nom)
                if gouv in gouvs_to_redistribute:
                    extracted_secteurs.append(d)
                else:
                    kept_details.append(d)
                    kept_secteurs.append(s_nom)
                    kept_obj += objectifs_par_secteur.get(s_nom, 0)
            new_groupes.append((kept_secteurs, kept_obj, kept_details))
        
        if not extracted_secteurs:
            return groupes_secteurs
        
        extracted_secteurs.sort(key=lambda d: objectifs_par_secteur.get(d['nom'] if isinstance(d, dict) else d, 0), reverse=True)
        
        for d in extracted_secteurs:
            s_nom = d['nom'] if isinstance(d, dict) else d
            obj_s = objectifs_par_secteur.get(s_nom, 0)
            gouv_s = self._get_gouvernorat_from_secteur(s_nom)
            
            valid_indices = [i for i in range(len(new_groupes)) 
                           if not self._would_violate_exclusive_groups(gouv_s, new_groupes[i][0])]
            if not valid_indices:
                valid_indices = list(range(len(new_groupes)))
            
            min_idx = min(valid_indices, key=lambda i: new_groupes[i][1])
            
            old_secteurs, old_obj, old_details = new_groupes[min_idx]
            new_groupes[min_idx] = (
                list(old_secteurs) + [s_nom],
                old_obj + obj_s,
                list(old_details) + [d if isinstance(d, dict) else {'nom': d, 'objectif': obj_s}]
            )
        
        return new_groupes
    
    def _fix_gouvernorats_non_seuls(self, groupes_secteurs, objectifs_par_secteur):
        if len(groupes_secteurs) <= 1:
            return groupes_secteurs
        
        max_iterations = 10
        for _ in range(max_iterations):
            changed = False
            for idx, (secteurs_list, objectif_total, details) in enumerate(groupes_secteurs):
                gouvs_in_group = set()
                for d in details:
                    s_nom = d['nom'] if isinstance(d, dict) else d
                    gouvs_in_group.add(self._get_gouvernorat_from_secteur(s_nom))
                
                solo_gouvs = [g for g in gouvs_in_group if g in self.GOUVERNORATS_NON_SEULS]
                if not solo_gouvs or len(gouvs_in_group) > len(solo_gouvs):
                    continue
                
                solo_gouv = solo_gouvs[0]
                best_target = None
                best_swap_score = float('inf')
                best_give_sect = None
                best_take_sect = None
                
                for t_idx, (t_sects, t_obj, t_details) in enumerate(groupes_secteurs):
                    if t_idx == idx:
                        continue
                    t_gouvs = set()
                    for d in t_details:
                        s_nom = d['nom'] if isinstance(d, dict) else d
                        t_gouvs.add(self._get_gouvernorat_from_secteur(s_nom))
                    
                    has_non_solo = any(g not in self.GOUVERNORATS_NON_SEULS for g in t_gouvs)
                    if not has_non_solo:
                        continue
                    
                    for d_take in t_details:
                        take_nom = d_take['nom'] if isinstance(d_take, dict) else d_take
                        take_gouv = self._get_gouvernorat_from_secteur(take_nom)
                        if take_gouv in self.GOUVERNORATS_NON_SEULS:
                            continue
                        if self._should_keep_secteur_with_gouvernorat(take_nom, t_sects, t_sects + secteurs_list):
                            continue
                        take_gouv_g = self._get_gouvernorat_from_secteur(take_nom)
                        if self._would_violate_exclusive_groups(take_gouv_g, secteurs_list):
                            continue
                        
                        for d_give in details:
                            give_nom = d_give['nom'] if isinstance(d_give, dict) else d_give
                            give_gouv = self._get_gouvernorat_from_secteur(give_nom)
                            if give_gouv != solo_gouv:
                                continue
                            if self._would_violate_exclusive_groups(give_gouv, t_sects):
                                continue
                            
                            give_obj = objectifs_par_secteur.get(give_nom, 0)
                            take_obj = objectifs_par_secteur.get(take_nom, 0)
                            score = abs(give_obj - take_obj)
                            if score < best_swap_score:
                                best_swap_score = score
                                best_target = t_idx
                                best_give_sect = d_give
                                best_take_sect = d_take
                
                if best_target is not None:
                    give_nom = best_give_sect['nom'] if isinstance(best_give_sect, dict) else best_give_sect
                    take_nom = best_take_sect['nom'] if isinstance(best_take_sect, dict) else best_take_sect
                    give_obj = objectifs_par_secteur.get(give_nom, 0)
                    take_obj = objectifs_par_secteur.get(take_nom, 0)
                    
                    s_list, s_obj, s_details = groupes_secteurs[idx]
                    new_s_details = [d for d in s_details if (d['nom'] if isinstance(d, dict) else d) != give_nom]
                    new_s_details.append(best_take_sect if isinstance(best_take_sect, dict) else {'nom': best_take_sect, 'objectif': take_obj})
                    new_s_list = [d['nom'] if isinstance(d, dict) else d for d in new_s_details]
                    groupes_secteurs[idx] = (new_s_list, s_obj - give_obj + take_obj, new_s_details)
                    
                    t_list, t_obj, t_details = groupes_secteurs[best_target]
                    new_t_details = [d for d in t_details if (d['nom'] if isinstance(d, dict) else d) != take_nom]
                    new_t_details.append(best_give_sect if isinstance(best_give_sect, dict) else {'nom': best_give_sect, 'objectif': give_obj})
                    new_t_list = [d['nom'] if isinstance(d, dict) else d for d in new_t_details]
                    groupes_secteurs[best_target] = (new_t_list, t_obj - take_obj + give_obj, new_t_details)
                    
                    changed = True
                    break
            
            if not changed:
                break
        
        return groupes_secteurs
    
    def _rebalance_clusters_exclusive(self, clusters_totals, secteurs, objectifs_par_secteur, objectif_cible):
        """
        Rééquilibre les objectifs entre clusters pour K-means exclusif
        Respecte la contrainte: les gouvernorats avec 2-3 secteurs ne doivent pas être divisés
        Optimise l'équilibre des objectifs ET la proximité géographique
        """
        if len(clusters_totals) <= 1:
            return clusters_totals
        
        # Calculer le nombre moyen de secteurs par cluster
        total_secteurs = sum(c['nombre_secteurs'] for c in clusters_totals)
        n_clusters = len(clusters_totals)
        secteurs_cible = total_secteurs / n_clusters if n_clusters > 0 else 0
        secteurs_min = max(1, int(secteurs_cible * 0.5))  # Au moins 50% de la moyenne
        secteurs_max = int(secteurs_cible * 1.5) + 1  # Au plus 150% de la moyenne
        
        max_iterations = 50  # Plus d'itérations pour un meilleur équilibrage
        stagnation_count = 0
        last_best_score = float('inf')
        
        for iteration in range(max_iterations):
            # Calculer le score global actuel (objectifs + secteurs)
            current_score = self._calculate_balance_score(clusters_totals, objectif_cible, secteurs_cible)
            
            # Détecter stagnation
            if abs(current_score - last_best_score) < 0.005:
                stagnation_count += 1
            else:
                stagnation_count = 0
            last_best_score = min(last_best_score, current_score)
            
            if stagnation_count >= 5:
                break  # Arrêter si aucune amélioration depuis 5 itérations
            
            # Trier par objectif total décroissant (cluster_id comme critère secondaire pour stabilité)
            clusters_totals.sort(key=lambda x: (-x['total_objectif'], x['cluster_id']))
            
            cluster_surcharge = clusters_totals[0]
            cluster_leger = clusters_totals[-1]
            
            surcharge = cluster_surcharge['total_objectif'] - objectif_cible
            deficit = objectif_cible - cluster_leger['total_objectif']
            
            # Calculer le déséquilibre en pourcentage
            if objectif_cible > 0:
                desequilibre_obj_pct = max(surcharge, deficit) / objectif_cible * 100
            else:
                desequilibre_obj_pct = 0
            
            # Calculer aussi le déséquilibre des secteurs
            max_secteurs = max(c['nombre_secteurs'] for c in clusters_totals)
            min_secteurs = min(c['nombre_secteurs'] for c in clusters_totals)
            desequilibre_secteurs = max_secteurs - min_secteurs
            
            # Si les écarts sont acceptables, arrêter (seuil plus strict: 10%)
            if desequilibre_obj_pct < 10 and desequilibre_secteurs <= 2:
                break
            
            # Autoriser la division des gouvernorats conditionnels si le déséquilibre est fort
            allow_cond = desequilibre_obj_pct > 20
            
            # Trouver le MEILLEUR secteur à déplacer (score combiné objectifs + proximité)
            meilleur_move = None
            meilleur_score_amelioration = -float('inf')
            
            # Essayer toutes les paires source -> destination
            for idx_src, cluster_src in enumerate(clusters_totals):
                for idx_dst, cluster_dst in enumerate(clusters_totals):
                    if idx_src == idx_dst:
                        continue
                    
                    # Préférer déplacer des clusters surchargés vers des clusters légers
                    if cluster_src['total_objectif'] <= cluster_dst['total_objectif']:
                        continue
                    
                    for secteur in sorted(cluster_src['secteurs']):
                        # Vérifier contrainte gouvernorat
                        if self._should_keep_secteur_with_gouvernorat(secteur, cluster_src['secteurs'], secteurs, allow_conditional=allow_cond):
                            continue
                        
                        if self._would_break_pair(secteur, cluster_src['secteurs'], cluster_dst['secteurs']):
                            continue
                        
                        gouv_secteur = self._get_gouvernorat_from_secteur(secteur)
                        if self._would_violate_exclusive_groups(gouv_secteur, cluster_dst['secteurs']):
                            continue
                        
                        objectif_secteur = objectifs_par_secteur.get(secteur, 0)
                        
                        # Calculer les nouvelles valeurs
                        new_obj_src = cluster_src['total_objectif'] - objectif_secteur
                        new_obj_dst = cluster_dst['total_objectif'] + objectif_secteur
                        new_sect_src = cluster_src['nombre_secteurs'] - 1
                        new_sect_dst = cluster_dst['nombre_secteurs'] + 1
                        
                        # Vérifier les contraintes (plus souples)
                        if new_sect_src < secteurs_min or new_sect_dst > secteurs_max:
                            continue
                        if new_obj_src < objectif_cible * 0.55 or new_obj_dst > objectif_cible * 1.45:
                            continue
                        
                        # Calculer le score d'amélioration d'équilibre
                        score_obj_avant = abs(cluster_src['total_objectif'] - objectif_cible) + abs(cluster_dst['total_objectif'] - objectif_cible)
                        score_obj_apres = abs(new_obj_src - objectif_cible) + abs(new_obj_dst - objectif_cible)
                        amelioration_obj = score_obj_avant - score_obj_apres
                        
                        # Calculer le score de proximité (bonus si le secteur est proche des autres secteurs du cluster destination)
                        proximite_bonus = self._calculate_proximity_bonus(secteur, cluster_dst['secteurs'])
                        
                        # Score combiné: équilibre + proximité
                        amelioration_totale = amelioration_obj + proximite_bonus * objectif_cible * 0.05
                        
                        if amelioration_totale > meilleur_score_amelioration or (amelioration_totale == meilleur_score_amelioration and meilleur_move and secteur < meilleur_move[2]):
                            meilleur_score_amelioration = amelioration_totale
                            meilleur_move = (idx_src, idx_dst, secteur, objectif_secteur)
            
            if meilleur_move and meilleur_score_amelioration > 0:
                idx_src, idx_dst, secteur, objectif_secteur = meilleur_move
                cluster_src = clusters_totals[idx_src]
                cluster_dst = clusters_totals[idx_dst]
                
                # Retirer du cluster source
                idx = cluster_src['secteurs'].index(secteur)
                cluster_src['secteurs'].pop(idx)
                cluster_src['objectifs'].pop(idx)
                cluster_src['total_objectif'] -= objectif_secteur
                cluster_src['nombre_secteurs'] -= 1
                
                # Ajouter au cluster destination
                cluster_dst['secteurs'].append(secteur)
                cluster_dst['objectifs'].append(objectif_secteur)
                cluster_dst['total_objectif'] += objectif_secteur
                cluster_dst['nombre_secteurs'] += 1
            else:
                break
        
        # PHASE 2: Équilibrage agressif final si encore déséquilibré
        clusters_totals = self._aggressive_final_balance(clusters_totals, objectifs_par_secteur, objectif_cible, secteurs)
        
        return clusters_totals
    
    def _calculate_cluster_total_distance(self, secteurs_list):
        """
        Calcule la distance totale parcourue pour visiter tous les secteurs d'un cluster.
        Utilise la somme des distances entre secteurs consécutifs (chemin le plus simple).
        """
        if not secteurs_list or len(secteurs_list) <= 1:
            return 0
        
        total_distance = 0
        
        if self.distance_matrix is not None:
            for i in range(len(secteurs_list) - 1):
                secteur_i = secteurs_list[i]
                secteur_j = secteurs_list[i + 1]
                
                try:
                    dist = self._get_distance_between_secteurs(secteur_i, secteur_j)
                    total_distance += dist
                except:
                    gouv_i = self._get_gouvernorat_from_secteur(secteur_i)
                    gouv_j = self._get_gouvernorat_from_secteur(secteur_j)
                    if gouv_i == gouv_j:
                        total_distance += 15
                    elif self._are_gouvernorats_neighbors(gouv_i, gouv_j):
                        total_distance += 40
                    else:
                        total_distance += 100
        else:
            for i in range(len(secteurs_list) - 1):
                gouv_i = self._get_gouvernorat_from_secteur(secteurs_list[i])
                gouv_j = self._get_gouvernorat_from_secteur(secteurs_list[i + 1])
                if gouv_i == gouv_j:
                    total_distance += 15
                elif self._are_gouvernorats_neighbors(gouv_i, gouv_j):
                    total_distance += 40
                else:
                    total_distance += 100
        
        return total_distance
    
    def _get_distance_between_secteurs(self, secteur_i, secteur_j):
        """Obtient la distance entre deux secteurs depuis la matrice de distance"""
        if self.distance_matrix is None:
            return 50
        
        try:
            if secteur_i in self.distance_matrix.index and secteur_j in self.distance_matrix.columns:
                dist = self.distance_matrix.loc[secteur_i, secteur_j]
                if not pd.isna(dist):
                    return float(dist)
            
            secteur_i_simple = secteur_i.replace(' ', '')
            secteur_j_simple = secteur_j.replace(' ', '')
            if secteur_i_simple in self.distance_matrix.index and secteur_j_simple in self.distance_matrix.columns:
                dist = self.distance_matrix.loc[secteur_i_simple, secteur_j_simple]
                if not pd.isna(dist):
                    return float(dist)
        except:
            pass
        
        gouv_i = self._get_gouvernorat_from_secteur(secteur_i)
        gouv_j = self._get_gouvernorat_from_secteur(secteur_j)
        if gouv_i == gouv_j:
            return 15
        elif self._are_gouvernorats_neighbors(gouv_i, gouv_j):
            return 40
        else:
            return 100
    
    def _calculate_cluster_average_daily_distance(self, secteurs_list):
        """
        Estime la distance moyenne journalière pour un délégué.
        Hypothèse: un délégué visite 3-5 secteurs par jour.
        """
        total_dist = self._calculate_cluster_total_distance(secteurs_list)
        n_secteurs = len(secteurs_list)
        if n_secteurs <= 1:
            return 0
        secteurs_par_jour = min(4, n_secteurs)
        return (total_dist / max(1, n_secteurs - 1)) * secteurs_par_jour
    
    def _calculate_proximity_bonus(self, secteur, cluster_secteurs):
        """Calcule un bonus de proximité si le secteur est proche des autres secteurs du cluster"""
        if not cluster_secteurs:
            return 0
        
        gouv_secteur = self._get_gouvernorat_from_secteur(secteur)
        bonus = 0
        
        for other_secteur in cluster_secteurs:
            gouv_other = self._get_gouvernorat_from_secteur(other_secteur)
            if gouv_secteur == gouv_other:
                bonus += 2  # Même gouvernorat = bonus élevé
            elif self._are_gouvernorats_neighbors(gouv_secteur, gouv_other):
                bonus += 1  # Gouvernorats voisins = bonus moyen
        
        return bonus
    
    def _are_cluster_gouvernorats_connected(self, secteurs_list):
        """
        Vérifie que tous les gouvernorats d'un cluster forment un ensemble connecté.
        Chaque gouvernorat doit être voisin d'au moins un autre gouvernorat du cluster.
        """
        if not secteurs_list:
            return True
        
        gouvs = set()
        for secteur in secteurs_list:
            gouvs.add(self._get_gouvernorat_from_secteur(secteur))
        
        if len(gouvs) <= 1:
            return True
        
        gouvs_list = list(gouvs)
        visited = {gouvs_list[0]}
        queue = [gouvs_list[0]]
        
        while queue:
            current = queue.pop(0)
            for other_gouv in gouvs_list:
                if other_gouv not in visited:
                    if self._are_gouvernorats_neighbors(current, other_gouv):
                        visited.add(other_gouv)
                        queue.append(other_gouv)
        
        return len(visited) == len(gouvs)
    
    def _are_gouvernorats_neighbors(self, gouv1, gouv2):
        """Vérifie si deux gouvernorats sont voisins"""
        gouv1_normalized = self._normalize_gouvernorat_name(gouv1)
        gouv2_normalized = self._normalize_gouvernorat_name(gouv2)
        
        if gouv1_normalized in self.GOUVERNORATS_VOISINS:
            voisins = [self._normalize_gouvernorat_name(v) for v in self.GOUVERNORATS_VOISINS[gouv1_normalized]]
            return gouv2_normalized in voisins
        return False
    
    def _normalize_gouvernorat_name(self, gouv):
        """Normalise le nom d'un gouvernorat pour la comparaison"""
        gouv_lower = gouv.lower().strip()
        # Gérer les variantes
        if 'manouba' in gouv_lower:
            return 'Manouba'
        if 'kef' in gouv_lower:
            return 'Le Kef'
        if 'bouzid' in gouv_lower:
            return 'Sidi Bouzid'
        if 'arous' in gouv_lower:
            return 'Ben Arous'
        return gouv.strip()
    
    def _calculate_cluster_proximity_score(self, gouv, cluster_secteurs):
        """Calcule un score de proximité pour un gouvernorat par rapport à un cluster"""
        if not cluster_secteurs:
            return 0
        
        score = 0
        cluster_gouvs = set()
        
        for secteur in cluster_secteurs:
            cluster_gouvs.add(self._get_gouvernorat_from_secteur(secteur))
        
        for cluster_gouv in cluster_gouvs:
            if gouv == cluster_gouv:
                score += 3  # Même gouvernorat dans le cluster
            elif self._are_gouvernorats_neighbors(gouv, cluster_gouv):
                score += 1  # Gouvernorat voisin dans le cluster
        
        return score
    
    def _would_violate_exclusive_groups(self, gouv, cluster_secteurs):
        """
        Vérifie si ajouter un gouvernorat à un cluster violerait les groupes exclusifs.
        Les groupes exclusifs sont des paires de groupes de gouvernorats qui ne doivent
        JAMAIS être sur le même délégué.
        """
        if not cluster_secteurs:
            return False
        
        cluster_gouvs = set()
        for secteur in cluster_secteurs:
            cluster_gouvs.add(self._get_gouvernorat_from_secteur(secteur))
        
        for group_a, group_b in self.GROUPES_EXCLUSIFS:
            if gouv in group_a:
                if cluster_gouvs & group_b:
                    return True
            if gouv in group_b:
                if cluster_gouvs & group_a:
                    return True
        return False
    
    def _is_move_allowed_by_proximity(self, gouv, cluster_secteurs):
        """
        Vérifie si le déplacement d'un gouvernorat vers un cluster est autorisé.
        Le déplacement n'est autorisé QUE si le cluster destination contient 
        au moins un gouvernorat voisin ou le même gouvernorat.
        """
        if not cluster_secteurs:
            return True  # Cluster vide = autorisé (premier secteur)
        
        cluster_gouvs = set()
        for secteur in cluster_secteurs:
            cluster_gouvs.add(self._get_gouvernorat_from_secteur(secteur))
        
        # Vérifier s'il y a au moins un gouvernorat voisin ou identique
        for cluster_gouv in cluster_gouvs:
            if gouv == cluster_gouv:
                return True  # Même gouvernorat = autorisé
            if self._are_gouvernorats_neighbors(gouv, cluster_gouv):
                return True  # Gouvernorat voisin = autorisé
        
        return False  # Pas de voisin = non autorisé
    
    def _compute_max_regional_ecart(self, clusters_totals):
        """Calcule l'écart maximal d'objectifs au sein de chaque région."""
        regions = {}
        for c in clusters_totals:
            r = c.get('region', 'Unknown')
            if r not in regions:
                regions[r] = []
            regions[r].append(c['total_objectif'])
        
        max_ecart = 0
        for r, objs in regions.items():
            if len(objs) < 2:
                continue
            moy = sum(objs) / len(objs) if objs else 1
            ecart = ((max(objs) - min(objs)) / moy * 100) if moy > 0 else 0
            if ecart > max_ecart:
                max_ecart = ecart
        return max_ecart
    
    def _compute_regional_ecart_after_move(self, clusters_totals, source_cluster, target_cluster, new_src_obj, new_dst_obj):
        """Simule un mouvement et retourne le max écart régional résultant."""
        regions = {}
        for c in clusters_totals:
            r = c.get('region', 'Unknown')
            if r not in regions:
                regions[r] = []
            if c is source_cluster:
                regions[r].append(new_src_obj)
            elif c is target_cluster:
                regions[r].append(new_dst_obj)
            else:
                regions[r].append(c['total_objectif'])
        
        max_ecart = 0
        for r, objs in regions.items():
            if len(objs) < 2:
                continue
            moy = sum(objs) / len(objs) if objs else 1
            ecart = ((max(objs) - min(objs)) / moy * 100) if moy > 0 else 0
            if ecart > max_ecart:
                max_ecart = ecart
        return max_ecart
    
    def _aggressive_final_balance(self, clusters_totals, objectifs_par_secteur, objectif_cible, all_secteurs):
        """
        Équilibrage agressif avec priorité à l'équilibre RÉGIONAL des objectifs.
        Le score utilisé est l'écart maximal d'objectifs au sein d'une même région.
        Les contraintes sont levées progressivement si l'écart reste élevé.
        """
        if len(clusters_totals) <= 1:
            return clusters_totals
        
        for cluster in clusters_totals:
            cluster['km_jour'] = self._calculate_cluster_average_daily_distance(cluster['secteurs'])
        
        max_iterations = 500
        no_improvement_count = 0
        last_regional_ecart = float('inf')
        
        for iteration in range(max_iterations):
            for cluster in clusters_totals:
                cluster['km_jour'] = self._calculate_cluster_average_daily_distance(cluster['secteurs'])
            
            current_regional_ecart = self._compute_max_regional_ecart(clusters_totals)
            
            if current_regional_ecart < 5:
                break
            
            if abs(current_regional_ecart - last_regional_ecart) < 0.05:
                no_improvement_count += 1
                if no_improvement_count > 40:
                    break
            else:
                no_improvement_count = 0
            last_regional_ecart = current_regional_ecart
            
            best_move = None
            best_move_type = None
            best_move_data = None
            best_new_regional_ecart = current_regional_ecart
            best_new_km_penalty = float('inf')
            
            relax_divisibility = current_regional_ecart > 3
            relax_pairs = current_regional_ecart > 5
            relax_proximity = current_regional_ecart > 8
            relax_connectivity = current_regional_ecart > 10
            
            regions = {}
            for c in clusters_totals:
                r = c.get('region', 'Unknown')
                if r not in regions:
                    regions[r] = []
                regions[r].append(c)
            
            worst_region = None
            worst_ecart = 0
            for r, rcs in regions.items():
                if len(rcs) < 2:
                    continue
                objs = [c['total_objectif'] for c in rcs]
                moy = sum(objs) / len(objs) if objs else 1
                ecart = ((max(objs) - min(objs)) / moy * 100) if moy > 0 else 0
                if ecart > worst_ecart:
                    worst_ecart = ecart
                    worst_region = r
            
            if worst_region is None:
                break
            
            region_clusters = regions[worst_region]
            source_cluster = max(region_clusters, key=lambda x: x['total_objectif'])
            
            for secteur in sorted(source_cluster['secteurs']):
                gouv = self._get_gouvernorat_from_secteur(secteur)
                
                if not relax_divisibility:
                    if not self._is_gouvernorat_divisible(gouv):
                        continue
                
                for target_cluster in region_clusters:
                    if target_cluster is source_cluster:
                        continue
                    
                    if not relax_pairs:
                        if self._would_break_pair(secteur, source_cluster['secteurs'], target_cluster['secteurs']):
                            continue
                    
                    if not relax_proximity:
                        if not self._is_move_allowed_by_proximity(gouv, target_cluster['secteurs']):
                            continue
                    
                    if self._would_violate_exclusive_groups(gouv, target_cluster['secteurs']):
                        continue
                    
                    obj = objectifs_par_secteur.get(secteur, 0)
                    new_src_obj = source_cluster['total_objectif'] - obj
                    new_dst_obj = target_cluster['total_objectif'] + obj
                    
                    new_secteurs_src = [s for s in source_cluster['secteurs'] if s != secteur]
                    new_secteurs_dst = target_cluster['secteurs'] + [secteur]
                    
                    if len(new_secteurs_src) == 0:
                        continue
                    if not relax_connectivity:
                        if not self._are_cluster_gouvernorats_connected(new_secteurs_src):
                            continue
                        if not self._are_cluster_gouvernorats_connected(new_secteurs_dst):
                            continue
                    
                    new_regional_ecart = self._compute_regional_ecart_after_move(
                        clusters_totals, source_cluster, target_cluster, new_src_obj, new_dst_obj)
                    
                    new_km = self._calculate_cluster_average_daily_distance(new_secteurs_src) + \
                             self._calculate_cluster_average_daily_distance(new_secteurs_dst)
                    
                    if new_regional_ecart < best_new_regional_ecart or \
                       (abs(new_regional_ecart - best_new_regional_ecart) < 0.3 and new_km < best_new_km_penalty):
                        best_new_regional_ecart = new_regional_ecart
                        best_new_km_penalty = new_km
                        best_move = secteur
                        best_move_type = 'secteur'
                        best_move_data = {'source': source_cluster, 'target': target_cluster}
            
            gouvernorats_in_source = {}
            for secteur in source_cluster['secteurs']:
                gouv = self._get_gouvernorat_from_secteur(secteur)
                if gouv not in gouvernorats_in_source:
                    gouvernorats_in_source[gouv] = {'secteurs': [], 'objectif_total': 0}
                gouvernorats_in_source[gouv]['secteurs'].append(secteur)
                gouvernorats_in_source[gouv]['objectif_total'] += objectifs_par_secteur.get(secteur, 0)
            
            for gouv, gouv_data in gouvernorats_in_source.items():
                if len(gouvernorats_in_source) <= 1:
                    continue
                
                for target_cluster in region_clusters:
                    if target_cluster is source_cluster:
                        continue
                    
                    if self._would_violate_exclusive_groups(gouv, target_cluster['secteurs']):
                        continue
                    
                    if not relax_proximity:
                        if not self._is_move_allowed_by_proximity(gouv, target_cluster['secteurs']):
                            continue
                    
                    obj_gouv = gouv_data['objectif_total']
                    new_src_obj = source_cluster['total_objectif'] - obj_gouv
                    new_dst_obj = target_cluster['total_objectif'] + obj_gouv
                    
                    new_secteurs_src = [s for s in source_cluster['secteurs'] if s not in gouv_data['secteurs']]
                    new_secteurs_dst = target_cluster['secteurs'] + gouv_data['secteurs']
                    
                    if len(new_secteurs_src) == 0:
                        continue
                    if not relax_connectivity:
                        if not self._are_cluster_gouvernorats_connected(new_secteurs_src):
                            continue
                        if not self._are_cluster_gouvernorats_connected(new_secteurs_dst):
                            continue
                    
                    new_regional_ecart = self._compute_regional_ecart_after_move(
                        clusters_totals, source_cluster, target_cluster, new_src_obj, new_dst_obj)
                    
                    new_km = self._calculate_cluster_average_daily_distance(new_secteurs_src) + \
                             self._calculate_cluster_average_daily_distance(new_secteurs_dst)
                    
                    if new_regional_ecart < best_new_regional_ecart or \
                       (abs(new_regional_ecart - best_new_regional_ecart) < 0.3 and new_km < best_new_km_penalty):
                        best_new_regional_ecart = new_regional_ecart
                        best_new_km_penalty = new_km
                        best_move = gouv
                        best_move_type = 'gouvernorat'
                        best_move_data = {'source': source_cluster, 'target': target_cluster, 'gouv_data': gouv_data}
            
            target_min_cluster = min(region_clusters, key=lambda x: x['total_objectif'])
            if source_cluster is not target_min_cluster:
                for s_src in list(source_cluster['secteurs']):
                    gouv_src = self._get_gouvernorat_from_secteur(s_src)
                    obj_src = objectifs_par_secteur.get(s_src, 0)
                    if not relax_divisibility and not self._is_gouvernorat_divisible(gouv_src):
                        continue
                    for s_dst in list(target_min_cluster['secteurs']):
                        obj_dst = objectifs_par_secteur.get(s_dst, 0)
                        if obj_src <= obj_dst:
                            continue
                        gouv_dst = self._get_gouvernorat_from_secteur(s_dst)
                        if not relax_divisibility and not self._is_gouvernorat_divisible(gouv_dst):
                            continue
                        if not relax_pairs:
                            temp_dst_after = [s for s in target_min_cluster['secteurs'] if s != s_dst] + [s_src]
                            temp_src_after = [s for s in source_cluster['secteurs'] if s != s_src] + [s_dst]
                            if self._would_break_pair(s_src, source_cluster['secteurs'], temp_dst_after):
                                continue
                            if self._would_break_pair(s_dst, target_min_cluster['secteurs'], temp_src_after):
                                continue
                        if self._would_violate_exclusive_groups(gouv_src, [s for s in target_min_cluster['secteurs'] if s != s_dst]):
                            continue
                        if self._would_violate_exclusive_groups(gouv_dst, [s for s in source_cluster['secteurs'] if s != s_src]):
                            continue
                        new_secteurs_src = [s for s in source_cluster['secteurs'] if s != s_src] + [s_dst]
                        new_secteurs_dst = [s for s in target_min_cluster['secteurs'] if s != s_dst] + [s_src]
                        if not relax_connectivity:
                            if not self._are_cluster_gouvernorats_connected(new_secteurs_src):
                                continue
                            if not self._are_cluster_gouvernorats_connected(new_secteurs_dst):
                                continue
                        if not relax_proximity:
                            if not self._is_move_allowed_by_proximity(gouv_src, new_secteurs_dst):
                                continue
                            if not self._is_move_allowed_by_proximity(gouv_dst, new_secteurs_src):
                                continue
                        new_src_obj = source_cluster['total_objectif'] - obj_src + obj_dst
                        new_dst_obj = target_min_cluster['total_objectif'] - obj_dst + obj_src
                        new_regional_ecart = self._compute_regional_ecart_after_move(
                            clusters_totals, source_cluster, target_min_cluster, new_src_obj, new_dst_obj)
                        new_km = self._calculate_cluster_average_daily_distance(new_secteurs_src) + \
                                 self._calculate_cluster_average_daily_distance(new_secteurs_dst)
                        if new_regional_ecart < best_new_regional_ecart or \
                           (abs(new_regional_ecart - best_new_regional_ecart) < 0.3 and new_km < best_new_km_penalty):
                            best_new_regional_ecart = new_regional_ecart
                            best_new_km_penalty = new_km
                            best_move = (s_src, s_dst)
                            best_move_type = 'swap'
                            best_move_data = {'source': source_cluster, 'target': target_min_cluster}
            
            if best_move and best_move_data:
                source_cluster = best_move_data['source']
                target_cluster = best_move_data['target']
                
                if best_move_type == 'secteur':
                    obj = objectifs_par_secteur.get(best_move, 0)
                    if best_move in source_cluster['secteurs']:
                        idx = source_cluster['secteurs'].index(best_move)
                        source_cluster['secteurs'].pop(idx)
                        if idx < len(source_cluster['objectifs']):
                            source_cluster['objectifs'].pop(idx)
                        source_cluster['total_objectif'] -= obj
                        source_cluster['nombre_secteurs'] -= 1
                        target_cluster['secteurs'].append(best_move)
                        target_cluster['objectifs'].append(obj)
                        target_cluster['total_objectif'] += obj
                        target_cluster['nombre_secteurs'] += 1
                
                elif best_move_type == 'swap':
                    s_src, s_dst = best_move
                    obj_src = objectifs_par_secteur.get(s_src, 0)
                    obj_dst = objectifs_par_secteur.get(s_dst, 0)
                    if s_src in source_cluster['secteurs'] and s_dst in target_cluster['secteurs']:
                        idx_src = source_cluster['secteurs'].index(s_src)
                        source_cluster['secteurs'].pop(idx_src)
                        if idx_src < len(source_cluster['objectifs']):
                            source_cluster['objectifs'].pop(idx_src)
                        idx_dst = target_cluster['secteurs'].index(s_dst)
                        target_cluster['secteurs'].pop(idx_dst)
                        if idx_dst < len(target_cluster['objectifs']):
                            target_cluster['objectifs'].pop(idx_dst)
                        source_cluster['secteurs'].append(s_dst)
                        source_cluster['objectifs'].append(obj_dst)
                        target_cluster['secteurs'].append(s_src)
                        target_cluster['objectifs'].append(obj_src)
                        source_cluster['total_objectif'] = source_cluster['total_objectif'] - obj_src + obj_dst
                        target_cluster['total_objectif'] = target_cluster['total_objectif'] - obj_dst + obj_src
                
                elif best_move_type == 'gouvernorat':
                    gouv_data = best_move_data.get('gouv_data', {})
                    for secteur in gouv_data.get('secteurs', []):
                        obj = objectifs_par_secteur.get(secteur, 0)
                        if secteur in source_cluster['secteurs']:
                            idx = source_cluster['secteurs'].index(secteur)
                            source_cluster['secteurs'].pop(idx)
                            if idx < len(source_cluster['objectifs']):
                                source_cluster['objectifs'].pop(idx)
                            source_cluster['total_objectif'] -= obj
                            source_cluster['nombre_secteurs'] -= 1
                            target_cluster['secteurs'].append(secteur)
                            target_cluster['objectifs'].append(obj)
                            target_cluster['total_objectif'] += obj
                            target_cluster['nombre_secteurs'] += 1
            else:
                break
        
        clusters_totals = self._fix_grand_tunis_only_clusters(clusters_totals, objectifs_par_secteur)
        
        clusters_totals = self._fix_sfax_only_clusters(clusters_totals, objectifs_par_secteur)
        
        clusters_totals = self._balance_within_regions(clusters_totals, objectifs_par_secteur)
        
        clusters_totals = self._force_balance_regions(clusters_totals, objectifs_par_secteur)
        
        return clusters_totals
    
    def _balance_within_regions(self, clusters_totals, objectifs_par_secteur):
        """
        Équilibre les objectifs entre délégués de la même région.
        Essaie toutes les paires source-cible (pas seulement max→min).
        Utilise des échanges (swaps) en plus des déplacements.
        Les contraintes sont levées très tôt pour maximiser l'équilibre.
        Exécute plusieurs passes avec des contraintes de plus en plus lâches.
        """
        regions = {}
        for cluster in clusters_totals:
            region = cluster.get('region', 'Unknown')
            if region not in regions:
                regions[region] = []
            regions[region].append(cluster)
        
        constraint_levels = [
            {'divisibility': True, 'pairs': False, 'proximity': False, 'connectivity': False},
            {'divisibility': True, 'pairs': True, 'proximity': False, 'connectivity': False},
            {'divisibility': True, 'pairs': True, 'proximity': True, 'connectivity': True},
        ]
        
        for region_name, region_clusters in regions.items():
            if len(region_clusters) < 2:
                continue
            
            for constraints in constraint_levels:
                relax_divisibility = constraints['divisibility']
                relax_pairs = constraints['pairs']
                relax_proximity = constraints['proximity']
                relax_connectivity = constraints.get('connectivity', False)
                
                no_improvement_count = 0
                last_obj_ecart = float('inf')
                
                for iteration in range(500):
                    for c in region_clusters:
                        c['km_jour'] = self._calculate_cluster_average_daily_distance(c['secteurs'])
                    
                    obj_values = [c['total_objectif'] for c in region_clusters]
                    obj_moyenne = sum(obj_values) / len(obj_values) if obj_values else 1
                    ecart_obj_pct = ((max(obj_values) - min(obj_values)) / obj_moyenne * 100) if obj_moyenne > 0 else 0
                    
                    if ecart_obj_pct < 2:
                        break
                    
                    if abs(ecart_obj_pct - last_obj_ecart) < 0.01:
                        no_improvement_count += 1
                        if no_improvement_count > 15:
                            break
                    else:
                        no_improvement_count = 0
                    last_obj_ecart = ecart_obj_pct
                    
                    best_move = None
                    best_move_type = None
                    best_move_data = None
                    best_new_obj_ecart = ecart_obj_pct
                    best_new_km_penalty = float('inf')
                    
                    sorted_clusters = sorted(region_clusters, key=lambda x: x['total_objectif'], reverse=True)
                    
                    for source_cluster in sorted_clusters:
                        if source_cluster['total_objectif'] <= obj_moyenne:
                            break
                        
                        for secteur in list(source_cluster['secteurs']):
                            gouv = self._get_gouvernorat_from_secteur(secteur)
                            
                            if not relax_divisibility:
                                if not self._is_gouvernorat_divisible(gouv):
                                    continue
                            
                            for target_cluster in region_clusters:
                                if target_cluster is source_cluster:
                                    continue
                                if target_cluster['total_objectif'] >= source_cluster['total_objectif']:
                                    continue
                                
                                if not relax_pairs:
                                    if self._would_break_pair(secteur, source_cluster['secteurs'], target_cluster['secteurs']):
                                        continue
                                
                                if self._would_violate_exclusive_groups(gouv, target_cluster['secteurs']):
                                    continue
                                
                                if not relax_proximity:
                                    if not self._is_move_allowed_by_proximity(gouv, target_cluster['secteurs']):
                                        continue
                                
                                obj = objectifs_par_secteur.get(secteur, 0)
                                new_src_obj = source_cluster['total_objectif'] - obj
                                new_dst_obj = target_cluster['total_objectif'] + obj
                                old_gap = abs(source_cluster['total_objectif'] - target_cluster['total_objectif'])
                                new_gap = abs(new_src_obj - new_dst_obj)
                                if new_gap >= old_gap:
                                    continue
                                
                                new_secteurs_src = [s for s in source_cluster['secteurs'] if s != secteur]
                                new_secteurs_dst = target_cluster['secteurs'] + [secteur]
                                
                                if len(new_secteurs_src) == 0:
                                    continue
                                if not relax_connectivity:
                                    if not self._are_cluster_gouvernorats_connected(new_secteurs_src):
                                        continue
                                    if not self._are_cluster_gouvernorats_connected(new_secteurs_dst):
                                        continue
                                
                                all_new_obj = []
                                all_new_km = []
                                for c in region_clusters:
                                    if c is source_cluster:
                                        all_new_obj.append(new_src_obj)
                                        all_new_km.append(self._calculate_cluster_average_daily_distance(new_secteurs_src))
                                    elif c is target_cluster:
                                        all_new_obj.append(new_dst_obj)
                                        all_new_km.append(self._calculate_cluster_average_daily_distance(new_secteurs_dst))
                                    else:
                                        all_new_obj.append(c['total_objectif'])
                                        all_new_km.append(c['km_jour'])
                                
                                new_obj_moy = sum(all_new_obj) / len(all_new_obj) if all_new_obj else 1
                                new_ecart_obj = ((max(all_new_obj) - min(all_new_obj)) / new_obj_moy * 100) if new_obj_moy > 0 else 0
                                new_km_moy = sum(all_new_km) / len(all_new_km) if all_new_km else 1
                                new_ecart_km = ((max(all_new_km) - min(all_new_km)) / new_km_moy * 100) if new_km_moy > 0 else 0
                                
                                if new_ecart_obj < best_new_obj_ecart or (abs(new_ecart_obj - best_new_obj_ecart) < 0.3 and new_ecart_km < best_new_km_penalty):
                                    best_new_obj_ecart = new_ecart_obj
                                    best_new_km_penalty = new_ecart_km
                                    best_move = secteur
                                    best_move_type = 'secteur'
                                    best_move_data = {'source': source_cluster, 'target': target_cluster}
                        
                        gouvernorats_in_source = {}
                        for secteur in source_cluster['secteurs']:
                            gouv = self._get_gouvernorat_from_secteur(secteur)
                            if gouv not in gouvernorats_in_source:
                                gouvernorats_in_source[gouv] = {'secteurs': [], 'objectif_total': 0}
                            gouvernorats_in_source[gouv]['secteurs'].append(secteur)
                            gouvernorats_in_source[gouv]['objectif_total'] += objectifs_par_secteur.get(secteur, 0)
                        
                        for gouv, gouv_info in gouvernorats_in_source.items():
                            if len(gouvernorats_in_source) <= 1:
                                continue
                            
                            for target_cluster in region_clusters:
                                if target_cluster is source_cluster:
                                    continue
                                if target_cluster['total_objectif'] >= source_cluster['total_objectif']:
                                    continue
                                
                                if self._would_violate_exclusive_groups(gouv, target_cluster['secteurs']):
                                    continue
                                if not relax_proximity:
                                    if not self._is_move_allowed_by_proximity(gouv, target_cluster['secteurs']):
                                        continue
                                
                                obj_gouv = gouv_info['objectif_total']
                                new_src_obj_g = source_cluster['total_objectif'] - obj_gouv
                                new_dst_obj_g = target_cluster['total_objectif'] + obj_gouv
                                old_gap_g = abs(source_cluster['total_objectif'] - target_cluster['total_objectif'])
                                new_gap_g = abs(new_src_obj_g - new_dst_obj_g)
                                if new_gap_g >= old_gap_g:
                                    continue
                                
                                new_secteurs_src = [s for s in source_cluster['secteurs'] if s not in gouv_info['secteurs']]
                                new_secteurs_dst = target_cluster['secteurs'] + gouv_info['secteurs']
                                
                                if len(new_secteurs_src) == 0:
                                    continue
                                if not relax_connectivity:
                                    if not self._are_cluster_gouvernorats_connected(new_secteurs_src):
                                        continue
                                    if not self._are_cluster_gouvernorats_connected(new_secteurs_dst):
                                        continue
                                
                                all_new_obj = []
                                all_new_km = []
                                for c in region_clusters:
                                    if c is source_cluster:
                                        all_new_obj.append(c['total_objectif'] - obj_gouv)
                                        all_new_km.append(self._calculate_cluster_average_daily_distance(new_secteurs_src))
                                    elif c is target_cluster:
                                        all_new_obj.append(c['total_objectif'] + obj_gouv)
                                        all_new_km.append(self._calculate_cluster_average_daily_distance(new_secteurs_dst))
                                    else:
                                        all_new_obj.append(c['total_objectif'])
                                        all_new_km.append(c['km_jour'])
                                
                                new_obj_moy = sum(all_new_obj) / len(all_new_obj) if all_new_obj else 1
                                new_ecart_obj = ((max(all_new_obj) - min(all_new_obj)) / new_obj_moy * 100) if new_obj_moy > 0 else 0
                                new_km_moy = sum(all_new_km) / len(all_new_km) if all_new_km else 1
                                new_ecart_km = ((max(all_new_km) - min(all_new_km)) / new_km_moy * 100) if new_km_moy > 0 else 0
                                
                                if new_ecart_obj < best_new_obj_ecart or (abs(new_ecart_obj - best_new_obj_ecart) < 0.3 and new_ecart_km < best_new_km_penalty):
                                    best_new_obj_ecart = new_ecart_obj
                                    best_new_km_penalty = new_ecart_km
                                    best_move = gouv
                                    best_move_type = 'gouvernorat'
                                    best_move_data = {'source': source_cluster, 'target': target_cluster, 'gouv_data': gouv_info}
                    
                    source_max = sorted_clusters[0] if sorted_clusters else None
                    target_min = sorted_clusters[-1] if sorted_clusters else None
                    if source_max and target_min and source_max is not target_min:
                        for s_src in list(source_max['secteurs']):
                            gouv_src = self._get_gouvernorat_from_secteur(s_src)
                            obj_src = objectifs_par_secteur.get(s_src, 0)
                            if not relax_divisibility and not self._is_gouvernorat_divisible(gouv_src):
                                continue
                            for s_dst in list(target_min['secteurs']):
                                obj_dst = objectifs_par_secteur.get(s_dst, 0)
                                if obj_src <= obj_dst:
                                    continue
                                gouv_dst = self._get_gouvernorat_from_secteur(s_dst)
                                if not relax_divisibility and not self._is_gouvernorat_divisible(gouv_dst):
                                    continue
                                if not relax_pairs:
                                    temp_dst_after = [s for s in target_min['secteurs'] if s != s_dst] + [s_src]
                                    temp_src_after = [s for s in source_max['secteurs'] if s != s_src] + [s_dst]
                                    if self._would_break_pair(s_src, source_max['secteurs'], temp_dst_after):
                                        continue
                                    if self._would_break_pair(s_dst, target_min['secteurs'], temp_src_after):
                                        continue
                                if self._would_violate_exclusive_groups(gouv_src, [s for s in target_min['secteurs'] if s != s_dst]):
                                    continue
                                if self._would_violate_exclusive_groups(gouv_dst, [s for s in source_max['secteurs'] if s != s_src]):
                                    continue
                                new_secteurs_src = [s for s in source_max['secteurs'] if s != s_src] + [s_dst]
                                new_secteurs_dst = [s for s in target_min['secteurs'] if s != s_dst] + [s_src]
                                if not relax_connectivity:
                                    if not self._are_cluster_gouvernorats_connected(new_secteurs_src):
                                        continue
                                    if not self._are_cluster_gouvernorats_connected(new_secteurs_dst):
                                        continue
                                if not relax_proximity:
                                    if not self._is_move_allowed_by_proximity(gouv_src, new_secteurs_dst):
                                        continue
                                    if not self._is_move_allowed_by_proximity(gouv_dst, new_secteurs_src):
                                        continue
                                all_new_obj = []
                                all_new_km = []
                                for c in region_clusters:
                                    if c is source_max:
                                        all_new_obj.append(c['total_objectif'] - obj_src + obj_dst)
                                        all_new_km.append(self._calculate_cluster_average_daily_distance(new_secteurs_src))
                                    elif c is target_min:
                                        all_new_obj.append(c['total_objectif'] - obj_dst + obj_src)
                                        all_new_km.append(self._calculate_cluster_average_daily_distance(new_secteurs_dst))
                                    else:
                                        all_new_obj.append(c['total_objectif'])
                                        all_new_km.append(c['km_jour'])
                                new_obj_moy = sum(all_new_obj) / len(all_new_obj) if all_new_obj else 1
                                new_ecart_obj = ((max(all_new_obj) - min(all_new_obj)) / new_obj_moy * 100) if new_obj_moy > 0 else 0
                                new_km_moy = sum(all_new_km) / len(all_new_km) if all_new_km else 1
                                new_ecart_km = ((max(all_new_km) - min(all_new_km)) / new_km_moy * 100) if new_km_moy > 0 else 0
                                if new_ecart_obj < best_new_obj_ecart or (abs(new_ecart_obj - best_new_obj_ecart) < 0.3 and new_ecart_km < best_new_km_penalty):
                                    best_new_obj_ecart = new_ecart_obj
                                    best_new_km_penalty = new_ecart_km
                                    best_move = (s_src, s_dst)
                                    best_move_type = 'swap'
                                    best_move_data = {'source': source_max, 'target': target_min}
                    
                    if best_move and best_move_data:
                        source = best_move_data['source']
                        target = best_move_data['target']
                        
                        if best_move_type == 'secteur':
                            obj = objectifs_par_secteur.get(best_move, 0)
                            if best_move in source['secteurs']:
                                idx = source['secteurs'].index(best_move)
                                source['secteurs'].pop(idx)
                                if idx < len(source['objectifs']):
                                    source['objectifs'].pop(idx)
                                source['total_objectif'] -= obj
                                source['nombre_secteurs'] -= 1
                                target['secteurs'].append(best_move)
                                target['objectifs'].append(obj)
                                target['total_objectif'] += obj
                                target['nombre_secteurs'] += 1
                        
                        elif best_move_type == 'swap':
                            s_src, s_dst = best_move
                            obj_src = objectifs_par_secteur.get(s_src, 0)
                            obj_dst = objectifs_par_secteur.get(s_dst, 0)
                            if s_src in source['secteurs'] and s_dst in target['secteurs']:
                                idx_src = source['secteurs'].index(s_src)
                                source['secteurs'].pop(idx_src)
                                if idx_src < len(source['objectifs']):
                                    source['objectifs'].pop(idx_src)
                                idx_dst = target['secteurs'].index(s_dst)
                                target['secteurs'].pop(idx_dst)
                                if idx_dst < len(target['objectifs']):
                                    target['objectifs'].pop(idx_dst)
                                source['secteurs'].append(s_dst)
                                source['objectifs'].append(obj_dst)
                                target['secteurs'].append(s_src)
                                target['objectifs'].append(obj_src)
                                source['total_objectif'] = source['total_objectif'] - obj_src + obj_dst
                                target['total_objectif'] = target['total_objectif'] - obj_dst + obj_src
                        
                        elif best_move_type == 'gouvernorat':
                            gouv_info = best_move_data.get('gouv_data', {})
                            for secteur in gouv_info.get('secteurs', []):
                                obj = objectifs_par_secteur.get(secteur, 0)
                                if secteur in source['secteurs']:
                                    idx = source['secteurs'].index(secteur)
                                    source['secteurs'].pop(idx)
                                    if idx < len(source['objectifs']):
                                        source['objectifs'].pop(idx)
                                    source['total_objectif'] -= obj
                                    source['nombre_secteurs'] -= 1
                                    target['secteurs'].append(secteur)
                                    target['objectifs'].append(obj)
                                    target['total_objectif'] += obj
                                    target['nombre_secteurs'] += 1
                    else:
                        break
                
                obj_values_final = [c['total_objectif'] for c in region_clusters]
                obj_moy_final = sum(obj_values_final) / len(obj_values_final) if obj_values_final else 1
                ecart_final = ((max(obj_values_final) - min(obj_values_final)) / obj_moy_final * 100) if obj_moy_final > 0 else 0
                if ecart_final < 5:
                    break
        
        return clusters_totals
    
    def _force_balance_regions(self, clusters_totals, objectifs_par_secteur):
        """
        Rééquilibrage FORCÉ des objectifs par région.
        Nord : aucune contrainte, priorité 1 = objectifs égaux, priorité 2 = distance minimale.
        Autres régions : contrainte de proximité pour Grand Tunis uniquement.
        """
        grand_tunis_gouvs = {'Tunis', 'Ariana', 'Ben Arous', 'La Manouba', 'Manouba'}

        regions = {}
        for cluster in clusters_totals:
            region = cluster.get('region', 'Unknown')
            if region not in regions:
                regions[region] = []
            regions[region].append(cluster)

        for region_name, region_clusters in regions.items():
            if len(region_clusters) < 2:
                continue

            is_nord = region_name.strip().lower() == 'nord'

            for iteration in range(2000):
                obj_values = [c['total_objectif'] for c in region_clusters]
                obj_moyenne = sum(obj_values) / len(obj_values) if obj_values else 1
                ecart_pct = ((max(obj_values) - min(obj_values)) / obj_moyenne * 100) if obj_moyenne > 0 else 0

                if ecart_pct < 5:
                    break

                src = max(region_clusters, key=lambda x: x['total_objectif'])
                tgt = min(region_clusters, key=lambda x: x['total_objectif'])

                if src is tgt:
                    break

                gap = src['total_objectif'] - tgt['total_objectif']
                ideal_move = gap / 2.0

                best_secteur = None
                best_obj_score = float('inf')
                best_km_score = float('inf')

                for secteur in sorted(src['secteurs']):
                    obj = objectifs_par_secteur.get(secteur, 0)
                    gouv = self._get_gouvernorat_from_secteur(secteur)

                    if not is_nord:
                        if self._would_violate_exclusive_groups(gouv, tgt['secteurs']):
                            continue
                        if gouv in grand_tunis_gouvs:
                            if not self._is_move_allowed_by_proximity(gouv, tgt['secteurs']):
                                continue

                    new_src_obj = src['total_objectif'] - obj
                    new_tgt_obj = tgt['total_objectif'] + obj
                    new_gap = abs(new_src_obj - new_tgt_obj)
                    if new_gap >= gap:
                        continue

                    obj_score = abs(obj - ideal_move)

                    if is_nord:
                        new_tgt_secteurs = tgt['secteurs'] + [secteur]
                        km_score = self._calculate_cluster_average_daily_distance(new_tgt_secteurs)
                    else:
                        km_score = 0.0

                    if obj_score < best_obj_score or (
                        abs(obj_score - best_obj_score) < 50 and km_score < best_km_score
                    ):
                        best_obj_score = obj_score
                        best_km_score = km_score
                        best_secteur = secteur

                if best_secteur is None:
                    for secteur in sorted(src['secteurs'], key=lambda s: objectifs_par_secteur.get(s, 0)):
                        obj = objectifs_par_secteur.get(secteur, 0)
                        gouv = self._get_gouvernorat_from_secteur(secteur)

                        if not is_nord:
                            if self._would_violate_exclusive_groups(gouv, tgt['secteurs']):
                                continue
                            if gouv in grand_tunis_gouvs:
                                if not self._is_move_allowed_by_proximity(gouv, tgt['secteurs']):
                                    continue

                        new_gap = abs((src['total_objectif'] - obj) - (tgt['total_objectif'] + obj))
                        if new_gap < gap:
                            best_secteur = secteur
                            break

                if best_secteur is None:
                    break

                obj = objectifs_par_secteur.get(best_secteur, 0)
                if best_secteur in src['secteurs']:
                    idx = src['secteurs'].index(best_secteur)
                    src['secteurs'].pop(idx)
                    if idx < len(src['objectifs']):
                        src['objectifs'].pop(idx)
                    src['total_objectif'] -= obj
                    src['nombre_secteurs'] -= 1
                    tgt['secteurs'].append(best_secteur)
                    tgt['objectifs'].append(obj)
                    tgt['total_objectif'] += obj
                    tgt['nombre_secteurs'] += 1

        return clusters_totals
    
    def _is_grand_tunis_only(self, secteurs_list):
        """Vérifie si un cluster contient uniquement des gouvernorats du Grand Tunis"""
        grand_tunis_gouvs = {'Tunis', 'Ariana', 'Ben Arous', 'La Manouba', 'Manouba'}
        
        cluster_gouvs = set()
        for secteur in secteurs_list:
            gouv = self._get_gouvernorat_from_secteur(secteur)
            gouv_normalized = self._normalize_gouvernorat_name(gouv)
            cluster_gouvs.add(gouv_normalized)
        
        for gouv in cluster_gouvs:
            if gouv not in grand_tunis_gouvs:
                return False
        return True
    
    def _fix_grand_tunis_only_clusters(self, clusters_totals, objectifs_par_secteur):
        """
        Corrige les clusters qui n'ont que le Grand Tunis.
        RÈGLE ABSOLUE: Aucun délégué ne peut avoir uniquement le Grand Tunis.
        Chaque délégué doit avoir au moins un gouvernorat hors Grand Tunis.
        """
        grand_tunis_neighbors = ['Bizerte', 'Zaghouan', 'Nabeul', 'Beja', 'Jendouba']
        
        max_attempts = 10
        for attempt in range(max_attempts):
            all_fixed = True
            
            for cluster in clusters_totals:
                if not self._is_grand_tunis_only(cluster['secteurs']):
                    continue
                
                all_fixed = False
                
                for other_cluster in clusters_totals:
                    if other_cluster is cluster:
                        continue
                    
                    other_gouvs = {}
                    for secteur in other_cluster['secteurs']:
                        gouv = self._get_gouvernorat_from_secteur(secteur)
                        gouv_norm = self._normalize_gouvernorat_name(gouv)
                        if gouv_norm not in other_gouvs:
                            other_gouvs[gouv_norm] = []
                        other_gouvs[gouv_norm].append(secteur)
                    
                    for neighbor_gouv in grand_tunis_neighbors:
                        if neighbor_gouv not in other_gouvs:
                            continue
                        
                        secteurs_to_move = other_gouvs[neighbor_gouv]
                        remaining_secteurs = [s for s in other_cluster['secteurs'] if s not in secteurs_to_move]
                        
                        if len(remaining_secteurs) == 0:
                            continue
                        
                        for secteur in secteurs_to_move:
                            obj = objectifs_par_secteur.get(secteur, 0)
                            
                            if secteur in other_cluster['secteurs']:
                                idx = other_cluster['secteurs'].index(secteur)
                                other_cluster['secteurs'].pop(idx)
                                if idx < len(other_cluster['objectifs']):
                                    other_cluster['objectifs'].pop(idx)
                                other_cluster['total_objectif'] -= obj
                                other_cluster['nombre_secteurs'] -= 1
                                
                                cluster['secteurs'].append(secteur)
                                cluster['objectifs'].append(obj)
                                cluster['total_objectif'] += obj
                                cluster['nombre_secteurs'] += 1
                        
                        if not self._is_grand_tunis_only(cluster['secteurs']):
                            break
                    
                    if not self._is_grand_tunis_only(cluster['secteurs']):
                        break
            
            if all_fixed:
                break
        
        return clusters_totals
    
    def _is_sfax_only(self, secteurs_list):
        """Vérifie si un cluster contient uniquement Sfax"""
        cluster_gouvs = set()
        for secteur in secteurs_list:
            gouv = self._get_gouvernorat_from_secteur(secteur)
            gouv_normalized = self._normalize_gouvernorat_name(gouv)
            cluster_gouvs.add(gouv_normalized)
        
        # Si tous les gouvernorats sont Sfax
        return cluster_gouvs == {'Sfax'}
    
    def _fix_sfax_only_clusters(self, clusters_totals, objectifs_par_secteur):
        """
        Corrige les clusters qui n'ont que Sfax.
        RÈGLE: Dans le Sud, aucun délégué ne peut avoir uniquement Sfax.
        Chaque délégué avec Sfax doit avoir au moins un gouvernorat voisin.
        """
        sfax_neighbors = ['Mahdia', 'Sidi Bouzid', 'Kairouan', 'Gabes', 'Gafsa']
        
        max_attempts = 10
        for attempt in range(max_attempts):
            all_fixed = True
            
            for cluster in clusters_totals:
                if not self._is_sfax_only(cluster['secteurs']):
                    continue
                
                all_fixed = False
                
                for other_cluster in clusters_totals:
                    if other_cluster is cluster:
                        continue
                    
                    other_gouvs = {}
                    for secteur in other_cluster['secteurs']:
                        gouv = self._get_gouvernorat_from_secteur(secteur)
                        gouv_norm = self._normalize_gouvernorat_name(gouv)
                        if gouv_norm not in other_gouvs:
                            other_gouvs[gouv_norm] = []
                        other_gouvs[gouv_norm].append(secteur)
                    
                    for neighbor_gouv in sfax_neighbors:
                        if neighbor_gouv not in other_gouvs:
                            continue
                        
                        secteurs_to_move = other_gouvs[neighbor_gouv]
                        remaining_secteurs = [s for s in other_cluster['secteurs'] if s not in secteurs_to_move]
                        
                        if len(remaining_secteurs) == 0:
                            continue
                        
                        for secteur in secteurs_to_move:
                            obj = objectifs_par_secteur.get(secteur, 0)
                            
                            if secteur in other_cluster['secteurs']:
                                idx = other_cluster['secteurs'].index(secteur)
                                other_cluster['secteurs'].pop(idx)
                                if idx < len(other_cluster['objectifs']):
                                    other_cluster['objectifs'].pop(idx)
                                other_cluster['total_objectif'] -= obj
                                other_cluster['nombre_secteurs'] -= 1
                                
                                cluster['secteurs'].append(secteur)
                                cluster['objectifs'].append(obj)
                                cluster['total_objectif'] += obj
                                cluster['nombre_secteurs'] += 1
                        
                        if not self._is_sfax_only(cluster['secteurs']):
                            break
                    
                    if not self._is_sfax_only(cluster['secteurs']):
                        break
            
            if all_fixed:
                break
        
        return clusters_totals
    
    def _try_balance_other_pairs(self, clusters_totals, objectifs_par_secteur, objectif_cible):
        """Essaie d'équilibrer d'autres paires de clusters (pas seulement max/min)"""
        n = len(clusters_totals)
        if n <= 2:
            return False
        
        improved = False
        
        # Essayer toutes les paires possibles
        for i in range(n):
            for j in range(i + 1, n):
                cluster_a = clusters_totals[i]
                cluster_b = clusters_totals[j]
                
                if cluster_a['total_objectif'] <= cluster_b['total_objectif']:
                    cluster_high, cluster_low = cluster_b, cluster_a
                else:
                    cluster_high, cluster_low = cluster_a, cluster_b
                
                ecart = cluster_high['total_objectif'] - cluster_low['total_objectif']
                ecart_pct = ecart / objectif_cible * 100 if objectif_cible > 0 else 0
                
                if ecart_pct < 20:
                    continue
                
                # Identifier gouvernorats dans cluster_high
                gouvernorats_in_high = {}
                for secteur in cluster_high['secteurs']:
                    gouv = self._get_gouvernorat_from_secteur(secteur)
                    if gouv not in gouvernorats_in_high:
                        gouvernorats_in_high[gouv] = {'secteurs': [], 'objectif_total': 0}
                    gouvernorats_in_high[gouv]['secteurs'].append(secteur)
                    gouvernorats_in_high[gouv]['objectif_total'] += objectifs_par_secteur.get(secteur, 0)
                
                # Chercher le meilleur gouvernorat à déplacer (avec proximité)
                best_gouv = None
                best_gouv_data = None
                best_new_ecart = ecart
                best_proximity = -1
                
                for gouv, gouv_data in gouvernorats_in_high.items():
                    if len(gouvernorats_in_high) <= 1:
                        continue
                    
                    if not self._is_move_allowed_by_proximity(gouv, cluster_low['secteurs']):
                        continue
                    
                    if self._would_violate_exclusive_groups(gouv, cluster_low['secteurs']):
                        continue
                    
                    obj_gouv = gouv_data['objectif_total']
                    
                    new_high = cluster_high['total_objectif'] - obj_gouv
                    new_low = cluster_low['total_objectif'] + obj_gouv
                    
                    if new_low > new_high + objectif_cible * 0.05:
                        continue
                    
                    new_ecart = abs(new_high - new_low)
                    
                    # Calculer le score de proximité
                    proximity = self._calculate_cluster_proximity_score(gouv, cluster_low['secteurs'])
                    
                    # Préférer les gouvernorats proches du cluster destination
                    if new_ecart < best_new_ecart or (new_ecart == best_new_ecart and proximity > best_proximity):
                        best_new_ecart = new_ecart
                        best_proximity = proximity
                        best_gouv = gouv
                        best_gouv_data = gouv_data
                
                # Déplacer le meilleur gouvernorat trouvé
                if best_gouv and best_new_ecart < ecart:
                    for secteur in best_gouv_data['secteurs']:
                        obj = objectifs_par_secteur.get(secteur, 0)
                        
                        if secteur in cluster_high['secteurs']:
                            idx = cluster_high['secteurs'].index(secteur)
                            cluster_high['secteurs'].pop(idx)
                            if idx < len(cluster_high['objectifs']):
                                cluster_high['objectifs'].pop(idx)
                            cluster_high['total_objectif'] -= obj
                            cluster_high['nombre_secteurs'] -= 1
                            
                            cluster_low['secteurs'].append(secteur)
                            cluster_low['objectifs'].append(obj)
                            cluster_low['total_objectif'] += obj
                            cluster_low['nombre_secteurs'] += 1
                    
                    improved = True
                
                if improved:
                    break
            if improved:
                break
        
        return improved
    
    def _calculate_balance_score(self, clusters_totals, objectif_cible, secteurs_cible):
        """Calcule un score de déséquilibre (plus petit = meilleur équilibre)"""
        if not clusters_totals:
            return 0
        
        score = 0
        for cluster in clusters_totals:
            # Écart objectif normalisé
            if objectif_cible > 0:
                score += abs(cluster['total_objectif'] - objectif_cible) / objectif_cible
            # Écart secteurs normalisé (pondération 0.3)
            if secteurs_cible > 0:
                score += abs(cluster['nombre_secteurs'] - secteurs_cible) / secteurs_cible * 0.3
        
        return score / len(clusters_totals)
    
    def _is_gouvernorat_divisible(self, gouvernorat):
        """Vérifie si un gouvernorat peut être divisé entre plusieurs délégués"""
        gouv_lower = gouvernorat.lower().strip()
        for divisible_gov in self.GOUVERNORATS_DIVISIBLES:
            if divisible_gov.lower() in gouv_lower or gouv_lower in divisible_gov.lower():
                return True
        return False
    
    def _get_paired_gouvernorat(self, gouvernorat):
        """Retourne le gouvernorat apparié ou None"""
        gouv = gouvernorat.strip()
        for a, b in self.GOUVERNORATS_PAIRES:
            if a == gouv:
                return b
            if b == gouv:
                return a
        return None
    
    def _would_break_pair(self, secteur, source_secteurs, target_secteurs):
        """Vérifie si déplacer un secteur casserait une paire géographique ou une paire de secteurs"""
        gouv = self._get_gouvernorat_from_secteur(secteur)
        paired = self._get_paired_gouvernorat(gouv)
        if paired is not None:
            paired_in_source = any(self._get_gouvernorat_from_secteur(s) == paired for s in source_secteurs if s != secteur)
            if paired_in_source:
                paired_in_target = any(self._get_gouvernorat_from_secteur(s) == paired for s in target_secteurs)
                if not paired_in_target:
                    return True
        
        paired_secteur = self._get_paired_secteur(secteur)
        if paired_secteur is not None:
            if paired_secteur in source_secteurs and paired_secteur not in target_secteurs:
                return True
        
        return False
    
    def _get_paired_secteur(self, secteur):
        """Retourne le secteur apparié, ou None"""
        for s_a, s_b in self.SECTEURS_PAIRES:
            if secteur == s_a:
                return s_b
            if secteur == s_b:
                return s_a
        return None
    
    def _merge_split_gouvernorats(self, clusters_totals, all_secteurs, objectifs_par_secteur):
        """
        Post-traitement: fusionne les gouvernorats NON DIVISIBLES qui ont été séparés sur plusieurs clusters.
        Seuls Tunis, Ariana, Ben Arous, La Manouba et Sfax peuvent être divisés.
        Tous les autres gouvernorats doivent rester sur un seul délégué.
        """
        # Identifier tous les gouvernorats et leurs secteurs
        gouvernorat_counts = {}
        for secteur in all_secteurs:
            gouv = self._get_gouvernorat_from_secteur(secteur)
            if gouv not in gouvernorat_counts:
                gouvernorat_counts[gouv] = []
            gouvernorat_counts[gouv].append(secteur)
        
        # Gouvernorats à ne pas séparer = tous ceux qui ne sont PAS divisibles
        gouv_to_keep_together = {g: sects for g, sects in gouvernorat_counts.items() 
                                  if not self._is_gouvernorat_divisible(g)}
        
        if not gouv_to_keep_together:
            return clusters_totals
        
        # Itérer jusqu'à satisfaction de toutes les contraintes (max 10 iterations)
        max_iterations = 10
        for iteration in range(max_iterations):
            splits_found = False
            
            for gouv, gouv_secteurs in sorted(gouv_to_keep_together.items()):
                # Trouver dans quels clusters sont les secteurs de ce gouvernorat
                cluster_distribution = {}
                for cluster in clusters_totals:
                    for secteur in cluster['secteurs']:
                        if secteur in gouv_secteurs:
                            cluster_id = cluster['cluster_id']
                            if cluster_id not in cluster_distribution:
                                cluster_distribution[cluster_id] = []
                            cluster_distribution[cluster_id].append(secteur)
                
                # S'il y a plus d'un cluster pour ce gouvernorat, fusionner
                if len(cluster_distribution) > 1:
                    splits_found = True
                    # Trouver le cluster avec le plus de secteurs de ce gouvernorat
                    target_cluster_id = max(cluster_distribution.keys(), key=lambda x: (len(cluster_distribution[x]), x))
                    target_cluster = next(c for c in clusters_totals if c['cluster_id'] == target_cluster_id)
                    
                    # Déplacer les secteurs des autres clusters vers le target_cluster
                    for cluster_id, secteurs_in_cluster in sorted(cluster_distribution.items()):
                        if cluster_id != target_cluster_id:
                            source_cluster = next(c for c in clusters_totals if c['cluster_id'] == cluster_id)
                            
                            for secteur in secteurs_in_cluster:
                                if secteur in source_cluster['secteurs']:
                                    # Retirer du cluster source
                                    idx = source_cluster['secteurs'].index(secteur)
                                    source_cluster['secteurs'].pop(idx)
                                    objectif_secteur = source_cluster['objectifs'].pop(idx) if idx < len(source_cluster['objectifs']) else objectifs_par_secteur.get(secteur, 0)
                                    source_cluster['total_objectif'] -= objectif_secteur
                                    source_cluster['nombre_secteurs'] -= 1
                                    
                                    # Ajouter au cluster cible
                                    target_cluster['secteurs'].append(secteur)
                                    target_cluster['objectifs'].append(objectif_secteur)
                                    target_cluster['total_objectif'] += objectif_secteur
                                    target_cluster['nombre_secteurs'] += 1
            
            # Si aucun split trouvé, sortir de la boucle
            if not splits_found:
                break
        
        # Redistribuer vers les clusters vides au lieu de les supprimer
        clusters_totals = self._refill_empty_clusters(clusters_totals, objectifs_par_secteur)
        
        # Forcer les paires géographiques dans le même cluster
        for gouv_a, gouv_b in self.GOUVERNORATS_PAIRES:
            cluster_a_id = None
            cluster_b_id = None
            for cluster in clusters_totals:
                for sect in cluster['secteurs']:
                    gouv = self._get_gouvernorat_from_secteur(sect)
                    if gouv == gouv_a and cluster_a_id is None:
                        cluster_a_id = cluster['cluster_id']
                    if gouv == gouv_b and cluster_b_id is None:
                        cluster_b_id = cluster['cluster_id']
            if cluster_a_id is not None and cluster_b_id is not None and cluster_a_id != cluster_b_id:
                target = next(c for c in clusters_totals if c['cluster_id'] == cluster_b_id)
                if self._would_violate_exclusive_groups(gouv_a, target['secteurs']):
                    continue
                source = next(c for c in clusters_totals if c['cluster_id'] == cluster_a_id)
                for sect in list(source['secteurs']):
                    if self._get_gouvernorat_from_secteur(sect) == gouv_a:
                        idx = source['secteurs'].index(sect)
                        obj_s = source['objectifs'].pop(idx) if idx < len(source['objectifs']) else objectifs_par_secteur.get(sect, 0)
                        source['secteurs'].pop(idx)
                        source['total_objectif'] -= obj_s
                        source['nombre_secteurs'] -= 1
                        target['secteurs'].append(sect)
                        target['objectifs'].append(obj_s)
                        target['total_objectif'] += obj_s
                        target['nombre_secteurs'] += 1
        
        # Forcer les paires de secteurs dans le même cluster
        for sect_a, sect_b in self.SECTEURS_PAIRES:
            cluster_a_id = None
            cluster_b_id = None
            for cluster in clusters_totals:
                if sect_a in cluster['secteurs']:
                    cluster_a_id = cluster['cluster_id']
                if sect_b in cluster['secteurs']:
                    cluster_b_id = cluster['cluster_id']
            if cluster_a_id is not None and cluster_b_id is not None and cluster_a_id != cluster_b_id:
                source = next(c for c in clusters_totals if c['cluster_id'] == cluster_a_id)
                target = next(c for c in clusters_totals if c['cluster_id'] == cluster_b_id)
                idx = source['secteurs'].index(sect_a)
                obj_s = source['objectifs'].pop(idx) if idx < len(source['objectifs']) else objectifs_par_secteur.get(sect_a, 0)
                source['secteurs'].pop(idx)
                source['total_objectif'] -= obj_s
                source['nombre_secteurs'] -= 1
                target['secteurs'].append(sect_a)
                target['objectifs'].append(obj_s)
                target['total_objectif'] += obj_s
                target['nombre_secteurs'] += 1
        
        clusters_totals = self._refill_empty_clusters(clusters_totals, objectifs_par_secteur)
        
        return clusters_totals
    
    def _get_pair_chain(self, gouv):
        """
        Retourne l'ensemble complet de gouvernorats liés par des paires transitives.
        Ex: si Sidi Bouzid↔Mahdia et Mahdia↔Monastir, retourne {Sidi Bouzid, Mahdia, Monastir}
        """
        chain = {gouv}
        changed = True
        while changed:
            changed = False
            for a, b in self.GOUVERNORATS_PAIRES:
                if a in chain and b not in chain:
                    chain.add(b)
                    changed = True
                elif b in chain and a not in chain:
                    chain.add(a)
                    changed = True
        return chain

    def _refill_empty_clusters(self, clusters_totals, objectifs_par_secteur):
        """
        Au lieu de supprimer les clusters vides, déplace un groupe complet de gouvernorats
        (incluant toute la chaîne de paires) du cluster le plus chargé vers le cluster vide.
        Cela évite que les contraintes de paires ne défassent le remplissage.
        """
        empty_clusters = [c for c in clusters_totals if c['nombre_secteurs'] <= 0]
        if not empty_clusters:
            return clusters_totals
        
        for empty_cluster in empty_clusters:
            non_empty = [c for c in clusters_totals if c['nombre_secteurs'] > 1]
            if not non_empty:
                break
            
            best_source = None
            best_group_sects = None
            best_remaining = -1
            
            for source in sorted(non_empty, key=lambda c: c['nombre_secteurs'], reverse=True):
                gouv_groups = {}
                for sect in source['secteurs']:
                    gouv = self._get_gouvernorat_from_secteur(sect)
                    if gouv not in gouv_groups:
                        gouv_groups[gouv] = []
                    gouv_groups[gouv].append(sect)
                
                chain_groups = {}
                for gouv in gouv_groups:
                    chain = frozenset(self._get_pair_chain(gouv))
                    if chain not in chain_groups:
                        chain_groups[chain] = []
                    chain_groups[chain].extend(gouv_groups[gouv])
                
                if len(chain_groups) < 2:
                    if self._is_gouvernorat_divisible(list(gouv_groups.keys())[0] if gouv_groups else ''):
                        half = len(source['secteurs']) // 2
                        if half > 0:
                            sects_to_move = sorted(source['secteurs'])[half:]
                            remaining = len(source['secteurs']) - len(sects_to_move)
                            if remaining > 0 and (best_group_sects is None or remaining > best_remaining):
                                best_source = source
                                best_group_sects = sects_to_move
                                best_remaining = remaining
                    continue
                
                for chain_key, chain_sects in sorted(chain_groups.items(), key=lambda x: len(x[1])):
                    remaining = len(source['secteurs']) - len(chain_sects)
                    if remaining > 0 and len(chain_sects) > 0:
                        sousse_in_chain = any(self._get_gouvernorat_from_secteur(s) == 'Sousse' for s in chain_sects)
                        sousse_in_remaining = any(self._get_gouvernorat_from_secteur(s) == 'Sousse' 
                                                  for s in source['secteurs'] if s not in chain_sects)
                        if sousse_in_chain and not sousse_in_remaining:
                            continue
                        if sousse_in_remaining and remaining == len([s for s in source['secteurs'] if s not in chain_sects and self._get_gouvernorat_from_secteur(s) == 'Sousse']):
                            continue
                        
                        if best_group_sects is None or remaining > best_remaining:
                            best_source = source
                            best_group_sects = chain_sects
                            best_remaining = remaining
                    break
                
                if best_source is not None:
                    break
            
            if best_source is not None and best_group_sects is not None:
                for sect in list(best_group_sects):
                    if sect in best_source['secteurs']:
                        idx = best_source['secteurs'].index(sect)
                        best_source['secteurs'].pop(idx)
                        obj_s = best_source['objectifs'].pop(idx) if idx < len(best_source['objectifs']) else objectifs_par_secteur.get(sect, 0)
                        best_source['total_objectif'] -= obj_s
                        best_source['nombre_secteurs'] -= 1
                        
                        empty_cluster['secteurs'].append(sect)
                        empty_cluster['objectifs'].append(obj_s)
                        empty_cluster['total_objectif'] = empty_cluster.get('total_objectif', 0) + obj_s
                        empty_cluster['nombre_secteurs'] = len(empty_cluster['secteurs'])
            else:
                print(f"WARNING: Could not refill empty cluster {empty_cluster.get('cluster_id', '?')} - no movable group found")
        
        clusters_totals = [c for c in clusters_totals if c['nombre_secteurs'] > 0]
        return clusters_totals
    
    def _group_secteurs_simple_fallback(self, secteurs, objectifs_par_secteur, objectifs_list, n_delegates):
        """
        Fallback simple en cas d'erreur K-means.
        IMPORTANT: Seuls Tunis, Ariana, Ben Arous, La Manouba et Sfax peuvent être divisés.
        Tous les autres gouvernorats doivent rester ensemble sur le même délégué.
        """
        # Identifier les gouvernorats NON divisibles qui doivent rester ensemble
        gouvernorat_counts = self._get_gouvernorat_secteurs_count(secteurs)
        locked_gouvernorats = {g for g in gouvernorat_counts.keys() 
                              if not self._is_gouvernorat_divisible(g)}
        
        # Regrouper les secteurs des gouvernorats verrouillés
        gouvernorat_groups = {}  # gouvernorat -> liste de (secteur, objectif)
        individual_secteurs = []  # secteurs qui peuvent être distribués individuellement
        
        for secteur in secteurs:
            gouv = self._get_gouvernorat_from_secteur(secteur)
            objectif = objectifs_par_secteur.get(secteur, 0)
            
            if gouv in locked_gouvernorats:
                if gouv not in gouvernorat_groups:
                    gouvernorat_groups[gouv] = []
                gouvernorat_groups[gouv].append((secteur, objectif))
            else:
                individual_secteurs.append((secteur, objectif))
        
        # Trier les groupes de gouvernorats par objectif total décroissant
        gouvernorat_items = []
        for gouv, secteur_list in gouvernorat_groups.items():
            total_obj = sum(obj for _, obj in secteur_list)
            gouvernorat_items.append((gouv, secteur_list, total_obj))
        gouvernorat_items.sort(key=lambda x: x[2], reverse=True)
        
        # Trier les secteurs individuels par objectif décroissant
        individual_secteurs.sort(key=lambda x: x[1], reverse=True)
        
        # Initialiser les groupes
        groupes = [[] for _ in range(n_delegates)]
        objectifs_groupes = [0] * n_delegates
        
        # D'abord, placer les groupes de gouvernorats verrouillés (ensemble)
        for gouv, secteur_list, total_obj in gouvernorat_items:
            # Trouver le groupe avec le plus petit objectif actuel
            idx_min = objectifs_groupes.index(min(objectifs_groupes))
            # Ajouter TOUS les secteurs de ce gouvernorat au même groupe
            for secteur, objectif in secteur_list:
                groupes[idx_min].append(secteur)
            objectifs_groupes[idx_min] += total_obj
        
        # Ensuite, distribuer les secteurs individuels
        for secteur, objectif in individual_secteurs:
            idx_min = objectifs_groupes.index(min(objectifs_groupes))
            groupes[idx_min].append(secteur)
            objectifs_groupes[idx_min] += objectif
        
        # Préparer le résultat
        result = []
        for i, groupe_secteurs in enumerate(groupes):
            objectif_groupe = sum(objectifs_par_secteur.get(s, 0) for s in groupe_secteurs)
            secteurs_detaille = [{'nom': s, 'objectif': objectifs_par_secteur.get(s, 0)} for s in groupe_secteurs]
            secteurs_detaille.sort(key=lambda x: x['objectif'], reverse=True)
            result.append((groupe_secteurs, objectif_groupe, secteurs_detaille))
        
        return result
    
    def _get_objectifs_par_secteur_pour_region(self, region_name):
        """
        Récupère les objectifs totaux par secteur pour une région spécifique
        """
        if region_name not in self.SECTEURS_PAR_REGION:
            return {}
        
        secteurs_region = self.SECTEURS_PAR_REGION[region_name]
        objectifs_par_secteur = {}
        
        # Initialiser seulement les secteurs non retirés
        for secteur in secteurs_region:
            if not self._is_secteur_retire(secteur):
                objectifs_par_secteur[secteur] = 0
        
        # Somme des objectifs de tous les produits pour chaque secteur
        for product in self.product_folders:
            secteur_dist, secteur_total = self.get_secteur_distribution_with_objectives(product)
            
            if secteur_dist:
                for secteur in secteurs_region:
                    # Vérifier si le secteur est retiré
                    if self._is_secteur_retire(secteur):
                        continue
                    
                    # Chercher le secteur dans la distribution
                    for secteur_dist_name, secteur_data in secteur_dist.items():
                        if self._secteurs_match(secteur, secteur_dist_name):
                            quantite = secteur_data.get('quantite', 0)
                            objectifs_par_secteur[secteur] += quantite
                            break
        
        return objectifs_par_secteur
    
    def _group_secteurs_by_objective_with_details(self, secteurs_region, objectifs_par_secteur, objectif_cible_par_delegue, n_delegates):
        """
        Regroupe les secteurs par objectif avec détails des objectifs par secteur.
        IMPORTANT: Respecte la contrainte que les gouvernorats avec 2-3 secteurs
        doivent rester ensemble sur le même délégué.
        """
        # Filtrer les secteurs retirés
        secteurs_region_filtres = [s for s in secteurs_region if not self._is_secteur_retire(s)]
        
        # Identifier les gouvernorats avec 2-3 secteurs qui doivent rester ensemble
        gouvernorat_counts = self._get_gouvernorat_secteurs_count(secteurs_region_filtres)
        locked_gouvernorats = {g for g, count in gouvernorat_counts.items() if 2 <= count <= 3}
        
        # Regrouper les secteurs des gouvernorats verrouillés
        gouvernorat_groups = {}  # gouvernorat -> liste de (secteur, objectif)
        individual_secteurs = []  # secteurs qui peuvent être distribués individuellement
        
        for secteur in secteurs_region_filtres:
            gouv = self._get_gouvernorat_from_secteur(secteur)
            objectif = objectifs_par_secteur.get(secteur, 0)
            
            if gouv in locked_gouvernorats:
                if gouv not in gouvernorat_groups:
                    gouvernorat_groups[gouv] = []
                gouvernorat_groups[gouv].append((secteur, objectif))
            else:
                individual_secteurs.append((secteur, objectif))
        
        # Trier les groupes de gouvernorats par objectif total décroissant
        gouvernorat_items = []
        for gouv, secteur_list in gouvernorat_groups.items():
            total_obj = sum(obj for _, obj in secteur_list)
            gouvernorat_items.append((gouv, secteur_list, total_obj))
        gouvernorat_items.sort(key=lambda x: x[2], reverse=True)
        
        # Trier les secteurs individuels par objectif décroissant
        individual_secteurs.sort(key=lambda x: x[1], reverse=True)
        
        # Initialiser les groupes
        groupes = [[] for _ in range(n_delegates)]
        objectifs_groupes = [0] * n_delegates
        secteurs_detaille_groupes = [[] for _ in range(n_delegates)]
        
        # D'abord, placer les groupes de gouvernorats verrouillés (ensemble)
        for gouv, secteur_list, total_obj in gouvernorat_items:
            idx_min = objectifs_groupes.index(min(objectifs_groupes))
            for secteur, objectif in secteur_list:
                groupes[idx_min].append(secteur)
                secteurs_detaille_groupes[idx_min].append({
                    'nom': secteur,
                    'objectif': objectif
                })
            objectifs_groupes[idx_min] += total_obj
        
        # Ensuite, distribuer les secteurs individuels
        for secteur, objectif in individual_secteurs:
            idx_min = objectifs_groupes.index(min(objectifs_groupes))
            groupes[idx_min].append(secteur)
            objectifs_groupes[idx_min] += objectif
            secteurs_detaille_groupes[idx_min].append({
                'nom': secteur,
                'objectif': objectif
            })
        
        # Retourner les groupes avec leurs objectifs totaux et secteurs détaillés
        result = []
        for i, (groupe_secteurs, groupe_secteurs_detaille) in enumerate(zip(groupes, secteurs_detaille_groupes)):
            objectif_groupe = sum(secteur.get('objectif', 0) for secteur in groupe_secteurs_detaille)
            result.append((groupe_secteurs, objectif_groupe, groupe_secteurs_detaille))
        
        return result
    
    def distribute_delegates_by_secteur_with_clustering(self, region_name, n_delegates, product=None):
        """
        Répartit les délégués d'une région entre les secteurs en utilisant le clustering K-means EXCLUSIF
        """
        if region_name not in self.SECTEURS_PAR_REGION:
            return {'erreur': f'Région {region_name} non trouvée'}
        
        if n_delegates <= 0:
            return {'erreur': 'Nombre de délégués doit être > 0'}
        
        # Obtenir les secteurs de la région
        secteurs_region = self.SECTEURS_PAR_REGION[region_name]
        
        # Filtrer les secteurs retirés
        secteurs_region_filtres = [s for s in secteurs_region if not self._is_secteur_retire(s)]
        
        # Obtenir les objectifs par secteur
        if product:
            secteur_dist, secteur_total = self.get_secteur_distribution_with_objectives(product)
            objectifs_par_secteur = {}
            for secteur in secteurs_region_filtres:
                for secteur_dist_name, secteur_data in secteur_dist.items():
                    if self._secteurs_match(secteur, secteur_dist_name):
                        objectifs_par_secteur[secteur] = secteur_data.get('quantite', 0)
                        break
                else:
                    objectifs_par_secteur[secteur] = 0
        else:
            objectifs_par_secteur = self._get_objectifs_par_secteur_pour_region(region_name)
        
        # Calculer l'objectif cible par délégué
        total_objectif = sum(objectifs_par_secteur.values())
        objectif_cible_par_delegue = total_objectif / n_delegates if n_delegates > 0 else 0
        
        # UTILISER K-MEANS EXCLUSIVEMENT
        try:
            # Préparer les données
            secteurs_avec_objectifs = []
            objectifs_avec_secteurs = []
            for secteur in secteurs_region_filtres:
                objectif = objectifs_par_secteur.get(secteur, 0)
                secteurs_avec_objectifs.append(secteur)
                objectifs_avec_secteurs.append(objectif)
            
            # Adapter si nécessaire
            n_clusters_adapted = min(n_delegates, len(secteurs_avec_objectifs))
            if n_clusters_adapted <= 1:
                # Pas de clustering nécessaire
                repartition = {}
                delegue_key = 'Délégué_1'
                secteurs_detaille = [{'nom': s, 'objectif': objectifs_par_secteur.get(s, 0)} for s in secteurs_avec_objectifs]
                repartition[delegue_key] = {
                    'secteurs': secteurs_detaille,
                    'objectif_total': total_objectif,
                    'nombre_secteurs': len(secteurs_detaille)
                }
                
                return {
                    'region': region_name,
                    'nombre_delegues': 1,
                    'nombre_secteurs': len(secteurs_region_filtres),
                    'repartition': repartition,
                    'statistiques': {
                        'objectif_total_region': total_objectif,
                        'objectif_moyen_par_delegue': total_objectif,
                        'objectif_min_par_delegue': total_objectif,
                        'objectif_max_par_delegue': total_objectif,
                        'desequilibre_percent': 0,
                        'evaluation_equilibre': 'Parfaitement équilibré',
                        'methode_utilisee': 'K-means (1 cluster)'
                    }
                }
            
            # Appliquer K-means exclusif
            groupes_secteurs, methode = self._cluster_secteurs_with_kmeans_exclusive(
                region_name, secteurs_avec_objectifs, objectifs_par_secteur,
                objectifs_avec_secteurs, n_clusters_adapted, objectif_cible_par_delegue
            )
            
            # Créer la répartition
            repartition = {}
            for i, (secteurs_groupe, objectif_groupe, secteurs_detaille) in enumerate(groupes_secteurs):
                delegue_key = f'Délégué_{i+1}'
                repartition[delegue_key] = {
                    'secteurs': secteurs_detaille,
                    'objectif_total': objectif_groupe,
                    'nombre_secteurs': len(secteurs_detaille)
                }
            
            # Calculer les statistiques
            objectifs_par_delegue = [data['objectif_total'] for data in repartition.values()]
            if objectifs_par_delegue:
                objectif_min = min(objectifs_par_delegue)
                objectif_max = max(objectifs_par_delegue)
                objectif_moyen = sum(objectifs_par_delegue) / len(objectifs_par_delegue)
                desequilibre_pct = ((objectif_max - objectif_min) / objectif_moyen * 100) if objectif_moyen > 0 else 0
            else:
                objectif_min = objectif_max = objectif_moyen = desequilibre_pct = 0
            
            return {
                'region': region_name,
                'nombre_delegues': len(repartition),
                'nombre_secteurs': len(secteurs_region_filtres),
                'repartition': repartition,
                'statistiques': {
                    'objectif_total_region': total_objectif,
                    'objectif_moyen_par_delegue': objectif_moyen,
                    'objectif_min_par_delegue': objectif_min,
                    'objectif_max_par_delegue': objectif_max,
                    'desequilibre_percent': desequilibre_pct,
                    'evaluation_equilibre': 'Équilibré' if desequilibre_pct < 20 else 'Partiellement équilibré' if desequilibre_pct < 40 else 'Déséquilibré',
                    'methode_utilisee': methode
                }
            }
            
        except Exception as e:
            pass  # Fallback to simple method
            return self._distribute_simple(secteurs_region_filtres, objectifs_par_secteur, n_delegates, region_name)
    
    def _distribute_simple(self, secteurs_region, objectifs_par_secteur, n_delegates, region_name):
        """
        Distribution simple sans clustering (fallback)
        """
        # Trier les secteurs par objectif
        secteurs_tries = sorted(
            [(s, objectifs_par_secteur.get(s, 0)) for s in secteurs_region],
            key=lambda x: x[1],
            reverse=True
        )
        
        # Initialiser les délégués
        repartition = {f'Délégué_{i+1}': {'secteurs': [], 'objectif_total': 0} for i in range(n_delegates)}
        
        # Distribuer équitablement
        for i, (secteur, objectif) in enumerate(secteurs_tries):
            delegate_idx = i % n_delegates
            delegate_key = f'Délégué_{delegate_idx + 1}'
            
            repartition[delegate_key]['secteurs'].append({
                'nom': secteur,
                'objectif': objectif
            })
            repartition[delegate_key]['objectif_total'] += objectif
        
        # Calculer les statistiques
        objectifs_par_delegue = [data['objectif_total'] for data in repartition.values()]
        if objectifs_par_delegue:
            objectif_min = min(objectifs_par_delegue)
            objectif_max = max(objectifs_par_delegue)
            objectif_moyen = sum(objectifs_par_delegue) / len(objectifs_par_delegue)
            desequilibre_pct = ((objectif_max - objectif_min) / objectif_moyen * 100) if objectif_moyen > 0 else 0
        else:
            objectif_min = objectif_max = objectif_moyen = desequilibre_pct = 0
        
        # Trier les secteurs par objectif dans chaque délégué
        for delegate_key in repartition:
            repartition[delegate_key]['secteurs'].sort(key=lambda x: x['objectif'], reverse=True)
        
        return {
            'region': region_name,
            'nombre_delegues': n_delegates,
            'nombre_secteurs': len(secteurs_region),
            'repartition': repartition,
            'statistiques': {
                'objectif_total_region': sum(objectifs_par_delegue),
                'objectif_moyen_par_delegue': objectif_moyen,
                'objectif_min_par_delegue': objectif_min,
                'objectif_max_par_delegue': objectif_max,
                'desequilibre_percent': desequilibre_pct,
                'evaluation_equilibre': 'Équilibré' if desequilibre_pct < 20 else 'Partiellement équilibré' if desequilibre_pct < 40 else 'Déséquilibré',
                'methode_utilisee': 'K-means adapté (fallback simple)'
            }
        }
    
    def _generate_delegate_recommendations_simple(self, delegues_theorique, delegues_arrondi, taux_utilisation, jours_travail_an):
        """Génère des recommandations basées sur les calculs"""
        recommendations = []
        
        if taux_utilisation < 80:
            recommendations.append(f"Taux d'utilisation bas ({taux_utilisation:.1f}%). Considérer réaffectation des délégués.")
        
        if delegues_arrondi - delegues_theorique > 0.5:
            recommendations.append(f"Arrondi supérieur important. Évaluer possibilité de partage de délégués.")
        
        if jours_travail_an < 200:
            recommendations.append(f"Nombre de jours travaillés bas ({jours_travail_an}). Vérifier les jours fériés et congés.")
        
        if not recommendations:
            recommendations.append("Répartition optimale selon les paramètres actuels.")
        
        return recommendations
    
    # NOUVELLES MÉTHODES POUR GÉRER LES SECTEURS RETIRÉS
    
    def _is_secteur_retire(self, secteur_nom):
        """Vérifie si un secteur est dans la liste des secteurs retirés"""
        if not hasattr(self, 'secteurs_retires') or not self.secteurs_retires:
            return False
        
        secteur_norm = self._normalize_secteur_name_for_matching(secteur_nom)
        
        for secteur_retire in self.secteurs_retires:
            secteur_retire_norm = self._normalize_secteur_name_for_matching(secteur_retire)
            if self._secteurs_match(secteur_norm, secteur_retire_norm):
                return True
        
        return False
    
    def _filter_secteurs_retires_dict(self, objectifs_dict):
        """Filtre les secteurs retirés d'un dictionnaire d'objectifs"""
        if not hasattr(self, 'secteurs_retires') or not self.secteurs_retires:
            return objectifs_dict.copy()
        
        filtered = {}
        for secteur, objectif in objectifs_dict.items():
            if not self._is_secteur_retire(secteur):
                filtered[secteur] = objectif
        
        return filtered
    
    def _filter_secteurs_retires_list(self, secteurs_list):
        """Filtre les secteurs retirés d'une liste de secteurs"""
        if not hasattr(self, 'secteurs_retires') or not self.secteurs_retires:
            return secteurs_list.copy()
        
        filtered = []
        for secteur in secteurs_list:
            if not self._is_secteur_retire(secteur):
                filtered.append(secteur)
        
        return filtered

