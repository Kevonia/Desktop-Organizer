import os
import shutil
from datetime import datetime
from pathlib import Path

def organize_desktop():
    # Get the desktop path (works for both Windows and macOS)
    desktop_path = Path.home() / "Desktop"
    
    # List all files and directories on the desktop
    items = list(desktop_path.iterdir())
    
    # Filter out directories and only process files
    files = [item for item in items if item.is_file()]
    
    print(f"Found {len(files)} files to organize...")
    
    organized_count = 0
    skipped_count = 0
    
    for file_path in files:
        try:
            # Get file creation/modification time
            creation_time = datetime.fromtimestamp(file_path.stat().st_ctime)
            year = str(creation_time.year)
            month = creation_time.strftime("%m-%B")  # e.g., "01-January"
            
            # Get file extension (type)
            file_extension = file_path.suffix.lower()
            if not file_extension:  # If no extension, use "no_extension"
                file_type = "no_extension"
            else:
                file_type = file_extension[1:]  # Remove the dot
            
            # Create the target directory structure: Year/Month/FileType/
            target_dir = desktop_path / year / month / file_type
            target_dir.mkdir(parents=True, exist_ok=True)
            
            # Move the file
            target_file = target_dir / file_path.name
            
            # Handle duplicate file names
            counter = 1
            while target_file.exists():
                stem = file_path.stem
                new_name = f"{stem}_{counter}{file_path.suffix}"
                target_file = target_dir / new_name
                counter += 1
            
            shutil.move(str(file_path), str(target_file))
            print(f"Moved: {file_path.name} -> {target_dir.name}/")
            organized_count += 1
            
        except Exception as e:
            print(f"Error processing {file_path.name}: {e}")
            skipped_count += 1
            continue
    
    print(f"\nOrganization complete!")
    print(f"Files organized: {organized_count}")
    print(f"Files skipped: {skipped_count}")

def preview_organization():
    """Preview what the organization would look like without actually moving files"""
    desktop_path = Path.home() / "Desktop"
    items = list(desktop_path.iterdir())
    files = [item for item in items if item.is_file()]
    
    print("Preview of organization structure:")
    print("-" * 50)
    
    for file_path in files:
        try:
            creation_time = datetime.fromtimestamp(file_path.stat().st_ctime)
            year = str(creation_time.year)
            month = creation_time.strftime("%m-%B")
            file_extension = file_path.suffix.lower()
            file_type = file_extension[1:] if file_extension else "no_extension"
            
            print(f"{file_path.name} -> {year}/{month}/{file_type}/")
            
        except Exception as e:
            print(f"{file_path.name} -> Error: {e}")
    
    print(f"\nTotal files that would be organized: {len(files)}")

if __name__ == "__main__":
    print("Desktop Organizer")
    print("=" * 50)
    print("1. Preview organization (dry run)")
    print("2. Organize files for real")
    print("3. Exit")
    
    choice = input("\nEnter your choice (1-3): ").strip()
    
    if choice == "1":
        preview_organization()
    elif choice == "2":
        # Ask for confirmation
        confirm = input("\nAre you sure you want to organize your desktop files? (y/n): ").lower()
        if confirm in ['y', 'yes']:
            organize_desktop()
        else:
            print("Operation cancelled.")
    elif choice == "3":
        print("Goodbye!")
    else:
        print("Invalid choice. Please run the script again.")