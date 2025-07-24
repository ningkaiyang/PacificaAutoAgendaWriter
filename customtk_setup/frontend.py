"""
Frontend for City of Pacifica – Agenda Summary Generator
Launch this file (`python3 frontend.py`) to run the CustomTkinter GUI.

All heavy processing is delegated to backend.AgendaBackend so that the
GUI can later be replaced without touching business logic.
"""

from __future__ import annotations

import os
import traceback
from datetime import datetime
from typing import List

import customtkinter as ctk
import pandas as pd
from PIL import Image
from tkinter import filedialog, messagebox, ttk

from customtk_setup.backend import AgendaBackend  # our new data/LLM layer

ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")


class AgendaSummaryGeneratorGUI(ctk.CTk):
    """CustomTkinter GUI which uses AgendaBackend for all processing."""

    def __init__(self):
        super().__init__()

        # ---------------------------------------------------------------- GUI setup
        self.title("City of Pacifica - Agenda Summary Generator")
        self.geometry("1280x720")
        self.minsize(800, 600)
        try:
            if os.path.exists("icon.ico"):
                self.iconbitmap("icon.ico")
        except Exception:
            pass

        self.bg_color = "#F5F5DC"
        self.primary_color = "#4682B4"
        self.accent_color = "#5A9BD5"
        self.text_color = "#333333"
        self.configure(fg_color=self.bg_color)

        # ---------------------------------------------------------------- backend
        self.backend = AgendaBackend()

        # Runtime state
        self.csv_data: pd.DataFrame | None = None
        self.filtered_items: List[pd.Series] = []
        self.generated_report_text: str = ""
        self.meeting_dates_for_report: List[str] = []

        # Widgets created later
        self.tree: ttk.Treeview | None = None

        # ---------------------------------------------------------------- build UI
        self.main_container = ctk.CTkFrame(self, fg_color=self.bg_color)
        self.main_container.pack(fill="both", expand=True, padx=20, pady=20)

        self.create_navigation()
        self.create_views()
        self.show_view("Home")

    # ============ NAVIGATION =====================================================
    def create_navigation(self):
        nav = ctk.CTkFrame(self.main_container, fg_color=self.bg_color, height=50)
        nav.pack(fill="x", pady=(0, 20))
        nav.pack_propagate(False)

        self.nav_buttons = {}
        for name in ("Home", "Help", "Credits"):
            btn = ctk.CTkButton(
                nav,
                text=name,
                width=120,
                height=40,
                fg_color=self.primary_color,
                hover_color=self.accent_color,
                text_color="white",
                command=lambda n=name: self.show_view(n),
            )
            btn.pack(side="left", padx=(0, 10))
            self.nav_buttons[name] = btn

    # ============ VIEWS ==========================================================
    def create_views(self):
        self.view_container = ctk.CTkFrame(self.main_container, fg_color=self.bg_color)
        self.view_container.pack(fill="both", expand=True)

        self.views ={"Home": ctk.CTkFrame(self.view_container, fg_color=self.bg_color),
                     "Help": ctk.CTkFrame(self.view_container, fg_color=self.bg_color),
                     "Credits": ctk.CTkFrame(self.view_container, fg_color=self.bg_color)}

        self.create_home_view()
        self.create_help_view()
        self.create_credits_view()

    def show_view(self, name: str):
        for vname, frame in self.views.items():
            frame.pack_forget()
        frame = self.views[name]
        frame.pack(fill="both", expand=True)

        # Ensure correct sub-state of Home
        if name == "Home":
            self.review_state.pack_forget()
            self.generation_state.pack_forget()
            self.upload_state.pack(fill="both", expand=True)

    # ------------------------------------------------------------------ HOME view
    def create_home_view(self):
        home = self.views["Home"]

        # Upload state
        self.upload_state = ctk.CTkFrame(home, fg_color=self.bg_color)
        self.upload_state.pack(fill="both", expand=True)

        center = ctk.CTkFrame(self.upload_state, fg_color=self.bg_color)
        center.place(relx=0.5, rely=0.5, anchor="center")

        # Logo
        try:
            if os.path.exists("logo.png"):
                img = Image.open("logo.png").resize((200, 200), Image.Resampling.LANCZOS)
                cimg = ctk.CTkImage(img, size=(200, 200))
                ctk.CTkLabel(center, image=cimg, text="").pack(pady=(0, 30))
        except Exception:
            pass

        # Drop area
        drop = ctk.CTkFrame(
            center, width=600, height=300, fg_color="white",
            border_width=2, border_color=self.primary_color
        )
        drop.pack()
        drop.pack_propagate(False)

        ctk.CTkLabel(
            drop,
            text="Drag & Drop not fully supported. Please use the button.",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=self.text_color,
            wraplength=550
        ).pack(pady=(80, 20), padx=20)

        ctk.CTkButton(
            drop,
            text="Or Click to Select File",
            width=200,
            height=50,
            fg_color=self.primary_color,
            hover_color=self.accent_color,
            font=ctk.CTkFont(size=16),
            command=self.select_file
        ).pack()

        warn = ("Please ensure your .csv file is formatted correctly. "
                "It must include required columns and 'Include in Summary for Mayor' set to Y.")
        ctk.CTkLabel(center, text=warn, font=ctk.CTkFont(size=12),
                     text_color=self.text_color, wraplength=600,
                     justify="center").pack(pady=(20, 0))

        # Review & generation states (hidden until needed)
        self.review_state = ctk.CTkFrame(home, fg_color=self.bg_color)
        self.generation_state = ctk.CTkFrame(home, fg_color=self.bg_color)
        self.create_generation_state_widgets()

    # ---------------------------------------------------------------- file select
    def select_file(self):
        filename = filedialog.askopenfilename(
            title="Select CSV File",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        if filename:
            self.process_csv_file(filename)

    def process_csv_file(self, filepath: str):
        try:
            self.csv_data, self.filtered_items = self.backend.process_csv(filepath)
        except ValueError as ve:
            messagebox.showerror("Invalid File Format", str(ve))
            return
        except Exception as exc:
            messagebox.showerror("Error Reading File", str(exc))
            return

        # Switch to review state
        self.upload_state.pack_forget()
        self.review_state.pack(fill="both", expand=True)
        self.create_review_state()

    # ---------------------------------------------------------------- REVIEW state
    def create_review_state(self):
        # reset content
        for w in self.review_state.winfo_children():
            w.destroy()

        bar = ctk.CTkFrame(self.review_state, fg_color=self.bg_color, height=60)
        bar.pack(fill="x", pady=(0, 20))
        bar.pack_propagate(False)

        ctk.CTkButton(
            bar, text="Back to Home", width=120, height=30,
            fg_color=self.accent_color, hover_color=self.primary_color,
            command=lambda: self.show_view("Home")
        ).pack(side="left", padx=10)

        self.count_label = ctk.CTkLabel(
            bar,
            text=f"Review Items for Report ({len(self.filtered_items)} items found)",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=self.text_color
        )
        self.count_label.pack(side="left", padx=(20, 0))

        self.generate_btn = ctk.CTkButton(
            bar, text="Generate Report", width=150, height=40,
            fg_color=self.primary_color, hover_color=self.accent_color,
            font=ctk.CTkFont(size=16), command=self.generate_report
        )
        self.generate_btn.pack(side="right", padx=(0, 20))

        ctk.CTkButton(
            bar, text="Select All", width=100, height=30,
            fg_color=self.accent_color, hover_color=self.primary_color,
            command=lambda: self.tree.selection_set(self.tree.get_children())
        ).pack(side="right", padx=5)

        ctk.CTkButton(
            bar, text="Deselect All", width=100, height=30,
            fg_color=self.accent_color, hover_color=self.primary_color,
            command=lambda: self.tree.selection_set(())
        ).pack(side="right", padx=5)

        # Treeview listing
        style = ttk.Style(self)
        style.theme_use("default")
        style.configure("Treeview", background="white", foreground=self.text_color,
                        fieldbackground="white", rowheight=25,
                        font=ctk.CTkFont(size=11))
        style.map("Treeview", background=[("selected", self.primary_color)],
                  foreground=[("selected", "white")])
        style.configure("Treeview.Heading", font=ctk.CTkFont(size=12, weight="bold"))

        container = ctk.CTkFrame(self.review_state, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        self.tree = ttk.Treeview(
            container,
            columns=("Date", "Section", "Item", "Notes"),
            show="headings", selectmode="extended"
        )
        for col, w in [("Date", 100), ("Section", 180), ("Item", 400), ("Notes", 350)]:
            self.tree.heading(col, text=col, anchor="w")
            self.tree.column(col, width=w, anchor="w", stretch=col in ("Item", "Notes"))

        for i, row in enumerate(self.filtered_items):
            date = str(row.get("MEETING DATE", ""))
            sec = str(row.get("AGENDA SECTION", "")).replace("\n", " ").replace("•", "-").strip()
            title = str(row.get("AGENDA ITEM", "")).replace("\n", " ").replace("•", "-").strip()
            notes = ""
            if pd.notna(row.get("NOTES")):
                n = str(row["NOTES"]).replace("\n", " ").replace("•", "-").strip()
                if n and n.lower() != "nan":
                    notes = n
            self.tree.insert("", "end", iid=str(i), values=(date, sec, title, notes))

        # scrollbar
        sb = ttk.Scrollbar(container, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)

        # default select all
        self.tree.selection_set(self.tree.get_children())

        # toggle selection on click
        def on_click(event):
            if self.tree.identify("region", event.x, event.y) == "cell":
                iid = self.tree.identify_row(event.y)
                if iid:
                    if iid in self.tree.selection():
                        self.tree.selection_remove(iid)
                    else:
                        self.tree.selection_add(iid)
                return "break"
        self.tree.bind("<Button-1>", on_click)

    # ---------------------------------------------------------------- GENERATE state
    def create_generation_state_widgets(self):
        bar = ctk.CTkFrame(self.generation_state, fg_color=self.bg_color, height=60)
        bar.pack(fill="x", pady=(0, 20))
        bar.pack_propagate(False)

        ctk.CTkButton(
            bar, text="Back to Review", width=150, height=40,
            fg_color=self.accent_color, hover_color=self.primary_color,
            font=ctk.CTkFont(size=16),
            command=lambda: (self.generation_state.pack_forget(),
                             self.review_state.pack(fill="both", expand=True))
        ).pack(side="left", padx=20)

        ctk.CTkLabel(
            bar, text="Generating Report...",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=self.text_color
        ).pack(side="left", padx=20)

        self.save_btn = ctk.CTkButton(
            bar, text="Save Report", width=150, height=40,
            fg_color=self.primary_color, hover_color=self.accent_color,
            font=ctk.CTkFont(size=16), state="disabled",
            command=self.save_generated_report
        )
        self.save_btn.pack(side="right", padx=20)

        self.generation_textbox = ctk.CTkTextbox(
            self.generation_state, fg_color="white", text_color=self.text_color,
            font=ctk.CTkFont(family="monospace", size=12), wrap="word"
        )
        self.generation_textbox.pack(fill="both", expand=True, padx=20, pady=(0, 20))

    # ---------------------------------------------------------------- actions
    def generate_report(self):
        if not self.tree:
            return
        selected = [self.filtered_items[int(iid)] for iid in self.tree.selection()]
        if not selected:
            messagebox.showwarning("No Items Selected", "Please select at least one item.")
            return

        # switch UI state
        self.review_state.pack_forget()
        self.generation_state.pack(fill="both", expand=True)
        self.generation_textbox.delete("1.0", "end")
        self.save_btn.configure(state="disabled")
        self.generate_btn.configure(text="Generating...", state="disabled")

        # call backend
        self.backend.generate_report(
            selected,
            token_callback=self._token_cb,
            done_callback=self._done_cb,
            error_callback=self._err_cb,
        )

# ---------- backend callbacks ------------------------------------
    def _token_cb(self, txt: str):
        # ensure GUI thread
        self.after(0, lambda t=txt: (self.generation_textbox.insert("end", t),
                                     self.generation_textbox.see("end")))

    def _done_cb(self, full_text: str, dates: List[str]):
        def _finish():
            self.generated_report_text = full_text
            self.meeting_dates_for_report = dates
            self.save_btn.configure(state="normal")
            self.generate_btn.configure(text="Generate Report", state="normal")
            messagebox.showinfo("Generation Complete",
                                "The report has been generated.")
        self.after(0, _finish)

    def _err_cb(self, exc: Exception):
        def _show():
            messagebox.showerror("Generation Error",
                                 f"{exc}\n\n{traceback.format_exc()}")
            self.generation_state.pack_forget()
            self.review_state.pack(fill="both", expand=True)
            self.generate_btn.configure(text="Generate Report", state="normal")
        self.after(0, _show)

    # ---------------------------------------------------------------- SAVE
    def save_generated_report(self):
        if not self.generated_report_text.strip():
            messagebox.showwarning("No Content", "Nothing to save.")
            return
        doc = self.backend.create_word_document(
            self.generated_report_text, self.meeting_dates_for_report
        )
        self._save_doc_dialog(doc)

    def _save_doc_dialog(self, doc):
        fname = filedialog.asksaveasfilename(
            defaultextension=".docx",
            filetypes=[("Word Documents", "*.docx"), ("All Files", "*.*")],
            initialfile=f"Council_Agenda_Summary_{datetime.now():%Y%m%d}.docx"
        )
        if fname:
            try:
                doc.save(fname)
                messagebox.showinfo("Success", f"Saved to:\n{fname}")
            except Exception as exc:
                messagebox.showerror("Save Error", str(exc))

    # ---------------------------------------------------------------- HELP / CREDITS
    def create_help_view(self):
        frame = self.views["Help"]
        scroll = ctk.CTkScrollableFrame(frame, fg_color="white")
        scroll.pack(fill="both", expand=True, padx=20, pady=20)
        help_text = """How to Use

1. Click "Or Click to Select File" and choose your agenda CSV.
2. Review the automatically selected items; deselect any not needed.
3. Click "Generate Report" and wait for the AI to finish.
4. Press "Save Report" to export a Word (.docx) file.
"""
        ctk.CTkLabel(scroll, text=help_text, font=ctk.CTkFont(size=14),
                     text_color=self.text_color, justify="left").pack(anchor="nw",
                                                                      padx=20, pady=20)

    def create_credits_view(self):
        frame = self.views["Credits"]
        cent = ctk.CTkFrame(frame, fg_color=self.bg_color)
        cent.place(relx=0.5, rely=0.5, anchor="center")
        ctk.CTkLabel(cent, text="Agenda Summary Generator v1.0",
                     font=ctk.CTkFont(size=28, weight="bold"),
                     text_color=self.text_color).pack(pady=(0, 20))
        text = ("Project Lead & Developer: Nickolas Yang\n"
                "Coordination: Madeleine Hur\n\n"
                "Powered by local LLMs (llama-cpp-python).")
        ctk.CTkLabel(cent, text=text, font=ctk.CTkFont(size=12),
                     text_color=self.text_color, justify="center").pack()

# ==============================================================================
def main():
    AgendaSummaryGeneratorGUI().mainloop()


if __name__ == "__main__":
    main()