# create_spec.py
import PyInstaller.__main__
import os

# Create the spec file
PyInstaller.__main__.run([
    '--name=AgendaSummaryGenerator',
    '--onefile',  # or --onedir for faster startup
    '--windowed',  # Hide console window
    '--add-data=language_models;language_models',  # Include model directory
    '--add-data=logo.png;.',  # Include logo if exists
    '--add-data=icon.ico;.',  # Include icon if exists
    '--hidden-import=llama_cpp',
    '--hidden-import=customtkinter',
    '--hidden-import=pandas',
    '--hidden-import=docx',
    'twopassqwen.py'
])