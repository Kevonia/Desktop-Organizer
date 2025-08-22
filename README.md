# 🗂️ Desktop File Organizer

A Python script that automatically organizes your desktop files into
structured folders by **Year → Month → File Type**.

This helps keep your desktop clean and makes it easier to find files
later.

------------------------------------------------------------------------

## 🚀 Features

-   Organizes files into folders by:

        Year / Month / FileType /

    Example:

        2025 / 01-January / pdf /
        2025 / 01-January / jpg /

-   Handles **duplicate file names** automatically by appending
    numbers.\

-   Supports **files with no extension** (saved under `no_extension/`).\

-   Provides a **preview mode** (dry run) before making changes.\

-   Works on **Windows, macOS, and Linux**.

------------------------------------------------------------------------

## 📦 Requirements

-   Python **3.7+**\
-   Standard libraries only (`os`, `shutil`, `datetime`, `pathlib`)

No external dependencies required.

------------------------------------------------------------------------

## ⚙️ Installation

1.  Clone or download this repository.\
2.  Save the script as `desktop_organizer.py`.\
3.  Make sure Python is installed (`python3 --version`).

------------------------------------------------------------------------

## ▶️ Usage

Run the script in your terminal:

``` bash
python desktop_organizer.py
```

You'll see the following menu:

    Desktop Organizer
    ==================================================
    1. Preview organization (dry run)
    2. Organize files for real
    3. Exit

### 📝 Option 1: Preview (Dry Run)

Shows how your desktop will be organized without moving any files.

### 📂 Option 2: Organize Files

Moves files into `Year/Month/FileType` folders.\
- Asks for confirmation before making changes.\
- Handles duplicate file names by renaming them (e.g., `file_1.pdf`).

### ❌ Option 3: Exit

Quits the program.

------------------------------------------------------------------------

## 📌 Example

Before organization:

    Desktop/
     ├── resume.pdf
     ├── photo.jpg
     ├── notes.txt
     ├── screenshot.png

After organization:

    Desktop/
     ├── 2025/
     │    ├── 01-January/
     │    │    ├── pdf/
     │    │    │    └── resume.pdf
     │    │    ├── jpg/
     │    │    │    └── photo.jpg
     │    │    ├── txt/
     │    │    │    └── notes.txt
     │    │    ├── png/
     │    │    │    └── screenshot.png

------------------------------------------------------------------------

## ⚠️ Notes

-   Only organizes **files on the desktop**, not subfolders.\
-   Existing files inside the `Year/Month/FileType/` structure won't be
    moved again.\
-   Safe to re-run multiple times.

------------------------------------------------------------------------

## 🛠️ License

This project is released under the **MIT License**.\
Feel free to use and modify it.
