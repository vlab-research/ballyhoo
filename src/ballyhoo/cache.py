"""What a render depends on, and whether it must run again.

Pure. The shell reads the files and passes in their contents and digests.
"""
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


def should_render(stored, digest, check=False, force=False):
    """Skip only a normal run whose stored hash matches. --check must render to verify."""
    return check or force or stored != digest
