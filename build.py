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
# set to False for a final release build
DEBUG_MODE = False  # okay, time for the final build, no more console

def clean_previous_build():
    # a good practice to clean up old files before a new build
    print("--- Cleaning up previous build artifacts...")
    for folder in ["build", "dist"]:
        if os.path.exists(folder):
            shutil.rmtree(folder)
    spec_file = f"{APP_NAME}.spec"
    if os.path.exists(spec_file):
        os.remove(spec_file)

def find_llama_cpp_lib():
    """find the path to llama_cpp's shared library."""
    try:
        import llama_cpp
        package_path = Path(llama_cpp.__file__).parent
        # the library is usually in a 'lib' subfolder or 'llamacpp/lib'
        lib_path = package_path / "lib"
        if not lib_path.is_dir():
            lib_path = package_path / "llamacpp" / "lib"

        if lib_path.is_dir():
            print(f"Found llama_cpp lib at: {lib_path}")
            return str(lib_path)
    except (ImportError, AttributeError):
        pass  # just continue if it's not found
    print("Warning: Could not find llama_cpp lib path. The build may fail.")
    return None

def find_kivy_hooks():
    """Find the path to Kivy's PyInstaller hooks."""
    try:
        import kivy  # it's lowercase 'k'
        kivy_path = Path(kivy.__file__).parent
        # this is the standard path for the hooks
        hooks_path = kivy_path / "tools" / "packaging" / "pyinstaller_hooks"
        if hooks_path.is_dir():
            print(f"Found Kivy hooks at: {hooks_path}")
            return str(hooks_path)
    except (ImportError, AttributeError):
        pass  # continue if not found
    print("Warning: Could not find Kivy hooks path. The build may fail.")
    return None

def pre_build_checks():
    """Run checks and setup steps before the main build process."""
    # 1. check for entry point file
    if not os.path.exists(ENTRY_POINT):
        print(f"Error: Entry point script '{ENTRY_POINT}' not found.")
        sys.exit(1)

    # 2. create logo.ico from logo.png if it doesn't exist
    if not os.path.exists(ICON_FILE):
        print(f"Icon file '{ICON_FILE}' not found. Attempting to create it from 'logo.png'...")
        if not os.path.exists('logo.png'):
            print("Warning: 'logo.png' not found. Cannot create icon. A default icon will be used.")
        else:
            try:
                from PIL import Image
                img = Image.open('logo.png')
                # creating a multi-size icon
                img.save(ICON_FILE, sizes=[(256, 256), (128, 128), (64, 64), (32, 32), (16, 16)])
                print(f"Successfully created '{ICON_FILE}' from 'logo.png'.")
            except ImportError:
                print("Warning: 'Pillow' library is not installed. Cannot create .ico file.")
                print("Please install it with: pip install Pillow")
            except Exception as e:
                print(f"Warning: Could not create '{ICON_FILE}'. The build will use a default icon. Error: {e}")

def main():
    """Configure and run the PyInstaller build."""
    # --- Find required paths ---
    kivy_hooks_path = find_kivy_hooks()
    llama_lib_path = find_llama_cpp_lib()

    # --- Define PyInstaller arguments ---
    pyinstaller_args = [
        '--name', APP_NAME,
        '--onefile',
        f'--icon={ICON_FILE}',
        '--log-level', 'INFO',  # okay lets add more logging to see what's up
    ]

    # lets switch between console and windowed mode
    if DEBUG_MODE:
        print("--- Building in DEBUG mode (console window will be visible) ---")
        pyinstaller_args.append('--console')
    else:
        print("--- Building in RELEASE mode (no console window) ---")
        pyinstaller_args.append('--windowed')


    # --- Add data files ---
    # pyinstaller's --add-data format is 'source;dest_in_bundle' on windows
    pyinstaller_args.extend([
        '--add-data', f'logo.png{os.pathsep}.',
        '--add-data', f'notification.wav{os.pathsep}.',
    ])

    # --- Add hidden imports that PyInstaller might miss ---
    pyinstaller_args.extend([
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
        '--hidden-import', 'kivy.core.image.img_pil',
        '--hidden-import', 'kivy.core.image.img_sdl2',
        '--hidden-import', 'kivy.core.audio.audio_sdl2',
        '--hidden-import', 'kivy.core.text.text_sdl2',
        '--hidden-import', 'kivy.core.window.window_sdl2',
        '--hidden-import', 'plyer.platforms.win.notification',
        '--hidden-import', 'plyer.platforms.win.filechooser',
        '--hidden-import', 'win10toast',
        '--hidden-import', 'plyer.platforms.win.libs.balloontip',
        '--hidden-import', 'pandas',
        '--hidden-import', 'huggingface_hub',
        '--hidden-import', 'docx',
        '--hidden-import', 'openpyxl',
        '--hidden-import', 'llama_cpp',
        '--hidden-import', 'lxml._elementpath',
        '--hidden-import', 'diskcache',
        '--hidden-import', 'pyperclip',
    ])
    
    # okay let's exclude modules we know we don't need
    # this should clean up the camera and gstreamer warnings in the log
    # the app log also says it ignores some of these, so let's be explicit
    pyinstaller_args.extend([
        '--exclude-module', 'kivy.core.camera.camera_picamera',
        '--exclude-module', 'kivy.core.camera.camera_gi',
        '--exclude-module', 'kivy.core.camera.camera_opencv',
        '--exclude-module', 'kivy.lib.gstplayer',
        '--exclude-module', 'kivy.core.video.video_ffmpeg',
        '--exclude-module', 'kivy.core.video.video_ffpyplayer',
        '--exclude-module', 'kivy.core.audio.audio_ffpyplayer',
        '--exclude-module', 'kivy.core.image.img_tex',
        '--exclude-module', 'kivy.core.image.img_dds',
    ])
    
    # --- Entry point script ---
    pyinstaller_args.append(ENTRY_POINT)

    # add kivy hooks path to the command if found
    if kivy_hooks_path:
        pyinstaller_args.extend(['--additional-hooks-dir', kivy_hooks_path])

    # add llama_cpp lib path to the command if found
    if llama_lib_path:
        # for libraries, --add-binary is often more reliable than --add-data
        pyinstaller_args.extend(['--add-binary', f'{llama_lib_path}{os.pathsep}llama_cpp/lib'])

    print("--- Starting PyInstaller Build ---")
    print(f"App Name: {APP_NAME}")
    print(f"Entry Point: {ENTRY_POINT}")
    print(f"Platform: {sys.platform}")
    print(f"PyInstaller command: {' '.join(pyinstaller_args)}")
    print("------------------------------------")

    # --- Execute PyInstaller ---
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
    clean_previous_build()
    pre_build_checks()
    main()
