#!/usr/bin/env python3
import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib, Gio, Gdk, Pango
import urllib.request, urllib.error
import json, threading, queue, os, base64, datetime, re, signal, sys

signal.signal(signal.SIGINT, lambda *_: os._exit(0))
try:
    from gi.repository import GLibUnix
    GLibUnix.signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, lambda: os._exit(0))
except ImportError:
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, lambda: os._exit(0))

API_URL  = "https://api.deepseek.com/v1/chat/completions"
HIST_DIR = os.path.expanduser("~/.local/share/deepseek-chat")
KEY_FILE = os.path.expanduser("~/Documents/cle_deepseek_v4_api.txt")
os.makedirs(HIST_DIR, exist_ok=True)

# Coût estimé par million de tokens (USD)
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

MAX_CHARS = 100_000

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

CSS_DARK = """
window { background:#242424; }
headerbar { background:#141414; border-bottom:1px solid #2a2a2a; }
headerbar windowcontrols button { background:transparent; }
.app-title { font-weight:bold; font-size:12pt; color:#d0d0d0; }
.app-sub   { font-size:9pt; color:#606060; }
.sidebar { background:#1e1e1e; border-right:1px solid #333333; min-width:200px; }
.sidebar-title { color:#a0a0a0; font-size:9pt; font-weight:bold; padding:8px 12px 4px; letter-spacing:1px; }
.cfg     { background:#2a2a2a; padding:8px 10px; margin:0 10px 6px; border-radius:10px; border:1px solid #383838; }
.lbl     { color:#909090; font-size:10pt; }
checkbutton label { color:#d0d0d0; font-size:10pt; }
textview { background:#242424; color:#e8e8e8; }
textview text { background:#242424; color:#e8e8e8; }
.input-tv textview, .input-tv textview text { background:#1a1a1a; color:#e8e8e8; }
.input-tv { border:1px solid #444444; border-radius:7px; padding:2px; }
.input-tv:focus-within { border-color:#3584e4; }
.send  { background:#3584e4; color:#fff; font-weight:bold; border-radius:7px; padding:5px 14px; }
.send:hover { background:#4a94f0; }
.send:disabled { background:#383838; color:#606060; }
.tool  { background:#2a2a2a; color:#d0d0d0; border-radius:7px; padding:4px 9px; border:1px solid #404040; }
.tool:hover { background:#353535; }
.sess-row { padding:7px 10px; border-bottom:1px solid #2a2a2a; }
.sess-name { color:#d0d0d0; font-size:10pt; }
.del-btn { background:transparent; color:#606060; border-radius:5px; padding:2px 6px; font-size:10pt; border:none; }
.del-btn:hover { background:#3a2020; color:#f66151; }
.new-sess { background:#252525; color:#909090; border-radius:0; padding:8px 12px; font-size:10pt; border-bottom:1px solid #333; }
.new-sess:hover { background:#2d2d2d; color:#d0d0d0; }
.status { color:#606060; font-size:9pt; padding:2px 12px 4px; }
.search-bar { background:#1e1e1e; padding:4px 10px; border-bottom:1px solid #333; }
.toggle, .theme-btn, .web-btn, .hdr-btn { background:transparent; color:#606060; border-radius:6px; padding:4px 9px; border:none; }
.toggle:hover, .theme-btn:hover, .web-btn:hover, .hdr-btn:hover { background:#1e1e1e; color:#d0d0d0; }
.quit-btn { background:transparent; color:#f66151; border-radius:6px; padding:4px 9px; border:none; font-weight:bold; }
.quit-btn:hover { background:#3a1a1a; color:#ff8070; }
"""

CSS_LIGHT = """
window { background:#eeeae6; }
headerbar { background:#e4e0dc; border-bottom:1px solid #ccc8c4; }
headerbar windowcontrols button { background:transparent; }
.app-title { font-weight:bold; font-size:12pt; color:#2a2a2a; }
.app-sub   { font-size:9pt; color:#888888; }
.sidebar { background:#e8e4e0; border-right:1px solid #ccc8c4; min-width:200px; }
.sidebar-title { color:#888888; font-size:9pt; font-weight:bold; padding:8px 12px 4px; letter-spacing:1px; }
.cfg     { background:#e4e0dc; padding:8px 10px; margin:0 10px 6px; border-radius:10px; border:1px solid #ccc8c4; }
.lbl     { color:#666666; font-size:10pt; }
checkbutton label { color:#2a2a2a; font-size:10pt; }
textview { background:#eeeae6; color:#1a1a1a; }
textview text { background:#eeeae6; color:#1a1a1a; }
.input-tv textview, .input-tv textview text { background:#f5f2ef; color:#1a1a1a; }
.input-tv { border:1px solid #bab6b2; border-radius:7px; padding:2px; }
.input-tv:focus-within { border-color:#3584e4; }
.send  { background:#3584e4; color:#fff; font-weight:bold; border-radius:7px; padding:5px 14px; }
.send:hover { background:#1c6fd0; }
.send:disabled { background:#c8c4c0; color:#989490; }
.tool  { background:#e4e0dc; color:#3a3a3a; border-radius:7px; padding:4px 9px; border:1px solid #c8c4c0; }
.tool:hover { background:#dedad6; }
.sess-row { padding:7px 10px; border-bottom:1px solid #dedad6; }
.sess-name { color:#2a2a2a; font-size:10pt; }
.del-btn { background:transparent; color:#b0aca8; border-radius:5px; padding:2px 6px; font-size:10pt; border:none; }
.del-btn:hover { background:#f5d0d0; color:#c01c28; }
.new-sess { background:#e8e4e0; color:#666666; border-radius:0; padding:8px 12px; font-size:10pt; border-bottom:1px solid #d0ccc8; }
.new-sess:hover { background:#dedad6; color:#1a1a1a; }
.status { color:#909090; font-size:9pt; padding:2px 12px 4px; }
.search-bar { background:#e8e4e0; padding:4px 10px; border-bottom:1px solid #ccc8c4; }
.toggle, .theme-btn, .web-btn, .hdr-btn { background:transparent; color:#888888; border-radius:6px; padding:4px 9px; border:none; }
.toggle:hover, .theme-btn:hover, .web-btn:hover, .hdr-btn:hover { background:#d8d4d0; color:#1a1a1a; }
.quit-btn { background:transparent; color:#c01c28; border-radius:6px; padding:4px 9px; border:none; font-weight:bold; }
.quit-btn:hover { background:#fce4e4; color:#a0001a; }
"""

TAGS_DARK = {
    "you":   {"foreground":"#78aeed","weight":700},
    "ai":    {"foreground":"#57e389","weight":700},
    "err":   {"foreground":"#f66151","weight":700},
    "think": {"foreground":"#c061cb","style":2},
    "body":  {"foreground":"#e8e8e8"},
    "code":  {"foreground":"#8ff0a4","family":"Monospace","background":"#1a1a1a"},
    "bold":  {"foreground":"#ffbe6f","weight":700},
    "info":  {"foreground":"#606060","style":2},
    "hl":    {"background":"#b8860b","foreground":"#ffffff"},
}
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

class Win(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Nseek")
        self.set_default_size(960, 700)
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
    def _build_headerbar(self):
        hb = Gtk.HeaderBar()
        hb.set_show_title_buttons(True)
        self.set_titlebar(hb)

        self.toggle_btn = Gtk.Button(label="☰")
        self.toggle_btn.add_css_class("toggle"); self.toggle_btn.set_focusable(False)
        self.toggle_btn.set_tooltip_text("Historique  [Ctrl+H]")
        self.toggle_btn.connect("clicked", self._toggle_sidebar)
        hb.pack_start(self.toggle_btn)

        tb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        tb.set_valign(Gtk.Align.CENTER)
        t1 = Gtk.Label(label="Nseek"); t1.add_css_class("app-title")
        t2 = Gtk.Label(label="Client IA natif GTK4"); t2.add_css_class("app-sub")
        tb.append(t1); tb.append(t2)
        hb.set_title_widget(tb)

        # Boutons droite
        for label, tooltip, cb, cls in [
            ("🔍",      "Rechercher  [Ctrl+F]",              self._toggle_search, "hdr-btn"),
            ("A-",      "Police plus petite",                 self._font_smaller,  "hdr-btn"),
            ("A+",      "Police plus grande",                 self._font_bigger,   "hdr-btn"),
            ("📋 Copier","Copier dernière réponse [Ctrl+⇧+C]",self._copy_reply,   "hdr-btn"),
            ("💾 Export","Exporter conversation  [Ctrl+E]",   self._export,        "hdr-btn"),
            ("🌐 Web",  "Ouvrir DeepSeek Web  [Ctrl+B]",     self._open_web,      "web-btn"),
            ("❓ Aide", "Aide  [Ctrl+?]",                     self._show_help,     "hdr-btn"),
            ("☀️",      "Thème clair/sombre  [Ctrl+T]",       self._switch_theme,  "theme-btn"),
            ("✕",       "Quitter  [Ctrl+Q]",                  self._quit,          "quit-btn"),
        ]:
            b = Gtk.Button(label=label); b.add_css_class(cls)
            b.set_focusable(False); b.set_tooltip_text(tooltip)
            b.connect("clicked", cb)
            if label == "☀️": self.theme_btn = b
            hb.pack_end(b)

    # ── Sidebar ───────────────────────────────────────────────
    def _build_sidebar(self):
        self.sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.sidebar.add_css_class("sidebar")
        self.sidebar.set_size_request(210, -1)
        title = Gtk.Label(label="CONVERSATIONS"); title.add_css_class("sidebar-title"); title.set_xalign(0)
        self.sidebar.append(title)
        nb = Gtk.Button(label="＋  Nouvelle conversation")
        nb.add_css_class("new-sess"); nb.set_focusable(False)
        nb.connect("clicked", self._new_session)
        self.sidebar.append(nb)
        sw = Gtk.ScrolledWindow(); sw.set_vexpand(True)
        self.sess_list = Gtk.ListBox()
        self.sess_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.sess_list.connect("row-activated", self._load_sess_row)
        sw.set_child(self.sess_list)
        self.sidebar.append(sw)
        self.paned.set_start_child(self.sidebar)
        self.paned.set_position(210)
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
    def _build_main(self, root):
        main = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        main.set_hexpand(True)

        # Config
        cfg = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        cfg.add_css_class("cfg")
        for lbl_txt, attr, vis, hint in [
            ("Clé API :", "key", False, "sk-..."),
            ("System :", "sys", True, "Instructions permanentes pour le modèle"),
        ]:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            l = Gtk.Label(label=lbl_txt); l.add_css_class("lbl"); l.set_size_request(65,-1)
            buf = Gtk.TextBuffer()
            tv  = Gtk.TextView(buffer=buf)
            tv.set_wrap_mode(Gtk.WrapMode.WORD_CHAR); tv.set_accepts_tab(False)
            tv.set_size_request(-1, 34); tv.set_hexpand(True)
            tv.set_top_margin(6); tv.set_bottom_margin(6)
            tv.set_left_margin(6); tv.set_right_margin(6)
            wrap = Gtk.Box(); wrap.add_css_class("input-tv"); wrap.set_hexpand(True); wrap.append(tv)
            row.append(l); row.append(wrap); cfg.append(row)
            setattr(self, f"{attr}_buf", buf); setattr(self, f"{attr}_tv", tv)

        self.sys_buf.set_text("Tu es un assistant serviable. Réponds toujours en français.")

        r2 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        l2 = Gtk.Label(label="Modèle :"); l2.add_css_class("lbl"); l2.set_size_request(65,-1)
        self.model_dd = Gtk.DropDown.new_from_strings(["deepseek-v4-pro","deepseek-v4-flash","deepseek-chat"])
        self.model_dd.set_selected(0); self.model_dd.set_focusable(False)
        self.think_cb = Gtk.CheckButton(label="🧠 Thinking"); self.think_cb.set_focusable(False)
        self.stream_cb = Gtk.CheckButton(label="⚡ Streaming"); self.stream_cb.set_active(True); self.stream_cb.set_focusable(False)
        r2.append(l2); r2.append(self.model_dd); r2.append(self.think_cb); r2.append(self.stream_cb)
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
        csw.set_focusable(False)
        csw.set_margin_start(10); csw.set_margin_end(10); csw.set_margin_bottom(4)

        # Drag & drop sur la fenêtre principale (plus fiable sur Wayland)
        drop = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
        drop.connect("drop", self._on_drop)
        drop.connect("enter", lambda *_: Gdk.DragAction.COPY)
        csw.add_controller(drop)
        main.append(csw)

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
        mw = Gtk.Box(); mw.add_css_class("input-tv"); mw.set_hexpand(True); mw.append(self.msg_tv)
        kc = Gtk.EventControllerKey(); kc.connect("key-pressed", self._on_key); self.msg_tv.add_controller(kc)
        bar.append(mw)
        clr = Gtk.Button(label="🗑"); clr.add_css_class("tool"); clr.set_focusable(False)
        clr.set_tooltip_text("Effacer [Ctrl+L]"); clr.connect("clicked", self._clear); bar.append(clr)
        self.send_btn = Gtk.Button(label="Envoyer ➤"); self.send_btn.add_css_class("send")
        self.send_btn.set_focusable(False); self.send_btn.connect("clicked", self._send)
        bar.append(self.send_btn)
        main.append(bar)
        self.paned.set_end_child(main)

    def _build_statusbar(self, root):
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        bar.set_margin_start(12); bar.set_margin_end(12)
        bar.set_margin_top(4); bar.set_margin_bottom(6)

        self.status = Gtk.Label(label="Prêt.")
        self.status.set_xalign(0); self.status.set_hexpand(True)
        self.status.add_css_class("status")
        bar.append(self.status)

        self.stats_lbl = Gtk.Label()
        self.stats_lbl.set_xalign(1)
        bar.append(self.stats_lbl)
        root.append(bar)
        self._refresh_stats(0, 0, 0.0)  # initialisation à zéro

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
    def _setup_shortcuts(self):
        kc = Gtk.EventControllerKey()
        kc.connect("key-pressed", self._on_window_key)
        self.add_controller(kc)

    def _on_window_key(self, ctrl, kv, kc, st):
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

    def _show_help(self, *_):
        dlg = Gtk.Dialog(title="Aide — Nseek", transient_for=self, modal=True)
        dlg.set_default_size(560, 600)
        box = dlg.get_content_area()
        box.set_margin_top(16); box.set_margin_bottom(16)
        box.set_margin_start(16); box.set_margin_end(16); box.set_spacing(8)

        title = Gtk.Label()
        title.set_markup('<span font="14" font_weight="bold" foreground="#3584e4">🤖 Nseek — Aide</span>')
        title.set_xalign(0); box.append(title)

        sep = Gtk.Separator(); box.append(sep)

        fg  = "#e0e0e0" if self.is_dark else "#1a1a1a"
        acc = "#78aeed" if self.is_dark else "#1c71d8"
        grn = "#57e389" if self.is_dark else "#26a269"

        help_text = f"""<span foreground="{fg}">
<b><span foreground="{acc}">🖊️ SAISIE</span></b>
• <b>Entrée</b> → Envoyer le message
• <b>Maj+Entrée</b> → Saut de ligne
• <b>📎</b> → Joindre un fichier ou une image
• Glisser-déposer un fichier dans la fenêtre de chat

<b><span foreground="{acc}">🤖 MODÈLES</span></b>
• <b>deepseek-v4-pro</b> → Le plus puissant, pour les tâches complexes
• <b>deepseek-v4-flash</b> → Rapide et économique
• <b>deepseek-chat</b> → Modèle standard

<b><span foreground="{acc}">⚙️ OPTIONS</span></b>
• <b>🧠 Thinking</b> → Affiche le raisonnement interne du modèle
• <b>⚡ Streaming</b> → Affiche la réponse au fil de l'eau
• <b>System</b> → Instruction permanente envoyée à chaque requête
• <b>A+ / A-</b> → Ajuste la taille de la police du chat

<b><span foreground="{acc}">⌨️ RACCOURCIS CLAVIER</span></b>
• <b>Ctrl+N</b> → Nouvelle conversation
• <b>Ctrl+L</b> → Effacer la conversation
• <b>Ctrl+F</b> → Rechercher dans la conversation
• <b>Ctrl+E</b> → Exporter la conversation (.txt dans Documents)
• <b>Ctrl+Shift+C</b> → Copier la dernière réponse
• <b>Ctrl+H</b> → Afficher/masquer l'historique
• <b>Ctrl+T</b> → Basculer thème clair/sombre
• <b>Ctrl+B</b> → Ouvrir DeepSeek Web dans le navigateur
• <b>Ctrl+Q</b> → Quitter l'application

<b><span foreground="{acc}">📋 CHAT</span></b>
• Cliquer-glisser pour sélectionner du texte dans le chat
• <b>Ctrl+C</b> sur une sélection pour la copier
• <b>📋 Copier</b> → Copie la dernière réponse complète

<b><span foreground="{acc}">📂 HISTORIQUE</span></b>
• Les conversations sont sauvegardées automatiquement
• Le titre est extrait du premier message
• Cliquer sur une session pour la recharger
• <b>🗑</b> → Supprimer une session

<b><span foreground="{acc}">💰 STATS (barre du bas)</span></b>
• <span foreground="{grn}">⬆</span> = tokens envoyés  •  <b>⬇</b> = tokens reçus
• <b>💰</b> = coût de l'échange  •  total cumulé de la session
</span>"""
        lbl = Gtk.Label(); lbl.set_markup(help_text.strip())
        lbl.set_xalign(0); lbl.set_wrap(True); lbl.set_wrap_mode(2)

        sw = Gtk.ScrolledWindow(); sw.set_child(lbl); sw.set_vexpand(True)
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        box.append(sw)

        close_btn = Gtk.Button(label="Fermer"); close_btn.add_css_class("send")
        close_btn.set_halign(Gtk.Align.END)
        close_btn.connect("clicked", lambda *_: dlg.destroy())
        box.append(close_btn)

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
        if s: msgs.append({"role":"system","content":s})
        msgs.extend(self.history)
        return msgs

    # ── Clé API ───────────────────────────────────────────────
    def _load_key(self):
        try:
            with open(KEY_FILE) as f: self.key_buf.set_text(f.read().strip())
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

    def _ins(self, text, *tags):
        it = self.buf.get_end_iter()
        if tags: self.buf.insert_with_tags_by_name(it, text, *tags)
        else:    self.buf.insert(it, text)

    def _scroll(self):
        self.view.scroll_to_iter(self.buf.get_end_iter(), 0, False, 0, 1)

    def _render(self, text):
        for p in re.split(r'(```[\w]*\n.*?```)', text, flags=re.DOTALL):
            if p.startswith('```'):
                self._ins(re.sub(r'^```\w*\n?','',p).rstrip('`\n') + "\n", "code")
            else:
                for line in p.split('\n'):
                    for seg in re.split(r'(\*\*[^*]+\*\*|`[^`]+`)', line):
                        if seg.startswith('**') and seg.endswith('**'): self._ins(seg[2:-2], "bold")
                        elif seg.startswith('`') and seg.endswith('`'):  self._ins(seg[1:-1], "code")
                        else: self._ins(seg, "body")
                    self._ins('\n', "body")

    def _msg(self, kind, text, thinking=""):
        if kind == "you":   self._ins("\n🧑 Toi\n", "you")
        elif kind == "ai":  self._ins("\n🤖 DeepSeek\n", "ai")
        elif kind == "err": self._ins("\n⚠️  Erreur\n", "err")
        elif kind == "info":
            self._ins(text + "\n", "info"); GLib.idle_add(self._scroll); return
        if thinking: self._ins("💭 Raisonnement :\n","think"); self._render(thinking)
        self._render(text); self._ins("\n","body"); GLib.idle_add(self._scroll)

    # ── Thème ─────────────────────────────────────────────────
    def _switch_theme(self, *_):
        self.is_dark = not self.is_dark
        self.css_provider.load_from_string(CSS_DARK if self.is_dark else CSS_LIGHT)
        self.theme_btn.set_label("☀️" if self.is_dark else "🌙")
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
        self.session_name = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M")
        self._msg("info","Conversation effacée."); self.msg_tv.grab_focus()

    # ── Envoi ─────────────────────────────────────────────────
    def _send(self, *_):
        key  = self._get_key()
        text = self._get_msg()
        if not key:   self._msg("err","Entre ta clé API."); return
        if not text and not self.attached_file: return
        models = ["deepseek-v4-pro","deepseek-v4-flash","deepseek-chat"]
        model  = models[self.model_dd.get_selected()]
        think  = self.think_cb.get_active()
        stream = self.stream_cb.get_active()
        self.msg_buf.set_text("")
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
                GLib.idle_add(self._scroll)  # scroll final une seule fois

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


class App(Gtk.Application):
    def __init__(self): super().__init__(application_id="fr.local.deepseek-v4")
    def do_activate(self):
        win = Win(self)
        # Icône de la fenêtre
        icon_path = os.path.join(os.path.dirname(__file__), "assets", "nseek-icon-ciel.svg")
        if os.path.exists(icon_path):
            win.set_icon_name(icon_path)
        win.present()

if __name__ == "__main__": App().run()
