# City of Pacifica - Agenda Summary Generator

## Overview
This application is designed to significantly streamline the process of creating comprehensive agenda summaries for the City of Pacifica City Council meetings. It operates by ingesting a structured comma-separated value (CSV) file, leveraging a local Large Language Model (LLM) to perform both summarization and categorization of agenda items, and subsequently generating a professionally formatted Microsoft Word (.docx) document that is ready for review and finalization. The goal is to provide an efficient, privacy-focused, and user-friendly tool for managing meeting agenda data.

## Key Features
*   **GUI Overhaul:** A redesigned, modern user interface built with Kivy for a more intuitive and visually appealing experience.
*   **One-Click Model Installation:** A simple, one-time setup process to download and install the required local LLM directly from the settings menu.
*   **Full Item Parsing & Auto-Selection:** The application now parses all agenda items from the CSV and presents them in a clear, scrollable list. Items can be automatically pre-selected for inclusion based on a flag in the source file.
*   **Flexible CSV Headers:** Customize the exact column header names (e.g., "MEETING DATE", "AGENDA ITEM") in the settings to match your specific CSV file format. No need to edit the file itself.
*   **Customizable AI Prompts:** Advanced users can modify the prompt templates used for both summarization (Pass 1) and formatting (Pass 2) via the settings menu, allowing for fine-tuned control over the AI's output.
*   **Self-Scrolling Console:** Both the main generation output and the optional debug console now scroll automatically, allowing you to watch the process unfold in real-time without manual intervention.
*   **System Notifications:** When a report is finished, the application window is brought to the foreground, a sound effect is played, and a native OS notification is displayed, so you never miss a completed task.
*   **Quick Uninstall:** A clean uninstall option in the settings menu allows for the complete removal of all application data, including the downloaded model and configuration files.
*   **Cross-Platform:** Built with Python and Kivy to run on Windows, macOS, and Linux.

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

## How to Use
1.  **Launch App:** Execute the application by running the Python script:
    ```bash
    python3 kivyfrontend.py
    ```
2.  **Install Model (First Time Only):** Upon the first launch, navigate to the `Settings` menu and click the `Install` button to download the required AI model. This is a one-time setup.
3.  **Prepare CSV:** Ensure your agenda data is in a `.csv` file. The column headers should match the application's settings (which can be configured).
4.  **Upload File:** Drag and drop your `.csv` file onto the main window or use the upload area to browse for it.
5.  **Review Items:** A new screen will appear showing all agenda items. Items flagged for inclusion will be pre-selected. Review and toggle selections as needed.
6.  **Generate:** Click the "Generate" button to start the AI summarization process.
7.  **Save:** Once complete, save the report as a `.docx` file.

## Current Status
This application is at **Version 3.0 (Kivy Overhaul)**. It represents a major architectural and feature update, focusing on user experience, configurability, and a more robust workflow.

## Technical Stack
*   **GUI:** `Kivy`
*   **Data Processing:** `pandas`
*   **Local LLM Interaction:** `llama-cpp-python`
*   **Model Management:** `huggingface-hub`
*   **Word Document Generation:** `python-docx`
*   **System Notifications:** `plyer`