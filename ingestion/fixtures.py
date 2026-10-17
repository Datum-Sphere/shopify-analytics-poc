"""Load reserved synthetic data through the same JSONB upserts; never calls Shopify."""
import json
from pathlib import Path

from ingestion.config import IngestionError
from ingestion.storage import ENTITIES, Repository, connect

FIXTURE_STORE = "financial-fixtures.invalid"
FIXTURE_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "financials.json"


def load_records(repository):
    if not repository.is_synthetic or not repository.store.endswith(".invalid"):
        raise IngestionError("fixtures: only explicitly synthetic .invalid datasets are allowed")
    run_id = repository.start()
    counts = dict.fromkeys(ENTITIES, 0)
    try:
        for record in json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))["records"]:
            repository.upsert(record["entity"], record["payload"], record["parent_source_id"])
            counts[record["entity"]] += 1
        unique_counts = repository.counts()
        repository.finish(run_id, "succeeded", counts)
        return {"dataset": "synthetic", "processed": counts, "unique_records": unique_counts}
    except Exception:
        repository.connection.rollback()
        repository.finish(run_id, "failed", {}, "fixtures: load failed")
        raise IngestionError("fixtures: load failed") from None


def main():
    try:
        with connect() as connection:
            repo = Repository(connection, FIXTURE_STORE, is_synthetic=True)
            repo.initialize()
            print(json.dumps(load_records(repo), sort_keys=True))
    except Exception:
        print('{"status":"failed","error":"fixtures: database/configuration or fixture load failure"}')
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
