import json

from doc_sync.audit import AuditRecord


def test_audit_record_serializes_required_fields(tmp_path):
    record = AuditRecord(triggering_prs=[12], changed_paths=["src/a.py"])
    record.generated_paths = ["docs/a.md"]
    record.complete("success")
    target = tmp_path / "audit.json"
    record.write(target)
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["triggering_prs"] == [12]
    assert data["changed_paths"] == ["src/a.py"]
    assert data["generated_paths"] == ["docs/a.md"]
    assert data["completed_at"]
