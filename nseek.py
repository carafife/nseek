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
window { background:#060d1a; }
headerbar { background:#080f1e; border-bottom:1px solid #152238; }
headerbar windowcontrols button { background:transparent; }
.app-title { font-weight:bold; font-size:12pt; color:#c8ddf0; letter-spacing:2px; }
.app-sub   { font-size:9pt; color:#2a5a9a; letter-spacing:3px; }
.sidebar { background:#060d1a; border-right:1px solid #152238; min-width:200px; }
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
.new-sess { background:#09142a; color:#4a8ac0; border-radius:0; padding:10px 12px; font-size:10pt; border:none; border-bottom:1px solid #152238; border-top:1px solid #152238; letter-spacing:1px; outline:none; box-shadow:none; }
.new-sess:hover { background:#0d1f3c; color:#7aaad0; }
.new-sess:focus { outline:none; box-shadow:none; border:none; border-bottom:1px solid #152238; border-top:1px solid #152238; }
.status { color:#1e3a5f; font-size:9pt; padding:2px 12px 4px; }
.search-bar { background:#060d1a; padding:4px 10px; border-bottom:1px solid #152238; }
.toggle, .theme-btn, .web-btn, .hdr-btn { background:transparent; color:#2a5a9a; border-radius:5px; padding:4px 9px; border:none; }
.toggle:hover, .theme-btn:hover, .web-btn:hover, .hdr-btn:hover { background:#09142a; color:#7aaad0; }
.quit-btn { background:transparent; color:#c04040; border-radius:5px; padding:4px 9px; border:none; font-weight:bold; }
.quit-btn:hover { background:#1a0808; color:#e05555; }
.vtoolbar { background:#060d1a; border-left:1px solid #152238; }
.vtool { background:transparent; color:#2a5a9a; border-radius:5px; padding:6px; border:none; font-size:14pt; min-width:36px; }
.vtool:hover { background:#09142a; color:#7aaad0; }
.vtool.quit-btn { color:#c04040; }
.vtool.quit-btn:hover { background:#1a0808; color:#e05555; }
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

CSS_LIGHT = """
window { background:#c8d8f0; }
headerbar { background:#b8ccec; border-bottom:1px solid #8aacd8; }
headerbar windowcontrols button { background:transparent; }
.app-title { font-weight:bold; font-size:12pt; color:#0d2545; letter-spacing:2px; }
.app-sub   { font-size:9pt; color:#1a4f8a; letter-spacing:3px; }
.sidebar { background:#bccce8; border-right:1px solid #8aacd8; min-width:200px; }
.sidebar-title { color:#1a4f8a; font-size:9pt; font-weight:bold; padding:10px 12px 8px; letter-spacing:3px; border-bottom:1px solid #8aacd8; margin-bottom:4px; }
.cfg     { background:#b0c4e0; padding:8px 10px; margin:0 10px 6px; border-radius:6px; border:1px solid #8aacd8; }
.lbl     { color:#1a4f8a; font-size:10pt; }
checkbutton label { color:#0d2545; font-size:10pt; }
textview { background:#c8d8f0; color:#0d2545; }
textview text { background:#c8d8f0; color:#0d2545; }
.input-tv textview, .input-tv textview text { background:#b8ccec; color:#0d2545; }
.input-tv { border:1px solid #8aacd8; border-radius:5px; padding:2px; }
.input-tv:focus-within { border-color:#1a4f8a; }
.send  { background:#1a4f8a; color:#e0eeff; font-weight:bold; border-radius:5px; padding:5px 14px; letter-spacing:1px; }
.send:hover { background:#0d3566; color:#ffffff; }
.send:disabled { background:#8aacd8; color:#6888a8; }
.tool  { background:#b0c4e0; color:#1a4f8a; border-radius:5px; padding:4px 9px; border:1px solid #8aacd8; }
.tool:hover { background:#9ab8d4; color:#0d2545; }
.sess-row { padding:7px 10px; border-bottom:1px solid #a8bcd8; background:#bccce8; }
.sess-name { color:#0d2545; font-size:10pt; }
.del-btn { background:transparent; color:#8aacd8; border-radius:5px; padding:2px 6px; font-size:10pt; border:none; }
.del-btn:hover { background:#f5d0d0; color:#c01c28; }
.new-sess { background:#bccce8; color:#1a4f8a; border-radius:0; padding:10px 12px; font-size:10pt; border:none; border-bottom:1px solid #8aacd8; border-top:1px solid #8aacd8; letter-spacing:1px; }
.new-sess:hover { background:#b0c4e0; color:#0d2545; }
.status { color:#4a7aaa; font-size:9pt; padding:2px 12px 4px; }
.search-bar { background:#bccce8; padding:4px 10px; border-bottom:1px solid #8aacd8; }
.toggle, .theme-btn, .web-btn, .hdr-btn { background:transparent; color:#1a4f8a; border-radius:5px; padding:4px 9px; border:none; }
.toggle:hover, .theme-btn:hover, .web-btn:hover, .hdr-btn:hover { background:#9ab8d4; color:#0d2545; }
.quit-btn { background:transparent; color:#c01c28; border-radius:5px; padding:4px 9px; border:none; font-weight:bold; }
.quit-btn:hover { background:#f5d0d0; color:#a0001a; }
.vtoolbar { background:#bccce8; border-left:1px solid #8aacd8; }
.vtool { background:transparent; color:#1a4f8a; border-radius:5px; padding:6px; border:none; font-size:14pt; min-width:36px; }
.vtool:hover { background:#9ab8d4; color:#0d2545; }
.vtool.quit-btn { color:#c01c28; }
.vtool.quit-btn:hover { background:#f5d0d0; color:#a0001a; }
.code-copy-btn { background:#b0c4d8; color:#0d2545; border:1px solid #8aacd8; border-radius:4px; padding:3px 10px; font-size:9pt; }
.code-copy-btn:hover { background:#9ab8d4; color:#060f22; }
.code-header { background:#a8c0d8; padding:4px 8px; border-radius:6px 6px 0 0; border-bottom:1px solid #8aacd8; }
.code-lang { color:#0d2545; font-size:9pt; font-weight:bold; letter-spacing:1px; }
listbox { background:#bccce8; border:none; }
listbox row { background:#bccce8; border:none; }
listbox row:hover { background:#b0c4e0; }
listbox row:selected { background:#9ab8d4; border:none; }
scrolledwindow { background:#bccce8; border:none; }
viewport { background:#bccce8; border:none; }
"""

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
    def _build_headerbar(self):
        hb = Gtk.HeaderBar()
        hb.set_show_title_buttons(True)
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

        for w in [btn_credits, btn_web]:
            hb.pack_end(w)

    def _build_toolbar(self, root):
        """Barre d'icônes verticale à droite de la zone de chat."""
        pass  # injectée dans _build_main via overlay

    # ── Sidebar ───────────────────────────────────────────────
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
        # Conteneur horizontal : zone principale + toolbar verticale
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        hbox.set_hexpand(True); hbox.set_vexpand(True)

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
        mw = Gtk.Box(); mw.add_css_class("input-tv"); mw.set_hexpand(True); mw.append(self.msg_tv)
        kc = Gtk.EventControllerKey(); kc.connect("key-pressed", self._on_key); self.msg_tv.add_controller(kc)
        bar.append(mw)
        clr = Gtk.Button(label="🗑"); clr.add_css_class("tool"); clr.set_focusable(False)
        clr.set_tooltip_text("Effacer [Ctrl+L]"); clr.connect("clicked", self._clear); bar.append(clr)
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
            ("A+", "Police plus grande",              self._font_bigger),
            ("A−", "Police plus petite",              self._font_smaller),
            None,
            ("🔖", "Nouvelle conversation  [Ctrl+N]", self._new_session),
            ("🗑",  "Effacer  [Ctrl+L]",              self._clear),
            None,
            ("❓", "Aide",                            self._show_help),
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
                if lbl == "✕": btn.add_css_class("quit-btn")
                btn.set_focusable(False); btn.set_tooltip_text(tip)
                btn.connect("clicked", cb)
                toolbar.append(btn)

        hbox.append(main)
        hbox.append(toolbar)
        self.paned.set_end_child(hbox)

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
                # Extraire le langage et le code
                lines = p.split('\n')
                lang = lines[0].replace('```','').strip()
                code = '\n'.join(lines[1:]).rstrip('`\n')

                # Insérer le bouton copier via ChildAnchor
                GLib.idle_add(self._insert_code_block, lang, code)
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
        scheme_id = "oblivion" if self.is_dark else "classic"
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
        """Après streaming, efface la dernière réponse et la re-rend avec détection de code."""
        # Trouver le dernier "🤖 DeepSeek" dans le buffer
        start = self.buf.get_start_iter()
        end   = self.buf.get_end_iter()
        marker = "🤖 DeepSeek"
        found = None
        it = self.buf.get_start_iter()
        while True:
            res = it.forward_search(marker, Gtk.TextSearchFlags.VISIBLE_ONLY, end)
            if not res: break
            found = res[0]
            it = res[1]
        if not found: self._scroll(); return

        # Supprimer tout après le marqueur AI jusqu'à la fin
        found.forward_chars(len(marker))
        self.buf.delete(found, self.buf.get_end_iter())

        # Re-rendre proprement
        self._ins("\n", "body")
        self._render(reply)
        self._ins("\n", "body")
        self._scroll()

    def _copy_code(self, code, lang, btn):
        provider = Gdk.ContentProvider.new_for_value(code)
        self.get_clipboard().set_content(provider)
        original = btn.get_label()
        btn.set_label("✅ Copié !")
        self.status.set_text(f"✅ Code {lang or ''} copié ({len(code)} caractères)")
        GLib.timeout_add(2000, lambda: btn.set_label(original) or False)

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
    def __init__(self):
        super().__init__(application_id="fr.local.nseek")
        self.set_resource_base_path(None)
    def do_activate(self):
        self._show_splash()

    def _show_splash(self):
        splash = Gtk.Window(title="Nseek")
        splash.set_default_size(700, 380)
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
        box.set_margin_top(40); box.set_margin_bottom(40)
        box.set_margin_start(60); box.set_margin_end(60)
        splash.set_child(box)

        logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "nseek-logo.png")
        if os.path.exists(logo_path):
            from gi.repository import GdkPixbuf, Gdk as GdkLocal
            pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(logo_path, 580, 265, True)
            texture = GdkLocal.Texture.new_for_pixbuf(pb)
            pic = Gtk.Picture.new_for_paintable(texture)
            pic.set_size_request(580, 265)
            pic.set_can_shrink(False)
            box.append(pic)

        self._progress = Gtk.ProgressBar()
        self._progress.set_margin_start(40); self._progress.set_margin_end(40)
        self._progress.set_fraction(0.0)
        box.append(self._progress)

        lbl = Gtk.Label(label="Chargement…"); lbl.add_css_class("splash-loading")
        box.append(lbl)

        splash.present()
        self._splash = splash
        self._progress_val = 0.0
        self._main_win = Win(self)
        GLib.timeout_add(55, self._update_progress)

    def _update_progress(self):
        self._progress_val += 0.018
        self._progress.set_fraction(min(self._progress_val, 1.0))
        if self._progress_val >= 1.0:
            self._splash.destroy()
            self._main_win.present()
            return False
        return True

if __name__ == "__main__": App().run()
