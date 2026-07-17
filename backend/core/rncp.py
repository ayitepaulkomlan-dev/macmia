"""
core/rncp.py — Référentiel RNCP des blocs de compétences IA / Data.
Source : pipeline d'extraction CV MACMIA.
"""

RNCP_REFERENTIEL = {
    "BC1_collecte_donnees": {
        "label": "Collecte et préparation des données",
        "keywords": [
            "sql", "nosql", "mysql", "postgresql", "mongodb", "cassandra",
            "etl", "pipeline", "nettoyage", "prétraitement", "preprocessing",
            "scraping", "beautifulsoup", "scrapy", "api", "collecte",
            "hadoop", "spark", "kafka", "data lake", "data warehouse",
            "ingestion", "extraction", "transformation",
        ],
        "competences": [
            "Collecte de données (web scraping, API, bases de données)",
            "ETL / Pipeline de données",
            "Nettoyage et prétraitement des données",
            "SQL / NoSQL (MySQL, PostgreSQL, MongoDB, Cassandra)",
            "Big Data (Hadoop, Spark, Kafka)",
            "Data Warehouse / Data Lake",
            "Web scraping (BeautifulSoup, Scrapy)",
        ]
    },
    "BC2_analyse_modelisation": {
        "label": "Analyse et modélisation des données",
        "keywords": [
            "machine learning", "deep learning", "apprentissage", "modèle",
            "classification", "régression", "clustering", "svm", "random forest",
            "forêt", "réseau de neurones", "neural", "cnn", "rnn", "lstm",
            "transformer", "nlp", "langage naturel", "traitement du texte",
            "computer vision", "vision", "image", "segmentation", "détection",
            "scikit", "sklearn", "keras", "tensorflow", "pytorch",
            "statistique", "analyse", "modélisation", "prédiction",
            "séries temporelles", "time series", "numpy", "pandas",
            "matplotlib", "seaborn", "histogramme", "seuillage",
            "algorithme", "calcul", "estimation", "données",
        ],
        "competences": [
            "Statistiques descriptives et inférentielles",
            "Machine Learning supervisé (régression, classification, forêts aléatoires, SVM)",
            "Machine Learning non supervisé (clustering, réduction de dimensionnalité)",
            "Deep Learning (CNN, RNN, LSTM, Transformers)",
            "NLP / Traitement du langage naturel",
            "Computer Vision",
            "Séries temporelles",
            "Optimisation de modèles (hyperparamètres, cross-validation)",
            "Python (scikit-learn, pandas, numpy, matplotlib, seaborn)",
            "R (tidyverse, ggplot2)",
        ]
    },
    "BC3_ia_generative": {
        "label": "IA générative et LLM",
        "keywords": [
            "llm", "large language model", "gpt", "llama", "mistral", "claude",
            "rag", "retrieval", "augmented", "generation", "prompt",
            "fine-tuning", "finetuning", "langchain", "llamaindex",
            "embedding", "vectoriel", "chromadb", "pinecone", "weaviate",
            "agent conversationnel", "chatbot", "génératif", "generative",
        ],
        "competences": [
            "LLM (GPT, Llama, Mistral, Claude)",
            "RAG (Retrieval-Augmented Generation)",
            "Prompt engineering",
            "Fine-tuning de modèles",
            "LangChain / LlamaIndex",
            "Embeddings vectoriels",
            "Vector databases (Pinecone, ChromaDB, Weaviate)",
        ]
    },
    "BC4_developpement_deploiement": {
        "label": "Développement et déploiement IA",
        "keywords": [
            "python", "fastapi", "flask", "django", "docker", "kubernetes",
            "ci/cd", "github actions", "gitlab", "mlops", "mlflow", "dvc",
            "aws", "azure", "gcp", "cloud", "git", "déploiement",
            "api rest", "backend", "serveur", "application",
            "capteur", "iot", "lot", "grafana", "tableau de bord",
            "surveillance", "monitoring",
        ],
        "competences": [
            "Python avancé",
            "API REST (FastAPI, Flask, Django)",
            "Docker / Kubernetes",
            "CI/CD (GitHub Actions, GitLab CI)",
            "MLOps (MLflow, DVC, Kubeflow)",
            "Cloud (AWS, Azure, GCP)",
            "Git / GitHub / GitLab",
            "Tests unitaires",
        ]
    },
    "BC5_visualisation_communication": {
        "label": "Visualisation et communication des données",
        "keywords": [
            "power bi", "tableau", "plotly", "dataviz", "visualisation",
            "dashboard", "rapport", "reporting", "graphique", "chart",
            "storytelling", "présentation", "rédaction",
        ],
        "competences": [
            "Power BI",
            "Tableau",
            "Matplotlib / Seaborn / Plotly",
            "Dataviz interactive",
            "Storytelling avec les données",
            "Rédaction de rapports techniques",
        ]
    },
    "BC6_gestion_projet_ia": {
        "label": "Gestion de projet IA",
        "keywords": [
            "scrum", "agile", "kanban", "gestion de projet", "chef de projet",
            "planning", "planification", "budget", "équipe", "pilotage",
            "conduite du changement", "expression des besoins", "cadrage",
        ],
        "competences": [
            "Méthodes agiles (Scrum, Kanban)",
            "Gestion de projet (PRINCE2, PMP)",
            "Cadrage et expression des besoins",
            "Pilotage d'équipes data",
            "Budget et planification",
            "Conduite du changement",
        ]
    },
    "BC7_ethique_securite": {
        "label": "Éthique, sécurité et conformité IA",
        "keywords": [
            "rgpd", "protection des données", "ia act", "biais", "équité",
            "cybersécurité", "sécurité", "explicabilité", "xai",
            "gouvernance", "conformité", "éthique",
        ],
        "competences": [
            "RGPD / Protection des données",
            "IA Act (réglementation européenne)",
            "Biais algorithmiques et équité",
            "Cybersécurité des systèmes IA",
            "Explicabilité des modèles (XAI)",
            "Gouvernance des données",
        ]
    },
    "BC8_metiers_sectoriels": {
        "label": "Compétences métiers et sectorielles",
        "keywords": [
            "finance", "santé", "industrie", "maintenance prédictive",
            "marketing", "crm", "recommandation", "rh", "supply chain",
            "logistique", "énergie", "smart grid", "transport",
            "réseau social", "social network",
        ],
        "competences": [
            "Finance / Analyse financière",
            "Santé / Bioinformatique",
            "Industrie / IoT / Maintenance prédictive",
            "Marketing / CRM / Recommandation",
            "RH / People Analytics",
            "Supply Chain / Logistique",
            "Énergie / Smart Grid",
        ]
    }
}


RNCP_DESCRIPTIONS = {
    "BC1_collecte_donnees":          "Collecte, ingestion et préparation de données (SQL, NoSQL, ETL, APIs, scraping, pipelines)",
    "BC2_analyse_modelisation":      "Analyse statistique et modélisation ML/DL CLASSIQUE (classification, régression, clustering, CNN, RNN, NLP, computer vision, segmentation d'images, séries temporelles, scikit-learn, Keras, PyTorch, TensorFlow). ATTENTION: la vision par ordinateur et le traitement d'images médicales sont BC2, pas BC3.",
    "BC3_ia_generative":             "IA GÉNÉRATIVE uniquement : modèles qui produisent du contenu (texte, images, code) — LLM (GPT, Llama, Mistral, Claude), RAG, embeddings, bases vectorielles, agents conversationnels, prompt engineering, fine-tuning. Ne pas y mettre le ML classique ni la vision par ordinateur.",
    "BC4_developpement_deploiement": "Développement logiciel et déploiement IA (Python, APIs REST, Docker, CI/CD, MLOps, cloud, IoT, monitoring)",
    "BC5_visualisation_communication":"Visualisation de données et communication (dashboards, Power BI, Plotly, React, reporting, storytelling)",
    "BC6_gestion_projet_ia":         "Gestion de projet IA (Scrum, Agile, planification, pilotage d'équipe, expression des besoins)",
    "BC7_ethique_securite":          "Éthique, sécurité et conformité IA (RGPD, biais algorithmiques, explicabilité, gouvernance des données)",
    "BC8_metiers_sectoriels":        "Compétences métiers sectorielles (finance, santé, industrie, marketing, RH, supply chain, énergie)",
}
