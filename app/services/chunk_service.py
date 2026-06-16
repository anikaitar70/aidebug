"""Simple code chunking service for extracted source files."""

from pathlib import Path
from typing import Dict, Iterable, List

TEXT_CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".cpp", ".cc", ".c", ".h", ".hpp",
    ".go", ".rs", ".rb", ".php", ".swift", ".kt", ".kts", ".scala",
    ".pl", ".sh", ".bash", ".yaml", ".yml", ".json", ".xml", ".html",
    ".css", ".sql", ".md", ".txt",
}

DEFAULT_MIN_LINES = 300
DEFAULT_MAX_LINES = 500


def is_text_code_file(path: Path) -> bool:
    """Return True if the file is a supported text-based code file."""
    return path.is_file() and path.suffix.lower() in TEXT_CODE_EXTENSIONS


def _read_text_file(path: Path) -> str:
    """Read a file as UTF-8 text, falling back to latin-1 on decode errors."""
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="latin-1", errors="ignore")


def _language_from_suffix(path: Path) -> str:
    """Infer a simple language label from file extension."""
    return path.suffix.lower().lstrip('.') or 'text'


def _block_marker_patterns(language: str) -> List[str]:
    """Return line-start markers for common code block boundaries."""
    language = language.lower()
    if language == 'py' or language == 'python':
        return ['def ', 'class ', '@']
    if language in {'js', 'ts', 'jsx', 'tsx'}:
        return ['function ', 'class ', 'const ', 'let ', 'var ', 'async ', 'export ', 'import ']  # import tends to start groups
    if language == 'java':
        return ['class ', 'interface ', 'enum ', 'public ', 'private ', 'protected ', '@']
    if language in {'c', 'cpp', 'cc', 'h', 'hpp'}:
        return ['#include', 'struct ', 'class ', 'enum ', 'typedef ', 'void ', 'int ', 'float ', 'double '] 
    if language == 'go':
        return ['func ', 'package ', 'import ']
    if language == 'rs' or language == 'rust':
        return ['fn ', 'struct ', 'enum ', 'impl ', 'mod ', 'trait ']
    if language == 'rb' or language == 'ruby':
        return ['def ', 'class ', 'module ', 'require ', 'include ']
    if language == 'php':
        return ['function ', 'class ', 'interface ', 'namespace ', 'use ']
    if language in {'swift', 'kt', 'kts', 'scala'}:
        return ['func ', 'class ', 'struct ', 'interface ', 'object ', 'package ', 'import ']
    return ['class ', 'def ', 'function ', 'import ', 'package ', 'namespace ', 'struct ', 'interface ', 'module ']


def _chunk_lines(lines: List[str], max_lines: int) -> List[str]:
    """Split lines into fixed-size chunks."""
    return [
        '\n'.join(lines[i:i + max_lines])
        for i in range(0, len(lines), max_lines)
        if lines[i:i + max_lines]
    ]


def _split_into_blocks(lines: List[str], language: str) -> List[List[str]]:
    """Group lines into blocks based on simple block markers."""
    markers = _block_marker_patterns(language)
    blocks: List[List[str]] = []
    current_block: List[str] = []

    for raw_line in lines:
        line = raw_line.strip()
        if line and any(line.startswith(marker) for marker in markers):
            if current_block:
                blocks.append(current_block)
            current_block = [raw_line]
        else:
            current_block.append(raw_line)

    if current_block:
        blocks.append(current_block)

    return blocks


def _combine_blocks(blocks: List[List[str]], min_lines: int, max_lines: int) -> List[str]:
    """Combine block groups into chunks respecting size bounds."""
    combined: List[str] = []
    current: List[str] = []
    current_count = 0

    for block in blocks:
        block_count = len(block)
        if current_count + block_count > max_lines and current:
            combined.append('\n'.join(current))
            current = []
            current_count = 0

        if block_count > max_lines:
            # A single block is already too large; split it by size.
            for slice_start in range(0, block_count, max_lines):
                combined.append('\n'.join(block[slice_start:slice_start + max_lines]))
            continue

        current.extend(block)
        current_count += block_count

        if current_count >= min_lines:
            combined.append('\n'.join(current))
            current = []
            current_count = 0

    if current:
        combined.append('\n'.join(current))

    return combined


def read_and_chunk_code_files(
    directory: str,
    min_lines: int = DEFAULT_MIN_LINES,
    max_lines: int = DEFAULT_MAX_LINES,
) -> List[Dict[str, object]]:
    """Read text-based code files and split them into metadata-rich chunks."""
    root = Path(directory)
    results: List[Dict[str, object]] = []

    if not root.exists() or not root.is_dir():
        return results

    file_paths = sorted([path for path in root.rglob('*') if is_text_code_file(path)])
    chunk_index = 0

    for path in file_paths:
        content = _read_text_file(path)
        lines = content.splitlines()
        language = _language_from_suffix(path)

        if len(lines) <= max_lines:
            chunks = [content] if content.strip() else []
        else:
            blocks = _split_into_blocks(lines, language)
            chunks = _combine_blocks(blocks, min_lines, max_lines)
            if not chunks:
                chunks = _chunk_lines(lines, max_lines)

        for index, chunk_text in enumerate(chunks):
            if not chunk_text.strip():
                continue
            results.append({
                'content': chunk_text,
                'metadata': {
                    'file_name': path.name,
                    'file_path': str(path),
                    'chunk_index': index,
                }
            })
            chunk_index += 1

    return results


def read_files(directory: str) -> List[Dict[str, object]]:
    """Read all supported code files and return raw file contents with metadata."""
    root = Path(directory)
    results: List[Dict[str, object]] = []

    if not root.exists() or not root.is_dir():
        return results

    for path in sorted(root.rglob('*')):
        if not is_text_code_file(path):
            continue

        content = _read_text_file(path)
        if not content.strip():
            continue

        results.append({
            'content': content,
            'metadata': {
                'file_name': path.name,
                'file_path': str(path),
                'chunk_index': 0,
            }
        })

    return results
