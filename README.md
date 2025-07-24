# City of Pacifica - Agenda Summary Generator

## Overview
This application streamlines the process of creating agenda summaries for the City of Pacifica's City Council meetings. It ingests a structured CSV file, uses a local Large Language Model (LLM) to summarize and categorize agenda items, and generates a formatted Microsoft Word document ready for review.

## Key Features
*   **CSV Ingestion:** Parses agenda items from a `.csv` file.
*   **AI-Powered Summarization:** Utilizes a two-pass approach with a local LLM for high-quality, privacy-focused content generation.
*   **Automated Formatting:** Creates a professionally formatted `.docx` report with proper headers, sections, and styling.
*   **Cross-Platform GUI:** Built with Kivy for a consistent experience on Windows, macOS, and Linux.
*   **User-Friendly Interface:** Features drag-and-drop file uploads, item review and selection, and real-time generation progress.
*   **Configurable:** Allows users to select their own LLM model file and custom prompt templates through a settings menu.

## How to Use
1.  **Launch App:** Run `python3 kivyfrontend.py`.
2.  **Install Model:** On first launch, go to `Settings` and click `Install` to download the required AI model. This is a one-time setup.
3.  **Prepare CSV:** Ensure your agenda data is in a `.csv` file with the required columns.
4.  **Upload File:** Drag and drop your `.csv` file onto the main window or click to browse.
5.  **Review Items:** Deselect any items you wish to exclude from the summary.
6.  **Generate:** Click the "Generate" button to start the AI process.
7.  **Save:** Once complete, save the report as a `.docx` file.

## Current Status
This application is at **Version 2.0 (Kivy Edition)**. It has been rebuilt from the ground up using the Kivy framework to provide a more robust and feature-rich cross-platform experience.

*   **Built-in Model Installer:** The application includes a one-click installer for the required AI model (`unsloth/Qwen3-4B-GGUF`). The model is downloaded to a local application data folder, ensuring it's always available.
*   **Placeholders:** The generated Word document includes placeholders for manual input (e.g., "TBD" items, "Significant Items Completed Since [Date]") to allow for final human review and additions.

## TBD
*   **Video Demonstration:** A link for a video demonstration in the help tab is yet to be added.
*   **Help Tab Improvements:** Planning to enhance the help tab with more detailed instructions and troubleshooting tips
*   **GUI Experience:** Working on improving the overall user interface for smoother navigation and better usability - add Pacifica branding and make neater fun stuff.
*   **Improved Error Messages:** Add more details to why a .csv import fails, potentially scanning across set of expected column headers in the .csv until a mismatch to what is expected occurs, and then saying that it expects column 'A' to be 'MEETING DATE', etc.
*   **Ignoring Certain Statements:** Parse out and ignore everything denoted by brackets [] in what is sent to the LLM.
*   **Settings Menu: Prompt Selection:** Create a settings menu and appdata folder and allow for flexible prompt modification in the back-end. It should have button to edit the PASS 1 or PASS 2 prompt then it opens a text box for what the prompt is and you can modify it there. (And can still use {}) to use fstrings replacements.
*   **Settings Menu: Debug Mode:** Create a settings menu and appdata folder and allow for toggling a Debug Mode, where when enabled a terminal appears where the PASS 1 and PASS 2 thoughts are outputted, alongside input values and token speeds and memory, to see and help debug on any OS.
*   **Settings Menu: Uninstall App:** Clean up the app files including where model got downloaded and json settings.


## Technical Stack
*   **GUI:** `Kivy`
*   **Data Processing:** `pandas`
*   **Local LLM Interaction:** `llama-cpp-python`
*   **Word Document Generation:** `python-docx`
