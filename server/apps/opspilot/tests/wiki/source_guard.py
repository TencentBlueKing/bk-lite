import ast
from dataclasses import dataclass
from pathlib import Path

ORM_CREATION_METHODS = {
    "create",
    "get_or_create",
    "update_or_create",
    "bulk_create",
}
PLANNED_WIKI_TEST_PATTERNS = (
    "test_directory_*.py",
    "test_generation_*.py",
    "test_structure_*.py",
    "test_wiki_directory_views.py",
)
EXCLUDED_HELPER_FILENAMES = {
    "conftest.py",
    "factories.py",
    "legacy_helpers.py",
    "source_guard.py",
}


@dataclass(frozen=True)
class KnowledgePageCreationViolation:
    path: Path
    line: int
    column: int
    operation: str


def _is_knowledge_page_reference(node):
    return (isinstance(node, ast.Name) and node.id == "KnowledgePage") or (isinstance(node, ast.Attribute) and node.attr == "KnowledgePage")


class _KnowledgePageCreationVisitor(ast.NodeVisitor):
    def __init__(self, path):
        self.path = Path(path)
        self.violations = []

    def visit_Call(self, node):
        operation = None
        if _is_knowledge_page_reference(node.func):
            operation = "constructor"
        elif isinstance(node.func, ast.Attribute) and node.func.attr in ORM_CREATION_METHODS:
            manager = node.func.value
            if isinstance(manager, ast.Attribute) and manager.attr == "objects" and _is_knowledge_page_reference(manager.value):
                operation = f"objects.{node.func.attr}"

        if operation is not None:
            self.violations.append(
                KnowledgePageCreationViolation(
                    path=self.path,
                    line=node.lineno,
                    column=node.col_offset,
                    operation=operation,
                )
            )
        self.generic_visit(node)


def find_knowledge_page_creation_violations(source, filename="<memory>"):
    tree = ast.parse(source, filename=str(filename))
    visitor = _KnowledgePageCreationVisitor(filename)
    visitor.visit(tree)
    return visitor.violations


def is_planned_wiki_test_path(path):
    path = Path(path)
    if path.name in EXCLUDED_HELPER_FILENAMES:
        return False
    return any(path.match(pattern) for pattern in PLANNED_WIKI_TEST_PATTERNS)


def _iter_planned_wiki_tests(test_directory):
    test_directory = Path(test_directory)
    for path in sorted(test_directory.glob("*.py")):
        if is_planned_wiki_test_path(path):
            yield path


def scan_planned_wiki_tests(test_directory=None):
    root = Path(test_directory) if test_directory is not None else Path(__file__).parent
    violations = []
    for path in _iter_planned_wiki_tests(root):
        violations.extend(
            find_knowledge_page_creation_violations(
                path.read_text(encoding="utf-8"),
                filename=path,
            )
        )
    return violations
