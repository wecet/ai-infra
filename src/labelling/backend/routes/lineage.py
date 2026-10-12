"""Project lineage graph spanning datasets, tracking, models, and deployments."""
import json
import os

from fastapi import APIRouter

from common import database, get_project

router = APIRouter()
LAKEFS_PUBLIC_URL = os.environ.get("LAKEFS_PUBLIC_URL", "http://localhost:8002").rstrip("/")
MLFLOW_PUBLIC_URL = os.environ.get("MLFLOW_PUBLIC_URL", "http://localhost:5001").rstrip("/")


def _mlflow_url(value):
    if not value: return None
    experiment, run = value.split(":", 1) if ":" in value else ("0", value)
    return f"{MLFLOW_PUBLIC_URL}/#/experiments/{experiment}/runs/{run}"


@router.get("/api/projects/{project_id}/lineage")
def project_lineage(project_id: str):
    with database() as db:
        project = get_project(db, project_id)
        batches = db.execute('''SELECT id,kind,created_at,sample_count,details FROM import_batches
            WHERE project_id=? ORDER BY created_at,rowid''', (project_id,)).fetchall()
        versions = db.execute('''SELECT id,name,sample_count,created_at FROM dataset_versions
            WHERE project_id=? ORDER BY version_number''', (project_id,)).fetchall()
        commits = db.execute('''SELECT * FROM lakefs_commits WHERE project_id=? ORDER BY created_at,rowid''',
                             (project_id,)).fetchall()
        jobs = db.execute('''SELECT id,version_id,base_model,run_name,status,mlflow_run_id,created_at,completed_at
            FROM training_jobs WHERE project_id=? ORDER BY created_at,rowid''', (project_id,)).fetchall()
        models = db.execute('''SELECT * FROM registered_models WHERE project_id=? ORDER BY created_at,rowid''',
                            (project_id,)).fetchall()
        deployments = db.execute('''SELECT * FROM model_deployments WHERE project_id=? ORDER BY created_at,rowid''',
                                 (project_id,)).fetchall()
    nodes = [{"id": f"project:{project_id}", "type": "project", "title": project["name"],
              "subtitle": project["annotation_type"].replace("_", " "), "created_at": project["created_at"],
              "target": {"kind": "project"}}]
    edges = []
    previous = f"project:{project_id}"
    for index, row in enumerate(batches, 1):
        details = json.loads(row["details"] or "[]")
        sample_count = row["sample_count"] if row["sample_count"] is not None else len(details)
        node_id = f"batch:{row['id']}"
        labels = {"project_created": "Project created", "new_additions": "Import batch",
                  "images_deleted": "Images deleted", "images_restored": "Images restored",
                  "projects_merged": "Projects merged"}
        nodes.append({"id": node_id, "type": "batch", "subtype": row["kind"],
                      "title": labels.get(row["kind"], row["kind"].replace("_", " ").title()),
                      "subtitle": f"{sample_count or 0} image{'s' if sample_count != 1 else ''}",
                      "created_at": row["created_at"], "target": {"kind": "history", "id": row["id"]}})
        edges.append({"from": previous, "to": node_id}); previous = node_id
    for row in versions:
        node_id = f"version:{row['id']}"
        nodes.append({"id": node_id, "type": "version", "title": row["name"],
                      "subtitle": f"{row['sample_count']} frozen samples", "created_at": row["created_at"],
                      "target": {"kind": "version", "id": row["id"]}})
        candidates = [node for node in nodes if node["type"] == "batch" and node["created_at"] <= row["created_at"]]
        edges.append({"from": candidates[-1]["id"] if candidates else f"project:{project_id}", "to": node_id})
    for row in commits:
        node_id = f"lakefs:{row['id']}"
        nodes.append({"id": node_id, "type": "lakefs", "title": f"lakeFS {row['commit_id'][:10]}",
                      "subtitle": f"{row['repository']}/{row['branch']}", "created_at": row["created_at"],
                      "target": {"kind": "external", "url": f"{LAKEFS_PUBLIC_URL}/repositories/{row['repository']}/commits/{row['commit_id']}"}})
        edges.append({"from": f"version:{row['version_id']}", "to": node_id})
    for row in jobs:
        node_id = f"training:{row['id']}"
        nodes.append({"id": node_id, "type": "training", "title": row["run_name"] or row["base_model"],
                      "subtitle": f"Training {row['status']}", "status": row["status"],
                      "created_at": row["created_at"],
                      "target": {"kind": "external", "url": _mlflow_url(row["mlflow_run_id"])}
                                if row["mlflow_run_id"] else {"kind": "training", "id": row["id"]}})
        edges.append({"from": f"version:{row['version_id']}", "to": node_id})
        # A commit is a mirror of the frozen version, not the trainer's input source.
        for commit in commits:
            if commit["version_id"] == row["version_id"]:
                edges.append({"from": f"lakefs:{commit['id']}", "to": node_id, "kind": "snapshot"})
    for row in models:
        node_id = f"model:{row['id']}"
        nodes.append({"id": node_id, "type": "model", "title": row["name"],
                      "subtitle": f"Registered model v{row['model_version']}", "created_at": row["created_at"],
                      "target": {"kind": "model", "id": row["id"]}})
        edges.append({"from": f"training:{row['training_job_id']}", "to": node_id})
    for row in deployments:
        node_id = f"deployment:{row['id']}"
        target = {"kind": "external", "url": row["endpoint"]} if row["endpoint"] else {"kind": "training"}
        nodes.append({"id": node_id, "type": "deployment", "title": row["name"],
                      "subtitle": f"{row['environment']} · {row['status']}", "status": row["status"],
                      "created_at": row["created_at"], "target": target})
        edges.append({"from": f"model:{row['registered_model_id']}", "to": node_id})
    return {"nodes": nodes, "edges": edges, "counts": {
        "batches": len(batches), "versions": len(versions), "lakefs_commits": len(commits),
        "training_runs": len(jobs), "registered_models": len(models), "deployments": len(deployments)}}
