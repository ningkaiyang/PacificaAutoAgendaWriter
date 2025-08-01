# build.py
import PyInstaller.__main__
import os
import sys
import shutil
from pathlib import Path

# --- Configuration ---
APP_NAME = "AutoAgendaWriter"
ENTRY_POINT = "kivyfrontend.py"
ICON_FILE = "logo.ico"

def find_llama_cpp_lib():
    """find the path to llama_cpp's shared library."""
    try:
        import llama_cpp
        package_path = Path(llama_cpp.__file__).parent
        lib_path = package_path / "lib"
        if lib_path.is_dir():
            print(f"Found llama_cpp lib at: {lib_path}")
            return str(lib_path)
    except (ImportError, AttributeError):
        pass
    print("Warning: Could not find llama_cpp lib path. The build may fail.")
    return None

def find_kivy_hooks():
    """Find the path to Kivy's PyInstaller hooks."""
    try:
        import Kivy
        kivy_path = Path(Kivy.__file__).parent
        hooks_path = kivy_path / "tools" / "packaging" / "pyinstaller" / "hooks"
        if hooks_path.is_dir():
            return str(hooks_path)
    except (ImportError, AttributeError):
        pass
    print("Warning: Could not find Kivy hooks path. The build may fail.")
    return None

def main():
    # --- Platform-specific setup ---
    is_windows = sys.platform.startswith('win')
    
    # Kivy hooks are essential for a successful build
    kivy_hooks_path = find_kivy_hooks()

    # Find and add the llama_cpp library
    llama_lib_path = find_llama_cpp_lib()

    # Define PyInstaller arguments
    pyinstaller_args = [
        '--name', APP_NAME,
        '--onefile',
        '--windowed',  # Hides the console window on release builds
        f'--icon={ICON_FILE}',

        # --- Add data files ---
        # Explicitly add data files. PyInstaller's --add-data format is 'source:dest_in_bundle'
        # On Windows, the separator is ';', on others it's ':'
        '--add-data', f'logo.png{os.pathsep}.',
        '--add-data', f'notification.wav{os.pathsep}.',

        # --- Add hidden imports that PyInstaller might miss ---
        # Kivy and its dependencies
        '--hidden-import', 'kivy.app',
        '--hidden-import', 'kivy.uix.boxlayout',
        '--hidden-import', 'kivy.uix.button',
        '--hidden-import', 'kivy.uix.checkbox',
        '--hidden-import', 'kivy.uix.filechooser',
        '--hidden-import', 'kivy.uix.gridlayout',
        '--hidden-import', 'kivy.uix.image',
        '--hidden-import', 'kivy.uix.label',
        '--hidden-import', 'kivy.uix.popup',
        '--hidden-import', 'kivy.uix.recycleview',
        '--hidden-import', 'kivy.uix.screenmanager',
        '--hidden-import', 'kivy.uix.scrollview',
        '--hidden-import', 'kivy.uix.textinput',
        '--hidden-import', 'kivy.graphics.texture',
        '--hidden-import', 'kivy.graphics.vertex_instructions',
        '--hidden-import', 'kivy.properties',

        # Plyer and platform-specific backends
        '--hidden-import', 'plyer.platforms.win.notification',
        '--hidden-import', 'plyer.platforms.win.filechooser',
        '--hidden-import', 'win10toast',
        '--hidden-import', 'plyer.platforms.win.libs.balloontip',

        # Other dependencies
        '--hidden-import', 'pandas',
        '--hidden-import', 'huggingface_hub',
        '--hidden-import', 'docx',
        '--hidden-import', 'llama_cpp',
        
        # --- Entry point script ---
        ENTRY_POINT
    ]

    # Add Kivy hooks path to the command
    if kivy_hooks_path:
        pyinstaller_args.extend(['--additional-hooks-dir', kivy_hooks_path])

    # Add llama_cpp lib path to the command
    if llama_lib_path:
        # we want to place the lib folder inside a 'llama_cpp' folder in the bundle
        pyinstaller_args.extend(['--add-data', f'{llama_lib_path}{os.pathsep}llama_cpp/lib'])

    print("--- Starting PyInstaller Build ---")
    print(f"App Name: {APP_NAME}")
    print(f"Entry Point: {ENTRY_POINT}")
    print(f"Platform: {sys.platform}")
    print(f"PyInstaller command: {' '.join(pyinstaller_args)}")
    print("------------------------------------")

    # Execute PyInstaller
    try:
        PyInstaller.__main__.run(pyinstaller_args)
        print("\n--- Build Successful ---")
        print(f"Executable created in '{os.path.join(os.getcwd(), 'dist')}'")
    except Exception as e:
        print(f"\n--- Build Failed ---")
        print(f"An error occurred during the PyInstaller build: {e}")
        print("Please check the output above for specific error messages.")
        sys.exit(1)

if __name__ == '__main__':
    # --- Pre-build Checks and Setup ---
    # 1. Check for entry point file
    if not os.path.exists(ENTRY_POINT):
        print(f"Error: Entry point script '{ENTRY_POINT}' not found.")
        sys.exit(1)

    # 2. Create logo.ico from logo.png if it doesn't exist
    if not os.path.exists(ICON_FILE):
        print(f"Icon file '{ICON_FILE}' not found. Attempting to create it from 'logo.png'...")
        if not os.path.exists('logo.png'):
            print("Error: 'logo.png' not found. Cannot create icon.")
            # We can proceed without an icon, PyInstaller will use a default one.
        else:
            try:
                from PIL import Image
                img = Image.open('logo.png')
                img.save(ICON_FILE, sizes=[(256, 256), (128, 128), (64, 64), (32, 32), (16, 16)])
                print(f"Successfully created '{ICON_FILE}' from 'logo.png'.")
            except ImportError:
                print("Warning: 'Pillow' library is not installed. Cannot create .ico file.")
                print("Please install it with: pip install Pillow")
            except Exception as e:
                print(f"Warning: Could not create '{ICON_FILE}'. The build will use a default icon. Error: {e}")

    main()
