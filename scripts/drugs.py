"""Demo drug list (generic names as used in Kompas slugs).

Replace this with the Excel input list later; for now it is a broad oncology set
used to validate the mapping. Some drugs have several Kompas formulations and so
use a qualified slug (e.g. 'methotrexaat__bij_tumoren_'); the oncology form is the
one used here.
"""

DRUGS = [
    "doxorubicine", "epirubicine", "daunorubicine", "idarubicine", "mitoxantron",
    "cisplatine", "carboplatine", "oxaliplatine",
    "cyclofosfamide", "ifosfamide", "chloorambucil", "melfalan", "busulfan",
    "bendamustine", "dacarbazine", "temozolomide", "procarbazine",
    "capecitabine", "gemcitabine", "cytarabine", "methotrexaat__bij_tumoren_",
    "pemetrexed", "mercaptopurine", "tioguanine__als_cytostaticum_", "fludarabine",
    "cladribine__als_cytostaticum_", "nelarabine", "azacitidine", "decitabine",
    "paclitaxel", "docetaxel", "cabazitaxel", "vinblastine", "vincristine",
    "vinorelbine", "etoposide", "irinotecan", "topotecan", "bleomycine",
    "mitomycine", "trabectedine", "eribuline",
    "tamoxifen", "anastrozol", "letrozol", "exemestaan", "fulvestrant",
    "bicalutamide", "enzalutamide", "apalutamide", "darolutamide", "abirateron",
    "gosereline", "leuproreline", "triptoreline", "degarelix",
    "trastuzumab", "pertuzumab", "trastuzumab_emtansine", "trastuzumab_deruxtecan",
    "bevacizumab__intraveneus_", "cetuximab", "panitumumab", "rituximab", "obinutuzumab",
    "brentuximab_vedotin", "polatuzumab_vedotin", "daratumumab", "isatuximab",
    "blinatumomab", "inotuzumab_ozogamicine",
    "nivolumab", "pembrolizumab", "atezolizumab", "durvalumab", "avelumab",
    "ipilimumab", "cemiplimab",
    "imatinib", "dasatinib", "nilotinib", "bosutinib", "ponatinib",
    "erlotinib", "gefitinib", "afatinib", "osimertinib", "crizotinib",
    "alectinib", "brigatinib", "lorlatinib", "sunitinib", "sorafenib",
    "pazopanib", "regorafenib", "cabozantinib", "lenvatinib", "axitinib",
    "vemurafenib", "dabrafenib", "encorafenib", "trametinib", "cobimetinib",
    "binimetinib", "palbociclib", "ribociclib", "abemaciclib", "olaparib",
    "niraparib", "rucaparib", "ibrutinib", "acalabrutinib", "venetoclax",
    "ruxolitinib", "midostaurine", "gilteritinib",
    "bortezomib", "carfilzomib", "ixazomib", "lenalidomide", "thalidomide",
    "pomalidomide",
]
