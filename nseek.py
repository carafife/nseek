#!/usr/bin/env python3
# ─────────────────────────────────────────────────────────────────────────────
# Nseek — Client IA natif GTK4 pour Linux
# Auteur  : carafife
# Licence : GPL v3
# Dépend  : Python 3.10+, GTK 4, GtkSource 5, VTE 3.91, pypdf (optionnel)
# ─────────────────────────────────────────────────────────────────────────────
import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib, Gio, Gdk, Pango
import urllib.request, urllib.error
import json, threading, queue, os, base64, datetime, re, signal, sys

# ── Gestion du signal SIGINT (Ctrl+C dans le terminal) ───────────────────────
signal.signal(signal.SIGINT, lambda *_: os._exit(0))
try:
    from gi.repository import GLibUnix
    GLibUnix.signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, lambda: os._exit(0))
except ImportError:
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, lambda: os._exit(0))

# ── Constantes globales ───────────────────────────────────────────────────────
API_URL  = "https://api.deepseek.com/v1/chat/completions"  # Endpoint DeepSeek
HIST_DIR = os.path.expanduser("~/.local/share/deepseek-chat")  # Dossier historique JSON
KEY_FILE = os.path.expanduser("~/Documents/cle_deepseek_v4_api.txt")  # Clé API sauvegardée
os.makedirs(HIST_DIR, exist_ok=True)

# ── Coûts estimés par million de tokens (USD) ─────────────────────────────────
COSTS = {
    "deepseek-v4-pro":   {"in": 1.74,  "out": 3.48},
    "deepseek-v4-flash": {"in": 0.14,  "out": 0.28},
    "deepseek-chat":     {"in": 0.14,  "out": 0.28},
}

def make_title(messages):
    """Génère un titre lisible à partir du premier message utilisateur."""
    for m in messages:
        if m['role'] == 'user':
            c = m['content'] if isinstance(m['content'], str) else ""
            # Nettoyer et tronquer
            c = re.sub(r'\s+', ' ', c).strip()
            c = re.sub(r'[^\w\s\u00C0-\u017E?!.,]', '', c)
            words = c.split()[:7]  # 7 premiers mots max
            title = ' '.join(words)
            return title[:45] if title else "Conversation"
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
# ── Extraction de texte depuis fichiers (PDF, texte brut) ───────────────────
def extract_text(path, mime):
    """Extrait le texte d'un fichier selon son type."""
    if mime == 'application/pdf':
        try:
            import pypdf
            reader = pypdf.PdfReader(path)
            text = '\n'.join(p.extract_text() or '' for p in reader.pages)
            return text.strip(), len(reader.pages)
        except Exception as e:
            return f"[Erreur lecture PDF: {e}]", 0
    else:
        for enc in ['utf-8', 'latin-1', 'cp1252']:
            try:
                with open(path, encoding=enc) as f:
                    return f.read(), 0
            except Exception:
                continue
        return open(path, 'rb').read().decode(errors='replace'), 0

MAX_CHARS = 100_000  # Limite de caractères pour les fichiers joints

# ── Gestion des sessions (historique JSON) ───────────────────────────────────
def session_path(name): return os.path.join(HIST_DIR, name + '.json')

def save_session(name, messages):
    if not messages: return
    title = make_title(messages)
    with open(session_path(name), 'w') as f:
        json.dump({'name': name, 'title': title, 'messages': messages}, f, ensure_ascii=False, indent=2)
def load_session(fname):
    with open(os.path.join(HIST_DIR, fname)) as f: return json.load(f)
def delete_session(name):
    p = session_path(name)
    if os.path.exists(p): os.remove(p)
def list_sessions():
    return sorted([f[:-5] for f in os.listdir(HIST_DIR) if f.endswith('.json')], reverse=True)

# ── Feuilles de style GTK4 ───────────────────────────────────────────────────
# CSS_DARK : thème sombre bleu marine (défaut)
CSS_DARK = """
window { background:#060d1a; }
headerbar { background:#080f1e; border-bottom:1px solid #152238; }
headerbar windowcontrols button { background:transparent; }
.app-title { font-weight:bold; font-size:12pt; color:#c8ddf0; letter-spacing:2px; }
.app-sub   { font-size:9pt; color:#2a5a9a; letter-spacing:3px; }
.sidebar { background:#060d1a; border-right:1px solid #152238; min-width:300px; }
.sidebar-title { color:#4a8ac0; font-size:9pt; font-weight:bold; padding:10px 12px 8px; letter-spacing:3px; border-bottom:1px solid #152238; margin-bottom:4px; }
.cfg     { background:#09142a; padding:8px 10px; margin:0 10px 6px; border-radius:6px; border:1px solid #152238; }
.lbl     { color:#2a5a9a; font-size:10pt; }
checkbutton label { color:#7aaad0; font-size:10pt; }
textview { background:#060d1a; color:#c8ddf0; }
textview text { background:#060d1a; color:#c8ddf0; }
.input-tv textview, .input-tv textview text { background:#08111f; color:#c8ddf0; }
.input-tv { border:1px solid #152238; border-radius:5px; padding:2px; }
.input-tv:focus-within { border-color:#1e4a8a; }
.send  { background:#1a3d7a; color:#c8ddf0; font-weight:bold; border-radius:5px; padding:5px 14px; letter-spacing:1px; border:1px solid #2a5a9a; }
.send:hover { background:#1e4a8a; color:#e0eeff; }
.send:disabled { background:#09142a; color:#152238; }
.tool  { background:#09142a; color:#7aaad0; border-radius:5px; padding:4px 9px; border:1px solid #152238; }
.tool:hover { background:#152238; color:#c8ddf0; }
.sess-row { padding:7px 10px; border-bottom:1px solid #0a1525; background:#060d1a; }
.sess-name { color:#7aaad0; font-size:10pt; }
.del-btn { background:transparent; color:#152238; border-radius:5px; padding:2px 6px; font-size:10pt; border:none; }
.del-btn:hover { background:#1a0a0a; color:#e05555; }
.new-sess { background:#0d1f3c; color:#60a5fa; border-radius:0; padding:10px 12px; font-size:11pt; font-weight:bold; border:none; border-bottom:1px solid #1e3a5f; border-top:1px solid #1e3a5f; letter-spacing:1px; outline:none; box-shadow:none; }
.new-sess:hover { background:#152238; color:#93c5fd; }
.new-sess:focus { outline:none; box-shadow:none; border:none; border-bottom:1px solid #1e3a5f; border-top:1px solid #1e3a5f; }
.status { color:#1e3a5f; font-size:9pt; padding:2px 12px 4px; }
.search-bar { background:#060d1a; padding:4px 10px; border-bottom:1px solid #152238; }
.toggle { background:#0d1f3c; color:#60a5fa; border-radius:5px; padding:4px 10px; border:1px solid #1e3a5f; font-size:13pt; font-weight:bold; }
.theme-btn, .web-btn, .hdr-btn { background:transparent; color:#2a5a9a; border-radius:5px; padding:4px 9px; border:none; }
.toggle:hover, .theme-btn:hover, .web-btn:hover, .hdr-btn:hover { background:#09142a; color:#7aaad0; }
.quit-btn { background:transparent; color:#fbbf24; border:none; font-weight:bold; font-size:13pt; padding:4px 10px; }
.quit-btn:hover { background:transparent; color:#fcd34d; }
.vtoolbar { background:#060d1a; border-left:1px solid #152238; }
.vtool { background:transparent; color:#2a5a9a; border-radius:5px; padding:6px; border:none; font-size:14pt; min-width:36px; }
.vtool:hover { background:#09142a; color:#7aaad0; }
.vtool-quit { background:transparent; color:#f66151; border-radius:5px; padding:6px; border:none; font-size:14pt; min-width:36px; }
.vtool-quit:hover { background:#3a1a1a; color:#ff8070; }
notebook { background:#060d1a; }
notebook header { background:#080f1e; border-bottom:2px solid #152238; }
notebook header tabs tab { background:#080f1e; color:#2a5a9a; padding:6px 16px; border:none; border-bottom:2px solid transparent; }
notebook header tabs tab:checked { background:#060d1a; color:#7aaad0; border-bottom:2px solid #2a5a9a; }
notebook header tabs tab:hover { background:#09142a; color:#4a8ac0; }
notebook stack { background:#060d1a; }
.code-copy-btn { background:#0d1f3c; color:#60a5fa; border:1px solid #1e3a5f; border-radius:4px; padding:3px 10px; font-size:9pt; }
.code-copy-btn:hover { background:#1e3a5f; color:#93c5fd; }
.code-header { background:#0a1628; padding:4px 8px; border-radius:6px 6px 0 0; border-bottom:1px solid #1e3a5f; }
.code-lang { color:#60a5fa; font-size:9pt; font-weight:bold; letter-spacing:1px; }
listbox { background:#060d1a; border:none; }
listbox row { background:#060d1a; border:none; outline:none; }
listbox row:hover { background:#09142a; }
listbox row:selected { background:#09142a; border:none; }
listbox row:selected:focus { background:#09142a; border:none; outline:none; box-shadow:none; }
scrolledwindow { background:#060d1a; border:none; }
scrolledwindow undershoot.top, scrolledwindow undershoot.bottom,
scrolledwindow overshoot.top, scrolledwindow overshoot.bottom { background:#060d1a; }
viewport { background:#060d1a; border:none; }
separator { background:#060d1a; border:none; min-height:0; min-width:0; }
"""

# CSS_LIGHT : thème clair bleu ardoise
CSS_LIGHT = """
window { background:#f5f5f0; }
headerbar { background:#e8e8e2; border-bottom:1px solid #c8c8c0; }
headerbar windowcontrols button { background:transparent; }
.app-title { font-weight:bold; font-size:12pt; color:#0d2545; letter-spacing:2px; }
.app-sub   { font-size:9pt; color:#2a5a9a; letter-spacing:3px; }
.sidebar { background:#eeede8; border-right:1px solid #c8c8c0; min-width:300px; }
.sidebar-title { color:#1a4f8a; font-size:9pt; font-weight:bold; padding:10px 12px 8px; letter-spacing:3px; border-bottom:1px solid #c8c8c0; }
.cfg     { background:#e8e8e2; padding:8px 10px; margin:0 10px 6px; border-radius:6px; border:1px solid #c8c8c0; }
.lbl     { color:#1a4f8a; font-size:10pt; }
checkbutton label { color:#0d2545; font-size:10pt; }
textview { background:#f5f5f0; color:#0d1e35; }
textview text { background:#f5f5f0; color:#0d1e35; }
.input-tv textview, .input-tv textview text { background:#ffffff; color:#0d1e35; }
.input-tv { border:1px solid #c8c8c0; border-radius:5px; padding:2px; }
.input-tv:focus-within { border-color:#1a4f8a; }
.send  { background:#1a4f8a; color:#ffffff; font-weight:bold; border-radius:5px; padding:5px 14px; letter-spacing:1px; }
.send:hover { background:#0d3566; color:#ffffff; }
.send:disabled { background:#c8c8c0; color:#888888; }
.tool  { background:#e0e0da; color:#1a4f8a; border-radius:5px; padding:4px 9px; border:1px solid #c8c8c0; }
.tool:hover { background:#d0d0ca; color:#0d2545; }
.sess-row { padding:7px 10px; border-bottom:1px solid #dcdcd6; background:#eeede8; }
.sess-name { color:#0d2545; font-size:10pt; }
.del-btn { background:transparent; color:#c0bdb8; border-radius:5px; padding:2px 6px; font-size:10pt; border:none; }
.del-btn:hover { background:#fde8e8; color:#c01c28; }
.new-sess { background:#e0ecf8; color:#1a4f8a; border-radius:0; padding:10px 12px; font-size:11pt; font-weight:bold; border:none; border-bottom:1px solid #a0c0e0; border-top:1px solid #a0c0e0; letter-spacing:1px; }
.new-sess:hover { background:#cce0f5; color:#0d2545; }
.status { color:#4a7aaa; font-size:9pt; padding:2px 12px 4px; }
.search-bar { background:#eeede8; padding:4px 10px; border-bottom:1px solid #c8c8c0; }
.toggle { background:#d8e8f8; color:#1a4f8a; border-radius:5px; padding:4px 10px; border:1px solid #a0c0e0; font-size:13pt; font-weight:bold; }
.theme-btn, .web-btn, .hdr-btn { background:transparent; color:#1a4f8a; border-radius:5px; padding:4px 9px; border:none; }
.toggle:hover, .theme-btn:hover, .web-btn:hover, .hdr-btn:hover { background:#d8d8d2; color:#0d2545; }
.quit-btn { background:transparent; color:#b45309; border-radius:5px; padding:4px 9px; border:none; font-weight:bold; font-size:14pt; }
.quit-btn:hover { background:#fef3c7; color:#92400e; }
.vtoolbar { background:#e8e8e2; border-left:1px solid #c8c8c0; }
.vtool { background:transparent; color:#1a4f8a; border-radius:5px; padding:6px; border:none; font-size:14pt; min-width:36px; }
.vtool:hover { background:#d8d8d2; color:#0d2545; }
.vtool.quit-btn { color:#c01c28; }
.vtool.quit-btn:hover { background:#fde8e8; color:#a0001a; }
.code-header { background:#dde3ec; padding:4px 8px; border-top:1px solid #c0cce0; border-bottom:1px solid #c0cce0; }
.code-lang { color:#1a4f8a; font-size:9pt; font-weight:bold; letter-spacing:1px; }
.code-copy-btn { background:#e8eef8; color:#1a4f8a; border:1px solid #a0b8d8; border-radius:4px; padding:3px 10px; font-size:9pt; }
.code-copy-btn:hover { background:#1a4f8a; color:#ffffff; }
listbox { background:#eeede8; border:none; }
listbox row { background:#eeede8; border:none; }
listbox row:hover { background:#e8e8e2; }
listbox row:selected { background:#dcdcd6; border:none; }
scrolledwindow { background:#eeede8; border:none; }
viewport { background:#eeede8; border:none; }
notebook { background:#f5f5f0; }
notebook header { background:#e8e8e2; border-bottom:2px solid #c8c8c0; }
notebook header tabs tab { background:#e8e8e2; color:#4a7aaa; padding:6px 16px; border:none; border-bottom:2px solid transparent; }
notebook header tabs tab:checked { background:#f5f5f0; color:#0d2545; border-bottom:2px solid #1a4f8a; }
notebook header tabs tab:hover { background:#dcdcd6; color:#0d2545; }
notebook stack { background:#f5f5f0; }
"""

# ── Tags TextBuffer pour la coloration du chat ───────────────────────────────
# TAGS_DARK : couleurs pour le thème sombre
TAGS_DARK = {
    "you":   {"foreground":"#60a5fa","weight":700},
    "ai":    {"foreground":"#34d399","weight":700},
    "err":   {"foreground":"#f87171","weight":700},
    "think": {"foreground":"#a78bfa","style":2},
    "body":  {"foreground":"#e0eeff"},
    "code":  {"foreground":"#6ee7b7","family":"Monospace","background":"#0a1628"},
    "bold":  {"foreground":"#fbbf24","weight":700},
    "info":  {"foreground":"#2d5a8a","style":2},
    "hl":    {"background":"#1d4ed8","foreground":"#ffffff"},
}
# TAGS_LIGHT : couleurs pour le thème clair
TAGS_LIGHT = {
    "you":   {"foreground":"#1c71d8","weight":700},
    "ai":    {"foreground":"#26a269","weight":700},
    "err":   {"foreground":"#c01c28","weight":700},
    "think": {"foreground":"#9141ac","style":2},
    "body":  {"foreground":"#1a1a1a"},
    "code":  {"foreground":"#1e6b1e","family":"Monospace","background":"#e0edd0"},
    "bold":  {"foreground":"#8a4800","weight":700},
    "info":  {"foreground":"#888886","style":2},
    "hl":    {"background":"#e6a817","foreground":"#000000"},
}

# ─────────────────────────────────────────────────────────────────────────────
# Fenêtre principale de Nseek
# Contient : headerbar, sidebar historique, zone chat, toolbar verticale
# ─────────────────────────────────────────────────────────────────────────────
class Win(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Nseek")
        self.set_default_size(960, 700)
        self.maximize()
        self.history       = []
        self.session_name  = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M")
        self.attached_file = None
        self.last_reply    = ""
        self.total_tokens  = 0
        self.total_cost    = 0.0
        self.session_in    = 0
        self.session_out   = 0
        self.font_size     = 11
        self.is_dark       = True
        self.css_provider  = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(
            self.get_display(), self.css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.css_provider.load_from_string(CSS_DARK)
        # CSS supplémentaire pour les dialogues en mode sombre
        self.dlg_css = Gtk.CssProvider()
        self.dlg_css.load_from_string("""
            dialog { background:#2a2a2a; color:#e0e0e0; }
            dialog .dialog-vbox { background:#2a2a2a; }
            dialog label { color:#e0e0e0; }
            dialog box { background:#2a2a2a; }
            scrolledwindow { background:#2a2a2a; }
        """)
        Gtk.StyleContext.add_provider_for_display(
            self.get_display(), self.dlg_css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 2)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_child(root)
        self._build_headerbar()
        self.paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self.paned.set_vexpand(True)
        root.append(self.paned)
        self._build_sidebar()
        self._build_main(root)
        self._build_toolbar(root)
        self._build_statusbar(root)
        self._setup_shortcuts()
        self._load_key()
        self._msg("info", "Bienvenue ! Clé API pré-remplie. Pose ta question.")
        GLib.idle_add(self.msg_tv.grab_focus)
        self.connect("close-request", self._on_close)
        # Drop target sur la fenêtre entière
        win_drop = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
        win_drop.connect("drop", self._on_drop)
        win_drop.connect("enter", lambda *_: Gdk.DragAction.COPY)
        self.add_controller(win_drop)

    def _on_close(self, *_):
        if self.history:
            save_session(self.session_name, self.history)
        os._exit(0)

    # ── HeaderBar ────────────────────────────────────────────
    # ── Construction de la barre de titre (HeaderBar) ────────────────────────
    def _build_headerbar(self):
        hb = Gtk.HeaderBar()
        hb.set_show_title_buttons(False)  # cacher les boutons GNOME
        self.set_titlebar(hb)

        # Gauche : sidebar toggle
        self.toggle_btn = Gtk.Button(label="☰")
        self.toggle_btn.add_css_class("toggle"); self.toggle_btn.set_focusable(False)
        self.toggle_btn.set_tooltip_text("Historique  [Ctrl+H]")
        self.toggle_btn.connect("clicked", self._toggle_sidebar)
        hb.pack_start(self.toggle_btn)

        # Titre enrichi au centre
        tb = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        tb.set_valign(Gtk.Align.CENTER)
        tv = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        t1 = Gtk.Label(label="Nseek"); t1.add_css_class("app-title")
        t2 = Gtk.Label(label="CLIENT IA NATIF GTK4"); t2.add_css_class("app-sub")
        tv.append(t1); tv.append(t2)
        tb.append(tv)
        hb.set_title_widget(tb)

        # Droite headerbar : uniquement Web + Crédits
        sep = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        sep.set_margin_top(8); sep.set_margin_bottom(8); sep.set_opacity(0.3)

        btn_credits = Gtk.Button(label="💳 Crédits")
        btn_credits.add_css_class("web-btn"); btn_credits.set_focusable(False)
        btn_credits.set_tooltip_text("Recharger les crédits DeepSeek")
        btn_credits.connect("clicked", lambda *_: Gio.AppInfo.launch_default_for_uri("https://platform.deepseek.com/top-up", None))

        btn_web = Gtk.Button(label="🌐 Web")
        btn_web.add_css_class("web-btn"); btn_web.set_focusable(False)
        btn_web.set_tooltip_text("Ouvrir DeepSeek Web  [Ctrl+B]")
        btn_web.connect("clicked", self._open_web)

        # ✕ en premier = tout à droite
        quit_btn = Gtk.Button(label="✕")
        quit_btn.add_css_class("quit-btn"); quit_btn.set_focusable(False)
        quit_btn.set_tooltip_text("Quitter Nseek  [Ctrl+Q]")
        quit_btn.connect("clicked", self._quit)
        hb.pack_end(quit_btn)

        for w in [btn_credits, btn_web]:
            hb.pack_end(w)

    # ── Toolbar verticale droite (boutons d'action) ────────────────────────────
    def _build_toolbar(self, root):
        """Barre d'icônes verticale à droite de la zone de chat."""
        pass  # injectée dans _build_main via overlay

    # ── Sidebar ───────────────────────────────────────────────
    # ── Construction du panneau historique gauche (sidebar) ───────────────────
    def _build_sidebar(self):
        self.sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.sidebar.add_css_class("sidebar")
        self.sidebar.set_size_request(210, -1)
        title = Gtk.Label(label="CONVERSATIONS"); title.add_css_class("sidebar-title"); title.set_xalign(0.5)
        self.sidebar.append(title)
        nb = Gtk.Button(label="＋  Nouvelle conversation")
        nb.add_css_class("new-sess"); nb.set_focusable(False)
        nb.connect("clicked", self._new_session)
        self.sidebar.append(nb)
        sw = Gtk.ScrolledWindow(); sw.set_vexpand(True)
        sw.add_css_class("sidebar")
        self.sess_list = Gtk.ListBox()
        self.sess_list.add_css_class("sidebar")
        self.sess_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.sess_list.connect("row-activated", self._load_sess_row)
        sw.set_child(self.sess_list)
        self.sidebar.append(sw)
        self.paned.set_start_child(self.sidebar)
        self.paned.set_position(300)
        self._refresh_sidebar()

    def _refresh_sidebar(self):
        while self.sess_list.get_row_at_index(0): self.sess_list.remove(self.sess_list.get_row_at_index(0))
        for name in list_sessions():
            try:
                data = load_session(name + '.json')
                title = data.get('title') or make_title(data.get('messages', []))
            except Exception:
                title = name.replace('_', ' ')
            self._add_sess_row(name, title)

    def _add_sess_row(self, name, title=None):
        row = Gtk.ListBoxRow(); row.session_name = name
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        box.add_css_class("sess-row")
        vb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL); vb.set_hexpand(True)
        # Titre en gras
        display = title if title else name.replace('_',' ')
        nl = Gtk.Label(label=display[:38]); nl.set_xalign(0); nl.add_css_class("sess-name")
        nl.set_ellipsize(Pango.EllipsizeMode.END)
        # Date en petit
        date_str = name[:16].replace('_',' ') if len(name) >= 16 else name
        dl = Gtk.Label(label=date_str); dl.set_xalign(0)
        dl.add_css_class("lbl"); dl.set_margin_top(1)
        vb.append(nl); vb.append(dl); box.append(vb)
        db = Gtk.Button(label="🗑"); db.add_css_class("del-btn"); db.set_focusable(False)
        db.connect("clicked", self._del_session, name); box.append(db)
        row.set_child(box); self.sess_list.append(row)

    # ── Affiche/masque le panneau historique ──────────────────────────────────
    def _toggle_sidebar(self, *_):
        self.sidebar.set_visible(not self.sidebar.get_visible())

    def _del_session(self, btn, name):
        delete_session(name)
        if name == self.session_name:
            self.history = []; self.session_name = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M")
            self.buf.set_text(""); self._msg("info", "Session supprimée.")
        self._refresh_sidebar()

    def _load_sess_row(self, lb, row):
        data = load_session(row.session_name + '.json')
        self.history = data.get('messages', [])
        self.session_name = row.session_name
        self.buf.set_text("")
        for m in self.history:
            c = m['content']
            self._msg("you" if m['role']=='user' else "ai",
                      c if isinstance(c,str) else "(multimédia)")
        self.status.set_text(f"Session : {self.session_name}")
        GLib.idle_add(self.msg_tv.grab_focus)

    # ── Démarre une nouvelle conversation vide ────────────────────────────────
    def _new_session(self, *_):
        try:
            if self.history:
                save_session(self.session_name, self.history)
                self._refresh_sidebar()
            self.history = []
            self.session_name = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M")
            self.buf.set_text("")
            self._msg("info", "Nouvelle conversation.")
            self.status.set_text(f"Session : {self.session_name}")
            GLib.idle_add(self.msg_tv.grab_focus)
        except Exception as e:
            import traceback; traceback.print_exc()
            print(f"ERREUR _new_session: {e}")

    # ── Zone principale ───────────────────────────────────────
    # ── Construction de la zone principale (config + chat + input) ────────────
    def _build_main(self, root):
        # Conteneur horizontal : zone principale + toolbar verticale
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        hbox.set_hexpand(True); hbox.set_vexpand(True)

        main = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        main.set_hexpand(True)

        # Config
        cfg = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        cfg.add_css_class("cfg")

        # Clé API — label masqué + bouton édition (Wayland workaround)
        row_key = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        l_key = Gtk.Label(label="Clé API :"); l_key.add_css_class("lbl"); l_key.set_size_request(65,-1)
        self.key_buf = Gtk.TextBuffer()
        self.key_lbl = Gtk.Label(label="— non définie —")
        self.key_lbl.set_hexpand(True); self.key_lbl.set_xalign(0)
        self.key_lbl.set_ellipsize(3); self.key_lbl.add_css_class("lbl")
        self.key_lbl.set_tooltip_text("Votre clé API DeepSeek (sk-...)")
        self.key_buf.connect("changed", lambda b: self._update_key_lbl())
        btn_edit_key = Gtk.Button(label="✏️")
        btn_edit_key.add_css_class("tool"); btn_edit_key.set_focusable(False)
        btn_edit_key.set_tooltip_text("Saisir / modifier la clé API")
        btn_edit_key.connect("clicked", self._edit_api_key)
        row_key.append(l_key); row_key.append(self.key_lbl); row_key.append(btn_edit_key)
        cfg.append(row_key)

        # Persona — label + bouton édition (Wayland workaround)
        row_sys = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        l_sys = Gtk.Label(label="Persona :"); l_sys.add_css_class("lbl"); l_sys.set_size_request(65,-1)
        self.sys_buf = Gtk.TextBuffer()
        self.sys_buf.set_text("Tu es un assistant serviable et précis.")
        self.sys_lbl = Gtk.Label()
        self.sys_lbl.set_hexpand(True); self.sys_lbl.set_xalign(0)
        self.sys_lbl.set_ellipsize(3)  # PANGO_ELLIPSIZE_END
        self.sys_lbl.add_css_class("lbl")
        self.sys_lbl.set_tooltip_text("Décris le rôle souhaité — ex: «Tu es un expert Linux Fedora» · «Tu es un professeur patient» · «Tu es un développeur Python senior»")
        self._update_sys_lbl()
        self.sys_buf.connect("changed", lambda b: self._update_sys_lbl())
        btn_edit_sys = Gtk.Button(label="✏️")
        btn_edit_sys.add_css_class("tool"); btn_edit_sys.set_focusable(False)
        btn_edit_sys.set_tooltip_text("Modifier le persona")
        btn_edit_sys.connect("clicked", self._edit_persona)
        row_sys.append(l_sys); row_sys.append(self.sys_lbl); row_sys.append(btn_edit_sys)
        cfg.append(row_sys)

        r2 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        l2 = Gtk.Label(label="Modèle :"); l2.add_css_class("lbl"); l2.set_size_request(65,-1)
        self.model_dd = Gtk.DropDown.new_from_strings(["deepseek-v4-pro","deepseek-v4-flash","deepseek-chat"])
        self.model_dd.set_selected(0); self.model_dd.set_focusable(False)

        # Sélecteur de langue
        self.LANGUAGES = [
            ("🇫🇷 Français",    "Réponds toujours en français, y compris dans ton raisonnement interne."),
            ("🇬🇧 English",     "Always respond in English, including your internal reasoning."),
            ("🇪🇸 Español",     "Responde siempre en español, incluyendo tu razonamiento interno."),
            ("🇨🇳 中文",        "请始终用中文回答，包括内部推理过程。"),
            ("🇸🇦 العربية",     "أجب دائماً باللغة العربية، بما في ذلك تفكيرك الداخلي."),
            ("🇧🇷 Português",   "Responda sempre em português, incluindo seu raciocínio interno."),
            ("🇷🇺 Русский",     "Всегда отвечай на русском языке, включая внутренние рассуждения."),
            ("🇩🇪 Deutsch",     "Antworte immer auf Deutsch, einschließlich deiner internen Überlegungen."),
            ("🇯🇵 日本語",      "常に日本語で答えてください。内部推論も含めて。"),
            ("🇮🇳 हिन्दी",      "हमेशा हिंदी में जवाब दें, आंतरिक तर्क सहित।"),
        ]
        lang_names = [l[0] for l in self.LANGUAGES]
        self.lang_dd = Gtk.DropDown.new_from_strings(lang_names)
        self.lang_dd.set_selected(0); self.lang_dd.set_focusable(False)
        self.lang_dd.set_tooltip_text("Langue de réponse")

        self.think_cb = Gtk.CheckButton(label="🧠 Thinking"); self.think_cb.set_active(True); self.think_cb.set_focusable(False)
        self.stream_cb = Gtk.CheckButton(label="⚡ Streaming"); self.stream_cb.set_active(True); self.stream_cb.set_focusable(False)
        r2.append(l2); r2.append(self.model_dd); r2.append(self.lang_dd)
        r2.append(self.think_cb); r2.append(self.stream_cb)
        cfg.append(r2)
        main.append(cfg)

        # Barre de recherche avec Revealer
        self.search_rev = Gtk.Revealer()
        self.search_rev.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
        self.search_rev.set_transition_duration(150)
        self.search_rev.set_reveal_child(False)

        self.search_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.search_bar.add_css_class("search-bar")
        self.search_buf = Gtk.TextBuffer()
        self.search_tv  = Gtk.TextView(buffer=self.search_buf)
        self.search_tv.set_wrap_mode(Gtk.WrapMode.NONE); self.search_tv.set_accepts_tab(False)
        self.search_tv.set_size_request(-1, 28); self.search_tv.set_hexpand(True)
        self.search_tv.set_top_margin(4); self.search_tv.set_bottom_margin(4)
        self.search_tv.set_left_margin(6)
        skc = Gtk.EventControllerKey(); skc.connect("key-pressed", self._on_search_key)
        self.search_tv.add_controller(skc)
        sw = Gtk.Box(); sw.add_css_class("input-tv"); sw.set_hexpand(True); sw.append(self.search_tv)
        lbl_search = Gtk.Label(label="Rechercher :"); lbl_search.add_css_class("lbl")
        self.search_bar.append(lbl_search); self.search_bar.append(sw)
        sb = Gtk.Button(label="✕ Fermer"); sb.add_css_class("tool"); sb.set_focusable(False)
        sb.connect("clicked", self._toggle_search); self.search_bar.append(sb)
        self.search_rev.set_child(self.search_bar)
        main.append(self.search_rev)

        # Chat TextView
        self.buf  = Gtk.TextBuffer()
        self.view = Gtk.TextView(buffer=self.buf)
        self.view.set_editable(False)
        self.view.set_focusable(True)   # focusable pour permettre la sélection
        self.view.set_cursor_visible(True)
        self.view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        # Rediriger la frappe vers msg_tv quand le chat a le focus
        chat_kc = Gtk.EventControllerKey()
        chat_kc.connect("key-pressed", self._on_chat_key)
        self.view.add_controller(chat_kc)
        self.view.set_left_margin(14); self.view.set_right_margin(14)
        self.view.set_top_margin(8); self.view.set_pixels_below_lines(6)
        self._apply_font()
        tags = TAGS_DARK
        for name, kw in tags.items(): self.buf.create_tag(name, **kw)
        csw = Gtk.ScrolledWindow(); csw.set_child(self.view); csw.set_vexpand(True)
        csw.set_focusable(False); csw.add_css_class("chat")
        csw.set_margin_start(10); csw.set_margin_end(10); csw.set_margin_bottom(4)

        # Filigrane — logo overlay à faible opacité
        overlay = Gtk.Overlay()
        overlay.set_child(csw)
        overlay.set_vexpand(True)
        try:
            from gi.repository import GdkPixbuf, Gdk as GdkL
            assets = os.path.dirname(os.path.abspath(__file__))
            if self.is_dark:
                logo_path = os.path.join(assets, "assets", "nseek-logo-ciel.png")
            else:
                logo_path = os.path.join(assets, "assets", "nseek-logo-marine.png")
            if not os.path.exists(logo_path):
                logo_path = os.path.join(assets, "assets", "nseek-logo.png")
            if os.path.exists(logo_path):
                pb = GdkPixbuf.Pixbuf.new_from_file(logo_path)
                texture = GdkL.Texture.new_for_pixbuf(pb)
                wm = Gtk.Picture.new_for_paintable(texture)
                wm.set_can_shrink(True)
                wm.set_hexpand(True); wm.set_vexpand(True)
                wm.set_halign(Gtk.Align.CENTER)
                wm.set_valign(Gtk.Align.CENTER)
                wm.set_opacity(0.38)
                wm.set_sensitive(False)
                self.wm_picture = wm  # référence pour changer au switch thème
                overlay.add_overlay(wm)
                overlay.set_measure_overlay(wm, False)
        except Exception as e:
            print(f"Filigrane : {e}")

        # Drag & drop sur la fenêtre principale (plus fiable sur Wayland)
        drop = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
        drop.connect("drop", self._on_drop)
        drop.connect("enter", lambda *_: Gdk.DragAction.COPY)
        csw.add_controller(drop)
        main.append(overlay)

        # Fichier attaché
        self.file_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.file_bar.set_margin_start(10); self.file_bar.set_margin_end(10)
        self.file_lbl = Gtk.Label(); self.file_lbl.add_css_class("lbl"); self.file_lbl.set_hexpand(True)
        rb = Gtk.Button(label="✕"); rb.add_css_class("tool"); rb.set_focusable(False)
        rb.connect("clicked", lambda *_: [setattr(self,'attached_file',None), self.file_bar.set_visible(False)])
        self.file_bar.append(self.file_lbl); self.file_bar.append(rb)
        self.file_bar.set_visible(False); main.append(self.file_bar)

        # Barre de saisie
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        bar.set_margin_start(10); bar.set_margin_end(10); bar.set_margin_bottom(6)
        fb = Gtk.Button(label="📎"); fb.add_css_class("tool"); fb.set_focusable(False)
        fb.set_tooltip_text("Joindre fichier/image"); fb.connect("clicked", self._pick_file)
        bar.append(fb)
        self.msg_buf = Gtk.TextBuffer()
        self.msg_tv  = Gtk.TextView(buffer=self.msg_buf)
        self.msg_tv.set_wrap_mode(Gtk.WrapMode.WORD_CHAR); self.msg_tv.set_accepts_tab(False)
        self.msg_tv.set_size_request(-1, 38); self.msg_tv.set_hexpand(True)
        self.msg_tv.set_top_margin(6); self.msg_tv.set_bottom_margin(6); self.msg_tv.set_left_margin(6)
        # Limiter la hauteur de saisie à 120px max avec scroll
        mw = Gtk.ScrolledWindow(); mw.add_css_class("input-tv"); mw.set_hexpand(True)
        mw.set_child(self.msg_tv)
        mw.set_max_content_height(120); mw.set_propagate_natural_height(True)
        mw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        kc = Gtk.EventControllerKey(); kc.connect("key-pressed", self._on_key); self.msg_tv.add_controller(kc)
        bar.append(mw)
        # 🗑 dans la barre efface UNIQUEMENT le texte saisi (pas la conversation)
        clr = Gtk.Button(label="🗑"); clr.add_css_class("tool"); clr.set_focusable(False)
        clr.set_tooltip_text("Effacer le texte saisi")
        clr.connect("clicked", lambda *_: self.msg_buf.set_text("") or self.msg_tv.grab_focus())
        bar.append(clr)
        self.send_btn = Gtk.Button(label="Envoyer ➤"); self.send_btn.add_css_class("send")
        self.send_btn.set_focusable(False); self.send_btn.connect("clicked", self._send)
        bar.append(self.send_btn)
        main.append(bar)

        # ── Toolbar verticale droite ──────────────────────────
        toolbar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        toolbar.add_css_class("vtoolbar")
        toolbar.set_margin_top(8); toolbar.set_margin_bottom(8)
        toolbar.set_margin_start(4); toolbar.set_margin_end(6)
        toolbar.set_valign(Gtk.Align.FILL)

        tool_items = [
            ("🔍", "Rechercher  [Ctrl+F]",          self._toggle_search),
            ("📋", "Copier dernière réponse",         self._copy_reply),
            ("💾", "Exporter conversation",           self._export),
            ("🖨️", "Imprimer la conversation",        self._print_conv),
            ("A+", "Police plus grande",              self._font_bigger),
            ("A−", "Police plus petite",              self._font_smaller),
            None,
            ("🔄", "Régénérer la dernière réponse", self._regenerate),
            ("🗑",  "Effacer  [Ctrl+L]",              self._clear),
            None,
            ("❓", "Aide contextuelle",               self._show_help),
            ("Doc", "Manuel utilisateur",             self._open_manual),
            None,
            ("✏️", "Éditeur de code  [Ctrl+Shift+E]", self._open_editor_window),
            None,
            ("☀️", "Thème clair/sombre  [Ctrl+T]",   self._switch_theme),
            ("✕",  "Quitter  [Ctrl+Q]",              self._quit),
        ]

        for item in tool_items:
            if item is None:
                sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
                sep.set_margin_top(4); sep.set_margin_bottom(4); sep.set_opacity(0.2)
                toolbar.append(sep)
            else:
                lbl, tip, cb = item
                btn = Gtk.Button(label=lbl)
                # Thème et ✕ sont poussés en bas via un spacer
                if lbl == "☀️":
                    spacer = Gtk.Box(); spacer.set_vexpand(True)
                    toolbar.append(spacer)
                    self.theme_btn = btn
                btn.add_css_class("vtool")
                if lbl == "✕": btn.remove_css_class("vtool"); btn.add_css_class("vtool-quit")
                btn.set_focusable(False); btn.set_tooltip_text(tip)
                btn.connect("clicked", cb)
                toolbar.append(btn)

        hbox.append(main)
        hbox.append(toolbar)

        # Notebook avec onglet Chat + onglet Terminal
        self.paned.set_end_child(hbox)

    # ── Éditeur de code indépendant (GtkSourceView + exécution) ──────────────
    def _open_editor_window(self, *_):
        """Ouvre l'éditeur dans une fenêtre indépendante."""
        if hasattr(self, '_editor_win') and self._editor_win and self._editor_win.is_visible():
            self._editor_win.present(); return

        import gi; gi.require_version('GtkSource', '5')
        from gi.repository import GtkSource

        win = Gtk.Window(title="Nseek — Éditeur de code")
        win.set_default_size(900, 700)
        win.maximize()
        self._editor_win = win

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        # ── Barre d'outils ────────────────────────────────────
        tbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        tbar.add_css_class("code-header")
        tbar.set_margin_start(6); tbar.set_margin_end(6)
        tbar.set_margin_top(4); tbar.set_margin_bottom(4)

        title_lbl = Gtk.Label(label=" ✏️ ÉDITEUR "); title_lbl.add_css_class("code-lang")
        tbar.append(title_lbl)

        langs = ["python3","sh","javascript","c","cpp","rust","go","sql","html","css","json","yaml"]
        self.editor_lang_model = Gtk.StringList.new(langs)
        self.editor_lang_dd = Gtk.DropDown(model=self.editor_lang_model)
        self.editor_lang_dd.set_focusable(False)
        self.editor_lang_dd.set_tooltip_text("Langage")
        self.editor_lang_dd.connect("notify::selected", self._on_editor_lang_changed)
        tbar.append(self.editor_lang_dd)

        spacer = Gtk.Box(); spacer.set_hexpand(True); tbar.append(spacer)

        for lbl, tip, cb in [
            ("🗑 Vider",    "Vider l'éditeur",              lambda *_: self.editor_buf.set_text("")),
            ("📋 Coller",   "Coller le dernier code",        self._paste_to_editor),
            ("↩",          "Annuler  [Ctrl+Z]",             lambda *_: self.editor_buf.undo()),
            ("↪",          "Rétablir  [Ctrl+Y]",            lambda *_: self.editor_buf.redo()),
            ("💾 Sauver",   "Sauvegarder",                   self._save_editor_code),
            ("▶ Exécuter", "Exécuter le code",              self._run_editor_code),
        ]:
            b = Gtk.Button(label=lbl); b.set_focusable(False)
            b.add_css_class("send" if "Exécuter" in lbl else "tool")
            b.set_tooltip_text(tip); b.connect("clicked", cb)
            if "Exécuter" in lbl: self.run_btn = b
            tbar.append(b)

        # Bouton retour Nseek
        btn_nseek = Gtk.Button(label="🐋 Nseek")
        btn_nseek.add_css_class("web-btn"); btn_nseek.set_focusable(False)
        btn_nseek.set_tooltip_text("Basculer vers Nseek")
        btn_nseek.connect("clicked", lambda *_: self.present())
        tbar.append(btn_nseek)

        btn_close = Gtk.Button(label="✕")
        btn_close.add_css_class("quit-btn"); btn_close.set_focusable(False)
        btn_close.set_tooltip_text("Fermer l'éditeur")
        btn_close.connect("clicked", lambda *_: win.hide())
        tbar.append(btn_close)

        box.append(tbar)

        # ── GtkSourceView ─────────────────────────────────────
        self.editor_buf = GtkSource.Buffer()
        lm = GtkSource.LanguageManager.get_default()
        lang = lm.get_language("python3")
        if lang: self.editor_buf.set_language(lang)
        self.editor_buf.set_highlight_syntax(True)
        sm = GtkSource.StyleSchemeManager.get_default()
        scheme = sm.get_scheme("oblivion" if self.is_dark else "Adwaita")
        if scheme: self.editor_buf.set_style_scheme(scheme)

        self.editor_view = GtkSource.View(buffer=self.editor_buf)
        self.editor_view.set_editable(True)
        self.editor_view.set_show_line_numbers(True)
        self.editor_view.set_highlight_current_line(True)
        self.editor_view.set_monospace(True)
        self.editor_view.set_auto_indent(True)
        self.editor_view.set_tab_width(4)
        self.editor_view.set_vexpand(True); self.editor_view.set_hexpand(True)
        self.editor_view.set_top_margin(6); self.editor_view.set_left_margin(8)

        sw = Gtk.ScrolledWindow(); sw.set_child(self.editor_view); sw.set_vexpand(True)
        box.append(sw)

        # ── Zone sortie ───────────────────────────────────────
        out_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        out_bar.add_css_class("code-header")
        out_bar.set_margin_start(6); out_bar.set_margin_end(6)
        out_bar.set_margin_top(2); out_bar.set_margin_bottom(2)
        Gtk.Label(label=" 📤 SORTIE ")
        out_lbl = Gtk.Label(label=" 📤 SORTIE "); out_lbl.add_css_class("code-lang")
        out_bar.append(out_lbl)
        out_sp = Gtk.Box(); out_sp.set_hexpand(True); out_bar.append(out_sp)

        self.send_err_btn = Gtk.Button(label="🤖 Demander correction à Nseek")
        self.send_err_btn.add_css_class("code-copy-btn"); self.send_err_btn.set_focusable(False)
        self.send_err_btn.set_visible(False)
        self.send_err_btn.connect("clicked", self._send_error_to_deepseek)
        out_bar.append(self.send_err_btn)

        btn_clr = Gtk.Button(label="🗑"); btn_clr.add_css_class("tool"); btn_clr.set_focusable(False)
        btn_clr.connect("clicked", self._clear_terminal)
        out_bar.append(btn_clr)
        box.append(out_bar)

        # Terminal VTE pour l'exécution interactive (supporte input())
        try:
            gi.require_version('Vte', '3.91')
            from gi.repository import Vte
            self.term = Vte.Terminal()
            self.term.set_size_request(-1, 200)
            self.term.set_scrollback_lines(1000)
            self.term.set_font_scale(0.95)
            self._has_vte = True
            # Détecter la fin d'exécution et le code de retour
            self.term.connect("child-exited", self._on_child_exited)
            sw_out = Gtk.ScrolledWindow(); sw_out.set_child(self.term)
            sw_out.set_size_request(-1, 200); sw_out.set_vexpand(True)
        except Exception:
            # Fallback : TextView classique
            self._has_vte = False
            self.output_buf = Gtk.TextBuffer()
            self.output_view = Gtk.TextView(buffer=self.output_buf)
            self.output_view.set_editable(False); self.output_view.set_monospace(True)
            self.output_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
            sw_out = Gtk.ScrolledWindow(); sw_out.set_child(self.output_view)
            sw_out.set_size_request(-1, 280); sw_out.set_vexpand(True)
        box.append(sw_out)

        win.set_child(box)
        # Empêcher la fermeture accidentelle
        win.connect("close-request", lambda w: False)
        win.present()
        self.editor_view.grab_focus()

    def _on_editor_lang_changed(self, dd, _):
        import gi; gi.require_version('GtkSource', '5')
        from gi.repository import GtkSource
        lang_id = self.editor_lang_model.get_string(dd.get_selected())
        lm = GtkSource.LanguageManager.get_default()
        lang = lm.get_language(lang_id)
        if lang: self.editor_buf.set_language(lang)

    def _paste_to_editor(self, *_):
        if hasattr(self, '_last_code') and self._last_code:
            self.editor_buf.set_text(self._last_code)
            if hasattr(self, '_editor_win') and self._editor_win:
                self._editor_win.present()
                self.editor_view.grab_focus()
            self.status.set_text("✅ Code collé dans l'éditeur")
        else:
            self.status.set_text("⚠️ Aucun code copié depuis le chat")

    def _save_editor_code(self, *_):
        if not hasattr(self, 'editor_buf'): return
        try:
            code = self.editor_buf.get_text(
                self.editor_buf.get_start_iter(), self.editor_buf.get_end_iter(), False)
            if not code.strip():
                self._out("⚠️ Éditeur vide !"); return
            lang_id = self.editor_lang_model.get_string(self.editor_lang_dd.get_selected())
            ext = {"python3":"py","sh":"sh","javascript":"js","c":"c","cpp":"cpp",
                   "rust":"rs","go":"go","sql":"sql"}.get(lang_id, "txt")
            fname = os.path.expanduser(
                f"~/Documents/nseek_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.{ext}")
            with open(fname, 'w') as f: f.write(code)
            self._out(f"✅ Sauvegardé : {fname}")
            self.status.set_text(f"✅ Sauvegardé : {fname}")
        except Exception as e:
            self._out(f"❌ Erreur sauvegarde : {e}")

    def _out(self, msg):
        """Affiche un message dans le terminal VTE ou le buffer de sortie."""
        if getattr(self, '_has_vte', False):
            self.status.set_text(msg)
        else:
            if hasattr(self, 'output_buf'):
                self.output_buf.set_text(msg)

    def _clear_terminal(self, *_):
        if getattr(self, '_has_vte', False):
            self.term.reset(True, True)
        else:
            self.output_buf.set_text("")

    def _run_editor_code(self, *_):
        import tempfile
        if not hasattr(self, 'editor_buf'): return
        code = self.editor_buf.get_text(
            self.editor_buf.get_start_iter(), self.editor_buf.get_end_iter(), False)
        if not code.strip():
            self._out("⚠️ Éditeur vide !")
            return
        lang_id = self.editor_lang_model.get_string(self.editor_lang_dd.get_selected())
        ext = {"python3":"py","sh":"sh","javascript":"js","go":"go"}.get(lang_id, "txt")
        runners = {"python3":"python3","sh":"bash","javascript":"node","go":"go run"}
        runner = runners.get(lang_id)
        if not runner:
            self._out(f"⚠️ Non supporté : {lang_id}")
            return

        # Sauver dans un fichier temp
        with tempfile.NamedTemporaryFile(suffix=f".{ext}", mode='w', delete=False) as f:
            f.write(code); tmp = f.name

        self.run_btn.set_sensitive(False); self.run_btn.set_label("⏳...")
        self.send_err_btn.set_visible(False)

        if getattr(self, '_has_vte', False):
            # VTE : exécution interactive complète (supporte input())
            gi.require_version('Vte', '3.91')
            from gi.repository import Vte
            import tempfile as _tf
            code_file = _tf.mktemp(suffix='.exitcode')
            cmd = (f"{runner} {tmp}; _code=$?; "
                   f"echo ''; echo '--- Terminé (code: '$_code') ---'; "
                   f"rm -f {tmp}; echo $_code > {code_file}")
            self.term.reset(True, True)
            self.term.spawn_async(
                Vte.PtyFlags.DEFAULT, None,
                ['/bin/bash', '-c', cmd],
                None, GLib.SpawnFlags(0),
                None, None, -1, None, self._on_vte_done, None
            )
            # Poller le fichier de code de sortie toutes les 500ms
            def _poll(cf=code_file):
                if os.path.exists(cf):
                    try:
                        with open(cf) as f: exit_code = int(f.read().strip())
                    except: exit_code = 0
                    os.unlink(cf)
                    self.run_btn.set_sensitive(True)
                    self.run_btn.set_label("▶ Exécuter")
                    # Toujours afficher le bouton correction après exécution
                    self.send_err_btn.set_visible(True)
                    return False  # Arrêter le timer
                return True  # Continuer à surveiller
            GLib.timeout_add(500, _poll)
        else:
            # Fallback subprocess
            import subprocess, threading
            def run_t():
                try:
                    r = subprocess.run(runner.split()+[tmp], capture_output=True, text=True, timeout=30)
                    os.unlink(tmp)
                    GLib.idle_add(self._show_output, r.stdout, r.stderr, r.returncode)
                except subprocess.TimeoutExpired:
                    GLib.idle_add(self._show_output, "", "⏱️ Timeout (30s)", 1)
                except Exception as e:
                    GLib.idle_add(self._show_output, "", str(e), 1)
            threading.Thread(target=run_t, daemon=True).start()

    def _on_vte_done(self, terminal, pid, error, userdata):
        """Appelé quand VTE a spawné le process."""
        if error:
            GLib.idle_add(self._reset_run_btn)

    def _reset_run_btn(self):
        self.run_btn.set_sensitive(True)
        self.run_btn.set_label("▶ Exécuter")
        return False

    def _on_child_exited(self, terminal, status):
        """Appelé quand le process VTE se termine — détecte les erreurs."""
        import os as _os
        exit_code = _os.waitstatus_to_exitcode(status) if hasattr(_os, 'waitstatus_to_exitcode') else (status >> 8)
        def _update():
            self.run_btn.set_sensitive(True)
            self.run_btn.set_label("▶ Exécuter")
            self.send_err_btn.set_visible(exit_code != 0)
            self.term.grab_focus()
            return False
        GLib.idle_add(_update)

    def _show_output(self, stdout, stderr, rc):
        self.run_btn.set_sensitive(True); self.run_btn.set_label("▶ Exécuter")
        out = (f"✅ Succès\n\n{stdout}" if rc==0 else f"❌ Échec (code {rc})\n\n{stdout}")
        if stderr: out += f"\n⚠️ Erreurs :\n{stderr}"
        self._out(out.strip())
        if rc != 0:
            self._last_error = stderr or stdout
            self.send_err_btn.set_visible(True)

    def _send_error_to_deepseek(self, *_):
        """Envoie le code + l'erreur à DeepSeek — cache l'éditeur pour éviter le tiling GNOME."""
        code = self.editor_buf.get_text(
            self.editor_buf.get_start_iter(), self.editor_buf.get_end_iter(), False)
        lang_id = self.editor_lang_model.get_string(self.editor_lang_dd.get_selected())
        # Récupérer le texte du terminal VTE ou le dernier stderr connu
        error = ""
        if getattr(self, '_has_vte', False):
            try:
                error = self.term.get_text_format(1, None, False)[0]  # Vte.Format.TEXT = 1
            except Exception:
                error = getattr(self, '_last_error', 'Erreur d\'exécution (voir terminal)')
        else:
            error = getattr(self, '_last_error', '')
        msg = f"Ce code {lang_id} génère une erreur. Peux-tu le corriger ?\n\n```{lang_id}\n{code}\n```\n\nErreur :\n```\n{error.strip()[-2000:]}\n```"
        self.msg_buf.set_text(msg)
        if hasattr(self, '_editor_win') and self._editor_win:
            self._editor_win.hide()
        GLib.timeout_add(300, self._send)

    def _open_terminal_window(self):
        """Ouvre le terminal dans une fenêtre séparée (focus Wayland OK)."""
        import gi; gi.require_version('Vte', '3.91')
        from gi.repository import Vte

        if self._term_window and self._term_window.is_visible():
            self._term_window.present(); return

        win = Gtk.Window(title="Nseek — Terminal")
        win.set_default_size(800, 500)
        win.set_transient_for(self)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        # Barre d'outils
        tbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        tbar.add_css_class("code-header")
        tbar.set_margin_start(6); tbar.set_margin_end(6)
        tbar.set_margin_top(4); tbar.set_margin_bottom(4)
        lbl = Gtk.Label(label=" ⚡ TERMINAL BASH "); lbl.add_css_class("code-lang")
        tbar.append(lbl)
        spacer = Gtk.Box(); spacer.set_hexpand(True); tbar.append(spacer)
        btn_paste = Gtk.Button(label="📋 Coller le code")
        btn_paste.add_css_class("code-copy-btn"); btn_paste.set_focusable(False)
        btn_paste.connect("clicked", self._paste_to_terminal)
        tbar.append(btn_paste)
        box.append(tbar)

        # Terminal VTE
        self.terminal = Vte.Terminal()
        self.terminal.set_vexpand(True); self.terminal.set_hexpand(True)
        self.terminal.set_scrollback_lines(5000)
        from gi.repository import Gdk as GdkV
        bg = GdkV.RGBA(); bg.red=0.024; bg.green=0.051; bg.blue=0.102; bg.alpha=1.0
        fg = GdkV.RGBA(); fg.red=0.784; fg.green=0.867; fg.blue=0.941; fg.alpha=1.0
        self.terminal.set_colors(fg, bg, None)
        try:
            self.terminal.spawn_sync(
                Vte.PtyFlags.DEFAULT, os.path.expanduser("~"),
                ["/bin/bash", "--login"], None,
                GLib.SpawnFlags.DEFAULT, None, None, None)
        except Exception as e:
            print(f"Terminal: {e}")

        box.append(self.terminal)
        win.set_child(box)
        win.present()
        self._term_window = win
        self.terminal.grab_focus()

    def _focus_terminal(self):
        if self._term_window:
            self._term_window.present()
            self.terminal.grab_focus()
        return False

    def _build_terminal(self):
        """Construit l'onglet terminal VTE."""
        import gi; gi.require_version('Vte', '3.91')
        from gi.repository import Vte, GLib as GLib2

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.set_vexpand(True); box.set_hexpand(True)

        # Barre d'outils terminal
        tbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        tbar.add_css_class("code-header")
        tbar.set_margin_start(6); tbar.set_margin_end(6)
        tbar.set_margin_top(4); tbar.set_margin_bottom(4)

        lbl = Gtk.Label(label=" ⚡ TERMINAL BASH ")
        lbl.add_css_class("code-lang"); tbar.append(lbl)

        spacer = Gtk.Box(); spacer.set_hexpand(True); tbar.append(spacer)

        # Bouton coller le dernier code copié
        self.paste_code_btn = Gtk.Button(label="📋 Coller le code")
        self.paste_code_btn.add_css_class("code-copy-btn")
        self.paste_code_btn.set_focusable(False)
        self.paste_code_btn.set_tooltip_text("Colle le dernier code copié dans le terminal")
        self.paste_code_btn.connect("clicked", self._paste_to_terminal)
        tbar.append(self.paste_code_btn)

        # Bouton reset terminal
        btn_reset = Gtk.Button(label="🔄 Reset")
        btn_reset.add_css_class("tool"); btn_reset.set_focusable(False)
        btn_reset.set_tooltip_text("Relancer le terminal")
        btn_reset.connect("clicked", lambda *_: self._reset_terminal())
        tbar.append(btn_reset)

        box.append(tbar)

        # Terminal VTE — scroll natif VTE, pas de ScrolledWindow
        self.terminal = Vte.Terminal()
        self.terminal.set_vexpand(True); self.terminal.set_hexpand(True)
        self.terminal.set_scroll_on_output(True)
        self.terminal.set_scrollback_lines(5000)

        # Couleurs marine
        from gi.repository import Gdk as GdkV
        bg = GdkV.RGBA(); bg.red=0.024; bg.green=0.051; bg.blue=0.102; bg.alpha=1.0
        fg = GdkV.RGBA(); fg.red=0.784; fg.green=0.867; fg.blue=0.941; fg.alpha=1.0
        self.terminal.set_colors(fg, bg, None)

        # Lancer bash avec spawn_sync pour détecter les erreurs
        try:
            self.terminal.spawn_sync(
                Vte.PtyFlags.DEFAULT,
                os.path.expanduser("~"),
                ["/bin/bash", "--login"],
                None,
                GLib.SpawnFlags.DEFAULT,
                None, None, None
            )
            print("Terminal bash démarré OK")
        except Exception as e:
            print(f"Erreur spawn terminal: {e}")
            # Fallback : sh
            try:
                self.terminal.spawn_sync(
                    Vte.PtyFlags.DEFAULT,
                    os.path.expanduser("~"),
                    ["/bin/sh"],
                    None,
                    GLib.SpawnFlags.DO_NOT_REAP_CHILD,
                    None, None, None
                )
                print("Terminal sh démarré OK (fallback)")
            except Exception as e2:
                print(f"Erreur spawn sh: {e2}")

        box.append(self.terminal)
        return box

    def _paste_to_terminal(self, *_):
        if hasattr(self, '_last_code') and self._last_code:
            if not (self._term_window and self._term_window.is_visible()):
                self._open_terminal_window()
            GLib.timeout_add(300, lambda: (
                self.terminal.feed_child((self._last_code + "\n").encode()),
                self.status.set_text("✅ Code collé dans le terminal")
            ) and False)
        else:
            self.status.set_text("⚠️ Aucun code copié — utilise d'abord 📋 Copier")

    def _reset_terminal(self):
        """Relance le terminal."""
        self.terminal.spawn_async(
            __import__('gi.repository', fromlist=['Vte']).Vte.PtyFlags.DEFAULT,
            os.path.expanduser("~"), ["/bin/bash"], None,
            __import__('gi').repository.GLib.SpawnFlags.DO_NOT_REAP_CHILD,
            None, None, -1, None, None
        )

    # ── Barre de statut (bas de fenêtre) : status + copyright + stats tokens ──
    def _build_statusbar(self, root):
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        bar.set_margin_start(12); bar.set_margin_end(12)
        bar.set_margin_top(4); bar.set_margin_bottom(6)

        self.status = Gtk.Label(label="Prêt.")
        self.status.set_xalign(0); self.status.set_hexpand(True)
        self.status.add_css_class("status")
        bar.append(self.status)

        # Copyright
        copy_box2 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        copy_box2.set_valign(Gtk.Align.CENTER)
        try:
            from gi.repository import GdkPixbuf, Gdk as _GdkI2
            _icon_path2 = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets', 'nseek-icon-ciel.png')
            if os.path.exists(_icon_path2):
                _pb2 = GdkPixbuf.Pixbuf.new_from_file_at_scale(_icon_path2, 60, 60, True)
                _tex2 = _GdkI2.Texture.new_for_pixbuf(_pb2)
                _img2 = Gtk.Picture.new_for_paintable(_tex2)
                _img2.set_size_request(60, 60)
                _img2.set_can_shrink(False)
                copy_box2.append(_img2)
        except Exception: pass
        copy_lbl2 = Gtk.Label()
        copy_lbl2.set_markup('<span font="10" font_weight="bold" foreground="#5ab4f0">© 2026 carafife — Nseek v1.0 — GPL v3</span>')
        copy_box2.append(copy_lbl2)
        bar.append(copy_box2)

        self.stats_lbl = Gtk.Label()
        self.stats_lbl.set_xalign(1)
        bar.append(self.stats_lbl)
        root.append(bar)
        self._refresh_stats(0, 0, 0.0)

    def _refresh_stats(self, in_tok, out_tok, cost):
        markup = (
            f'<span font="10" foreground="#57e389"><b>⬆</b> {self.session_in}</span>'
            f'<span font="10" foreground="#606060">  </span>'
            f'<span font="10" foreground="#78aeed"><b>⬇</b> {self.session_out}</span>'
            f'<span font="10" foreground="#606060">  tokens  │  </span>'
            f'<span font="10" foreground="#ffbe6f">💰 ${self.total_cost:.5f}</span>'
            f'<span font="10" foreground="#606060">  session</span>'
        )
        GLib.idle_add(self.stats_lbl.set_markup, markup)

    # ── Raccourcis clavier ────────────────────────────────────
    # ── Raccourcis clavier globaux ────────────────────────────────────────────
    def _setup_shortcuts(self):
        # Raccourcis clavier sur la zone chat uniquement (pas le terminal)
        kc = Gtk.EventControllerKey()
        kc.connect("key-pressed", self._on_window_key)
        # Attacher au msg_tv et à la fenêtre en BUBBLE (après les enfants)
        kc.set_propagation_phase(Gtk.PropagationPhase.BUBBLE)
        self.add_controller(kc)

    def _on_window_key(self, ctrl, kv, kc, st):
        # Ne pas intercepter si le terminal a le focus
        if hasattr(self, 'terminal') and self.terminal.has_focus():
            return False
        C = Gdk.ModifierType.CONTROL_MASK
        S = Gdk.ModifierType.SHIFT_MASK
        if not (st & C): return False
        if kv == Gdk.KEY_n: self._new_session();    return True
        if kv == Gdk.KEY_l: self._clear();          return True
        if kv == Gdk.KEY_e: self._export();         return True
        if kv == Gdk.KEY_f: self._toggle_search();  return True
        if kv == Gdk.KEY_t: self._switch_theme();   return True
        if kv == Gdk.KEY_h: self._toggle_sidebar(); return True
        if kv == Gdk.KEY_b: self._open_web();       return True
        if kv == Gdk.KEY_q: self._quit();           return True
        if (st & S) and kv == Gdk.KEY_C: self._copy_reply(); return True
        return False

    # ── Helpers clavier ───────────────────────────────────────
    def _on_chat_key(self, ctrl, kv, kc, st):
        C = Gdk.ModifierType.CONTROL_MASK
        if (st & C) and kv == Gdk.KEY_c: return False  # Ctrl+C = copier sélection
        if kv in (65505,65506,65507,65508,65513,65514): return False  # modifiers
        self.msg_tv.grab_focus()
        return False

    def _on_drop(self, drop_target, value, x, y):
        try:
            if isinstance(value, Gdk.FileList):
                files = list(value)
                if files: return self._attach_gfile(files[0])
            elif isinstance(value, str):
                # text/uri-list : une URI par ligne
                for line in value.strip().splitlines():
                    line = line.strip()
                    if line.startswith('file://'):
                        return self._attach_gfile(Gio.File.new_for_uri(line))
            elif hasattr(value, 'get_path'):
                return self._attach_gfile(value)
            self.status.set_text(f"Type non reconnu : {type(value).__name__}")
            return False
        except Exception as e:
            self.status.set_text(f"Erreur drop : {e}")
            print(f"DROP erreur: {e}")
            return False

    def _attach_gfile(self, gfile):
        path = gfile.get_path()
        if not path: return False
        name = os.path.basename(path)
        data = open(path, 'rb').read()
        mime = ('image/jpeg' if path.lower().endswith(('.jpg','.jpeg')) else
                'image/png'  if path.lower().endswith('.png') else
                'application/pdf' if path.lower().endswith('.pdf') else 'text/plain')
        self.attached_file = {'name':name,'mime':mime,
                              'b64':base64.b64encode(data).decode(),'path':path}
        self.file_lbl.set_text(f"📎 {name}")
        self.file_bar.set_visible(True)
        self.status.set_text(f"✅ Fichier prêt : {name}")
        return True

    # ── Fenêtre d'aide contextuelle ────────────────────────────────────────────
    def _open_manual(self, *_):
        """Ouvre le manuel utilisateur — le génère si absent."""
        base = os.path.dirname(os.path.abspath(__file__))
        docs_dir = os.path.join(base, "docs")
        os.makedirs(docs_dir, exist_ok=True)
        manuel = os.path.join(docs_dir, "manuel.html")
        theme = "dark" if self.is_dark else "light"
        # Générer le fichier s'il n'existe pas
        if not os.path.exists(manuel):
            self._generate_manual(manuel)
        uri = f"file://{manuel}?theme={theme}"
        try:
            Gio.AppInfo.launch_default_for_uri(uri, None)
        except Exception as e:
            self.status.set_text(f"Erreur ouverture manuel : {e}")

    def _generate_manual(self, path):
        """Génère le manuel HTML dans le fichier indiqué."""
        html = '''<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Nseek — Manuel Utilisateur</title>
<style>
:root{--bg:#060d1a;--bg2:#0a1628;--bg3:#0d1f3c;--bd:#152238;--ac:#2a5a9a;--ac2:#4a8fd4;--ci:#7aaad0;--tx:#e0eeff;--mu:#4a7aaa;--gr:#34d399;--ye:#fbbf24;--re:#f87171;--cb:#0a1628}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--tx);font-family:\'Segoe UI\',sans-serif;font-size:15px;line-height:1.7}
body.light{--bg:#f5f5f0;--bg2:#eeede8;--bg3:#e8e8e2;--bd:#c8c8c0;--ac:#1a4f8a;--ac2:#2a6aaa;--ci:#1a4f8a;--tx:#0d1e35;--mu:#4a7aaa;--gr:#1a7a4a;--ye:#b45309;--re:#c01c28;--cb:#dde3ec}
header{background:linear-gradient(135deg,var(--bg),var(--bg3),var(--bg));border-bottom:1px solid var(--bd);padding:3rem 2rem 2rem;text-align:center}
.logo{font-size:3rem;font-weight:700;color:var(--ci);letter-spacing:-2px}
.logo span{color:var(--ac2)}
.sub{font-size:.8rem;letter-spacing:4px;color:var(--ac2);margin:.25rem 0}
.pow{font-size:.75rem;color:var(--mu);margin:.25rem 0}
.badge{display:inline-block;background:var(--bg3);border:1px solid var(--bd);color:var(--ci);font-size:.7rem;padding:.2rem .8rem;border-radius:20px;margin:.75rem 0}
.theme-btn{background:var(--bg3);border:1px solid var(--bd);color:var(--ci);padding:.6rem 1.6rem;border-radius:20px;cursor:pointer;font-size:1rem;margin:.5rem 0;font-weight:500}
.wrap{max-width:100%;padding:2rem 3rem}
.toc{background:var(--bg2);border:1px solid var(--bd);border-left:3px solid var(--ac);border-radius:8px;padding:1.5rem;margin:2rem 0}
.toc h2{color:var(--ac2);font-size:.8rem;letter-spacing:3px;margin-bottom:.75rem}
.toc a{color:var(--ci);text-decoration:none;font-size:.9rem}
.toc a:hover{color:var(--tx)}
.toc ol{padding-left:1.5rem}
.toc li{margin:.25rem 0}
section{margin:3rem 0}
.sh{display:flex;align-items:center;gap:.75rem;margin-bottom:1.25rem;padding-bottom:.75rem;border-bottom:1px solid var(--bd)}
.si{font-size:1.4rem}
.st{font-size:1.3rem;font-weight:700;color:var(--ci)}
.sn{font-size:.7rem;color:var(--ac);margin-left:auto;background:var(--bg3);padding:.15rem .5rem;border-radius:4px;border:1px solid var(--bd)}
p{margin:.6rem 0}
.card{background:var(--bg2);border:1px solid var(--bd);border-radius:8px;padding:1.25rem 1.5rem;margin:.75rem 0}
.ct{font-weight:700;color:var(--ac2);margin-bottom:.5rem;font-size:.9rem}
ul{padding-left:1.5rem;color:var(--ci)}
li{margin:.2rem 0}
.note{background:rgba(42,90,154,.15);border-left:3px solid var(--ac);padding:.75rem 1rem;margin:.75rem 0;font-size:.9rem;border-radius:0 6px 6px 0}
.tip{background:rgba(52,211,153,.1);border-left:3px solid var(--gr);padding:.75rem 1rem;margin:.75rem 0;font-size:.9rem;border-radius:0 6px 6px 0}
.warn{background:rgba(251,191,36,.1);border-left:3px solid var(--ye);padding:.75rem 1rem;margin:.75rem 0;font-size:.9rem;border-radius:0 6px 6px 0}
code{font-family:monospace;background:var(--cb);border:1px solid var(--bd);color:var(--ci);padding:.1rem .4rem;border-radius:4px;font-size:.85rem}
pre{background:var(--cb);border:1px solid var(--bd);border-radius:6px;padding:1rem;margin:.75rem 0;overflow-x:auto;font-family:monospace;font-size:.85rem;color:var(--ci)}
kbd{background:var(--bg3);border:1px solid var(--ac);color:var(--ci);font-family:monospace;font-size:.75rem;padding:.15rem .5rem;border-radius:4px}
.sg{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:.6rem;margin:.75rem 0}
.si2{background:var(--bg2);border:1px solid var(--bd);border-radius:6px;padding:.5rem .9rem;display:flex;align-items:center;gap:.6rem;font-size:.85rem}
.lg{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:.4rem;margin:.75rem 0}
.li{background:var(--bg2);border:1px solid var(--bd);border-radius:6px;padding:.4rem .75rem;font-size:.9rem}
.wf{display:flex;flex-direction:column;margin:.75rem 0}
.ws{display:flex;align-items:flex-start;gap:1rem;padding:.6rem 0;border-left:2px solid var(--bd);padding-left:1.5rem;position:relative}
.ws::before{content:attr(data-n);position:absolute;left:-13px;background:var(--ac);color:white;width:24px;height:24px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:.7rem;font-weight:700}
.ws:last-child{border-left-color:transparent}
.wt{font-weight:600;color:var(--ac2)}
.wd{font-size:.85rem;color:var(--ci)}
.pal{display:flex;gap:.5rem;flex-wrap:wrap;margin:.75rem 0}
.sw{display:flex;flex-direction:column;align-items:center;gap:.2rem}
.sb{width:55px;height:35px;border-radius:5px;border:1px solid var(--bd)}
.sl{font-family:monospace;font-size:.6rem;color:var(--mu)}
footer{border-top:1px solid var(--bd);padding:2rem;text-align:center;color:var(--mu);font-size:.85rem;margin-top:4rem}
footer strong{color:var(--ci)}
</style>
</head>
<body>
<header>
  <img id="logo-img" src="" alt="Nseek" style="max-width:580px;width:90%;height:auto;display:block;margin:0 auto 0.5rem">
  <button class="theme-btn" id="tb">☀️ Thème clair</button>
</header>
<div class="wrap">
  <nav class="toc">
    <h2>📋 TABLE DES MATIÈRES</h2>
    <ol>
      <li><a href="#s1">Présentation</a></li>
      <li><a href="#s2">Installation et démarrage</a></li>
      <li><a href="#s3">Interface — Vue d\'ensemble</a></li>
      <li><a href="#s4">Le Chat IA</a></li>
      <li><a href="#s5">Le Persona</a></li>
      <li><a href="#s6">Sélecteur de langue</a></li>
      <li><a href="#s7">Historique des conversations</a></li>
      <li><a href="#s8">L\'Éditeur de code</a></li>
      <li><a href="#s9">Raccourcis clavier</a></li>
      <li><a href="#s10">Toolbar verticale</a></li>
      <li><a href="#s11">Thèmes clair / sombre</a></li>
      <li><a href="#s12">Crédits et licences</a></li>
    </ol>
  </nav>

  <section id="s1"><div class="sh"><span class="si">🐋</span><span class="st">Présentation</span><span class="sn">01</span></div>
  <p><strong>Nseek</strong> est un client IA natif pour Linux, construit avec GTK4 et Python. Il permet d\'interagir avec les modèles <strong>DeepSeek V4</strong> directement depuis le bureau GNOME.</p>
  <div class="card"><div class="ct">✨ Fonctionnalités clés</div><ul>
  <li>Chat IA en streaming temps réel</li><li>Historique sauvegardé localement (JSON)</li>
  <li>Éditeur de code avec coloration syntaxique (GtkSourceView 5)</li>
  <li>Exécution du code depuis l\'éditeur</li><li>Persona configurable</li>
  <li>Sélecteur de 10 langues</li><li>Pièces jointes (texte, PDF)</li>
  <li>Thème clair et sombre</li><li>Impression des conversations</li>
  </ul></div>
  <div class="tip">Nseek fonctionne sur Linux avec GNOME/Wayland. Une clé API DeepSeek est requise.</div>
  </section>

  <section id="s2"><div class="sh"><span class="si">⚙️</span><span class="st">Installation et démarrage</span><span class="sn">02</span></div>
  <div class="card"><div class="ct">📦 Dépendances</div>
  <pre>dnf install python3-gobject gtk4 gtksourceview5 python3-pip
pip install pypdf cairosvg --break-system-packages</pre></div>
  <div class="card"><div class="ct">🚀 Lancement</div><pre>python3 ~/Programmes/nseek.py</pre></div>
  <div class="card"><div class="ct">🔑 Clé API</div>
  <p>Créez votre clé sur <code>platform.deepseek.com</code> et enregistrez-la dans :</p>
  <pre>~/Documents/cle_deepseek_v4_api.txt</pre></div>
  <div class="warn">Votre clé API est sensible — ne la partagez jamais.</div>
  </section>

  <section id="s3"><div class="sh"><span class="si">🖥️</span><span class="st">Interface — Vue d\'ensemble</span><span class="sn">03</span></div>
  <div class="card"><div class="ct">🗺️ Structure</div>
  <pre>┌────────────────────────────────────────────────────┐
│  HeaderBar : Nseek  |  CLIENT IA NATIF GTK4  🌐 💳 ✕ │
├─────────────┬──────────────────────────────┬───────┤
│             │ Clé API / Persona / Modèle   │  🔍  │
│ CONVERSATIONS│──────────────────────────────│  📋  │
│             │                              │  💾  │
│ + Nouvelle  │      Zone de Chat            │  🖨️  │
│             │   (messages + blocs code)    │  ...  │
│  Historique │──────────────────────────────│  Doc  │
│             │  [📎] [Message...   ] 🗑 ➤   │  ✏️  │
├─────────────┴──────────────────────────────┴───────┤
│  Statut          © 2026 carafife     ⬆ ⬇ 💰        │
└────────────────────────────────────────────────────┘</pre></div>
  </section>

  <section id="s4"><div class="sh"><span class="si">💬</span><span class="st">Le Chat IA</span><span class="sn">04</span></div>
  <div class="card"><div class="ct">📤 Envoyer</div><ul>
  <li><kbd>Entrée</kbd> — Envoyer le message</li>
  <li><kbd>Maj+Entrée</kbd> — Saut de ligne</li></ul></div>
  <div class="card"><div class="ct">🤖 Modèles</div><ul>
  <li><strong>deepseek-v4-pro</strong> — Le plus puissant</li>
  <li><strong>deepseek-v4-flash</strong> — Rapide et économique</li>
  <li><strong>deepseek-chat</strong> — Modèle standard</li></ul></div>
  <div class="card"><div class="ct">⚙️ Options</div><ul>
  <li><strong>🧠 Thinking</strong> — Raisonnement interne visible</li>
  <li><strong>⚡ Streaming</strong> — Réponse en temps réel</li></ul></div>
  <div class="card"><div class="ct">💻 Blocs de code</div>
  <p>Nseek détecte les blocs de code et les affiche avec coloration syntaxique et un bouton <strong>📋 Copier</strong>.</p></div>
  </section>

  <section id="s5"><div class="sh"><span class="si">🎭</span><span class="st">Le Persona</span><span class="sn">05</span></div>
  <p>Le <strong>Persona</strong> est une instruction permanente définissant le rôle de l\'IA. Cliquez sur <strong>✏️</strong> pour le modifier.</p>
  <div class="card"><div class="ct">💡 Exemples</div><ul>
  <li><em>Tu es un expert Linux Fedora. Donne des réponses concises.</em></li>
  <li><em>Tu es un professeur patient. Explique avec des analogies.</em></li>
  <li><em>Tu es un développeur Python senior. Code pythonique.</em></li>
  <li><em>Tu es un traducteur. Traduis sans commenter.</em></li></ul></div>
  </section>

  <section id="s6"><div class="sh"><span class="si">🗣️</span><span class="st">Sélecteur de langue</span><span class="sn">06</span></div>
  <p>Choisissez la langue de réponse — l\'instruction est ajoutée automatiquement.</p>
  <div class="lg">
  <div class="li">🇫🇷 Français</div><div class="li">🇬🇧 English</div><div class="li">🇪🇸 Español</div>
  <div class="li">🇨🇳 中文</div><div class="li">🇸🇦 العربية</div><div class="li">🇧🇷 Português</div>
  <div class="li">🇷🇺 Русский</div><div class="li">🇩🇪 Deutsch</div><div class="li">🇯🇵 日本語</div>
  <div class="li">🇮🇳 हिन्दी</div></div>
  </section>

  <section id="s7"><div class="sh"><span class="si">📚</span><span class="st">Historique des conversations</span><span class="sn">07</span></div>
  <p>Sauvegardé dans <code>~/.local/share/deepseek-chat/</code> (JSON).</p>
  <div class="card"><div class="ct">🗂️ Gestion</div><ul>
  <li><strong>+ Nouvelle conversation</strong> — Démarre une session vierge</li>
  <li>Cliquer sur une session — Recharge la conversation</li>
  <li><strong>🗑</strong> — Supprime la session</li>
  <li><kbd>Ctrl+H</kbd> — Affiche/masque le panneau</li></ul></div>
  </section>

  <section id="s8"><div class="sh"><span class="si">✏️</span><span class="st">L\'Éditeur de code</span><span class="sn">08</span></div>
  <p>Cliquez sur <strong>✏️</strong> dans la toolbar pour ouvrir l\'éditeur.</p>
  <div class="wf">
  <div class="ws" data-n="1"><div><div class="wt">Demandez du code à DeepSeek</div><div class="wd">Posez votre question dans le chat</div></div></div>
  <div class="ws" data-n="2"><div><div class="wt">Copiez le bloc</div><div class="wd">Cliquez 📋 Copier dans le bloc généré</div></div></div>
  <div class="ws" data-n="3"><div><div class="wt">Collez dans l\'éditeur</div><div class="wd">✏️ → 📋 Coller le code</div></div></div>
  <div class="ws" data-n="4"><div><div class="wt">Exécutez</div><div class="wd">▶ Exécuter — résultat affiché en bas</div></div></div>
  <div class="ws" data-n="5"><div><div class="wt">Correction automatique</div><div class="wd">🤖 Demander correction → envoie l\'erreur à DeepSeek</div></div></div>
  </div>
  <div class="card"><div class="ct">🌐 Langages exécutables</div>
  <p><code>python3</code> <code>bash</code> <code>javascript</code> <code>go</code></p></div>
  </section>

  <section id="s9"><div class="sh"><span class="si">⌨️</span><span class="st">Raccourcis clavier</span><span class="sn">09</span></div>
  <div class="sg">
  <div class="si2"><kbd>Ctrl+N</kbd><span>Nouvelle conversation</span></div>
  <div class="si2"><kbd>Ctrl+L</kbd><span>Effacer</span></div>
  <div class="si2"><kbd>Ctrl+F</kbd><span>Rechercher</span></div>
  <div class="si2"><kbd>Ctrl+E</kbd><span>Exporter (.txt)</span></div>
  <div class="si2"><kbd>Ctrl+H</kbd><span>Afficher/masquer historique</span></div>
  <div class="si2"><kbd>Ctrl+T</kbd><span>Thème clair/sombre</span></div>
  <div class="si2"><kbd>Ctrl+B</kbd><span>DeepSeek Web</span></div>
  <div class="si2"><kbd>Ctrl+Q</kbd><span>Quitter</span></div>
  <div class="si2"><kbd>Entrée</kbd><span>Envoyer le message</span></div>
  <div class="si2"><kbd>Maj+Entrée</kbd><span>Saut de ligne</span></div>
  </div>
  </section>

  <section id="s10"><div class="sh"><span class="si">🔧</span><span class="st">Toolbar verticale droite</span><span class="sn">10</span></div>
  <div class="card"><div class="ct">Boutons de la toolbar (de haut en bas)</div><ul>
  <li>🔍 Rechercher dans le chat</li><li>📋 Copier la dernière réponse</li>
  <li>💾 Exporter la conversation</li><li>🖨️ Imprimer</li>
  <li>A+ / A− Police plus grande/petite</li>
  <li>🔄 Régénérer la dernière réponse</li><li>🗑 Effacer la conversation</li>
  <li>❓ Aide contextuelle</li><li>Doc Manuel utilisateur</li>
  <li>✏️ Éditeur de code</li><li>☀️/🌙 Thème</li><li>✕ Quitter</li></ul></div>
  </section>

  <section id="s11"><div class="sh"><span class="si">🎨</span><span class="st">Thèmes</span><span class="sn">11</span></div>
  <p><kbd>Ctrl+T</kbd> ou bouton ☀️/🌙 pour basculer.</p>
  <div class="card"><div class="ct">🌙 Thème sombre (défaut)</div>
  <div class="pal">
  <div class="sw"><div class="sb" style="background:#060d1a"></div><div class="sl">#060d1a</div></div>
  <div class="sw"><div class="sb" style="background:#0a1628"></div><div class="sl">#0a1628</div></div>
  <div class="sw"><div class="sb" style="background:#2a5a9a"></div><div class="sl">#2a5a9a</div></div>
  <div class="sw"><div class="sb" style="background:#7aaad0"></div><div class="sl">#7aaad0</div></div>
  </div></div>
  <div class="card"><div class="ct">☀️ Thème clair</div>
  <div class="pal">
  <div class="sw"><div class="sb" style="background:#f5f5f0;border:1px solid #ddd"></div><div class="sl">#f5f5f0</div></div>
  <div class="sw"><div class="sb" style="background:#c8d8f0"></div><div class="sl">#c8d8f0</div></div>
  <div class="sw"><div class="sb" style="background:#1a4f8a"></div><div class="sl">#1a4f8a</div></div>
  <div class="sw"><div class="sb" style="background:#0d1e35"></div><div class="sl">#0d1e35</div></div>
  </div></div>
  </section>

  <section id="s12"><div class="sh"><span class="si">📜</span><span class="st">Crédits et licences</span><span class="sn">12</span></div>
  <div class="card"><div class="ct">👤 Auteur</div>
  <p><strong>carafife</strong> — <code>github.com/carafife/nseek</code></p></div>
  <div class="card"><div class="ct">📄 Licence GPL v3</div>
  <p>Libre d\'utilisation, modification et redistribution.</p></div>
  <div class="card"><div class="ct">🔗 Technologies</div><ul>
  <li><strong>Python 3.10+</strong>, <strong>GTK 4</strong>, <strong>GtkSourceView 5</strong></li>
  <li><strong>DeepSeek API</strong>, <strong>pypdf</strong>, <strong>cairosvg</strong></li></ul></div>
  </section>
</div>
<footer><p>🐋 <strong>Nseek v1.0</strong> — Client IA natif GTK4 Linux</p>
<p>&copy; 2026 <strong>carafife</strong> — GPL v3</p></footer>
<script>
const p=new URLSearchParams(window.location.search);
if(p.get(\'theme\')==\'light\')document.body.classList.add(\'light\');
const b=document.getElementById(\'tb\');
b.addEventListener(\'click\',()=>{
  document.body.classList.toggle(\'light\');
  b.textContent=document.body.classList.contains(\'light\')?\'🌙 Thème sombre\':\'☀️ Thème clair\';
});
</script>
</body></html>'''
        # Injecter le logo PNG et l'icône en base64
        try:
            import base64
            base_dir = os.path.dirname(os.path.abspath(__file__))
            # Logo principal (header)
            logo_path = os.path.join(base_dir, 'assets', 'nseek-logo.png')
            if os.path.exists(logo_path):
                with open(logo_path, 'rb') as lf:
                    logo_b64 = base64.b64encode(lf.read()).decode()
                html = html.replace('src="" alt="Nseek"',
                    f'src="data:image/png;base64,{logo_b64}" alt="Nseek"')
            # Icône petite (sections + footer) — remplace les emojis 🐋
            icon_path = os.path.join(base_dir, 'assets', 'nseek-icon-ciel.png')
            if os.path.exists(icon_path):
                with open(icon_path, 'rb') as lf:
                    icon_b64 = base64.b64encode(lf.read()).decode()
                icon_img = f'<img src="data:image/png;base64,{icon_b64}" style="width:168px;height:168px;vertical-align:middle;margin-right:4px" alt="Nseek">'
                html = html.replace('🐋 ', icon_img + ' ')
                html = html.replace('🐋', icon_img)
        except Exception:
            pass
        with open(path, 'w', encoding='utf-8') as f:
            f.write(html)
        self.status.set_text(f"✅ Manuel généré : {path}")

    def _show_help(self, *_):
        dlg = Gtk.Window(title="Aide — Nseek")
        dlg.set_default_size(580, 620)
        dlg.set_transient_for(self)
        dlg.set_modal(True)

        # Appliquer le CSS de l'appli
        Gtk.StyleContext.add_provider_for_display(
            dlg.get_display(), self.css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        # En-tête
        hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        hdr.add_css_class("code-header")
        hdr.set_margin_start(12); hdr.set_margin_end(12)
        hdr.set_margin_top(10); hdr.set_margin_bottom(10)
        t = Gtk.Label(label="🐋 Nseek — Aide"); t.add_css_class("app-title")
        t.set_xalign(0); t.set_hexpand(True)
        hdr.append(t)
        btn_x = Gtk.Button(label="✕"); btn_x.add_css_class("quit-btn")
        btn_x.set_focusable(False)
        btn_x.connect("clicked", lambda *_: dlg.destroy())
        hdr.append(btn_x)
        box.append(hdr)

        sep = Gtk.Separator(); box.append(sep)

        # Contenu avec couleurs adaptées au thème
        acc = "#60a5fa" if self.is_dark else "#1a4f8a"
        fg  = "#e0eeff" if self.is_dark else "#0d1e35"
        fg2 = "#7aaad0" if self.is_dark else "#4a7aaa"

        sections = [
            ("✏️ SAISIE", [
                ("<b>Entrée</b>", "Envoyer le message"),
                ("<b>Maj+Entrée</b>", "Saut de ligne"),
                ("<b>📎</b>", "Joindre un fichier texte/PDF"),
                ("Glisser-déposer", "Un fichier dans la fenêtre"),
            ]),
            ("🤖 MODÈLES", [
                ("<b>deepseek-v4-pro</b>", "Le plus puissant"),
                ("<b>deepseek-v4-flash</b>", "Rapide et économique"),
                ("<b>deepseek-chat</b>", "Modèle standard"),
            ]),
            ("⚙️ OPTIONS", [
                ("<b>🧠 Thinking</b>", "Raisonnement interne visible"),
                ("<b>⚡ Streaming</b>", "Réponse au fil de l'eau"),
                ("<b>🎭 Persona ✏️</b>", "Rôle/comportement de l'IA — cliquer ✏️ pour modifier"),
                ("<b>🗣️ Langue</b>", "Langue de réponse (10 langues disponibles)"),
                ("<b>A+ / A-</b>", "Taille de la police"),
            ]),
            ("⌨️ RACCOURCIS", [
                ("<b>Ctrl+N</b>", "Nouvelle conversation"),
                ("<b>Ctrl+L</b>", "Effacer la conversation"),
                ("<b>Ctrl+F</b>", "Rechercher dans le chat"),
                ("<b>Ctrl+E</b>", "Exporter (.txt)"),
                ("<b>Ctrl+H</b>", "Afficher/masquer historique"),
                ("<b>Ctrl+T</b>", "Thème clair/sombre"),
                ("<b>Ctrl+B</b>", "Ouvrir DeepSeek Web"),
                ("<b>Ctrl+Q</b>", "Quitter"),
            ]),
            ("🔧 TOOLBAR DROITE", [
                ("<b>🔍</b>", "Rechercher dans le chat"),
                ("<b>📋</b>", "Copier la dernière réponse"),
                ("<b>💾</b>", "Exporter la conversation"),
                ("<b>🖨️</b>", "Imprimer la conversation"),
                ("<b>A+ / A-</b>", "Taille de la police"),
                ("<b>🔄</b>", "Régénérer la dernière réponse"),
                ("<b>🗑</b>", "Effacer la conversation"),
                ("<b>❓</b>", "Aide contextuelle"),
                ("<b>Doc</b>", "Manuel utilisateur complet"),
                ("<b>✏️</b>", "Ouvrir l'éditeur de code"),
                ("<b>☀️/🌙</b>", "Basculer thème clair/sombre"),
                ("<b>✕</b>", "Quitter Nseek"),
            ]),
            ("✏️ ÉDITEUR DE CODE", [
                ("<b>📋 Coller</b>", "Colle le dernier code copié"),
                ("<b>▶ Exécuter</b>", "Lance le code — terminal interactif (supporte input())"),
                ("<b>💾 Sauver</b>", "Sauvegarde dans ~/Documents/"),
                ("<b>🤖 Correction</b>", "Envoie le code + l'erreur à DeepSeek"),
                ("<b>🐋 Nseek</b>", "Revenir à la fenêtre Nseek"),
            ]),
            ("🔑 CLÉ API & PERSONA", [
                ("<b>Clé API ✏️</b>", "Cliquer ✏️ pour saisir ou modifier la clé"),
                ("<b>Persona ✏️</b>", "Définit le rôle de l'IA — cliquer ✏️ pour modifier"),
                ("<b>Clé sauvegardée</b>", "~/Documents/cle_deepseek_v4_api.txt"),
            ]),
            ("💰 STATS (barre du bas)", [
                ("<b>⬆ / ⬇</b>", "Tokens envoyés / reçus"),
                ("<b>💰</b>", "Coût de la session en cours"),
            ]),
        ]

        content = ""
        for title, items in sections:
            content += f'\n<b><span foreground="{acc}">  {title}</span></b>\n'
            for k, v in items:
                content += f'<span foreground="{fg2}">  • </span><span foreground="{fg}">{k}</span><span foreground="{fg2}"> → {v}</span>\n'

        lbl = Gtk.Label()
        lbl.set_markup(f'<span font="10">{content}</span>')
        lbl.set_xalign(0); lbl.set_wrap(True); lbl.set_wrap_mode(2)
        lbl.set_margin_start(8); lbl.set_margin_end(8)

        sw = Gtk.ScrolledWindow(); sw.set_child(lbl); sw.set_vexpand(True)
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        box.append(sw)

        sep2 = Gtk.Separator(); box.append(sep2)

        # Pied
        foot = Gtk.Box()
        foot.set_margin_start(12); foot.set_margin_end(12)
        foot.set_margin_top(8); foot.set_margin_bottom(8)
        sp = Gtk.Box(); sp.set_hexpand(True); foot.append(sp)
        close_btn = Gtk.Button(label="Fermer"); close_btn.add_css_class("send")
        close_btn.set_focusable(False)
        close_btn.connect("clicked", lambda *_: dlg.destroy())
        foot.append(close_btn)
        box.append(foot)

        dlg.set_child(box)
        kc = Gtk.EventControllerKey()
        kc.connect("key-pressed", lambda c,k,kc2,s: dlg.destroy() or True if k==65307 else False)
        dlg.add_controller(kc)
        dlg.present()

    def _on_key(self, ctrl, kv, kc, st):
        if kv == 65293 and not (st & 1): self._send(); return True
        return False

    def _on_search_key(self, ctrl, kv, kc, st):
        if kv == 65307: self._toggle_search(); return True  # Échap
        if kv == 65293: self._do_search(); return True      # Entrée
        GLib.idle_add(self._do_search)
        return False

    # ── Getters texte ─────────────────────────────────────────
    def _gbuf(self, buf):
        return buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False).strip()

    def _get_key(self): return self._gbuf(self.key_buf)
    def _get_msg(self): return self._gbuf(self.msg_buf)
    def _get_sys(self): return self._gbuf(self.sys_buf)

    def _build_messages(self):
        msgs = []
        s = self._get_sys()
        lang_idx = int(self.lang_dd.get_selected())
        lang_instr = self.LANGUAGES[lang_idx][1]
        system = f"{s}\n{lang_instr}" if s.strip() else lang_instr
        msgs.append({"role":"system","content":system})
        msgs.extend(self.history)
        return msgs

    # ── Clé API ───────────────────────────────────────────────
    def _load_key(self):
        try:
            with open(KEY_FILE) as f:
                self.key_buf.set_text(f.read().strip())
            self._update_key_lbl()
        except Exception: pass

    # ── Fichiers ──────────────────────────────────────────────
    def _pick_file(self, *_):
        Gtk.FileDialog().open(self, None, self._on_file, None)

    def _on_file(self, dlg, res, _):
        try:
            gf = dlg.open_finish(res); path = gf.get_path()
            name = os.path.basename(path); data = open(path,'rb').read()
            mime = ('image/jpeg' if path.lower().endswith(('.jpg','.jpeg')) else
                    'image/png'  if path.lower().endswith('.png') else
                    'application/pdf' if path.lower().endswith('.pdf') else 'text/plain')
            self.attached_file = {'name':name,'mime':mime,'b64':base64.b64encode(data).decode(),'path':path}
            self.file_lbl.set_text(f"📎 {name}"); self.file_bar.set_visible(True)
        except Exception as e: print(e)

    # ── Affichage ─────────────────────────────────────────────
    def _apply_font(self):
        self.font_css = Gtk.CssProvider()
        self.font_css.load_from_string(f"textview {{ font-size: {self.font_size}pt; }}")
        Gtk.StyleContext.add_provider_for_display(
            self.get_display(), self.font_css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1)

    def _font_bigger(self, *_):
        if self.font_size < 20:
            self.font_size += 1; self._apply_font()

    def _font_smaller(self, *_):
        if self.font_size > 8:
            self.font_size -= 1; self._apply_font()

    # ── Insertion de texte dans le buffer de chat ─────────────────────────────
    def _ins(self, text, *tags):
        it = self.buf.get_end_iter()
        if tags: self.buf.insert_with_tags_by_name(it, text, *tags)
        else:    self.buf.insert(it, text)

    def _scroll(self):
        self.view.scroll_to_iter(self.buf.get_end_iter(), 0, False, 0, 1)

    # ── Rendu markdown simplifié + détection blocs de code ───────────────────
    def _render(self, text):
        for p in re.split(r'(```[\w]*\n.*?```)', text, flags=re.DOTALL):
            if p.startswith('```'):
                lines = p.split('\n')
                lang = lines[0].replace('```', '').strip()
                code = '\n'.join(lines[1:]).rstrip('`\n')
                self._insert_code_block(lang, code)
            else:
                for line in p.split('\n'):
                    for seg in re.split(r'(\*\*[^*]+\*\*|`[^`]+`)', line):
                        if seg.startswith('**') and seg.endswith('**'): self._ins(seg[2:-2], "bold")
                        elif seg.startswith('`') and seg.endswith('`'):  self._ins(seg[1:-1], "code")
                        else: self._ins(seg, "body")
                    self._ins('\n', "body")

    def _insert_code_block(self, lang, code):
        """Insère un bloc GtkSourceView avec coloration syntaxique."""
        import gi
        gi.require_version('GtkSource', '5')
        from gi.repository import GtkSource

        self._ins("\n", "body")

        # Mapping noms markdown → IDs GtkSource
        lang_map = {
            'python': 'python3', 'py': 'python3',
            'bash': 'sh', 'shell': 'sh', 'sh': 'sh',
            'javascript': 'js', 'js': 'js', 'typescript': 'typescript',
            'c': 'c', 'cpp': 'cpp', 'c++': 'cpp',
            'rust': 'rust', 'go': 'go', 'java': 'java',
            'sql': 'sql', 'html': 'html', 'css': 'css',
            'xml': 'xml', 'json': 'json', 'yaml': 'yaml',
            'markdown': 'markdown', 'md': 'markdown',
        }
        lang_id = lang_map.get(lang.lower() if lang else '', lang or '')

        # Buffer GtkSource
        src_buf = GtkSource.Buffer()
        lm = GtkSource.LanguageManager.get_default()
        language = lm.get_language(lang_id)
        if language:
            src_buf.set_language(language)
        src_buf.set_text(code)
        src_buf.set_highlight_syntax(True)

        # Thème
        sm = GtkSource.StyleSchemeManager.get_default()
        scheme_id = "oblivion" if self.is_dark else "Adwaita"
        scheme = sm.get_scheme(scheme_id)
        if not scheme:
            scheme = sm.get_scheme(sm.get_scheme_ids()[0])
        if scheme:
            src_buf.set_style_scheme(scheme)

        # Vue source
        src_view = GtkSource.View(buffer=src_buf)
        src_view.set_editable(False)
        src_view.set_show_line_numbers(True)
        src_view.set_highlight_current_line(False)
        src_view.set_monospace(True)
        src_view.set_hexpand(True)
        src_view.set_size_request(580, -1)

        # Conteneur
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        box.set_hexpand(True)

        # En-tête : nom du langage seulement
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        header.add_css_class("code-header")
        lbl = Gtk.Label(label=f" {lang.upper() if lang else 'CODE'} ")
        lbl.add_css_class("code-lang")
        header.append(lbl)
        box.append(header)
        box.append(src_view)

        # Pied : bouton copier à droite
        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        footer.add_css_class("code-header")
        spacer = Gtk.Box(); spacer.set_hexpand(True)
        footer.append(spacer)
        code_snap = code; lang_snap = lang  # captures explicites
        btn = Gtk.Button(label=f"📋 Copier le {lang_snap or 'code'}")
        btn.add_css_class("code-copy-btn"); btn.set_focusable(False)
        btn.connect("clicked", lambda *_, c=code_snap, l=lang_snap, b=btn: self._copy_code(c, l, b))
        footer.append(btn)
        box.append(footer)

        # Insérer dans le TextView
        anchor = self.buf.create_child_anchor(self.buf.get_end_iter())
        self.view.add_child_at_anchor(box, anchor)
        self._ins("\n\n", "body")

    def _rerender_last_response(self, reply):
        """Après streaming, efface la dernière réponse et la re-rend avec blocs de code."""
        end = self.buf.get_end_iter()
        marker = "🤖 DeepSeek"
        found = None
        it = self.buf.get_start_iter()
        while True:
            res = it.forward_search(marker, Gtk.TextSearchFlags.VISIBLE_ONLY, end)
            if not res: break
            found = res[0]; it = res[1]
        if not found: self._scroll(); return
        found.forward_chars(len(marker) + 1)
        self.buf.delete(found, self.buf.get_end_iter())
        self._ins("\n", "body")
        self._render(reply)
        self._ins("\n", "body")
        self._scroll()

    def _copy_code(self, code, lang, btn):
        provider = Gdk.ContentProvider.new_for_value(code)
        self.get_clipboard().set_content(provider)
        self._last_code = code  # mémorise pour coller dans le terminal
        original = btn.get_label()
        btn.set_label("✅ Copié !")
        self.status.set_text(f"✅ Code {lang or ''} copié — utilise ⚡ Terminal pour l'exécuter")
        GLib.timeout_add(2000, lambda: btn.set_label(original) or False)

    # ── Affichage d'un message dans le chat (vous/IA/erreur/info) ─────────────
    def _msg(self, kind, text, thinking=""):
        if kind == "you":   self._ins("\n🧑 Toi\n", "you")
        elif kind == "ai":  self._ins("\n🤖 DeepSeek\n", "ai")
        elif kind == "err": self._ins("\n⚠️  Erreur\n", "err")
        elif kind == "info":
            self._ins(text + "\n", "info"); GLib.idle_add(self._scroll); return
        if thinking: self._ins("💭 Raisonnement :\n","think"); self._render(thinking)
        self._render(text); self._ins("\n","body"); GLib.idle_add(self._scroll)

    # ── Thème ─────────────────────────────────────────────────
    # ── Bascule thème clair/sombre et met à jour le filigrane ─────────────────
    def _switch_theme(self, *_):
        self.is_dark = not self.is_dark
        self.css_provider.load_from_string(CSS_DARK if self.is_dark else CSS_LIGHT)
        self.theme_btn.set_label("☀️" if self.is_dark else "🌙")
        # Changer le filigrane selon le thème
        try:
            assets = os.path.dirname(os.path.abspath(__file__))
            logo = "nseek-logo-ciel.png" if self.is_dark else "nseek-logo-marine.png"
            path = os.path.join(assets, "assets", logo)
            if os.path.exists(path) and hasattr(self, 'wm_picture'):
                from gi.repository import GdkPixbuf, Gdk as GdkL
                pb = GdkPixbuf.Pixbuf.new_from_file(path)
                texture = GdkL.Texture.new_for_pixbuf(pb)
                self.wm_picture.set_paintable(texture)
        except Exception: pass
        if self.is_dark:
            self.dlg_css.load_from_string("""
                dialog { background:#2a2a2a; color:#e0e0e0; }
                dialog label { color:#e0e0e0; }
                dialog box { background:#2a2a2a; }
                scrolledwindow { background:#2a2a2a; }
            """)
        else:
            self.dlg_css.load_from_string("""
                dialog { background:#eeeae6; color:#1a1a1a; }
                dialog label { color:#1a1a1a; }
                dialog box { background:#eeeae6; }
                scrolledwindow { background:#eeeae6; }
            """)
        tags = TAGS_DARK if self.is_dark else TAGS_LIGHT
        for name, props in tags.items():
            tag = self.buf.get_tag_table().lookup(name)
            if tag:
                for k,v in props.items(): tag.set_property(k,v)

    # ── Recherche ─────────────────────────────────────────────
    def _toggle_search(self, *_):
        dlg = Gtk.Dialog(title="Rechercher", transient_for=self, modal=True)
        dlg.set_default_size(420, -1)
        dlg.set_deletable(True)

        box = dlg.get_content_area()
        box.set_spacing(10); box.set_margin_top(14); box.set_margin_bottom(14)
        box.set_margin_start(14); box.set_margin_end(14)

        lbl = Gtk.Label(label="Tape ta recherche (les touches s'accumulent) :")
        lbl.set_xalign(0); lbl.add_css_class("lbl"); box.append(lbl)

        # Label qui affiche le texte tapé (pas d'Entry/TextView = pas de bug IM)
        query = [""]
        query_lbl = Gtk.Label(label="▌")
        query_lbl.set_xalign(0)
        query_lbl.set_markup('<span foreground="#3584e4" font_size="13pt">▌</span>')
        qwrap = Gtk.Box(); qwrap.add_css_class("input-tv")
        qwrap.set_margin_top(2); qwrap.set_margin_bottom(2)
        qwrap.set_size_request(-1, 38)
        qwrap.append(query_lbl); box.append(qwrap)

        result_lbl = Gtk.Label(label="Appuie sur Entrée pour rechercher  •  Échap pour fermer")
        result_lbl.set_xalign(0); result_lbl.add_css_class("lbl"); box.append(result_lbl)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_box.set_halign(Gtk.Align.END)
        btn_close  = Gtk.Button(label="✕ Fermer"); btn_close.add_css_class("tool")
        btn_search = Gtk.Button(label="🔍 Rechercher"); btn_search.add_css_class("send")
        btn_box.append(btn_close); btn_box.append(btn_search)
        box.append(btn_box)

        def update_label():
            txt = query[0] if query[0] else ""
            query_lbl.set_markup(
                f'<span foreground="#3584e4" font_size="13pt">{txt}▌</span>'
                if txt else '<span foreground="#606060" font_size="13pt">▌</span>')

        def do_search(*_):
            self._clear_highlights()
            q = query[0].strip()
            if not q: return
            start = self.buf.get_start_iter()
            end   = self.buf.get_end_iter()
            count = 0; first = None
            while True:
                found = start.forward_search(q, Gtk.TextSearchFlags.VISIBLE_ONLY, end)
                if not found: break
                ms, me = found
                self.buf.apply_tag_by_name("hl", ms, me)
                if first is None: first = ms
                start = me; count += 1
            icon = "✅" if count else "❌"
            result_lbl.set_text(f"{icon} {count} résultat(s) pour « {q} »")
            if first: self.view.scroll_to_iter(first, 0, False, 0, 0.3)
            self.status.set_text(f"🔍 {count} résultat(s) pour « {q} »")

        def on_key(ctrl, kv, kc, st):
            if kv == 65307:   dlg.destroy(); return True          # Échap
            if kv == 65293:   do_search();   return True          # Entrée
            if kv == 65288:                                        # Backspace
                query[0] = query[0][:-1]; update_label(); return True
            if kv == 65289:   return True                          # Tab ignoré
            # Caractères imprimables
            ch = chr(kv) if 32 <= kv < 127 else ""
            if not ch and kv > 127:
                try: ch = chr(kv)
                except Exception: ch = ""
            if ch:
                query[0] += ch; update_label()
            return True

        kc = Gtk.EventControllerKey()
        kc.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        kc.connect("key-pressed", on_key)
        dlg.add_controller(kc)

        btn_search.connect("clicked", do_search)
        btn_close.connect("clicked", lambda *_: dlg.destroy())
        dlg.connect("close-request", lambda *_: (self._clear_highlights(), self.msg_tv.grab_focus(), False)[-1])

        dlg.present()

    def _focus_search(self):
        self.search_tv.grab_focus()
        return False  # ne pas répéter

    def _do_search(self):
        try:
            self._clear_highlights()
            q = self._gbuf(self.search_buf)
            if not q: return
            start = self.buf.get_start_iter()
            end   = self.buf.get_end_iter()
            count = 0
            while True:
                found = start.forward_search(q, Gtk.TextSearchFlags.VISIBLE_ONLY, end)
                if not found: break
                ms, me = found
                self.buf.apply_tag_by_name("hl", ms, me)
                start = me; count += 1
            self.status.set_text(f"🔍 {count} résultat(s) pour « {q} »")
            it = self.buf.get_start_iter()
            f2 = it.forward_search(q, Gtk.TextSearchFlags.VISIBLE_ONLY, self.buf.get_end_iter())
            if f2: self.view.scroll_to_iter(f2[0], 0, False, 0, 0.3)
        except Exception as e:
            import traceback; traceback.print_exc()

    def _clear_highlights(self):
        try:
            self.buf.remove_tag_by_name("hl", self.buf.get_start_iter(), self.buf.get_end_iter())
        except Exception: pass

    def _on_search_key(self, ctrl, kv, kc, st):
        if kv == 65307: self._toggle_search(); return True   # Échap
        if kv == 65293: self._do_search();     return True   # Entrée
        return False  # Pas de live-search pour éviter les crashs

    # ── Copier ────────────────────────────────────────────────
    # ── Impression de la conversation via GTK PrintOperation ─────────────────
    def _print_conv(self, *_):
        """Imprime la conversation via la boîte de dialogue d'impression GTK."""
        op = Gtk.PrintOperation()
        op.set_job_name(f"Nseek — {self.session_name}")
        op.set_n_pages(1)

        def draw_page(operation, context, page_nr):
            cr = context.get_cairo_context()
            width = context.get_width()
            layout = context.create_pango_layout()
            import gi; gi.require_version('Pango','1.0')
            from gi.repository import Pango
            layout.set_width(int(width * Pango.SCALE))
            layout.set_wrap(Pango.WrapMode.WORD_CHAR)
            # Construire le texte de la conversation
            lines = [f"Nseek — Conversation du {self.session_name}\n{'='*60}\n"]
            for m in self.history:
                role = "Vous" if m['role'] == 'user' else "DeepSeek"
                lines.append(f"\n{role} :\n{m['content']}\n")
            layout.set_text('\n'.join(lines))
            import gi; gi.require_version('PangoCairo','1.0')
            from gi.repository import PangoCairo
            cr.move_to(10, 10)
            PangoCairo.show_layout(cr, layout)

        op.connect("draw-page", draw_page)
        try:
            op.run(Gtk.PrintOperationAction.PRINT_DIALOG, self)
        except Exception as e:
            self.status.set_text(f"Impression : {e}")

    # ── Régénère la dernière réponse de l'IA ──────────────────────────────────
    def _regenerate(self, *_):
        if not self.history:
            self.status.set_text("⚠️ Aucune conversation à régénérer."); return
        if self.history[-1]['role'] == 'assistant':
            self.history.pop()
        if not self.history or self.history[-1]['role'] != 'user':
            self.status.set_text("⚠️ Aucun message à régénérer."); return
        last_q = self.history[-1]['content']
        preview = last_q[:120] + "..." if len(last_q) > 120 else last_q
        self._ins(f"\n🔄 Régénération de la réponse à :\n", "ai")
        self._ins(f"« {preview} »\n\n", "body")
        self.status.set_text("🔄 Régénération en cours...")
        self._send(regenerate=True)

    def _update_key_lbl(self):
        key = self.key_buf.get_text(self.key_buf.get_start_iter(), self.key_buf.get_end_iter(), False)
        if key:
            # Masquer la clé : sk-****...****xxxx
            masked = key[:3] + "****" + key[-4:] if len(key) > 7 else "****"
            self.key_lbl.set_text(masked)
        else:
            self.key_lbl.set_text("— non définie —")

    def _edit_api_key(self, *_):
        """Dialogue de saisie de la clé API (surface Wayland indépendante)."""
        dlg = Gtk.Window(title="Nseek — Clé API DeepSeek")
        dlg.set_default_size(560, 240)
        dlg.set_transient_for(self)
        dlg.set_modal(True)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_margin_top(16); box.set_margin_bottom(16)
        box.set_margin_start(16); box.set_margin_end(16)

        hdr = Gtk.Label()
        hdr.set_markup('<b>🔑 Clé API DeepSeek</b>')
        hdr.set_xalign(0); hdr.add_css_class("lbl")
        box.append(hdr)

        info = Gtk.Label()
        info.set_markup('<span font="9" foreground="#4a7aaa">Obtenez votre clé sur platform.deepseek.com · Format : sk-...</span>')
        info.set_xalign(0); info.set_wrap(True)
        box.append(info)

        edit_buf = Gtk.TextBuffer()
        current = self.key_buf.get_text(self.key_buf.get_start_iter(), self.key_buf.get_end_iter(), False)
        edit_buf.set_text(current)
        edit_tv = Gtk.TextView(buffer=edit_buf)
        edit_tv.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        edit_tv.set_top_margin(8); edit_tv.set_left_margin(8)
        edit_tv.set_right_margin(8); edit_tv.set_bottom_margin(8)
        edit_tv.set_hexpand(True)
        sw = Gtk.ScrolledWindow(); sw.set_child(edit_tv)
        sw.set_hexpand(True); sw.set_size_request(-1, 70)
        sw.add_css_class("input-tv")
        box.append(sw)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        spacer = Gtk.Box(); spacer.set_hexpand(True); btn_box.append(spacer)

        btn_cancel = Gtk.Button(label="Annuler"); btn_cancel.add_css_class("tool")
        btn_cancel.set_focusable(False)
        btn_cancel.connect("clicked", lambda *_: dlg.destroy())
        btn_box.append(btn_cancel)

        btn_ok = Gtk.Button(label="✅ Valider"); btn_ok.add_css_class("send")
        btn_ok.set_focusable(False)
        def _validate(*_):
            txt = edit_buf.get_text(edit_buf.get_start_iter(), edit_buf.get_end_iter(), False).strip()
            self.key_buf.set_text(txt)
            # Sauvegarder dans le fichier
            try:
                os.makedirs(os.path.dirname(KEY_FILE), exist_ok=True)
                with open(KEY_FILE, 'w') as f: f.write(txt)
                self.status.set_text("✅ Clé API sauvegardée")
            except Exception as e:
                self.status.set_text(f"⚠️ Clé définie mais non sauvegardée : {e}")
            dlg.destroy()
        btn_ok.connect("clicked", _validate)
        btn_box.append(btn_ok)
        box.append(btn_box)

        kc = Gtk.EventControllerKey()
        kc.connect("key-pressed", lambda c,k,kc2,s: dlg.destroy() or True if k==65307 else False)
        dlg.add_controller(kc)
        dlg.set_child(box)
        dlg.present()
        GLib.timeout_add(100, lambda: edit_tv.grab_focus() or False)

    def _update_sys_lbl(self):
        txt = self.sys_buf.get_text(self.sys_buf.get_start_iter(), self.sys_buf.get_end_iter(), False)
        self.sys_lbl.set_text(txt if txt else "—")

    # ── Dialogue d'édition du Persona (surface Wayland indépendante) ──────────
    def _edit_persona(self, *_):
        """Dialogue d'édition du persona (fenêtre séparée pour focus Wayland)."""
        dlg = Gtk.Window(title="Nseek — Modifier le Persona")
        dlg.set_default_size(580, 280)
        dlg.set_transient_for(self)
        dlg.set_modal(True)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_top(16); box.set_margin_bottom(16)
        box.set_margin_start(16); box.set_margin_end(16)

        # En-tête
        hdr = Gtk.Label()
        hdr.set_markup('<b>🎭 Persona</b> — Définit le rôle et le comportement de l\'IA')
        hdr.set_xalign(0); hdr.add_css_class("lbl")
        box.append(hdr)

        # Exemples
        ex = Gtk.Label()
        ex.set_markup('<span font="9" foreground="#4a7aaa">Exemples : «Tu es un expert Linux Fedora» · «Tu es un professeur patient» · «Tu es un développeur Python senior» · «Tu es un traducteur»</span>')
        ex.set_wrap(True); ex.set_xalign(0)
        box.append(ex)

        # Zone de texte éditable
        edit_buf = Gtk.TextBuffer()
        current = self.sys_buf.get_text(self.sys_buf.get_start_iter(), self.sys_buf.get_end_iter(), False)
        edit_buf.set_text(current)
        edit_tv = Gtk.TextView(buffer=edit_buf)
        edit_tv.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        edit_tv.set_top_margin(8); edit_tv.set_left_margin(8)
        edit_tv.set_right_margin(8); edit_tv.set_bottom_margin(8)
        edit_tv.set_hexpand(True); edit_tv.set_vexpand(True)
        sw = Gtk.ScrolledWindow(); sw.set_child(edit_tv)
        sw.set_hexpand(True); sw.set_vexpand(True)
        sw.set_size_request(-1, 100)
        sw.add_css_class("input-tv")
        box.append(sw)

        # Boutons
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        spacer = Gtk.Box(); spacer.set_hexpand(True); btn_box.append(spacer)

        btn_cancel = Gtk.Button(label="Annuler"); btn_cancel.add_css_class("tool")
        btn_cancel.set_focusable(False)
        btn_cancel.connect("clicked", lambda *_: dlg.destroy())
        btn_box.append(btn_cancel)

        btn_ok = Gtk.Button(label="✅ Valider"); btn_ok.add_css_class("send")
        btn_ok.set_focusable(False)
        def _validate(*_):
            txt = edit_buf.get_text(edit_buf.get_start_iter(), edit_buf.get_end_iter(), False)
            self.sys_buf.set_text(txt)
            dlg.destroy()
        btn_ok.connect("clicked", _validate)
        btn_box.append(btn_ok)
        box.append(btn_box)

        # Touche Échap pour fermer
        kc = Gtk.EventControllerKey()
        kc.connect("key-pressed", lambda c,k,kc2,s: dlg.destroy() or True if k==65307 else False)
        dlg.add_controller(kc)

        dlg.set_child(box)
        dlg.present()
        GLib.timeout_add(100, lambda: edit_tv.grab_focus() or False)

    def _on_sys_key(self, ctrl, kv, kc, st, tv):
        return False

    def _copy_reply(self, *_):
        for m in reversed(self.history):
            if m['role'] == 'assistant':
                txt = m['content'] if isinstance(m['content'], str) else ""
                if txt:
                    # GTK4 Wayland : passer par Gdk.ContentProvider
                    provider = Gdk.ContentProvider.new_for_value(txt)
                    self.get_clipboard().set_content(provider)
                    self.status.set_text(f"✅ Réponse copiée ({len(txt)} caractères).")
                    return
        self.status.set_text("Aucune réponse à copier.")

    # ── Exporter ──────────────────────────────────────────────
    # ── Exporte la conversation en .txt dans ~/Documents ──────────────────────
    def _export(self, *_):
        if not self.history:
            self.status.set_text("Rien à exporter."); return
        fname = os.path.expanduser(f"~/Documents/deepseek_{self.session_name}.txt")
        with open(fname, 'w') as f:
            f.write(f"Conversation Nseek — {self.session_name}\n")
            f.write("=" * 60 + "\n\n")
            for m in self.history:
                role = "Vous" if m['role']=='user' else "DeepSeek"
                content = m['content'] if isinstance(m['content'],str) else "(multimédia)"
                f.write(f"[{role}]\n{content}\n\n")
        self.status.set_text(f"✅ Exporté : ~/Documents/deepseek_{self.session_name}.txt")

    # ── Web / Quitter ─────────────────────────────────────────
    def _open_web(self, *_):
        Gio.AppInfo.launch_default_for_uri("https://chat.deepseek.com", None)

    def _quit(self, *_):
        if self.history:
            save_session(self.session_name, self.history)
        self.get_application().quit()
        os._exit(0)

    # ── Effacer ───────────────────────────────────────────────
    def _clear(self, *_):
        if self.history: save_session(self.session_name, self.history); self._refresh_sidebar()
        self.history = []; self.buf.set_text(""); self.last_reply = ""
        self.msg_buf.set_text("")  # effacer aussi le champ de saisie
        self.session_name = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M")
        self._msg("info","Conversation effacée."); self.msg_tv.grab_focus()

    # ── Envoi ─────────────────────────────────────────────────
    # ── Envoi d'un message à l'API DeepSeek ──────────────────────────────────
    # regenerate=True : renvoie l'historique sans nouveau message
    def _send(self, *_, regenerate=False):
        import threading
        key  = self._get_key()
        if not key: self._msg("err","Entre ta clé API."); return
        models = ["deepseek-v4-pro","deepseek-v4-flash","deepseek-chat"]
        model  = models[self.model_dd.get_selected()]
        think  = self.think_cb.get_active()
        stream = self.stream_cb.get_active()

        if regenerate:
            messages = [{"role":m["role"],"content":m["content"]} for m in self.history]
            self.send_btn.set_sensitive(False)
            fn = self._call_stream if stream else self._call_sync
            threading.Thread(target=fn, args=(key,model,think,messages), daemon=True).start()
            return

        text = self._get_msg()
        af = self.attached_file
        if af:
            if af['mime'].startswith('image/'):
                self._msg("info", "⚠️ Images non supportées par l'API DeepSeek V4. Utilisez le site web pour les images.")
                self.attached_file = None; self.file_bar.set_visible(False)
                if not text: return
                content = text
                self._msg("you", text)
            else:
                raw, pages = extract_text(af['path'], af['mime'])
                size = len(raw)
                info = f"{size:,} caractères"
                if pages: info += f", {pages} pages PDF"

                if size <= MAX_CHARS:
                    # Fichier entier
                    content = f"[Fichier: {af['name']} — {info}]\n\n{raw}\n\n{text}"
                    self._msg("you", f"📎 {af['name']} ({info})\n{text}")
                else:
                    # Fichier trop long — demander quoi faire
                    trunc = raw[:MAX_CHARS]
                    content = f"[Fichier: {af['name']} — {info} — TRONQUÉ à {MAX_CHARS:,} caractères]\n\n{trunc}\n\n{text}"
                    self._msg("info",
                        f"⚠️ Fichier volumineux ({size:,} car.). "
                        f"Seuls les {MAX_CHARS:,} premiers caractères ont été envoyés.")
                    self._msg("you", f"📎 {af['name']} (tronqué)\n{text}")

                self.attached_file = None; self.file_bar.set_visible(False)
        else:
            content = text; self._msg("you", text)
        self.history.append({"role":"user","content":content})
        messages = self._build_messages()
        self.send_btn.set_sensitive(False)
        self.status.set_text("⏳ Envoi en cours…")
        fn = self._call_stream if stream else self._call_sync
        threading.Thread(target=fn, args=(key,model,think,messages), daemon=True).start()
    # ── API Streaming ─────────────────────────────────────────
    # ── Appel API en mode streaming (thread séparé) ───────────────────────────
    def _call_stream(self, key, model, think, messages):
        body = {"model":model,"messages":messages,"max_tokens":4096,"stream":True,
                "stream_options":{"include_usage":True}}
        if think:
            body["thinking"] = {"type":"enabled"}
            body["reasoning_effort"] = "medium"
        req = urllib.request.Request(
            API_URL, data=json.dumps(body).encode(),
            headers={"Content-Type":"application/json","Authorization":f"Bearer {key}"})

        # Queue partagée entre le thread réseau et le timer GTK
        q = queue.Queue()
        full = []
        done = threading.Event()

        def _drain():
            """Appelé par GLib toutes les 500ms — batch maximal, pas de scroll intermédiaire."""
            items = []
            try:
                while True: items.append(q.get_nowait())
            except queue.Empty: pass
            if items:
                self.buf.begin_irreversible_action()
                for kind, text in items:
                    if kind == 'think': self._ins(text, "think")
                    elif kind == 'body': self._ins(text, "body")
                    elif kind == 'ai_lbl': self._ins(text, "ai")
                    elif kind == 'newline': self._ins("\n", "body")
                self.buf.end_irreversible_action()
                # Scroll seulement si la réponse est terminée
                if done.is_set(): self._scroll()
            return not done.is_set()

        GLib.timeout_add(500, _drain)

        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                q.put(('ai_lbl', "\n🤖 DeepSeek\n"))
                thinking_done = False; in_think = False

                for raw_line in r:
                    line = raw_line.decode('utf-8').strip()
                    if not line.startswith("data: "): continue
                    data_str = line[6:]
                    if data_str == "[DONE]": break
                    try:
                        chunk = json.loads(data_str)
                        usage = chunk.get("usage")
                        if usage and usage.get("prompt_tokens"):
                            self._update_stats(model,
                                usage.get("prompt_tokens",0),
                                usage.get("completion_tokens",0))
                        choices = chunk.get("choices", [])
                        if not choices: continue
                        delta = choices[0].get("delta", {})

                        rc = delta.get("reasoning_content","")
                        if rc and think:
                            if not in_think:
                                q.put(('think', "💭 Raisonnement :\n"))
                                in_think = True
                            q.put(('think', rc))

                        ct = delta.get("content","")
                        if ct:
                            if in_think and not thinking_done:
                                q.put(('newline', ''))
                                thinking_done = True; in_think = False
                            full.append(ct)
                            q.put(('body', ct))
                    except Exception:
                        pass

                q.put(('newline', ''))
                reply = ''.join(full)
                self.last_reply = reply
                self.history.append({"role":"assistant","content":reply})
                save_session(self.session_name, self.history)
                GLib.idle_add(self._refresh_sidebar)
                GLib.idle_add(self.status.set_text, "✅ Réponse reçue.")
                # Re-rendre proprement si la réponse contient du code
                if '```' in reply:
                    GLib.idle_add(self._rerender_last_response, reply)
                else:
                    GLib.idle_add(self._scroll)

        except urllib.error.HTTPError as e:
            body2 = e.read().decode(errors="replace")
            try:    m = json.loads(body2)["error"]["message"]
            except: m = body2[:200]
            if self.history and self.history[-1]['role'] == 'user':
                self.history.pop()
            GLib.idle_add(self._msg, "err", f"HTTP {e.code} — {m}", "")
            GLib.idle_add(self.status.set_text, "Erreur.")
        except Exception as e:
            if self.history and self.history[-1]['role'] == 'user':
                self.history.pop()
            GLib.idle_add(self._msg, "err", str(e), "")
            GLib.idle_add(self.status.set_text, "Erreur réseau.")
        finally:
            done.set()
            GLib.idle_add(self.send_btn.set_sensitive, True)
            GLib.idle_add(self.msg_tv.grab_focus)

    # ── API Sync ──────────────────────────────────────────────
    # ── Appel API en mode synchrone (thread séparé) ──────────────────────────
    def _call_sync(self, key, model, think, messages):
        body = {"model":model,"messages":messages,"max_tokens":4096}
        if think: body["thinking"]={"type":"enabled"}; body["reasoning_effort"]="medium"
        req = urllib.request.Request(
            API_URL, data=json.dumps(body).encode(),
            headers={"Content-Type":"application/json","Authorization":f"Bearer {key}"})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                d = json.load(r); msg = d["choices"][0]["message"]
                reply = msg.get("content",""); rthink = msg.get("reasoning_content","") if think else ""
                if "usage" in d:
                    u = d["usage"]
                    self._update_stats(model, u.get("prompt_tokens",0), u.get("completion_tokens",0))
                self.last_reply = reply
                self.history.append({"role":"assistant","content":reply})
                save_session(self.session_name, self.history)
                GLib.idle_add(self._msg, "ai", reply, rthink)
                GLib.idle_add(self._refresh_sidebar)
        except urllib.error.HTTPError as e:
            body2 = e.read().decode(errors="replace")
            try:    m = json.loads(body2)["error"]["message"]
            except: m = body2[:200]
            GLib.idle_add(self._msg, "err", f"HTTP {e.code} — {m}", "")
            GLib.idle_add(self.status.set_text, "Erreur.")
        except Exception as e:
            GLib.idle_add(self._msg, "err", str(e), "")
        GLib.idle_add(self.send_btn.set_sensitive, True)
        GLib.idle_add(self.msg_tv.grab_focus)

    # ── Stats ─────────────────────────────────────────────────
    def _update_stats(self, model, in_tok, out_tok):
        costs = COSTS.get(model, {"in":0.14,"out":0.28})
        cost  = (in_tok * costs["in"] + out_tok * costs["out"]) / 1_000_000
        self.session_in   += in_tok
        self.session_out  += out_tok
        self.total_tokens += in_tok + out_tok
        self.total_cost   += cost
        self._refresh_stats(in_tok, out_tok, cost)


# ─────────────────────────────────────────────────────────────────────────────
# Application GTK4 — point d'entrée, gère le splash screen puis lance Win
# ─────────────────────────────────────────────────────────────────────────────
class App(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="fr.local.nseek")
        self.set_resource_base_path(None)
    def do_activate(self):
        self._show_splash()

    # ── Écran de démarrage animé avec logo et barre de progression ───────────
    def _show_splash(self):
        splash = Gtk.Window(title="Nseek")
        splash.set_default_size(860, 460)
        splash.set_resizable(False)
        splash.set_decorated(False)

        splash_css = Gtk.CssProvider()
        splash_css.load_from_string("""
            window { background-color:#0d2545; }
            .splash-loading { color:#4a8fd4; font-size:10pt; }
            progressbar trough { background-color:#1a3a6a; border-radius:6px; min-height:8px; }
            progressbar progress { background-color:#2d8fe0; border-radius:6px; min-height:8px; }
        """)
        Gtk.StyleContext.add_provider_for_display(
            splash.get_display(), splash_css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 10)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        box.set_vexpand(True); box.set_hexpand(True)
        box.set_valign(Gtk.Align.CENTER); box.set_halign(Gtk.Align.CENTER)
        box.set_margin_top(20); box.set_margin_bottom(20)
        box.set_margin_start(20); box.set_margin_end(20)
        splash.set_child(box)

        # Logo splash — version standard qui fonctionne
        base = os.path.dirname(os.path.abspath(__file__))
        logo_path = os.path.join(base, "assets", "nseek-logo.png")
        if os.path.exists(logo_path):
            from gi.repository import GdkPixbuf, Gdk as GdkLocal
            pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(logo_path, 700, 320, True)
            texture = GdkLocal.Texture.new_for_pixbuf(pb)
            pic = Gtk.Picture.new_for_paintable(texture)
            pic.set_size_request(600, 270)
            pic.set_can_shrink(True)
            pic.set_hexpand(True)
            box.append(pic)

        self._progress = Gtk.ProgressBar()
        self._progress.set_margin_start(40); self._progress.set_margin_end(40)
        self._progress.set_fraction(0.0)
        box.append(self._progress)

        lbl = Gtk.Label(label="Chargement…"); lbl.add_css_class("splash-loading")
        lbl.set_margin_top(8)
        box.append(lbl)

        # 9. Espacement entre les lignes
        pw_lbl = Gtk.Label()
        pw_lbl.set_markup('<span font="12" font_weight="bold" foreground="#7aaad0">powered by DeepSeek V4</span>')
        pw_lbl.set_margin_top(6)
        box.append(pw_lbl)

        copy_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        copy_box.set_halign(Gtk.Align.CENTER)
        copy_box.set_margin_top(4); copy_box.set_margin_bottom(8)
        try:
            from gi.repository import GdkPixbuf, Gdk as _GdkI
            _icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets', 'nseek-icon-ciel.png')
            if os.path.exists(_icon_path):
                _pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(_icon_path, 84, 84, True)
                _tex = _GdkI.Texture.new_for_pixbuf(_pb)
                _img = Gtk.Picture.new_for_paintable(_tex)
                _img.set_size_request(84, 84)
                _img.set_can_shrink(False)
                copy_box.append(_img)
        except Exception: pass
        copy_lbl = Gtk.Label()
        copy_lbl.set_markup('<span font="11" font_weight="bold" foreground="#90d8ff">© 2026 carafife — Nseek v1.0 — GPL v3</span>')
        copy_box.append(copy_lbl)
        box.append(copy_box)

        splash.present()
        self._splash = splash
        self._progress_val = 0.0
        self._main_win = Win(self)
        GLib.timeout_add(55, self._update_progress)

    # ── Animation de la barre de progression du splash ────────────────────────
    def _update_progress(self):
        self._progress_val += 0.022
        self._progress.set_fraction(min(self._progress_val, 1.0))
        if self._progress_val >= 1.0:
            self._splash.destroy()
            self._main_win.present()
            return False
        return True

# ── Point d'entrée principal ─────────────────────────────────────────────────
if __name__ == "__main__": App().run()
