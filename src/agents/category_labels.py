"""Noms français des catégories de produits Olist (identifiants anglais de product_category_name_translation.csv).

Source unique : utilisée par les textes de l'agent BO3, le PDF, les réponses de l'assistant et l'interface (via /api/bo3/meta).
Une catégorie absente du dictionnaire garde un libellé lisible dérivé de son identifiant.
"""
from __future__ import annotations

CATEGORY_FR: dict[str, str] = {
    "agro_industry_and_commerce": "Agro-industrie et commerce", "air_conditioning": "Climatisation", "art": "Art",
    "arts_and_craftmanship": "Arts et artisanat", "audio": "Audio", "auto": "Automobile", "baby": "Bébé", "bed_bath_table": "Linge de maison",
    "books_general_interest": "Livres grand public", "books_imported": "Livres importés", "books_technical": "Livres techniques",
    "cds_dvds_musicals": "CD, DVD et comédies musicales", "christmas_supplies": "Articles de Noël", "cine_photo": "Cinéma et photo",
    "computers": "Ordinateurs", "computers_accessories": "Informatique et accessoires", "consoles_games": "Consoles et jeux vidéo",
    "construction_tools_construction": "Outillage de construction", "construction_tools_lights": "Éclairage et électricité",
    "construction_tools_safety": "Équipement de sécurité (chantier)", "cool_stuff": "Objets tendance", "costruction_tools_garden": "Outillage de jardin",
    "costruction_tools_tools": "Outillage", "diapers_and_hygiene": "Couches et hygiène", "drinks": "Boissons", "dvds_blu_ray": "DVD et Blu-ray",
    "electronics": "Électronique", "fashio_female_clothing": "Mode femme", "fashion_bags_accessories": "Sacs et accessoires de mode",
    "fashion_childrens_clothes": "Mode enfant", "fashion_male_clothing": "Mode homme", "fashion_shoes": "Chaussures", "fashion_sport": "Vêtements de sport",
    "fashion_underwear_beach": "Lingerie et maillots de bain", "fixed_telephony": "Téléphonie fixe", "flowers": "Fleurs", "food": "Alimentation",
    "food_drink": "Épicerie et boissons", "furniture_bedroom": "Meubles de chambre", "furniture_decor": "Meubles et décoration",
    "furniture_living_room": "Meubles de salon", "furniture_mattress_and_upholstery": "Matelas et tapisserie",
    "garden_tools": "Jardinage", "health_beauty": "Santé et beauté", "home_appliances": "Électroménager", "home_appliances_2": "Électroménager (gros)",
    "home_comfort_2": "Confort de la maison (2)", "home_confort": "Confort de la maison", "home_construction": "Construction et rénovation",
    "housewares": "Articles ménagers", "industry_commerce_and_business": "Industrie, commerce et entreprise",
    "kitchen_dining_laundry_garden_furniture": "Mobilier cuisine, salle à manger et jardin", "la_cuisine": "Cuisine", "luggage_accessories": "Bagagerie",
    "market_place": "Place de marché (divers)", "music": "Musique", "musical_instruments": "Instruments de musique", "no_items": "Sans article",
    "office_furniture": "Mobilier de bureau", "party_supplies": "Articles de fête", "pc_gamer": "PC gamer", "perfumery": "Parfumerie",
    "pet_shop": "Animalerie", "portateis_cozinha_e_preparadores_de_alimentos": "Petits appareils de cuisine",
    "security_and_services": "Sécurité et services", "signaling_and_security": "Signalisation et sécurité", "small_appliances": "Petit électroménager",
    "small_appliances_home_oven_and_coffee": "Fours et machines à café", "sports_leisure": "Sports et loisirs", "stationery": "Papeterie",
    "tablets_printing_image": "Tablettes, impression et image", "telephony": "Téléphonie mobile", "toys": "Jouets", "unknown": "Catégorie inconnue",
    "watches_gifts": "Montres et cadeaux", "autre": "Autres catégories",
}


def cat_label(slug: object) -> str:
    """Libellé français d'une catégorie ; repli lisible (« some_category » → « Some category »)."""
    s = str(slug or "").strip()
    if not s:
        return "Catégorie inconnue"
    return CATEGORY_FR.get(s, s.replace("_", " ").capitalize())
