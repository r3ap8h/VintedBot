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

`config/searches.json` contient tes recherches (y compris d'éventuels
webhooks Discord dédiés par recherche) : ce fichier est **ignoré par git**
(voir `.gitignore`) pour ne jamais exposer un webhook si tu pousses ce projet
sur un dépôt public. Un modèle neutre est fourni dans
`config/searches.example.json` (GoPro Hero 13, max 200€, vérifiée toutes les
3 minutes) — copie-le en `config/searches.json` pour démarrer :

```powershell
copy config\searches.example.json config\searches.json
```

Tu peux ensuite modifier `config/searches.json` à la main, passer par la CLI,
ou par l'**interface web** (voir plus bas) — les trois partagent le même
fichier de config.

### Recherche simple (mots-clés + prix)

```powershell
python main.py add --nom "GoPro Hero 13" --mots-cles "gopro hero 13" --prix-max 200
python main.py list
python main.py disable gopro13
python main.py enable gopro13
python main.py remove gopro13
```

### Recherche avancée (catégorie via URL Vinted)

Pour une catégorie precise (`catalog_ids`), la methode fiable reste de
construire ta recherche directement sur **vinted.fr** avec les filtres du
site, puis de copier l'URL résultante. Le programme la parse
automatiquement :

```powershell
python main.py add-url --nom "Nike Air Max Homme" --url "https://www.vinted.fr/catalog?search_text=air+max&catalog[]=1238&price_to=80" --intervalle-minutes 3
```

La commande affiche un résumé de ce qui a été compris (mots-clés, prix,
filtres avancés détectés) pour que tu puisses vérifier avant de laisser
tourner la surveillance. Ajoute `--webhook <url>` à `add` ou `add-url` pour
donner un webhook Discord dédié à cette recherche (sinon elle utilise le
webhook global de `.env`).

### Critères de filtrage texte (état, marque, taille, terme obligatoire...)

Vinted n'a pas de table stable "nom de filtre → id" pour l'état, la marque ou
la taille (non documenté, changeant sans préavis). Plutôt que de dépendre de
ces ids (`status_ids`, `brand_ids`, `size_ids`...), le programme **filtre côté
application** en comparant les champs texte lisibles renvoyés par l'API
(`status`, `brand_title`, `size_title`) aux critères que tu définis — un
critère non renseigné ne filtre rien.

Critères disponibles, combinables entre eux :

- **Terme obligatoire** : doit apparaître dans le titre de l'annonce.
- **Termes optionnels** : juste indicatifs, élargissent la requête envoyée à
  Vinted mais n'excluent jamais une annonce.
- **État** : un ou plusieurs des 5 niveaux Vinted (Neuf avec étiquette, Neuf
  sans étiquette, Très bon état, Bon état, Satisfaisant).
- **Marque** : texte libre, ou `--sans-marque` pour cibler les annonces sans
  marque renseignée.
- **Taille / format** : texte libre.

```powershell
python main.py add --nom "Robes Zara TBE" --mots-cles "" --terme-obligatoire "robe" --termes-optionnels "fleurie, longue" --etat "Très bon état" --etat "Bon état" --marque "Zara" --taille "M"
```

⚠️ **Couleur, matière et motif ne sont pas gérés** : vérifié en conditions
réelles, ces informations ne sont disponibles ni dans la réponse de recherche
(`GET /api/v2/catalog/items`), ni dans le détail d'une annonce (l'endpoint
`/api/v2/items/{id}` renvoie 404 avec une session anonyme). Les ajouter
nécessiterait de dépendre d'ids Vinted non documentés, ce que ce projet évite
volontairement.

## Test manuel (sans Discord)

Avant de brancher Discord, tu peux vérifier que la recherche Vinted fonctionne
elle-même en lançant directement le client :

```powershell
python -m src.vinted_client
```

Ça affiche dans la console les 5 dernières annonces trouvées pour "gopro hero
13" (prix max 200€). Si tu obtiens une erreur 403 persistante, c'est un
blocage Datadome — voir l'avertissement plus haut.

## Interface web (optionnelle)

Une interface locale permet de gérer les recherches et les webhooks sans
toucher au JSON ni à la CLI : ajouter/modifier/supprimer une recherche (mode
simple ou en collant une URL Vinted, avec aperçu des filtres avant
validation), assigner un webhook Discord dédié à une recherche, tester
n'importe quel webhook, et consulter l'historique des dernières annonces
notifiées.

```powershell
python -m src.webapp
```

Puis ouvre **http://127.0.0.1:8000** dans ton navigateur.

C'est un **second process, séparé de `python main.py`** : les deux tournent
en parallèle (deux terminaux) et partagent `config/searches.json` et
`data/seen_items.db`. Le scheduler (`main.py`) relit `config/searches.json`
automatiquement toutes les ~90 secondes, donc une recherche ajoutée,
modifiée, activée/désactivée ou supprimée depuis l'interface web est prise en
compte **sans avoir à redémarrer `python main.py`**.

Pour assigner un webhook dédié à une recherche (ex: un salon Discord séparé
pour une catégorie d'objets), renseigne son URL dans le formulaire d'ajout ou
d'édition de la recherche. Depuis la page **Webhooks**, un bouton "Envoyer un
message de test" permet de vérifier que le webhook global ou celui d'une
recherche fonctionne, avec le résultat (succès/erreur) affiché directement
dans la page.

⚠️ **Sécurité** : ce serveur écoute uniquement sur `127.0.0.1` (jamais
accessible depuis le réseau) et n'a **aucune authentification** — il permet de
lire/modifier les webhooks Discord configurés. Ne l'expose jamais sur
internet ou sur ton réseau local tel quel. Les webhooks ne sont jamais
affichés en clair dans les pages (toujours tronqués, ex:
`https://discord.com/api/webhooks/1234.../***`), sauf dans le champ de
formulaire au moment de les éditer.

## Lancer la surveillance

```powershell
python main.py
```

Le programme tourne indéfiniment, vérifie chaque recherche active à son
intervalle configuré (avec un peu de hasard pour désynchroniser les appels),
et poste une notification Discord pour chaque nouvelle annonce qui passe les
critères de la recherche (texte + critères texte, voir plus haut). À la toute
première vérification d'une recherche, les annonces déjà existantes sont
enregistrées **sans notification** (pour ne pas spammer Discord avec tout
l'historique) ; seules les nouveautés suivantes déclenchent une alerte. Les
annonces reçues qui ne passent pas les critères texte sont tout de même
enregistrées (pour ne pas être ré-analysées), mais ne notifient jamais.

La notification Discord affiche le prix demandé et, quand Vinted le fournit,
le prix total avec la protection acheteur (hors frais de livraison, non
connus avant le paiement), un bouton "Voir l'annonce sur Vinted" en plus du
titre cliquable, et jusqu'à 4 photos regroupées en galerie quand l'annonce en
a plusieurs.

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
│   ├── searches.example.json  # modele neutre, sans webhook
│   └── searches.json       # recherches definies par l'utilisateur (ignore par git)
├── data/
│   └── seen_items.db       # SQLite, créé automatiquement
├── templates/               # pages HTML de l'interface web (Jinja2)
├── src/
│   ├── vinted_client.py    # session HTTP, cookies/CSRF, recherche, filtres bruts
│   ├── url_parser.py       # extraction des filtres depuis une URL Vinted
│   ├── storage.py          # SQLite : annonces déjà vues, historique
│   ├── notifier.py         # Notifier (interface) + DiscordNotifier + masquage webhook
│   ├── searches.py         # chargement/validation/écriture atomique des recherches
│   ├── filtres_texte.py    # filtrage cote application (etat/marque/taille/terme obligatoire)
│   ├── scheduler.py        # boucle principale, rechargement a chaud, cache de webhooks
│   ├── cli.py              # add / add-url / list / enable / disable / remove
│   └── webapp.py           # interface web locale (FastAPI)
├── main.py                 # point d'entrée du scheduler
└── logs/
    └── vinted_watcher.log
```

La V2 pourra enrichir encore le dashboard web sans réécrire le cœur du
projet : `notifier.py` contient le squelette `WebNotifier` (non implémenté)
pour un futur mode de notification alternatif, a ajouter a cote de
`DiscordNotifier` sans toucher au scheduler.
