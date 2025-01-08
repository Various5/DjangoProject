import os


def gather_file_contents(input_dir, output_file):
    """
    Gathers the contents of all .html and .py files in a directory into a single text file,
    excluding the '/venv/', '/migrations/', and '__pycache__' directories.

    Args:
    - input_dir (str): Path to the directory containing the files.
    - output_file (str): Path to the output text file.
    """
    try:
        with open(output_file, 'w', encoding='utf-8') as out_file:
            for root, dirs, files in os.walk(input_dir):
                # Exclude '/venv/', '/migrations/', and '__pycache__' directories
                dirs[:] = [d for d in dirs if d not in {'.venv', 'migrations', '__pycache__', '.git', '.idea'}]

                for file_name in files:
                    if file_name.endswith(('.html', '.py')):
                        file_path = os.path.join(root, file_name)
                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as in_file:
                            # Write file path and content to output file
                            out_file.write(f"{file_path}\n")
                            out_file.write(in_file.read())
                            out_file.write("\n" + "#" * 80 + "\n")  # Separator
        print(f"Contents written to {output_file}")
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    input_directory = input("Enter the directory to scan: ")
    output_txt_file = input("Enter the output text file name (e.g., output.txt): ")
    gather_file_contents(input_directory, output_txt_file)
