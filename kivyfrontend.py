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
 • Native OS file dialogs (via osascript on macOS, with fallback to Kivy)
 • Settings menu (model, prompt, debug)
 • Soft-cancel of generation on Back
 • Optional on-screen debug console
"""

from __future__ import annotations

import json
import os
import subprocess
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
# Native file dialog functions
# --------------------------------------------------------------------------------------
def native_open_file_dialog(title="Select File", file_types=None, multiple=False):
    """open file dialog using native OS dialogs (macOS via osascript)"""
    if platform == "macosx":
        try:
            # build applescript command that returns POSIX path directly
            script = f'''
            set theFile to choose file with prompt "{title}"
            return POSIX path of theFile
            '''
            
            # add file type filtering if needed
            if file_types:
                # convert file types to applescript format
                if any("*.csv" in ft[1] for ft in file_types):
                    script = f'''
                    set theFile to choose file with prompt "{title}" of type {{"csv"}}
                    return POSIX path of theFile
                    '''
                elif any("*.gguf" in ft[1] for ft in file_types):
                    script = f'''
                    set theFile to choose file with prompt "{title}" of type {{"gguf"}}
                    return POSIX path of theFile
                    '''
                elif any("*.bin" in ft[1] for ft in file_types):
                    script = f'''
                    set theFile to choose file with prompt "{title}" of type {{"bin"}}
                    return POSIX path of theFile
                    '''
            
            # run osascript
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0 and result.stdout.strip():
                posix_path = result.stdout.strip()
                print(f"native open dialog returned: {posix_path}")  # debug
                return [posix_path]
                
        except Exception as e:
            print(f"native file dialog error: {e}")
    
    return None  # fallback needed


def native_save_file_dialog(title="Save File", filename="", file_types=None):
    """save file dialog using native OS dialogs (macOS via osascript)"""
    if platform == "macosx":
        try:
            # build applescript for save dialog that returns POSIX path directly
            script = f'''
            set theFile to choose file name with prompt "{title}"'''
            if filename:
                script += f' default name "{filename}"'
            script += '''
            return POSIX path of theFile
            '''
            
            # run osascript
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0 and result.stdout.strip():
                posix_path = result.stdout.strip()
                print(f"native save dialog returned: {posix_path}")  # debug
                return posix_path
                
        except Exception as e:
            print(f"native save dialog error: {e}")
    
    return None  # fallback needed

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
            font_size=18,  # increased default font size
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


class UploadZone(BoxLayout):
    """Unified drag-and-drop and click upload zone."""

    def __init__(self, app_instance, **kw):
        super().__init__(
            orientation="vertical",
            size_hint=(1, 0.7),
            padding=40,
            spacing=20,
            **kw,
        )
        self.app_instance = app_instance
        self.is_hovered = False
        
        # create the visual background
        with self.canvas.before:
            Color(*StyledButton.hex2rgba("#FFFFFF", 1))  # white base background
            self._bg_rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[15])
            Color(*StyledButton.hex2rgba(PACIFICA_BLUE, 0.4))  # blue overlay
            self._overlay_rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[15])
        
        self.bind(pos=self._update_canvas, size=self._update_canvas)
        
        # main upload text/button
        self.upload_label = Label(
            text="[size=48][b]Click to Upload CSV[/b][/size]\n[size=28]or drag and drop your file here[/size]",  # increased font sizes
            markup=True,
            halign="center",
            valign="middle",
            color=[1, 1, 1, 1],  # white text for visibility on blue background
        )
        self.upload_label.bind(size=self._update_text_size)
        self.add_widget(self.upload_label)
        
        # add some visual spacing
        self.add_widget(Widget(size_hint_y=0.2))
        
        # file format hint
        hint_label = Label(
            text="[size=22]Supported format: CSV files only[/size]",  # increased font size
            markup=True,
            halign="center",
            valign="middle",
            color=[1, 1, 1, 0.8],  # slightly transparent white
            size_hint_y=None,
            height=35,  # increased height
        )
        hint_label.bind(size=lambda inst, *_: inst.setter("text_size")(inst, (inst.width, None)))
        self.add_widget(hint_label)

    def _update_canvas(self, *_):
        """update canvas rectangles when position/size changes"""
        self._bg_rect.pos = self.pos
        self._bg_rect.size = self.size
        self._overlay_rect.pos = self.pos
        self._overlay_rect.size = self.size

    def _update_text_size(self, *_):
        """update text wrapping"""
        self.upload_label.text_size = (self.width * 0.9, None)

    def on_touch_down(self, touch):
        """handle clicks anywhere in the upload zone"""
        if self.collide_point(*touch.pos):
            # add visual feedback by temporarily darkening the zone
            self._set_hover_state(True)
            # trigger file browser
            self.app_instance._open_file_browser("csv")
            return True
        return super().on_touch_down(touch)
    
    def on_touch_up(self, touch):
        """reset visual state on touch release"""
        if self.collide_point(*touch.pos):
            self._set_hover_state(False)
        return super().on_touch_up(touch)
    
    def _set_hover_state(self, hovered):
        """update visual appearance for hover/press state"""
        self.is_hovered = hovered
        self.canvas.before.clear()
        with self.canvas.before:
            Color(*StyledButton.hex2rgba("#FFFFFF", 1))  # white base background
            self._bg_rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[15])
            if hovered:
                Color(*StyledButton.hex2rgba(PACIFICA_BLUE, 0.7))  # darker blue when pressed
            else:
                Color(*StyledButton.hex2rgba(PACIFICA_BLUE, 0.4))  # normal blue
            self._overlay_rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[15])


# --------------------------------------------------------------------------------------
# Simple item widget for the list
# --------------------------------------------------------------------------------------
class AgendaItem(BoxLayout):
    def __init__(self, text, index, app, **kwargs):
        super().__init__(orientation="horizontal", spacing=10, size_hint_y=None, **kwargs)  # remove fixed height
        
        self.app = app
        self.index = index
        self.selected = True  # start selected by default
        
        # create a checkbox to show selection state
        self.checkbox = CheckBox(active=True, size_hint_x=None, width=40)
        self.checkbox.bind(active=self.on_checkbox_toggle)
        self.add_widget(self.checkbox)
        
        # Create label for the text content with proper text wrapping
        self.label = Label(
            text=text,
            markup=False,  # disable markup to avoid formatting issues
            text_size=(None, None),  # will be set in _update_text_size
            halign="left",
            valign="top",  # align to top for multi-line text
            color=[0, 0, 0, 1],
            size_hint_x=1,
            size_hint_y=None,  # important: don't let label stretch vertically
            font_size=24  # smaller font size for better fitting
        )
        self.label.bind(texture_size=self._on_label_texture_size)  # bind to texture_size instead of size
        self.add_widget(self.label)
        
        # set initial background after widget is fully constructed
        from kivy.clock import Clock
        Clock.schedule_once(lambda dt: self._setup_initial_size(), 0)
    
    def _setup_initial_size(self):
        """setup initial text size and height after widget is constructed"""
        self._update_text_size()
        self.update_background()
    
    def _update_text_size(self, *args):
        """update text_size when label size changes for proper text wrapping"""
        if self.label.parent:  # make sure label is added to parent
            # set text width to available space minus checkbox width and spacing
            available_width = self.width - self.checkbox.width - 20  # 20 for spacing and padding
            if available_width > 0:
                self.label.text_size = (available_width, None)
    
    def _on_label_texture_size(self, instance, texture_size):
        """called when label's rendered text size changes"""
        # update the label height to match the text height
        self.label.height = texture_size[1]
        # update the container height to fit the label plus some padding
        self.height = max(50, texture_size[1] + 20)  # minimum 50px height, 20px padding
    
    def on_size(self, *args):
        """update background and text size when widget size changes"""
        self._update_text_size()
        self.update_background()
    
    def on_checkbox_toggle(self, checkbox, value):
        """handle checkbox toggle"""
        self.selected = value
        self.update_background()
        
        # notify the app
        if value:
            self.app.mark_selected(self.index)
        else:
            self.app.mark_deselected(self.index)
    
    def on_touch_down(self, touch):
        """make the entire row clickable"""
        if self.collide_point(*touch.pos):
            # toggle selection when clicked anywhere on the row
            self.checkbox.active = not self.checkbox.active
            return True
        return super().on_touch_down(touch)
    
    def update_background(self):
        """update background color based on selection"""
        if not self.canvas:  # check if canvas exists
            return
            
        self.canvas.before.clear()
        with self.canvas.before:
            if self.selected:
                Color(*StyledButton.hex2rgba(PACIFICA_BLUE, 0.3))  # light blue background
            else:
                Color(*StyledButton.hex2rgba("#FFFFFF", 1.0))  # white background
            Rectangle(pos=self.pos, size=self.size)
    
    def on_pos(self, *args):
        """update background rectangle when position changes"""
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
        Window.size = (1280, 720)  # set default window size
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

        # add logo above header if available
        try:
            if os.path.exists("logo.png"):
                from kivy.uix.image import Image as KivyImage
                logo = KivyImage(source="logo.png", size_hint=(None, None), size=(120, 120))
                root.add_widget(logo)
        except Exception:
            pass

        header = Label(
            text="[b]City of Pacifica[/b]\nAgenda Summary Generator",
            markup=True,
            font_size=36,  # increased font size
            color=[0, 0, 0, 1],
            size_hint_y=None,
            height=120,  # increased height for larger font
        )
        root.add_widget(header)

        # unified upload zone (replaces both drop area and browse button)
        upload_zone = UploadZone(self)
        root.add_widget(upload_zone)

        nav_bar = BoxLayout(orientation='horizontal', size_hint_y=None, height=40, spacing=10)
        nav_bar.add_widget(Widget())

        settings_btn = StyledButton(text="Settings", size_hint=(None, None), width=140, height=45, font_size=18)  # increased size and font
        settings_btn.bind(on_release=lambda *_: self._navigate_to("settings"))
        nav_bar.add_widget(settings_btn)

        help_btn = StyledButton(text="Help", size_hint=(None, None), width=140, height=45, font_size=18)  # increased size and font
        help_btn.bind(on_release=lambda *_: self._navigate_to("help"))
        nav_bar.add_widget(help_btn)

        credits_btn = StyledButton(text="Credits", size_hint=(None, None), width=140, height=45, font_size=18)  # increased size and font
        credits_btn.bind(on_release=lambda *_: self._navigate_to("credits"))
        nav_bar.add_widget(credits_btn)

        nav_bar.add_widget(Widget())
        root.add_widget(nav_bar)

        root.add_widget(Label(size_hint_y=0.1))  # smaller spacer
        self.screen_manager.add_widget(scr)


    def _open_file_browser(self, filetype: str):
        # try native dialog first
        if filetype == "csv":
            filters = [("CSV files", "*.csv"), ("All files", "*.*")]
            title = "Select CSV File"
        else:
            filters = [("All files", "*.*")]
            title = "Select File"
        
        selection = native_open_file_dialog(title=title, file_types=filters)
        if selection:
            self._process_csv(selection[0])
            return
        
        # fallback to kivy file chooser
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

        topbar = BoxLayout(orientation="horizontal", size_hint_y=None, height=50, spacing=10)  # increased height
        back_btn = StyledButton(text="Back", width=120, height=50, font_size=18)  # increased size and font
        back_btn.bind(on_release=lambda *_: self._navigate_to("home"))  # use navigation method
        topbar.add_widget(back_btn)

        self.review_label = Label(text="Items Selected: 0", color=[0, 0, 0, 1], font_size=18)  # increased font size
        topbar.add_widget(self.review_label)

        gen_btn = StyledButton(text="Generate", width=180, height=50, font_size=18)  # increased size and font
        gen_btn.bind(on_release=lambda *_: self._start_generation())
        topbar.add_widget(gen_btn)

        layout.add_widget(topbar)

        # Create a scrollable list using ScrollView and BoxLayout
        scroll = ScrollView(size_hint=(1, 1))
        self.items_container = BoxLayout(orientation='vertical', size_hint_y=None, spacing=2)
        self.items_container.bind(minimum_height=self.items_container.setter('height'))
        scroll.add_widget(self.items_container)
        layout.add_widget(scroll)

        sel_bar = BoxLayout(size_hint_y=None, height=50, spacing=10)  # increased height
        sel_all = StyledButton(text="Select All", width=140, height=50, font_size=18)  # increased size and font
        sel_all.bind(on_release=lambda *_: self._select_all_items(True))
        sel_bar.add_widget(sel_all)
        desel_all = StyledButton(text="Deselect All", width=140, height=50, font_size=18)  # increased size and font
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

        top = BoxLayout(orientation="horizontal", size_hint_y=None, height=50, spacing=10)  # increased height
        self.back_gen_btn = StyledButton(text="Back", width=120, height=50, font_size=18)  # increased size and font
        self.back_gen_btn.bind(on_release=lambda *_: self._cancel_generation())
        top.add_widget(self.back_gen_btn)

        save_btn = StyledButton(text="Save", width=140, height=50, font_size=18)  # increased size and font
        save_btn.disabled = True
        self.save_button = save_btn
        save_btn.bind(on_release=lambda *_: self._save_report())
        top.add_widget(save_btn)

        layout.add_widget(top)

        # scrollable log textbox
        self.gen_output = TextInput(
            readonly=True,
            font_size=16,  # increased font size
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

        title = Label(text="[b]Settings[/b]", markup=True, font_size=32, size_hint_y=None, height=80, color=[0, 0, 0, 1])  # increased font size and height
        root.add_widget(title)

        # Model picker
        model_box = BoxLayout(orientation="horizontal", size_hint_y=None, height=50, spacing=10)  # increased height
        model_lbl = Label(text="Model:", color=[0, 0, 0, 1], size_hint_x=0.2, font_size=18)  # increased font size
        self.model_path_lbl = Label(text=CONF["model_path"], color=[0, 0, 0, 1], halign="left", font_size=16)  # increased font size
        self.model_path_lbl.bind(size=lambda inst, *_: inst.setter("text_size")(inst, (inst.width, None)))
        choose_model = StyledButton(text="Choose", width=120, height=50, font_size=18)  # increased size and font
        choose_model.bind(on_release=lambda *_: self._choose_model())
        model_box.add_widget(model_lbl)
        model_box.add_widget(self.model_path_lbl)
        model_box.add_widget(choose_model)
        root.add_widget(model_box)

        # Prompt picker
        prompt_box = BoxLayout(orientation="horizontal", size_hint_y=None, height=50, spacing=10)  # increased height
        prompt_lbl = Label(text="Prompt File:", color=[0, 0, 0, 1], size_hint_x=0.2, font_size=18)  # increased font size
        self.prompt_path_lbl = Label(text=CONF.get("prompt_path", ""), color=[0, 0, 0, 1], halign="left", font_size=16)  # increased font size
        self.prompt_path_lbl.bind(size=lambda inst, *_: inst.setter("text_size")(inst, (inst.width, None)))
        choose_prompt = StyledButton(text="Choose", width=120, height=50, font_size=18)  # increased size and font
        choose_prompt.bind(on_release=lambda *_: self._choose_prompt())
        prompt_box.add_widget(prompt_lbl)
        prompt_box.add_widget(self.prompt_path_lbl)
        prompt_box.add_widget(choose_prompt)
        root.add_widget(prompt_box)

        # Debug switch
        dbg_switch = ToggleSwitch("Debug Mode", CONF["debug"], self._toggle_debug)
        root.add_widget(dbg_switch)

        btn_bar = BoxLayout(size_hint_y=None, height=50, spacing=10)  # increased height
        back_btn = StyledButton(text="Back", width=120, height=50, font_size=18)  # increased size and font
        back_btn.bind(on_release=lambda *_: self._navigate_to("home"))  # use navigation method
        btn_bar.add_widget(back_btn)
        root.add_widget(btn_bar)

        self.screen_manager.add_widget(scr)

    # pickers
    def _choose_model(self):
        # try native dialog first
        filters = [("GGUF Model files", "*.gguf"), ("Binary Model files", "*.bin"), ("All files", "*.*")]
        selection = native_open_file_dialog(title="Select Model File", file_types=filters)
        
        if selection:
            CONF["model_path"] = selection[0]
            self.model_path_lbl.text = selection[0]
            save_conf(CONF)
            # reload model async
            self.backend.model_path = selection[0]
            self.backend._load_llm_model_async()
            return
        
        # fallback to kivy file chooser
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
        # try native dialog first
        filters = [
            ("Text files", "*.txt"),
            ("Prompt files", "*.prompt"),
            ("Markdown files", "*.md"),
            ("JSON files", "*.json"),
            ("Python files", "*.py"),
            ("All files", "*.*")
        ]
        selection = native_open_file_dialog(title="Select Prompt File", file_types=filters)
        
        if selection:
            CONF["prompt_path"] = selection[0]
            self.prompt_path_lbl.text = selection[0]
            save_conf(CONF)
            self._load_prompt_from_file(selection[0])
            return
        
        # fallback to kivy file chooser
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
        root = BoxLayout(orientation="vertical", padding=20, spacing=20)
        scr.add_widget(root)
        
        # title with back button
        header = BoxLayout(orientation="horizontal", size_hint_y=None, height=60, spacing=10)
        back_btn = StyledButton(text="Back", size_hint=(None, None), width=120, height=50, font_size=18)
        back_btn.bind(on_release=lambda *_: self._navigate_to("home"))
        header.add_widget(back_btn)
        
        title = Label(text="[b]Help & Instructions[/b]", markup=True, font_size=32, color=[0, 0, 0, 1])
        header.add_widget(title)
        header.add_widget(Widget())  # spacer
        root.add_widget(header)
        
        # scrollable content
        scroll = ScrollView()
        content = BoxLayout(orientation="vertical", spacing=15, size_hint_y=None, padding=20)
        content.bind(minimum_height=content.setter('height'))
        
        help_text = (
            "[size=24][b]How to Use the Agenda Summary Generator[/b][/size]\n\n"
            "[size=18][b]Step 1: Prepare Your CSV File[/b][/size]\n"
            "• Ensure your CSV file contains the required columns:\n"
            "  - MEETING DATE\n"
            "  - AGENDA SECTION\n"
            "  - AGENDA ITEM\n"
            "  - Include in Summary for Mayor (must be 'Y' for inclusion)\n"
            "  - NOTES (optional)\n\n"
            "[size=18][b]Step 2: Upload Your File[/b][/size]\n"
            "• Click the large upload area on the home screen or\n"
            "• Drag and drop your CSV file directly onto the upload zone\n\n"
            "[size=18][b]Step 3: Review and Select Items[/b][/size]\n"
            "• Review the automatically filtered agenda items\n"
            "• Items marked 'Y' for 'Include in Summary for Mayor' are pre-selected\n"
            "• Click individual items to toggle selection\n"
            "• Use 'Select All' or 'Deselect All' buttons for bulk actions\n\n"
            "[size=18][b]Step 4: Generate the Report[/b][/size]\n"
            "• Click 'Generate' to start the AI processing\n"
            "• Watch the real-time generation progress\n"
            "• The process uses a two-pass approach for better quality\n\n"
            "[size=18][b]Step 5: Save Your Report[/b][/size]\n"
            "• Once generation is complete, click 'Save'\n"
            "• Choose your save location using the native file dialog\n"
            "• The report will be saved as a Word (.docx) document\n\n"
            "[size=18][b]Tips for Best Results[/b][/size]\n"
            "• Ensure consistent date formatting in your CSV\n"
            "• Keep agenda item descriptions clear and concise\n"
            "• Use the Notes field for additional context when needed\n"
            "• Review the generated content before saving"
        )
        
        help_label = Label(
            text=help_text,
            markup=True,
            color=[0, 0, 0, 1],
            text_size=(None, None),
            halign="left",
            valign="top",
            size_hint_y=None
        )
        help_label.bind(width=lambda inst, width: inst.setter('text_size')(inst, (width - 40, None)))
        help_label.bind(texture_size=help_label.setter('height'))
        content.add_widget(help_label)
        
        scroll.add_widget(content)
        root.add_widget(scroll)
        
        self.screen_manager.add_widget(scr)

    def _build_credits(self):
        scr = CreditsScreen(name="credits")
        root = BoxLayout(orientation="vertical", padding=20, spacing=20)
        scr.add_widget(root)
        
        # title with back button
        header = BoxLayout(orientation="horizontal", size_hint_y=None, height=60, spacing=10)
        back_btn = StyledButton(text="Back", size_hint=(None, None), width=120, height=50, font_size=18)
        back_btn.bind(on_release=lambda *_: self._navigate_to("home"))
        header.add_widget(back_btn)
        
        title = Label(text="[b]About & Credits[/b]", markup=True, font_size=32, color=[0, 0, 0, 1])
        header.add_widget(title)
        header.add_widget(Widget())  # spacer
        root.add_widget(header)
        
        # main content in center
        content_frame = BoxLayout(orientation="vertical", spacing=25, size_hint=(0.8, None), height=400)
        content_frame.pos_hint = {'center_x': 0.5}
        
        # app title
        app_title = Label(
            text="[size=36][b]City of Pacifica[/b]\nAgenda Summary Generator[/size]",
            markup=True,
            halign="center",
            color=[0, 0, 0, 1],
            size_hint_y=None,
            height=100
        )
        content_frame.add_widget(app_title)
        
        # version and description
        version_info = Label(
            text="[size=24][b]Version 2.0 - Kivy Edition[/b][/size]\n\n"
                 "[size=18]A modern, cross-platform application for generating\n"
                 "AI-powered summaries of city council agenda items\n"
                 "for executive review and public transparency.[/size]",
            markup=True,
            halign="center",
            color=[0, 0, 0, 1],
            size_hint_y=None,
            height=120
        )
        content_frame.add_widget(version_info)
        
        # credits
        credits_info = Label(
            text="[size=20][b]Development Team[/b][/size]\n\n"
                 "[size=18]Project Lead & Developer: [b]Nickolas Yang[/b]\n"
                 "Project Coordination: [b]Madeleine Hur[/b]\n\n"
                 "Built with Python, Kivy, and local LLMs\n"
                 "Powered by llama-cpp-python for privacy-focused AI processing[/size]",
            markup=True,
            halign="center",
            color=[0, 0, 0, 1],
            size_hint_y=None,
            height=140
        )
        content_frame.add_widget(credits_info)
        
        # add to centered container
        center_container = BoxLayout()
        center_container.add_widget(Widget())  # left spacer
        center_container.add_widget(content_frame)
        center_container.add_widget(Widget())  # right spacer
        
        root.add_widget(center_container)
        root.add_widget(Widget())  # bottom spacer
        
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
        # try native save dialog first
        filters = [("Word Documents", "*.docx"), ("All files", "*.*")]
        save_path = native_save_file_dialog(
            title="Save Report",
            filename=suggested_name,
            file_types=filters
        )
        
        if save_path:
            # ensure .docx extension
            if not save_path.lower().endswith(".docx"):
                save_path += ".docx"
            
            try:
                doc.save(save_path)
                self._show_info(f"saved to {save_path}")
                return
            except Exception as exc:
                self._show_error("save error", str(exc))
                return
        
        # fallback to kivy file chooser with proper save functionality
        content = BoxLayout(orientation='vertical', spacing=10, padding=10)
        
        # file chooser
        fc = FileChooserListView(path=os.getcwd(), filters=["*.docx"])
        content.add_widget(fc)
        
        # filename input
        filename_input = TextInput(
            text=suggested_name,
            size_hint_y=None,
            height=40,
            multiline=False,
            hint_text="Enter filename..."
        )
        content.add_widget(filename_input)
        
        # buttons
        btn_layout = BoxLayout(size_hint_y=None, height=40, spacing=10)
        cancel_btn = StyledButton(text="Cancel", size_hint_x=0.5)
        save_btn = StyledButton(text="Save", size_hint_x=0.5)
        btn_layout.add_widget(cancel_btn)
        btn_layout.add_widget(save_btn)
        content.add_widget(btn_layout)
        
        popup = Popup(title="Save Report", content=content, size_hint=(0.9, 0.9))
        
        def _on_save(*args):
            # get filename from input
            filename = filename_input.text.strip()
            if not filename:
                filename = suggested_name
            
            # ensure .docx extension
            if not filename.lower().endswith(".docx"):
                filename += ".docx"
            
            # construct full path
            save_path = os.path.join(fc.path, filename)
            
            try:
                doc.save(save_path)
                popup.dismiss()
                self._show_info(f"saved to {save_path}")
            except Exception as exc:
                self._show_error("save error", str(exc))
        
        def _on_cancel(*args):
            popup.dismiss()
        
        # update path when folder selection changes
        def _on_selection(instance, selection):
            if selection and os.path.isdir(selection[0]):
                fc.path = selection[0]
        
        save_btn.bind(on_release=_on_save)
        cancel_btn.bind(on_release=_on_cancel)
        fc.bind(selection=_on_selection)
        
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