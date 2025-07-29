# build.py
import PyInstaller.__main__
import os

# --- Configuration ---
APP_NAME = "AutoAgendaWriter"
ENTRY_POINT = "kivyfrontend.py"
ICON_FILE = "logo.ico"

def main():
    # Define PyInstaller arguments
    pyinstaller_args = [
        '--name', APP_NAME,
        '--onefile',
        '--windowed',  # Hides the console window
        f'--icon={ICON_FILE}',

        # --- Add data files ---
        # Syntax: '--add-data', 'source{os.pathsep}destination'
        # '.' means the root of the bundled app.
        '--add-data', f'logo.png{os.pathsep}.',
        '--add-data', f'notification.wav{os.pathsep}.',

        # --- Add hidden imports that PyInstaller might miss ---
        '--hidden-import', 'plyer.platforms.win.notification',

        # --- Entry point script ---
        ENTRY_POINT
    ]

    print(f"Running PyInstaller with args: {pyinstaller_args}")

    # Execute PyInstaller
    PyInstaller.__main__.run(pyinstaller_args)

if __name__ == '__main__':
    # Create logo.ico from logo.png if it doesn't exist
    if not os.path.exists(ICON_FILE):
        try:
            from PIL import Image
            img = Image.open('logo.png')
            img.save(ICON_FILE)
            print(f"'{ICON_FILE}' created from 'logo.png'.")
        except Exception as e:
            print(f"Warning: Could not create '{ICON_FILE}'. Please create it manually. Error: {e}")

    main()
