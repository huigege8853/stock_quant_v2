from pathlib import Path
import re
from dataclasses import dataclass


# True = 只预演，不实际创建
DRY_RUN = False

# 树文本文件路径（相对于当前脚本）
TREE_FILE = Path(__file__).resolve().with_name("models_tree_M9_1_1.txt")

# 自动生成的对比报告
COMPARE_FILE = Path(__file__).resolve().with_name("project_tree_compare.md")


@dataclass
class Stats:
    created_dirs: int = 0
    skipped_dirs: int = 0
    created_files: int = 0
    skipped_files: int = 0


def read_tree_text(tree_file: Path) -> str:
    if not tree_file.exists():
        raise FileNotFoundError(f"树文件不存在: {tree_file}")
    return tree_file.read_text(encoding="utf-8")


def parse_tree_lines(tree_text: str):
    lines = [line.rstrip("\n") for line in tree_text.splitlines() if line.strip()]
    if not lines:
        raise ValueError("树文本为空")
    return lines


def resolve_root(project_root: Path, root_line: str) -> Path:
    """
    支持以下根写法：
    - ./
    - .
    - /
    - root/
    - project_root/
    - 其它目录名（相对于项目根）
    """
    token = root_line.strip()

    if token in {".", "./", "/", "root", "root/", "project_root", "project_root/"}:
        return project_root

    if token.endswith("/"):
        token = token[:-1].strip()

    if not token:
        return project_root

    root = project_root / token

    # 防呆：避免当前项目目录名又被套一层
    if root.name == project_root.name and root != project_root:
        raise ValueError(
            "检测到重复项目根目录嵌套。\n"
            f"project_root = {project_root}\n"
            f"resolved root = {root}\n"
            "很可能是 models_tree_M9_1_1.txt 第一行写成了项目名目录，"
            "但脚本又默认以当前项目根为基准拼接，导致出现 project/project/... 套娃。\n"
            "如果你想直接在当前项目根下创建，请把第一行改成 ./"
        )

    return root


def get_level_and_name(line: str):
    """
    解析一行树文本，返回:
    - level: 层级（根下面第一层目录/文件为 1）
    - name: 节点名字
    - is_dir: 是否目录
    """
    m = re.match(r"^((?:│   |    )*)([├└]── )(.+)$", line)
    if not m:
        raise ValueError(f"无法解析这一行，请检查缩进和树符号格式:\n{line}")

    indent_part = m.group(1)
    name = m.group(3).strip()
    level = len(indent_part) // 4 + 1
    is_dir = name.endswith("/")

    if is_dir:
        name = name[:-1].strip()

    if not name:
        raise ValueError(f"空名称节点，原始行:\n{line}")

    return level, name, is_dir

def collect_target_nodes(lines, root: Path):
    """
    从树文本中收集“目标应存在”的目录/文件集合
    """
    expected_dirs = set()
    expected_files = set()

    stack = {0: root}

    for raw_line in lines[1:]:
        level, name, is_dir = get_level_and_name(raw_line)

        parent = stack.get(level - 1)
        if parent is None:
            raise ValueError(
                f"层级断裂，找不到父目录。"
                f"\nline: {raw_line}\nlevel: {level}\nknown stack: {stack}"
            )

        current = parent / name

        if is_dir:
            expected_dirs.add(current)
            stack[level] = current

            deeper_levels = [k for k in list(stack.keys()) if k > level]
            for k in deeper_levels:
                del stack[k]
        else:
            expected_files.add(current)

    return expected_dirs, expected_files


def collect_actual_nodes(root: Path):
    actual_dirs = set()
    actual_files = set()

    if not root.exists():
        return actual_dirs, actual_files

    for p in root.rglob("*"):
        if p.is_dir():
            actual_dirs.add(p)
        elif p.is_file():
            actual_files.add(p)

    return actual_dirs, actual_files


def collect_actual_tree_text(root: Path) -> str:
    if not root.exists():
        return f"{root.as_posix()}/\n(目录不存在)"

    lines = [f"{root.as_posix()}/"]

    def walk(path: Path, prefix: str = ""):
        items = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        for idx, item in enumerate(items):
            is_last = idx == len(items) - 1
            branch = "└── " if is_last else "├── "
            name = item.name + ("/" if item.is_dir() else "")
            lines.append(f"{prefix}{branch}{name}")

            if item.is_dir():
                extension = "    " if is_last else "│   "
                walk(item, prefix + extension)

    walk(root)
    return "\n".join(lines)


def to_project_relative(path: Path, project_root: Path) -> str:
    try:
        return path.relative_to(project_root).as_posix()
    except ValueError:
        return path.as_posix()


def create_tree(tree_text: str, dry_run: bool = False):
    project_root = Path(__file__).resolve().parents[1]
    lines = parse_tree_lines(tree_text)
    root = resolve_root(project_root, lines[0])

    stats = Stats()
    created_dirs = []
    created_files = []

    print(f"Tree file: {TREE_FILE}")
    print(f"Project root: {project_root}")
    print(f"Root line: {lines[0]}")
    print(f"Resolved root: {root}")
    print(f"Mode: {'DRY_RUN' if dry_run else 'APPLY'}")
    print("-" * 60)

    if root == project_root:
        print(f"[ROOT] using current project root: {root}")
    else:
        if root.exists():
            if not root.is_dir():
                raise ValueError(f"根路径已存在但不是目录: {root}")
            print(f"[DIR ] skip    {root}")
            stats.skipped_dirs += 1
        else:
            print(f"[DIR ] create  {root}")
            if not dry_run:
                root.mkdir(parents=True, exist_ok=True)
            created_dirs.append(root)
            stats.created_dirs += 1

    stack = {0: root}

    for raw_line in lines[1:]:
        level, name, is_dir = get_level_and_name(raw_line)

        parent = stack.get(level - 1)
        if parent is None:
            raise ValueError(
                f"层级断裂，找不到父目录。"
                f"\nline: {raw_line}\nlevel: {level}\nknown stack: {stack}"
            )

        current = parent / name

        if is_dir:
            if current.exists():
                if not current.is_dir():
                    raise ValueError(f"路径已存在但不是目录: {current}")
                print(f"[DIR ] skip    {current}")
                stats.skipped_dirs += 1
            else:
                print(f"[DIR ] create  {current}")
                if not dry_run:
                    current.mkdir(parents=True, exist_ok=True)
                created_dirs.append(current)
                stats.created_dirs += 1

            stack[level] = current

            deeper_levels = [k for k in list(stack.keys()) if k > level]
            for k in deeper_levels:
                del stack[k]

        else:
            if current.exists():
                if not current.is_file():
                    raise ValueError(f"路径已存在但不是文件: {current}")
                print(f"[FILE] skip    {current}")
                stats.skipped_files += 1
            else:
                print(f"[FILE] create  {current}")
                if not dry_run:
                    current.parent.mkdir(parents=True, exist_ok=True)
                    current.touch(exist_ok=True)
                created_files.append(current)
                stats.created_files += 1

    expected_dirs, expected_files = collect_target_nodes(lines, root)
    actual_dirs, actual_files = collect_actual_nodes(root)

    missing_dirs = sorted(expected_dirs - actual_dirs, key=lambda p: p.as_posix())
    missing_files = sorted(expected_files - actual_files, key=lambda p: p.as_posix())

    extra_dirs = sorted(actual_dirs - expected_dirs, key=lambda p: p.as_posix())
    extra_files = sorted(actual_files - expected_files, key=lambda p: p.as_posix())

    print("-" * 60)
    print("Summary:")
    print(f"  created dirs : {stats.created_dirs}")
    print(f"  skipped dirs : {stats.skipped_dirs}")
    print(f"  created files: {stats.created_files}")
    print(f"  skipped files: {stats.skipped_files}")
    print(f"  missing dirs after run : {len(missing_dirs)}")
    print(f"  missing files after run: {len(missing_files)}")
    print(f"  extra dirs in actual   : {len(extra_dirs)}")
    print(f"  extra files in actual  : {len(extra_files)}")

    return {
        "project_root": project_root,
        "root": root,
        "stats": stats,
        "created_dirs": created_dirs,
        "created_files": created_files,
        "missing_dirs": missing_dirs,
        "missing_files": missing_files,
        "extra_dirs": extra_dirs,
        "extra_files": extra_files,
    }


def _to_md_list(paths, project_root: Path, empty_text: str):
    if not paths:
        return empty_text
    return "\n".join(f"- {to_project_relative(p, project_root)}" for p in paths)


def generate_compare_report(
    tree_text: str,
    result: dict,
    compare_file: Path,
    dry_run: bool,
):
    project_root = result["project_root"]
    root = result["root"]
    stats = result["stats"]

    created_dirs = result["created_dirs"]
    created_files = result["created_files"]
    missing_dirs = result["missing_dirs"]
    missing_files = result["missing_files"]
    extra_dirs = result["extra_dirs"]
    extra_files = result["extra_files"]

    actual_tree_text = collect_actual_tree_text(root)

    status_apply = "x" if not dry_run else " "
    status_clean = "x" if (not missing_dirs and not missing_files) else " "
    status_exact = "x" if (
        not missing_dirs and not missing_files and not extra_dirs and not extra_files
    ) else " "

    created_dirs_md = _to_md_list(created_dirs, project_root, "本次未创建目录。")
    created_files_md = _to_md_list(created_files, project_root, "本次未创建文件。")
    missing_dirs_md = _to_md_list(missing_dirs, project_root, "无缺失目录。")
    missing_files_md = _to_md_list(missing_files, project_root, "无缺失文件。")
    extra_dirs_md = _to_md_list(extra_dirs, project_root, "无多余目录。")
    extra_files_md = _to_md_list(extra_files, project_root, "无多余文件。")

    compare_scope = (
        f"{to_project_relative(root, project_root)}/"
        if root != project_root
        else "./"
    )

    content = f"""# Project Tree Compare

    ## Compare Scope

    ```text
    {compare_scope}
    ```
    ## Target Tree
    ```text
    {tree_text.strip()}
    ```
    ## Actual Tree
    ```text
    {actual_tree_text}
    ```
    
    ## Run Mode
    ```text
    {"DRY_RUN" if dry_run else "APPLY"}
    ```
    ## Summary
    ```text
    created dirs: {stats.created_dirs}
    skipped dirs: {stats.skipped_dirs}
    created files: {stats.created_files}
    skipped files: {stats.skipped_files}
    ```
    ## Created Directories
    ```text
    {created_dirs_md}
    ```
    ## Created Files
    ```text
    {created_files_md}
    ```   
    ## Missing Directories After Run
    ```text
    {missing_dirs_md}
    ```     
    ## Missing Files After Run
    ```text
    {missing_files_md}
    ```  
    ## Extra Directories In Actual Tree
    ```text
    {extra_dirs_md}
    ```
    ## Extra Files In Actual Tree
    ```text
    {extra_files_md}
    ```
    ## Status
    ```text
    已完成对比
    [{status_apply}] 已正式创建文件
    [{status_clean}] 目标树已补齐
    [{status_exact}] 实际树与目标树完全一致
        ```
    ## Notes
    ```text
    该文件由 tools/create_from_tree.py 自动生成
    Target Tree 来自 tools/models_tree_M9_1_1.txt
    Actual Tree 为当前磁盘实际目录结构快照
    Missing * After Run 表示执行完成后，目标里仍不存在的项
    Extra * In Actual Tree 表示实际存在、但目标树未声明的项
    ```
"""
    compare_file.write_text(content, encoding="utf-8")
    print("-" * 60)
    print(f"Compare report written to: {compare_file}")

if __name__ == "__main__":
    tree_text = read_tree_text(TREE_FILE)
    result = create_tree(tree_text, dry_run=DRY_RUN)
    generate_compare_report(
        tree_text=tree_text,
        result=result,
        compare_file=COMPARE_FILE,
        dry_run=DRY_RUN,
    )

    

    
