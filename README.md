# City of Pacifica - Agenda Summary Generator

## Overview
The "City of Pacifica - Agenda Summary Generator" is a desktop application designed to streamline the process of summarizing city council agenda items. It allows users to upload a specially formatted CSV file, automatically filters relevant items, uses a local Large Language Model (LLM) to generate concise summaries, and compiles them into a professionally formatted Microsoft Word (.docx) document.

**Goal:** To simplify the process of creating agenda summaries, especially for officials like the City of Pacifica clerk, by automating the transformation of raw agenda data into a digestible report.

## Key Features
*   **CSV File Upload:** Easily import agenda data via drag-and-drop or file selection.
*   **Data Validation:** Ensures your CSV file has all the necessary columns for accurate processing.
*   **Intelligent Filtering:** Automatically identifies agenda items marked for inclusion in the summary report.
*   **Review & Selection:** Provides a user-friendly interface to review and select specific items before summarization.
*   **AI-Powered Summarization:** Utilizes a local LLM (Large Language Model) to generate concise summaries of each agenda item.
*   **Professional Document Generation:** Creates a well-formatted Microsoft Word (.docx) document ready for review and distribution.

## How to Use
1.  **Prepare Your CSV File:** Ensure your .csv file contains the required headers and data, especially the "Include in Summary for Mayor" column, marked with 'Y' for items you want to include.
2.  **Upload Your File:** On the "Home" tab of the application, drag your prepared .csv file into the designated area or click the button to select it from your computer.
3.  **Review and Select Items:** After a successful upload, the application will display a list of all agenda items identified for potential inclusion. All items are selected by default, but you can uncheck any item you wish to exclude.
4.  **Generate the Report:** Click the "Generate Report" button. The application will then process the selected items, generate summaries using its local AI, and prepare the Word document.
5.  **Save Your Document:** A "Save As" dialog will appear. Choose a name and location to save your new Microsoft Word (.docx) report.

## Current Status
This application is currently in development (version 1.0) and serves as a powerful tool to automate parts of the agenda summary process.
*   **Local LLM Required:** The application relies on a local LLM model file (e.g., `gemma-2b-it.gguf`) to be present in the same directory as the executable.
*   **Placeholders:** The generated Word document includes placeholders for manual input (e.g., "TBD" items, "Significant Items Completed Since [Date]") to allow for final human review and additions.

## TBD
*   **Video Demonstration:** A link for a video demonstration in the help tab is yet to be added.
*   **Help Tab Improvements:** Planning to enhance the help tab with more detailed instructions and troubleshooting tips
*   **GUI Experience:** Working on improving the overall user interface for smoother navigation and better usability - add Pacifica branding and make neater fun stuff.
*   **Improved Error Messages:** Add more details to why a .csv import fails, potentially scanning across set of expected column headers in the .csv until a mismatch to what is expected occurs, and then saying that it expects column 'A' to be 'MEETING DATE', etc.
*   **Parsing ALL rows:** Parse and display ALL rows in the checkbox menu, and only check the ones marked Y, to allow for overall viewing of spreadsheet within app. Make checkbox menu more condensed and optimized quicker to load because it lags right now.
*   **Ignoring Certain Statements:** Parse out and ignore everything denoted by brackets [] in what is sent to the LLM.
*   **Drag and Drop:** Fix drag and drop for .csv input.
*   **Model Selection:** Allow for flexible model selection.
*   **Back Button Stoppage:** Back button from generation screen cancels the LLM generation running in the background.

## Technical Stack
*   **GUI:** `customtkinter`
*   **Data Processing:** `pandas`
*   **Local LLM Interaction:** `llama-cpp-python`
*   **Word Document Generation:** `python-docx`
