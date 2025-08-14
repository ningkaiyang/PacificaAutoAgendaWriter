# City of Pacifica - Agenda Summary Generator

## Overview
This application is designed to significantly streamline the process of creating comprehensive agenda summaries for the City of Pacifica City Council meetings. It operates by directly reading Microsoft Excel (.xlsx) files, allowing users to select a specific sheet for processing. It then leverages a local Large Language Model (LLM) to perform both summarization and categorization of agenda items, and subsequently generates a professionally formatted Microsoft Word (.docx) document that is ready for review and finalization. The goal is to provide an efficient, privacy-focused, and user-friendly tool for managing meeting agenda data.

## Key Features
*   **Direct Excel (.xlsx) Handling**: Read Microsoft Excel files directly.
*   **Sheet Selection:** If a workbook contains multiple sheets, you are prompted to select the correct one.
*   **One-Click Model Installation:** A simple, one-time setup process to download and install the required local LLM directly from the settings menu.
*   **Full Item Parsing & Auto-Selection:** The application parses all agenda items from your selected Excel sheet and presents them in a clear, scrollable list. Items can be automatically pre-selected for inclusion based on a flag in the source file.
*   **Flexible Column Headers:** Customize the exact column header names (e.g., "MEETING DATE", "AGENDA ITEM") in the settings to match your specific spreadsheet format. No need to edit the file itself.
*   **Customizable AI Prompts:** Advanced users can modify the prompt templates used for both summarization (Pass 1) and formatting (Pass 2) via the settings menu, allowing for fine-tuned control over the AI's output.
*   **Self-Scrolling Console:** Both the main generation output and the optional debug console now scroll automatically, allowing you to watch the process unfold in real-time without manual intervention.
*   **System Notifications:** When a report is finished, the application window is brought to the foreground, a sound effect is played, and a native OS notification is displayed, so you never miss a completed task.
*   **Copy to Clipboard:** Instantly copy the entire generated report text with a single click, ready to be pasted into emails or other documents.
*   **Quick Uninstall:** A clean uninstall option in the settings menu allows for the complete removal of all application data, including the downloaded model and configuration files.
*   **Cross-Platform:** Built with Python and Kivy to run on Windows, macOS, and Linux.
*   **Multi-Model Management:** Install, switch, and delete multiple local GGUF models directly from the Model Settings screen. Perfect for experimenting with different model sizes or quantisations.

## Installation
1.  **Clone the repository or download the source code.**
2.  **Navigate to the application directory:**
    ```bash
    cd /path/to/AutoAgendaWriter
    ```
3.  **Install the required dependencies using pip:**
    ```bash
    pip install -r requirements.txt
    ```
    This will install Kivy, pandas, llama-cpp-python, and all other necessary libraries.

After cloning/installing dependencies, you can prepare the model in one of two ways:

**A. Offline Install (no internet required)**
1. Obtain the model file `Qwen3-4B-Instruct-2507-Q4_1.gguf` (≈ 2.6 GB) from a trusted source.
2. Launch the application and open **Settings → Model Settings**.
3. On the **Install Model** page, drag-and-drop the `.gguf` file (or click to browse).
   The file will be copied to your user data directory and renamed automatically.

**B. Online Download (internet required)**
Click "Download Model from HuggingFace Online" on the Install Model page and follow the prompts.

## How to Use
1.  **Launch App:** Execute the application by running the Python script:
    ```bash
    python3 kivyfrontend.py
    ```
2.  **Install Model (First Time Only):** Upon the first launch, navigate to `Settings` -> `Model Settings` to download and install the required AI model. This is a one-time setup.
3.  **Prepare Your Data:** Ensure your agenda data is in a Microsoft Excel `.xlsx` file. The column headers should match the application's settings (which can be configured in `Settings`).
4.  **Upload File:** Drag and drop your `.xlsx` file onto the main window or use the upload area to browse for it.
5.  **Select Sheet:** If your Excel file contains multiple sheets, a popup will appear. Select the sheet that contains your agenda data.
6.  **Review Items:** A new screen will appear showing all agenda items from the selected sheet. Items flagged for inclusion ('Y' or 'Yes' in the `Include` column, case-insensitive) will be pre-selected. Review and toggle selections as needed.
7.  **Generate:** Click the "Generate" button to start the AI summarization process.
8.  **Save or Copy:** Once complete, you can save the report as a `.docx` file or copy the full text to your clipboard. After saving, a confirmation dialog appears with an option to open the file's location.
9.  **Switch Models (Optional):** At any time, open **Settings → Model Settings** and pick a different model from the drop-down menu. The new model will load in the background.

## Current Status
This application is at **Version 5.0 (Direct Excel Handling)**. It represents a major architectural and feature update, simplifying the end-user workflow by removing the need for CSV conversion.

## Technical Stack
*   **GUI:** `Kivy`
*   **Data Processing:** `pandas`
*   **Local LLM Interaction:** `llama-cpp-python`
*   **Model Management:** `huggingface-hub`
*   **Word Document Generation:** `python-docx`
*   **System Notifications:** `plyer`

## Building the Application

To create a standalone executable for your operating system, you can use the provided build script. This is useful for distributing the application to users who do not have Python installed.

1.  Ensure all development dependencies, including `PyInstaller` and `Pillow`, are installed. If you have a `requirements-dev.txt` or similar, install from it. Otherwise, install them manually:
    ```bash
    pip install pyinstaller pillow
    ```
2.  Run the build script from your terminal in the project's root directory:
    ```bash
    python build.py
    ```
3.  The build process will take a few minutes. Once complete, the final application will be located in the `dist` folder (e.g., `dist/AutoAgendaWriter.exe` on Windows).