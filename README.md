# Vinted Watcher

Surveillance automatique de Vinted pour un usage **strictement personnel** (veille
d'achat) : le programme vérifie périodiquement une ou plusieurs recherches et
envoie une notification Discord dès qu'une nouvelle annonce correspond à tes
critères.

## ⚠️ Avertissement important

- Vinted **n'a pas d'API publique documentée**. Ce projet utilise l'endpoint
  interne `GET /api/v2/catalog/items`, celui que le site web utilise lui-même,
  protégé par Datadome (anti-bot). Cet endpoint **peut changer sans préavis** :
  si le programme s'arrête de fonctionner, c'est probablement que Vinted a
  changé la structure de sa page ou de son API.
- Reste **raisonnable** sur la fréquence des vérifications (jamais moins d'une
  minute par recherche, imposé par le code). Ce n'est pas un outil de scraping
  massif ni de revente automatisée.
- En cas de blocages Datadome fréquents (403 persistants même après
  renouvellement de session), la piste recommandée est de remplacer `requests`
  par [`curl_cffi`](https://github.com/lexiforest/curl_cffi), qui imite la
  signature TLS d'un vrai Chrome (`impersonate="chrome124"` par ex.) là où
  `requests` a une signature TLS reconnaissable comme non-navigateur. Ce n'est
  pas implémenté par défaut pour ne pas ajouter de dépendance inutile tant que
  ce n'est pas nécessaire.

## Installation (Windows)

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

Copie ensuite le fichier d'exemple et renseigne ton webhook Discord :

```powershell
copy .env.example .env
```

Puis édite `.env` :

```
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
```

### Créer un webhook Discord

Dans le salon Discord où tu veux recevoir les alertes : **Paramètres du
salon → Intégrations → Webhooks → Nouveau webhook**, puis copie l'URL du
webhook (bouton "Copier l'URL du webhook") dans `.env`.

## Configurer une recherche

Un exemple est déjà prêt dans `config/searches.json` (GoPro Hero 13, max
200€, vérifiée toutes les 3 minutes). Tu peux le modifier à la main, ou passer
par la CLI :

```powershell
python main.py add --nom "GoPro Hero 13" --mots-cles "gopro hero 13" --prix-max 200
python main.py list
python main.py disable gopro13
python main.py enable gopro13
python main.py remove gopro13
```

## Test manuel (sans Discord)

Avant de brancher Discord, tu peux vérifier que la recherche Vinted fonctionne
elle-même en lançant directement le client :

```powershell
python -m src.vinted_client
```

Ça affiche dans la console les 5 dernières annonces trouvées pour "gopro hero
13" (prix max 200€). Si tu obtiens une erreur 403 persistante, c'est un
blocage Datadome — voir l'avertissement plus haut.

## Lancer la surveillance

```powershell
python main.py
```

Le programme tourne indéfiniment, vérifie chaque recherche active à son
intervalle configuré (avec un peu de hasard pour désynchroniser les appels),
et poste une notification Discord pour chaque nouvelle annonce détectée. À la
toute première vérification d'une recherche, les annonces déjà existantes sont
enregistrées **sans notification** (pour ne pas spammer Discord avec tout
l'historique) ; seules les nouveautés suivantes déclenchent une alerte.

Arrêt propre avec `Ctrl+C`.

Les logs sont écrits dans `logs/vinted_watcher.log` et affichés dans la
console.

## Lancement automatique au démarrage de Windows (optionnel)

Via le **Planificateur de tâches** (`taskschd.msc`) :

1. Créer une tâche de base → déclencheur "À l'ouverture de session".
2. Action : "Démarrer un programme"
   - Programme : `C:\chemin\vers\vinted-watcher\venv\Scripts\python.exe`
   - Arguments : `main.py`
   - Démarrer dans : `C:\chemin\vers\vinted-watcher`
3. Cocher "Exécuter que l'utilisateur soit connecté ou non" si tu veux que ça
   tourne même sans être connecté (nécessite un mot de passe Windows
   enregistré dans la tâche).

## Architecture

```
vinted-watcher/
├── .env.example
├── .gitignore
├── requirements.txt
├── README.md
├── config/
│   └── searches.json       # recherches définies par l'utilisateur
├── data/
│   └── seen_items.db       # SQLite, créé automatiquement
├── src/
│   ├── vinted_client.py    # session HTTP, cookies/CSRF, recherche
│   ├── storage.py          # SQLite : annonces déjà vues
│   ├── notifier.py         # Notifier (interface) + DiscordNotifier
│   ├── searches.py         # chargement/validation des recherches
│   ├── scheduler.py        # boucle principale de vérification
│   └── cli.py              # add / list / enable / disable / remove
├── main.py                 # point d'entrée
└── logs/
    └── vinted_watcher.log
```

La V2 pourra brancher un dashboard web sans réécrire le cœur du projet :
`notifier.py` contient déjà le squelette `WebNotifier` (non implémenté), il
suffira de l'implémenter et de l'ajouter à côté de `DiscordNotifier` dans
`main.py`.
