"""Modules d'import de fichiers.

Chaque importeur retourne un dict {kind, data, warnings} :
- kind : "devis_lines" | "chantiers" | "clients" | "depense_facture"
- data : structure normalisée prête à pré-remplir un formulaire
- warnings : liste de messages utilisateur (lignes ignorées, ambiguïtés...)
"""
