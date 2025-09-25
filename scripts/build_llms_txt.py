# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

import os

FILE_HEADER = "===== `{filename}` =====\n\n"
FILE_FOOTER = "\n\n===== End of `{filename}` =====\n\n"


def build_llms_txt():
    """
    Build the `llms.txt` file in the project root.
    This works by concatenating all project docs into a single file.
    """
    content = ""

    # start by reading the README.md file
    content += file_content_to_string("README.md")

    # then read all markdown files in the docs directory
    for filename in os.listdir("docs"):
        if filename.endswith(".md"):
            content += file_content_to_string(f"docs/{filename}")

    # write the content to the llms.txt file
    with open("llms.txt", "w") as f:
        f.write(content)


def file_content_to_string(filename: str) -> str:
    """
    Read the content of the given filename and return it as a string.
    """
    with open(filename) as f:
        content = f.read()
        return (
            FILE_HEADER.format(filename=filename)
            + content
            + FILE_FOOTER.format(filename=filename)
        )


if __name__ == "__main__":
    build_llms_txt()
