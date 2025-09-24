# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

import os


def build_llms_txt():
    """
    Build the `llms.txt` file in the project root.
    This works by concatenating all project docs into a single file.
    """
    content = ""

    # start by reading the README.md file
    with open("README.md") as f:
        content += create_file_header("README.md")
        content += f.read()
        content += create_file_footer("README.md")
    
    # then read all markdown files in the docs directory
    for filename in os.listdir("docs"):
        if filename.endswith(".md"):
            with open(f"docs/{filename}") as f:
                content += create_file_header(f'docs/{filename}')
                content += f.read()
                content += create_file_footer(f'docs/{filename}')
    
    # write the content to the llms.txt file
    with open("llms.txt", "w") as f:
        f.write(content)

def create_file_header(filename: str) -> str:
    """
    Create a file header for the given filename.
    """
    return f"===== `{filename}` =====\n\n"

def create_file_footer(filename: str) -> str:
    """
    Create a file footer for the given filename.
    """
    return f"\n\n===== End of `{filename}` =====\n\n"

if __name__ == "__main__":
    build_llms_txt()