"""`ballyhoo provenance made`: files only, no browser."""
import yaml
from PIL import Image

from ballyhoo import art, provenance
from ballyhoo.cli import main


def image(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 8), (10, 20, 30)).save(path)
    return path


def test_made_writes_a_valid_sidecar_for_each_image(tmp_path, capsys):
    a, b = image(tmp_path / "characters" / "a.png"), image(tmp_path / "scenes" / "b.jpg")
    assert main(["provenance", "made", str(a), str(b), "--by", "The partner's designer", "--rights", "Made for us"]) == 0
    record = yaml.safe_load(art.sidecar(b).read_text())
    assert record == provenance.made(art.file_digest(b), "The partner's designer", "Made for us")
    assert provenance.problems(record, art.file_digest(b)) == []
    assert art.sidecar(a).exists()


def test_made_writes_nothing_if_any_image_cannot_have_provenance(tmp_path, capsys):
    a, b = image(tmp_path / "a.png"), image(tmp_path / "b.png")
    art.write_sidecar(b, {"source": "stock"})
    font = tmp_path / "Hind-Bold.ttf"
    font.write_bytes(b"not an image")
    assert main(["provenance", "made", str(a), str(b), str(font), str(tmp_path / "gone.png"),
                 "--by", "x", "--rights", "y"]) == 1
    assert not art.sidecar(a).exists()
    assert yaml.safe_load(art.sidecar(b).read_text()) == {"source": "stock"}
    assert capsys.readouterr().out.splitlines() == [
        f"FAIL  {b}: already has provenance; edit or delete b.png.provenance.yaml by hand",
        f"FAIL  {font}: not an image",
        f"FAIL  {tmp_path / 'gone.png'}: no such file",
    ]
