"""kivyfrontend.py
City of Pacifica - Agenda Summary Generator (Kivy edition)
 
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
import shutil
import subprocess
import sys
# --- Clipboard crash workaround (Windows) -----------------------------------
# Some Windows installations fall back to Tkinter for clipboard; if the Tk
# provider is not fully initialised, any TextInput copy (Ctrl+C) crashes.
# We patch Clipboard.copy with a safer version that tries the default, then
# falls back to pyperclip or a one-shot hidden Tkinter root.
try:
    from kivy.core.clipboard import Clipboard as _KivyClipboard

    _orig_copy_fn = _KivyClipboard.copy

    def _safe_clipboard_copy(text: str):
        try:
            _orig_copy_fn(text)                    # Try normal Kivy provider
            return
        except Exception as first_exc:
            try:
                import pyperclip                  # 1st fallback
                pyperclip.copy(text)
                return
            except Exception:
                pass
            try:
                import tkinter as _tk             # 2nd fallback (hidden root)
                _r = _tk.Tk()
                _r.withdraw()
                _r.clipboard_clear()
                _r.clipboard_append(text)
                _r.update()                       # keep clipboard after quit
                _r.destroy()
                return
            except Exception:
                # Final fallback – give up but prevent hard crash
                print(f"[clipboard] copy failed: {first_exc}", file=sys.stderr)

    # Monkey-patch the singleton provider instance
    _KivyClipboard.copy = _safe_clipboard_copy
except Exception as e:
    print(f"[clipboard] Could not patch clipboard provider: {e}", file=sys.stderr)
# ---------------------------------------------------------------------------
import threading
import traceback
import webbrowser
import re
import time
from datetime import datetime
from typing import List, Callable

import pandas as pd
from kivy import platform  # type: ignore
from kivy.app import App
from kivy.clock import mainthread
from kivy.core.window import Window
from kivy.core.audio import SoundLoader

# More robust notification setup
notification = None
try:
    # On macOS, plyer requires pyobjus. Check for it explicitly.
    if platform == 'macosx':
        import pyobjus  # This will raise ImportError if not installed
    from plyer import notification
except ImportError:
    if platform == 'macosx':
        print("Warning: 'pyobjus' or 'plyer' not found. System notifications on macOS will be disabled.", file=sys.stderr)
        print("To enable them, run: pip install 'plyer[mac_os_notification]'", file=sys.stderr)
    else:
        print("Warning: 'plyer' not found. System notifications will be disabled.", file=sys.stderr)
        print("To enable them, run: pip install plyer", file=sys.stderr)

from kivy.graphics import Color, Rectangle, RoundedRectangle
from kivy.properties import (
    BooleanProperty,
    ListProperty,
    ObjectProperty,
    StringProperty,
    NumericProperty,
)
from kivy.uix.widget import Widget
from kivy.uix.gridlayout import GridLayout
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
from kivy.uix.relativelayout import RelativeLayout
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput
from kivy.config import Config
Config.set('input', 'mouse', 'mouse,multitouch_on_demand')

from kivybackend import AgendaBackend, PROMPT_TEMPLATE_PASS1, PROMPT_TEMPLATE_PASS2

# --------------------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------------------
MODEL_REPO = "unsloth/Qwen3-4B-Instruct-2507-GGUF"
MODEL_FILENAME = "Qwen3-4B-Instruct-2507-Q4_1.gguf"

PACIFICA_BLUE = "#4682B4"  # headers / accents
PACIFICA_SAND = "#F5F5DC"  # background
TEXT_COLOR = "#222222"

DEFAULT_SPREADSHEET_HEADERS = {
    "date": "MEETING DATE",
    "section": "AGENDA SECTION",
    "item": "AGENDA ITEM",
    "notes": "NOTES",
    "include": "Include in Summary for Mayor",
}

# Column sizing for review screen (proportional widths)
COLUMN_SIZES = {
    "date": 0.1,
    "section": 0.17,
    "item": 0.38,
    "notes": 0.35
}

# --------------------------------------------------------------------------------------
# Native file dialog functions
# --------------------------------------------------------------------------------------
def native_open_file_dialog(title="Select File", file_types=None, multiple=False):
    """open file dialog using native OS dialogs (macOS via osascript, Windows via tkinter)"""
    if platform == 'win':
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()  # Hide the main window
            filepath = filedialog.askopenfilename(
                title=title,
                filetypes=file_types
            )
            return [filepath] if filepath else []
        except Exception as e:
            print(f"native file dialog error on windows: {e}")
            return None # fallback needed

    elif platform == "macosx":
        try:
            # Build the base AppleScript command
            script = f'choose file with prompt "{title}"'

            # Dynamically build the 'of type' clause from file_types
            if file_types:
                allowed_extensions = []
                for _, pattern in file_types:
                    # Filter out wildcards like '*.*' and get the extension
                    if pattern.startswith("*.") and pattern != "*.*":
                        allowed_extensions.append(pattern[2:])
                
                if allowed_extensions:
                    # Format for AppleScript: {"ext1", "ext2"}
                    type_list = ", ".join(f'"{ext}"' for ext in allowed_extensions)
                    script += f' of type {{{type_list}}}'
            
            # Finalize the script for osascript
            full_script = f'''
            set theFile to {script}
            return POSIX path of theFile
            '''
            
            result = subprocess.run(
                ["osascript", "-e", full_script],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0 and result.stdout.strip():
                posix_path = result.stdout.strip()
                print(f"native open dialog returned: {posix_path}")  # debug
                return [posix_path]
            
            if result.returncode == 1:
                # User cancelled the dialog. Return an empty list to signify this.
                print("Native open dialog cancelled by user.")
                return []
                
        except Exception as e:
            print(f"native file dialog error: {e}")
    
    return None  # fallback needed


def native_save_file_dialog(title="Save File", filename="", file_types=None):
    """save file dialog using native OS dialogs (macOS via osascript, Windows via tkinter)"""
    if platform == 'win':
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()  # Hide the main window
            filepath = filedialog.asksaveasfilename(
                title=title,
                initialfile=filename,
                filetypes=file_types,
                defaultextension=".docx"
            )
            return filepath if filepath else ""
        except Exception as e:
            print(f"native file dialog error on windows: {e}")
    elif platform == "macosx":
        try:
            # build applescript for save dialog that returns POSIX path directly
            script = f'''
            set theFile to choose file name with prompt "{title}"'''
            if filename:
                script += f' default name "{filename}"'
            script += '''
            return POSIX path of theFile
            '''
            
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
            
            if result.returncode == 1:
                # User cancelled the dialog. Return an empty string to signify this.
                print("Native save dialog cancelled by user.")
                return ""
                
        except Exception as e:
            print(f"native save dialog error: {e}")
    
    return None  # fallback needed

# --------------------------------------------------------------------------------------
# Helper widgets
# --------------------------------------------------------------------------------------
class StyledButton(Button):
    """Flat button with Pacifica colours, rounded corners, shadow, and hover effect."""
    is_hovered = BooleanProperty(False)
    # A ListProperty to store the base RGBA color of the button.
    # This will be used by _update_color for all state changes.
    base_bg_color_rgba = ListProperty([0, 0, 0, 0]) # Initial dummy value, will be set in __init__

    def __init__(self, bg_color_name_override: str | None = None, **kw):
        app = App.get_running_app()
        scale = app.gui_scale_factor if app else 1.0

        # Determine the initial base color based on override or default
        initial_hex_color = bg_color_name_override if bg_color_name_override else PACIFICA_BLUE
        self.base_bg_color_rgba = self.hex2rgba(initial_hex_color, 1.0)

        # set a default font_size if not provided by the caller
        if "font_size" not in kw:
            kw["font_size"] = 26
        kw["font_size"] = kw["font_size"] * scale

        if "width" in kw and kw["width"] is not None:
            kw["width"] = kw["width"] * scale

        if "height" in kw and kw["height"] is not None:
            kw["height"] = kw["height"] * scale

        super().__init__(
            background_normal="",
            background_color=[0, 0, 0, 0],  # transparent background
            color=[1, 1, 1, 1],
            **kw,
        )
        
        # bind to mouse position to check for hover
        Window.bind(mouse_pos=self.on_mouse_pos)
        # Bind _update_color to relevant properties including base_bg_color_rgba
        self.bind(
            pos=self._update_rect,
            size=self._update_rect,
            state=self._update_color,
            is_hovered=self._update_color,
            base_bg_color_rgba=self._update_color
        )

        with self.canvas.before:
            # Drop shadow
            self.shadow_color = Color(0, 0, 0, 0.2)
            self.shadow = RoundedRectangle(pos=self.pos, size=self.size, radius=[15 * scale])
            
            # Main background. Use base_bg_color_rgba for the initial color.
            self.bg_color = Color(*self.base_bg_color_rgba)
            self.rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[15 * scale])

    def on_mouse_pos(self, *args):
        """check if mouse is over the button"""
        if not self.get_root_window():
            return  # do nothing if button is not displayed
        
        pos = args[1]
        # check if cursor is within button bounds
        inside = self.collide_point(*self.to_widget(*pos))
        if self.is_hovered != inside:
            self.is_hovered = inside

    def _update_rect(self, *_):
        """update both shadow and main rectangle"""
        app = App.get_running_app()
        scale = app.gui_scale_factor if app else 1.0
        # shadow is slightly offset
        shadow_offset = 3 * scale
        self.shadow.pos = (self.pos[0] + shadow_offset, self.pos[1] - shadow_offset)
        self.shadow.size = self.size
        
        self.rect.pos = self.pos
        self.rect.size = self.size

    def _update_color(self, *_):
        """update color based on state (normal, hover, down)"""
        # Get the current base color from the property
        r, g, b, a = self.base_bg_color_rgba

        if self.state == 'down':
            # Darker color when pressed (e.g., 70% intensity)
            current_r, current_g, current_b = [min(1.0, max(0.0, c * 0.7)) for c in (r, g, b)]
            self.bg_color.rgba = [current_r, current_g, current_b, a]
            self.shadow_color.a = 0.1 # less shadow when pressed
        elif self.is_hovered:
            # Lighter color on hover (e.g., 15% lighter)
            current_r, current_g, current_b = [min(1.0, max(0.0, c * 1.15)) for c in (r, g, b)]
            self.bg_color.rgba = [current_r, current_g, current_b, a]
            self.shadow_color.a = 0.4 # more prominent shadow on hover
        else:
            # Normal state, use the base color
            self.bg_color.rgba = self.base_bg_color_rgba
            self.shadow_color.a = 0.2 # normal shadow

    @staticmethod
    def hex2rgba(hx: str, alpha=1.0):
        hx = hx.lstrip("#")
        return [int(hx[i : i + 2], 16) / 255.0 for i in (0, 2, 4)] + [alpha]


class TogglableStyledButton(StyledButton):
    """A StyledButton that can be toggled between active/inactive states."""
    active = BooleanProperty(False)

    def __init__(self, initial_active: bool, callback: Callable[[bool], None], text_on: str | None = None, text_off: str | None = None, **kw):
        # Text is managed internally, remove from kwargs if present.
        kw.pop("text", None)
        super().__init__(**kw)
        self.active = initial_active
        self._callback = callback
        self.text_on = text_on or "Debug Mode Enabled"
        self.text_off = text_off or "Debug Mode Disabled"

        # Bind visuals update to 'active' property change.
        # This will handle text update and trigger color update.
        self.bind(active=self._update_visuals)
        self.bind(on_release=self._on_release_toggle)

        # The parent StyledButton binds _update_color to state and is_hovered.
        # Our override of _update_color will be used automatically.
        
        # Set initial text and color.
        self._update_visuals(self, self.active)

    def _on_release_toggle(self, *args):
        """Toggle active state and call the callback."""
        self.active = not self.active
        self._callback(self.active)

    def _update_visuals(self, instance, value):
        """Update button text and trigger a color update."""
        self.text = self.text_on if self.active else self.text_off
        self._update_color()

    def _update_color(self, *_):
        """Override to integrate active state into hover/down logic."""
        if self.active:
            # Green shades for "Enabled"
            base_color = "#5CB85C"
            hover_color = "#6DC06D"
            pressed_color = "#4CAF50"
        else:
            # Red shades for "Disabled"
            base_color = "#D9534F"
            hover_color = "#E06B68"
            pressed_color = "#C9302C"

        if self.state == 'down':
            self.bg_color.rgba = self.hex2rgba(pressed_color, 0.9)
            self.shadow_color.a = 0.1
        elif self.is_hovered:
            self.bg_color.rgba = self.hex2rgba(hover_color, 1.0)
            self.shadow_color.a = 0.4
        else:
            self.bg_color.rgba = self.hex2rgba(base_color, 1.0)
            self.shadow_color.a = 0.2


class ToggleSwitch(BoxLayout):
    """Simple labelled on/off switch. This class is now obsolete."""

    active = BooleanProperty(False)

    def __init__(self, text: str, initial: bool, callback, **kw):
        super().__init__(orientation="horizontal", spacing=10, size_hint_y=None, height=32, **kw)
        self.add_widget(Label(text=text, color=[0, 0, 0, 1], size_hint_x=0.8, halign="left", valign="middle"))
        cb = CheckBox(active=initial)
        cb.bind(active=lambda _, v: callback(v))
        self.add_widget(cb)


class UploadZone(BoxLayout):
    """Unified drag-and-drop and click upload zone."""

    def __init__(self, app_instance, filetype: str = "xlsx", **kw):
        app = App.get_running_app()
        scale = app.gui_scale_factor if app else 1.0

        super().__init__(
            orientation="vertical",
            size_hint=(1, 7.0),
            padding=40 * scale,
            spacing=20 * scale,
            **kw,
        )
        self.app_instance = app_instance
        self.filetype = filetype
        self.is_hovered = False
        self.is_uninstalled_state = False

        # create the visual background
        with self.canvas.before:
            Color(*StyledButton.hex2rgba("#FFFFFF", 1))  # white base background
            self._bg_rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[15 * scale])
            self.overlay_color = Color(*StyledButton.hex2rgba(PACIFICA_BLUE, 0.4))  # blue overlay
            self._overlay_rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[15 * scale])

        self.bind(pos=self._update_canvas, size=self._update_canvas)

        # main upload text/button
        self.upload_label = Label(
            text=f"[size={int(48 * scale)}][b]Click to Upload Excel File[/b][/size]\n[size={int(28 * scale)}]or drag and drop your file here[/size]",
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
        self.hint_label = Label(
            text=f"[size={int(22 * scale)}]Supported format: Excel files (.xlsx)[/size]",
            markup=True,
            halign="center",
            valign="middle",
            color=[1, 1, 1, 0.8],  # slightly transparent white
            size_hint_y=None,
            height=35 * scale,
        )
        self.hint_label.bind(size=lambda inst, *_: inst.setter("text_size")(inst, (inst.width, None)))
        self.add_widget(self.hint_label)

    def set_uninstalled_state(self, is_uninstalled):
        app = App.get_running_app()
        scale = app.gui_scale_factor if app else 1.0
        self.is_uninstalled_state = is_uninstalled
        if is_uninstalled:
            self.upload_label.text = f"[size={int(48 * scale)}][b]Setup Required[/b][/size]\n[size={int(28 * scale)}]Please go to Settings to install the model.[/size]"
            self.hint_label.text = ""
            self.overlay_color.rgba = StyledButton.hex2rgba("#D9534F", 0.7) # Red
        else:
            self.upload_label.text = f"[size={int(48 * scale)}][b]Click to Upload Excel File[/b][/size]\n[size={int(28 * scale)}]or drag and drop your file here[/size]"
            self.hint_label.text = f"[size={int(22 * scale)}]Supported format: Excel files (.xlsx)[/size]"
            self.overlay_color.rgba = StyledButton.hex2rgba(PACIFICA_BLUE, 0.4) # Blue
        self._set_hover_state(False)


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
            if self.is_uninstalled_state:
                # Route directly to Model Settings when no model is installed
                self.app_instance._navigate_to("model_install")
                return True
            # add visual feedback by temporarily darkening the zone
            self._set_hover_state(True)
            # trigger file browser for the configured filetype
            self.app_instance._open_file_browser(self.filetype)
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
        if self.is_uninstalled_state:
            base_color = StyledButton.hex2rgba("#D9534F", 0.7)
            hover_color = StyledButton.hex2rgba("#D9534F", 0.9)
        else:
            base_color = StyledButton.hex2rgba(PACIFICA_BLUE, 0.4)
            hover_color = StyledButton.hex2rgba(PACIFICA_BLUE, 0.7)

        if hovered:
            self.overlay_color.rgba = hover_color
        else:
            self.overlay_color.rgba = base_color


class ModelUploadZone(UploadZone):
    """UploadZone specialised for .gguf model files."""
    def __init__(self, app_instance, **kw):
        super().__init__(app_instance, filetype="gguf", **kw)
        # Overwrite labels for model install context
        app = App.get_running_app()
        scale = app.gui_scale_factor if app else 1.0
        self.upload_label.text = (
            f"[size={int(48*scale)}][b]Click to Install Model[/b][/size]\n"
            f"[size={int(28*scale)}]or drag and drop your .gguf file here[/size]"
        )
        self.hint_label.text = f"[size={int(22*scale)}]Accepted file: *.gguf[/size]"


# --------------------------------------------------------------------------------------
# Simple item widget for the list
# --------------------------------------------------------------------------------------
class AgendaItem(BoxLayout):
    def __init__(self, date_text, section_text, item_text, notes_text, index, app, **kwargs):
        app = App.get_running_app()
        scale = app.gui_scale_factor if app else 1.0
        # Overall padding for the entire row (checkbox + columns)
        super().__init__(orientation="horizontal", padding=(20 * scale, 15 * scale), spacing=15 * scale, size_hint_y=None, **kwargs)
        
        self.app = app
        self.index = index
        self.selected = True  # start selected by default
        
        # Checkbox for selection
        self.checkbox = CheckBox(active=True, size_hint_x=None, width=40 * scale)
        self.checkbox.bind(active=self.on_checkbox_toggle)
        self.add_widget(self.checkbox)
        
        # Container for all columnar labels
        self.columns_container = BoxLayout(
            orientation="horizontal",
            size_hint_x=1, # Takes remaining horizontal space
            spacing=15 * scale,
            padding=10 * scale
        )
        self.add_widget(self.columns_container)

        # Individual labels for each column
        self.date_label = self._create_label(date_text, COLUMN_SIZES["date"])
        self.section_label = self._create_label(section_text, COLUMN_SIZES["section"])
        self.item_label = self._create_label(item_text, COLUMN_SIZES["item"])
        self.notes_label = self._create_label(notes_text, COLUMN_SIZES["notes"])
        
        self.columns_container.add_widget(self.date_label)
        self.columns_container.add_widget(self.section_label)
        self.columns_container.add_widget(self.item_label)
        self.columns_container.add_widget(self.notes_label)
        
        self.column_labels = [self.date_label, self.section_label, self.item_label, self.notes_label]

        # Bind to columns_container's width to recalculate text_size for its children
        self.columns_container.bind(width=self._update_column_layout)
        # Bind each label's texture_size to re-evaluate the overall row height
        for label in self.column_labels:
            label.bind(texture_size=self._on_label_texture_size)
        
        # Set initial background after widget is fully constructed
        from kivy.clock import Clock
        Clock.schedule_once(lambda dt: self._setup_initial_size(), 0)
    
    def _create_label(self, text, size_hint_x_val):
        """Helper to create consistently styled column labels."""
        app = App.get_running_app()
        scale = app.gui_scale_factor if app else 1.0
        return Label(
            text=text,
            markup=False,
            text_size=(None, None),  # Will be set dynamically
            halign="left",
            valign="top",  # Align to top for multi-line text
            color=[0, 0, 0, 1],
            size_hint_x=size_hint_x_val,
            size_hint_y=None,  # Important: don't let label stretch vertically by default
            font_size=26 * scale
        )
    
    def _setup_initial_size(self):
        """Setup initial text size and height after widget is constructed."""
        # Trigger layout update, which will in turn calculate label text_size and item height.
        self._update_column_layout()
        self.update_background()
    
    def _update_column_layout(self, *args):
        """Dynamically update text_size for all column labels based on container width."""
        # Calculate available width for the labels within columns_container
        # This accounts for columns_container's own internal padding and spacing
        available_width_for_labels = (
            self.columns_container.width
            - (self.columns_container.padding[0] + self.columns_container.padding[2])
            - (self.columns_container.spacing * (len(self.column_labels) - 1))
        )
        
        if available_width_for_labels <= 0:
            return

        for label in self.column_labels:
            # Calculate actual width for each label based on its size_hint_x
            label_actual_width = available_width_for_labels * label.size_hint_x
            if label_actual_width > 0:
                label.text_size = (label_actual_width, None) # Set width, height will adjust automatically
    
    def _on_label_texture_size(self, instance, texture_size):
        """Callback when any individual label's rendered text size changes."""
        # Update the specific label's height to match its content
        instance.height = texture_size[1]
        
        # Find the maximum height among all column labels to determine row height
        max_label_height = 0
        for label in self.column_labels:
            max_label_height = max(max_label_height, label.texture_size[1] if label.texture_size else 0)
            
        # Set the height of the columns_container to fit the tallest label plus its vertical padding
        self.columns_container.height = max_label_height + (self.columns_container.padding[1] + self.columns_container.padding[3])
        
        app = App.get_running_app()
        scale = app.gui_scale_factor if app else 1.0
        # Set the overall AgendaItem (row) height, ensuring a minimum height
        self.height = max(50 * scale, self.columns_container.height + (self.padding[1] + self.padding[3]))

    
    def on_size(self, *args):
        """Update background when widget size changes."""
        self.update_background()
        # No need to call _update_column_layout or _draw_column_separators directly here
        # as columns_container.width/pos binding handles it.
    
    def on_checkbox_toggle(self, checkbox, value):
        """handle checkbox toggle"""
        self.selected = value
        self.update_background()
        
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


class ModelInstallScreen(Screen):
    """Screen for offline model installation via drag-and-drop or file chooser."""
    pass


# --------------------------------------------------------------------------------------
# Main App
# --------------------------------------------------------------------------------------
class PacificaAgendaApp(App):
    title = "City of Pacifica - Agenda Summary Generator"

    gui_scale_factor = NumericProperty(1.0)
    backend: AgendaBackend
    screen_manager: ScreenManager = ObjectProperty(None)
    spreadsheet_data: pd.DataFrame | None = None
    filtered_items: List[pd.Series] = []
    selected_indices: set[int] = set()
    generation_cancel_event = threading.Event()

    auto_scroll_gen = BooleanProperty(True)
    auto_scroll_debug = BooleanProperty(True)

    generated_report_text = ""
    meeting_dates_for_report: List[str] = []
    prompt_pass1: str = ""
    prompt_pass2: str = ""
    spreadsheet_headers: dict = {}

    debug_console: TextInput | None = None
    sv_debug: ScrollView | None = None
    sv_gen_output: ScrollView | None = None

    # New properties for dynamic layout control
    generation_area: BoxLayout | None = None        # Reference to the main generation layout
    gen_output_container: BoxLayout | None = None  # Reference to the main output container
    debug_container: BoxLayout | None = None       # Reference to the debug console's container

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Config persistence
        self.config_file = os.path.join(self.user_data_dir, "pacifica_agenda_gui.json")
        self.CONF = self._load_conf()

        self.gui_scale_factor = self.CONF.get("gui_scale", 1.0)

        # Load prompts from config, with fallback to defaults
        self.prompt_pass1 = self.CONF.get("prompt_pass1") or PROMPT_TEMPLATE_PASS1
        self.prompt_pass2 = self.CONF.get("prompt_pass2") or PROMPT_TEMPLATE_PASS2
        # Load spreadsheet headers from config, with fallback to defaults
        self.spreadsheet_headers = (
            self.CONF.get("spreadsheet_headers") or DEFAULT_SPREADSHEET_HEADERS.copy()
        )

    def _load_conf(self) -> dict:
        default_conf = {
            "current_model": "",
            "prompt_pass1": None,
            "prompt_pass2": None,
            "spreadsheet_headers": None,
            "debug": False,
            "ignore_brackets": False,
            "gui_scale": 1.0,
        }
        try:
            with open(self.config_file, "r", encoding="utf-8") as fp:
                data = json.load(fp)
                # Ensure new keys exist for older configs
                if "spreadsheet_headers" not in data:
                    data["spreadsheet_headers"] = DEFAULT_SPREADSHEET_HEADERS.copy()
                if "ignore_brackets" not in data:
                    data["ignore_brackets"] = False
                if "gui_scale" not in data:
                    data["gui_scale"] = 1.0
                default_conf.update(data)
        except Exception:
            # On first run or error, populate with defaults
            default_conf["spreadsheet_headers"] = DEFAULT_SPREADSHEET_HEADERS.copy()
        return default_conf

    def _save_conf(self):
        self.CONF["gui_scale"] = self.gui_scale_factor
        try:
            with open(self.config_file, "w", encoding="utf-8") as fp:
                json.dump(self.CONF, fp, indent=2)
        except Exception as e:
            # Inform the user rather than failing silently
            self._show_error(
                "Settings Save Error",
                f"Unable to save settings to:\n{self.config_file}\n\n"
                f"This means recent changes may not persist.\n\nDetails: {e}"
            )

    def build(self):
        Window.clearcolor = StyledButton.hex2rgba(PACIFICA_SAND, 1)
        
        self.backend = AgendaBackend(
            user_data_dir=self.user_data_dir,
        )

        self.screen_manager = ScreenManager(transition=SlideTransition(duration=0.25))
        self._build_home()
        self._build_review()
        self._build_generation()
        self._build_settings()
        self._build_help()
        self._build_credits()
        self._build_model_install()

        # Set initial model status in settings UI
        self._update_model_status()

        # Set initial debug console visibility based on loaded config
        self._update_debug_console_visibility(self.CONF["debug"])

        # Update home screen UI based on installation status
        self._update_home_screen_ui()

        # Load selected model if configured
        self._initialize_model_loading()

        # bind drag-and-drop
        if platform in ("win", "linux", "macosx"):
            Window.bind(on_dropfile=self._on_file_drop)

        return self.screen_manager

    def on_start(self):
        """this is called after build() and the window is created, so we can center it"""
        try:
            # calculate the position and set it
            Window.left = 100
            Window.top = 50
            Window.maximize()
        except Exception as e:
            print(f"could not center window: {e}")

    def _navigate_to(self, screen_name: str):
        """navigate to a screen with proper slide direction"""
        current_screen = self.screen_manager.current
        
        # determine slide direction based on navigation flow
        if current_screen == "home":
            # going from home to any other screen slides left
            self.screen_manager.transition.direction = "left"
        elif screen_name == "home":
            # going back to home from any screen slides right
            self.screen_manager.transition.direction = "right"
        elif current_screen == "review" and screen_name == "generation":
            # going from review to generation slides left
            self.screen_manager.transition.direction = "left"
        elif current_screen == "generation" and screen_name == "review":
            # going back from generation to review slides right
            self.screen_manager.transition.direction = "right"
        elif current_screen == "model_install" and screen_name == "settings":
            # going back from model install to settings slides right
            self.screen_manager.transition.direction = "right"
        else:
            # default direction for other transitions
            self.screen_manager.transition.direction = "left"
        
        self.screen_manager.current = screen_name

    # ---------------------------------------------------------------- Home
    def _build_home(self):
        scale = self.gui_scale_factor
        scr = HomeScreen(name="home")
        root = BoxLayout(orientation="vertical", padding=40 * scale, spacing=20 * scale)
        scr.add_widget(root)

        # logo and header container
        logo_header = BoxLayout(orientation="horizontal", size_hint=(1, None), height=200 * scale, spacing=20 * scale)
        logo_header.add_widget(Widget(size_hint_x=1))  # add spacer to center content
        try:
            from kivy.uix.image import Image as KivyImage
            if os.path.exists("logo.png"):
                logo = KivyImage(source="logo.png", size_hint=(None, None), size=(180 * scale, 180 * scale))
                logo_header.add_widget(logo)
        except Exception:
            pass
        header = Label(
            text="[b]City of Pacifica[/b]\nAgenda Summary Generator",
            markup=True,
            font_size=36 * scale,
            color=[0, 0, 0, 1],
            size_hint=(2, None),
            height=180 * scale,
        )
        header.halign = "center"
        header.valign = "middle"
        header.bind(width=lambda inst, w: inst.setter("text_size")(inst, (w, None)))
        logo_header.add_widget(header)
        logo_header.add_widget(Widget(size_hint_x=1))  # add spacer to center content
        root.add_widget(logo_header)

        # unified upload zone (replaces both drop area and browse button)
        self.upload_zone = UploadZone(self)
        root.add_widget(self.upload_zone)

        nav_bar = BoxLayout(orientation='horizontal', size_hint_y=None, height=75 * scale, spacing=15 * scale)
        nav_bar.add_widget(Widget())

        settings_btn = StyledButton(text="Settings", size_hint=(None, None), width=220, height=75)
        settings_btn.bind(on_release=lambda *_: self._navigate_to("settings"))
        nav_bar.add_widget(settings_btn)

        help_btn = StyledButton(text="Help", size_hint=(None, None), width=220, height=75)
        help_btn.bind(on_release=lambda *_: self._navigate_to("help"))
        nav_bar.add_widget(help_btn)

        credits_btn = StyledButton(text="Credits", size_hint=(None, None), width=220, height=75)
        credits_btn.bind(on_release=lambda *_: self._navigate_to("credits"))
        nav_bar.add_widget(credits_btn)

        nav_bar.add_widget(Widget())
        root.add_widget(nav_bar)
        
        # Add a spacer to push the source label to the bottom.
        root.add_widget(Widget(size_hint_y=1))

        # Small note about source code / extra details
        source_label = Label(
            text=f"[size={int(24 * scale)}]Source code and extra details available at the bottom of the Help menu![/size]",
            markup=True,
            halign="center",
            valign="middle",
            color=[0.45, 0.58, 0.7, 1],
            size_hint_y=None,
            height=30 * scale,
        )
        root.add_widget(source_label)

        root.add_widget(Label(size_hint_y=0.1))  # smaller spacer
        self.screen_manager.add_widget(scr)


    def _open_file_browser(self, filetype: str):
        # try native dialog first
        if filetype == "xlsx":
            title = "Select Excel File"
            if platform == "macosx":
                # On macOS, don't filter to avoid greyed-out files. We'll validate post-selection.
                filters = None
            else:
                # On Windows, use filters for better UX. On other platforms, allow all and validate later.
                filters = [("Excel files", "*.xlsx"), ("All files", "*.*")]
        elif filetype == "gguf":
            if platform == "macosx":
                # On macOS, don't filter to avoid lag/greyed-out files. We'll validate post-selection.
                filters = None
            else:
                # On other platforms, filtering is fine.
                filters = [("GGUF model files", "*.gguf"), ("All files", "*.*")]
            title = "Select a .gguf model file"
        else:
            filters = [("All files", "*.*")]
            title = "Select File"
        
        selection = native_open_file_dialog(title=title, file_types=filters)
        # If native dialog was used, selection will be a list (empty on cancel).
        # If native dialog is not supported/failed, it will be None.
        if selection is not None:
            if selection:  # If list is not empty (file was selected)
                path = selection[0]
                if filetype == "xlsx":
                    if not path.lower().endswith(".xlsx"):
                        self._show_error("Invalid File Type", "Please select a Microsoft Excel .xlsx file.")
                        return
                    self._process_spreadsheet_file(path)
                elif filetype == "gguf":
                    self._handle_gguf_file(path)
            return  # Return here to prevent Kivy fallback
        
        # fallback to kivy file chooser
        if filetype == "xlsx":
            # On macOS, allow all files and post-validate like native. Else, filter to .xlsx for convenience.
            kivy_filters = None if platform == "macosx" else ["*.xlsx"]
            popup_title = "Select Excel File"
            callback = self._process_spreadsheet_file
        elif filetype == "gguf":
            kivy_filters = ["*.gguf"]
            popup_title = "Select .gguf Model File"
            callback = self._handle_gguf_file
        else:
            kivy_filters = None
            popup_title = "Select File"
            callback = lambda _: None # No-op for unknown types

        chooser = FileChooserListView(filters=kivy_filters, path=os.getcwd())
        popup = Popup(title=popup_title, content=chooser, size_hint=(0.9, 0.9))

        def _file_chosen(instance, selection, touch):
            if selection:
                path = selection[0]
                if filetype == "xlsx" and not path.lower().endswith(".xlsx"):
                    # Keep popup open; inform user of invalid selection
                    self._show_error("Invalid File Type", "Please select a Microsoft Excel .xlsx file.")
                    return
                popup.dismiss()
                callback(path)

        chooser.bind(on_submit=_file_chosen)
        popup.open()

    def _on_file_drop(self, _window, file_path_bytes):
        path = file_path_bytes.decode("utf-8")
        current_screen = self.screen_manager.current

        if path.lower().endswith(".xlsx") and current_screen == "home":
            self._process_spreadsheet_file(path)
        elif path.lower().endswith(".gguf") and current_screen == "model_install":
            self._handle_gguf_file(path)

    def _process_spreadsheet_file(self, filepath: str):
        """Process an Excel file by first allowing user to select a sheet.

        Uses a context-managed ExcelFile to ensure handles are closed promptly.
        Retries once after a short delay if Windows intermittently throws
        'ValueError: I/O operation on closed file'.
        """
        try:
            # Helper wrapped in a context-manager so the underlying file handle
            # is deterministically released as soon as we're done.
            def _get_sheet_names():
                with pd.ExcelFile(filepath) as excel_file:
                    return excel_file.sheet_names

            try:
                sheet_names = _get_sheet_names()
            except ValueError as e:
                # Windows race-condition workaround: retry once after 100 ms.
                if "I/O operation on closed file" in str(e):
                    time.sleep(0.1)
                    sheet_names = _get_sheet_names()
                else:
                    raise

            if not sheet_names:
                self._show_error("Excel Error", "The Excel file contains no sheets.")
                return

            # If only one sheet, process it directly
            if len(sheet_names) == 1:
                self._load_and_process_sheet(filepath, sheet_names[0])
            else:
                # Show sheet selection popup
                self._show_sheet_selection_popup(filepath, sheet_names)

        except Exception as exc:
            self._show_error("Excel Error", f"Failed to read Excel file: {str(exc)}")
            return

    def _show_sheet_selection_popup(self, filepath: str, sheet_names: List[str]):
        """Display a popup with a scrollable, clickable list of sheets. Selected row is blue-highlighted."""
        scale = self.gui_scale_factor
        
        content = BoxLayout(orientation='vertical', spacing=10 * scale, padding=10 * scale)
        
        # Instructions
        label = Label(
            text="Please select the sheet containing your agenda data:",
            size_hint_y=None,
            height=40 * scale,
            font_size=24 * scale,
            color=[1, 1, 1, 1]
        )
        content.add_widget(label)

        # Scrollable list of sheet names
        from math import ceil
        row_height = 60 * scale

        scroll = ScrollView(size_hint_y=1, scroll_wheel_distance=15 * scale)
        list_container = BoxLayout(orientation='vertical', spacing=6 * scale, size_hint_y=None)
        list_container.bind(minimum_height=list_container.setter('height'))

        # Add white background to list_container to fill empty space
        with list_container.canvas.before:
            Color(1, 1, 1, 1)
            self.list_rect = Rectangle(pos=list_container.pos, size=list_container.size)
        def update_rect(instance, value):
            self.list_rect.pos = instance.pos
            self.list_rect.size = instance.size
        list_container.bind(pos=update_rect, size=update_rect)

        scroll.add_widget(list_container)
        content.add_widget(scroll)

        # Track selection
        selected_index = [0]  # mutable container for closure
        buttons: List[Button] = []

        # Helper to update visuals for selection
        def update_visuals():
            for i, btn in enumerate(buttons):
                if i == selected_index[0]:
                    btn.background_normal = ""
                    btn.background_color = StyledButton.hex2rgba(PACIFICA_BLUE, 1.0)
                    btn.color = [1, 1, 1, 1]
                else:
                    btn.background_normal = ""
                    btn.background_color = [1, 1, 1, 1]
                    btn.color = [0, 0, 0, 1]

        # Create a button for each sheet
        for idx, name in enumerate(sheet_names):
            btn = Button(
                text=name,
                size_hint_y=None,
                height=row_height,
                font_size=26 * scale,
                background_normal="",
                background_color=[1, 1, 1, 1],
                color=[0, 0, 0, 1],
                halign="left",
                valign="middle"
            )
            # Ensure text wraps/pads nicely
            btn.text_size = (None, None)

            def on_btn_release(instance, i=idx):
                selected_index[0] = i
                update_visuals()

            btn.bind(on_release=on_btn_release)
            buttons.append(btn)
            list_container.add_widget(btn)

        # Initialize visuals with first item selected
        update_visuals()

        # Buttons
        btn_layout = BoxLayout(size_hint_y=None, height=75 * scale, spacing=10 * scale)
        cancel_btn = StyledButton(text="Cancel")
        select_btn = StyledButton(text="Select")
        btn_layout.add_widget(cancel_btn)
        btn_layout.add_widget(select_btn)
        content.add_widget(btn_layout)
        
        popup = Popup(
            title="Select Sheet",
            content=content,
            size_hint=(0.6, 0.6),
            auto_dismiss=False
        )
        
        def on_select(*_):
            idx = selected_index[0] if 0 <= selected_index[0] < len(sheet_names) else 0
            selected_sheet = sheet_names[idx]
            popup.dismiss()
            self._load_and_process_sheet(filepath, selected_sheet)
        
        def on_cancel(*_):
            popup.dismiss()
        
        select_btn.bind(on_release=on_select)
        cancel_btn.bind(on_release=on_cancel)
        
        popup.open()
    
    def _load_and_process_sheet(self, filepath: str, sheet_name: str):
        """Load the selected sheet and process it through the backend.

        Wraps `pd.read_excel` in a retry to mitigate transient Windows file-locking.
        """
        try:
            # Read the specific sheet into a DataFrame with retry.
            def _read_df():
                return pd.read_excel(filepath, sheet_name=sheet_name)

            try:
                df = _read_df()
            except ValueError as e:
                if "I/O operation on closed file" in str(e):
                    time.sleep(0.1)
                    df = _read_df()
                else:
                    raise

            # Process through the backend
            self.spreadsheet_data, self.filtered_items = self.backend.process_spreadsheet_data(
                df, self.spreadsheet_headers
            )

            # Navigate to review screen
            self._populate_review_list()
            self._navigate_to("review")

        except Exception as exc:
            self._show_error("Processing Error", str(exc))

    # ---------------------------------------------------------------- Review screen
    def _build_review(self):
        scale = self.gui_scale_factor
        scr = ReviewScreen(name="review")
        layout = BoxLayout(orientation="vertical", padding=20 * scale, spacing=15 * scale)
        scr.add_widget(layout)

        topbar = BoxLayout(orientation="horizontal", size_hint_y=None, height=75 * scale, spacing=10 * scale)
        back_btn = StyledButton(text="Back", size_hint=(None, None), width=180, height=75)
        back_btn.bind(on_release=lambda *_: self._navigate_to("home"))
        topbar.add_widget(back_btn)

        self.review_label = Label(text="Items Selected: 0", color=[0, 0, 0, 1], font_size=50 * scale)
        topbar.add_widget(self.review_label)

        gen_btn = StyledButton(text="Generate", size_hint=(None, None), width=240, height=75)
        gen_btn.bind(on_release=lambda *_: self._start_generation())
        topbar.add_widget(gen_btn)

        layout.add_widget(topbar)

        # Create a scrollable list using ScrollView and BoxLayout
        # Header row for columns
        header_container = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=50 * scale,
            padding=(20 * scale, 15 * scale), # Match AgendaItem's outer padding
            spacing=15 * scale # Match AgendaItem's outer spacing
        )
        with header_container.canvas.before:
            Color(*StyledButton.hex2rgba(PACIFICA_BLUE, 0.2)) # Light blue header background
            Rectangle(pos=header_container.pos, size=header_container.size)
        header_container.bind(pos=lambda inst, val: setattr(inst.canvas.before.children[-1], 'pos', val),
                              size=lambda inst, val: setattr(inst.canvas.before.children[-1], 'size', val))

        # Placeholder for checkbox column
        header_container.add_widget(Widget(size_hint_x=None, width=40 * scale))

        # Container for header labels to match AgendaItem's internal structure
        header_labels_container = BoxLayout(
            orientation="horizontal",
            size_hint_x=1,
            spacing=15 * scale,
            padding=10 * scale
        )
        header_labels_container.add_widget(Label(text="Date", size_hint_x=COLUMN_SIZES["date"], halign="left", valign="middle", color=TEXT_COLOR, font_size=26 * scale, bold=True))
        header_labels_container.add_widget(Label(text="Section", size_hint_x=COLUMN_SIZES["section"], halign="left", valign="middle", color=TEXT_COLOR, font_size=26 * scale, bold=True))
        header_labels_container.add_widget(Label(text="Item", size_hint_x=COLUMN_SIZES["item"], halign="left", valign="middle", color=TEXT_COLOR, font_size=26 * scale, bold=True))
        header_labels_container.add_widget(Label(text="Notes", size_hint_x=COLUMN_SIZES["notes"], halign="left", valign="middle", color=TEXT_COLOR, font_size=26 * scale, bold=True))
        
        layout.add_widget(header_container)
        header_container.add_widget(header_labels_container)

        scroll = ScrollView(size_hint=(1, 1), scroll_distance=100, scroll_wheel_distance=150 * scale)
        self.items_container = BoxLayout(orientation='vertical', size_hint_y=None, spacing=2)
        self.items_container.bind(minimum_height=self.items_container.setter('height'))
        scroll.add_widget(self.items_container)
        layout.add_widget(scroll)

        sel_bar = BoxLayout(size_hint_y=None, height=75 * scale, spacing=10 * scale)
        sel_all = StyledButton(text="Select All", size_hint=(None, None), width=220, height=75)
        sel_all.bind(on_release=lambda *_: self._select_all_items(True))
        sel_bar.add_widget(sel_all)
        desel_all = StyledButton(text="Deselect All", size_hint=(None, None), width=220, height=75)
        desel_all.bind(on_release=lambda *_: self._select_all_items(False))
        sel_bar.add_widget(desel_all)
        layout.add_widget(sel_bar)

        self.screen_manager.add_widget(scr)

    def _populate_review_list(self):
        self.selected_indices.clear()
        self.items_container.clear_widgets()

        for idx, row in enumerate(self.filtered_items):
            # pre-select if Include column is 'y' or 'yes' (case-insensitive)
            include_val = str(row.get(self.spreadsheet_headers["include"], "")).strip().lower()
            include_flag = include_val in ("y", "yes")

            # Extract individual column data
            # Get the ignore_brackets setting
            ignore_brackets = self.CONF.get("ignore_brackets", False)

            date_text = self.backend.get_display_date(row.get(self.spreadsheet_headers["date"], ""))
            section_text = str(row.get(self.spreadsheet_headers["section"], "")).replace("\n", " ").replace("•", "-").strip()
            if section_text == "nan":
                section_text = "placeholder" # Or suitable default/empty string
            item_text = str(row.get(self.spreadsheet_headers["item"], "")).replace("\n", " ").replace("•", "-").strip()
            if item_text == "nan":
                item_text = "unnamed item" # Or suitable default/empty string
            notes_text = ""
            if pd.notna(row.get(self.spreadsheet_headers["notes"])):
                n = str(row[self.spreadsheet_headers["notes"]]).replace("\n", " ").replace("•", "-").strip()
                if n and n.lower() != "nan":
                    notes_text = n
            
            # Conditionally strip brackets if setting is enabled
            if ignore_brackets:
                date_text = re.sub(r'\[.*?\]', '', date_text).strip()
                section_text = re.sub(r'\[.*?\]', '', section_text).strip()
                item_text = re.sub(r'\[.*?\]', '', item_text).strip()
                notes_text = re.sub(r'\[.*?\]', '', notes_text).strip()

            # Instantiate AgendaItem with individual column data
            widget = AgendaItem(date_text, section_text, item_text, notes_text, idx, self)
            widget.checkbox.active = include_flag
            widget.selected = include_flag

            self.items_container.add_widget(widget)
            if include_flag:
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
        scale = self.gui_scale_factor
        scr = GenerationScreen(name="generation")
        layout = BoxLayout(orientation="vertical", padding=10 * scale, spacing=10 * scale)
        scr.add_widget(layout)

        top = BoxLayout(orientation="horizontal", size_hint_y=None, height=75 * scale, spacing=10 * scale)
        self.back_gen_btn = StyledButton(text="Back", size_hint=(None, None), width=180, height=75)
        self.back_gen_btn.bind(on_release=lambda *_: self._cancel_generation())
        top.add_widget(self.back_gen_btn)

        save_btn = StyledButton(text="Save DOCX", size_hint=(None, None), width=220, height=75)
        save_btn.disabled = True
        self.save_button = save_btn
        save_btn.bind(on_release=lambda *_: self._save_report())
        top.add_widget(save_btn)

        copy_btn = StyledButton(text="Copy Text", size_hint=(None, None), width=220, height=75)
        copy_btn.disabled = True
        self.copy_button = copy_btn
        copy_btn.bind(on_release=lambda *_: self._copy_report_to_clipboard())
        top.add_widget(copy_btn)

        layout.add_widget(top)

        # A container for all generation-related outputs that will take up the remaining space
        self.generation_area = BoxLayout(orientation='vertical', spacing=10 * scale)
        layout.add_widget(self.generation_area)

        # --- Main Generation Output Area ---
        # This container will have a fixed proportional height, making the ScrollView stable.
        self.gen_output_container = BoxLayout(orientation='vertical')

        self.gen_output = TextInput(
            readonly=True,
            font_size=28 * scale,
            foreground_color=[0, 0, 0, 1],
            background_color=[1, 1, 1, 1],
            size_hint_y=None,
        )
        self.gen_output.bind(minimum_height=self.gen_output.setter('height'))

        self.sv_gen_output = ScrollView(scroll_wheel_distance=50 * scale)
        self.sv_gen_output.add_widget(self.gen_output)
        self.sv_gen_output.bind(on_scroll_stop=self._on_scroll_stop)
        self.gen_output_container.add_widget(self.sv_gen_output)

        # --- Optional Debug Console Area ---
        # ALWAYS create debug console components, their visibility is controlled later
        # Initialize main output to full height; this will be adjusted by _update_debug_console_visibility
        self.gen_output_container.size_hint_y = 1.0
        self.generation_area.add_widget(self.gen_output_container)

        self.debug_container = BoxLayout(orientation='vertical', size_hint_y=0.5, spacing=5 * scale)
        
        debug_title = Label(
            text="[b]Debug Console[/b]",
            markup=True,
            size_hint_y=None,
            height=30 * scale,
            color=TEXT_COLOR,
            font_size=20 * scale
        )
        self.debug_container.add_widget(debug_title)

        self.debug_console = TextInput(
            readonly=True,
            size_hint_y=None,
            background_color=[0.1, 0.1, 0.1, 1],
            foreground_color=[0.8, 1.0, 0.8, 1],
            font_size=14 * scale
        )
        self.debug_console.bind(minimum_height=self.debug_console.setter('height'))

        self.sv_debug = ScrollView(scroll_wheel_distance=50 * scale)
        self.sv_debug.add_widget(self.debug_console)
        self.sv_debug.bind(on_scroll_stop=self._on_scroll_stop)
        self.debug_container.add_widget(self.sv_debug)

        # DO NOT add self.debug_container to self.generation_area here.
        # This will be handled dynamically by _update_debug_console_visibility.

        self.screen_manager.add_widget(scr)

    def _update_debug_console_visibility(self, visible: bool):
        """
        Dynamically adds/removes the debug console and adjusts layout.
        Called from build() for initial setup and _toggle_debug() for runtime changes.
        """
        # Ensure all necessary widgets have been built and assigned to self.properties
        if self.generation_area is None or self.gen_output_container is None or \
           self.debug_container is None or self.debug_console is None or self.sv_debug is None:
            print("Warning: Debug console components not fully initialized. Cannot update visibility.")
            return

        if visible:
            # If debug is on, add debug_container and set proportional heights
            if self.debug_container not in self.generation_area.children:
                self.generation_area.add_widget(self.debug_container)
            self.gen_output_container.size_hint_y = 0.5
            self.debug_container.size_hint_y = 0.5
        else:
            # If debug is off, remove debug_container and make main output take full height
            if self.debug_container in self.generation_area.children:
                self.generation_area.remove_widget(self.debug_container)
            self.gen_output_container.size_hint_y = 1.0
            # self.debug_container.size_hint_y will retain 0.5 but won't be in layout.

        # Schedule a layout update to ensure changes are applied immediately
        # (A small delay can sometimes help Kivy's layout engine react better)
        from kivy.clock import Clock
        Clock.schedule_once(lambda dt: self.generation_area.do_layout(), 0)

    # ---------------------------------------------------------------- Settings
    def _build_settings(self):
        scale = self.gui_scale_factor
        scr = SettingsScreen(name="settings")
        root = BoxLayout(orientation="vertical", padding=20 * scale, spacing=20 * scale)
        scr.add_widget(root)

        title = Label(text="[b]Settings[/b]", markup=True, font_size=48 * scale, size_hint_y=None, height=80 * scale, color=[0, 0, 0, 1])
        root.add_widget(title)

        grid = GridLayout(cols=2, rows=6, row_force_default=True, row_default_height=75 * scale, spacing=(10 * scale,10 * scale), size_hint_y=None)
        grid.bind(minimum_height=grid.setter('height'))

        # Model row
        label_model = Label(
            text="Model",
            color=[0, 0, 0, 1],
            font_size=28 * scale,
            bold=True,
            halign='left',
            valign='middle',
            size_hint_x=0.3
        )
        label_model.bind(size=lambda inst, *_: inst.setter('text_size')(inst, (inst.width, None)))
        self.model_status_lbl = Label(
            text="Checking...",
            color=[0, 0, 0, 1],
            halign='left',
            font_size=28 * scale
        )
        self.model_status_lbl.bind(size=lambda inst, *_: inst.setter('text_size')(inst, (inst.width, None)))
        self.install_model_btn = StyledButton(
            text="Model Settings",
            size_hint=(None, None),
            width=280,
            height=75
        )
        self.install_model_btn.bind(on_release=lambda *_: self._open_model_install_menu())
        control_model = BoxLayout(orientation="horizontal", spacing=10 * scale, size_hint_x=0.7)
        control_model.add_widget(self.model_status_lbl)
        control_model.add_widget(self.install_model_btn)
        grid.add_widget(label_model)
        grid.add_widget(control_model)

        # Prompt Templates row
        label_prompts = Label(
            text="Prompt Templates",
            color=[0, 0, 0, 1],
            font_size=28 * scale,
            bold=True,
            halign='left',
            valign='middle',
            size_hint_x=0.3
        )
        label_prompts.bind(size=lambda inst, *_: inst.setter('text_size')(inst, (inst.width, None)))
        edit_p1_btn = StyledButton(text="Edit Pass 1 Prompt", size_hint_x=None, width=300)
        edit_p1_btn.bind(on_release=lambda *_: self._open_prompt_editor("pass1"))
        edit_p2_btn = StyledButton(text="Edit Pass 2 Prompt", size_hint_x=None, width=300)
        edit_p2_btn.bind(on_release=lambda *_: self._open_prompt_editor("pass2"))
        control_prompts = BoxLayout(orientation="horizontal", spacing=10 * scale, size_hint_x=0.7)
        control_prompts.add_widget(edit_p1_btn)
        control_prompts.add_widget(edit_p2_btn)
        grid.add_widget(label_prompts)
        grid.add_widget(control_prompts)

        # Spreadsheet Headers row
        label_headers = Label(
            text="Spreadsheet Column Required Header Names",
            color=[0, 0, 0, 1],
            font_size=28 * scale,
            bold=True,
            halign='left',
            valign='middle',
            size_hint_x=0.3
        )
        label_headers.bind(size=lambda inst, *_: inst.setter('text_size')(inst, (inst.width, None)))
        
        control_headers = BoxLayout(orientation="horizontal", spacing=5 * scale, size_hint_x=0.7)
        
        # Create buttons for each header. Use smaller font size to fit and set fixed width.
        btn_h_date = StyledButton(text="Date", font_size=22, size_hint_x=None, width=150, on_release=lambda *_: self._open_header_editor("date", "Meeting Date Header"))
        btn_h_section = StyledButton(text="Section", font_size=22, size_hint_x=None, width=150, on_release=lambda *_: self._open_header_editor("section", "Agenda Section Header"))
        btn_h_item = StyledButton(text="Item", font_size=22, size_hint_x=None, width=150, on_release=lambda *_: self._open_header_editor("item", "Agenda Item Header"))
        btn_h_notes = StyledButton(text="Notes", font_size=22, size_hint_x=None, width=150, on_release=lambda *_: self._open_header_editor("notes", "Notes Header"))
        btn_h_include = StyledButton(text="Include", font_size=22, size_hint_x=None, width=150, on_release=lambda *_: self._open_header_editor("include", "Include Flag Header"))

        control_headers.add_widget(btn_h_date)
        control_headers.add_widget(btn_h_section)
        control_headers.add_widget(btn_h_item)
        control_headers.add_widget(btn_h_notes)
        control_headers.add_widget(btn_h_include)
        control_headers.add_widget(Widget()) # Add a spacer to push buttons to the left

        grid.add_widget(label_headers)
        grid.add_widget(control_headers)

        # Debug Mode row
        label_debug = Label(
            text="Debug Mode",
            color=[0, 0, 0, 1],
            font_size=28 * scale,
            bold=True,
            halign='left',
            valign='middle',
            size_hint_x=0.3
        )
        label_debug.bind(size=lambda inst, *_: inst.setter('text_size')(inst, (inst.width, None)))
        debug_toggle_btn = TogglableStyledButton(
            initial_active=self.CONF["debug"],
            callback=self._toggle_debug,
            size_hint=(None, None),
            width=320,
            height=75
        )
        control_debug = BoxLayout(orientation="horizontal", spacing=10 * scale, size_hint_x=0.7)
        control_debug.add_widget(debug_toggle_btn)
        control_debug.add_widget(Widget()) # Add a spacer to push button to left if control_debug takes more space
        grid.add_widget(label_debug)
        grid.add_widget(control_debug)

        # Ignore Brackets row
        label_brackets = Label(
            text="Ignore Bracketed Text []",
            color=[0, 0, 0, 1],
            font_size=28 * scale,
            bold=True,
            halign='left',
            valign='middle',
            size_hint_x=0.3
        )
        label_brackets.bind(size=lambda inst, *_: inst.setter('text_size')(inst, (inst.width, None)))
        brackets_toggle_btn = TogglableStyledButton(
            initial_active=self.CONF.get("ignore_brackets", False),
            callback=self._toggle_ignore_brackets,
            size_hint=(None, None),
            width=320,
            height=75,
            text_on="Ignoring Brackets",
            text_off="Not Ignoring Brackets"
        )
        control_brackets = BoxLayout(orientation="horizontal", spacing=10 * scale, size_hint_x=0.7)
        control_brackets.add_widget(brackets_toggle_btn)
        control_brackets.add_widget(Widget())
        grid.add_widget(label_brackets)
        grid.add_widget(control_brackets)
        
        # GUI Scale row
        label_scale = Label(
            text="GUI Scale Factor",
            color=[0, 0, 0, 1],
            font_size=28 * scale,
            bold=True,
            halign='left',
            valign='middle',
            size_hint_x=0.3
        )
        label_scale.bind(size=lambda inst, *_: inst.setter('text_size')(inst, (inst.width, None)))
        
        self.scale_input = TextInput(
            text=str(self.gui_scale_factor),
            size_hint=(None, None),
            width=100 * scale,
            height=50 * scale,
            font_size=24 * scale,
            multiline=False
        )

        # Create a wrapper layout to center the TextInput
        scale_input_wrapper = RelativeLayout(
            size_hint=(None, 1), # Take full height of the row, use fixed width
            width=self.scale_input.width
        )
        self.scale_input.pos_hint = {'center_y': 0.5}
        scale_input_wrapper.add_widget(self.scale_input)
        
        set_scale_btn = StyledButton(
            text="Set Scale",
            size_hint=(None, None),
            width=180,
            height=75
        )
        set_scale_btn.bind(on_release=lambda *_: self._set_gui_scale())

        reset_scale_btn = StyledButton(
            text="Reset",
            size_hint=(None, None),
            width=180,
            height=75
        )
        reset_scale_btn.bind(on_release=lambda *_: self._set_gui_scale(reset=True))

        control_scale = BoxLayout(orientation="horizontal", spacing=10 * scale, size_hint_x=0.7)
        control_scale.add_widget(scale_input_wrapper)
        control_scale.add_widget(set_scale_btn)
        control_scale.add_widget(reset_scale_btn)
        control_scale.add_widget(Widget())

        grid.add_widget(label_scale)
        grid.add_widget(control_scale)

        root.add_widget(grid)
    
        # Add a flexible spacer to push content to the top and leave space at the bottom
        root.add_widget(Widget())
    
        btn_bar = BoxLayout(size_hint_y=None, height=75 * scale, spacing=10 * scale)
        back_btn = StyledButton(text="Back", size_hint=(None, None), width=180, height=75)
        back_btn.bind(on_release=lambda *_: self._navigate_to("home"))

        uninstall_btn = StyledButton(
            text="Uninstall App",
            size_hint=(None, None),
            width=220,
            height=75,
            bg_color_name_override="#D9534F"  # Red color for uninstall button
        )
        uninstall_btn.bind(on_release=lambda *_: self._confirm_uninstall())

        btn_bar.add_widget(back_btn)
        btn_bar.add_widget(Widget())  # Spacer
        btn_bar.add_widget(uninstall_btn)

        root.add_widget(btn_bar)
        self.screen_manager.add_widget(scr)

    def _set_gui_scale(self, reset=False):
        if reset:
            new_scale = 1.0
        else:
            try:
                new_scale = float(self.scale_input.text)
                if new_scale <= 0:
                    raise ValueError("Scale must be positive")
                if new_scale > 3.0:
                    self._show_error("Invalid Scale", "GUI scale factor cannot exceed 3.0.")
                    return
            except (ValueError, TypeError):
                self._show_error("Invalid Scale", "Please enter a valid positive number for the scale factor (e.g., 1.0 or 1.2).")
                return

        self.gui_scale_factor = new_scale
        self._save_conf()
        self._rebuild_ui()

    def _rebuild_ui(self):
        """
        Clears and rebuilds the entire UI to apply scaling changes.
        Preserves essential state like loaded spreadsheet data.
        """
        # Store current screen to return to it after rebuild
        current_screen = self.screen_manager.current
        
        # Clear all widgets from all screens, and the screen manager itself
        for screen in self.screen_manager.screens:
            screen.clear_widgets()
        self.screen_manager.clear_widgets()

        # Re-build all screens with the new scale factor
        self._build_home()
        self._build_review()
        self._build_generation()
        self._build_settings()
        self._build_help()
        self._build_credits()
        self._build_model_install() # Ensure ModelInstallScreen is rebuilt
        
        # Restore necessary state
        self._update_model_status()
        self._update_debug_console_visibility(self.CONF["debug"])
        self._update_home_screen_ui()
        if self.filtered_items:
             self._populate_review_list()
        
        # Return to the screen the user was on
        self.screen_manager.current = "home" # Go home first to avoid visual glitches
        self.screen_manager.current = current_screen
        self._show_info("GUI Scale Updated", "UI has been rescaled.")

    # ---------------------------  Model Management ---------------------------
    def _initialize_model_loading(self):
        """Attempt to load the model noted in config (current_model)."""
        model_filename = self.CONF.get("current_model", "")
        if model_filename:
            try:
                self.backend.load_model_by_filename(model_filename)
            except Exception as e:
                print(f"[frontend] Could not load model '{model_filename}': {e}")
                self.CONF["current_model"] = ""
                self._save_conf()
        # Update labels etc.
        self._update_model_status()
        # Populate spinner after backend lists are ready
        from kivy.clock import Clock
        Clock.schedule_once(lambda dt: self._refresh_models_dropdown(), 0.1)

    def _refresh_models_dropdown(self):
        """Refresh spinner values with the latest available models."""
        if not hasattr(self, "model_spinner"):
            return
        self.model_spinner.values = self.backend.get_available_models()

        # Ensure current value is still valid
        current = self.CONF.get("current_model", "")
        if current and current in self.model_spinner.values:
            self.model_spinner.text = current
        else:
            self.model_spinner.text = "Select Model"

        # Manually update visuals to ensure the color is always correct,
        # especially on initial load.
        self._update_spinner_visuals(self.model_spinner, self.model_spinner.text)

    def _on_spinner_click(self, spinner):
        """Called when the spinner button is clicked, before the dropdown opens."""
        # If the dropdown is about to open but has no items, show an info message.
        if not spinner.values:
            self._show_info("No Models Installed",
                            "Please install a model first.\n\n"
                            "You can download the recommended model using the button below, "
                            "or drag and drop a .gguf file into the upload area.")

    def _update_spinner_visuals(self, spinner, text):
        """Sets the spinner's visual state based on the selected text."""
        if text == "Select Model":
            # Highlight with green if no model is selected
            spinner.background_normal = ''
            spinner.background_down = ''
            spinner.background_color = StyledButton.hex2rgba("#5CB85C", 1.0)
        else:
            # A model is selected, so revert to default spinner appearance
            spinner.background_normal = 'atlas://data/images/defaulttheme/spinner'
            spinner.background_down = 'atlas://data/images/defaulttheme/spinner_pressed'
            spinner.background_color = (1, 1, 1, 1) # Reset tint

    def _on_model_selected(self, spinner, text):
        """User picked a model from the dropdown. This triggers a model load."""
        self._update_spinner_visuals(spinner, text)

        if text == "Select Model":
            return

        # This part is the action that should only happen on user selection.
        try:
            self.backend.load_model_by_filename(text)
            self.CONF["current_model"] = text
            self._save_conf()
            self._show_info(f"Model '{text}' selected and loading in background.")
            self._update_model_status()
        except Exception as e:
            self._show_error("Model Load Error", str(e))
            # On error, refresh dropdown to revert selection and color.
            self._refresh_models_dropdown()

    def _confirm_delete_model(self):
        """Ask user confirmation before deleting the selected model."""
        fname = self.CONF.get("current_model", "")
        if not fname:
            self._show_error("No Model Selected", "Please select a model to delete first.")
            return

        content = BoxLayout(orientation='vertical', spacing=10, padding=10)
        label = Label(text=f"Delete model '{fname}'?\nThis cannot be undone.", halign='center')
        btns = BoxLayout(size_hint_y=None, height=75, spacing=10)
        cancel = StyledButton(text="Cancel")
        ok = StyledButton(text="Delete", bg_color_name_override="#D9534F")
        btns.add_widget(cancel); btns.add_widget(ok)
        content.add_widget(label); content.add_widget(btns)
        popup = Popup(title="Confirm Delete", content=content, size_hint=(0.7,0.4), auto_dismiss=False)
        cancel.bind(on_release=lambda *_: popup.dismiss())
        ok.bind(on_release=lambda *_: (popup.dismiss(), self._delete_model_file(fname)))
        popup.open()

    def _delete_model_file(self, fname: str):
        """Physically delete model file and refresh UI."""
        try:
            path = os.path.join(self.backend._get_models_dir(), fname)
            if os.path.exists(path):
                os.remove(path)
            # If deleted model was current, clear selection
            if self.CONF.get("current_model") == fname:
                self.CONF["current_model"] = ""
                self.backend.llm_model = None
            self._save_conf()
            self._refresh_models_dropdown()
            self._update_model_status()
            self._show_info(f"Model '{fname}' deleted.")
        except Exception as e:
            self._show_error("Delete Error", str(e))

    @mainthread
    def _update_model_status(self):
        current = self.CONF.get("current_model", "")
        available = self.backend.get_available_models()
        if current and current in available:
            self.model_status_lbl.text = f"Current Model: {current}"
        else:
            if available:
                self.model_status_lbl.text = "No model selected"
            else:
                self.model_status_lbl.text = "No models found – please install one"
        # Button stays enabled & labelled as 'Model Settings'
        self.install_model_btn.text = "Model Settings"
        self.install_model_btn.disabled = False
        self._update_home_screen_ui()

    def _install_model(self):
        content = BoxLayout(orientation='vertical', spacing=10, padding=10)
        
        label = Label(
            text=f"This will download the model ({MODEL_FILENAME}, ~2.6GB) to your user data directory:\n"
                 f"{self.user_data_dir}\n\n"
                 f"A 'models' folder will be created if it doesn't exist.\n"
                 f"This may take a while depending on your internet connection.\n\n"
                 f"[b]Do you want to proceed?[/b]",
            markup=True,
            halign='center'
        )
        content.add_widget(label)

        btn_layout = BoxLayout(size_hint_y=None, height=75, spacing=10)
        cancel_btn = StyledButton(text="Cancel")
        confirm_btn = StyledButton(text="Download")
        btn_layout.add_widget(cancel_btn)
        btn_layout.add_widget(confirm_btn)
        content.add_widget(btn_layout)

        popup = Popup(title="Confirm Model Download", content=content, size_hint=(0.8, 0.6), auto_dismiss=False)

        def on_confirm(*_):
            popup.dismiss()
            self.model_status_lbl.text = "Downloading... (may take a while)"
            # Button stays enabled for settings
            # Start download in a thread
            threading.Thread(
                target=self.backend.download_model,
                args=(self._on_model_download_complete, self._on_model_download_error),
                daemon=True
            ).start()

        def on_cancel(*_):
            popup.dismiss()

        confirm_btn.bind(on_release=on_confirm)
        cancel_btn.bind(on_release=on_cancel)

        popup.open()

    @mainthread
    def _on_model_download_complete(self, model_path: str):
        """
        Called by backend.download_model() once the model has downloaded **and** loaded.
        model_path is the absolute path; convert to filename & update state.
        """
        fname = os.path.basename(model_path)
        self.CONF["current_model"] = fname
        self._save_conf()

        # Refresh dropdown / labels
        self._refresh_models_dropdown()
        self._update_model_status()
        self._show_info("Model downloaded and loading in background.")
        self._navigate_to("settings")

    @mainthread
    def _on_model_download_error(self, exc: Exception):
        error_message = (
            "[b]Model download failed.[/b]\n\n"
            "This may be due to an issue with your internet connection, a firewall, or a temporary problem with the model provider.\n\n"
            "Please check your connection and try again. If the problem persists, contact IT support.\n\n"
            f"[size=14]Details: {str(exc)}[/size]"
        )
        self._show_error("Model Download Failed", error_message, markup=True)
        self._update_model_status()

    def _toggle_debug(self, value: bool):
        self.CONF["debug"] = value
        self._save_conf()
        # Immediately update the debug console's visibility
        self._update_debug_console_visibility(value)

    def _toggle_ignore_brackets(self, value: bool):
        self.CONF["ignore_brackets"] = value
        self._save_conf()

    def _open_header_editor(self, header_key: str, title_text: str):
        content = BoxLayout(orientation='vertical', spacing=10, padding=10)
        
        title_label = Label(
            text=f"Editing: {title_text}",
            size_hint_y=None,
            height=40,
            font_size=24,
            color=TEXT_COLOR
        )
        content.add_widget(title_label)
        
        info_label = Label(
            text="Type the exact column header name from your spreadsheet. This is case-sensitive.",
            size_hint_y=None,
            height=50,
            font_size=20,
            color=TEXT_COLOR
        )
        info_label.bind(width=lambda inst, w: inst.setter("text_size")(inst, (w, None)))
        content.add_widget(info_label)

        text_input = TextInput(
            text=self.spreadsheet_headers.get(header_key, ""),
            font_size=24,
            multiline=False,
            size_hint_y=None,
            height=50
        )
        content.add_widget(text_input)

        content.add_widget(Widget()) # Spacer

        btn_layout = BoxLayout(size_hint_y=None, height=75, spacing=10)
        reset_btn = StyledButton(text="Reset to Default")
        cancel_btn = StyledButton(text="Cancel")
        save_btn = StyledButton(text="Save & Close")
        btn_layout.add_widget(reset_btn)
        btn_layout.add_widget(cancel_btn)
        btn_layout.add_widget(save_btn)
        content.add_widget(btn_layout)

        popup = Popup(title=f"Edit {title_text}", content=content, size_hint=(0.8, 0.6), auto_dismiss=False)

        def on_save(*_):
            new_header = text_input.text.strip()
            if not new_header:
                self._show_error("Invalid Header", "Header name cannot be empty.")
                return
            self.spreadsheet_headers[header_key] = new_header
            self.CONF["spreadsheet_headers"] = self.spreadsheet_headers
            self._save_conf()
            self._show_info(f"'{title_text}' header saved.")
            popup.dismiss()

        def on_reset(*_):
            text_input.text = DEFAULT_SPREADSHEET_HEADERS[header_key]

        def on_cancel(*_):
            popup.dismiss()

        save_btn.bind(on_release=on_save)
        reset_btn.bind(on_release=on_reset)
        cancel_btn.bind(on_release=on_cancel)

        popup.open()

    def _open_prompt_editor(self, prompt_type: str):
        if prompt_type == "pass1":
            title = "Edit Pass 1 (Summarization) Prompt"
            initial_text = self.prompt_pass1
            default_text = PROMPT_TEMPLATE_PASS1
        elif prompt_type == "pass2":
            title = "Edit Pass 2 (Formatting) Prompt"
            initial_text = self.prompt_pass2
            default_text = PROMPT_TEMPLATE_PASS2
        else:
            return

        content = BoxLayout(orientation='vertical', spacing=10, padding=10)
        
        # Configure TextInput for scrolling within a ScrollView
        text_input = TextInput(
            text=initial_text,
            font_size=22,  # Increased font size for readability
            size_hint_y=None,  # Disable vertical size hint to allow custom height
        )
        # Bind the height of the TextInput to its minimum_height.
        # This makes the TextInput grow vertically as more text is added.
        text_input.bind(minimum_height=text_input.setter('height'))

        # ScrollView to contain the resizable TextInput
        scroll_view = ScrollView(scroll_wheel_distance=100)
        scroll_view.add_widget(text_input)
        content.add_widget(scroll_view)

        btn_layout = BoxLayout(size_hint_y=None, height=75, spacing=10)
        reset_btn = StyledButton(text="Reset to Default")
        cancel_btn = StyledButton(text="Cancel")
        save_btn = StyledButton(text="Save & Close")
        btn_layout.add_widget(reset_btn)
        btn_layout.add_widget(cancel_btn)
        btn_layout.add_widget(save_btn)
        content.add_widget(btn_layout)

        popup = Popup(title=title, content=content, size_hint=(0.9, 0.9), auto_dismiss=False)

        def on_save(*_):
            new_text = text_input.text
            if prompt_type == "pass1":
                self.prompt_pass1 = new_text
                self.CONF["prompt_pass1"] = new_text
            else: # pass2
                self.prompt_pass2 = new_text
                self.CONF["prompt_pass2"] = new_text
            self._save_conf()
            self._show_info("Prompt saved successfully.")
            popup.dismiss()

        def on_reset(*_):
            text_input.text = default_text

        def on_cancel(*_):
            popup.dismiss()

        save_btn.bind(on_release=on_save)
        reset_btn.bind(on_release=on_reset)
        cancel_btn.bind(on_release=on_cancel)

        popup.open()

    def _confirm_uninstall(self):
        content = BoxLayout(orientation='vertical', spacing=10, padding=10)

        label = Label(
            text="This will delete all cached data, including the downloaded model and settings.\n"
                 "The application will close, and you will need to manually drag the app to the Trash.\n\n"
                 "[b]Are you sure you want to continue?[/b]",
            markup=True,
            halign='center'
        )
        content.add_widget(label)

        btn_layout = BoxLayout(size_hint_y=None, height=75, spacing=10)
        cancel_btn = StyledButton(text="Cancel")
        confirm_btn = StyledButton(text="Uninstall", bg_color_name_override="#D9534F")
        btn_layout.add_widget(cancel_btn)
        btn_layout.add_widget(confirm_btn)
        content.add_widget(btn_layout)

        popup = Popup(title="Confirm Uninstall", content=content, size_hint=(0.7, 0.5), auto_dismiss=False)

        def on_confirm(*_):
            popup.dismiss()
            self._do_uninstall()

        def on_cancel(*_):
            popup.dismiss()

        confirm_btn.bind(on_release=on_confirm)
        cancel_btn.bind(on_release=on_cancel)

        popup.open()

    def _do_uninstall(self):
        try:
            data_dir = self.user_data_dir
            if os.path.exists(data_dir):
                shutil.rmtree(data_dir)

            # Reset model keys in config
            self.CONF.pop("current_model", None)
            self.CONF.pop("model_path", None)  # legacy
            self._save_conf()
            self._update_model_status()

            # Show a final message before quitting
            if platform == 'win':
                msg = ("Application data has been removed.\n"
                       "Please delete the application executable (.exe) "
                       "to complete uninstallation.")
            elif platform == 'macosx':
                msg = ("Application data has been removed.\n"
                       "Please drag the application to the Trash "
                       "to complete uninstallation.")
            else: # Linux, etc.
                msg = ("Application data has been removed.\n"
                       "Please delete the application file "
                       "to complete uninstallation.")

            final_msg_content = Label(text=msg, halign='center')
            popup = Popup(title="Uninstall Complete", content=final_msg_content, size_hint=(0.6, 0.4))

            # Use a clock schedule to close the app after the popup is shown
            from kivy.clock import Clock
            def close_app(*_):
                self.stop()

            popup.bind(on_dismiss=close_app)
            popup.open()

        except Exception as e:
            self._show_error("Uninstall Error", f"Could not remove application data: {e}")

    def _update_home_screen_ui(self):
        current = self.CONF.get("current_model", "")
        is_installed = current and (current in self.backend.get_available_models())
        self.upload_zone.set_uninstalled_state(not is_installed)

    def _on_ref_press(self, _, ref):
        """Handle hyperlink clicks in labels."""
        if ref == "github_repo":
            webbrowser.open("https://github.com/ningkaiyang/PacificaAutoAgendaWriter")
        elif ref == "nick_linkedin":
            webbrowser.open("https://www.linkedin.com/in/nickolasyang/")
        elif ref == "madeleine_linkedin":
            webbrowser.open("https://www.linkedin.com/in/madeleine-hur")

    # ---------------------------------------------------------------- Help & Credits
    def _build_help(self):
        scale = self.gui_scale_factor
        scr = HelpScreen(name="help")
        # When this screen is about to be shown, update the help text
        scr.bind(on_pre_enter=self._update_help_text)
        root = BoxLayout(orientation="vertical", padding=20 * scale, spacing=20 * scale)
        scr.add_widget(root)
        
        # title with back button
        header = BoxLayout(orientation="horizontal", size_hint_y=None, height=85 * scale, spacing=10 * scale)
        back_btn = StyledButton(text="Back", size_hint=(None, None), width=180, height=75)
        back_btn.bind(on_release=lambda *_: self._navigate_to("home"))
        header.add_widget(back_btn)
        
        title = Label(text="[b]Help & Instructions[/b]", markup=True, font_size=50 * scale, color=[0, 0, 0, 1])
        header.add_widget(title)
        header.add_widget(Widget(size_hint=(None, None), width=150 * scale))  # spacer to balance title
        root.add_widget(header)
        
        # scrollable content
        scroll = ScrollView()
        content = BoxLayout(orientation="vertical", spacing=15 * scale, size_hint_y=None, padding=20 * scale)
        content.bind(minimum_height=content.setter('height'))
        
        # Create the label but don't set its text yet. _update_help_text will do it.
        self.help_label = Label(
            text="", # Will be populated dynamically
            markup=True,
            font_size=26 * scale,
            color=[0, 0, 0, 1],
            text_size=(None, None),
            halign="left",
            valign="top",
            size_hint_y=None
        )
        self.help_label.bind(width=lambda inst, width: inst.setter('text_size')(inst, (width - 40, None)))
        self.help_label.bind(texture_size=lambda inst, size: setattr(inst, 'height', size[1]))
        self.help_label.bind(on_ref_press=self._on_ref_press)
        content.add_widget(self.help_label)
        
        scroll.add_widget(content)
        root.add_widget(scroll)
        
        self.screen_manager.add_widget(scr)

    def _update_help_text(self, *args):
        # This method is called right before the help screen is displayed.
        # It builds the help text with the current spreadsheet header configuration.
        scale = self.gui_scale_factor
        help_text = (
            f"[size={int(42 * scale)}][b]Welcome to the Agenda Summary Generator v5.0![/b][/size]\n\n"
            "This guide will walk you through using the application, from initial setup to generating your first report.\n\n"
            
            f"[size={int(34 * scale)}][b]First-Time Setup & Model Installing[/b][/size]\n\n"
            "Before you can generate reports, you need at least one AI model installed. Navigate to Settings and click the Model Settings button to access the Install Models screen.\n\n"
            "You can add a model in two ways:\n\n"
            "[b]Internet Install the Recommended Model (From Online)[/b]\n"
            "This is the easiest way to get started. Click the large button at the bottom to download the recommended model (approx. 2.6 GB). The application will install it for you, which may take a few minutes.\n\n"
            "[b]Install a Model from a File (Offline)[/b]\n"
            "This option is for any GGUF-format model saved on your computer or a drive. In the large upload area, click to browse for a .gguf file or drag and drop the file directly onto the zone. The model file will be copied into the application's data folder and become available for use.\n\n"
            "Once installed, your models will appear in the Available Models dropdown list. Select a model from the dropdown to use it for generation; it will load in the background. You can install multiple models and switch between them. Use the Refresh button to update the list if you've manually added files, and the Delete Model button to remove the currently selected model.\n\n"

            f"[size={int(34 * scale)}][b]How to Generate a Report[/b][/size]\n\n"
            "[b]Prepare Your Excel File[/b]\n"
            "Your data must be in a Microsoft Excel (.xlsx) file. If your file has multiple sheets, the app will prompt you to select the one containing your agenda data.\n"
            "The selected sheet needs specific column headers. By default, it looks for:\n"
            f"  - \"[b]{self.spreadsheet_headers['date']}[/b]\" for the Meeting Date\n"
            f"  - \"[b]{self.spreadsheet_headers['section']}[/b]\" for the Agenda Section\n"
            f"  - \"[b]{self.spreadsheet_headers['item']}[/b]\" for the Agenda Item Title\n"
            f"  - \"[b]{self.spreadsheet_headers['notes']}[/b]\" for any additional notes\n"
            f"  - \"[b]{self.spreadsheet_headers['include']}[/b]\" to automatically select an item (cell value '[b]Y[/b]' or '[b]Yes[/b]' — case-insensitive)\n"
            "For the app to identify agenda items correctly, the date column value must start with a number in [date]-[3-letter-month] format (e.g., 01-Jan or 31-Dec).\n\n"

            "[b]Upload Your File[/b]\n"
            "On the home screen, drag and drop your .xlsx file onto the large upload area or click the area to open a file browser. If your Excel file has multiple sheets, a popup will ask you to select which sheet to process.\n\n"

            "[b]Review and Select Items[/b]\n"
            "After uploading, a list of all agenda items found in your file will appear. Items are automatically checked if their Include column is Y or Yes (case-insensitive). Manually check or uncheck any item by clicking on it. Use the Select All and Deselect All buttons for quick changes. Toggle Ignore Bracketed Text in settings to filter out text in brackets.\n\n"
            
            "[b]Generate the Summary[/b]\n"
            "Once satisfied with your selections, click the Generate button. You will see the AI generating the report in real-time on a new screen. Generation time depends on the selected model and your computer hardware. Processing may take longer on slower computers. The output window and debug console (if enabled) will scroll automatically.\n\n"

            "[b]Save or Copy Your Report[/b]\n"
            "When finished, the Save and Copy buttons will activate. A notification sound will play, and the app window will come to the front. Click Save to export the report as a formatted Microsoft Word (.docx) file, or Copy to place the entire report text on your clipboard. After saving, a confirmation dialog appears with OK and Open File Location buttons to reveal the saved file in your file manager.\n\n"

            f"[size={int(34 * scale)}][b]Advanced Settings[/b][/size]\n\n"
            "The Settings screen provides powerful customization options:\n"
            "• Model Settings: This button takes you to the model installation and management screen, as described in Part 1.\n"
            "• Spreadsheet Column Headers: If your Excel file uses different header names (e.g., 'Meeting_Date' instead of 'MEETING DATE'), you can change what the app looks for here. Click each button ('Date', 'Section', etc.) to edit the corresponding header name.\n"
            "• Prompt Templates: Advanced users can edit the instructions (prompts) given to the AI. This allows for fine-tuning the summarization and formatting style.\n"
            "• Debug Mode: Toggling this on will show a detailed debug console on the generation screen, which is useful for troubleshooting. It displays the exact text sent to the AI and performance metrics like generation speed. For developers.\n"
            "• Ignore Bracketed Text: When enabled, the app will automatically remove any text found inside square brackets `[]` from your spreadsheet data before sending it to the AI.\n"
            "• GUI Scale Factor: If UI elements appear too large or too small on your screen, you can adjust the scale. Enter a number (e.g., `1.0` for default, `1.2` for larger, `0.9` for smaller) and click 'Set Scale'. The UI will immediately rescale. A restart is not required.\n"
            "• Uninstall App: This provides a quick way to completely remove all application data, including the downloaded model, settings, and logs. [b]Settings deletion is irreversible.[/b]\n\n"

            f"[size={int(34 * scale)}][b]More Information (Video Guide!) & Source Code[/b][/size]\n\n"
            "For the full documentation, source code, latest releases, and video guide, please visit the GitHub repository:\n"
            "[ref=github_repo][u][color=4682B4]https://github.com/ningkaiyang/PacificaAutoAgendaWriter[/color][/u][/ref]"
        )
        if hasattr(self, 'help_label'):
            self.help_label.text = help_text

    def _build_credits(self):
        scale = self.gui_scale_factor
        scr = CreditsScreen(name="credits")
        root = BoxLayout(orientation="vertical", padding=20 * scale, spacing=10 * scale)
        scr.add_widget(root)

        # build header with back button and centered title
        header = BoxLayout(orientation="horizontal", size_hint_y=None, height=85 * scale, spacing=20 * scale)
        back_btn = StyledButton(text="Back", size_hint=(None, None), width=180, height=75)
        back_btn.bind(on_release=lambda *_: self._navigate_to("home"))
        header.add_widget(back_btn)

        title = Label(
            text="[b]About & Credits[/b]",
            markup=True,
            font_size=50 * scale,
            color=[0, 0, 0, 1],
            halign="center",
            valign="middle"
        )
        title.bind(size=title.setter('text_size'))
        header.add_widget(title)
        
        # add a spacer to balance the back button, keeping title centered
        header.add_widget(Widget(size_hint=(None, None), width=150 * scale))
        root.add_widget(header)

        # scrollable area for the main content
        scroll = ScrollView(size_hint=(1, 1))
        # New layout to center content vertically within the scrollview
        aligner_layout = BoxLayout(orientation="vertical", size_hint_y=1, padding=(0, 0)) # Adjusted vertical padding for overall look
        
        # Spacer above the content
        aligner_layout.add_widget(Widget())

        content = BoxLayout(orientation="vertical", spacing=15 * scale, size_hint_y=None, padding=(20 * scale, 0)) # Removed vertical padding here, using aligner_layout instead
        content.bind(minimum_height=content.setter('height'))
        
        aligner_layout.add_widget(content)
        
        # Spacer below the content
        aligner_layout.add_widget(Widget())

        scroll.add_widget(aligner_layout)
        root.add_widget(scroll)

        # helper to add a centered label with wrapping
        def add_centered(text, fs, bold=False):
            fs = fs * scale
            formatted_text = f"[b]{text}[/b]" if bold else text
            lbl = Label(
                text=f"[size={int(fs)}]{formatted_text}[/size]",
                markup=True,
                font_size=fs,
                color=[0, 0, 0, 1],
                size_hint_y=None,
                halign="center",
                valign="middle",
            )
            lbl.bind(
                width=lambda inst, w: inst.setter("text_size")(inst, (w, None)),
                texture_size=lambda inst, size: setattr(inst, "height", size[1]),
                on_ref_press=self._on_ref_press,
            )
            content.add_widget(lbl)
            content.add_widget(Widget(size_hint_y=None, height=5 * scale)) # reduced spacing

        # Add logo similar to home screen
        try:
            from kivy.uix.image import Image as KivyImage
            if os.path.exists("logo.png"):
                logo_container = BoxLayout(orientation="horizontal", size_hint=(1, None), height=220 * scale) # slightly taller to accommodate padding
                logo_container.add_widget(Widget(size_hint_x=1))  # spacer for centering
                logo = KivyImage(source="logo.png", size_hint=(None, None), size=(200 * scale, 200 * scale)) # Larger square size
                logo_container.add_widget(logo)
                logo_container.add_widget(Widget(size_hint_x=1))  # spacer for centering
                content.add_widget(logo_container)
                content.add_widget(Widget(size_hint_y=None, height=20 * scale)) # spacing after logo
        except Exception:
            pass

        # app title
        add_centered("City of Pacifica\nAgenda Summary Generator", 46, bold=True)
        content.add_widget(Widget(size_hint_y=None, height=15 * scale))
        
        # version
        add_centered("Version 5.0 - Direct Excel Handling", 38, bold=True)
        content.add_widget(Widget(size_hint_y=None, height=15 * scale))

        # description
        add_centered(
            "A modern, cross-platform app for generating "
            "AI-powered summaries of city council agenda items "
            "for executive review and public transparency.",
            28,
        )
        content.add_widget(Widget(size_hint_y=None, height=20 * scale))

        # development team header
        add_centered("Development Team (Best Interns Ever !!! 2025)", 36, bold=True)
        content.add_widget(Widget(size_hint_y=None, height=15 * scale))

        # team details
        add_centered(
            "Project Lead & Developer: [ref=nick_linkedin][u][color=4682B4]Nickolas Yang[/color][/u][/ref]\n"
            "Project Coordination: [ref=madeleine_linkedin][u][color=4682B4]Madeleine Hur[/color][/u][/ref]",
            30,
        )
        content.add_widget(Widget(size_hint_y=None, height=20 * scale))
        
        add_centered(
            "Built with Python, Kivy, and HuggingFace Open-Source Local LLMs.\n"
            "Powered by llama-cpp-python for privacy-focused local AI processing.",
            26,
        )

        # let things settle then add to screen
        self.screen_manager.add_widget(scr)

    def _build_model_install(self):
        """Create the model installation screen (offline + download)."""
        scale = self.gui_scale_factor
        scr = ModelInstallScreen(name="model_install")
        root = BoxLayout(orientation="vertical", padding=40*scale, spacing=20*scale)
        scr.add_widget(root)

        # Header bar
        top_bar = BoxLayout(orientation="horizontal", size_hint_y=None, height=75*scale, spacing=10*scale)
        back_btn = StyledButton(text="Back", size_hint=(None,None), width=180, height=75)
        back_btn.bind(on_release=lambda *_: self._navigate_to("settings"))
        top_bar.add_widget(back_btn)

        title = Label(text="[b]Install Models[/b]", markup=True,
                      font_size=50*scale, color=[0,0,0,1],
                      halign="center", valign="middle")
        title.bind(size=lambda inst, *_: inst.setter('text_size')(inst, (inst.width, None)))
        top_bar.add_widget(title)

        # Add a spacer of the same width as the back button to center the title
        top_bar.add_widget(Widget(size_hint=(None, None), width=180 * scale))
        root.add_widget(top_bar)

        # Upload zone for .gguf
        self.model_upload_zone = ModelUploadZone(self)
        root.add_widget(self.model_upload_zone)

        # Spacer removed to bring button closer to upload zone. The root layout's
        # spacing property will handle the gap.

        # Download-from-internet button (centered in its own layout)
        dl_btn_container = BoxLayout(orientation='horizontal', size_hint_y=None, height=90*scale)
        dl_btn = StyledButton(text="Download Qwen3-4B-Instruct-2507-Q4_1.gguf from Online (Uses Internet)",
                              size_hint=(None,None), width=900, height=90)
        dl_btn.bind(on_release=lambda *_: self._install_model())
        
        dl_btn_container.add_widget(Widget()) # Spacer left
        dl_btn_container.add_widget(dl_btn)
        dl_btn_container.add_widget(Widget()) # Spacer right
        root.add_widget(dl_btn_container)

        # Available models dropdown + refresh + delete
        list_bar = BoxLayout(orientation='horizontal', size_hint_y=None, height=75*scale, spacing=20*scale)
        list_bar.add_widget(Label(text="Available Models:", color=[0,0,0,1], size_hint_x=None, width=220*scale, font_size=28*scale))
        self.model_spinner = Spinner(text="Select Model",
                                     values=self.backend.get_available_models(),
                                     size_hint=(None,None), width=600*scale, height=75*scale,
                                     font_size=28*scale,
                                     background_normal='')
        self.model_spinner.bind(text=self._on_model_selected)
        self.model_spinner.bind(on_release=self._on_spinner_click)
        refresh_btn = StyledButton(text="Refresh", size_hint=(None,None), width=150, height=75)
        refresh_btn.bind(on_release=lambda *_: self._refresh_models_dropdown())
        del_btn = StyledButton(text="Delete Model", bg_color_name_override="#D9534F",
                               size_hint=(None,None), width=200, height=75)
        del_btn.bind(on_release=lambda *_: self._confirm_delete_model())
        list_bar.add_widget(self.model_spinner)
        list_bar.add_widget(refresh_btn)
        list_bar.add_widget(del_btn)
        root.add_widget(list_bar)

        # Initial refresh to set proper selection
        from kivy.clock import Clock
        Clock.schedule_once(lambda dt: self._refresh_models_dropdown(), 0)

        self.screen_manager.add_widget(scr)

    def _handle_gguf_file(self, file_path: str):
        """Copy the selected .gguf into the user models dir, preserve filename, then load."""
        if not file_path or not file_path.lower().endswith(".gguf"):
            self._show_error("Invalid File Type", "The selected file was not a .gguf model file.\nPlease try again.")
            return
        try:
            if not os.path.isfile(file_path):
                self._show_error("File Error", "Selected file does not exist.")
                return
            models_dir = os.path.join(self.user_data_dir, "models")
            os.makedirs(models_dir, exist_ok=True)
            base_name = os.path.basename(file_path)
            dest_path = os.path.join(models_dir, base_name)
            shutil.copy(file_path, dest_path)

            # Update config & backend
            self.CONF["current_model"] = base_name
            self._save_conf()

            self.backend.load_model_by_filename(base_name)

            # UI updates
            self._refresh_models_dropdown()
            self._update_model_status()
            self._show_info(f"Model '{base_name}' installed and loading in background.")
        except Exception as exc:
            self._show_error("Install Error", f"Could not install model: {exc}")

    # ---------------------------------------------------------------- Generation logic
    def _open_model_install_menu(self):
        self.screen_manager.transition.direction = "left"
        self.screen_manager.current = "model_install"

    def _start_generation(self):
        if not self.selected_indices:
            self._show_error("Nothing Selected", "Please select at least one row.")
            return
        rows = [self.filtered_items[i] for i in sorted(self.selected_indices)]

        # Reset auto-scroll state for the new generation
        self.auto_scroll_gen = True
        self.auto_scroll_debug = True

        from kivy.clock import Clock

        # Clear and prepare main output for generation
        self.gen_output.text = "Generating...\n"

        # Clear and prepare debug console, then schedule scroll to bottom
        if self.debug_console and self.sv_debug:
            self.debug_console.text = ""
            Clock.schedule_once(lambda dt: setattr(self.sv_debug, 'scroll_y', 0), -1)

        self.save_button.disabled = True
        self.generation_cancel_event.clear()
        self._navigate_to("generation")

        debug_cb = None
        if self.CONF["debug"]:
            debug_cb = self._update_debug_console

        # start backend thread
        try:
            self.backend.generate_report(
                rows,
                token_callback=self._token_cb,
                done_callback=self._done_cb,
                error_callback=self._err_cb,
                cancel_event=self.generation_cancel_event,
                prompt_template_pass1=self.prompt_pass1,
                prompt_template_pass2=self.prompt_pass2,
                debug_callback=debug_cb,
                ignore_brackets=self.CONF.get("ignore_brackets", False),
                spreadsheet_headers=self.spreadsheet_headers,
            )
        except RuntimeError as exc:
            self._show_error("Model Error", str(exc))
            self.screen_manager.current = "review" # Go back to review screen

    def _cancel_generation(self):
        """
        Confirm before cancelling long-running generation.
        Shows a confirmation popup if generation is in progress;
        otherwise navigates back immediately.
        """
        # Determine if a generation is currently in progress
        in_progress = False
        try:
            # save_button is disabled during generation and enabled upon completion
            in_progress = bool(self.save_button.disabled)
        except Exception:
            in_progress = False

        if not in_progress:
            self._navigate_to("review")
            return

        scale = self.gui_scale_factor

        content = BoxLayout(orientation='vertical', spacing=10 * scale, padding=10 * scale)

        msg = "This will cancel the current report generation. Are you sure?"
        lbl = Label(text=msg, halign='center', valign='middle')
        lbl.bind(size=lambda inst, *_: inst.setter('text_size')(inst, (inst.width, None)))
        content.add_widget(lbl)

        btn_box = BoxLayout(size_hint_y=None, height=75 * scale, spacing=10 * scale)
        yes_btn = StyledButton(text="Yes, Cancel", bg_color_name_override="#D9534F", size_hint=(0.5, None), height=75)
        no_btn = StyledButton(text="No, Continue Generating", size_hint=(0.5, None), height=75)

        btn_box.add_widget(yes_btn)
        btn_box.add_widget(no_btn)
        content.add_widget(btn_box)

        popup = Popup(title="Cancel Generation?", content=content, size_hint=(0.7, 0.4), auto_dismiss=False)

        def confirm_cancel(*_):
            self.generation_cancel_event.set()
            popup.dismiss()
            self._navigate_to("review")

        no_btn.bind(on_release=lambda *_: popup.dismiss())
        yes_btn.bind(on_release=confirm_cancel)
        popup.open()

    # backend callbacks
    def _token_cb(self, txt: str):
        if self.generation_cancel_event.is_set():
            return
        self._append_gen_text(txt)

    @mainthread
    def _append_gen_text(self, txt: str):
        """Appends text to the main generation output with smart scrolling."""
        if not self.sv_gen_output:
            self.gen_output.text += txt
            return

        self.gen_output.text += txt

        if self.auto_scroll_gen:
            def scroll_if_needed(dt):
                # Only scroll if the content is taller than the view to prevent visual glitches.
                if self.sv_gen_output and self.gen_output and self.sv_gen_output.height < self.gen_output.height:
                    self.sv_gen_output.scroll_y = 0
            
            from kivy.clock import Clock
            Clock.schedule_once(scroll_if_needed, -1)

    @mainthread
    def _done_cb(self, full_text: str, dates: List[str]):
        if self.generation_cancel_event.is_set():
            return
        self.generated_report_text = full_text
        self.meeting_dates_for_report = dates
        self.save_button.disabled = False
        self.copy_button.disabled = False
        self._append_gen_text("\n--- DONE ---\n")
        if Window.focus:
            self._show_info("Generation Complete. You can now save the report.")
        else:
            self._send_completion_notification()

    def _err_cb(self, exc: Exception):
        self._show_error("Generation Error", str(exc))
        self.screen_manager.current = "review"

    def _on_scroll_stop(self, scroll_view, touch=None):
        """
        Detects user scrolling to enable/disable auto-scroll.
        This is bound to on_scroll_stop, which fires when scrolling ceases.
        The `touch` argument may be None.
        """
        # A small threshold to reliably detect if scrolled away from bottom.
        # scroll_y is 0 at bottom, 1 at top.
        is_at_bottom = scroll_view.scroll_y <= 0.01

        if scroll_view == self.sv_gen_output:
            self.auto_scroll_gen = is_at_bottom
        elif scroll_view == self.sv_debug:
            self.auto_scroll_debug = is_at_bottom

    @mainthread
    def _update_debug_console(self, text: str):
        """Callback to append text to the debug console from a worker thread."""
        if not (self.debug_console and self.sv_debug):
            return

        self.debug_console.text += text

        if self.auto_scroll_debug:
            def scroll_if_needed(dt):
                # Only scroll if the content is taller than the view to prevent visual glitches.
                if self.sv_debug and self.debug_console and self.sv_debug.height < self.debug_console.height:
                    self.sv_debug.scroll_y = 0

            from kivy.clock import Clock
            Clock.schedule_once(scroll_if_needed, -1)

    def _send_completion_notification(self):
        """Send a system notification when generation is done and app is not focused."""
        # 1. Raise window to grab attention (flashing icon). This is now safe
        # because this method is called from _done_cb, which is on the main thread.
        # We still wrap it in a try-except as a defensive measure.
        try:
            Window.raise_window()
        except Exception:
            pass  # Silently fail if OS blocks this

        # 2. Play a sound if available
        try:
            # NOTE: Requires 'notification.wav' or 'notification.mp3' in the root directory.
            sound = SoundLoader.load('notification.wav')
            if not sound:
                sound = SoundLoader.load('notification.mp3')  # Fallback to mp3
            
            if sound:
                sound.play()
        except Exception as e:
            print(f"Could not play notification sound: {e}", file=sys.stderr)

        # 3. Send a system notification if plyer and its dependencies are installed
        if notification:
            try:
                # .ico for Windows, .png for macOS/Linux (plyer handles this)
                icon_path = ""
                if platform == "win" and os.path.exists("logo.ico"):
                    icon_path = "logo.ico"
                elif os.path.exists("logo.png"):
                    icon_path = "logo.png"
                

                notification.notify(
                    title="Generation Complete",
                    message="The agenda summary report is ready to be saved.",
                    app_name="Pacifica Agenda Generator",
                    app_icon=icon_path,
                    timeout=10,  # Display notification for 10 seconds
                )
            except Exception as e:
                # Catching errors here is important for issues that occur at runtime
                # even if dependencies are installed (e.g., D-Bus issues on Linux).
                print(f"Error sending plyer notification: {e}", file=sys.stderr)

    def _copy_report_to_clipboard(self):
        from kivy.core.clipboard import Clipboard
        if self.generated_report_text:
            Clipboard.copy(self.generated_report_text)
            self._show_info("Report Copied", "The generated report text has been copied to the clipboard.")

    # ---------------------------------------------------------------- Save document
    def _save_report(self):
        if not self.generated_report_text.strip():
            return

        # Determine the reporting year on the frontend
        current_year = datetime.now().year

        # Pass the year to the backend
        doc = self.backend.create_word_document(
            self.generated_report_text,
            self.meeting_dates_for_report,
            reporting_year=current_year
        )
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
        
        if save_path is not None:
            # Native dialog was used. If save_path is not empty, a file was chosen.
            # If it's an empty string, user cancelled.
            if save_path:
                # ensure .docx extension
                if not save_path.lower().endswith(".docx"):
                    save_path += ".docx"
                
                try:
                    doc.save(save_path)
                    self._show_save_success_popup(save_path)
                except Exception as exc:
                    self._show_error("save error", str(exc))
            return # Return here to prevent Kivy fallback
        
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
        btn_layout = BoxLayout(size_hint_y=None, height=75, spacing=10)
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
                self._show_save_success_popup(save_path)
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
    def _show_error(self, title, msg, markup=False, *args):
        content = Label(text=msg, markup=markup, halign="center")
        popup = Popup(title=title, content=content, size_hint=(0.8, 0.5))
        content.bind(width=lambda *x: content.setter('text_size')(content, (content.width, None)))
        popup.open()

    @mainthread
    def _show_info(self, msg, *args):
        content = Label(text=msg, halign="center")
        popup = Popup(title="Info", content=content, size_hint=(0.6, 0.4))
        content.bind(width=lambda *x: content.setter('text_size')(content, (content.width, None)))
        popup.open()

    @mainthread
    def _show_save_success_popup(self, path):
        scale = self.gui_scale_factor
        content = BoxLayout(orientation='vertical', spacing=10 * scale, padding=10 * scale)

        lbl = Label(text=f"Report saved successfully to:\n{path}", halign='center', valign='middle')
        lbl.bind(width=lambda inst, w: inst.setter('text_size')(inst, (w, None)))
        content.add_widget(lbl)

        btn_box = BoxLayout(size_hint_y=None, height=75 * scale, spacing=10 * scale)
        ok_btn = StyledButton(text="OK", size_hint=(0.5, None), height=75)
        open_btn = StyledButton(text="Open File Location", size_hint=(0.5, None), height=75)
        btn_box.add_widget(ok_btn)
        btn_box.add_widget(open_btn)
        content.add_widget(btn_box)

        popup = Popup(title="Save Successful", content=content, size_hint=(0.8, 0.4), auto_dismiss=False)

        def open_folder(*_):
            try:
                if sys.platform.startswith("win"):
                    subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
                elif sys.platform == "darwin":  # macOS
                    subprocess.Popen(["open", "-R", path])
                else:  # linux and others
                    subprocess.Popen(["xdg-open", os.path.dirname(path)])
            except Exception as e:
                self._show_error("Open Folder Error", f"Could not open file location:\n{e}")
            finally:
                popup.dismiss()

        open_btn.bind(on_release=open_folder)
        ok_btn.bind(on_release=lambda *_: popup.dismiss())
        popup.open()


# --------------------------------------------------------------------------------------
if __name__ == "__main__":
    PacificaAgendaApp().run()