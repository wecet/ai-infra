"""Export AI Studio docs as an interlinked Obsidian knowledge graph.

Edit CONFIG or call export(vault_path). No argument parser is used.
"""
import hashlib
import json
import re
import subprocess
from datetime import date
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
CONFIG = {"vault": Path.home() / "Documents" / "Obsidian Vault", "folder": "AI Studio"}
# Source, note title, topic concepts. Keep source documents authoritative.
GUIDES = [
    ('README.md', 'Repository Overview', ['Platform', 'Deployment', 'Authentication']),
    ('docs/README.md', 'Documentation Index', ['Platform']),
    ('docs/platform-overview.md', 'Platform Overview', ['Platform', 'Datasets', 'Training', 'Evaluation']),
    ('src/labelling/README.md', 'Studio Workflow', ['Datasets', 'Annotations', 'Lineage', 'Authentication']),
    ('docs/users-and-repository-access.md', 'Users and Repository Access', ['Authentication', 'Permissions', 'Teams', 'MySQL']),
    ('docs/training-jobs-and-evaluation.md', 'Training Jobs and Evaluation', ['Training', 'Evaluation', 'TensorBoard', 'MLflow']),
    ('docs/workspace-authoring.md', 'Workspace Authoring', ['Workspaces', 'Model Interfaces', 'Configuration', 'Augmentations and Callbacks']),
    ('libs/ai_interfaces/README.md', 'Model Interfaces Guide', ['Model Interfaces', 'Workspaces', 'Configuration']),
    ('tests/README.md', 'PyTorch Demos', ['Workspaces', 'Training', 'Augmentations and Callbacks', 'TensorBoard']),
    ('docs/deployment.md', 'Deployment Guide', ['Deployment', 'MySQL', 'Training']),
    ('docs/configurable-variables.md', 'Environment Variables', ['Configuration', 'Deployment', 'MySQL']),
    ('docs/migration.md', 'Migration and Persistence', ['Deployment', 'MySQL', 'Datasets']),
    ('docs/lakefs-commands.md', 'lakeFS Commands', ['lakeFS', 'Datasets', 'Lineage']),
    ('docs/roadmap.md', 'Product Roadmap', ['Roadmap', 'Platform', 'Training', 'Permissions']),
    ('docs/ui-ux-roadmap.md', 'UI and UX Roadmap', ['Roadmap', 'Platform']),
    ('docs/project-families.md', 'Project Families', ['Roadmap', 'Datasets', 'Anomaly Detection']),
]
CONCEPTS = {
    'Platform': 'AI Studio connects dataset preparation, versioning, training, evaluation and lineage. Vision workflows are available; Language and LLM/VLM are placeholders.',
    'Datasets': 'A published dataset version freezes membership and annotations. Training records the exact train/test membership; saved-model evaluation uses the held-out test partition.',
    'Annotations': 'Classification uses image labels and detection uses bounding boxes. Unsupervised anomaly datasets skip annotation and review requirements.',
    'Anomaly Detection': 'Unsupervised vision datasets have no class labels. Frozen train/test assignments support training and score-based evaluation without claiming labelled accuracy.',
    'Authentication': 'Studio accounts and sessions live in MySQL. A fresh installation creates admin/admin and requires a password change before repository access. Existing credentials are not reset on restart.',
    'Permissions': 'System owners administer users and all repositories. Repository creators own their projects and can share Read/Write access with users or teams. The API enforces access, including downloads and merges.',
    'Teams': 'System owners create teams and manage their membership. Team and direct repository grants combine using the highest available permission.',
    'MySQL': 'MySQL 8.4 stores identities, password hashes, sessions, teams and repository grants. Dataset metadata and image files remain in the existing Studio SQLite/data volume.',
    'Training': 'The compute agent owns execution independently of the browser. Studio restores job phases, metrics, heartbeat and recent logs. An agent process restart interrupts an in-process trainer; checkpoint resume is not implemented.',
    'Evaluation': 'Saved models are evaluated on recorded held-out samples. Results include predictions, task-specific metrics and failure examples; unlabelled anomalies show scores and flags instead of verified failures.',
    'Workspaces': 'A model repository opts into discovery with ai-workbench.json and ai_workbench.py. Its implementation supplies Pydantic configuration plus train, load and predict lifecycle methods.',
    'Model Interfaces': 'Framework-neutral Python abstract classes connect workspaces to Studio. PyTorch and TensorFlow implementations can share the same contracts when their dependencies are installed in the agent.',
    'Configuration': 'Pydantic fields define defaults, validation, descriptions and UI controls. Infrastructure supplies dataset/output paths and identity fields. Callback and augmentation choices belong to the selected workspace.',
    'Augmentations and Callbacks': 'Workspace Enums declare supported callbacks and augmentation keys. The implementation must apply enabled options; a schema declaration alone does not implement them.',
    'TensorBoard': 'TensorBoard displays per-run training metrics and supported visual explanations. Studio links to the selected run; callbacks must exist in the chosen workspace.',
    'MLflow': 'MLflow tracks training runs, configuration, metrics and artifacts. Its direct service endpoint has separate access controls from the Studio portal.',
    'lakeFS': 'Published versions can be pushed to lakeFS for versioned dataset storage. Local publication and a lakeFS commit are distinct events.',
    'Lineage': 'Lineage connects imports, dataset versions, lakeFS commits, training runs, registered models and deployment records. Edge descriptions explain each relationship.',
    'Deployment': 'Compose operates Studio, MySQL, lakeFS, MLflow, the compute agent and TensorBoard. Back up identity, datasets, training artifacts and tracking data together; direct service endpoints need separate access controls.',
    'Roadmap': 'Roadmap notes describe proposed work and acceptance criteria. Implementation updates identify completed slices; proposals are not shipped features or delivery commitments.',
}
MAPS = {
    'Data Workflows': ['Datasets', 'Annotations', 'Anomaly Detection', 'lakeFS', 'Lineage'],
    'Model Development': ['Workspaces', 'Model Interfaces', 'Configuration', 'Augmentations and Callbacks', 'Training', 'Evaluation', 'TensorBoard', 'MLflow'],
    'Operations and Access': ['Deployment', 'Authentication', 'Permissions', 'Teams', 'MySQL'],
    'Product Planning': ['Roadmap', 'Platform'],
}
RELATIONS = {
    'Authentication': ['MySQL', 'Permissions', 'Teams'],
    'Permissions': ['Authentication', 'Teams', 'Datasets'],
    'Training': ['Datasets', 'Workspaces', 'Evaluation', 'TensorBoard', 'MLflow'],
    'Evaluation': ['Datasets', 'Training', 'Model Interfaces'],
    'Workspaces': ['Model Interfaces', 'Configuration', 'Augmentations and Callbacks'],
    'Lineage': ['Datasets', 'lakeFS', 'Training', 'MLflow'],
    'Deployment': ['MySQL', 'Authentication', 'Training'],
}


def note_name(title):
    return f'AI Studio - {title}'


def link(title, label=None):
    return '[[' + note_name(title) + ('|' + label if label else '') + ']]'


def slug(value):
    return re.sub(r'[^a-z0-9]+', '-', value.lower()).strip('-')


def metadata(title, kind, topics, revision, source=None):
    fields = {'title': f'AI Studio — {title}', 'type': kind,
              'tags': ['ai-infra', f'ai-infra/{kind}', *[f'ai-infra/{slug(topic)}' for topic in topics]],
              'updated': date.today().isoformat(), 'source_revision': revision}
    if source:
        fields['source'] = source
        fields['status'] = 'proposal-with-implementation-updates' if 'roadmap' in source or 'project-families' in source else 'documented-behavior'
    return '---\n' + '\n'.join(f'{key}: {json.dumps(value, ensure_ascii=False)}' for key,value in fields.items()) + '\n---\n\n'


def export(vault):
    revision = subprocess.check_output(['git','rev-parse','HEAD'], cwd=ROOT, text=True).strip()
    source_titles = {str((ROOT / source).resolve()): title for source,title,_ in GUIDES}
    notes = {}
    def convert_links(text, source):
        def replace(match):
            label, target = match.groups()
            if re.match(r'^(https?:|mailto:|#)', target): return match.group(0)
            path, _, heading = unquote(target).partition('#')
            resolved = (ROOT / source).parent.joinpath(path).resolve()
            if str(resolved) in source_titles:
                name = note_name(source_titles[str(resolved)])
                # Markdown slug anchors differ from Obsidian heading names; link to the note.
                return f'[[{name}|{label}]]'
            if resolved.exists() and resolved.is_relative_to(ROOT):
                relative = resolved.relative_to(ROOT).as_posix()
                return f'[{label}](https://github.com/wecet/ai-infra/blob/{revision}/{relative}' + (f'#{heading}' if heading else '') + ')'
            return match.group(0)
        # Keep code examples byte-for-byte, including paths and example links.
        pieces = re.split(r'(^```[^\n]*\n.*?^```\s*$)', text, flags=re.M|re.S)
        return ''.join(part if index % 2 else re.sub(r'\[([^\]]+)\]\(([^)]+)\)', replace, part) for index,part in enumerate(pieces))
    for source,title,topics in GUIDES:
        body = convert_links((ROOT / source).read_text(), source)
        header = metadata(title,'guide',topics,revision,source)
        context = f'> Imported from `{source}` at `{revision[:7]}`. Source review dates and proposal labels are preserved.\n\n'
        related = '\n\n## Knowledge graph links\n\n[[AI Studio|Knowledge hub]] · ' + ' · '.join(link(topic) for topic in topics) + '\n'
        notes[f'Guides/{note_name(title)}.md'] = header + context + body + related
    for topic,summary in CONCEPTS.items():
        refs = [(title,source) for source,title,topics in GUIDES if topic in topics]
        body = f'# {topic}\n\n{summary}\n\n## Guides\n\n' + '\n'.join('- '+link(title) for title,_ in refs)
        neighbors = RELATIONS.get(topic, [])
        # Add explicit relationships from neighboring concepts as well.
        neighbors = sorted(set(neighbors + [key for key,values in RELATIONS.items() if topic in values]))
        if neighbors: body += '\n\n## Related concepts\n\n' + ' · '.join(link(item) for item in neighbors)
        body += '\n\n[[AI Studio|Knowledge hub]]\n'
        notes[f'Concepts/{note_name(topic)}.md'] = metadata(topic,'concept',[topic],revision) + body
    for title,topics in MAPS.items():
        guides = [name for _,name,values in GUIDES if set(values)&set(topics)]
        body = f'# {title}\n\n## Concepts\n\n' + ' · '.join(link(topic) for topic in topics)
        body += '\n\n## Documentation\n\n' + '\n'.join('- '+link(name) for name in guides) + '\n\n[[AI Studio|Knowledge hub]]\n'
        notes[f'Maps/{note_name(title)}.md'] = metadata(title,'map',topics,revision) + body
    hub = '# AI Studio\n\nDocumentation and concepts for the AI Infrastructure workspace. Follow a topic map, open a guide, or use backlinks to find related workflows.\n\n## Topic maps\n\n' + '\n'.join('- '+link(title) for title in MAPS)
    hub += '\n\n## All documentation\n\n' + '\n'.join('- '+link(title) for _,title,_ in GUIDES)
    hub += '''\n\n## Search and Graph view\n\n- Search `tag:ai-infra` for all project notes, or `path:"AI Studio"` to scope search to this folder.
- Search `tag:ai-infra/authentication`, `tag:ai-infra/training` or `tag:ai-infra/roadmap` for a topic.
- Open a concept and use **Backlinks** or **Local graph** to see its guides and relationships.
- In Graph view, filter with `path:"AI Studio"`; optionally enable tags and group by `path:"AI Studio/Concepts"` or `path:"AI Studio/Guides"`.
- Imported roadmap proposals retain their original status; check implementation updates before assuming a feature exists.

## Refreshing documentation

The repository remains the source of truth. Run `python3 tools/export_obsidian.py` from the AI Infrastructure checkout to refresh these generated notes. If you edit a generated note, export stops rather than overwriting it. Keep personal commentary in separate notes and link to these notes with wikilinks.
'''
    notes['AI Studio.md'] = metadata('Knowledge Hub','map',['Platform'],revision) + hub
    # Verify every internal link resolves before writing anything.
    names = {Path(path).stem for path in notes}
    for path,content in notes.items():
        for target in re.findall(r'\[\[([^\]|]+)(?:\|[^\]]*)?\]\]', content):
            if target not in names: raise ValueError(f'Unresolved link in {path}: {target}')
    folder = Path(vault) / CONFIG['folder']
    manifest_path = folder / '.ai-studio-export.json'
    if manifest_path.is_symlink(): raise RuntimeError('Export manifest must not be a symlink')
    previous = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    conflicts = []
    for relative in set(notes)|set(previous):
        path = folder / relative
        if not path.resolve().is_relative_to(folder.resolve()) or path.suffix != '.md' or path.is_symlink():
            raise RuntimeError(f'Unsafe export path: {relative}')
        if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() != previous.get(relative): conflicts.append(relative)
    if conflicts: raise RuntimeError('Local notes would be overwritten: ' + ', '.join(sorted(conflicts)))
    for relative,content in notes.items():
        path = folder / relative
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(content)
    for relative in previous.keys()-notes.keys(): (folder/relative).unlink(missing_ok=True)
    manifest_path.write_text(json.dumps({path:hashlib.sha256(content.encode()).hexdigest() for path,content in notes.items()},indent=2)+'\n')
    print(f'Exported {len(GUIDES)} guides, {len(CONCEPTS)} concepts and {len(MAPS)+1} maps to {folder}; all wikilinks resolve.')


if __name__ == '__main__':
    export(CONFIG['vault'])
