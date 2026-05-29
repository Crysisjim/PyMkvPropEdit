# ❓ FAQ — Foire Aux Questions / Frequently Asked Questions

---

## 🇫🇷 Français

### L'application ne démarre pas

1. Vérifier que Python 3.10+ est installé : `python --version` dans un terminal
2. Vérifier que Python est dans le PATH (relancer le terminal après installation)
3. Lancer `run.bat` — il installe automatiquement les dépendances
4. Consulter `pymkvpropedit.log` pour les erreurs détaillées

### "mkvpropedit n'est pas reconnu"

Dans l'onglet **Options**, vérifier le chemin vers `mkvpropedit.exe`.
- Version portable : le chemin doit pointer vers `mkvtools\mkvpropedit.exe` (configuré auto par `run.bat`)
- Installation MKVToolNix : généralement `C:\Program Files\MKVToolNix\mkvpropedit.exe`

### L'Audio Sync ne fonctionne pas

1. Vérifier que numpy et scipy sont installés : `pip install numpy scipy`
2. Vérifier que FFmpeg est configuré dans Options
3. Si le fichier est court (< 5 min) : mettre **Début analyse = 0**
4. Réduire la durée d'analyse si le fichier est encore plus court

### Le drag & drop ne fonctionne pas

`tkinterdnd2` est nécessaire. Il est installé automatiquement par `run.bat`.
Si l'erreur persiste : `pip install tkinterdnd2`

### Les notifications ne s'affichent pas

`win11toast` nécessite Windows 10/11. Installer via : `pip install win11toast`
Sur Windows 10, les notifications peuvent nécessiter d'activer le Centre de notifications.

### Changer la langue de l'application

Options tab → Langue → FR / EN → Sauvegarder → Redémarrer l'application.

### Mes presets/paramètres ont disparu

Les fichiers `pymkvpropedit_settings.json` et `presets.json` sont dans le **même dossier** que le fichier `.pyw`.
Vérifier qu'ils n'ont pas été déplacés ou supprimés.

---

## 🇬🇧 English

### The application won't start

1. Check Python 3.10+ is installed: `python --version` in a terminal
2. Check Python is in PATH (restart terminal after installation)
3. Run `run.bat` — it installs dependencies automatically
4. Check `pymkvpropedit.log` for detailed errors

### "mkvpropedit is not recognized"

In the **Options** tab, check the path to `mkvpropedit.exe`.
- Portable version: path should point to `mkvtools\mkvpropedit.exe` (auto-configured by `run.bat`)
- MKVToolNix installation: typically `C:\Program Files\MKVToolNix\mkvpropedit.exe`

### Audio Sync doesn't work

1. Check numpy and scipy are installed: `pip install numpy scipy`
2. Check FFmpeg is configured in Options
3. If the file is short (< 5 min): set **Analysis start = 0**
4. Reduce analysis duration for even shorter files

### Drag & drop doesn't work

`tkinterdnd2` is required. It's installed automatically by `run.bat`.
If the issue persists: `pip install tkinterdnd2`

### Notifications don't appear

`win11toast` requires Windows 10/11. Install via: `pip install win11toast`
On Windows 10, notifications may require enabling the Notification Center.

### How to change the app language

Options tab → Language → FR / EN → Save → Restart the application.

### My presets/settings disappeared

The `pymkvpropedit_settings.json` and `presets.json` files are in the **same folder** as the `.pyw` file.
Check they haven't been moved or deleted.
