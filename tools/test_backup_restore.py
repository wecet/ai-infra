import hashlib
import io
import json
import tarfile
import pytest
from backup_restore import inspect_backup, restore


def test_backup_rejects_corruption_and_unsafe_members(tmp_path):
    path = tmp_path / 'labelling_data.tar'
    with tarfile.open(path, 'w') as archive:
        info = tarfile.TarInfo('../escape'); info.size = 1
        archive.addfile(info, io.BytesIO(b'x'))
    manifest = {'format': 1, 'volumes': {'labelling_data': {'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}}}
    (tmp_path / 'manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match='Unsafe'): inspect_backup(tmp_path)
    path.write_bytes(b'broken')
    with pytest.raises(ValueError, match='Checksum'): inspect_backup(tmp_path)


def test_safe_extract_roundtrip_and_database_reference_check(tmp_path, monkeypatch):
    import sqlite3
    from pathlib import Path
    from backup_restore import extract_safe, verify_data
    import sys
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'src/labelling/backend'))
    import common
    source = tmp_path / 'source'; source.mkdir()
    monkeypatch.setattr(common, 'DATA', source)
    common.init_db()
    with common.database() as db:
        db.execute("INSERT INTO projects(id,name,classes) VALUES ('p','test','[]')")
        db.execute("INSERT INTO images(id,project_id,source_path,stored_name,digest,width,height) VALUES ('i','p','source.png','i.png','hash',1,1)")
    (source / 'images/p').mkdir(parents=True)
    (source / 'images/p/i.png').write_bytes(b'image')
    archive_path = tmp_path / 'data.tar'
    with tarfile.open(archive_path, 'w') as archive: archive.add(source, arcname='.')
    destination = tmp_path / 'restored'; destination.mkdir()
    with tarfile.open(archive_path) as archive: extract_safe(archive, destination)
    verify_data(destination)
    (destination / 'images/p/i.png').unlink()
    with pytest.raises(ValueError, match='Live image missing'): verify_data(destination)
