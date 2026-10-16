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
