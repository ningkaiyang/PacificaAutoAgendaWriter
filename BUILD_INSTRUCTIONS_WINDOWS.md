# Final Instructions for Building on Windows

Follow these steps carefully on your Windows laptop to package the application.

**Step 1: Set Up Your Python Environment**

It is highly recommended to use a virtual environment to avoid conflicts with other Python projects.

1.  Open a Command Prompt (`cmd.exe`).
2.  Navigate to the project directory:
    ```bash
    cd path\to\your\AutoAgendaWriter
    ```
3.  Create a virtual environment:
    ```bash
    python -m venv venv
    ```
4.  Activate the virtual environment:
    ```bash
    venv\Scripts\activate
    ```
    Your command prompt should now show `(venv)` at the beginning of the line.

**Step 2: Install Dependencies**

This is the most critical step. Because `llama-cpp-python` can be complex, we will install it carefully.

1.  **For NVIDIA GPU users (Recommended for best performance):**
    If you have an NVIDIA graphics card, run these commands first to enable GPU acceleration.
    ```bash
    set CMAKE_ARGS="-DLLAMA_CUBLAS=on"
    set FORCE_CMAKE=1
    pip install llama-cpp-python --no-cache-dir --force-reinstall
    ```
2.  **For all other users (CPU-only):**
    If you do not have an NVIDIA GPU, you can try to install `llama-cpp-python` directly. You may need to install the [Visual Studio Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/) if you encounter errors.
    ```bash
    pip install llama-cpp-python
    ```
3.  **Install the rest of the dependencies:**
    Now, install everything else from the `requirements.txt` file.
    ```bash
    pip install -r requirements.txt
    ```

**Step 3: Run the Build Script**

The `build.py` script has been enhanced to handle the packaging process automatically.

1.  Make sure you are still in the project directory with the virtual environment active.
2.  Run the build script:
    ```bash
    python build.py
    ```
3.  The script will print detailed information about the build process. It will automatically find Kivy's tools, add all necessary files, and run PyInstaller.

**Step 4: Locate Your Executable**

1.  If the build is successful, you will see a "--- Build Successful ---" message.
2.  A new folder named `dist` will be created in your project directory.
3.  Inside the `dist` folder, you will find `AutoAgendaWriter.exe`. This is your standalone application. You can move this file to another location on your computer, and it should run without needing Python or any other dependencies installed.
