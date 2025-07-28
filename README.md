# City of Pacifica - Agenda Summary Generator

## Overview
This application is designed to significantly streamline the process of creating comprehensive agenda summaries specifically for the City of Pacifica City Council meetings. It operates by ingesting a structured comma-separated value (CSV) file, leveraging a local Large Language Model (LLM) to perform both summarization and categorization of agenda items, and subsequently generating a professionally formatted Microsoft Word (.docx) document that is ready for review and finalization. The goal is to provide an efficient, privacy-focused, and user-friendly tool for managing meeting agenda data.

## Key Features
*   **CSV Ingestion:** Robustly parses and extracts agenda items directly from a `.csv` file. The application expects specific column headers within the CSV file for proper data processing.
*   **AI-Powered Summarization:** Employs a sophisticated two-pass approach utilizing a locally executed LLM. This method ensures the generation of high-quality, concise summaries while maintaining user privacy, as the data does not leave the user's machine.
*   **Automated Formatting:** Automatically generates a professionally formatted `.docx` report. This includes the application of appropriate headers, structured sections, and consistent styling to ensure readability and a polished appearance.
*   **Cross-Platform GUI:** Developed using the Kivy framework, providing a consistent and responsive graphical user interface experience across major operating systems, including Windows, macOS, and Linux.
*   **User-Friendly Interface:** Features an intuitive interface designed for ease of use. Key elements include drag-and-drop functionality for uploading CSV files, a clear mechanism for reviewing and selecting specific agenda items to include in the summary, and real-time progress indicators during the generation process.
*   **Configurable:** Allows users to customize the application's behavior through a dedicated settings menu. This includes the ability to select to inspect outputs, install the LLM model, define custom prompt templates, or perform a clean uninstall.
*   **Modifiable Headers:** The names of the CSV columns ("MEETING DATE", "AGENDA SECTION", etc.) can be customized in the settings menu to match your specific file format. These settings are saved and loaded automatically.

## How to Use
1.  **Launch App:** Execute the application by running the Python script: `python3 kivyfrontend.py`.
2.  **Install Model:** Upon the first launch of the application, navigate to the `Settings` menu and click the `Install` button to initiate the download of the required AI model (`unsloth/Qwen3-4B-GGUF`). This is a one-time setup procedure.
3.  **Prepare CSV:** Ensure your agenda data is organized within a `.csv` file, adhering to the required column structure specified by the application.
4.  **Upload File:** You can either drag and drop your `.csv` file directly onto the main application window or use the browse button to select and upload the file.
5.  **Review Items:** Carefully review the list of agenda items presented in the application. Deselect any items that you wish to exclude from the final summary.
6.  **Generate:** Click the "Generate" button to initiate the AI-powered summarization process based on the selected items and configured settings.
7.  **Save:** Once the generation process is complete, save the resulting report as a `.docx` file to your desired location.

## Current Status
This application is currently at **Version 2.0 (Kivy Edition)**. It represents a significant update, having been completely rebuilt from scratch using the Kivy framework to deliver a more robust, feature-rich, and consistent cross-platform experience.

*   **Built-in Model Installer:** The application includes a convenient one-click installer for the necessary AI model (`unsloth/Qwen3-4B-GGUF`). The model is downloaded and stored in a local application data folder, ensuring it is readily available for future use.
*   **Placeholders:** The generated Word document incorporates specific placeholders (e.g., "TBD" items, "Significant Items Completed Since [Date]"). These placeholders are intended to facilitate final human review, manual additions, and adjustments to the summary.

## TBD (Future Development)
*   **Video Demonstration:** A link to a video demonstration is planned to be added to the help tab in the future.
*   **Help Tab Improvements:** Plans are underway to enhance the help tab with more detailed instructions, comprehensive troubleshooting tips, and additional resources.
*   **Done Notification:** When finished with generation, app outputs a notification and maybe a sound or something to notify user, so it can be left running generating in the background and will still display some kind of thing that will tell user it is finished, anything works, preferably visual not audio though.

## Technical Stack
*   **GUI:** `Kivy`
*   **Data Processing:** `pandas`
*   **Local LLM Interaction:** `llama-cpp-python`
*   **Word Document Generation:** `python-docx`