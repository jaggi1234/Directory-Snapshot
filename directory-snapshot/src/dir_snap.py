from pathlib import Path
from shutil import rmtree
try:
    from tqdm import tqdm
    tqdm_missing = False
except ImportError:
    tqdm_missing = True
    pass

from templates import *
from utils import *
from args_parsing import prepare_args_parser


dest_path_root = None


def write_file_entry(entry, out_file_path, progress_bar):
    filesize = entry.stat().st_size
    filesize_rounded = round_file_size_to_human_friendly_units(filesize)
    filename_escaped = escape_html_special_chars(entry.name)
    table_row = template_files_table_row.format(filename=filename_escaped, filesize=filesize_rounded)
    append_text_to_file(out_file_path, table_row)
    progress_bar.update() if progress_bar else None
    return filesize


def write_dir_entry(entry, dir_size, out_file_path):
    dir_size_readable = round_file_size_to_human_friendly_units(dir_size)
    dirname_escaped = escape_html_special_chars(entry.name)
    dirname_escaped = escape_html_special_chars(entry.name, True)
    href = dirname_escaped + "/" + dirname_escaped
    table_row = template_dirs_table_row.format(href=href, dirname=dirname_escaped, dirsize=dir_size_readable)
    append_text_to_file(out_file_path, table_row)


def write_symlink_entry(entry, out_file_path, progress_bar):
    filename_escaped = escape_html_special_chars(entry.name)
    file_resolved = entry.resolve().name
    table_row = template_symlinks_table_row.format(filename=filename_escaped, filename_resolved=file_resolved)
    append_text_to_file(out_file_path, table_row)
    progress_bar.update() if progress_bar else None


def get_snapshot(src_path: Path, dest_path: Path, progress_bar, 
                 ignore_hidden, ignore_symlinks, max_rec_depth):
    source_path_size = 0
    pwd: Path = dest_path / src_path.name
    if pwd.exists():
        rmtree(pwd)
    pwd.mkdir(parents=True, exist_ok=True)

    # Create the output file
    out_file_path: Path = pwd / (src_path.name + ".html")
    out_file_path.touch()

    if src_path == dest_path_root:
        # Don't go further down the filesystem heirarchy
        # as it will result in an infinite recursion.
        print("Original destination path reached!!")
        out_file_path.write_text("<b>This was the original destination path!</b>\n")
        return -1
    
    src_path_contents: List[Path] = list_dir_contents(src_path, ignore_symlinks, ignore_hidden)
    if src_path_contents is None:
        return 0
    
    # Sort, since directory iteration is not ordered on some file systems
    src_path_contents.sort()

    # Categorize the contents into separate containers depending upon their file-types
    symlinks, files, dirs = [], [], []
    for entry in src_path_contents:
        if entry.is_dir():
            dirs.append(entry)
        elif entry.is_symlink():
            symlinks.append(entry)
        else:
            files.append(entry)
            # TODO: Handle other file types also.

    # Write table header
    html_header = template_html_header.format(filename = escape_html_special_chars(src_path.name))
    out_file_path.write_text(html_header)

    # Write files info to table
    append_text_to_file(out_file_path, template_files_table_header)
    if not files:
        append_text_to_file(out_file_path, "No files found.\n")
    for entry in files:
        try:
            filesize = write_file_entry(entry, out_file_path, progress_bar)
            source_path_size += filesize
        except Exception as e:
            print(f"Error while processing file '{entry}': {e}")
    append_text_to_file(out_file_path, template_table_close)

    # Write directories info to table
    append_text_to_file(out_file_path, template_dirs_table_header)
    if not dirs:
        append_text_to_file(out_file_path, "No subdirectories found.\n")
    elif max_rec_depth == 0:
        append_text_to_file(out_file_path, "Recursion depth limit reached!\n")
        dirs = []
    for entry in dirs:
        try:
            dir_size = get_snapshot(src_path / entry.name, pwd, progress_bar, 
                                    ignore_hidden, ignore_symlinks, max_rec_depth-1)
            source_path_size += dir_size
            write_dir_entry(entry, dir_size, out_file_path)
        except Exception as e:
            print(f"Error while processing directory '{entry}': {e}")
    append_text_to_file(out_file_path, template_table_close)

    # Write symlinks info to table
    if not ignore_symlinks:
        append_text_to_file(out_file_path, template_symlinks_table_header)
        if not symlinks:
            append_text_to_file(out_file_path, "No symlinks found.\n")
        for entry in symlinks:
            try:
                write_symlink_entry(entry, out_file_path, progress_bar)
            except Exception as e:
                print(f"Error while processing directory '{entry}': {e}")
        append_text_to_file(out_file_path, template_table_close)

    # Write the footer
    total_dir_size = round_file_size_to_human_friendly_units(source_path_size)
    append_text_to_file(out_file_path, template_table_footer.format(total_dir_size = total_dir_size))
    progress_bar.update() if progress_bar else None
    return source_path_size


def main():
    args = prepare_args_parser()
    src_path = args['src-path'] # '/Users/ajaggi/Downloads'
    dest_path = args['dest-path'] # '/Users/ajaggi/Desktop/snapshots'
    src_path = Path(src_path).resolve()
    dest_path = Path(dest_path).resolve()
    print('Source directory = "{}"'.format(src_path))
    print('Destination directory = "{}"\n'.format(dest_path))

    if not src_path.exists():
        print(f'ERROR: Source path {src_path.absolute()} does not exist!')

    hide_progress_bar = args['hide_progress_bar']
    dry_run = args['dry_run']
    ignore_hidden = args['ignore_hidden']
    ignore_symlinks = args['ignore_symlinks']
    max_rec_depth = args['max_recursion_depth']

    if tqdm_missing and not hide_progress_bar:
        print('Warning: tqdm package not found! Skipping progress bar')
        hide_progress_bar = True

    progress_bar = None
    if not hide_progress_bar:
        print('Precomputing directory size to populate progress bar properly...')
        source_path_size = get_num_files_in_dir_recursive(src_path, ignore_symlinks, ignore_hidden)
        print(f"Source path size = {source_path_size}")
        progress_bar = tqdm(total=source_path_size,
                        desc='Computing snapshot',
                        unit=' items')

    if dry_run:
        exit(0)

    global dest_path_root
    dest_path_root = dest_path

    get_snapshot(src_path, dest_path, progress_bar, ignore_hidden, ignore_symlinks, max_rec_depth)
    if progress_bar is not None:
        progress_bar.update(source_path_size - progress_bar.n)
        progress_bar.close()


if __name__ == "__main__":
    main()
