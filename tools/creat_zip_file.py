#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
根据 txt 文件中的路径列表打包 zip。

特点：
1. txt 中每一行是一个文件路径
2. zip 中不保留目录结构
3. zip 中的文件名会带上原路径信息，用下划线连接
"""

import argparse
import re
import zipfile
from pathlib import Path


def read_file_list(txt_path: str) -> list[Path]:
    """
    读取 txt 文件中的文件路径列表。
    支持空行、注释行。
    """
    paths = []

    with open(txt_path, "r", encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()

            if not line:
                continue

            if line.startswith("#"):
                continue

            paths.append(Path(line))

    return paths


def make_flat_filename(path: Path) -> str:
    """
    把路径转换成 zip 里的扁平文件名。

    例如：
    src/stock_quant_v2/scripts/demo.py

    转成：
    src_stock_quant_v2_scripts_demo.py
    """
    path_str = str(path)

    # 统一 Windows 和 Linux / macOS 路径分隔符
    path_str = path_str.replace("\\", "/")

    # 去掉开头多余的 ./ 或 /
    path_str = path_str.lstrip("./").lstrip("/")

    # 把路径中的非法或不方便的字符替换成下划线
    filename = re.sub(r'[\\/:\*\?"<>\|]+', "_", path_str)

    return filename


def ensure_unique_name(filename: str, used_names: set[str]) -> str:
    """
    避免 zip 里出现重名文件。
    如果重名，自动追加 _2、_3。
    """
    if filename not in used_names:
        used_names.add(filename)
        return filename

    file_path = Path(filename)
    stem = file_path.stem
    suffix = file_path.suffix

    index = 2
    while True:
        new_name = f"{stem}_{index}{suffix}"
        if new_name not in used_names:
            used_names.add(new_name)
            return new_name
        index += 1


def zip_files_from_txt(
    txt_path: str,
    output_zip: str,
    base_dir: str = ".",
) -> None:
    """
    根据 txt 文件中的路径列表打包 zip。
    """
    txt_path_obj = Path(txt_path).resolve()
    output_zip_path = Path(output_zip).resolve()
    base_path = Path(base_dir).resolve()

    file_paths = read_file_list(str(txt_path_obj))

    output_zip_path.parent.mkdir(parents=True, exist_ok=True)

    missing_files = []
    skipped_files = []
    used_names = set()

    with zipfile.ZipFile(
        output_zip_path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
    ) as zipf:
        for listed_path in file_paths:
            full_path = base_path / listed_path

            if not full_path.exists():
                missing_files.append(str(listed_path))
                continue

            if not full_path.is_file():
                skipped_files.append(str(listed_path))
                continue

            arcname = make_flat_filename(listed_path)
            arcname = ensure_unique_name(arcname, used_names)

            zipf.write(full_path, arcname=arcname)

            print(f"已添加：{listed_path}")
            print(f"  -> zip 文件名：{arcname}")

    print("\n打包完成")
    print(f"输出文件：{output_zip_path}")

    if missing_files:
        print("\n以下文件不存在，已跳过：")
        for file in missing_files:
            print(f"- {file}")

    if skipped_files:
        print("\n以下路径不是文件，已跳过：")
        for file in skipped_files:
            print(f"- {file}")


def main():
    parser = argparse.ArgumentParser(
        description="根据 txt 文件中的文件路径列表打包 zip，并把路径拼到文件名中"
    )

    parser.add_argument(
        "txt",
        help="包含文件路径列表的 txt 文件，例如 tools/files.txt",
    )

    parser.add_argument(
        "-o",
        "--output",
        default="selected_files.zip",
        help="输出 zip 文件路径，默认 selected_files.zip",
    )

    parser.add_argument(
        "--base-dir",
        default=".",
        help="项目根目录，默认当前目录",
    )

    args = parser.parse_args()

    zip_files_from_txt(
        txt_path=args.txt,
        output_zip=args.output,
        base_dir=args.base_dir,
    )


if __name__ == "__main__":
    main()