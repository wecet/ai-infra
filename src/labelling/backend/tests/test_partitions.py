from services.partitions import freeze, partition


def test_frozen_membership_survives_configuration_change():
    snapshot = {'project': {'annotation_type': 'image_classification', 'export_train_percent': 80}, 'images': [
        {'id': str(i), 'source_path': str(i)} for i in range(20)]}
    freeze(snapshot)
    before = partition(snapshot)
    snapshot['project']['export_train_percent'] = 1
    assert partition(snapshot) == before
    sets = [set(before[key]) for key in ('train', 'validation', 'test')]
    assert all(sets) and not (sets[0] & sets[1] or sets[0] & sets[2] or sets[1] & sets[2])
    assert len(set.union(*sets)) == 20
