"""kivyfrontend.py
City of Pacifica – Agenda Summary Generator (Kivy edition)

Run:  python3 kivyfrontend.py
Dependencies:
    pip install kivy pandas python-docx llama-cpp-python
Optionally for prettier widgets you may install kivymd, but this file
only uses vanilla Kivy to avoid extra requirements.

This GUI intentionally mirrors the workflow of the existing
CustomTkinter GUI while adding:
 • Native drag-and-drop
 • Settings menu (model, prompt, debug)
 • Soft-cancel of generation on Back
 • Optional on-screen debug console
"""

from __future__ import annotations

import json
import os
import sys
import threading
import traceback
from datetime import datetime
from typing import List

import pandas as pd
from kivy import platform  # type: ignore
from kivy.app import App
from kivy.clock import mainthread
from kivy.core.window import Window
from kivy.graphics import Color, Rectangle, RoundedRectangle
from kivy.properties import BooleanProperty, ListProperty, ObjectProperty, StringProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.checkbox import CheckBox
from kivy.uix.filechooser import FileChooserListView
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.recycleview import RecycleView
from kivy.uix.recycleview.views import RecycleDataViewBehavior
from kivy.uix.screenmanager import Screen, ScreenManager, SlideTransition
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget
from kivy.config import Config
Config.set('input', 'mouse', 'mouse,multitouch_on_demand')

from kivybackend import AgendaBackend, PROMPT_TEMPLATE

# --------------------------------------------------------------------------------------
# Constants / Config persistence
# --------------------------------------------------------------------------------------
CONFIG_FILE = os.path.join(os.path.expanduser("\"~\""), ".pacifica_agenda_gui.json")

DEFAULT_CONF = {
    "model_path": "language_models/Qwen3-4B-Q6_K.gguf",
    "prompt_path": "",  # empty => use PROMPT_TEMPLATE embedded
    "debug": False,
}

PACIFICA_BLUE = "#4682B4"  # headers / accents
PACIFICA_SAND = "#F5F5DC"  # background
TEXT_COLOR = "#222222"


def load_conf() -> dict:
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as fp:
            data = json.load(fp)
            DEFAULT_CONF.update(data)
    except Exception:
        pass
    return DEFAULT_CONF.copy()


def save_conf(conf: dict):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as fp:
            json.dump(conf, fp, indent=2)
    except Exception:
        pass


CONF = load_conf()

# --------------------------------------------------------------------------------------
# Helper widgets
# --------------------------------------------------------------------------------------
class StyledButton(Button):
    """Flat button with Pacifica colours."""

    def __init__(self, **kw):
        super().__init__(
            background_normal="",
            background_color=self.hex2rgba(PACIFICA_BLUE, 1.0),
            color=[1, 1, 1, 1],
            font_size=16,
            **kw,
        )

    @staticmethod
    def hex2rgba(hx: str, alpha=1.0):
        hx = hx.lstrip("#")
        return [int(hx[i : i + 2], 16) / 255.0 for i in (0, 2, 4)] + [alpha]


class ToggleSwitch(BoxLayout):
    """Simple labelled on/off switch."""

    active = BooleanProperty(False)

    def __init__(self, text: str, initial: bool, callback, **kw):
        super().__init__(orientation="horizontal", spacing=10, size_hint_y=None, height=32, **kw)
        self.add_widget(Label(text=text, color=[0, 0, 0, 1], size_hint_x=0.8, halign="left", valign="middle"))
        cb = CheckBox(active=initial)
        cb.bind(active=lambda _, v: callback(v))
        self.add_widget(cb)


class DropLabel(Label):
    """Label that changes appearance on drag enter."""

    def __init__(self, **kw):
        super().__init__(
            text="Drag CSV Here or Click Browse",
            font_size=22,
            halign="center",
            valign="middle",
            color=[0, 0, 0, 1],
            **kw,
        )
        self.bind(size=self._update_text_size)

    def _update_text_size(self, *_):
        self.text_size = (self.width * 0.9, None)


# --------------------------------------------------------------------------------------
# Simple item widget for the list
# --------------------------------------------------------------------------------------
class AgendaItem(BoxLayout):
    def __init__(self, text, index, app, **kwargs):
        super().__init__(orientation="horizontal", spacing=10, size_hint_y=None, height=50, **kwargs)
        
        self.app = app
        self.index = index
        self.selected = True  # start selected by default
        
        # Create a checkbox to show selection state
        self.checkbox = CheckBox(active=True, size_hint_x=None, width=40)
        self.checkbox.bind(active=self.on_checkbox_toggle)
        self.add_widget(self.checkbox)
        
        # Create label for the text content
        self.label = Label(
            text=text,
            markup=True,
            text_size=(None, None),
            halign="left",
            valign="middle",
            color=[0, 0, 0, 1],
            size_hint_x=1
        )
        self.label.bind(size=self._update_text_size)
        self.add_widget(self.label)
        
        # Set initial background after widget is fully constructed
        # Use Clock.schedule_once to delay this until the next frame
        from kivy.clock import Clock
        Clock.schedule_once(lambda dt: self.update_background(), 0)
    
    def _update_text_size(self, *args):
        # Update text_size when label size changes for proper text wrapping
        self.label.text_size = (self.label.width, None)
    
    def on_checkbox_toggle(self, checkbox, value):
        """Handle checkbox toggle"""
        self.selected = value
        self.update_background()
        
        # Notify the app
        if value:
            self.app.mark_selected(self.index)
        else:
            self.app.mark_deselected(self.index)
    
    def update_background(self):
        """Update background color based on selection"""
        if not self.canvas:  # Check if canvas exists
            return
            
        self.canvas.before.clear()
        with self.canvas.before:
            if self.selected:
                Color(*StyledButton.hex2rgba(PACIFICA_BLUE, 0.3))  # light blue background
            else:
                Color(*StyledButton.hex2rgba("#FFFFFF", 1.0))  # white background
            Rectangle(pos=self.pos, size=self.size)
    
    def on_size(self, *args):
        """Update background rectangle when size changes"""
        self.update_background()
    
    def on_pos(self, *args):
        """Update background rectangle when position changes"""
        self.update_background()


# --------------------------------------------------------------------------------------
# Item view for the RecycleView (keeping for potential future use)
# --------------------------------------------------------------------------------------
class SelectableItem(RecycleDataViewBehavior, BoxLayout):
    index = None
    selected = BooleanProperty(False)
    selectable = BooleanProperty(True)

    def __init__(self, **kwargs):
        super().__init__(orientation="horizontal", spacing=10, size_hint_y=None, height=50, **kwargs)
        
        # Create a checkbox to show selection state
        self.checkbox = CheckBox(active=False, size_hint_x=None, width=40)
        self.checkbox.bind(active=self.on_checkbox_toggle)
        self.add_widget(self.checkbox)
        
        # Create label for the text content
        self.label = Label(
            text="",
            markup=True,
            text_size=(None, None),
            halign="left",
            valign="middle",
            color=[0, 0, 0, 1],
            size_hint_x=1
        )
        self.label.bind(size=self._update_text_size)
        self.add_widget(self.label)
        
        # Bind the selected property to update checkbox
        self.bind(selected=self.on_selected_change)
    
    def _update_text_size(self, *args):
        # Update text_size when label size changes for proper text wrapping
        self.label.text_size = (self.label.width, None)

    def refresh_view_attrs(self, rv, index, data):
        """Called when the view is recycled"""
        self.index = index
        
        # Update the content from data
        self.label.text = data.get("text", "")
        self.label.markup = data.get("markup", True)
        self.height = data.get("height", 50)
        
        # Update selection state from data
        self.selected = data.get("selected", False)
        
        return super().refresh_view_attrs(rv, index, data)
    
    def on_selected_change(self, instance, value):
        """Update checkbox when selected property changes"""
        self.checkbox.active = value
        
        # Update background color based on selection
        if hasattr(self, 'canvas'):
            self.canvas.before.clear()
            with self.canvas.before:
                if value:
                    Color(*StyledButton.hex2rgba(PACIFICA_BLUE, 0.3))  # light blue background
                else:
                    Color(*StyledButton.hex2rgba("#FFFFFF", 1.0))  # white background
                Rectangle(pos=self.pos, size=self.size)
    
    def on_checkbox_toggle(self, checkbox, value):
        """Handle checkbox toggle"""
        self.selected = value
        
        # Update the RecycleView data
        # Find the RecycleView by walking up the parent tree
        rv = self.parent
        while rv and not hasattr(rv, 'data'):
            rv = rv.parent
            
        if rv and hasattr(rv, 'data') and self.index is not None and self.index < len(rv.data):
            rv.data[self.index]["selected"] = value
            
            # Notify the app
            if hasattr(rv, 'app'):
                if value:
                    rv.app.mark_selected(self.index)
                else:
                    rv.app.mark_deselected(self.index)

    def on_touch_down(self, touch):
        if super().on_touch_down(touch):
            return True
        if self.collide_point(*touch.pos) and self.selectable:
            # Toggle selection when clicked (but not on checkbox)
            if not self.checkbox.collide_point(*touch.pos):
                self.checkbox.active = not self.checkbox.active
            return True
        return False
    
    def on_size(self, *args):
        """Update background rectangle when size changes"""
        self.on_selected_change(self, self.selected)


# --------------------------------------------------------------------------------------
# Screens
# --------------------------------------------------------------------------------------
class HomeScreen(Screen):
    pass


class ReviewScreen(Screen):
    pass


class GenerationScreen(Screen):
    pass


class SettingsScreen(Screen):
    pass


class HelpScreen(Screen):
    pass


class CreditsScreen(Screen):
    pass


# --------------------------------------------------------------------------------------
# Main App
# --------------------------------------------------------------------------------------
class PacificaAgendaApp(App):
    title = "City of Pacifica - Agenda Summary Generator"

    backend: AgendaBackend
    screen_manager: ScreenManager = ObjectProperty(None)
    csv_data: pd.DataFrame | None = None
    filtered_items: List[pd.Series] = []
    selected_indices: set[int] = set()
    generation_cancel_event = threading.Event()

    generated_report_text = ""
    meeting_dates_for_report: List[str] = []
    current_prompt_template: str = ""

    debug_console: TextInput | None = None

    def build(self):
        Window.clearcolor = StyledButton.hex2rgba(PACIFICA_SAND, 1)
        self.backend = AgendaBackend(model_path=CONF["model_path"])

        self.current_prompt_template = PROMPT_TEMPLATE  # default
        if CONF.get("prompt_path") and os.path.exists(CONF["prompt_path"]):
            self._load_prompt_from_file(CONF["prompt_path"])

        self.screen_manager = ScreenManager(transition=SlideTransition(duration=0.25))
        self._build_home()
        self._build_review()
        self._build_generation()
        self._build_settings()
        self._build_help()
        self._build_credits()

        # bind drag-and-drop
        if platform in ("win", "linux", "macosx"):
            Window.bind(on_dropfile=self._on_file_drop)

        return self.screen_manager

    # ---------------------------------------------------------------- Home
    def _build_home(self):
        scr = HomeScreen(name="home")
        root = BoxLayout(orientation="vertical", padding=40, spacing=20)
        scr.add_widget(root)

        header = Label(
            text="[b]City of Pacifica[/b]\nAgenda Summary Generator",
            markup=True,
            font_size=32,
            color=[0, 0, 0, 1],
            size_hint_y=None,
            height=100,
        )
        root.add_widget(header)

        # Drop area
        drop_area = BoxLayout(
            orientation="vertical",
            size_hint=(1, 0.6),
            padding=20,
            spacing=10,
        )
        with drop_area.canvas.before:
            Color(*StyledButton.hex2rgba("#FFFFFF", 1)) # Add white background
            RoundedRectangle(pos=drop_area.pos, size=drop_area.size, radius=[10])
        with drop_area.canvas.before:
            Color(*StyledButton.hex2rgba(PACIFICA_BLUE, 0.6))
            self._drop_rect = RoundedRectangle(pos=drop_area.pos, size=drop_area.size, radius=[10])
        drop_area.bind(pos=self._update_drop_rect, size=self._update_drop_rect)
        lbl = DropLabel()
        drop_area.add_widget(lbl)
        root.add_widget(drop_area)

        browse_box = BoxLayout(size_hint_y=None, height=50, padding=(0, 10, 0, 0))
        browse_btn = StyledButton(text="Click to Upload CSV", size_hint=(None, None), width=200, height=50)
        browse_btn.bind(on_release=lambda *_: self._open_file_browser("csv"))
        browse_box.add_widget(Widget())
        browse_box.add_widget(browse_btn)
        browse_box.add_widget(Widget())
        root.add_widget(browse_box)

        nav_bar = BoxLayout(orientation='horizontal', size_hint_y=None, height=40, spacing=10)
        nav_bar.add_widget(Widget())

        settings_btn = StyledButton(text="Settings", size_hint=(None, None), width=120, height=40)
        settings_btn.bind(on_release=lambda *_: setattr(self.screen_manager, "current", "settings"))
        nav_bar.add_widget(settings_btn)

        help_btn = StyledButton(text="Help", size_hint=(None, None), width=120, height=40)
        help_btn.bind(on_release=lambda *_: setattr(self.screen_manager, "current", "help"))
        nav_bar.add_widget(help_btn)

        credits_btn = StyledButton(text="Credits", size_hint=(None, None), width=120, height=40)
        credits_btn.bind(on_release=lambda *_: setattr(self.screen_manager, "current", "credits"))
        nav_bar.add_widget(credits_btn)

        nav_bar.add_widget(Widget())
        root.add_widget(nav_bar)

        root.add_widget(Label(size_hint_y=0.2))  # spacer
        self.screen_manager.add_widget(scr)

    def _update_drop_rect(self, instance, *_):
        self._drop_rect.pos, self._drop_rect.size = instance.pos, instance.size

    def _open_file_browser(self, filetype: str):
        chooser = FileChooserListView(filters=["*.csv"] if filetype == "csv" else None, path=os.getcwd())
        popup = Popup(title="Select CSV", content=chooser, size_hint=(0.9, 0.9))

        def _file_chosen(instance, selection, touch):
            if selection:
                popup.dismiss()
                self._process_csv(selection[0])

        chooser.bind(on_submit=_file_chosen)
        popup.open()

    def _on_file_drop(self, _window, file_path_bytes):
        path = file_path_bytes.decode("utf-8")
        if path.lower().endswith(".csv"):
            self._process_csv(path)

    def _process_csv(self, filepath: str):
        try:
            self.csv_data, self.filtered_items = self.backend.process_csv(filepath)
        except Exception as exc:
            self._show_error("CSV Error", str(exc))
            return
        # go to review
        self._populate_review_list()
        self.screen_manager.current = "review"

    # ---------------------------------------------------------------- Review screen
    def _build_review(self):
        scr = ReviewScreen(name="review")
        layout = BoxLayout(orientation="vertical", padding=20, spacing=15)
        scr.add_widget(layout)

        topbar = BoxLayout(orientation="horizontal", size_hint_y=None, height=40, spacing=10)
        back_btn = StyledButton(text="Back", width=100, height=40)
        back_btn.bind(on_release=lambda *_: setattr(self.screen_manager, "current", "home"))  # go back to home
        topbar.add_widget(back_btn)

        self.review_label = Label(text="Items Selected: 0", color=[0, 0, 0, 1])
        topbar.add_widget(self.review_label)

        gen_btn = StyledButton(text="Generate", width=150, height=40)
        gen_btn.bind(on_release=lambda *_: self._start_generation())
        topbar.add_widget(gen_btn)

        layout.add_widget(topbar)

        # Create a scrollable list using ScrollView and BoxLayout
        scroll = ScrollView(size_hint=(1, 1))
        self.items_container = BoxLayout(orientation='vertical', size_hint_y=None, spacing=2)
        self.items_container.bind(minimum_height=self.items_container.setter('height'))
        scroll.add_widget(self.items_container)
        layout.add_widget(scroll)

        sel_bar = BoxLayout(size_hint_y=None, height=40, spacing=10)
        sel_all = StyledButton(text="Select All", width=120, height=40)
        sel_all.bind(on_release=lambda *_: self._select_all_items(True))
        sel_bar.add_widget(sel_all)
        desel_all = StyledButton(text="Deselect All", width=120, height=40)
        desel_all.bind(on_release=lambda *_: self._select_all_items(False))
        sel_bar.add_widget(desel_all)
        layout.add_widget(sel_bar)

        self.screen_manager.add_widget(scr)

    def _populate_review_list(self):
        self.selected_indices.clear()
        
        # Clear existing items
        self.items_container.clear_widgets()
        
        # Add each item as a widget
        for idx, row in enumerate(self.filtered_items):
            date = str(row.get("MEETING DATE", "")).strip()
            sec = str(row.get("AGENDA SECTION", "")).replace("\\n", " ").replace("•", "-").strip()
            item = str(row.get("AGENDA ITEM", "")).replace("\\n", " ").replace("•", "-").strip()
            notes = ""
            if pd.notna(row.get("NOTES")):
                n = str(row["NOTES"]).replace("\\n", " ").replace("•", "-").strip()
                if n and n.lower() != "nan":
                    notes = n
            
            # Create display text without markup formatting issues
            display = f"{date} | {sec} | {item}"
            if notes:
                display += f" ({notes})"
            
            # Create and add the item widget
            item_widget = AgendaItem(display, idx, self)
            self.items_container.add_widget(item_widget)
            self.selected_indices.add(idx)
        
        self.review_label.text = f"Items Selected: {len(self.selected_indices)}"

    def _select_all_items(self, select=True):
        # Update all item widgets
        for child in self.items_container.children:
            if isinstance(child, AgendaItem):
                child.checkbox.active = select
                child.selected = select
                child.update_background()
        
        # Update selection tracking
        if select:
            self.selected_indices = set(range(len(self.items_container.children)))
        else:
            self.selected_indices.clear()
        
        self.review_label.text = f"Items Selected: {len(self.selected_indices)}"

    # called from child item views
    def mark_selected(self, index: int):
        self.selected_indices.add(index)
        self.review_label.text = f"Items Selected: {len(self.selected_indices)}"

    def mark_deselected(self, index: int):
        self.selected_indices.discard(index)
        self.review_label.text = f"Items Selected: {len(self.selected_indices)}"

    # ---------------------------------------------------------------- Generation screen
    def _build_generation(self):
        scr = GenerationScreen(name="generation")
        layout = BoxLayout(orientation="vertical", padding=10, spacing=10)
        scr.add_widget(layout)

        top = BoxLayout(orientation="horizontal", size_hint_y=None, height=40, spacing=10)
        self.back_gen_btn = StyledButton(text="Back", width=100, height=40)
        self.back_gen_btn.bind(on_release=lambda *_: self._cancel_generation())
        top.add_widget(self.back_gen_btn)

        save_btn = StyledButton(text="Save", width=120, height=40)
        save_btn.disabled = True
        self.save_button = save_btn
        save_btn.bind(on_release=lambda *_: self._save_report())
        top.add_widget(save_btn)

        layout.add_widget(top)

        # scrollable log textbox
        self.gen_output = TextInput(
            readonly=True,
            font_size=14,
            foreground_color=[0, 0, 0, 1],
            background_color=[1, 1, 1, 1],
        )
        sv = ScrollView()
        sv.add_widget(self.gen_output)
        layout.add_widget(sv)

        # Optional debug console under generation output if enabled
        if CONF["debug"]:
            self.debug_console = TextInput(
                readonly=True,
                size_hint_y=0.4,
                font_name="Courier" if platform != "ios" else None,
                background_color=[0.1, 0.1, 0.1, 1],
                foreground_color=[1, 1, 1, 1],
            )
            layout.add_widget(self.debug_console)
            # redirect stdout/stderr
            sys.stdout = self
            sys.stderr = self

        self.screen_manager.add_widget(scr)

    # file-like for debug console
    def write(self, msg):
        if self.debug_console:
            @mainthread
            def _append():
                self.debug_console.text += msg
                self.debug_console.cursor = (0, len(self.debug_console.text))
            _append()

    def flush(self):
        pass  # needed for IOBase compliance

    # ---------------------------------------------------------------- Settings
    def _build_settings(self):
        scr = SettingsScreen(name="settings")
        root = BoxLayout(orientation="vertical", padding=20, spacing=20)
        scr.add_widget(root)

        title = Label(text="[b]Settings[/b]", markup=True, font_size=28, size_hint_y=None, height=60)
        root.add_widget(title)

        # Model picker
        model_box = BoxLayout(orientation="horizontal", size_hint_y=None, height=40, spacing=10)
        model_lbl = Label(text="Model:", color=[0, 0, 0, 1], size_hint_x=0.2)
        self.model_path_lbl = Label(text=CONF["model_path"], color=[0, 0, 0, 1], halign="left")
        self.model_path_lbl.bind(size=lambda inst, *_: inst.setter("text_size")(inst, (inst.width, None)))
        choose_model = StyledButton(text="Choose", width=100, height=40)
        choose_model.bind(on_release=lambda *_: self._choose_model())
        model_box.add_widget(model_lbl)
        model_box.add_widget(self.model_path_lbl)
        model_box.add_widget(choose_model)
        root.add_widget(model_box)

        # Prompt picker
        prompt_box = BoxLayout(orientation="horizontal", size_hint_y=None, height=40, spacing=10)
        prompt_lbl = Label(text="Prompt File:", color=[0, 0, 0, 1], size_hint_x=0.2)
        self.prompt_path_lbl = Label(text=CONF.get("prompt_path", ""), color=[0, 0, 0, 1], halign="left")
        self.prompt_path_lbl.bind(size=lambda inst, *_: inst.setter("text_size")(inst, (inst.width, None)))
        choose_prompt = StyledButton(text="Choose", width=100, height=40)
        choose_prompt.bind(on_release=lambda *_: self._choose_prompt())
        prompt_box.add_widget(prompt_lbl)
        prompt_box.add_widget(self.prompt_path_lbl)
        prompt_box.add_widget(choose_prompt)
        root.add_widget(prompt_box)

        # Debug switch
        dbg_switch = ToggleSwitch("Debug Mode", CONF["debug"], self._toggle_debug)
        root.add_widget(dbg_switch)

        btn_bar = BoxLayout(size_hint_y=None, height=40, spacing=10)
        back_btn = StyledButton(text="Back", width=100, height=40)
        back_btn.bind(on_release=lambda *_: setattr(self.screen_manager, "current", "home"))  # go back to home
        btn_bar.add_widget(back_btn)
        root.add_widget(btn_bar)

        self.screen_manager.add_widget(scr)

    # pickers
    def _choose_model(self):
        chooser = FileChooserListView(path=os.getcwd(), filters=["*.gguf", "*.bin"])
        popup = Popup(title="Select Model", content=chooser, size_hint=(0.9, 0.9))

        def _sel(_, selection):
            if selection:
                CONF["model_path"] = selection[0]
                self.model_path_lbl.text = selection[0]
                save_conf(CONF)
                popup.dismiss()
                # reload model async
                self.backend.model_path = selection[0]
                self.backend._load_llm_model_async()

        chooser.bind(on_submit=_sel)
        popup.open()

    def _choose_prompt(self):
        chooser = FileChooserListView(path=os.getcwd(), filters=["*.txt", "*.prompt", "*.md", "*.json", "*.py", "*"])
        popup = Popup(title="Select Prompt File", content=chooser, size_hint=(0.9, 0.9))

        def _sel(_, selection):
            if selection:
                CONF["prompt_path"] = selection[0]
                self.prompt_path_lbl.text = selection[0]
                save_conf(CONF)
                popup.dismiss()
                self._load_prompt_from_file(selection[0])

        chooser.bind(on_submit=_sel)
        popup.open()

    def _load_prompt_from_file(self, path: str):
        try:
            with open(path, "r", encoding="utf-8") as fp:
                self.current_prompt_template = fp.read()
            self._show_info("Custom prompt loaded successfully.")
        except Exception as exc:
            self.current_prompt_template = PROMPT_TEMPLATE  # fallback to default
            self._show_error("Prompt Load Error", str(exc))

    def _toggle_debug(self, value: bool):
        CONF["debug"] = value
        save_conf(CONF)
        self._show_info("Debug mode will apply on next app restart.")

    # ---------------------------------------------------------------- Help & Credits
    def _build_help(self):
        scr = HelpScreen(name="help")
        root = BoxLayout(orientation="vertical", padding=20)
        scr.add_widget(root)
        txt = (
            "[b]How to Use[/b]\n\n"
            "1. Drag a properly formatted CSV onto the home screen or click Browse.\n"
            "2. Review the list and (de)select rows.\n"
            "3. Press Generate – wait until finished.\n"
            "4. Press Save to export a Word document.\n"
        )
        root.add_widget(Label(text=txt, markup=True, color=[0, 0, 0, 1]))
        back_btn = StyledButton(text="Back", size_hint=(None, None), width=100, height=40)
        back_btn.bind(on_release=lambda *_: setattr(self.screen_manager, "current", "home"))  # go back to home
        root.add_widget(back_btn)
        self.screen_manager.add_widget(scr)

    def _build_credits(self):
        scr = CreditsScreen(name="credits")
        root = BoxLayout(orientation="vertical", padding=20, spacing=20)
        scr.add_widget(root)
        root.add_widget(
            Label(
                text="[b]Agenda Summary Generator v1.0[/b]\n\nDeveloper: Nickolas Yang\nCoordination: Madeleine Hur\nPowered by local LLMs (llama-cpp-python)",
                markup=True,
                halign="center",
                color=[0, 0, 0, 1],
            )
        )
        back_btn = StyledButton(text="Back", size_hint=(None, None), width=100, height=40)
        back_btn.bind(on_release=lambda *_: setattr(self.screen_manager, "current", "home"))  # go back to home
        root.add_widget(back_btn)
        self.screen_manager.add_widget(scr)

    # ---------------------------------------------------------------- Generation logic
    def _start_generation(self):
        if not self.selected_indices:
            self._show_error("Nothing Selected", "Please select at least one row.")
            return
        rows = [self.filtered_items[i] for i in sorted(self.selected_indices)]
        self.gen_output.text = "Generating...\n"
        self.save_button.disabled = True
        self.generation_cancel_event.clear()
        self.screen_manager.current = "generation"

        # start backend thread
        self.backend.generate_report(
            rows,
            token_callback=self._token_cb,
            done_callback=self._done_cb,
            error_callback=self._err_cb,
            cancel_event=self.generation_cancel_event,
            prompt_template=self.current_prompt_template,
        )

    def _cancel_generation(self):
        self.generation_cancel_event.set()
        self.screen_manager.current = "review"

    # backend callbacks
    def _token_cb(self, txt: str):
        if self.generation_cancel_event.is_set():
            return
        self._append_gen_text(txt)

    @mainthread
    def _append_gen_text(self, txt: str):
        self.gen_output.text += txt
        self.gen_output.cursor = (0, len(self.gen_output.text))

    def _done_cb(self, full_text: str, dates: List[str]):
        if self.generation_cancel_event.is_set():
            return
        self.generated_report_text = full_text
        self.meeting_dates_for_report = dates
        self.save_button.disabled = False
        self._append_gen_text("\n--- DONE ---\n")

    def _err_cb(self, exc: Exception):
        self._show_error("Generation Error", str(exc))
        self.screen_manager.current = "review"

    # ---------------------------------------------------------------- Save document
    def _save_report(self):
        if not self.generated_report_text.strip():
            return
        doc = self.backend.create_word_document(self.generated_report_text, self.meeting_dates_for_report)
        fname = f"Council_Agenda_Summary_{datetime.now():%Y%m%d}.docx"
        self._save_docx(doc, fname)

    def _save_docx(self, doc, suggested_name: str):
        from kivy.core.window import Window
        fc = FileChooserListView(path=os.getcwd(), filters=["*.docx"])
        popup = Popup(title="Save Report", content=fc, size_hint=(0.9, 0.9))

        def _on_submit(_, sel):
            if sel:
                path = sel[0]
                if not path.lower().endswith(".docx"):
                    path += ".docx"
            else:
                path = os.path.join(fc.path, suggested_name)
            try:
                doc.save(path)
                popup.dismiss()
                self._show_info(f"Saved to {path}")
            except Exception as exc:
                self._show_error("Save Error", str(exc))

        fc.bind(on_submit=_on_submit)
        popup.open()

    # ---------------------------------------------------------------- Alerts
    @mainthread
    def _show_error(self, title, msg):
        Popup(title=title, content=Label(text=msg), size_hint=(0.6, 0.4)).open()

    @mainthread
    def _show_info(self, msg):
        Popup(title="Info", content=Label(text=msg), size_hint=(0.6, 0.3)).open()


# --------------------------------------------------------------------------------------
if __name__ == "__main__":
    PacificaAgendaApp().run()