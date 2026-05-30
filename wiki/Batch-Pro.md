# 🚀 Batch Pro

L'onglet **Batch Pro** automatise un workflow complet : renommage type FileBot, métadonnées de niveau Kodi/MetaX, réordonnancement des pistes et synchronisation audio — le tout en un seul passage.
The **Batch Pro** tab automates a full workflow: FileBot-style renaming, Kodi/MetaX-level metadata, track reordering and audio sync — all in one pass.

> 🔑 Configurez vos clés API d'abord : voir **[Clés API](API-Keys)**.
> 🔑 Configure your API keys first: see **[API Keys](API-Keys)**.

---

## 🗂️ Les 4 sections / The 4 sections

### ① Fichiers / Files
Ajoutez vos `.mkv` (boutons, dossier, ou glisser-déposer).
Add your `.mkv` files (buttons, folder, or drag & drop).

### ② Renommage Auto / Auto-Rename
- Choisissez la **langue** et l'**API** (`Auto` / `TVDB` / `TMDB` / `TVmaze`).
- Cliquez **🔍 Rechercher les noms** → le tableau propose un nouveau nom (double-clic pour éditer).
- La colonne **Statut** indique la source utilisée (ex. `✓ TVDB`).
- **Format série / Series:** `Titre - S01E07 - Nom épisode.mkv`
- **Format film / Movie:** `Titre (2025) 1080p x265 Dolby Vision.mkv` (résolution/codec/HDR auto)

**🎨 Bouton Illus./Desc.** — ouvre le **picker** : pour chaque champ (illustration, description courte, synopsis long, cast, **réalisateur/producteur/studio**, genres) vous choisissez la source (TVDB / TMDB / TVmaze) indépendamment. Cochez *Appliquer à tous* pour utiliser les mêmes **sources** sur tous les fichiers (le contenu reste propre à chaque épisode).

**🎨 Illus./Desc. button** — opens the **picker**: for each field (cover, short description, long synopsis, cast, **director/producer/studio**, genres) pick the source (TVDB / TMDB / TVmaze) independently. Tick *Apply to all* to reuse the same **sources** across files (content stays per-episode).

### ③ Ordre des pistes / Track Order
- **Charger fichier référence** ou **Premier fichier de la liste** comme modèle.
- **↑ Monter / ↓ Descendre** pour définir l'ordre voulu.
- L'ordre est appliqué par correspondance **type + langue + forced**. Les fichiers avec un nombre/ordre de pistes différent sont gérés et signalés dans le log.

- **Load reference file** or **First file in list** as a template.
- **↑ Up / ↓ Down** to set the desired order.
- Applied by **type + language + forced** matching. Files with a different track count/order are handled and reported in the log.

### ④ Pipeline & Exécution / Pipeline & Execution
Cochez les étapes souhaitées :
Tick the desired steps:

| Option | Effet / Effect |
|--------|----------------|
| Synchroniser audio | Sync FFT (numpy/scipy) — délais auto / auto FFT delays |
| + sous-titres | Applique le décalage aux subs / apply offset to subtitles |
| Appliquer paramètres mkvpropedit | Noms/flags de pistes / track names & flags |
| Réordonner les pistes | Selon le modèle / per template |
| Renommer fichier | Nom auto / auto name |
| Intégrer métadonnées | Tags MKV + cover + NFO Kodi / MKV tags + cover + Kodi NFO |
| Supprimer anciens tags/cover | Nettoie avant d'écrire / clean before writing |
| Dossier de sortie | Place les fichiers finaux ailleurs / move finals elsewhere |

➡️ **Sync + réordonnancement = un seul passage mkvmerge** (remux sans ré-encodage), puis mkvpropedit, métadonnées, renommage.
➡️ **Sync + reorder = a single mkvmerge pass** (remux, no re-encode), then mkvpropedit, metadata, rename.

Une **barre de progression dédiée** affiche `%`, ETA, temps écoulé et compteur `N/total`.
A **dedicated progress bar** shows `%`, ETA, elapsed time and `N/total` counter.

---

## 🏷️ Métadonnées écrites / Metadata written

**Tags MKV :** `TITLE`, `SHOW`, `SUMMARY` (court), `SYNOPSIS` (long), `DESCRIPTION`, `DATE_RELEASED`, `CONTENT_TYPE`, `SEASON/EPISODE.PART_NUM`, `GENRE`, `ARTIST`/`ACTOR`, `DIRECTOR`, `WRITTEN_BY`, `PRODUCER`, `PRODUCTION_STUDIO`/`COPYRIGHT`, `LAW_RATING`/`RATING`, `IMDB`.

**Pièces jointes / Attachments :** `cover.jpg` (poster téléchargé / downloaded poster) + `kodi-metadata` (NFO `<episodedetails>` lu directement par Kodi / read directly by Kodi).

> 💡 Pour réalisateur / producteur / studio : utilisez **TMDB** comme source crew (TVDB ne fournit pas le crew).
> 💡 For director / producer / studio: use **TMDB** as the crew source (TVDB does not provide crew).

---

[🏠 Home](Home) • [🔑 Clés API](API-Keys) • [🗂️ Onglets](Tabs-Overview)
