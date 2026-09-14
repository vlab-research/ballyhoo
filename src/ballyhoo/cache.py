"""What a render depends on, and whether it must run again.

Pure. The shell reads the files and passes in their contents and digests.
"""
import ast
import hashlib
import re

REF = re.compile(r"""(?:src|href)\s*=\s*["']([^"']+)["']|url\(\s*["']?([^"')]+?)["']?\s*\)""")
NOT_A_FILE = re.compile(r"^(data:|[a-z][a-z0-9+.-]*://|#)", re.IGNORECASE)


def template_refs(source):
    """Local files a template references through src, href or CSS url(): sorted, unique."""
    refs = {(a or b).strip() for a, b in REF.findall(source)}
    return sorted(r for r in refs if r and not NOT_A_FILE.match(r))


def inputs_digest(code, text, template, ref_digests):
    """One hash over everything a render depends on.

    `code` is a digest of ballyhoo's own source, `ref_digests` maps each referenced
    path (as written in the template) to a digest of that file. Every part is
    length-prefixed, so moving characters between parts changes the hash.
    """
    h = hashlib.sha256()
    for part in (code, text, template, *(f"{ref}\0{ref_digests[ref]}" for ref in sorted(ref_digests))):
        data = part.encode()
        h.update(len(data).to_bytes(8, "big"))
        h.update(data)
    return h.hexdigest()


def _relative_imports(path, source):
    """Files within the package that a module's relative imports may load, whether or not they exist."""
    package = path.split("/")[:-1]
    found = set()
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.ImportFrom) or not node.level or node.level - 1 > len(package):
            continue
        target = package[:len(package) - node.level + 1] + (node.module.split(".") if node.module else [])
        found.update("/".join(target[:i] + ["__init__.py"]) for i in range(len(target) + 1))
        if target:
            found.add("/".join(target) + ".py")
        for alias in node.names:  # `from . import fit` names a module; `from .art import file_digest` does not
            found.update(("/".join(target + [alias.name]) + ".py", "/".join(target + [alias.name, "__init__.py"])))
    return found


def code_modules(entry, sources):
    """The package's files that `entry` loads, itself included, following relative imports.

    `sources` maps each file's path within the package ("render.py", "providers/fal.py") to its
    source. The render digest covers only these, so a module rendering never imports (a provider,
    the sourcing shell) can change without re-rendering every study, and one it does import cannot.
    """
    found, todo = set(), [entry]
    while todo:
        path = todo.pop()
        if path not in found and path in sources:
            found.add(path)
            todo += _relative_imports(path, sources[path])
    return sorted(found)


def should_render(stored, digest, check=False, force=False):
    """Skip only a normal run whose stored hash matches. --check must render to verify."""
    return check or force or stored != digest
