# 🔑 Clés API / API Keys

L'onglet **Batch Pro** utilise trois fournisseurs de métadonnées : **TVDB**, **TMDB** et **TVmaze**.
The **Batch Pro** tab uses three metadata providers: **TVDB**, **TMDB** and **TVmaze**.

| Fournisseur / Provider | Clé requise / Key needed | Usage |
|------------------------|--------------------------|-------|
| **TheTVDB** | ✅ (gratuite / free) | Séries, recommandé pour Kodi / Series, recommended for Kodi |
| **TMDB** | ✅ (gratuite / free) | Séries + films, réalisateurs/producteurs/studios / Series + movies, directors/producers/studios |
| **TVmaze** | ❌ Aucune / None | Fallback séries / Series fallback |

> 🇫🇷 Collez vos clés dans **Options** (champs masqués `*`). Elles sont stockées **uniquement** dans votre `pymkvpropedit_settings.json` local.
> 🇬🇧 Paste your keys in **Options** (masked `*` fields). They are stored **only** in your local `pymkvpropedit_settings.json`.

---

## 🎬 TheTVDB (v4)

**🇫🇷**
1. Créez un compte sur **[thetvdb.com/auth/register](https://thetvdb.com/auth/register)**
2. Ouvrez **[Dashboard → Account → API Access](https://thetvdb.com/dashboard/account/apikey)**
3. Générez une **clé API v4** (project API key)
4. Collez-la dans **Options → Clé API TheTVDB**

**🇬🇧**
1. Create an account at **[thetvdb.com/auth/register](https://thetvdb.com/auth/register)**
2. Open **[Dashboard → Account → API Access](https://thetvdb.com/dashboard/account/apikey)**
3. Generate a **v4 API key** (project API key)
4. Paste it in **Options → TheTVDB API key**

> ℹ️ TVDB gère le mieux les bibliothèques Kodi (titres, numérotation des épisodes).
> TVDB best matches Kodi libraries (titles, episode numbering).

---

## 🎥 TMDB (v3 auth)

**🇫🇷**
1. Créez un compte sur **[themoviedb.org/signup](https://www.themoviedb.org/signup)**
2. Ouvrez **[Paramètres → API](https://www.themoviedb.org/settings/api)**
3. Demandez une clé **API (v3 auth)** — usage personnel, gratuit, validation immédiate
4. Copiez la **API Key (v3 auth)** dans **Options → Clé API TMDB**

**🇬🇧**
1. Create an account at **[themoviedb.org/signup](https://www.themoviedb.org/signup)**
2. Open **[Settings → API](https://www.themoviedb.org/settings/api)**
3. Request an **API key (v3 auth)** — personal use, free, instant approval
4. Copy the **API Key (v3 auth)** into **Options → TMDB API key**

> ℹ️ TMDB fournit réalisateurs, producteurs (personnes) et studios — utile pour des métadonnées complètes.
> TMDB provides directors, producers (people) and studios — useful for complete metadata.

---

## 🆓 TVmaze

Aucune clé n'est nécessaire. TVmaze sert de **fallback automatique** pour les séries si aucune autre source ne répond.
No key needed. TVmaze acts as an **automatic fallback** for series when no other source responds.

---

## 🔒 Confidentialité / Privacy

- Les clés ne quittent jamais votre machine, sauf pour interroger directement les API officielles.
- Keys never leave your machine except to query the official APIs directly.
- Pour les retirer : videz les champs dans **Options** et sauvegardez.
- To remove them: clear the fields in **Options** and save.

---

[🏠 Home](Home) • [🚀 Batch Pro](Batch-Pro) • [⚙️ Options](Options-Settings)
