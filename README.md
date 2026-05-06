# Nseek — Client IA natif GTK4 pour Linux

![Python](https://img.shields.io/badge/Python-3.10+-blue)
![GTK](https://img.shields.io/badge/GTK-4.0-green)
![Fedora](https://img.shields.io/badge/Fedora-compatible-blue)
![License](https://img.shields.io/badge/License-MIT-yellow)

**Nseek** est un client natif GTK4 pour interagir avec l'API [DeepSeek V4](https://platform.deepseek.com) sous Linux. Léger, rapide et intégré au bureau GNOME.

![Capture d'écran de Nseek](screenshot.png)

---

## ✨ Fonctionnalités

- 💬 **Chat en temps réel** avec streaming des réponses
- 🧠 **Mode Thinking** — affiche le raisonnement interne du modèle
- 📂 **Historique intelligent** — titres extraits automatiquement des conversations
- 📎 **Fichiers & PDF** — envoie des fichiers texte ou PDF jusqu'à 100 000 caractères
- 🔍 **Recherche** dans les conversations avec surlignage
- 💾 **Export** des conversations en `.txt`
- 📊 **Stats en temps réel** — tokens utilisés et coût estimé
- 🎨 **Thèmes clair/sombre** intégrés
- ⌨️ **Raccourcis clavier** complets
- 🌐 Accès direct à **DeepSeek Web**

---

## 📋 Prérequis

- Linux (testé sur **Fedora 41+**)
- Python 3.10+
- GTK 4.0
- PyGObject

```bash
# Fedora
sudo dnf install python3-gobject gtk4
pip install pypdf --break-system-packages
```

---

## 🚀 Installation

```bash
git clone https://github.com/carafife/nseek.git
cd nseek
python3 nseek.py
```

---

## 🔑 Configuration

1. Obtiens une clé API sur [platform.deepseek.com](https://platform.deepseek.com/api_keys)
2. Lance Nseek et colle ta clé dans le champ **Clé API**
3. **Optionnel** — pour ne pas ressaisir ta clé à chaque démarrage, sauvegarde-la dans un fichier texte :

```bash
echo "sk-TACLÉ" > ~/Documents/cle_deepseek_v4_api.txt
```

> ⚠️ Ce nom de fichier est celui attendu par Nseek pour le chargement automatique. Ne le renomme pas.

---

## ⌨️ Raccourcis clavier

| Raccourci | Action |
|-----------|--------|
| `Ctrl+N` | Nouvelle conversation |
| `Ctrl+L` | Effacer la conversation |
| `Ctrl+F` | Rechercher |
| `Ctrl+E` | Exporter en .txt |
| `Ctrl+Shift+C` | Copier la dernière réponse |
| `Ctrl+H` | Afficher/masquer l'historique |
| `Ctrl+T` | Basculer thème clair/sombre |
| `Ctrl+B` | Ouvrir DeepSeek Web |
| `Ctrl+Q` | Quitter |

---

## 🤖 Modèles supportés

| Modèle | Description |
|--------|-------------|
| `deepseek-v4-pro` | Le plus puissant, pour les tâches complexes |
| `deepseek-v4-flash` | Rapide et économique |
| `deepseek-chat` | Modèle standard |

---

## 📄 Licence

MIT License — libre d'utilisation, modification et distribution.

---

## 🙏 Remerciements

- [DeepSeek](https://deepseek.com) pour l'API
- La communauté [Fedora](https://fedoraproject.org) pour l'inspiration
