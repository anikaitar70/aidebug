"""Code parsing service for multiple programming languages"""

import logging
import re
from typing import List, Optional, Set, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)

# Keywords to exclude when extracting call references
_CALL_KEYWORDS = {
    "if", "for", "while", "return", "raise", "import", "from", "class", "def",
    "async", "await", "try", "except", "finally", "with", "yield", "pass",
    "break", "continue", "elif", "else", "and", "or", "not", "in", "is",
    "function", "const", "let", "var", "new", "typeof", "instanceof", "switch",
    "case", "default", "throw", "catch", "export", "public", "private",
    "protected", "static", "void", "int", "float", "double", "boolean",
    "true", "false", "null", "undefined", "this", "super", "None", "self",
}


class CodeChunk:
    """Represents a parsed code chunk"""

    def __init__(
        self,
        content: str,
        language: str,
        start_line: int,
        end_line: int,
        chunk_type: str = "code",
        function_name: Optional[str] = None,
        class_name: Optional[str] = None,
        chunk_index: int = 0,
        references: Optional[List[str]] = None,
    ):
        self.content = content
        self.language = language
        self.start_line = start_line
        self.end_line = end_line
        self.chunk_type = chunk_type
        self.function_name = function_name
        self.class_name = class_name
        self.chunk_index = chunk_index
        self.references = references or []
        self.imports: List[str] = []

    @property
    def symbol_name(self) -> Optional[str]:
        """Primary symbol defined by this chunk."""
        return self.function_name or self.class_name


class CodeParser:
    """Parse source code into meaningful chunks"""

    LANGUAGE_MAP = {
        '.py': 'python',
        '.js': 'javascript',
        '.jsx': 'javascript',
        '.ts': 'typescript',
        '.tsx': 'typescript',
        '.java': 'java',
        '.cpp': 'cpp',
        '.c': 'c',
        '.go': 'go',
        '.rs': 'rust',
        '.rb': 'ruby',
    }

    _PY_DEF = re.compile(r"^(\s*)(async\s+def|def|class)\s+(\w+)")
    _JS_DEF = re.compile(
        r"^\s*(?:export\s+)?(?:async\s+)?(?:function\s+(\w+)|class\s+(\w+)|"
        r"(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?(?:function|\([^)]*\)\s*=>))"
    )
    _JAVA_DEF = re.compile(
        r"^\s*(?:public|private|protected|static|\s)*"
        r"(?:[\w<>\[\],\s]+)\s+(\w+)\s*\("
    )
    _JAVA_CLASS = re.compile(r"^\s*(?:public|private|protected|\s)*class\s+(\w+)")
    _CALL_PATTERN = re.compile(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\s*\(")

    @staticmethod
    def get_language(filename: str) -> str:
        """Detect language from filename"""
        ext = Path(filename).suffix.lower()
        return CodeParser.LANGUAGE_MAP.get(ext, 'unknown')

    @staticmethod
    def parse_by_functions(
        content: str,
        language: str,
        filename: str,
    ) -> List[CodeChunk]:
        """
        Parse code into function/method/class level chunks.

        Args:
            content: Source code content
            language: Programming language
            filename: Source filename (may include relative path)

        Returns:
            List of code chunks ordered by appearance in file
        """
        lines = content.split('\n')

        if language == 'python':
            chunks = CodeParser._parse_python(lines)
        elif language in ['javascript', 'typescript']:
            chunks = CodeParser._parse_javascript(lines, language)
        elif language == 'java':
            chunks = CodeParser._parse_java(lines)
        else:
            chunks = CodeParser._chunk_by_size(content, lines, language)

        for index, chunk in enumerate(chunks):
            chunk.chunk_index = index
            chunk.references = CodeParser._extract_references(chunk.content)

        file_imports = CodeParser._extract_imports(content, language)
        for chunk in chunks:
            chunk.imports = file_imports

        return chunks

    @staticmethod
    def _extract_imports(content: str, language: str) -> List[str]:
        """Extract import/require statements from file content."""
        imports: List[str] = []
        for line in content.splitlines():
            stripped = line.strip()
            if language == "python":
                if stripped.startswith("import ") or stripped.startswith("from "):
                    imports.append(stripped)
            elif language in ("javascript", "typescript"):
                if stripped.startswith("import ") or "require(" in stripped:
                    imports.append(stripped)
            elif language == "java":
                if stripped.startswith("import "):
                    imports.append(stripped)
        return imports[:30]

    @staticmethod
    def _extract_references(content: str) -> List[str]:
        """Extract function/method call names from chunk content."""
        refs: Set[str] = set()
        for match in CodeParser._CALL_PATTERN.finditer(content):
            name = match.group(1)
            if name not in _CALL_KEYWORDS:
                refs.add(name)
        return sorted(refs)

    @staticmethod
    def _parse_python(lines: List[str]) -> List[CodeChunk]:
        """Parse Python by indentation-aware function/class blocks."""
        boundaries: List[Tuple[int, str, str, Optional[str]]] = []
        current_class: Optional[str] = None

        for i, line in enumerate(lines):
            match = CodeParser._PY_DEF.match(line)
            if not match:
                continue
            kind = match.group(2).strip()
            name = match.group(3)
            if kind == 'class':
                current_class = name
                boundaries.append((i, 'class', name, None))
            else:
                boundaries.append((i, 'function', name, current_class))

        if not boundaries:
            return CodeParser._chunk_by_size('\n'.join(lines), lines, 'python')

        chunks: List[CodeChunk] = []
        for idx, (start_idx, kind, name, enclosing_class) in enumerate(boundaries):
            end_idx = boundaries[idx + 1][0] - 1 if idx + 1 < len(boundaries) else len(lines) - 1
            block_lines = lines[start_idx:end_idx + 1]
            chunk_content = '\n'.join(block_lines)
            if not chunk_content.strip():
                continue
            chunks.append(CodeChunk(
                content=chunk_content,
                language='python',
                start_line=start_idx + 1,
                end_line=end_idx + 1,
                chunk_type=kind,
                function_name=name if kind == 'function' else None,
                class_name=name if kind == 'class' else enclosing_class,
            ))

        return chunks

    @staticmethod
    def _parse_javascript(lines: List[str], language: str) -> List[CodeChunk]:
        """Parse JS/TS by function/class boundaries using brace tracking."""
        boundaries: List[Tuple[int, str, str]] = []

        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped or stripped.startswith('//') or stripped.startswith('/*'):
                continue

            func_match = re.match(
                r"^(?:export\s+)?(?:async\s+)?function\s+(\w+)",
                stripped,
            )
            class_match = re.match(r"^(?:export\s+)?class\s+(\w+)", stripped)
            const_match = re.match(
                r"^(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?",
                stripped,
            )

            if func_match:
                boundaries.append((i, 'function', func_match.group(1)))
            elif class_match:
                boundaries.append((i, 'class', class_match.group(1)))
            elif const_match and ('=>' in stripped or 'function' in stripped):
                boundaries.append((i, 'function', const_match.group(1)))

        if not boundaries:
            return CodeParser._chunk_by_size('\n'.join(lines), lines, language)

        chunks: List[CodeChunk] = []
        for idx, (start_idx, kind, name) in enumerate(boundaries):
            if idx + 1 < len(boundaries):
                end_idx = boundaries[idx + 1][0] - 1
            else:
                end_idx = CodeParser._find_block_end(lines, start_idx)
            block_lines = lines[start_idx:end_idx + 1]
            chunk_content = '\n'.join(block_lines)
            if not chunk_content.strip():
                continue
            chunks.append(CodeChunk(
                content=chunk_content,
                language=language,
                start_line=start_idx + 1,
                end_line=end_idx + 1,
                chunk_type=kind,
                function_name=name if kind == 'function' else None,
                class_name=name if kind == 'class' else None,
            ))

        return chunks

    @staticmethod
    def _find_block_end(lines: List[str], start_idx: int) -> int:
        """Find closing brace for a JS block starting at start_idx."""
        brace_depth = 0
        started = False
        for i in range(start_idx, len(lines)):
            for char in lines[i]:
                if char == '{':
                    brace_depth += 1
                    started = True
                elif char == '}':
                    brace_depth -= 1
                    if started and brace_depth == 0:
                        return i
        return len(lines) - 1

    @staticmethod
    def _parse_java(lines: List[str]) -> List[CodeChunk]:
        """Parse Java methods and classes."""
        boundaries: List[Tuple[int, str, str, Optional[str]]] = []
        current_class: Optional[str] = None

        for i, line in enumerate(lines):
            class_match = CodeParser._JAVA_CLASS.match(line)
            if class_match:
                current_class = class_match.group(1)
                boundaries.append((i, 'class', current_class, None))
                continue

            method_match = CodeParser._JAVA_DEF.match(line)
            if method_match and '(' in line:
                boundaries.append((i, 'method', method_match.group(1), current_class))

        if not boundaries:
            return CodeParser._chunk_by_size('\n'.join(lines), lines, 'java')

        chunks: List[CodeChunk] = []
        for idx, (start_idx, kind, name, enclosing_class) in enumerate(boundaries):
            end_idx = boundaries[idx + 1][0] - 1 if idx + 1 < len(boundaries) else len(lines) - 1
            block_lines = lines[start_idx:end_idx + 1]
            chunk_content = '\n'.join(block_lines)
            if not chunk_content.strip():
                continue
            chunks.append(CodeChunk(
                content=chunk_content,
                language='java',
                start_line=start_idx + 1,
                end_line=end_idx + 1,
                chunk_type=kind,
                function_name=name if kind == 'method' else None,
                class_name=name if kind == 'class' else enclosing_class,
            ))

        return chunks

    @staticmethod
    def _chunk_by_size(content: str, lines: List[str], language: str) -> List[CodeChunk]:
        """Fallback: chunk code by size when structure parsing fails."""
        chunks: List[CodeChunk] = []
        chunk_size = 50

        for i in range(0, len(lines), chunk_size):
            chunk_lines = lines[i:min(i + chunk_size, len(lines))]
            chunk_content = '\n'.join(chunk_lines)

            if chunk_content.strip():
                chunks.append(CodeChunk(
                    content=chunk_content,
                    language=language,
                    start_line=i + 1,
                    end_line=min(i + chunk_size, len(lines)),
                    chunk_type='chunk',
                ))

        return chunks

    @staticmethod
    def build_chunk_metadata(
        chunk: CodeChunk,
        file_id: str,
        file_path: str,
        language: str,
    ) -> dict:
        """Build standardized metadata dict for vector storage."""
        path_obj = Path(file_path)
        return {
            'file_id': file_id,
            'file_path': file_path.replace('\\', '/'),
            'filename': path_obj.name,
            'language': language,
            'start_line': chunk.start_line,
            'end_line': chunk.end_line,
            'chunk_type': chunk.chunk_type,
            'chunk_index': chunk.chunk_index,
            'function_name': chunk.function_name or '',
            'class_name': chunk.class_name or '',
            'imports': ','.join(chunk.imports[:30]),
            'references': ','.join(chunk.references[:50]),
        }

    @staticmethod
    def build_embedding_text(chunk: CodeChunk, file_path: str) -> str:
        """Build enriched text for embedding that includes path and symbol context."""
        parts = [f"File: {file_path}"]
        if chunk.function_name:
            parts.append(f"Function: {chunk.function_name}")
        if chunk.class_name and chunk.class_name != chunk.function_name:
            parts.append(f"Class: {chunk.class_name}")
        if chunk.imports:
            parts.append(f"Imports: {', '.join(chunk.imports[:10])}")
        if chunk.references:
            parts.append(f"Calls: {', '.join(chunk.references[:20])}")
        parts.append(chunk.content)
        return '\n'.join(parts)
