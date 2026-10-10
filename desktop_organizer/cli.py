"""Command-line interface. Run with no arguments for the interactive menu."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from desktop_organizer import APP_NAME, __version__
from desktop_organizer.core import Organizer, SortMode, reports, setups, shell, transfer
from desktop_organizer.core.categories import CATEGORIES
from desktop_organizer.core.config import FolderProfile, describe_pattern
from desktop_organizer.core.history import UndoResult
from desktop_organizer.core.mover import RunResult
from desktop_organizer.core.origin import find_origin
from desktop_organizer.core.paths import resolve_folder
from desktop_organizer.core.safety import UnsafeFolderError, ensure_destination
from desktop_organizer.core.stats import collect, format_size
from desktop_organizer.core.structure import NAME_TOKENS, TOKENS, PatternError, example, validate, validate_name


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="desktop-organizer", description=f"{APP_NAME} {__version__}")
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    sub = parser.add_subparsers(dest="command")

    def structure_options(p: argparse.ArgumentParser) -> None:
        group = p.add_mutually_exclusive_group()
        group.add_argument("--mode", choices=[m.value for m in SortMode], help="a ready-made structure")
        group.add_argument("--pattern", help="your own structure, e.g. '{category}/{year}'")

    for name, help_text in (("preview", "show what would move"), ("organize", "move the files")):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("folder", nargs="?", help="folder path or name (desktop, downloads, documents...)")
        p.add_argument("--all", action="store_true", help="every saved folder")
        structure_options(p)
        if name == "organize":
            p.add_argument("-y", "--yes", action="store_true", help="don't ask for confirmation")
            p.add_argument("--force", action="store_true", help="organize even if the folder looks like a project")

    p = sub.add_parser("undo", help="undo the most recent run")
    p.add_argument("-y", "--yes", action="store_true")
    sub.add_parser("history", help="list past runs")

    folders = sub.add_parser("folders", help="manage saved folders").add_subparsers(dest="action", required=True)
    folders.add_parser("list")
    p = folders.add_parser("add", help="save a folder (path or name like downloads)")
    p.add_argument("folder")
    structure_options(p)
    dest = p.add_mutually_exclusive_group()
    dest.add_argument("--dest", help="put organized files in this folder instead (e.g. on a USB drive)")
    dest.add_argument("--here", action="store_true", help="put organized files back inside the folder itself")
    names = p.add_mutually_exclusive_group()
    names.add_argument("--rename", help="rename files as they move, e.g. '{date} {name}'")
    names.add_argument("--keep-names", action="store_true", help="stop renaming files")
    p = folders.add_parser("remove")
    p.add_argument("folder")

    structure = sub.add_parser("structure", help="choose how files are arranged").add_subparsers(
        dest="action", required=True
    )
    structure.add_parser("show")
    structure.add_parser("tokens", help="list placeholders for custom patterns")
    p = structure.add_parser("set", help="set the default, or one folder's, structure")
    structure_options(p)
    p.add_argument("--folder", help="only for this saved folder")

    categories = sub.add_parser("categories", help="your own file categories").add_subparsers(
        dest="action", required=True
    )
    categories.add_parser("list")
    p = categories.add_parser("add", help="e.g. categories add Invoices pdf")
    p.add_argument("name")
    p.add_argument("extensions", nargs="+")
    p = categories.add_parser("remove")
    p.add_argument("name")

    report = sub.add_parser("report", help="save a preview or a past run as CSV or HTML").add_subparsers(
        dest="action", required=True
    )
    p = report.add_parser("preview", help="what would move, without moving anything")
    p.add_argument("folder", nargs="?")
    p.add_argument("-o", "--output", required=True, help="file to write (.csv or .html)")
    p = report.add_parser("run", help="what a past run moved (the latest one if no number is given)")
    p.add_argument("run_id", nargs="?", type=int)
    p.add_argument("-o", "--output", required=True, help="file to write (.csv or .html)")

    p = sub.add_parser("stats", help="what's taking up space in a folder")
    p.add_argument("folder", nargs="?")
    p.add_argument("--months", type=int, default=6, help="count files not used in this many months")
    p.add_argument("--top", type=int, default=10, help="how many of the largest files to list")

    setup = sub.add_parser("setups", help="ready-made setups for students, freelancers...").add_subparsers(
        dest="action", required=True
    )
    setup.add_parser("list")
    p = setup.add_parser("apply")
    p.add_argument("name", help="e.g. student, freelancer, photographer, music")

    io = sub.add_parser("settings", help="export or import rules, categories and layouts").add_subparsers(
        dest="action", required=True
    )
    for name in ("export", "import"):
        p = io.add_parser(name)
        p.add_argument("file")
        p.add_argument("--only", nargs="+", choices=transfer.PARTS, help="just these parts")

    p = sub.add_parser("where", help="where did this file come from?")
    p.add_argument("file")

    p = sub.add_parser("shell", help="File Explorer right-click menu (Windows)")
    p.add_argument("action", choices=["on", "off", "status"])
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    organizer = Organizer()
    try:
        if args.command is None:
            return menu(organizer)
        handler = {
            "preview": cmd_preview,
            "organize": cmd_organize,
            "undo": lambda o, a: undo_last(o, confirm=not a.yes),
            "history": lambda o, a: show_history(o),
            "folders": cmd_folders,
            "structure": cmd_structure,
            "categories": cmd_categories,
            "report": cmd_report,
            "stats": cmd_stats,
            "setups": cmd_setups,
            "settings": cmd_settings,
            "where": cmd_where,
            "shell": cmd_shell,
        }[args.command]
        return handler(organizer, args)
    except (PatternError, UnsafeFolderError, ValueError, OSError) as exc:
        print(f"Error: {exc}")
        return 1


# --- commands ----------------------------------------------------------------


def cmd_preview(organizer: Organizer, args) -> int:
    pattern = _pattern_arg(args)
    for folder in _target_folders(organizer, args):
        preview(organizer, folder, pattern)
    return 0


def cmd_organize(organizer: Organizer, args) -> int:
    pattern = _pattern_arg(args)
    code = 0
    for folder in _target_folders(organizer, args):
        code = max(code, organize(organizer, folder, pattern, confirm=not args.yes, force=args.force))
    return code


def cmd_folders(organizer: Organizer, args) -> int:
    settings = organizer.settings
    if args.action == "list":
        print_folders(organizer)
    elif args.action == "add":
        folder = resolve_folder(args.folder)
        organizer.check(folder)  # refuse system folders up front
        profile = settings.add_folder(args.folder, _pattern_arg(args))
        if args.dest:
            destination = resolve_folder(args.dest)
            ensure_destination(destination)
            profile.destination = str(destination.resolve())
        elif args.here:
            profile.destination = None
        if args.rename:
            profile.rename = validate_name(args.rename)
        elif args.keep_names:
            profile.rename = None
        settings.save()
        print(f"Saved {profile.name} ({describe_pattern(profile.pattern or settings.pattern)}).")
        if profile.destination:
            print(f"Organized files go to {profile.target}.")
        if profile.rename:
            print(f"Files are renamed to: {profile.rename}")
        for warning in organizer.check(folder):
            print(f"Warning: {warning}")
    elif args.action == "remove":
        if not settings.remove_folder(args.folder):
            print(f"{args.folder} isn't a saved folder.")
            return 1
        settings.save()
        print("Removed.")
    return 0


def cmd_structure(organizer: Organizer, args) -> int:
    settings = organizer.settings
    if args.action == "show":
        print(f"Default: {describe_pattern(settings.pattern)}  e.g. {example(settings.pattern, settings.custom_categories)}")
        print_folders(organizer)
    elif args.action == "tokens":
        print_tokens()
    elif args.action == "set":
        pattern = _pattern_arg(args)
        if not pattern:
            print("Give --mode or --pattern.")
            return 1
        if args.folder:
            profile = settings.add_folder(args.folder, pattern)
            print(f"{profile.name} now uses {describe_pattern(pattern)}.")
        else:
            settings.pattern = pattern
            print(f"Default structure is now {describe_pattern(pattern)}.")
        settings.save()
        print(f"Example: {example(pattern, settings.custom_categories)}")
    return 0


def cmd_categories(organizer: Organizer, args) -> int:
    settings = organizer.settings
    if args.action == "list":
        print_categories(organizer)
    elif args.action == "add":
        settings.set_category(args.name, args.extensions)
        settings.save()
        print(f"{args.name}: {', '.join(settings.custom_categories[args.name.strip()])}")
    elif args.action == "remove":
        if not settings.remove_category(args.name):
            print(f"No custom category called {args.name}.")
            return 1
        settings.save()
        print("Removed.")
    return 0


def cmd_report(organizer: Organizer, args) -> int:
    if args.action == "preview":
        folder = resolve_folder(args.folder) if args.folder else _target_folders(organizer, args)[0]
        pattern = organizer.pattern_for(folder)
        report = reports.preview_report(folder, pattern, organizer.preview(folder))
    else:
        run_id = args.run_id
        if run_id is None:
            runs = organizer.history.runs(limit=1)
            if not runs:
                print("No runs yet.")
                return 1
            run_id = runs[0].id
        report = reports.run_report(organizer.history, run_id)
    saved = reports.save(report, Path(args.output))
    print(f"Saved {len(report.rows)} file(s) to {saved}")
    return 0


def cmd_stats(organizer: Organizer, args) -> int:
    folder = resolve_folder(args.folder) if args.folder else _target_folders(organizer, args)[0]
    stats = collect(folder, organizer.settings.custom_categories, stale_days=args.months * 30, top=args.top)
    print(f"\n{folder}: {format_size(stats.total_size)} in {stats.file_count:,} files")
    print(f"Not used in {args.months} months: {format_size(stats.stale_size)} ({stats.stale_count:,} files)")
    print("\nBy category:")
    for name, total in stats.categories_by_size():
        print(f"  {name:<14} {format_size(total.size):>10}  {total.count:>7,} files")
    if stats.largest:
        print(f"\nLargest {len(stats.largest)} files:")
        for entry in stats.largest:
            print(f"  {format_size(entry.size):>10}  {entry.path}")
    return 0


def cmd_setups(organizer: Organizer, args) -> int:
    if args.action == "list":
        for setup in setups.SETUPS:
            print(f"{setup.key:<14} {setup.name}: {setup.summary}")
        return 0
    setup = setups.get(args.name)
    if setup is None:
        print(f"No setup called {args.name}. Try: {', '.join(s.key for s in setups.SETUPS)}")
        return 1
    summary = setup.apply(organizer.settings)
    organizer.settings.save()
    print(f"{setup.name} setup added.")
    for line in summary.lines():
        print(f"  {line}")
    return 0


def cmd_settings(organizer: Organizer, args) -> int:
    parts = args.only or list(transfer.PARTS)
    if args.action == "export":
        saved = transfer.export_file(organizer.settings, Path(args.file), parts)
        print(f"Saved to {saved}")
        return 0
    data = transfer.read_file(Path(args.file))
    summary = transfer.apply(organizer.settings, data, parts)
    organizer.settings.save()
    for line in summary.lines():
        print(line)
    return 0


def cmd_where(organizer: Organizer, args) -> int:
    path = Path(args.file).expanduser().absolute()
    origin = find_origin(path, organizer.history)
    print(origin.summary())
    for source, destination, when in origin.moves:
        print(f"  {when:%Y-%m-%d %H:%M}  {source}  ->  {destination}")
    if origin.download:
        for label, url in (("Page", origin.download.referrer_url), ("File", origin.download.host_url)):
            if url:
                print(f"  {label}: {url}")
    return 0


def cmd_shell(organizer: Organizer, args) -> int:
    if not shell.is_supported():
        print("The File Explorer menu is only available on Windows.")
        return 1
    if args.action != "status":
        shell.set_enabled(args.action == "on")
    print("File Explorer menu: " + ("on" if shell.is_enabled() else "off"))
    return 0


# --- actions shared by commands and the menu ---------------------------------


def preview(organizer: Organizer, folder: Path, pattern: str | None = None) -> int:
    pattern = pattern or organizer.pattern_for(folder)
    moves = organizer.preview(folder, pattern)
    print(f"\nPreview for {folder}  [{describe_pattern(pattern)}]")
    print("-" * 50)
    for move in moves:
        renamed = f" (as {move.new_name})" if move.new_name else ""
        where = move.relative_target.as_posix() + "/"
        if move.root != folder:  # organized into another folder
            where = f"{move.root}{os.sep}{where}"
        print(f"{move.source.name} -> {where}{renamed}")
    print(f"Total files that would be organized: {len(moves)}")
    return 0


def organize(organizer: Organizer, folder: Path, pattern: str | None, confirm: bool, force: bool = False) -> int:
    warnings = organizer.check(folder)
    for warning in warnings:
        print(f"Warning: {warning}")
    if warnings and not force:
        if not confirm:
            print(f"Skipped {folder}. Use --force to organize it anyway.")
            return 1
        if not _ask("Organize it anyway? (y/n): "):
            print("Operation cancelled.")
            return 0
    moves = organizer.preview(folder, pattern)
    if not moves:
        print(f"Nothing to organize in {folder}.")
        return 0
    if confirm and not _ask(f"Move {len(moves)} files in {folder}? (y/n): "):
        print("Operation cancelled.")
        return 0
    result = organizer.organize(folder, moves, pattern)
    _print_run(result, folder)
    return 0 if not result.failed else 2


def undo_last(organizer: Organizer, confirm: bool) -> int:
    run = organizer.history.last_undoable_run()
    if run is None:
        print("Nothing to undo.")
        return 0
    when = run.started_at.strftime("%Y-%m-%d %H:%M")
    if confirm and not _ask(f"Undo run #{run.id} in {run.folder} from {when} ({run.move_count} files)? (y/n): "):
        print("Operation cancelled.")
        return 0
    result = organizer.undo(run.id)
    _print_undo(result)
    return 0 if not result.failed else 2


def show_history(organizer: Organizer) -> int:
    runs = organizer.history.runs()
    if not runs:
        print("No runs yet.")
        return 0
    for run in runs:
        status = "undone" if run.undone_at else f"{run.move_count} files"
        print(f"#{run.id:<4} {run.started_at:%Y-%m-%d %H:%M}  {status:<10}  {run.folder}")
    return 0


def print_folders(organizer: Organizer) -> None:
    settings = organizer.settings
    if not settings.folders:
        print("No saved folders.")
    for i, profile in enumerate(settings.folders, start=1):
        print(f"{i}. {profile.name:<12} {describe_pattern(profile.pattern or settings.pattern):<28} {profile.location}")


def print_tokens() -> None:
    print("Placeholders for custom structures (use / between folder levels):")
    for token, (description, sample) in TOKENS.items():
        print(f"  {{{token}}}".ljust(18) + f"{description}  (e.g. {sample})")
    print("Example: '{category}/{year}' or 'Sorted/{year}/{month_name}/{type}'")
    print("\nWhen renaming (folders add --rename), you can also use:")
    for token, (description, sample) in NAME_TOKENS.items():
        print(f"  {{{token}}}".ljust(18) + f"{description}  (e.g. {sample})")
    print("Example: '{date} {name}' turns IMG_1234.jpg into 2025-01-05 IMG_1234.jpg")


def print_categories(organizer: Organizer) -> None:
    custom = organizer.settings.custom_categories
    if custom:
        print("Your categories (checked first):")
        for name, exts in custom.items():
            print(f"  {name}: {', '.join(exts)}")
    print("Built-in categories:")
    for name, exts in CATEGORIES.items():
        print(f"  {name}: {', '.join(sorted(exts))}")


# --- interactive menu -------------------------------------------------------------


def menu(organizer: Organizer) -> int:
    try:
        while True:
            print(f"\n{APP_NAME}")
            print("=" * 50)
            print_folders(organizer)
            print()
            print("1. Preview organization (dry run)")
            print("2. Organize files for real")
            print("3. Undo last organization")
            print("4. Show history")
            print("5. Manage folders")
            print("6. Change folder structure")
            print("7. Exit")
            choice = input("\nEnter your choice (1-7): ").strip()
            try:
                if choice in ("1", "2"):
                    for folder in _pick_folders(organizer):
                        if choice == "1":
                            preview(organizer, folder)
                        else:
                            organize(organizer, folder, None, confirm=True)
                elif choice == "3":
                    undo_last(organizer, confirm=True)
                elif choice == "4":
                    show_history(organizer)
                elif choice == "5":
                    _menu_folders(organizer)
                elif choice == "6":
                    _menu_structure(organizer)
                elif choice == "7":
                    print("Goodbye!")
                    return 0
                else:
                    print("Invalid choice.")
            except (PatternError, UnsafeFolderError, ValueError) as exc:
                print(f"Error: {exc}")
    except (EOFError, KeyboardInterrupt):
        print()
        return 0


def _pick_folders(organizer: Organizer) -> list[Path]:
    folders = organizer.settings.folders
    if len(folders) == 1:
        return [folders[0].location]
    if not folders:
        print("No saved folders. Add one with 'Manage folders'.")
        return []
    choice = input(f"Which folder? (1-{len(folders)}, or A for all): ").strip().lower()
    if choice == "a":
        return [f.location for f in folders]
    profile = _by_number(folders, choice)
    return [profile.location] if profile else []


def _menu_folders(organizer: Organizer) -> None:
    settings = organizer.settings
    print("\nA. Add a folder   R. Remove a folder")
    choice = input("Choose: ").strip().lower()
    if choice == "a":
        spec = input("Folder path, or a name like downloads / documents / pictures: ").strip().strip('"')
        if not spec:
            return
        folder = resolve_folder(spec)
        for warning in organizer.check(folder):
            print(f"Warning: {warning}")
        profile = settings.add_folder(spec)
        settings.save()
        print(f"Saved {profile.name}. It uses the default structure until you change it.")
    elif choice == "r":
        profile = _by_number(settings.folders, input("Number to remove: ").strip())
        if profile:
            settings.folders.remove(profile)
            settings.save()
            print(f"Removed {profile.name}.")


def _menu_structure(organizer: Organizer) -> None:
    settings = organizer.settings
    target: FolderProfile | None = None
    if settings.folders:
        choice = input(f"Change the default (D) or one folder (1-{len(settings.folders)})? ").strip().lower()
        if choice != "d":
            target = _by_number(settings.folders, choice)
            if target is None:
                return

    modes = list(SortMode)
    for i, mode in enumerate(modes, start=1):
        print(f"{i}. {mode.label:<26} e.g. {example(mode.pattern, settings.custom_categories)}")
    custom_number = len(modes) + 1
    print(f"{custom_number}. Build my own")
    if target is not None:
        print(f"{custom_number + 1}. Use the default")
    choice = input("Choose: ").strip()

    if choice == str(custom_number):
        print_tokens()
        pattern = validate(input("Your structure: "))
    elif target is not None and choice == str(custom_number + 1):
        pattern = None
    else:
        mode = _by_number(modes, choice)
        if mode is None:
            return
        pattern = mode.pattern

    if target is None:
        settings.pattern = pattern
    else:
        target.pattern = pattern
    settings.save()
    effective = pattern or settings.pattern
    print(f"Saved. Example: {example(effective, settings.custom_categories)}")


# --- helpers -----------------------------------------------------------------------


def _pattern_arg(args) -> str | None:
    if getattr(args, "mode", None):
        return SortMode(args.mode).pattern
    if getattr(args, "pattern", None):
        return validate(args.pattern)
    return None


def _target_folders(organizer: Organizer, args) -> list[Path]:
    if getattr(args, "all", False):
        return [f.location for f in organizer.settings.folders]
    if getattr(args, "folder", None):
        return [resolve_folder(args.folder)]
    return [organizer.settings.folders[0].location] if organizer.settings.folders else [resolve_folder("desktop")]


def _by_number(items: list, choice: str):
    if choice.isdigit() and 1 <= int(choice) <= len(items):
        return items[int(choice) - 1]
    print("Invalid choice.")
    return None


def _print_run(result: RunResult, folder: Path) -> None:
    for source, destination in result.moved:
        try:
            where = destination.parent.relative_to(folder).as_posix() + "/"
        except ValueError:  # organized into another folder
            where = str(destination.parent)
        renamed = f" (as {destination.name})" if destination.name != source.name else ""
        print(f"Moved: {source.name} -> {where}{renamed}")
    for source, reason in result.failed:
        print(f"Error processing {source.name}: {reason}")
    print("\nOrganization complete!")
    print(f"Files organized: {len(result.moved)}")
    print(f"Files skipped: {len(result.failed)}")
    if result.moved:
        print("Changed your mind? Choose 'Undo last organization' (or run: desktop-organizer undo).")


def _print_undo(result: UndoResult) -> None:
    for _, restored in result.restored:
        print(f"Restored: {restored.name}")
    for path, reason in result.failed:
        print(f"Could not restore {path.name}: {reason}")
    print(f"\nRestored {len(result.restored)} files, {len(result.failed)} failed.")


def _ask(prompt: str) -> bool:
    return input(prompt).strip().lower() in ("y", "yes")
